"""
Google Drive連携サービス（共通モジュール）

全ドキュメントタイプ（契約書・注文書・支払通知書）のGoogle Driveアップロードを統一管理する。
  - サービスアカウントキーファイル認証（共有ドライブ対応）
  - ドキュメントタイプ別フォルダIDの管理
  - パートナー別サブフォルダの自動作成
"""
import io
import os
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────
# 内部ヘルパー
# ──────────────────────────────────────────

def _get_drive_service():
    """Google Drive APIサービスを取得する。認証情報がなければNoneを返す。"""
    credentials_file = getattr(settings, 'GOOGLE_DRIVE_CREDENTIALS_FILE', '')
    if not credentials_file or not os.path.exists(credentials_file):
        logger.info("[Google Drive] サービスアカウントキーが未設定のためスキップ")
        return None

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
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        logger.warning(f"[Google Drive] サービス初期化エラー: {e}")
        return None


def _get_folder_id(doc_type):
    """
    ドキュメントタイプに応じたフォルダIDを取得する。
    個別設定がなければROOT_FOLDER_IDにフォールバック。

    Args:
        doc_type: 'contract', 'order', 'payment'
    """
    folder_map = {
        'contract': 'GOOGLE_DRIVE_CONTRACT_FOLDER_ID',
        'order': 'GOOGLE_DRIVE_ORDER_FOLDER_ID',
        'payment': 'GOOGLE_DRIVE_PAYMENT_FOLDER_ID',
    }
    setting_name = folder_map.get(doc_type, '')
    folder_id = getattr(settings, setting_name, '') if setting_name else ''
    if not folder_id:
        folder_id = getattr(settings, 'GOOGLE_DRIVE_ROOT_FOLDER_ID', '')
    return folder_id


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


def _upload_file(service, pdf_content, filename, parent_id):
    """PDFファイルをアップロードし、(file_id, web_link) を返す。"""
    from googleapiclient.http import MediaInMemoryUpload

    media = MediaInMemoryUpload(pdf_content, mimetype='application/pdf')
    file_metadata = {
        'name': filename,
        'parents': [parent_id],
    }
    uploaded = service.files().create(
        body=file_metadata, media_body=media,
        fields='id, webViewLink',
        supportsAllDrives=True,
    ).execute()

    file_id = uploaded.get('id')
    web_link = uploaded.get('webViewLink', '')
    logger.info(f"[Google Drive] アップロード成功: {filename} (ID: {file_id})")
    print(f"[Google Drive] アップロード成功: {filename} (URL: {web_link})")
    return file_id, web_link


def _update_file(service, file_id, pdf_content):
    """既存ファイルを上書き更新する。"""
    from googleapiclient.http import MediaInMemoryUpload

    media = MediaInMemoryUpload(pdf_content, mimetype='application/pdf')
    updated = service.files().update(
        fileId=file_id,
        media_body=media,
        fields='id, webViewLink',
        supportsAllDrives=True,
    ).execute()
    logger.info(f"[Google Drive] 更新成功: {file_id}")
    return updated.get('id'), updated.get('webViewLink', '')


def _find_existing_file(service, filename, parent_id):
    """既存ファイルを検索する。見つかればfile_idを返す。"""
    query = (
        f"name='{filename}' and "
        f"'{parent_id}' in parents and "
        f"trashed=false"
    )
    results = service.files().list(
        q=query, spaces='drive', fields='files(id)', pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


# ──────────────────────────────────────────
# 公開API
# ──────────────────────────────────────────

def upload_contract_pdf(partner, pdf_content, signed_at):
    """
    承認済み契約書PDFをGoogle Driveにアップロードする。

    フォルダ構成: 契約書フォルダ/パートナー名/契約書_パートナー名_日付.pdf
    """
    folder_id = _get_folder_id('contract')
    if not folder_id:
        logger.info("[Google Drive] CONTRACT_FOLDER_IDが未設定のためスキップ")
        return None

    service = _get_drive_service()
    if not service:
        return None

    try:
        partner_folder_id = _find_or_create_folder(service, partner.name, folder_id)
        date_str = signed_at.strftime('%Y%m%d')
        filename = f"契約書_{partner.name}_{date_str}.pdf"
        file_id, _ = _upload_file(service, pdf_content, filename, partner_folder_id)
        return file_id
    except Exception as e:
        logger.warning(f"[Google Drive] 契約書アップロードエラー: {e}")
        print(f"[Google Drive] アップロードエラー: {e}")
        return None


def upload_order_pdf(order):
    """
    注文書PDFをGoogle Driveにアップロードする。
    既存ファイルがあれば上書き更新。

    フォルダ構成: 注文書フォルダ/パートナー名/order_注文番号.pdf

    Returns:
        dict: {'file_id': str, 'url': str}
    Raises:
        ValueError: フォルダIDが未設定の場合
    """
    folder_id = _get_folder_id('order')
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_ORDER_FOLDER_ID が未設定です。")

    service = _get_drive_service()
    if not service:
        raise ValueError("Google Drive サービスの初期化に失敗しました。")

    partner_folder_id = _find_or_create_folder(service, order.partner.name, folder_id)
    filename = f"order_{order.order_id}.pdf"

    # PDFデータ取得
    if order.order_pdf:
        order.order_pdf.seek(0)
        pdf_data = order.order_pdf.read()
    else:
        from orders.services.pdf_generator import generate_order_pdf
        buffer = generate_order_pdf(order)
        pdf_data = buffer.getvalue()

    # 既存ファイル検索（上書き用）
    existing_id = _find_existing_file(service, filename, partner_folder_id)
    if existing_id:
        file_id, web_link = _update_file(service, existing_id, pdf_data)
    else:
        file_id, web_link = _upload_file(service, pdf_data, filename, partner_folder_id)

    return {
        'file_id': file_id,
        'url': web_link or f"https://drive.google.com/file/d/{file_id}/view",
    }


def upload_payment_pdf(pdf_buffer, filename, folder_id=None):
    """
    支払通知書/請求書PDFをGoogle Driveにアップロードする。

    Args:
        pdf_buffer: PDFのバイトストリーム（seekable）
        filename: ファイル名
        folder_id: 保存先フォルダID（省略時はPAYMENT_FOLDER_IDを使用）

    Returns:
        GoogleドライブのファイルID
    """
    if folder_id is None:
        folder_id = _get_folder_id('payment')

    service = _get_drive_service()
    if not service:
        return ''

    from googleapiclient.http import MediaIoBaseUpload

    pdf_buffer.seek(0)
    media = MediaIoBaseUpload(
        pdf_buffer, mimetype='application/pdf', resumable=True
    )
    file_metadata = {
        'name': filename,
        'mimeType': 'application/pdf',
    }
    if folder_id:
        file_metadata['parents'] = [folder_id]

    uploaded = service.files().create(
        body=file_metadata, media_body=media,
        fields='id, webViewLink',
        supportsAllDrives=True,
    ).execute()

    file_id = uploaded.get('id', '')
    logger.info(f"[Google Drive] 支払通知書アップロード成功: {filename} (ID: {file_id})")
    return file_id


def get_drive_file_url(file_id):
    """DriveファイルIDからURLを生成"""
    return f"https://drive.google.com/file/d/{file_id}/view"
