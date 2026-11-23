"""Step 6b: round trip. Re-import the exported FBX into a clean scene and compare it with the rig in AirshipRig.blend:
bone positions and orientations, vertex positions and weights (rest), and the deformed vertices at several frames of
the test sweep (SK_Airship_testanim.fbx vs the same action on the original rig).

  blender -b --factory-startup --python rig/scripts/rig_roundtrip.py -- [--json checks/rig/roundtrip.json]

Never saves anything but the JSON report.
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Matrix
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[argv.index('--json') + 1] if '--json' in argv else C.CHECKS + '/roundtrip.json'
FRAMES = [1, 31, 75, 135, 165, 255, 315, 390, 435, 510, 570, 630, 700, 780, 870, 940]


def world_co(ob, evaluated=False):
    if evaluated:
        dg = bpy.context.evaluated_depsgraph_get()
        oe = ob.evaluated_get(dg); me = oe.to_mesh()
    else:
        me = ob.data
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    M = np.array(ob.matrix_world)
    if evaluated:
        oe.to_mesh_clear()
    return co @ M[:3, :3].T + M[:3, 3]


def weights(ob):
    names = {g.index: g.name for g in ob.vertex_groups}
    out = []
    for v in ob.data.vertices:
        out.append(tuple(sorted((names[g.group], round(g.weight, 6)) for g in v.groups if g.weight > 0)))
    return out


def snapshot(arm, meshes, frames=None):
    S = {'bones': {}, 'meshes': {}}
    for b in arm.data.bones:
        M = arm.matrix_world @ b.matrix_local
        S['bones'][b.name] = dict(head=np.array(M.to_translation()), rot=M.to_3x3().normalized(),
                                  parent=b.parent.name if b.parent else None)
    for o in meshes:
        S['meshes'][o.name] = dict(co=world_co(o), w=weights(o))
    if frames:
        S['frames'] = {}
        for f in frames:
            bpy.context.scene.frame_set(f)
            S['frames'][f] = {o.name: world_co(o, True) for o in meshes}
    return S


# ---------------------------------------------------------------- reference: the rig
bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
arm = bpy.data.objects['Armature']
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm]
REF = snapshot(arm, meshes)
arm.animation_data_create(); arm.animation_data.action = bpy.data.actions['SK_Airship_TestSweep']
REF['frames'] = snapshot(arm, meshes, FRAMES)['frames']


def load_fbx(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False, primary_bone_axis='Z',
                             secondary_bone_axis='X', ignore_leaf_bones=False, use_custom_normals=True, anim_offset=0.0)
    a = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    assert len(a) == 1, a
    return a[0], [o for o in bpy.data.objects if o.type == 'MESH']


R = {}
for tag, fn, frames in (('rest', 'SK_Airship.fbx', None), ('testanim', 'SK_Airship_testanim.fbx', FRAMES)):
    arm2, meshes2 = load_fbx(os.path.join(C.EXPORT, fn))
    sc = bpy.context.scene
    r = {'armature_object': arm2.name, 'armature_scale': [round(x, 6) for x in arm2.matrix_world.to_scale()],
         'meshes': len(meshes2), 'bones': len(arm2.data.bones)}
    S = snapshot(arm2, meshes2, frames)
    # bones
    miss = sorted(set(REF['bones']) ^ set(S['bones']))
    dpos = max(float(np.linalg.norm(REF['bones'][b]['head'] - S['bones'][b]['head'])) for b in REF['bones'] if b in S['bones'])
    drot = max(math.degrees((REF['bones'][b]['rot'].to_quaternion().rotation_difference(S['bones'][b]['rot'].to_quaternion())).angle)
               for b in REF['bones'] if b in S['bones'])
    par = [b for b in REF['bones'] if b in S['bones'] and REF['bones'][b]['parent'] != S['bones'][b]['parent']]
    r.update(bone_name_mismatch=miss, bone_max_pos_err_m=dpos, bone_max_rot_err_deg=round(drot, 6), parent_mismatch=par)
    # meshes
    mm = sorted(set(REF['meshes']) ^ set(S['meshes']))
    dco, wbad, nv = 0.0, 0, 0
    for n, ref in REF['meshes'].items():
        if n not in S['meshes']:
            continue
        got = S['meshes'][n]
        assert len(got['co']) == len(ref['co']), (n, len(got['co']), len(ref['co']))
        dco = max(dco, float(np.abs(got['co'] - ref['co']).max()))
        wbad += sum(1 for a, b in zip(ref['w'], got['w']) if a != b)
        nv += len(ref['co'])
    r.update(mesh_name_mismatch=mm, vertices=nv, vertex_max_pos_err_m=dco, vertices_with_different_weights=wbad)
    if frames:
        sc.frame_start, sc.frame_end = 1, 961
        act = arm2.animation_data.action if arm2.animation_data else None
        r['imported_action'] = act.name if act else None
        r['imported_frame_range'] = list(act.frame_range) if act else None
        err = {}
        for f in frames:
            e = 0.0
            for n, ref in REF['frames'][f].items():
                e = max(e, float(np.abs(S['frames'][f][n] - ref).max()))
            err[f] = round(e, 6)
        r['deformed_max_err_m_per_frame'] = err
        r['deformed_max_err_m'] = max(err.values())
        # the sweep must actually move things (else the comparison proves nothing)
        r['reference_max_motion_from_rest_m_per_frame'] = {
            f: round(max(float(np.linalg.norm(REF['frames'][f][n] - REF['meshes'][n]['co'], axis=1).max()) for n in REF['meshes']), 4)
            for f in frames}
    R[tag] = r
    print('[roundtrip]', tag, r)
C.dump_json(R, OUT)
print('[roundtrip] wrote', OUT)
