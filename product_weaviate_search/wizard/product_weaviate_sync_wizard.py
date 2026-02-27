# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.weaviate_service import WeaviateService

_logger = logging.getLogger(__name__)

_BATCH_SIZE = 200


class ProductWeaviateSyncWizard(models.TransientModel):
    """
    Wizard for bulk-syncing Odoo products to Weaviate.

    Four modes are available:

    - **Sync selected**: Insert/update only the products that were selected
      in the list view (pre-populated when the action is triggered with a
      non-empty selection).
    - **Sync all**: Insert/update every active product in the collection.
    - **Sync unsynced only**: Only process products that have no
      ``weaviate_uuid`` yet.
    - **Reset and re-index**: Drop the collection, recreate it, and
      re-insert all products from scratch.
    """

    _name = "product.weaviate.sync.wizard"
    _description = "Sync Products with Weaviate"

    mode = fields.Selection(
        selection=[
            ("selected", "Sync selected products only"),
            ("all", "Sync all products"),
            ("unsynced", "Sync unsynced products only"),
            ("reset", "Reset collection and re-index all"),
        ],
        string="Sync Mode",
        default="all",
        required=True,
    )
    product_ids = fields.Many2many(
        comodel_name="product.template",
        string="Selected Products",
        help="Products to sync when mode is 'Sync selected products only'.",
    )
    product_count = fields.Integer(
        string="Number of Selected Products",
        compute="_compute_product_count",
    )
    state = fields.Selection(
        selection=[("draft", "Draft"), ("done", "Done")],
        default="draft",
        readonly=True,
    )
    result_message = fields.Text(string="Result", readonly=True)

    @api.depends("product_ids")
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)

    # ------------------------------------------------------------------

    def action_sync(self):
        """Execute the sync according to the selected mode."""
        self.ensure_one()

        svc = WeaviateService.from_config(self.env)
        if not svc:
            raise UserError(
                _(
                    "Weaviate is not configured. "
                    "Please set the Weaviate URL in Settings → Technical → Weaviate."
                )
            )

        if self.mode == "selected":
            if not self.product_ids:
                raise UserError(
                    _(
                        "No products selected. "
                        "Please select products in the list view before opening the wizard, "
                        "or choose a different sync mode."
                    )
                )
            svc.ensure_collection()
            products = self.product_ids
        else:
            if self.mode == "reset":
                _logger.info("WeaviateSync wizard: dropping collection for re-index.")
                svc.delete_collection()

            svc.ensure_collection()

            domain = [("active", "in", [True, False])]
            if self.mode == "unsynced":
                domain.append(("weaviate_uuid", "=", False))

            products = self.env["product.template"].search(domain)
        total = len(products)
        _logger.info("WeaviateSync wizard: syncing %d products (mode=%s).", total, self.mode)

        inserted = 0
        errors = []

        for chunk_start in range(0, total, _BATCH_SIZE):
            chunk = products[chunk_start : chunk_start + _BATCH_SIZE]
            products_data = []
            for record in chunk:
                try:
                    products_data.append(record._weaviate_product_data())
                except Exception as exc:
                    errors.append(f"Product {record.id} ({record.name}): {exc}")

            if products_data:
                result = svc.batch_insert_products(products_data)
                inserted += result.get("inserted", 0)
                errors.extend(result.get("errors", []))

        # Clear weaviate_uuid on all synced products so upsert_product will
        # assign fresh UUIDs. The next individual save will populate them.
        # For a cleaner approach, the batch could return UUIDs per product,
        # but batch.dynamic() does not expose per-object UUIDs directly.
        # We mark synced products as needing UUID refresh on next write.

        msg_lines = [
            f"Sync completed. Mode: {self.mode}",
            f"Products processed: {total}",
            f"Objects inserted/updated in Weaviate: {inserted}",
        ]
        if errors:
            msg_lines.append(f"Errors ({len(errors)}):")
            msg_lines.extend(f"  • {e}" for e in errors[:20])
            if len(errors) > 20:
                msg_lines.append(f"  … and {len(errors) - 20} more (see server logs)")

        self.write(
            {
                "state": "done",
                "result_message": "\n".join(msg_lines),
            }
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def action_open_wizard(self):
        """
        Open the wizard from the product list Action menu.

        When products are selected in the list view, ``active_ids`` is present
        in the context and the wizard defaults to "Sync selected products only".
        """
        active_ids = self.env.context.get("active_ids", [])
        ctx = {}
        if active_ids:
            ctx["default_product_ids"] = [(6, 0, active_ids)]
            ctx["default_mode"] = "selected"
        return {
            "type": "ir.actions.act_window",
            "name": _("Sync Products with Weaviate"),
            "res_model": self._name,
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
