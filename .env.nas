# ============================================================
# EDI_MP - NAS本番用 環境変数
# ============================================================

# デバッグモード（本番は False）
DEBUG=False

# シークレットキー（本番用）
SECRET_KEY=KfuEv6tD6dRpNUkFlHWlznWnzT44c_LYQ3Wcv2RRVZSJxt_U0cSv1EMpWE_H2WOz3qc

# PostgreSQL 接続設定
DATABASE_URL=postgres://edi_user:edi_mp_secure_2026@db:5432/edi_mp
POSTGRES_PASSWORD=edi_mp_secure_2026

# ホスト許可設定
ALLOWED_HOSTS=192.168.50.198,nasamagi19,localhost,127.0.0.1

# CSRF信頼オリジン
CSRF_TRUSTED_ORIGINS=http://192.168.50.198:8090,http://nasamagi19:8090

# Google Drive連携（不要なら空欄のまま）
GOOGLE_DRIVE_ROOT_FOLDER_ID=
