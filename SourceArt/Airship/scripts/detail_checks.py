"""Checks shared by every detail zone (round 3): distance to a target surface (silhouette), pod outline growth,
PA_Airship hull boxes, plus the per-zone checklist helpers (rigid skin, non-manifold edges, role materials, zone
ownership). Moved from detail_zone1.py on 2026-11-28 (unchanged maths) and extended.
"""
import bpy, sys, os, math, random, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S


# ================================================================== checks
def dist_report(co, surf, name, limit, vkind=None):
    """max distance of detail vertices from the target surface (the silhouette rule)"""
    co = np.asarray(co)
    if len(co) == 0:
        return dict(name=name, verts=0)
    d = np.array([(lambda r: r[3] if r[0] is not None else 9.0)(surf.bvh.find_nearest(V(c), 9.0)) for c in co])
    w = int(np.argmax(d))
    kinds = {}
    if vkind is not None:
        for k in np.nonzero(d > limit)[0]:
            kinds[vkind[k]] = kinds.get(vkind[k], 0) + 1
    return dict(name=name, max_dist_m=round(float(d[w]), 3), worst=[round(float(x), 3) for x in co[w]],
                verts_over_limit=int((d > limit).sum()), over_limit_by_kind=kinds, verts=len(co), limit_m=limit,
                p99_m=round(float(np.percentile(d, 99)), 3))


def pod_frame_coords(co, T0, A, e0, e90):
    rel = np.asarray(co) - T0
    h = rel @ A
    x, y = rel @ e0, rel @ e90
    return h, np.degrees(np.arctan2(y, x)), np.hypot(x, y)


def silhouette_table(pod_bvh, T0, A, e0, e90, r_out=4.0, h_rng=(-1.75, 4.2), pod_co=None):
    """the pod's largest existing radius per 0.5 degree of angle over its whole height (ray casts toward the axis, and
    the pod's own vertices: some outer faces of the big plates are not found by the ray casts)"""
    ths = np.arange(-180.0, 180.0, 0.5)
    out = np.zeros(len(ths))
    for k, th in enumerate(ths):
        a = math.radians(th + 0.13)
        d = e0 * math.cos(a) + e90 * math.sin(a)
        best = 0.0
        for h in np.arange(h_rng[0], h_rng[1], 0.06):
            hit = pod_bvh.ray_cast(V(T0 + A * h + d * r_out), V(-d), r_out)
            if hit[0] is not None:
                best = max(best, r_out - hit[3])
        out[k] = best
    if pod_co is not None:
        _, pth, pr = pod_frame_coords(pod_co, T0, A, e0, e90)
        for k, th in enumerate(ths):
            m = np.abs((pth - th + 180.0) % 360.0 - 180.0) <= 0.5
            if m.any():
                out[k] = max(out[k], float(pr[m].max()))
    return ths, out


def envelope_report(co, pod_bvh, T0, A, e0, e90, name, r_out=4.0, sil=None, vkind=None):
    """how far detail vertices stick out of the pod's existing radial envelope.
    local: a ray from r_out toward the axis at the vertex's own height and angle finds the outermost existing pod
    surface there (strict: a pipe over the ribs counts from the drum between them).
    silhouette: the pod's largest existing radius at that angle (+-3 deg) over its whole height, i.e. growth of the
    pod's outline seen from that side (silhouette_table)."""
    co = np.asarray(co)
    if len(co) == 0:
        return dict(name=name, verts=0)
    h, th, r = pod_frame_coords(co, T0, A, e0, e90)
    ex = np.zeros(len(co))
    for k in range(len(co)):
        a = math.radians(th[k] + 0.31)
        d = e0 * math.cos(a) + e90 * math.sin(a)
        o = T0 + A * (h[k] + 0.011) + d * r_out
        hit = pod_bvh.ray_cast(V(o), V(-d), r_out)
        r_env = (r_out - hit[3]) if hit[0] is not None else 0.0
        ex[k] = r[k] - r_env
    kinds = {}
    if vkind is not None:
        for k in np.nonzero(ex > 0.15)[0]:
            kinds[vkind[k]] = kinds.get(vkind[k], 0) + 1
    out = dict(name=name, local_max_excess_m=round(float(ex.max()), 3), local_p99_m=round(float(np.percentile(ex, 99)), 3),
               local_verts_over_0_15=int((ex > 0.15).sum()), local_over_0_15_by_kind=kinds, verts=len(ex))
    if sil is not None:
        ths, rmax = sil
        se = np.zeros(len(co))
        for k in range(len(co)):
            dd = np.abs((ths - th[k] + 180.0) % 360.0 - 180.0)
            se[k] = r[k] - rmax[dd <= 3.0].max()
        w = int(np.argmax(se))
        sk = {}
        if vkind is not None:
            for k in np.nonzero(se > 0.0)[0]:
                sk[vkind[k]] = sk.get(vkind[k], 0) + 1
        out.update(silhouette_max_excess_m=round(float(se[w]), 3), silhouette_verts_over_0=int((se > 0.0).sum()),
                   silhouette_over_0_by_kind=sk, silhouette_verts_over_0_05=int((se > 0.05).sum()),
                   silhouette_worst=dict(h=round(float(h[w]), 2), deg=round(float(th[w]), 1), r=round(float(r[w]), 3),
                                         kind=None if vkind is None else vkind[w]))
    return out


