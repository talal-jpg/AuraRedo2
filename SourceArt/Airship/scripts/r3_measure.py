"""Round 3 export plan: measurements for the Unreal stage (read only; never saves anything).

  blender_capped.sh --python SourceArt/Airship/scripts/r3_measure.py -- [--blend FULL.blend] [--out JSON]

Opens the assembled detail file (rig/detail/zones/AirshipRig_detail_full.blend by default) and writes one JSON:
  * sm_airship: faces / triangles / vertices, surface area, UV area, texel density of its existing UV map at 1024..8192
    (area-weighted percentiles), render-vertex estimate (unique vertex + corner normal + UV), UV maps;
  * details: per object and per bone group (Hull vs moving parts): triangles, vertices, render-vertex estimate (unique
    vertex + corner normal), surface area split into rivet faces (Freestyle mark), pieces under 15 cm, 15-60 cm and
    0.6 m+ (loose-piece bounding-box diagonal, as detail_assemble.lod_estimate), piece counts, rivet head sizes;
  * atlas sizing: texels needed for the non-rivet detail area at several texel densities and packing efficiencies.
"""
import bpy, sys, os, json, math, time
sys.dont_write_bytecode = True
import numpy as np

A = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
BLEND = A[A.index('--blend') + 1] if '--blend' in A else \
    '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones/AirshipRig_detail_full.blend'
OUT = A[A.index('--out') + 1] if '--out' in A else \
    '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/export_measure.json'
T0 = time.time()


def log(*a):
    print('[r3_measure %5.0fs]' % (time.time() - T0), *a, flush=True)


bpy.ops.wm.open_mainfile(filepath=BLEND)
arm = bpy.data.objects['Armature']


