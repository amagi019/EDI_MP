"""
MFA (Multi-Factor Authentication) — Django ORM Models

TOTP 2段階認証とパスキー（WebAuthn）のデータモデル。
WIP QA管理ツールから流用。
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


def _get_fernet():
    """SECRET_KEY から Fernet キーを導出する"""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class TOTPDevice(models.Model):
    """TOTP 2段階認証デバイス"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="totp_device",
        verbose_name="ユーザー",
    )
    secret = models.CharField(
        "TOTP秘密鍵（暗号化済み）",
        max_length=256,
    )
    confirmed = models.BooleanField(
        "設定完了",
        default=False,
        help_text="QRコード読み取り後に6桁コードで検証済みかどうか",
    )
    created_at = models.DateTimeField("設定日時", auto_now_add=True)

    class Meta:
        db_table = "mfa_totp_device"
        verbose_name = "TOTPデバイス"
        verbose_name_plural = "TOTPデバイス"

    def __str__(self):
        status = "有効" if self.confirmed else "未確認"
        return f"{self.user} - TOTP ({status})"

    def set_secret(self, raw_secret: str):
        """平文の秘密鍵を暗号化して保存"""
        f = _get_fernet()
        self.secret = f.encrypt(raw_secret.encode()).decode()

    def get_secret(self) -> str:
        """暗号化された秘密鍵を復号して返す。旧データ（平文）にも対応。"""
        try:
            f = _get_fernet()
            return f.decrypt(self.secret.encode()).decode()
        except Exception:
            # 暗号化前の旧データ（平文32文字のBase32）はそのまま返す
            return self.secret


class WebAuthnCredential(models.Model):
    """WebAuthn パスキー"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="webauthn_credentials",
        verbose_name="ユーザー",
    )
    credential_id = models.BinaryField(
        "クレデンシャルID",
        unique=True,
    )
    public_key = models.BinaryField(
        "公開鍵",
    )
    sign_count = models.IntegerField(
        "署名カウント",
        default=0,
    )
    name = models.CharField(
        "デバイス名",
        max_length=100,
        default="マイデバイス",
    )
    created_at = models.DateTimeField(
        "登録日時",
        auto_now_add=True,
    )

    class Meta:
        db_table = "mfa_webauthn_credential"
        verbose_name = "パスキー"
        verbose_name_plural = "パスキー"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.name}"
