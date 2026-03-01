# Weaviate Addons for Odoo

[![Build Status](https://github.com/OCA/weaviate/actions/workflows/test.yml/badge.svg?branch=19.0)](https://github.com/OCA/weaviate/actions/workflows/test.yml?query=branch%3A19.0)
[![Pre-commit Status](https://results.pre-commit.ci/badge/github/OCA/weaviate/19.0.svg)](https://results.pre-commit.ci/latest/github/OCA/weaviate/19.0)
[![codecov](https://codecov.io/gh/OCA/weaviate/branch/19.0/graph/badge.svg)](https://codecov.io/gh/OCA/weaviate)

Odoo addons that integrate [Weaviate](https://weaviate.io) vector search into Odoo for AI-powered semantic search and hybrid retrieval across business data.

Compatible with **Odoo 19.0**. License: **AGPL-3**.

---

## Available Addons

| Module | Version | Summary |
|--------|---------|---------|
| [product_weaviate_search](product_weaviate_search/) | 19.0.1.0.0 | Syncs products to Weaviate and replaces backend and eCommerce search with hybrid vector search |

---

## Planned Addons

The following modules are under consideration for future releases:

| Module | Summary |
|--------|---------|
| `partner_weaviate_search` | Semantic search for customers and vendors using Weaviate hybrid retrieval |
| `helpdesk_weaviate_search` | AI-powered ticket lookup and knowledge base search via Weaviate |
| `weaviate_base` | Shared Weaviate connection management and base service extracted from individual modules |

> Want to propose a new module? Open an issue or a pull request.

---

## Development

### Requirements

- Python 3.11+
- Odoo 19.0 source tree (or a running Odoo container)
- `weaviate-client >= 4.0` — installed automatically when Odoo loads `external_dependencies`

Install Python dev dependencies:

```bash
pip install weaviate-client pytest-odoo pre-commit
```

### Quick Start (Docker)

The repository ships a full Docker Compose stack (Odoo 19 + PostgreSQL 16 + Weaviate):

```bash
cp docker/.env.example docker/.env   # set OPENAI_API_KEY
docker compose -f docker/docker-compose.yml up -d
```

See [product_weaviate_search/README.md](product_weaviate_search/README.md) for full configuration and usage instructions.

### Code Quality

This project uses [pre-commit](https://pre-commit.com/) for linting and formatting.

```bash
pre-commit install        # install hooks into the local git repo
pre-commit run --all-files  # run all checks once
```

Hooks enforce: `ruff` (linting + import sorting), `black` (formatting), and the OCA standard checks (`oca-checks-odoo-module`).

---

## Running Tests

Tests live in `<module>/tests/` and follow the standard Odoo test conventions.
No live Weaviate instance is required — all external calls are mocked in the test suite.

### With pytest-odoo (recommended for local dev)

```bash
# From the repo root:
python -m pytest product_weaviate_search/tests/ \
    --odoo-database=<db_name> \
    --odoo-addons-path=. \
    -v
```

### With the Odoo test runner

```bash
# Inside your Odoo source directory or Docker container:
python odoo-bin -d <db_name> \
    --addons-path=<path_to_this_repo> \
    --test-enable \
    --stop-after-init \
    -i product_weaviate_search
```

### With Docker Compose

```bash
docker compose -f docker/docker-compose.yml run --rm odoo \
    python odoo-bin -d testdb \
    --addons-path=/mnt/extra-addons \
    --test-enable --stop-after-init \
    -i product_weaviate_search
```

---

## Test Plan

### Current coverage (23 tests across 3 files)

| File | Class | Tests | What it covers |
|------|-------|-------|----------------|
| `test_backend_search.py` | `TestExtractWeaviateQuery` | 7 | Domain extraction helper — all edge cases |
| `test_backend_search.py` | `TestBackendSearch` | 4 | `_search()` override — enable/disable/error/id injection |
| `test_product_sync.py` | `TestProductSync` | 7 | ORM hooks — create/write/unlink and `_weaviate_product_data()` |
| `test_weaviate_service.py` | `TestWeaviateServiceFromConfig` | 3 | `from_config()` factory — URL absent, URL set, default collection name |
| `test_weaviate_service.py` | `TestWeaviateServiceHybridSearch` | 2 | `hybrid_search()` — result parsing, empty results |

### Gaps to close (priority order)

#### 1. `tests/test_sync_wizard.py` — Bulk sync wizard

The four sync modes in `ProductWeaviateSyncWizard` are not covered yet.

```
TestSyncWizardSelectedProducts   test_sync_selected_calls_upsert_for_each
TestSyncWizardAllProducts        test_sync_all_products_calls_batch_insert
TestSyncWizardUnsyncedProducts   test_sync_unsynced_skips_products_with_uuid
TestSyncWizardResetReindex       test_reset_drops_collection_then_reinserts
                                 test_reset_calls_ensure_collection
```

#### 2. `tests/test_config_settings.py` — `res.config.settings` round-trip

Verify that the settings form reads from and writes to `ir.config_parameter` correctly.

```
TestConfigSettings   test_backend_search_toggle_persists
                     test_live_sync_toggle_persists
                     test_weaviate_url_persists
                     test_collection_name_defaults_to_OdooProduct
```

#### 3. `tests/test_search_fetch.py` — score-sorted `search_fetch()`

The current `TestBackendSearch` tests call `_search()` directly. We also need to verify that `search_fetch()` returns records ordered by Weaviate score, since that is the actual hook used by the Odoo 19 list view RPC chain (`web_search_read → search_read → search_fetch`).

```
TestSearchFetch   test_search_fetch_orders_by_weaviate_score
                  test_search_fetch_falls_back_to_orm_when_no_text_term
                  test_search_fetch_clears_score_cache_between_calls
```

#### 4. `tests/test_website_sale.py` — eCommerce controller (optional / HTTP)

Requires `website_sale` and uses `HttpCase`. Tagged `post_install` so it runs only after a full install.

```
TestWebsiteSaleSearch   test_shop_search_routes_through_weaviate
                        test_shop_search_falls_back_on_error
```

### Adding `@tagged` decorators

OCA tests use the `@tagged` decorator to allow selective test execution. The existing classes should be updated to add the appropriate tags:

```python
from odoo.tests.common import tagged

@tagged("product_weaviate", "-at_install", "post_install")
class TestBackendSearch(WeaviateTestCommon):
    ...
```

Standard OCA tags:
- `post_install` / `-at_install` — run after module installation, skip at-install phase
- `at_install` — run during module installation (for data/constraint checks)
- A module-scoped tag (`product_weaviate`) to let CI filter just this module's tests

### Setting up CI (GitHub Actions)

Create `.github/workflows/test.yml` using the OCA composite action:

```yaml
name: CI
on:
  push:
    branches: ["19.0"]
  pull_request:
    branches: ["19.0"]

jobs:
  test:
    uses: OCA/odoo-github-actions/.github/workflows/test.yml@v0
    with:
      odoo_version: "19.0"
    secrets: inherit
```

Also add `.github/workflows/pre-commit.yml` for automatic lint checks on every PR.

### Coverage targets

| Area | Current | Target |
|------|---------|--------|
| `weaviate_service.py` | Partial (factory + hybrid_search) | 85 %+ |
| `product_template.py` | ORM hooks + `_search` | `search_fetch` score-sort + liveSync toggle |
| `product_weaviate_sync_wizard.py` | None | All 4 modes |
| `res_config_settings.py` | None | Read/write cycle for all params |
| `website_sale.py` | None | Happy path + fallback |

---

## Contributing

This project follows the [OCA Contributing Guidelines](https://github.com/OCA/maintainer-tools/blob/master/CONTRIBUTING.md).

1. Fork the repository and create a branch from `19.0`.
2. Run `pre-commit install` before committing.
3. Add or update tests for every change.
4. Open a pull request against the `19.0` branch.

All contributions are subject to the [Odoo Community Association CLA](https://odoo-community.org/cla).

---

## License

This repository is licensed under the [GNU Affero General Public License v3 or later (AGPLv3+)](https://www.gnu.org/licenses/agpl-3.0.html).
