from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from .models import Invoice, InvoiceItem, WorkReport, ReceivedEmail
from core.domain.models import SentEmailLog
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

    # 有効なステータス遷移の定義
    VALID_TRANSITIONS = {
        'DRAFT': ['PENDING_REVIEW'],
        'PENDING_REVIEW': ['ISSUED', 'DRAFT'],  # 承認 or 差戻し（確認画面から）
        'ISSUED': ['SENT'],
        'SENT': ['CONFIRMED'],
        'CONFIRMED': ['PAID'],
    }

    def save_model(self, request, obj, form, change):
        old_status = None
        if change and obj.pk:
            try:
                old_status = Invoice.objects.get(pk=obj.pk).status
            except Invoice.DoesNotExist:
                pass

        # ステータス遷移の検証
        if old_status and old_status != obj.status:
            valid_next = self.VALID_TRANSITIONS.get(old_status, [])
            if obj.status not in valid_next:
                from django.contrib import messages as admin_messages
                valid_str = ' → '.join(valid_next) if valid_next else 'なし'
                admin_messages.error(
                    request,
                    f"ステータスを「{dict(Invoice.STATUS_CHOICES).get(old_status)}」から"
                    f"「{dict(Invoice.STATUS_CHOICES).get(obj.status)}」に変更できません。"
                    f"（許可される遷移先: {valid_str}）"
                )
                obj.status = old_status  # 元に戻す
                super().save_model(request, obj, form, change)
                return

        super().save_model(request, obj, form, change)

        # ステータス遷移に応じたメール通知
        if old_status and old_status != obj.status:
            if old_status == 'DRAFT' and obj.status == 'PENDING_REVIEW':
                self._send_review_request(request, obj)
            elif old_status == 'PENDING_REVIEW' and obj.status == 'ISSUED':
                self._send_invoice_notification(request, obj)

    def _send_review_request(self, request, invoice):
        """自社担当者に確認依頼メールを送信"""
        partner = invoice.order.partner if invoice.order else None
        if not partner:
            self.message_user(request, "パートナー情報が設定されていません。", level='warning')
            return

        # 自社担当者のメールアドレス
        if partner.staff_contact and partner.staff_contact.email:
            notify_email = partner.staff_contact.email
        else:
            notify_email = settings.DEFAULT_FROM_EMAIL

        review_url = request.build_absolute_uri(
            reverse('invoices:staff_invoice_review', kwargs={'invoice_id': invoice.pk})
        )
        invoice_pdf_url = request.build_absolute_uri(
            reverse('invoices:admin_invoice_pdf', kwargs={'invoice_id': invoice.pk})
        )

        subject = f"【請求書確認依頼】請求番号：{invoice.invoice_no}"
        message = f"""以下の請求書（支払通知書）の内容確認をお願いします。

■請求番号：{invoice.invoice_no}
■パートナー：{partner.name}
■対象年月：{invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定'}
■税込合計：¥{invoice.total_amount:,}-

▼確認・承認画面
{review_url}

▼請求書PDFプレビュー
{invoice_pdf_url}

内容に問題がなければ「承認」、修正が必要な場合は「差戻し」をお願いします。
"""
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [notify_email], fail_silently=False)
            if partner:
                SentEmailLog.objects.create(
                    partner=partner, subject=subject,
                    body=message, recipient=notify_email,
                )
            self.message_user(request, f"自社担当者 ({notify_email}) へ確認依頼メールを送信しました。")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Review request email failed for {invoice.invoice_no}: {e}")
            self.message_user(request, f"確認依頼メール送信に失敗しました: {e}", level='error')

    def _send_invoice_notification(self, request, invoice):
        """請求書（支払通知書）送付メールをパートナーへ送信"""
        partner = invoice.order.partner if invoice.order else None
        if not partner or not partner.email:
            self.message_user(request, "パートナーのメールアドレスが設定されていないため、メール通知は送信されませんでした。", level='warning')
            return

        login_url = request.build_absolute_uri(reverse('login'))
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
            SentEmailLog.objects.create(
                partner=partner, subject=subject,
                body=message, recipient=partner.email,
            )
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


@admin.register(WorkReport)
class WorkReportAdmin(admin.ModelAdmin):
    list_display = ('worker_name', 'target_month', 'total_hours', 'work_days', 'status', 'order', 'uploaded_at')
    list_filter = ('status', 'target_month')
    search_fields = ('worker_name', 'original_filename', 'order__order_id')
    readonly_fields = ('uploaded_at', 'daily_data_json', 'alerts_json')
    fieldsets = (
        ('基本情報', {
            'fields': ('order', 'worker_name', 'target_month', 'status', 'uploaded_by')
        }),
        ('ファイル', {
            'fields': ('file', 'original_filename')
        }),
        ('パース結果', {
            'fields': ('total_hours', 'work_days', 'daily_data_json', 'alerts_json', 'error_message')
        }),
        ('Google Drive', {
            'fields': ('drive_file_id',),
            'classes': ('collapse',)
        }),
    )


@admin.register(ReceivedEmail)
class ReceivedEmailAdmin(admin.ModelAdmin):
    list_display = ('received_at', 'from_email', 'subject', 'partner', 'status', 'attachment_filename')
    list_filter = ('status', 'received_at')
    search_fields = ('from_email', 'from_name', 'subject', 'partner__name')
    readonly_fields = ('message_id', 'created_at', 'processed_at')
    raw_id_fields = ('partner', 'work_report')
