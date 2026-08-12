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
| Lab UIs | NodePort: Headlamp `:30080`, Argo CD `:30443`, Vault `:30200` |
| AI gateway | agentgateway `1.4.1` + OpenAI (`gpt-5.5` / `gpt-5-mini`) |
| LLM observability | Langfuse + ClickHouse; traces via OTEL ([docs](docs/agentgateway-langfuse.md)) |
| Public tunnel | Not in v1 (ngrok deferred) |

Design: [`docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md`](docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md)

**Environment handbook (GitHub Pages):** [sebbycorp.github.io/k8s-viper](https://sebbycorp.github.io/k8s-viper/) — Hugo-built TOC + full lab docs (architecture, UIs, apps, secrets, versions, day-2, troubleshooting). Source: [`site/`](site/) (`cd site && hugo server`).

## Architecture

```text
bootstrap.sh  →  k3s + Argo CD + root Application
                      ↓
              argocd/apps/* (GitOps)
                      ↓
   platform/ingress | vault | external-secrets | headlamp | argocd-access
                      ↓
   <node-ip>:80/:443 (Traefik) + NodePorts 30080 / 30443 / 30200
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
apps/                         # your workloads later
docs/vault-eso-setup.md       # init / unseal / ESO wiring
docs/headlamp.md              # dashboard access + token auth
docs/platform-ui-access.md    # NodePort map for Argo / Headlamp / Vault
docs/why-traefik.md           # Traefik vs kgateway decision
docs/agentgateway-langfuse.md # AI gateway + Langfuse + Vault keys
platform/agentgateway/        # agentgateway Helm values
platform/agentgateway-ai/     # OpenAI routes + OTEL collector
platform/langfuse/            # Langfuse Helm + ExternalSecret
site/                         # Hugo handbook → GitHub Pages
```

## Prerequisites

- Linux node (x86_64 or aarch64) you can run as root
- Outbound HTTPS (k3s, Argo install manifests, Helm charts)
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
kubectl -n argocd get applications
```

**Platform UIs (NodePort)** — [docs/platform-ui-access.md](docs/platform-ui-access.md):

| UI | URL |
|----|-----|
| Headlamp | `http://<node-ip>:30080/` |
| Argo CD | `https://<node-ip>:30443/` (admin; self-signed cert) |
| Vault | `http://<node-ip>:30200/` (after init+unseal) |

```bash
# Argo CD admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

# Headlamp SA token
kubectl -n headlamp create token headlamp --duration=12h
```

**Demo ingress** — get node IP, then:

```bash
# /etc/hosts on your laptop
<node-ip>  whoami.viper.local headlamp.viper.local

curl -H 'Host: whoami.viper.local' http://<node-ip>/
```

**Vault** — initialize and connect ESO: [docs/vault-eso-setup.md](docs/vault-eso-setup.md)

## Day-2 GitOps

1. Change manifests or Helm values in a branch.
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
| whoami image | `traefik/whoami:v1.10.2` |

## Out of scope (v1)

- ngrok / public tunnels
- Multi-node / HA control plane
- MetalLB
- Push-based deploy from CI
- kgateway / Gateway API as primary edge (Traefik is intentional — [docs/why-traefik.md](docs/why-traefik.md))

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Applications stuck `Unknown` | Repo URL reachable from cluster; `kubectl -n argocd logs -l app.kubernetes.io/name=argocd-repo-server` |
| Project errors | `kubectl -n argocd get appproject viper` |
| whoami 404 | Host header / `/etc/hosts`; `kubectl -n apps get ingress,pods` |
| Headlamp 404 / no UI | Try `http://<node-ip>:30080/`; `kubectl -n headlamp get pods,svc,ingress` |
| Headlamp token rejected | Create a fresh SA token — see [docs/headlamp.md](docs/headlamp.md) |
| Argo UI unreachable | `kubectl -n argocd get svc argocd-server-nodeport`; app `platform-argocd-access` |
| Vault UI unreachable | `kubectl -n vault get svc vault-ui`; init+unseal first |
| Vault not ready | Normal until init+unseal — see vault docs |
| Re-run bootstrap | Safe: skips k3s if healthy; re-applies Argo + root app |
