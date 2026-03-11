# ER図（エンティティ関連図）

## 概要

EDI-MPシステムの全テーブル構成。3アプリ・18テーブル。

## ER図

```mermaid
erDiagram
    %% ===== core アプリ =====
    User ||--o| Profile : "1:1"
    Partner ||--o| Profile : "1:N"
    Partner ||--o| MasterContractProgress : "1:1"
    Partner ||--o{ SentEmailLog : "1:N"

    %% ===== orders アプリ =====
    Partner ||--o{ Order : "1:N"
    Partner ||--o{ PaymentTerm : "1:N"
    Partner ||--o{ ContractTerm : "1:N"
    Partner ||--o{ OrderBasicInfo : "1:N"

    Customer ||--o{ Project : "1:N"

    Project ||--o{ Order : "1:N"
    Project ||--o{ PaymentTerm : "1:N"
    Project ||--o{ ContractTerm : "1:N"
    Project ||--o{ OrderBasicInfo : "1:N"

    Order ||--o{ OrderItem : "1:N"
    Order ||--o{ Person : "1:N"
    Order o|--o| PaymentTerm : "0..1"
    Order o|--o| ContractTerm : "0..1"
    Order o|--o| Workplace : "0..1"
    Order o|--o| Deliverable : "0..1"

    %% ===== invoices アプリ =====
    Order ||--o| Invoice : "1:1"
    Invoice ||--o{ InvoiceItem : "1:N"

    %% ===== エンティティ定義 =====
    Partner {
        string partner_id PK
        string name
        string email
        string registration_no
        string bank_name
        string account_number
    }

    Customer {
        int id PK
        string name
        string registration_no
    }

    Profile {
        int id PK
        int user_id FK
        string partner_id FK
        bool is_first_login
    }

    MasterContractProgress {
        int id PK
        string partner_id FK
        string status "INVITED/INFO_DONE/CONTRACT_SENT/COMPLETED"
    }

    CompanyInfo {
        int id PK
        string name
        string representative_name
        string registration_no
    }

    Project {
        string project_id PK
        int customer_id FK
        string name
    }

    Order {
        string order_id PK "MP+YYYYMMDD+6桁"
        string partner_id FK
        string project_id FK
        string status "DRAFT/UNCONFIRMED/CONFIRMING/RECEIVED/APPROVED"
        date order_date
        date work_start
        date work_end
    }

    OrderItem {
        int id PK
        string order_id FK
        string person_name
        decimal effort
        int base_fee
        decimal time_lower_limit
        decimal time_upper_limit
        int shortage_rate
        int excess_rate
        decimal actual_hours
        int price "自動計算"
    }

    OrderBasicInfo {
        int id PK
        string partner_id FK
        string project_id FK
        string order_issuance_timing
        string invoice_issuance_timing
    }

    Invoice {
        int id PK
        string order_id FK "1:1"
        string invoice_no "YYMM+3桁"
        string acceptance_no "MP+invoice_no"
        string status "DRAFT/ISSUED/SENT/CONFIRMED/PAID"
        date target_month
        date payment_deadline
        int total_amount
    }

    InvoiceItem {
        int id PK
        int invoice_id FK
        string person_name
        decimal work_time
        int base_fee
        int shortage_rate
        int excess_rate
        int item_subtotal
    }

    PaymentTerm {
        int id PK
        string partner_id FK
        string project_id FK
        string description
    }

    ContractTerm {
        int id PK
        string partner_id FK
        string project_id FK
        string description
    }

    Workplace {
        int id PK
        string name
    }

    Deliverable {
        int id PK
        string description
    }

    SentEmailLog {
        int id PK
        string partner_id FK
        string subject
        datetime sent_at
    }

    EmailTemplate {
        int id PK
        string code UK
        string subject
        string body
    }

    BankMaster {
        string bank_code
        string branch_code
        string bank_name
        string branch_name
    }
```

## テーブル一覧

| アプリ | テーブル | 説明 |
|--------|---------|------|
| core | Partner | パートナー（発注先） |
| core | Customer | 取引先（受注元） |
| core | Profile | ユーザープロフィール（User⇔Partner紐付け） |
| core | CompanyInfo | 自社情報 |
| core | MasterContractProgress | 基本契約進捗 |
| core | SentEmailLog | 送信メールログ |
| core | EmailTemplate | メールテンプレート |
| core | BankMaster | 銀行マスタ |
| orders | Project | プロジェクト |
| orders | Order | 注文（ヘッダー） |
| orders | OrderItem | 注文明細（作業者ごと） |
| orders | OrderBasicInfo | 発注基本情報（発行タイミング等） |
| orders | PaymentTerm | 支払条件マスタ |
| orders | ContractTerm | 契約条件マスタ |
| orders | Workplace | 勤務場所マスタ |
| orders | Deliverable | 成果物マスタ |
| orders | Person | 担当者 |
| invoices | Invoice | 請求・支払通知（ヘッダー） |
| invoices | InvoiceItem | 請求明細（作業者ごと精算） |

## フィールドの配置

> ✅ `base_fee`, `time_lower_limit`, `time_upper_limit`, `shortage_rate`, `excess_rate` は **OrderItem（明細）と InvoiceItem（請求明細）** に配置。Order（ヘッダー）からは削除済み。

| フィールド | OrderItem | InvoiceItem |
|-----------|-----------|-------------|
| base_fee | ✅ | ✅ |
| time_lower_limit | ✅ | ✅ |
| time_upper_limit | ✅ | ✅ |
| shortage_rate | ✅ | ✅ |
| excess_rate | ✅ | ✅ |
