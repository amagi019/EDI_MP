"""
勤怠報告サービス層

StaffTimesheetのビジネスロジック：
 - 受注ベースの勤怠報告作成
 - パートナーWorkReportとの連携
"""
import datetime
from decimal import Decimal
from billing.domain.models import (
    StaffTimesheet, ReceivedOrder, ReceivedOrderItem,
)


def create_timesheet(order, order_item, worker_name, worker_type,
                     target_month, total_hours, work_days,
                     daily_data=None, partner_report=None,
                     excel_file_path=None, original_filename=''):
    """勤怠報告を作成（Excelファイル原本の保存含む）"""
    ts = StaffTimesheet(
        order=order,
        order_item=order_item,
        worker_name=worker_name,
        worker_type=worker_type,
        target_month=target_month,
        total_hours=Decimal(str(total_hours)),
        work_days=work_days,
        daily_data=daily_data,
        status='DRAFT',
        partner_report=partner_report,
        original_filename=original_filename,
    )

    # 一時保存されたExcelファイルをTimesheetに紐付け
    if excel_file_path:
        try:
            from django.core.files.storage import default_storage
            from django.core.files.base import File
            import os

            if default_storage.exists(excel_file_path):
                # 一時ファイルを読み込んで正式パスに保存
                ext = os.path.splitext(excel_file_path)[1] or '.xlsx'
                final_name = f'timesheets/excel/{worker_name}_{target_month.strftime("%Y%m")}{ext}'
                with default_storage.open(excel_file_path, 'rb') as temp_file:
                    ts.excel_file.save(final_name, File(temp_file), save=False)
                # 一時ファイルを削除
                try:
                    default_storage.delete(excel_file_path)
                except Exception:
                    pass
        except Exception:
            pass

    ts.save()
    return ts


def submit_timesheet(timesheet):
    """勤怠報告を提出"""
    timesheet.status = 'SUBMITTED'
    timesheet.save()
    return timesheet


def mark_as_sent(timesheet):
    """勤怠報告を送付済みにする（手動送付時用）"""
    timesheet.status = 'SENT'
    timesheet.save()
    return timesheet


def approve_timesheet(timesheet):
    """勤怠報告を承認"""
    timesheet.status = 'APPROVED'
    timesheet.save()
    return timesheet


def calculate_ses_billing(order_item, total_hours):
    """
    SES精算計算（パートナー側と同じロジック）
    Returns: (base_fee, excess_amount, shortage_amount, subtotal)
    """
    base_fee = int(order_item.unit_price * order_item.man_month)
    lower = float(order_item.time_lower_limit)
    upper = float(order_item.time_upper_limit)
    hours = float(total_hours)

    excess_amount = 0
    shortage_amount = 0

    if hours > upper and order_item.excess_rate > 0:
        excess_amount = int((hours - upper) * order_item.excess_rate)
    elif hours < lower and order_item.shortage_rate > 0:
        shortage_amount = int((lower - hours) * order_item.shortage_rate)

    subtotal = base_fee + excess_amount - shortage_amount
    return base_fee, excess_amount, shortage_amount, subtotal


def send_work_report_email(timesheet, subject=None, body=None, sender_email=None):
    """
    勤怠報告（作業報告書）をメールで送信する。
    Excelファイル原本がある場合はそれを添付する。

    Args:
        timesheet: StaffTimesheet
        subject: カスタム件名
        body: カスタム本文
        sender_email: 送信元（省略時はDEFAULT_FROM_EMAIL）

    Returns:
        dict: {'sent': True/False, 'errors': list}
    """
    from django.core.mail import EmailMessage
    from django.conf import settings
    import logging

    logger = logging.getLogger(__name__)
    result = {'sent': False, 'errors': []}

    order = timesheet.order
    customer = order.customer

    # 送信先: 受注の報告書送信先 → 取引先のメールにフォールバック
    to_email = order.report_to_email or customer.email
    if not to_email:
        result['errors'].append(f'{customer.name}のメールアドレスが未設定です。')
        return result

    from_email = sender_email or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
    to_list = [to_email]
    cc_list = []
    # CC: 受注のCC → 取引先のCCにフォールバック
    cc_source = order.report_cc_emails or customer.cc_email
    if cc_source:
        cc_list = [e.strip() for e in cc_source.split(',') if e.strip()]

    # メール構築
    email_subject = subject or f'{timesheet.worker_name}の稼働報告'
    email_body = body or _build_default_body(timesheet, order, customer)

    try:
        email = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email=from_email,
            to=to_list,
            cc=cc_list,
        )

        # Excelファイル原本を添付（あれば）
        if timesheet.excel_file:
            try:
                filename = timesheet.original_filename or f'作業報告書_{timesheet.worker_name}_{timesheet.target_month.strftime("%Y%m")}.xlsx'
                timesheet.excel_file.open('rb')
                email.attach(filename, timesheet.excel_file.read(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                timesheet.excel_file.close()
            except Exception as e:
                logger.warning(f'[Timesheet] Excelファイル添付スキップ: {e}')

        email.send()
        result['sent'] = True

        # 送信成功時にステータスを「送付済み」に更新
        if timesheet.status in ('DRAFT', 'SUBMITTED'):
            timesheet.status = 'SENT'
            timesheet.save(update_fields=['status'])

        logger.info(f'[Timesheet] 作業報告書メール送信: {to_email} ({timesheet.worker_name})')
    except Exception as e:
        result['errors'].append(f'メール送信エラー: {e}')
        logger.error(f'[Timesheet] メール送信エラー: {e}')

    return result


def _build_default_body(timesheet, order, customer):
    """作業報告書のデフォルトメール本文を構築"""
    from core.domain.models import CompanyInfo

    company = CompanyInfo.objects.first()

    contact = customer.contact_person or customer.name
    company_name = company.name if company else ''
    sender_name = company.contact_person if company else ''
    sender_email_addr = company.email if company else ''
    sender_phone = company.phone if company else ''

    work_start = order.work_start.strftime('%Y年%m月%d日') if order.work_start else ''
    work_end = order.work_end.strftime('%Y年%m月%d日') if order.work_end else ''

    body = (
        f'{customer.name}　{contact}様\n\n'
        f'お世話になっております。{company_name}　{sender_name}です。\n\n'
        f'{timesheet.worker_name}の稼働報告 を送付いたします。\n'
        f'ご確認お願いいたします。\n\n'
        f'注文番号：{order.order_number}\n'
        f'業務名：{order.project_name}\n'
        f'作業期間：{work_start} ～ {work_end}\n'
        f'作業責任者：{timesheet.worker_name}\n\n'
        f'--\n'
        f'*******************************************\n'
        f'{company_name}\n'
        f'{sender_name}\n'
        f'Mail：{sender_email_addr}\n'
        f'TEL：{sender_phone}\n'
        f'*******************************************\n'
    )
    return body
