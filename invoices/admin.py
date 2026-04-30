from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import reverse

from .models import Invoice, InvoiceItem, ReceivedEmail
from .services.billing_calculator import BillingCalculator
from .services.invoice_email_service import send_review_request, send_invoice_notification




# ============================================================
# Invoice
# ============================================================

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    fields = (
        'person_name', 'work_time', 'base_fee',
        'time_lower_limit', 'time_upper_limit',
        'shortage_rate', 'excess_rate',
        'item_subtotal', 'remarks',
    )
    readonly_fields = ('item_subtotal',)
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_no', 'order', 'target_month',
        'total_amount', 'status', 'view_pdf_links',
    )
    list_filter = ('status', 'target_month')
    search_fields = ('invoice_no', 'order__order_id', 'order__partner__name')
    readonly_fields = (
        'invoice_no', 'subtotal_amount', 'tax_amount',
        'total_amount', 'acceptance_no',
    )
    inlines = [InvoiceItemInline]

    fieldsets = (
        ('基本情報', {
            'fields': ('order', 'invoice_no', 'acceptance_no', 'status', 'department'),
        }),
        ('日付', {
            'fields': (
                'target_month', 'issue_date', 'acceptance_date',
                'payment_deadline', 'payment_date',
            ),
        }),
        ('稼働報告書', {
            'fields': ('work_report_file',),
            'description': 'Excel等の稼働報告書ファイルを添付してください。',
        }),
        ('計算結果（自動計算）', {
            'fields': ('subtotal_amount', 'tax_amount', 'total_amount'),
            'description': '明細を保存すると、自動的に合計金額が計算されます。',
        }),
    )

    # 有効なステータス遷移の定義
    VALID_TRANSITIONS = {
        'DRAFT': ['PENDING_REVIEW'],
        'PENDING_REVIEW': ['ISSUED', 'DRAFT'],
        'ISSUED': ['SENT'],
        'SENT': ['CONFIRMED'],
        'CONFIRMED': ['PAID'],
    }

    # ----------------------------------------------------------
    # save hooks
    # ----------------------------------------------------------

    def save_model(self, request, obj, form, change):
        old_status = self._get_old_status(obj) if change else None

        if old_status and old_status != obj.status:
            if not self._validate_transition(request, obj, old_status):
                return

        super().save_model(request, obj, form, change)

        if old_status and old_status != obj.status:
            self._handle_status_change(request, obj, old_status)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        BillingCalculator.calculate_invoice(form.instance)

    # ----------------------------------------------------------
    # status transition helpers
    # ----------------------------------------------------------

    @staticmethod
    def _get_old_status(obj):
        """DB上の現在のステータスを取得"""
        try:
            return Invoice.objects.get(pk=obj.pk).status
        except Invoice.DoesNotExist:
            return None

    def _validate_transition(self, request, obj, old_status):
        """ステータス遷移の妥当性を検証。無効な場合はFalseを返す。"""
        valid_next = self.VALID_TRANSITIONS.get(old_status, [])
        if obj.status in valid_next:
            return True

        labels = dict(Invoice.STATUS_CHOICES)
        valid_str = ' → '.join(valid_next) if valid_next else 'なし'
        messages.error(
            request,
            f'ステータスを「{labels.get(old_status)}」から'
            f'「{labels.get(obj.status)}」に変更できません。'
            f'（許可される遷移先: {valid_str}）',
        )
        obj.status = old_status
        super(InvoiceAdmin, self).save_model(request, obj, None, True)
        return False

    def _handle_status_change(self, request, obj, old_status):
        """ステータス変更に応じたメール通知"""
        if old_status == 'DRAFT' and obj.status == 'PENDING_REVIEW':
            ok, msg = send_review_request(obj, request)
        elif old_status == 'PENDING_REVIEW' and obj.status == 'ISSUED':
            ok, msg = send_invoice_notification(obj, request)
        else:
            return

        level = messages.SUCCESS if ok else messages.ERROR
        self.message_user(request, msg, level=level)

    # ----------------------------------------------------------
    # display helpers
    # ----------------------------------------------------------

    @admin.display(description='PDF発行')
    def view_pdf_links(self, obj):
        if not obj.pk:
            return '-'
        invoice_url = reverse('invoices:admin_invoice_pdf', args=[obj.pk])
        payment_url = reverse('invoices:admin_payment_notice_pdf', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank">請求書</a>&nbsp;'
            '<a class="button" href="{}" target="_blank"'
            ' style="background-color: #4b5563;">支払通知書</a>',
            invoice_url, payment_url,
        )


# ============================================================
# ReceivedEmail
# ============================================================

@admin.register(ReceivedEmail)
class ReceivedEmailAdmin(admin.ModelAdmin):
    list_display = (
        'received_at', 'from_email', 'subject',
        'partner', 'status', 'attachment_filename',
    )
    list_filter = ('status', 'received_at')
    search_fields = ('from_email', 'from_name', 'subject', 'partner__name')
    readonly_fields = ('message_id', 'created_at', 'processed_at')
    raw_id_fields = ('partner', 'monthly_timesheet')