def vertex_kinds(mesh):
    vk = ['?'] * len(mesh.v)
    for f, k in zip(mesh.f, mesh.k):
        for i in f:
            vk[i] = k
    return vk


def pa_report(co, path):
    """detail vertices against PA_Airship's hull boxes (UE cm: x*100, -y*100, z*100): inside any box, and standing above
    a box's top inside its footprint (the box tops are the walkable deck)"""
    if not os.path.exists(path):
        return dict(missing=path)
    B = C.load_json(path)['hull_boxes']
    mn = np.array([b['min'] for b in B]); mx = np.array([b['max'] for b in B])
    P = np.asarray(co) * np.array([100.0, -100.0, 100.0])
    inside, above, worst_above = 0, 0, None
    for p in P:
        foot = (p[0] >= mn[:, 0]) & (p[0] <= mx[:, 0]) & (p[1] >= mn[:, 1]) & (p[1] <= mx[:, 1])
        if not foot.any():
            continue
        inb = foot & (p[2] >= mn[:, 2]) & (p[2] <= mx[:, 2])
        inside += int(inb.any())
        up = foot & (p[2] > mx[:, 2])
        if up.any():
            above += 1
            dz = float((p[2] - mx[up, 2]).max())
            worst_above = dz if worst_above is None else max(worst_above, dz)
    return dict(boxes=len(B), verts=len(P), verts_inside_a_box=inside, verts_above_a_box_top=above,
                worst_cm_above_a_top=None if worst_above is None else round(worst_above, 1))


