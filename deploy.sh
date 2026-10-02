#!/bin/bash
# 部署腳本：部署前先備份資料庫，再重建並啟動容器
# 用法: ./deploy.sh [service]  (不給 service 代表全部)
#
# 注意：務必用 `docker compose`（v2 plugin）而非 `docker-compose`（v1 standalone）。
# v1 是已停止維護的舊版工具，recreate 容器時會讀取 image 的 ContainerConfig 欄位，
# 但新版 Docker Engine（containerd image store）已經不會產生這個欄位，
# 一 recreate 就會丟 KeyError: 'ContainerConfig'，把正在跑的容器停掉又建立失敗。
set -e
cd "$(dirname "$0")"

SERVICE=${1:-""}

# SearXNG 的密鑰改由 .env 提供（repo 是公開的）；沒設定的話 docker compose 會直接拒絕啟動
if ! grep -q '^SEARXNG_SECRET=..' .env 2>/dev/null; then
  echo "請先在 .env 加上 SearXNG 密鑰，例如：" >&2
  echo "  echo \"SEARXNG_SECRET=\$(openssl rand -hex 32)\" >> .env" >&2
  exit 1
fi

# 資料庫已經在跑的話，部署前先備份一份（backups/*-predeploy-*.dump）
if docker compose ps --status running --services 2>/dev/null | grep -qx db; then
  docker compose run --rm -e ONCE=1 -e BACKUP_PREFIX=predeploy backup
fi

if [ -n "$SERVICE" ]; then
  docker compose up -d --build "$SERVICE"
else
  docker compose up -d --build
fi
