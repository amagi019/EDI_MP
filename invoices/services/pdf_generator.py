from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
import io
import datetime
from django.conf import settings
from core.domain.models import CompanyInfo

def _setup_fonts(p):
    # フォント登録（日本語対応）
    font_name = "HeiseiMin-W3"
    try:
        pdfmetrics.getFont(font_name)
    except:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    return font_name

def _draw_company_info(p, x, y, font_name, side="自社"):
    p.setFont(font_name, 10)
    company = CompanyInfo.objects.first()
    if not company:
        name = "有限会社 マックプランニング"
        post = "〒116-0012"
        addr = "東京都荒川区東尾久8-9-14"
        tel = "090-3043-0477"
        fax = ""
        rep = "代表取締役 吉川 裕"
        reg_no = "TXXXXXXXXXXXXX"
    else:
        name = company.name
        post = f"〒{company.postal_code}"
        addr = company.address
        tel = company.tel
        fax = company.fax
        rep = f"{company.representative_title} {company.representative_name}"
        reg_no = company.registration_no

    p.drawString(x, y, name)
    p.setFont(font_name, 9)
    p.drawString(x, y - 5*mm, post)
    p.drawString(x, y - 9*mm, addr)
    p.drawString(x, y - 13*mm, f"TEL:{tel}  FAX:{fax}")
    if reg_no:
        p.drawString(x, y - 17*mm, f"登録番号: {reg_no}")
    
    return name, rep

def generate_invoice_pdf(invoice):
    """請求書PDFの生成 (11列構成)"""
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

    # 3. 宛先 (取引先)
    customer = invoice.order.customer
    p.setFont(font_name, 12)
    p.drawString(20*mm, height - 55*mm, f"{customer.name}  御中")
    if invoice.department:
        p.setFont(font_name, 10)
        p.drawString(20*mm, height - 61*mm, f"{invoice.department}")

    # 4. 発行人 (自社)
    _draw_company_info(p, 120*mm, height - 55*mm, font_name)

    # 5. 印影表示
    company = CompanyInfo.objects.first()
    if company and company.stamp_image:
        try:
            p.drawImage(company.stamp_image.path, 165*mm, height - 80*mm, width=22*mm, height=22*mm, mask='auto', preserveAspectRatio=True)
        except:
            pass

    # 6. ご請求額サマリ
    p.setFont(font_name, 12)
    p.drawString(20*mm, height - 90*mm, "御請求額")
    p.setFont(font_name, 16)
    p.drawString(45*mm, height - 90*mm, f"￥ {invoice.total_amount:,}-")
    p.line(40*mm, height - 92*mm, 100*mm, height - 92*mm)

    # 7. 請求テーブル (11列)
    # 番号, 項目, 単価, 作業H, 率, Min/MaxH, 減, 増, その他, 金額, 備考
    header = ["番号", "項目", "単価", "作業H", "率", "Min/MaxH", "減", "増", "他", "金額", "備考"]
    data = [header]
    
    for i, item in enumerate(invoice.items.all(), 1):
        range_text = f"{int(item.time_lower_limit)}/{int(item.time_upper_limit)}"
        row = [
            str(i),
            f"{item.person_name}\n({invoice.order.project.name})",
            f"{item.base_fee:,}",
            f"{item.work_time}",
            "1.0",
            range_text,
            f"{item.shortage_amount:,}" if item.shortage_amount > 0 else "0",
            f"{item.excess_amount:,}" if item.excess_amount > 0 else "0",
            "0",
            f"{item.item_subtotal:,}",
            item.remarks
        ]
        data.append(row)

    # フッター行 (小計等)
    data.append(["", "税抜小計", "", "", "", "", "", "", "", f"{invoice.subtotal_amount:,}", ""])
    data.append(["", "消費税(10%)", "", "", "", "", "", "", "", f"{invoice.tax_amount:,}", ""])
    data.append(["", "税込合計金額", "", "", "", "", "", "", "", f"{invoice.total_amount:,}", ""])

    col_widths = [10*mm, 35*mm, 18*mm, 14*mm, 10*mm, 18*mm, 14*mm, 14*mm, 8*mm, 20*mm, 15*mm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 7),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.black), # 明細部分のグリッド
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, -3), (8, -3)), # 小計ラベル
        ('SPAN', (1, -2), (8, -2)), # 消費税ラベル
        ('SPAN', (1, -1), (8, -1)), # 合計ラベル
        ('LINEBELOW', (1, -3), (-1, -1), 0.5, colors.black),
        ('LINEAFTER', (0, -3), (0, -1), 0.5, colors.black),
        ('LINEAFTER', (8, -3), (8, -1), 0.5, colors.black),
        ('LINEAFTER', (9, -3), (9, -1), 0.5, colors.black),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = height - 105*mm - h
    table.drawOn(p, 15*mm, table_y)

    # 8. 振込先
    p.setFont(font_name, 10)
    p.drawString(20*mm, table_y - 15*mm, "【お振込先】")
    p.setFont(font_name, 9)
    bank_y = table_y - 20*mm
    bank_info = (f"{customer.bank_name} {customer.bank_branch} "
                 f"{customer.account_type} {customer.account_number} "
                 f"口座名義: {customer.account_name}")
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

    # 3. 宛先 (自社 -> 取引先殿)
    customer = invoice.order.customer
    p.setFont(font_name, 12)
    p.drawString(20*mm, height - 55*mm, f"{customer.name}  殿")

    # 4. 発行人 (取引先 -> 自社名義)
    _draw_company_info(p, 120*mm, height - 55*mm, font_name)

    # 5. メッセージ
    p.setFont(font_name, 10)
    p.drawString(20*mm, height - 85*mm, "下記の通り、検収ならびにお支払い金額を通知いたします。")

    # 6. 合計金額 (枠付き)
    p.setFont(font_name, 14)
    p.rect(110*mm, height - 105*mm, 80*mm, 12*mm)
    p.drawString(115*mm, height - 102*mm, f"合計金額: ￥{invoice.total_amount:,}-")

    # 7. 検収テーブル (8列)
    # 番号, 名前, 数量, 単位, 単価, 金額, 諸経費, 合計
    header = ["番号", "名前 / 業務内容", "数量", "単位", "単価", "金額", "諸経費", "合計"]
    data = [header]
    
    for i, item in enumerate(invoice.items.all(), 1):
        # 明細行
        data.append([
            str(i),
            f"{item.person_name}\n({invoice.order.project.name})",
            "1.00",
            "月",
            f"￥{item.base_fee:,}",
            f"￥{item.base_fee:,}",
            "0",
            f"￥{item.base_fee:,}"
        ])
        # 調整金詳細行 (オプションで表示)
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
    table_y = height - 115*mm - h
    table.drawOn(p, 10*mm, table_y)

    # 8. 支払条件等
    p.setFont(font_name, 10)
    p.drawString(20*mm, table_y - 15*mm, "【支払方法】 銀行振込")
    p.drawString(20*mm, table_y - 20*mm, "【支払期日】 ご登録支払サイト日")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
