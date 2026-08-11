# k8s-viper

Single-node **k3s** powerhouse managed with **Argo CD** GitOps from this repository.

| Concern | Choice |
|--------|--------|
| Cluster | k3s, one node |
| Bootstrap | `scripts/bootstrap.sh` (once) |
| CD | Argo CD app-of-apps |
| Secrets | HashiCorp Vault OSS + External Secrets Operator |
| Ingress | Node IP via Traefik (k3s default) |
| Public tunnel | Not in v1 (ngrok deferred) |

Design: [`docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md`](docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md)

## Architecture

```text
bootstrap.sh  →  k3s + Argo CD + root Application
                      ↓
              argocd/apps/* (GitOps)
                      ↓
         platform/ingress | vault | external-secrets
                      ↓
              <node-ip>:80 / :443
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
apps/                         # your workloads later
docs/vault-eso-setup.md       # init / unseal / ESO wiring
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

**Argo CD UI** (admin password printed by bootstrap):

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
# https://localhost:8080  user: admin
```

**Demo ingress** — get node IP, then:

```bash
# /etc/hosts on your laptop
<node-ip>  whoami.viper.local

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
| whoami image | `traefik/whoami:v1.10.2` |

## Out of scope (v1)

- ngrok / public tunnels
- Multi-node / HA control plane
- MetalLB
- Push-based deploy from CI

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Applications stuck `Unknown` | Repo URL reachable from cluster; `kubectl -n argocd logs -l app.kubernetes.io/name=argocd-repo-server` |
| Project errors | `kubectl -n argocd get appproject viper` |
| whoami 404 | Host header / `/etc/hosts`; `kubectl -n apps get ingress,pods` |
| Vault not ready | Normal until init+unseal — see vault docs |
| Re-run bootstrap | Safe: skips k3s if healthy; re-applies Argo + root app |
