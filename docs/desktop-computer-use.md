# Computer-use desktop (lab prototype)

A custom desktop image behind **agentgateway** on Viper. First path is a
normal Deployment. Substrate / AgentHarness comes later.

## Architecture

```text
Human (Chat UI + separate Desktop Viewer)
        ↓
  agentgateway          ← policy, MCP, LLM routing, observability
        ↓
  kagent AgentHarness / Actor   (later; kagent 0.10.0-rc2 is on main via PR #8)
        ↓
  Substrate Actor (gVisor on this box; microVM later)
        ↓
  Custom Desktop Image
  ├── Xvfb + Window Manager
  ├── Browser + Apps
  ├── Streaming (noVNC)
  └── Agent process + computer-use tools
```

**This PR proves the bottom + the gateway front door only.** The desktop
runs as Deployment `desktop-computer-use` in namespace `desktop`. It does
**not** require substrate or AgentHarness to be installed.

Chat still goes through the existing LLM paths (`/v1`, `/openai`, `/spark`)
on the same Gateway (`agentgateway-proxy` :30100). The viewer and the
computer-use API are extra prefixes on that Gateway — not a second proxy.

```text
agentgateway-proxy :30100
     ├─ /v1 · /openai     → OpenAI
     ├─ /spark            → DGX Spark vLLM
     ├─ /desktop/         → noVNC (Service desktop-computer-use:6080)
     └─ /desktop-api/     → computer-use HTTP API (:18790)
```

## What is next (follow-up — do not do this yet)

**PR #8** (kagent **0.10.0-rc2** + substrate **0.0.12**) is on `main`. Next
wrap this desktop in an **ActorTemplate / AgentHarness**.

- Substrate on Viper = **gVisor** (this box).
- **microVM later.** Viper is dockerized k3s with **no `/dev/kvm`**. Do not
  claim microVM works on Viper.
- gVisor + Chromium may need a later tweak (seccomp / syscall allowlist).
  Do not block this Deployment on that work.

## Build and import the image on Viper

The Deployment uses `viper-desktop:dev` with `imagePullPolicy: IfNotPresent`.
The image **must be imported on the k3s node before the pod can start**.
Intended published name: `ghcr.io/sebbycorp/viper-desktop:dev`.

```bash
# on Viper
docker build -t viper-desktop:dev images/desktop-computer-use
docker save viper-desktop:dev | docker exec -i k3s-viper ctr images import -
```

Then wait for Argo app `platform-desktop` (or sync it). Check:

```bash
docker exec k3s-viper kubectl -n desktop get deploy,pods,svc
docker exec k3s-viper kubectl -n desktop describe pod -l app.kubernetes.io/name=desktop-computer-use
```

`ImagePullBackOff` means the import has not landed (or the tag does not
match). There is no registry pull for `viper-desktop:dev`.

## Viewer and API

Same NodePort as the rest of agentgateway: **`172.16.10.135:30100`**.

| What | URL |
|------|-----|
| Desktop viewer (noVNC) | `http://172.16.10.135:30100/desktop/` |
| noVNC UI (explicit) | `http://172.16.10.135:30100/desktop/vnc.html?autoconnect=1&resize=scale` |
| Computer-use health | `http://172.16.10.135:30100/desktop-api/health` |
| Screenshot (png) | `http://172.16.10.135:30100/desktop-api/screenshot` |
| Chat (unchanged) | `http://172.16.10.135:30100/v1` and `/spark` |

```bash
export GW=http://172.16.10.135:30100

curl -sS "$GW/desktop-api/health"
curl -sS -o /tmp/desktop.png "$GW/desktop-api/screenshot"

# click / type / key — no auth in the process (gateway is the front door)
curl -sS -X POST "$GW/desktop-api/click" \
  -H 'content-type: application/json' \
  -d '{"x":640,"y":400,"button":"left"}'

curl -sS -X POST "$GW/desktop-api/type" \
  -H 'content-type: application/json' \
  -d '{"text":"hello from viper"}'

curl -sS -X POST "$GW/desktop-api/key" \
  -H 'content-type: application/json' \
  -d '{"key":"Return"}'
```

VNC is **lab-open**: `x11vnc -nopw`. No password is stored in git or the
image. x11vnc listens on localhost inside the pod; only noVNC `:6080` and
the API `:18790` are on the Service. Keep `:30100` on the LAN.

## GitOps

| Piece | Path |
|-------|------|
| Image | `images/desktop-computer-use/` |
| App | `platform/desktop/` (ns `desktop`) |
| Routes | `platform/agentgateway-ai/httproute-desktop.yaml` + `backend-desktop.yaml` |
| Argo | `argocd/apps/platform-desktop.yaml` (wave 2, after `platform-agentgateway-ai`) |

Routes attach to Gateway `agentgateway-proxy` with the same `parentRef`
shape as OpenAI / Spark. Backends are `AgentgatewayBackend` `static` hosts
pointing at `desktop-computer-use.desktop.svc.cluster.local` (in-cluster
Service). URLRewrite strips `/desktop/` and `/desktop-api/` so noVNC and
the API see their native paths.

## Honest limits

- **noVNC is not WebRTC.** Expect a few hundred ms of glass-to-glass delay
  and JPEG/WebSocket artifacts. Fine for a lab viewer; not a product stream.
- **Do not suspend a live desktop.** The session is the pod. Delete/restart
  loses the X session. There is no snapshot/resume in this prototype.
- **Image must be imported** (`ctr images import`) before the pod can start.
  `IfNotPresent` will not pull `viper-desktop:dev` from a registry.
- **Viper cannot do microVM.** dockerized k3s, no `/dev/kvm`. Next isolation
  step is gVisor via substrate, not Firecracker/Cloud Hypervisor on this box.
- **gVisor + Chromium** may need a later syscall/seccomp tweak. This
  Deployment is not gVisor.
- **No auth on the computer-use process.** Lab-open on the LAN behind
  agentgateway. Do not publish `:30100` to the public internet.
- **Do not put VNC passwords in git.** If you add a password later, generate
  it at runtime (emptyDir / projected secret), never commit it.
