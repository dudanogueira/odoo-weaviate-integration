Bulk Sync
---------

Go to **Inventory / Products** (or **Sales / Products**) → select all
records → **Action → Sync with Weaviate**.

Three modes are available:

* **Sync all products** – Upsert every product (active or archived) into
  Weaviate. Safe to run repeatedly.
* **Sync unsynced products only** – Only process products that have no
  Weaviate UUID yet. Faster for incremental updates.
* **Reset collection and re-index all** – Drop the Weaviate collection and
  rebuild it from scratch. Use when you change the collection schema or want a
  clean slate.

Backend Search
--------------

Once **Enable Weaviate Backend Search** is turned on in Settings, the search
bar in the product list view sends text queries to Weaviate. Non-text filters
(e.g., category, price range) are preserved and ANDed with the Weaviate
results.

eCommerce Shop Search
---------------------

Once **Enable Weaviate eCommerce Shop Search** is turned on, visiting
``/shop?search=<query>`` routes the search through Weaviate. Results are
ordered by Weaviate relevance score. The feature requires the ``website_sale``
module to be installed.

Tuning
------

* **Result Limit** – Controls how many products Weaviate returns. Increase
  for large catalogues with many synonyms; decrease for faster responses.
* **Hybrid Alpha** – ``0.0`` gives pure keyword (BM25) matching;
  ``1.0`` gives pure semantic vector matching; ``0.5`` (default) blends both.
  Increase towards ``1.0`` for concept-based queries ("eco-friendly packaging");
  decrease towards ``0.0`` for exact SKU or barcode lookups.
