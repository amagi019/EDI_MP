"""
パートナーへ2段階認証の設定推奨メールを一括送信するコマンド。

Usage:
    python manage.py notify_mfa_available --dry-run   # 送信先確認のみ
    python manage.py notify_mfa_available              # 実際に送信
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from core.domain.models import Partner

logger = logging.getLogger(__name__)

SUBJECT = "【EDI Sophia】セキュリティ機能のご案内 — 2段階認証・パスキーをご利用いただけます"

BODY = """\
{partner_name}
ご担当者様

平素より大変お世話になっております。
株式会社マックプランニングです。

この度、EDI Sophia（発注管理システム）のセキュリティを強化いたしました。
新たに以下の認証機能をご利用いただけるようになりましたのでご案内申し上げます。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 2段階認証（ワンタイムパスワード）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ログイン時にパスワードに加えて、認証アプリ（Google Authenticator /
Microsoft Authenticator 等）で生成される6桁のワンタイムパスワードを
入力する仕組みです。
万が一パスワードが漏洩した場合でも、不正ログインを防止できます。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ パスキー（生体認証ログイン）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
指紋認証（Touch ID）や顔認証（Face ID / Windows Hello）を使って、
パスワードを入力せずに安全にログインできる機能です。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 設定方法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. EDI Sophia にログインしてください
   {login_url}
2. サイドバーの「セキュリティ設定」をクリック
   または直接アクセス: {security_url}
3. 画面の案内に従って設定してください

※ 現在のユーザーID・パスワードでのログインは引き続きご利用いただけます。
※ 2段階認証・パスキーの設定は任意です。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

セキュリティに関するご不明点やお困りごとがございましたら、
お気軽にお問い合わせください。

今後ともよろしくお願いいたします。

──────────────────────────
株式会社マックプランニング
EDI Sophia 管理チーム
──────────────────────────
"""


class Command(BaseCommand):
    help = "パートナー各位に2段階認証・パスキーの設定推奨メールを送信"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='実際には送信せず、送信先を表示するのみ',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        base_url = "https://edi.macplanning.com"
        login_url = f"{base_url}/accounts/login/"
        security_url = f"{base_url}/accounts/security/"

        partners = Partner.objects.filter(email__isnull=False).exclude(email='')
        self.stdout.write(f"対象パートナー: {partners.count()}社")

        sent = 0
        errors = 0

        for partner in partners:
            email = partner.email
            body = BODY.format(
                partner_name=partner.name,
                login_url=login_url,
                security_url=security_url,
            )

            if dry_run:
                self.stdout.write(f"  [DRY-RUN] {partner.name} <{email}>")
                continue

            try:
                send_mail(
                    SUBJECT,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"  ✅ {partner.name} <{email}>"))
                logger.info(f"[MFA通知] メール送信: {partner.name} ({email})")
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  ❌ {partner.name} <{email}> - {e}"))
                logger.error(f"[MFA通知] メール送信失敗: {partner.name} ({email}) - {e}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n[DRY-RUN] 送信はされていません。--dry-run を外して実行してください。"))
        else:
            self.stdout.write(f"\n送信完了: {sent}通 / エラー: {errors}通")
