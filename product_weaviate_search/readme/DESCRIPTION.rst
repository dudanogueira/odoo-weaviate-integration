This addon integrates `Weaviate <https://weaviate.io>`_ vector search into Odoo
to provide semantic, AI-powered product search in both the backend and the
eCommerce shop.

Features
--------

* **Real-time sync**: Products are automatically pushed to Weaviate whenever
  they are created, updated, or deleted in Odoo.
* **Hybrid search**: Combines BM25 keyword search with OpenAI vector embeddings
  (``text2vec-openai``) for highly relevant, semantic results.
* **Backend search**: The product list view search bar routes text queries
  through Weaviate and falls back gracefully to the standard ORM search if
  Weaviate is unavailable.
* **eCommerce search**: The ``/shop`` search endpoint is overridden to use
  Weaviate when the ``website_sale`` module is installed.
* **Bulk sync wizard**: A one-click wizard to seed or re-index all products.
* **Configurable**: All connection parameters, feature toggles, and search
  tuning options are available in *Settings → Weaviate*.
