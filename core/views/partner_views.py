from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.http import Http404
from django.urls import reverse, reverse_lazy
from django.views.generic import UpdateView, TemplateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin

from core.forms import PartnerOnboardingForm, QuickPartnerRegistrationForm
from core.domain.models import Partner, SentEmailLog
from core.permissions import (
    get_user_partner, StaffRequiredMixin, PartnerRequiredMixin,
)


class PartnerOnboardingView(PartnerRequiredMixin, UpdateView):
    """パートナー自身による情報登録・更新（オンボーディング）"""
    model = Partner
    form_class = PartnerOnboardingForm
    template_name = 'core/partner_onboarding.html'
    success_url = reverse_lazy('core:dashboard')

    def get_object(self, queryset=None):
        partner = get_user_partner(self.request.user)
        if partner is None:
            raise Http404("パートナー情報が見つかりません。")
        return partner

    def form_valid(self, form):
        from django.core.mail import send_mail
        from django.conf import settings
        from core.domain.models import MasterContractProgress

        partner = form.save()
        MasterContractProgress.objects.filter(partner=partner).update(status='INFO_DONE')
        messages.success(self.request, "パートナー情報を更新しました。")

        # スタッフ担当者へ通知メール送信
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            from core.utils import compose_partner_info_registered_email

            progress_url = self.request.build_absolute_uri(
                reverse('core:contract_progress_list')
            )
            subject, message = compose_partner_info_registered_email(partner, progress_url)

            if partner.staff_contact and partner.staff_contact.email:
                notify_email = partner.staff_contact.email
            else:
                notify_email = settings.DEFAULT_FROM_EMAIL
            send_mail(
                subject, message, settings.DEFAULT_FROM_EMAIL,
                [notify_email], fail_silently=False,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Staff notification failed for {partner.name}: {e}")

        return super().form_valid(form)


class PartnerManualView(LoginRequiredMixin, TemplateView):
    """パートナー向け操作マニュアル表示"""
    template_name = 'core/partner_manual.html'


class QuickPartnerRegistrationView(StaffRequiredMixin, FormView):
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
        self.request.session['last_registered_email'] = self.object.email
        self.request.session['last_registered_password'] = getattr(self.object, 'raw_password', '')
        return super().get_success_url()


class RegistrationSuccessView(StaffRequiredMixin, TemplateView):
    """登録完了後のガイド画面"""
    template_name = 'core/registration_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['registered_email'] = self.request.session.get('last_registered_email', '不明')
        context['registered_password'] = self.request.session.get('last_registered_password', '')
        return context


class PartnerEmailLogView(StaffRequiredMixin, TemplateView):
    """送信済みメールの閲覧"""
    template_name = 'core/partner_email_log.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        partner_id = self.kwargs.get('customer_id')
        partner = Partner.objects.get(partner_id=partner_id)
        context['customer'] = partner
        context['email_logs'] = SentEmailLog.objects.filter(partner=partner).order_by('-sent_at')
        return context
