"""Copy-only inspection of rig/AirshipRig.blend (deform flags = skinned bones, bone alignment, action stored not assigned).
  cp rig/AirshipRig.blend rig/tmp/verify/AirshipRig_copy.blend
  blender -b --factory-startup rig/tmp/verify/AirshipRig_copy.blend --python rig/scripts/verify_rigblend.py
"""
import bpy
arm = bpy.data.objects.get('Armature')
print('[rb] armature', arm and arm.name, 'action assigned:', arm.animation_data.action.name if arm and arm.animation_data and arm.animation_data.action else None)
print('[rb] actions', [(a.name, a.users, a.use_fake_user) for a in bpy.data.actions])
print('[rb] collections', [c.name for c in bpy.data.collections])
skinned = set()
for o in bpy.data.objects:
    if o.type == 'MESH' and o.parent == arm:
        names = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            for g in v.groups:
                if g.weight > 0: skinned.add(names[g.group])
deform = {b.name for b in arm.data.bones if b.use_deform}
print('[rb] bones', len(arm.data.bones), 'deform', len(deform), 'skinned', len(skinned), 'deform==skinned', deform == skinned, sorted(deform ^ skinned)[:10])
bad = [b.name for b in arm.data.bones if abs((b.tail_local - b.head_local).normalized().z - 1) > 1e-6 or abs(b.matrix_local.to_euler().y) > 1e-6]
print('[rb] non-world-aligned bones', bad[:10], 'lengths', sorted({round((b.tail_local - b.head_local).length, 4) for b in arm.data.bones}))
sm = bpy.data.objects.get('SM_Airship'); print('[rb] SM_Airship verts', len(sm.data.vertices) if sm else None, 'mods', [m.type for m in sm.modifiers] if sm else None)
print('[rb] meshes under armature', len([o for o in bpy.data.objects if o.type=='MESH' and o.parent==arm]), 'UCX objects', [o.name for o in bpy.data.objects if o.name.startswith('UCX')][:3])
