"""Round 3 export: the static meshes for Unreal (Docs/Airship/round3/EXPORT_R3.md sections 1, 4, 5 and 13.7).

  blender_capped.sh --python SourceArt/Airship/scripts/r3_export_static.py -- [--only hull|turrets] [--lod 0,1,2]

Reads rig/detail/r3export/AirshipR3_export.blend (r3_prep.py; never saved) and writes rig/detail/r3export/fbx/:
  SM_AirshipR3_HullDetail.fbx, _LOD1.fbx, _LOD2.fbx   the 12 Hull-bone detail objects merged (r3_prep), no armature, no
        skin: its vertices sit where the SK's Hull bone puts them, so in Unreal the static mesh is a component under the
        SK component (socket Hull: the Hull bone is at the origin with an identity rest pose). Vertices in UE component
        cm = (100 x, -100 y, 100 z) of Blender metres.
  SM_AirshipTurret_Base.fbx, SM_AirshipTurret_Gun.fbx   the two turret meshes from the export blend (collection
        R3_Turrets, appended there by r3_prep from rig/props/AirshipProps.blend): the same frames as round 2's
        export_turret.py (pivot = the object origin: the base at the yaw axis on the deck, the gun at the trunnion), now
        with UV1 R3Palette (palette slots 18 / 19) for MI_AirshipR3_Props.
FBX conventions = rig_export.py / export_turret.py: centimetres in the data and in the file (UnitScaleFactor 1), Y-up
file with the data pre-rotated so the mesh node is the identity, smoothing by face, normals per corner, no tangents, no
custom properties. Every mesh keeps all its UV layers (UVMap = the ink atlas, R3Palette = the palette index) and its
one material slot (M_AirshipR3_Detail / M_AirshipProps). Report: r3export/checks/export_static.json.
"""
import bpy, sys, os, math, json, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Matrix
import r3_common as RC

A = RC.argv()
ONLY = RC.arg(A, '--only', 'hull,turrets').split(',')
LODS = [int(x) for x in RC.arg(A, '--lod', '0,1,2').split(',')]
FBX_DIR = RC.OUT + '/fbx'
log = RC.Log('r3_export_static')
rep = dict(started=time.strftime('%Y-%m-%d %H:%M:%S'), protected_start=RC.protected_state(), files={})
RC.check_out_path(FBX_DIR + '/x.fbx')
os.makedirs(FBX_DIR, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND)
rep['export_blend_md5'] = RC.md5_file(RC.EXPORT_BLEND)
sc = bpy.context.scene
S = Matrix.Scale(100.0, 4)
RX = Matrix.Rotation(math.radians(90), 4, 'X')
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 0.01
ex_coll = bpy.data.collections.new('R3_StaticExport')
sc.collection.children.link(ex_coll)


def export_one(src, name, local, path):
    """a fresh object with a copy of src's mesh (no vertex groups, no modifiers, no parent), data -> cm Y-up, node = RX"""
    RC.check_out_path(path)
    if src.name == name:
        src.name = name + '_r3src'                     # in memory only: the exported object takes the real name
    me = src.data.copy()
    me.name = name
    M = (RX.inverted() @ S) if local else (RX.inverted() @ S @ src.matrix_world)
    me.transform(M)
    ex = bpy.data.objects.new(name, me)
    ex_coll.objects.link(ex)
    ex.vertex_groups.clear()
    ex.matrix_world = RX
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ex.select_set(True)
    bpy.context.view_layer.objects.active = ex
    bpy.context.view_layer.update()
    assert ex.name == name, (ex.name, name)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={'MESH'},
        global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
        use_space_transform=True, bake_space_transform=False, axis_forward='-Z', axis_up='Y',
        use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, use_triangles=False,
        use_custom_props=False, add_leaf_bones=False, path_mode='STRIP', embed_textures=False, bake_anim=False)
    r = dict(path=path, bytes=os.path.getsize(path), md5=RC.md5_file(path), source=src.name, verts=len(me.vertices),
             faces=len(me.polygons), tris=int(sum(len(p.vertices) - 2 for p in me.polygons)),
             uv_layers=[u.name for u in me.uv_layers], materials=[m.name for m in me.materials], local_frame=local)
    log('exported', os.path.basename(path), {k: r[k] for k in ('verts', 'tris', 'uv_layers', 'materials')})
    bpy.data.objects.remove(ex)
    return r


if 'hull' in ONLY:
    for lod in LODS:
        src = bpy.data.objects[RC.HULLDET + ('_LOD%d' % lod if lod else '')]
        assert np.allclose(np.array(src.matrix_world), np.eye(4)), src.name      # merged in world space (r3_prep)
        assert [m.name for m in src.data.materials] == [RC.MAT_DETAIL], [m.name for m in src.data.materials]
        assert [u.name for u in src.data.uv_layers] == [RC.UV_INK, RC.UV_PAL], [u.name for u in src.data.uv_layers]
        assert sorted({g.name for g in src.vertex_groups}) == ['Hull'], 'HullDetail must be all Hull bone'
        name = RC.HULLDET + ('_LOD%d' % lod if lod else '')
        rep['files'][name] = export_one(src, name, False, '%s/%s.fbx' % (FBX_DIR, name))

if 'turrets' in ONLY:
    for base_name, name in RC.TURRETS.items():
        src = bpy.data.objects[name]
        assert tuple(src.rotation_euler) == (0, 0, 0) and tuple(src.scale) == (1, 1, 1), name   # as export_turret.py
        assert [m.name for m in src.data.materials] == [RC.MAT_PROPS], [m.name for m in src.data.materials]
        assert [u.name for u in src.data.uv_layers] == [RC.UV_INK, RC.UV_PAL], [u.name for u in src.data.uv_layers]
        rep['files'][name] = export_one(src, name, True, '%s/%s.fbx' % (FBX_DIR, name))
        rep['files'][name]['object_location_m'] = [round(x, 6) for x in src.location]

rep['protected_end'] = RC.protected_state()
rep['protected_unchanged'] = all(rep['protected_start'][k]['md5'] == v['md5'] for k, v in rep['protected_end'].items())
rep['export_blend_md5_end'] = RC.md5_file(RC.EXPORT_BLEND)
rep['seconds'] = round(time.time() - log.t0, 1)
prev = RC.CHECK_DIR + '/export_static.json'
if os.path.isfile(prev) and set(ONLY) != {'hull', 'turrets'}:
    old = RC.load_json(prev)
    old['files'].update(rep['files'])
    rep['files'] = old['files']
RC.dump_json(rep, prev)
log('done; protected unchanged:', rep['protected_unchanged'], '| export blend unchanged:',
    rep['export_blend_md5_end'] == rep['export_blend_md5'])
sys.stdout.flush()
os._exit(0)
