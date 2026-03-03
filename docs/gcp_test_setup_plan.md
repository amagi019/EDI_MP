# GCPテスト環境構築およびメール送信防止の計画

この計画では、EDI-MPプロジェクトをGCPのサーバレス環境（Cloud Run）にデプロイし、テスト環境として運用するための手順と設定変更を定義します。特に、テスト中に不用意にメールが送信されないように設定を徹底します。

## ユーザーレビューが必要な項目
> [!IMPORTANT]
> - GCPのプロジェクトIDを **`edi-sophia-test`** として使用します。
> - データベースのパスワードやシークレットキーは、本番用とは別のものを設定します。

## 提案される変更

### 1. アプリケーション設定の変更

#### [MODIFY] [settings.py](file:///Users/yutaka/workspace/EDI_MP_1/EDI_MP/EDI_MP/settings.py)
環境変数 `EMAIL_BACKEND` を介してメール送信方法を切り替えられるようにし、デフォルトを `django.core.mail.backends.console.EmailBackend`（コンソール出力）に設定します。これにより、明示的に変更しない限り、実際のメールが送信されることはありません。

```python
# settings.py
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
```

### 2. GCPインフラストラクチャの構築

以下の手順でテスト環境を構築します。

#### Cloud SQL (PostgreSQL 15)
- インスタンス名: `edi-db-test`
- マシンスペック: `db-f1-micro` (コスト削減のため)
- リージョン: `asia-northeast1`
- プロジェクトID: `edi-sophia-test`

#### Secret Manager
以下の秘密情報を登録します。
- `SECRET_KEY`: Djangoのシークレットキー（テスト用）
- `DATABASE_URL`: Cloud SQLへの接続URL
- `EMAIL_BACKEND`: `django.core.mail.backends.console.EmailBackend` (明示的にコンソール出力を指定)

#### Cloud Run
- サービス名: `edi-system-test`
- 環境変数: `DEBUG=False`, `ALLOWED_HOSTS=*`, `EMAIL_BACKEND` (Secret Managerから参照)

## 検証計画

### 1. デプロイ後の導通確認
Cloud RunのURLにアクセスし、ログイン画面が表示されることを確認します。

### 2. メール送信の抑制テスト
1. テスト環境で注文書の「承認」操作など、メール送信が発生するアクションを実行します。
2. Cloud Runのログ（Google Cloud Logging）を確認し、メールの内容がログに出力されていること、および実際の宛先にメールが届いていないことを確認します。

#### 実行コマンド（ログ確認）
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=edi-system-test" --limit 50
```

### 3. 自動テストの実行
コンテナ内部で既存のDjangoテストがパスすることを確認します。
```bash
python manage.py test
```
