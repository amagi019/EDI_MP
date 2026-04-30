"""請求書関連メール送信サービス

Admin の save_model から呼ばれるメール通知ロジックを集約。
各関数は (success: bool, message: str) のタプルを返す。
"""
import logging
from textwrap import dedent

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from core.domain.models import SentEmailLog

logger = logging.getLogger(__name__)


def _format_month(invoice):
    """対象年月の表示文字列"""
    if invoice.target_month:
        return invoice.target_month.strftime('%Y年%m月')
    return '未設定'


# ============================================================
# 確認依頼（自社担当者向け）
# ============================================================

def send_review_request(invoice, request):
    """自社担当者に確認依頼メールを送信する。

    Returns:
        (bool, str): 成功フラグとユーザー向けメッセージ
    """
    partner = invoice.order.partner if invoice.order else None
    if not partner:
        return False, 'パートナー情報が設定されていません。'

    # 通知先: 担当者 → フォールバック: DEFAULT_FROM_EMAIL
    if partner.staff_contact and partner.staff_contact.email:
        recipient = partner.staff_contact.email
    else:
        recipient = settings.DEFAULT_FROM_EMAIL

    review_url = request.build_absolute_uri(
        reverse('invoices:staff_invoice_review', kwargs={'invoice_id': invoice.pk})
    )
    pdf_url = request.build_absolute_uri(
        reverse('invoices:admin_invoice_pdf', kwargs={'invoice_id': invoice.pk})
    )

    subject = f'【請求書確認依頼】請求番号：{invoice.invoice_no}'
    body = dedent(f"""\
        以下の請求書（支払通知書）の内容確認をお願いします。

        ■請求番号：{invoice.invoice_no}
        ■パートナー：{partner.name}
        ■対象年月：{_format_month(invoice)}
        ■税込合計：¥{invoice.total_amount:,}-

        ▼確認・承認画面
        {review_url}

        ▼請求書PDFプレビュー
        {pdf_url}

        内容に問題がなければ「承認」、修正が必要な場合は「差戻し」をお願いします。
    """)

    return _send_and_log(subject, body, recipient, partner, invoice)


# ============================================================
# 送付通知（パートナー向け）
# ============================================================

def send_invoice_notification(invoice, request):
    """請求書（支払通知書）送付メールをパートナーへ送信する。

    Returns:
        (bool, str): 成功フラグとユーザー向けメッセージ
    """
    partner = invoice.order.partner if invoice.order else None
    if not partner or not partner.email:
        return False, 'パートナーのメールアドレスが設定されていないため、メール通知は送信されませんでした。'

    login_url = request.build_absolute_uri(reverse('login'))

    subject = f'【支払通知書送付】請求番号：{invoice.invoice_no}'
    body = dedent(f"""\
        {partner.name} 様

        以下の支払通知書を送付いたします。
        システムにログインして内容をご確認の上、承認をお願いいたします。

        ■請求番号：{invoice.invoice_no}
        ■対象年月：{_format_month(invoice)}
        ■税込合計：¥{invoice.total_amount:,}-

        ▼ログインURL
        {login_url}

        ご不明な点がございましたら、担当者までお問い合わせください。
    """)

    return _send_and_log(subject, body, partner.email, partner, invoice)


# ============================================================
# 共通: 送信 + ログ記録
# ============================================================

def _send_and_log(subject, body, recipient, partner, invoice):
    """メール送信と SentEmailLog 記録を行う。"""
    try:
        send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL,
            [recipient], fail_silently=False,
        )
        SentEmailLog.objects.create(
            partner=partner,
            subject=subject,
            body=body,
            recipient=recipient,
        )
        return True, f'{recipient} へメールを送信しました。'
    except Exception as e:
        logger.warning('メール送信失敗 (Invoice %s): %s', invoice.invoice_no, e)
        return False, f'メール送信に失敗しました: {e}'
