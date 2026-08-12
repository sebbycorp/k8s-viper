# Platform UI access (NodePort)

Lab access for control-plane UIs on the **node IP** without `/etc/hosts` or
`kubectl port-forward`. Services stay private to your LAN — do not publish these
ports to the public internet without TLS + real auth.

## Ports (fixed)

| UI | URL | Auth |
|----|-----|------|
| **Headlamp** | `http://<node-ip>:30080/` | SA token — [docs/headlamp.md](headlamp.md) |
| **Argo CD** | `https://<node-ip>:30443/` | `admin` + initial secret (see below) |
| **Vault UI** | `http://<node-ip>:30200/` | root / app token after init — [docs/vault-eso-setup.md](vault-eso-setup.md) |

Also available:

| UI | Alternate |
|----|-----------|
| Headlamp | Ingress `http://headlamp.viper.local/` (host → node IP in `/etc/hosts`) |
| Argo CD | HTTP NodePort `http://<node-ip>:30081/` (often redirects to HTTPS) |
| whoami demo | Ingress `http://whoami.viper.local/` |

Get the node IP:

```bash
kubectl get nodes -o wide
# or
kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}{"\n"}'
```

## Argo CD login

```bash
# admin password (bootstrap creates this secret once)
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Open `https://<node-ip>:30443/`, user **admin**, accept the self-signed cert warning.

GitOps source for the NodePort Service: `platform/argocd-access/` → Application
`platform-argocd-access`. Bootstrap still installs Argo CD itself; this only
exposes the UI.

## Headlamp login

```bash
kubectl -n headlamp create token headlamp --duration=12h
```

Paste into the Headlamp token form. Full notes: [docs/headlamp.md](headlamp.md).

## Vault UI

Vault must be initialized and unsealed first. UI listens on the same API port
(8200) via Service `vault-ui` NodePort **30200**.

## Change ports later

| Component | Where |
|-----------|--------|
| Headlamp | `platform/headlamp/values.yaml` → `service.nodePort` |
| Vault UI | `platform/vault/values.yaml` → `ui.serviceNodePort` |
| Argo CD | `platform/argocd-access/argocd-server-nodeport.yaml` → `nodePort` |

PR → merge `main` → Argo auto-syncs. Pick free ports in **30000–32767** (avoid
Traefik’s dynamic LB node ports if you care about collisions).

## Security

- Token / password auth only; no SSO in v1.
- Headlamp chart uses `cluster-admin` for a full lab view.
- Prefer LAN-only access; close NodePorts if the node has a public IP.

## Ingress controller

HTTP hosts on `:80` use **k3s Traefik**, not kgateway. Decision and when to
revisit: [why-traefik.md](why-traefik.md).
