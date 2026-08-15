# Platform UI access (NodePort + Ingress)

Lab access on the **node / LAN IP** without `kubectl port-forward` where possible.
Services stay private to your LAN — do not publish these ports to the public
internet without TLS + real auth.

On Viper the LAN address is **`172.16.10.135`**. k3s is dockerized (`k3s-viper`);
that is the host IP. Docker must publish the NodePorts (see below). The k3s
node InternalIP may still be `172.17.0.2` (bridge only).

Talk to the cluster with `docker exec k3s-viper kubectl ...` (kubectl is not on
the host PATH).

ngrok TCP is used for **SSH to the box** (`ssh smaniak@2.tcp.ngrok.io -p <port>`),
not for exposing these UIs.

## Ports (fixed)

| UI / API | URL | Auth / notes |
|----------|-----|----------------|
| **Headlamp** | `http://172.16.10.135:30080/` | SA token — [headlamp.md](headlamp.md) |
| **Argo CD** | `https://172.16.10.135:30443/` | `admin` + initial secret |
| **Argo CD (HTTP)** | `http://172.16.10.135:30081/` | Often redirects to HTTPS |
| **Vault UI** | `http://172.16.10.135:30200/` | Root/app token after init+unseal — [vault-eso-setup.md](vault-eso-setup.md) |
| **agentgateway** (OpenAI `/v1` · Spark `/spark` · desktop `/desktop/`) | `http://172.16.10.135:30100/` | One Gateway. `GET /` → 404 is expected — [agentgateway-langfuse.md](agentgateway-langfuse.md) |
| **Desktop viewer** (noVNC) | `http://172.16.10.135:30100/desktop/` | Lab-open VNC behind the gateway — [desktop-computer-use.md](desktop-computer-use.md) |
| **Desktop computer-use API** | `http://172.16.10.135:30100/desktop-api/health` | No auth in the process; import `viper-desktop:dev` first |
| **Langfuse** | `http://172.16.10.135:30300/` | First-user signup in UI |
| **kagent UI** | `http://172.16.10.135:30500/` | OSS kagent 0.10.0-rc2 + Agent Substrate. Chat with `hello-substrate` — [kagent-substrate.md](kagent-substrate.md) |

### Ingress hosts (Traefik `:80`)

Map in client `/etc/hosts`:

```text
172.16.10.135  whoami.viper.local headlamp.viper.local langfuse.viper.local
```

| Host | Target |
|------|--------|
| `whoami.viper.local` | Demo whoami |
| `headlamp.viper.local` | Headlamp (token login) |
| `langfuse.viper.local` | Langfuse UI |

Get the IP:

```bash
# Prefer LAN IP of the host (172.16.10.135) for other devices on the subnet
ip -4 addr show
# k3s node InternalIP (may be Docker bridge):
docker exec k3s-viper kubectl get nodes -o wide
```

## Docker k3s host port maps

If k3s runs in a container, publish at least:

`80`, `443`, `6443`, `30080`, `30081`, `30200`, `30443`, **`30100`**, **`30300`**, **`30500`**.

## Argo CD login

```bash
docker exec k3s-viper kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Open `https://172.16.10.135:30443/`, user **admin**, accept the self-signed cert warning.

## Headlamp login

```bash
docker exec k3s-viper kubectl -n headlamp create token headlamp --duration=12h
```

## Vault UI

Initialize and unseal first. After every pod/node restart:

```bash
~/.config/k8s-viper/vault-unseal.sh   # if you use the lab helper
# or: docker exec k3s-viper kubectl -n vault exec vault-0 -- vault operator unseal
```

## agentgateway (one Gateway, OpenAI + Spark + desktop)

Same Gateway (`agentgateway-proxy` :30100). `GET /` returns 404 `route not found`
— expected. `svclb-agentgateway-proxy` Pending is cosmetic (Traefik owns `:80`).

```bash
export GW=http://172.16.10.135:30100

# OpenAI
curl -sS "$GW/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-5.5","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":64}'

# small model
curl -sS "$GW/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-5-mini","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":64}'

# DGX Spark (vLLM)
curl -sS "$GW/spark/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{"model":"Qwen/Qwen3.6-35B-A3B-FP8","messages":[{"role":"user","content":"hi"}],"max_tokens":64}'
```

| Path | Backend | Model |
|------|---------|-------|
| `/v1`, `/openai` | OpenAI (Vault key) | `gpt-5.5`, `gpt-5-mini` |
| `/spark` | DGX Spark `172.16.10.173:8000` | `Qwen/Qwen3.6-35B-A3B-FP8` |
| `/desktop/` | desktop-computer-use :6080 (noVNC) | viewer |
| `/desktop-api/` | desktop-computer-use :18790 | computer-use HTTP API |

Details: [agentgateway-langfuse.md](agentgateway-langfuse.md).

## Langfuse

1. Open `http://172.16.10.135:30300/` and create the first user.  
2. **Settings → API Keys** → store in Vault for OTEL (same runbook).

## Change ports later

| Component | Where |
|-----------|--------|
| Headlamp | `platform/headlamp/values.yaml` → `service.nodePort` |
| Vault UI | `platform/vault/values.yaml` → `ui.serviceNodePort` |
| Argo CD | `platform/argocd-access/argocd-server-nodeport.yaml` |
| agentgateway | `platform/agentgateway-ai/gateway.yaml` → Service `nodePort` |
| Langfuse | `platform/langfuse/values.yaml` → `langfuse.web.service.nodePort` |
| kagent UI | `platform/kagent-ai/ui-nodeport.yaml` (Helm UI Service has no `nodePort` field) |

PR → merge `main` → Argo auto-syncs. NodePort range **30000–32767**.

## Security

- Token / password auth only; no SSO in v1.  
- Headlamp chart uses `cluster-admin` for a full lab view.  
- Prefer LAN-only access (`172.16.10.0/24`).  
- Never commit OpenAI or Langfuse secrets. kagent's `kagent-openai` Secret is a dummy (`sk-routed-via-agentgateway`); the gateway holds the real key.

## Ingress controller

HTTP hosts on `:80` use **k3s Traefik** (cluster edge), not kgateway as the
default Ingress. agentgateway is the **AI/LLM data plane** (Gateway API),
separate from Traefik. See [why-traefik.md](why-traefik.md) and
[agentgateway-langfuse.md](agentgateway-langfuse.md).
