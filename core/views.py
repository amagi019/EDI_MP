from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Count, Q

from django.views.generic import CreateView, UpdateView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .forms import AdminCreationForm, PartnerUserCreationForm, PartnerOnboardingForm, QuickPartnerRegistrationForm
from .domain.models import Partner, MasterContractProgress, SentEmailLog
from orders.models import Order
from invoices.models import Invoice

@login_required
def dashboard(request):
    """進捗管理ダッシュボード"""
    user = request.user
    partner = None
    if hasattr(user, 'profile') and user.profile.partner:
        customer = user.profile.partner

    # フィルター条件の構築
    order_filter = Q()
    invoice_filter = Q()

    if not user.is_staff:
        if hasattr(user, 'profile') and user.profile.partner:
            customer = user.profile.partner
            order_filter &= Q(partner=partner)
            invoice_filter &= Q(order__partner=partner)
        else:
            # パートナーが紐付いていないユーザーは何も表示しない
            order_filter = Q(pk__in=[])
            invoice_filter = Q(pk__in=[])
    
    # 統計情報の取得
    unconfirmed_orders = Order.objects.filter(order_filter, status='UNCONFIRMED').select_related('partner', 'project')
    received_orders = Order.objects.filter(order_filter, status__in=['RECEIVED', 'APPROVED']).select_related('partner', 'project')
    confirming_invoices = Invoice.objects.filter(invoice_filter, status__in=['ISSUED', 'SENT']).select_related('order__partner', 'order__project')

    # スタッフ用：契約進捗リスト
    contract_progress_list = []
    if user.is_staff:
        contract_progress_list = MasterContractProgress.objects.select_related('partner').all().order_by('-updated_at')

    context = {
        'unconfirmed_orders_count': unconfirmed_orders.count(),
        'received_orders_count': received_orders.count(),
        'confirming_invoices_count': confirming_invoices.count(),
        'unconfirmed_orders': unconfirmed_orders,
        'received_orders': received_orders,
        'confirming_invoices': confirming_invoices,
        'is_authorized': user.is_staff or (partner is not None),
        'contract_progress_list': contract_progress_list,
    }
    return render(request, 'core/dashboard.html', context)

class AdminSignUpView(CreateView):
    template_name = 'core/admin_signup.html'
    form_class = AdminCreationForm
    success_url = reverse_lazy('login')

class CustomPasswordChangeView(PasswordChangeView):
    success_url = reverse_lazy('password_change_done')
    template_name = 'registration/password_change_form.html'

    def form_valid(self, form):
        # フォームが有効な場合（パスワード変更成功）、初回ログインフラグをオフにする
        if hasattr(self.request.user, 'profile'):
            self.request.user.profile.is_first_login = False
            self.request.user.profile.save()
        return super().form_valid(form)

class PartnerUserSignUpView(UserPassesTestMixin, CreateView):
    template_name = 'core/partner_signup.html'
    form_class = PartnerUserCreationForm
    success_url = reverse_lazy('core:dashboard') # またはユーザー一覧など

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        messages.success(self.request, "パートナーユーザーを登録しました。")
        return super().form_valid(form)


class PartnerOnboardingView(UpdateView):
    """パートナー自身による情報登録・更新（オンボーディング）"""
    model = Partner
    form_class = PartnerOnboardingForm
    template_name = 'core/partner_onboarding.html'
    success_url = reverse_lazy('core:dashboard')

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_object(self, queryset=None):
        # ログインユーザーに紐付くCustomerを取得
        if hasattr(self.request.user, 'profile') and self.request.user.profile.partner:
            return self.request.user.profile.partner
        raise Http404("パートナー情報が見つかりません。")

    def form_valid(self, form):
        partner = form.save()
        # 進捗状況を更新
        MasterContractProgress.objects.filter(partner=partner).update(status='INFO_DONE')
        messages.success(self.request, "パートナー情報を更新しました。")
        return super().form_valid(form)


