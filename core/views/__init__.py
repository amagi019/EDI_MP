"""
core/views パッケージ

旧 core/views.py からの後方互換のため、全ビューをre-exportする。
"""
from .dashboard_views import dashboard  # noqa: F401
from .auth_views import (  # noqa: F401
    MFALoginView,
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
    ContractRegenerateView,
    ContractPreviewView,
    ContractSendView,
    ContractApproveView,
)
from .bank_api import bank_search, branch_search  # noqa: F401
from .pwa_views import service_worker_view, manifest_view  # noqa: F401
