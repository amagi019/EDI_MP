"""
注文書サービス層 — ビューからビジネスロジックを分離
"""
import hashlib
import logging

from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from core.utils import compose_order_publish_email, compose_order_approve_email, get_notify_email
from .pdf_generator import generate_order_pdf, generate_acceptance_pdf
from .signature_service import SignatureService

logger = logging.getLogger(__name__)


def approve_order(order, user, request):
    """
    パートナーによる注文書の承諾処理。
    - ステータス更新（APPROVED）
    - 注文請書PDF生成・保存・改ざん防止ハッシュ
    - 電子署名依頼
    - 自社担当者へ通知メール
    - 月次タスク完了
    Returns: None
    """
    order.status = 'APPROVED'
    order.finalized_at = timezone.now()

    # 注文請書を生成して保存
    buffer = generate_acceptance_pdf(order)
    content = buffer.getvalue()
    order.document_hash = hashlib.sha256(content).hexdigest()
    order.acceptance_pdf.save(
        f"acceptance_{order.order_id}.pdf",
        ContentFile(content),
        save=False
    )

    # 電子署名依頼
    try:
        sig_service = SignatureService()
        sig_result = sig_service.request_signature(order)
        order.external_signature_id = sig_result['signature_id']
    except Exception as e:
        logger.warning(f"Signature request failed for {order.order_id}: {e}")

    order.save()

    # 自社担当者へメール送信
    _send_approve_notification(order, request)

    # 月次タスク（ORDER_APPROVE）を完了にする
    from tasks.services import complete_order_approve
    complete_order_approve(order)


def publish_order(order, request):
    """
    管理者による注文書の正式発行処理。
    - ステータス更新（UNCONFIRMED）
    - 注文書PDF永続保存
    - Google Drive連携
    - パートナーへメール通知
    Returns: (email_sent: bool)
    """
    order.status = 'UNCONFIRMED'

    # 正式発行時に注文書を永続保存
    buffer = generate_order_pdf(order)
    content = buffer.getvalue()
    order.order_pdf.save(
        f"order_{order.order_id}.pdf",
        ContentFile(content),
        save=False
    )
    order.save()

    # Google Driveへ自動アップロード
    try:
        from .google_drive_service import upload_order_pdf
        result = upload_order_pdf(order)
        order.drive_file_id = result['file_id']
        order.save(update_fields=['drive_file_id'])
    except Exception as e:
        logger.warning(f"Drive upload failed for {order.order_id}: {e}")

    # パートナーへ注文書送付メール
    email_sent = False
    if order.partner and order.partner.email:
        login_url = request.build_absolute_uri(reverse('login'))
        order_detail_url = request.build_absolute_uri(
            reverse('orders:order_detail', kwargs={'order_id': order.order_id})
        )
        subject, message = compose_order_publish_email(order, order_detail_url, login_url)
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [order.partner.email], fail_silently=False)
            email_sent = True
        except Exception as e:
            logger.warning(f"Order notification email failed for {order.order_id}: {e}")

    return email_sent


def _send_approve_notification(order, request):
    """注文承諾通知メールを自社担当者に送信する。"""
    order_url = request.build_absolute_uri(
        reverse('orders:order_detail', kwargs={'order_id': order.order_id})
    )
    subject, message = compose_order_approve_email(order, order_url)
    notify_email = get_notify_email(order.partner)

    try:
        logger.info(f"[注文承諾通知] 宛先: {notify_email}, 件名: {subject}")
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [notify_email], fail_silently=False)
        logger.info(f"[注文承諾通知] 送信成功")
    except Exception as e:
        logger.warning(f"[注文承諾通知] 送信エラー: {e}")
        raise  # ビュー側でメッセージを切り分けるため
