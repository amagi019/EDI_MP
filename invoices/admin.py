from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Invoice, InvoiceItem
from .services.billing_calculator import BillingCalculator

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    fields = ('person_name', 'work_time', 'base_fee', 'time_lower_limit', 'time_upper_limit', 'shortage_rate', 'excess_rate', 'item_subtotal', 'remarks')
    readonly_fields = ('item_subtotal',)
    extra = 0

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_no', 'order', 'target_month', 'total_amount', 'status', 'view_pdf_links')
    list_filter = ('status', 'target_month')
    search_fields = ('invoice_no', 'order__order_id', 'order__customer__name')
    readonly_fields = ('invoice_no', 'subtotal_amount', 'tax_amount', 'total_amount', 'acceptance_no')
    inlines = [InvoiceItemInline]
    
    fieldsets = (
        ('基本情報', {
            'fields': ('order', 'invoice_no', 'acceptance_no', 'status', 'department')
        }),
        ('日付', {
            'fields': ('target_month', 'issue_date', 'acceptance_date', 'payment_deadline')
        }),
        ('計算結果（自動計算）', {
            'fields': ('subtotal_amount', 'tax_amount', 'total_amount'),
            'description': '明細を保存すると、自動的に合計金額が計算されます。'
        }),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # 明細保存後に、各明細の計算と請求合計の算出を行う
        BillingCalculator.calculate_invoice(form.instance)

    def view_pdf_links(self, obj):
        if obj.pk:
            invoice_url = reverse('invoices:admin_invoice_pdf', args=[obj.pk])
            # 支払い通知書用のURL（後で実装）
            payment_notice_url = reverse('invoices:admin_payment_notice_pdf', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" target="_blank">請求書</a>&nbsp;'
                '<a class="button" href="{}" target="_blank" style="background-color: #4b5563;">支払通知書</a>',
                invoice_url, payment_notice_url
            )
        return "-"
    view_pdf_links.short_description = "PDF発行"
