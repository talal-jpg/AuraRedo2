"""Step 5: export SK_Airship.fbx (rest, no animation) and SK_Airship_testanim.fbx (+ the test sweep) for Unreal.

  blender -b --factory-startup --python rig/scripts/rig_export.py -- [--anim] [--out FILE.fbx]

Never saves the .blend. Burrower route (_AirshipWork_logs/burrower_rig_src/model/rig/export_ue.py):
* centimetres in the data and in the file (UnitScaleFactor 1), so UE imports 1:1;
* the armature node is named "Armature" (UE's FBX importer drops it), root bone `root`;
* Y-up file with the data pre-rotated so the Armature and mesh nodes have identity transforms;
* head (bow) toward +X and Z up in UE after its axis conversion; no leaf bones; smoothing by face (as SM_Airship.fbx);
* one deviation from the Burrower settings: primary_bone_axis 'Z' / secondary 'X' instead of 'Y' / 'X'. Our Blender
  bones point +Z (contract: tail = head + (0, 0, 0.5), roll 0); with this bone-axis mapping every joint is written
  with the orientation that UE's Y-up -> Z-up scene conversion turns into the identity, so in UE every bone has the
  same (identity) rest rotation as `root` and its local axes are the component axes (contract section 3).

Round 3 (2026-11-28, Docs/Airship/round3/EXPORT_R3.md sections 1, 4, 5), only with --round3 (alias --r3):
  blender -b --factory-startup --python rig_export.py -- --round3 [--lod 0|1|2] [--out FILE.fbx]
  reads rig/detail/r3export/AirshipR3_export.blend (r3_prep.py; never saved) instead of rig/AirshipRig.blend and exports
  32 meshes: SM_Airship (base edits applied; UV0 Talal's, UV1 R3Palette, UV2 R3Ink), the 30 props (UV0 atlas, UV1
  R3Palette) and SM_AirshipR3Detail_Moving (--lod 1 / 2: its _LOD1 / _LOD2 object instead) to
  rig/detail/r3export/fbx/SK_Airship.fbx (SK_Airship_LOD1.fbx / _LOD2.fbx). Same armature, transforms and FBX settings
  as round 2; the Hull-bone details (SM_AirshipR3_HullDetail) and the turrets are static meshes (r3_export_static.py).
  Without --round3 nothing below changes: round 2's rig/AirshipRig.blend, 31 meshes, rig/export/.
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mathutils import Matrix
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ANIM = '--anim' in argv
R3 = '--round3' in argv or '--r3' in argv
R3_LOD = int(argv[argv.index('--lod') + 1]) if '--lod' in argv else 0
if R3:
    import r3_common as RC
    assert not ANIM, 'round 3 has no test sweep export: the skeleton is unchanged (use the round 2 testanim FBX)'
    assert R3_LOD in (0, 1, 2), R3_LOD
    OUT = argv[argv.index('--out') + 1] if '--out' in argv else \
        os.path.join(RC.OUT, 'fbx', 'SK_Airship.fbx' if R3_LOD == 0 else 'SK_Airship_LOD%d.fbx' % R3_LOD)
    RC.check_out_path(OUT)
else:
    OUT = argv[argv.index('--out') + 1] if '--out' in argv else \
        os.path.join(C.EXPORT, 'SK_Airship_testanim.fbx' if ANIM else 'SK_Airship.fbx')

bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND if R3 else C.RIG_BLEND)
sc = bpy.context.scene
arm = bpy.data.objects['Armature']
if R3:
    # the export blend also holds the HullDetail static mesh, the LOD variants and the turrets: pick by name
    r3_names = sorted([o.name for o in bpy.data.objects if o.type == 'MESH' and
                       (o.name == C.HULL_OBJ or o.name.startswith(C.PROP_PREFIX))]) + \
        [RC.MOVING + ('_LOD%d' % R3_LOD if R3_LOD else '')]
    meshes = [bpy.data.objects[n] for n in r3_names]
    for o in meshes:
        assert o.parent == arm and any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers), o.name
    assert len(meshes) == 32, len(meshes)
    assert [o.name for o in meshes] == sorted(o.name for o in meshes), [o.name for o in meshes]   # FBX order = slot order
    assert meshes[0].name == C.HULL_OBJ and meshes[-1].name.startswith(RC.MOVING)
    assert [m.name for m in meshes[0].data.materials] == [RC.MAT_HULL]
    assert all([m.name for m in o.data.materials] == [RC.MAT_PROPS] for o in meshes[1:-1])
    assert [m.name for m in meshes[-1].data.materials] == [RC.MAT_DETAIL]
    assert [u.name for u in meshes[0].data.uv_layers] == [RC.UV_INK, RC.UV_PAL, RC.UV_HULL_INK]
    assert all([u.name for u in o.data.uv_layers] == [RC.UV_INK, RC.UV_PAL] for o in meshes[1:])
    # objects in layer collections that are excluded cannot be selected: include the ones holding the export objects
    _st = [bpy.context.view_layer.layer_collection]
    _want = {c.name for o in [arm] + meshes for c in o.users_collection}
    while _st:
        _l = _st.pop()
        if _l.collection.name in _want:
            _l.exclude = False; _l.hide_viewport = False; _l.collection.hide_viewport = False
        _st += list(_l.children)
    print('[export] round 3: %d meshes, LOD %d -> %s' % (len(meshes), R3_LOD, OUT))
else:
    meshes = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm and
                     any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)], key=lambda o: o.name)
    assert len(meshes) == 31, len(meshes)
assert meshes[0].name == C.HULL_OBJ    # sorted first -> its material M_Airship becomes slot 0
bpy.context.view_layer.objects.active = arm
if arm.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
for o in bpy.context.view_layer.objects:
    o.select_set(False)
for o in [arm] + meshes:
    o.hide_set(False); o.hide_viewport = False; o.select_set(True)
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
act = bpy.data.actions.get('SK_Airship_TestSweep')
if arm.animation_data:
    arm.animation_data.action = None
if ANIM:
    sc.name = 'SK_Airship_TestSweep'      # the FBX take / anim stack name
    arm.animation_data_create()
    arm.animation_data.action = act
    # pose translations are in bone-local metres; the data goes to cm below, so scale the location curves by 100
    try:
        fcs = list(act.fcurves)
    except Exception:
        fcs = []
    if not fcs:
        fcs = [fc for L in act.layers for s in L.strips for cb in s.channelbags for fc in cb.fcurves]
    n = 0
    for fc in fcs:
        if fc.data_path.endswith('.location'):
            for k in fc.keyframe_points:
                k.co.y *= 100.0; k.handle_left.y *= 100.0; k.handle_right.y *= 100.0
            n += 1
    print('[export] scaled', n, 'location curves of', len(fcs))
else:
    arm.animation_data_clear()

# metres -> centimetres in the data; Blender unit = 1 cm so the exporter writes UnitScaleFactor 1
S = Matrix.Scale(100.0, 4)
RX = Matrix.Rotation(math.radians(90), 4, 'X')
mesh_world = {o.name: o.matrix_world.copy() for o in meshes}
arm.data.transform(RX.inverted() @ S @ arm.matrix_world)
arm.matrix_world = RX
for o in meshes:
    o.data.transform(RX.inverted() @ S @ mesh_world[o.name])
    o.parent = arm; o.matrix_parent_inverse.identity(); o.matrix_world = RX
sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 0.01
arm.name = 'Armature'; arm.data.name = 'Armature'
bpy.context.view_layer.update()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.export_scene.fbx(
    filepath=OUT, use_selection=True, object_types={'ARMATURE', 'MESH'},
    global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
    use_space_transform=True, bake_space_transform=False, axis_forward='-Z', axis_up='Y',
    use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, use_triangles=False,
    use_custom_props=False, add_leaf_bones=False, primary_bone_axis='Z', secondary_bone_axis='X',
    use_armature_deform_only=False, armature_nodetype='NULL', path_mode='STRIP', embed_textures=False,
    bake_anim=ANIM, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
    bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0)
print('[export]', OUT, os.path.getsize(OUT), 'bytes', 'anim' if ANIM else 'rest')
