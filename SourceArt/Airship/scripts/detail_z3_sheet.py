"""Zone 3 before / after sheet (plain python3 + Pillow, no Blender).

  python3 -B detail_z3_sheet.py [MEDIA_DIR] [OUT.jpg]
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

MEDIA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/z3'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MEDIA, 'z3_sheet.jpg')
W, PAD, BG = 1920, 8, (36, 38, 44)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
f_title, f_row, f_lab = ImageFont.truetype(FONTB, 34), ImageFont.truetype(FONTB, 22), ImageFont.truetype(FONT, 20)

ROWS = [
    ('3/4 from aft-port, low, about 25 m: aft port flank, rear-left pod RL (zones 1, 2, 6, 7 loaded)',
     [('q34_aft_port_toon_before.jpg', 'before'), ('q34_aft_port_toon_after.jpg', 'after')]),
    ('3/4 from aft-starboard: aft starboard flank, rear-right pod RR',
     [('q34_aft_stbd_toon_before.jpg', 'before'), ('q34_aft_stbd_toon_after.jpg', 'after')]),
    ('Port aft flank, side (orthographic): strake + teeth, pipe channel, machinery bay, end ribs',
     [('side_aft_toon_before.jpg', 'before'), ('side_aft_toon_after.jpg', 'after')]),
    ('Starboard aft flank, side (orthographic)',
     [('side_aft_stbd_toon_before.jpg', 'before'), ('side_aft_stbd_toon_after.jpg', 'after')]),
    ('Port aft flank, about 5.7 m', [('close_aft_flank_toon_before.jpg', 'before'), ('close_aft_flank_toon_after.jpg', 'after')]),
    ('Starboard aft flank, about 5.7 m', [('close_aft_flank_stbd_toon_before.jpg', 'before'),
                                          ('close_aft_flank_stbd_toon_after.jpg', 'after')]),
    ('Rear-left pod RL from aft: hug pipes and actuators on the aft side, drum plates, nozzle hoops',
     [('close_rear_pod_toon_before.jpg', 'before'), ('close_rear_pod_toon_after.jpg', 'after')]),
    ('Rear-right pod RR from aft', [('close_rear_pod_stbd_toon_before.jpg', 'before'),
                                    ('close_rear_pod_stbd_toon_after.jpg', 'after')]),
    ('Both rear pods from below and aft', [('rear_pods_below_toon_before.jpg', 'before'), ('rear_pods_below_toon_after.jpg', 'after')]),
    ('After: RL front plates (lips, patches, straps) and the RL pocket (wall stiffeners, rust lip on the opening edge)',
     [('rear_pod_front_toon_after.jpg', 'RL from fore-port'), ('pocket_RL_toon_after.jpg', 'RL pocket')]),
    ('Seams (after): zone 1 / zone 3, zone 2 / zone 3 at x -11.55, and the aft end by the fan mount (zone 6)',
     [('seam_z1z3_toon_after.jpg', 'port seam, zone 1 left'), ('seam_z2z3_toon_after.jpg', 'starboard seam, zone 2 right'),
      ('seam_z3z6_toon_after.jpg', 'aft end, end rib')]),
    ('Rig limits, RL: A = pod +3 / +3, nozzle -5 / +5, petals open +35; B = pod -3 / -3, nozzle +5 / -5, petals -10',
     [('close_rear_pod_toon_after_poseARL.jpg', 'pose A'), ('close_rear_pod_toon_after_poseBRL.jpg', 'pose B')]),
    ('Clay + cavity (ambient occlusion)', [('q34_aft_port_clay_before.jpg', 'before'), ('q34_aft_port_clay_after.jpg', 'after')]),
    ('Clay + cavity, port aft flank', [('close_aft_flank_clay_before.jpg', 'before'), ('close_aft_flank_clay_after.jpg', 'after')]),
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
ImageDraw.Draw(head).text((PAD, 14), 'Airship detail pass, zone 3 (aft flanks, rear pods RL / RR): before / after, final colours',
                          fill=(255, 255, 255), font=f_title)
sheet = Image.new('RGB', (W, head.height + sum(b.height for b in blocks)), BG)
y = 0
for b in [head] + blocks:
    sheet.paste(b, (0, y))
    y += b.height
sheet.save(OUT, quality=86)
print('[sheet]', OUT, sheet.size)
