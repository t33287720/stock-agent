#!/bin/bash
# 部署腳本
# 用法: ./deploy.sh [service]  (不給 service 代表全部)
#
# 注意：務必用 `docker compose`（v2 plugin）而非 `docker-compose`（v1 standalone）。
# v1 是已停止維護的舊版工具，recreate 容器時會讀取 image 的 ContainerConfig 欄位，
# 但新版 Docker Engine（containerd image store）已經不會產生這個欄位，
# 一 recreate 就會丟 KeyError: 'ContainerConfig'，把正在跑的容器停掉又建立失敗。
set -e
cd "$(dirname "$0")"

SERVICE=${1:-""}

if [ -n "$SERVICE" ]; then
  docker compose up -d --build "$SERVICE"
else
  docker compose up -d --build
fi
