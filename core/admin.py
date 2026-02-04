from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .domain.models import Profile, Customer, CompanyInfo, BankMaster

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_id', 'name', 'tel', 'email', 'registration_no')
    search_fields = ('name', 'email', 'registration_no')
    readonly_fields = ('customer_id',)
    fieldsets = (
        (None, {
            'fields': ('customer_id', 'name', 'name_kana', 'registration_no', 'postal_code', 'address', 'tel', 'fax', 'email', 'cc', 'bcc')
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

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'customer', 'is_first_login')
    list_filter = ('is_first_login', 'customer')
    search_fields = ('user__username', 'customer__name')

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
