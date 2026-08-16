# fortigate-mcp (FortiOS tools)

Small FastMCP **STREAMABLE_HTTP** server for Sebastian's home FortiGate
(`fw-maniak-hq`, FortiGate 80F, FortiOS 7.4.11). Listens on **`:8084/mcp`**
— same shape as live `RemoteMCPServer/kagent-tool-server`
(`http://kagent-tools.kagent:8084/mcp`).

Intended tags:

- local / node import: `fortigate-mcp:dev`
- published name: `ghcr.io/sebbycorp/fortigate-mcp:dev`

The Deployment uses `fortigate-mcp:dev` with `imagePullPolicy: IfNotPresent`.
Import the image **before** the pod can start.

```bash
# on Viper
docker build -t fortigate-mcp:dev images/fortigate-mcp
docker save fortigate-mcp:dev | docker exec -i k3s-viper ctr images import -
```

Env (no secrets in the image):

| Variable | Default | Source |
|----------|---------|--------|
| `FORTIGATE_HOST` | `https://172.16.10.1` | Vault `secret/platform/fortigate` key `host` |
| `FORTIGATE_TOKEN` | (required) | Vault `secret/platform/fortigate` key `token` |
| `FORTIGATE_VERIFY_TLS` | `false` | lab self-signed cert (`curl -k`) |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8084` | listen address |

Auth to FortiOS is `Authorization: Bearer $FORTIGATE_TOKEN`. The process
never prints the token. Health: `GET /health`.

Agent runbook: [docs/fortigate-agent.md](../../docs/fortigate-agent.md).
