# GCPテスト環境構築およびメール送信防止設定の完了報告

GCPプロジェクト `edi-sophia-test` を使用したテスト環境の構築準備と、安全なテスト運用のためのメール送信防止設定が完了しました。

## 実施内容

### 1. アプリケーション設定の修正
`settings.py` を変更し、メール送信バックエンドを環境変数 `EMAIL_BACKEND` で切り替えられるようにしました。
- **防止策**: 環境変数が指定されない場合のデフォルトを `console.EmailBackend`（コンソール出力）に設定しました。これにより、意図せず実際のメールが送信されるリスクを排除しています。
- **修正ファイル**: [settings.py](file:///Users/yutaka/workspace/EDI_MP_1/EDI_MP/EDI_MP/settings.py)

### 2. テスト環境専用デプロイガイドの作成
プロジェクトID `edi-sophia-test` に特化し、Secret Manager でのメール抑制設定手順を含むマニュアルを新規作成しました。
- **作成ファイル**: [GCP_DEPLOY_GUIDE_TEST.md](file:///Users/yutaka/workspace/EDI_MP_1/EDI_MP/GCP_DEPLOY_GUIDE_TEST.md)

## 環境構築結果

GCPプロジェクト `edi-sophia-test` へのすべてのデプロイおよび設定工程が完了しました。

### 1. アプリケーションアクセス方法
現在、ブラウザで URL を開くと **403 Forbidden** となります。これは組織ポリシーによるアクセス制限です。
以下の手順で認証プロキシを起動してアクセスしてください。

#### `gcloud proxy` が動かない場合の対処法
Homebrew 版の gcloud はコンポーネント管理に制限があるため、以下のコマンドで公式版への移行を推奨します。
```bash
curl https://sdk.cloud.google.com | bash
```
インストール後、再ログイン (`gcloud auth login`) して以下のコマンドを実行してください。
```bash
gcloud run services proxy edi-system-test --region=asia-northeast1 --project=edi-sophia-test
```
実行後、ブラウザで **[http://localhost:8080](http://localhost:8080)** を開くとログイン画面が表示されます。

### 2. ログイン情報（テスト用）
- **ユーザーID**: `admin`
- **パスワード**: `password123`

### 3. 対応済み設定
- **データベース**: Cloud SQL (PostgreSQL 15) を新規作成し、マイグレーション（テーブル作成）を完了しました。
- **秘密情報**: Secret Manager に `SECRET_KEY`, `DATABASE_URL`, `EMAIL_BACKEND` を登録済みです。
- **メール送信抑制**: `EMAIL_BACKEND` に `console.EmailBackend` を設定しており、実際のメールは送信されず、すべて Cloud Run のログに出力されます。

### 4. トラブルシューティング済み
- **500 Internal Server Error**: 以下の2点を修正しました。
  1. **静的ファイルの集約**: `DEBUG=False` 時の WhiteNoise 実行に必要な `collectstatic` を Dockerfile に追加。
  2. **DB接続設定**: Cloud Run サービス側の設定に Cloud SQL インスタンスへの接続（Unixソケット）が不足していたため追加。
- **403 CSRF verification failed**: `DEBUG=False` 設定下でプロキシ（localhost）経由のログインを許可するため、`settings.py` に `CSRF_TRUSTED_ORIGINS` を追加し、`http://localhost:8080` を信頼リストに登録しました。

## 次のステップ
1. 引き続き `gcloud run services proxy` を実行した状態で、[http://localhost:8080](http://localhost:8080) を再読み込みしてください。
2. ログイン画面が表示されることを確認してください。
