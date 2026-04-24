#!/usr/bin/env bash
# Deploy Gateway to Raspberry Pi.
# Usage: ./deploy.sh <RPi-IP>
set -euo pipefail

RPI_HOST="${1:?Usage: $0 <RPi-IP>}"
RPI_USER="${RPI_USER:-masumi}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE_NAME="arduino-gateway"

echo "==> Transferring image to ${RPI_USER}@${RPI_HOST}..."
scp "/tmp/${IMAGE_NAME}.tar.gz" "${RPI_USER}@${RPI_HOST}:~/"

echo "==> Loading image on RPi..."
ssh "${RPI_USER}@${RPI_HOST}" "docker load < ~/${IMAGE_NAME}.tar.gz"

echo "==> Transferring deploy directory..."
rsync -av --exclude='.env' "${REPO_ROOT}/deploy/" "${RPI_USER}@${RPI_HOST}:~/deploy/"

echo "==> Transferring web directory..."
rsync -av "${REPO_ROOT}/web/" "${RPI_USER}@${RPI_HOST}:~/web/"

echo "==> Restarting containers..."
ssh "${RPI_USER}@${RPI_HOST}" \
  "cd ~/deploy && docker compose up -d --remove-orphans"

echo "==> Done. Dashboard: http://${RPI_HOST}:8080"
