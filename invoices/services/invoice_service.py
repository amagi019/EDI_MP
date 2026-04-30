"""
請求書・稼働報告書サービス層 — ビューからビジネスロジックを分離
"""
import logging

from django.urls import reverse

from core.utils import get_notify_email, normalize_name, compose_invoice_approve_email, send_system_mail
from core.domain.models import SentEmailLog
from ..models import Invoice, InvoiceItem

logger = logging.getLogger(__name__)


def confirm_invoice(invoice, partner, request):
    """
    パートナーによる請求書（支払通知書）の承諾処理。
    - ステータス更新（CONFIRMED）
    - 自社担当者へ通知メール
    Returns: (email_sent: bool)
    """
    invoice.status = 'CONFIRMED'
    invoice.save()

    invoice_url = request.build_absolute_uri(
        reverse('invoices:invoice_detail', kwargs={'invoice_id': invoice.pk})
    )
    subject, message = compose_invoice_approve_email(invoice, partner, invoice_url)
    notify_email = get_notify_email(partner)

    email_sent = False
    try:
        send_system_mail(subject, message, [notify_email])
        email_sent = True
        SentEmailLog.objects.create(
            partner=invoice.order.partner, subject=subject,
            body=message, recipient=notify_email,
        )
    except Exception as e:
        logger.warning(f"請求書承諾通知メール送信失敗: {e}")

    return email_sent


def approve_work_reports(reports, user, request):
    """
    パートナーによる稼働報告書の確定処理。
    - ステータス更新（APPROVED）
    - InvoiceItemへの自動連携
    - 月次タスク完了
    - 自社担当者へ通知メール
    Returns: (linked_count: int, email_sent: bool)
    """
    linked_count = 0
    for r in reports:
        r.status = 'APPROVED'
        r.save()

        # 月次タスク（REPORT_UPLOAD）を完了にする
        from tasks.services import complete_report_upload
        complete_report_upload(r)

        # InvoiceItem に作業時間を自動セット
        if r.total_hours and r.target_month and r.worker_name:
            linked = _link_to_invoice_item(r)
            if linked:
                linked_count += 1

    # 自社担当者にメール通知
    email_sent = _send_work_report_notification(reports, user, request)

    return linked_count, email_sent


def _link_to_invoice_item(report):
    """
    確定済みMonthlyTimesheetの作業時間をInvoiceItemに自動セットする。
    対象のInvoice/InvoiceItemがなければ作成する。
    """
    from .billing_calculator import BillingCalculator

    order = report.order

    invoice = Invoice.objects.filter(
        order=order,
        target_month=report.target_month,
    ).first()

    if not invoice:
        invoice = Invoice(
            order=order,
            target_month=report.target_month,
            status='DRAFT',
        )
        invoice.save()

    # 同じ作業者名のInvoiceItemを探す
    report_name_norm = normalize_name(report.worker_name)
    item = None
    for candidate in InvoiceItem.objects.filter(invoice=invoice):
        if normalize_name(candidate.person_name) == report_name_norm:
            item = candidate
            break

    if item:
        item.work_time = report.total_hours
        item.save()
    else:
        from orders.models import OrderItem
        order_item = None
        for candidate in OrderItem.objects.filter(order=order):
            if normalize_name(candidate.person_name) == report_name_norm:
                order_item = candidate
                break

        if not order_item:
            logger.warning(
                f'氏名マッチなし: MonthlyTimesheet "{report.worker_name}" に対応する'
                f'OrderItemが見つかりません（注文: {order.order_id}）。'
                f'精算条件なしでInvoiceItemを作成します。'
            )

        item = InvoiceItem(
            invoice=invoice,
            person_name=report.worker_name,
            work_time=report.total_hours,
        )
        if order_item:
            item.base_fee = order_item.base_fee
            item.time_lower_limit = order_item.time_lower_limit
            item.time_upper_limit = order_item.time_upper_limit
            item.shortage_rate = order_item.shortage_rate
            item.excess_rate = order_item.excess_rate
        item.save()

    try:
        BillingCalculator.calculate_invoice(invoice)
    except Exception as e:
        logger.warning(f'請求額計算エラー: {e}')

    return True


def _send_work_report_notification(reports, user, request):
    """稼働報告書確定通知メールを自社担当者に送信する。"""
    if not reports:
        return False

    first_report = reports[0]
    report_partner = first_report.order.partner
    notify_email = get_notify_email(report_partner)

    report_lines = []
    for r in reports:
        month_str = r.target_month.strftime('%Y年%m月') if r.target_month else '不明'
        alerts_text = ''
        if r.alerts_json:
            alerts_text = f'  ⚠ 土日祝稼働 {len(r.alerts_json)}件'
        report_lines.append(
            f"  ・{r.worker_name or '氏名不明'}: {r.total_hours}h / {r.work_days}日{alerts_text}"
        )

    month_display = first_report.target_month.strftime('%Y年%m月') if first_report.target_month else '不明'
    subject = f"【稼働報告書確定】{report_partner.name} - {month_display}"
    body = f"""{report_partner.name} の稼働報告書がパートナーにより確定されました。

■パートナー：{report_partner.name}
■対象月：{month_display}
■確定者：{user.username}

■報告内容：
{chr(10).join(report_lines)}

EDIシステムにログインして内容を確認してください。
"""
    email_sent = False
    try:
        send_system_mail(subject, body, [notify_email])
        email_sent = True
        SentEmailLog.objects.create(
            partner=report_partner, subject=subject,
            body=body, recipient=notify_email,
        )
    except Exception as e:
        logger.warning(f"稼働報告書確定通知メール送信失敗: {e}")

    return email_sent
