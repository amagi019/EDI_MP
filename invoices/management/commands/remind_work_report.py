"""
稼働報告書提出リマインドメール自動送信コマンド

月末3営業日前にパートナーへ稼働報告書の提出を促すメールを送信する。

Usage:
    # 通常実行（月末3営業日前のみ送信）
    python manage.py remind_work_report

    # プレビュー（送信せずに対象を表示）
    python manage.py remind_work_report --dry-run

    # 日付チェックをスキップして強制送信
    python manage.py remind_work_report --force

    # プレビュー + 日付スキップ
    python manage.py remind_work_report --dry-run --force
"""
import datetime
from calendar import monthrange

from django.core.management.base import BaseCommand

import jpholiday

from orders.models import OrderBasicInfo
from core.domain.models import SentEmailLog
from core.utils import compose_work_report_reminder_email, send_system_mail


class Command(BaseCommand):
    help = '稼働報告書提出リマインドメールをパートナーへ送信する（月末3営業日前）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='送信せずに対象パートナーを表示する',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='日付チェックをスキップして強制的に送信する',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        today = datetime.date.today()

        # 今月の月末3営業日前を計算
        deadline = self._calc_business_days_before_month_end(today, 3)

        if not force and today != deadline:
            self.stdout.write(
                f"今日（{today}）は月末3営業日前（{deadline}）ではありません。"
                f" --force オプションで強制実行できます。"
            )
            return

        self.stdout.write(f"対象月: {today.strftime('%Y年%m月')}")
        self.stdout.write(f"締切日: {deadline.strftime('%m月%d日')}")
        self.stdout.write("")

        # 有効な発注基本情報を取得（プロジェクト期間内のもの）
        active_infos = OrderBasicInfo.objects.filter(
            project_end_date__gte=today,
        ).select_related('partner', 'project')

        if not active_infos.exists():
            self.stdout.write(self.style.WARNING("有効な発注基本情報がありません。"))
            return

        target_month_str = today.strftime('%Y年%m月')
        deadline_str = deadline.strftime('%m月%d日')
        sent_count = 0
        skip_count = 0

        for info in active_infos:
            partner = info.partner
            project = info.project

            if not partner.email:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP: {partner.name}（メールアドレスなし）"
                ))
                skip_count += 1
                continue

            # 同月の同パートナー・同テーマへの送信済みチェック
            already_sent = SentEmailLog.objects.filter(
                partner=partner,
                subject__contains='稼働報告書ご提出のお願い',
                sent_at__year=today.year,
                sent_at__month=today.month,
            ).exists()

            if already_sent and not force:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP: {partner.name} × {project.name}（今月送信済み）"
                ))
                skip_count += 1
                continue

            # メール作成
            subject, body = compose_work_report_reminder_email(
                partner=partner,
                project_name=project.name,
                target_month_str=target_month_str,
                deadline_str=deadline_str,
            )

            if dry_run:
                self.stdout.write(self.style.SUCCESS(
                    f"  [DRY-RUN] {partner.name} × {project.name} → {partner.email}"
                ))
                self.stdout.write(f"    件名: {subject}")
                continue

            # 送信
            try:
                send_system_mail(
                    subject, body,
                    [partner.email],
                )

                # 送信ログ記録
                SentEmailLog.objects.create(
                    partner=partner,
                    subject=subject,
                    body=body,
                    recipient=partner.email,
                )

                sent_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  SENT: {partner.name} × {project.name} → {partner.email}"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"  ERROR: {partner.name} → {partner.email}: {e}"
                ))

        self.stdout.write("")
        if dry_run:
            self.stdout.write(f"[DRY-RUN] 送信対象: {active_infos.count() - skip_count}件")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"送信完了: {sent_count}件, スキップ: {skip_count}件"
            ))

    @staticmethod
    def _calc_business_days_before_month_end(today, days_before):
        """月末からdays_before営業日前の日付を計算する。"""
        _, last_day = monthrange(today.year, today.month)
        dt = datetime.date(today.year, today.month, last_day)

        count = 0
        while count < days_before:
            dt -= datetime.timedelta(days=1)
            # 土日チェック
            if dt.weekday() >= 5:
                continue
            # 祝日チェック
            if jpholiday.is_holiday(dt):
                continue
            count += 1

        return dt
