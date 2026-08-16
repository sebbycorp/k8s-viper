# OSS kagent + Agent Substrate

Lab install of **open-source** kagent and Agent Substrate on dockerized k3s.
This is **not** Solo Enterprise kagent (that lives in k8s-goose).

| Piece | Pin | Namespace |
|-------|-----|-----------|
| kagent Helm + CRDs | **0.10.0-rc2** (`oci://ghcr.io/kagent-dev/kagent/helm/kagent` + `…/kagent-crds`) | `kagent` |
| Agent Substrate Helm + CRDs | **0.0.9** (`oci://ghcr.io/kagent-dev/substrate/helm/substrate` + `…/substrate-crds`) | `ate-system` |
| Worker image | `ghcr.io/kagent-dev/substrate/ateom-gvisor:v0.0.9` | WorkerPool `kagent-default` |
| UI | NodePort **30500** | `kagent-ui-nodeport` |

Official published pairing (do not drift):

- `oci://ghcr.io/kagent-dev/kagent/helm/kagent:0.10.0-rc2` → substrate subchart **0.0.9**
- `oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds:0.10.0-rc2` → substrate-crds **0.0.9**
- kagent `go/go.mod` replace: `github.com/kagent-dev/substrate v0.0.9`

kagent 0.10.0-rc2 always writes `ActorTemplate` with `spec.pauseImage` and
`env[].valueFrom.secretKeyRef` (`KAGENT_CONFIG_JSON`, `KAGENT_AGENT_CARD_JSON`,
`KAGENT_SRT_SETTINGS_JSON`, `OPENAI_API_KEY`). Substrate **0.0.9** CRDs accept
that shape. **0.0.12** removed `valueFrom` and moved pause image to
`SandboxConfig`, so the apiserver rejects rc2's object (`hello-substrate`
Ready=False / ActorTemplateNotFound). Do **not** upgrade past 0.0.12 (no
newer tag restores `valueFrom`). Do **not** use 0.0.11 (CRD fields exist but
the rc2 ateapi client is 0.0.9). Do **not** edit `hello-substrate.yaml` to
paper over a CRD mismatch.

Official docs still mention 0.9.9 / 0.0.8. This lab pins the official rc2
pair: **0.10.0-rc2** + **0.0.9**.

## How it is wired

```text
kagent UI :30500
    → controller (kagent)
        → ModelConfig default-model-config
              provider OpenAI  model gpt-5.5
              baseUrl  http://agentgateway-proxy.agentgateway-system.svc.cluster.local/v1
              apiKey   dummy sk-routed-via-agentgateway  (Secret/kagent-openai)
        → agentgateway :30100 /v1  injects Vault secret/platform/openai
        → Agent Substrate ate-api  dns:///api.ate-system.svc:443  (JWT, insecure TLS)
        → WorkerPool kagent-default  (1 replica, gVisor ateom)
              → SandboxAgent hello-substrate
```

**One gateway.** kagent does not get a second OpenAI path and does not get a
real API key in git. The dummy Secret exists so the chart/controller have a
key reference; the gateway swaps in the Vault key on the way out.

Argo waves:

| Wave | Application | Source |
|------|-------------|--------|
| 1 | `platform-substrate-crds` | OCI `oci://ghcr.io/kagent-dev/substrate/helm/substrate-crds` 0.0.9 |
| 2 | `platform-substrate` | git `platform/substrate-app` (kustomize helmCharts 0.0.9 + valkey STS JSON6902) |
| 2 | `platform-substrate-rbac` | git `platform/substrate` (extra ate-api ClusterRole/Binding hook) |
| 3 | `platform-kagent-crds` | OCI `oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds` 0.10.0-rc2 |
| 4 | `platform-kagent` | OCI `oci://ghcr.io/kagent-dev/kagent/helm/kagent` 0.10.0-rc2 + `platform/kagent/values.yaml` |
| 5 | `platform-kagent-ai` | git `platform/kagent-ai` (dummy Secret, hello agent, UI NodePort) |

### Argo CD 3.5 OCI URLs (GHCR)

Argo CD **3.5** on this cluster resolves an OCI **parent** path as the
artifact. `oci://ghcr.io/kagent-dev/kagent/helm` + `chart: kagent` therefore
pulls the parent index and **403s** — same class of bug as agentgateway
(`oci://cr.agentgateway.dev/charts/agentgateway` + `chart: agentgateway`).

Working form (keep `chart:`):

```yaml
repoURL: oci://ghcr.io/kagent-dev/kagent/helm/kagent
chart: kagent
targetRevision: 0.10.0-rc2
```

Same for `kagent-crds` and `substrate-crds`. `platform-substrate` is git
`platform/substrate-app` (kustomize helmCharts pulls
`oci://ghcr.io/kagent-dev/substrate/helm` + chart name `substrate` — that
parent path is correct for helm/kustomize, not for Argo Helm `repoURL`).
AppProject `viper` allowlists the full chart URLs. Do not revert Argo Helm
apps to the parent path.

### Substrate 0.0.9 chart gaps (GitOps, not live-only)

Chart 0.0.9 cannot express extra ate-api-server ClusterRole rules. The hook
lives in `platform/substrate` and is applied by `platform-substrate-rbac`
(wave 2, Server-Side Apply). On **0.0.9** that ClusterRole is empty on
purpose: v0.0.9 ateapi only lists pods + `actortemplates` / `workerpools` /
`sandboxconfigs`, which the chart already grants. `csidriverconfigs` is a
0.0.12-only CRD. Do not re-add those verbs on this pin.

