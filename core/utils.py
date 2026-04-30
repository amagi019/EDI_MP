"""
招待メール作成・送信ユーティリティ
"""
import secrets
import string

from django.core.mail import send_mail
from django.template import Template, Context

from .domain.models import CompanyInfo, SentEmailLog, EmailTemplate


def normalize_name(name):
    """全角・半角スペースを除去して比較用に正規化する。"""
    return (name or '').replace(' ', '').replace('\u3000', '').strip()


def get_notify_email(partner):
    """パートナーの自社担当者メールアドレスを取得する。未設定時はDEFAULT_FROM_EMAIL。"""
    from django.conf import settings
    if partner and partner.staff_contact and partner.staff_contact.email:
        return partner.staff_contact.email
    return settings.DEFAULT_FROM_EMAIL


def _get_login_url():
    """ログインURLを取得する。settings.SITE_URL をベースにする。"""
    from django.conf import settings
    base = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    return f"{base}/accounts/login/"


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
        from django.conf import settings as django_settings
        send_mail(
            subject,
            body,
            django_settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send invitation email: {e}")
        raise


def compose_order_publish_email(order, order_url, login_url):
    """
    注文書送付メールの件名と本文を生成する（パートナー宛）。
    Returns: (subject, body)
    """
    company = CompanyInfo.objects.first()
    company_name = company.name if company else ''
    company_tel = company.tel if company else ''

    context = {
        'company_name': company_name,
        'company_tel': company_tel,
        'partner_name': order.partner.name,
        'order_id': order.order_id,
        'project_name': order.project.name if order.project else '',
        'order_date': str(order.order_date),
        'work_start': str(order.work_start),
        'work_end': str(order.work_end),
        'order_url': order_url,
        'login_url': login_url,
    }

    template_code = 'order_publish'
    default_subject = '【{{ company_name }}】注文書送付のご連絡（注文番号：{{ order_id }}）'
    default_body = """いつもお世話になっております。
{{ company_name }}でございます。

EDIシステムに注文書を登録いたしましたので、
下記URLよりログインし、注文書の内容をご確認ください。

《URL》
{{ order_url }}

《送付物》

「注文書」
「注文請書」
  各1通

《お願い》

注文書内容をご確認いただき、内容にご同意いただける場合は
「承諾」ボタンを押してください。
承諾いただけない場合はメールにてご返信ください。

※「承諾」をいただいた場合は、注文請書のご返送は不要となります。

■注文番号：{{ order_id }}
■プロジェクト：{{ project_name }}
■注文日：{{ order_date }}
■作業期間：{{ work_start }} 〜 {{ work_end }}

▼ログインURL
{{ login_url }}

操作手順について不明な点がございましたら、
ダッシュボードの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
"""

    template, _ = EmailTemplate.objects.get_or_create(
        code=template_code,
        defaults={
            'subject': default_subject,
            'body': default_body,
            'description': '注文書送付メール（パートナー宛）',
        }
    )

    ctx = Context(context)
    subject = Template(template.subject).render(ctx)
    body = Template(template.body).render(ctx)
    return subject, body


def compose_order_approve_email(order, order_url):
    """
    注文書承認通知メールの件名と本文を生成する（自社担当者宛）。
    Returns: (subject, body)
    """
    company = CompanyInfo.objects.first()
    company_name = company.name if company else ''

    context = {
        'company_name': company_name,
        'partner_name': order.partner.name,
        'order_id': order.order_id,
        'project_name': order.project.name if order.project else '',
        'order_date': str(order.order_date),
        'order_url': order_url,
    }

    template_code = 'order_approve'
    default_subject = '【承認通知】{{ partner_name }}様 注文番号：{{ order_id }}'
    default_body = """{{ partner_name }} 様より、以下の注文書が承諾されました。

■注文番号：{{ order_id }}
■プロジェクト：{{ project_name }}
■注文日：{{ order_date }}

■ 注文書確認URL:
{{ order_url }}
"""

    template, _ = EmailTemplate.objects.get_or_create(
        code=template_code,
        defaults={
            'subject': default_subject,
            'body': default_body,
            'description': '注文書承認通知メール（自社担当者宛）',
        }
    )

    ctx = Context(context)
    subject = Template(template.subject).render(ctx)
    body = Template(template.body).render(ctx)
    return subject, body


def _render_email_template(template_code, default_subject, default_body, description, context):
    """
    汎用メールテンプレートレンダリング。
    get_or_createでデフォルトテンプレートを保証し、Django Template構文でレンダリングする。
    Returns: (subject, body)
    """
    template, _ = EmailTemplate.objects.get_or_create(
        code=template_code,
        defaults={
            'subject': default_subject,
            'body': default_body,
            'description': description,
        }
    )
    ctx = Context(context)
    subject = Template(template.subject).render(ctx)
    body = Template(template.body).render(ctx)
    return subject, body


def compose_partner_info_registered_email(partner, progress_url):
    """② 基本情報登録通知メール（パートナー→自社）"""
    return _render_email_template(
        template_code='partner_info_registered',
        default_subject='【基本情報登録完了】{{ partner_name }}',
        default_body="""{{ partner_name }} 様がパートナー基本情報の登録を完了しました。

以下の内容をご確認いただき、基本契約書の作成・送付をお願いいたします。

《登録情報》
■ 会社名：{{ partner_name }}
■ 住所：{{ address }}
■ 代表者：{{ representative_name }}
■ 登録番号：{{ registration_no }}

《次のステップ》
1. 下記URLより登録内容を確認してください。
2. 問題なければ基本契約書を作成し、パートナーへ送付してください。

■ 基本契約進捗の確認:
{{ progress_url }}
""",
        description='基本情報登録通知メール（自社担当者宛）',
        context={
            'partner_name': partner.name,
            'address': partner.address or '未入力',
            'representative_name': partner.representative_name or '未入力',
            'registration_no': partner.registration_no or '未入力',
            'progress_url': progress_url,
        },
    )


def compose_contract_send_email(partner, contract_url):
    """③ 契約書承認依頼メール（自社→パートナー）"""
    company = CompanyInfo.objects.first()
    company_name = company.name if company else ''
    company_tel = company.tel if company else ''

    return _render_email_template(
        template_code='contract_send',
        default_subject='【{{ company_name }}】基本契約書のご確認（{{ partner_name }}様）',
        default_body="""{{ partner_name }}　御中

いつもお世話になっております。
{{ company_name }}でございます。

この度、基本契約書を作成いたしましたので、
下記ＵＲＬよりご確認をお願いいたします。

《URL》
{{ contract_url }}

《送付物》
「基本契約書」
  1通

《お願い》
契約書内容をご確認いただき、内容にご同意いただける場合は
「承諾」ボタンを押してください。
承諾いただけない場合はメールにてご返信ください。

※「承諾」をいただいた場合は、従来のように契約書のご返送は不要となります。

御手数ではございますが、ご協力の程お願い申し上げます。

《ご参考》
承諾済みの契約書は、ログイン後サイドバーの「基本契約書」からいつでもご確認いただけます。

操作手順について不明な点がございましたら
サイドバーの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        description='契約書承認依頼メール（パートナー宛）',
        context={
            'company_name': company_name,
            'company_tel': company_tel,
            'partner_name': partner.name,
            'contract_url': contract_url,
        },
    )


def compose_contract_approve_email(partner, contract_url, signed_at, signed_by):
    """④ 契約書承認メール（パートナー→自社）"""
    return _render_email_template(
        template_code='contract_approve',
        default_subject='【基本契約承認通知】{{ partner_name }}',
        default_body="""{{ partner_name }} 様が基本契約書を承諾しました。
契約が締結されましたのでお知らせいたします。

■ パートナー名：{{ partner_name }}
■ 承認日時：{{ signed_at }}
■ 承認者：{{ signed_by }}

■ 契約書確認URL:
{{ contract_url }}

※承諾済みの契約書PDFは上記URLよりご確認いただけます。
""",
        description='契約書承認通知メール（自社担当者宛）',
        context={
            'partner_name': partner.name,
            'contract_url': contract_url,
            'signed_at': signed_at,
            'signed_by': signed_by,
        },
    )


def compose_invoice_send_email(invoice, partner, login_url, invoice_url=''):
    """⑦ 支払通知・請求書送付メール（自社→パートナー）"""
    company = CompanyInfo.objects.first()
    company_name = company.name if company else ''
    company_tel = company.tel if company else ''

    return _render_email_template(
        template_code='invoice_send',
        default_subject='【{{ company_name }}】支払通知書送付（請求番号：{{ invoice_no }}）',
        default_body="""{{ partner_name }}　御中

いつもお世話になっております。
{{ company_name }}でございます。

EDIシステムに支払通知書を登録しましたので、
下記ＵＲＬからログインし、内容をご確認ください。

《URL》
{{ invoice_url }}

《送付物》
「支払通知書」
「請求書」
  各1通

《お願い》
請求書内容をご確認いただき、内容にご同意いただける場合は「承諾」ボタンを押してください。
承諾いただけない場合はメールにてご返信ください。

   対象月：{{ target_month }}
   税込合計：¥{{ total_amount }}-

※尚、「承諾」をいただいた場合は、従来のように請求書のご返送は不要となります。

御手数ではございますが、ご協力の程お願い申し上げます。

▼ログインURL
{{ login_url }}

操作手順について不明な点がございましたら
サイドバーの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        description='支払通知・請求書送付メール（パートナー宛）',
        context={
            'company_name': company_name,
            'company_tel': company_tel,
            'partner_name': partner.name,
            'invoice_no': invoice.invoice_no,
            'target_month': invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定',
            'total_amount': f'{invoice.total_amount:,}',
            'login_url': login_url,
            'invoice_url': invoice_url,
        },
    )


def compose_invoice_approve_email(invoice, partner, invoice_url):
    """⑧ 請求書承認メール（パートナー→自社）"""
    return _render_email_template(
        template_code='invoice_approve',
        default_subject='【請求書承認通知】請求番号：{{ invoice_no }}',
        default_body="""{{ partner_name }} 様より、以下の請求書（支払通知書）が承諾されました。

■請求番号：{{ invoice_no }}
■対象年月：{{ target_month }}
■税込合計：¥{{ total_amount }}-

■ 請求書確認URL:
{{ invoice_url }}
""",
        description='請求書承認通知メール（自社担当者宛）',
        context={
            'partner_name': partner.name,
            'invoice_no': invoice.invoice_no,
            'target_month': invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定',
            'total_amount': f'{invoice.total_amount:,}',
            'invoice_url': invoice_url,
        },
    )


def compose_work_report_reminder_email(partner, project_name, target_month_str, deadline_str):
    """⑥ 稼働報告書提出リマインドメール（自社→パートナー）"""
    company = CompanyInfo.objects.first()
    company_name = company.name if company else ''
    company_tel = company.tel if company else ''
    login_url = _get_login_url()

    return _render_email_template(
        template_code='work_report_reminder',
        default_subject='【{{ company_name }}】{{ target_month }}分 稼働報告書ご提出のお願い（{{ deadline }}締切）',
        default_body="""{{ partner_name }}　御中

いつもお世話になっております。
{{ company_name }}でございます。

{{ target_month }}分の稼働報告書のご提出をお願いいたします。

下記ＵＲＬからEDI-MPにログインし、
「稼働報告書」画面よりExcelファイルのアップロードをお願いいたします。

《URL》
{{ login_url }}

《対象プロジェクト》
{{ project_name }}

《提出期限》
{{ deadline }}

《ご注意》
・稼働報告書はExcel形式（.xlsx / .xlsm）でアップロードしてください。
・ファイルにパスワードは設定しないでください。
  受領したファイルはシステムで暗号化し厳重に管理しています。
・複数名の場合は、作業者ごとにファイルを分けてアップロードしてください。
・アップロード後、内容を確認し「確定」ボタンを押してください。

操作手順について不明な点がございましたら
サイドバーの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        description='稼働報告書提出リマインドメール（パートナー宛）',
        context={
            'company_name': company_name,
            'company_tel': company_tel,
            'partner_name': partner.name,
            'project_name': project_name,
            'target_month': target_month_str,
            'deadline': deadline_str,
            'login_url': login_url,
        },
    )


