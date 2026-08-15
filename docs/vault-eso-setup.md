# Vault + External Secrets Operator (day-1 secrets path)

This guide runs **after** `scripts/bootstrap.sh` and after Argo has synced:

- `platform-vault`
- `platform-external-secrets`

**Never commit** unseal keys, root tokens, or raw secret values to git.

## UI

After init + unseal, open the Vault UI on the node NodePort:

```text
http://172.16.10.135:30200/
```

On Viper, kubectl is inside the k3s container: `docker exec k3s-viper kubectl ...`.

Full port map: [platform-ui-access.md](platform-ui-access.md).

## Lab Vault secret inventory

Paths used by this platform (KV v2 mount `secret/`):

| Path | Used by | Fields (examples) |
|------|---------|-------------------|
| `secret/platform/openai` | agentgateway ExternalSecret (kagent uses a dummy Secret; gateway injects this key) | `api_key` |
| `secret/platform/langfuse` | Langfuse Helm via ExternalSecret | `salt`, `encryption_key`, `nextauth_secret`, `postgres_password`, `redis_password`, `clickhouse_password`, `minio_root_user`, `minio_root_password`, `nextauth_url` |
| `secret/platform/langfuse-otel` | OTEL collector → Langfuse | `public_key`, `secret_key`, `endpoint` |
| `secret/demo/whoami` | optional demo | app-specific |

Write OpenAI key (example):

```bash
export VAULT_TOKEN=...   # root or policy token
vault kv put secret/platform/openai api_key='sk-...' provider=openai
```

## 1. Wait for Vault pod

```bash
# Viper (dockerized k3s):
docker exec k3s-viper kubectl -n vault get pods
# Native k3s: export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
# Expect vault-0 Running (sealed until init+unseal)
```

## 2. Initialize (once)

```bash
kubectl -n vault exec -it vault-0 -- vault operator init -key-shares=5 -key-threshold=3
# Lab may use 1 share / threshold 1 — match what you used at init
```

Store **unseal keys** and **initial root token** offline (password manager).  
If you lose them on a single-node box, you lose access to Vault data.

Lab helper files (not in git): often
`~/.config/k8s-viper/vault-init.json` and `vault-unseal.sh`.

## 3. Unseal (after every pod restart until automated)

```bash
~/.config/k8s-viper/vault-unseal.sh
# or interactive:
kubectl -n vault exec -it vault-0 -- vault operator unseal
```

```bash
kubectl -n vault exec vault-0 -- vault status
```

## 4. Login and enable KV v2

```bash
kubectl -n vault exec -it vault-0 -- sh -c 'vault login'
# paste root token

kubectl -n vault exec vault-0 -- vault secrets enable -path=secret kv-v2
# ignore error if already enabled
```

## 5. Kubernetes auth for External Secrets Operator

```bash
kubectl -n vault exec vault-0 -- vault auth enable kubernetes
# ignore if already enabled

kubectl -n vault exec vault-0 -- sh -c '
  vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443" \
    disable_local_ca_jwt=false
'

kubectl -n vault exec vault-0 -- sh <<'EOF'
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

ClusterSecretStore (already applied when ready):

```bash
kubectl get clustersecretstore vault-backend
# Ready=True when Vault is unsealed and k8s auth works
```

Example store YAML: `platform/external-secrets/cluster-secret-store-vault.example.yaml`.

## 6. Apps consume secrets via ExternalSecret only

Examples in-repo:

- `platform/agentgateway-ai/external-secret-openai.yaml` → Secret `openai-secret`
- `platform/langfuse/external-secret.yaml` → Secret `langfuse-credentials`
- `platform/agentgateway-ai/otel-collector.yaml` → Secret `langfuse-otel-auth`
- `platform/kagent-ai/dummy-openai-secret.yaml` → dummy Secret `kagent-openai` (not from Vault)

Never put secret **values** in git — only paths and `ExternalSecret` manifests.

## Related

- AI gateway + Langfuse: [agentgateway-langfuse.md](agentgateway-langfuse.md)
- UI ports: [platform-ui-access.md](platform-ui-access.md)
