"""How well does a cannon at each port rail-post gap fill Talal's green marks in 3_cannon_spots.png?

Projects the rigged L1 cannon (all 7 parts, rest pose) through the solved sketch camera
(checks/verify/sketch_camera.json) at every port rail-post gap near each mark, rasterises its silhouette and compares it
with the mark (convex hull of the mark's green pixels): share of the silhouette inside the mark, and the distance between
the silhouette's and the mark's centroids (px). The same rule as rig_place.py sets the candidate origin (muzzle face
0.12 m inside the rail centre line + the station's inboard nudge, deck at the rail foot). Runs on a COPY of
AirshipRig.blend (never saved).

  blender -b --factory-startup <copy of rig/AirshipRig.blend> --python rig/scripts/verify_station_fit.py   (verify_all.sh)
Writes checks/verify/station_fit.json. Also casts every mark pixel onto the vertical surface through the port rail posts
("which stretch of rail did he mark"); the aft mark is seen so edge-on that neither reading pins it closer than a few m.
"""
import bpy, json
import numpy as np
from mathutils import Vector, Euler

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
SK = '/mnt/new_partition/UnrealProjects/_AirshipWork_logs/talal_sketches/3_cannon_spots.png'
RESEARCH = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/research'
cam = json.load(open(RIG + '/checks/verify/sketch_camera.json'))['3_cannon_spots']
place = json.load(open(RIG + '/checks/rig/placement.json'))['cannons']

img = bpy.data.images.load(SK)
W, H = img.size
px = np.array(img.pixels[:]).reshape(H, W, img.channels)[::-1]
green = (px[:, :, 1] > 0.70) & (px[:, :, 0] < 0.47) & (px[:, :, 2] < 0.47)
R = Euler(cam['rotation_euler']).to_matrix()
Rt = np.array(R.transposed())
Cc = np.array(cam['location'])
f = cam['lens_mm'] / 36.0 * W


def project(P):
    q = (P - Cc) @ Rt.T
    return np.stack([f * q[:, 0] / -q[:, 2] + W / 2 - 0.5, -f * q[:, 1] / -q[:, 2] + H / 2 - 0.5], 1)


def raster_tris(T):
    """T: (n,3,2) screen triangles -> bool mask (H, W)"""
    m = np.zeros((H, W), bool)
    for t in T:
        x0, y0 = np.floor(t.min(0)).astype(int); x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) , np.arange(y0, y1 + 1))
        p = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
        a, b, c = t
        def s(u, v, w):
            return (w[:, 0] - u[0]) * (v[1] - u[1]) - (w[:, 1] - u[1]) * (v[0] - u[0])
        d1, d2, d3 = s(a, b, p), s(b, c, p), s(c, a, p)
        ins = ~(((d1 < 0) | (d2 < 0) | (d3 < 0)) & ((d1 > 0) | (d2 > 0) | (d3 > 0)))
        m[gy.ravel()[ins], gx.ravel()[ins]] = True
    return m


def hull(points):
    pts = sorted(set(map(tuple, points)))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return np.array(lo[:-1] + hi[:-1], float)


def poly_mask(P):
    c = P.mean(0)
    return raster_tris(np.array([[c, P[i], P[(i + 1) % len(P)]] for i in range(len(P))]))


# marks: green pixels split by screen x gaps > 25 px (as verify_sketch_marks.py), filled by their convex hull
ys, xs = np.nonzero(green)
order = np.argsort(xs)
groups, cur = [], [order[0]]
for i in order[1:]:
    if xs[i] - xs[cur[-1]] > 25:
        groups.append(cur); cur = [i]
    else:
        cur.append(i)
groups.append(cur)
marks = [np.stack([xs[g], ys[g]], 1) for g in groups if len(g) >= 30]
marks.sort(key=lambda m: m[:, 0].mean())         # left (bow) first: mark 1 = fore, mark 2 = aft
MASKS = [poly_mask(hull(m)) for m in marks]

# cannon L1 geometry (world, rest)
tris = []
for o in bpy.data.objects:
    if o.type == 'MESH' and o.name.startswith('SM_AirshipProp_Cannon_L1_'):
        V = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
        for p in o.data.polygons:
            vs = list(p.vertices)
            for k in range(1, len(vs) - 1):
                tris.append(V[[vs[0], vs[k], vs[k + 1]]])
tris = np.array(tris)
O_L1 = np.array(place['L1']['origin'])

