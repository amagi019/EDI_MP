"""
Google Drive連携サービス
承認済み契約書PDFをGoogle Driveにアップロードする。
サービスアカウントキーが未設定の場合はスキップ（エラーにしない）。
共有ドライブ（Shared Drive）にも対応。
"""
import os
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Google Drive APIサービスを取得する。認証情報がなければNoneを返す。"""
    credentials_file = getattr(settings, 'GOOGLE_DRIVE_CREDENTIALS_FILE', '')
    if not credentials_file or not os.path.exists(credentials_file):
        logger.info("[Google Drive] サービスアカウントキーが未設定のためスキップ")
        return None

    # ファイルが空の場合もスキップ
    if os.path.getsize(credentials_file) == 0:
        logger.info("[Google Drive] サービスアカウントキーが空ファイルのためスキップ")
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        SCOPES = ['https://www.googleapis.com/auth/drive']
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logger.warning(f"[Google Drive] サービス初期化エラー: {e}")
        return None


def _find_or_create_folder(service, folder_name, parent_id):
    """指定名のフォルダを検索し、なければ作成する。共有ドライブ対応。"""
    query = (
        f"name='{folder_name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    results = service.files().list(
        q=query, spaces='drive', fields='files(id, name)', pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    # フォルダ作成
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    folder = service.files().create(
        body=file_metadata, fields='id',
        supportsAllDrives=True,
    ).execute()
    logger.info(f"[Google Drive] フォルダ作成: {folder_name} (ID: {folder.get('id')})")
    return folder.get('id')


def upload_contract_pdf(partner, pdf_content, signed_at):
    """
    承認済み契約書PDFをGoogle Driveにアップロードする。

    Args:
        partner: Partnerオブジェクト
        pdf_content: PDFのバイトデータ
        signed_at: 承認日時

    Returns:
        str: アップロードしたファイルのIDまたはNone
    """
    root_folder_id = getattr(settings, 'GOOGLE_DRIVE_CONTRACT_FOLDER_ID', '') or \
                     getattr(settings, 'GOOGLE_DRIVE_ROOT_FOLDER_ID', '')
    if not root_folder_id:
        logger.info("[Google Drive] CONTRACT_FOLDER_IDが未設定のためアップロードスキップ")
        return None

    service = _get_drive_service()
    if not service:
        return None

    try:
        # パートナー名のフォルダを検索/作成
        partner_folder_id = _find_or_create_folder(
            service, partner.name, root_folder_id
        )

        # PDFファイル名
        date_str = signed_at.strftime('%Y%m%d')
        file_name = f"契約書_{partner.name}_{date_str}.pdf"

        # アップロード
        from googleapiclient.http import MediaInMemoryUpload

        media = MediaInMemoryUpload(pdf_content, mimetype='application/pdf')
        file_metadata = {
            'name': file_name,
            'parents': [partner_folder_id],
        }
        uploaded_file = service.files().create(
            body=file_metadata, media_body=media, fields='id, webViewLink',
            supportsAllDrives=True,
        ).execute()

        file_id = uploaded_file.get('id')
        web_link = uploaded_file.get('webViewLink', '')
        logger.info(f"[Google Drive] アップロード成功: {file_name} (ID: {file_id})")
        print(f"[Google Drive] アップロード成功: {file_name} (URL: {web_link})")
        return file_id

    except Exception as e:
        logger.warning(f"[Google Drive] アップロードエラー: {e}")
        print(f"[Google Drive] アップロードエラー: {e}")
        return None
