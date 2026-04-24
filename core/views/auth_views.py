from django.contrib import messages
from django.conf import settings
from django.urls import reverse_lazy
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import redirect
from django.utils.safestring import mark_safe
from django.views.generic import CreateView

from core.forms import AdminCreationForm, PartnerUserCreationForm
from core.permissions import StaffRequiredMixin


class MFALoginView(auth_views.LoginView):
    """ログインビュー（2FA対応）"""
    template_name = 'registration/login.html'

    def form_valid(self, form):
        user = form.get_user()

        # TOTP 2段階認証が有効か確認
        from core.mfa.models import TOTPDevice
        totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

        if totp_device:
            # まだログインさせず、セッションにユーザーIDを保存して TOTP 検証画面へ
            self.request.session["_2fa_user_id"] = user.pk
            self.request.session["_2fa_backend"] = user.backend
            self.request.session["_2fa_next"] = self.get_redirect_url() or settings.LOGIN_REDIRECT_URL
            return redirect("mfa-totp-verify")

        # TOTP 未設定 → 通常ログイン + 案内メッセージ
        response = super().form_valid(form)
        messages.info(self.request, mark_safe("🔐 2段階認証を設定すると、アカウントをより安全に保護できます。<a href='/accounts/security/' style='color:#818cf8;font-weight:600;'>設定する →</a>"))
        return response


class AdminSignUpView(StaffRequiredMixin, CreateView):
    template_name = 'core/admin_signup.html'
    form_class = AdminCreationForm
    success_url = reverse_lazy('login')


class CustomPasswordChangeView(PasswordChangeView):
    success_url = reverse_lazy('password_change_done')
    template_name = 'registration/password_change_form.html'

    def form_valid(self, form):
        if hasattr(self.request.user, 'profile'):
            self.request.user.profile.is_first_login = False
            self.request.user.profile.save()
        return super().form_valid(form)


class PartnerUserSignUpView(StaffRequiredMixin, CreateView):
    template_name = 'core/partner_signup.html'
    form_class = PartnerUserCreationForm
    success_url = reverse_lazy('core:dashboard')

    def form_valid(self, form):
        messages.success(self.request, "パートナーユーザーを登録しました。")
        return super().form_valid(form)
