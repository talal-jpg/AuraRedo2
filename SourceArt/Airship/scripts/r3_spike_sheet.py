"""Round 3 export spike sheets (plain python3 + Pillow, no Blender).

  python3 -B r3_spike_sheet.py [SPIKE_DIR] [OUT_DIR]

Reads the renders of r3_spike.py (rig/detail/r3export/spike/<tag>/) and the approved zone 1 toon renders
(Docs/Airship/round3/media/zone1/) and writes Docs/Airship/round3/media/export/spike_*.jpg:
  spike_close_flank.jpg  approved toon | chosen bake, lit | chosen bake, flat (the texture alone) | chosen, LOD1 (dots)
  spike_q34.jpg          approved toon | chosen bake, lit
  spike_ink_methods.jpg  his comic shader on details (B) | + his shader re-baked on the hull (C) | distance-field lines (I)
  spike_side.jpg         approved toon side | chosen bake side (orthographic, whole ship, zone 1 details only)
  spike_chase.jpg        default chase camera (65 m, FOV 85 deg): chosen bake LOD0 | LOD1, 1:1 crops
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

SPIKE = sys.argv[1] if len(sys.argv) > 1 else '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/r3export/spike'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/export'
Z1 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/zone1'
CHOSEN = 'I'
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 22)
BG = (36, 38, 44)


def tile(path, w, h, label, crop=None):
    im = Image.open(path).convert('RGB')
    if crop:
        im = im.crop(crop)
    im = im.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    tw = d.textlength(label, font=FONT)
    d.rectangle((0, 0, tw + 16, 34), fill=(20, 22, 28))
    d.text((8, 5), label, fill=(240, 240, 240), font=FONT)
    return im


def sheet(tiles, cols, name):
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    s = Image.new('RGB', (cols * w + (cols + 1) * 6, rows * h + (rows + 1) * 6), BG)
    for k, t in enumerate(tiles):
        s.paste(t, (6 + (k % cols) * (w + 6), 6 + (k // cols) * (h + 6)))
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    s.save(p, quality=90)
    print('wrote', p, s.size)


c = os.path.join(SPIKE, CHOSEN)
sheet([tile(Z1 + '/close_flank_toon_after.jpg', 960, 540, 'approved toon (zone 1)'),
       tile(c + '/close_flank_lit.jpg', 960, 540, 'bake: palette + ink distance field, lit'),
       tile(c + '/close_flank_flat.jpg', 960, 540, 'the same, unlit (texture + palette only)'),
       tile(c + '/close_flank_lit_lod1.jpg', 960, 540, 'LOD1: no rivet geometry, baked dots')], 2, 'spike_close_flank.jpg')
sheet([tile(Z1 + '/q34_toon_after.jpg', 960, 540, 'approved toon (zone 1)'),
       tile(c + '/q34_lit.jpg', 960, 540, 'bake, lit (props: in-game paper look)')], 2, 'spike_q34.jpg')
sheet([tile(os.path.join(SPIKE, 'B', 'close_flank_lit.jpg'), 960, 540, 'A: his comic shader on details, his hull ink'),
       tile(os.path.join(SPIKE, 'C', 'close_flank_lit.jpg'), 960, 540, 'B: + hull re-baked, no hatching'),
       tile(c + '/close_flank_lit.jpg', 960, 540, 'C (chosen): geometric lines, distance field'),
       tile(Z1 + '/close_flank_toon_after.jpg', 960, 540, 'approved toon')], 2, 'spike_ink_methods.jpg')
sheet([tile(Z1 + '/side_toon_after.jpg', 1280, 550, 'approved toon side'),
       tile(c + '/side_lit.jpg', 1280, 550, 'bake, lit (zone 1 details only)')], 1, 'spike_side.jpg')
sheet([tile(c + '/chase65_lit.jpg', 900, 690, 'chase camera 65 m, FOV 85: LOD0 (1:1 crop)', crop=(780, 270, 1380, 730)),
       tile(c + '/chase65_lit_lod1.jpg', 900, 690, 'LOD1 (rivet dots), same crop', crop=(780, 270, 1380, 730))], 2,
      'spike_chase.jpg')
