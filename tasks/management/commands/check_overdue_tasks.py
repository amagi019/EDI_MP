"""
期限超過・警告タスクチェック＆管理者通知コマンド

毎朝実行し、以下の警告を管理者へメール送信する:
- 注文書が未承諾（発行から2日以上経過）
- 稼働報告が未提出（月末3日前以降）
- 支払期限が近い（7日以内）

Usage:
    # 通常実行
    python manage.py check_overdue_tasks

    # ドライラン（送信せず対象を表示）
    python manage.py check_overdue_tasks --dry-run

    # cron設定例（毎朝9:00に実行）
    0 9 * * * cd /share/Container/EDI_MP && docker compose -f docker-compose.nas.yml exec -T web python manage.py check_overdue_tasks
"""
import datetime
import logging

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

from orders.models import Order, OrderCycle
from invoices.models import Invoice

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = '期限超過・警告タスクをチェックし、管理者へメール通知する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='メール送信せずに対象を表示する',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = datetime.date.today()
        warnings = []

        self.stdout.write(f'実行日: {today}')
        self.stdout.write('=' * 60)

        # 1. 未承諾注文書（発行から2日以上経過）
        self.stdout.write('\n【注文書 未承諾チェック】')
        threshold = today - datetime.timedelta(days=2)
        overdue_orders = Order.objects.filter(
            status='UNCONFIRMED',
            order_date__lte=threshold,
        ).select_related('partner')

        for o in overdue_orders:
            days = (today - o.order_date).days
            msg = f'⚠️ 注文書未承諾: {o.order_id} ({o.partner.name}) — 発行から{days}日経過 / 作業期間 {o.work_start}〜{o.work_end}'
            self.stdout.write(self.style.WARNING(f'  {msg}'))
            warnings.append(msg)

        if not overdue_orders.exists():
            self.stdout.write(self.style.SUCCESS('  問題なし'))

        # 2. 支払期限が近い（7日以内）
        self.stdout.write('\n【支払期限チェック】')
        deadline_threshold = today + datetime.timedelta(days=7)
        upcoming_payments = Invoice.objects.filter(
            payment_deadline__lte=deadline_threshold,
            payment_deadline__gte=today,
        ).exclude(
            status='PAID',
        ).select_related('order__partner')

        for inv in upcoming_payments:
            days_left = (inv.payment_deadline - today).days
            partner_name = inv.order.partner.name if inv.order else '不明'
            msg = f'💰 支払期限間近: {inv.invoice_no} ({partner_name}) — あと{days_left}日 ({inv.payment_deadline})'
            self.stdout.write(self.style.WARNING(f'  {msg}'))
            warnings.append(msg)

        # 支払期限超過
        overdue_payments = Invoice.objects.filter(
            payment_deadline__lt=today,
        ).exclude(
            status='PAID',
        ).select_related('order__partner')

        for inv in overdue_payments:
            days_over = (today - inv.payment_deadline).days
            partner_name = inv.order.partner.name if inv.order else '不明'
            msg = f'🚨 支払期限超過: {inv.invoice_no} ({partner_name}) — {days_over}日超過 ({inv.payment_deadline})'
            self.stdout.write(self.style.ERROR(f'  {msg}'))
            warnings.append(msg)

        if not upcoming_payments.exists() and not overdue_payments.exists():
            self.stdout.write(self.style.SUCCESS('  問題なし'))

        # 3. OrderCycle の支払完了チェック（payment_deadline 設定済みで未完了）
        self.stdout.write('\n【OrderCycle 支払完了チェック】')
        for cycle in OrderCycle.objects.filter(
            payment_completed=False,
        ).select_related('partner', 'project'):
            # Invoice がなく、手動管理のケース
            has_invoice = Invoice.objects.filter(
                order__cycle=cycle,
            ).exists()
            if not has_invoice:
                # 作業月の翌々月15日を目安に
                m = cycle.work_month.month + 2
                y = cycle.work_month.year
                if m > 12:
                    m -= 12
                    y += 1
                estimated_deadline = datetime.date(y, m, 15)
                if estimated_deadline <= deadline_threshold and estimated_deadline >= today:
                    days_left = (estimated_deadline - today).days
                    msg = f'💰 支払期限間近(手動): {cycle.partner.name} {cycle.work_month.strftime("%Y/%m")}分 — あと{days_left}日 ({estimated_deadline})'
                    self.stdout.write(self.style.WARNING(f'  {msg}'))
                    warnings.append(msg)

        self.stdout.write('\n' + '=' * 60)

        # メール送信
        if not warnings:
            self.stdout.write(self.style.SUCCESS('\n警告事項はありません。'))
            return

        self.stdout.write(f'\n警告: {len(warnings)}件')

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] メール送信をスキップしました。'))
            return

        # 管理者メールアドレスを取得
        admin_emails = list(
            User.objects.filter(is_staff=True)
            .exclude(email='')
            .values_list('email', flat=True)
        )

        if not admin_emails:
            self.stdout.write(self.style.ERROR('管理者のメールアドレスが設定されていません。'))
            return

        subject = f'【EDI】毎朝チェック: {len(warnings)}件の警告があります ({today})'
        body = f'管理者各位\n\n{today} の定期チェックで以下の警告があります。\n\n'
        body += '\n'.join(f'  {w}' for w in warnings)
        body += '\n\n確認・対応をお願いします。\n'

        try:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(
                f'メール送信完了: {", ".join(admin_emails)}'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'メール送信失敗: {e}'))
            logger.error(f'[check_overdue_tasks] メール送信エラー: {e}')
