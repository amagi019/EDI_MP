import logging
import uuid
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class SignatureServiceError(Exception):
    """電子署名サービス関連の基本エラー"""
    pass

class BaseSignatureProvider:
    """電子署名プロバイダーの基底クラス"""
    def send_document(self, order):
        raise NotImplementedError()

    def get_status(self, document_id):
        raise NotImplementedError()

class MockSignatureProvider(BaseSignatureProvider):
    """開発・テスト用のモックプロバイダー"""
    def __init__(self, api_key=None):
        self.api_key = api_key or "mock_secret_key"

    def _authenticate(self):
        """外部APIの認証をシミュレーション"""
        if not self.api_key:
            raise SignatureServiceError("API key is missing.")
        logger.info("Mock: Authenticated with e-signature provider.")
        return "mock_access_token_123"

    def send_document(self, order):
        # 実際には外部APIを叩く前の認証
        token = self._authenticate()
        
        signature_id = f"sig_{uuid.uuid4().hex[:8]}"
        logger.info(f"Mock: Document sent for signature using token {token}. ID: {signature_id}")
        return {
            'signature_id': signature_id,
            'status': 'SENT',
            'url': f"https://mock-signature.com/sign/{signature_id}"
        }

    def get_status(self, signature_id):
        # APIを叩いて現在のステータスを取得するシミュレーション
        return 'COMPLETED'

class GoogleDocsSignatureProvider(BaseSignatureProvider):
    """Google Docs API (e-signature feature) 連携プロバイダー"""
    def send_document(self, order):
        # 実装案: Google Drive APIでPDFをアップロードし、署名リクエストを作成する
        # 現段階ではスタブとして定義
        raise NotImplementedError("Google Docs API integration is coming in the next update.")

class SignatureService:
    """電子署名管理サービス"""
    def __init__(self):
        # settings からプロバイダー設定を取得することを想定
        provider_type = getattr(settings, 'SIGNATURE_PROVIDER', 'mock')
        if provider_type == 'mock':
            self.provider = MockSignatureProvider(api_key=getattr(settings, 'SIGNATURE_API_KEY', None))
        else:
            self.provider = GoogleDocsSignatureProvider()

    def request_signature(self, order):
        """注文書への署名を依頼する"""
        try:
            # ドラフト状態では依頼不可
            if order.status == 'DRAFT':
                raise SignatureServiceError("下書き状態の注文書には署名依頼できません。")
                
            result = self.provider.send_document(order)
            return result
        except SignatureServiceError as e:
            raise e
        except Exception as e:
            logger.error(f"Failed to request signature: {e}")
            raise SignatureServiceError(f"電子署名の依頼中に予期せぬエラーが発生しました: {e}")
