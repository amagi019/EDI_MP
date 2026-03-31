from decimal import Decimal
import logging

from core.domain.models import CompanyInfo

logger = logging.getLogger(__name__)

# デフォルト消費税率（CompanyInfoが未設定の場合のフォールバック）
DEFAULT_TAX_RATE = Decimal('0.10')


def get_tax_rate():
    """管理画面で設定された消費税率を取得する（0〜1の小数で返す）。"""
    company = CompanyInfo.objects.first()
    if company and company.tax_rate is not None:
        return company.tax_rate / Decimal('100')
    return DEFAULT_TAX_RATE


class BillingCalculator:
    """SES精算計算ロジック（明細対応版）"""

    @staticmethod
    def calculate_invoice(invoice):
        """
        Invoiceに関連付くすべてのInvoiceItemを計算し、Invoice本体の合計金額を更新する。
        """
        subtotal = 0

        for item in invoice.items.all():
            excess_amount = 0
            shortage_amount = 0

            if item.work_time > item.time_upper_limit and item.time_upper_limit > 0:
                over_time = item.work_time - item.time_upper_limit
                amount = Decimal(item.excess_rate) * over_time
                excess_amount = int(amount)
            elif item.work_time < item.time_lower_limit and item.time_lower_limit > 0:
                short_time = item.time_lower_limit - item.work_time
                amount = Decimal(item.shortage_rate) * short_time
                shortage_amount = int(amount)

            item_subtotal = item.base_fee + excess_amount - shortage_amount

            item.excess_amount = excess_amount
            item.shortage_amount = shortage_amount
            item.item_subtotal = item_subtotal
            item.save()

            subtotal += item_subtotal

        # 管理画面で設定された消費税率を使用
        tax_rate = get_tax_rate()
        tax = int(subtotal * tax_rate)
        total = subtotal + tax

        from invoices.models import Invoice
        Invoice.objects.filter(pk=invoice.pk).update(
            subtotal_amount=subtotal,
            tax_amount=tax,
            total_amount=total
        )

        return invoice
