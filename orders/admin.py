from django.contrib import admin
from django.db import models
from .models import Order, OrderItem, Person, Project, Workplace, Deliverable, PaymentTerm, ContractTerm, Product, OrderBasicInfo

@admin.register(OrderBasicInfo)
class OrderBasicInfoAdmin(admin.ModelAdmin):
    list_display = ('project', 'partner', 'project_start_date', 'project_end_date', 'order_issuance_timing', 'invoice_issuance_timing')
    list_filter = ('partner', 'order_issuance_timing', 'invoice_issuance_timing')
    search_fields = ('project__name', 'partner__name')
    fieldsets = (
        (None, {
            'fields': ('partner', 'project', 'project_start_date', 'project_end_date',
                       'order_issuance_timing', 'invoice_issuance_timing')
        }),
        ('期限ルール設定', {
            'fields': (
                'order_create_deadline_day', 'order_approve_deadline_days_before',
                'report_upload_deadline_days_before',
                'invoice_create_deadline_day', 'invoice_approve_deadline_day',
                'reminder_days_before', 'alert_days_after',
            ),
            'classes': ('collapse',),
            'description': 'デフォルト値が設定されています。プロジェクトごとに変更が必要な場合のみ編集してください。',
        }),
    )




class OrderItemInline(admin.TabularInline):
    model = OrderItem
    fields = ('person_name', 'effort', 'base_fee', 'actual_hours', 'time_lower_limit', 'time_upper_limit', 'shortage_rate', 'excess_rate', 'price')
    readonly_fields = ('price',)
    extra = 1

class PersonInline(admin.TabularInline):
    model = Person
    extra = 1

from django.utils.html import format_html
from django.urls import reverse
from django import forms

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'partner', 'project', 'status', 'order_end_ym', 'order_date', 'view_pdf_links')
    list_filter = ('status', 'order_end_ym', 'partner')
    search_fields = ('order_id', 'partner__name', 'project__name')
    inlines = [OrderItemInline, PersonInline]
    date_hierarchy = 'order_date'
    
    fieldsets = (
        ('基本情報', {
            'fields': ('order_id', 'partner', 'project', 'status', 'order_date', 'order_end_ym', 'work_start', 'work_end')
        }),
        ('担当者・責任者情報', {
            'fields': ('甲_責任者', '甲_担当者', '乙_責任者', '乙_担当者', '作業責任者'),
            'description': 'PDFの各欄に表示される担当者・責任者名を入力します。'
        }),
        ('契約・支払条件', {
            'fields': (
                'workplace', 'deliverable', 'deliverable_text',
                'payment_term', 'payment_condition',
                'contract_term', 'contract_items'
            )
        }),
        ('履歴・コンプライアンス（電帳法対応）', {
            'fields': ('finalized_at', 'document_hash', 'order_pdf', 'acceptance_pdf'),
            'classes': ('collapse',),
        }),
        ('外部連携', {
            'fields': ('external_signature_id', 'drive_file_id'),
            'classes': ('collapse',),
        }),
        ('その他', {
            'fields': ('remarks',)
        }),
    )
    readonly_fields = ('order_id',)
    
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 6, 'cols': 80})},
    }

    def view_pdf_links(self, obj):
        order_url = reverse('orders:admin_order_pdf', args=[obj.order_id])
        acceptance_url = reverse('orders:admin_acceptance_pdf', args=[obj.order_id])
        return format_html(
            '<a class="button" href="{}" target="_blank">注文書</a>&nbsp;'
            '<a class="button" href="{}" target="_blank" style="background-color: #4b5563;">請書</a>',
            order_url, acceptance_url
        )
    view_pdf_links.short_description = "PDFプレビュー"

    actions = ['upload_to_drive']

    def upload_to_drive(self, request, queryset):
        from .services.google_drive_service import upload_order_pdf
        success = 0
        failed = 0
        for order in queryset:
            if not order.order_pdf:
                self.message_user(request, f"{order.order_id}: PDFが生成されていません。先に正式発行してください。", level='warning')
                failed += 1
                continue
            try:
                result = upload_order_pdf(order)
                order.drive_file_id = result['file_id']
                order.save(update_fields=['drive_file_id'])
                success += 1
            except Exception as e:
                self.message_user(request, f"{order.order_id}: アップロード失敗 - {e}", level='error')
                failed += 1
        if success:
            self.message_user(request, f"{success}件の注文書をGoogleドライブにアップロードしました。")
    upload_to_drive.short_description = "Google Driveにアップロード"

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_id', 'customer', 'name')
    list_filter = ('customer',)
    search_fields = ('name', 'customer__name')
    readonly_fields = ('project_id',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price')
    search_fields = ('name',)

# その他のマスタも簡易登録
admin.site.register(Workplace)
admin.site.register(Deliverable)
@admin.register(PaymentTerm)
class PaymentTermAdmin(admin.ModelAdmin):
    list_display = ('partner', 'project')
    list_filter = ('partner',)
    search_fields = ('partner__name', 'project__name')

@admin.register(ContractTerm)
class ContractTermAdmin(admin.ModelAdmin):
    list_display = ('partner', 'project')
    list_filter = ('partner',)
    search_fields = ('partner__name', 'project__name')
