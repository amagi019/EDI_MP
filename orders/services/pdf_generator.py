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
from core.services.contract_pdf_generator import _get_stamp_path

def _setup_fonts(p):
    # フォント登録（日本語対応）
    font_name = "HeiseiMin-W3"
    try:
        pdfmetrics.getFont(font_name)
    except:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    return font_name

def _draw_company_info(p, x, y, font_name, side="甲", name_font_size=10):
    """甲（自社情報）を描画し、描画に使った高さ(mm)を返す。"""
    label_font_size = name_font_size - 1  # ラベルは社名より1pt小さく
    detail_font_size = 9

    company = CompanyInfo.objects.first()
    if not company:
        name, post, addr, tel, fax = '', '', '', '', ''
    else:
        name = company.name
        post = f"〒{company.postal_code}"
        addr = company.address
        tel = company.tel
        fax = company.fax

    p.setFont(font_name, label_font_size)
    p.drawString(x, y, f"（{side}）")
    p.setFont(font_name, name_font_size)
    p.drawString(x, y - 5*mm, name)
    p.setFont(font_name, detail_font_size)
    p.drawString(x, y - 10*mm, post)
    p.drawString(x, y - 14*mm, addr)
    p.drawString(x, y - 18*mm, f"TEL:{tel}  FAX:{fax}")

    # 描画した合計高さ = ラベルからTEL行の下端まで ≒ 18mm + フォント分
    total_height = 20*mm
    return name, total_height


def _draw_header_section(p, width, height, font_name, order=None,
                          addressee_label="（乙）", addressee_name=None,
                          addressee_suffix="御中",
                          issuer_label="（甲）", issuer_info=None,
                          show_stamp=True):
    """宛先（左側）と発行者（右側）を自動バランスで配置し、次セクションのY座標を返す。

    レイアウトルール:
      1. 宛先の社名フォントは発行者の社名フォントより大きい
      2. 発行者の記載欄と宛先の記載欄が重ならない
      3. 発行者の記載位置（印影含む）が右寄せ
      4. 発行者と宛先の間に2行分（≒8mm）の間隔
      5. 発行者の下端（印影含む）と次セクションの間に2行分（≒8mm）の間隔

    Args:
        addressee_name: 宛先の社名（Noneの場合order.partner.nameを使用）
        issuer_info: dict(name, postal_code, address, tel, fax) 発行者情報。Noneの場合CompanyInfoを使用
        show_stamp: 角印を表示するか
    """
    LINE_GAP = 8 * mm
    ADDR_NAME_FONT = 12     # 宛先の社名フォント（大きい方）
    ISSUER_NAME_FONT = 10   # 発行者の社名フォント（小さい方）
    RIGHT_MARGIN = 20 * mm
    STAMP_SIZE = 22 * mm
    STAMP_OVERLAP = 0.35

    # --- 宛先名の決定 ---
    if addressee_name is None:
        addressee_name = order.partner.name if order else ''

    # --- 発行者情報の決定 ---
    company = CompanyInfo.objects.first()
    if issuer_info is None:
        issuer_info = {
            'name': company.name if company else '',
            'postal_code': company.postal_code if company else '',
            'address': company.address if company else '',
            'tel': company.tel if company else '',
            'fax': company.fax if company else '',
        }

    # --- 宛先セクション描画（左側・大フォント） ---
    addr_label_y = height - 50*mm
    p.setFont(font_name, ADDR_NAME_FONT)
    p.drawString(20*mm, addr_label_y, addressee_label)
    p.setFont(font_name, ADDR_NAME_FONT)
    addr_name_y = addr_label_y - 6*mm
    p.drawString(20*mm, addr_name_y, f"{addressee_name}  {addressee_suffix}")
    addr_bottom = addr_name_y

    # --- 発行者セクション: X座標の自動右寄せ計算 ---
    issuer_name = issuer_info['name']
    p.setFont(font_name, ISSUER_NAME_FONT)
    name_width = p.stringWidth(issuer_name, font_name, ISSUER_NAME_FONT)

    if show_stamp:
        stamp_protrusion = STAMP_SIZE * (1 - STAMP_OVERLAP)
    else:
        stamp_protrusion = 0

    tel_fax_text = f"TEL:{issuer_info['tel']}  FAX:{issuer_info['fax']}"
    tel_width = p.stringWidth(tel_fax_text, font_name, 9)

    max_content_width = max(name_width + stamp_protrusion, tel_width)
    issuer_x = width - RIGHT_MARGIN - max_content_width

    # --- 発行者セクション: Y座標の自動計算 ---
    issuer_y = addr_bottom - LINE_GAP

    # --- 発行者セクション描画 ---
    label_font_size = ISSUER_NAME_FONT - 1
    p.setFont(font_name, label_font_size)
    p.drawString(issuer_x, issuer_y, issuer_label)
    p.setFont(font_name, ISSUER_NAME_FONT)
    p.drawString(issuer_x, issuer_y - 5*mm, issuer_name)
    p.setFont(font_name, 9)
    p.drawString(issuer_x, issuer_y - 10*mm, f"〒{issuer_info['postal_code']}")
    p.drawString(issuer_x, issuer_y - 14*mm, issuer_info['address'])
    p.drawString(issuer_x, issuer_y - 18*mm, tel_fax_text)
    issuer_height = 20*mm

    # --- 角印描画 ---
    stamp_bottom = issuer_y - issuer_height  # デフォルト（角印なしの場合）
    if show_stamp:
        stamp_path = _get_stamp_path(company)
        stamp_x = issuer_x + name_width - STAMP_SIZE * STAMP_OVERLAP
        stamp_y = issuer_y - 5*mm - STAMP_SIZE * 0.65
        p.drawImage(stamp_path, stamp_x, stamp_y, width=STAMP_SIZE, height=STAMP_SIZE,
                    mask='auto', preserveAspectRatio=True)
        stamp_bottom = stamp_y

    # --- 次セクション開始Y座標の計算 ---
    issuer_text_bottom = issuer_y - issuer_height
    actual_bottom = min(issuer_text_bottom, stamp_bottom)
    next_section_y = actual_bottom - LINE_GAP

    return next_section_y

