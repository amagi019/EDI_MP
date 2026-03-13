from django.contrib import messages
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordChangeView
from django.views.generic import CreateView

from core.forms import AdminCreationForm, PartnerUserCreationForm
from core.permissions import StaffRequiredMixin


class AdminSignUpView(CreateView):
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
