"""Docs/Airship/round2/media/deck_ink_before_after.jpg from hull_ink_render.py's renders (plain python3 + Pillow):
top view before | after, then the forward and aft perspective views, before above after.

  python3 -B SourceArt/Airship/scripts/hull_ink_media.py
"""
import os
from PIL import Image, ImageDraw

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/renders/hull_ink'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../Docs/Airship/round2/media/deck_ink_before_after.jpg')
GAP, BG = 8, (40, 40, 46)


def tile(path, w, label):
    im = Image.open(path).convert('RGB')
    im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    tw = int(d.textlength(label)) + 16
    d.rectangle((0, 0, tw, 22), fill=(18, 18, 24))
    d.text((8, 5), label, fill=(235, 235, 235))
    return im


top_b = tile(RIG + '/before_top.png', 489, "before: Talal's hull texture")
top_a = tile(RIG + '/after_top.png', 489, 'after: T_AirshipDrivable_ComicLines')
per = [[tile(RIG + '/before_persp_fwd.png', 700, 'before (forward deck)'),
        tile(RIG + '/after_persp_fwd.png', 700, 'after (forward deck)')],
       [tile(RIG + '/before_persp_aft.png', 700, 'before (main deck)'),
        tile(RIG + '/after_persp_aft.png', 700, 'after (main deck)')]]
H = max(top_b.height, per[0][0].height * 2 + GAP)
W = top_b.width * 2 + GAP * 2 + 700 * 2 + GAP
sheet = Image.new('RGB', (W, H), BG)
sheet.paste(top_b, (0, 0))
sheet.paste(top_a, (top_b.width + GAP, 0))
x0 = top_b.width * 2 + GAP * 2
for col, (b, a) in enumerate(per):
    sheet.paste(b, (x0 + col * (700 + GAP), 0))
    sheet.paste(a, (x0 + col * (700 + GAP), b.height + GAP))
OUT = os.path.normpath(OUT)
sheet.save(OUT, quality=88)
print('wrote', OUT, sheet.size)
