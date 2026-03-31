from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
import io
import os
import datetime
import html
from django.conf import settings
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from core.domain.models import CompanyInfo
from orders.services.pdf_generator import (
    _setup_fonts as _setup_fonts_shared,
    _draw_header_section,
    _get_stamp_path,
)

def _setup_fonts(p):
    return _setup_fonts_shared(p)

def generate_invoice_pdf(invoice):
    """請求書PDFの生成 (8列構成・自社宛)"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _setup_fonts(p)

    # 1. 請求番号・日付 (右上)
    p.setFont(font_name, 10)
    p.drawRightString(width - 20*mm, height - 15*mm, f"請求番号：{invoice.invoice_no}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"発行日：{invoice.issue_date.strftime('%Y年%m月%d日')}")

    # 2. タイトル
    p.setFont(font_name, 20)
    p.drawCentredString(width / 2, height - 35*mm, "御 請 求 書")

    # 3-4. 宛先（自社）＋発行者（パートナー）の自動バランス配置
    company = CompanyInfo.objects.first()
    partner = invoice.order.partner
    next_y = _draw_header_section(
        p, width, height, font_name,
        addressee_label="",
        addressee_name=company.name if company else '',
        addressee_suffix="御中",
        issuer_label="",
        issuer_info={
            'name': partner.name,
            'postal_code': partner.postal_code,
            'address': partner.address,
            'tel': partner.tel,
            'fax': getattr(partner, 'fax', ''),
        },
        show_stamp=False,  # パートナー発行の請求書のため角印不要
    )

    # 5. メッセージ
    p.setFont(font_name, 10)
    p.drawString(20*mm, next_y, "下記の通り、ご請求申し上げます。")

    # 6. 合計金額 (枠付き)
    p.setFont(font_name, 14)
    amount_y = next_y - 15*mm
    p.rect(110*mm, amount_y - 4*mm, 80*mm, 12*mm)
    p.drawString(115*mm, amount_y, f"御請求額: ￥{invoice.total_amount:,}-")

    # 7. 請求テーブル (8列)
    header = ["番号", "名前 / 業務内容", "数量", "単位", "単価", "金額", "諸経費", "合計"]
    data = [header]
    
    left_style = ParagraphStyle(name='Normal', fontName=font_name, fontSize=8, leading=10)
    
    for i, item in enumerate(invoice.items.all(), 1):
        person_safe = html.escape(item.person_name)
        project_safe = html.escape(invoice.order.project.name)
        item_para = Paragraph(f"{person_safe}<br/>({project_safe})", left_style)

        data.append([
            str(i),
            item_para,
            "1.00",
            "月",
            f"￥{item.base_fee:,}",
            f"￥{item.base_fee:,}",
            "0",
            f"￥{item.base_fee:,}"
        ])
        if item.excess_amount > 0:
            data.append(["", f"超過精算: {item.work_time}h (上限:{item.time_upper_limit}h)", "", "", f"￥{item.excess_rate:,}", f"￥{item.excess_amount:,}", "", ""])
        elif item.shortage_amount > 0:
            data.append(["", f"控除精算: {item.work_time}h (下限:{item.time_lower_limit}h)", "", "", f"￥{item.shortage_rate:,}", f"▲￥{item.shortage_amount:,}", "", ""])

    # フッター
    data.append(["", "税込合計金額", "", "", "", "", "", f"￥{invoice.total_amount:,}"])

    col_widths = [12*mm, 60*mm, 15*mm, 12*mm, 25*mm, 25*mm, 15*mm, 25*mm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 8),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, -1), (6, -1)),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = amount_y - 15*mm - h  # 合計金額の下に動的配置
    table.drawOn(p, 10*mm, table_y)

    # 8. 振込先
    p.setFont(font_name, 10)
    p.drawString(20*mm, table_y - 15*mm, "【お振込先】")
    p.setFont(font_name, 9)
    bank_y = table_y - 20*mm
    bank_info = (f"{partner.bank_name} {partner.bank_branch} "
                 f"{partner.account_type} {partner.account_number} "
                 f"口座名義: {partner.account_name}")
    p.drawString(25*mm, bank_y, bank_info)

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

def generate_payment_notice_pdf(invoice):
    """支払い通知書PDFの生成 (8列構成)"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _setup_fonts(p)

    # 1. 右上の採番・日付
    p.setFont(font_name, 10)
    p.drawRightString(width - 20*mm, height - 15*mm, f"検収番号：{invoice.acceptance_no}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"作成日：{invoice.issue_date.strftime('%Y年%m月%d日')}")

    # 2. タイトル
    p.setFont(font_name, 18)
    ym_str = invoice.target_month.strftime('%Y年%m月度')
    p.drawCentredString(width / 2, height - 35*mm, f"{ym_str} 検収兼お支払通知書")

    # 3-4. 宛先（取引先）＋発行者（自社）の自動バランス配置（角印あり）
    customer = invoice.order.partner
    next_y = _draw_header_section(
        p, width, height, font_name,
        addressee_label="",
        addressee_name=customer.name,
        addressee_suffix="殿",
        issuer_label="",
        show_stamp=True,  # 支払通知書は自社発行のため角印あり
    )

    # 5. メッセージ
    p.setFont(font_name, 10)
    p.drawString(20*mm, next_y, "下記の通り、検収ならびにお支払い金額を通知いたします。")

    # 6. 合計金額 (枠付き)
    p.setFont(font_name, 14)
    amount_y = next_y - 15*mm
    p.rect(110*mm, amount_y - 4*mm, 80*mm, 12*mm)
    p.drawString(115*mm, amount_y, f"合計金額: ￥{invoice.total_amount:,}-")

    # 7. 検収テーブル (8列)
    header = ["番号", "名前 / 業務内容", "数量", "単位", "単価", "金額", "諸経費", "合計"]
    data = [header]
    
    left_style = ParagraphStyle(name='Normal', fontName=font_name, fontSize=8, leading=10)
    
    for i, item in enumerate(invoice.items.all(), 1):
        person_safe = html.escape(item.person_name)
        project_safe = html.escape(invoice.order.project.name)
        item_para = Paragraph(f"{person_safe}<br/>({project_safe})", left_style)

        data.append([
            str(i),
            item_para,
            "1.00",
            "月",
            f"￥{item.base_fee:,}",
            f"￥{item.base_fee:,}",
            "0",
            f"￥{item.base_fee:,}"
        ])
        if item.excess_amount > 0:
            data.append(["", f"超過精算: {item.work_time}h (上限:{item.time_upper_limit}h)", "", "", f"￥{item.excess_rate:,}", f"￥{item.excess_amount:,}", "", ""])
        elif item.shortage_amount > 0:
            data.append(["", f"控除精算: {item.work_time}h (下限:{item.time_lower_limit}h)", "", "", f"￥{item.shortage_rate:,}", f"▲￥{item.shortage_amount:,}", "", ""])

    # フッター
    data.append(["", "税込合計金額", "", "", "", "", "", f"￥{invoice.total_amount:,}"])

    col_widths = [12*mm, 60*mm, 15*mm, 12*mm, 25*mm, 25*mm, 15*mm, 25*mm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 8),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, -1), (6, -1)),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = amount_y - 15*mm - h  # 合計金額の下に動的配置
    table.drawOn(p, 10*mm, table_y)

    # 8. 支払条件等
    p.setFont(font_name, 10)
    p.drawString(20*mm, table_y - 15*mm, "【支払方法】 銀行振込")
    p.drawString(20*mm, table_y - 20*mm, "【支払期日】 ご登録支払サイト日")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