class PartnerManualView(LoginRequiredMixin, TemplateView):
    """パートナー向け操作マニュアル表示"""
    template_name = 'core/partner_manual.html'


class StaffOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff
from django.views.generic import TemplateView, FormView

class QuickPartnerRegistrationView(LoginRequiredMixin, StaffOnlyMixin, FormView):
    """自社担当者によるクイック取引先登録"""
    form_class = QuickPartnerRegistrationForm
    template_name = 'core/quick_partner_registration.html'
    success_url = reverse_lazy('core:registration_success')

    def form_valid(self, form):
        from django.db import IntegrityError
        try:
            self.object = form.save()
            messages.success(self.request, "パートナーユーザーを登録しました。")
            return super().form_valid(form)
        except IntegrityError as e:
            form.add_error(None, f"登録中にエラーが発生しました: {e}")
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"予期せぬエラーが発生しました: {e}")
            return self.form_invalid(form)

    def get_success_url(self):
        # 登録したユーザー情報をセッションに保存して成功画面で表示できるようにする
        self.request.session['last_registered_email'] = self.object.email
        self.request.session['last_registered_password'] = getattr(self.object, 'raw_password', '')
        return super().get_success_url()


class RegistrationSuccessView(LoginRequiredMixin, StaffOnlyMixin, TemplateView):
    """登録完了後のガイド画面"""
    template_name = 'core/registration_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['registered_email'] = self.request.session.get('last_registered_email', '不明')
        context['registered_password'] = self.request.session.get('last_registered_password', '')
        return context

class PartnerEmailLogView(LoginRequiredMixin, StaffOnlyMixin, TemplateView):
    """送信済みメールの閲覧"""
    template_name = 'core/partner_email_log.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        partner_id = self.kwargs.get('customer_id')
        partner = Partner.objects.get(partner_id=partner_id)
        context['customer'] = partner
        context['email_logs'] = SentEmailLog.objects.filter(partner=partner).order_by('-sent_at')
        return context

class ContractProgressListView(LoginRequiredMixin, TemplateView):
    """基本契約進捗一覧"""
    template_name = 'core/contract_progress_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # スタッフユーザーのみ全ての進捗を表示、非スタッフは自分の進捗のみ表示
        if user.is_staff:
            contract_progress_list = MasterContractProgress.objects.select_related('partner').all().order_by('-updated_at')
        else:
            # 非スタッフの場合、自分の顧客情報の進捗のみ表示
            if hasattr(user, 'profile') and user.profile.partner:
                contract_progress_list = MasterContractProgress.objects.filter(
                    partner=user.profile.partner
                ).select_related('partner')
            else:
                contract_progress_list = MasterContractProgress.objects.none()
        
        context['contract_progress_list'] = contract_progress_list
        context['is_staff'] = user.is_staff
        return context


