#!/bin/bash
# EDI_MP NAS用エントリポイントスクリプト
set -e

# メディアディレクトリの作成
mkdir -p /app/media

# 引数がある場合はそのまま実行
exec "$@"
