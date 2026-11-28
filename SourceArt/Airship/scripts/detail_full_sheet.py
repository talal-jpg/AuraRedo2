"""Whole-ship before / after sheet of the round 3 detail pass (plain python3 + Pillow, no Blender).

  python3 -B detail_full_sheet.py [MEDIA_DIR] [OUT.jpg]

Reads the renders of `detail_assemble.py --tool render` (<shot>_<look>_<state>.jpg in Docs/Airship/round3/media/full)
and writes one labelled sheet (full_sheet.jpg).
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

MEDIA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/full'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MEDIA, 'full_sheet.jpg')
W = 1920
PAD = 8
BG = (36, 38, 44)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
f_title = ImageFont.truetype(FONTB, 32)
f_sub = ImageFont.truetype(FONT, 20)
f_row = ImageFont.truetype(FONTB, 22)
f_lab = ImageFont.truetype(FONT, 20)


def pair(shot, look='toon'):
    return [('%s_%s_before.jpg' % (shot, look), 'before'), ('%s_%s_after.jpg' % (shot, look), 'after')]


ROWS = [
    ('Port side, orthographic', pair('side')),
    ('Starboard side, orthographic', pair('side_stbd')),
    ('Top, orthographic', pair('top')),
    ('3/4 from front-port, about 31 m (turrets at their mounts)', pair('q34_fp')),
    ('3/4 from rear-starboard, about 30 m', pair('q34_rs')),
    ('From behind at your fan screenshot angle: the fan backs are open, the blades show (answer 4)', pair('talal_back')),
    ('Chase camera, about 45 m behind and 15 deg down (the view you fly with)', pair('pilot_45')),
    ('Chase camera swung 30 deg to port, about 45 m', pair('pilot_45q')),
    ('Stern straight from behind, about 15 m: the transom between the fans', pair('transom_rear')),
    ('From below, about 27 m', pair('below')),
    ('Belly from port, a little below: frames end on the bilge stringer, short heavy hoses', pair('belly_port')),
    ('On the main deck at eye height, looking at the new stairs to the turret deck (answer 3)', pair('deck_eye')),
    ('Close-ups, about 4-5 m: the stairs\' landing (steel hand rails), the port fan\'s exhaust (blade collar, tip caps)',
     [('stairs_close_toon_after.jpg', 'stairs, after'), ('fan_close_L_toon_after.jpg', 'port fan exhaust, after')]),
    ('Keel block under the bow, from below port: rust since your answer of 2026-11-28', pair('keel_low')),
    ('Clay + cavity (ambient occlusion), 3/4 from front-port', pair('q34_fp', 'clay')),
    ('Clay + cavity (ambient occlusion), from below', pair('below', 'clay')),
]


def cell(path, w):
    im = Image.open(os.path.join(MEDIA, path)).convert('RGB')
    h = int(round(im.height * w / im.width))
    return im.resize((w, h), Image.LANCZOS)


def label(img, text, font):
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), text, font=font)
    d.rectangle((0, 0, bb[2] + 16, bb[3] + 12), fill=(20, 20, 24))
    d.text((8, 5), text, fill=(240, 240, 240), font=font)


blocks = []
missing = []
for title, items in ROWS:
    items = [(f, l) for f, l in items if os.path.exists(os.path.join(MEDIA, f)) or missing.append(f)]
    if not items:
        continue
    n = 2
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
head = Image.new('RGB', (W, 96), BG)
d = ImageDraw.Draw(head)
d.text((PAD, 10), 'Airship detail pass, round 3: the whole ship, before / after (review fixes + your 3 answers)',
       fill=(255, 255, 255), font=f_title)
d.text((PAD, 58), 'Final look = reference 1\'s yellow and rust (toon preview). All seven zones, open fan backs, stairs; '
                  'keel block rust, blade collar + tip caps, steel hand rails (2026-11-28).', fill=(200, 200, 200),
       font=f_sub)
H = head.height + sum(b.height for b in blocks)
sheet = Image.new('RGB', (W, H), BG)
y = 0
for b in [head] + blocks:
    sheet.paste(b, (0, y))
    y += b.height
sheet.save(OUT, quality=86)
print('[sheet]', OUT, sheet.size, 'missing', missing)
