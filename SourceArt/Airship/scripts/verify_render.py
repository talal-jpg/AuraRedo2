"""Verification renders of SK_Airship.fbx from a fresh import (factory scene, nothing saved):
rest vs posed pairs (colour per bone, Hull grey) and Talal's sketch viewpoint.

  blender -b --factory-startup --python rig/scripts/verify_render.py -- [--fbx F] [--only NAME,...] [--scale 1.0]

Writes rig/renders/verify/*.png.
"""
import bpy, sys, os, math, colorsys, hashlib
from mathutils import Matrix, Vector, Quaternion

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
OUTD = RIG + '/renders/verify'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(k, d):
    return argv[argv.index(k) + 1] if k in argv else d
FBX = arg('--fbx', RIG + '/export/SK_Airship.fbx')
ONLY = set(arg('--only', '').split(',')) - {''}
SCALE = float(arg('--scale', '1.0'))
os.makedirs(OUTD, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX, automatic_bone_orientation=False, primary_bone_axis='Z',
                         secondary_bone_axis='X', ignore_leaf_bones=False, use_anim=False)
sc = bpy.context.scene
arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
meshes = [o for o in bpy.data.objects if o.type == 'MESH']

# ---------------------------------------------------------------- colour per bone (point colour attribute)
def bone_colour(name):
    if name == 'Hull':
        return (0.62, 0.62, 0.60, 1)
    if name in ('Helm', 'Helm_Wheel') and MODE[0] == 'talal':
        return (1.0, 0.1, 0.1, 1) if name == 'Helm_Wheel' else (0.85, 0.1, 0.1, 1)
    if name.startswith('Cannon') and MODE[0] == 'talal':
        return (0.1, 0.35, 1.0, 1)
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, 0.85, 0.95)
    return (r, g, b, 1)
MODE = ['bones']
def paint():
    for o in meshes:
        me = o.data
        gname = {g.index: g.name for g in o.vertex_groups}
        at = me.color_attributes.get('BoneCol') or me.color_attributes.new('BoneCol', 'FLOAT_COLOR', 'POINT')
        cols = []
        for v in me.vertices:
            b = gname[v.groups[0].group] if v.groups else 'Hull'
            if MODE[0] == 'talal' and not (b.startswith('Cannon') or b.startswith('Helm')):
                cols.extend((0.62, 0.62, 0.60, 1))
            else:
                cols.extend(bone_colour(b))
        at.data.foreach_set('color', cols)
        me.color_attributes.active_color = at
        me.attributes.default_color_name = 'BoneCol'

sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
items = [i.identifier for i in bpy.types.View3DShading.bl_rna.properties['color_type'].enum_items]
sh.color_type = 'VERTEX' if 'VERTEX' in items else 'ATTRIBUTE'
sh.show_cavity = True; sh.cavity_type = 'WORLD'; sh.cavity_ridge_factor = 1.0; sh.cavity_valley_factor = 1.0
sh.show_object_outline = False
sc.display.render_aa = '8'
sh.background_type = 'VIEWPORT' if hasattr(sh, 'background_type') else None
sc.world = bpy.data.worlds.new('W'); sc.world.color = (0.23, 0.23, 0.24)
sc.render.film_transparent = False
sc.view_settings.view_transform = 'Standard'
cam_d = bpy.data.cameras.new('VCam'); cam = bpy.data.objects.new('VCam', cam_d)
sc.collection.objects.link(cam); sc.camera = cam

def render(name, loc, look, lens=35, res=(1280, 720), ortho=None):
    if ONLY and name not in ONLY:
        return
    cam.location = Vector(loc)
    d = Vector(look) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cam_d.type = 'ORTHO'; cam_d.ortho_scale = ortho
    else:
        cam_d.type = 'PERSP'; cam_d.lens = lens
    cam_d.clip_end = 500
    sc.render.resolution_x, sc.render.resolution_y = int(res[0] * SCALE), int(res[1] * SCALE)
    sc.render.filepath = os.path.join(OUTD, name + '.png')
    bpy.ops.render.render(write_still=True)
    print('[render]', sc.render.filepath)

