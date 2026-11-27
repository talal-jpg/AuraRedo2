"""Round 2 (2026-11-24) review renders of the rig: removed deck pieces, wheel size, turrets, cannon bore. Never saves.

  blender -b --factory-startup --python rig/scripts/round2_render.py -- --mode highlight|before|after|turret [--out DIR]

* highlight: Talal's mesh (the byte copy rig/AirshipRig_src.blend) from above, bow down and port to the right like the
  top view Talal marked up, with the islands listed in deck_removals.json in red (to check them against his 5 arrows).
* before:    the current rig (rig/AirshipRig.blend) from above and from port. Run it before rig_all.sh rebuilds the rig.
* after:     the rebuilt rig + the two turrets (from props/AirshipProps.blend) at their mounts: top, port side, forward deck,
             helm close-up with a 141.6 cm capsule at PilotSeat, the port turret with a capsule at its gunner seat, the
             L1 cannon muzzle with a 1 m ball 80 cm ahead of it.
* turret:    props/Turret.blend on its own (studio): front and rear 3/4, side at pitch -20 / 0 / +40 with the gunner
             capsule 1.0 m behind the axis.
Workbench, studio light, outlines; hull light grey, props coloured per part. Output: rig/renders/round2/<mode>_<view>.png
"""
import bpy, bmesh, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V, Matrix
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
MODE = argv[argv.index('--mode') + 1] if '--mode' in argv else 'after'
OUT = argv[argv.index('--out') + 1] if '--out' in argv else C.RIG + '/renders/round2'
os.makedirs(OUT, exist_ok=True)

GREY, RED = (0.80, 0.80, 0.78), (0.95, 0.08, 0.06)
PROP_COL = {'Helm_Pedestal': (0.62, 0.42, 0.25), 'Helm_Wheel': (0.85, 0.55, 0.20), 'Cannon': (0.30, 0.33, 0.40),
            'Turret_Base': (0.25, 0.45, 0.80), 'Turret_Gun': (0.15, 0.70, 0.90), 'Capsule': (0.25, 0.80, 0.30),
            'Ball': (0.10, 0.10, 0.12)}

bpy.ops.wm.open_mainfile(filepath={'highlight': C.SRC_BLEND, 'turret': C.TURRET_BLEND}.get(MODE, C.RIG_BLEND))
sc = bpy.context.scene
ship = bpy.data.objects.get(C.HULL_OBJ)
show = [ship] if ship else []


def paint(o, col_of_vertex):
    me = o.data
    a = me.color_attributes.get('R2Color') or me.color_attributes.new('R2Color', 'BYTE_COLOR', 'POINT')
    cols = np.ones((len(me.vertices), 4), np.float32)
    cols[:, :3] = col_of_vertex
    a.data.foreach_set('color', cols.ravel())
    me.color_attributes.active_color = a
    me.color_attributes.render_color_index = me.color_attributes.find('R2Color')


if MODE == 'turret':
    for n in ('Turret_Base', 'Turret_Gun'):
        paint(bpy.data.objects[n], np.array(PROP_COL[n]))
        show.append(bpy.data.objects[n])
elif MODE == 'highlight':
    visl = np.array(C.load_json(C.RESEARCH + '/sm_airship_vertex_parts.json')['vertex_island'])
    assert len(visl) == len(ship.data.vertices)
    red = np.isin(visl, C.removed_islands())
    paint(ship, np.where(red[:, None], np.array(RED), np.array(GREY)))
    print('[r2] highlighted', int(red.sum()), 'vertices in', len(C.removed_islands()), 'islands')
else:
    arm = bpy.data.objects['Armature']
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    if arm.animation_data:
        arm.animation_data.action = None
    paint(ship, np.array(GREY))
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith(C.PROP_PREFIX):
            k = o.name[len(C.PROP_PREFIX):]
            paint(o, np.array(PROP_COL['Cannon' if k.startswith('Cannon') else k]))
            show.append(o)

