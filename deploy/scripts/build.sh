#!/usr/bin/env bash
# Build Gateway Docker image for ARM (Raspberry Pi 3B/4) on a developer machine.
# Requires: docker buildx, QEMU binfmt support
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE_NAME="arduino-gateway"
PLATFORM="linux/arm/v7"   # Change to linux/arm64 for RPi 5

echo "==> Setting up buildx builder..."
docker buildx inspect arduino-builder &>/dev/null \
  || docker buildx create --name arduino-builder --use
docker buildx use arduino-builder

echo "==> Building ${IMAGE_NAME} for ${PLATFORM}..."
docker buildx build \
  --platform "${PLATFORM}" \
  --file "${REPO_ROOT}/deploy/gateway/Dockerfile" \
  --output "type=docker,name=${IMAGE_NAME}:latest" \
  "${REPO_ROOT}"

echo "==> Saving image to /tmp/${IMAGE_NAME}.tar.gz..."
docker save "${IMAGE_NAME}:latest" | gzip > "/tmp/${IMAGE_NAME}.tar.gz"

echo "Done. Upload with: scp /tmp/${IMAGE_NAME}.tar.gz pi@<RPi-IP>:~/"
