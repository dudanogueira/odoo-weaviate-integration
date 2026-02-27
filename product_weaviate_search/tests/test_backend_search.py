# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from .common import WeaviateTestCommon


class TestExtractWeaviateQuery(WeaviateTestCommon):
    """Unit tests for the domain extraction helper."""

    def _extract(self, domain):
        return self.env["product.template"]._extract_weaviate_query(domain)

    def test_simple_name_ilike(self):
        """A plain ('name', 'ilike', 'foo') domain is extracted correctly."""
        query, remainder = self._extract([("name", "ilike", "blue widget")])
        self.assertEqual(query, "blue widget")
        self.assertEqual(remainder, [])

    def test_display_name_ilike(self):
        query, remainder = self._extract([("display_name", "ilike", "widget")])
        self.assertEqual(query, "widget")
        self.assertEqual(remainder, [])

    def test_ilike_with_extra_filters(self):
        """Extra (non-text) filters are preserved in the remainder."""
        domain = [
            ("name", "ilike", "cable"),
            ("active", "=", True),
            ("categ_id", "=", 5),
        ]
        query, remainder = self._extract(domain)
        self.assertEqual(query, "cable")
        self.assertIn(("active", "=", True), remainder)
        self.assertIn(("categ_id", "=", 5), remainder)

    def test_no_text_term_returns_none(self):
        """A domain with no text-search term returns (None, original_domain)."""
        domain = [("active", "=", True)]
        query, remainder = self._extract(domain)
        self.assertIsNone(query)

    def test_empty_domain(self):
        query, remainder = self._extract([])
        self.assertIsNone(query)

    def test_empty_string_not_extracted(self):
        """Empty strings should not trigger Weaviate routing."""
        query, remainder = self._extract([("name", "ilike", "  ")])
        self.assertIsNone(query)

    def test_non_watched_field_not_extracted(self):
        """ilike on a field not in TEXT_FIELDS is left in the domain."""
        domain = [("description_pickingout", "ilike", "ship fast")]
        query, remainder = self._extract(domain)
        self.assertIsNone(query)
        self.assertEqual(remainder, domain)


class TestBackendSearch(WeaviateTestCommon):
    """Integration-style tests for the _search override."""

    def setUp(self):
        super().setUp()
        self._set_backend_search_enabled(True)

    def test_search_routes_to_weaviate_when_enabled(self):
        """When enabled, text search should call hybrid_search."""
        self.mock_service.hybrid_search.return_value = []
        self.env["product.template"]._search([("name", "ilike", "widget")])
        self.mock_service.hybrid_search.assert_called_once_with("widget")

    def test_search_falls_back_when_disabled(self):
        """When disabled, hybrid_search must NOT be called."""
        self._set_backend_search_enabled(False)
        self.mock_service.reset_mock()
        self.env["product.template"]._search([("name", "ilike", "widget")])
        self.mock_service.hybrid_search.assert_not_called()

    def test_search_falls_back_on_weaviate_error(self):
        """If Weaviate raises, _search must not propagate the exception."""
        self.mock_service.hybrid_search.side_effect = RuntimeError("connection error")
        # Should not raise.
        result = self.env["product.template"]._search(
            [("name", "ilike", "widget")]
        )
        self.assertIsNotNone(result)
        # Restore side effect.
        self.mock_service.hybrid_search.side_effect = None

    def test_search_injects_id_domain(self):
        """Weaviate IDs should be injected as ('id', 'in', [...]) domain."""
        product = self.env["product.template"].create({"name": "Unique Item XYZ"})
        self.mock_service.hybrid_search.return_value = [product.id]

        results = self.env["product.template"].search(
            [("name", "ilike", "Unique Item XYZ")]
        )
        self.assertIn(product, results)
