"""
billing ドメインモデル

売上請求書（お客様への請求書発行）のエンティティ定義。
EDI Sophia の invoices（買掛: パートナーへの支払い）とは逆方向の取引。
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import datetime
import uuid


class BillingCustomer(models.Model):
    """請求先（お客様）"""
    name = models.CharField(_("取引先名"), max_length=128)
    title = models.CharField(_("役職"), max_length=64, blank=True)
    contact_person = models.CharField(_("担当者"), max_length=64, blank=True)
    email = models.EmailField(_("メールアドレス"), blank=True)
    cc_email = models.TextField(
        _("CCメールアドレス"), blank=True,
        help_text=_("複数指定する場合はカンマ区切りで入力")
    )
    phone = models.CharField(_("電話番号"), max_length=20, blank=True)
    postal_code = models.CharField(_("郵便番号"), max_length=10, blank=True)
    address = models.CharField(_("住所1"), max_length=255, blank=True)
    address2 = models.CharField(_("住所2"), max_length=255, blank=True)
    # 報告書送付先
    report_email = models.TextField(
        _("報告書送付先メール"), blank=True,
        help_text=_("稼働報告書の送付先。複数指定する場合はカンマ区切りで入力")
    )

    class Meta:
        verbose_name = _("請求先")
        verbose_name_plural = _("請求先")
        ordering = ['name']

    def __str__(self):
        return self.name


class BillingProduct(models.Model):
    """商品・SESサービスマスタ"""
    TAX_CHOICES = [
        ('10', _('10%')),
        ('8', _('8%（軽減税率）')),
        ('0', _('非課税')),
    ]

    name = models.CharField(_("商品名"), max_length=30)
    unit_price = models.IntegerField(_("単価"), default=0)
    unit = models.CharField(_("単位"), max_length=20, default="式")
    tax_category = models.CharField(
        _("税区分"), max_length=2, choices=TAX_CHOICES, default='10'
    )

    class Meta:
        verbose_name = _("商品")
        verbose_name_plural = _("商品")
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def unit_price_fmt(self):
        return f"{self.unit_price:,}"


class BillingInvoice(models.Model):
    """売上請求書"""
    STATUS_CHOICES = [
        ('DRAFT', _('下書き')),
        ('ISSUED', _('発行済')),
        ('SENT', _('送付済')),
        ('PAID', _('入金済')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        BillingCustomer, on_delete=models.PROTECT,
        verbose_name=_("請求先"), related_name='billing_invoices'
    )
    company = models.ForeignKey(
        'core.CompanyInfo', on_delete=models.PROTECT,
        verbose_name=_("自社情報"), null=True, blank=True
    )
    issue_date = models.DateField(_("請求日"), default=datetime.date.today)
    due_date = models.DateField(_("支払期日"), null=True, blank=True)
    subject = models.CharField(_("件名"), max_length=255, blank=True)
    notes = models.TextField(_("備考"), blank=True)
    status = models.CharField(
        _("ステータス"), max_length=10, choices=STATUS_CHOICES, default='DRAFT'
    )

    # 受注への紐付け（Phase 2追加）
    received_order = models.ForeignKey(
        'billing.ReceivedOrder', on_delete=models.SET_NULL,
        verbose_name=_("受注"), null=True, blank=True,
        related_name='billing_invoices'
    )

    # PDF・ドライブ連携
    pdf_file = models.FileField(
        _("PDFファイル"), upload_to='billing/invoices/', blank=True, null=True
    )
    drive_file_id = models.CharField(
        _("DriveファイルID"), max_length=200, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("売上請求書")
        verbose_name_plural = _("売上請求書")
        ordering = ['-issue_date', '-created_at']

    def __str__(self):
        return f"{self.issue_date} - {self.customer.name} - {self.subject}"

    @property
    def status_badge_style(self):
        """ステータスバッジのインラインスタイル"""
        styles = {
            'PAID': 'background: rgba(16,185,129,0.15); color: #10B981;',
            'SENT': 'background: rgba(79,70,229,0.15); color: #818CF8;',
            'ISSUED': 'background: rgba(245,158,11,0.15); color: #F59E0B;',
            'DRAFT': 'background: rgba(148,163,184,0.15); color: #94A3B8;',
        }
        return styles.get(self.status, styles['DRAFT'])

    @property
    def invoice_number(self):
        """請求書番号（YYYYMM-連番形式）"""
        return f"INV-{self.issue_date.strftime('%Y%m')}-{str(self.pk)[:8].upper()}"

    @property
    def subtotal(self):
        """税抜合計"""
        return sum(item.amount for item in self.items.all())

    @property
    def tax_amount(self):
        """消費税合計"""
        return sum(item.tax for item in self.items.all())

    @property
    def total(self):
        """税込合計"""
        return self.subtotal + self.tax_amount

    @property
    def subtotal_fmt(self):
        return f"{self.subtotal:,}"

    @property
    def total_fmt(self):
        return f"{self.total:,}"

    @property
    def tax_summary(self):
        """税率ごとの内訳（インボイス制度対応）"""
        from collections import defaultdict
        summary = defaultdict(lambda: {'subtotal': 0, 'tax': 0})
        for item in self.items.all():
            rate = item.tax_rate_display
            summary[rate]['subtotal'] += item.amount
            summary[rate]['tax'] += item.tax
        return dict(summary)


class BillingItem(models.Model):
    """請求明細"""
    TAX_CHOICES = BillingProduct.TAX_CHOICES
    MAN_MONTH_CHOICES = [
        ('1.00', '1.00'),
        ('0.75', '0.75'),
        ('0.50', '0.50'),
        ('0.25', '0.25'),
    ]

    invoice = models.ForeignKey(
        BillingInvoice, on_delete=models.CASCADE,
        verbose_name=_("請求書"), related_name='items'
    )
    product = models.ForeignKey(
        BillingProduct, on_delete=models.SET_NULL,
        verbose_name=_("商品"), null=True, blank=True
    )
    product_name = models.CharField(
        _("商品名"), max_length=30, blank=True,
        help_text=_("商品選択で自動入力、手入力も可")
    )
    unit_price = models.IntegerField(_("単価"), default=0)
    man_month = models.DecimalField(
        _("人月"), max_digits=4, decimal_places=2, default=1,

    )
    tax_category = models.CharField(
        _("税区分"), max_length=2, choices=TAX_CHOICES, default='10'
    )
    sort_order = models.IntegerField(_("表示順"), default=0)

    class Meta:
        verbose_name = _("請求明細")
        verbose_name_plural = _("請求明細")
        ordering = ['sort_order', 'pk']

    def __str__(self):
        return f"{self.product_name} x {self.man_month}"

    @property
    def tax_rate(self):
        """税率（小数）"""
        rates = {'10': 0.10, '8': 0.08, '0': 0.0}
        return rates.get(self.tax_category, 0.10)

    @property
    def tax_rate_display(self):
        """税率表示用"""
        return dict(self.TAX_CHOICES).get(self.tax_category, '10%')

    @property
    def amount(self):
        """金額（税抜）= 単価 × 人月"""
        return int(self.unit_price * self.man_month)

    @property
    def unit_price_fmt(self):
        return f"{self.unit_price:,}"

    @property
    def amount_fmt(self):
        return f"{self.amount:,}"

    @property
    def tax(self):
        """消費税額"""
        return int(self.amount * self.tax_rate)

    @property
    def total(self):
        """合計（税込）"""
        return self.amount + self.tax


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# クライアント管理 — 新規モデル（Phase 2）
# パートナー管理と対称的な業務フロー:
#   取引先登録 → 基本契約 → 受注 → 勤怠報告 → 請求 → 入金確認
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ClientContract(models.Model):
    """クライアント基本契約（パートナー側のOrderBasicInfoに対応）"""
    BILLING_TIMING_CHOICES = [
        ('FIRST_DAY', _('月初')),
        ('10TH_DAY', _('10日')),
        ('15TH_DAY', _('15日')),
        ('20TH_DAY', _('20日')),
        ('LAST_DAY', _('月末')),
    ]

    customer = models.ForeignKey(
        BillingCustomer, on_delete=models.CASCADE,
        verbose_name=_("取引先"), related_name='contracts'
    )
    project_name = models.CharField(_("案件名"), max_length=128)
    start_date = models.DateField(_("契約開始日"))
    end_date = models.DateField(_("契約終了日"))
    billing_timing = models.CharField(
        _("請求タイミング"), max_length=20,
        choices=BILLING_TIMING_CHOICES, default='LAST_DAY'
    )
    payment_terms = models.CharField(
        _("支払条件"), max_length=255,
        default="毎月末日締め翌月末日払い", blank=True
    )
    remarks = models.TextField(_("備考"), blank=True)
    is_active = models.BooleanField(_("有効"), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("クライアント基本契約")
        verbose_name_plural = _("クライアント基本契約")
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.customer.name} - {self.project_name}"


class ReceivedOrder(models.Model):
    """受注（クライアントからの注文書）— パートナー側のOrderに対応"""
    STATUS_CHOICES = [
        ('REGISTERED', _('登録済')),
        ('ACTIVE', _('進行中')),
        ('COMPLETED', _('完了')),
        ('CANCELLED', _('取消')),
    ]

    contract = models.ForeignKey(
        ClientContract, on_delete=models.SET_NULL,
        verbose_name=_("基本契約"), null=True, blank=True,
        related_name='received_orders'
    )
    customer = models.ForeignKey(
        BillingCustomer, on_delete=models.PROTECT,
        verbose_name=_("取引先"), related_name='received_orders'
    )
    order_number = models.CharField(
        _("注文番号"), max_length=50, blank=True,
        help_text=_("クライアントが発番した注文番号")
    )
    target_month = models.DateField(
        _("対象月"), help_text=_("YYYY-MM-01形式")
    )
    work_start = models.DateField(_("作業開始日"))
    work_end = models.DateField(_("作業終了日"))
    project_name = models.CharField(_("業務名称"), max_length=255, blank=True)

    # 注文書原本
    order_file = models.FileField(
        _("注文書PDF"), upload_to='received_orders/',
        blank=True, null=True,
        help_text=_("クライアントから受領した注文書PDF")
    )
    parsed_data = models.JSONField(
        _("パース結果"), null=True, blank=True,
        help_text=_("PDFから自動抽出されたデータ")
    )

    status = models.CharField(
        _("ステータス"), max_length=20,
        choices=STATUS_CHOICES, default='REGISTERED'
    )
    is_recurring = models.BooleanField(
        _("継続注文"), default=False,
        help_text=_("毎月自動でロールフォワードする注文")
    )
    parent_order = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        verbose_name=_("元注文"), null=True, blank=True,
        related_name='child_orders',
        help_text=_("ロールフォワード元の注文")
    )
    order_date = models.DateField(_("注文日"), default=datetime.date.today)
    remarks = models.TextField(_("備考"), blank=True)

    # 作業報告書メール送信先
    report_to_email = models.EmailField(
        _("報告書送信先(TO)"), blank=True,
        help_text=_("作業報告書の送信先メールアドレス")
    )
    report_cc_emails = models.TextField(
        _("報告書CC"), blank=True,
        help_text=_("カンマ区切りで複数指定可（例: a@example.com, b@example.com）")
    )
    # 請求書メール送信先
    invoice_to_email = models.EmailField(
        _("請求書送信先(TO)"), blank=True,
        help_text=_("請求書の送信先メールアドレス")
    )
    invoice_cc_emails = models.TextField(
        _("請求書CC"), blank=True,
        help_text=_("カンマ区切りで複数指定可")
    )

    # パートナー側の発注との紐付け
    partner_order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL,
        verbose_name=_("パートナー発注"), null=True, blank=True,
        related_name='received_orders',
        help_text=_("対応するパートナーへの発注")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("受注")
        verbose_name_plural = _("受注")
        ordering = ['-target_month', '-created_at']

    def __str__(self):
        return f"{self.order_number or '---'} - {self.customer.name} ({self.target_month.strftime('%Y/%m')})"


class ReceivedOrderItem(models.Model):
    """受注明細 — パートナー側のOrderItemに対応"""
    order = models.ForeignKey(
        ReceivedOrder, on_delete=models.CASCADE,
        related_name='items', verbose_name=_("受注")
    )
    product = models.ForeignKey(
        BillingProduct, on_delete=models.SET_NULL,
        verbose_name=_("商品"), null=True, blank=True
    )
    person_name = models.CharField(_("要員名"), max_length=64, blank=True)
    unit_price = models.IntegerField(_("単価"), default=0)
    man_month = models.DecimalField(
        _("人月"), max_digits=4, decimal_places=2, default=1.00
    )
    # SES精算条件
    SETTLEMENT_CHOICES = [
        ('MIDDLE', _('中間割')),
        ('RANGE', _('上下限割')),
    ]
    settlement_type = models.CharField(
        _("精算条件"), max_length=10, choices=SETTLEMENT_CHOICES,
        default='RANGE'
    )
    settlement_middle_hours = models.DecimalField(
        _("中間基準時間"), max_digits=5, decimal_places=2, default=170.00,
        help_text=_("中間割の場合の基準時間")
    )
    time_lower_limit = models.DecimalField(
        _("基準時間_下限"), max_digits=5, decimal_places=2, default=140.00
    )
    time_upper_limit = models.DecimalField(
        _("基準時間_上限"), max_digits=5, decimal_places=2, default=180.00
    )
    shortage_rate = models.IntegerField(_("控除単価"), default=0)
    excess_rate = models.IntegerField(_("超過単価"), default=0)

    class Meta:
        verbose_name = _("受注明細")
        verbose_name_plural = _("受注明細")

    def __str__(self):
        name = self.person_name or (self.product.name if self.product else _('明細'))
        return f"{self.order.order_number} - {name}"


# StaffTimesheet は MonthlyTimesheet に統合済み（2026-04-30）


class PaymentRecord(models.Model):
    """入金記録 — パートナー側には対応物なし（新規概念）"""
    METHOD_CHOICES = [
        ('TRANSFER', _('銀行振込')),
        ('CHECK', _('小切手')),
        ('OTHER', _('その他')),
    ]

    invoice = models.ForeignKey(
        BillingInvoice, on_delete=models.CASCADE,
        verbose_name=_("請求書"), related_name='payments'
    )
    payment_date = models.DateField(_("入金日"))
    amount = models.IntegerField(_("入金額"))
    method = models.CharField(
        _("入金方法"), max_length=10,
        choices=METHOD_CHOICES, default='TRANSFER'
    )
    reference = models.CharField(
        _("振込名義/備考"), max_length=255, blank=True
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        verbose_name=_("確認者"), null=True, blank=True
    )
    confirmed_at = models.DateTimeField(_("確認日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("入金記録")
        verbose_name_plural = _("入金記録")
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.payment_date} - ¥{self.amount:,} ({self.get_method_display()})"


class MonthlyTimesheet(models.Model):
    """月次稼働報告 — 自社社員・パートナー共通の統合モデル

    旧 StaffTimesheet（自社社員勤怠）と旧 WorkReport（パートナー稼働報告）を統合。
    report_type で区別する。
    """
    REPORT_TYPE_CHOICES = [
        ('INTERNAL', _('自社社員')),
        ('PARTNER', _('パートナー')),
    ]
    STATUS_CHOICES = [
        ('DRAFT', _('下書き')),
        ('UPLOADED', _('受領済')),
        ('PARSED', _('解析済')),
        ('ALERT', _('要確認')),
        ('SUBMITTED', _('提出済')),
        ('APPROVED', _('承認済')),
        ('SENT', _('送付済')),
        ('ERROR', _('エラー')),
    ]
    WORKER_TYPE_CHOICES = [
        ('INTERNAL', _('自社社員')),
        ('PARTNER', _('パートナー')),
    ]

    # === 識別 ===
    report_type = models.CharField(
        _('報告種別'), max_length=10,
        choices=REPORT_TYPE_CHOICES, default='INTERNAL'
    )
    worker_name = models.CharField(_('作業者名'), max_length=128)
    worker_type = models.CharField(
        _('要員種別'), max_length=10,
        choices=WORKER_TYPE_CHOICES, default='INTERNAL'
    )
    employee_id = models.CharField(
        _('社員番号'), max_length=20, blank=True,
        help_text=_('PayrollSystemの社員番号。自社社員の場合に設定')
    )
    target_month = models.DateField(
        _('対象月'), help_text='常にYYYY-MM-01形式'
    )
    status = models.CharField(
        _('ステータス'), max_length=10,
        choices=STATUS_CHOICES, default='DRAFT'
    )

    # === リレーション ===
    order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL,
        verbose_name=_('パートナー発注'), null=True, blank=True,
        related_name='monthly_timesheets'
    )
    received_order = models.ForeignKey(
        ReceivedOrder, on_delete=models.SET_NULL,
        verbose_name=_('クライアント受注'), null=True, blank=True,
        related_name='monthly_timesheets'
    )
    received_order_item = models.ForeignKey(
        ReceivedOrderItem, on_delete=models.SET_NULL,
        verbose_name=_('受注明細'), null=True, blank=True,
        related_name='monthly_timesheets'
    )

    # === 稼働データ ===
    total_hours = models.DecimalField(
        _('合計稼働時間'), max_digits=6, decimal_places=2, default=0.00
    )
    work_days = models.IntegerField(_('稼働日数'), default=0)
    overtime_hours = models.DecimalField(
        _('残業時間'), max_digits=6, decimal_places=2, default=0.00
    )
    night_hours = models.DecimalField(
        _('深夜残業時間'), max_digits=6, decimal_places=2, default=0.00
    )
    holiday_hours = models.DecimalField(
        _('休日出勤時間'), max_digits=6, decimal_places=2, default=0.00
    )
    daily_data = models.JSONField(
        _('日別データ'), null=True, blank=True
    )

    # === ファイル ===
    excel_file = models.FileField(
        _('Excelファイル'), upload_to='timesheets/excel/',
        blank=True, null=True
    )
    pdf_file = models.FileField(
        _('PDFファイル'), upload_to='timesheets/pdf/',
        blank=True, null=True
    )
    original_filename = models.CharField(
        _('元ファイル名'), max_length=512, blank=True
    )
    drive_file_id = models.CharField(
        _('DriveファイルID'), max_length=200, blank=True
    )

    # === パートナー報告固有 ===
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        verbose_name=_('アップロード者'), null=True, blank=True,
        related_name='uploaded_timesheets'
    )
    uploaded_at = models.DateTimeField(
        _('アップロード日時'), null=True, blank=True
    )
    alerts_json = models.JSONField(
        _('警告データ'), null=True, blank=True
    )
    error_message = models.TextField(_('エラーメッセージ'), blank=True)
    sent_to_client_at = models.DateTimeField(
        _('クライアント送付日時'), null=True, blank=True
    )
    client_shared_url = models.URLField(
        _('共有URL'), max_length=500, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('月次稼働報告')
        verbose_name_plural = _('月次稼働報告')
        ordering = ['-target_month', 'worker_name']

    def __str__(self):
        type_label = '社員' if self.report_type == 'INTERNAL' else 'パートナー'
        month = self.target_month.strftime('%Y/%m') if self.target_month else '不明'
        return f"{self.worker_name} [{type_label}] - {month}"

    def get_status_display_custom(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def has_alerts(self):
        return bool(self.alerts_json)

    def save(self, *args, **kwargs):
        # target_month を月初に正規化
        if self.target_month:
            self.target_month = self.target_month.replace(day=1)
        # 自社社員の場合、employee_id を自動設定
        if self.worker_type == 'INTERNAL' and not self.employee_id:
            self._auto_fill_employee_id()
        super().save(*args, **kwargs)

    def _auto_fill_employee_id(self):
        import logging
        from billing.domain.synced_employee import SyncedEmployee
        logger = logging.getLogger(__name__)
        def normalize(name):
            return name.replace(' ', '').replace('\u3000', '').strip()
        normalized = normalize(self.worker_name)
        matches = [
            emp for emp in SyncedEmployee.objects.filter(is_active=True)
            if normalize(emp.name) == normalized
        ]
        if len(matches) == 1:
            self.employee_id = matches[0].employee_id
            logger.info(f'employee_id自動設定: {self.worker_name} → {self.employee_id}')
