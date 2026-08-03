from PIL import ImageFont

fonts = ['seguisym.ttf', 'seguiemj.ttf', 'segoeui.ttf', 'arial.ttf', 'arialuni.ttf', 'segoeuis.ttf']
fonts_found = []
for f in fonts:
    try:
        font = ImageFont.truetype(f, 20)
        fonts_found.append(f)
    except Exception as e:
        pass
print('Found fonts:', fonts_found)
