# k3s GitOps Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap a single-node k3s cluster from this repo with Argo CD app-of-apps, Vault OSS, External Secrets Operator, and node-IP Traefik ingress (no ngrok).

**Architecture:** `scripts/bootstrap.sh` installs k3s + Argo CD + root Application once; Argo syncs `argocd/apps/*` which deploy `platform/*` from git. CI validates manifests only.

**Tech Stack:** k3s, Argo CD (pinned install.yaml), Traefik (k3s default), Vault Helm chart via Argo, External Secrets Operator via Argo, GitHub Actions + kubeconform.

**Spec:** `docs/superpowers/specs/2026-08-11-k3s-gitops-platform-design.md`

---

## File map

| Path | Responsibility |
|------|----------------|
| `scripts/bootstrap.sh` | Install k3s, Argo CD, root Application |
| `scripts/validate.sh` | Local manifest validation (mirrors CI) |
| `bootstrap/argocd/root-application.yaml` | Root app-of-apps Application |
| `argocd/project.yaml` | AppProject `viper` |
| `argocd/apps/*.yaml` | Child Applications |
| `platform/ingress/` | Traefik HelmChartConfig + example Ingress |
| `platform/vault/` | Vault Helm Argo app sources |
| `platform/external-secrets/` | ESO + ClusterSecretStore template |
| `apps/sample/` | Optional hello Ingress demo |
| `.github/workflows/ci.yaml` | PR/main validation |
| `README.md` | Bring-up and day-2 docs |

---

### Task 1: Repo skeleton + README shell

**Files:**
- Create: `apps/.gitkeep`
- Create: `platform/ingress/.gitkeep` (replaced in later tasks)
- Modify: `README.md`

- [ ] **Step 1: Create directory placeholders and rewrite README** with overview matching the design (bootstrap, GitOps, Vault, node IP, no ngrok).

- [ ] **Step 2: Commit**

```bash
git add README.md apps/.gitkeep
git commit -m "docs: outline k3s GitOps platform README and layout"
```

---

### Task 2: Argo CD root app, project, and app-of-apps Applications

**Files:**
- Create: `bootstrap/argocd/root-application.yaml`
- Create: `argocd/project.yaml`
- Create: `argocd/apps/platform-ingress.yaml`
- Create: `argocd/apps/platform-vault.yaml`
- Create: `argocd/apps/platform-external-secrets.yaml`
- Create: `argocd/apps/argocd-project.yaml` (syncs project from git after bootstrap)

**Root Application** (applied by bootstrap only):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/sebbycorp/k8s-viper.git
    targetRevision: main
    path: argocd/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**AppProject** `viper` allows this repo and namespaces: `argocd`, `vault`, `external-secrets`, `default`, `apps`, `kube-system`.

Each child Application:
- `project: viper` (except `argocd-project` may use `default` until project exists — order with sync-wave)
- Automated sync + selfHeal
- Correct `path` and `namespace`

**Sync waves:**
- `argocd-project`: wave `-1`
- platform apps: wave `0` (ESO CRDs need server-side apply)

- [ ] **Step 1: Write all YAML files above with pinned repo URL (overridable note in bootstrap).**

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(argocd): add root app-of-apps, project, and platform Applications"
```

---

### Task 3: Platform ingress (Traefik node-IP defaults)

**Files:**
- Create: `platform/ingress/kustomization.yaml`
- Create: `platform/ingress/helmchartconfig-traefik.yaml`
- Create: `platform/ingress/namespace-apps.yaml`
- Create: `platform/ingress/example-whoami.yaml` (optional demo Deployment+Service+Ingress)

k3s Traefik is configured via `HelmChartConfig` in `kube-system`:

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    ports:
      web:
        exposedPort: 80
      websecure:
        exposedPort: 443
    # dashboard off by default; enable only if desired later
```

Example `whoami` Ingress host `whoami.viper.local` → document `/etc/hosts` → node IP.

- [ ] **Step 1: Write ingress kustomization and resources.**

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(platform): Traefik node-IP ingress defaults and whoami example"
```

---

### Task 4: Platform Vault (single-node Raft)

**Files:**
- Create: `platform/vault/kustomization.yaml`
- Create: `platform/vault/namespace.yaml`
- Create: `platform/vault/application-source` via Helm in Argo Application OR kustomize with Helm chart

**Preferred for Argo:** child Application uses Helm source:

Update `argocd/apps/platform-vault.yaml` to:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: platform-vault
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  project: viper
  sources:
    - repoURL: https://helm.releases.hashicorp.com
      chart: vault
      targetRevision: 0.30.0
      helm:
        valueFiles:
          - $values/platform/vault/values.yaml
    - repoURL: https://github.com/sebbycorp/k8s-viper.git
      targetRevision: main
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: vault
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**values.yaml** (single replica, UI on, TLS disabled for LAN v1, data PVC):

```yaml
global:
  enabled: true
  tlsDisable: true

injector:
  enabled: false

