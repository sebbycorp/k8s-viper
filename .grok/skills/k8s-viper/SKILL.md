---
name: k8s-viper
description: >
  Work in the k8s-viper repo: single-node k3s GitOps platform (Argo CD app-of-apps,
  Vault + ESO, Traefik node-IP ingress, Headlamp, agentgateway OpenAI proxy, Langfuse).
  Use when adding platform components or apps, changing Helm values/manifests,
  bootstrap/validate scripts, secrets wiring, ingress hosts, AI gateway, or day-2
  cluster ops. Triggers: k8s-viper, GitOps, Argo CD app, platform/, apps/, Vault,
  ExternalSecret, Headlamp, agentgateway, Langfuse, k3s bootstrap, "add a platform app",
  "deploy to viper". Slash: /k8s-viper.
---

# k8s-viper

Source of truth for a **single-node k3s** box. Imperative bootstrap once; **GitOps thereafter**.

Canonical overview: `README.md`. Design: `docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md`.

## Hard rules

1. **Never commit secrets** — no Vault tokens, unseal keys, kubeconfigs with credentials, or raw passwords. Values live in Vault; git holds `ExternalSecret` / paths only.
2. **Do not `kubectl apply` platform desired state** as the primary path. Change git → PR → `scripts/validate.sh` → merge → Argo syncs.
3. **Bootstrap only** installs k3s + Argo CD + root Application (`scripts/bootstrap.sh`). Everything else is Application CRs under `argocd/apps/`.
4. **v1 non-goals:** multi-node HA, MetalLB, ngrok/public tunnel, push-based CD from CI, cloud KMS auto-unseal.
5. **Pin versions** in Application `targetRevision` / image tags; record pins in `README.md` when changing them.

## Layout

| Path | Role |
|------|------|
| `scripts/bootstrap.sh` | One-time / idempotent install of k3s, Argo CD, root app |
| `scripts/validate.sh` | Local/CI checks (no cluster credentials) |
| `bootstrap/argocd/` | Root Application seed (bootstrap applies this) |
| `argocd/project.yaml` | AppProject `viper` (source repos + destination namespaces) |
| `argocd/apps/` | Child Applications (app-of-apps tree) |
| `platform/<name>/` | Cluster services (Helm values and/or kustomize) |
| `apps/<name>/` | User workloads |
| `docs/` | Operator runbooks (Vault, Headlamp, AI gateway, …) |
| `site/` | Hugo environment handbook (GitHub Pages) |
| `.github/workflows/ci.yaml` | PR validation only — no live cluster mutate |

## Platform inventory

| Application | Source | Namespace |
|-------------|--------|-----------|
| `argocd-project` | git `argocd/project.yaml` | `argocd` |
| `platform-ingress` | git `platform/ingress` | `kube-system` (+ `apps` for whoami) |
| `platform-vault` | Helm HashiCorp + values ref | `vault` |
| `platform-external-secrets` | Helm ESO + values ref | `external-secrets` |
| `platform-headlamp` | Helm Headlamp + values ref | `headlamp` |
| `platform-argocd-access` | kustomize NodePort for Argo UI | `argocd` |
| `platform-gateway-api` | Gateway API CRDs | cluster |
| `platform-agentgateway-crds` | agentgateway CRDs Helm | `agentgateway-system` |
| `platform-agentgateway` | agentgateway control plane | `agentgateway-system` |
| `platform-agentgateway-ai` | OpenAI Gateway/routes + OTEL | `agentgateway-system` |
| `platform-langfuse-secrets` | Langfuse ExternalSecret | `langfuse` |
| `platform-langfuse` | Langfuse + ClickHouse Helm | `langfuse` |

Ingress front door: **node IP** `:80`/`:443` via k3s Traefik. Demo hosts: `whoami.viper.local`, `headlamp.viper.local`, `langfuse.viper.local`.

Lab UI NodePorts (fixed): Headlamp **30080**, Argo CD **30443**, Vault UI **30200**, agentgateway **30100**, Langfuse **30300** — see `docs/platform-ui-access.md` and `docs/agentgateway-langfuse.md`.

## Add a platform component

1. Create `platform/<name>/` (Helm `values.yaml` and/or kustomize manifests).
2. Create `argocd/apps/platform-<name>.yaml`:
   - `project: viper`
   - automated sync + prune + selfHeal
   - `CreateNamespace=true`, prefer `ServerSideApply=true`
   - Helm multi-source pattern (match Vault/ESO/Headlamp): chart source + git `ref: values` for `$values/platform/<name>/values.yaml`
   - Plain manifests: single `source.path` like `platform-ingress`
3. Update `argocd/project.yaml`:
   - `sourceRepos` for any new Helm repo URL
   - `destinations` for the target namespace
4. Extend `scripts/validate.sh` `require_file` (and kubeconform list if plain YAML).
5. Document access/ops under `docs/` and a short pointer in `README.md`.
6. Run `./scripts/validate.sh` before finishing.

## Add a workload app

1. Put manifests (or Helm values) under `apps/<name>/`.
2. Add `argocd/apps/<name>.yaml` → `project: viper`, destination namespace (usually `apps` or a dedicated NS).
3. If new namespace: allow it in `argocd/project.yaml` destinations; create NS via sync option or a namespace manifest.
4. Ingress: `ingressClassName: traefik`, host `*.viper.local` (document `/etc/hosts` mapping to node IP).
5. Secrets: `ExternalSecret` referencing Vault — never inline Secret data. Follow `docs/vault-eso-setup.md`.

## Secrets path

- Operator runbook: `docs/vault-eso-setup.md` (init, unseal, ESO store, **secret inventory**).
- Example store: `platform/external-secrets/cluster-secret-store-vault.example.yaml` — copy/adapt; do not commit real credentials.
- Inventory: `secret/platform/openai`, `secret/platform/langfuse`, `secret/platform/langfuse-otel`.
- Apps reference secret **paths/keys** only via `ExternalSecret`.

## Dashboard + platform UIs + AI

- Access map (all ports): `docs/platform-ui-access.md`.
- Headlamp: `platform-headlamp` → **:30080** — token login `docs/headlamp.md`.
- Argo UI: `platform-argocd-access` → **:30443**.
- Vault UI: **:30200** — unseal after restarts.
- agentgateway OpenAI: **:30100** — models `gpt-5.5` / `gpt-5-mini` — `docs/agentgateway-langfuse.md`.
- Langfuse: **:30300** — ClickHouse included in chart — same AI runbook.
- Do **not** set Headlamp `config.unsafeUseServiceAccountToken: true` unless behind a real auth proxy.
- Chart pins live in Application `targetRevision`; record in `README.md`.

## Day-2 change loop

```text
edit manifests/values → ./scripts/validate.sh → PR → merge main → Argo auto-sync
```

Cluster checks (when kubeconfig available):

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl -n argocd get applications
```

## Bootstrap / validate

- Bootstrap: `sudo ./scripts/bootstrap.sh` (optional `REPO_URL`, `REPO_REVISION`, `INSTALL_K3S_SKIP=1`).
- Validate always before claiming done: `./scripts/validate.sh`.

## When editing this skill

Keep rules here; put long procedures in `docs/` and link them. Update the platform inventory table when adding/removing Argo apps.
