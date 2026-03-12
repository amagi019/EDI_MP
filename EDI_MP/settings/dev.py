"""
開発環境固有の設定

ローカル開発時に使用。DEBUG=True、SQLite、コンソールメール出力等。
"""

from .base import *  # noqa: F401,F403

# 開発環境のデフォルト
DEBUG = True

# 開発用セキュリティ設定（全てオフ）
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
