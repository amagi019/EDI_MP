"""
稼働報告メール自動取込コマンド

メールサーバー（IMAP）に接続し、パートナーからの稼働報告メールを
自動的に取り込んでMonthlyTimesheetとして登録する。

使い方:
  python manage.py fetch_emails
  python manage.py fetch_emails --dry-run  # テスト実行（取込なし）
"""
from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'パートナーからの稼働報告メールを取り込む'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='テスト実行（実際の取込は行わない）',
        )

    def handle(self, *args, **options):
        from invoices.services.email_receiver import fetch_and_process_emails

        self.stdout.write(self.style.NOTICE('メール受信チェックを開始します...'))

        result = fetch_and_process_emails()

        # 結果出力
        self.stdout.write(f'  処理件数: {result["processed"]}件')
        self.stdout.write(f'  取込件数: {result["imported"]}件')

        for d in result.get('details', []):
            icon = '✅' if d.get('imported') else '⏭️'
            self.stdout.write(
                f'  {icon} {d.get("from", "")} | {d.get("subject", "")[:40]} '
                f'| {d.get("reason", "")}'
            )

        for e in result.get('errors', []):
            self.stdout.write(self.style.ERROR(f'  ❌ {e}'))

        if result['imported'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f'{result["imported"]}件の稼働報告メールを取り込みました。'
            ))
        else:
            self.stdout.write(self.style.NOTICE('取り込み対象のメールはありませんでした。'))
