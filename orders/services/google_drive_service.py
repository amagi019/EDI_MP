"""
Google Drive連携（注文書）- 共通モジュールのラッパー

後方互換のため、既存のインポートパスを維持する。
実体は core.services.google_drive_service に統合済み。
"""
from core.services.google_drive_service import upload_order_pdf  # noqa: F401
