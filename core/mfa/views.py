"""
MFA (Multi-Factor Authentication) — Views

TOTP 2段階認証とパスキー（WebAuthn）のビュー。
WIP QA管理ツールから流用、EDI Sophia用に調整。
"""
import base64
import io
import json
import logging

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import TOTPDevice, WebAuthnCredential

logger = logging.getLogger(__name__)
User = get_user_model()

APP_NAME = "EDI Sophia"


# RP (Relying Party) の設定
def _get_rp_id(request):
    """RP IDを取得（ドメイン名）"""
    host = request.get_host().split(":")[0]
    return host


def _get_rp_origin(request):
    """RP Originを取得"""
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}"


# ===========================================================================
# セキュリティ設定画面
# ===========================================================================


class SecuritySettingsView(LoginRequiredMixin, View):
    """セキュリティ設定画面"""

    def get(self, request):
        user = request.user
        totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        passkeys = WebAuthnCredential.objects.filter(user=user)

        return render(request, "mfa/security_settings.html", {
            "totp_enabled": totp_device is not None,
            "passkeys": passkeys,
        })


# ===========================================================================
# TOTP 2段階認証
# ===========================================================================


class TOTPSetupView(LoginRequiredMixin, View):
    """TOTP設定画面 — QRコード表示 & 検証"""

    def get(self, request):
        # 新しいシークレットを生成（既存の未確認デバイスは上書き）
        raw_secret = pyotp.random_base32()
        device, created = TOTPDevice.objects.get_or_create(
            user=request.user,
            defaults={"secret": "", "confirmed": False},
        )
        if created or not device.confirmed:
            device.set_secret(raw_secret)
            device.save(update_fields=["secret"])
        elif device.confirmed:
            messages.info(request, "2段階認証は既に有効です")
            return redirect("mfa-settings")
            
        secret_plain = device.get_secret()
        qr_base64 = self._generate_qr(request.user.username, secret_plain)
        return render(request, "mfa/totp_setup.html", {
            "qr_base64": qr_base64,
            "secret_key": secret_plain,
        })

    def post(self, request):
        code = request.POST.get("code", "").strip()
        device = TOTPDevice.objects.filter(user=request.user).first()

        if not device:
            messages.error(request, "設定情報が見つかりません。もう一度やり直してください。")
            return redirect("mfa-totp-setup")

        totp = pyotp.TOTP(device.get_secret())
        if totp.verify(code, valid_window=1):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            logger.info(f"[MFA] TOTP有効化: {request.user.username}")
            messages.success(request, "✅ 2段階認証を有効にしました")
            return redirect("mfa-settings")
        else:
            messages.error(request, "認証コードが正しくありません。もう一度入力してください。")
            secret_plain = device.get_secret()
            qr_base64 = self._generate_qr(request.user.username, secret_plain)
            return render(request, "mfa/totp_setup.html", {
                "qr_base64": qr_base64,
                "secret_key": secret_plain,
            })

    @staticmethod
    def _generate_qr(username, secret):
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=username, issuer_name=APP_NAME)
        img = qrcode.make(uri, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")


class TOTPDisableView(LoginRequiredMixin, View):
    """TOTP無効化"""

    def post(self, request):
        TOTPDevice.objects.filter(user=request.user).delete()
        logger.info(f"[MFA] TOTP無効化: {request.user.username}")
        messages.success(request, "2段階認証を無効にしました")
        return redirect("mfa-settings")


class TOTPVerifyView(View):
    """ログイン後のTOTP検証画面"""

    def get(self, request):
        if "_2fa_user_id" not in request.session:
            return redirect("login")
        return render(request, "mfa/totp_verify.html")

    def post(self, request):
        user_id = request.session.get("_2fa_user_id")
        if not user_id:
            return redirect("login")

        code = request.POST.get("code", "").strip()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return redirect("login")

        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if not device:
            return redirect("login")

        totp = pyotp.TOTP(device.get_secret())
        if totp.verify(code, valid_window=1):
            # 2FA成功 → 本ログイン
            del request.session["_2fa_user_id"]
            backend = request.session.pop("_2fa_backend", None)
            login(request, user, backend=backend)
            next_url = request.session.pop("_2fa_next", "/")
            logger.info(f"[MFA] TOTP認証成功: {user.username}")
            return redirect(next_url)
        else:
            messages.error(request, "認証コードが正しくありません")
            return render(request, "mfa/totp_verify.html")


# ===========================================================================
# パスキー（WebAuthn）
# ===========================================================================


class PasskeyRegisterBeginView(LoginRequiredMixin, View):
    """パスキー登録開始（チャレンジ生成）"""

    def post(self, request):
        user = request.user
        rp_id = _get_rp_id(request)

        existing_creds = WebAuthnCredential.objects.filter(user=user)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=c.credential_id)
            for c in existing_creds
        ]

        display_name = user.get_full_name() or user.username
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=APP_NAME,
            user_id=str(user.pk).encode(),
            user_name=user.username,
            user_display_name=display_name,
            exclude_credentials=exclude_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )

        request.session["_webauthn_register_challenge"] = bytes_to_base64url(options.challenge)

        from webauthn.helpers import options_to_json
        return JsonResponse(json.loads(options_to_json(options)), safe=False)


