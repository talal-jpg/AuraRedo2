"""Round 3 review fixes (EXPORT_R3.md section 15, review nit "use_triangles"): how far could the ink lines move if Unreal
triangulated a quad or n-gon along a different diagonal than the bake did?

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_tri_check.py

The bake rasterises Blender's loop triangles (r3_common.tri_arrays: quads split 0-2 unless concave). The FBX files keep
quads and n-gons (rig_export / r3_export_static: use_triangles False); Unreal's FBX import (legacy and Interchange, 5.8)
triangulates them with the FBX SDK's FbxGeometryConverter::Triangulate (closed source; UnrealEd Fbx*Import.cpp,
Interchange FbxMesh.cpp). For a quad there are only two diagonals, so the worst case is the other one. For each textured
(atlas) quad of every ink page, points in UV space (the UV centroid and 0.25 / 0.5 / 0.75 along both UV diagonals) are
mapped to 3D through both splits; the distance between the two 3D points is how far the distance field (and so a line)
would sit from where the bake put it. N-gons: Blender's split against a fan from the first corner. Read only on
rig/detail/r3export/AirshipR3_export.blend; writes Docs/Airship/round3/export_tri_check.json.
"""
import bpy, sys, os, json
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import r3_common as RC

log = RC.Log('r3_tri_check')
prot0 = RC.protected_state()
bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND)