server:
  dev:
    enabled: false
  standalone:
    enabled: true
    config: |
      ui = true
      listener "tcp" {
        tls_disable = 1
        address = "[::]:8200"
        cluster_address = "[::]:8201"
      }
      storage "file" {
        path = "/vault/data"
      }
  dataStorage:
    enabled: true
    size: 10Gi
  ui:
    enabled: true
    serviceType: ClusterIP
```

Note: integrated Raft with 1 replica is also valid; **file storage** is simpler for true single-node v1 and matches "one box". Spec said Raft — use **standalone file** OR **ha.raft replicas: 1**. Prefer standalone file for simplicity unless Raft is required; design said Raft — implement **ha.enabled true, replicas 1, raft enabled** if chart allows, else standalone file with comment.

Actually Vault HA raft with 1 node:

```yaml
server:
  standalone:
    enabled: false
  ha:
    enabled: true
    replicas: 1
    raft:
      enabled: true
      setNodeId: true
      config: |
        ui = true
        listener "tcp" {
          tls_disable = 1
          address = "[::]:8200"
          cluster_address = "[::]:8201"
        }
        storage "raft" {
          path = "/vault/data"
        }
```

- [ ] **Step 1: Write `platform/vault/values.yaml` and Helm-based Application.**

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(platform): Vault OSS single-node Raft via Argo Helm"
```

---

### Task 5: External Secrets Operator + Vault store template

**Files:**
- Create: `platform/external-secrets/kustomization.yaml` OR Helm Application
- Create: `platform/external-secrets/cluster-secret-store-vault.yaml` (documented; may be inactive until Vault auth exists)
- Create: `docs/vault-eso-setup.md` (init, unseal, K8s auth, store)

ESO Application (Helm):

```yaml
# chart external-secrets from https://charts.external-secrets.io
# targetRevision pin e.g. 0.14.0 or current stable
```

Include a **disabled or example** `ClusterSecretStore` with clear comments that operator must configure Vault auth first. Prefer example file `cluster-secret-store-vault.example.yaml` not applied, plus docs steps.

- [ ] **Step 1: Write ESO Argo Application + example store + setup doc.**

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(platform): External Secrets Operator and Vault integration docs"
```

---

### Task 6: Bootstrap script

**Files:**
- Create: `scripts/bootstrap.sh` (executable)

Behavior:
1. `set -euo pipefail`
2. Env: `REPO_URL` (default github.com/sebbycorp/k8s-viper.git), `REPO_REVISION` (default main), `ARGOCD_VERSION` (default v3.5.0), `K3S_INSTALL_URL` default get.k3s.io
3. Install k3s if missing: `curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --write-kubeconfig-mode 644" sh -`
4. Export `KUBECONFIG=/etc/rancher/k3s/k3s.yaml`
5. Wait for node Ready
6. `kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -`
7. `kubectl apply -n argocd --server-side --force-conflicts -f https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml`
8. Wait for argocd-server rollout
9. Sed-replace or envsubst `REPO_URL`/`REPO_REVISION` into root Application and apply from repo path (if script runs from clone) OR curl raw from REPO_URL
10. Print admin password command, node IP, next steps

Must work when run from a git clone of this repo (`SCRIPT_DIR` relative paths to `bootstrap/argocd/root-application.yaml`).

- [ ] **Step 1: Write bootstrap.sh with helper functions wait_for_node, wait_for_deploy.**

- [ ] **Step 2: shellcheck if available; chmod +x.**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add k3s + Argo CD bootstrap script"
```

---

### Task 7: CI + local validate script

**Files:**
- Create: `.github/workflows/ci.yaml`
- Create: `scripts/validate.sh`

validate.sh:
- Check required files exist
- `python3 -c` YAML parse or use `yq` if present
- If `kubeconform` installed, run against plain manifests (skip Helm-only apps)
- Exit non-zero on failure

ci.yaml:
- checkout
- install kubeconform
- run `scripts/validate.sh`
- optionally kustomize build platform/ingress

- [ ] **Step 1: Write validate.sh and ci.yaml.**

- [ ] **Step 2: Run validate.sh locally.**

- [ ] **Step 3: Commit**

```bash
git commit -m "ci: add manifest validation workflow and script"
```

---

### Task 8: Final docs polish

**Files:**
- Modify: `README.md` — full bring-up, Vault init, day-2 workflow, troubleshooting
- Create: `docs/day-2-gitops.md` (optional if README sufficient)

- [ ] **Step 1: Complete operator documentation.**

- [ ] **Step 2: Commit**

```bash
git commit -m "docs: complete bring-up and GitOps operator guide"
```

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| bootstrap.sh k3s+Argo+root | Task 6 |
| app-of-apps | Task 2 |
| Vault OSS | Task 4 |
| ESO | Task 5 |
| Node IP Traefik | Task 3 |
| No ngrok | All (omitted) |
| CI validate only | Task 7 |
| Secrets not in git | Tasks 4–5 |
| README / docs | Tasks 1, 5, 8 |

## Execution notes

- Prefer implementing multi-source Helm Applications for Vault/ESO over vendoring charts.
- Pin chart/Argo versions in files.
- Do not commit Vault tokens or unseal keys.
- After all tasks: run `scripts/validate.sh`; do not require a live k3s cluster in CI.
```