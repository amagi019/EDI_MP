from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from .domain.models import Profile, Partner, Customer, CompanyInfo, BankMaster, SentEmailLog, MasterContractProgress, EmailTemplate

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'tel', 'email', 'registration_no', 'representative_name')
    search_fields = ('name', 'registration_no')

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ('partner_id', 'name', 'tel', 'email', 'registration_no')
    search_fields = ('name', 'email', 'registration_no')
    readonly_fields = ('partner_id',)
    actions = ['prepare_invitation_email']
    fieldsets = (
        (None, {
            'fields': ('partner_id', 'name', 'name_kana', 'registration_no', 'postal_code', 'address', 'tel', 'fax', 'email', 'cc', 'bcc')
        }),
        (_('代表者・担当者情報'), {
            'fields': ('representative_name', 'representative_name_kana', 'representative_position', 'responsible_person', 'contact_person')
        }),
        (_('銀行口座情報'), {
            'fields': ('bank_name', 'bank_branch', 'account_type', 'account_number', 'account_name')
        }),
        (_('添付書類'), {
            'fields': ('attachment_file',)
        }),
    )

    def get_urls(self):
        custom_urls = [
            path('invitation-preview/', self.admin_site.admin_view(self.invitation_preview_view), name='partner_invitation_preview'),
            path('invitation-send/', self.admin_site.admin_view(self.invitation_send_view), name='partner_invitation_send'),
        ]
        return custom_urls + super().get_urls()

    @admin.action(description="招待メール作成（アカウント作成）")
    def prepare_invitation_email(self, request, queryset):
        """選択パートナーに対してアカウント作成＋メールプレビューを表示"""
        from django.contrib.auth.models import User
        from .utils import compose_invitation_email, generate_random_password

        preview_data = []
        skipped = []

        for partner in queryset:
            # 既にアカウントが存在するかチェック
            if Profile.objects.filter(partner=partner).exists():
                skipped.append(partner.name)
                continue

            if not partner.email:
                skipped.append(f"{partner.name}（メールアドレス未登録）")
                continue

            password = generate_random_password()

            # ユーザーアカウント作成
            user = User.objects.create_user(
                username=partner.email,
                email=partner.email,
                password=password,
            )
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.partner = partner
            profile.save()

            # 基本契約進捗を作成
            MasterContractProgress.objects.get_or_create(
                partner=partner,
                defaults={'status': 'INVITED'}
            )

            subject, body = compose_invitation_email(partner, partner.email, password)
            preview_data.append({
                'partner_id': partner.partner_id,
                'partner_name': partner.name,
                'email': partner.email,
                'subject': subject,
                'body': body,
            })

        if skipped:
            self.message_user(request, f"スキップ: {', '.join(skipped)}（既にアカウントあり、またはメール未登録）", messages.WARNING)

        if not preview_data:
            self.message_user(request, "送信対象のパートナーがありません。", messages.WARNING)
            return redirect(reverse('admin:core_partner_changelist'))

        # セッションにプレビューデータを保存
        request.session['invitation_preview_data'] = preview_data
        return redirect(reverse('admin:partner_invitation_preview'))

    def invitation_preview_view(self, request):
        """メールプレビュー画面"""
        preview_data = request.session.get('invitation_preview_data', [])
        if not preview_data:
            messages.warning(request, "プレビューデータがありません。")
            return redirect(reverse('admin:core_partner_changelist'))

        context = {
            **self.admin_site.each_context(request),
            'title': '招待メール確認',
            'preview_data': preview_data,
        }
        return render(request, 'admin/core/partner/invitation_preview.html', context)

    def invitation_send_view(self, request):
        """メール送信実行"""
        if request.method != 'POST':
            return redirect(reverse('admin:core_partner_changelist'))

        preview_data = request.session.pop('invitation_preview_data', [])
        if not preview_data:
            messages.warning(request, "送信データがありません。")
            return redirect(reverse('admin:core_partner_changelist'))

        from django.core.mail import send_mail as django_send_mail

        sent_count = 0
        for item in preview_data:
            try:
                partner = Partner.objects.get(partner_id=item['partner_id'])

                SentEmailLog.objects.create(
                    partner=partner,
                    subject=item['subject'],
                    body=item['body'],
                )

                django_send_mail(
                    item['subject'],
                    item['body'],
                    f"noreply@{item['email'].split('@')[1]}",
                    [item['email']],
                    fail_silently=False,
                )
                sent_count += 1
            except Exception as e:
                messages.error(request, f"{item['partner_name']} への送信に失敗: {e}")

        if sent_count:
            messages.success(request, f"{sent_count}件の招待メールを送信しました。")
        return redirect(reverse('admin:core_partner_changelist'))

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'partner', 'is_first_login')
    list_filter = ('is_first_login', 'partner')
    search_fields = ('user__username', 'partner__name')

@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ('name', 'representative_name', 'tel', 'bank_name', 'account_number')
    fieldsets = (
        (None, {
            'fields': ('name', 'postal_code', 'address', 'tel', 'fax', 'registration_no')
        }),
        (_('代表者・担当者情報'), {
            'fields': ('representative_title', 'representative_name', 'responsible_person', 'contact_person')
        }),
        (_('銀行口座情報'), {
            'fields': ('bank_name', 'bank_branch', 'account_type', 'account_number', 'account_name')
        }),
        (_('画像'), {
            'fields': ('stamp_image', 'logo_image')
        }),
    )
@admin.register(BankMaster)
class BankMasterAdmin(admin.ModelAdmin):
    list_display = ('bank_code', 'bank_name', 'branch_code', 'branch_name')
    search_fields = ('bank_name', 'branch_name', 'bank_code')

admin.site.register(SentEmailLog)
admin.site.register(MasterContractProgress)

@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('code', 'subject', 'description', 'updated_at')
    search_fields = ('code', 'subject', 'description')
    readonly_fields = ('code', 'updated_at')
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields
        return ('updated_at',)

