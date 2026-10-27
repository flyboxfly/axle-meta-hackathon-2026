"""Create a precise synthetic vision fixture; never uses carrier records."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    image = Image.new('RGB', (1000, 680), '#010e19')
    draw = ImageDraw.Draw(image)
    # Portable bundled bitmap font, enlarged by font_size where Pillow supports it.
    title = ImageFont.load_default(size=38)
    body = ImageFont.load_default(size=30)
    small = ImageFont.load_default(size=22)
    draw.text((48, 40), 'SYNTHETIC FREIGHT OPPORTUNITY', font=title, fill='#2ebbe4')
    draw.text((48, 105), 'TEST FIXTURE - NOT A LIVE LOAD', font=small, fill='#fdad75')
    rows = [
        ('Equipment', '26-foot box truck'),
        ('Total all-in payout', '$420.00'),
        ('Loaded miles', '180'),
        ('Additional miles (deadhead + repositioning)', '60'),
    ]
    y = 170
    for label, value in rows:
        draw.text((48, y), label, font=small, fill='#b6cad3')
        draw.text((48, y+30), value, font=body, fill='#fdfcf6')
        y += 100
    draw.text((48, 600), 'Operating costs and schedule are not supplied.', font=small, fill='#b6cad3')
    path = Path(__file__).resolve().parents[1] / 'fixtures' / 'synthetic_freight_screenshot.png'
    image.save(path)
    print(path)


if __name__ == '__main__':
    main()
