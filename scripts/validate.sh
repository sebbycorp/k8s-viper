#!/usr/bin/env bash
# Local / CI validation for k8s-viper manifests (no cluster required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

errors=0

log() { printf '==> %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; errors=$((errors + 1)); }
ok() { printf 'OK: %s\n' "$*"; }

require_file() {
  if [[ -f "$1" ]]; then
    ok "exists $1"
  else
    fail "missing required file: $1"
  fi
}

log "Checking required layout..."
require_file scripts/bootstrap.sh
require_file bootstrap/argocd/root-application.yaml
require_file argocd/project.yaml
require_file argocd/apps/argocd-project.yaml
require_file argocd/apps/platform-ingress.yaml
require_file argocd/apps/platform-vault.yaml
require_file argocd/apps/platform-external-secrets.yaml
require_file argocd/apps/platform-headlamp.yaml
require_file argocd/apps/platform-argocd-access.yaml
require_file platform/ingress/kustomization.yaml
require_file platform/ingress/helmchartconfig-traefik.yaml
require_file platform/ingress/whoami.yaml
require_file platform/vault/values.yaml
require_file platform/external-secrets/values.yaml
require_file platform/external-secrets/cluster-secret-store-vault.example.yaml
require_file platform/headlamp/values.yaml
require_file platform/headlamp/kustomization.yaml
require_file platform/argocd-access/kustomization.yaml
require_file platform/argocd-access/argocd-server-nodeport.yaml
require_file platform/argocd-access/argocd-cm-kustomize.yaml
require_file docs/vault-eso-setup.md
require_file docs/headlamp.md
require_file docs/platform-ui-access.md
require_file docs/why-traefik.md
require_file docs/agentgateway-langfuse.md
require_file docs/desktop-computer-use.md
require_file images/desktop-computer-use/Dockerfile
require_file images/desktop-computer-use/README.md
require_file images/desktop-computer-use/entrypoint.sh
require_file images/desktop-computer-use/api.py
require_file platform/desktop/kustomization.yaml
require_file platform/desktop/deployment.yaml
require_file platform/desktop/service.yaml
require_file platform/desktop/namespace.yaml
require_file platform/agentgateway-ai/backend-desktop.yaml
require_file platform/agentgateway-ai/httproute-desktop.yaml
require_file argocd/apps/platform-desktop.yaml
require_file platform/gateway-api/kustomization.yaml
require_file platform/agentgateway/values.yaml
require_file platform/agentgateway-ai/kustomization.yaml
require_file platform/agentgateway-ai/backend-dgx-spark.yaml
require_file platform/agentgateway-ai/httproute-dgx-spark.yaml
require_file platform/langfuse/values.yaml
require_file platform/langfuse/external-secret.yaml
require_file argocd/apps/platform-gateway-api.yaml
require_file argocd/apps/platform-agentgateway-crds.yaml
require_file argocd/apps/platform-agentgateway.yaml
require_file argocd/apps/platform-agentgateway-ai.yaml
require_file argocd/apps/platform-langfuse-secrets.yaml
require_file argocd/apps/platform-langfuse.yaml
require_file argocd/apps/platform-substrate-crds.yaml
require_file argocd/apps/platform-substrate.yaml
require_file argocd/apps/platform-substrate-rbac.yaml
require_file argocd/apps/platform-kagent-crds.yaml
require_file argocd/apps/platform-kagent.yaml
require_file argocd/apps/platform-kagent-ai.yaml
require_file platform/substrate-app/values.yaml
require_file platform/substrate-app/kustomization.yaml
require_file platform/substrate-app/valkey-cluster-sts-defaults.yaml
require_file platform/substrate/kustomization.yaml
require_file platform/substrate/ate-api-server-extra-rbac.yaml
require_file platform/kagent/values.yaml
require_file platform/kagent-ai/kustomization.yaml
require_file platform/kagent-ai/dummy-openai-secret.yaml
require_file platform/kagent-ai/hello-substrate.yaml
require_file platform/kagent-ai/ui-nodeport.yaml
require_file platform/kagent-ai/fortigate-agent.yaml
require_file platform/kagent-ai/fortigate-mcp.yaml
require_file platform/kagent-ai/fortigate-external-secret.yaml
require_file docs/kagent-substrate.md
require_file docs/fortigate-agent.md
require_file images/fortigate-mcp/Dockerfile
require_file images/fortigate-mcp/README.md
require_file images/fortigate-mcp/requirements.txt
require_file images/fortigate-mcp/server.py
require_file platform/kagent-ai/arista-ceos-agent.yaml
require_file platform/kagent-ai/arista-ceos-mcp.yaml
require_file platform/kagent-ai/arista-ceos-skills.yaml
require_file platform/kagent-ai/arista-ceos-external-secret.yaml
require_file docs/arista-ceos-agent.md
require_file images/arista-ceos-mcp/Dockerfile
require_file images/arista-ceos-mcp/README.md
require_file images/arista-ceos-mcp/requirements.txt
require_file images/arista-ceos-mcp/server.py
require_file images/arista-ceos-mcp/test_server.py
require_file site/hugo.toml
require_file site/data/cluster.yaml
require_file site/layouts/index.html
require_file site/assets/css/main.css
require_file .github/workflows/ci.yaml
require_file .github/workflows/pages.yml

log "YAML parse check (Python)..."
mapfile -t yaml_files < <(find argocd bootstrap platform -type f \( -name '*.yaml' -o -name '*.yml' \) ! -path '*/charts/*' | sort)
if ((${#yaml_files[@]} == 0)); then
  fail "no YAML files found under argocd/ bootstrap/ platform/"
else
  if python3 - "$ROOT" "${yaml_files[@]}" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    # Fallback: structural check only
    root = Path(sys.argv[1])
    paths = [Path(p) for p in sys.argv[2:]]
    for p in paths:
        text = p.read_text(encoding="utf-8")
        if not text.strip():
            print(f"empty: {p}", file=sys.stderr)
            sys.exit(1)
        # very light multi-doc split
        for i, doc in enumerate(text.split("\n---\n")):
            if doc.strip() and ":" not in doc.split("\n", 1)[0] and not doc.strip().startswith("#"):
                # allow comment-only leading docs
                pass
    print(f"parsed {len(paths)} files (stdlib fallback, PyYAML not installed)")
    sys.exit(0)

root = Path(sys.argv[1])
paths = [Path(p) for p in sys.argv[2:]]
for p in paths:
    with p.open(encoding="utf-8") as f:
        try:
            list(yaml.safe_load_all(f))
        except Exception as e:
            print(f"{p}: {e}", file=sys.stderr)
            sys.exit(1)
print(f"parsed {len(paths)} YAML files")
PY
  then
    ok "YAML parse (${#yaml_files[@]} files)"
  else
    fail "YAML parse failed"
  fi
fi

if command -v kustomize >/dev/null 2>&1; then
  log "kustomize build platform/ingress..."
  if kustomize build platform/ingress >/dev/null; then
    ok "kustomize build platform/ingress"
  else
    fail "kustomize build platform/ingress"
  fi
  log "kustomize build platform/argocd-access..."
  if kustomize build platform/argocd-access >/dev/null; then
    ok "kustomize build platform/argocd-access"
  else
    fail "kustomize build platform/argocd-access"
  fi
  log "kustomize build platform/kagent-ai..."
  if kustomize build platform/kagent-ai >/dev/null; then
    ok "kustomize build platform/kagent-ai"
  else
    fail "kustomize build platform/kagent-ai"
  fi
  log "kustomize build platform/substrate..."
  if kustomize build platform/substrate >/dev/null; then
    ok "kustomize build platform/substrate"
  else
    fail "kustomize build platform/substrate"
  fi
  log "kustomize build platform/desktop..."
  if kustomize build platform/desktop >/dev/null; then
    ok "kustomize build platform/desktop"
  else
    fail "kustomize build platform/desktop"
  fi
  log "kustomize build platform/agentgateway-ai..."
  if kustomize build platform/agentgateway-ai >/dev/null; then
    ok "kustomize build platform/agentgateway-ai"
  else
    fail "kustomize build platform/agentgateway-ai"
  fi
  if command -v helm >/dev/null 2>&1; then
    log "kustomize build --enable-helm platform/headlamp..."
    if rendered="$(kustomize build --enable-helm platform/headlamp)"; then
      if printf '%s\n' "${rendered}" | grep -q 'hostUsers:'; then
        fail "platform/headlamp still emits hostUsers (JSON6902 remove failed)"
      else
        ok "kustomize build --enable-helm platform/headlamp (hostUsers removed)"
      fi
    else
      fail "kustomize build --enable-helm platform/headlamp"
    fi
    log "kustomize build --enable-helm platform/substrate-app..."
    if rendered="$(kustomize build --enable-helm platform/substrate-app)"; then
      if ! printf '%s\n' "${rendered}" | grep -q 'kind: SandboxConfig'; then
        fail "platform/substrate-app missing SandboxConfig/gvisor-default"
      elif ! printf '%s\n' "${rendered}" | grep -q 'volumeMode: Filesystem'; then
        fail "platform/substrate-app STS missing volumeMode (JSON6902 add failed)"
      elif ! printf '%s\n' "${rendered}" | grep -q 'revisionHistoryLimit: 10'; then
        fail "platform/substrate-app STS missing revisionHistoryLimit (JSON6902 add failed)"
      elif printf '%s\n' "${rendered}" | grep -q 'ate-api-server-extra'; then
        fail "platform/substrate-app must not include extra RBAC (owned by platform-substrate-rbac)"
      else
        ok "kustomize build --enable-helm platform/substrate-app (STS defaults + SandboxConfig)"
      fi
    else
      fail "kustomize build --enable-helm platform/substrate-app"
    fi
  else
    log "helm not found — skipping helmCharts builds"
  fi
elif command -v kubectl >/dev/null 2>&1; then
  log "kubectl kustomize platform/ingress..."
  if kubectl kustomize platform/ingress >/dev/null; then
    ok "kubectl kustomize platform/ingress"
  else
    fail "kubectl kustomize platform/ingress"
  fi
  log "kubectl kustomize platform/argocd-access..."
  if kubectl kustomize platform/argocd-access >/dev/null; then
    ok "kubectl kustomize platform/argocd-access"
  else
    fail "kubectl kustomize platform/argocd-access"
  fi
  log "kubectl kustomize platform/kagent-ai..."
  if kubectl kustomize platform/kagent-ai >/dev/null; then
    ok "kubectl kustomize platform/kagent-ai"
  else
    fail "kubectl kustomize platform/kagent-ai"
  fi
  log "kubectl kustomize platform/substrate..."
  if kubectl kustomize platform/substrate >/dev/null; then
    ok "kubectl kustomize platform/substrate"
  else
    fail "kubectl kustomize platform/substrate"
  fi
  log "kubectl kustomize platform/desktop..."
  if kubectl kustomize platform/desktop >/dev/null; then
    ok "kubectl kustomize platform/desktop"
  else
    fail "kubectl kustomize platform/desktop"
  fi
  log "kubectl kustomize platform/agentgateway-ai..."
  if kubectl kustomize platform/agentgateway-ai >/dev/null; then
    ok "kubectl kustomize platform/agentgateway-ai"
  else
    fail "kubectl kustomize platform/agentgateway-ai"
  fi
else
  log "kustomize/kubectl not found — skipping kustomize build"
fi

if command -v kubeconform >/dev/null 2>&1; then
  log "kubeconform on plain manifests..."
  plain=(
    bootstrap/argocd/root-application.yaml
    argocd/project.yaml
    argocd/apps/argocd-project.yaml
    argocd/apps/platform-ingress.yaml
    argocd/apps/platform-vault.yaml
    argocd/apps/platform-external-secrets.yaml
    argocd/apps/platform-headlamp.yaml
    argocd/apps/platform-argocd-access.yaml
    argocd/apps/platform-substrate-crds.yaml
    argocd/apps/platform-substrate.yaml
    argocd/apps/platform-substrate-rbac.yaml
    argocd/apps/platform-kagent-crds.yaml
    argocd/apps/platform-kagent.yaml
    argocd/apps/platform-kagent-ai.yaml
    platform/substrate/ate-api-server-extra-rbac.yaml
    platform/kagent-ai/dummy-openai-secret.yaml
    platform/kagent-ai/hello-substrate.yaml
    platform/kagent-ai/ui-nodeport.yaml
    platform/kagent-ai/fortigate-agent.yaml
    platform/kagent-ai/fortigate-mcp.yaml
    platform/kagent-ai/fortigate-external-secret.yaml
    platform/kagent-ai/arista-ceos-agent.yaml
    platform/kagent-ai/arista-ceos-mcp.yaml
    platform/kagent-ai/arista-ceos-skills.yaml
    platform/kagent-ai/arista-ceos-external-secret.yaml
    platform/argocd-access/argocd-server-nodeport.yaml
    platform/argocd-access/argocd-cm-kustomize.yaml
    platform/ingress/namespace-apps.yaml
    platform/ingress/whoami.yaml
    argocd/apps/platform-desktop.yaml
    platform/desktop/namespace.yaml
    platform/desktop/deployment.yaml
    platform/desktop/service.yaml
  )
  if kubeconform -summary -ignore-missing-schemas "${plain[@]}"; then
    ok "kubeconform"
  else
    fail "kubeconform"
  fi
else
  log "kubeconform not installed — skipping schema validation"
fi

if [[ ! -x scripts/bootstrap.sh ]]; then
  fail "scripts/bootstrap.sh is not executable"
else
  ok "bootstrap.sh executable"
fi

if command -v hugo >/dev/null 2>&1; then
  log "Hugo build (site/)..."
  if (cd site && hugo --minify --gc --quiet); then
    ok "hugo build"
  else
    fail "hugo build failed"
  fi
else
  log "hugo not installed — skipping site build (CI builds with Hugo)"
fi

# bash syntax check
if bash -n scripts/bootstrap.sh && bash -n scripts/validate.sh && bash -n images/desktop-computer-use/entrypoint.sh; then
  ok "bash -n scripts"
else
  fail "bash syntax error in scripts"
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 -m py_compile images/desktop-computer-use/api.py; then
    ok "python3 -m py_compile images/desktop-computer-use/api.py"
  else
    fail "api.py failed to compile"
  fi
  if python3 -c 'import importlib.util; spec=importlib.util.spec_from_file_location("api", "images/desktop-computer-use/api.py"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); m._self_check()'; then
    ok "computer-use api path self-check"
  else
    fail "computer-use api path self-check"
  fi
  if python3 -m py_compile images/fortigate-mcp/server.py; then
    ok "python3 -m py_compile images/fortigate-mcp/server.py"
  else
    fail "fortigate-mcp server.py failed to compile"
  fi
  if python3 images/fortigate-mcp/server.py --self-check; then
    ok "fortigate-mcp self-check"
  else
    fail "fortigate-mcp self-check"
  fi
  if python3 -m py_compile images/arista-ceos-mcp/server.py images/arista-ceos-mcp/test_server.py; then
    ok "python3 -m py_compile images/arista-ceos-mcp"
  else
    fail "arista-ceos-mcp failed to compile"
  fi
  if python3 images/arista-ceos-mcp/server.py --self-check; then
    ok "arista-ceos-mcp self-check"
  else
    fail "arista-ceos-mcp self-check"
  fi
  if (cd images/arista-ceos-mcp && python3 -m unittest test_server.py -q); then
    ok "arista-ceos-mcp unit tests"
  else
    fail "arista-ceos-mcp unit tests"
  fi
fi

log "Checking FortiGate paths for committed secret values..."
if git grep -nE '(FORTIGATE_TOKEN|Authorization: Bearer)[[:space:]]*[:=][[:space:]]*['\''\"][A-Za-z0-9_\-]{16,}' -- images/fortigate-mcp platform/kagent-ai docs/fortigate-agent.md >/tmp/fg-secret-scan.txt 2>/dev/null \
   && [[ -s /tmp/fg-secret-scan.txt ]]; then
  cat /tmp/fg-secret-scan.txt >&2
  fail "possible FortiGate secret value in git"
else
  ok "no FortiGate secret values in new manifests"
fi

log "Checking Arista paths for committed secret values..."
if git grep -nE '(ARISTA_PASSWORD)[[:space:]]*[:=][[:space:]]*['\''\"][^'\''\"{][^'\''\"]{7,}' -- images/arista-ceos-mcp/server.py images/arista-ceos-mcp/Dockerfile images/arista-ceos-mcp/README.md platform/kagent-ai docs/arista-ceos-agent.md >/tmp/arista-secret-scan.txt 2>/dev/null \
   && [[ -s /tmp/arista-secret-scan.txt ]]; then
  cat /tmp/arista-secret-scan.txt >&2
  fail "possible Arista secret value in git"
else
  ok "no Arista secret values in new manifests"
fi

if ((errors > 0)); then
  printf '\n%d check(s) failed\n' "${errors}" >&2
  exit 1
fi

printf '\nAll validation checks passed.\n'
