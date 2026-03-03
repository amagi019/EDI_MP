"""
メール送信サービス（PDF添付・複数宛先対応）
"""
from django.core.mail import EmailMessage
from django.conf import settings
from core.domain.models import SentEmailLog


def send_invoice_email(invoice, to_list, cc_list, subject, body, pdf_buffer=None):
    """
    請求書メールを送信する。

    Args:
        invoice: BillingInvoiceインスタンス
        to_list: TO宛先リスト（list of str）
        cc_list: CC宛先リスト（list of str）
        subject: 件名
        body: 本文
        pdf_buffer: PDFのバイトストリーム（添付する場合）

    Returns:
        送信成功: True / 失敗: False
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=to_list,
        cc=cc_list,
    )

    # PDF添付
    if pdf_buffer:
        pdf_buffer.seek(0)
        filename = f"請求書_{invoice.customer.name}_{invoice.issue_date}.pdf"
        email.attach(filename, pdf_buffer.read(), 'application/pdf')

    try:
        email.send()

        # 送信ログを記録（SentEmailLogはpartner必須のため、billing用はスキップ）
        try:
            SentEmailLog.objects.create(
                partner=None,
                subject=subject,
                body=body,
            )
        except Exception:
            pass  # partnerがNULL不可の場合はスキップ

        return True
    except Exception:
        return False


def parse_email_list(email_string):
    """
    カンマ区切りのメールアドレス文字列をリストに変換する。

    Args:
        email_string: "a@test.com, b@test.com"

    Returns:
        ['a@test.com', 'b@test.com']
    """
    if not email_string:
        return []
    return [e.strip() for e in email_string.split(',') if e.strip()]
