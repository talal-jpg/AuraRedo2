"""Step 6c: check renders of the rig (Workbench, colour per bone from the vertex groups, outlines).

  blender -b --factory-startup --python rig/scripts/rig_render.py -- [--only rest,A,B] [--views v1,v2] [--res 1.0]

Poses: rest; A = every control at its + limit; B = every control at its - limit (values below). Never saves the .blend.
Output: renders/rig/<pose>_<view>.png
"""
import bpy, sys, os, math, colorsys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ONLY = argv[argv.index('--only') + 1].split(',') if '--only' in argv else ['rest', 'A', 'B']
VIEWS = argv[argv.index('--views') + 1].split(',') if '--views' in argv else None
RES = float(argv[argv.index('--res') + 1]) if '--res' in argv else 1.0

POSES = {
    'rest': {},
    'A': dict(**{'NozzlePitchDeg_' + p: 5 for p in C.PODS}, **{'NozzleRollDeg_' + p: 5 for p in C.PODS},
              **{'NozzleFlareDeg_' + p: 35 for p in C.PODS}, TurbineYawDeg_L=12, TurbineYawDeg_R=12, RotorAngleDeg_L=45,
              RotorAngleDeg_R=45, RudderDeg=30, WheelAngleDeg=90, SearchLightPanDeg=90, LampWobbleXDeg=4, ChainSwingDeg=25,
              WinchSpinDeg=45, **{'CannonYawDeg_' + c: 20 for c in C.CANNONS}, **{'CannonElevDeg_' + c: 9 for c in C.CANNONS},
              **{'CannonRecoilCm_' + c: 60 for c in C.CANNONS}),
    'B': dict(**{'NozzlePitchDeg_' + p: -5 for p in C.PODS}, **{'NozzleRollDeg_' + p: -5 for p in C.PODS},
              **{'NozzleFlareDeg_' + p: -10 for p in C.PODS}, TurbineYawDeg_L=-12, TurbineYawDeg_R=-12, RotorAngleDeg_L=45,
              RotorAngleDeg_R=45, RudderDeg=-30, WheelAngleDeg=-30, SearchLightPanDeg=-90, LampWobbleXDeg=-4, ChainSwingDeg=0,
              WinchSpinDeg=-45, **{'CannonYawDeg_' + c: -20 for c in C.CANNONS}, **{'CannonElevDeg_' + c: -10 for c in C.CANNONS},
              **{'CannonRecoilCm_' + c: 60 for c in C.CANNONS}),
}
# (camera location, look-at, ortho scale or None for perspective lens, resolution)
CAMS = {
    'side_port': ((5.0, 70.0, 3.0), (5.5, 0.0, 2.0), 56.0, (1600, 800)),
    'top': ((5.5, 0.0, 70.0), (5.5, 0.0, 0.0), 56.0, (1600, 900)),
    'aft34_above': ((-44.0, 30.0, 26.0), (2.0, 0.0, 1.0), None, (1600, 1000)),
    'below34_fwd': ((36.0, -30.0, -22.0), (0.0, 0.0, -1.0), None, (1600, 1000)),
    'thruster_FL': ((12.0, 15.0, -9.5), (3.4, 4.7, -4.6), None, (1200, 900)),
    'fans_rudder': ((-38.0, 15.0, 9.0), (-17.5, 0.0, 1.0), None, (1400, 900)),
    'deck_aft': ((-21.0, 13.0, 11.0), (-8.5, 2.5, 3.0), None, (1400, 900)),
    'cannon_L2': ((-11.0, 13.0, 5.5), (-11.4, 4.8, 3.4), None, (1200, 900)),
    'cannon_R1': ((0.9, -13.2, 6.0), (-0.46, -6.6, 3.1), None, (1200, 900)),
    'cannon_L1': ((-0.1, 13.2, 5.5), (-0.46, 4.9, 3.3), None, (1200, 900)),
    'deck_fwd_pair': ((-22.0, 15.0, 11.0), (-4.0, 0.0, 3.0), None, (1400, 900)),
    'helm': ((-12.5, 4.5, 6.0), (-6.9, 0.0, 3.6), None, (1200, 900)),
    'gantry': ((36.0, 13.0, 15.0), (25.0, 0.0, 6.5), None, (1400, 900)),
    'top_cannon_R1': ((-0.46, -6.7, 30.0), (-0.46, -6.7, 0.0), 4.6, (1000, 1000)),
    'top_cannon_L2': ((-11.4, 4.9, 30.0), (-11.4, 4.9, 0.0), 4.6, (1000, 1000)),
    'out_cannon_L2': ((-11.6, 16.0, 3.7), (-11.45, 4.5, 3.5), None, (1200, 900)),
    'top_fans': ((-16.5, 0.0, 40.0), (-16.5, 0.0, 0.0), 22.0, (1400, 1000)),
    'fan_L_pylon': ((-9.0, 13.0, 4.5), (-17.0, 6.0, 1.4), None, (1200, 900)),
    'chain_fwd': ((22.0, -14.0, 3.0), (24.0, -3.1, 3.2), None, (1200, 900)),
}
SETS = {'rest': ['side_port', 'top', 'aft34_above', 'below34_fwd', 'thruster_FL', 'fans_rudder', 'deck_aft', 'deck_fwd_pair', 'cannon_L1', 'cannon_L2', 'helm', 'gantry'],
        'A': ['aft34_above', 'below34_fwd', 'thruster_FL', 'fans_rudder', 'deck_aft', 'deck_fwd_pair', 'cannon_L1', 'cannon_L2', 'cannon_R1', 'helm', 'gantry',
              'top_cannon_R1', 'top_cannon_L2', 'out_cannon_L2'],
        'B': ['aft34_above', 'below34_fwd', 'thruster_FL', 'fans_rudder', 'deck_aft', 'deck_fwd_pair', 'cannon_L1', 'cannon_L2', 'cannon_R1', 'helm', 'gantry',
              'top_cannon_R1', 'top_cannon_L2', 'out_cannon_L2']}
