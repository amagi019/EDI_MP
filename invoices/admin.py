from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
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
    search_fields = ('invoice_no', 'order__order_id', 'order__partner__name')
    readonly_fields = ('invoice_no', 'subtotal_amount', 'tax_amount', 'total_amount', 'acceptance_no')
    inlines = [InvoiceItemInline]
    
    fieldsets = (
        ('基本情報', {
            'fields': ('order', 'invoice_no', 'acceptance_no', 'status', 'department')
        }),
        ('日付', {
            'fields': ('target_month', 'issue_date', 'acceptance_date', 'payment_deadline', 'payment_date')
        }),
        ('稼働報告書', {
            'fields': ('work_report_file',),
            'description': 'Excel等の稼働報告書ファイルを添付してください。'
        }),
        ('計算結果（自動計算）', {
            'fields': ('subtotal_amount', 'tax_amount', 'total_amount'),
            'description': '明細を保存すると、自動的に合計金額が計算されます。'
        }),
    )

    def save_model(self, request, obj, form, change):
        old_status = None
        if change and obj.pk:
            try:
                old_status = Invoice.objects.get(pk=obj.pk).status
            except Invoice.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

        # ステータスが「発行済」に変更された場合、パートナーへ送付メールを送信
        if old_status and old_status != 'ISSUED' and obj.status == 'ISSUED':
            self._send_invoice_notification(request, obj)

    def _send_invoice_notification(self, request, invoice):
        """請求書（支払通知書）送付メールをパートナーへ送信"""
        partner = invoice.order.partner if invoice.order else None
        if not partner or not partner.email:
            self.message_user(request, "パートナーのメールアドレスが設定されていないため、メール通知は送信されませんでした。", level='warning')
            return

        login_url = f"{settings.CSRF_TRUSTED_ORIGINS[0].rstrip('/')}/accounts/login/" if settings.CSRF_TRUSTED_ORIGINS else "http://localhost:8000/accounts/login/"
        subject = f"【支払通知書送付】請求番号：{invoice.invoice_no}"
        message = f"""{partner.name} 様

以下の支払通知書を送付いたします。
システムにログインして内容をご確認の上、承認をお願いいたします。

■請求番号：{invoice.invoice_no}
■対象年月：{invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定'}
■税込合計：¥{invoice.total_amount:,}-

▼ログインURL
{login_url}

ご不明な点がございましたら、担当者までお問い合わせください。
"""
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [partner.email], fail_silently=False)
            self.message_user(request, f"パートナー ({partner.email}) へ送付メールを送信しました。")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Invoice notification email failed for {invoice.invoice_no}: {e}")
            self.message_user(request, f"メール送信に失敗しました: {e}", level='error')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # 明細保存後に、各明細の計算と請求合計の算出を行う
        BillingCalculator.calculate_invoice(form.instance)

    def view_pdf_links(self, obj):
        if obj.pk:
            invoice_url = reverse('invoices:admin_invoice_pdf', args=[obj.pk])
            payment_notice_url = reverse('invoices:admin_payment_notice_pdf', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" target="_blank">請求書</a>&nbsp;'
                '<a class="button" href="{}" target="_blank" style="background-color: #4b5563;">支払通知書</a>',
                invoice_url, payment_notice_url
            )
        return "-"
    view_pdf_links.short_description = "PDF発行"
