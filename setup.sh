#!/bin/bash
# ============================================
# EDI_MP ワンクリックセットアップスクリプト
# ============================================
# 使い方: bash setup.sh
# 
# このスクリプトは対話形式で必要な情報を聞きながら
# アプリケーションのセットアップを自動で行います。
# ============================================

set -e

echo ""
echo "========================================"
echo "  EDI_MP セットアップツール"
echo "========================================"
echo ""

# --- 1. 環境チェック ---
echo "🔍 環境を確認しています..."

if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません。"
    echo "   NASの管理画面からDockerをインストールしてください。"
    exit 1
fi

if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Composeが見つかりません。"
    exit 1
fi

echo "✅ Docker: $(docker --version)"
echo ""

# --- 2. .envファイルの作成 ---
ENV_FILE=".env.nas"

if [ -f "$ENV_FILE" ]; then
    echo "⚠️  $ENV_FILE は既に存在します。上書きしますか？ (y/N)"
    read -r overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
        echo "既存の $ENV_FILE を使用します。"
    else
        rm "$ENV_FILE"
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "📝 環境変数を設定します。"
    echo "   以下の質問に答えてください。"
    echo ""

    # SECRET_KEY自動生成
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))" 2>/dev/null || openssl rand -base64 50 | head -c 50)

    # NASのIPアドレス取得
    NAS_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

    echo "📧 メール差出人アドレスを入力してください（例: info@your-company.com）:"
    read -r FROM_EMAIL

    echo "📧 SMTPユーザー（Gmailアドレス）を入力してください:"
    read -r SMTP_USER

    echo "🔑 SMTPパスワード（Gmailアプリパスワード）を入力してください:"
    read -rs SMTP_PASS
    echo ""

    cat > "$ENV_FILE" << EOF
DJANGO_SETTINGS_MODULE=EDI_MP.settings.production
SECRET_KEY=${SECRET_KEY}
ALLOWED_HOSTS=localhost,127.0.0.1,${NAS_IP}
CSRF_TRUSTED_ORIGINS=http://${NAS_IP}:8090
DEFAULT_FROM_EMAIL=${FROM_EMAIL}
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=${SMTP_USER}
EMAIL_HOST_PASSWORD=${SMTP_PASS}
EOF

    echo "✅ $ENV_FILE を作成しました。"
    echo ""
fi

# --- 3. Dockerビルド＆起動 ---
echo "🐳 Dockerコンテナをビルドしています..."
docker compose up -d --build

echo ""
echo "⏳ コンテナの起動を待っています..."
sleep 5

# --- 4. データベース初期化 ---
echo "🗄️  データベースを初期化しています..."
docker compose exec -T web python manage.py migrate --noinput

# --- 5. 管理者ユーザー作成 ---
echo ""
echo "👤 管理者ユーザーを作成します。"
echo "   ユーザー名を入力してください（例: admin）:"
read -r ADMIN_USER

echo "   メールアドレスを入力してください:"
read -r ADMIN_EMAIL

echo "   パスワードを入力してください:"
read -rs ADMIN_PASS
echo ""

docker compose exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='${ADMIN_USER}').exists():
    User.objects.create_superuser('${ADMIN_USER}', '${ADMIN_EMAIL}', '${ADMIN_PASS}')
    print('✅ 管理者ユーザーを作成しました。')
else:
    print('⚠️  ユーザー ${ADMIN_USER} は既に存在します。')
"

# --- 6. 完了 ---
NAS_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo "========================================"
echo "  ✅ セットアップ完了！"
echo "========================================"
echo ""
echo "  アプリURL:  http://${NAS_IP}:8090/"
echo "  管理画面:   http://${NAS_IP}:8090/admin/"
echo ""
echo "  次のステップ:"
echo "  1. ブラウザで管理画面を開く"
echo "  2. 会社情報（CompanyInfo）を登録する"
echo "  3. 印影画像をアップロードする"
echo ""
echo "========================================"
