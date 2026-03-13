from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.urls import reverse
from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin

from core.domain.models import Partner, MasterContractProgress
from core.permissions import (
    Role, get_user_role, get_user_partner, is_owner_of_partner,
    StaffRequiredMixin,
)


class ContractProgressListView(LoginRequiredMixin, TemplateView):
    """基本契約進捗一覧"""
    template_name = 'core/contract_progress_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        role = get_user_role(user)

        if role == Role.STAFF:
            contract_progress_list = MasterContractProgress.objects.select_related('partner').all().order_by('-updated_at')
        else:
            partner = get_user_partner(user)
            if partner:
                contract_progress_list = MasterContractProgress.objects.filter(
                    partner=partner
                ).select_related('partner')
            else:
                contract_progress_list = MasterContractProgress.objects.none()

        context['contract_progress_list'] = contract_progress_list
        context['is_staff'] = (role == Role.STAFF)
        return context


class ContractGenerateView(StaffRequiredMixin, View):
    """基本契約書PDFを生成し保存する"""

    def post(self, request, partner_id):
        import hashlib
        from django.core.files.base import ContentFile
        from core.services.contract_pdf_generator import generate_contract_pdf

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress, _ = MasterContractProgress.objects.get_or_create(partner=partner)

        buffer = generate_contract_pdf(partner)
        pdf_content = buffer.getvalue()
        pdf_hash = hashlib.sha256(pdf_content).hexdigest()

        if progress.contract_pdf:
            progress.contract_pdf.delete(save=False)
        progress.contract_pdf.save(
            f'contract_{partner_id}.pdf',
            ContentFile(pdf_content),
            save=False
        )
        progress.pdf_hash = pdf_hash
        progress.status = 'CONTRACT_SENT'
        progress.save()

        messages.success(request, f"{partner.name} の基本契約書PDFを生成しました。")
        return redirect('core:contract_progress_list')


class ContractPreviewView(LoginRequiredMixin, View):
    """基本契約書PDFプレビュー"""

    @method_decorator(xframe_options_exempt)
    def get(self, request, partner_id):
        from core.services.contract_pdf_generator import generate_contract_pdf

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, partner):
                raise PermissionDenied("権限がありません。")

        if progress.contract_pdf:
            response = HttpResponse(progress.contract_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="contract_{partner_id}.pdf"'
            return response

        buffer = generate_contract_pdf(partner, signed_at=progress.signed_at)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="contract_{partner_id}.pdf"'
        return response


class ContractSendView(StaffRequiredMixin, View):
    """契約書送付メール"""

    def post(self, request, partner_id):
        from django.utils import timezone
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        from core.domain.models import SentEmailLog

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        if not progress.contract_pdf:
            messages.error(request, "契約書PDFが生成されていません。先に契約書を作成してください。")
            return redirect('core:contract_progress_list')

        # 冪等性チェック：既に送信済みなら重複送信を防止
        if progress.status in ('PENDING_APPROVAL', 'COMPLETED'):
            messages.info(request, "この契約書は既に送信済みです。")
            return redirect('core:contract_progress_list')

        contract_url = request.build_absolute_uri(
            reverse('core:contract_approve', kwargs={'partner_id': partner_id})
        )

        from core.utils import compose_contract_send_email
        subject, body = compose_contract_send_email(partner, contract_url)

        try:
            send_mail(
                subject, body, django_settings.DEFAULT_FROM_EMAIL,
                [partner.email], fail_silently=False,
            )
            SentEmailLog.objects.create(partner=partner, subject=subject, body=body, recipient=partner.email)
            progress.sent_at = timezone.now()
            progress.status = 'PENDING_APPROVAL'
            progress.save()
            messages.success(request, f"{partner.name} に契約書を送信しました。")
        except Exception as e:
            messages.error(request, f"メール送信に失敗しました: {e}")

        return redirect('core:contract_progress_list')


class ContractApproveView(LoginRequiredMixin, View):
    """パートナーによる契約書承認（GET:スタッフ+パートナー閲覧可 / POST:パートナー本人のみ）"""

    def get(self, request, partner_id):
        """承認画面を表示"""
        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, partner):
                raise PermissionDenied("権限がありません。")

        context = {
            'partner': partner,
            'progress': progress,
        }
        return render(request, 'core/contract_approve.html', context)

    def post(self, request, partner_id):
        """承認処理（パートナー本人のみ実行可能）"""
        import hashlib
        from django.utils import timezone
        from django.core.files.base import ContentFile
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        from core.services.contract_pdf_generator import generate_contract_pdf
        from core.domain.models import SentEmailLog

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        if not is_owner_of_partner(request.user, partner):
            raise PermissionDenied("承認はパートナーご自身で行ってください。")

        if progress.status == 'COMPLETED':
            messages.info(request, "この契約書は既に締結済みです。")
            return redirect('core:dashboard')

        # 承認処理
        now = timezone.now()
        progress.signed_at = now
        progress.signed_by = request.user
        progress.status = 'COMPLETED'

        # 承認日時入りのPDFを再生成
        buffer = generate_contract_pdf(partner, signed_at=now)
        pdf_content = buffer.getvalue()
        pdf_hash = hashlib.sha256(pdf_content).hexdigest()

        if progress.contract_pdf:
            progress.contract_pdf.delete(save=False)
        progress.contract_pdf.save(
            f'contract_{partner_id}_signed.pdf',
            ContentFile(pdf_content),
            save=False
        )
        progress.pdf_hash = pdf_hash
        progress.save()

        # 自社担当者に承認通知メール
        try:
            if partner.staff_contact and partner.staff_contact.email:
                notify_email = partner.staff_contact.email
            else:
                notify_email = django_settings.DEFAULT_FROM_EMAIL

            contract_url = request.build_absolute_uri(
                reverse('core:contract_approve', kwargs={'partner_id': partner_id})
            )
            local_now = timezone.localtime(now)

            from core.utils import compose_contract_approve_email
            subject, body = compose_contract_approve_email(
                partner, contract_url,
                signed_at=local_now.strftime('%Y年%m月%d日 %H:%M'),
                signed_by=request.user.get_full_name() or request.user.username,
            )

            print(f"[通知メール] 宛先: {notify_email}, 件名: {subject}")
            send_mail(subject, body, django_settings.DEFAULT_FROM_EMAIL, [notify_email], fail_silently=False)
            print(f"[通知メール] 送信成功")
            SentEmailLog.objects.create(
                partner=partner, subject=subject, body=body, recipient=notify_email,
            )
        except Exception as e:
            print(f"[通知メール] 送信エラー: {e}")

        # Google Driveに承認済みPDFをアップロード
        try:
            from core.services.google_drive_service import upload_contract_pdf as drive_upload
            drive_upload(partner, pdf_content, now)
        except Exception as e:
            print(f"[Google Drive] アップロードスキップ: {e}")

        messages.success(request, "基本契約書を承認しました。契約が締結されました。")
        return redirect('core:dashboard')
