# as_11a_hull_survey_blender.py - Blender HEADLESS helper (not an Unreal script) for PA_Airship's hull boxes (as_11b -> as_11):
# a column survey of the Hull-skinned faces of SK_Airship (the round-2 rig: the five removed deck pieces are gone) on a
# 25 cm grid in Unreal component space (cm). Per cell: every hit of a ray going straight down from above the ship (any
# face normal), top down, as [z, normal z]. Also the ChainFwd vertices (its body is built from them in as_11b).
# Opens rig/AirshipRig.blend READ-ONLY (never saved) and writes <clone>/Saved/Airship/hull_survey.json.
#   /home/talal/.local/bin/blender -b /mnt/new_partition/BlenderProjects/StylizedAirship/rig/AirshipRig.blend \
#     --python Docs/Airship/scripts/ue/as_11a_hull_survey_blender.py
# Every vertex is 100 % on one bone (README_rig.md); a face is Hull's when all its vertices are (as as_20a).
import bpy, json, os, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
OUT = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/hull_survey.json'
STEP = 25.0
col = bpy.data.collections.get('SK_Airship')
objs = [o for o in (col.all_objects if col else bpy.data.objects) if o.type == 'MESH']
verts, polys, chain = [], [], []
for o in objs:
    mw = o.matrix_world
    names = {g.index: g.name for g in o.vertex_groups}
    me = o.data
    owner = [None] * len(me.vertices)
    for v in me.vertices:
        for ge in v.groups:
            if ge.weight > 0.5:
                owner[v.index] = names.get(ge.group)
    base = len(verts)
    for v in me.vertices:
        w = mw @ v.co
        p = Vector((100.0 * w.x, -100.0 * w.y, 100.0 * w.z))
        verts.append(p)
        if owner[v.index] == 'ChainFwd':
            chain.append([round(p.x, 2), round(p.y, 2), round(p.z, 2)])
    for p in me.polygons:
        if all(owner[i] == 'Hull' for i in p.vertices):
            polys.append([base + i for i in p.vertices])
tree = BVHTree.FromPolygons(verts, polys, all_triangles=False)
hv = sorted(set(i for p in polys for i in p))
mn = [min(verts[i][k] for i in hv) for k in range(3)]
mx = [max(verts[i][k] for i in hv) for k in range(3)]
cells = []
down = Vector((0.0, 0.0, -1.0))
x = math.floor(mn[0] / STEP) * STEP + STEP / 2
while x <= mx[0]:
    y = math.floor(mn[1] / STEP) * STEP + STEP / 2
    while y <= mx[1]:
        o = Vector((x, y, mx[2] + 100.0))
        hits = []
        for _ in range(40):
            loc, nor, idx, dist = tree.ray_cast(o, down)
            if loc is None:
                break
            hits.append([round(loc.z, 1), round(nor.z, 3)])
            o = Vector((x, y, loc.z - 0.05))
        if hits:
            cells.append([round(x, 1), round(y, 1), hits])
        y += STEP
    x += STEP
with open(OUT, 'w') as f:
    json.dump({'source': bpy.data.filepath, 'step_cm': STEP, 'hull_bounds': [mn, mx], 'hull_polys': len(polys),
               'cells': cells, 'chain_verts': chain}, f)
print('HULL_SURVEY cells=%d polys=%d chain=%d -> %s' % (len(cells), len(polys), len(chain), OUT))
