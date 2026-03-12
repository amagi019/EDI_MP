# テスト手順書（ローカル環境 ＆ NAS環境）

## 前提条件

- Python 3.9+ がインストール済み
- プロジェクトルート: `/Users/yutaka/workspace/EDI_MP_1/EDI_MP/`

---

## 1. 環境起動

```bash
cd /Users/yutaka/workspace/EDI_MP_1/EDI_MP

# 方法A: ワンコマンド
./start.sh

# 方法B: 手動
source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

> ⚠️ `invoices/models.py` のステータス名変更があるため、初回は `makemigrations` → `migrate` を必ず実行してください。

### アクセスURL

| URL | 用途 |
|-----|------|
| http://127.0.0.1:8090/ | フロントエンド |
| http://127.0.0.1:8090/admin/ | Django管理画面 |

### メールについて

ローカル環境ではメールは送信されません（`console.EmailBackend`）。メール内容はターミナルに表示されます。

---

## 2. テストデータの準備

### 管理者アカウント作成（初回のみ）

```bash
python manage.py createsuperuser
# ユーザー名・メール・パスワードを入力
```

### パートナー登録（管理画面から）

1. http://127.0.0.1:8090/admin/ にログイン
2. 「パートナー」→「パートナーを追加」
   - 会社名、メールアドレスを入力して保存

### プロジェクト登録（管理画面から）

1. 「ORDERS」→「プロジェクト」→「プロジェクトを追加」
   - 取引先（パートナー）を選択、プロジェクト名を入力して保存

---

## 3. テストケース

### A. 招待メール送信（Admin カスタムアクション）

1. http://127.0.0.1:8090/admin/core/customer/ を開く
2. テスト用パートナーにチェックを入れる
3. アクション「**招待メール作成（アカウント作成）**」を選択 → 実行
4. **確認ポイント**:
   - プレビュー画面にメール内容（ログインURL、ID、パスワード）が表示されること
   - 「送信する」クリック → ターミナルにメール内容が出力されること
   - 既にアカウントがあるパートナーはスキップされること

### B. サイドバーのメニュー構成

1. 管理者でログイン → http://127.0.0.1:8090/
2. **確認ポイント**: サイドバーが以下の順で表示されること
   - ダッシュボード
   - パートナー管理（パートナー登録 / 基本契約進捗）
   - 発注管理（発注書作成 / 注文書一覧）
   - 請求管理（支払通知一覧）
   - 請求書発行（ダッシュボード / 請求書 / 請求先 / 商品）
   - 管理画面

### C. 発注書作成

1. サイドバーの「**発注書作成**」をクリック
2. フォームに入力:
   - パートナー、プロジェクトを選択
   - 注文日、対象月、作業開始日・終了日を入力
   - 担当者名を入力（任意）
   - 基本料金、基準時間などを入力
3. 明細行の「**明細行を追加**」ボタンで行が追加されることを確認
4. 「**下書き保存**」をクリック
5. **確認ポイント**:
   - 注文詳細画面にリダイレクトされること
   - ステータスが「下書き」であること
   - 注文書一覧に表示されること

### D. 発注書の正式発行

1. 注文詳細画面で「**正式発行**」ボタンをクリック（※既存機能）
2. **確認ポイント**:
   - ステータスが「未確認（発行済）」に変更されること
   - PDFが生成されていること

### E. 請求書の承認ボタン確認

1. 管理画面で請求書データを作成（テストデータ）
2. パートナーユーザーでログイン
3. 請求書詳細画面を開く
4. **確認ポイント**:
   - ボタンが「**承認する**」と表示されていること（「確定する」ではない）
   - 確認ダイアログに「この請求書を承認しますか？」と表示されること

---

## 4. トラブルシューティング

| 問題 | 対処 |
|------|------|
| `ModuleNotFoundError: No module named 'xxx'` | `pip install -r requirements.txt` を実行 |
| マイグレーションエラー | `python manage.py makemigrations` → `python manage.py migrate` |
| 管理者アカウントがない | `python manage.py createsuperuser` で作成 |
| スタティックファイルが表示されない | `python manage.py collectstatic` を実行 |
| パートナー選択肢が空 | 管理画面でパートナーを先に登録 |

---

# NAS環境テスト（実メール送信）

## 5. NAS環境の準備

### テスト用メールアドレス

| 役割 | メールアドレス |
|------|---------------|
| パートナー（受信テスト用） | y.yosikawa@gmail.com |
| 自社担当者（通知受信） | y.yoshikawa@macplanning.com |

### Gmail SMTPの設定

NASの `.env` ファイルに以下を追加してください：

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=y.yoshikawa@macplanning.com
EMAIL_HOST_PASSWORD=（Googleアプリパスワード）
DEFAULT_FROM_EMAIL=y.yoshikawa@macplanning.com
```

> ⚠️ **Googleアプリパスワード** の取得手順:
> 1. https://myaccount.google.com/apppasswords にアクセス
> 2. アプリ名（例: `EDI-MP`）を入力して「作成」
> 3. 表示された16文字のパスワードを `EMAIL_HOST_PASSWORD` に設定
>
> ※ Google Workspaceを利用している場合は、管理者がアプリパスワードを許可している必要があります。

### NASでの起動

```bash
# NASにSSH接続後
cd /path/to/EDI_MP
docker compose up -d --build
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

---

## 6. NASテストケース

### F. 招待メール送信（実メール）

1. NAS管理画面でテスト用パートナーを登録（メール: `y.yosikawa@gmail.com`）
2. パートナー一覧 → テスト用パートナーを選択 → 「招待メール作成（アカウント作成）」実行
3. プレビュー画面でメール内容を確認 → 「送信する」をクリック
4. **確認ポイント**:
   - `y.yosikawa@gmail.com` にメールが届くこと
   - メール内にログインURL、ID、パスワードが記載されていること
   - URLが `https://edi.macplanning.com/` で始まること

### G. 発注書作成 → PDFプレビュー

1. サイドバー「発注書作成」からテスト発注書を作成
2. 注文詳細画面でPDFプレビューを確認
3. 「正式発行」→ ステータスが「未確認（発行済）」に変更されることを確認

### H. パートナーのログイン・承認テスト

1. 招待メールに記載されたID/パスワードでEDI-MPにログイン（`https://edi.macplanning.com/`）
2. 注文書一覧に発行済みの注文書が表示されることを確認
3. 注文書を承認 → `y.yoshikawa@macplanning.com` に承認通知メールが届くことを確認

---

## 7. テスト完了後

- [ ] 招待メールが `y.yosikawa@gmail.com` に届いた
- [ ] メール内のURLからログインできた
- [ ] サイドバーのメニュー順が正しい
- [ ] 発注書の作成・下書き保存ができた
- [ ] PDFプレビューが正しく表示された
- [ ] 正式発行後、ステータスが変更された
- [ ] パートナーが承認後、承認通知メールが届いた
- [ ] 請求書詳細画面のボタンが「承認する」になっている

