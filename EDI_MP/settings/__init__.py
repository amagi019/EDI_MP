"""
Settings パッケージの初期化

環境変数 DJANGO_ENV で自動的に適切な設定ファイルを読み込む:
- DJANGO_ENV=production → prod.py
- DJANGO_ENV=development (デフォルト) → dev.py

既存の参照（manage.py, wsgi.py等の 'EDI_MP.settings'）を
変更せずに動作する後方互換設計。
"""

import os

env = os.environ.get('DJANGO_ENV', 'development')

if env == 'production':
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
