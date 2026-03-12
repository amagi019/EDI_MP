#!/bin/bash
# EDI_MP NAS用エントリポイントスクリプト
set -e

# メディアディレクトリの作成
mkdir -p /app/media

# マイグレーション自動適用（本番デプロイ時にスキーマを自動更新）
echo "Running database migrations..."
python manage.py migrate --noinput
echo "Migrations complete."

# 引数がある場合はそのまま実行
exec "$@"