def _build_fee_table(order, font_name):
    """業務委託料金のサブテーブルを生成（フル幅版）"""
    items = order.items.all()
    if not items.exists():
        return "（明細行が登録されていません）"

    # ヘッダー行（単位は括弧内に記載）
    header = ["氏名", "基本料金（円/月）", "不足単価（円/h）", "超過単価（円/h）", "基準時間（h/月）"]
    sub_data = [header]

    for item in items:
        name = item.person_name or "作業担当者"
        sub_data.append([
            name,
            f"¥{item.base_fee:,}",
            f"¥{item.shortage_rate:,}",
            f"¥{item.excess_rate:,}",
            f"{item.time_lower_limit}～{item.time_upper_limit}",
        ])

    # フッター行
    sub_data.append(["※作業報告書に基づく稼動実費精算とする。", "", "", "", ""])

    # フル幅: メインテーブル全幅(180mm)からパディング分を引いた幅を使用
    sub_table = Table(sub_data, colWidths=[38*mm, 38*mm, 30*mm, 30*mm, 38*mm])
    sub_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font_name, 9),
        ('FONT', (0, 0), (-1, 0), font_name, 8),
        ('GRID', (0, 0), (-1, -2), 0.3, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.92, 0.92, 0.92)),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        # フッター行はスパン＆罫線なし
        ('SPAN', (0, -1), (-1, -1)),
        ('ALIGN', (0, -1), (0, -1), 'LEFT'),
        ('FONT', (0, -1), (0, -1), font_name, 8),
        ('GRID', (0, -1), (-1, -1), 0, colors.white),
    ]))
    return sub_table