# ---------------------------------------------------------------- posing helpers (world space)
AWI = arm.matrix_world.inverted()
def pose_world(bname, axis=None, deg=0.0, offset=(0, 0, 0), pivot=None):
    """Rotate bone (and so its children) by deg about a WORLD axis through its current head (or pivot), then move."""
    bpy.context.view_layer.update()
    pb = arm.pose.bones[bname]
    Mw = arm.matrix_world @ pb.matrix
    p = Vector(pivot) if pivot is not None else Mw.translation.copy()
    R = Matrix.Rotation(math.radians(deg), 4, Vector(axis).normalized()) if axis is not None else Matrix.Identity(4)
    Mnew = Matrix.Translation(Vector(offset)) @ Matrix.Translation(p) @ R @ Matrix.Translation(-p) @ Mw
    pb.matrix = AWI @ Mnew
    bpy.context.view_layer.update()
def head(bname):
    bpy.context.view_layer.update()
    return (arm.matrix_world @ arm.pose.bones[bname].matrix).translation.copy()
def reset():
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()

A = Vector((-0.13917303085327148, 0.0, -0.9902680516242981)).normalized()
POD = {'FL': (3.833, 4.656, -0.934), 'FR': (3.833, -4.918, -1.130), 'RL': (-7.167, 5.130, -1.204), 'RR': (-7.167, -5.768, -1.239)}
def pose_thrusters(petal=35.0, nozzle=12.0, pod=3.0):
    for t, o in POD.items():
        pose_world('Thruster_' + t, (1, 0, 0), pod)
        pose_world('Thruster_%s_Nozzle' % t, (0, 1, 0), nozzle)
        T0 = Vector(o) + Vector((0, 0, -0.4))
        for i in range(12):
            b = 'Thruster_%s_Petal%02d' % (t, i)
            hb = head(b)
            # current (posed) nozzle axis: rotate A with the pod + nozzle rotations
            Rn = (arm.matrix_world @ arm.pose.bones['Thruster_%s_Nozzle' % t].matrix).to_3x3().normalized() @ \
                 (arm.matrix_world @ arm.pose.bones['Thruster_%s_Nozzle' % t].bone.matrix_local).to_3x3().normalized().inverted()
            Ap = Rn @ A
            nz = head('Thruster_%s_Nozzle' % t)
            rel = hb - nz
            radial = rel - rel.dot(Ap) * Ap
            dvec = radial.normalized()
            pose_world(b, Ap.cross(dvec), petal)
def pose_steer(yaw=25.0):
    for s in 'LR':
        pose_world('Turbine_' + s, (0, 0, 1), yaw)
        pose_world('Turbine_%s_Rotor' % s, (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0), 15.0)  # yawed duct axis
        pose_world('Turbine_%s_Rod' % s, (1, 0, 0), 20.0)
    pose_world('Rudder', (0, 0, 1), 30.0)
def pose_deck():
    for c, yaw, elev in [('L1', 20, 8.75), ('R1', 20, -10), ('L2', -20, -10), ('R2', -20, 8.75)]:
        side = 1 if c[0] == 'L' else -1
        aim0 = Vector((0, side, 0))
        pose_world('Cannon_' + c, (0, 0, 1), yaw)
        aim = Matrix.Rotation(math.radians(yaw), 3, 'Z') @ aim0
        lat = Vector((0, 0, 1)).cross(aim)
        # + elevation raises the muzzle: rotate about lat so that aim tilts up
        ax = aim.cross(Vector((0, 0, 1)))
        pose_world('Cannon_%s_Barrel' % c, ax, elev)
        pose_world('Cannon_%s_Quoin' % c, None, 0, offset=tuple(-aim * min(0.15, max(0.0, 0.024 * elev))))
        for w in ['FL', 'FR', 'BL', 'BR']:
            pose_world('Cannon_%s_Wheel_%s' % (c, w), lat, 40)
        pose_world('Cannon_' + c, None, 0, offset=tuple(-aim * 0.6))       # recoil 60 cm
    pose_world('Helm_Wheel', (1, 0, 0), 90)
