import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# フォントの設定（macOS標準の日本語フォント）
FONT_PATH = '/System/Library/Fonts/Supplemental/AppleGothic.ttf'
FONT_NAME = 'AppleGothic'
pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))

def create_pdf(filename):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # マージン
    margin = 50
    y = height - margin
    
    # 登録したフォントを使用
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(width/2, y, "電子取引データの訂正及び削除の防止に関する事務処理規定")
    y -= 40
    
    lines = [
        "第1条（目的）",
        "この規定は、電子帳簿保存法第7条に規定する電子取引の取引情報に係る電磁的記録の保存",
        "について、不当な訂正及び削除の防止に関し、必要な事項を定めることを目的とする。",
        "",
        "第2条（適用範囲）",
        "この規定は、本EDIシステム（以下「システム」という）を利用して授受される、以下の",
        "書類に係る電磁的記録に適用する。",
        "1. 注文書",
        "2. 注文請書",
        "3. 請求明細（支払通知書）",
        "",
        "第3条（管理責任者）",
        "1. システムの運用及び管理に当たっては、管理責任者1名を置くものとする。",
        "2. 管理責任者は、[経理部長]とする。",
        "3. 管理責任者は、この規定の運用状況を適宜確認し、必要に応じて規定の見直しを行う。",
        "",
        "第4条（データの訂正・削除の禁止）",
        "1. システムに保存された取引データは、原則として訂正及び削除を行わない。",
        "2. やむを得ない理由によりデータの訂正又は削除が必要となった場合は、以下の手順による",
        "   ものとする。",
        "   (1) 作成者による訂正・削除理由の申告",
        "   (2) 管理責任者による承認",
        "   (3) システム上の履歴保持機能、又は修正前後が確認できる形式での保存",
        "",
        "第5条（保存期間）",
        "システム上の電磁的記録は、法人税法その他の税法に定める保存期間（原則として7年間）",
        "にわたり、適切に保存されるものとする。",
        "",
        "第6条（検索機能の確保）",
        "管理責任者は、税務調査等の際に必要となる以下の検索機能が適切に動作するよう管理する。",
        "1. 取引年月日、取引金額、取引先による検索",
        "2. 日付又は金額の範囲指定による検索",
        "3. 2つ以上の任意の項目の組み合わせによる検索",
        "",
        "附則",
        "この規定は、2026年2月1日から施行する。"
    ]
    
    c.setFont(FONT_NAME, 10)
    for line in lines:
        if y < margin:
            c.showPage()
            y = height - margin
            c.setFont(FONT_NAME, 10)
        
        c.drawString(margin, y, line)
        y -= 20
        
    c.save()

if __name__ == "__main__":
    output_path = "/Users/yutaka/workspace/EDI_MP/事務処理規定_電子取引.pdf"
    create_pdf(output_path)
    print(f"PDF created at: {output_path}")
