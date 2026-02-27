# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import threading

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import html2plaintext

from ..services.weaviate_service import WeaviateService

_logger = logging.getLogger(__name__)

# Thread-local store for Weaviate search scores.
# Populated by _search() so that the weaviate_search_score computed field can
# read the score for each record within the same HTTP request/worker thread.
_weaviate_scores = threading.local()

# Fields on product.template that, when changed, require a Weaviate resync.
_WATCHED_FIELDS = frozenset(
    {
        "name",
        "description",
        "description_sale",
        "default_code",
        "barcode",
        "categ_id",
        "list_price",
        "active",
        # website_description is added by website_sale — checked at runtime via getattr
        "website_description",
    }
)


def _is_live_sync_enabled(env):
    return (
        env["ir.config_parameter"]
        .sudo()
        .get_param("product_weaviate_search.live_sync_enabled", "True")
        == "True"
    )


def _is_backend_search_enabled(env):
    # Context key takes priority — set by the search panel filters in the list view.
    ctx_override = env.context.get("weaviate_search")
    if ctx_override is not None:
        return bool(ctx_override)
    return (
        env["ir.config_parameter"]
        .sudo()
        .get_param("product_weaviate_search.backend_search_enabled", "False")
        == "True"
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    weaviate_uuid = fields.Char(
        string="Weaviate UUID",
        copy=False,
        index=True,
        readonly=True,
        groups="base.group_system",
        help="UUID of this product in the Weaviate vector database.",
    )
    weaviate_search_score = fields.Float(
        string="Weaviate Score",
        compute="_compute_weaviate_search_score",
        digits=(16, 4),
        help=(
            "Hybrid search relevance score returned by Weaviate (0.0–1.0). "
            "Only meaningful when the product list was filtered via Weaviate search."
        ),
    )

    # ------------------------------------------------------------------
    # Weaviate score (populated per-request via thread-local storage)
    # ------------------------------------------------------------------

    def _compute_weaviate_search_score(self):
        scores = getattr(_weaviate_scores, "scores", {})
        for record in self:
            record.weaviate_search_score = scores.get(record.id, 0.0)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _weaviate_product_data(self):
        """
        Return a dict of this product's indexable data for Weaviate.
        Must be called on a single record (``self.ensure_one()``).
        """
        self.ensure_one()
        categ_name = self.categ_id.complete_name if self.categ_id else ""
        website_description = html2plaintext(getattr(self, "website_description", "") or "")
        return {
            "odoo_id": self.id,
            "name": self.name or "",
            "description": self.description or "",
            "description_sale": self.description_sale or "",
            "default_code": self.default_code or "",
            "barcode": self.barcode or "",
            "categ_name": categ_name,
            "list_price": self.list_price or 0.0,
            "active": self.active,
            "website_description": website_description,
        }

    # ------------------------------------------------------------------
    # ORM hooks — real-time sync
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if _is_live_sync_enabled(self.env):
            records._weaviate_sync_after_write()
        return records

    def write(self, vals):
        result = super().write(vals)
        if _is_live_sync_enabled(self.env) and _WATCHED_FIELDS.intersection(vals.keys()):
            self._weaviate_sync_after_write()
        return result

    def unlink(self):
        # Capture UUIDs before the records are deleted.
        uuid_map = {r.id: r.weaviate_uuid for r in self if r.weaviate_uuid}
        result = super().unlink()
        if uuid_map and _is_live_sync_enabled(self.env):
            svc = WeaviateService.from_config(self.env)
            if svc:
                for odoo_id, weaviate_uuid in uuid_map.items():
                    try:
                        svc.delete_product(weaviate_uuid)
                    except Exception as exc:
                        _logger.warning(
                            "WeaviateSync: failed to delete product %s (uuid=%s): %s",
                            odoo_id,
                            weaviate_uuid,
                            exc,
                        )
        return result

    def _weaviate_sync_after_write(self):
        """
        Upsert all records in ``self`` to Weaviate.

        Failures are logged as warnings and do **not** roll back the Odoo
        transaction, so a Weaviate outage never blocks product saves.
        """
        svc = WeaviateService.from_config(self.env)
        if not svc:
            return
        for record in self:
            try:
                product_data = record._weaviate_product_data()
                if record.weaviate_uuid:
                    svc.update_product(record.weaviate_uuid, product_data)
                else:
                    new_uuid = svc.upsert_product(product_data)
                    # Write UUID back via raw SQL to avoid re-triggering the
                    # write() hook and causing infinite recursion.
                    self.env.cr.execute(
                        "UPDATE product_template SET weaviate_uuid = %s WHERE id = %s",
                        (new_uuid, record.id),
                    )
            except Exception as exc:
                _logger.warning(
                    "WeaviateSync: failed to sync product %s: %s", record.id, exc
                )

    # ------------------------------------------------------------------
    # Backend search override
    # ------------------------------------------------------------------

    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        """
        Post-sort results by Weaviate score when a Weaviate search was performed.

        In Odoo 19, ``search_read()`` calls ``search_fetch()`` directly,
        bypassing ``search()``.  This is therefore the correct interception
        point for score-based result ordering.

        Scores are reset here — before ``super().search_fetch()`` is called —
        so that stale scores from a previous Weaviate search never bleed into
        a subsequent standard ORM search, while still being readable after
        ``_search`` sets them (``_fetch_query`` does not call ``_search``).
        """
        _weaviate_scores.scores = {}

        result = super().search_fetch(
            domain, field_names, offset=offset, limit=limit, order=order
        )
        scores = getattr(_weaviate_scores, "scores", {})
        if scores:
            result = result.sorted(key=lambda r: scores.get(r.id, 0.0), reverse=True)
        return result

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        """
        Override to route text-based searches through Weaviate hybrid search.

        When ``weaviate_backend_search_enabled`` is ``True`` and the domain
        contains an ``ilike`` condition on a text field, the text term is
        extracted, sent to Weaviate, and the returned product IDs replace
        the original text condition.

        Falls back to the standard ORM search transparently if:
        - Weaviate backend search is disabled
        - No text-search term is detected in the domain
        - Weaviate is unreachable
        - Weaviate returns no results

        ``**kwargs`` forwards any extra ORM keyword arguments introduced in
        future Odoo versions (e.g. ``active_test``) to ``super()``.

        Note: scores are reset in ``search()``, not here, to avoid internal
        Odoo ``_search`` calls (field fetching, ACL checks) clobbering scores
        that were just set by the Weaviate search path.
        """
        # weaviate_search_score is non-stored — strip it from the SQL ORDER BY
        # to avoid a "column does not exist" error.  The search() override
        # re-sorts the recordset by score after the SQL query returns.
        if order and "weaviate_search_score" in order:
            order = None

        if not _is_backend_search_enabled(self.env):
            return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

        query_text, clean_domain = self._extract_weaviate_query(domain)
        if not query_text:
            return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

        try:
            svc = WeaviateService.from_config(self.env)
            if not svc:
                return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

            score_map = svc.hybrid_search(query_text)
            _logger.info(
                "WeaviateSearch: query=%r  results=%d  scores=%s",
                query_text,
                len(score_map),
                {k: round(v, 4) for k, v in list(score_map.items())[:10]},
            )

            if not score_map:
                # No Weaviate results → fall through so the UI shows
                # "no records" via the normal ORM path.
                return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

            # Store scores so weaviate_search_score can read them this request.
            _weaviate_scores.scores = score_map
            weaviate_ids = list(score_map.keys())

            final_domain = list(Domain([("id", "in", weaviate_ids)]) & Domain(clean_domain))
            _logger.info(
                "WeaviateSearch: final_domain=%s", final_domain
            )
            return super()._search(
                final_domain, offset=offset, limit=limit, order=order, **kwargs
            )

        except Exception as exc:
            _logger.warning(
                "WeaviateSearch: hybrid search failed, falling back to ORM: %s", exc
            )
            _weaviate_scores.scores = {}
            return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def _extract_weaviate_query(self, domain):
        """
        Extract the text search term from a domain using recursive descent
        parsing so that Odoo's prefix (Polish) notation is handled correctly.

        When a text leaf is removed, any binary operator whose only remaining
        operand was that leaf is collapsed, keeping the domain syntactically
        valid regardless of how deeply nested the text condition is.

        Returns ``(query_text | None, clean_domain)`` where ``clean_domain``
        is a valid Odoo domain with the text-field ilike conditions removed.

        Triggered fields / operators:
        - Fields: ``name``, ``display_name``, ``description``,
          ``description_sale``, ``default_code``
        - Operators: ``ilike``, ``=ilike``, ``like``
        """
        # All fields that Odoo's standard product search uses for text matching.
        # Any ilike/like on these fields is replaced by Weaviate's hybrid search.
        TEXT_FIELDS = frozenset(
            {
                "name",
                "display_name",
                "description",
                "description_sale",
                "default_code",
                "barcode",
                "product_variant_ids.default_code",
                "product_variant_ids.barcode",
            }
        )
        TEXT_OPERATORS = frozenset({"ilike", "=ilike", "like"})

        if not domain or not isinstance(domain, (list, tuple)):
            return None, domain

        # Normalise to explicit prefix notation so every binary operator has
        # exactly two operands and we never encounter implicit top-level ANDs.
        # Uses odoo.fields.Domain (Odoo 19+) instead of the deprecated
        # expression.normalize_domain from odoo.osv.
        tokens = list(Domain(domain))
        query_text = None

        def is_text_leaf(tok):
            return (
                isinstance(tok, (list, tuple))
                and len(tok) == 3
                and tok[0] in TEXT_FIELDS
                and tok[1] in TEXT_OPERATORS
                and isinstance(tok[2], str)
                and tok[2].strip()
            )

        def parse(idx):
            """Consume one expression from *tokens* starting at *idx*.

            Returns ``(flat_token_list, new_idx)``.  An empty list means the
            expression was entirely removed (it was a text search leaf, or all
            its children were removed).
            """
            nonlocal query_text

            if idx >= len(tokens):
                return [], idx

            tok = tokens[idx]

            if tok == "!":
                child, new_idx = parse(idx + 1)
                if not child:
                    # The negated sub-expression was dropped — drop ! too.
                    return [], new_idx
                return ["!"] + child, new_idx

            if tok in ("&", "|"):
                left, idx1 = parse(idx + 1)
                right, idx2 = parse(idx1)
                if not left and not right:
                    return [], idx2
                if not left:
                    return right, idx2
                if not right:
                    return left, idx2
                return [tok] + left + right, idx2

            if is_text_leaf(tok):
                if query_text is None:
                    query_text = tok[2].strip()
                return [], idx + 1  # consumed and dropped

            # Regular non-text leaf — keep it.
            return [list(tok)], idx + 1

        clean_tokens, _ = parse(0)
        return query_text, clean_tokens
