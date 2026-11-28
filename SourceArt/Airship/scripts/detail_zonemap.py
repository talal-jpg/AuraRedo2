"""Zone map render (round 3): the ship coloured by owning zone (detail_zones.py), port, starboard, top and bottom.

  blender_capped.sh --python detail_zonemap.py -- [--out DIR] [--scale 60]
  python3 -B detail_zonemap.py --sheet DIR OUT.jpg            # (plain python3 + Pillow) labelled 2 x 2 sheet

Opens rig/AirshipRig.blend (never saved), appends zone 1's details (coloured as Z1) and the two turrets, draws the open
space volumes of VOLUMES (stairs box, fan backs) as wire boxes in their zone's colour and the KEEP_CLEAR volumes in dark
grey. Writes zonemap_<view>.jpg, zonemap_marks.json (where the boundary lines fall in each image) and
zone_faces.json (per zone: SM_Airship faces and area).
"""
import sys, os, json, math

COLOURS = {   # zone -> (r, g, b) linear, for the map only
    'Z1': (0.95, 0.55, 0.12), 'Z2': (0.20, 0.45, 0.95), 'Z3': (0.25, 0.70, 0.25), 'Z4': (0.90, 0.18, 0.18),
    'Z5': (0.55, 0.30, 0.85), 'Z6': (0.10, 0.75, 0.75), 'Z7': (0.95, 0.40, 0.75), 'none': (0.80, 0.78, 0.74),
}
VIEWS = ('side', 'side_stbd', 'top', 'bottom')


def blender_main():
    import bpy
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import numpy as np
    from mathutils import Vector as V
    from bpy_extras.object_utils import world_to_camera_view
    import rig_common as C
    import detail_common as D
    import detail_ship as S
    import detail_zones as Z
    import detail_render as R
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = a[a.index('--out') + 1] if '--out' in a else '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/zones'
    scale = int(a[a.index('--scale') + 1]) if '--scale' in a else 60
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    sc, cam = R.base_scene()
    arm = bpy.data.objects['Armature']
    D.append_zone(1, arm)
    R.add_turrets()
    ship = S.Ship(bpy)
    zi = Z.ZoneIndex(ship)
    D_ = zi.summary()
    why = {}
    for z, w in zip(zi.zone, zi.why):
        why.setdefault(z, {}).setdefault(w, 0)
        why[z][w] += 1
    C.dump_json(dict(zones=D_, rules=why, about='SM_Airship faces per owning zone (detail_zones.face_zones)'),
                os.path.join(out, 'zone_faces.json'))
    mats = {z: R.toon_material('MZ_' + z, c) for z, c in COLOURS.items()}
    dark = R.toon_material('MZ_dark', (0.18, 0.18, 0.2))
    me = ship.ob.data
    me.materials.clear()
    order = list(COLOURS)
    for z in order:
        me.materials.append(mats[z])
    me.polygons.foreach_set('material_index', np.array([order.index(z) for z in zi.zone], np.int32))
    me.update()
    z1light = R.toon_material('MZ_Z1_details', (1.0, 0.78, 0.45))
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob == ship.ob:
            continue
        if ob.name.startswith('SM_AirshipDetail_Z1_'):
            ob.data.materials.clear(); ob.data.materials.append(z1light)
        else:
            ob.data.materials.clear(); ob.data.materials.append(dark)
    # volumes as wire boxes
    coll = bpy.data.collections.new('ZoneVolumes')
    sc.collection.children.link(coll)

    def wire(name, verts, faces, mat):
        m = bpy.data.meshes.new(name)
        m.from_pydata(verts, [], faces)
        o = bpy.data.objects.new(name, m)
        coll.objects.link(o)
        w = o.modifiers.new('W', 'WIREFRAME'); w.thickness = 0.06
        m.materials.append(mat)
        return o

    def box(prm):
        x0, x1, y0, y1, z0, z1 = prm
        v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        return v, f

    def cyl(axis, prm, k=24):
        if axis == 'x':
            x0, x1, cy, cz, r = prm
            ring = lambda x: [(x, cy + r * math.cos(2 * math.pi * i / k), cz + r * math.sin(2 * math.pi * i / k)) for i in range(k)]
            v = ring(x0) + ring(x1)
        else:
            cx, cy, r, z0, z1 = prm
            ring = lambda z: [(cx + r * math.cos(2 * math.pi * i / k), cy + r * math.sin(2 * math.pi * i / k), z) for i in range(k)]
            v = ring(z0) + ring(z1)
        f = [(i, (i + 1) % k, k + (i + 1) % k, k + i) for i in range(k)]
        return v, f
    for i, (z, kind, prm, _) in enumerate(Z.VOLUMES):
        v, f = box(prm) if kind == 'box' else cyl('x', prm)
        wire('Vol_%d_%s' % (i, z), v, f, mats[z])
    for name, kind, prm, _ in Z.KEEP_CLEAR:
        if kind == 'cyl_z':
            v, f = cyl('z', prm)
        else:
            cx, cy, cz, r = prm
            v, f = cyl('z', (cx, cy, r, cz, cz + r))
        wire('Keep_' + name, v, f, dark)
    R.toon_world(sc)
    R.ink_lines(sc, 2.0, 1.0, R.INK, material_boundary=True)
    sc.render.resolution_percentage = scale
    marks = {}
    pts = {'x_aft_-11.55': (Z.X_AFT, 9.0, -1.0), 'x_fwd_6.95': (Z.X_FWD, 9.0, -1.0), 'transom_-15.0': (Z.TRANSOM_X, 9.0, -1.0)}
    for vname in VIEWS:
        R.set_shot(sc, cam, vname)
        bpy.context.view_layer.update()
        mk = {}
        for k, p in pts.items():
            for yz in ((9.0, -1.0), (-9.0, -1.0), (0.0, 9.0), (0.0, -9.0)):
                q = world_to_camera_view(sc, cam, V((p[0],) + yz))
                mk.setdefault(k, []).append([round(q.x, 4), round(1 - q.y, 4)])
        marks[vname] = mk
        sc.render.filepath = os.path.join(out, 'zonemap_%s.jpg' % vname)
        bpy.ops.render.render(write_still=True)
        print('[zonemap]', sc.render.filepath)
    C.dump_json(marks, os.path.join(out, 'zonemap_marks.json'))
    print('[zonemap] zones', json.dumps(D_))


