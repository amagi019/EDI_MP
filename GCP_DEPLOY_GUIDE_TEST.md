# GCPテスト環境(edi-sophia-test) 構築・デプロイマニュアル

このドキュメントは、プロジェクトID `edi-sophia-test` を使用して、メール送信を抑制したテスト環境を構築する手順を説明します。

## 1. プロジェクトの準備

```bash
# プロジェクトの作成（未作成の場合）
gcloud projects create edi-sophia-test

# プロジェクトの設定
gcloud config set project edi-sophia-test

# 必要なAPIの有効化
gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com
```

## 2. データベース(Cloud SQL)の構築

コストを抑えるため、最小スペック `db-f1-micro` を使用します。

```bash
# インスタンス作成
gcloud sql instances create edi-db-test \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=asia-northeast1

# データベース作成
gcloud sql databases create edidb --instance=edi-db-test
```

## 3. 秘密情報の登録 (Secret Manager)

メール送信を抑制（コンソール出力に限定）するため、`EMAIL_BACKEND` を明示的に設定します。

```bash
# SECRET_KEY の登録（テスト用の任意の文字列）
echo -n "django-insecure-test-key-replace-me" | gcloud secrets create SECRET_KEY --data-file=-

# EMAIL_BACKEND の登録（重要：これによりメール送信が抑制されます）
echo -n "django.core.mail.backends.console.EmailBackend" | gcloud secrets create EMAIL_BACKEND --data-file=-

# DATABASE_URL の登録
# [USER], [PASSWORD] は適切に設定してください
echo -n "postgres://postgres:[PASSWORD]@/edidb?host=/cloudsql/edi-sophia-test:asia-northeast1:edi-db-test" | \
    gcloud secrets create DATABASE_URL --data-file=-
```

## 4. デプロイの実行 (Cloud Run)

```bash
gcloud run deploy edi-system-test \
    --source . \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --set-secrets="SECRET_KEY=SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest,EMAIL_BACKEND=EMAIL_BACKEND:latest" \
    --set-env-vars="DEBUG=False,ALLOWED_HOSTS=*"
```

## 5. 動作確認

### ログによるメール送信の確認
注文承認などのアクションを実行した後、以下のコマンドでログを確認してください。メールの内容がログに出力されていれば、設定は正しく機能しています（実際のメールは送信されません）。

## 6. トラブルシューティング（403 Forbidden が出る場合）

組織ポリシーにより、ブラウザで直接 URL を開いてもアクセスできません。

```bash
# 認証プロキシを起動（このコマンドを動かし続ける）
gcloud run services proxy edi-system-test --region=asia-northeast1

# ブラウザで以下にアクセス
http://localhost:8080
```

`gcloud proxy` のインストールでエラーが出る場合は、Homebrew 版ではなく **公式インストーラー (curl https://sdk.cloud.google.com | bash)** を使用して gcloud を再インストールしてください。
