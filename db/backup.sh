#!/bin/sh
# 資料庫自動備份：啟動時先備份一次，之後每 24 小時一次，只保留最近 KEEP_DAYS 天。
# 由 docker-compose 的 backup 服務執行（PGHOST / PGUSER / PGPASSWORD / PGDATABASE 由環境變數提供）。
# ONCE=1 只備份一次就結束（deploy.sh 部署前備份、測試用）。
#
# 還原（會覆蓋目前的資料）：
#   docker compose exec -T db pg_restore -U stockuser -d stockdb --clean --if-exists < backups/<檔名>.dump
set -eu
DIR=${BACKUP_DIR:-/backups}
KEEP_DAYS=${KEEP_DAYS:-14}
PREFIX=${BACKUP_PREFIX:-daily}
mkdir -p "$DIR"

while true; do
  file="$DIR/$PGDATABASE-$PREFIX-$(date +%Y%m%d-%H%M%S).dump"
  if pg_dump -Fc -f "$file.tmp" && mv "$file.tmp" "$file"; then
    echo "[backup] $(date '+%F %T') 已備份 $file（$(du -h "$file" | cut -f1)）"
  else
    rm -f "$file.tmp"
    echo "[backup] $(date '+%F %T') 備份失敗" >&2
  fi
  find "$DIR" -name "$PGDATABASE-$PREFIX-*.dump" -mtime +"$KEEP_DAYS" -print -delete
  [ "${ONCE:-}" = 1 ] && exit 0
  sleep 86400
done
