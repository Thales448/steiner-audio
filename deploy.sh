#!/bin/bash
# Package app/ and the Ask API into tar.gz files split across ConfigMaps, then roll both deployments.
# The static site stays on /. The API is steiner-api, ingress path /api (see k8s/06-ingress.yaml).
# No image registry is required: the API runs from python:3.12-alpine with the index mounted in.
set -euo pipefail
cd "$(dirname "$0")"
export KUBECONFIG=${KUBECONFIG:-/workspace/kubeconfig}
K() { for i in 1 2 3 4 5; do kubectl --request-timeout=30s "$@" && return 0; echo "retry $i: kubectl $*" >&2; sleep 4; done; return 1; }

if [[ ! -f research/index.json || ! -f research/passages.jsonl ]]; then
  echo "missing research/index.json — run: python3 research/build_research_index.py" >&2
  exit 1
fi

# $1 configmap prefix, $2 deployment template, $3 directory that already contains site.tgz
bundle_deploy() {
  local prefix="$1" template="$2" work="$3"
  local sha mounts vols n idx name p
  sha=$(sha256sum "$work/site.tgz" | cut -c1-12)
  split -b 700000 -d -a 2 "$work/site.tgz" "$work/part-"
  mounts=""; vols=""; n=0
  for p in "$work"/part-*; do
    idx=$(basename "$p" | sed 's/part-//')
    name="${prefix}-$idx"
    kubectl create configmap "$name" -n steiner --from-file="part-$((10#$idx))=$p" --dry-run=client -o yaml > "$work/cm-$idx.yaml"
    K apply --server-side --force-conflicts -f "$work/cm-$idx.yaml" >/dev/null
    mounts="$mounts{name: b$idx, mountPath: /bundle/$idx}, "
    vols="$vols      - {name: b$idx, configMap: {name: $name}}\n"
    n=$((n+1))
  done
  echo "bundle $prefix $sha in $n configmaps"
  sed -e "s/BUNDLE_SHA/$sha/" -e "s|BUNDLE_MOUNTS|${mounts%, }|" -e "s|      BUNDLE_VOLUMES|$vols|" "$template" > "$work/deploy.yaml"
  K apply -f "$work/deploy.yaml"
}

K apply -f k8s/00-namespace.yaml
K apply -f k8s/01-nginx-conf.yaml

W=$(mktemp -d)
tar -C app --exclude=data/catalog.full.json -czf "$W/site.tgz" .
bundle_deploy steiner-bundle k8s/03-deployment.yaml "$W"
K apply -f k8s/04-service.yaml
K apply -f k8s/05-certificate.yaml

A=$(mktemp -d)
mkdir -p "$A/root/api" "$A/root/research"
cp api/server.py api/retrieve.py "$A/root/api/"
cp research/index.json research/passages.jsonl "$A/root/research/"
tar -C "$A/root" -czf "$A/site.tgz" .
bundle_deploy steiner-api-bundle k8s/07-api-deployment.yaml "$A"
K apply -f k8s/08-api-service.yaml
K apply -f k8s/06-ingress.yaml

K -n steiner rollout status deploy/steiner --timeout=180s
K -n steiner rollout status deploy/steiner-api --timeout=180s