class ContractGenerateView(LoginRequiredMixin, StaffOnlyMixin, View):
    """基本契約書PDFを生成し保存する"""

    def post(self, request, partner_id):
        import hashlib
        from django.core.files.base import ContentFile
        from .services.contract_pdf_generator import generate_contract_pdf

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress, _ = MasterContractProgress.objects.get_or_create(partner=partner)

        # 契約書PDF生成
        buffer = generate_contract_pdf(partner)
        pdf_content = buffer.getvalue()

        # SHA256ハッシュ計算
        pdf_hash = hashlib.sha256(pdf_content).hexdigest()

        # 保存
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

    def get(self, request, partner_id):
        from .services.contract_pdf_generator import generate_contract_pdf

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        user = request.user
        # パートナーの場合、自分のパートナーのみ閲覧可能
        if not user.is_staff:
            if not hasattr(user, 'profile') or not user.profile.partner:
                return HttpResponseForbidden("パートナー情報がありません。")
            if user.profile.partner != partner:
                return HttpResponseForbidden("権限がありません。")

        # 保存済みPDFがあればそれを返す
        if progress.contract_pdf:
            response = HttpResponse(progress.contract_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="contract_{partner_id}.pdf"'
            return response

        # なければ動的に生成
        buffer = generate_contract_pdf(partner, signed_at=progress.signed_at)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="contract_{partner_id}.pdf"'
        return response


class ContractSendView(LoginRequiredMixin, StaffOnlyMixin, View):
    """契約書送付メール"""

    def post(self, request, partner_id):
        from django.utils import timezone
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        from .domain.models import SentEmailLog, EmailTemplate

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        if not progress.contract_pdf:
            messages.error(request, "契約書PDFが生成されていません。先に契約書を作成してください。")
            return redirect('core:contract_progress_list')

        # メール送信
        contract_url = request.build_absolute_uri(f'/contract/{partner_id}/preview/')
        subject = f"【基本契約書のご確認】{partner.name} 様"
        body = (
            f"{partner.name} 御中\n\n"
            f"有限会社マックプランニングです。\n\n"
            f"基本契約書を作成いたしましたので、以下のURLよりご確認ください。\n\n"
            f"■ 契約書確認URL:\n{contract_url}\n\n"
            f"内容をご確認のうえ、「承認」ボタンを押してください。\n\n"
            f"ご不明な点がございましたら、お気軽にお問い合わせください。\n\n"
            f"有限会社 マックプランニング"
        )

        try:
            send_mail(
                subject,
                body,
                django_settings.DEFAULT_FROM_EMAIL,
                [partner.email],
                fail_silently=False,
            )
            # ログ保存
            SentEmailLog.objects.create(partner=partner, subject=subject, body=body)
            progress.sent_at = timezone.now()
            progress.status = 'PENDING_APPROVAL'
            progress.save()
            messages.success(request, f"{partner.name} に契約書を送信しました。")
        except Exception as e:
            messages.error(request, f"メール送信に失敗しました: {e}")

        return redirect('core:contract_progress_list')


class ContractApproveView(LoginRequiredMixin, View):
    """パートナーによる契約書承認"""

    def get(self, request, partner_id):
        """承認画面を表示"""
        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        user = request.user
        if not user.is_staff:
            if not hasattr(user, 'profile') or not user.profile.partner:
                return HttpResponseForbidden("パートナー情報がありません。")
            if user.profile.partner != partner:
                return HttpResponseForbidden("権限がありません。")

        context = {
            'partner': partner,
            'progress': progress,
        }
        return render(request, 'core/contract_approve.html', context)

    def post(self, request, partner_id):
        """承認処理"""
        import hashlib
        from django.utils import timezone
        from django.core.files.base import ContentFile
        from .services.contract_pdf_generator import generate_contract_pdf

        partner = get_object_or_404(Partner, partner_id=partner_id)
        progress = get_object_or_404(MasterContractProgress, partner=partner)

        user = request.user
        if not user.is_staff:
            if not hasattr(user, 'profile') or not user.profile.partner:
                return HttpResponseForbidden("パートナー情報がありません。")
            if user.profile.partner != partner:
                return HttpResponseForbidden("権限がありません。")

        if progress.status == 'COMPLETED':
            messages.info(request, "この契約書は既に締結済みです。")
            return redirect('core:dashboard')

        # 承認処理
        now = timezone.now()
        progress.signed_at = now
        progress.signed_by = user
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

        # 管理者に承認通知メール
        try:
            from django.core.mail import send_mail
            from django.conf import settings as django_settings
            from .domain.models import SentEmailLog

            admin_email = django_settings.DEFAULT_FROM_EMAIL
            subject = f"【基本契約承認通知】{partner.name}"
            body = (
                f"{partner.name} が基本契約書を承認しました。\n\n"
                f"承認日時: {now.strftime('%Y年%m月%d日 %H:%M')}\n"
                f"承認者: {user.get_full_name() or user.username}\n"
            )
            send_mail(subject, body, admin_email, [admin_email], fail_silently=True)
        except:
            pass

        messages.success(request, "基本契約書を承認しました。契約が締結されました。")
        return redirect('core:dashboard')
