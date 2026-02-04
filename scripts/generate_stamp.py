from PIL import Image, ImageDraw, ImageFont
import os
import sys

def generate_vertical_stamp(text, output_path):
    # 背景透明の正方形画像を作成
    size = 400  # 高解像度で作成して後で縮小またはPDF側でサイズ調整
    img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # 赤色の枠
    border_width = size // 20
    draw.rectangle([border_width//2, border_width//2, size - border_width//2, size - border_width//2], 
                   outline=(220, 0, 0, 255), width=border_width)

    # フォントの読み込み
    # Macのシステムフォントから明朝体またはボールド系のフォントを探す
    font_paths = [
        "/System/Library/Fonts/ヒラギノ明朝 ProN W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
        "/System/Library/Fonts/Supplemental/Yu Mincho.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc"
    ]
    
    font_path = None
    for p in font_paths:
        if os.path.exists(p):
            font_path = p
            break
    
    if not font_path:
        print("Suitable font not found.")
        return

    try:
        # 印鑑（角印）の文字配置：右から左、上から下
        # 「有限会社マックプランニング印」 15文字
        # 3列 x 5行 に配置
        full_text = text
        if not full_text.endswith("印"):
            full_text += "印"
            
        # 1列5文字、全3列
        rows_per_col = 5
        cols = 3
        
        # 文字を分割
        # 右列: [0:5], 中列: [5:10], 左列: [10:15]
        columns = [
            full_text[0:5],
            full_text[5:10],
            full_text[10:15]
        ]
        
        # フォントサイズを調整（400 / 5 = 80 付近）
        font_size = int(size * 0.16)
        font = ImageFont.truetype(font_path, font_size)
        
        margin = border_width + 10
        inner_size = size - (margin * 2)
        col_width = inner_size / cols
        row_height = inner_size / rows_per_col
        
        # 右端から順に描画
        for c in range(cols):
            col_text = columns[c]
            # c=0 は右列
            x_pos = size - margin - (c + 1) * col_width + (col_width * 0.1)
            for r in range(len(col_text)):
                char = col_text[r]
                y_pos = margin + r * row_height
                
                # 文字の中央寄せ微調整
                bbox = draw.textbbox((0, 0), char, font=font)
                w = bbox[2] - bbox[0]
                # h = bbox[3] - bbox[1]
                
                draw.text((x_pos + (col_width - w) / 2, y_pos), char, font=font, fill=(220, 0, 0, 255))
                
    except Exception as e:
        print(f"Hanko generation error: {e}")

    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path)
    print(f"Stamp generated at {output_path}")

if __name__ == "__main__":
    company_name = "有限会社マックプランニング"
    generate_vertical_stamp(company_name, "media/stamps/default_stamp.png")
