# Product Weaviate Search

Syncs `product.template` records to a [Weaviate](https://weaviate.io) vector database and replaces the backend product list search — and optionally the eCommerce `/shop` search — with Weaviate **hybrid search** (BM25 + vector similarity).

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start (Docker Compose)](#quick-start-docker-compose)
- [Configuration](#configuration)
- [Syncing Products](#syncing-products)
- [Searching](#searching)
- [Technical Details](#technical-details)

---

## Features

- **Real-time sync** — products are pushed to Weaviate automatically on create / write / unlink (configurable — can be disabled in Settings).
- **Backend hybrid search** — the product list search bar uses Weaviate instead of SQL `ILIKE`, returning semantically relevant results ordered by relevance score.
- **eCommerce shop search** — optionally replaces the `/shop?search=` endpoint (requires the *eCommerce* `website_sale` module).
- **Bulk sync wizard** — sync all products, only unsynced ones, or reset and re-index the entire collection in one click, accessible from Settings or from the product list Action menu.
- **Score column** — search results show the Weaviate relevance score (0.0–1.0) in the product list view.
- **Per-search toggle** — "Weaviate Search" / "Standard Search" filters in the product list search bar let you switch engines per query.
- **Vectorizer** — `text2vec-openai` (requires an OpenAI API key).

---

## Prerequisites

- **Odoo 19.0**
- **Weaviate** ≥ 1.28 running with the `text2vec-openai` module enabled (other should follow next)
- **Python package** `weaviate-client >= 4.0` (installed automatically via `external_dependencies`)
- **OpenAI API key** for the `text2vec-openai` vectorizer

---

## Quick Start (Docker Compose)

The repository ships a ready-to-use Docker Compose stack that runs Odoo 19, PostgreSQL, and Weaviate together.

**1. Copy the env file and add your OpenAI key**

```bash
cp docker/.env.example docker/.env
# Edit docker/.env and set:  OPENAI_API_KEY=sk-...
```

**2. Start the stack**

```bash
docker compose -f docker/docker-compose.yml up -d
```

**3. Open Odoo** at http://localhost:8069 and create a new database.
When prompted, check **Load demo data** — this pre-fills the Weaviate connection settings for the Docker stack.

> **OpenAI key note:** Because `OPENAI_API_KEY` in `docker/.env` is passed directly to the Weaviate container as `OPENAI_APIKEY`, Weaviate can vectorize requests without the key being re-entered in Odoo. The *OpenAI API Key* field in Settings is therefore **optional** for the Docker stack — leave it blank and Weaviate will use its own environment variable. You only need to fill it in if you want Odoo to forward the key explicitly (e.g. when Weaviate does *not* have it in its environment, such as a Weaviate Cloud deployment or a custom instance without the env var).

| Service       | URL / Address         |
|---------------|-----------------------|
| Odoo          | http://localhost:8069 |
| Weaviate HTTP | http://localhost:8080 |
| Weaviate gRPC | localhost:50051       |

**4. Install the addon** — go to **Apps**, remove the "Apps" filter, search for *Product Weaviate Search*, and install it.

---

## Configuration

Go to **Settings → Weaviate**.

### Docker / local setup

If you used the included Docker Compose stack **and loaded demo data**, the connection fields are already filled in:

| Field           | Value                                           |
|-----------------|-------------------------------------------------|
| Deployment Type | Custom                                          |
| HTTP Host       | `weaviate`                                      |
| HTTP Port       | `8080`                                          |
| gRPC Host       | `weaviate`                                      |
| gRPC Port       | `50051`                                         |
| OpenAI API Key  | *(optional — see note below)*                   |
| Collection Name | `OdooProduct`                                   |

**OpenAI API Key — Docker stack:** When `OPENAI_API_KEY` is set in `docker/.env`, Docker Compose passes it to the Weaviate container as its own `OPENAI_APIKEY` environment variable. Weaviate then uses it automatically for every vectorization request, so **you do not need to enter it again in Odoo Settings**. Leave the field blank and everything works.

Fill the field only when Weaviate does *not* have the key in its own environment — for example a Weaviate Cloud deployment or a self-hosted instance started without the env var. In those cases Odoo forwards the key as the `X-OpenAI-Api-Key` request header on every call.

### Weaviate Cloud setup

Select **Weaviate Cloud** as the Deployment Type and fill in:

- **Cluster URL** — e.g. `https://your-cluster.weaviate.cloud`
- **Weaviate API Key** — your WCD cluster key
- **OpenAI API Key** — your OpenAI key

### Loading demo data after install

If the database was created **without** demo data, you can load it afterwards:

1. Open Settings in debug mode: navigate to `http://localhost:8069/odoo/settings?debug=1` (or append `?debug=1` to the current Settings URL and reload).
2. Scroll to the very bottom of the Settings page and click **Load Demo Data**.

### Enable search features

After saving the connection settings, scroll to **Search Features** and enable:

- **Live Sync** — push products to Weaviate on every create / update / delete. Disable during bulk imports or data migrations.
- **Backend Product Search** — replaces the product list search bar.
- **eCommerce Shop Search** — replaces `/shop?search=` (requires `website_sale`).

---

## Syncing Products

Products must be indexed in Weaviate before search works.

### From Settings

Go to **Settings → Weaviate → Product Sync** and click **Open Sync Wizard**.

### From the Product List

1. Go to **Sales → Products** (or **Inventory → Products**).
2. Switch to **list view** (the list icon next to the grid icon).
3. Optionally **select specific products** — or leave all unselected to choose a bulk mode in the wizard.
4. Click **Action → Sync with Weaviate**.

### Sync modes

| Mode                        | What it does                                                                              |
|-----------------------------|-------------------------------------------------------------------------------------------|
| Sync selected products only | Upserts only the products you selected in the list view.                                  |
| Sync all products           | Upserts every active and inactive product.                                                |
| Sync unsynced products only | Upserts only products that have no Weaviate UUID yet (new since the last full sync).      |
| Reset and re-index          | Drops the Weaviate collection, recreates it, and re-indexes every product from scratch. Use after schema changes or data corruption. |

---

## Searching

### Backend (product list)

When *Backend Product Search* is enabled, typing in the product list search bar sends the query to Weaviate. Results are:

- Ordered by **relevance score** (highest first).
- Filtered to active products only (via Weaviate, before results reach SQL).
- Shown with a **Score** column (0.0–1.0) in the list.

### Per-search engine toggle

In the product list search bar, open the **Filters** dropdown and select:

- **Weaviate Search** — forces hybrid search for this session.
- **Standard Search** — forces standard Odoo SQL search, ignoring the global toggle.

These filters override the global *Backend Product Search* setting for the duration of the current filter selection.

### eCommerce shop

When *eCommerce Shop Search* is enabled, `/shop?search=<query>` routes the query through Weaviate. Falls back to the standard Odoo fuzzy search if Weaviate is unreachable.

---

## Technical Details

### Weaviate collection schema

Collection name: `OdooProduct` (configurable)

| Property            | Type    | Vectorized |
|---------------------|---------|------------|
| odoo_id             | INT     | No         |
| name                | TEXT    | Yes        |
| description         | TEXT    | Yes        |
| description_sale    | TEXT    | Yes        |
| default_code        | TEXT    | No         |
| barcode             | TEXT    | No         |
| categ_name          | TEXT    | Yes        |
| list_price          | NUMBER  | No         |
| active              | BOOLEAN | No         |
| website_description | TEXT    | Yes        |

### Hybrid search parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Alpha     | `0.5`   | Balance between BM25 keyword (0.0) and pure vector search (1.0). Tunable in Settings. |
| Fusion    | `RELATIVE_SCORE` | Scores normalised to 0.0–1.0. |
| Limit     | `50`    | Maximum results returned per query. |

### UUID strategy

Each product is assigned a **deterministic UUID** derived from its Odoo database ID using `weaviate.util.generate_uuid5`. This enables true upsert semantics — re-syncing a product always overwrites the same Weaviate object, with no duplicates.

### Multi-worker safety

`WeaviateService` is a stateless pure-Python class. Every public method opens a fresh connection, performs its work, and closes it in a `finally` block — safe for Odoo's multi-worker (multi-process) architecture.

### Failure isolation

All Weaviate calls (sync and search) are wrapped in `try/except`. Failures are logged as `WARNING` and never raise an exception to the Odoo user. A Weaviate outage does not block product saves or page loads.

### Odoo 19 notes

- Uses `odoo.fields.Domain` for domain manipulation (`odoo.osv.expression` is deprecated in Odoo 19).
- The search result ordering hook is on `search_fetch()` — in Odoo 19 the list view RPC chain is `web_search_read → search_read → search_fetch → _search`, and `search()` is bypassed.

---

## Credits

**Authors:** Odoo Community Association (OCA)

**License:** [GNU Affero General Public License v3 or later (AGPLv3+)](https://www.gnu.org/licenses/agpl-3.0.html)
