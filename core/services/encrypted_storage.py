"""
暗号化ファイルストレージバックエンド

アップロードされたファイルを Fernet (AES-128-CBC) で暗号化して保存し、
読み取り時に自動的に復号する Django カスタムストレージ。

使い方:
    from core.services.encrypted_storage import EncryptedFileSystemStorage

    class MyModel(models.Model):
        file = models.FileField(storage=EncryptedFileSystemStorage())

鍵管理:
    - 環境変数 FILE_ENCRYPTION_KEY に Fernet 鍵を設定
    - `python manage.py generate_encryption_key` で鍵を生成可能
    - 鍵未設定時は平文保存にフォールバック（開発環境用）
"""

import io
import logging

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage

logger = logging.getLogger(__name__)

# 暗号化済みファイルを識別するマジックバイト列（16バイト）
ENCRYPTION_MARKER = b'EDIENC:FERNET:v1'
MARKER_LENGTH = len(ENCRYPTION_MARKER)


def _get_fernet():
    """Fernet インスタンスを取得する。鍵未設定時は None を返す。"""
    key = getattr(settings, 'FILE_ENCRYPTION_KEY', '')
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error(f'[EncryptedStorage] Fernet 初期化エラー: {e}')
        return None


def _is_encrypted(data: bytes) -> bool:
    """データが暗号化済みかどうかを判定する。"""
    return data[:MARKER_LENGTH] == ENCRYPTION_MARKER


class EncryptedFileSystemStorage(FileSystemStorage):
    """
    ファイルを暗号化して保存する FileSystemStorage のサブクラス。

    - _save: ファイル保存時に暗号化
    - _open: ファイル読み取り時に復号
    - 暗号化済みファイルには先頭に ENCRYPTION_MARKER を付与
    - 既存の平文ファイルはそのまま読み取り可能（フォールバック）
    """

    def _save(self, name, content):
        """ファイル保存時に暗号化する。"""
        fernet = _get_fernet()

        if fernet is None:
            # 鍵未設定: 平文で保存
            return super()._save(name, content)

        try:
            # ファイル内容を読み取り
            raw_data = content.read()
            if isinstance(raw_data, str):
                raw_data = raw_data.encode('utf-8')

            # 既に暗号化済みの場合はそのまま保存（二重暗号化防止）
            if _is_encrypted(raw_data):
                content.seek(0)
                return super()._save(name, content)

            # 暗号化
            encrypted_data = fernet.encrypt(raw_data)

            # マーカー + 暗号化データ
            encrypted_content = ContentFile(ENCRYPTION_MARKER + encrypted_data)
            return super()._save(name, encrypted_content)

        except Exception as e:
            logger.error(f'[EncryptedStorage] 暗号化エラー ({name}): {e}')
            # 暗号化失敗時は平文で保存（データロス防止）
            content.seek(0)
            return super()._save(name, content)

    def _open(self, name, mode='rb'):
        """ファイル読み取り時に復号する。"""
        # まず通常通りファイルを開く
        f = super()._open(name, mode)

        if 'b' not in mode:
            return f

        fernet = _get_fernet()
        if fernet is None:
            return f

        try:
            raw_data = f.read()
            f.close()

            if not _is_encrypted(raw_data):
                # 平文ファイル（暗号化導入前のファイル）: そのまま返す
                return File(io.BytesIO(raw_data), name=name)

            # マーカーを除去して復号
            encrypted_data = raw_data[MARKER_LENGTH:]
            decrypted_data = fernet.decrypt(encrypted_data)

            return File(io.BytesIO(decrypted_data), name=name)

        except Exception as e:
            logger.error(f'[EncryptedStorage] 復号エラー ({name}): {e}')
            # 復号失敗時は元データをそのまま返す（アクセス不能にしない）
            f = super()._open(name, mode)
            return f


# シングルトンインスタンス（モデルフィールドで共有）
encrypted_storage = EncryptedFileSystemStorage()
