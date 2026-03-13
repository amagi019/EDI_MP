#!/bin/bash
# ============================================================
# 銀行マスタ自動更新スクリプト
# NAS上でcron実行し、zengin-code APIからBankMasterを更新
# cron登録例: 0 4 1 * * /share/Container/EDI_MP/scripts/update_bank_master.sh
# ============================================================
set -e

DOCKER_BIN="/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker"
CONTAINER_NAME="edi-mp-web"
DATE=$(date +%Y%m%d_%H%M%S)

echo "========================================="
echo " 銀行マスタ更新: ${DATE}"
echo "========================================="

${DOCKER_BIN} exec ${CONTAINER_NAME} python manage.py update_bank_master

echo ""
echo "✅ 銀行マスタ更新完了"
