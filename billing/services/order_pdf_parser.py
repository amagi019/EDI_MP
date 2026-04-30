"""
注文書PDFパーサー

クライアントから受領した注文書PDFをpdfminerでテキスト抽出し、
正規表現で必要項目を自動パースする。

対応形式:
  - イービジネス形式（注文番号: EB...）
  - NTP形式（発注書番号: PO-...）
  - 汎用形式（正規表現でベストエフォートパース）
"""
import re
import io
from decimal import Decimal
from pdfminer.high_level import extract_text


def parse_order_pdf(file_obj):
    """
    注文書PDFからデータを自動抽出する。

    Args:
        file_obj: アップロードされたファイルオブジェクト（InMemoryUploadedFile等）

    Returns:
        dict: パース結果。パース失敗した項目はNone。
        {
            'order_number': str or None,
            'order_date': str or None,  # YYYY-MM-DD
            'project_name': str or None,
            'work_start': str or None,  # YYYY-MM-DD
            'work_end': str or None,    # YYYY-MM-DD
            'unit_price': int or None,
            'time_lower': float or None,
            'time_upper': float or None,
            'excess_rate': int or None,
            'shortage_rate': int or None,
            'person_name': str or None,
            'payment_terms': str or None,
            'raw_text': str,    # 抽出テキスト全文（デバッグ用）
            'format': str,      # 検出フォーマット
        }
    """
    # PDFテキスト抽出
    file_obj.seek(0)
    text = extract_text(io.BytesIO(file_obj.read()))

    result = {
        'order_number': None,
        'order_date': None,
        'project_name': None,
        'work_start': None,
        'work_end': None,
        'unit_price': None,
        'time_lower': None,
        'time_upper': None,
        'excess_rate': None,
        'shortage_rate': None,
        'person_name': None,
        'payment_terms': None,
        'raw_text': text,
        'format': 'unknown',
    }

    # フォーマット検出・パース
    if _is_ebusiness_format(text):
        result['format'] = 'ebusiness'
        _parse_ebusiness(text, result)
    elif _is_ntp_format(text):
        result['format'] = 'ntp'
        _parse_ntp(text, result)
    else:
        result['format'] = 'generic'
        _parse_generic(text, result)

    return result


def _is_ebusiness_format(text):
    """イービジネス形式かを判定"""
    return 'イー・ビジネス' in text or re.search(r'EB\d{6}[A-Z]\d+', text)


def _is_ntp_format(text):
    """NTP形式かを判定"""
    return 'NTP' in text or 'PO-' in text


def _parse_ebusiness(text, result):
    """イービジネス形式をパース"""
    # 注文番号: EB260228I00010
    m = re.search(r'(?:注[⽂文]番号[：:]?\s*)([A-Z]{2}\d{6}[A-Z]\d+)', text)
    if m:
        result['order_number'] = m.group(1)

    # 注文日: 2026年2月28日
    m = re.search(r'(\d{4})年(\d{1,2})[⽉月](\d{1,2})日', text)
    if m:
        result['order_date'] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 業務名称
    # pdfminerはテーブルを「業務名称\n作業期間\n<業務名>\n<日付>」の順で抽出する
    # まず「作業期間」ラベルの後、日付パターンの前にある行を取得
    m = re.search(r'業務名称\s*\n+\s*作業期間\s*\n+\s*(.+?)\s*\n', text)
    if m:
        name = m.group(1).strip()
        # 日付パターンでないことを確認
        if not re.match(r'\d{4}年', name):
            result['project_name'] = re.sub(r'\s+', ' ', name)[:255]
    # フォールバック: 従来のパターン
    if not result['project_name']:
        m = re.search(r'(?:業務名称|件名)\s*\n?\s*(.+?)(?:\n|作業期間)', text, re.DOTALL)
        if m:
            name = m.group(1).strip()
            if name and name != '作業期間':
                result['project_name'] = re.sub(r'\s+', ' ', name)[:255]

    # 作業期間: 2026年3月1日 〜 2026年3月31日
    m = re.search(
        r'(\d{4})年(\d{1,2})[⽉月](\d{1,2})日\s*[〜～~]\s*(\d{4})年(\d{1,2})[⽉月](\d{1,2})日',
        text
    )
    if m:
        result['work_start'] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        result['work_end'] = f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"

    # 月額基本料金: ￥800,000
    m = re.search(r'[⽉月]額基本料[⾦金][：:]?\s*[￥¥]?([\d,]+)', text)
    if m:
        result['unit_price'] = int(m.group(1).replace(',', ''))

    # 基準時間: 140.0h〜200.0h
    m = re.search(r'基準時間[：:]?\s*([\d.]+)\s*h?\s*[〜～~]\s*([\d.]+)\s*h?', text)
    if m:
        result['time_lower'] = float(m.group(1))
        result['time_upper'] = float(m.group(2))

    # 超過単価: ￥4,000/h
    m = re.search(r'超過単価[：:]?\s*[￥¥]?([\d,]+)', text)
    if m:
        result['excess_rate'] = int(m.group(1).replace(',', ''))

    # 不足単価 / 控除単価: ￥5,710/h
    m = re.search(r'(?:不[⾜足]|控除)単価[：:]?\s*[￥¥]?([\d,]+)', text)
    if m:
        result['shortage_rate'] = int(m.group(1).replace(',', ''))

    # 作業責任者（= 作業者名）
    m = re.search(r'作業責任者\s*\n+\s*(.+?)(?:\s*\n)', text)
    if m:
        name = m.group(1).strip()
        # 「連絡窓口」や日付パターンでないことを確認
        if name and not re.match(r'(連絡|委託|業務|￥|\d{4}年)', name):
            result['person_name'] = name

    # 支払条件
    m = re.search(r'(?:⽀払|支払)条件\s*\n?\s*(.+?)(?:\n|①)', text, re.DOTALL)
    if m:
        result['payment_terms'] = m.group(1).strip()[:255]


