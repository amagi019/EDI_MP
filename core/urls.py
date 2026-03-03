from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('signup/admin/', views.AdminSignUpView.as_view(), name='admin_signup'),
    path('signup/partner/', views.PartnerUserSignUpView.as_view(), name='partner_signup'),
    path('partner/onboarding/', views.PartnerOnboardingView.as_view(), name='partner_onboarding'),
    path('partner/manual/', views.PartnerManualView.as_view(), name='partner_manual'),
    path('staff/register-partner/', views.QuickPartnerRegistrationView.as_view(), name='quick_partner_registration'),
    path('staff/registration-success/', views.RegistrationSuccessView.as_view(), name='registration_success'),
    path('staff/partner-email-log/<str:customer_id>/', views.PartnerEmailLogView.as_view(), name='partner_email_log'),
    path('contract-progress/', views.ContractProgressListView.as_view(), name='contract_progress_list'),
]
