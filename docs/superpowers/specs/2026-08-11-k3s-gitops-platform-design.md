# k8s-viper: Single-Node k3s GitOps Platform Design

**Date:** 2026-08-11  
**Status:** Approved for implementation planning  
**Repo:** https://github.com/sebbycorp/k8s-viper

## Goal

Turn this repository into the source of truth for a **single-node k3s “powerhouse” box**:

- Imperative **bootstrap once** (k3s + Argo CD + root Application)
- **GitOps thereafter** via Argo CD app-of-apps
- **HashiCorp Vault OSS** for secrets
- **Node IP** as the cluster front door (no MetalLB, no cloud LB)
- **No ngrok** in v1 (deferred; can be added later as a platform app)

## Non-goals (v1)

- Multi-node / HA control plane
- MetalLB or external LoadBalancer controllers
- ngrok or other public tunnel agents
- Push-based CD from CI (`kubectl apply` as primary deploy path)
- Cloud KMS auto-unseal for Vault
- Full observability stack (Prometheus/Grafana) — optional later under `platform/`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Single node                                            │
│                                                         │
│  bootstrap.sh ──► k3s ──► Argo CD (install once)        │
│                      │                                  │
│                      ▼                                  │
│              Root Application (app-of-apps)             │
│                      │                                  │
│         ┌────────────┼────────────┐                     │
│         ▼            ▼            ▼                     │
│    platform/     platform/      apps/                   │
│    (ingress)     (vault, eso)   (workloads)             │
│                                                         │
│  Front door: <node-ip>:80 / :443 (Traefik)              │
└─────────────────────────────────────────────────────────┘
           ▲
           │  git push / PR merge
    this repo (desired state)
           ▲
           │  CI: lint / validate only
    GitHub Actions
```

### Control flow

1. Operator runs `scripts/bootstrap.sh` on the node.
2. Script installs k3s (if needed), installs Argo CD, applies the root Application.
3. Argo CD syncs child Applications from git (`argocd/apps/`).
4. Platform components and apps reconcile continuously from this repo.
5. CI validates changes on PRs; it does not mutate the live cluster.

### Ownership split

| Concern | Owner |
|--------|--------|
| k3s install, first Argo CD install, root Application seed | `scripts/bootstrap.sh` |
| Argo AppProject, Application CRs, in-cluster config | git → Argo CD |
| Vault, External Secrets Operator, ingress defaults, apps | git → Argo CD |
| Secret **values** (tokens, passwords, unseal keys) | Vault / offline operator storage — **never git** |
| Secret **references** (`ExternalSecret`, paths, keys) | git |

## Repository layout

```text
k8s-viper/
├── README.md
├── scripts/
│   └── bootstrap.sh
├── bootstrap/
│   └── argocd/
│       ├── kustomization.yaml          # or install yaml refs
│       └── root-application.yaml
├── argocd/
│   ├── project.yaml
│   └── apps/                           # app-of-apps children
│       ├── platform-ingress.yaml
│       ├── platform-vault.yaml
│       └── platform-external-secrets.yaml
├── platform/
│   ├── ingress/
│   ├── vault/
│   └── external-secrets/
├── apps/
│   └── .gitkeep                        # sample app optional in first impl slice
└── .github/
    └── workflows/
        └── ci.yaml