spec = C.load_json(C.CHECKS + '/bones_spec.json') if MODE in ('before', 'after') else None
B = (lambda n: V(spec['bones'][n]['head'])) if spec else None


def deck_z(x, y, top=20.0):
    """first hit straight down on the (evaluated) hull"""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    if not hasattr(deck_z, 'tree'):
        deck_z.tree = BVHTree.FromObject(ship, dg)
    h = deck_z.tree.ray_cast(V((x, y, top)), V((0, 0, -1)), 40.0)
    return h[0].z if h[0] is not None else None


def add_mesh(name, bm, M, col):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.matrix_world = M
    for p in me.polygons:
        p.use_smooth = True
    paint(o, np.array(col))
    show.append(o)
    return o


def capsule(name, foot, r=C.MECH_CAPSULE_RADIUS, hh=C.MECH_CAPSULE_HALF_HEIGHT):
    """UE-style capsule standing on foot: total height 2 * hh, radius r"""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=r)
    for v in bm.verts:
        v.co.z += (hh - r) if v.co.z > 0 else -(hh - r)
        v.co.z += hh
    return add_mesh(name, bm, Matrix.Translation(V(foot)), PROP_COL['Capsule'])


def ball(name, centre, r=0.5):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=20, radius=r)
    return add_mesh(name, bm, Matrix.Translation(V(centre)), PROP_COL['Ball'])


TURRET = {}
if MODE == 'after':
    # the turrets as Unreal shows them: base yaw part at the mount (z = deck top), gun at PivotHeight on it
    with bpy.data.libraries.load(C.PROPS_BLEND, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in ('Turret_Base', 'Turret_Gun')]
    tobs = {o.name: o for o in dst.objects if o is not None}
    assert set(tobs) == {'Turret_Base', 'Turret_Gun'}, list(tobs)
    pivot_h = tobs['Turret_Gun'].location.z - tobs['Turret_Base'].location.z
    for side, (x, y) in C.TURRET_MOUNTS.items():
        z = deck_z(x, y)
        for n, o in tobs.items():
            c = o.copy()
            c.data = o.data.copy()
            c.name = '%s_%s' % (n, side)
            sc.collection.objects.link(c)
            c.matrix_world = Matrix.Translation(V((x, y, z))) @ o.matrix_basis
            paint(c, np.array(PROP_COL[n]))
            show.append(c)
        TURRET[side] = V((x, y, z))
    print('[r2] turret pivot height', round(pivot_h, 3), 'mounts', {k: tuple(round(a, 3) for a in v) for k, v in TURRET.items()})

for o in bpy.data.objects:
    o.hide_render = o not in show
    o.hide_viewport = False
for coll in bpy.data.collections:
    coll.hide_render = False

sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
items = [i.identifier for i in bpy.types.View3DShading.bl_rna.properties['color_type'].enum_items]
sh.color_type = 'VERTEX' if 'VERTEX' in items else 'ATTRIBUTE'
sh.show_object_outline = True
sh.object_outline_color = (0.05, 0.05, 0.08)
sh.show_cavity = True
sh.cavity_type = 'WORLD'
sh.show_backface_culling = False
sc.display.render_aa = '8'
sc.render.film_transparent = False
sc.world = sc.world or bpy.data.worlds.new('W')
sc.world.color = (0.22, 0.23, 0.25)
sc.render.image_settings.file_format = 'PNG'
sc.render.resolution_percentage = 100
cd = bpy.data.cameras.new('R2Cam')
cam = bpy.data.objects.new('R2Cam', cd)
sc.collection.objects.link(cam)
sc.camera = cam
cd.clip_start, cd.clip_end = 0.05, 400


def shot(name, loc, at, up=(0, 0, 1), ortho=None, lens=40, res=(1400, 1000)):
    cam.location = V(loc)
    fwd = (V(at) - V(loc)).normalized()
    upv = V(up)
    right = fwd.cross(upv).normalized()
    upv = right.cross(fwd).normalized()
    R = Matrix((right, upv, -fwd)).transposed()
    cam.rotation_euler = R.to_euler()
    cd.sensor_fit = 'AUTO'
    if ortho:
        cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else:
        cd.type = 'PERSP'; cd.lens = lens
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, '%s_%s.png' % (MODE, name))
    bpy.ops.render.render(write_still=True)
    print('[r2] wrote', sc.render.filepath)


