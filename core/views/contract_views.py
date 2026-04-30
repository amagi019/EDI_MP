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
from core.utils import get_notify_email


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


class ContractRegenerateView(StaffRequiredMixin, View):
    """基本契約書PDFをステータス維持のまま再生成する（パートナー情報修正後の反映用）"""

    def post(self, request, partner_id):
        import hashlib
        from django.core.files.base import ContentFile
        from core.services.contract_pdf_generator import generate_contract_pdf

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        # 承認済みの場合は承認日時を引き継いでPDF再生成
        buffer = generate_contract_pdf(partner, signed_at=progress.signed_at)
        pdf_content = buffer.getvalue()
        pdf_hash = hashlib.sha256(pdf_content).hexdigest()

        if progress.contract_pdf:
            progress.contract_pdf.delete(save=False)

        filename = f'contract_{partner_id}_signed.pdf' if progress.signed_at else f'contract_{partner_id}.pdf'
        progress.contract_pdf.save(filename, ContentFile(pdf_content), save=False)
        progress.pdf_hash = pdf_hash
        progress.save()

        messages.success(request, f"{partner.name} の基本契約書PDFを再作成しました。")
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
        from core.domain.models import SentEmailLog
        from core.utils import compose_contract_send_email, send_system_mail

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

        subject, body = compose_contract_send_email(partner, contract_url)

        try:
            send_system_mail(subject, body, [partner.email])
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
        """承諾処理（パートナー本人のみ実行可能）"""
        from core.services.contract_service import approve_contract

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        if not is_owner_of_partner(request.user, partner):
            raise PermissionDenied("承諾はパートナーご自身で行ってください。")

        if progress.status == 'COMPLETED':
            messages.info(request, "この契約書は既に締結済みです。")
            return redirect('core:dashboard')

        approve_contract(partner, progress, request.user, request)

        messages.success(request, "基本契約書を承諾しました。契約が締結されました。")
        return redirect('core:dashboard')
