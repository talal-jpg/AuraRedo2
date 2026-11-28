"""Zone 4 (bow) before / after sheet (plain python3 + Pillow, no Blender).

  python3 -B detail_z4_sheet.py [MEDIA_DIR] [OUT.jpg]
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

MEDIA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/z4'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MEDIA, 'z4_sheet.jpg')
W, PAD, BG = 1600, 8, (36, 38, 44)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
f_title, f_row, f_lab = ImageFont.truetype(FONTB, 30), ImageFont.truetype(FONTB, 19), ImageFont.truetype(FONT, 17)

BA = lambda s: [(s + '_toon_before.jpg', 'before'), (s + '_toon_after.jpg', 'after')]
ROWS = [
    ('3/4 from bow-port, low, about 25 m (zones 1, 2, 3, 6, 7 loaded)', BA('q34_bow_p')),
    ('3/4 from bow-starboard, low', BA('q34_bow_s')),
    ('Port bow, side (orthographic): wedge plates, angle irons, bay; bow flank strake + teeth; keel block', BA('side_bow_p')),
    ('Bow head-on and from below', [('bow_head_toon_after.jpg', 'head-on, after'), ('bow_below_toon_after.jpg', 'below, after')]),
    ('Wedge, port side, about 5.5 m: machinery bay, conduit pair under the top angle, bolted rust blocks', BA('close_wedge_p')),
    ('Wedge bottom, about 5 m: two machinery bays, pipe channel, angle irons', BA('close_wedge_low')),
    ('Wedge front face: slotted armour plates, frame ribs, bolted rust blocks', BA('close_front')),
    ('Port bow flank, about 5.5 m: strake + teeth (from x 7.35), plates round the ship\'s own rust plates', BA('close_flank_bow_p')),
    ('Starboard bow flank, about 5.5 m', BA('close_flank_bow_s')),
    ('Keel block under the bow: grey plates on fitted patches, rust straps, copper pipe, keel angle', BA('close_keel_p')),
    ('Seams (after): zone 1 / zone 4 and zone 2 / zone 4 at the FL / FR pocket fore rims',
     [('seam_p_toon_after.jpg', 'port, zone 1 left'), ('seam_s_toon_after.jpg', 'starboard, zone 2 left')]),
    ('Clay + cavity (ambient occlusion)', [('q34_bow_p_clay_after.jpg', 'bow 3/4, after'),
                                           ('close_wedge_low_clay_after.jpg', 'wedge bottom, after')]),
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
    row = Image.new('RGB', (W, h + 36 + PAD), BG)
    ImageDraw.Draw(row).text((PAD, 8), title, fill=(255, 214, 120), font=f_row)
    x = PAD
    for c in cells:
        row.paste(c, (x, 36))
        x += cw + PAD
    blocks.append(row)
head = Image.new('RGB', (W, 64), BG)
ImageDraw.Draw(head).text((PAD, 14), 'Airship detail pass, zone 4 (bow): before / after, final colours',
                          fill=(255, 255, 255), font=f_title)
sheet = Image.new('RGB', (W, head.height + sum(b.height for b in blocks)), BG)
y = 0
for b in [head] + blocks:
    sheet.paste(b, (0, y))
    y += b.height
sheet.save(OUT, quality=84)
print('[sheet]', OUT, sheet.size)
