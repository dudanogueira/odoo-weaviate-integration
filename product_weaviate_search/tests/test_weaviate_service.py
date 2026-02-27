# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from odoo.addons.product_weaviate_search.services.weaviate_service import (
    WeaviateService,
)


class TestWeaviateServiceFromConfig(TransactionCase):
    """Test WeaviateService.from_config factory method."""

    def test_returns_none_when_url_not_set(self):
        """from_config should return None if weaviate URL is empty."""
        self.env["ir.config_parameter"].sudo().set_param(
            "product_weaviate_search.url", ""
        )
        svc = WeaviateService.from_config(self.env)
        self.assertIsNone(svc)

    def test_returns_service_when_url_set(self):
        """from_config should return a WeaviateService when URL is configured."""
        self.env["ir.config_parameter"].sudo().set_param(
            "product_weaviate_search.url", "http://localhost:8080"
        )
        svc = WeaviateService.from_config(self.env)
        self.assertIsNotNone(svc)
        self.assertIsInstance(svc, WeaviateService)
        self.assertEqual(svc.url, "http://localhost:8080")

    def test_collection_name_default(self):
        """Collection name defaults to OdooProduct."""
        self.env["ir.config_parameter"].sudo().set_param(
            "product_weaviate_search.url", "http://localhost:8080"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "product_weaviate_search.collection_name", ""
        )
        svc = WeaviateService.from_config(self.env)
        self.assertEqual(svc.collection_name, "OdooProduct")


class TestWeaviateServiceHybridSearch(TransactionCase):
    """Test hybrid_search method with a mocked weaviate client."""

    def _make_service(self):
        return WeaviateService(
            deployment_type="local",
            url="http://localhost:8080",
            api_key="",
            openai_api_key="sk-test",
            collection_name="OdooProduct",
            search_limit=10,
            search_alpha=0.5,
        )

    def _make_mock_object(self, odoo_id):
        obj = MagicMock()
        obj.properties = {"odoo_id": odoo_id}
        return obj

    def test_hybrid_search_returns_odoo_ids(self):
        """hybrid_search should return a list of integer Odoo product IDs."""
        svc = self._make_service()
        mock_response = MagicMock()
        mock_response.objects = [
            self._make_mock_object(10),
            self._make_mock_object(20),
            self._make_mock_object(30),
        ]
        mock_col = MagicMock()
        mock_col.query.hybrid.return_value = mock_response

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.collections.get.return_value = mock_col

        with patch.object(svc, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = lambda s, *a: mock_client
            mock_get_client.return_value.__exit__ = MagicMock(return_value=False)

            # Use a simpler approach: patch the contextmanager directly.
            from contextlib import contextmanager

            @contextmanager
            def fake_client():
                yield mock_client

            mock_get_client.return_value = fake_client()

            # Call the method under test.
            with patch.object(svc, "_get_client", return_value=fake_client()):
                result = svc.hybrid_search("blue widget")

        self.assertEqual(result, [10, 20, 30])

    def test_hybrid_search_empty_results(self):
        """hybrid_search returns [] when Weaviate returns no objects."""
        svc = self._make_service()
        mock_response = MagicMock()
        mock_response.objects = []
        mock_col = MagicMock()
        mock_col.query.hybrid.return_value = mock_response
        mock_client = MagicMock()
        mock_client.collections.get.return_value = mock_col

        from contextlib import contextmanager

        @contextmanager
        def fake_client():
            yield mock_client

        with patch.object(svc, "_get_client", return_value=fake_client()):
            result = svc.hybrid_search("nonexistent thing")

        self.assertEqual(result, [])
