#!/bin/bash
# EDI-MP 開発サーバー起動スクリプト
set -e

# プロジェクトのルートディレクトリに移動
cd "$(dirname "$0")"

# 仮想環境の作成（初回のみ）
if [ ! -d ".venv" ]; then
    echo "🔧 仮想環境を作成中..."
    python3 -m venv .venv
fi

# 仮想環境の有効化
echo "🔄 仮想環境を有効化中..."
source .venv/bin/activate

# 依存パッケージのインストール
echo "📦 依存パッケージをインストール中..."
pip install -q -r requirements.txt

# マイグレーションの実行
echo "🗄️ データベースマイグレーションを実行中..."
python manage.py migrate --run-syncdb

# 静的ファイルの収集
echo "📁 静的ファイルを収集中..."
python manage.py collectstatic --noinput

# 開発サーバーの起動
echo ""
echo "✅ 開発サーバーを起動します"
echo "   フロントエンド: http://127.0.0.1:8000/"
echo "   管理者画面:     http://127.0.0.1:8000/admin/"
echo ""
python manage.py runserver
