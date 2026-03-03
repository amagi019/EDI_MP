#!/bin/bash
# ============================================================
# EDI_MP NASバックアップスクリプト
# NAS上で実行し、PostgreSQLとmediaのバックアップを取得
# cron登録例: 0 3 * * * /share/Container/EDI_MP/scripts/backup_nas.sh
# ============================================================
set -e

# 設定
PROJECT_DIR="/share/Container/EDI_MP"
BACKUP_DIR="/share/Container/EDI_MP/backups"
DOCKER_BIN="/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker"
CONTAINER_NAME="edi-mp-db"
DB_USER="edi_user"
DB_NAME="edi_mp"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

echo "========================================="
echo " EDI_MP バックアップ: ${DATE}"
echo "========================================="

# バックアップディレクトリ作成
mkdir -p "${BACKUP_DIR}"

# 1. PostgreSQL バックアップ（pg_dump）
echo "[1/3] PostgreSQLバックアップ中..."
${DOCKER_BIN} exec -t ${CONTAINER_NAME} pg_dump -U ${DB_USER} ${DB_NAME} \
    > "${BACKUP_DIR}/db_${DATE}.sql"
echo "  → ${BACKUP_DIR}/db_${DATE}.sql"

# 2. メディアファイルバックアップ
echo "[2/3] メディアファイルバックアップ中..."
MEDIA_BACKUP="${BACKUP_DIR}/media_${DATE}.tar.gz"
${DOCKER_BIN} exec -t edi-mp-web tar czf - /app/media 2>/dev/null \
    > "${MEDIA_BACKUP}" || echo "  → メディアファイルなし（スキップ）"
if [ -s "${MEDIA_BACKUP}" ]; then
    echo "  → ${MEDIA_BACKUP}"
else
    rm -f "${MEDIA_BACKUP}"
fi

# 3. 古いバックアップの削除
echo "[3/3] ${RETENTION_DAYS}日以上前のバックアップを削除中..."
find "${BACKUP_DIR}" -name "db_*.sql" -mtime +${RETENTION_DAYS} -delete 2>/dev/null
find "${BACKUP_DIR}" -name "media_*.tar.gz" -mtime +${RETENTION_DAYS} -delete 2>/dev/null

echo ""
echo "✅ バックアップ完了"
echo "   保存先: ${BACKUP_DIR}"
ls -lh "${BACKUP_DIR}"/db_${DATE}.* "${BACKUP_DIR}"/media_${DATE}.* 2>/dev/null
