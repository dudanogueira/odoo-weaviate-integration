# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from contextlib import contextmanager

_logger = logging.getLogger(__name__)


class WeaviateService:
    """
    Stateless service layer for all Weaviate operations.

    Each public method opens a fresh connection, performs its work, and closes
    the connection in a finally block. This is safe for Odoo's multi-worker
    architecture where a Python object cannot be shared across processes.

    Usage from an Odoo model::

        from odoo.addons.product_weaviate_search.services.weaviate_service import (
            WeaviateService,
        )
        svc = WeaviateService.from_config(self.env)
        if svc:
            ids = svc.hybrid_search("blue widget")
    """

    # Single source of truth for the Weaviate collection schema.
    # Tuples of (property_name, dtype_key, skip_vectorization, description)
    # dtype_key maps to weaviate DataType via _DTYPE_MAP inside ensure_collection.
    COLLECTION_PROPERTIES = [
        ("odoo_id", "INT", True, "Odoo product.template database ID"),
        ("name", "TEXT", False, "Product name"),
        ("description", "TEXT", False, "Internal product description"),
        ("description_sale", "TEXT", False, "Sales description shown to customers"),
        ("default_code", "TEXT", True, "Internal reference / SKU"),
        ("barcode", "TEXT", True, "EAN/UPC barcode"),
        ("categ_name", "TEXT", False, "Product category name"),
        ("list_price", "NUMBER", True, "Sales price"),
        ("active", "BOOLEAN", True, "Whether the product is active"),
        (
            "website_description",
            "TEXT",
            False,
            "Website HTML description stripped to plain text",
        ),
    ]

    def __init__(
        self,
        deployment_type,
        url,
        api_key,
        openai_api_key,
        collection_name,
        search_limit=50,
        search_alpha=0.5,
        # custom deployment parameters
        http_host="",
        http_port=8080,
        http_secure=False,
        grpc_host="",
        grpc_port=50051,
        grpc_secure=False,
    ):
        self.deployment_type = deployment_type or "custom"
        self.url = url
        self.api_key = api_key or ""
        self.openai_api_key = openai_api_key or ""
        self.collection_name = collection_name or "OdooProduct"
        self.search_limit = int(search_limit) if search_limit else 50
        self.search_alpha = float(search_alpha) if search_alpha else 0.5
        # custom connection fields — ports are always int, secure flags always bool
        self.http_host = http_host or ""
        self.http_port = int(http_port) if http_port else 8080
        self.http_secure = bool(http_secure)
        self.grpc_host = grpc_host or ""
        self.grpc_port = int(grpc_port) if grpc_port else 50051
        self.grpc_secure = bool(grpc_secure)

    @classmethod
    def from_config(cls, env):
        """
        Instantiate from Odoo ``ir.config_parameter`` values.

        Returns ``None`` if neither a URL (local/cloud) nor a custom HTTP host
        is configured, so callers can guard with ``if svc:`` before any network I/O.
        """
        get = lambda key, default="": env["ir.config_parameter"].sudo().get_param(
            f"product_weaviate_search.{key}", default
        )
        deployment_type = get("deployment_type", "custom")
        url = get("url")
        http_host = get("http_host")

        # Need at least a URL or a custom HTTP host.
        if not url and not http_host:
            _logger.debug(
                "WeaviateService: no URL or HTTP host configured — "
                "skipping Weaviate operation."
            )
            return None

        def get_int(key, default):
            val = get(key)
            try:
                return int(val) if val else default
            except (ValueError, TypeError):
                return default

        def get_bool(key):
            # ir.config_parameter stores booleans as the literal string "True"/"False".
            return get(key, "False") == "True"

        return cls(
            deployment_type=deployment_type,
            url=url,
            api_key=get("api_key", ""),
            openai_api_key=get("openai_api_key", ""),
            collection_name=get("collection_name", "OdooProduct"),
            search_limit=get_int("search_limit", 50),
            search_alpha=float(get("search_alpha") or 0.5),
            http_host=http_host,
            http_port=get_int("http_port", 8080),
            http_secure=get_bool("http_secure"),
            grpc_host=get("grpc_host", ""),
            grpc_port=get_int("grpc_port", 50051),
            grpc_secure=get_bool("grpc_secure"),
        )

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @contextmanager
    def _get_client(self):
        """
        Context manager that yields an open ``weaviate.WeaviateClient``.

        Guarantees ``client.close()`` even on exceptions.
        """
        import weaviate
        from weaviate.auth import Auth

        client = None
        try:
            headers = {
                "X-Weaviate-Client-Integration": "OdooProductWeaviateSearch/1.0"
            }
            if self.openai_api_key:
                headers["X-OpenAI-Api-Key"] = self.openai_api_key

            if self.deployment_type == "cloud":
                client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=self.url,
                    auth_credentials=Auth.api_key(self.api_key),
                    headers=headers,
                )
            else:
                # "custom" — explicit host/port/secure for both HTTP and gRPC
                kwargs = dict(
                    http_host=self.http_host,
                    http_port=self.http_port,
                    http_secure=self.http_secure,
                    grpc_host=self.grpc_host or self.http_host,
                    grpc_port=self.grpc_port,
                    grpc_secure=self.grpc_secure,
                    headers=headers,
                )
                if self.api_key:
                    kwargs["auth_credentials"] = Auth.api_key(self.api_key)
                client = weaviate.connect_to_custom(**kwargs)

            yield client
        except Exception as exc:
            _logger.exception("WeaviateService: connection error: %s", exc)
            raise
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Schema / Collection Management
    # ------------------------------------------------------------------

    def ensure_collection(self):
        """
        Create the Weaviate collection if it does not already exist.

        Idempotent — safe to call repeatedly.
        Returns ``True`` if the collection was created, ``False`` if it
        already existed.
        """
        from weaviate.classes.config import Configure, DataType, Property

        _DTYPE_MAP = {
            "TEXT": DataType.TEXT,
            "INT": DataType.INT,
            "NUMBER": DataType.NUMBER,
            "BOOLEAN": DataType.BOOL,
        }

        with self._get_client() as client:
            if client.collections.exists(self.collection_name):
                _logger.info(
                    "WeaviateService: collection '%s' already exists.",
                    self.collection_name,
                )
                return False

            properties = [
                Property(
                    name=prop_name,
                    data_type=_DTYPE_MAP[dtype_str],
                    description=description,
                    skip_vectorization=skip_vec,
                    vectorize_property_name=False,
                )
                for prop_name, dtype_str, skip_vec, description in self.COLLECTION_PROPERTIES
            ]

            client.collections.create(
                name=self.collection_name,
                description="Odoo product.template objects for hybrid vector search",
                vector_config=Configure.Vectors.text2vec_openai(
                    vectorize_collection_name=False,
                ),
                properties=properties,
            )
            _logger.info(
                "WeaviateService: created collection '%s'.",
                self.collection_name,
            )
            return True

    def delete_collection(self):
        """Drop the collection entirely. Used before a full re-index."""
        with self._get_client() as client:
            if client.collections.exists(self.collection_name):
                client.collections.delete(self.collection_name)
                _logger.info(
                    "WeaviateService: deleted collection '%s'.",
                    self.collection_name,
                )

    # ------------------------------------------------------------------
    # Deterministic UUID
    # ------------------------------------------------------------------

    @staticmethod
    def deterministic_uuid(odoo_id: int) -> str:
        """
        Return a stable UUID derived from ``odoo_id`` using ``generate_uuid5``.

        The same Odoo product ID always maps to the same Weaviate UUID, which
        enables true upsert semantics via batch without a prior fetch query.
        """
        from weaviate.util import generate_uuid5

        return str(generate_uuid5(str(odoo_id)))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert_product(self, product_data: dict) -> str:
        """
        Insert or update a single product using a deterministic UUID.

        Uses ``batch.dynamic()`` with a pre-computed UUID so Weaviate
        applies upsert semantics — no fetch query required.

        Returns the deterministic UUID string.
        """
        det_uuid = self.deterministic_uuid(product_data["odoo_id"])
        with self._get_client() as client:
            col = client.collections.get(self.collection_name)
            with col.batch.dynamic() as batch:
                batch.add_object(properties=product_data, uuid=det_uuid)
        return det_uuid

    def batch_insert_products(self, products_data: list) -> dict:
        """
        Batch upsert a list of product dicts.

        Each object is assigned a deterministic UUID so the operation is
        idempotent — re-running it updates existing objects rather than
        creating duplicates.

        Uses ``col.batch.dynamic()`` which auto-adjusts batch size based on
        Weaviate server feedback.

        Returns ``{"inserted": int, "errors": list[str]}``.
        """
        with self._get_client() as client:
            col = client.collections.get(self.collection_name)
            inserted = 0
            with col.batch.dynamic() as batch:
                for product_data in products_data:
                    det_uuid = self.deterministic_uuid(product_data["odoo_id"])
                    batch.add_object(properties=product_data, uuid=det_uuid)
                    inserted += 1

            errors = []
            if hasattr(batch, "failed_objects"):
                errors = [str(f.message) for f in batch.failed_objects]

            return {"inserted": inserted, "errors": errors}

    def update_product(self, weaviate_uuid: str, product_data: dict):
        """Update a product by its Weaviate UUID."""
        with self._get_client() as client:
            col = client.collections.get(self.collection_name)
            col.data.update(uuid=weaviate_uuid, properties=product_data)

    def delete_product(self, weaviate_uuid: str):
        """Delete a product by its Weaviate UUID."""
        with self._get_client() as client:
            col = client.collections.get(self.collection_name)
            col.data.delete_by_id(uuid=weaviate_uuid)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def hybrid_search(
        self, query: str, limit: int = None, alpha: float = None, autocut: int = None
    ) -> dict:
        """
        Perform hybrid (vector + BM25) search against the product collection.

        Returns an ordered dict of ``{odoo_id: score}`` where score is the
        Weaviate RELATIVE_SCORE hybrid score (0.0–1.0, higher = more relevant).
        The dict preserves insertion order, i.e. highest-scoring results first.

        :param query: Free-text search string.
        :param limit: Override the configured result limit.
        :param alpha: Override the configured BM25/vector balance
                      (0.0 = pure BM25, 1.0 = pure vector).
        :param autocut: Stop returning results after N consecutive score drops.
                        ``None`` or ``0`` disables autocut.
        """
        from weaviate.classes.query import Filter, HybridFusion, MetadataQuery

        effective_alpha = alpha if alpha is not None else self.search_alpha
        effective_autocut = autocut if autocut else None
        # When autocut is active, omit limit — Weaviate uses the less
        # restrictive of the two, which would defeat the purpose of autocut.
        effective_limit = None if effective_autocut else (
            limit if limit is not None else self.search_limit
        )

        with self._get_client() as client:
            col = client.collections.get(self.collection_name)
            response = col.query.hybrid(
                query=query,
                alpha=effective_alpha,
                fusion_type=HybridFusion.RELATIVE_SCORE,
                limit=effective_limit,
                auto_limit=effective_autocut,
                return_properties=["odoo_id"],
                return_metadata=MetadataQuery(score=True),
                # Only return active products — mirrors Odoo's default active filter
                # and avoids wasting result slots on inactive/archived products.
                filters=Filter.by_property("active").equal(True),
            )
            return {
                int(obj.properties["odoo_id"]): (
                    obj.metadata.score if obj.metadata and obj.metadata.score is not None else 0.0
                )
                for obj in response.objects
            }