def pose_bow():
    for s in ['AftL', 'MidL', 'MidR', 'FwdC']:
        pose_world('SearchLight_' + s, (1, 0, 0), 10)
        pose_world('SearchLight_%s_Head' % s, (0, 0, 1), 60)
    a = head('ChainFwd'); b = head('ChainFwd_End')
    pose_world('ChainFwd', a - b, 25)        # sign chosen to swing outward (-Y side)
    pose_world('Winch_Fwd', (0, 1, 0), 45); pose_world('Winch_Aft', (0, 1, 0), 45)

VIEWS = {
    'deck': ((-30.0, 22.0, 15.0), (-8.5, 0.0, 3.0), 30),
    'deck_top': ((-8.5, 0.0, 40.0), (-8.5, 0.0, 2.6), None, (1280, 960), 20.0),
    'below': ((-12.0, 26.0, -22.0), (-1.5, 0.0, -3.5), 28),
    'stern': ((-42.0, 14.0, 8.0), (-17.0, 0.0, 1.0), 30),
    'bow': ((40.0, -14.0, 14.0), (26.0, -0.5, 6.0), 30),
}
def shoot(prefix):
    for k, v in VIEWS.items():
        if len(v) == 3:
            render('%s_%s' % (prefix, k), v[0], v[1], v[2])
        else:
            render('%s_%s' % (prefix, k), v[0], v[1], None, v[3], v[4])

paint()
reset()
shoot('rest')
pose_thrusters(); pose_steer(); pose_deck(); pose_bow()
shoot('posed')
reset()
# Talal's sketch viewpoint (port side, slightly above, bow left), helm red, cannons blue
MODE[0] = 'talal'; paint()
sh.show_object_outline = True
for i, (loc, look, lens) in enumerate([((2.0, 44.0, 13.0), (-3.0, 0.0, 0.5), 26),
                                       ((-4.0, 40.0, 11.0), (-4.0, 0.0, 1.0), 24)]):
    render('talal_view_%d' % i, loc, look, lens, (1316, 680))
# optional ghost of the fore cannon pair moved to another station (--ghost-fwd DX,DY,DZ), drawn yellow
GHOST = arg('--ghost-fwd', '')
if GHOST:
    dx, dy, dz = [float(t) for t in GHOST.split(',')]
    for o in list(meshes):
        for c, sgn in (('_L1_', 1), ('_R1_', -1)):
            if c in o.name:
                g = o.copy(); g.data = o.data.copy(); g.modifiers.clear(); g.parent = None
                g.matrix_world = Matrix.Translation(Vector((dx, sgn * dy, dz))) @ o.matrix_world
                sc.collection.objects.link(g)
                at = g.data.color_attributes['BoneCol']
                at.data.foreach_set('color', [1.0, 0.85, 0.0, 1.0] * len(g.data.vertices))
# the solved cameras of Talal's sketches (verify_sketch_camera.py)
import json as _json
_cj = RIG + '/checks/verify/sketch_camera.json'
if os.path.exists(_cj):
    for key, c in _json.load(open(_cj)).items():
        nm = 'sketchcam_' + key + ('_ghost' if GHOST else '')
        if ONLY and nm not in ONLY:
            continue
        cam.location = Vector(c['location']); cam.rotation_euler = c['rotation_euler']
        cam_d.type = 'PERSP'; cam_d.lens = c['lens_mm']; cam_d.sensor_fit = 'HORIZONTAL'; cam_d.sensor_width = 36
        sc.render.resolution_x, sc.render.resolution_y = c['res']
        sc.render.filepath = os.path.join(OUTD, nm + '.png')
        bpy.ops.render.render(write_still=True)
        print('[render]', sc.render.filepath)
# close-up of the aft deck from the same side
render('talal_view_deck_close', (-12.0, 20.0, 9.0), (-8.0, 0.0, 3.0), 30, (1316, 680))
print('[verify_render] done')