def generate_order_pdf(order, watermark=None):
    """注文書PDFの生成"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _setup_fonts(p)

    # 1. 注文番号・日付 (右上)
    p.setFont(font_name, 10)
    p.drawRightString(width - 20*mm, height - 15*mm, f"注文番号 : {order.order_id}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"{order.order_date.strftime('%Y年%m月%d日')}")

    # 2. タイトル
    p.setFont(font_name, 20)
    p.drawCentredString(width / 2, height - 35*mm, "注  文  書")

    # ウォーターマーク
    if watermark:
        p.saveState()
        p.setFont(font_name, 80)
        p.setStrokeColor(colors.lightgrey, alpha=0.3)
        p.setFillColor(colors.lightgrey, alpha=0.3)
        p.rotate(45)
        p.drawCentredString(width / 2 + 50*mm, height / 2 - 100*mm, watermark)
        p.restoreState()

    # 3-6. 乙（宛先）＋甲（発行者）＋角印の自動バランス配置
    next_y = _draw_header_section(p, width, height, font_name, order)

    # 7. 本文（甲セクションの下端から自動計算された位置に配置）
    company = CompanyInfo.objects.first()
    p.setFont(font_name, 10)
    p.drawString(20*mm, next_y, "下記の通り注文致しますので、ご了承の上、折り返し注文請書をご送付下さい。")

    # 8. 詳細テーブル
    kou_res = order.甲_責任者 or (company.responsible_person if company else "")
    kou_cnt = order.甲_担当者 or (company.contact_person if company else "")
    otsu_res = order.乙_責任者 or order.partner.responsible_person
    otsu_cnt = order.乙_担当者 or order.partner.contact_person

    fee_table = _build_fee_table(order, font_name)

    data = [
        ["業務名称", order.project.name if order.project else ""],
        ["作業期間", f"{order.work_start.strftime('%Y年%m月%d日')} ～ {order.work_end.strftime('%Y年%m月%d日')}"],
        ["委託業務責任者（甲）", kou_res, "連絡窓口担当者（甲）", kou_cnt],
        ["委託業務責任者（乙）", otsu_res, "連絡窓口担当者（乙）", otsu_cnt],
        ["作業責任者", order.作業責任者, "", ""],
        ["業務委託料金", "", "", ""],
        [fee_table, "", "", ""],
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
        # 業務委託料金: ラベル行は全列スパン・左上配置
        ('SPAN', (0, 5), (3, 5)),
        ('VALIGN', (0, 5), (0, 5), 'TOP'),
        ('ALIGN', (0, 5), (0, 5), 'LEFT'),
        # 料金テーブル行も全列スパン
        ('SPAN', (0, 6), (3, 6)),
        ('TOPPADDING', (0, 6), (0, 6), 0),
        ('BOTTOMPADDING', (0, 6), (0, 6), 0),
        ('LEFTPADDING', (0, 6), (0, 6), 0),
        ('RIGHTPADDING', (0, 6), (0, 6), 0),
        # 作業場所以降
        ('SPAN', (1, 7), (3, 7)),
        ('SPAN', (1, 8), (3, 8)),
        ('SPAN', (1, 9), (3, 9)),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = next_y - 5*mm - h  # 本文の直下に配置
    table.drawOn(p, 20*mm, table_y)

    # 9. 契約条項
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
    p.drawRightString(width - 20*mm, height - 15*mm, f"注文番号 : {order.order_id}")
    p.drawRightString(width - 20*mm, height - 20*mm, f"{order.order_date.strftime('%Y年%m月%d日')}")

    # 2. タイトル
    p.setFont(font_name, 20)
    p.drawCentredString(width / 2, height - 35*mm, "注  文  請  書")

    # 3. 印紙枠
    p.rect(20*mm, height - 40*mm, 20*mm, 25*mm)
    p.setFont(font_name, 8)
    p.drawCentredString(30*mm, height - 28*mm, "印紙")

    # 4-5. 甲（宛先＝自社）＋乙（発行者＝パートナー）の自動バランス配置
    company = CompanyInfo.objects.first()
    next_y = _draw_header_section(
        p, width, height, font_name, order,
        addressee_label="（甲）",
        addressee_name=company.name if company else '',
        addressee_suffix="御中",
        issuer_label="（乙）",
        issuer_info={
            'name': order.partner.name,
            'postal_code': order.partner.postal_code,
            'address': order.partner.address,
            'tel': order.partner.tel,
            'fax': getattr(order.partner, 'fax', ''),
        },
        show_stamp=False,  # 注文請書はパートナー発行のため角印なし
    )

    # 6. テーブル
    kou_res = order.甲_責任者 or (company.responsible_person if company else "")
    kou_cnt = order.甲_担当者 or (company.contact_person if company else "")
    otsu_res = order.乙_責任者 or order.partner.responsible_person
    otsu_cnt = order.乙_担当者 or order.partner.contact_person

    fee_table = _build_fee_table(order, font_name)

    data = [
        ["業務名称", order.project.name if order.project else ""],
        ["作業期間", f"{order.work_start.strftime('%Y年%m月%d日')} ～ {order.work_end.strftime('%Y年%m月%d日')}"],
        ["委託業務責任者（甲）", kou_res, "連絡窓口担当者（甲）", kou_cnt],
        ["委託業務責任者（乙）", otsu_res, "連絡窓口担当者（乙）", otsu_cnt],
        ["作業責任者", order.作業責任者, "", ""],
        ["業務委託料金", "", "", ""],
        [fee_table, "", "", ""],
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
        # 業務委託料金: ラベル行は全列スパン・左上配置
        ('SPAN', (0, 5), (3, 5)),
        ('VALIGN', (0, 5), (0, 5), 'TOP'),
        ('ALIGN', (0, 5), (0, 5), 'LEFT'),
        # 料金テーブル行も全列スパン
        ('SPAN', (0, 6), (3, 6)),
        ('TOPPADDING', (0, 6), (0, 6), 0),
        ('BOTTOMPADDING', (0, 6), (0, 6), 0),
        ('LEFTPADDING', (0, 6), (0, 6), 0),
        ('RIGHTPADDING', (0, 6), (0, 6), 0),
        # 作業場所以降
        ('SPAN', (1, 7), (3, 7)),
        ('SPAN', (1, 8), (3, 8)),
        ('SPAN', (1, 9), (3, 9)),
    ]))

    w, h = table.wrapOn(p, width, height)
    table_y = next_y - 5*mm - h  # 動的Y座標
    table.drawOn(p, 20*mm, table_y)

    # 7. お客様サイン欄 (底部)
    p.rect(20*mm, 20*mm, 40*mm, 15*mm)
    p.drawCentredString(40*mm, 25*mm, "承諾署名")
    p.rect(60*mm, 20*mm, 130*mm, 15*mm)
    p.setFont(font_name, 10)
    p.drawString(65*mm, 27*mm, f"{order.partner.name}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
