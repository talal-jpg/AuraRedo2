"""Props in SK_Airship.fbx vs the baked-atlas source rig/props/AirshipProps.blend (open a COPY, never saved):
per-corner UVs identical (so the baked T_AirshipProps_* maps fit), same topology, rigid placement (Kabsch residual).

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
json.dump(rep, open(OUT, 'w'), indent=1)
print('[verify_props] defects:', rep['defects'] or 'none', '| max uv delta', max(r['uv_max_delta'] for r in rep['props'].values()),
      '| max rigid residual', max(r['rigid_residual_m'] for r in rep['props'].values()))
