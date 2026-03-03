from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class AdminCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="メールアドレス")

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        user.is_superuser = True
        if commit:
            user.save()
            from .domain.models import Profile
            Profile.objects.get_or_create(user=user)
        return user

from .domain.models import Partner

class PartnerUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="メールアドレス")
    partner = forms.ModelChoiceField(
        queryset=Partner.objects.all(),
        required=True,
        label="パートナー",
        help_text="このユーザーが所属するパートナーを選択してください。"
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            from .domain.models import Profile
            profile, created = Profile.objects.get_or_create(user=user)
            profile.partner = self.cleaned_data.get('partner')
            profile.save()
        return user


class PartnerOnboardingForm(forms.ModelForm):
    """パートナー情報登録フォーム"""
    class Meta:
        model = Partner
        fields = [
            'name', 'name_kana', 'postal_code', 'address', 'tel', 'fax', 'email',
            'representative_name', 'representative_name_kana', 'representative_position',
            'registration_no', 'attachment_file',
            'bank_name', 'bank_branch', 'account_type', 'account_number', 'account_name',
        ]
        widgets = {
            'registration_no': forms.TextInput(attrs={'placeholder': 'T1234567890123'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attachment_file'].widget.attrs.update({'class': 'file-input'})

    def clean_registration_no(self):
        registration_no = self.cleaned_data.get('registration_no')
        if registration_no:
            import re
            from django.utils.translation import gettext_lazy as _
            if not re.match(r'^T\d{13}$', registration_no.strip()):
                raise forms.ValidationError(_("登録番号はTから始まる13桁の数値で入力してください。"))
        return registration_no.strip() if registration_no else ''


class QuickPartnerRegistrationForm(forms.Form):
    """自社担当者がパートナーとユーザーを同時に登録するフォーム"""
    company_name = forms.CharField(max_length=128, label="パートナー企業名", help_text="正式名称を入力してください。")
    email = forms.EmailField(required=True, label="担当者メールアドレス", help_text="ログインIDとして使用されます。")

    def clean_email(self):
        email = self.cleaned_data.get('email')
        from django.contrib.auth.models import User
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("このメールアドレスは既に登録されています。")
        return email

    def save(self):
        import secrets
        import string
        from django.db import transaction
        from django.contrib.auth.models import User
        from .domain.models import Partner, Profile, MasterContractProgress
        
        with transaction.atomic():
            email = self.cleaned_data["email"]
            company_name = self.cleaned_data["company_name"]
            
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for i in range(10))
            
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password
            )
            
            partner = Partner.objects.create(
                name=company_name,
                email=email
            )
            
            profile, created = Profile.objects.get_or_create(user=user)
            profile.partner = partner
            profile.save()
            
            MasterContractProgress.objects.create(partner=partner, status='INVITED')
            
            self.send_invitation_email(partner, email, password)
            
            user.raw_password = password
            return user

    def send_invitation_email(self, partner, email, password):
        from django.core.mail import send_mail
        from django.template import Template, Context
        from .domain.models import CompanyInfo, SentEmailLog, EmailTemplate
        
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
            'login_url': 'http://localhost:8000/accounts/login/', 
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
        template, created = EmailTemplate.objects.get_or_create(
            code=template_code,
            defaults={
                'subject': default_subject,
                'body': default_body,
                'description': '新規パートナー招待メール'
            }
        )
        
        subject_template = Template(template.subject)
        body_template = Template(template.body)
        
        ctx = Context(context)
        subject = subject_template.render(ctx)
        message = body_template.render(ctx)
        
        SentEmailLog.objects.create(
            partner=partner,
            subject=subject,
            body=message
        )
        
        try:
            send_mail(
                subject,
                message,
                f"noreply@{email.split('@')[1]}",
                [email],
                fail_silently=False,
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send invitation email: {e}")
