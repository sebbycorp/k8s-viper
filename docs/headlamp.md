# Headlamp (Kubernetes dashboard)

[Headlamp](https://headlamp.dev/) is the in-cluster OSS dashboard for k8s-viper.
Argo CD deploys it from `argocd/apps/platform-headlamp.yaml` using
`platform/headlamp/values.yaml`.

## Access

**Preferred (NodePort):** open `http://<node-ip>:30080/`

```bash
kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}{"\n"}'
```

**Also (Ingress):** map the node IP and open http://headlamp.viper.local/

```text
<node-ip>  headlamp.viper.local
```

When Headlamp asks for a token, create one (cluster-admin SA used by the chart
is fine for a private lab; create a read-only SA if you prefer):

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Token for the Headlamp service account (chart SA name may be headlamp)
kubectl -n headlamp create token headlamp --duration=12h
```

Paste the token into the Headlamp login form.

If the SA name differs:

```bash
kubectl -n headlamp get sa
kubectl -n headlamp create token <sa-name> --duration=12h
```

Port map for all platform UIs (including agentgateway and Langfuse):
[platform-ui-access.md](platform-ui-access.md).

## Security notes

- **v1 lab:** NodePort + token auth on a private network is enough. Do not expose
  Headlamp to the public internet without TLS and real identity (OIDC).
- Leave `config.unsafeUseServiceAccountToken: false` (default). Enabling it
  makes every browser user the pod SA with no login.
- Chart binds to `cluster-admin` for a full dashboard experience. Narrow
  `clusterRoleBinding.clusterRoleName` in values when multi-user access appears.

## Day-2 changes

Edit `platform/headlamp/values.yaml` (NodePort, ingress host, resources, OIDC
later), PR, merge to `main`. Argo auto-syncs. Pin chart bumps in
`argocd/apps/platform-headlamp.yaml` `targetRevision`.
