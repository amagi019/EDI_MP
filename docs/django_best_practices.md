---
description: Django開発における必須ルールとベストプラクティス
---

# Django開発ベストプラクティス — プロジェクトルール

本ドキュメントは EDI_MP プロジェクトにおける Django 開発の必須ルールです。

---

## 1. URL生成

### ❌ 禁止: ハードコードURL

```python
# BAD
url = f"/orders/{order.order_id}/"
url = f"{settings.CSRF_TRUSTED_ORIGINS[0]}/accounts/login/"
```

### ✅ 必須: `reverse()` + `build_absolute_uri()`

```python
# GOOD — ビュー内
from django.urls import reverse
url = request.build_absolute_uri(
    reverse('orders:order_detail', kwargs={'order_id': order.order_id})
)

# GOOD — モデルの get_absolute_url()
url = request.build_absolute_uri(order.get_absolute_url())
```

### ✅ 必須: モデルに `get_absolute_url()` を実装

```python
class Order(models.Model):
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('orders:order_detail', kwargs={'order_id': self.order_id})
```

---

## 2. 設計原則

### DRY (Don't Repeat Yourself)
- 同一ロジックの重複禁止。共通関数・Mixin・Service層に集約する。
- 権限チェックは `core/permissions.py` のMixin/デコレータを使用する。

### Fat Model, Thin View
- ビジネスロジックはModel の メソッド または `services/` ディレクトリに配置。
- Viewはリクエストの制御（入力検証・権限チェック・レスポンス返却）に専念。

### Explicit is better than implicit
- 魔法のような自動処理よりも明示的な記述を優先する。

---

## 3. セキュリティ

### 本番環境チェックリスト
- `DEBUG=False`
- `SECRET_KEY` は環境変数から取得（ソースコードにハードコードしない）
- `SESSION_COOKIE_SECURE=True`（HTTPS環境）
- `CSRF_COOKIE_SECURE=True`（HTTPS環境）
- `SECURE_HSTS_SECONDS` を設定（推奨: 31536000=1年）
- `ALLOWED_HOSTS` に `*` を使わない

### 組み込みセキュリティ機能
- CSRF保護を無効化しない（`@csrf_exempt` の使用禁止）
- ORM を使用し、生SQL（`raw()`, `extra()`）を避ける
- テンプレートで `|safe` フィルタの使用は最小限に

---

## 4. 環境変数と設定管理

### 機密情報は `.env` に記載
- `SECRET_KEY`, `DATABASE_URL`, メールパスワード等
- `.env` は `.gitignore` に含め、Gitリポジトリにコミットしない
- `django-environ` を使用して読み込む

### 環境別設定
- `.env`（ローカル開発）と `.env.nas`（本番）で環境を切り替え
- セキュリティ設定は環境変数で本番のみ有効化

---

## 5. データベースとQuerySet

### N+1問題の回避
```python
# BAD — N+1クエリ
orders = Order.objects.all()
for order in orders:
    print(order.partner.name)  # 注文ごとにSQLが発行される

# GOOD — select_related
orders = Order.objects.select_related('partner', 'project').all()
```

### マイグレーション管理
- マイグレーションファイルは必ずGitにコミット
- `makemigrations` と `migrate` は開発時に必ず実行
- 本番デプロイ時は `entrypoint.sh` で自動適用

---

## 6. テンプレート

### 静的ファイル
```html
<!-- BAD -->
<link rel="stylesheet" href="/static/css/style.css">

<!-- GOOD -->
{% load static %}
<link rel="stylesheet" href="{% static 'css/style.css' %}">
```

### Djangoテンプレートタグの改行禁止
```html
<!-- BAD: 改行するとバグになる -->
{{ value|floatformat:0
}}

<!-- GOOD: 1行で記述 -->
{{ value|floatformat:0 }}
```

---

## 7. プロジェクト構造

```
EDI_MP/
├── EDI_MP/          # プロジェクト設定
│   └── settings.py
├── core/            # コアドメイン（認証・パートナー・契約）
│   ├── domain/models.py
│   ├── permissions.py     # 権限管理（一元化）
│   ├── services/          # ビジネスロジック
│   └── views.py
├── orders/          # 発注管理
├── invoices/        # 請求管理
├── billing/         # 請求書発行（旧システム）
└── docs/            # ドキュメント
```

### App分割の指針
- ドメインごとにAppを分離（認証、発注、請求）
- App間の依存は最小限に（循環参照を避ける）
