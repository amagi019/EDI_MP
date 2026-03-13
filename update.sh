#!/bin/bash
# ============================================
# EDI_MP リモートアップデートスクリプト
# ============================================
# 使い方: bash update.sh
#
# Tailscale経由でSSH接続後、このスクリプトを実行するだけで
# アプリケーションが最新版に更新されます。
# ============================================

set -e

echo ""
echo "========================================"
echo "  EDI_MP アップデートツール"
echo "========================================"
echo ""

# 現在のバージョン表示
if [ -f "VERSION" ]; then
    CURRENT=$(cat VERSION)
    echo "現在のバージョン: $CURRENT"
fi

# --- 1. バックアップ ---
echo "📦 データベースをバックアップしています..."
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# SQLiteの場合
if [ -f "db.sqlite3" ]; then
    cp db.sqlite3 "$BACKUP_DIR/"
    echo "✅ db.sqlite3 → $BACKUP_DIR/"
fi

# mediaファイル
if [ -d "media" ]; then
    cp -r media "$BACKUP_DIR/"
    echo "✅ media/ → $BACKUP_DIR/"
fi

# .envファイル
if [ -f ".env.nas" ]; then
    cp .env.nas "$BACKUP_DIR/"
    echo "✅ .env.nas → $BACKUP_DIR/"
fi

echo ""

# --- 2. コード更新 ---
echo "📥 最新コードを取得しています..."
if [ -d ".git" ]; then
    git stash 2>/dev/null || true
    git pull origin main
    echo "✅ git pull 完了"
else
    echo "⚠️  Gitリポジトリではありません。手動でコードを転送してください。"
    echo "   続行しますか？ (y/N)"
    read -r cont
    if [ "$cont" != "y" ] && [ "$cont" != "Y" ]; then
        echo "中断しました。"
        exit 0
    fi
fi

echo ""

# --- 3. Dockerコンテナ再ビルド ---
echo "🐳 コンテナを更新しています..."
docker compose down
docker compose up -d --build

echo ""
echo "⏳ コンテナの起動を待っています..."
sleep 5

# --- 4. データベースマイグレーション ---
echo "🗄️  データベースを更新しています..."
docker compose exec -T web python manage.py migrate --noinput

# --- 5. 静的ファイル更新 ---
echo "📁 静的ファイルを更新しています..."
docker compose exec -T web python manage.py collectstatic --noinput 2>/dev/null || true

# --- 6. バージョン表示 ---
if [ -f "VERSION" ]; then
    NEW_VERSION=$(cat VERSION)
    echo ""
    echo "========================================"
    echo "  ✅ アップデート完了！"
    echo "========================================"
    echo ""
    echo "  $CURRENT → $NEW_VERSION"
    echo ""
    echo "  バックアップ: $BACKUP_DIR/"
    echo "========================================"
else
    echo ""
    echo "========================================"
    echo "  ✅ アップデート完了！"
    echo "========================================"
    echo ""
    echo "  バックアップ: $BACKUP_DIR/"
    echo "========================================"
fi
