"""Textured close-ups of the props from a fresh import of SK_Airship.fbx with T_AirshipProps_ComicLines.png on UV
channel 0 (and SM_Airship with T_Airship_ComicLines.png), to see that the baked ink lands on the right faces.

  blender -b --factory-startup --python rig/scripts/verify_props_render.py
"""
import bpy, os
from mathutils import Vector
RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
OUTD = RIG + '/renders/verify'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=RIG + '/export/SK_Airship.fbx', automatic_bone_orientation=False,
                         primary_bone_axis='Z', secondary_bone_axis='X', use_anim=False)
img_p = bpy.data.images.load(RIG + '/props/textures/T_AirshipProps_ComicLines.png')
img_h = bpy.data.images.load('/mnt/new_partition/BlenderProjects/StylizedAirship/textures/T_Airship_ComicLines.png') \
    if os.path.exists('/mnt/new_partition/BlenderProjects/StylizedAirship/textures/T_Airship_ComicLines.png') else None
def tex_mat(name, img):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = img
    nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    return m
mp = tex_mat('VP', img_p); mh = tex_mat('VH', img_h) if img_h else None
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    o.data.materials.clear()
    o.data.materials.append(mp if o.name.startswith('SM_AirshipProp_') else (mh or mp))
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'FLAT'; sh.color_type = 'TEXTURE'
sc.world = bpy.data.worlds.new('W'); sc.world.color = (0.3, 0.3, 0.32)
sc.view_settings.view_transform = 'Standard'
cd = bpy.data.cameras.new('C'); cam = bpy.data.objects.new('C', cd); sc.collection.objects.link(cam); sc.camera = cam
def shot(name, loc, look, lens=50, res=(1100, 800)):
    cam.location = Vector(loc); cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cd.lens = lens; sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUTD, name + '.png'); bpy.ops.render.render(write_still=True)
    print('[render]', sc.render.filepath)
shot('tex_helm', (-3.2, 3.5, 5.6), (-6.9, 0.0, 3.6), 45)
shot('tex_cannon_L1', (1.88, 3.08, 4.5), (-0.46, 6.48, 2.9), 40)
shot('tex_cannon_R2', (-8.6, -1.2, 4.6), (-11.47, -4.6, 3.1), 40)