SETS['rest'] += ['top_cannon_R1', 'top_cannon_L2', 'out_cannon_L2']
for k in SETS:
    SETS[k] += ['top_fans', 'fan_L_pylon', 'chain_fwd']

bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
sc = bpy.context.scene
arm = bpy.data.objects['Armature']
spec = C.load_json(C.CHECKS + '/bones_spec.json')
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm]
for o in bpy.data.objects:
    o.hide_render = not (o in meshes)
for coll in bpy.data.collections:
    coll.hide_render = False

# colour per bone
order = spec['order']
COL = {}
for i, n in enumerate(order):
    if n == 'Hull':
        COL[n] = (0.78, 0.78, 0.76)
        continue
    h = (i * 0.61803398875) % 1.0
    COL[n] = colorsys.hsv_to_rgb(h, 0.75, 0.95)
for o in meshes:
    me = o.data
    names = {g.index: g.name for g in o.vertex_groups}
    a = me.color_attributes.get('BoneColor') or me.color_attributes.new('BoneColor', 'BYTE_COLOR', 'POINT')
    cols = np.empty((len(me.vertices), 4), np.float32)
    for v in me.vertices:
        c = COL[names[v.groups[0].group]]
        cols[v.index] = (*c, 1.0)
    a.data.foreach_set('color', cols.ravel())
    me.color_attributes.active_color = a
    me.color_attributes.render_color_index = me.color_attributes.find('BoneColor')

sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
items = [i.identifier for i in bpy.types.View3DShading.bl_rna.properties['color_type'].enum_items]
sh.color_type = 'VERTEX' if 'VERTEX' in items else 'ATTRIBUTE'
sh.show_object_outline = True; sh.object_outline_color = (0.05, 0.05, 0.08)
sh.show_cavity = True; sh.cavity_type = 'WORLD'
sh.show_backface_culling = False
sc.display.render_aa = '8'
sc.render.film_transparent = False
sc.world = sc.world or bpy.data.worlds.new('W')
sc.render.image_settings.file_format = 'PNG'
cam_data = bpy.data.cameras.new('RigCam'); cam = bpy.data.objects.new('RigCam', cam_data)
sc.collection.objects.link(cam); sc.camera = cam
cam_data.clip_start = 0.1; cam_data.clip_end = 400
os.makedirs(C.RENDERS, exist_ok=True)


def aim(loc, at):
    cam.location = V(loc)
    cam.rotation_euler = (V(at) - V(loc)).to_track_quat('-Z', 'Y').to_euler()


for pose in ONLY:
    C.apply_pose(arm, spec, POSES[pose])
    bpy.context.view_layer.update()
    for view in SETS[pose]:
        if VIEWS and view not in VIEWS:
            continue
        loc, at, ortho, res = CAMS[view]
        aim(loc, at)
        if ortho:
            cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
        else:
            cam_data.type = 'PERSP'; cam_data.lens = 35 if view in ('aft34_above', 'below34_fwd') else 40
        sc.render.resolution_x, sc.render.resolution_y = int(res[0] * RES), int(res[1] * RES)
        sc.render.filepath = os.path.join(C.RENDERS, '%s_%s.png' % (pose, view))
        bpy.ops.render.render(write_still=True)
        print('[render]', sc.render.filepath)
