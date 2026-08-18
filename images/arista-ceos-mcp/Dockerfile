# Arista EOS eAPI MCP tools (read-only cEOS lab).
# Local tag: arista-ceos-mcp:dev  (ctr images import on the k3s node)
# STREAMABLE_HTTP on :8084 /mcp. Creds from env (Vault/ESO). Do not bake secrets in.
# TLS verify defaults ON in the process; the lab Deployment sets ARISTA_VERIFY_TLS=false.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8084

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin mcp

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && rm -rf /root/.cache/pip

COPY --chown=mcp:mcp server.py /app/server.py

USER 1000:1000
EXPOSE 8084
CMD ["python", "/app/server.py"]
