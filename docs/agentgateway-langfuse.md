# agentgateway + OpenAI + DGX Spark + Langfuse

Lab stack for **AI traffic** on k8s-viper:

| Component | Version / notes |
|-----------|-----------------|
| **agentgateway** | Helm/chart **1.4.1** — Gateway API AI data plane |
| **OpenAI backend** | Vault `secret/platform/openai` → ExternalSecret → gateway auth |
| **OpenAI models** | Client-selected: **`gpt-5.5`** (full), **`gpt-5-mini`** (small) on `/v1` and `/openai` |
| **DGX Spark** | vLLM at `172.16.10.173:8000` — **`Qwen/Qwen3.6-35B-A3B-FP8`** on `/spark` (no auth) |
| **Langfuse** | Helm **1.5.41** (app ~3.224) + Postgres, Redis, **ClickHouse**, MinIO |
| **OTEL collector** | agentgateway traces → Langfuse OTLP HTTP |

Traefik remains the **cluster Ingress** for `*.viper.local`. agentgateway is
**not** a replacement for Traefik; it fronts LLM/API traffic. See
[why-traefik.md](why-traefik.md).

## Access

| Service | URL |
|---------|-----|
| agentgateway (OpenAI `/v1` · `/openai`; Spark `/spark`) | `http://<node-ip>:30100/` |
| Langfuse UI | `http://<node-ip>:30300/` or `http://langfuse.viper.local/` |
| Vault | `http://<node-ip>:30200/` |

LAN example: `http://172.16.10.135:30100/`.

Docker k3s must publish **30100** and **30300** (plus existing UI ports). Full
map: [platform-ui-access.md](platform-ui-access.md).

`/etc/hosts`:

```text
<node-ip>  langfuse.viper.local headlamp.viper.local whoami.viper.local
```

## Vault paths (no secrets in git)

| Path | Contents |
|------|----------|
| `secret/platform/openai` | `api_key` (OpenAI) |
| `secret/platform/langfuse` | salt, encryption_key, nextauth_secret, DB/MinIO passwords |
| `secret/platform/langfuse-otel` | `public_key`, `secret_key`, `endpoint` for OTLP |

Vault + ESO ops: [vault-eso-setup.md](vault-eso-setup.md).

## Call OpenAI through agentgateway

No OpenAI key in the client — the gateway injects Vault credentials.

```bash
export GW=http://172.16.10.135:30100   # or your node-ip

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

| Model id | Role |
|----------|------|
| `gpt-5.5` | Full / default quality (verified on this lab) |
| `gpt-5-mini` | Small / cheaper (verified) |
| `gpt-5.5-mini` | **Not** a valid id for this account — do not use |

Also available via the same backend when OpenAI allows them (e.g. `gpt-4o-mini`).

Git paths:

- Backend: `platform/agentgateway-ai/backend-openai.yaml`
- Route: `platform/agentgateway-ai/httproute-openai.yaml`
- OpenAI ExternalSecret: `platform/agentgateway-ai/external-secret-openai.yaml`

## Call DGX Spark through agentgateway

Same Gateway (`agentgateway-proxy` :30100). Path prefix `/spark` — no client key.
vLLM host/model from [k8s-goose](https://github.com/sebbycorp/k8s-goose) `config/backends/dgx-spark-llm.yaml`.

```bash
export GW=http://172.16.10.135:30100   # or your node-ip

curl -sS "$GW/spark/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role":"user","content":"Say hello from k8s-viper Spark"}],
    "max_tokens": 64
  }' | jq .
```

| Path | Backend | Model |
|------|---------|-------|
| `/v1`, `/openai` | OpenAI (`api.openai.com`) | `gpt-5.5`, `gpt-5-mini` |
| `/spark` | DGX Spark `172.16.10.173:8000` | `Qwen/Qwen3.6-35B-A3B-FP8` |

Git paths:

- Backend: `platform/agentgateway-ai/backend-dgx-spark.yaml`
- Route: `platform/agentgateway-ai/httproute-dgx-spark.yaml`

## Wire traces to Langfuse

1. Wait for Langfuse pods: `kubectl -n langfuse get pods`
2. Open Langfuse UI → first-user signup → **Settings → API Keys**
3. Store keys in Vault (Vault unsealed):

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

4. ExternalSecret `langfuse-otel-auth` refreshes; restart collector if needed:

```bash
kubectl -n agentgateway-system rollout restart deploy/langfuse-otel-collector
```

5. Ensure proxy exports OTEL (re-apply if controller recreates the Deployment):

```bash
kubectl -n agentgateway-system set env deploy/agentgateway-proxy \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-otel-collector.agentgateway-system.svc.cluster.local:4317 \
  OTEL_EXPORTER_OTLP_PROTOCOL=grpc \
  OTEL_SERVICE_NAME=agentgateway-proxy
```

6. Send a chat completion through the gateway; open Langfuse **Traces**.

## Argo CD applications

| Application | Role | Namespace |
|-------------|------|-----------|
| `platform-gateway-api` | Gateway API CRDs | cluster |
| `platform-agentgateway-crds` | agentgateway CRDs (OCI Helm 1.4.1) | `agentgateway-system` |
| `platform-agentgateway` | control plane (OCI Helm 1.4.1) | `agentgateway-system` |
| `platform-agentgateway-ai` | Gateway, OpenAI + Spark backends, routes, OTEL | `agentgateway-system` |
| `platform-langfuse-secrets` | NS + ExternalSecret | `langfuse` |
| `platform-langfuse` | Langfuse Helm 1.5.41 | `langfuse` |

## Ops notes

- Unseal Vault after every restart: `~/.config/k8s-viper/vault-unseal.sh`
- Single-node lab: ClickHouse **1 replica**, small resources — not production HA
- Image pulls (Bitnami legacy / Langfuse) need working egress DNS from the cluster
- Never commit API keys or Langfuse secrets
- Day-2: edit git → `./scripts/validate.sh` → merge → Argo sync
