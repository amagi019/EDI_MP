"""銀行マスタCSVインポートコマンド。

使い方:
    python manage.py import_bank_master path/to/bank_data.csv

CSVフォーマット（ヘッダー行あり、UTF-8）:
    銀行コード,銀行名,支店コード,支店名
    0001,みずほ銀行,001,東京営業部
    0001,みずほ銀行,004,丸の内支店
    ...
"""
import csv
from django.core.management.base import BaseCommand
from core.domain.models import BankMaster


class Command(BaseCommand):
    help = '銀行マスタCSVをインポートします'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='CSVファイルのパス')
        parser.add_argument(
            '--clear', action='store_true',
            help='インポート前に既存データを全削除する',
        )
        parser.add_argument(
            '--encoding', type=str, default='utf-8',
            help='CSVファイルのエンコーディング（デフォルト: utf-8）',
        )

    def handle(self, *args, **options):
        csv_path = options['csv_file']
        encoding = options['encoding']

        if options['clear']:
            deleted, _ = BankMaster.objects.all().delete()
            self.stdout.write(f'既存データ {deleted} 件を削除しました。')

        created = 0
        skipped = 0
        errors = 0

        with open(csv_path, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)

            # ヘッダー名の柔軟な対応
            fieldnames = reader.fieldnames
            if not fieldnames:
                self.stderr.write('CSVファイルにヘッダー行がありません。')
                return

            # カラム名のマッピング（よくあるパターンに対応）
            col_map = {}
            for name in fieldnames:
                stripped = name.strip().replace('\ufeff', '')
                if stripped in ('銀行コード', 'bank_code', '金融機関コード'):
                    col_map['bank_code'] = name
                elif stripped in ('銀行名', 'bank_name', '金融機関名'):
                    col_map['bank_name'] = name
                elif stripped in ('支店コード', 'branch_code', '店舗コード'):
                    col_map['branch_code'] = name
                elif stripped in ('支店名', 'branch_name', '店舗名'):
                    col_map['branch_name'] = name

            required = ['bank_code', 'bank_name', 'branch_code', 'branch_name']
            missing = [k for k in required if k not in col_map]
            if missing:
                self.stderr.write(
                    f'必須カラムが見つかりません: {missing}\n'
                    f'検出されたヘッダー: {fieldnames}'
                )
                return

            batch = []
            for row in reader:
                try:
                    bank_code = row[col_map['bank_code']].strip()
                    bank_name = row[col_map['bank_name']].strip()
                    branch_code = row[col_map['branch_code']].strip()
                    branch_name = row[col_map['branch_name']].strip()

                    if not bank_code or not branch_code:
                        skipped += 1
                        continue

                    batch.append(BankMaster(
                        bank_code=bank_code,
                        bank_name=bank_name,
                        branch_code=branch_code,
                        branch_name=branch_name,
                    ))
                    created += 1

                    # 1000件ごとにバルクインサート
                    if len(batch) >= 1000:
                        BankMaster.objects.bulk_create(
                            batch, ignore_conflicts=True
                        )
                        batch = []
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        self.stderr.write(f'行エラー: {e} - {row}')

            # 残りを挿入
            if batch:
                BankMaster.objects.bulk_create(batch, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(
            f'完了: {created} 件インポート, {skipped} 件スキップ, {errors} 件エラー'
        ))
