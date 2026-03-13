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
    # 基本契約書関連
    path('contract/<str:partner_id>/generate/', views.ContractGenerateView.as_view(), name='contract_generate'),
    path('contract/<str:partner_id>/preview/', views.ContractPreviewView.as_view(), name='contract_preview'),
    path('contract/<str:partner_id>/send/', views.ContractSendView.as_view(), name='contract_send'),
    path('contract/<str:partner_id>/approve/', views.ContractApproveView.as_view(), name='contract_approve'),
    # 銀行マスタ検索API
    path('api/banks/', views.bank_search, name='api_bank_search'),
    path('api/banks/<str:bank_code>/branches/', views.branch_search, name='api_branch_search'),
]
