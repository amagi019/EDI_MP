"""
月次ルーチンタスクを自動生成する管理コマンド

OrderBasicInfo のプロジェクト期間と期限ルール設定に基づいて、
各月のタスク（注文書作成/承認、作業報告書、請求書作成/承認）を自動生成する。

使用方法:
  python manage.py generate_monthly_tasks          # 全プロジェクト対象
  python manage.py generate_monthly_tasks --months 3  # 今月から3ヶ月分
"""
import datetime
import calendar
from django.core.management.base import BaseCommand
from orders.models import OrderBasicInfo
from tasks.models import MonthlyTask
from tasks.scheduler import subtract_business_days


def last_day_of_month(year, month):
    """月末日を返す"""
    return calendar.monthrange(year, month)[1]


def get_prev_month(dt):
    """前月の1日を返す"""
    if dt.month == 1:
        return datetime.date(dt.year - 1, 12, 1)
    return datetime.date(dt.year, dt.month - 1, 1)


def get_next_month(dt):
    """翌月の1日を返す"""
    if dt.month == 12:
        return datetime.date(dt.year + 1, 1, 1)
    return datetime.date(dt.year, dt.month + 1, 1)


def generate_tasks_for_month(basic_info, work_month):
    """
    指定された作業月のタスク5件を生成する。
    期限はOrderBasicInfoの設定値を使用する。
    """
    bi = basic_info
    prev = get_prev_month(work_month)
    next_m = get_next_month(work_month)
    last_day = last_day_of_month(work_month.year, work_month.month)
    prev_last_day = last_day_of_month(prev.year, prev.month)

    tasks = [
        {
            'task_type': 'ORDER_CREATE',
            'responsible': 'STAFF',
            'deadline': datetime.date(prev.year, prev.month, min(bi.order_create_deadline_day, prev_last_day)),
        },
        {
            'task_type': 'ORDER_APPROVE',
            'responsible': 'PARTNER',
            'deadline': subtract_business_days(datetime.date(prev.year, prev.month, prev_last_day), bi.order_approve_deadline_days_before),
        },
        {
            'task_type': 'REPORT_UPLOAD',
            'responsible': 'PARTNER',
            'deadline': subtract_business_days(datetime.date(work_month.year, work_month.month, last_day), bi.report_upload_deadline_days_before),
        },
        {
            'task_type': 'INVOICE_CREATE',
            'responsible': 'STAFF',
            'deadline': datetime.date(next_m.year, next_m.month, min(bi.invoice_create_deadline_day, last_day_of_month(next_m.year, next_m.month))),
        },
        {
            'task_type': 'INVOICE_APPROVE',
            'responsible': 'PARTNER',
            'deadline': datetime.date(next_m.year, next_m.month, min(bi.invoice_approve_deadline_day, last_day_of_month(next_m.year, next_m.month))),
        },
    ]

    created_count = 0
    for task_data in tasks:
        _, created = MonthlyTask.objects.get_or_create(
            partner=basic_info.partner,
            project=basic_info.project,
            work_month=work_month,
            task_type=task_data['task_type'],
            defaults={
                'responsible': task_data['responsible'],
                'deadline': task_data['deadline'],
            }
        )
        if created:
            created_count += 1
    return created_count


class Command(BaseCommand):
    help = 'OrderBasicInfoに基づき月次ルーチンタスクを自動生成する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months', type=int, default=0,
            help='今月から指定月数分のタスクを生成（0=プロジェクト全期間）'
        )

    def handle(self, *args, **options):
        months_ahead = options['months']
        today = datetime.date.today()
        total_created = 0

        for bi in OrderBasicInfo.objects.select_related('partner', 'project').all():
            start = bi.project_start_date.replace(day=1)
            end = bi.project_end_date.replace(day=1)

            current = start
            while current <= end:
                if months_ahead > 0:
                    this_month = today.replace(day=1)
                    limit = this_month
                    for _ in range(months_ahead):
                        limit = get_next_month(limit)
                    if current < this_month or current >= limit:
                        current = get_next_month(current)
                        continue

                count = generate_tasks_for_month(bi, current)
                if count > 0:
                    self.stdout.write(
                        f"  {bi.partner.name} × {bi.project.name} "
                        f"{current.strftime('%Y/%m')}: {count}件生成"
                    )
                total_created += count
                current = get_next_month(current)

        self.stdout.write(self.style.SUCCESS(
            f"\n合計 {total_created}件 のタスクを生成しました。"
        ))
