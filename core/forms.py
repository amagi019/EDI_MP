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
        from .utils import send_invitation_email
        send_invitation_email(partner, email, password)
