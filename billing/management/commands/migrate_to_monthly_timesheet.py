"""
StaffTimesheet + WorkReport → MonthlyTimesheet データ移行コマンド
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'StaffTimesheet と WorkReport のデータを MonthlyTimesheet に移行する'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='実行せずに確認のみ')

    def handle(self, *args, **options):
        from billing.domain.models import StaffTimesheet, MonthlyTimesheet, ReceivedOrder
        from invoices.models import WorkReport
        dry_run = options['dry_run']

        self.stdout.write(self.style.NOTICE('=== MonthlyTimesheet データ移行 ==='))

        # 1. StaffTimesheet → MonthlyTimesheet (INTERNAL)
        staff_count = 0
        for ts in StaffTimesheet.objects.all():
            exists = MonthlyTimesheet.objects.filter(
                report_type='INTERNAL',
                worker_name=ts.worker_name,
                target_month=ts.target_month.replace(day=1),
                received_order=ts.order,
            ).exists()
            if exists:
                self.stdout.write(f'  SKIP (既存): {ts.worker_name} {ts.target_month}')
                continue

            if not dry_run:
                MonthlyTimesheet.objects.create(
                    report_type='INTERNAL',
                    worker_name=ts.worker_name,
                    worker_type=ts.worker_type,
                    employee_id=ts.employee_id,
                    target_month=ts.target_month.replace(day=1),
                    status=ts.status,
                    order=None,  # StaffTimesheet には Order FK なし
                    received_order=ts.order,  # ReceivedOrder
                    received_order_item=ts.order_item,
                    total_hours=ts.total_hours,
                    work_days=ts.work_days,
                    overtime_hours=ts.overtime_hours,
                    night_hours=ts.night_hours,
                    holiday_hours=ts.holiday_hours,
                    daily_data=ts.daily_data,
                    excel_file=ts.excel_file.name if ts.excel_file else '',
                    pdf_file=ts.pdf_file.name if ts.pdf_file else '',
                    original_filename=ts.original_filename,
                    drive_file_id=ts.drive_file_id,
                )
            staff_count += 1
            self.stdout.write(f'  移行: StaffTimesheet → {ts.worker_name} {ts.target_month}')

        # 2. WorkReport → MonthlyTimesheet (PARTNER)
        wr_count = 0
        for wr in WorkReport.objects.all():
            target = wr.target_month.replace(day=1) if wr.target_month else None
            if not target:
                self.stdout.write(self.style.WARNING(f'  SKIP (月なし): WR id={wr.pk}'))
                continue

            exists = MonthlyTimesheet.objects.filter(
                report_type='PARTNER',
                worker_name=wr.worker_name,
                target_month=target,
                order=wr.order,
            ).exists()
            if exists:
                self.stdout.write(f'  SKIP (既存): {wr.worker_name} {target}')
                continue

            if not dry_run:
                MonthlyTimesheet.objects.create(
                    report_type='PARTNER',
                    worker_name=wr.worker_name or '',
                    worker_type='PARTNER',
                    target_month=target,
                    status=wr.status,
                    order=wr.order,
                    received_order=None,
                    total_hours=wr.total_hours or 0,
                    work_days=wr.work_days or 0,
                    daily_data=wr.daily_data_json,
                    excel_file=wr.file.name if wr.file else '',
                    pdf_file=wr.pdf_file.name if wr.pdf_file else '',
                    original_filename=wr.original_filename,
                    drive_file_id=wr.drive_file_id,
                    uploaded_by=wr.uploaded_by,
                    uploaded_at=wr.uploaded_at,
                    alerts_json=wr.alerts_json,
                    error_message=wr.error_message,
                    sent_to_client_at=wr.sent_to_client_at,
                    client_shared_url=wr.client_shared_url or '',
                )
            wr_count += 1
            self.stdout.write(f'  移行: WorkReport → {wr.worker_name} {target}')

        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}完了: StaffTimesheet {staff_count}件, WorkReport {wr_count}件 → MonthlyTimesheet'
        ))
