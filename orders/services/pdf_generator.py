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

def _draw_company_info(p, x, y, font_name, side="甲"):
    p.setFont(font_name, 10)
    company = CompanyInfo.objects.first()
    if not company:
        # デフォルト値
        name = "有限会社 マックプランニング"
        post = "〒116-0012"
        addr = "東京都荒川区東尾久8-9-14"
        tel = "090-3043-0477"
        fax = ""
        rep = "代表取締役 吉川 裕"
    else:
        name = company.name
        post = f"〒{company.postal_code}"
        addr = company.address
        tel = company.tel
        fax = company.fax
        rep = f"{company.representative_title} {company.representative_name}"

    p.drawString(x, y, f"（{side}）")
    p.setFont(font_name, 11)
    p.drawString(x, y - 5*mm, name)
    p.setFont(font_name, 9)
    p.drawString(x, y - 10*mm, post)
    p.drawString(x, y - 14*mm, addr)
    reg_no = company.registration_no if company else "TXXXXXXXXXXXXX"
    p.drawString(x, y - 18*mm, f"TEL:{tel}  FAX:{fax}")
    p.drawString(x, y - 22*mm, f"登録番号: {reg_no}")
    
    return name, rep

def generate_order_pdf(order, watermark=None):
    """注文書PDFの生成"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _setup_fonts(p)

    # 1. 注文番号・日付 (右上)
    p.setFont(font_name, 10)
    p.drawRightString(width - 20*mm, height - 15*mm, f"注文番号：{order.order_id}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"{order.order_date.strftime('%Y年%m月%d日')}")

    p.setFont(font_name, 18)
    p.drawCentredString(width / 2, height - 35*mm, "注 文 書")

    # ウォーターマーク（下書き用）
    if watermark:
        p.saveState()
        p.setFont(font_name, 80)
        p.setStrokeColor(colors.lightgrey, alpha=0.3)
        p.setFillColor(colors.lightgrey, alpha=0.3)
        p.rotate(45)
        p.drawCentredString(width / 2 + 50*mm, height / 2 - 100*mm, watermark)
        p.restoreState()

    # 3. 宛先 (乙)
    p.setFont(font_name, 12)
    p.drawString(20*mm, height - 50*mm, "（乙）")
    p.drawString(20*mm, height - 56*mm, f"{order.customer.name}  御中")

    # 4. 発行人 (甲) - 自社情報
    _draw_company_info(p, 110*mm, height - 55*mm, font_name, "甲")

    # 5. 印影表示
    company = CompanyInfo.objects.first()
    if company and company.stamp_image:
        try:
            stamp_path = company.stamp_image.path
            p.drawImage(stamp_path, 160*mm, height - 85*mm, width=22*mm, height=22*mm, mask='auto', preserveAspectRatio=True)
        except:
            pass

    # 6. 本文
    p.setFont(font_name, 10)
    p.drawString(20*mm, height - 105*mm, "下記の通り注文致しますので、ご了承の上、折り返し注文請書をご送付下さい。")

    # 7. 詳細テーブル
    company = CompanyInfo.objects.first()
    kou_res = order.甲_責任者 or (company.responsible_person if company else "")
    kou_cnt = order.甲_担当者 or (company.contact_person if company else "")
    otsu_res = order.乙_責任者 or order.customer.responsible_person
    otsu_cnt = order.乙_担当者 or order.customer.contact_person

    data = [
        ["業務名称", order.project.name if order.project else ""],
        ["作業期間", f"{order.work_start.strftime('%Y年%m月%d日')} ～ {order.work_end.strftime('%Y年%m月%d日')}"],
        ["委託業務責任者（甲）", kou_res, "連絡窓口担当者（甲）", kou_cnt],
        ["委託業務責任者（乙）", otsu_res, "連絡窓口担当者（乙）", otsu_cnt],
        ["作業責任者", order.作業責任者, "", ""],
        ["業務委託料金", f"月額基本料金：￥{order.base_fee:,}円/月 (消費税抜き)\n"
                         f"不足単価：￥{order.shortage_fee:,}/h\n"
                         f"超過単価：￥{order.excess_fee:,}/h\n"
                         f"※基準時間：{order.time_lower_limit}h～{order.time_upper_limit}h/月\n\n"
                         "作業報告書に基づく稼動実費精算とする。"],
        ["作業場所", order.workplace.name if order.workplace else ""],
        ["納入物件", order.deliverable_text],
        ["支払条件", order.payment_condition],
    ]

    table = Table(data, colWidths=[38*mm, 52*mm, 38*mm, 52*mm])
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, 0), (3, 0)), # 業務名称
        ('SPAN', (1, 1), (3, 1)), # 作業期間
        ('SPAN', (1, 4), (3, 4)), # 作業責任者
        ('SPAN', (1, 5), (3, 5)), # 料金
        ('SPAN', (1, 6), (3, 6)), # 場所
        ('SPAN', (1, 7), (3, 7)), # 納入物件
        ('SPAN', (1, 8), (3, 8)), # 支払条件
        ('BOTTOMPADDING', (0, 5), (-1, 5), 10),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = height - 110*mm - h
    table.drawOn(p, 20*mm, table_y)

    # 8. 契約条項
    p.setFont(font_name, 9)
    p.drawString(20*mm, table_y - 10*mm, "〈契約条項〉")
    text_obj = p.beginText(20*mm, table_y - 15*mm)
    text_obj.setFont(font_name, 8)
    for line in order.contract_items.split('\n'):
        text_obj.textLine(line)
    p.drawText(text_obj)

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

def generate_acceptance_pdf(order):
    """注文請書PDFの生成"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _setup_fonts(p)

    # 1. 注文番号・日付
    p.setFont(font_name, 10)
    p.drawRightString(width - 20*mm, height - 15*mm, f"注文番号：{order.order_id}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"{order.order_date.strftime('%Y年%m月%d日')}")

    # 2. タイトル
    p.setFont(font_name, 18)
    p.drawCentredString(width / 2, height - 35*mm, "注 文 請 書")

    # 3. 宛先 (甲) - 自社名
    p.setFont(font_name, 12)
    p.drawString(20*mm, height - 50*mm, "（甲）")
    company = CompanyInfo.objects.first()
    p.drawString(20*mm, height - 56*mm, f"{company.name if company else '有限会社 マックプランニング'}  御中")

    # 4. 発行人 (乙) - 取引先
    p.setFont(font_name, 10)
    p.drawString(110*mm, height - 50*mm, "（乙）")
    p.setFont(font_name, 11)
    p.drawString(110*mm, height - 55*mm, f"〒{order.customer.postal_code}")
    p.drawString(110*mm, height - 60*mm, order.customer.address)
    p.drawString(110*mm, height - 65*mm, order.customer.name)
    p.drawString(110*mm, height - 70*mm, f"TEL:{order.customer.tel}")

    # 5. 印影 (乙)
    # 本来は取引先の印影だが、ここでは自社情報の印影を乙（パートナー）としてのサンプルまたは
    # システム上アップロードされたものがあれば表示する
    # パートナーがアップロードした印影という概念がまだないので、一旦スキップかプレースホルダ

    # 6. テーブル (注文書と同じ内容)
    kou_res = order.甲_責任者 or (company.responsible_person if company else "")
    kou_cnt = order.甲_担当者 or (company.contact_person if company else "")
    otsu_res = order.乙_責任者 or order.customer.responsible_person
    otsu_cnt = order.乙_担当者 or order.customer.contact_person

    data = [
        ["業務名称", order.project.name if order.project else ""],
        ["作業期間", f"{order.work_start.strftime('%Y年%m月%d日')} ～ {order.work_end.strftime('%Y年%m月%d日')}"],
        ["委託業務責任者（甲）", kou_res, "連絡窓口担当者（甲）", kou_cnt],
        ["委託業務責任者（乙）", otsu_res, "連絡窓口担当者（乙）", otsu_cnt],
        ["作業責任者", order.作業責任者, "", ""],
        ["業務委託料金", f"月額基本料金：￥{order.base_fee:,}円/月 (消費税抜き)\n"
                         f"不足単価：￥{order.shortage_fee:,}/h\n"
                         f"超過単価：￥{order.excess_fee:,}/h\n"
                         f"※基準時間：{order.time_lower_limit}h～{order.time_upper_limit}h/月\n\n"
                         "作業報告書に基づく稼動実費精算とする。"],
        ["作業場所", order.workplace.name if order.workplace else ""],
        ["納入物件", order.deliverable_text],
        ["支払条件", order.payment_condition],
    ]

    table = Table(data, colWidths=[38*mm, 52*mm, 38*mm, 52*mm])
    table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, 0), (3, 0)),
        ('SPAN', (1, 1), (3, 1)),
        ('SPAN', (1, 4), (3, 4)),
        ('SPAN', (1, 5), (3, 5)),
        ('SPAN', (1, 6), (3, 6)),
        ('SPAN', (1, 7), (3, 7)),
        ('SPAN', (1, 8), (3, 8)),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = height - 100*mm - h
    table.drawOn(p, 20*mm, table_y)

    # 7. お客様サイン欄 (底部)
    p.rect(20*mm, 20*mm, 40*mm, 15*mm)
    p.drawCentredString(40*mm, 25*mm, "お客様サイン欄")
    p.rect(60*mm, 20*mm, 130*mm, 15*mm)
    p.drawString(65*mm, 27*mm, f"{order.customer.name}")
    
    # 印影表示は不要のため削除


    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
