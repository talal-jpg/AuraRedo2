"""Zone 7 contact sheet (python3 + Pillow): media/z7/z7_sheet.jpg from the renders in media/z7/.

  python3 -B detail_z7_sheet.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

M = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/z7'
W = 3000
BG = (238, 236, 230)


def font(sz):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans.ttf'):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


F, FT = font(22), font(34)
ROWS = [
    ('Gantry, port side (orthographic)', [('side_gantry_toon_before.jpg', 'before'), ('side_gantry_toon_after.jpg', 'after')]),
    ('Stairs (Talal point 3): 25 m 3/4 and eye height 1.6 m on the main deck',
     [('stairs_q34p_toon_before.jpg', 'before, 25 m'), ('stairs_q34p_toon_after.jpg', 'after, 25 m'),
      ('stairs_eye_toon_before.jpg', 'before, eye height'), ('stairs_eye_toon_after.jpg', 'after, eye height')]),
    ('Stairs close-ups', [('stairs_eye2_toon_after.jpg', 'from starboard aft'), ('stairs_close_toon_after.jpg', 'landing, 4 m'),
                          ('stairs_top_toon_after.jpg', 'from the turret deck'), ('stairs_q34s_toon_after.jpg', 'starboard 3/4, 25 m')]),
    ('Placement options that were mocked (simple boxes): chosen = central',
     [('stairs_options/eye_toon_after_central.jpg', 'central (chosen)'), ('stairs_options/q34p_toon_after_central.jpg', 'central'),
      ('stairs_options/q34p_toon_after_port.jpg', 'port side'), ('stairs_options/q34p_toon_after_across.jpg', 'across the aft face')]),
    ('Forward deck and truss', [('foredeck_toon_before.jpg', 'before'), ('foredeck_toon_after.jpg', 'after'),
                                ('truss_toon_before.jpg', 'truss before, 5.8 m'), ('truss_toon_after.jpg', 'truss after, 5.8 m')]),
    ('Under the turret deck, bow 3/4', [('under_toon_before.jpg', 'underside before'), ('under_toon_after.jpg', 'underside after'),
                                        ('q34_bow_toon_before.jpg', 'bow 3/4 before'), ('q34_bow_toon_after.jpg', 'bow 3/4 after')]),
    ('Search lights, winches, legs, chain', [('light_toon_after.jpg', 'search light AftL'),
                                             ('light_toon_after_pose_lights_pan90_wobble4.jpg', 'pan 90, wobble 4/-4'),
                                             ('winch_toon_after.jpg', 'winch bearings'), ('legs_toon_after.jpg', 'legs, pumps, heavy chain')]),
    ('More', [('truss_fwd_toon_after.jpg', 'fore deck wall, winch rope'), ('fwd_deck_toon_after.jpg', 'turret deck from aft'),
              ('rails_toon_after.jpg', 'main deck rails: rust collars'),
              ('foredeck_toon_after_pose_lights_pan90_wobble4.jpg', 'lights posed')]),
]


def main():
    tiles = []
    y = 70
    for title, items in ROWS:
        n = len(items)
        tw = (W - 20 * (n + 1)) // n
        th = int(tw * (900 / 2400 if 'side_gantry' in items[0][0] else 9 / 16))
        tiles.append((y, title, items, tw, th))
        y += 40 + th + 34 + 16
    im = Image.new('RGB', (W, y + 20), BG)
    d = ImageDraw.Draw(im)
    d.text((20, 18), 'Zone 7: gantry, turret deck and stairs (toon = final look). Zone 1 loaded; turrets placed read only.',
           fill=(20, 20, 20), font=FT)
    for (y0, title, items, tw, th) in tiles:
        d.text((20, y0 + 6), title, fill=(30, 30, 30), font=F)
        for i, (fn, lab) in enumerate(items):
            p = os.path.join(M, fn)
            x = 20 + i * (tw + 20)
            if os.path.exists(p):
                t = Image.open(p).convert('RGB')
                t = t.resize((tw, int(t.height * tw / t.width)))
                t = t.crop((0, max(0, (t.height - th) // 2), tw, max(0, (t.height - th) // 2) + th))
                im.paste(t, (x, y0 + 40))
            else:
                d.rectangle([x, y0 + 40, x + tw, y0 + 40 + th], outline=(150, 0, 0))
            d.text((x + 4, y0 + 40 + th + 6), lab, fill=(40, 40, 40), font=F)
    out = os.path.join(M, 'z7_sheet.jpg')
    im.save(out, quality=86)
    print(out, im.size)


if __name__ == '__main__':
    main()
