from PIL import Image, ImageDraw, ImageFont

def test_font(font_name, output_name):
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_name, 50)
        draw.text((10, 10), "♚♘", fill=(0, 0, 0), font=font)
        img.save(output_name)
        print(f"{font_name} success")
    except Exception as e:
        print(f"{font_name} failed: {e}")

test_font("seguisym.ttf", "test_sym.png")
test_font("seguiemj.ttf", "test_emj.png")
