"""
招待メール作成・送信ユーティリティ
"""
import secrets
import string

from django.core.mail import send_mail
from django.template import Template, Context

from .domain.models import CompanyInfo, SentEmailLog, EmailTemplate


def _get_login_url():
    """ログインURLを取得する。CSRF_TRUSTED_ORIGINS の最初のURLをベースにする。"""
    from django.conf import settings
    origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
    if origins:
        return f"{origins[0].rstrip('/')}/accounts/login/"
    return 'http://localhost:8000/accounts/login/'


def generate_random_password(length=10):
    """ランダムパスワードを生成する。"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def compose_invitation_email(partner, email, password):
    """
    招待メールの件名と本文を生成する（送信はしない）。
    Returns: (subject, body)
    """
    company = CompanyInfo.objects.first()
    if not company:
        company = CompanyInfo()

    context = {
        'company_name': company.name,
        'company_address': company.address,
        'company_tel': company.tel,
        'partner_name': partner.name,
        'email': email,
        'password': password,
        'login_url': _get_login_url(),
    }

    template_code = 'partner_invitation'
    default_subject = "【{{ company_name }}】EDIシステム アカウント発行のご案内"
    default_body = """{{ company_name }}
{{ partner_name }} 様

EDIシステムをご案内いたします。

この度、弊社との取引に関連して、EDIシステムのアカウントを発行いたしました。
本システムでは、注文書の確認、および会社情報の登録を行っていただけます。

以下の情報を使用してログインし、まず初めに「基本情報登録」をお願いいたします。

■ ログイン情報
ログインURL: {{ login_url }}
ログインID: {{ email }}
仮パスワード: {{ password }}

■ 初回ログイン後の流れ
1. 仮パスワードでログインしてください。
2. 自動的にパスワード変更画面が表示されますので、新しいパスワードを設定してください。
3. ダッシュボードの「会社情報を登録・更新する」より、貴社の基本情報および振込先情報の入力をお願いいたします。

本メールに心当たりがない場合は、お手数ですが破棄していただくか、弊社窓口までご連絡ください。

--------------------------------------------------
{{ company_name }}
{{ company_address }}
TEL: {{ company_tel }}
--------------------------------------------------
"""
    template, _ = EmailTemplate.objects.get_or_create(
        code=template_code,
        defaults={
            'subject': default_subject,
            'body': default_body,
            'description': '新規パートナー招待メール'
        }
    )

    ctx = Context(context)
    subject = Template(template.subject).render(ctx)
    body = Template(template.body).render(ctx)
    return subject, body


def send_invitation_email(partner, email, password):
    """招待メールを作成し、送信する。SentEmailLog にも記録する。"""
    subject, body = compose_invitation_email(partner, email, password)

    SentEmailLog.objects.create(
        partner=partner,
        subject=subject,
        body=body,
        recipient=email,
    )

    try:
        send_mail(
            subject,
            body,
            f"noreply@{email.split('@')[1]}",
            [email],
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send invitation email: {e}")
        raise
