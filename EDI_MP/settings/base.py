"""
共通設定（common / base）

全環境で共通の設定を定義。
環境固有の設定は dev.py / prod.py で上書きする。
"""

from pathlib import Path
import os
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False)
)
# Read .env file if it exists
if os.path.exists(BASE_DIR / ".env"):
    environ.Env.read_env(BASE_DIR / ".env")


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')  # .envファイルで設定必須

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')  # .envファイルで設定必須

# CSRF設定（プロキシ経由のアクセスを許可）
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'http://localhost:8000',
    'http://127.0.0.1:8000',
])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'core.apps.CoreConfig',
    'core.mfa.apps.MfaConfig',
    'orders',
    'invoices',
    'billing',
    'tasks.apps.TasksConfig',
    'payroll.apps.PayrollConfig',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.MaintenanceMiddleware',
    'core.middleware.FirstLoginMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'EDI_MP.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'EDI_MP.wsgi.application'


# Database
DATABASES = {
    'default': env.db('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True
LANGUAGES = [
    ('ja', '日本語'),
    ('en', 'English'),
]


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# メディアファイル
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 認証設定
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Google Drive連携
GOOGLE_DRIVE_SERVICE_ACCOUNT = env('GOOGLE_DRIVE_SERVICE_ACCOUNT', default='')
GOOGLE_DRIVE_CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials', 'drive-service-account.json')
# ドキュメントタイプ別フォルダID
GOOGLE_DRIVE_CONTRACT_FOLDER_ID = env('GOOGLE_DRIVE_CONTRACT_FOLDER_ID', default='')
GOOGLE_DRIVE_ORDER_FOLDER_ID = env('GOOGLE_DRIVE_ORDER_FOLDER_ID', default='')
GOOGLE_DRIVE_PAYMENT_FOLDER_ID = env('GOOGLE_DRIVE_PAYMENT_FOLDER_ID', default='')
GOOGLE_DRIVE_WORK_REPORT_FOLDER_ID = env('GOOGLE_DRIVE_WORK_REPORT_FOLDER_ID', default='')
GOOGLE_DRIVE_BILLING_INVOICE_FOLDER_ID = env('GOOGLE_DRIVE_BILLING_INVOICE_FOLDER_ID', default='')
# 後方互換: 旧ROOT_FOLDER_ID（個別未設定時のフォールバック）
GOOGLE_DRIVE_ROOT_FOLDER_ID = env('GOOGLE_DRIVE_ROOT_FOLDER_ID', default='')

# パスワードハッシュ化設定
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]

# メール設定
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@example.com')

# デフォルトのプライマリキーフィールド型
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# セキュリティ共通設定
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_CONTENT_TYPE_NOSNIFF = True

# アップロードサイズ制限
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10MB

# セッション設定
SESSION_COOKIE_AGE = 8 * 60 * 60  # 8時間
SESSION_COOKIE_NAME = 'edi_sessionid'
CSRF_COOKIE_NAME = 'edi_csrftoken'
SESSION_SAVE_EVERY_REQUEST = True  # リクエスト毎にセッション更新（アクティブなら延長）

# ============================================================
# システム間API連携設定
# ============================================================
# 共通APIキー（EDI・PayrollSystem双方で同じ値を設定）
EDI_API_KEY = env('EDI_API_KEY', default='')
# EDI APIのURL（PayrollSystem側で設定）
EDI_API_URL = env('EDI_API_URL', default='')
# PayrollSystem APIのURL（EDI側で設定）
PAYROLL_API_URL = env('PAYROLL_API_URL', default='')

# ============================================================
# Webhook セキュリティ設定
# ============================================================
# 外部サービスからのWebhookリクエストの HMAC-SHA256 署名検証用シークレット
WEBHOOK_SECRET = env('WEBHOOK_SECRET', default='')

