# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# Boolean parameters that require manual get/set because Odoo's config_parameter
# shortcut uses bool("False") which evaluates to True (any non-empty string is
# truthy in Python). We compare against the literal string "True" instead.
_BOOL_PARAMS = [
    "weaviate_http_secure",
    "weaviate_grpc_secure",
    "weaviate_backend_search_enabled",
    "weaviate_shop_search_enabled",
]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    weaviate_deployment_type = fields.Selection(
        selection=[("cloud", "Weaviate Cloud"), ("custom", "Custom")],
        string="Weaviate Deployment",
        config_parameter="product_weaviate_search.deployment_type",
        default="custom",
    )

    # --- Cloud ---
    weaviate_url = fields.Char(
        string="Cluster URL",
        config_parameter="product_weaviate_search.url",
        help="Weaviate Cloud cluster URL, e.g. https://xxx.weaviate.cloud",
    )
    weaviate_api_key = fields.Char(
        string="Weaviate API Key",
        config_parameter="product_weaviate_search.api_key",
        help="API key for Weaviate Cloud or secured custom instances.",
    )

    # --- Custom (connect_to_custom) ---
    weaviate_http_host = fields.Char(
        string="HTTP Host",
        config_parameter="product_weaviate_search.http_host",
        help="Hostname for the HTTP API connection, e.g. localhost or weaviate.",
    )
    weaviate_http_port = fields.Integer(
        string="HTTP Port",
        config_parameter="product_weaviate_search.http_port",
        default=8080,
        help="HTTP port. Default is 8080 for local; WCD uses 443.",
    )
    # NOTE: no config_parameter — handled manually in get_values/set_values
    # to avoid bool("False") == True in Python.
    weaviate_http_secure = fields.Boolean(
        string="HTTP Secure (HTTPS)",
        default=False,
        help="Enable HTTPS for the HTTP API connection.",
    )
    weaviate_grpc_host = fields.Char(
        string="gRPC Host",
        config_parameter="product_weaviate_search.grpc_host",
        help=(
            "Hostname for the gRPC API connection. "
            "Defaults to HTTP host if left empty."
        ),
    )
    weaviate_grpc_port = fields.Integer(
        string="gRPC Port",
        config_parameter="product_weaviate_search.grpc_port",
        default=50051,
        help="gRPC port. Default is 50051 for local; WCD uses 443.",
    )
    # NOTE: no config_parameter — handled manually (same reason as http_secure).
    weaviate_grpc_secure = fields.Boolean(
        string="gRPC Secure",
        default=False,
        help="Enable TLS for the gRPC API connection.",
    )

    weaviate_openai_api_key = fields.Char(
        string="OpenAI API Key",
        config_parameter="product_weaviate_search.openai_api_key",
        help=(
            "Used for the text2vec-openai vectorizer. "
            "Sent to Weaviate as the X-OpenAI-Api-Key header on every request."
        ),
    )

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    weaviate_collection_name = fields.Char(
        string="Collection Name",
        config_parameter="product_weaviate_search.collection_name",
        default="OdooProduct",
        help="Name of the Weaviate collection that stores product vectors.",
    )

    # ------------------------------------------------------------------
    # Feature Toggles (also Boolean — manual get/set)
    # ------------------------------------------------------------------

    weaviate_backend_search_enabled = fields.Boolean(
        string="Enable Weaviate Backend Search",
        default=False,
        help=(
            "When enabled, the product list view text search in the Odoo backend "
            "is replaced with Weaviate hybrid search."
        ),
    )
    weaviate_shop_search_enabled = fields.Boolean(
        string="Enable Weaviate eCommerce Shop Search",
        default=False,
        help=(
            "When enabled, the /shop search bar on the website is handled by "
            "Weaviate hybrid search instead of Odoo's default fuzzy search."
        ),
    )

    # ------------------------------------------------------------------
    # Search Tuning
    # ------------------------------------------------------------------

    weaviate_search_limit = fields.Integer(
        string="Search Result Limit",
        config_parameter="product_weaviate_search.search_limit",
        default=50,
        help="Maximum number of product results returned per Weaviate search query.",
    )
    weaviate_search_alpha = fields.Float(
        string="Hybrid Search Alpha",
        config_parameter="product_weaviate_search.search_alpha",
        default=0.5,
        help=(
            "Controls the balance between BM25 keyword search (0.0) and "
            "pure vector similarity search (1.0). "
            "0.5 gives equal weight to both."
        ),
    )

    # ------------------------------------------------------------------
    # Manual get/set for Boolean parameters
    # ------------------------------------------------------------------

    @api.model
    def get_values(self):
        res = super().get_values()
        get_param = self.env["ir.config_parameter"].sudo().get_param
        for fname in _BOOL_PARAMS:
            key = f"product_weaviate_search.{fname.removeprefix('weaviate_')}"
            # Compare to the literal string "True" — never use bool(str_value).
            res[fname] = get_param(key, "False") == "True"
        return res

    def set_values(self):
        super().set_values()
        set_param = self.env["ir.config_parameter"].sudo().set_param
        for fname in _BOOL_PARAMS:
            key = f"product_weaviate_search.{fname.removeprefix('weaviate_')}"
            set_param(key, str(self[fname]))
