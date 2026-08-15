# k8s-viper

Sebastian Maniak's lab. Single-node **dockerized k3s** on **Viper**, managed with **Argo CD** GitOps from this repository.

| Concern | Choice |
|--------|--------|
| Host | Viper · LAN `172.16.10.135` · user `smaniak` |
| Cluster | dockerized k3s — container `k3s-viper`, image `rancher/k3s:v1.32.5-k3s1` |
| Node | `k3s-viper` (Ready, control-plane + master) |
| kubectl | `docker exec k3s-viper kubectl ...` (not on the host PATH) |
| Bootstrap | `scripts/bootstrap.sh` (once) |
| CD | Argo CD app-of-apps |
| Secrets | HashiCorp Vault OSS + External Secrets Operator |
| Dashboard | Headlamp (OSS, in-cluster) |
| Ingress | Node IP via Traefik (k3s default) — [why not kgateway](docs/why-traefik.md) |
| Lab UIs | NodePorts on `172.16.10.135`: Headlamp `:30080`, Argo `:30443`, Vault `:30200`, agentgateway `:30100`, Langfuse `:30300`, kagent `:30500` |
| AI gateway | **One** Gateway (`agentgateway-proxy` :30100) → OpenAI (`/v1`) + DGX Spark (`/spark`) + desktop (`/desktop/`) |
| Agents | OSS **kagent 0.10.0-rc2** + **Agent Substrate 0.0.12** (`kagent` + `ate-system`); default model via the same gateway |
| LLM observability | Langfuse + ClickHouse; OTEL path configured (keys in Vault `secret/platform/langfuse-otel`) |
| SSH | LAN: `smaniak@172.16.10.135`. Remote: ngrok TCP `ssh smaniak@2.tcp.ngrok.io -p <port>` (port changes when ngrok restarts). ngrok is SSH to the box, not k8s UIs. |

Design: [`docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md`](docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md)

