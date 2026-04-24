"""
本番環境固有の設定

NAS (Docker) + Cloudflare Tunnel 経由のHTTPS環境で使用。
"""

from .base import *  # noqa: F401,F403
from .base import env

# 本番環境ではDEBUGは必ずFalse
DEBUG = False

# セキュリティ設定（本番環境で有効化）
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)  # Cloudflare側でリダイレクト済み
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)  # 1年
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)

# Cloudflare経由のHTTPS検知
SECURE_PROXY_SSL_HEADER_TUPLE = env.tuple('SECURE_PROXY_SSL_HEADER', default=None)
if SECURE_PROXY_SSL_HEADER_TUPLE:
    SECURE_PROXY_SSL_HEADER = SECURE_PROXY_SSL_HEADER_TUPLE

# 本番用ログ設定
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'audit': {
            'format': '%(asctime)s [%(name)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'audit_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': '/app/logs/audit.log',
            'when': 'D',
            'interval': 1,
            'backupCount': 30,
            'formatter': 'audit',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'orders': {
            'handlers': ['console', 'audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'tasks': {
            'handlers': ['console', 'audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'invoices': {
            'handlers': ['console', 'audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
