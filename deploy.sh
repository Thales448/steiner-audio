#!/bin/bash
# Package app/ into a tar.gz split across ConfigMaps (binaryData, <1MiB each) and roll the deployment.
set -euo pipefail; cd "$(dirname "$0")"
export KUBECONFIG=${KUBECONFIG:-/workspace/kubeconfig}
K() { for i in 1 2 3 4 5; do kubectl --request-timeout=30s "$@" && return 0; echo "retry $i: kubectl $*" >&2; sleep 4; done; return 1; }
W=$(mktemp -d); tar -C app --exclude=data/catalog.full.json -czf "$W/site.tgz" .
SHA=$(sha256sum "$W/site.tgz" | cut -c1-12); split -b 700000 -d -a 2 "$W/site.tgz" "$W/part-"
K apply -f k8s/00-namespace.yaml
MOUNTS=""; VOLS=""; n=0
for p in "$W"/part-*; do
  idx=$(basename "$p" | sed 's/part-//'); name="steiner-bundle-$idx"
  kubectl create configmap "$name" -n steiner --from-file="part-$((10#$idx))=$p" --dry-run=client -o yaml > "$W/cm-$idx.yaml"
  K apply --server-side --force-conflicts -f "$W/cm-$idx.yaml" >/dev/null
  MOUNTS="$MOUNTS{name: b$idx, mountPath: /bundle/$idx}, "; VOLS="$VOLS      - {name: b$idx, configMap: {name: $name}}\n"; n=$((n+1))
done
echo "bundle $SHA in $n configmaps"
sed -e "s/BUNDLE_SHA/$SHA/" -e "s|BUNDLE_MOUNTS|${MOUNTS%, }|" -e "s|      BUNDLE_VOLUMES|$VOLS|" k8s/03-deployment.yaml > "$W/deploy.yaml"
for f in k8s/01-nginx-conf.yaml "$W/deploy.yaml" k8s/04-service.yaml k8s/05-certificate.yaml k8s/06-ingress.yaml; do K apply -f "$f"; done
K -n steiner rollout status deploy/steiner --timeout=180s
