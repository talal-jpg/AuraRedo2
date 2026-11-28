"""Zone 2 contact sheet (python3 + Pillow): media/z2/z2_sheet.jpg from the renders in media/z2/ (and zone 1's approved
renders for comparison).

  python3 -B detail_z2_sheet.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

M = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/z2'
M1 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/zone1'
W = 3000
BG = (238, 236, 230)


def font(sz):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans.ttf'):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


F, FT = font(22), font(34)
ROWS = [
    ('Starboard side (orthographic): before / after', [('side_stbd_toon_before.jpg', 'before'), ('side_stbd_toon_after.jpg', 'after')]),
    ('3/4 from starboard-forward, about 25 m', [('q34_stbd_toon_before.jpg', 'before'), ('q34_stbd_toon_after.jpg', 'after'),
                                                (M1 + '/q34_toon_after.jpg', 'zone 1 (approved), port mirror')]),
    ('Starboard flank, about 5.5 m', [('close_flank_s_toon_before.jpg', 'before'), ('close_flank_s_toon_after.jpg', 'after'),
                                      (M1 + '/close_flank_toon_after.jpg', 'zone 1 (approved), port mirror')]),
    ('Front-right pod FR', [('close_pod_s_toon_before.jpg', 'before'), ('close_pod_s_toon_after.jpg', 'after'),
                            (M1 + '/close_pod_toon_after.jpg', 'zone 1 pod FL (approved)')]),
    ('Pod FR from below, and the rig limits', [('pod_low_s_toon_after.jpg', 'after'),
                                               ('pod_low_s_toon_after_poseAFR.jpg', 'pose A: pod +3/+3, nozzle -5/+5, petals +35'),
                                               ('pod_low_s_toon_after_poseBFR.jpg', 'pose B: pod -3/-3, nozzle +5/-5, petals -10'),
                                               ('close_pod_s_toon_after_poseAFR.jpg', 'pose A, close')]),
    ('FR pocket rim and the seams (Z3 aft of x -11.55, Z4 forward of x 6.95: not built yet)',
     [('pocket_f_toon_before.jpg', 'pocket, before'), ('pocket_f_toon_after.jpg', 'pocket, after'),
      ('seam_aft_s_toon_after.jpg', 'aft seam (x -11.55)'), ('seam_fwd_s_toon_after.jpg', 'fore seam (x 6.95)')]),
    ('The narrow strip over the RR pocket; clay + cavity', [('rr_strip_s_toon_after.jpg', 'strip above the RR pocket'),
                                                            ('q34_stbd_clay_after.jpg', 'clay, 25 m'),
                                                            ('close_flank_s_clay_after.jpg', 'clay, flank'),
                                                            ('close_pod_s_clay_after.jpg', 'clay, pod')]),
]


def main():
    tiles = []
    y = 70
    for title, items in ROWS:
        n = len(items)
        tw = (W - 20 * (n + 1)) // n
        th = int(tw * (1100 / 2560 if 'side_stbd' in items[0][0] else 9 / 16))
        tiles.append((y, title, items, tw, th))
        y += 40 + th + 34 + 16
    im = Image.new('RGB', (W, y + 20), BG)
    d = ImageDraw.Draw(im)
    d.text((20, 18), 'Zone 2: starboard flank + front-right pod (toon = final look). Zones 1, 6, 7 loaded; turrets placed read only.',
           fill=(20, 20, 20), font=FT)
    for (y0, title, items, tw, th) in tiles:
        d.text((20, y0 + 6), title, fill=(30, 30, 30), font=F)
        for i, (fn, lab) in enumerate(items):
            p = fn if fn.startswith('/') else os.path.join(M, fn)
            x = 20 + i * (tw + 20)
            if os.path.exists(p):
                t = Image.open(p).convert('RGB')
                t = t.resize((tw, int(t.height * tw / t.width)))
                t = t.crop((0, max(0, (t.height - th) // 2), tw, max(0, (t.height - th) // 2) + th))
                im.paste(t, (x, y0 + 40))
            else:
                d.rectangle([x, y0 + 40, x + tw, y0 + 40 + th], outline=(150, 0, 0))
            d.text((x + 4, y0 + 40 + th + 6), lab, fill=(40, 40, 40), font=F)
    out = os.path.join(M, 'z2_sheet.jpg')
    im.save(out, quality=86)
    print(out, im.size)


if __name__ == '__main__':
    main()