def sheet(media, out):
    from PIL import Image, ImageDraw, ImageFont
    FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    ft, fl, fs = ImageFont.truetype(FONTB, 30), ImageFont.truetype(FONTB, 22), ImageFont.truetype(FONT, 19)
    marks = json.load(open(os.path.join(media, 'zonemap_marks.json')))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    titles = {'side': 'Port side (bow to the left)', 'side_stbd': 'Starboard side (bow to the right)',
              'top': 'Top (bow to the right, port up)', 'bottom': 'Bottom (bow to the right)'}
    ims = []
    for v in VIEWS:
        im = Image.open(os.path.join(media, 'zonemap_%s.jpg' % v)).convert('RGB')
        d = ImageDraw.Draw(im)
        W, H = im.size
        mk = marks[v]
        for j, (k, lst) in enumerate(mk.items()):
            xs = [p[0] * W for p in lst]
            x = sum(xs) / len(xs)
            if not (0 < x < W):
                continue
            for y in range(0, H, 22):
                d.line([(x, y), (x, y + 11)], fill=(20, 20, 30), width=2)
            d.text((x + 5, 8 + 24 * j), k.replace('_', ' '), font=fs, fill=(20, 20, 30))
        d.text((12, H - 34), titles[v], font=fl, fill=(20, 20, 30))
        ims.append(im)
    w, h = ims[0].size
    leg_h = 330
    S_ = Image.new('RGB', (2 * w + 30, 2 * h + 90 + leg_h), (236, 236, 232))
    d = ImageDraw.Draw(S_)
    d.text((14, 12), 'Round 3 detail zones (detail_zones.py): SM_Airship coloured by owning zone; light orange = zone 1 '
                     'details (approved); wire boxes = open-space volumes; dark wire = keep-clear', font=ft, fill=(20, 20, 30))
    for i, im in enumerate(ims):
        S_.paste(im, (10 + (i % 2) * (w + 10), 60 + (i // 2) * (h + 10)))
    import detail_zones as Z
    y0 = 70 + 2 * (h + 10)
    for i, z in enumerate(list(Z.ZONES) + ['none']):
        col = tuple(int(255 * min(1, c ** (1 / 2.2))) for c in COLOURS[z])
        x = 20 + (i % 2) * (S_.size[0] // 2)
        y = y0 + (i // 2) * 72
        d.rectangle([x, y, x + 40, y + 40], fill=col, outline=(20, 20, 30))
        txt = Z.ZONES.get(z, 'nobody: deck planks and walkable tops, deck props (stay plain)')
        d.text((x + 52, y), z, font=fl, fill=(20, 20, 30))
        # wrap the description
        words, line, yy = txt.split(), '', y + 26
        for wd in words:
            if d.textlength(line + ' ' + wd, font=fs) > S_.size[0] // 2 - 110:
                d.text((x + 52, yy), line, font=fs, fill=(40, 40, 50)); yy += 21; line = wd
            else:
                line = (line + ' ' + wd).strip()
        d.text((x + 52, yy), line, font=fs, fill=(40, 40, 50))
    S_.save(out, quality=90)
    print('[zonemap] sheet', out, S_.size)


if __name__ == '__main__':
    if '--sheet' in sys.argv:
        i = sys.argv.index('--sheet')
        sheet(sys.argv[i + 1], sys.argv[i + 2])
    else:
        blender_main()
