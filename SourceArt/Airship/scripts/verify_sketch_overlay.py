"""Overlay Talal's green marks (and a faint copy of his sketch) on the renders from the solved sketch cameras.
  python3 rig/scripts/verify_sketch_overlay.py   (system python with PIL)"""
from PIL import Image, ImageChops
S = '/mnt/new_partition/UnrealProjects/_AirshipWork_logs/talal_sketches/'
O = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/renders/verify/'
import os
for key, rname in [('3_cannon_spots', '3_cannon_spots'), ('2_steering_wheel_spot', '2_steering_wheel_spot'),
                   ('3_cannon_spots', '3_cannon_spots_ghost')]:
    if not os.path.exists(O + 'sketchcam_' + rname + '.png'):
        continue
    sk = Image.open(S + key + '.png').convert('RGB')
    rd = Image.open(O + 'sketchcam_' + rname + '.png').convert('RGB')
    blend = Image.blend(rd, sk, 0.45)
    px = sk.load(); out = blend.copy(); po = out.load(); pr = rd.copy(); pp = pr.load()
    for y in range(sk.size[1]):
        for x in range(sk.size[0]):
            r, g, b = px[x, y]
            if g > 180 and r < 120 and b < 120:      # Talal's green marks
                po[x, y] = (0, 255, 0); pp[x, y] = (0, 255, 0)
    out.save(O + 'overlay_blend_' + rname + '.png')
    pr.save(O + 'overlay_marks_' + rname + '.png')
    # 2x close-ups around the marks (deck between the bow gantry and the fans)
    box = (400, 150, 1050, 362) if key.startswith('3_') else (560, 170, 1060, 380)
    for img, nm in ((pr, 'overlay_marks_'), (out, 'overlay_blend_')):
        z = img.crop(box); z = z.resize((z.size[0] * 2, z.size[1] * 2), Image.LANCZOS)
        z.save(O + nm + rname + '_zoom.png')
    print('wrote', O + 'overlay_*_' + rname + '.png')
