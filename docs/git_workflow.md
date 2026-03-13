# Git 運用ガイド

## リポジトリ情報

- **URL**: https://github.com/amagi019/EDI_MP
- **メインブランチ**: `main`（リリース済みの安定版）
- **検証ブランチ**: `staging`（自社NASでの本番検証用）
- **開発ブランチ**: `TestDev_001`（開発・修正用）

---

## ブランチ戦略

```
TestDev_001（開発）  →  staging（検証）  →  main（リリース）

  ローカルPCで開発        自社NASで本番検証      協力会社に自動配信
  ・機能追加              ・実データで動作確認    ・cronで自動git pull
  ・バグ修正              ・問題なければmainへ    ・翌朝最新版に更新
  ・ローカルテスト
```

### 各ブランチの役割

| ブランチ | 用途 | デプロイ先 | 自動更新 |
|---------|------|-----------|---------|
| `TestDev_001` | 開発・修正 | ローカルPC | - |
| `staging` | 本番検証 | **自社NAS** | ✅ cronで定期pull |
| `main` | リリース版 | **協力会社NAS** | ✅ cronで定期pull |

---

## 日常の開発フロー

### ステップ1：ローカルで開発
```bash
# 開発ブランチで作業
git checkout TestDev_001

# 変更をコミット
git add .
git commit -m "feat: ○○機能を追加"

# ローカルテスト（runserver で確認）
python manage.py runserver 8090
```

### ステップ2：自社NASで検証
```bash
# 検証ブランチにマージ
git checkout staging
git merge TestDev_001
git push origin staging
```
→ 自社NASのcronが自動でpull → 本番データで動作確認

### ステップ3：問題なければリリース
```bash
# mainブランチにマージ
git checkout main
git merge staging
git push origin main

# 開発ブランチに戻る
git checkout TestDev_001
```
→ 協力会社NASのcronが自動でpull → 翌朝最新版に更新

---

## GitHubでPull Requestを使う場合

1. PR作成ページを開く:
   - 検証: 👉 https://github.com/amagi019/EDI_MP/compare/staging...TestDev_001
   - リリース: 👉 https://github.com/amagi019/EDI_MP/compare/main...staging

2. 差分を確認後、**「Merge pull request」** → **「Confirm merge」**

---

## 緊急時の対応（ホットフィックス）

本番で緊急バグが見つかった場合：

```bash
# mainから直接修正ブランチを作成
git checkout main
git checkout -b hotfix/緊急修正名

# 修正してコミット
git add .
git commit -m "hotfix: ○○の緊急修正"

# main と staging 両方にマージ
git checkout main
git merge hotfix/緊急修正名
git push origin main

git checkout staging
git merge hotfix/緊急修正名
git push origin staging

# 開発ブランチにも反映
git checkout TestDev_001
git merge main
```

---

## コミットメッセージの規約

| プレフィックス | 用途 | 例 |
|-------------|------|-----|
| `feat:` | 新機能 | `feat: レスポンシブ対応を追加` |
| `fix:` | バグ修正 | `fix: メール重複送信を修正` |
| `docs:` | ドキュメント | `docs: ベストプラクティスを追加` |
| `refactor:` | リファクタリング | `refactor: ハードコーディング除去` |
| `hotfix:` | 緊急修正 | `hotfix: ログインエラーを修正` |

---

## よく使うコマンド

```bash
# 状態確認
git status
git log --oneline -5

# ブランチ一覧
git branch -a

# ブランチ切替
git checkout TestDev_001
git checkout staging
git checkout main

# リモートの最新を取得
git pull origin main
```

---

## 自動更新の仕組み

### 自社NAS（stagingブランチを追跡）
```cron
# 毎日午前3時にstagingブランチを自動pull
0 3 * * * cd /volume1/docker/EDI_MP && git checkout staging && bash update.sh >> /var/log/edi_update.log 2>&1
```

### 協力会社NAS（mainブランチを追跡）
```cron
# 毎日午前3時にmainブランチを自動pull
0 3 * * * cd /volume1/docker/EDI_MP && git checkout main && bash update.sh >> /var/log/edi_update.log 2>&1
```