if MODE == 'turret':
    gun = bpy.data.objects['Turret_Gun']
    capsule('Capsule_Gunner', (-C.TURRET_SEAT_BEHIND, 0.0, 0.0))
    shot('front34', loc=(3.6, 2.4, 2.4), at=(0.4, 0.0, 1.1), lens=40, res=(1200, 1000))
    shot('rear34', loc=(-3.4, -2.2, 2.6), at=(0.0, 0.0, 1.2), lens=40, res=(1200, 1000))
    for p in (-20, 0, 40):
        gun.rotation_euler = (0.0, math.radians(-p), 0.0)
        bpy.context.view_layer.update()
        shot('side_pitch%+d' % p, loc=(0.3, 6.0, 1.3), at=(0.3, 0.0, 1.1), ortho=3.6, res=(1200, 900))
    gun.rotation_euler = (0.0, 0.0, 0.0)
    shot('top', loc=(0.3, 0.0, 10.0), at=(0.3, 0.0, 0.0), up=(1, 0, 0), ortho=3.0, res=(1000, 1000))
    raise SystemExit(0)

# Talal's marked-up view: from above, bow at the bottom (screen up = -X), port (+Y) on the right
TOP = dict(loc=(6.5, 0.0, 80.0), at=(6.5, 0.0, 0.0), up=(-1, 0, 0), ortho=55.0, res=(760, 1400))
shot('top', **TOP)
if MODE == 'highlight':
    shot('top_fwd', loc=(17.0, 0.0, 80.0), at=(17.0, 0.0, 0.0), up=(-1, 0, 0), ortho=24.0, res=(800, 1100))
    shot('persp_fwd', loc=(-6.0, 9.0, 16.0), at=(12.0, 0.0, 5.0), lens=30, res=(1400, 900))
else:
    shot('side_port', loc=(6.5, 80.0, 3.0), at=(6.5, 0.0, 3.0), ortho=56.0, res=(1600, 760))
    shot('deck_fwd', loc=(-4.0, 9.0, 15.0), at=(16.0, 0.0, 6.0), lens=30, res=(1400, 900))
    hw, ps = B('Helm_Wheel'), B('PilotSeat')
    if MODE == 'after':
        capsule('Capsule_Pilot', ps)
    shot('helm', loc=(hw.x - 4.2, 3.0, hw.z + 1.4), at=(hw.x - 0.25, 0.0, hw.z - 0.25), lens=45, res=(1200, 900))
    shot('helm_side', loc=(hw.x - 0.3, 6.0, hw.z), at=(hw.x - 0.3, 0.0, hw.z - 0.3), lens=50, res=(1200, 900))
    mz, br = B('Cannon_L1_Muzzle'), B('Cannon_L1_Barrel')
    aim = (mz - br).normalized()
    if MODE == 'after':
        ball('Ball_L1', mz + aim * 0.80)
    shot('cannon_L1_muzzle', loc=mz + aim * 3.2 + V((3.0, 0, 1.0)), at=mz + aim * 0.5, lens=45, res=(1200, 900))
    if MODE == 'after':
        t = TURRET['L']
        capsule('Capsule_TurretL', t + V((-C.TURRET_SEAT_BEHIND, 0.0, 0.0)))
        shot('turret_L', loc=t + V((-4.5, 2.6, 2.6)), at=t + V((0.2, 0.0, 1.1)), lens=40, res=(1200, 900))
        shot('turret_L_front', loc=t + V((4.5, 1.5, 2.0)), at=t + V((0.0, 0.0, 1.1)), lens=40, res=(1200, 900))
        shot('turret_L_top', loc=t + V((0.0, 0.0, 12.0)), at=t, up=(-1, 0, 0), ortho=4.0, res=(900, 900))
