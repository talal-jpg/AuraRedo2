"""Props in SK_Airship.fbx vs the baked-atlas source rig/props/AirshipProps.blend (open a COPY, never saved):
per-corner UVs identical (so the baked T_AirshipProps_* maps fit), same topology, rigid placement (Kabsch residual).
Round 2: the turret static meshes export/SM_AirshipTurret_Base.fbx / _Gun.fbx against Turret_Base / Turret_Gun the same
way, plus their file conventions (UnitScaleFactor 1, the SK's axes, identity node, one UV channel, material
M_AirshipProps) and the pivot (vertices = the object's local coordinates, so the FBX origin is the object origin).

  cp rig/props/AirshipProps.blend rig/tmp/verify/AirshipProps_copy.blend
  blender -b --factory-startup rig/tmp/verify/AirshipProps_copy.blend --python rig/scripts/verify_props.py -- [--fbx F]
"""
import bpy, sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_fbxlib as F
from io_scene_fbx.fbx_utils import RIGHT_HAND_AXES
from bpy_extras.io_utils import axis_conversion

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
FBX = argv[argv.index('--fbx') + 1] if '--fbx' in argv else RIG + '/export/SK_Airship.fbx'
OUT = RIG + '/checks/verify/props_verify.json'
sc = F.load(FBX)
gs = sc.global_settings
key = ((int(gs['UpAxis']), int(gs['UpAxisSign'])), (int(gs['FrontAxis']), int(gs['FrontAxisSign'])), (int(gs['CoordAxis']), int(gs['CoordAxisSign'])))
up, fw = {v: k for k, v in RIGHT_HAND_AXES.items()}[key]
CV = np.array(axis_conversion(from_forward=fw, from_up=up))
TOM = float(gs['UnitScaleFactor']) * 0.01
geom_of = {}
for kind, ch, pa, pn in sc.conns:
    if ch in sc.geoms and pa in sc.models:
        geom_of[sc.models[pa]['name']] = ch
rep = {'defects': [], 'props': {}}
for name, gu in sorted(geom_of.items()):
    if name == 'SM_Airship':
        continue
    src = name.replace('SM_AirshipProp_', '')
    src = 'Cannon_' + '_'.join(src.split('_')[2:]) if src.startswith('Cannon_') else src
    o = bpy.data.objects[src]
    me = o.data
    gd = F.geometry_data(sc.geoms[gu])
    uid = [u for u, m in sc.models.items() if m['name'] == name][0]
    G = np.array(F.global_matrix(sc, uid))
    V = np.array(gd['vertices']).reshape(-1, 3)
    Vw = ((CV @ G[:3, :3]) @ V.T).T + CV @ G[:3, 3]
    Vw *= TOM
    S = np.array([tuple(o.matrix_world @ v.co) for v in me.vertices])
    pvi = np.array(gd['pvi']); cv = np.where(pvi < 0, ~pvi, pvi)
    topo = len(cv) == len(me.loops) and np.array_equal(cv, np.array([l.vertex_index for l in me.loops]))
    fuv = np.array(F.per_corner_uv(gd['uv'][0])); suv = np.array([tuple(d.uv) for d in me.uv_layers[0].data])
    uvd = float(np.abs(fuv - suv).max()) if len(fuv) == len(suv) else None
    # Kabsch: S (source, cannon/helm frame) -> Vw (ship)
    cs, cw = S.mean(0), Vw.mean(0)
    H = (S - cs).T @ (Vw - cw)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    resid = float(np.linalg.norm((R @ (S - cs).T).T + cw - Vw, axis=1).max())
    rec = {'verts': len(V), 'src_verts': len(S), 'topology_same': bool(topo), 'uv_max_delta': uvd, 'rigid_residual_m': resid}
    rep['props'][name] = rec
    if not topo or uvd is None or uvd > 1e-6 or resid > 1e-4:
        rep['defects'].append('%s vs %s: %s' % (name, src, rec))

