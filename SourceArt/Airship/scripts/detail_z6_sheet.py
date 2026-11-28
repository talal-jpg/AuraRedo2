"""Zone 6 before / after sheet (plain python3 + Pillow, no Blender).

  python3 -B detail_z6_sheet.py [MEDIA_DIR] [OUT.jpg]
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

MEDIA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/z6'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(MEDIA, 'z6_sheet.jpg')
W, PAD, BG = 1920, 8, (36, 38, 44)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
f_title, f_row, f_lab = ImageFont.truetype(FONTB, 34), ImageFont.truetype(FONTB, 22), ImageFont.truetype(FONT, 20)

ROWS = [
    ('Your screenshot angle: behind-port, above the deck, looking forward at both fans (fan backs now open)',
     [('talal_back_toon_before.jpg', 'before'), ('talal_back_toon_after.jpg', 'after')]),
    ('Straight from behind, both fans: blades visible through the open exhausts',
     [('stern_toon_before.jpg', 'before'), ('stern_toon_after.jpg', 'after')]),
    ('Port fan straight from behind: rust exhaust rim, dark liner, 5-strut stator, bearing hub with a short tail cone',
     [('back_L_toon_before.jpg', 'before'), ('back_L_toon_after.jpg', 'after')]),
    ('Port fan from the side: plate rows, front rim band, gimbal track, two machinery bays',
     [('side_L_toon_before.jpg', 'before'), ('side_L_toon_after.jpg', 'after')]),
    ('Stern 3/4 from aft-port, high', [('q34_aft_hi_toon_before.jpg', 'before'), ('q34_aft_hi_toon_after.jpg', 'after')]),
    ('Transom between the port fan and the rudder', [('transom_close_toon_before.jpg', 'before'),
                                                    ('transom_close_toon_after.jpg', 'after')]),
    ('Close-ups (after)', [('fan_close_L_toon_after.jpg', 'port fan exhaust, 5 m'), ('fan_low_L_toon_after.jpg', 'port fan from below'),
                           ('fan_front_L_toon_after.jpg', 'port fan intake side')]),
    ('Close-ups (after)', [('rudder_close_toon_after.jpg', 'rudder'), ('back_R_toon_after.jpg', 'starboard fan from behind')]),
    ('Rig limits (after): A = fan yaw L +12 / R -12, rudder +30, rods swung +20; B = yaw L -12 / R +12, rudder -30, rods -20',
     [('talal_back_toon_after_pose_poseA.jpg', 'pose A'), ('talal_back_toon_after_pose_poseB.jpg', 'pose B')]),
    ('Rig limits, port fan from behind', [('back_L_toon_after_pose_poseA.jpg', 'pose A'), ('back_L_toon_after_pose_poseB.jpg', 'pose B')]),
    ('Clay + cavity (ambient occlusion)', [('talal_back_clay_before.jpg', 'before'), ('talal_back_clay_after.jpg', 'after')]),
    ('Clay + cavity, port fan from behind', [('back_L_clay_before.jpg', 'before'), ('back_L_clay_after.jpg', 'after')]),
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
ImageDraw.Draw(head).text((PAD, 14), 'Airship detail pass, zone 6 (stern and fans, open fan backs): before / after, final colours',
                          fill=(255, 255, 255), font=f_title)
sheet = Image.new('RGB', (W, head.height + sum(b.height for b in blocks)), BG)
y = 0
for b in [head] + blocks:
    sheet.paste(b, (0, y))
    y += b.height
sheet.save(OUT, quality=86)
print('[sheet]', OUT, sheet.size)
