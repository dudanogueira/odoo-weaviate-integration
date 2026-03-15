# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def _is_shop_search_enabled(env):
    return (
        env["ir.config_parameter"]
        .sudo()
        .get_param("product_weaviate_search.shop_search_enabled", "False")
        == "True"
    )


# The try/except ImportError pattern is the OCA-standard way to make a
# controller override conditional on an optional module dependency.
# If website_sale is not installed this entire block is a no-op.
try:
    from odoo.addons.website_sale.controllers.main import WebsiteSale
    from odoo.http import request

    from ..services.weaviate_service import WeaviateService

    class WebsiteSaleWeaviate(WebsiteSale):
        """
        Extend the website_sale shop controller to replace the text search
        with Weaviate hybrid search when enabled.

        The override point is ``_shop_lookup_products``, which is the method
        specifically designed for extension in Odoo's website_sale module.
        It returns ``(fuzzy_search_term, product_count, product_recordset)``.
        """

        def _shop_lookup_products(self, options, post, search, website):
            """
            Intercept the shop search and delegate to Weaviate when enabled.

            Falls back to the default Odoo shop search transparently if:
            - Shop search is disabled in settings
            - The search query is empty
            - Weaviate is not configured or unreachable
            - Weaviate returns no results
            """
            if not search or not _is_shop_search_enabled(request.env):
                return super()._shop_lookup_products(options, post, search, website)

            try:
                svc = WeaviateService.from_config(request.env)
                if not svc:
                    return super()._shop_lookup_products(
                        options, post, search, website
                    )

                get_param = request.env["ir.config_parameter"].sudo().get_param
                shop_limit = int(
                    get_param("product_weaviate_search.shop_search_limit", "0") or 0
                )
                autocut = int(
                    get_param("product_weaviate_search.search_autocut", "0") or 0
                )
                score_map = svc.hybrid_search(
                    search,
                    limit=shop_limit or None,
                    autocut=autocut or None,
                )
                if not score_map:
                    return super()._shop_lookup_products(
                        options, post, search, website
                    )

                weaviate_ids = list(score_map.keys())

                # Build a product recordset from the Weaviate IDs, respecting
                # website publication status.
                products = (
                    request.env["product.template"]
                    .sudo()
                    .search(
                        [
                            ("id", "in", weaviate_ids),
                            ("website_published", "=", True),
                        ]
                    )
                )

                # Preserve Weaviate relevance ordering (highest score first).
                id_order = {pid: idx for idx, pid in enumerate(weaviate_ids)}
                products = products.sorted(key=lambda p: id_order.get(p.id, 9999))

                return "", len(products), products

            except Exception as exc:
                _logger.warning(
                    "WeaviateShopSearch: hybrid search failed, falling back to Odoo "
                    "default search: %s",
                    exc,
                )
                return super()._shop_lookup_products(options, post, search, website)

except ImportError:
    # website_sale is not installed — controller override is skipped entirely.
    pass
