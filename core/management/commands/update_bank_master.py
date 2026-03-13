"""銀行マスタをzengin-code APIから自動更新するコマンド。

使い方:
    python manage.py update_bank_master

データソース:
    https://zengin-code.github.io/api/banks.json  （銀行一覧）
    https://zengin-code.github.io/api/branches/{bank_code}.json （支店一覧）

cronでの定期実行例（毎月1日の午前3時）:
    0 3 1 * * docker exec edi-mp-web python manage.py update_bank_master
"""
import json
import logging
import ssl
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand
from django.db import transaction

from core.domain.models import BankMaster

logger = logging.getLogger(__name__)

API_BASE = 'https://zengin-code.github.io/api'

# 金融機関コード範囲 → 種別接尾辞マッピング
# 参考: https://www.zenginkyo.or.jp/
CODE_RANGE_SUFFIXES = [
    # (開始コード, 終了コード, 接尾辞)
    ('0001', '0032', '銀行'),      # 都市銀行・新たな形態の銀行
    ('0033', '0099', '銀行'),      # ネット銀行等
    ('0116', '0199', '銀行'),      # 地方銀行
    ('0501', '0599', '銀行'),      # 第二地方銀行
    ('1000', '1999', '信用金庫'),   # 信用金庫
    ('2000', '2999', '信用組合'),   # 信用組合
    ('3000', '3999', '農業協同組合'),  # 農協（JA）
    ('4000', '4999', '漁業協同組合'),  # 漁協
    ('5000', '5999', '労働金庫'),   # 労金
    ('9000', '9999', '銀行'),      # その他
]


class Command(BaseCommand):
    help = 'zengin-code APIから銀行マスタを自動更新します'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='実際のDB更新を行わず、取得件数のみ表示する',
        )

    def _get_ssl_context(self):
        """SSL コンテキストを取得（macOS Python 3.9 の証明書問題に対応）"""
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

    def _fetch_json(self, url):
        """URLからJSONデータを取得する"""
        req = urllib.request.Request(url, headers={
            'User-Agent': 'EDI-MP BankMaster Updater/1.0',
        })
        try:
            ctx = self._get_ssl_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as e:
            logger.error(f'API取得エラー: {url} - {e}')
            return None

    def _bank_display_name(self, code, name):
        """銀行コードと短縮名から表示用の銀行名を生成する"""
        # 既にフルネームの場合はそのまま返す
        suffixes = ('銀行', '信用金庫', '信金', '信用組合', '農協',
                    '労金', '労働金庫', '農業協同組合', '漁業協同組合', '信連')
        if any(name.endswith(s) for s in suffixes):
            return name
        # コード範囲から種別を判定
        for start, end, suffix in CODE_RANGE_SUFFIXES:
            if start <= code <= end:
                return name + suffix
        return name + '銀行'

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write('銀行一覧を取得中...')
        banks_data = self._fetch_json(f'{API_BASE}/banks.json')
        if banks_data is None:
            self.stderr.write(self.style.ERROR('銀行一覧の取得に失敗しました。'))
            return

        self.stdout.write(f'  {len(banks_data)} 件の銀行を取得')

        all_records = []
        error_count = 0

        for bank_code, bank_info in banks_data.items():
            bank_name = self._bank_display_name(bank_code, bank_info['name'])

            # 各銀行の支店一覧を取得
            branches_data = self._fetch_json(
                f'{API_BASE}/branches/{bank_code}.json'
            )
            if branches_data is None:
                error_count += 1
                if error_count <= 3:
                    self.stderr.write(f'  ⚠ {bank_name}({bank_code})の支店取得失敗')
                continue

            for branch_code, branch_info in branches_data.items():
                all_records.append(BankMaster(
                    bank_code=bank_code,
                    bank_name=bank_name,
                    branch_code=branch_code,
                    branch_name=branch_info['name'],
                ))

            if len(all_records) % 5000 == 0:
                self.stdout.write(f'  取得中... {len(all_records)} 件')

        self.stdout.write(f'合計 {len(all_records)} 件の支店データを取得')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] DB更新はスキップ。{len(all_records)} 件を取得済み。'
            ))
            return

        if not all_records:
            self.stderr.write(self.style.ERROR('取得データが0件のため更新をスキップします。'))
            return

        # トランザクション内で全件入れ替え
        self.stdout.write('データベースを更新中...')
        with transaction.atomic():
            deleted, _ = BankMaster.objects.all().delete()
            self.stdout.write(f'  既存データ {deleted} 件を削除')

            # バルクインサート（1000件ずつ）
            for i in range(0, len(all_records), 1000):
                BankMaster.objects.bulk_create(all_records[i:i+1000])

        self.stdout.write(self.style.SUCCESS(
            f'完了: {len(all_records)} 件をインポートしました。'
            f'（エラー: {error_count} 件）'
        ))