# ---------------------------------------------------------------- round 2: turret static meshes
TUR = {'SM_AirshipTurret_Base': 'Turret_Base', 'SM_AirshipTurret_Gun': 'Turret_Gun'}
rep['turrets'] = {}
for fname, src in TUR.items():
    path = os.path.join(os.path.dirname(FBX), fname + '.fbx')
    if not os.path.exists(path):
        rep['defects'].append('%s missing' % path)
        continue
    ts = F.load(path)
    g = ts.global_settings
    k2 = ((int(g['UpAxis']), int(g['UpAxisSign'])), (int(g['FrontAxis']), int(g['FrontAxisSign'])), (int(g['CoordAxis']), int(g['CoordAxisSign'])))
    mods = [(u, m) for u, m in ts.models.items() if m['type'] == 'Mesh']
    rec = {'file': path, 'unit_scale_factor': float(g['UnitScaleFactor']), 'axes_same_as_sk': k2 == key,
           'mesh_nodes': [m['name'] for _, m in mods],
           'other_nodes': sorted({m['type'] for m in ts.models.values()} - {'Mesh'})}
    if len(mods) != 1 or mods[0][1]['name'] != fname:
        rep['defects'].append('%s mesh nodes %s' % (fname, rec['mesh_nodes']))
        rep['turrets'][fname] = rec
        continue
    uid = mods[0][0]
    gu = [ch for kind, ch, pa, pn in ts.conns if ch in ts.geoms and pa == uid][0]
    mats = [ts.materials[ch]['name'] for kind, ch, pa, pn in ts.conns if ch in ts.materials and pa == uid]
    G = np.array(F.global_matrix(ts, uid))
    Gc = CV @ G[:3, :3]
    rec['node_is_identity'] = float(np.abs(G - np.eye(4)).max())     # data pre-rotated like the SK's mesh nodes
    gd = F.geometry_data(ts.geoms[gu])
    Vf = ((Gc @ np.array(gd['vertices']).reshape(-1, 3).T).T + CV @ G[:3, 3]) * float(g['UnitScaleFactor']) * 0.01
    o = bpy.data.objects[src]
    me = o.data
    S = np.array([tuple(v.co) for v in me.vertices])          # object-local metres: the pivot is the object origin
    pvi = np.array(gd['pvi']); cv = np.where(pvi < 0, ~pvi, pvi)
    topo = len(cv) == len(me.loops) and np.array_equal(cv, np.array([l.vertex_index for l in me.loops]))
    fuv = np.array(F.per_corner_uv(gd['uv'][0])); suv = np.array([tuple(d.uv) for d in me.uv_layers[0].data])
    rec.update(verts=len(Vf), src_verts=len(S), topology_same=bool(topo), materials=mats, uv_layers=len(gd['uv']),
               uv_max_delta=float(np.abs(fuv - suv).max()) if len(fuv) == len(suv) else None,
               pos_max_delta_m=float(np.abs(Vf - S).max()) if len(Vf) == len(S) else None,
               uv_range=[fuv.min(0).round(4).tolist(), fuv.max(0).round(4).tolist()],
               bbox_cm=[(Vf.min(0) * 100).round(2).tolist(), (Vf.max(0) * 100).round(2).tolist()])
    rep['turrets'][fname] = rec
    bad = (abs(rec['unit_scale_factor'] - 1) > 1e-6 or not rec['axes_same_as_sk'] or rec['other_nodes'] or
           rec['node_is_identity'] > 1e-5 or not topo or rec['uv_layers'] != 1 or mats != ['M_AirshipProps'] or
           rec['uv_max_delta'] is None or rec['uv_max_delta'] > 1e-6 or rec['pos_max_delta_m'] is None or
           rec['pos_max_delta_m'] > 1e-4 or fuv.min() < -1e-6 or fuv.max() > 1 + 1e-6)
    if bad:
        rep['defects'].append('%s vs %s: %s' % (fname, src, rec))
json.dump(rep, open(OUT, 'w'), indent=1)
print('[verify_props] defects:', rep['defects'] or 'none', '| max uv delta', max(r['uv_max_delta'] for r in rep['props'].values()),
      '| max rigid residual', max(r['rigid_residual_m'] for r in rep['props'].values()),
      '| turrets', {k: (v.get('uv_max_delta'), v.get('pos_max_delta_m')) for k, v in rep['turrets'].items()})
