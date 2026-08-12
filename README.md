# k8s-viper

Single-node **k3s** powerhouse managed with **Argo CD** GitOps from this repository.

| Concern | Choice |
|--------|--------|
| Cluster | k3s, one node |
| Bootstrap | `scripts/bootstrap.sh` (once) |
| CD | Argo CD app-of-apps |
| Secrets | HashiCorp Vault OSS + External Secrets Operator |
| Dashboard | Headlamp (OSS, in-cluster) |
| Ingress | Node IP via Traefik (k3s default) — [why not kgateway](docs/why-traefik.md) |
| Lab UIs | NodePorts: Headlamp `:30080`, Argo `:30443`, Vault `:30200`, agentgateway `:30100`, Langfuse `:30300` |
| AI gateway | agentgateway `1.4.1` + OpenAI (`gpt-5.5` / `gpt-5-mini`) via Vault |
| LLM observability | Langfuse + ClickHouse; OTEL from agentgateway ([docs](docs/agentgateway-langfuse.md)) |
| Public tunnel | Not in v1 (ngrok deferred) |

Design: [`docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md`](docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md)

**Environment handbook (GitHub Pages):** [sebbycorp.github.io/k8s-viper](https://sebbycorp.github.io/k8s-viper/) — Hugo TOC + full lab docs. Source: [`site/`](site/) (`cd site && hugo server`).

## Architecture

```text
bootstrap.sh  →  k3s + Argo CD + root Application
                      ↓
              argocd/apps/* (GitOps)
                      ↓
   platform/ingress | vault | external-secrets | headlamp | argocd-access
   platform/gateway-api | agentgateway* | langfuse
                      ↓
   Traefik :80/:443  +  NodePorts 30080 / 30443 / 30200 / 30100 / 30300
                      ↓
   agentgateway → OpenAI (Vault key) → optional traces → Langfuse
```

## Repo layout

```text
scripts/bootstrap.sh          # only imperative install path
bootstrap/argocd/             # root Application seed
argocd/project.yaml           # AppProject viper
argocd/apps/                  # child Applications
platform/ingress/             # Traefik HelmChartConfig + whoami demo
platform/vault/values.yaml    # Vault Helm values (Raft, 1 replica)
platform/external-secrets/    # ESO Helm values + Vault store example
platform/headlamp/values.yaml # Headlamp dashboard Helm values
platform/argocd-access/       # Argo CD UI NodePort Service
platform/gateway-api/         # Gateway API CRDs
platform/agentgateway/        # agentgateway control plane values
platform/agentgateway-ai/     # OpenAI Gateway/routes + OTEL collector
platform/langfuse/            # Langfuse Helm + ExternalSecret
apps/                         # your workloads later
docs/                         # operator runbooks (see below)
site/                         # Hugo handbook → GitHub Pages
```

### Docs index

| Doc | Topic |
|-----|--------|
| [docs/platform-ui-access.md](docs/platform-ui-access.md) | All NodePorts, Ingress hosts, LAN access |
| [docs/headlamp.md](docs/headlamp.md) | Headlamp token login |
| [docs/vault-eso-setup.md](docs/vault-eso-setup.md) | Vault init/unseal, ESO, secret paths |
| [docs/agentgateway-langfuse.md](docs/agentgateway-langfuse.md) | OpenAI via agentgateway, Langfuse, OTEL |
| [docs/why-traefik.md](docs/why-traefik.md) | Traefik vs kgateway (cluster Ingress) |

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

If k3s is already installed:

```bash
sudo INSTALL_K3S_SKIP=1 ./scripts/bootstrap.sh
```

### After bootstrap

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
# Dockerized k3s often uses: export KUBECONFIG=$HOME/.kube/config
kubectl -n argocd get applications
```

**Platform UIs (NodePort)** — full table: [docs/platform-ui-access.md](docs/platform-ui-access.md)

| UI | URL |
|----|-----|
| Headlamp | `http://<node-ip>:30080/` |
| Argo CD | `https://<node-ip>:30443/` (admin; self-signed cert) |
| Vault | `http://<node-ip>:30200/` (after init+unseal) |
| agentgateway | `http://<node-ip>:30100/` (OpenAI proxy) |
| Langfuse | `http://<node-ip>:30300/` |

```bash
# Argo CD admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

# Headlamp SA token
kubectl -n headlamp create token headlamp --duration=12h
```

**Demo ingress** — LAN IP in `/etc/hosts`:

```bash
<node-ip>  whoami.viper.local headlamp.viper.local langfuse.viper.local

curl -H 'Host: whoami.viper.local' http://<node-ip>/
```

**Vault** — init, unseal, ESO, secret inventory: [docs/vault-eso-setup.md](docs/vault-eso-setup.md)

**AI** — OpenAI through agentgateway + Langfuse: [docs/agentgateway-langfuse.md](docs/agentgateway-langfuse.md)

```bash
export GW=http://<node-ip>:30100
curl -sS "$GW/v1/chat/completions" -H 'content-type: application/json' \
  -d '{"model":"gpt-5.5","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":64}'
```

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

## Versions (pinned)

| Component | Pin |
|-----------|-----|
| Argo CD | `v3.5.0` (bootstrap) |
| Vault Helm chart | `0.30.0` |
| External Secrets chart | `0.14.4` |
| Headlamp Helm chart | `0.44.0` |
| agentgateway / CRDs | `1.4.1` |
| Langfuse Helm chart | `1.5.41` |
| Gateway API CRDs | `v1.6.0` |
| whoami image | `traefik/whoami:v1.10.2` |

## Out of scope (v1)

- ngrok / public tunnels
- Multi-node / HA control plane
- MetalLB
- Push-based deploy from CI
- Replacing Traefik with kgateway as **cluster Ingress** (agentgateway is the AI data plane only — [docs/why-traefik.md](docs/why-traefik.md))

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Applications stuck `Unknown` | Repo URL / OCI chart reachable; `argocd-repo-server` logs |
| Project errors | `kubectl -n argocd get appproject viper` (sourceRepos + destinations) |
| whoami 404 | Host header / `/etc/hosts`; `kubectl -n apps get ingress,pods` |
| Headlamp 404 / no UI | `http://<node-ip>:30080/`; Docker published ports |
| Headlamp token rejected | Fresh SA token — [docs/headlamp.md](docs/headlamp.md) |
| Argo UI unreachable | `svc argocd-server-nodeport`; app `platform-argocd-access` |
| Vault UI unreachable / sealed | Unseal; [docs/vault-eso-setup.md](docs/vault-eso-setup.md) |
| ClusterSecretStore not Ready | Vault unsealed + k8s auth role `external-secrets` |
| agentgateway OpenAI 401/404 | Vault openai key; model id (`gpt-5.5` / `gpt-5-mini`) |
| Langfuse ImagePullBackOff | Cluster egress/DNS to Docker Hub |
| Re-run bootstrap | Safe: skips k3s if healthy; re-applies Argo + root app |
