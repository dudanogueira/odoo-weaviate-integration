FROM odoo:19.0

USER root

# Install the Weaviate Python client (v4) and its gRPC dependencies.
RUN pip install --no-cache-dir --break-system-packages --ignore-installed "weaviate-client>=4.0.0"

USER odoo
