# EDIシステム 基本設計書 (DDDアーキテクチャ)

本ドキュメントは、マックプランニング様専用のEDIシステムの現在の基本設計（アーキテクチャ・層構成）について定義したものです。

本システムは、保守性と拡張性を高めるため、**ドメイン駆動設計（DDD: Domain-Driven Design）**をベースにした階層化アーキテクチャを採用しています。通常のDjangoにおける素の `views.py` へのベタ書きを避け、ドメインの関心事とインフラ（DB・外部API等）の関心事を分離しています。

---

## 1. 全体アーキテクチャ構成

システムは以下の4つの主要レイヤーに分割されています。

1. **プレゼンテーション層 (Presentation Layer)** / インターフェース層
2. **ユースケース / アプリケーション層 (Application Layer)**
3. **ドメイン層 (Domain Layer) / モデル層**
4. **インフラストラクチャ層 (Infrastructure / External IF Layer)**

機能分割（コンテキスト）としては大きく `core`（共通）、`orders`（発注・稼働）、`invoices`（請求・支払通知）の3つのDjangoアプリケーション（境界づけられたコンテキスト）を持っています。

---

## 2. 各層の役割と設計詳細

### 2.1 プレゼンテーション層 / Web層 (`views.py`, `templates/`)
- **責務**:
  - ユーザーからのHTTPリクエストの受け取りと、レスポンス（HTML、PDF、JSON等）の返却。
  - セッションと権限（Role・Owner等）のチェック。
  - 入力値のバリデーション（Django Form / DRF Serializer を利用）。
- **設計のポイント**:
  - ビジネスロジックを持たず、リクエストを受け取った後は**サービス層（Application Service/Domain Service）を呼び出すだけ**に留める「薄いコントローラー（Thin View）」として実装されています。
  - 今回実装された「支払通知書」「請求書」の表示画面など、ボタン表示の制御やPDFへのルーティングをここで担います。

### 2.2 サービス層 (`services/`)
- **責務**:
  - ビジネスユースケース（「稼働報告を提出し、Google Driveにアップロードし、クライアントへ確認メールを送信する」などの一連のフロー）の制御。
  - 複数のドメインモデルやインフラ部品をまたがる一連のトランザクション実行。
- **代表的な実装**:
  - **`pdf_generator.py`**:
    - HTML/Viewとは完全に切り離され、ReportLabを用いたPDFの動的生成（印鑑の配置、8列レイアウトでの自動改行処理など）を担当します。
  - **`email_service.py`**:
    - DBから取得した `EmailTemplate` モデルをパースし、パートナーやクライアントへの通知メールを送信するユースケース。

### 2.3 ドメイン・モデル層 (`models.py`, `domain/`)
- **責務**:
  - システムのコアとなる「状態」と「ビジネスルール」を表現。
  - データ構造と、そのデータに対する制約（金額はマイナスにならない、ステータス遷移のルール等）。
- **コンテキスト（境界）と主なモデル**:
  1. **`core` コンテキスト**:
     - `CompanyInfo`: 自社（マックプランニング様）の情報や印影画像。
     - `EmailTemplate`: 自動メール送信用のマスタデータ。
  2. **`orders` コンテキスト**:
     - `Order`: 注文書・請書。契約期間や基本料金・超過/控除単価などの条件。
     - `WorkReport`: パートナーから提出される稼働報告書ファイル（Excel等）。
  3. **`invoices` コンテキスト**:
     - `Invoice`, `InvoiceItem`: 請求データ。稼働報告から計算された金額（超過分・控除分）の明細と集計。ステータス（一時保存、送付済）の管理。

### 2.4 インフラ・外部システム連携層 (External I/F Layer)
- **責務**:
  - ドメインモデルが扱えない「外部システムへのI/O処理」を担当。
  - RDBMS（PostgreSQL）との通信（Django ORMが兼任）。
  - 今回構築された **Google Drive API** などのサードパーティ連携。
- **代表的な実装**:
  - **`google_drive_service.py`**:
    - Google Cloud の Service Account（JSONキー）を用いて認証し、Google Drive API へファイルをアップロード。
    - アップロードしたファイルに対し「リンクを知っている全員が閲覧可能」な権限（Permissions）を設定し、その共有URL（`webViewLink`）をドメイン/サービス層へ返す責務のみを独立して持ちます。
  - **Gmail SMTP 連携**:
    - アプリ（EDIシステム）から送信したメールデータは、GmailのSMTPサーバ（`smtp.gmail.com`）を経由して送信されます。仕様上、EDIシステム内から放たれたメールは、送信に利用された**Gmailアカウントの「送信済み（Sent）」フォルダに自動的に同期・保存**されます。これによりEDIアプリ側で重い送信履歴データベースを持つ必要をなくしています。

---

## 3. コンテキスト間通信・処理フローの例

**【例】稼働報告のアップロードからクライアントへの送付フロー機能**

1. **Presentation**: パートナーがWeb画面（`WorkReportUploadView`）からExcelを選択してSubmit。
2. **Domain/Infrastructure (ORM)**: `WorkReport` モデルとしてデータがDBやローカルNASの一時領域に保存される。
3. **Application Service**:
   - `views.py`（スタッフによる送付アクション）が `google_drive_service.py` を呼び出す。
   - `google_drive_service.py` 内部でGoogle APIを実行し、Drive上のURLを取得。
   - `email_service.py` にURLを渡し、`EmailTemplate`（文面定義）を使って置換しメール生成。
4. **External I/F**:
   - 生成されたメールがGmail SMTPサーバへリレーされる（Gmailの「送信済み」に入る）。

この設計により、「もし今後Google DriveではなくBoxを使いたい」「メールではなくSlack通知にしたい」となった場合でも、ドメイン層やView層を変更することなく、External I/F と Application Service における部品の差し替えだけで対応が可能となっています。
