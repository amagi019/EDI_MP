from django.apps import AppConfig


class MfaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.mfa'
    verbose_name = 'MFA (2段階認証)'
