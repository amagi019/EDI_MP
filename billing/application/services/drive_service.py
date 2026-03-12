"""
Googleドライブ保存サービス（請求書/支払通知書）- 共通モジュールのラッパー

後方互換のため、既存のインポートパスを維持する。
実体は core.services.google_drive_service に統合済み。
"""
from core.services.google_drive_service import (  # noqa: F401
    upload_payment_pdf as upload_to_drive,
    get_drive_file_url,
)
