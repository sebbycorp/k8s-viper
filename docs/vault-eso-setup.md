# Vault + External Secrets Operator (day-1 secrets path)

This guide runs **after** `scripts/bootstrap.sh` and after Argo has synced:

- `platform-vault`
- `platform-external-secrets`

**Never commit** unseal keys, root tokens, or raw secret values to git.

## UI

After init + unseal, open the Vault UI on the node NodePort:

```text
http://<node-ip>:30200/
```

See [docs/platform-ui-access.md](platform-ui-access.md) for the full port map
(Argo CD / Headlamp / Vault).

## 1. Wait for Vault pod

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl -n vault get pods
# Expect vault-0 Running (it will be sealed / not ready for traffic until init+unseal)
```

## 2. Initialize (once)

```bash
kubectl -n vault exec -it vault-0 -- vault operator init -key-shares=5 -key-threshold=3
```

Store the **5 unseal keys** and **initial root token** offline (password manager / sealed note).  
If you lose them on a single-node box, you lose access to Vault data.

## 3. Unseal (after every pod restart until you automate)

```bash
kubectl -n vault exec -it vault-0 -- vault operator unseal   # key 1
kubectl -n vault exec -it vault-0 -- vault operator unseal   # key 2
kubectl -n vault exec -it vault-0 -- vault operator unseal   # key 3
```

Check status:

```bash
kubectl -n vault exec -it vault-0 -- vault status
```

## 4. Login and enable KV v2

```bash
kubectl -n vault exec -it vault-0 -- sh -c 'vault login'
# paste root token when prompted

kubectl -n vault exec -it vault-0 -- vault secrets enable -path=secret kv-v2
```

Write a test secret:

```bash
kubectl -n vault exec -it vault-0 -- vault kv put secret/demo/whoami message="hello-from-vault"
```

## 5. Kubernetes auth for External Secrets Operator

```bash
kubectl -n vault exec -it vault-0 -- vault auth enable kubernetes

# SA JWT reviewer + CA from the cluster
kubectl -n vault exec -it vault-0 -- sh <<'EOF'
vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443"
EOF
```

Vault on Kubernetes usually needs the token reviewer JWT and CA. Preferred approach using the Vault chart service account:

```bash
# From a workstation with kubectl:
export VAULT_SA_SECRET_NAME="$(kubectl -n vault get sa vault -o jsonpath='{.secrets[0].name}' 2>/dev/null || true)"

# Modern clusters may not auto-create SA secrets; create a token Secret or use:
kubectl -n vault exec -it vault-0 -- sh -c '
  vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443" \
    disable_local_ca_jwt=false
'
```

If `disable_local_ca_jwt=false` works with your Vault version (1.15+ in-cluster), prefer it. Otherwise follow [Vault Kubernetes auth](https://developer.hashicorp.com/vault/docs/auth/kubernetes) for your k3s version.

Create policy + role for ESO:

```bash
kubectl -n vault exec -it vault-0 -- sh <<'EOF'
vault policy write external-secrets - <<'POLICY'
path "secret/data/*" {
  capabilities = ["read", "list"]
}
path "secret/metadata/*" {
  capabilities = ["read", "list"]
}
POLICY

vault write auth/kubernetes/role/external-secrets \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=external-secrets \
  ttl=1h
EOF
```

> Service account name may differ slightly depending on the ESO chart release name. Confirm with:
>
> ```bash
> kubectl -n external-secrets get sa
> ```
>
> Adjust `bound_service_account_names` to match (often `external-secrets`).

## 6. ClusterSecretStore

1. Copy the example:

   ```bash
   cp platform/external-secrets/cluster-secret-store-vault.example.yaml \
      platform/external-secrets/manifests/cluster-secret-store-vault.yaml
   ```

2. Add it to `platform/external-secrets/manifests/kustomization.yaml` **or** apply with kubectl once:

   ```bash
   kubectl apply -f platform/external-secrets/cluster-secret-store-vault.example.yaml
   ```

3. For ongoing GitOps, prefer a dedicated Argo Application or extend the ESO multi-source app with a `path: platform/external-secrets/manifests` source after the store is ready.

Example `ExternalSecret`:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: demo-whoami
  namespace: apps
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: demo-whoami
    creationPolicy: Owner
  data:
    - secretKey: message
      remoteRef:
        key: demo/whoami
        property: message
```

## 7. UI access (LAN / port-forward)

```bash
kubectl -n vault port-forward svc/vault-ui 8200:8200
# open http://127.0.0.1:8200
```

Do not expose Vault on the node Ingress without TLS and auth hardening.

## Recovery notes

| Event | Action |
|-------|--------|
| Node reboot | Unseal Vault again (3 keys) |
| Lost unseal keys | Restore from backup or re-init (data loss if no snapshot) |
| ESO SecretSyncedError | Check Vault unsealed, role SA name, KV path |