def _parse_ntp(text, result):
    """NTP形式をパース"""
    # 発注書番号: PO-0000000001
    m = re.search(r'(PO-\d+)', text)
    if m:
        result['order_number'] = m.group(1)

    # 日付: 2024-11-13
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if m:
        result['order_date'] = m.group(1)

    # 件名（案件名）
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if '件名' in line:
            # 次の非空行が件名
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j].strip():
                    result['project_name'] = lines[j].strip()[:255]
                    break
            break
    # フォールバック: 「向けPJ」等を探す
    if not result['project_name']:
        m = re.search(r'([^\n]*(?:PJ|プロジェクト|案件)[^\n]*)', text)
        if m:
            result['project_name'] = m.group(1).strip()[:255]

    # 月額単価: ￥750,000
    m = re.search(r'基本[⽉月]?額?単価[：:]?\s*[￥¥]?([\d,]+)', text)
    if m:
        result['unit_price'] = int(m.group(1).replace(',', ''))
    else:
        # フォールバック: 最初の大きな金額
        amounts = re.findall(r'([\d,]{5,})円', text)
        if amounts:
            result['unit_price'] = int(amounts[0].replace(',', ''))

    # 精算条件: 140h～200h
    m = re.search(r'精算条件[：:]?\s*([\d.]+)\s*h?\s*[〜～~ー]\s*([\d.]+)\s*h?', text)
    if m:
        result['time_lower'] = float(m.group(1))
        result['time_upper'] = float(m.group(2))

    # 超過控除単価: ￥4,410/h
    m = re.search(r'超過控除単価[：:]?\s*[￥¥]?([\d,]+)', text)
    if m:
        rate = int(m.group(1).replace(',', ''))
        result['excess_rate'] = rate
        result['shortage_rate'] = rate  # NTPは超過控除同額

    # 納品期限
    dates = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
    if len(dates) >= 2:
        result['work_end'] = dates[-1]  # 最後の日付を作業終了日に
        # work_startは対象月初に設定
        m2 = re.match(r'(\d{4}-\d{2})-\d{2}', dates[-1])
        if m2:
            result['work_start'] = f"{m2.group(1)}-01"


def _parse_generic(text, result):
    """汎用パーサー — ベストエフォートで項目を拾う"""
    # 注文番号パターン
    m = re.search(r'(?:注文番号|発注番号|PO番号)[：:\s]*([A-Za-z0-9\-]+)', text)
    if m:
        result['order_number'] = m.group(1)

    # 日付
    m = re.search(r'(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})', text)
    if m:
        result['order_date'] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 単価
    m = re.search(r'(?:単価|月額)[：:\s]*[￥¥]?([\d,]+)', text)
    if m:
        result['unit_price'] = int(m.group(1).replace(',', ''))

    # 精算幅
    m = re.search(r'([\d.]+)\s*h?\s*[〜～~ー]\s*([\d.]+)\s*h?', text)
    if m:
        result['time_lower'] = float(m.group(1))
        result['time_upper'] = float(m.group(2))

    # 超過単価
    m = re.search(r'超過[^\d]*[￥¥]?([\d,]+)', text)
    if m:
        result['excess_rate'] = int(m.group(1).replace(',', ''))

    # 控除単価
    m = re.search(r'(?:控除|不足)[^\d]*[￥¥]?([\d,]+)', text)
    if m:
        result['shortage_rate'] = int(m.group(1).replace(',', ''))
