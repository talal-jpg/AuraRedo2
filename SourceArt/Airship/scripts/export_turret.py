"""Round 2: export the front machine-gun turret as two static meshes for Unreal and write turret_dims.json.

  blender -b --factory-startup --python rig/scripts/export_turret.py

Input : rig/props/AirshipProps.blend (Turret_Base / Turret_Gun with their atlas UVs, M_AirshipProps; never saved),
        checks/rig/placement.json (turret mounts measured on the ship), bones_blender.json and skin_report.json
        (rig_build.py: helm, pilot seat, removed deck pieces).
Output: export/SM_AirshipTurret_Base.fbx, export/SM_AirshipTurret_Gun.fbx, checks/rig/turret_dims.json.

FBX conventions = rig_export.py (the SK): centimetres in the data and in the file (UnitScaleFactor 1), Y-up file with
the data pre-rotated so the mesh node is the identity, so in Unreal X = forward (the gun fires +X), Z = up, Blender +Y
(the gun's left) = UE -Y; smoothing by face, normals per corner, no tangents, one UV channel, one material slot
M_AirshipProps; no armature, no UCX (AAirshipTurret's HitBox is the collision). Pivot = the object origin:
Turret_Base at the yaw axis on the deck (z 0 = deck top), Turret_Gun at the trunnion (pitch) axis centre.
"""
import bpy, sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Matrix, Vector as V
import rig_common as C

PARTS = {'Turret_Base': 'SM_AirshipTurret_Base', 'Turret_Gun': 'SM_AirshipTurret_Gun'}
OUT_JSON = C.CHECKS + '/turret_dims.json'

bpy.ops.wm.open_mainfile(filepath=C.PROPS_BLEND)
sc = bpy.context.scene
base, gun, muz = (bpy.data.objects[n] for n in ('Turret_Base', 'Turret_Gun', 'Turret_Muzzle'))
assert muz.parent == gun
assert tuple(base.rotation_euler) == (0, 0, 0) and tuple(gun.rotation_euler) == (0, 0, 0)
assert tuple(base.scale) == (1, 1, 1) and tuple(gun.scale) == (1, 1, 1)
pivot = gun.location - base.location
assert abs(pivot.x) < 1e-6 and abs(pivot.y) < 1e-6, pivot
muzzle_local = V(muz.location)


def local_co(o):
    a = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get('co', a)
    return a.reshape(-1, 3)


cb, cg = local_co(base), local_co(gun)
for o in (base, gun):
    assert [m.name for m in o.data.materials] == ['M_AirshipProps'], (o.name, [m.name for m in o.data.materials])
    assert [u.name for u in o.data.uv_layers] == ['UVMap'], (o.name, [u.name for u in o.data.uv_layers])

# ------------------------------------------------------------------ export (one FBX per part, pivot = object origin)
S = Matrix.Scale(100.0, 4)
RX = Matrix.Rotation(math.radians(90), 4, 'X')
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 0.01
os.makedirs(C.EXPORT, exist_ok=True)
files = {}
for src, name in PARTS.items():
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    o = bpy.data.objects[src]
    me = o.data.copy()
    me.name = name
    me.transform(RX.inverted() @ S)              # local metres -> cm, Z-up data -> the file's Y-up (pre-rotated)
    ex = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ex)
    ex.matrix_world = RX                         # with the exporter's Y-up conversion: identity node in the file
    ex.select_set(True)
    bpy.context.view_layer.objects.active = ex
    bpy.context.view_layer.update()
    path = os.path.join(C.EXPORT, name + '.fbx')
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={'MESH'},
        global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
        use_space_transform=True, bake_space_transform=False, axis_forward='-Z', axis_up='Y',
        use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, use_triangles=False,
        use_custom_props=False, add_leaf_bones=False, path_mode='STRIP', embed_textures=False, bake_anim=False)
    files[name] = dict(path=path, bytes=os.path.getsize(path), verts=len(me.vertices),
                       tris=sum(len(p.vertices) - 2 for p in me.polygons))
    print('[turret] exported', path, files[name])

# ------------------------------------------------------------------ dims for Unreal (cm, UE axes)
P = C.load_json(C.PLACEMENT_JSON)
bones = {r['bone']: r for r in C.load_json(C.CHECKS + '/bones_blender.json')['bones']}
skin = C.load_json(C.CHECKS + '/skin_report.json')
TU = P['turrets']
rb = np.hypot(cb[:, 0], cb[:, 1])
r2 = lambda v: round(float(v), 2)
ue_vec = lambda v: [r2(100 * v[0]), r2(-100 * v[1]) + 0.0, r2(100 * v[2])]


