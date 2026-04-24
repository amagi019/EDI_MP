"""
MFA (Multi-Factor Authentication) — URL patterns
"""
from django.urls import path

from . import views

urlpatterns = [
    # セキュリティ設定
    path("security/", views.SecuritySettingsView.as_view(), name="mfa-settings"),

    # TOTP
    path("security/totp/setup/", views.TOTPSetupView.as_view(), name="mfa-totp-setup"),
    path("security/totp/disable/", views.TOTPDisableView.as_view(), name="mfa-totp-disable"),
    path("verify/totp/", views.TOTPVerifyView.as_view(), name="mfa-totp-verify"),

    # パスキー
    path("security/passkey/register/begin/", views.PasskeyRegisterBeginView.as_view(), name="mfa-passkey-register-begin"),
    path("security/passkey/register/complete/", views.PasskeyRegisterCompleteView.as_view(), name="mfa-passkey-register-complete"),
    path("security/passkey/<int:pk>/delete/", views.PasskeyDeleteView.as_view(), name="mfa-passkey-delete"),
    path("passkey/login/begin/", views.PasskeyLoginBeginView.as_view(), name="mfa-passkey-login-begin"),
    path("passkey/login/complete/", views.PasskeyLoginCompleteView.as_view(), name="mfa-passkey-login-complete"),
]
