# EDI_MP インストールガイド

## 概要
このアプリケーションをNAS環境にインストールする手順書です。

## 前提条件
- NAS（Synology等）にDockerがインストール済みであること
- NASにSSHアクセスが可能であること

---

## 方法A：ワンクリックセットアップ（推奨）

### 1. ソースコードをNASに転送
USBメモリまたはSCPでプロジェクトフォルダをNASにコピー。

### 2. セットアップスクリプトを実行
```bash
cd /volume1/docker/EDI_MP
bash setup.sh
```

スクリプトが以下を自動実行します：
- `.env` ファイルの対話的な作成（質問に答えるだけ）
- Dockerイメージのビルド・起動
- データベースの初期化
- 管理者ユーザーの作成

### 3. ブラウザで初期設定
`http://<NASのIPアドレス>:8090/admin/` にアクセスし：
1. **会社情報** → 会社名・住所・代表者を入力、印影画像をアップロード
2. **メールテンプレート** → 必要に応じて文面を修正

---

## 方法B：手動セットアップ

### 1. 環境変数の設定
`.env.nas.sample` をコピーして `.env.nas` を作成し、各項目を入力：
```bash
cp .env.nas.sample .env.nas
nano .env.nas  # エディタで編集
```

### 2. Docker起動
```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### 3. ブラウザで初期設定
方法Aのステップ3と同じ。

---

## 環境変数一覧

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `SECRET_KEY` | Djangoの秘密鍵（自動生成可） | `<ランダム文字列>` |
| `ALLOWED_HOSTS` | アクセス許可ホスト | `192.168.1.100,edi.example.com` |
| `DEFAULT_FROM_EMAIL` | メール差出人 | `info@example.com` |
| `EMAIL_HOST_USER` | SMTPユーザー | `user@gmail.com` |
| `EMAIL_HOST_PASSWORD` | SMTPパスワード | `<アプリパスワード>` |

---

## 提供物チェックリスト

| # | 提供物 | 含まれるか |
|---|--------|-----------|
| 1 | ソースコード | ✅ |
| 2 | `.env.nas.sample` | ✅ |
| 3 | `docker-compose.yml` | ✅ |
| 4 | `setup.sh` | ✅ |
| 5 | 本手順書 | ✅ |

> ⚠️ `.env`ファイル、`media/`ディレクトリ、データベースファイルは**含めない**
