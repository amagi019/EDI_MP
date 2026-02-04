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

from .domain.models import Customer

class PartnerUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="メールアドレス")
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=True,
        label="取引先",
        help_text="このユーザーが所属する取引先を選択してください。"
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            from .domain.models import Profile
            profile, created = Profile.objects.get_or_create(user=user)
            profile.customer = self.cleaned_data.get('customer')
            profile.save()
        return user


class PartnerOnboardingForm(forms.ModelForm):
    """パートナー情報登録フォーム（改善版）"""
    class Meta:
        model = Customer
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
        # レイアウト調整（自作CSS用）
        self.fields['attachment_file'].widget.attrs.update({'class': 'file-input'})

    def clean_registration_no(self):
        registration_no = self.cleaned_data.get('registration_no')
        if registration_no:
            # 簡易バリデーション: Tから始まる14桁
            import re
            from django.utils.translation import gettext_lazy as _
            if not re.match(r'^T\d{13}$', registration_no.strip()):
                raise forms.ValidationError(_("登録番号はTから始まる13桁の数値で入力してください。"))
        return registration_no.strip() if registration_no else ''


class QuickPartnerRegistrationForm(forms.Form):
    """自社担当者が取引先名とユーザーを同時に登録するフォーム（パスワード自動生成）"""
    company_name = forms.CharField(max_length=128, label="取引先企業名", help_text="正式名称を入力してください。")
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
        from .domain.models import Customer, Profile, MasterContractProgress
        
        with transaction.atomic():
            email = self.cleaned_data["email"]
            company_name = self.cleaned_data["company_name"]
            
            # 10桁のパスワードを自動生成
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for i in range(10))
            
            # User作成
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password
            )
            
            # Customer作成
            customer = Customer.objects.create(
                name=company_name,
                email=email
            )
            
            # Profile作成と紐付け
            profile, created = Profile.objects.get_or_create(user=user)
            profile.customer = customer
            profile.save()
            
            # 進捗状況の初期化
            MasterContractProgress.objects.create(customer=customer, status='INVITED')
            
            # メール送信 (生成したパスワードを含める)
            self.send_invitation_email(customer, email, password)
            
            user.raw_password = password
            return user

    def send_invitation_email(self, customer, email, password):
        from django.core.mail import send_mail
        from django.template.loader import render_to_string
        from .domain.models import CompanyInfo, SentEmailLog
        
        company = CompanyInfo.objects.first()
        if not company:
            company = CompanyInfo() # デフォルト値を使用
            
        context = {
            'company_name': company.name,
            'company_address': company.address,
            'company_tel': company.tel,
            'partner_name': customer.name,
            'email': email,
            'password': password,
            'login_url': 'http://localhost:8000/accounts/login/', # 本番環境ではドメインを動的に取得すべき
        }
        
        subject = f"【{company.name}】EDIシステム アカウント発行のご案内"
        message = render_to_string('core/emails/partner_invitation.txt', context)
        
        # メールログの記録
        SentEmailLog.objects.create(
            customer=customer,
            subject=subject,
            body=message
        )
        
        try:
            send_mail(
                subject,
                message,
                f"noreply@{email.split('@')[1]}", # 簡易的な送信元
                [email],
                fail_silently=False,
            )
        except Exception as e:
            # 送信失敗してもユーザー登録自体は完了しているため、エラーログのみ記録
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send invitation email: {e}")