class PasskeyRegisterCompleteView(LoginRequiredMixin, View):
    """パスキー登録完了"""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            body = json.loads(request.body)
            challenge_b64 = request.session.pop("_webauthn_register_challenge", None)
            if not challenge_b64:
                return JsonResponse({"error": "チャレンジが見つかりません"}, status=400)

            rp_id = _get_rp_id(request)
            origin = _get_rp_origin(request)

            verification = verify_registration_response(
                credential=body,
                expected_challenge=base64url_to_bytes(challenge_b64),
                expected_rp_id=rp_id,
                expected_origin=origin,
            )

            device_name = body.get("device_name", "マイデバイス")

            WebAuthnCredential.objects.create(
                user=request.user,
                credential_id=verification.credential_id,
                public_key=verification.credential_public_key,
                sign_count=verification.sign_count,
                name=device_name,
            )

            logger.info(f"[MFA] パスキー登録: {request.user.username} ({device_name})")
            return JsonResponse({"status": "ok"})
        except Exception as e:
            logger.error(f"[MFA] パスキー登録エラー: {e}")
            return JsonResponse({"error": str(e)}, status=400)


class PasskeyDeleteView(LoginRequiredMixin, View):
    """パスキー削除"""

    def post(self, request, pk):
        cred = WebAuthnCredential.objects.filter(pk=pk, user=request.user).first()
        if cred:
            name = cred.name
            cred.delete()
            logger.info(f"[MFA] パスキー削除: {request.user.username} ({name})")
            messages.success(request, f"パスキー「{name}」を削除しました")
        return redirect("mfa-settings")


class PasskeyLoginBeginView(View):
    """パスキーログイン開始（チャレンジ生成）"""

    def post(self, request):
        rp_id = _get_rp_id(request)

        options = generate_authentication_options(
            rp_id=rp_id,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        request.session["_webauthn_login_challenge"] = bytes_to_base64url(options.challenge)

        from webauthn.helpers import options_to_json
        return JsonResponse(json.loads(options_to_json(options)), safe=False)


class PasskeyLoginCompleteView(View):
    """パスキーログイン完了"""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            body = json.loads(request.body)
            challenge_b64 = request.session.pop("_webauthn_login_challenge", None)
            if not challenge_b64:
                return JsonResponse({"error": "チャレンジが見つかりません"}, status=400)

            raw_id = base64url_to_bytes(body["rawId"])
            cred = WebAuthnCredential.objects.filter(credential_id=raw_id).first()
            if not cred:
                return JsonResponse({"error": "パスキーが見つかりません"}, status=400)

            rp_id = _get_rp_id(request)
            origin = _get_rp_origin(request)

            verification = verify_authentication_response(
                credential=body,
                expected_challenge=base64url_to_bytes(challenge_b64),
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=bytes(cred.public_key),
                credential_current_sign_count=cred.sign_count,
            )

            cred.sign_count = verification.new_sign_count
            cred.save(update_fields=["sign_count"])

            user = cred.user
            if not user.is_active:
                return JsonResponse({"error": "アカウントが無効です"}, status=403)

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            logger.info(f"[MFA] パスキーログイン: {user.username}")
            return JsonResponse({"status": "ok"})

        except Exception as e:
            logger.error(f"[MFA] パスキーログインエラー: {e}")
            return JsonResponse({"error": str(e)}, status=400)