```

### Path conventions

- **`bootstrap/`** — artifacts consumed only by the bootstrap script (not continuously reconciled as the long-term app tree, except where the root Application must live).
- **`argocd/apps/`** — Application CRs; root app watches this directory (or a parent kustomization that lists them).
- **`platform/*`** — cluster services, one directory per concern.
- **`apps/*`** — user workloads; empty or minimal sample in v1.

## Bootstrap contract

### Inputs

| Input | Default | Notes |
|-------|---------|--------|
| `REPO_URL` | `https://github.com/sebbycorp/k8s-viper.git` | Override for forks |
| `REPO_REVISION` | `main` | Branch or tag Argo tracks |
| `K3S_VERSION` | stable channel / pinned in script | Pin in implementation for reproducibility |
| `ARGOCD_NAMESPACE` | `argocd` | Fixed unless documented otherwise |

### Behavior

1. **Preflight:** require root or passwordless kubectl-capable privileges as documented; fail fast if unsupported OS/arch assumptions break.
2. **k3s:** install single-node server if not already installed; leave Traefik enabled; use default local-path provisioner; do not disable servicelb unless we explicitly document host-port Traefik-only mode. Prefer stock k3s ingress behavior so `<node-ip>:80/:443` works.
3. **kubeconfig:** write/merge operator-friendly kubeconfig path (document `~/.kube/config` or `/etc/rancher/k3s/k3s.yaml` usage).
4. **Wait:** node `Ready`; `kube-system` critical pods ready.
5. **Argo CD:** create namespace, apply upstream stable install (version-pinned), wait for `argocd-server` ready.
6. **Root Application:** apply Application that points at this repo + `argocd/apps` (app-of-apps pattern).
7. **Output:** print Argo initial admin password retrieval command, node IP, and next steps for Vault init.

### Must not

- Commit or echo Vault unseal keys / root token into git.
- Install ngrok.
- Apply entire platform via raw kubectl except what is required to start Argo (Argo install + root app).
- Assume multi-node.

### Idempotency

Re-running bootstrap on an already-bootstrapped node should be safe:

- Skip k3s install if k3s is active (or support explicit reinstall flag later).
- Re-apply Argo/root Application manifests (server-side apply or kubectl apply).

## Argo CD design

### AppProject

- Single project (e.g. `viper`) allowing namespaces needed by platform (`argocd`, `vault`, `external-secrets`, `kube-system` only if required for ingress config, plus app namespaces as added).
- Source repo restricted to this git repository URL (configurable via bootstrap).
- Destination: in-cluster only for v1.

### Root / app-of-apps

- Root Application (applied by bootstrap) syncs `argocd/apps`.
- Each child Application maps 1:1 to a platform (or app) directory.
- Automated sync enabled for platform apps in v1 (prune optional but recommended for platform with care); self-heal enabled so drift is corrected.
- Sync waves / hooks only where ordering is required (e.g. CRDs before CRs for ESO).

### Suggested child apps (v1)

| Application | Path | Namespace |
|-------------|------|-----------|
| platform-ingress | `platform/ingress` | as needed (often kube-system or traefik) |
| platform-vault | `platform/vault` | `vault` |
| platform-external-secrets | `platform/external-secrets` | `external-secrets` |

## Ingress (node IP)

### Design

- Single node ⇒ **one IP** is the front door.
- Use **k3s default Traefik** unless implementation proves a clear need to replace it.
- Platform ingress layer may include:
  - Example Ingress / IngressRoute patterns
  - Optional Traefik HelmChartConfig / values for entrypoints, trusted IPs, dashboard (dashboard off public by default)
  - Documentation for accessing via `http://<node-ip>` and host-based rules via `/etc/hosts` or local DNS

### Explicitly out of v1

- MetalLB
- external-dns
- cert-manager + public DNS01 (optional later; LAN HTTP is enough for v1)
- ngrok

### Future ngrok hook

When added later, ngrok should tunnel to the **same node ingress ports** (`:80`/`:443`), not per-Service tunnels. No layout change required beyond a new `platform/ngrok` + Application CR.

## Secrets: Vault OSS + External Secrets Operator

### Vault

- Deploy **HashiCorp Vault OSS** via GitOps under `platform/vault`.
- **Storage:** integrated Raft (single voter) suitable for one node.
- **Replicas:** 1.
- **UI:** enabled for LAN use; not exposed without intentional Ingress.
- **Injection:** prefer **External Secrets Operator** over Vault Agent Injector for v1 so apps consume normal Kubernetes Secrets.

### Initialization (human / operator script, not git state)

1. Argo deploys Vault; pod becomes ready but **sealed** / uninitialized.
2. Operator runs documented init steps (`vault operator init`) against the live Service/pod.
3. Store unseal keys + root token **offline** (password manager, paper, etc.).
4. Unseal after restarts (manual Shamir unseal for v1).
5. Enable KV v2 engine at a conventional path (e.g. `secret/`).
6. Create a policy + auth method for ESO (Kubernetes auth recommended once bootstrap identity is available; token auth acceptable for first bring-up if documented as temporary).

### External Secrets Operator

- Deploy ESO from `platform/external-secrets`.
- Define `ClusterSecretStore` (or namespaced `SecretStore`) referencing Vault.
- Workloads use `ExternalSecret` resources in git; **no plaintext secret data in git**.

### Bootstrap secrets caveat

Argo CD’s initial admin password remains a Kubernetes Secret created by the Argo install (retrieve via `kubectl`). Do not put a static admin password in git.

## CI (validate only)

### Pipeline (GitHub Actions)

On pull request and push to `main`:

- YAML syntax / kubeconform or kustomize build for manifest paths
- Optional: `helm template` if Helm charts are vendored/referenced
- Fail on invalid manifests
- **No** credentials to the cluster required
- **No** `kubectl apply` to production

### Local dev

Document `kubectl` + `kustomize`/`helm` checks mirroring CI for offline validation.

## Failure modes and recovery

| Failure | Expected handling |
|---------|-------------------|
| Bootstrap interrupted mid-k3s install | Re-run bootstrap; k3s install is resumable/idempotent per script checks |
| Argo CD down | Cluster keeps running last-applied state; fix Argo via kubectl from node kubeconfig; re-apply root app if needed |
| Git out of sync / bad sync | Argo shows degraded; revert commit in git; auto-sync heals |
| Vault sealed after reboot | Workloads with existing K8s Secrets keep working until rotation; new ExternalSecrets fail until operator unseals Vault |
| Vault data loss on disk | Single-node risk accepted in v1; document backup of Raft data path as follow-up |
| Node disk full / k3s crash | Host-level recovery; GitOps re-applies desired state once API is back |
| Wrong REPO_URL/revision in root app | Fix Application with kubectl or re-run bootstrap with correct env |

## Security baseline (v1)

- Single-node physical/LAN trust model; not a hardened multi-tenant public cloud.
- No secret values in git.
- Limit Argo project to this repo and intended namespaces.
- Do not expose Kubernetes API publicly.
- Vault UI / Argo UI: LAN or `kubectl port-forward` only unless operator adds Ingress deliberately.
- Prefer TLS later (cert-manager); HTTP on LAN acceptable for initial bring-up.

## Testing strategy

| Layer | What |
|-------|------|
| Script | Bootstrap dry-run flags where feasible; documented manual run on a clean VM |
| Manifests | CI kubeconform/kustomize build |
| Integration | After bootstrap: Argo apps Healthy; Traefik responds on node IP; Vault pod running; ESO CRDs installed |
| Secrets path | After manual Vault init: sample ExternalSecret syncs a test value into a K8s Secret |

## Implementation phases (for planning)

1. **Repo skeleton** — directories, README overview, CI stub.
2. **Bootstrap** — k3s + Argo CD + root Application.
3. **Argo project + app-of-apps wiring**.
4. **Platform ingress** — defaults/examples for node-IP Traefik.
5. **Vault** — Helm/Kustomize package, single-node Raft.
6. **ESO** — operator + store template + docs for Vault connect.
7. **Docs** — bring-up guide, Vault init/unseal, day-2 GitOps workflow.
8. **Optional sample app** — proves Ingress + ExternalSecret path end-to-end.

## Success criteria

- Fresh machine: run one bootstrap script → Ready k3s node + Argo CD + root app syncing.
- Merging to `main` changes cluster state via Argo without CI needing cluster credentials.
- Vault runs in-cluster; secrets are not stored in git.
- An HTTP service is reachable via `<node-ip>` through Traefik/Ingress.
- ngrok is absent; design leaves a clear extension point under `platform/`.

## Deferred follow-ups

- ngrok agent as `platform/ngrok`
- cert-manager + real TLS
- kube-prometheus-stack / logging
- Vault auto-unseal / snapshots
- Multi-node expansion (explicit non-goal until redesign)
```