"""Combined before / after sheet of a detail zone (plain python3 + Pillow, no Blender).

  python3 -B detail_sheet.py [MEDIA_DIR] [OUT.jpg]

Reads the renders of detail_render.py (<shot>_<look>_<state>[_<pose>].jpg) and writes one labelled sheet.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

MEDIA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/zone1'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MEDIA, 'zone1_sheet.jpg')
W = 1920
PAD = 8
BG = (36, 38, 44)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
f_title = ImageFont.truetype(FONTB, 34)
f_row = ImageFont.truetype(FONTB, 22)
f_lab = ImageFont.truetype(FONT, 20)

ROWS = [
    ('Whole port side, same camera (zone 1 = flank between the two port cannons + the front-left pod)',
     [('side_toon_before.jpg', 'before'), ('side_toon_after.jpg', 'after')]),
    ('3/4 low from port-forward, about 25 m (gameplay ship camera distance), reference 1 palette + ink',
     [('q34_toon_before.jpg', 'before'), ('q34_toon_after.jpg', 'after')]),
    ('Hull flank at about 5.5 m (what a player on a platform sees)',
     [('close_flank_toon_before.jpg', 'before'), ('close_flank_toon_after.jpg', 'after')]),
    ('Front-left thruster pod at about 5.5 m',
     [('close_pod_toon_before.jpg', 'before'), ('close_pod_toon_after.jpg', 'after')]),
    ('In-game look: paper white, navy ink (heavy outline, thin creases, no ink on rivets), 25 m',
     [('q34_paper_before.jpg', 'before'), ('q34_paper_after.jpg', 'after')]),
    ('In-game look, hull flank 5.5 m', [('close_flank_paper_before.jpg', 'before'), ('close_flank_paper_after.jpg', 'after')]),
    ('Clay + cavity (ambient occlusion), 25 m', [('q34_clay_before.jpg', 'before'), ('q34_clay_after.jpg', 'after')]),
    ('Clay + cavity, hull flank 5.5 m', [('close_flank_clay_before.jpg', 'before'), ('close_flank_clay_after.jpg', 'after')]),
    ('Clay + cavity, pod 5.5 m', [('close_pod_clay_before.jpg', 'before'), ('close_pod_clay_after.jpg', 'after')]),
    ('Rig check: pod, nozzle and petals at their limits (no new contacts in 243 poses)',
     [('pod_low_toon_after.jpg', 'rest'),
      ('pod_low_toon_after_poseA.jpg', 'pod +3/+3, nozzle -5/+5, petals open +35'),
      ('pod_low_toon_after_poseB.jpg', 'pod -3/-3, nozzle +5/-5, petals closed -10')]),
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
for title, items in ROWS:
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
ImageDraw.Draw(head).text((PAD, 14), 'Airship detail pass, zone 1 (pass 2): before / after (preview colours, final look = texture bake)',
                          fill=(255, 255, 255), font=f_title)
H = head.height + sum(b.height for b in blocks)
sheet = Image.new('RGB', (W, H), BG)
y = 0
for b in [head] + blocks:
    sheet.paste(b, (0, y))
    y += b.height
sheet.save(OUT, quality=88)
print('[sheet]', OUT, sheet.size)
