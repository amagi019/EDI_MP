from django.shortcuts import render
from django.contrib import messages
from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Count, Q

from django.views.generic import CreateView, UpdateView, TemplateView
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
        customer = form.save()
        # 進捗状況を更新
        MasterContractProgress.objects.filter(customer=customer).update(status='INFO_DONE')
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
        customer_id = self.kwargs.get('customer_id')
        customer = Customer.objects.get(customer_id=customer_id)
        context['customer'] = customer
        context['email_logs'] = SentEmailLog.objects.filter(customer=customer).order_by('-sent_at')
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
