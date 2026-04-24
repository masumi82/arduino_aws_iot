#!/usr/bin/env bash
# Build Gateway Docker image for ARM (Raspberry Pi 3B/4) on a developer machine.
# Requires: docker buildx, QEMU binfmt support
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE_NAME="arduino-gateway"
PLATFORM="linux/arm64"   # RPi 4/5 (aarch64)

echo "==> Setting up buildx builder..."
docker buildx inspect arduino-builder &>/dev/null \
  || docker buildx create --name arduino-builder --driver docker-container --use
docker buildx use arduino-builder

echo "==> Building ${IMAGE_NAME} for ${PLATFORM}..."
docker buildx build \
  --platform "${PLATFORM}" \
  --file "${REPO_ROOT}/deploy/gateway/Dockerfile" \
  --load \
  --tag "${IMAGE_NAME}:latest" \
  "${REPO_ROOT}"

echo "==> Saving image to /tmp/${IMAGE_NAME}.tar.gz..."
docker save "${IMAGE_NAME}:latest" | gzip > "/tmp/${IMAGE_NAME}.tar.gz"

echo "Done. Upload with: scp /tmp/${IMAGE_NAME}.tar.gz pi@<RPi-IP>:~/"
