# as_09_part_bounds_blender.py - Blender HEADLESS helper (not an Unreal script): per-bone vertex bounds of SK_Airship in
# Unreal component space (cm), for the physics shapes of PA_Airship (as_11) and CR_Airship (as_12).
# Opens rig/AirshipRig.blend READ-ONLY (never saved) and writes <clone>/Saved/Airship/part_bounds.json.
#   /mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/blender -b \
#     /mnt/new_partition/BlenderProjects/StylizedAirship/rig/AirshipRig.blend --python as_09_part_bounds_blender.py
# Every vertex is 100 % on one bone (README_rig.md), rest pose = base mesh coords * matrix_world.
import bpy, json, os
OUT = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/part_bounds.json'
col = bpy.data.collections.get('SK_Airship')
objs = [o for o in (col.all_objects if col else bpy.data.objects) if o.type == 'MESH']
acc = {}
for o in objs:
    mw = o.matrix_world
    names = {g.index: g.name for g in o.vertex_groups}
    for v in o.data.vertices:
        best = None
        for ge in v.groups:
            if ge.weight > 0.5:
                best = names.get(ge.group)
        if best is None:
            continue
        w = mw @ v.co
        p = (100.0 * w.x, -100.0 * w.y, 100.0 * w.z)
        a = acc.setdefault(best, {'n': 0, 'min': [1e9] * 3, 'max': [-1e9] * 3, 'sum': [0.0] * 3})
        a['n'] += 1
        for i in range(3):
            a['min'][i] = min(a['min'][i], p[i])
            a['max'][i] = max(a['max'][i], p[i])
            a['sum'][i] += p[i]
out = {}
for b, a in sorted(acc.items()):
    out[b] = {'n': a['n'], 'min': [round(x, 2) for x in a['min']], 'max': [round(x, 2) for x in a['max']],
              'centroid': [round(s / a['n'], 2) for s in a['sum']],
              'centre': [round(0.5 * (a['min'][i] + a['max'][i]), 2) for i in range(3)],
              'size': [round(a['max'][i] - a['min'][i], 2) for i in range(3)]}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w') as f:
    json.dump({'source': bpy.data.filepath, 'objects': len(objs), 'space': 'UE component cm (100x,-100y,100z)',
               'bones': out}, f, indent=1)
print('PART_BOUNDS bones=%d objects=%d -> %s' % (len(out), len(objs), OUT))
