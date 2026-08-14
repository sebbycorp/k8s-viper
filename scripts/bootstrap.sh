#!/usr/bin/env bash
# Bootstrap a single-node k3s cluster with Argo CD and the k8s-viper root Application.
# Usage (from a clone of this repo, on the target node):
#   sudo ./scripts/bootstrap.sh
# Optional env:
#   REPO_URL          default: https://github.com/sebbycorp/k8s-viper.git
#   REPO_REVISION     default: main
#   ARGOCD_VERSION    default: v3.5.0
#   INSTALL_K3S_SKIP  set to 1 to skip k3s install (cluster already present)

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/sebbycorp/k8s-viper.git}"
REPO_REVISION="${REPO_REVISION:-main}"
ARGOCD_VERSION="${ARGOCD_VERSION:-v3.5.0}"
INSTALL_K3S_SKIP="${INSTALL_K3S_SKIP:-0}"
ARGOCD_NAMESPACE="${ARGOCD_NAMESPACE:-argocd}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_APP_TEMPLATE="${REPO_ROOT}/bootstrap/argocd/root-application.yaml"
PROJECT_MANIFEST="${REPO_ROOT}/argocd/project.yaml"

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

wait_for_node() {
  local timeout="${1:-180}"
  local start
  start="$(date +%s)"
  log "Waiting for node to become Ready (timeout ${timeout}s)..."
  while true; do
    if kubectl get nodes --no-headers 2>/dev/null | grep -q ' Ready'; then
      log "Node is Ready."
      return 0
    fi
    if (( "$(date +%s)" - start > timeout )); then
      die "timed out waiting for node Ready"
    fi
    sleep 3
  done
}

wait_for_deployment() {
  local ns="$1"
  local name="$2"
  local timeout="${3:-300}"
  log "Waiting for deployment/${name} in ${ns} (timeout ${timeout}s)..."
  kubectl -n "${ns}" rollout status "deployment/${name}" --timeout="${timeout}s"
}

install_k3s() {
  if [[ "${INSTALL_K3S_SKIP}" == "1" ]]; then
    log "INSTALL_K3S_SKIP=1 — skipping k3s install."
    return 0
  fi
  if systemctl is-active --quiet k3s 2>/dev/null || command -v k3s >/dev/null 2>&1; then
    if kubectl get nodes >/dev/null 2>&1 || KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get nodes >/dev/null 2>&1; then
      log "k3s already present and reachable — skipping install."
      return 0
    fi
  fi
  need_cmd curl
  log "Installing k3s (single-node server, Traefik enabled)..."
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --write-kubeconfig-mode 644" sh -
}

configure_kubeconfig() {
  if [[ -f /etc/rancher/k3s/k3s.yaml ]]; then
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  fi
  if [[ -z "${KUBECONFIG:-}" && -f "${HOME}/.kube/config" ]]; then
    export KUBECONFIG="${HOME}/.kube/config"
  fi
  need_cmd kubectl
  kubectl cluster-info >/dev/null 2>&1 || die "kubectl cannot reach the cluster; set KUBECONFIG"
  log "Using KUBECONFIG=${KUBECONFIG:-<default>}"
}

install_argocd() {
  log "Ensuring namespace ${ARGOCD_NAMESPACE} exists..."
  kubectl create namespace "${ARGOCD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

  log "Installing Argo CD ${ARGOCD_VERSION} (server-side apply)..."
  kubectl apply -n "${ARGOCD_NAMESPACE}" --server-side --force-conflicts \
    -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"

  wait_for_deployment "${ARGOCD_NAMESPACE}" argocd-server 300
  # controller + repo-server are also required for sync
  wait_for_deployment "${ARGOCD_NAMESPACE}" argocd-repo-server 300
  wait_for_deployment "${ARGOCD_NAMESPACE}" argocd-applicationset-controller 300 || true

  # platform/headlamp uses kustomize helmCharts; repo-server needs --enable-helm.
  # Same key is GitOps-managed in platform/argocd-access/argocd-cm-kustomize.yaml.
  log "Enabling kustomize.buildOptions=--enable-helm on argocd-cm..."
  kubectl -n "${ARGOCD_NAMESPACE}" patch configmap argocd-cm --type merge \
    -p '{"data":{"kustomize.buildOptions":"--enable-helm"}}'
}

