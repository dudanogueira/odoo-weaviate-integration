# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase


class WeaviateTestCommon(TransactionCase):
    """
    Base test class that patches ``WeaviateService.from_config`` so tests
    can run without a live Weaviate instance.

    Subclasses can configure ``self.mock_service`` to control return values::

        self.mock_service.hybrid_search.return_value = [1, 2, 3]
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a mock service instance used across all tests in the class.
        cls.mock_service = MagicMock()
        cls.mock_service.hybrid_search.return_value = []
        cls.mock_service.upsert_product.return_value = "fake-uuid-1234"
        cls.mock_service.update_product.return_value = None
        cls.mock_service.delete_product.return_value = None
        cls.mock_service.batch_insert_products.return_value = {
            "inserted": 0,
            "errors": [],
        }
        cls.mock_service.ensure_collection.return_value = True

    def setUp(self):
        super().setUp()
        # Patch from_config at the module level where it is imported by models.
        self._patch_from_config = patch(
            "odoo.addons.product_weaviate_search.services."
            "weaviate_service.WeaviateService.from_config",
            return_value=self.mock_service,
        )
        self._patch_from_config.start()
        self.addCleanup(self._patch_from_config.stop)

        # Also patch inside the product_template module where it is imported.
        self._patch_from_config_model = patch(
            "odoo.addons.product_weaviate_search.models."
            "product_template.WeaviateService.from_config",
            return_value=self.mock_service,
        )
        self._patch_from_config_model.start()
        self.addCleanup(self._patch_from_config_model.stop)

    def _set_backend_search_enabled(self, enabled: bool):
        self.env["ir.config_parameter"].sudo().set_param(
            "product_weaviate_search.backend_search_enabled",
            "True" if enabled else "False",
        )
