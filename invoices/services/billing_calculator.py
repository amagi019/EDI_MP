from decimal import Decimal
from math import floor

class BillingCalculator:
    """SES精算計算ロジック"""

    @staticmethod
    def calculate(invoice):
        """
        Invoiceオブジェクトを受け取り、work_timeとOrderの条件に基づいて
        金額フィールド（excess, deduction, total等）を更新する。
        """
        order = invoice.order
        work_time = invoice.work_time
        
        # 契約条件の取り出し（Decimal型で計算）
        lower_limit = order.time_lower_limit
        upper_limit = order.time_upper_limit
        base_fee = order.base_fee
        excess_fee = order.excess_fee
        shortage_fee = order.shortage_fee
        
        excess_amount = 0
        deduction_amount = 0
        
        # 精算計算
        if work_time > upper_limit and upper_limit > 0:
            # 超過
            over_time = work_time - upper_limit
            # 一般的には切り捨て等の端数処理があるかもしれないが、一旦単純計算
            # 要件定義に詳細がないため、標準的な計算とする
            # 超過単価 * 超過時間
            # Decimal * Int なので注意。Pythonでは計算可能だが、結果をIntにする必要があるか？
            # 「超過金額：¥0」等の表記から整数を期待
            
            # PythonのDecimal計算
            amount = Decimal(excess_fee) * over_time
            excess_amount = int(amount) # 切り捨て
            
        elif work_time < lower_limit and lower_limit > 0:
            # 不足（控除）
            shortage_time = lower_limit - work_time
            amount = Decimal(shortage_fee) * shortage_time
            deduction_amount = int(amount) # 切り捨て
        
        # 合計計算
        # 基本給 + 超過 - 控除
        subtotal = base_fee + excess_amount - deduction_amount
        
        # 消費税（10%固定とする、軽減税率等は考慮せず）
        tax = int(subtotal * 0.1)
        total = subtotal + tax
        
        # 結果をInvoiceにセット
        invoice.excess_amount = excess_amount
        invoice.deduction_amount = deduction_amount
        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax
        invoice.total_amount = total
        
        return invoice
