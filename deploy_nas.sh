#!/bin/bash
# ============================================================
# EDI_MP NASデプロイスクリプト
# ローカルからNASへプロジェクトを転送し、Dockerコンテナを起動する
# ============================================================
set -e

# 設定（環境変数 or デフォルト値）
NAS_HOST="${NAS_HOST:-192.168.50.198}"
NAS_USER="${NAS_USER:-yutaka}"
NAS_DIR="${NAS_DIR:-/share/Container/EDI_MP}"
COMPOSE_FILE="docker-compose.nas.yml"
DOCKER_BIN="/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker"
# docker-compose は個別コンポーネントを呼び出す
DOCKER_COMPOSE="$DOCKER_BIN compose"

# カラー出力
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} EDI_MP NASデプロイ${NC}"
echo -e "${GREEN}========================================${NC}"

# プロジェクトルートに移動
cd "$(dirname "$0")"

# 1. NAS上にディレクトリ作成
echo -e "\n${YELLOW}[1/4] NAS上にディレクトリを作成中...${NC}"
ssh ${NAS_USER}@${NAS_HOST} "mkdir -p ${NAS_DIR}"

# 2. ファイル転送（rsync）
echo -e "\n${YELLOW}[2/4] プロジェクトファイルをNASに転送中...${NC}"
rsync -avz --progress --delete \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='db.sqlite3' \
    --exclude='media/' \
    --exclude='staticfiles/' \
    --exclude='.env' \
    --exclude='node_modules' \
    --exclude='.gemini' \
    --exclude='.agent' \
    --exclude='*.pdf' \
    --exclude='設計書/' \
    --exclude='credentials/' \
    ./ ${NAS_USER}@${NAS_HOST}:${NAS_DIR}/

# 3. .env.nas を .env.nas としてコピー（NAS上では .env.nas を使用）
echo -e "\n${YELLOW}[3/4] 環境変数ファイルを確認中...${NC}"
ssh ${NAS_USER}@${NAS_HOST} "
    if [ ! -f ${NAS_DIR}/.env.nas ]; then
        echo '⚠️  .env.nas が見つかりません。手動で作成してください。'
        exit 1
    fi
"

# 4. Docker Compose でビルド＆起動
echo -e "\n${YELLOW}[4/4] Dockerコンテナをビルド・起動中...${NC}"
ssh ${NAS_USER}@${NAS_HOST} "
    cd ${NAS_DIR}
    ${DOCKER_COMPOSE} -f ${COMPOSE_FILE} up -d --build
"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN} デプロイ完了！${NC}"
echo -e "${GREEN} アクセスURL: http://${NAS_HOST}:8090${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${YELLOW}※ 印影画像は管理画面の「会社情報」から登録してください。${NC}"
