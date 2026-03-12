"""
Googleドライブ保存サービス（請求書/支払通知書）
共有ドライブ対応。
"""
import os
from django.conf import settings
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


SCOPES = ['https://www.googleapis.com/auth/drive']


def _get_drive_service():
    """Google Drive APIサービスを取得"""
    cred_path = getattr(settings, 'GOOGLE_DRIVE_CREDENTIALS_FILE', '')
    if not cred_path:
        cred_path = os.path.join(
            settings.BASE_DIR, 'credentials', 'drive-service-account.json'
        )

    # サービスアカウントJSONが存在し、中身がある場合はそれを使用
    if os.path.exists(cred_path) and os.path.getsize(cred_path) > 0:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=SCOPES
        )
    else:
        # Application Default Credentials (ADC) を使用
        import google.auth
        credentials, _ = google.auth.default(scopes=SCOPES)

    return build('drive', 'v3', credentials=credentials)


def upload_to_drive(pdf_buffer, filename, folder_id=None):
    """
    PDFファイルをGoogleドライブにアップロードする。

    Args:
        pdf_buffer: PDFのバイトストリーム
        filename: ファイル名（例: "請求書_2024年11月_○○.pdf"）
        folder_id: 保存先フォルダID（省略時はPAYMENT_FOLDER_IDを使用）

    Returns:
        GoogleドライブのファイルID
    """
    service = _get_drive_service()

    if folder_id is None:
        folder_id = getattr(settings, 'GOOGLE_DRIVE_PAYMENT_FOLDER_ID', '') or \
                     getattr(settings, 'GOOGLE_DRIVE_ROOT_FOLDER_ID', '')

    file_metadata = {
        'name': filename,
        'mimeType': 'application/pdf',
    }
    if folder_id:
        file_metadata['parents'] = [folder_id]

    pdf_buffer.seek(0)
    media = MediaIoBaseUpload(
        pdf_buffer, mimetype='application/pdf', resumable=True
    )

    file = service.files().create(
        body=file_metadata, media_body=media,
        fields='id,webViewLink',
        supportsAllDrives=True
    ).execute()

    return file.get('id', '')


def get_drive_file_url(file_id):
    """DriveファイルIDからURLを生成"""
    return f"https://drive.google.com/file/d/{file_id}/view"