def bary_map(p, a, b, c, A, B, C):
    """UV point p in UV triangle (a, b, c) -> 3D point on (A, B, C); also returns inside (barycentrics >= -1e-6)"""
    v0, v1, v2 = b - a, c - a, p - a
    d00 = (v0 * v0).sum(-1); d01 = (v0 * v1).sum(-1); d11 = (v1 * v1).sum(-1)
    d20 = (v2 * v0).sum(-1); d21 = (v2 * v1).sum(-1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-20
    den = np.where(ok, den, 1.0)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    u = 1 - v - w
    ins = ok & (u >= -1e-6) & (v >= -1e-6) & (w >= -1e-6)
    return u[:, None] * A + v[:, None] * B + w[:, None] * C, ins


def map_split(p, uv, co, tris):
    """p (n, 2) per quad; tris = two (3,) corner index tuples into the quad's 4 corners -> 3D, found"""
    out = np.zeros((len(p), 3)); found = np.zeros(len(p), bool)
    for t in tris:
        P, ins = bary_map(p, uv[:, t[0]], uv[:, t[1]], uv[:, t[2]], co[:, t[0]], co[:, t[1]], co[:, t[2]])
        take = ins & ~found
        out[take] = P[take]; found |= take
    return out, found


def check(obj_name, page, uvname, atlas_only):
    ob = bpy.data.objects[obj_name]
    me = ob.data
    d = RC.mesh_np(me)
    co = d['co']
    uvl = RC.uv_get(me, uvname)
    nP = len(d['ls'])
    kind = RC.face_attr_get(me, 'r3_kind')
    keep = np.ones(nP, bool) if (kind is None or not atlas_only) else (kind == RC.K_ATLAS)
    tl, tv, tp = RC.tri_arrays(me)
    size = RC.PAGES[page]['size']
    res = dict(object=obj_name, uv=uvname, faces=int(nP), textured=int(keep.sum()))
    # ---- quads
    q = np.nonzero(keep & (d['lt'] == 4))[0]
    ls = d['ls'][q]
    L = ls[:, None] + np.arange(4)[None, :]                 # loops of each quad, polygon order
    quv = uvl[L]                                             # (n, 4, 2)
    qco = co[d['lv'][L]]                                     # (n, 4, 3)
    # Blender's split: the shared corners of the polygon's two loop triangles
    order = np.argsort(tp, kind='stable')
    tps = tp[order]
    first = np.searchsorted(tps, q)
    tri_loops = tl.reshape(-1, 3) if tl.ndim == 1 else tl
    i0 = order[first]; i1 = order[first + 1]
    loc = lambda tri: tri_loops[tri] - ls[:, None]           # corner numbers 0..3
    c0, c1 = loc(i0), loc(i1)
    shared = np.array([sorted(set(a) & set(b)) for a, b in zip(c0.tolist(), c1.tolist())])
    blender_02 = (shared[:, 0] == 0) & (shared[:, 1] == 2)
    # samples in UV: centroid and 0.25 / 0.5 / 0.75 along both UV diagonals
    S = [quv.mean(1)]
    for t in (0.25, 0.5, 0.75):
        S.append(quv[:, 0] + t * (quv[:, 2] - quv[:, 0]))
        S.append(quv[:, 1] + t * (quv[:, 3] - quv[:, 1]))
    worst = np.zeros(len(q))
    valid = np.zeros(len(q), bool)
    A_ = ((0, 1, 2), (0, 2, 3)); B_ = ((0, 1, 3), (1, 2, 3))
    for p in S:
        PA, fa = map_split(p, quv, qco, A_)
        PB, fb = map_split(p, quv, qco, B_)
        ok = fa & fb
        dd = np.linalg.norm(PA - PB, axis=1)
        worst = np.where(ok, np.maximum(worst, dd), worst)
        valid |= ok
    w = worst[valid] * 100.0                                   # cm
    # the lines sit on polygon edges (every feature edge is an island border), where both splits agree: the shift that
    # matters is the one delta cm inside the quad from an edge (delta = the line's half width: about 0.5 cm at 5 m,
    # 2 cm at 20 m, 4 cm at 40-70 m). Points: from each edge's UV midpoint toward the UV centroid, delta cm in 3D.
    near = {}
    PA_c, fa_c = map_split(quv.mean(1), quv, qco, A_)
    for delta in (0.005, 0.02, 0.04):
        wd = np.zeros(len(q)); vd = np.zeros(len(q), bool)
        for e in range(4):
            mu = 0.5 * (quv[:, e] + quv[:, (e + 1) % 4]); m3 = 0.5 * (qco[:, e] + qco[:, (e + 1) % 4])
            D = np.linalg.norm(PA_c - m3, axis=1)
            t = np.clip(delta / np.maximum(D, 1e-9), 0, 1)
            p = mu + t[:, None] * (quv.mean(1) - mu)
            PA, fa = map_split(p, quv, qco, A_)
            PB, fb = map_split(p, quv, qco, B_)
            ok = fa & fb & fa_c
            wd = np.where(ok, np.maximum(wd, np.linalg.norm(PA - PB, axis=1)), wd); vd |= ok
        x = wd[vd] * 100.0
        px_ = 2 * delta * 100.0 / (2.2 if delta < 0.04 else 1.7)      # pixel size (cm) where the half width is delta
        near['%.1fcm_from_edge' % (delta * 100)] = dict(
            p99=round(float(np.percentile(x, 99)), 3), p999=round(float(np.percentile(x, 99.9)), 3), max=round(float(x.max()), 3),
            pixel_cm_there=round(px_, 2), p999_px=round(float(np.percentile(x, 99.9)) / px_, 2), max_px=round(float(x.max()) / px_, 2),
            over_quarter_px=int((x > 0.25 * px_).sum()))
    dens = None
    res['quads'] = dict(n=int(len(q)), blender_split_0_2=int(blender_02.sum()), sampled=int(valid.sum()),
                        shift_cm=dict(p50=round(float(np.percentile(w, 50)), 4), p95=round(float(np.percentile(w, 95)), 3),
                                      p99=round(float(np.percentile(w, 99)), 3), p999=round(float(np.percentile(w, 99.9)), 3),
                                      max=round(float(w.max()), 3)),
                        over_0p1cm=int((w > 0.1).sum()), over_0p5cm=int((w > 0.5).sum()), over_1cm=int((w > 1.0).sum()),
                        over_2cm=int((w > 2.0).sum()), near_edges=near)
    # ---- n-gons: Blender's loop triangles against a fan from corner 0 (centroids of Blender's triangles)
    g = np.nonzero(keep & (d['lt'] > 4))[0]
    gw = []
    for f in g[:200000]:
        s0, n = d['ls'][f], d['lt'][f]
        Lg = np.arange(s0, s0 + n)
        uv_ = uvl[Lg]; c_ = co[d['lv'][Lg]]
        mine = order[np.searchsorted(tps, f):np.searchsorted(tps, f, side='right')]
        cents = np.array([uvl[tri_loops[t]].mean(0) for t in mine])
        PA = np.array([co[d['lv'][tri_loops[t]]].mean(0) for t in mine])
        fan = [(0, k, k + 1) for k in range(1, n - 1)]
        PB, fb = map_split(cents, np.repeat(uv_[None], len(cents), 0), np.repeat(c_[None], len(cents), 0), fan)
        if fb.any():
            gw.append(float(np.linalg.norm(PA[fb] - PB[fb], axis=1).max()))
    gw = np.array(gw) * 100.0 if gw else np.zeros(1)
    res['ngons'] = dict(n=int(len(g)), checked=int(len(gw)), shift_cm=dict(p50=round(float(np.percentile(gw, 50)), 4),
                        p99=round(float(np.percentile(gw, 99)), 3), max=round(float(gw.max()), 3)),
                        over_0p5cm=int((gw > 0.5).sum()))
    log(obj_name, 'near edges', json.dumps(near))
    log(obj_name, uvname, json.dumps(res['quads']['shift_cm']), 'quads > 0.5 cm %d of %d; ngons max %.3f cm' % (
        res['quads']['over_0p5cm'], len(q), res['ngons']['shift_cm']['max']))
    return res


out = dict(about=__doc__.strip().splitlines()[0], export_blend_md5=RC.md5_file(RC.EXPORT_BLEND), pages={})
hme = bpy.data.objects[RC.HULL_OBJ].data
out['pages']['hull'] = check(RC.HULL_OBJ, 'hull', RC.page_uv(hme, 'hull'), True)
out['pages']['H'] = check(RC.HULLDET, 'H', RC.UV_INK, True)
out['pages']['M'] = check(RC.MOVING, 'M', RC.UV_INK, True)
props = sorted(o.name for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(RC.PROP_PREFIX))
pr = [check(n, 'P', RC.UV_INK, False) for n in props]
out['pages']['P'] = dict(objects=len(pr), quads_max_cm=max(r['quads']['shift_cm']['max'] for r in pr),
                         quads_over_0p5cm=sum(r['quads']['over_0p5cm'] for r in pr), quads=sum(r['quads']['n'] for r in pr))
out['protected_unchanged'] = prot0 == RC.protected_state()
RC.dump_json(out, RC.DOCS + '/export_tri_check.json')
log('done; protected unchanged', out['protected_unchanged'])
sys.stdout.flush()
os._exit(0)
