from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import colors
import io
import os
from datetime import date
from django.conf import settings
from core.domain.models import CompanyInfo


def _setup_fonts(p):
    font_name = "HeiseiMin-W3"
    try:
        pdfmetrics.getFont(font_name)
    except:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    return font_name


def _get_stamp_path(company):
    """角印画像のパスを取得する。見つからない場合はFileNotFoundErrorを発生させる。"""
    if company and company.stamp_image:
        try:
            path = company.stamp_image.path
            if os.path.exists(path):
                return path
        except Exception:
            pass
    fallback = os.path.join(settings.MEDIA_ROOT, 'stamps', 'company_seal.png')
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError(
        "角印画像が見つかりません。media/stamps/company_seal.png を配置するか、"
        "管理画面の会社情報で角印画像をアップロードしてください。"
    )


def _draw_stamp(p, font_name, company, name_x, name_y, name_font_size=11):
    """角印を社名の右端に被せて描画する。角印画像がない場合はエラー。"""
    stamp_path = _get_stamp_path(company)
    name = company.name if company else "有限会社 マックプランニング"
    name_width = p.stringWidth(name, font_name, name_font_size)
    stamp_size = 22 * mm
    stamp_x = name_x + name_width - stamp_size * 0.35
    stamp_y = name_y - stamp_size * 0.65
    p.drawImage(stamp_path, stamp_x, stamp_y, width=stamp_size, height=stamp_size, mask='auto', preserveAspectRatio=True)


# 契約条項テンプレート
CONTRACT_ARTICLES = [
    ("第1条（目的）",
     "甲は、甲の業務の一部を乙に委託し、乙はこれを受託する。"),
    ("第2条（委託業務）",
     "甲が乙に委託する業務の内容、期間、報酬その他の条件は、個別の注文書により定める。"),
    ("第3条（善管注意義務）",
     "乙は、善良なる管理者の注意をもって委託業務を遂行するものとする。"),
    ("第4条（再委託の禁止）",
     "乙は、甲の書面による事前承諾なく、委託業務の全部または一部を第三者に再委託してはならない。"),
    ("第5条（秘密保持）",
     "甲および乙は、本契約に関連して知り得た相手方の技術上、営業上の秘密を、"
     "相手方の事前の書面による承諾なく第三者に開示・漏洩してはならない。"),
    ("第6条（報酬の支払い）",
     "甲は、乙に対し、個別の注文書に定める報酬を、乙の請求に基づき支払うものとする。"),
    ("第7条（契約期間）",
     "本契約の有効期間は、締結日から1年間とする。ただし、期間満了の1ヶ月前までに"
     "甲乙いずれからも書面による解約の申し出がない場合、同一条件でさらに1年間更新されるものとし、以後も同様とする。"),
    ("第8条（解除）",
     "甲または乙は、相手方が本契約の条項に違反し、催告後相当期間内に"
     "是正されない場合、本契約を解除することができる。"),
    ("第9条（反社会的勢力の排除）",
     "甲および乙は、自己が反社会的勢力に該当しないことを表明し、"
     "将来にわたって該当しないことを確約する。"),
    ("第10条（協議事項）",
     "本契約に定めのない事項または本契約の条項の解釈に疑義が生じた場合は、"
     "甲乙誠意をもって協議のうえ解決するものとする。"),
]


