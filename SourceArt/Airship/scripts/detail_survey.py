"""Ship survey for the round 3 zone map (read only): cross sections, transom, parts, pods, fans, moving parts.

  blender_capped.sh --python detail_survey.py -- [--out rig/detail/zones/ship_survey.json]

Opens rig/AirshipRig.blend (never saved) and writes plain numbers the zone map (detail_zones.py) and ZONES.md use.
"""
import bpy, sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
import rig_common as C
import detail_common as D
import detail_ship as S


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def r(v, n=3):
    return [round(float(x), n) for x in v]


def main():
    o = opts()
    out = o.get('out', D.ZONES_DIR + '/ship_survey.json')
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    me = ship.ob.data
    skin = ship.surface(ship.p_island == S.SKIN)
    allb = ship.bvh(np.ones(len(ship.polys), bool))
    rep = {}
    # ---- cross sections of the skin
    secs = []
    for x in np.arange(-17.0, 31.6, 0.25):
        row = dict(x=round(float(x), 2))
        hz = skin.ray((x, 0.0, 40.0), (0, 0, -1), 80.0)
        row['deck_z_c'] = None if hz is None else round(float(hz[0][2]), 3)
        hk = skin.ray((x, 0.0, -40.0), (0, 0, 1), 80.0)
        row['keel_z_c'] = None if hk is None else round(float(hk[0][2]), 3)
        for side, nm in ((1, 'port'), (-1, 'stbd')):
            best = None
            for z in np.arange(-6.0, 9.0, 0.1):
                h = skin.ray((x, side * 40.0, z), (0, -side, 0), 80.0)
                if h is not None and (best is None or abs(h[0][1]) > abs(best[1])):
                    best = (z, h[0][1])
            row[nm + '_maxw'] = None if best is None else [round(float(best[1]), 3), round(float(best[0]), 2)]
            # chart rays (FlankChart convention: axis (x, side*1.5, 0.3), phi 0 = horizontal outboard)
            hits = {}
            for ph in (30.0, 0.0, -30.0, -56.0, -70.0, -80.0):
                p = math.radians(ph)
                d = np.array([0.0, side * math.cos(p), math.sin(p)])
                ax = np.array([x, side * 1.5, 0.3])
                h = skin.ray(ax + 20 * d, -d, 30.0)
                hits['%d' % ph] = None if h is None else r(h[0])
            row[nm + '_chart'] = hits
        secs.append(row)
    rep['sections'] = secs
    # ---- transom: rays from aft toward +x
    tr = []
    for y in np.arange(-6.0, 6.01, 0.5):
        for z in np.arange(-5.0, 4.01, 0.25):
            h = skin.ray((-40.0, y, z), (1, 0, 0), 60.0)
            if h is not None and h[4][0] < -0.5:
                tr.append(r(h[0]) + [round(float(h[4][0]), 2)])
    tr = np.array(tr) if tr else np.zeros((0, 4))
    rep['transom'] = dict(n=len(tr), x_min=round(float(tr[:, 0].min()), 3) if len(tr) else None,
                          x_max=round(float(tr[:, 0].max()), 3) if len(tr) else None,
                          y=[round(float(tr[:, 1].min()), 2), round(float(tr[:, 1].max()), 2)] if len(tr) else None,
                          z=[round(float(tr[:, 2].min()), 2), round(float(tr[:, 2].max()), 2)] if len(tr) else None)
    # ---- bow tip: rays from the front toward -x
    bt = []
    for y in np.arange(-3.0, 3.01, 0.25):
        for z in np.arange(-3.0, 9.01, 0.25):
            h = allb.ray_cast(V((60.0, y, z)), V((-1, 0, 0)), 80.0)
            if h[0] is not None:
                bt.append(r(h[0]) + [int(ship.p_island[h[2]])])
    bt = np.array(bt)
    k = int(np.argmax(bt[:, 0]))
    rep['bow_tip'] = dict(x=float(bt[k, 0]), at=bt[k].tolist())
    # ---- islands: per source / part / piece, bbox (rig mesh), tris
    groups = {}
    co = ship.co
    for isl in np.unique(ship.v_island):
        rec = ship.islands[int(isl)]
        vm = ship.v_island == isl
        pm = ship.p_island == isl
        key = '%s|%s|%s|%s' % (rec['src'], rec['part'], rec.get('piece', ''), ship.v_bone[np.nonzero(vm)[0][0]])
        g = groups.setdefault(key, dict(islands=[], tris=0, bbmin=[9e9] * 3, bbmax=[-9e9] * 3))
        g['islands'].append(int(isl))
        g['tris'] += int(sum(len(ship.polys[i]) - 2 for i in np.nonzero(pm)[0]))
        g['bbmin'] = r(np.minimum(g['bbmin'], co[vm].min(0)))
        g['bbmax'] = r(np.maximum(g['bbmax'], co[vm].max(0)))
    for g in groups.values():
        if len(g['islands']) > 12:
            g['islands'] = g['islands'][:12] + ['... %d in all' % len(g['islands'])]
    rep['groups'] = groups
    # hull-src islands one by one (skin, keel, tabs ...)
    rep['hull_src_islands'] = {int(i): dict(tris=int(sum(len(ship.polys[p]) - 2 for p in np.nonzero(ship.p_island == i)[0])),
                                            bbmin=r(co[ship.v_island == i].min(0)), bbmax=r(co[ship.v_island == i].max(0)))
                               for i in np.unique(ship.v_island) if ship.islands[int(i)]['src'] == 'Hull'}
    # ---- pods: frames, plate islands (12 verts), angles of plates / side boxes in each pod's frame, drum radius
    pods = {}
    for p in C.PODS:
        O, T0, A, NP = ship.pod_frame(p)
        e0, e90 = S.pod_basis(A)
        info = dict(origin=r(O), T0=r(T0), axis=r(A), nozzle_pivot=r(NP), e0=r(e0), e90=r(e90))
        for piece in ('plate', 'side_box', 'drum', 'rib'):
            ids = sorted(i for i, rr in ship.islands.items() if rr['part'] == 'Pod_' + p and rr.get('piece') == piece)
            lst = []
            for i in ids:
                v = co[ship.v_island == i]
                rel = v - T0
                h = rel @ A
                th = np.degrees(np.arctan2(rel @ e90, rel @ e0))
                rad = np.hypot(rel @ e0, rel @ e90)
                c = v.mean(0) - T0
                lst.append(dict(id=i, nv=int(len(v)), h=[round(float(h.min()), 3), round(float(h.max()), 3)],
                                th_c=round(float(math.degrees(math.atan2(c @ e90, c @ e0))), 1),
                                th=[round(float(th.min()), 1), round(float(th.max()), 1)],
                                r=[round(float(rad.min()), 3), round(float(rad.max()), 3)]))
            info[piece] = lst
        pods[p] = info
    rep['pods'] = pods
    # ---- moving parts and props (world bboxes at rest)
    obs = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob.name == C.HULL_OBJ:
            continue
        v = np.array([ob.matrix_world @ vv.co for vv in ob.data.vertices])
        if len(v):
            obs[ob.name] = dict(bbmin=r(v.min(0)), bbmax=r(v.max(0)), verts=len(v),
                                coll=[c.name for c in ob.users_collection])
    rep['objects'] = obs
    rep['bones'] = {b.name: r(b.head_local) for b in ship.arm.data.bones}
    rep['frames'] = {k: v for k, v in ship.frames.items() if k.startswith('Fan') or k.startswith('Search')}
    C.dump_json(rep, out)
    print('[survey] wrote', out)


if __name__ == '__main__':
    main()