# ================================================================== per-zone checklist helpers (2026-11-28)
def loose_piece_volumes(ob):
    """signed volume per loose piece of a mesh object (world space). Closed pieces with a negative volume are inside
    out (faces wound the wrong way: Unreal culls their outside). Returns (volumes array, piece id per polygon)"""
    me = ob.data
    nV = len(me.vertices)
    co = np.empty(nV * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    M = np.array(ob.matrix_world)
    co = co @ M[:3, :3].T + M[:3, 3]
    par = np.arange(nV)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    polys = [list(p.vertices) for p in me.polygons]
    for p in polys:
        r0 = find(p[0])
        for q in p[1:]:
            rq = find(q)
            if rq != r0:
                par[rq] = r0
    root = np.array([find(i) for i in range(nV)])
    pid = np.array([root[p[0]] for p in polys])
    vol = {}
    for p, c in zip(polys, pid):
        a = co[p[0]]
        s = 0.0
        for i in range(1, len(p) - 1):
            s += float(np.dot(a, np.cross(co[p[i]], co[p[i + 1]])))
        vol[int(c)] = vol.get(int(c), 0.0) + s / 6.0
    return vol, pid


def object_report(ob, zone=None, arm_name='Armature'):
    """the per-object items of the zone checklist (ZONES.md): name / collection convention, parent + Armature modifier,
    rigid skin, role materials on every face, non-manifold edges, inside-out pieces, triangles"""
    import bmesh
    me = ob.data
    zn = str(zone).upper().lstrip('Z') if zone else None
    names = {g.index: g.name for g in ob.vertex_groups}
    not_rigid = sum(1 for v in me.vertices if len(v.groups) != 1 or abs(v.groups[0].weight - 1.0) > 1e-6)
    bones = sorted({names[v.groups[0].group] for v in me.vertices if len(v.groups) == 1})
    mi = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get('material_index', mi)
    keys = [(m.get('palette_key') if m else None) for m in me.materials]
    bad_role = int(sum(1 for i in mi if i >= len(keys) or keys[i] not in D.MAT_KEYS))
    roles = {}
    for i in mi:
        k = keys[i] if i < len(keys) else None
        roles[str(k)] = roles.get(str(k), 0) + 1
    bm = bmesh.new(); bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    vol, _ = loose_piece_volumes(ob)
    inv = [v for v in vol.values() if v < -1e-9]
    arm_mod = [m for m in ob.modifiers if m.type == 'ARMATURE']
    rep = dict(object=ob.name, tris=int(sum(len(p.vertices) - 2 for p in me.polygons)), verts=len(me.vertices),
               pieces=len(vol), inside_out_pieces=len(inv), inside_out_volume_m3=round(-sum(inv), 6),
               nonmanifold_edges=nm, not_rigid_vertices=not_rigid, bones=bones,
               parent=ob.parent.name if ob.parent else None,
               armature_modifier=bool(arm_mod) and arm_mod[0].object is not None and arm_mod[0].object.name == arm_name,
               faces_without_role=bad_role, faces_by_role=roles,
               collections=[c.name for c in ob.users_collection])
    if zn:
        rep['name_ok'] = ob.name.startswith('SM_AirshipDetail_Z%s_' % zn)
        rep['collection_ok'] = ('Detail_Z' + zn) in rep['collections']
    rep['ok'] = (nm == 0 and not_rigid == 0 and bad_role == 0 and not inv and rep['parent'] == arm_name and
                 rep['armature_modifier'] and rep.get('name_ok', True) and rep.get('collection_ok', True))
    return rep


def world_co(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    M = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def zone_checks(objs, zone, ship, index=None, sample=4, silhouette=0.20):
    """the geometric items of the zone checklist for a set of detail objects: ownership (detail_zones), keep-clear
    volumes, PA_Airship walkable tops, distance to the ship (silhouette rule: hull details within ~20 cm of the skin;
    pods / turbines / the gantry are checked by the zone against their own part)"""
    import detail_zones as Z
    index = index or Z.ZoneIndex(ship)
    co = np.concatenate([world_co(o) for o in objs]) if objs else np.zeros((0, 3))
    ship_surf = ship.surface(np.ones(len(ship.polys), bool))
    return dict(
        ownership=Z.ownership_report(index, co, zone, sample=sample),
        pa_boxes=pa_report(co, '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/pa_hull_boxes.json'),
        to_ship=dist_report(co[::sample], ship_surf, 'detail vertices vs any SM_Airship face', silhouette),
        bbox=[[round(float(v), 3) for v in co.min(0)], [round(float(v), 3) for v in co.max(0)]] if len(co) else None)


if __name__ == '__main__':
    # blender_capped.sh --python detail_checks.py -- --blend FILE --zone Z1 [--out FILE.json] [--sample 4]
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    bpy.ops.wm.open_mainfile(filepath=g('--blend', D.zone_blend(1)))
    zone = g('--zone', 'Z1')
    zn = zone.upper().lstrip('Z')
    objs = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('SM_AirshipDetail_Z%s_' % zn)]
    ship = S.Ship(bpy)
    rep = dict(zone=zone, objects=[object_report(o, zone) for o in objs],
               zone_checks=zone_checks(objs, 'Z' + zn, ship, sample=int(g('--sample', 4))))
    out = g('--out', D.TMP_DIR + '/checks_z%s.json' % zn)
    C.dump_json(rep, out)
    for r in rep['objects']:
        print('[checks]', json.dumps({k: r[k] for k in ('object', 'ok', 'tris', 'pieces', 'inside_out_pieces',
                                                         'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')}))
    print('[checks] zone', json.dumps(rep['zone_checks']))
    print('[checks] wrote', out)
    sys.stdout.flush()
    os._exit(0)
