from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Invoice
from .services.billing_calculator import BillingCalculator

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_no', 'order', 'target_month', 'work_time', 'total_amount', 'status', 'view_pdf_link')
    list_filter = ('status', 'target_month')
    search_fields = ('invoice_no', 'order__order_id', 'order__customer__name')
    readonly_fields = ('invoice_no', 'excess_amount', 'deduction_amount', 'subtotal_amount', 'tax_amount', 'total_amount', 'acceptance_no')
    
    fieldsets = (
        ('基本情報', {
            'fields': ('order', 'invoice_no', 'acceptance_no', 'status')
        }),
        ('日付', {
            'fields': ('target_month', 'issue_date', 'acceptance_date', 'payment_deadline')
        }),
        ('検収入力（SES）', {
            'fields': ('work_time',),
            'description': '実稼働時間を入力して保存すると、自動的に金額計算が行われます。'
        }),
        ('計算結果（自動計算）', {
            'fields': ('excess_amount', 'deduction_amount', 'subtotal_amount', 'tax_amount', 'total_amount')
        }),
    )

    def save_model(self, request, obj, form, change):
        # 保存前に計算を実行
        # work_timeとOrder情報から金額算出
        obj = BillingCalculator.calculate(obj)
        super().save_model(request, obj, form, change)

    def view_pdf_link(self, obj):
        if obj.pk:
            url = reverse('invoices:admin_invoice_pdf', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">PDF発行</a>', url)
        return "-"
    view_pdf_link.short_description = "PDF"
