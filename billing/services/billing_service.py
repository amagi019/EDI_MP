"""
請求連携サービス層

受注 + 勤怠報告 → BillingInvoice自動生成のビジネスロジック
"""
import datetime
from decimal import Decimal
from billing.domain.models import (
    BillingInvoice, BillingItem, ReceivedOrder, MonthlyTimesheet,
)
from billing.services.timesheet_service import calculate_ses_billing
from core.domain.models import CompanyInfo


def create_invoice_from_received_order(received_order, issue_date=None):
    """
    受注 + 承認済み勤怠報告から請求書を自動生成する。

    Returns:
        tuple: (BillingInvoice, item_count, warnings)
    """
    warnings = []
    issue_date = issue_date or datetime.date.today()

    # 自社情報
    company = CompanyInfo.objects.first()

    # 送付済み or 承認済み勤怠の取得
    timesheets = MonthlyTimesheet.objects.filter(
        order=received_order,
        status__in=['SENT', 'APPROVED'],
    )

    if not timesheets.exists():
        warnings.append('送付済みまたは承認済みの勤怠報告がありません。基本料金で請求書を作成します。')

    # 請求書作成
    invoice = BillingInvoice.objects.create(
        customer=received_order.customer,
        company=company,
        received_order=received_order,
        issue_date=issue_date,
        subject=received_order.project_name or f'{received_order.customer.name} - {received_order.target_month.strftime("%Y年%m月")}分',
        status='DRAFT',
    )

    item_count = 0

    if timesheets.exists():
        # 勤怠報告ベースの明細
        for ts in timesheets:
            if ts.order_item:
                base_fee, excess, shortage, subtotal = calculate_ses_billing(
                    ts.order_item, ts.total_hours
                )
                product_name = ts.worker_name or (ts.order_item.person_name or '業務委託')
                BillingItem.objects.create(
                    invoice=invoice,
                    product_name=f'{product_name}（{ts.target_month.strftime("%Y/%m")}）',
                    unit_price=subtotal,
                    man_month=Decimal('1.00'),
                    tax_category='10',
                    sort_order=item_count,
                )
                item_count += 1
            else:
                warnings.append(f'{ts.worker_name}: 受注明細が紐付いていないため基本料金なし')
    else:
        # 勤怠なし → 受注明細から基本料金で生成
        for item in received_order.items.all():
            name = item.person_name or (item.product.name if item.product else '業務委託')
            BillingItem.objects.create(
                invoice=invoice,
                product_name=f'{name}（{received_order.target_month.strftime("%Y/%m")}）',
                unit_price=item.unit_price,
                man_month=item.man_month,
                tax_category='10',
                sort_order=item_count,
            )
            item_count += 1

    return invoice, item_count, warnings


def send_invoice_email(invoice, sender_email=None, custom_subject=None, custom_body=None):
    """
    請求書をメールで送信し、ステータスをSENTに更新する。

    Args:
        invoice: BillingInvoice
        sender_email: 送信元メールアドレス（省略時はDEFAULT_FROM_EMAIL）
        custom_subject: カスタム件名
        custom_body: カスタム本文

    Returns:
        dict: {'sent': True/False, 'drive_file_id': str, 'errors': list}
    """
    from django.core.mail import EmailMessage
    from django.conf import settings
    from billing.application.services.pdf_generator import generate_billing_pdf
    import logging

    logger = logging.getLogger(__name__)
    result = {'sent': False, 'drive_file_id': '', 'errors': []}

    # メール送信先チェック
    customer = invoice.customer
    if not customer.email:
        result['errors'].append(f'{customer.name}のメールアドレスが未設定です。')
        return result

    # PDF生成
    try:
        pdf_buffer = generate_billing_pdf(invoice)
        pdf_data = pdf_buffer.getvalue()
    except Exception as e:
        result['errors'].append(f'PDF生成エラー: {e}')
        return result

    # 件名・本文
    month_str = ''
    if invoice.received_order:
        month_str = invoice.received_order.target_month.strftime('%Y年%m月')

    subject = custom_subject or f'【請求書】{invoice.subject or month_str}'
    body = custom_body or (
        f'{customer.contact_person or customer.name} 様\n\n'
        f'いつもお世話になっております。\n'
        f'{invoice.company.name if invoice.company else ""}でございます。\n\n'
        f'下記の通り、請求書をお送りいたします。\n\n'
        f'件名: {invoice.subject}\n'
        f'請求日: {invoice.issue_date.strftime("%Y年%m月%d日")}\n'
        f'お支払期日: {invoice.due_date.strftime("%Y年%m月%d日") if invoice.due_date else "別途ご相談"}\n\n'
        f'添付PDFをご確認くださいますようお願いいたします。\n\n'
        f'何卒よろしくお願い申し上げます。'
    )

    from_email = sender_email or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
    to_list = [customer.email]

    # CC
    cc_list = []
    if customer.cc_email:
        cc_list = [e.strip() for e in customer.cc_email.split(',') if e.strip()]

    # メール送信
    try:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=to_list,
            cc=cc_list,
        )
        filename = f'請求書_{customer.name}_{invoice.issue_date.strftime("%Y%m%d")}.pdf'
        email.attach(filename, pdf_data, 'application/pdf')
        email.send()
        result['sent'] = True
        logger.info(f'[Billing] 請求書メール送信成功: {customer.email}')
    except Exception as e:
        result['errors'].append(f'メール送信エラー: {e}')
        logger.error(f'[Billing] メール送信エラー: {e}')
        return result

    # ステータス更新 → SENT
    invoice.status = 'SENT'
    invoice.save(update_fields=['status', 'updated_at'])

    # Google Drive保存
    drive_file_id = _save_invoice_to_drive(invoice, pdf_data)
    if drive_file_id:
        result['drive_file_id'] = drive_file_id

    return result


def _save_invoice_to_drive(invoice, pdf_data):
    """送信済み請求書PDFをGoogle Driveに保存する。"""
    import logging
    from core.services.google_drive_service import (
        _get_drive_service, _find_or_create_folder, _upload_file,
    )
    from django.conf import settings

    logger = logging.getLogger(__name__)

    folder_id = getattr(settings, 'GOOGLE_DRIVE_BILLING_INVOICE_FOLDER_ID', '')
    if not folder_id:
        folder_id = getattr(settings, 'GOOGLE_DRIVE_ROOT_FOLDER_ID', '')
    if not folder_id:
        logger.info('[Billing] Google Drive フォルダIDが未設定のためスキップ')
        return ''

    service = _get_drive_service()
    if not service:
        return ''

    try:
        # 取引先別サブフォルダ
        customer_folder = _find_or_create_folder(
            service, invoice.customer.name, folder_id
        )
        filename = f'請求書_{invoice.customer.name}_{invoice.issue_date.strftime("%Y%m%d")}.pdf'
        file_id, web_link = _upload_file(service, pdf_data, filename, customer_folder)

        # DBに保存
        invoice.drive_file_id = file_id
        invoice.save(update_fields=['drive_file_id', 'updated_at'])

        logger.info(f'[Billing] Google Drive保存成功: {filename} (ID: {file_id})')
        return file_id
    except Exception as e:
        logger.warning(f'[Billing] Google Drive保存エラー: {e}')
        return ''

