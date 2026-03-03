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
    address = models.CharField(_("住所"), max_length=255, blank=True)

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