# port rail posts (same rule as rig_place.py)
isl = json.load(open(RESEARCH + '/sm_airship_islands.json'))['islands']
posts = sorted([r for r in isl if r['src'] == 'DeckRails' and r['bbmax'][2] - r['bbmin'][2] > 0.9 and r['c'][1] > 0],
               key=lambda r: r['c'][0])
gaps = []
for a, b in zip(posts[:-1], posts[1:]):
    x = (a['c'][0] + b['c'][0]) / 2
    gaps.append(dict(x=x, rail_y=(a['c'][1] + b['c'][1]) / 2, foot_z=(a['bbmin'][2] + b['bbmin'][2]) / 2))

PX = np.array([p['c'][0] for p in posts]); PY = np.array([p['c'][1] for p in posts])


def on_rail_plane(sx, sy):
    """ray through screen pixel -> x where it meets the vertical surface through the port rail-post line"""
    d = np.array(R @ Vector(((sx + 0.5 - W / 2) / f, -(sy + 0.5 - H / 2) / f, -1.0)))
    t0, t1 = 1.0, 200.0
    g = lambda t: (Cc + t * d)[1] - np.interp((Cc + t * d)[0], PX, PY)
    for _ in range(60):                 # bisection: camera is outboard (g > 0), far side inboard (g < 0)
        tm = (t0 + t1) / 2
        if g(tm) > 0:
            t0 = tm
        else:
            t1 = tm
    p = Cc + t0 * d
    return p[0], p[2]


out = {'camera': cam, 'marks': []}
for mi, (mk, M) in enumerate(zip(marks, MASKS)):
    mc = np.argwhere(M).mean(0)[::-1]
    # where along the rail the mark is drawn: every filled-mark pixel cast onto the rail's vertical surface
    yy, xx = np.nonzero(M)
    rp = np.array([on_rail_plane(x, y) for x, y in zip(xx, yy)])
    rs = np.array([on_rail_plane(x, y) for x, y in mk])
    q = lambda a: [round(float(np.percentile(a, p)), 2) for p in (5, 50, 95)]
    rail_reading = dict(filled_x_p5_p50_p95=q(rp[:, 0]), filled_x_mean=round(float(rp[:, 0].mean()), 2),
                        filled_z_p5_p50_p95=q(rp[:, 1]), strokes_x_p5_p50_p95=q(rs[:, 0]),
                        centroid_ray_x=round(float(on_rail_plane(*mc)[0]), 2))
    print('[fit] mark', mi + 1, 'on the rail plane', rail_reading)
    nudge = 0.0 if mi == 0 else place['L2']['nudge_inboard_m']
    rows = []
    for g in gaps:
        if not (-16.0 < g['x'] < 4.0):
            continue
        o = np.array([g['x'], g['rail_y'] - (1.86 + 0.12 + nudge), g['foot_z']])
        S = raster_tris(project((tris + (o - O_L1)).reshape(-1, 3)).reshape(-1, 3, 2))
        n = int(S.sum())
        if n == 0:
            continue
        inside = int((S & M).sum())
        sc = np.argwhere(S).mean(0)[::-1]
        rows.append(dict(gap_x=round(g['x'], 3), origin=[round(float(v), 3) for v in o], silhouette_px=n,
                         inside_mark=round(inside / n, 3), centroid_dist_px=round(float(np.linalg.norm(sc - mc)), 1),
                         centroid_dx_px=round(float(sc[0] - mc[0]), 1)))
    rows = [r for r in rows if r['inside_mark'] > 0.0 or abs(r['centroid_dx_px']) < 120]
    best = min(rows, key=lambda r: r['centroid_dist_px'])
    out['marks'].append(dict(mark=mi + 1, screen_x=[int(mk[:, 0].min()), int(mk[:, 0].max())],
                             mark_px_filled=int(M.sum()), mark_centroid_px=[round(float(v), 1) for v in mc],
                             on_rail_plane=rail_reading,
                             candidates=rows, best_by_centroid=best['gap_x'],
                             best_by_inside=max(rows, key=lambda r: r['inside_mark'])['gap_x']))
    print('[fit] mark', mi + 1, 'centroid', mc.round(1), 'best by centroid', best['gap_x'])
    for r in rows:
        print('[fit]   gap %+8.3f  inside %.2f  centroid dist %5.1f px (dx %+6.1f)' % (r['gap_x'], r['inside_mark'], r['centroid_dist_px'], r['centroid_dx_px']))
with open(RIG + '/checks/verify/station_fit.json', 'w') as fh:
    json.dump(out, fh, indent=1)
print('[fit] wrote', RIG + '/checks/verify/station_fit.json')
