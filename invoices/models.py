from django.db import models
from django.utils.translation import gettext_lazy as _
from orders.models import Order
import datetime

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', _('下書き')),
        ('PENDING_REVIEW', _('確認待ち')),
        ('ISSUED', _('発行済')),
        ('SENT', _('送付済')),
        ('CONFIRMED', _('パートナー承諾済')),
        ('PAID', _('支払済')),
    ]

    class Meta:
        verbose_name = _("請求・支払通知書")
        verbose_name_plural = _("請求・支払通知書")

    order = models.OneToOneField(Order, on_delete=models.CASCADE, verbose_name=_("注文"), related_name='invoice')
    
    # 請求・支払通知書番号
    invoice_no = models.CharField(_("請求番号"), max_length=20, unique=True, help_text="YYMM+3桁連番 (例: 2602001)")
    acceptance_no = models.CharField(_("検収番号"), max_length=22, blank=True, help_text="MP+請求番号")
    
    target_month = models.DateField(_("対象年月"), help_text="請求対象月")
    issue_date = models.DateField(_("作成日"), default=datetime.date.today)
    acceptance_date = models.DateField(_("検収日"), null=True, blank=True)
    payment_deadline = models.DateField(_('支払締切日'), null=True, blank=True)
    payment_date = models.DateField(_('支払日'), null=True, blank=True, help_text='実際に支払を行った日付')
    
    department = models.CharField(_('部署名'), max_length=128, blank=True, help_text='請求書に表示する部署名')
    
    # 稼働報告書（エビデンス）
    work_report_file = models.FileField(_('稼働報告書'), upload_to='invoices/work_reports/', blank=True, null=True, help_text='Excel等の稼働報告書ファイル')
    
    # サマリ金額（InvoiceItemの合計）
    subtotal_amount = models.IntegerField(_("税抜合計"), default=0)
    tax_amount = models.IntegerField(_("消費税"), default=0)
    total_amount = models.IntegerField(_("税込合計"), default=0)
    
    status = models.CharField(_("ステータス"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.invoice_no} ({self.order.project.name})"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('invoices:invoice_detail', kwargs={'invoice_id': self.pk})

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            # YYMM形式の接頭辞を作成
            prefix = datetime.date.today().strftime('%y%m')
            # 同一接頭辞の最大値を取得
            last_invoice = Invoice.objects.filter(invoice_no__startswith=prefix).order_by('-invoice_no').first()
            if last_invoice:
                try:
                    last_seq = int(last_invoice.invoice_no[4:])
                    next_seq = last_seq + 1
                except ValueError:
                    next_seq = 1
            else:
                next_seq = 1
            self.invoice_no = f"{prefix}{str(next_seq).zfill(3)}"
        
        if self.invoice_no:
            self.acceptance_no = f"MP{self.invoice_no}"

        # 支払期限の自動計算（Order の PaymentTerm から算出）
        if not self.payment_deadline and self.target_month and self.order_id:
            if self.order.payment_term:
                self.payment_deadline = self.order.payment_term.calculate_deadline(self.target_month)
            else:
                # PaymentTerm 未設定時のフォールバック: 翌月末日
                import calendar
                m = self.target_month.month + 1
                y = self.target_month.year
                if m > 12:
                    m -= 12
                    y += 1
                last_day = calendar.monthrange(y, m)[1]
                self.payment_deadline = datetime.date(y, m, last_day)

        super().save(*args, **kwargs)

class InvoiceItem(models.Model):
    """請求明細（作業者ごとの精算）"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    person_name = models.CharField(_("名前"), max_length=64)
    
    # SES実績
    work_time = models.DecimalField(_("実稼働時間"), max_digits=6, decimal_places=2, default=0.00)
    
    # 精算条件（計算用、Order/OrderItemからコピー）
    base_fee = models.IntegerField(_("単価/基本料金"), default=0)
    time_lower_limit = models.DecimalField(_("基準時間_下限"), max_digits=5, decimal_places=2, default=0.00)
    time_upper_limit = models.DecimalField(_("基準時間_上限"), max_digits=5, decimal_places=2, default=0.00)
    shortage_rate = models.IntegerField(_("不足単価"), default=0)
    excess_rate = models.IntegerField(_("超過単価"), default=0)
    
    # 計算結果
    excess_amount = models.IntegerField(_("超過金額"), default=0)
    shortage_amount = models.IntegerField(_("控除金額"), default=0)
    item_subtotal = models.IntegerField(_("金額（税抜）"), default=0)
    
    remarks = models.CharField(_("備考"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("請求明細")
        verbose_name_plural = _("請求明細")

    def __str__(self):
        return f"{self.invoice.invoice_no} - {self.person_name}"


class WorkReport(models.Model):
    """稼働報告書（パートナーの作業責任者がアップロード）"""
    STATUS_CHOICES = [
        ('UPLOADED', _('受領済')),
        ('PARSED', _('解析済')),
        ('ALERT', _('要確認')),
        ('APPROVED', _('確定済')),
        ('ERROR', _('解析エラー')),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE,
        verbose_name=_("注文"), related_name='work_reports'
    )
    target_month = models.DateField(_("対象年月"), null=True, blank=True,
        help_text="B列の日付データから自動検出")
    worker_name = models.CharField(_("作業者氏名"), max_length=128, blank=True,
        help_text="オートシェイプまたはファイル名から自動取得")
    uploaded_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True,
        verbose_name=_("アップロード者")
    )
    uploaded_at = models.DateTimeField(_("アップロード日時"), auto_now_add=True)
    file = models.FileField(_("報告書ファイル"), upload_to='work_reports/')
    original_filename = models.CharField(_("元ファイル名"), max_length=512, blank=True)
    status = models.CharField(
        _("ステータス"), max_length=20,
        choices=STATUS_CHOICES, default='UPLOADED'
    )
    client_shared_url = models.URLField(_("共有URL"), max_length=500, blank=True)
    sent_to_client_at = models.DateTimeField(_("送付日時"), null=True, blank=True)

    # パース結果
    total_hours = models.DecimalField(
        _("合計時間"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    work_days = models.IntegerField(_("稼働日数"), null=True, blank=True)
    daily_data_json = models.JSONField(
        _("日別データ"), null=True, blank=True,
        help_text='[{"date": "2026-02-02", "hours": 8.0, "start": "9:00", "end": "18:00"}, ...]'
    )

    # チェック結果
    alerts_json = models.JSONField(
        _("警告データ"), null=True, blank=True,
        help_text='[{"date": "2026-02-08", "type": "weekend", "hours": 8.0, "day_name": "土"}, ...]'
    )
    error_message = models.TextField(_("エラーメッセージ"), blank=True)

    # Google Drive
    drive_file_id = models.CharField(
        _("DriveファイルID"), max_length=200, blank=True
    )

    class Meta:
        verbose_name = _("稼働報告書")
        verbose_name_plural = _("稼働報告書")
        ordering = ['-uploaded_at']

    def __str__(self):
        name = self.worker_name or self.original_filename
        month = self.target_month.strftime('%Y年%m月') if self.target_month else '不明'
        return f"{name} - {month}"

    @property
    def has_alerts(self):
        return bool(self.alerts_json)


class ReceivedEmail(models.Model):
    """受信メールログ（稼働報告メール取込用）"""
    STATUS_CHOICES = [
        ('NEW', _('新規')),
        ('IMPORTED', _('取込済')),
        ('FORWARDED', _('転送済')),
        ('IGNORED', _('対象外')),
        ('ERROR', _('エラー')),
    ]

    message_id = models.CharField(_("Message-ID"), max_length=512, unique=True)
    from_email = models.EmailField(_("送信元"))
    from_name = models.CharField(_("送信者名"), max_length=255, blank=True)
    subject = models.CharField(_("件名"), max_length=512)
    received_at = models.DateTimeField(_("受信日時"))
    body_text = models.TextField(_("本文"), blank=True)

    # パートナー照合
    partner = models.ForeignKey(
        'core.Partner', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name=_("照合パートナー"),
        related_name='received_emails'
    )

    # 処理結果
    status = models.CharField(
        _("ステータス"), max_length=20,
        choices=STATUS_CHOICES, default='NEW'
    )
    work_report = models.ForeignKey(
        WorkReport, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name=_("稼働報告書"),
        related_name='source_emails'
    )
    error_message = models.TextField(_("エラーメッセージ"), blank=True)

    # 添付ファイル情報
    attachment_filename = models.CharField(
        _("添付ファイル名"), max_length=512, blank=True
    )
    attachment_file = models.FileField(
        _("添付ファイル"), upload_to='received_emails/',
        blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(_("処理日時"), null=True, blank=True)

    class Meta:
        verbose_name = _("受信メール")
        verbose_name_plural = _("受信メール")
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.from_name or self.from_email} - {self.subject[:50]}"

    @property
    def status_badge_style(self):
        styles = {
            'NEW': 'background: rgba(245,158,11,0.15); color: #F59E0B;',
            'IMPORTED': 'background: rgba(16,185,129,0.15); color: #10B981;',
            'FORWARDED': 'background: rgba(79,70,229,0.15); color: #818CF8;',
            'IGNORED': 'background: rgba(148,163,184,0.15); color: #94A3B8;',
            'ERROR': 'background: rgba(239,68,68,0.15); color: #EF4444;',
        }
        return styles.get(self.status, styles['NEW'])
