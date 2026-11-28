"""Zone 5 (belly and keel) before / after sheet (plain python3 + Pillow, no Blender).

  python3 -B detail_z5_sheet.py [MEDIA_DIR] [OUT.jpg]
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

MEDIA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/z5'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MEDIA, 'z5_sheet.jpg')
W, PAD, BG = 1920, 8, (36, 38, 44)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
f_title, f_row, f_lab = ImageFont.truetype(FONTB, 34), ImageFont.truetype(FONTB, 22), ImageFont.truetype(FONT, 20)

ROWS = [
    ('From below, about 30 m (how players see it when the ship flies over): zones 1, 2, 3, 4, 6, 7 loaded',
     [('belly_30m_toon_before.jpg', 'before'), ('belly_30m_toon_after.jpg', 'after')]),
    ('Straight up from below (orthographic): keel girder, pipe mains, belly frames, 4 machinery bays, hoses, chains',
     [('belly_ortho_toon_before.jpg', 'before'), ('belly_ortho_toon_after.jpg', 'after')]),
    ('Low 3/4 from fore-port, about 30 m', [('q34_low_toon_before.jpg', 'before'), ('q34_low_toon_after.jpg', 'after')]),
    ('Low 3/4 from aft-starboard, about 35 m', [('q34_low_aft_toon_before.jpg', 'before'), ('q34_low_aft_toon_after.jpg', 'after')]),
    ('Belly amidships, about 6 m: bay with housing and pump, hose fitting, keel strake with padeye and chain',
     [('close_mid_toon_before.jpg', 'before'), ('close_mid_toon_after.jpg', 'after')]),
    ('Aft belly, about 6 m: both aft bays, hoses, pipe mains, aft chain',
     [('close_aft_toon_before.jpg', 'before'), ('close_aft_toon_after.jpg', 'after')]),
    ('Forward belly, about 6 m: forward chain between the front pods',
     [('close_fwd_toon_before.jpg', 'before'), ('close_fwd_toon_after.jpg', 'after')]),
    ('Seams (after): bilge line on port (zone 1 above), stern (zone 6), bow (zone 4 keel block)',
     [('seam_bilge_port_toon_after.jpg', 'bilge line, port'), ('seam_stern_toon_after.jpg', 'stern'),
      ('seam_bow_toon_after.jpg', 'bow, x 6.95')]),
    ('Clay + cavity (ambient occlusion), from below', [('belly_30m_clay_before.jpg', 'before'), ('belly_30m_clay_after.jpg', 'after')]),
    ('Clay + cavity, belly amidships', [('close_mid_clay_before.jpg', 'before'), ('close_mid_clay_after.jpg', 'after')]),
]


def cell(path, w):
    im = Image.open(os.path.join(MEDIA, path)).convert('RGB')
    return im.resize((w, int(round(im.height * w / im.width))), Image.LANCZOS)


def label(img, text, font):
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), text, font=font)
    d.rectangle((0, 0, bb[2] + 16, bb[3] + 12), fill=(20, 20, 24))
    d.text((8, 5), text, fill=(240, 240, 240), font=font)


blocks = []
for title, items in ROWS:
    items = [(f, lab) for f, lab in items if os.path.exists(os.path.join(MEDIA, f))]
    if not items:
        print('[sheet] skipped (no files):', title)
        continue
    n = len(items)
    cw = (W - PAD * (n + 1)) // n
    cells = []
    for f, lab in items:
        c = cell(f, cw)
        label(c, lab, f_lab)
        cells.append(c)
    h = max(c.height for c in cells)
    row = Image.new('RGB', (W, h + 40 + PAD), BG)
    ImageDraw.Draw(row).text((PAD, 8), title, fill=(255, 214, 120), font=f_row)
    x = PAD
    for c in cells:
        row.paste(c, (x, 40))
        x += cw + PAD
    blocks.append(row)
head = Image.new('RGB', (W, 70), BG)
ImageDraw.Draw(head).text((PAD, 14), 'Airship detail pass, zone 5 (belly and keel): before / after, final colours',
                          fill=(255, 255, 255), font=f_title)
sheet = Image.new('RGB', (W, head.height + sum(b.height for b in blocks)), BG)
y = 0
for b in [head] + blocks:
    sheet.paste(b, (0, y))
    y += b.height
# keep the sheet small: half size
sheet = sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS)
sheet.save(OUT, quality=85)
print('[sheet]', OUT, sheet.size)
