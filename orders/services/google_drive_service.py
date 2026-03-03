"""
Google Drive APIサービス
注文書PDFをGoogleドライブの共有フォルダにアップロードする。

フォルダ構成:
  共有フォルダ/注文書/パートナー会社名/order_XXXXX.pdf
"""
import io
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Google Drive APIサービスを構築する"""
    from google.auth import default, impersonated_credentials
    from googleapiclient.discovery import build

    sa_email = getattr(settings, 'GOOGLE_DRIVE_SERVICE_ACCOUNT', None)

    # サービスアカウント偽装（組織ポリシーでJSON鍵作成が禁止されている場合）
    if sa_email:
        source_credentials, _ = default()
        target_scopes = ['https://www.googleapis.com/auth/drive']
        credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=sa_email,
            target_scopes=target_scopes,
        )
    else:
        # ADC（Application Default Credentials）を直接使用
        credentials, _ = default(scopes=['https://www.googleapis.com/auth/drive'])

    return build('drive', 'v3', credentials=credentials)


def _find_or_create_folder(service, name, parent_id):
    """指定した親フォルダ内にフォルダを検索し、なければ作成する"""
    query = (
        f"name='{name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    results = service.files().list(
        q=query, spaces='drive', fields='files(id, name)', pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    # フォルダ作成
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
    logger.info(f"Created Drive folder: {name} (id={folder['id']})")
    return folder['id']


def upload_order_pdf(order):
    """
    注文書PDFをGoogleドライブにアップロードする。

    フォルダ構成: 共有フォルダ/注文書/パートナー会社名/order_XXXXX.pdf
    既存ファイルがあれば上書き（更新）する。

    Returns:
        dict: {'file_id': str, 'url': str} アップロード結果
    Raises:
        Exception: アップロードに失敗した場合
    """
    from googleapiclient.http import MediaIoBaseUpload

    root_folder_id = getattr(settings, 'GOOGLE_DRIVE_ROOT_FOLDER_ID', None)
    if not root_folder_id:
        raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID が設定されていません。settings.py を確認してください。")

    service = _get_drive_service()

    # 1. パートナー会社名フォルダを検索/作成（ROOT直下）
    partner_name = order.partner.name
    partner_folder_id = _find_or_create_folder(service, partner_name, root_folder_id)

    # 3. PDFファイル名
    filename = f"order_{order.order_id}.pdf"

    # 4. 既存ファイルを検索（上書き用）
    query = (
        f"name='{filename}' and "
        f"'{partner_folder_id}' in parents and "
        f"trashed=false"
    )
    results = service.files().list(
        q=query, spaces='drive', fields='files(id)', pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    existing_files = results.get('files', [])

    # 5. PDFデータを取得
    if order.order_pdf:
        order.order_pdf.seek(0)
        pdf_data = order.order_pdf.read()
    else:
        from .pdf_generator import generate_order_pdf
        buffer = generate_order_pdf(order)
        pdf_data = buffer.getvalue()

    media = MediaIoBaseUpload(
        io.BytesIO(pdf_data),
        mimetype='application/pdf',
        resumable=True
    )

    # 6. アップロード or 更新
    if existing_files:
        file_id = existing_files[0]['id']
        file = service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        logger.info(f"Updated Drive file: {filename} (id={file['id']})")
    else:
        file_metadata = {
            'name': filename,
            'parents': [partner_folder_id],
        }
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        logger.info(f"Uploaded to Drive: {filename} (id={file['id']})")

    return {
        'file_id': file['id'],
        'url': file.get('webViewLink', f"https://drive.google.com/file/d/{file['id']}/view"),
    }
