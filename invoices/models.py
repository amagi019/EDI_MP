from django.db import models
from django.utils.translation import gettext_lazy as _
from orders.models import Order
import datetime

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', _('下書き')),
        ('ISSUED', _('発行済')),
        ('SENT', _('送付済')),
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
    payment_deadline = models.DateField(_("支払締切日"), null=True, blank=True)
    
    department = models.CharField(_("部署名"), max_length=128, blank=True, help_text="請求書に表示する部署名")
    
    # サマリ金額（InvoiceItemの合計）
    subtotal_amount = models.IntegerField(_("税抜合計"), default=0)
    tax_amount = models.IntegerField(_("消費税"), default=0)
    total_amount = models.IntegerField(_("税込合計"), default=0)
    
    status = models.CharField(_("ステータス"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.invoice_no} ({self.order.project.name})"

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
