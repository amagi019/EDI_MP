from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
import io
import os
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

def generate_invoice_pdf(invoice):
    """
    請求データから支払通知書・請求書PDFを生成し、バッファとして返す
    """
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _setup_fonts(p)

    # 1. 請求番号・日付 (右上)
    p.setFont(font_name, 10)
    p.drawRightString(width - 20*mm, height - 15*mm, f"請求番号：{invoice.invoice_no}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"{invoice.issue_date.strftime('%Y年%m月%d日')}")

    # 2. タイトル
    p.setFont(font_name, 18)
    p.drawCentredString(width / 2, height - 35*mm, "支 付 通 知 書 ・ 請 求 書")
    
    p.setFont(font_name, 12)
    ym_str = invoice.target_month.strftime('%Y年%m月度')
    p.drawCentredString(width / 2, height - 42*mm, f"{ym_str} 検収兼お支払い通知書")

    # 3. 宛先 (自社)
    company = CompanyInfo.objects.first()
    p.setFont(font_name, 12)
    company_name = company.name if company else "有限会社 マックプランニング"
    p.drawString(20*mm, height - 60*mm, f"{company_name}  御中")

    # 4. 発行人・請求元 (取引先)
    customer = invoice.order.customer
    p.setFont(font_name, 10)
    x_right = 110*mm
    y_right = height - 60*mm
    
    name = customer.name
    post = f"〒{customer.postal_code}"
    addr = customer.address
    tel = customer.tel
    
    # 取引先の銀行口座情報
    bank_info = f"{customer.bank_name} {customer.bank_branch} {customer.account_type} {customer.account_number}\n口座名義: {customer.account_name}"

    p.drawString(x_right, y_right, name)
    p.setFont(font_name, 9)
    p.drawString(x_right, y_right - 5*mm, post)
    p.drawString(x_right, y_right - 10*mm, addr)
    p.drawString(x_right, y_right - 14*mm, f"TEL:{tel}")
    
    # 登録番号は現在は自社のものを表示すべきか、取引先のものを表示すべきか？
    # 取引先が登録番号を持っていない場合は、自社の情報を宛先に表示するのみとする。
    # ユーザー指示では「請求元には、取引先の名前や住所、連絡先を記載」となっているため、登録番号は一旦外すか検討。
    # ここでは取引先情報の表示に徹する。

    # 5. 印影表示 (自社宛の請求書のため非表示)
    # if company and company.stamp_image: ...

    # 6. 金額サマリ
    p.setFont(font_name, 11)
    p.drawString(20*mm, height - 85*mm, "下記の通り、検収ならびにお支払い金額を通知いたします。")
    
    p.setFont(font_name, 14)
    p.rect(20*mm, height - 105*mm, 80*mm, 12*mm)
    p.drawString(22*mm, height - 102*mm, f"合計金額: ￥{invoice.total_amount:,}-")
    p.setFont(font_name, 9)
    p.drawString(25*mm, height - 110*mm, f"(内 消費税: ￥{invoice.tax_amount:,})")

    # 7. 明細テーブル
    person_name = ""
    persons = invoice.order.persons.all()
    if persons.exists():
        person_name = persons.first().name

    data = [
        ["項目 / 詳細", "数量/単位", "単価", "金額"],
        [f"業務委託基本料金\n({invoice.order.project.name} / {person_name})", "1.00", f"￥{invoice.order.base_fee:,}", f"￥{invoice.order.base_fee:,}"],
        [f"精算幅: {invoice.order.time_lower_limit}h ～ {invoice.order.time_upper_limit}h\n稼働時間: {invoice.work_time}h", "", "", ""],
    ]
    
    if invoice.excess_amount > 0:
        over_time = max(0, float(invoice.work_time) - float(invoice.order.time_upper_limit))
        data.append([f"超過精算 ({over_time:.2f}h)", "", f"￥{invoice.order.excess_fee:,}", f"￥{invoice.excess_amount:,}"])
    elif invoice.deduction_amount > 0:
        short_time = max(0, float(invoice.order.time_lower_limit) - float(invoice.work_time))
        data.append([f"控除精算 ({short_time:.2f}h)", "", f"￥{invoice.order.shortage_fee:,}", f"▲￥{invoice.deduction_amount:,}"])

    # 調整等のスペース（空行）
    data.append(["", "", "", ""])
    
    data.append(["税抜小計", "", "", f"￥{invoice.subtotal_amount:,}"])
    data.append(["消費税 (10%)", "", "", f"￥{invoice.tax_amount:,}"])
    data.append(["税込合計", "", "", f"￥{invoice.total_amount:,}"])

    table = Table(data, colWidths=[80*mm, 30*mm, 30*mm, 35*mm])
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, -1), (-1, -1), 10), # 税込合計
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = height - 120*mm - h
    table.drawOn(p, 20*mm, table_y)

    # 8. 振込先情報
    p.setFont(font_name, 10)
    p.drawString(20*mm, table_y - 15*mm, "【お振込先】")
    text_obj = p.beginText(25*mm, table_y - 20*mm)
    text_obj.setFont(font_name, 9)
    for line in bank_info.split('\n'):
        text_obj.textLine(line)
    p.drawText(text_obj)

    # 9. 備考
    p.setFont(font_name, 10)
    p.drawString(20*mm, table_y - 45*mm, "【備考】")
    p.setFont(font_name, 9)
    p.drawString(25*mm, table_y - 50*mm, invoice.order.remarks if invoice.order.remarks else "特記事項なし")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
