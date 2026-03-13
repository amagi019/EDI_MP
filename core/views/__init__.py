"""
core/views パッケージ

旧 core/views.py からの後方互換のため、全ビューをre-exportする。
"""
from .dashboard_views import dashboard  # noqa: F401
from .auth_views import (  # noqa: F401
    AdminSignUpView,
    CustomPasswordChangeView,
    PartnerUserSignUpView,
)
from .partner_views import (  # noqa: F401
    PartnerOnboardingView,
    PartnerManualView,
    QuickPartnerRegistrationView,
    RegistrationSuccessView,
    PartnerEmailLogView,
)
from .contract_views import (  # noqa: F401
    ContractProgressListView,
    ContractGenerateView,
    ContractPreviewView,
    ContractSendView,
    ContractApproveView,
)
