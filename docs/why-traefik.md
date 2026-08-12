# Why Traefik (not kgateway)

k8s-viper v1 uses **k3s-bundled Traefik** as the HTTP front door on the node IP
(`:80` / `:443`). That is a deliberate lab choice, not a claim that Traefik is
always better than Gateway API implementations such as **kgateway**.

## Decision

| Item | Choice |
|------|--------|
| **Ingress / edge (v1)** | Traefik (k3s default) |
| **API model** | Kubernetes `Ingress` + `ingressClassName: traefik` |
| **Deferred** | kgateway / Gateway API (`Gateway`, `HTTPRoute`) |

## Why Traefik here

1. **Ships with k3s** — single-node bootstrap already has Traefik and ServiceLB.
   No second controller install for day-1.
2. **v1 scope** — secrets (Vault + ESO), GitOps (Argo), dashboard (Headlamp). Edge
   only needs a few host rules on the node IP, not a full gateway platform.
3. **Ingress is enough** — demos (`whoami`, Headlamp host) are host-based HTTP.
   Classic Ingress covers that with low ceremony.
4. **Fewer moving parts** — no extra CRDs, upgrade surface, or data plane to
   operate alongside Argo and Vault on one box.
5. **Matches the design** — design doc and bootstrap assume stock k3s ingress so
   `<node-ip>:80/:443` works out of the box.

## What kgateway is good for

Use (or evaluate) **kgateway** when you want:

- **Gateway API** as the primary model (`Gateway` / `HTTPRoute` / policies)
- Advanced L7 (auth plugins, rate limits, richer routing, multi-team edge)
- A dedicated Envoy-based data plane you will own and upgrade explicitly
- Patterns beyond “lab hosts on a single node”

That is a **platform** choice. v1 intentionally stays on the k3s default path.

## Comparison (lab lens)

| | Traefik (v1) | kgateway |
|--|--------------|----------|
| Install | Free with k3s | Extra chart / CRDs / Argo app |
| API | Ingress (+ Traefik CRDs if needed) | Gateway API first |
| Ops cost on one node | Low | Higher |
| Fine for host demos + LAN | Yes | Overkill for v1 |
| Advanced edge policies | Limited / CRD-heavy | Strong fit |

## When to revisit

Consider Gateway API + kgateway (or another impl) if you:

- Standardize on `HTTPRoute` only across apps
- Need policies Ingress does not express cleanly
- Split edge ownership from the k3s Traefik lifecycle

Until then: **Traefik on the node IP** + **NodePorts for control-plane UIs**
(Headlamp / Argo / Vault) remains the documented access model.

## Related

- Ingress defaults: `platform/ingress/`
- UI ports: [platform-ui-access.md](platform-ui-access.md)
- Design: [specs/2026-08-11-k3s-gitops-platform-design.md](superpowers/specs/2026-08-11-k3s-gitops-platform-design.md)
