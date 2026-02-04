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

    order = models.OneToOneField(Order, on_delete=models.CASCADE, verbose_name=_("注文"), related_name='invoice')
    
    # 請求・支払通知書番号
    invoice_no = models.CharField(_("請求番号"), max_length=20, unique=True, help_text="YYYYMM+3桁連番 (例: 2512006)")
    acceptance_no = models.CharField(_("検収番号"), max_length=22, blank=True, help_text="MP+請求番号")
    
    target_month = models.DateField(_("対象年月"), help_text="請求対象月")
    issue_date = models.DateField(_("作成日"), default=datetime.date.today)
    acceptance_date = models.DateField(_("検収日"), null=True, blank=True)
    payment_deadline = models.DateField(_("支払締切日"), null=True, blank=True)
    
    # SES実績値
    work_time = models.DecimalField(_("実稼働時間"), max_digits=6, decimal_places=2, help_text="単位: 時間")
    
    # 計算結果
    excess_amount = models.IntegerField(_("超過金額"), default=0)
    deduction_amount = models.IntegerField(_("控除金額"), default=0) # 割引額
    
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
            import random
            import string
            # 英数字、大文字、小文字（混在）10桁を生成
            characters = string.ascii_letters + string.digits
            while True:
                random_no = ''.join(random.choice(characters) for _ in range(10))
                # 重複チェック
                if not Invoice.objects.filter(invoice_no=random_no).exists():
                    self.invoice_no = random_no
                    break
        
        if self.invoice_no:
            self.acceptance_no = f"MP{self.invoice_no}"
            
        super().save(*args, **kwargs)
