#!/bin/bash
# InkWild — daily Postgres backup.
#
# Runs inside the `backup` service container (postgres:16-alpine) which shares
# the compose default network with `db`. Dumps the `inkwild` database to
# /backups/inkwild-YYYY-MM-DD.sql.gz and prunes archives older than 7 days.
#
# 恢复 (restore) — from the host, with the stack running:
#   gunzip < inkwild-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U postgres -d inkwild
#
# Or directly from inside a container:
#   gunzip < /backups/inkwild-YYYY-MM-DD.sql.gz | psql -h db -U postgres -d inkwild
set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DB_HOST="${PGHOST:-db}"
DB_USER="${PGUSER:-postgres}"
DB_NAME="${PGDATABASE:-inkwild}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "$BACKUP_DIR"

stamp="$(date +%F)"
target="$BACKUP_DIR/inkwild-$stamp.sql.gz"

echo "[backup] $(date -Iseconds) dumping $DB_NAME from $DB_HOST -> $target"
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$target"

echo "[backup] pruning archives older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -name 'inkwild-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "[backup] done: $target ($(du -h "$target" | cut -f1))"
