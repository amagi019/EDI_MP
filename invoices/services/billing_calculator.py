from decimal import Decimal
from math import floor

class BillingCalculator:
    """SES精算計算ロジック（明細対応版）"""

    @staticmethod
    def calculate_invoice(invoice):
        """
        Invoiceに関連付くすべてのInvoiceItemを計算し、Invoice本体の合計金額を更新する。
        """
        subtotal = 0
        
        # 各明細の計算
        for item in invoice.items.all():
            excess_amount = 0
            shortage_amount = 0
            
            # 精算幅のチェック
            if item.work_time > item.time_upper_limit and item.time_upper_limit > 0:
                # 超過
                over_time = item.work_time - item.time_upper_limit
                amount = Decimal(item.excess_rate) * over_time
                excess_amount = int(amount)
            elif item.work_time < item.time_lower_limit and item.time_lower_limit > 0:
                # 不足
                short_time = item.time_lower_limit - item.work_time
                amount = Decimal(item.shortage_rate) * short_time
                shortage_amount = int(amount)
            
            # 明細合計 = (単価 * 1.0) + 超過 - 控除
            # ※ 工数は現在の InvoiceItem には記録していない（OrderのOrderItemにある）が、
            # 基本的には工数は1.0として、単価（base_fee）を調整済みとして扱うか、
            # 将来的には InvoiceItem にも effort を持たせる検討が必要。
            # 現状はシンプルに base_fee + excess - shortage とする。
            item_subtotal = item.base_fee + excess_amount - shortage_amount
            
            # 明細を更新
            item.excess_amount = excess_amount
            item.shortage_amount = shortage_amount
            item.item_subtotal = item_subtotal
            item.save()
            
            subtotal += item_subtotal
            
        # Invoice（親）の合計値を計算
        tax = int(subtotal * 0.1)
        total = subtotal + tax
        
        # データベースを直接更新（無限ループ回避のため）
        from invoices.models import Invoice
        Invoice.objects.filter(pk=invoice.pk).update(
            subtotal_amount=subtotal,
            tax_amount=tax,
            total_amount=total
        )
        
        return invoice
