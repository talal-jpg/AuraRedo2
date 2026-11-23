"""Back-project Talal's green marks (sketches 2 and 3) onto his SM_Airship through the solved sketch cameras
(checks/verify/sketch_camera.json) and report where on the ship each mark lands, to compare with the helm / cannon
bones. Runs on a COPY of StylizedAirship.blend (never saved).

  blender -b --factory-startup rig/checks/verify/Talal_copy.blend --python rig/scripts/verify_sketch_marks.py
"""
import bpy, json, math, os
import numpy as np
from mathutils import Vector, Euler
from mathutils.bvhtree import BVHTree

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
SK = '/mnt/new_partition/UnrealProjects/_AirshipWork_logs/talal_sketches/'
cams = json.load(open(RIG + '/checks/verify/sketch_camera.json'))
o = bpy.data.objects['SM_Airship']
me = o.data
V = [o.matrix_world @ v.co for v in me.vertices]
bvh = BVHTree.FromPolygons(V, [tuple(p.vertices) for p in me.polygons])
out = {}
for key, c in cams.items():
    img = bpy.data.images.load(SK + key + '.png')
    W, H = img.size
    px = np.array(img.pixels[:]).reshape(H, W, img.channels)[::-1]    # row 0 = top
    g = (px[:, :, 1] > 0.70) & (px[:, :, 0] < 0.47) & (px[:, :, 2] < 0.47)
    ys, xs = np.nonzero(g)
    R = Euler(c['rotation_euler']).to_matrix()
    C = Vector(c['location'])
    f = c['lens_mm'] / 36.0 * W
    hits = []
    for x, y in zip(xs, ys):
        d = R @ Vector(((x + 0.5 - W / 2) / f, -(y + 0.5 - H / 2) / f, -1.0))
        loc, nrm, fi, dist = bvh.ray_cast(C, d.normalized())
        if loc is not None:
            hits.append((x, y, loc.x, loc.y, loc.z))
    hits = np.array(hits)
    # split marks by screen x gaps (> 25 px)
    order = np.argsort(hits[:, 0])
    hs = hits[order]
    groups = [[hs[0]]]
    for h in hs[1:]:
        if h[0] - groups[-1][-1][0] > 25:
            groups.append([h])
        else:
            groups[-1].append(h)
    res = []
    for gp in groups:
        gp = np.array(gp)
        if len(gp) < 30:
            continue
        # ignore the hits of the helm "wheel" circle drawn in the sky (they hit far geometry or nothing)
        q = lambda a, p: round(float(np.percentile(a, p)), 2)
        res.append({'pixels': len(gp), 'screen_x': [int(gp[:, 0].min()), int(gp[:, 0].max())],
                    'screen_y': [int(gp[:, 1].min()), int(gp[:, 1].max())],
                    'x_p5_p50_p95': [q(gp[:, 2], 5), q(gp[:, 2], 50), q(gp[:, 2], 95)],
                    'y_p5_p50_p95': [q(gp[:, 3], 5), q(gp[:, 3], 50), q(gp[:, 3], 95)],
                    'z_p5_p50_p95': [q(gp[:, 4], 5), q(gp[:, 4], 50), q(gp[:, 4], 95)]})
    out[key] = {'green_pixels': int(g.sum()), 'hit_pixels': len(hits), 'marks': res}
    # rectangle only (sketch 2): rows below the stick, the filled box
    if key.startswith('2_'):
        box = hits[(hits[:, 1] > np.percentile(hits[:, 1], 60))]
        out[key]['helm_box_bottom_rows'] = {'x_p5_p50_p95': [round(float(np.percentile(box[:, 2], p)), 2) for p in (5, 50, 95)],
                                            'y_p5_p50_p95': [round(float(np.percentile(box[:, 3], p)), 2) for p in (5, 50, 95)],
                                            'z_p50': round(float(np.median(box[:, 4])), 2)}
json.dump(out, open(RIG + '/checks/verify/sketch_marks.json', 'w'), indent=1)
print('[marks]', json.dumps(out))
