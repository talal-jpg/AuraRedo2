"""Read-only: list what a .blend holds (collections, objects, transforms, mesh stats, materials, modifiers).
  blender -b --factory-startup FILE.blend --python rig_inspect.py
"""
import bpy
print("FILE", bpy.data.filepath)
def walk(c, d=0):
    print("  " * d + "COLL", c.name, "hide_render", getattr(c, "hide_render", None), "objs", len(c.objects))
    for ch in c.children:
        walk(ch, d + 1)
walk(bpy.context.scene.collection)
for o in bpy.data.objects:
    line = f"OBJ {o.name:32s} {o.type:8s} parent={o.parent.name if o.parent else None} colls={[c.name for c in o.users_collection]} " \
           f"loc={tuple(round(v,4) for v in o.location)} rot={tuple(round(v,4) for v in o.rotation_euler)} scl={tuple(round(v,4) for v in o.scale)}"
    if o.type == 'MESH':
        me = o.data
        line += f" v={len(me.vertices)} f={len(me.polygons)} uv={[u.name for u in me.uv_layers]} mats={[m.name if m else None for m in me.materials]}" \
                f" mods={[m.type for m in o.modifiers]} attrs={[a.name for a in me.attributes]} custom_normals={me.has_custom_normals} hidden={o.hide_get()}/{o.hide_render}"
    print(line)
for m in bpy.data.materials:
    imgs = [n.image.filepath for n in (m.node_tree.nodes if m.node_tree else []) if n.type == 'TEX_IMAGE' and n.image]
    print("MAT", m.name, "users", m.users, "imgs", imgs)
for i in bpy.data.images:
    print("IMG", i.name, i.filepath, i.size[:], i.colorspace_settings.name)