def generate_contract_pdf(partner, signed_at=None, created_date=None):
    """基本契約書PDFを生成する"""
    buffer = io.BytesIO()
    width, height = A4
    p = canvas.Canvas(buffer, pagesize=A4)
    font_name = _setup_fonts(p)

    company = CompanyInfo.objects.first()

    if created_date is None:
        created_date = date.today()

    # --- ページ1: 表紙・契約当事者・条文 ---

    # タイトル
    p.setFont(font_name, 16)
    p.drawCentredString(width / 2, height - 35 * mm, "業務委託基本契約書")

    # 作成日
    p.setFont(font_name, 9)
    p.drawRightString(width - 20 * mm, height - 35 * mm, f"作成日: {created_date.strftime('%Y年%m月%d日')}")

    # サブタイトル
    p.setFont(font_name, 9)
    p.drawCentredString(width / 2, height - 44 * mm,
                        "以下の条項に基づき、甲乙間において業務委託に関する基本契約を締結する。")

    # 甲の情報（自社）
    y_pos = height - 58 * mm
    p.setFont(font_name, 10)
    p.drawString(20 * mm, y_pos, "（甲）")
    if company:
        p.setFont(font_name, 11)
        p.drawString(20 * mm, y_pos - 5 * mm, company.name)
        p.setFont(font_name, 9)
        p.drawString(20 * mm, y_pos - 10 * mm, f"〒{company.postal_code}")
        p.drawString(20 * mm, y_pos - 14 * mm, company.address)
        p.drawString(20 * mm, y_pos - 18 * mm,
                     f"{company.representative_title} {company.representative_name}")
    else:
        p.setFont(font_name, 11)
        p.drawString(20 * mm, y_pos - 5 * mm, "有限会社 マックプランニング")

    # 甲の角印
    p.setFont(font_name, 11)
    _draw_stamp(p, font_name, company, 20 * mm, y_pos - 5 * mm, 11)

    # 乙の情報（パートナー）
    p.setFont(font_name, 10)
    p.drawString(110 * mm, y_pos, "（乙）")
    p.setFont(font_name, 11)
    p.drawString(110 * mm, y_pos - 5 * mm, partner.name)
    p.setFont(font_name, 9)
    if partner.postal_code:
        p.drawString(110 * mm, y_pos - 10 * mm, f"〒{partner.postal_code}")
    if partner.address:
        p.drawString(110 * mm, y_pos - 14 * mm, partner.address)
    if partner.representative_name:
        rep_title = partner.representative_position or ""
        p.drawString(110 * mm, y_pos - 18 * mm,
                     f"{rep_title} {partner.representative_name}")

    # 契約条項
    y_pos = height - 92 * mm
    for i, (title, body) in enumerate(CONTRACT_ARTICLES):
        if y_pos < 30 * mm:
            p.showPage()
            font_name = _setup_fonts(p)
            y_pos = height - 25 * mm

        p.setFont(font_name, 10)
        p.drawString(20 * mm, y_pos, title)
        y_pos -= 6 * mm

        p.setFont(font_name, 9)
        # テキストを折り返して描画（A4幅に収まるよう調整）
        max_width = width - 45 * mm  # 左20mm + 右25mm分を引く
        remaining = body
        while remaining:
            # 幅に収まる文字数を計算
            line = ""
            for char in remaining:
                test = line + char
                if p.stringWidth(test, font_name, 9) > max_width:
                    break
                line = test
            if not line:
                line = remaining[0]
            remaining = remaining[len(line):]
            p.drawString(25 * mm, y_pos, line)
            y_pos -= 5 * mm

        y_pos -= 3 * mm

    # --- 署名欄 ---
    if y_pos < 70 * mm:
        p.showPage()
        font_name = _setup_fonts(p)
        y_pos = height - 25 * mm

    y_pos -= 10 * mm
    p.setFont(font_name, 10)
    p.drawString(20 * mm, y_pos, "上記条項を証するため、本契約書を電子的に作成し、")
    y_pos -= 6 * mm
    p.drawString(20 * mm, y_pos, "甲乙記名のうえ締結する。")
    y_pos -= 12 * mm

    # 締結日
    if signed_at:
        from django.utils import timezone as tz
        local_signed = tz.localtime(signed_at)
        date_str = local_signed.strftime("%Y年%m月%d日")
    else:
        date_str = "　　　　年　　月　　日（乙の電子承認時に自動記入）"
    p.setFont(font_name, 10)
    p.drawString(20 * mm, y_pos, f"締結日: {date_str}")
    y_pos -= 18 * mm

    # 甲の署名欄
    p.setFont(font_name, 10)
    p.drawString(20 * mm, y_pos, "（甲）")
    p.setFont(font_name, 11)
    if company:
        p.drawString(20 * mm, y_pos - 7 * mm, company.name)
        p.drawString(20 * mm, y_pos - 14 * mm,
                     f"{company.representative_title} {company.representative_name}")
    else:
        p.drawString(20 * mm, y_pos - 7 * mm, "有限会社 マックプランニング")

    # 甲の角印
    _draw_stamp(p, font_name, company, 20 * mm, y_pos - 7 * mm, 11)

    # 乙の署名欄
    p.setFont(font_name, 10)
    p.drawString(110 * mm, y_pos, "（乙）")
    p.setFont(font_name, 11)
    p.drawString(110 * mm, y_pos - 7 * mm, partner.name)
    if partner.representative_name:
        rep_title = partner.representative_position or ""
        p.drawString(110 * mm, y_pos - 14 * mm,
                     f"{rep_title} {partner.representative_name}")

    if signed_at:
        # 承認済みの場合: 電子承認マークを表示
        p.setFont(font_name, 9)
        p.setFillColor(colors.HexColor('#10B981'))
        p.drawString(110 * mm, y_pos - 22 * mm, "【電子承認済】")
        p.setFillColor(colors.black)
        p.drawString(110 * mm, y_pos - 27 * mm, f"承認日時: {local_signed.strftime('%Y年%m月%d日 %H:%M')}")
    else:
        # 未承認の場合
        p.setFont(font_name, 8)
        p.setFillColor(colors.gray)
        p.drawString(110 * mm, y_pos - 22 * mm, "※ 乙の電子承認をもって締結とする")
        p.setFillColor(colors.black)

    # フッター: 電子契約に関する注記
    p.setFont(font_name, 7)
    p.setFillColor(colors.gray)
    p.drawString(20 * mm, 15 * mm,
                 "本契約書は電帳法に基づき電子的に作成・保存されています。"
                 "乙の電子承認は、押印に代わる法的効力を有します。")
    p.setFillColor(colors.black)

    p.save()
    buffer.seek(0)
    return buffer
