# as_20a_deck_survey_blender.py - Blender HEADLESS helper (not an Unreal script): surveys the horizontal surfaces of the
# Hull-skinned geometry of SK_Airship (deck, gantry) on a 25 cm grid, in Unreal component space (cm), for the Wreck
# solver's deck / gantry slabs of CR_Airship (as_20b_deck_slabs.py turns the grid into boxes, as_12 reads those).
# Opens rig/AirshipRig.blend READ-ONLY (never saved) and writes <clone>/Saved/Airship/deck_survey.json.
#   /mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/blender -b \
#     /mnt/new_partition/BlenderProjects/StylizedAirship/rig/AirshipRig.blend --python as_20a_deck_survey_blender.py
# Rays go straight down from above the ship; every hit on a Hull face whose normal is within ~25 deg of vertical is kept
# (all layers, not only the first), so the deck under the gantry is found too.
import bpy, json, os, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/deck_survey.json'
STEP = 25.0
col = bpy.data.collections.get('SK_Airship')
objs = [o for o in (col.all_objects if col else bpy.data.objects) if o.type == 'MESH']
verts, polys = [], []
for o in objs:
    mw = o.matrix_world
    gi = o.vertex_groups.get('Hull')
    if gi is None:
        continue
    gidx = gi.index
    me = o.data
    on_hull = [False] * len(me.vertices)
    for v in me.vertices:
        for ge in v.groups:
            if ge.group == gidx and ge.weight > 0.5:
                on_hull[v.index] = True
    base = len(verts)
    for v in me.vertices:
        w = mw @ v.co
        verts.append(Vector((100.0 * w.x, -100.0 * w.y, 100.0 * w.z)))
    for p in me.polygons:
        if all(on_hull[i] for i in p.vertices):
            polys.append([base + i for i in p.vertices])
tree = BVHTree.FromPolygons(verts, polys, all_triangles=False)
mn = [min(v[i] for v in verts) for i in range(3)]
mx = [max(v[i] for v in verts) for i in range(3)]
cells = []
x = math.floor(mn[0] / STEP) * STEP
down = Vector((0.0, 0.0, -1.0))
nrays = 0
while x <= mx[0] + 1e-6:
    y = math.floor(mn[1] / STEP) * STEP
    while y <= mx[1] + 1e-6:
        o = Vector((x, y, mx[2] + 100.0))
        hits = []
        for _ in range(12):
            loc, nor, idx, dist = tree.ray_cast(o, down)
            nrays += 1
            if loc is None:
                break
            if abs(nor.z) > 0.9:
                hits.append(round(loc.z, 1))
            o = Vector((x, y, loc.z - 0.05))
        if hits:
            cells.append([round(x, 1), round(y, 1), hits])
        y += STEP
    x += STEP
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w') as f:
    json.dump({'source': bpy.data.filepath, 'space': 'UE component cm (100x,-100y,100z)', 'step_cm': STEP,
               'hull_polys': len(polys), 'bounds': [mn, mx], 'rays': nrays,
               'cells': cells, 'note': 'cells: [x, y, [z of every near-horizontal Hull face hit, top down]]'}, f)
print('DECK_SURVEY cells=%d polys=%d rays=%d -> %s' % (len(cells), len(polys), nrays, OUT))
