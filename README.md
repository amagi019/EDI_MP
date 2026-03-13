# EDI・注文管理システム (EDI-MP)

## 1. 主な機能

- **パートナーオンボーディング**: 取引先による会社情報、インボイス登録番号、振込先情報のオンライン登録。
- **基本契約管理**: 契約書の自動生成、送付、オンライン承認、Google Drive自動保存。
- **デジタル発注フロー**:
    - **下書き (DRAFT)**: 管理者による発注データ作成。
    - **正式発行 (PUBLISH)**: パートナーへの公開・Google Drive保存。
    - **オンライン受領・承認**: パートナーによる内容確認と承認。
- **請求書・支払通知書**: PDF生成、Google Drive保存。
- **電帳法・インボイス制度対応**:
    - 適格請求書発行事業者番号（T番号）の管理とバリデーション。
    - 注文書・注文請書のPDF永続保存および改ざん防止ハッシュの生成。
    - 確定日時のタイムスタンプ保持。
- **Google Drive連携**: 契約書・注文書・支払通知書を共有ドライブの専用フォルダに自動保存。

---

## 2. 技術スタック

| 項目 | 技術 |
|------|------|
| フレームワーク | Django 4.2 LTS |
| データベース（開発） | PostgreSQL (Docker / ローカル) |
| データベース（本番） | PostgreSQL (Docker on QNAP NAS) |
| 静的ファイル配信 | WhiteNoise |
| 本番サーバー | Gunicorn / Docker (QNAP TS-462) |
| リバースプロキシ / SSL | Cloudflare Tunnel |
| PDF生成 | ReportLab |
| 外部連携 | Google Drive API (サービスアカウント認証) |
| Python バージョン | 3.9+ |

---

## 3. システムの起動方法

### ワンコマンドで起動（推奨）

```bash
./start.sh
```

このスクリプトは以下を自動で実行します:
1. 仮想環境の作成（初回のみ）
2. 仮想環境の有効化
3. 依存パッケージのインストール
4. データベースマイグレーション
5. 静的ファイル収集
6. 開発サーバー起動

> **初回実行時**: `chmod +x start.sh` で実行権限を付与してください。

### 手動で起動する場合

```bash
# 仮想環境の作成（初回のみ）
python3 -m venv .venv

# 仮想環境の有効化
source .venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt

# データベースマイグレーション
python manage.py migrate

# 開発サーバーの起動
python manage.py runserver 8090
```

### アクセスURL

| URL | 用途 |
|-----|------|
| http://127.0.0.1:8090/ | ローカル開発環境 |
| http://127.0.0.1:8090/admin/ | ローカル管理者画面 (Django Admin) |
| https://edi.macplanning.com/ | 本番環境 (QNAP TS-462) |
| https://edi.macplanning.com/admin/ | 本番管理者画面 |

---

## 4. アカウントと運用フロー

### A. 管理者（自社ユーザー）
1. **初期登録**: `/signup/admin/` より登録（または `createsuperuser`）。
2. **取引先登録**: ダッシュボードの「取引先登録」からクイック登録。
3. **基本契約**: 契約書生成 → 送付 → パートナー承認 → Google Drive保存。
4. **発注管理**: 注文書作成 → 正式発行 → パートナー承認。

### B. 取引先（パートナーユーザー）
1. **アカウント発行**: 管理者がクイック登録でアカウントを作成。招待メールが自動送信。
2. **オンボーディング**: ログイン後のダッシュボードから「会社情報を登録・更新する」をクリックし、インボイス登録番号や振込先口座情報を登録。
3. **基本契約の承認**: 契約書を確認し「承認」ボタンをクリック。
4. **注文の承認**: 届いた注文書の内容を確認し「承諾する」ボタンをクリック。承認と同時にシステムが「注文請書」を自動生成・保存。

---

## 5. プロジェクト構造

```
EDI_MP/
├── EDI_MP/              # プロジェクト設定
│   └── settings/        # 環境別設定（base, dev, prod）
├── core/                # コアドメイン（認証・パートナー・契約）
│   ├── domain/models.py
│   ├── permissions.py   # 権限管理（一元化）
│   ├── services/        # ビジネスロジック（Google Drive含む）
│   └── views/           # ビューパッケージ（分割済み）
│       ├── auth_views.py
│       ├── partner_views.py
│       ├── contract_views.py
│       └── dashboard_views.py
├── orders/              # 発注管理
├── invoices/            # 請求管理
├── billing/             # 請求書発行・支払通知
├── docs/                # ドキュメント
│   ├── samples/         # サンプルPDF
│   └── archived/        # アーカイブ済みドキュメント
└── 設計書/              # 設計ドキュメント
```

---

## 6. Google Drive連携

契約書・注文書・支払通知書は Google Drive の共有ドライブに自動保存されます。

### フォルダ構成
| ドキュメント | 環境変数 |
|---|---|
| 契約書 | `GOOGLE_DRIVE_CONTRACT_FOLDER_ID` |
| 注文書 | `GOOGLE_DRIVE_ORDER_FOLDER_ID` |
| 支払通知書 | `GOOGLE_DRIVE_PAYMENT_FOLDER_ID` |

### 設定
- サービスアカウント: `edi-drive-uploader@edi-sophia-test.iam.gserviceaccount.com`
- キーファイル: `credentials/drive-service-account.json`（Git管理外）

---

## 7. データの永続性

開発・本番ともに PostgreSQL を使用しています。
データベースは Docker ボリュームに永続化されており、コンテナの停止・再構築でもデータは保持されます。

---

## 8. 技術仕様とコンプライアンス

- **データ完全性**: 承認された文書（PDF）はサーバー上に永続保存され、SHA256ハッシュが生成されます。
- **マスタ管理**: `BankMaster` による正確な金融機関データの選択をサポート。
- **外部連携 (SignatureService)**: `orders/services/signature_service.py` を通じて外部電子署名プロバイダーとの連携が可能。
- **Webhook受領**: `orders/webhooks.py` にて、外部サービスからの署名完了イベントを処理します。

---

## 9. ドキュメント

- [ユーザーマニュアル](docs/USER_MANUAL.md): システムの利用方法詳細
- [運用テスト仕様書](docs/operational_test_plan.md): 動作確認手順
- [NASデプロイ手順書](docs/deploy_nas.md): NASへのデプロイ手順
- [Git運用ガイド](docs/git_workflow.md): ブランチ運用・PR作成手順
- [Djangoベストプラクティス](docs/django_best_practices.md): コーディングルール

---

## 10. 管理者向けのパスワード変更

1. ログイン中: `/accounts/password_change/`
2. 管理者画面: 「ユーザー」モデルから変更。
3. CLI: `python manage.py changepassword [ユーザー名]`