**Environment handbook (GitHub Pages):** [sebbycorp.github.io/k8s-viper](https://sebbycorp.github.io/k8s-viper/) — Hugo TOC + full lab docs. Source: [`site/`](site/) (`cd site && hugo server`).

## Architecture

```text
bootstrap.sh  →  dockerized k3s (k3s-viper) + Argo CD + root Application
                      ↓
              argocd/apps/* (GitOps)
                      ↓
   platform/ingress | vault | external-secrets | headlamp | argocd-access
   platform/gateway-api | agentgateway* | langfuse
   platform/substrate* | kagent* | kagent-ai
                      ↓
   Traefik :80/:443  +  NodePorts 30080 / 30443 / 30200 / 30100 / 30300 / 30500
                      ↓
   agentgateway-proxy :30100
        ├─ /v1 · /openai  → OpenAI (Vault key)      gpt-5.5 / gpt-5-mini
        ├─ /spark         → DGX Spark vLLM :8000    Qwen/Qwen3.6-35B-A3B-FP8
        ├─ /desktop/      → noVNC desktop viewer
        └─ /desktop-api/  → computer-use HTTP API
                      ↓
   kagent UI :30500  → default model gpt-5.5 via gateway /v1 (dummy key in git)
   Agent Substrate (ate-system) → gVisor workers (kagent-default)
                      ↓
   OTEL collector → Langfuse (configured; keys in Vault)
```

**One AI gateway, two providers.** There is a single Gateway (`agentgateway-proxy` in `agentgateway-system`) on NodePort **30100**. Not two gateways. Two `AgentgatewayBackend` + `HTTPRoute` objects attach to that Gateway.

| Path | Backend | Model | Auth |
|------|---------|-------|------|
| `/v1`, `/openai` | OpenAI (`api.openai.com`) | `gpt-5.5`, `gpt-5-mini` | Vault `secret/platform/openai` → ExternalSecret `openai-secret` |
| `/spark` | DGX Spark `172.16.10.173:8000` (vLLM) | `Qwen/Qwen3.6-35B-A3B-FP8` | none (config inspired by [sebbycorp/k8s-goose](https://github.com/sebbycorp/k8s-goose)) |

Desktop viewer (noVNC) and computer-use API share the same Gateway: `/desktop/` and `/desktop-api/` — [docs/desktop-computer-use.md](docs/desktop-computer-use.md).

`GET /` on `:30100` returns **404 `route not found`** — that is expected.

Known cosmetic: `svclb-agentgateway-proxy` stays **Pending** because Traefik already owns host `:80`/`:443`. AI data plane is NodePort **30100**. Do not try to steal port 80.

## Repo layout

```text
scripts/bootstrap.sh          # only imperative install path
bootstrap/argocd/             # root Application seed
argocd/project.yaml           # AppProject viper
argocd/apps/                  # child Applications
platform/ingress/             # Traefik HelmChartConfig + whoami demo
platform/vault/values.yaml    # Vault Helm values (Raft, 1 replica)
platform/external-secrets/    # ESO Helm values + Vault store example
platform/headlamp/            # Headlamp (kustomize helmCharts + hostUsers patch)
platform/argocd-access/       # Argo CD UI NodePort + argocd-cm --enable-helm
platform/gateway-api/         # Gateway API CRDs
platform/agentgateway/        # agentgateway control plane values
platform/agentgateway-ai/     # one Gateway, OpenAI + Spark + desktop routes, OTEL collector
platform/desktop/             # computer-use desktop Deployment (noVNC + API)
platform/langfuse/            # Langfuse Helm + ExternalSecret
platform/substrate/           # Agent Substrate Helm values (0.0.12) + extra ate-api-server RBAC
platform/kagent/              # kagent OSS Helm values (0.10.0-rc2)
platform/kagent-ai/           # dummy OpenAI Secret + hello SandboxAgent + UI NodePort
images/desktop-computer-use/  # viper-desktop:dev image
apps/                         # your workloads later
docs/                         # operator runbooks (see below)
site/                         # Hugo handbook → GitHub Pages
```

### Docs index

| Doc | Topic |
|-----|--------|
| [docs/platform-ui-access.md](docs/platform-ui-access.md) | All NodePorts, Ingress hosts, LAN access |
| [docs/headlamp.md](docs/headlamp.md) | Headlamp token login + hostUsers GitOps note |
| [docs/vault-eso-setup.md](docs/vault-eso-setup.md) | Vault init/unseal, ESO, secret paths |
| [docs/agentgateway-langfuse.md](docs/agentgateway-langfuse.md) | One gateway / two backends, Langfuse, OTEL |
| [docs/kagent-substrate.md](docs/kagent-substrate.md) | OSS kagent + Agent Substrate (UI :30500, hello agent) |
| [docs/desktop-computer-use.md](docs/desktop-computer-use.md) | Computer-use desktop (noVNC + API) behind agentgateway |
| [docs/why-traefik.md](docs/why-traefik.md) | Traefik vs kgateway (cluster Ingress) |

## Talk to the cluster

kubectl is **not** on the Viper host PATH. Use the container:

```bash
docker exec k3s-viper kubectl get nodes -o wide
docker exec k3s-viper kubectl -n argocd get applications
```

SSH:

```bash
# LAN
ssh smaniak@172.16.10.135

# Remote (ngrok TCP — port changes when ngrok restarts)
ssh smaniak@2.tcp.ngrok.io -p <port>
```

## Prerequisites

- Linux node (x86_64 or aarch64) you can run as root
- Outbound HTTPS (k3s, Argo install manifests, Helm charts, OpenAI, image registries)
- This repo cloned on the node (or bootstrap from a checkout)

## Quick start

```bash
git clone https://github.com/sebbycorp/k8s-viper.git
cd k8s-viper
sudo ./scripts/bootstrap.sh
```

Optional overrides:

```bash
sudo REPO_URL=https://github.com/YOU/k8s-viper.git \
     REPO_REVISION=main \
     ARGOCD_VERSION=v3.5.0 \
     ./scripts/bootstrap.sh
```

If k3s is already installed (this lab: dockerized `k3s-viper`):

```bash
sudo INSTALL_K3S_SKIP=1 ./scripts/bootstrap.sh
```

### After bootstrap

On Viper, talk to the cluster through the container:

```bash
docker exec k3s-viper kubectl -n argocd get applications
```

Native k3s installs can still use `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`.

**Platform UIs (NodePort)** — full table: [docs/platform-ui-access.md](docs/platform-ui-access.md)

| UI | URL |
|----|-----|
| Headlamp | http://172.16.10.135:30080/ |
| Argo CD | https://172.16.10.135:30443/ |
| Vault | http://172.16.10.135:30200/ |
| agentgateway | http://172.16.10.135:30100/ |
| Desktop viewer | http://172.16.10.135:30100/desktop/ |
| Langfuse | http://172.16.10.135:30300/ |
| kagent UI | http://172.16.10.135:30500/ |

```bash
# Argo CD admin password
docker exec k3s-viper kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

# Headlamp SA token
docker exec k3s-viper kubectl -n headlamp create token headlamp --duration=12h
```

**Demo ingress** — LAN IP in `/etc/hosts`:

```bash
172.16.10.135  whoami.viper.local headlamp.viper.local langfuse.viper.local

curl -H 'Host: whoami.viper.local' http://172.16.10.135/
```

**Vault** — init, unseal, ESO, secret inventory: [docs/vault-eso-setup.md](docs/vault-eso-setup.md)

**AI** — one gateway, two providers: [docs/agentgateway-langfuse.md](docs/agentgateway-langfuse.md).  
**Agents** — OSS kagent + Agent Substrate: [docs/kagent-substrate.md](docs/kagent-substrate.md).

```bash
export GW=http://172.16.10.135:30100

# OpenAI
curl -sS "$GW/v1/chat/completions" -H 'content-type: application/json' \
  -d '{"model":"gpt-5.5","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":64}'

# DGX Spark (vLLM)
curl -sS "$GW/spark/v1/chat/completions" -H 'content-type: application/json' \
  -d '{"model":"Qwen/Qwen3.6-35B-A3B-FP8","messages":[{"role":"user","content":"hi"}],"max_tokens":64}'
```

## Headlamp GitOps

`platform-headlamp` is a **git path** `platform/headlamp` using kustomize `helmCharts` (chart **0.44.0**) plus a JSON6902 patch that **removes** `spec.template.spec.hostUsers`.

Reason: the chart emits `hostUsers: true`; k3s 1.32 drops the API default, so Argo stayed OutOfSync. Do **not** set `hostUsers: false`.

`argocd-cm` has `kustomize.buildOptions: --enable-helm` via `platform/argocd-access`. After changing that key, restart `argocd-repo-server`.

## Secrets

Do **not** put secret values in git or this README.

| Where | What |
|-------|------|
| Vault | Paths in [docs/vault-eso-setup.md](docs/vault-eso-setup.md) — `secret/platform/openai`, `secret/platform/langfuse`, `secret/platform/langfuse-otel` |
| kagent dummy | `platform/kagent-ai/dummy-openai-secret.yaml` — `sk-routed-via-agentgateway` only. Real OpenAI key stays on the gateway. |
| Notion | Projects / k8s-viper / Secrets (SSH, Vault unseal/root, Langfuse, OpenAI, OTEL) |

Apps consume secrets via `ExternalSecret` only.

## Observability

Langfuse + OTEL collector (`langfuse-otel-collector` in `agentgateway-system`) exports OTLP HTTP to Langfuse. Proxy env points at the collector `:4317`. Path is wired; keys live in Vault `secret/platform/langfuse-otel`. Configured — do not treat traces as proven in production.

Runbook: [docs/agentgateway-langfuse.md](docs/agentgateway-langfuse.md).

## What is running (as of 2026-08-15)

Platform apps **Synced / Healthy** as of 2026-08-14:

`root`, `argocd-project`, `platform-argocd-access`, `platform-headlamp`, `platform-ingress`, `platform-vault`, `platform-external-secrets`, `platform-gateway-api`, `platform-agentgateway`, `platform-agentgateway-crds`, `platform-agentgateway-ai`, `platform-langfuse`, `platform-langfuse-secrets`.

GitOps also defines: `platform-substrate-crds`, `platform-substrate`, `platform-substrate-rbac`, `platform-kagent-crds`, `platform-kagent`, `platform-kagent-ai`.

`platform-desktop` is the computer-use desktop app (wave 2). The pod stays
`ImagePullBackOff` until `viper-desktop:dev` is imported on the node —
[docs/desktop-computer-use.md](docs/desktop-computer-use.md).

Known cosmetic: `svclb-agentgateway-proxy` **Pending** because Traefik already owns host `:80`/`:443`. AI data plane is NodePort **30100**. Do not try to steal port 80.

## Day-2 GitOps

1. Change manifests or Helm values on a branch.
2. Open a PR — CI runs `scripts/validate.sh` (no cluster credentials).
3. Merge to `main`.
4. Argo CD auto-syncs (prune + self-heal on platform apps).

Do **not** put secret values in git. Store them in Vault; reference via `ExternalSecret`.

## Local validation

```bash
./scripts/validate.sh
```

## Versions (pinned / lab observed)

| Component | Pin |
|-----------|-----|
| k3s | `v1.32.5+k3s1` (dockerized `rancher/k3s:v1.32.5-k3s1`) |
| Argo CD | `v3.5.0` (bootstrap) |
| Vault Helm chart | `0.30.0` |
| Vault image | `hashicorp/vault:1.19.0` |
| External Secrets chart | `0.14.4` |
| Headlamp Helm chart | `0.44.0` |
| Headlamp image | `ghcr.io/headlamp-k8s/headlamp:v0.44.0` |
| agentgateway / CRDs | `v1.4.1` (OCI `oci://cr.agentgateway.dev/charts`) |
| agentgateway images | `v1.4.1` |
| Langfuse Helm chart | `1.5.41` |
| OTEL collector | `otel/opentelemetry-collector-contrib:0.132.1` |
| Gateway API CRDs | `v1.6.0` |
| whoami image | `traefik/whoami:v1.10.2` |
| kagent OSS Helm / CRDs | `0.10.0-rc2` (OCI `oci://ghcr.io/kagent-dev/kagent/helm/kagent`) |
| Agent Substrate Helm / CRDs | `0.0.12` (OCI `oci://ghcr.io/kagent-dev/substrate/helm/substrate`) |
| Substrate worker image | `ghcr.io/kagent-dev/substrate/ateom-gvisor:v0.0.12` |
| desktop image | `viper-desktop:dev` (intended publish `ghcr.io/sebbycorp/viper-desktop:dev`) |

## Out of scope (v1)

- ngrok for **k8s UIs** (ngrok TCP is used for SSH to the box only)
- Multi-node / HA control plane
- MetalLB
- Push-based deploy from CI
- Replacing Traefik with kgateway as **cluster Ingress** (agentgateway is the AI data plane only — [docs/why-traefik.md](docs/why-traefik.md))
- Substrate Actor wrap for the computer-use desktop (follow-up; first path is a Deployment — [docs/desktop-computer-use.md](docs/desktop-computer-use.md)). kagent install is OSS + gVisor `ateom-gvisor` only.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `kubectl: command not found` on the host | `docker exec k3s-viper kubectl ...` |
| Applications stuck `Unknown` | Repo URL / OCI chart reachable; `argocd-repo-server` logs |
| kagent/substrate OCI **403** | Argo 3.5 needs the **full** GHCR chart URL (`…/helm/kagent`, not `…/helm`) — [docs/kagent-substrate.md](docs/kagent-substrate.md) |
| Project errors | `docker exec k3s-viper kubectl -n argocd get appproject viper` (sourceRepos + destinations) |
| whoami 404 | Host header / `/etc/hosts`; `docker exec k3s-viper kubectl -n apps get ingress,pods` |
| Headlamp 404 / no UI | `http://172.16.10.135:30080/`; Docker published ports |
| Headlamp token rejected | Fresh SA token — [docs/headlamp.md](docs/headlamp.md) |
| `platform-headlamp` OutOfSync / `hostUsers` | JSON6902 removes `hostUsers`; do not set `false`. Restart `argocd-repo-server` after `--enable-helm` |
| Argo UI unreachable | `svc argocd-server-nodeport`; app `platform-argocd-access` |
| Vault UI unreachable / sealed | Unseal; [docs/vault-eso-setup.md](docs/vault-eso-setup.md) |
| ClusterSecretStore not Ready | Vault unsealed + k8s auth role `external-secrets` |
| agentgateway `GET /` → 404 | Expected — use `/v1`, `/spark`, `/desktop/`, or `/desktop-api/health` |
| desktop ImagePullBackOff | Import `viper-desktop:dev` on the node — [docs/desktop-computer-use.md](docs/desktop-computer-use.md) |
| agentgateway OpenAI 401/404 | Vault openai key; model id (`gpt-5.5` / `gpt-5-mini`) |
| Spark 502 / no route | Backend `172.16.10.173:8000`; model `Qwen/Qwen3.6-35B-A3B-FP8` |
| `svclb-agentgateway-proxy` Pending | Cosmetic — Traefik owns `:80`/`:443`. Use NodePort **30100** |
| Langfuse ImagePullBackOff | Cluster egress/DNS to Docker Hub |
| kagent UI unreachable | `http://172.16.10.135:30500/`; Docker must publish **30500**; app `platform-kagent-ai` |
| hello-substrate not Ready | WorkerPool `kagent-default`; gVisor-on-dockerized-k3s — [docs/kagent-substrate.md](docs/kagent-substrate.md) |
| ate-api-server CrashLoop / not Ready | Missing cluster list on `storageclasses` / `csidriverconfigs` — app `platform-substrate-rbac` |
| Re-run bootstrap | Safe: skips k3s if healthy; re-applies Argo + root app |
