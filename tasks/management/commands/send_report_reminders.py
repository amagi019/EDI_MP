"""
稼働報告書提出リマインドメール送信コマンド

月末3営業日前に、未提出の稼働報告書についてパートナーへリマインドメールを送信する。

Usage:
    # 通常実行（月末3営業日前のみ送信）
    python manage.py send_report_reminders

    # ドライラン（送信せず対象を表示）
    python manage.py send_report_reminders --dry-run

    # 日付チェックをスキップして強制送信
    python manage.py send_report_reminders --force

    # cron設定例（毎日9:00に実行）
    0 9 * * * cd /share/Container/EDI_MP && docker compose -f docker-compose.nas.yml exec -T web python manage.py send_report_reminders
"""
import datetime
import calendar
import logging

import jpholiday
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

from tasks.models import MonthlyTask
from core.utils import compose_work_report_reminder_email

logger = logging.getLogger(__name__)


def get_business_days_before_month_end(year, month, n_days):
    """
    指定月の月末からn営業日前の日付を返す。
    営業日 = 土日・祝日を除いた平日。
    """
    last_day = calendar.monthrange(year, month)[1]
    current = datetime.date(year, month, last_day)
    count = 0

    while count < n_days:
        current -= datetime.timedelta(days=1)
        # 平日かつ祝日でなければ営業日
        if current.weekday() < 5 and not jpholiday.is_holiday(current):
            count += 1

    return current


def is_reminder_day(today, n_days=3):
    """今日が月末n営業日前かどうかを判定する。"""
    target = get_business_days_before_month_end(today.year, today.month, n_days)
    return today == target


class Command(BaseCommand):
    help = '月末3営業日前に稼働報告書の提出リマインドメールをパートナーに送信する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='メール送信せずに対象を表示する',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='日付チェックをスキップして強制送信する',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=3,
            help='月末から何営業日前にリマインドするか（デフォルト: 3）',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        n_days = options['days']
        today = datetime.date.today()

        self.stdout.write(f'実行日: {today}')
        self.stdout.write(f'月末{n_days}営業日前: {get_business_days_before_month_end(today.year, today.month, n_days)}')

        # 日付チェック
        if not force and not is_reminder_day(today, n_days):
            self.stdout.write(self.style.WARNING(
                f'今日は月末{n_days}営業日前ではありません。--force で強制送信できます。'
            ))
            return

        # 対象タスクを取得
        pending_reports = MonthlyTask.objects.filter(
            task_type='REPORT_UPLOAD',
            status='PENDING',
            reminder_sent=False,
        ).select_related('partner', 'project')

        if not pending_reports.exists():
            self.stdout.write(self.style.SUCCESS('リマインド対象のタスクはありません。'))
            return

        self.stdout.write(f'対象タスク: {pending_reports.count()}件')
        self.stdout.write('-' * 60)

        sent_count = 0
        error_count = 0

        for task in pending_reports:
            partner = task.partner
            project = task.project
            target_month_str = task.work_month.strftime('%Y年%m月')
            deadline_str = task.deadline.strftime('%Y年%m月%d日')

            self.stdout.write(
                f'  {partner.name} / {project.name} / '
                f'{target_month_str} / 期限: {deadline_str}'
            )

            if dry_run:
                self.stdout.write(self.style.WARNING('    → [DRY RUN] スキップ'))
                continue

            if not partner.email:
                self.stdout.write(self.style.ERROR(f'    → メールアドレス未設定'))
                error_count += 1
                continue

            # メール生成
            subject, body = compose_work_report_reminder_email(
                partner=partner,
                project_name=project.name,
                target_month_str=target_month_str,
                deadline_str=deadline_str,
            )

            # メール送信
            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [partner.email],
                    fail_silently=False,
                )
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'    → 送信完了: {partner.email}'
                ))
                logger.info(
                    f'[リマインド送信] {partner.name} ({partner.email}) '
                    f'/ {project.name} / {target_month_str}'
                )
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'    → 送信失敗: {e}'))
                logger.error(
                    f'[リマインド送信エラー] {partner.name}: {e}'
                )

        self.stdout.write('-' * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'ドライラン完了: {pending_reports.count()}件が対象'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'送信完了: {sent_count}件, エラー: {error_count}件'
            ))
