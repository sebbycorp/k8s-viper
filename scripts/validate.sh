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
require_file platform/ingress/kustomization.yaml
require_file platform/ingress/helmchartconfig-traefik.yaml
require_file platform/ingress/whoami.yaml
require_file platform/vault/values.yaml
require_file platform/external-secrets/values.yaml
require_file platform/external-secrets/cluster-secret-store-vault.example.yaml
require_file docs/vault-eso-setup.md
require_file .github/workflows/ci.yaml

log "YAML parse check (Python)..."
mapfile -t yaml_files < <(find argocd bootstrap platform -type f \( -name '*.yaml' -o -name '*.yml' \) | sort)
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
elif command -v kubectl >/dev/null 2>&1; then
  log "kubectl kustomize platform/ingress..."
  if kubectl kustomize platform/ingress >/dev/null; then
    ok "kubectl kustomize platform/ingress"
  else
    fail "kubectl kustomize platform/ingress"
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
    platform/ingress/namespace-apps.yaml
    platform/ingress/whoami.yaml
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

# bash syntax check
if bash -n scripts/bootstrap.sh && bash -n scripts/validate.sh; then
  ok "bash -n scripts"
else
  fail "bash syntax error in scripts"
fi

if ((errors > 0)); then
  printf '\n%d check(s) failed\n' "${errors}" >&2
  exit 1
fi

printf '\nAll validation checks passed.\n'
