# Platform UI access (NodePort + Ingress)

Lab access on the **node / LAN IP** without `kubectl port-forward` where possible.
Services stay private to your LAN — do not publish these ports to the public
internet without TLS + real auth.

On this lab the LAN address is often **`172.16.10.135`** (host Wi‑Fi). If k3s
runs in Docker, that is the host IP; Docker must publish the NodePorts
(see below). The k3s node InternalIP may still be `172.17.0.2` (bridge only).

## Ports (fixed)

| UI / API | URL | Auth / notes |
|----------|-----|----------------|
| **Headlamp** | `http://<node-ip>:30080/` | SA token — [headlamp.md](headlamp.md) |
| **Argo CD** | `https://<node-ip>:30443/` | `admin` + initial secret |
| **Argo CD (HTTP)** | `http://<node-ip>:30081/` | Often redirects to HTTPS |
| **Vault UI** | `http://<node-ip>:30200/` | Root/app token after init+unseal — [vault-eso-setup.md](vault-eso-setup.md) |
| **agentgateway** (OpenAI proxy) | `http://<node-ip>:30100/` | No client key; gateway uses Vault OpenAI key — [agentgateway-langfuse.md](agentgateway-langfuse.md) |
| **Langfuse** | `http://<node-ip>:30300/` | First-user signup in UI |

### Ingress hosts (Traefik `:80`)

Map in client `/etc/hosts`:

```text
<node-ip>  whoami.viper.local headlamp.viper.local langfuse.viper.local
```

| Host | Target |
|------|--------|
| `whoami.viper.local` | Demo whoami |
| `headlamp.viper.local` | Headlamp (token login) |
| `langfuse.viper.local` | Langfuse UI |

Get the IP:

```bash
# Prefer LAN IP of the host (e.g. 172.16.10.135) for other devices on the subnet
ip -4 addr show
# k3s node InternalIP (may be Docker bridge):
kubectl get nodes -o wide
```

## Docker k3s host port maps

If k3s runs in a container, publish at least:

`80`, `443`, `6443`, `30080`, `30081`, `30200`, `30443`, **`30100`**, **`30300`**.

## Argo CD login

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Open `https://<node-ip>:30443/`, user **admin**, accept the self-signed cert warning.

## Headlamp login

```bash
kubectl -n headlamp create token headlamp --duration=12h
```

## Vault UI

Initialize and unseal first. After every pod/node restart:

```bash
~/.config/k8s-viper/vault-unseal.sh   # if you use the lab helper
# or: kubectl -n vault exec vault-0 -- vault operator unseal
```

## agentgateway (OpenAI)

```bash
export GW=http://172.16.10.135:30100   # or your node-ip

curl -sS "$GW/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-5.5","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":64}'

# small model
curl -sS "$GW/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-5-mini","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":64}'
```

Models: **`gpt-5.5`** (full), **`gpt-5-mini`** (small). Details:
[agentgateway-langfuse.md](agentgateway-langfuse.md).

## Langfuse

1. Open `http://<node-ip>:30300/` and create the first user.  
2. **Settings → API Keys** → store in Vault for OTEL (same runbook).

## Change ports later

| Component | Where |
|-----------|--------|
| Headlamp | `platform/headlamp/values.yaml` → `service.nodePort` |
| Vault UI | `platform/vault/values.yaml` → `ui.serviceNodePort` |
| Argo CD | `platform/argocd-access/argocd-server-nodeport.yaml` |
| agentgateway | `platform/agentgateway-ai/gateway.yaml` → Service `nodePort` |
| Langfuse | `platform/langfuse/values.yaml` → `langfuse.web.service.nodePort` |

PR → merge `main` → Argo auto-syncs. NodePort range **30000–32767**.

## Security

- Token / password auth only; no SSO in v1.  
- Headlamp chart uses `cluster-admin` for a full lab view.  
- Prefer LAN-only access (`172.16.10.0/24`).  
- Never commit OpenAI or Langfuse secrets.

## Ingress controller

HTTP hosts on `:80` use **k3s Traefik** (cluster edge), not kgateway as the
default Ingress. agentgateway is the **AI/LLM data plane** (Gateway API),
separate from Traefik. See [why-traefik.md](why-traefik.md) and
[agentgateway-langfuse.md](agentgateway-langfuse.md).
