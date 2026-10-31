#!/usr/bin/env bash
# Reproducible Ubuntu 22.04 build plus clean-container packaged acceptance.
# Uses the local Docker daemon and retains the caller's registry/proxy settings.
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$studio_root"
studio_docker=(env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock)
studio_ca="${STUDIO_BUILD_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
if [ ! -r "$studio_ca" ]; then
    printf '%s\n' 'Set STUDIO_BUILD_CA_BUNDLE to your trusted combined public CA bundle.' >&2
    exit 1
fi
studio_commit="$(git rev-parse HEAD)"
if ! git diff --quiet HEAD; then studio_commit="${studio_commit}-dirty"; fi
"${studio_docker[@]}" build --secret "id=proxy_ca,src=$studio_ca" \
    --build-arg "STUDIO_BUILD_COMMIT=$studio_commit" \
    -f packaging/Dockerfile.ubuntu22 -t android-automation-studio-ubuntu22:local .
studio_container="$("${studio_docker[@]}" create android-automation-studio-ubuntu22:local)"
trap '"${studio_docker[@]}" rm "$studio_container" >/dev/null' EXIT
mkdir -p dist
for studio_file in AndroidAutomationStudio-ubuntu-x86_64.tar.gz \
    AndroidAutomationStudio-ubuntu-x86_64.tar.gz.sha256 \
    linux-frozen-smoke.json ubuntu22-clean-runtime-smoke.json ubuntu22-runtime-info.txt; do
    "${studio_docker[@]}" cp "$studio_container:/artifacts/$studio_file" "dist/$studio_file"
done
printf '%s\n' "Built and tested artifact: $studio_root/dist/AndroidAutomationStudio-ubuntu-x86_64.tar.gz"
