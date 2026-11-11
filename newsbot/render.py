import math
import json
import re
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .config import now
from .photos import credit_line

BG = '#08090D'
WHITE = '#FAF8F3'
MUTED = '#CBC9C4'
GOLD = '#FFC449'


def font(size, bold=False):
    names = ([r'C:\Windows\Fonts\arialbd.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
             if bold else [r'C:\Windows\Fonts\arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'])
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    raise ValueError('Font Arial/DejaVu tidak ditemukan. Pasang font sebelum membuat desain.')


def wrap(draw, text, face, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            # Split long URLs/words rather than clipping them.
            if draw.textlength(word, font=face) > width:
                if line:
                    lines.append(line)
                    line = ''
                part = ''
                for char in word:
                    if draw.textlength(part + char, font=face) > width:
                        lines.append(part)
                        part = char
                    else:
                        part += char
                line = part
            elif draw.textlength((line + ' ' + word).strip(), font=face) <= width:
                line = (line + ' ' + word).strip()
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def textbox(draw, text, box, start, minimum, color, bold=False):
    x, y, width, height = box
    for size in range(start, minimum - 1, -2):
        face = font(size, bold)
        lines = wrap(draw, text, face, width)
        step = round(size * 1.3)
        if len(lines) * step <= height:
            for i, line in enumerate(lines):
                draw.text((x, y + i * step), line, font=face, fill=color)
            return y + len(lines) * step
    raise ValueError('Teks terlalu panjang untuk desain. Ringkas naskah terlebih dahulu.')


def editorial_art(category, title, cover):
    """Abstract market illustration. Decorative geometry carries no price data."""
    market = (category + ' ' + title).casefold()
    negative = bool(re.search(r'\b(turun|melemah|anjlok|merosot|jatuh)\b', title.casefold()))
    accent = '#FF5458' if negative else GOLD
    crypto = any(term in market for term in ('crypto', 'kripto', 'bitcoin', 'ethereum', 'stablecoin'))
    market_stat = any(term in market for term in ('ihsg', 'saham', 'bursa', 'inflasi', 'yield', 'suku bunga'))
    figure = re.search(r'(?<!\w)\d+(?:[.,]\d+)?\s*%', title) if market_stat else None
    image = Image.new('RGB', (1080, 1350), BG)
    draw = ImageDraw.Draw(image)
    rgb = (160, 22, 32) if negative else (19, 109, 95) if market_stat else (137, 75, 23)
    center_x, center_y = 570, 365 if cover else 290
    for radius in range(850, 15, -12):
        strength = ((850 - radius) / 850) ** 1.6
        color = tuple(round(9 + channel * strength * (1 if cover else .7)) for channel in rgb)
        draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=color)
    for x in range(-90, 1160, 60):
        draw.line((540 + (x - 540) * .46, 260, x, 870), fill='#293133', width=1)
    for y in (280, 314, 359, 419, 492, 583, 695, 832):
        draw.line((0, y, 1080, y), fill='#293133', width=1)
    for i in range(16):
        left = i * 73 - 16
        top = 680 - (i * 101 % 270)
        draw.rectangle((left, top, left + 49, 880), fill='#11191C', outline='#324144', width=2)
        for y in range(top + 18, 740, 28):
            draw.line((left + 12, y, left + 36, y), fill='#424844', width=2)
    for radius, color in ((289, '#343B38'), (262, '#626150'), (222, '#817052')):
        draw.arc((center_x-radius, center_y-radius, center_x+radius, center_y+radius), 194, 473, fill=color, width=2)
    draw.arc((center_x-258, center_y-258, center_x+258, center_y+258), 208, 312, fill=accent, width=6)
    if figure:
        stat = figure.group().replace(' ', '')
        if not negative and re.search(r'\b(naik|menguat)\b', title.casefold()):
            stat = '+' + stat
        size = min(180, int(950 / max(4, len(stat))))
        draw.text((center_x, center_y), stat, font=font(size, True), fill=WHITE, anchor='mm', stroke_width=2, stroke_fill='#142323')
    elif crypto:
        symbol = 'BTC' if 'bitcoin' in market or 'btc' in market else 'ETH' if 'ethereum' in market else 'CRYPTO'
        draw.text((center_x, center_y), symbol, font=font(112, True), fill=accent, anchor='mm')
    else:
        # Geometric globe for policy, world news, and commodities.
        bounds = (center_x-173, center_y-173, center_x+173, center_y+173)
        draw.ellipse(bounds, outline=accent, width=5)
        for width in (62, 120):
            draw.ellipse((center_x-width, center_y-173, center_x+width, center_y+173), outline=accent, width=2)
        for offset in (-85, 0, 85):
            span = math.sqrt(173**2 - offset**2)
            draw.line((center_x-span, center_y+offset, center_x+span, center_y+offset), fill=accent, width=2)
    mask = Image.new('L', (1, 1350))
    mask.putdata([round(255 * min(1, max(0, (y - (520 if cover else 340)) / 420)) ** 1.25) for y in range(1350)])
    image.paste(BG, (0, 0, 1080, 1350), mask.resize(image.size))
    return image, accent


def headline(draw, title, x, y, width, height, accent):
    title = title.upper()
    for size in range(78, 35, -2):
        face = font(size, True)
        lines = wrap(draw, title, face, width)
        step = round(size * 1.03)
        if size > 44 and len(lines) > 1 and draw.textlength(lines[-1], font=face) < width * .24:
            continue
        if len(lines) * step <= height:
            highlight = next((i for i, line in enumerate(lines) if '%' in line), len(lines) - 1)
            for index, line in enumerate(lines):
                draw.text((x, y + index * step), line, font=face,
                          fill=accent if index == highlight and len(lines) > 1 else WHITE)
            return y + len(lines) * step
    raise ValueError('Judul terlalu panjang untuk desain.')


def render_package(story, draft, destination, brand, ident, version, demo=False, photo=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    slides = []
    for index, slide in enumerate(draft.slides, 1):
        cover = index == 1
        image, accent = editorial_art(story.category, slide.title, cover)
        if cover and photo:
            backdrop = ImageOps.fit(photo.image, (1080, 1010), Image.Resampling.LANCZOS, centering=(.5, .34))
            image = Image.new('RGB', (1080, 1350), BG)
            image.paste(backdrop, (0, 0))
            mask = Image.new('L', (1, 1350))
            mask.putdata([round(255 * max(.66 * max(0, 1-y/190), min(1, max(0, (y-410)/430))**1.4)) for y in range(1350)])
            image.paste(BG, (0, 0, 1080, 1350), mask.resize(image.size))
        draw = ImageDraw.Draw(image)
        display_brand = 'Limitcrypto.id' if brand.casefold() == 'arus' else brand
        hexagon = [(97 + 34 * math.cos(i * math.pi / 3), 88 + 34 * math.sin(i * math.pi / 3)) for i in range(6)]
        draw.line([*hexagon, hexagon[0]], fill=GOLD, width=4, joint='curve')
        inner = [(97 + 24 * math.cos(i * math.pi / 3), 88 + 24 * math.sin(i * math.pi / 3)) for i in range(6)]
        draw.line([*inner, inner[0]], fill='#B4964A', width=1)
        for x, y in inner[::2]:
            draw.ellipse((x-2, y-2, x+2, y+2), fill=WHITE)
        textbox(draw, display_brand, (149, 67, 760, 45), 32, 22, WHITE, True)
        draw.text((1010, 75), f'{index:02}/{len(draft.slides):02}', font=font(21, True), fill=MUTED, anchor='ra')
        category_y = 710 if cover else 548
        textbox(draw, ('SIMULASI / ' if demo else '') + story.category.upper(),
                (68, category_y, 940, 32), 23, 17, accent, True)
        if cover and photo:
            draw.text((1010, category_y), 'FOTO ARSIP / ILUSTRASI', font=font(16, True), fill=WHITE, anchor='ra')
        title_end = headline(draw, slide.title, 65, category_y + 45, 950, 222, accent)
        body_y = title_end + 24
        textbox(draw, slide.body, (68, body_y, 940, 1204 - body_y), 34, 22, MUTED)
        draw.line((68, 1235, 1012, 1235), fill='#323138', width=2)
        label = 'SIMULASI FIKTIF' if demo else '@' + display_brand.upper().replace(' ', '')
        draw.text((540, 1277), label, font=font(22), fill=WHITE, anchor='mm')
        path = destination / f'{index:02}.png'
        image.save(path)
        slides.append(path)
    source_text = '\n'.join(f'- {s.title}: {s.url}' for s in story.sources)
    photo_credit = ''
    if photo:
        (destination / ('foto-asli' + photo.extension)).write_bytes(photo.original)
        (destination / 'foto-kredit.json').write_text(json.dumps(photo.credit, ensure_ascii=False, indent=2), encoding='utf-8')
        photo_credit = '\n\n' + credit_line(photo.credit)
    (destination / 'caption.txt').write_text(draft.caption + '\n\nSumber:\n' + source_text +
                                           photo_credit + f'\n\nDiperiksa: {now().isoformat()}', encoding='utf-8')
    (destination / 'alt-text.txt').write_text('\n\n'.join(f'{i}. {s}' for i, s in enumerate(draft.alt_text, 1)), encoding='utf-8')
    (destination / 'evidence.json').write_text(story.model_dump_json(indent=2), encoding='utf-8')
    (destination / 'draft.json').write_text(draft.model_dump_json(indent=2), encoding='utf-8')
    (destination / 'README.txt').write_text('SIMULASI FIKTIF\n' if demo else 'Periksa kembali sebelum unggah. Paket ini tidak memposting otomatis.\n', encoding='utf-8')
    bundle = destination / f'N-{ident:03}-v{version}.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(destination.iterdir()):
            if path.suffix in ('.jpg', '.png', '.txt', '.json'):
                archive.write(path, path.name)
    return slides, bundle
