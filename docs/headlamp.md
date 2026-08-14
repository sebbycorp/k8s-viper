# Headlamp (Kubernetes dashboard)

[Headlamp](https://headlamp.dev/) is the in-cluster OSS dashboard for k8s-viper.
Argo CD deploys it from `argocd/apps/platform-headlamp.yaml` pointing at
`platform/headlamp` (kustomize `helmCharts` + `values.yaml`). A JSON6902
patch drops `spec.template.spec.hostUsers` from the chart so desired matches
live: k3s drops `hostUsers: true` (the API default), which otherwise leaves
the app permanently OutOfSync. Do not set `hostUsers: false` (that enables
user namespaces).

## Access

**Preferred (NodePort):** open `http://172.16.10.135:30080/`

On Viper, kubectl is inside the k3s container (`docker exec k3s-viper kubectl ...`).

**Also (Ingress):** map the node IP and open http://headlamp.viper.local/

```text
172.16.10.135  headlamp.viper.local
```

When Headlamp asks for a token, create one (cluster-admin SA used by the chart
is fine for a private lab; create a read-only SA if you prefer):

```bash
docker exec k3s-viper kubectl -n headlamp create token headlamp --duration=12h
```

Paste the token into the Headlamp login form.

If the SA name differs:

```bash
docker exec k3s-viper kubectl -n headlamp get sa
docker exec k3s-viper kubectl -n headlamp create token <sa-name> --duration=12h
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
`platform/headlamp/kustomization.yaml` (`helmCharts[].version`).

Repo-server must run `kustomize build --enable-helm`. `platform-argocd-access`
SSA-merges `kustomize.buildOptions: --enable-helm` onto `argocd-cm` (bootstrap
also sets the key on new clusters). After that key is live, restart
`argocd-repo-server` so it picks up the option.
