# F5 BIG-IP SandboxAgent

Read-only VIP monitor for the lab BIG-IP at `172.16.10.10`.
Sibling of `fortigate` / `hello-substrate`. Pins unchanged:
kagent **0.10.0-rc2**, Agent Substrate **0.0.9**.

## Architecture

```text
kagent UI :30500
    → SandboxAgent/f5-bigip  (Go, gVisor, WorkerPool kagent-default)
        → RemoteMCPServer/f5-bigip-mcp
              http://f5-bigip-mcp.kagent:8084/mcp
            → Deployment/f5-bigip-mcp  (image f5-bigip-mcp:dev)
                → https://172.16.10.10/mgmt/tm/ltm/...   Basic auth from Vault
```

## Vault (key names only)

| | |
|--|--|
| Path | `secret/platform/f5-bigip` |
| Keys | `host`, `username`, `password` |
| Host | `https://172.16.10.10` |

Never commit the password.

## Import + apply

On Viper, after this PR is on main:

```bash
cd images/f5-bigip-mcp
docker build -t f5-bigip-mcp:dev .
docker save f5-bigip-mcp:dev | docker exec -i k3s-viper ctr images import -
# Argo syncs platform/kagent-ai, or:
kubectl kustomize platform/kagent-ai | docker exec -i k3s-viper kubectl apply -f -
```

## Example questions

- Which VIPs are down?
- Is `/Common/foo` available?
- What pool members sit behind that VIP?

A2A path: `POST /api/a2a-sandboxes/kagent/f5-bigip` (classic `/api/a2a/` 404s).