def ue_bbox(co):
    """[min, max] in UE axes (Y flips, so Blender's max Y is UE's min Y)"""
    u = co * np.array((100.0, -100.0, 100.0))
    return [[r2(x) + 0.0 for x in u.min(0)], [r2(x) + 0.0 for x in u.max(0)]]

helm_wheel = bpy.data.objects['Helm_Wheel']
cw = local_co(helm_wheel)
D = dict(
    about='Round 2 turret + helm numbers for Unreal (UE component / hull space, cm). Written by export_turret.py.',
    pivot_height_cm=r2(100 * pivot.z),
    muzzle_forward_cm=r2(100 * muzzle_local.x),
    muzzle_offset_cm=ue_vec(muzzle_local),
    barrel_offsets_y_cm=[-10.0, 10.0],
    base_radius_cm=r2(100 * rb.max()),
    base_height_cm=r2(100 * cb[:, 2].max()),
    base_bbox_cm=ue_bbox(cb),
    base_bounds_cm=dict(zip(('min', 'max'), ue_bbox(cb))),       # the same, in the form as_53_turret_import.py reads
    gun_length_cm=r2(100 * (cg[:, 0].max() - cg[:, 0].min())),
    gun_bbox_cm=ue_bbox(cg),
    gun_bounds_cm=dict(zip(('min', 'max'), ue_bbox(cg))),
    gun_rear_extent_cm=r2(-100 * cg[:, 0].min()),
    hitbox_suggestion=dict(extent_cm=[r2(100 * rb.max()), r2(100 * rb.max()), r2(50 * cb[:, 2].max())],
                           centre_z_cm=r2(50 * cb[:, 2].max()),
                           note='box round the yaw part (base + shield); the gun swings above and ahead of it'),
    pitch_range_deg=[-20.0, 40.0],
    axes='BaseMesh yaws about its origin (the mount on the deck, Z up); GunMesh at (0, 0, pivot_height_cm) on '
         'BaseMesh pitches about its Y (+ = muzzle up); the muzzle is at (muzzle_forward_cm, 0, 0) on GunMesh, '
         'between the two barrels; the ammo crate is on the turret\'s left (UE -Y)',
    mounts={},
    deck_top_cm_at_mounts={},
    rail_top_cm=None, rail_inner_y_cm=None,
    pilot_seat_ue=bones['PilotSeat']['head_ue_cm'],
    helm_ue=bones['Helm']['head_ue_cm'],
    helm_wheel_ue=bones['Helm_Wheel']['head_ue_cm'],
    helm_wheel_size_cm=[r2(100 * (cw[:, i].max() - cw[:, i].min())) for i in range(3)],
    helm_wheel_offset_from_helm_cm=ue_vec(C.HELM_WHEEL_OFS),
    pilot_behind_axle_cm=r2(100 * C.PILOT_BEHIND_AXLE),
    removed_islands=skin['deck_removal']['removed_islands'],
    removed=dict((k, skin['deck_removal'][k]) for k in ('removed_verts', 'removed_tris', 'kept_verts', 'kept_tris')),
    removed_pieces=[dict(arrow=p['arrow'], name=p['name'], islands=p['islands']) for p in skin['deck_removal']['pieces']],
    cannon_bore_radius_cm=22.0, cannon_muzzle_face_radius_cm=25.0,
    files=files,
)
for side, t in TU.items():
    idx = 0 if side == 'L' else 1
    D['mounts'][side] = dict(turret_index=idx, station=4 + idx, location_cm=t['mount_ue_cm'],
                             yaw_limits_deg=t['yaw_limits_ue'], gunner_seat_cm=t['seat_ue_cm'],
                             base_to_rail_gap_cm=r2(100 * t['base_to_rail_gap']) if t['base_to_rail_gap'] is not None else None,
                             sweep_contacts=t['sweep_contacts'])
    D['deck_top_cm_at_mounts'][side] = r2(t['mount_ue_cm'][2])
    if t['rail_top_above_deck'] is not None:
        D['rail_top_cm'] = r2(t['mount_ue_cm'][2] + 100 * t['rail_top_above_deck'])
    if t['rail_inner_abs_y'] is not None:
        D['rail_inner_y_cm'] = r2(100 * t['rail_inner_abs_y'])
C.dump_json(D, OUT_JSON)
print('[turret] wrote', OUT_JSON, {k: D[k] for k in ('pivot_height_cm', 'muzzle_forward_cm', 'base_radius_cm',
                                                     'deck_top_cm_at_mounts', 'rail_top_cm', 'rail_inner_y_cm',
                                                     'pilot_seat_ue', 'helm_wheel_ue', 'helm_wheel_size_cm')})
for side, m in D['mounts'].items():
    print('[turret] mount', side, m['location_cm'], 'yaw', m['yaw_limits_deg'], 'rail gap cm', m['base_to_rail_gap_cm'],
          'sweep contacts', len(m['sweep_contacts']))
