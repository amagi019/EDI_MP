"""
消費税計算サービス
"""
from collections import defaultdict


def calculate_tax_summary(items):
    """
    明細リストから税率ごとの小計・消費税を集計する。
    インボイス制度に対応した税率ごとの内訳を返す。
    """
    summary = defaultdict(lambda: {'subtotal': 0, 'tax': 0, 'total': 0})

    for item in items:
        rate_label = item.tax_rate_display
        summary[rate_label]['subtotal'] += item.amount
        summary[rate_label]['tax'] += item.tax
        summary[rate_label]['total'] += item.total

    return dict(summary)