def arrays(ob):
    me = ob.data
    nV, nP, nL = len(me.vertices), len(me.polygons), len(me.loops)
    co = np.empty(nV * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    M = np.array(ob.matrix_world); co = co @ M[:3, :3].T + M[:3, 3]
    ls = np.empty(nP, np.int64); me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(nP, np.int64); me.polygons.foreach_get('loop_total', lt)
    lv = np.empty(nL, np.int64); me.loops.foreach_get('vertex_index', lv)
    mark = np.zeros(nP, bool); me.polygons.foreach_get('use_freestyle_mark', mark)
    mi = np.empty(nP, np.int64); me.polygons.foreach_get('material_index', mi)
    area = np.empty(nP); me.polygons.foreach_get('area', area)
    me.calc_loop_triangles()
    tl = np.empty(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get('loops', tl)
    tp = np.empty(len(me.loop_triangles), np.int64); me.loop_triangles.foreach_get('polygon_index', tp)
    cn = np.empty(nL * 3); me.corner_normals.foreach_get('vector', cn) if hasattr(me, 'corner_normals') else None
    cn = cn.reshape(-1, 3)
    uvs = {}
    for u in me.uv_layers:
        a = np.empty(nL * 2); u.data.foreach_get('uv', a); uvs[u.name] = a.reshape(-1, 2)
    return dict(co=co, ls=ls, lt=lt, lv=lv, mark=mark, mi=mi, area=area, tl=tl.reshape(-1, 3), tp=tp, cn=cn, uvs=uvs,
                mats=[m.name if m else None for m in me.materials])


def render_verts(d, uv=None):
    """unique (vertex, rounded corner normal[, uv]) = what an engine keeps as separate vertices"""
    k = [d['lv'][:, None].astype(np.float64), np.round(d['cn'], 3)]
    if uv is not None:
        k.append(np.round(uv, 5))
    return int(len(np.unique(np.hstack(k), axis=0)))


def pieces(d):
    nV = len(d['co'])
    par = np.arange(nV)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for s, t in zip(d['ls'].tolist(), d['lt'].tolist()):
        vs = d['lv'][s:s + t]
        r0 = find(int(vs[0]))
        for q in vs[1:].tolist():
            rq = find(q)
            if rq != r0:
                par[rq] = r0
    root = np.array([find(i) for i in range(nV)])
    pid = root[d['lv'][d['ls']]]
    lo = np.full((nV, 3), np.inf); hi = np.full((nV, 3), -np.inf)
    np.minimum.at(lo, root, d['co']); np.maximum.at(hi, root, d['co'])
    diag = np.linalg.norm(hi - lo, axis=1)
    return pid, diag      # diag indexed by root id


def pct(x, w, qs=(5, 10, 25, 50, 75, 90, 95)):
    o = np.argsort(x); x, w = x[o], w[o]
    c = np.cumsum(w) / w.sum()
    return {str(q): round(float(np.interp(q / 100.0, c, x)), 2) for q in qs}


rep = dict(blend=BLEND, about=__doc__.strip().splitlines()[0])

# ------------------------------------------------------------------ SM_Airship
sm = bpy.data.objects['SM_Airship']
d = arrays(sm)
uv = d['uvs'][list(d['uvs'])[0]]
tri_uv = uv[d['tl']]
uva = 0.5 * np.abs((tri_uv[:, 1, 0] - tri_uv[:, 0, 0]) * (tri_uv[:, 2, 1] - tri_uv[:, 0, 1]) -
                   (tri_uv[:, 2, 0] - tri_uv[:, 0, 0]) * (tri_uv[:, 1, 1] - tri_uv[:, 0, 1]))
tri_co = d['co'][d['lv'][d['tl']]]
a3 = 0.5 * np.linalg.norm(np.cross(tri_co[:, 1] - tri_co[:, 0], tri_co[:, 2] - tri_co[:, 0]), axis=1)
ok = a3 > 1e-8
dens = {}
for res in (1024, 2048, 4096, 8192):
    t = np.sqrt(uva[ok] * res * res / a3[ok])
    dens[str(res)] = pct(t, a3[ok])
rep['sm_airship'] = dict(
    faces=int(len(d['ls'])), tris=int(len(d['tl'])), verts=int(len(d['co'])), uv_maps=list(d['uvs']), materials=d['mats'],
    area_m2=round(float(a3.sum()), 1), uv_area_used=round(float(uva.sum()), 4),
    texels_per_m_area_weighted=dens,
    texels_per_m_note='texel density = sqrt(UV area * res^2 / 3D area) per triangle, area-weighted percentiles',
    render_verts_est=render_verts(d, uv), bbox_min=np.round(d['co'].min(0), 3).tolist(), bbox_max=np.round(d['co'].max(0), 3).tolist())
log('SM_Airship', rep['sm_airship']['tris'], 'tris, area', rep['sm_airship']['area_m2'], 'density@4096', dens['4096'])

# ------------------------------------------------------------------ details
dets = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('SM_AirshipDetail_')], key=lambda o: o.name)
rep['details'] = {}
tot = dict(tris=0, verts=0, rv=0, area=0.0)
group = {}
rivet_sizes = []
for ob in dets:
    d = arrays(ob)
    gnames = {g.index: g.name for g in ob.vertex_groups}
    # bone of each vertex (rigid skin)
    vb = []
    for v in ob.data.vertices:
        gs = [g for g in v.groups if g.weight > 0.5]
        vb.append(gnames[gs[0].group] if gs else '?')
    vb = np.array(vb)
    bones = sorted(set(vb.tolist()))
    hull = bones == ['Hull']
    pid, diag = pieces(d)
    pdiag = diag[pid]
    tri_area = d['area'][d['tp']] / np.maximum(1, (d['lt'][d['tp']] - 2))
    rv_p = d['mark']
    cls_p = np.where(rv_p, 'rivet', np.where(pdiag < 0.15, 'lt15cm', np.where(pdiag < 0.6, '15to60cm', 'ge60cm')))
    area_by = {c: round(float(d['area'][cls_p == c].sum()), 2) for c in ('rivet', 'lt15cm', '15to60cm', 'ge60cm')}
    tris_by = {c: int(np.sum(cls_p[d['tp']] == c)) for c in ('rivet', 'lt15cm', '15to60cm', 'ge60cm')}
    roots = np.unique(pid)
    npieces = {c: int(len(np.unique(pid[cls_p == c]))) for c in ('rivet', 'lt15cm', '15to60cm', 'ge60cm')}
    rroots = np.unique(pid[rv_p])
    rivet_sizes += diag[rroots].tolist()
    mat_area = {}
    for k, m in enumerate(d['mats']):
        mat_area[m] = round(float(d['area'][d['mi'] == k].sum()), 2)
    rvn = render_verts(d)
    e = dict(bones=bones if len(bones) <= 4 else bones[:4] + ['... %d bones' % len(bones)], hull_bone=hull,
             tris=int(len(d['tl'])), verts=int(len(d['co'])), render_verts_est=rvn, faces=int(len(d['ls'])),
             area_m2=round(float(d['area'].sum()), 2), area_by_class=area_by, tris_by_class=tris_by, pieces=npieces,
             area_by_material=mat_area, uv_maps=list(d['uvs']))
    rep['details'][ob.name] = e
    gk = 'Hull' if hull else 'moving'
    g = group.setdefault(gk, dict(objects=0, tris=0, verts=0, render_verts_est=0, area_m2=0.0,
                                  area_by_class={c: 0.0 for c in area_by}, tris_by_class={c: 0 for c in tris_by}))
    g['objects'] += 1; g['tris'] += e['tris']; g['verts'] += e['verts']; g['render_verts_est'] += rvn
    g['area_m2'] += e['area_m2']
    for c in area_by:
        g['area_by_class'][c] += area_by[c]; g['tris_by_class'][c] += tris_by[c]
    log('%-36s %7d tris %7d rverts %8.1f m2  %s' % (ob.name, e['tris'], rvn, e['area_m2'], area_by))
for g in group.values():
    g['area_m2'] = round(g['area_m2'], 1)
    g['area_by_class'] = {k: round(v, 1) for k, v in g['area_by_class'].items()}
rep['detail_groups'] = group
rs = np.array(rivet_sizes)
rep['rivet_pieces'] = dict(count=int(len(rs)), diag_m=pct(rs, np.ones(len(rs)), (5, 50, 95)) if len(rs) else None)

# ------------------------------------------------------------------ atlas sizing (non-rivet detail area)
sizing = {}
for gk, g in group.items():
    a = g['area_m2'] - g['area_by_class']['rivet']
    a_lod2 = g['area_by_class']['ge60cm']
    rows = {}
    for D_ in (32, 48, 64, 96, 128, 192, 256):
        for eff in (0.6, 0.7):
            tex = a * D_ * D_ / eff
            rows['%d t/m, eff %.1f' % (D_, eff)] = dict(texels_M=round(tex / 1e6, 2), side=int(math.ceil(math.sqrt(tex))),
                                                       pages_4096=round(tex / 4096 ** 2, 2), pages_8192=round(tex / 8192 ** 2, 2))
    sizing[gk] = dict(non_rivet_area_m2=round(a, 1), ge60cm_area_m2=round(a_lod2, 1), rows=rows)
rep['atlas_sizing'] = sizing
rep['seconds'] = round(time.time() - T0, 1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w') as f:
    json.dump(rep, f, indent=1)
log('groups', json.dumps(group))
log('rivets', rep['rivet_pieces'])
log('wrote', OUT)
