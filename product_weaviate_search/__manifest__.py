# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Product Weaviate Search",
    "summary": (
        "Syncs products to Weaviate and replaces backend and eCommerce "
        "search with Weaviate hybrid vector search"
    ),
    "version": "19.0.1.0.0",
    "development_status": "Beta",
    "category": "Product",
    "website": "https://github.com/OCA/product-attribute",
    "author": "Odoo Community Association (OCA)",
    "maintainers": [],
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "product",
        "base_setup",
        # "website_sale" is an optional runtime dependency; the controller
        # override loads it conditionally via try/except ImportError.
    ],
    "external_dependencies": {
        "python": ["weaviate"],
    },
    "data": [
        "security/ir.model.access.csv",
        "security/product_weaviate_security.xml",
        "data/ir_config_parameter_data.xml",
        "views/res_config_settings_view.xml",
        "views/product_template_views.xml",
        "wizard/product_weaviate_sync_wizard_view.xml",
    ],
}
