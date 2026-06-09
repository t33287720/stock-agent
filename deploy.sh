#!/bin/bash
# 部署腳本 — 解決 docker-compose v1 的 ContainerConfig bug
# 用法: ./deploy.sh [service]  (不給 service 代表全部)
set -e
cd "$(dirname "$0")"

SERVICE=${1:-""}

# 清除舊的 hash-prefix 殭屍容器（docker-compose v1 + Docker 29.x 的相容問題）
docker ps -a --filter "label=com.docker.compose.project=stock" --format "{{.Names}}" \
  | grep "^[0-9a-f]*_" \
  | xargs -r docker rm -f 2>/dev/null && true

if [ -n "$SERVICE" ]; then
  docker-compose up -d --build "$SERVICE"
else
  docker-compose up -d --build
fi
