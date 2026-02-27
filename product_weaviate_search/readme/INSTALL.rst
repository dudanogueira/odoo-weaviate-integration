Prerequisites
-------------

1. A running Weaviate instance (≥ 1.23.7) with the ``text2vec-openai`` module
   enabled. See the included ``docker/docker-compose.yml`` for a ready-to-use
   local stack.

2. An OpenAI API key with access to the ``text-embedding-ada-002`` model (or
   any model supported by Weaviate's ``text2vec-openai``).

3. The ``weaviate-client`` Python package (≥ 4.0.0) must be installed in the
   Odoo Python environment::

       pip install "weaviate-client>=4.0.0"

   Or add it to your project's ``requirements.txt``.

Installation
------------

1. Copy (or symlink) the ``product_weaviate_search`` directory into your Odoo
   ``addons`` path.
2. Restart the Odoo service.
3. Go to **Apps** and install **Product Weaviate Search**.
4. Navigate to **Settings → Weaviate** and configure:

   - Deployment type (Local or Weaviate Cloud)
   - Weaviate URL
   - OpenAI API Key
   - Enable Backend Search and/or eCommerce Shop Search

5. Open the **Products** list, click **Action → Sync with Weaviate**, choose
   *Sync all products*, and click **Start Sync**.

Docker Quick Start
------------------

A full development stack (Odoo 19 + PostgreSQL + Weaviate) is provided::

    cp docker/.env.example docker/.env
    # Edit docker/.env and set OPENAI_API_KEY=sk-...
    docker compose -f docker/docker-compose.yml up -d
