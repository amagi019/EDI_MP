"""
EDI API クライアント

PayrollSystemからEDIの勤怠データAPIを呼び出すためのクライアント。
"""
import json
import logging
import urllib.request
import urllib.error
from django.conf import settings

logger = logging.getLogger(__name__)


class EDIAPIClient:
    """EDIシステムのAPIクライアント"""

    def __init__(self):
        self.base_url = getattr(settings, 'EDI_API_URL', '')
        self.api_key = getattr(settings, 'EDI_API_KEY', '')

    @property
    def is_configured(self):
        """API接続が設定されているか"""
        return bool(self.base_url and self.api_key)

    def fetch_timesheets(self, year, month):
        """
        EDIから指定月の勤怠データを取得する。

        Args:
            year: 年（例: 2026）
            month: 月（例: 3）

        Returns:
            list[dict]: 勤怠データのリスト
            各要素は以下を含む:
                - employee_id: 社員番号
                - worker_name: 作業者名
                - worker_type: 要員種別 (INTERNAL/PARTNER)
                - total_hours: 合計稼働時間
                - work_days: 稼働日数
                - status: ステータス

        Raises:
            ConnectionError: API接続エラー
            PermissionError: 認証エラー
            RuntimeError: その他のAPIエラー
        """
        if not self.is_configured:
            raise RuntimeError(
                'EDI API未設定（EDI_API_URL, EDI_API_KEY を確認してください）'
            )

        url = (
            f"{self.base_url.rstrip('/')}"
            f"/billing/api/timesheets/?year={year}&month={month}"
        )
        req = urllib.request.Request(url)
        req.add_header('X-API-Key', self.api_key)
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise PermissionError('EDI API 認証エラー: APIキーを確認してください')
            raise RuntimeError(f'EDI API エラー: HTTP {e.code}')
        except urllib.error.URLError as e:
            raise ConnectionError(f'EDI 接続エラー: {e.reason}')

        return data.get('timesheets', [])
