# GCPデプロイ & 外部結合テスト実施マニュアル

本ドキュメントでは、準備したDockerfileと設定を用いて、GCP環境へのデプロイおよび外部システムとの連携テストを実施する手順を説明します。

## 1. GCP環境の初期設定
ターミナルで以下のコマンドを順に実行してください。
1. Homebrewでインストール
brew install --cask google-cloud-sdk
2. パスの設定（自動で反映されない場合）
source "$(brew --prefix)/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/path.zsh.inc"
source "$(brew --prefix)/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/completion.zsh.inc"
3. 初期化
最後に、Googleアカウントとの連携とプロジェクト設定を行います。
gcloud init
ブラウザが開くので、使用するGoogleアカウントでサインインし、認証を完了させてください。その後、ターミナルに戻り、プロジェクトの選択やゾーンの設定など、対話形式で初期設定を完了させます。 
ブラウザでログイン: 使用したいGoogleアカウントを選択し、Google Cloud SDKへの権限を「許可」します。
プロジェクトの選択: ターミナルに戻ると、既存のプロジェクト一覧が表示されます。使用するプロジェクトの番号を入力するか、新しく作成します。
    Create a nuw projectを選択し、プロジェクト名を入力します。
2. 新しくプロジェクトを作成する場合
まだプロジェクトがない、あるいはこの場で新しく作りたい場合は、自分で決めた任意のID を入力してください Google Workspace Guides。 
命名ルール: 6〜30文字、小文字の英数字とハイフンのみ、先頭は小文字 Google Cloud Documentation。



### プロジェクトの設定
```bash
# GCPへのログイン
gcloud auth login

# プロジェクトの作成（既存の場合は設定のみ）
gcloud projects create [PROJECT_ID]　　gcloud projects create edi-sophia
gcloud config set project [PROJECT_ID]　　gcloud config set project edi-sophia

# 必要なAPIの有効化
# Storage API の有効化
gcloud services enable storage-component.googleapis.com
# Cloud Run、Cloud SQL、Secret Manager、Cloud Build の有効化

gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com
```

### データベース(Cloud SQL)の作成
```bash
gcloud sql instances create edi-db-instance \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=asia-northeast1

gcloud sql databases create edidb --instance=edi-db-instance
```

## 2. 秘密情報の登録 (Secret Manager)
本番環境で必要な設定を登録します。

```bash
# SECRET_KEY の登録
echo -n "your-secret-key" | gcloud secrets create SECRET_KEY --data-file=-

# DATABASE_URL の登録
# 形式: postgres://USER:PASSWORD@/DB_NAME?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME
echo -n "postgres://postgres:password@/edidb?host=/cloudsql/[PROJECT_ID]:asia-northeast1:edi-db-instance" | \
    gcloud secrets create DATABASE_URL --data-file=-
```

## 3. デプロイの実行 (Cloud Run)
Cloud Buildを使用してイメージをビルドし、Cloud Runにデプロイします。

```bash
# ビルドとデプロイを一括実行
gcloud run deploy edi-system \
    --source . \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --set-secrets="SECRET_KEY=SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest" \
    --set-env-vars="DEBUG=False,ALLOWED_HOSTS=*"
```

## 4. 外部結合テストの実施

### ステップ1: Webhook URLの登録
デプロイ後に発行される URL（例: `https://edi-system-xxxx.a.run.app`）を、外部電子署名サービス等のWebhook設定画面に登録してください。
- エンドポイント例: `https://[YOUR-URL]/orders/webhooks/`

### ステップ2: 導通テスト
1. システムにログインし、テスト用の注文書を作成。
2. 「正式発行」ボタンを押し、外部サービスへのリクエストが飛ぶか確認。
3. 外部サービス側で署名を行い、Webhook経由でステータスが「完了」になるか確認。

## 5. トラブルシューティング
ログの確認コマンド：
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=edi-system" --limit 50
```