apply_project_and_root_app() {
  [[ -f "${ROOT_APP_TEMPLATE}" ]] || die "missing ${ROOT_APP_TEMPLATE} (run from a full clone of k8s-viper)"
  [[ -f "${PROJECT_MANIFEST}" ]] || die "missing ${PROJECT_MANIFEST}"

  local tmp
  tmp="$(mktemp)"
  # shellcheck disable=SC2016
  sed \
    -e "s|repoURL: https://github.com/sebbycorp/k8s-viper.git|repoURL: ${REPO_URL}|g" \
    -e "s|targetRevision: main|targetRevision: ${REPO_REVISION}|g" \
    "${ROOT_APP_TEMPLATE}" >"${tmp}"

  log "Applying AppProject viper..."
  # Allow bootstrap REPO_URL in project sourceRepos when forking
  local project_tmp
  project_tmp="$(mktemp)"
  sed \
    -e "s|https://github.com/sebbycorp/k8s-viper.git|${REPO_URL}|g" \
    "${PROJECT_MANIFEST}" >"${project_tmp}"
  kubectl apply -f "${project_tmp}"
  rm -f "${project_tmp}"

  log "Applying root Application (repo=${REPO_URL} revision=${REPO_REVISION})..."
  kubectl apply -f "${tmp}"
  rm -f "${tmp}"
}

print_next_steps() {
  local node_ip admin_pass_cmd
  node_ip="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)"
  if [[ -z "${node_ip}" ]]; then
    node_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi

  admin_pass_cmd="kubectl -n ${ARGOCD_NAMESPACE} get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo"

  cat <<EOF

========================================================================
 k8s-viper bootstrap complete
========================================================================

 Cluster front door (LAN):  http://${node_ip:-<node-ip>}/
 Demo host (after sync):    whoami.viper.local  -> add to /etc/hosts:
                            ${node_ip:-<node-ip>}  whoami.viper.local

 Platform UIs (after Argo syncs NodePorts — see docs/platform-ui-access.md):
   Headlamp:       http://${node_ip:-<node-ip>}:30080/
   Argo CD:        https://${node_ip:-<node-ip>}:30443/  (user: admin; self-signed)
   Vault UI:       http://${node_ip:-<node-ip>}:30200/  (after init+unseal)
   agentgateway:   http://${node_ip:-<node-ip>}:30100/  (OpenAI proxy)
   Langfuse:       http://${node_ip:-<node-ip>}:30300/

 Initial Argo CD admin password:
   ${admin_pass_cmd}

 Fallback Argo CD (port-forward):
   kubectl -n ${ARGOCD_NAMESPACE} port-forward svc/argocd-server 8080:443
   open https://localhost:8080  (user: admin)

 GitOps source:
   ${REPO_URL} @ ${REPO_REVISION}

 Next:
   1. Watch apps:  kubectl -n argocd get applications
   2. Init Vault:  see docs/vault-eso-setup.md
   3. Day-2:       merge to ${REPO_REVISION}; Argo reconciles

 KUBECONFIG:
   export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

========================================================================
EOF
}

main() {
  if [[ "$(id -u)" -ne 0 ]] && [[ "${INSTALL_K3S_SKIP}" != "1" ]]; then
    if ! systemctl is-active --quiet k3s 2>/dev/null; then
      die "run as root for k3s install (or set INSTALL_K3S_SKIP=1 if the cluster already exists)"
    fi
  fi

  install_k3s
  configure_kubeconfig
  wait_for_node 180
  install_argocd
  apply_project_and_root_app
  print_next_steps
}

main "$@"
