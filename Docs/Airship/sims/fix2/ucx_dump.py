import bpy, json, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath='/mnt/new_partition/BlenderProjects/StylizedAirship/export/SM_Airship.fbx')
out = {}
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    me = o.data
    mw = o.matrix_world
    vs = [mw @ v.co for v in me.vertices]
    if not o.name.startswith('UCX'):
        out['_render_' + o.name] = {'nverts': len(vs)}
        continue
    faces = []
    for p in me.polygons:
        n = (mw.to_3x3() @ p.normal).normalized()
        c = mw @ p.center
        faces.append([round(n.x, 4), round(n.y, 4), round(n.z, 4), round(c.x, 4), round(c.y, 4), round(c.z, 4), round(p.area, 4)])
    out[o.name] = {'min': [round(min(v[i] for v in vs), 3) for i in range(3)], 'max': [round(max(v[i] for v in vs), 3) for i in range(3)],
                   'verts': [[round(v.x, 3), round(v.y, 3), round(v.z, 3)] for v in vs], 'faces': faces,
                   'scale': list(o.scale), 'rot': list(o.rotation_euler)}
json.dump(out, open('/mnt/new_partition/UnrealProjects/_AirshipWork_logs/scratch/fix2/ucx.json', 'w'))
print('UCXDONE', [k for k in out])
