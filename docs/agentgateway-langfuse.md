# agentgateway + OpenAI + Langfuse

Lab stack for **AI traffic** on k8s-viper:

- **agentgateway** `1.4.1` — Gateway API data plane for LLMs  
- **OpenAI** backend using Vault key `secret/platform/openai`  
- **Models** (client-selected): `gpt-5.5` (full), `gpt-5-mini` (small)  
- **Langfuse** `1.5.41` (+ Postgres, Redis, **ClickHouse**, MinIO) for LLM observability  
- **OTel collector** bridges gateway traces → Langfuse OTLP  

## Access

| Service | URL |
|---------|-----|
| agentgateway (OpenAI proxy) | `http://<node-ip>:30100/` |
| Langfuse UI | `http://<node-ip>:30300/` or `http://langfuse.viper.local/` |
| Vault | `http://<node-ip>:30200/` |

Docker k3s: publish host ports **30100** and **30300** (and keep 80 for Traefik).

`/etc/hosts`:

```text
<node-ip>  langfuse.viper.local headlamp.viper.local whoami.viper.local
```

## Vault paths (no secrets in git)

| Path | Contents |
|------|----------|
| `secret/platform/openai` | `api_key` (OpenAI) |
| `secret/platform/langfuse` | salt, encryption_key, nextauth_secret, DB passwords |
| `secret/platform/langfuse-otel` | `public_key`, `secret_key`, `endpoint` (after project keys) |

## Call OpenAI through agentgateway

```bash
export GW=http://172.16.10.135:30100

# Full model
curl -sS "$GW/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{
    "model": "gpt-5.5",
    "messages": [{"role":"user","content":"Say hello from k8s-viper"}],
    "max_completion_tokens": 64
  }' | jq .

# Small model
curl -sS "$GW/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{
    "model": "gpt-5-mini",
    "messages": [{"role":"user","content":"Say hello briefly"}],
    "max_completion_tokens": 64
  }' | jq .
```

Verified on this lab: `gpt-5.5` works; use `gpt-5-mini` for the small model (`gpt-5.5-mini` is not a valid OpenAI id for this key).

No OpenAI key in the client request — the gateway injects it from Vault via ExternalSecret.

## Wire traces to Langfuse

1. Open Langfuse UI → sign up (first user) → **Settings → API Keys** → create keys.  
2. Store in Vault (after unseal):

```bash
ROOT=$(python3 -c "import json; print(json.load(open('$HOME/.config/k8s-viper/vault-init.json'))['root_token_initial'])")
kubectl -n vault exec vault-0 -- sh -c "
export VAULT_TOKEN='$ROOT'
vault kv put secret/platform/langfuse-otel \
  public_key='pk-lf-...' \
  secret_key='sk-lf-...' \
  endpoint='http://langfuse-web.langfuse.svc.cluster.local:3000/api/public/otel'
"
```

3. ExternalSecret `langfuse-otel-auth` refreshes; restart collector if needed:

```bash
kubectl -n agentgateway-system rollout restart deploy/langfuse-otel-collector
```

4. Send a chat completion through the gateway; open Langfuse **Traces**.

### Proxy → collector

Configure the agentgateway **proxy** pods to export OTEL (env on the data plane). After Gateway is programmed, annotate or patch the proxy Deployment if the controller does not inject OTEL by default:

```bash
kubectl -n agentgateway-system set env deploy/agentgateway-proxy \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-otel-collector.agentgateway-system.svc.cluster.local:4317 \
  OTEL_EXPORTER_OTLP_PROTOCOL=grpc \
  OTEL_SERVICE_NAME=agentgateway-proxy
```

(Re-apply after controller recreates the proxy Deployment.)

## Argo apps

| Application | Role |
|-------------|------|
| `platform-gateway-api` | Gateway API CRDs |
| `platform-agentgateway-crds` | agentgateway CRDs Helm |
| `platform-agentgateway` | control plane Helm |
| `platform-agentgateway-ai` | Gateway, OpenAI backend, routes, OTEL |
| `platform-langfuse-secrets` | NS + ExternalSecret |
| `platform-langfuse` | Langfuse Helm (+ ClickHouse, etc.) |

## Ops notes

- Unseal Vault after every restart: `~/.config/k8s-viper/vault-unseal.sh`  
- Single-node lab: ClickHouse **1 replica**, small resources — not production HA.  
- If a model name is rejected by OpenAI, change the `model` field in the curl body (API truth > docs).  
- Never commit API keys or Langfuse secrets.
