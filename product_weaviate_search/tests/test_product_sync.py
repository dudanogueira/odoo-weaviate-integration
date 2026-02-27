# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from .common import WeaviateTestCommon


class TestProductSync(WeaviateTestCommon):
    """Test that product ORM hooks trigger the correct WeaviateService calls."""

    def test_create_triggers_upsert(self):
        """Creating a product should call upsert_product once."""
        self.mock_service.reset_mock()
        self.env["product.template"].create({"name": "Test Widget"})
        self.mock_service.upsert_product.assert_called_once()

    def test_write_watched_field_triggers_update(self):
        """Writing a watched field (name) should call update_product."""
        product = self.env["product.template"].create({"name": "Widget A"})
        # Simulate a stored UUID.
        product.sudo().write({"weaviate_uuid": "uuid-abc"})
        self.mock_service.reset_mock()

        product.write({"name": "Widget A Updated"})
        self.mock_service.update_product.assert_called_once()

    def test_write_unwatched_field_does_not_trigger_sync(self):
        """Writing a field not in _WATCHED_FIELDS must not call Weaviate."""
        product = self.env["product.template"].create({"name": "Widget B"})
        self.mock_service.reset_mock()

        # 'sale_ok' is not in the watched set.
        product.write({"sale_ok": False})
        self.mock_service.update_product.assert_not_called()
        self.mock_service.upsert_product.assert_not_called()

    def test_unlink_triggers_delete(self):
        """Deleting a product with a weaviate_uuid should call delete_product."""
        product = self.env["product.template"].create({"name": "Widget C"})
        product.sudo().write({"weaviate_uuid": "uuid-del"})
        self.mock_service.reset_mock()

        product.unlink()
        self.mock_service.delete_product.assert_called_once_with("uuid-del")

    def test_unlink_without_uuid_skips_delete(self):
        """Deleting a product without a weaviate_uuid should not call Weaviate."""
        product = self.env["product.template"].create({"name": "Widget D"})
        # Ensure no UUID is set.
        self.env.cr.execute(
            "UPDATE product_template SET weaviate_uuid = NULL WHERE id = %s",
            (product.id,),
        )
        self.mock_service.reset_mock()

        product.unlink()
        self.mock_service.delete_product.assert_not_called()

    def test_weaviate_product_data_fields(self):
        """_weaviate_product_data should return all expected keys."""
        product = self.env["product.template"].create(
            {
                "name": "Smart Widget",
                "description": "An internal note",
                "description_sale": "Great for customers",
                "default_code": "SW-001",
                "list_price": 49.99,
            }
        )
        data = product._weaviate_product_data()
        expected_keys = {
            "odoo_id",
            "name",
            "description",
            "description_sale",
            "default_code",
            "barcode",
            "categ_name",
            "list_price",
            "active",
            "website_description",
        }
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(data["odoo_id"], product.id)
        self.assertEqual(data["name"], "Smart Widget")
        self.assertAlmostEqual(data["list_price"], 49.99)
