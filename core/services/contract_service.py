"""
基本契約サービス層 — ビューからビジネスロジックを分離
"""
import hashlib
import logging

from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from core.domain.models import MasterContractProgress, SentEmailLog
from core.services.contract_pdf_generator import generate_contract_pdf
from core.utils import get_notify_email

logger = logging.getLogger(__name__)


def approve_contract(partner, progress, user, request):
    """
    パートナーによる基本契約の承諾処理。
    - ステータス更新
    - 承諾日時入りPDF再生成・保存
    - 自社担当者へ通知メール
    - Google Driveへアップロード
    Returns: None
    """
    now = timezone.now()
    progress.signed_at = now
    progress.signed_by = user
    progress.status = 'COMPLETED'

    # 承諾日時入りのPDFを再生成
    buffer = generate_contract_pdf(partner, signed_at=now)
    pdf_content = buffer.getvalue()
    pdf_hash = hashlib.sha256(pdf_content).hexdigest()

    if progress.contract_pdf:
        progress.contract_pdf.delete(save=False)
    progress.contract_pdf.save(
        f'contract_{partner.partner_id}_signed.pdf',
        ContentFile(pdf_content),
        save=False
    )
    progress.pdf_hash = pdf_hash
    progress.save()

    # 自社担当者に承諾通知メール
    _send_approve_notification(partner, user, now, request)

    # Google Driveにアップロード
    _upload_to_drive(partner, pdf_content, now)


def _send_approve_notification(partner, user, signed_at, request):
    """承諾通知メールを自社担当者に送信する。"""
    try:
        notify_email = get_notify_email(partner)
        contract_url = request.build_absolute_uri(
            reverse('core:contract_approve', kwargs={'partner_id': partner.partner_id})
        )
        local_now = timezone.localtime(signed_at)

        from core.utils import compose_contract_approve_email
        subject, body = compose_contract_approve_email(
            partner, contract_url,
            signed_at=local_now.strftime('%Y年%m月%d日 %H:%M'),
            signed_by=user.get_full_name() or user.username,
        )

        logger.info(f"[通知メール] 宛先: {notify_email}, 件名: {subject}")
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [notify_email], fail_silently=False)
        logger.info(f"[通知メール] 送信成功")
        SentEmailLog.objects.create(
            partner=partner, subject=subject, body=body, recipient=notify_email,
        )
    except Exception as e:
        logger.warning(f"[通知メール] 送信エラー: {e}")


def _upload_to_drive(partner, pdf_content, signed_at):
    """承諾済みPDFをGoogle Driveにアップロードする。"""
    try:
        from core.services.google_drive_service import upload_contract_pdf as drive_upload
        drive_upload(partner, pdf_content, signed_at)
    except Exception as e:
        logger.info(f"[Google Drive] アップロードスキップ: {e}")
