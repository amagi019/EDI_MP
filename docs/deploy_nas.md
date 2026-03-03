# EDI_MP NASデプロイ手順書

## 前提条件

- QNAP NAS（IP: `192.168.50.198`）にContainer Stationがインストール済み
- MacからNASにSSH接続可能

## 初回デプロイ

### 1. SSH鍵の設定（推奨）

```bash
ssh-keygen -t ed25519 -C "yutaka@mac"
ssh-copy-id yutaka@192.168.50.198
```

### 2. デプロイ実行

```bash
cd /Users/yutaka/workspace/EDI_MP_1/EDI_MP
chmod +x deploy_nas.sh
./deploy_nas.sh
```

### 3. 初回のみ：管理者ユーザー作成

```bash
ssh yutaka@192.168.50.198
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker
$DOCKER exec -it edi-mp-web python manage.py createsuperuser
```

### 4. アクセス確認

- **アプリ**: http://192.168.50.198:8090
- **管理画面**: http://192.168.50.198:8090/admin/

## SQLiteからのデータ移行（任意）

既存のSQLiteデータをPostgreSQLに移行する場合：

```bash
# ローカルでデータエクスポート
cd /Users/yutaka/workspace/EDI_MP_1/EDI_MP
source .venv/bin/activate
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission > data_dump.json

# NASに転送
scp data_dump.json yutaka@192.168.50.198:/share/Container/EDI_MP/

# NAS上でインポート
ssh yutaka@192.168.50.198
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker
$DOCKER exec -it edi-mp-web python manage.py loaddata /app/data_dump.json
```

## アップデート

コードを変更した後、再デプロイ：

```bash
./deploy_nas.sh
```

## バックアップ

### 手動バックアップ

```bash
ssh yutaka@192.168.50.198
/share/Container/EDI_MP/scripts/backup_nas.sh
```

### 自動バックアップ（cron）

NAS上で以下を `crontab -e` で設定：

```
0 3 * * * /share/Container/EDI_MP/scripts/backup_nas.sh >> /share/Container/EDI_MP/backups/backup.log 2>&1
```

## トラブルシューティング

```bash
# コンテナの状態確認
DOCKER=/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker
$DOCKER ps | grep edi-mp

# ログ確認
$DOCKER logs edi-mp-web --tail 50
$DOCKER logs edi-mp-db --tail 50

# コンテナ再起動
cd /share/Container/EDI_MP
$DOCKER compose -f docker-compose.nas.yml restart

# 完全再構築
$DOCKER compose -f docker-compose.nas.yml down
$DOCKER compose -f docker-compose.nas.yml up -d --build
```
