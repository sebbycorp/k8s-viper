# OSS kagent + Agent Substrate

Lab install of **open-source** kagent and Agent Substrate on dockerized k3s.
This is **not** Solo Enterprise kagent (that lives in k8s-goose).

| Piece | Pin | Namespace |
|-------|-----|-----------|
| kagent Helm + CRDs | **0.10.0-rc2** (`oci://ghcr.io/kagent-dev/kagent/helm`) | `kagent` |
| Agent Substrate Helm + CRDs | **0.0.12** (`oci://ghcr.io/kagent-dev/substrate/helm`) | `ate-system` |
| Worker image | `ghcr.io/kagent-dev/substrate/ateom-gvisor:v0.0.12` | WorkerPool `kagent-default` |
| UI | NodePort **30500** | `kagent-ui-nodeport` |

Official docs still mention 0.9.9 / 0.0.8. This lab pins the newest published
pair as of 2026-08-15: **0.10.0-rc2** (2026-08-11) + **0.0.12** (2026-08-12).

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
| 1 | `platform-substrate-crds` | OCI `substrate-crds` 0.0.12 |
| 2 | `platform-substrate` | OCI `substrate` 0.0.12 + `platform/substrate/values.yaml` |
| 3 | `platform-kagent-crds` | OCI `kagent-crds` 0.10.0-rc2 |
| 4 | `platform-kagent` | OCI `kagent` 0.10.0-rc2 + `platform/kagent/values.yaml` |
| 5 | `platform-kagent-ai` | git `platform/kagent-ai` (dummy Secret, hello agent, UI NodePort) |

`kagent-crds` keeps `substrate.enabled=false` (chart default) so it does **not**
install the older bundled substrate-crds 0.0.9. Substrate CRDs come from
`platform-substrate-crds` 0.0.12.

Valkey stays at **6** replicas. The 0.0.12 cluster-init Job hardcodes pods
`0..5`; shrinking `valkey.replicas` hangs init.

`grafana-mcp` and `observability-agent` are off (no Grafana in this lab).
`kmcp` stays on.

## Chat

1. Publish Docker NodePort **30500** on the k3s container (with the other UIs).
2. Open `http://172.16.10.135:30500/`.
3. Pick **kagent/hello-substrate**.
4. Ask something like: `What Kubernetes version is this cluster, and where are you running?`

```bash
docker exec k3s-viper kubectl -n kagent get sandboxagents,modelconfigs,remotemcpservers
docker exec k3s-viper kubectl -n kagent get workerpool
docker exec k3s-viper kubectl -n ate-system get pods
docker exec k3s-viper kubectl -n argocd get applications | grep -E 'kagent|substrate'
```

Wait for `hello-substrate` Ready. The first golden snapshot is often 60–90s.

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
- Substrate **desktop / computer-use** worker image — follow-up PR. This
  install uses `ateom-gvisor` only.

## Related

- UI ports: [platform-ui-access.md](platform-ui-access.md)
- Gateway + models: [agentgateway-langfuse.md](agentgateway-langfuse.md)
- Vault paths: [vault-eso-setup.md](vault-eso-setup.md)