`SandboxConfig/gvisor-default` is owned only by `platform-substrate`
(`platform/substrate-app` helmCharts). 0.0.9 `SandboxConfig` has no
`pauseImage` (that field is on `ActorTemplate`; kagent rc2 writes it there).
Do not apply that CR from `platform-substrate-rbac` (SharedResourceWarning).
Do not Replace the CR.

`kagent-crds` keeps `substrate.enabled=false` (chart default) so it does **not**
double-install the bundled substrate-crds 0.0.9. Substrate CRDs come from
`platform-substrate-crds` 0.0.9.

Valkey stays at **6** replicas. The 0.0.9 cluster-init Job hardcodes pods
`0..5`; shrinking `valkey.replicas` hangs init. Chart 0.0.9's
`StatefulSet/valkey-cluster` (JWT mode) omits Kubernetes API-defaulted fields
(VCT `volumeMode` / `status`, PVC retention, revision history, update
strategy, pod/container defaults). There is no values key for those. Desired
matches live via JSON6902 in `platform/substrate-app/valkey-cluster-sts-defaults.yaml`.
Do not Replace the StatefulSet and do not add `ignoreDifferences`.

Chart 0.0.9 ships `valkey/valkey:8.0`. A cluster that already ran 0.0.12
(`valkey/valkey:9.1`) must treat the downgrade as a **wipe** (delete the
Valkey PVCs / re-run cluster-init). Do not expect 9.1 data to come up on 8.0.

All default Helm Agents are off (`k8s-agent`, `kgateway-agent`, `istio-agent`,
`promql-agent`, `observability-agent`, `argo-rollouts-agent`, `helm-agent`,
`cilium-policy-agent`, `cilium-manager-agent`, `cilium-debug-agent`). Chart
0.10.0-rc2 toggles are top-level `<name>.enabled` (not `agents.*`).
`grafana-mcp` is off (no Grafana). `querydoc` stays on (tool Deployment, not
an Agent). `kmcp` stays on. The only lab agent is `hello-substrate`
(`platform/kagent-ai`).

## Chat

1. Publish Docker NodePort **30500** on the k3s container (with the other UIs).
2. Open `http://172.16.10.135:30500/`.
3. Pick **kagent/hello-substrate**.
4. Ask something like: `What Kubernetes version is this cluster, and where are you running?`

```bash
docker exec k3s-viper kubectl -n kagent get sandboxagents,modelconfigs,remotemcpservers
docker exec k3s-viper kubectl -n kagent get workerpool
docker exec k3s-viper kubectl -n kagent get actortemplates
docker exec k3s-viper kubectl -n ate-system get pods
docker exec k3s-viper kubectl -n argocd get applications | grep -E 'kagent|substrate'
```

Wait for `hello-substrate` Ready. The first golden snapshot is often 60–90s.

kagent 0.10.0-rc2 creating `ActorTemplate` with `valueFrom.secretKeyRef` is
**correct for substrate 0.0.9**. If that object is rejected
(`spec.containers[0].env[…].value: Required value` or
`ActorTemplateNotFound`), the CRDs are still 0.0.12 (or another pin that
dropped `valueFrom`). Fix the CRD + control-plane pin; do not invent env
vars on `SandboxAgent/hello-substrate`.

## Secrets

| What | Where |
|------|--------|
| Real OpenAI key | Vault `secret/platform/openai` → gateway ExternalSecret `openai-secret` |
| Dummy kagent key | `platform/kagent-ai/dummy-openai-secret.yaml` — `sk-routed-via-agentgateway` |
| License JWTs / Solo keys | **Not used.** OSS only. Do not commit them. |

## Known risk: gVisor on dockerized k3s

Agent Substrate workers run **ateom-gvisor** and atelet is **privileged** with
a hostPath at `/var/lib/ateom-gvisor`. On dockerized k3s (`k3s-viper` in
Docker), `runsc` / nested gVisor may fail (missing runtime, seccomp, or
`/dev/kvm`).

This does **not** block the GitOps install. If workers CrashLoop or
`hello-substrate` never becomes Ready:

- Check atelet / worker logs in `ate-system` and `kagent`.
- Confirm the node can run privileged pods (k3s-in-Docker usually can).
- Nested gVisor may need `runsc` on the k3s node or a privileged worker
  override later — treat that as day-2, not a reason to skip the apps.

JWT-to-ateapi stays on (`ateApiInsecure: true` to the in-cluster API). Do not
disable chart JWT bootstrap to “simplify” the lab.

## Out of scope (this install)

- Solo Enterprise kagent / license JWTs (k8s-goose)
- A real OpenAI key in git
- Substrate **Actor wrap** for the computer-use desktop — follow-up. The
  first path is a normal Deployment behind agentgateway:
  [desktop-computer-use.md](desktop-computer-use.md). This kagent install
  uses `ateom-gvisor` only.

## Related

- UI ports: [platform-ui-access.md](platform-ui-access.md)
- Gateway + models: [agentgateway-langfuse.md](agentgateway-langfuse.md)
- Vault paths: [vault-eso-setup.md](vault-eso-setup.md)
