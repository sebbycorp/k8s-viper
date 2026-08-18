# arista-ceos-mcp (Arista EOS eAPI tools)

Read-only FastMCP **STREAMABLE_HTTP** server for the isolated Containerlab
cEOS demo (`spine1`, `leaf1`, `leaf2`). Listens on **`:8084/mcp`** — same
shape as live `RemoteMCPServer/kagent-tool-server` and `f5-bigip-mcp`.

Intended tags:

- local / node import: `arista-ceos-mcp:dev`
- published name: `ghcr.io/sebbycorp/arista-ceos-mcp:dev`

The Deployment uses `arista-ceos-mcp:dev` with `imagePullPolicy: IfNotPresent`.
Import the image **before** the pod can start.

```bash
# on Viper
docker build -t arista-ceos-mcp:dev images/arista-ceos-mcp
docker save arista-ceos-mcp:dev | docker exec -i k3s-viper ctr images import -
```

Env (no secrets in the image):

| Variable | Default | Source |
|----------|---------|--------|
| `ARISTA_HOSTS_JSON` | (required) | Vault `secret/platform/arista-ceos` key `hosts_json` (alias `hosts` → `ARISTA_HOSTS`) |
| `ARISTA_USERNAME` | (required unless per-node) | Vault key `username` |
| `ARISTA_PASSWORD` | (required unless per-node) | Vault key `password` |
| `ARISTA_ALLOWED_NODES` | `spine1,leaf1,leaf2` | Deployment (strict allowlist) |
| `ARISTA_VERIFY_TLS` | `true` (safe default) | lab Deployment sets `false` for Containerlab / self-signed |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8084` | listen address |

Auth to eAPI is HTTP Basic. The process never prints the password.
Health: `GET /health`. Tools accept **node names only** — never a URL.

Agent runbook: [docs/arista-ceos-agent.md](../../docs/arista-ceos-agent.md).
