"""Steps 2-4: build the SK_Airship rig (armature, rigid skin, props, materials, test action) per RIG_CONTRACT.md.

  blender -b --factory-startup --python rig/scripts/rig_build.py -- [--placement checks/rig/placement.json]

Input : rig/AirshipRig_src.blend (byte copy of Talal's StylizedAirship.blend, never written),
        rig/props/AirshipProps.blend (helm + cannon with the shared prop atlas), checks/rig/placement.json (rig_place.py),
        the research island classifier (sm_airship_islands.json / sm_airship_vertex_parts.json).
Output: rig/AirshipRig.blend (overwritten on every run), checks/rig/bones_blender.json, checks/rig/skin_report.json.

* SM_Airship geometry/UVs untouched (checked by hash before/after). One vertex group per bone, weight 1.0, exactly one
  group per vertex (100 % rigid per island, like the Burrower's hard pieces).
* Bones world-aligned: head at the pivot, tail = head + (0, 0, 0.5), roll 0; deform only on skinned bones.
* Props: helm (2 objects) + 4 cannon copies (7 objects each) with their own mesh copies (same atlas UVs), placed from
  placement.json; each prop object is 100 % on its bone.
"""
import bpy, sys, os, math, hashlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V, Matrix, Quaternion
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PLACEMENT = argv[argv.index('--placement') + 1] if '--placement' in argv else C.PLACEMENT_JSON
T0 = time.time()
bpy.ops.wm.open_mainfile(filepath=C.SRC_BLEND)
P = C.load_json(PLACEMENT)
ship = bpy.data.objects[C.HULL_OBJ]
assert ship.matrix_world == Matrix.Identity(4)


def mesh_hash(me):
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co)
    uv = np.empty(len(me.loops) * 2, np.float32); me.uv_layers['UVMap'].data.foreach_get('uv', uv)
    lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
    h = hashlib.md5()
    for a in (co, uv, lv):
        h.update(a.tobytes())
    return h.hexdigest()


HASH0 = mesh_hash(ship.data)

# ------------------------------------------------------------------ geometry facts for the pivots
co, polys = C.mesh_arrays(ship.data)
vbones, VP, ISL = C.hull_vertex_bones()
assert len(vbones) == len(co) == 36908
visl = np.array(VP['vertex_island'])
IS = {r['id']: r for r in ISL['islands']}
# the classifier's islands must still be exactly the mesh's loose parts
shells = C.loose_parts(len(co), polys)
pairs = set(zip(visl.tolist(), shells.tolist()))
assert len(pairs) == len(set(visl.tolist())) == len(set(shells.tolist())) == 1150, len(pairs)
for r in ISL['islands']:
    m = visl == r['id']
    assert np.allclose(co[m].mean(0), r['c'], atol=2e-3), (r['id'], co[m].mean(0), r['c'])
FR = ISL['frames']


def island_verts(pred):
    ids = [r['id'] for r in ISL['islands'] if pred(r)]
    return co[np.isin(visl, ids)], ids


BONES = {}      # name -> dict(head, parent, deform)
ORDER = []
META = {'petal_axis': {}, 'petal_hinge_vs_formula_m': {}, 'cannon_aim': {}, 'cannon_axle': {}, 'notes': {}}


def bone(name, parent, head, deform):
    assert name not in BONES
    BONES[name] = dict(head=C.r3(head, 5), parent=parent, deform=deform)
    ORDER.append(name)


bone('root', None, (0, 0, 0), False)
bone('Hull', 'root', (0, 0, 0), True)

# thrusters
for p in C.PODS:
    f = FR['Pod_' + p]
    ob = bpy.data.objects.get(C.POD_OBJ[p])
    if ob is not None:
        assert (ob.matrix_world.translation - V(f['origin'])).length < 1e-4, p
    A = V(f['axis_nozzle']).normalized(); T0p = V(f['T0'])
    b = 'Thruster_' + p
    bone(b, 'Hull', f['origin'], True)
    bone(b + '_Nozzle', b, f['nozzle_pivot'], True)
    tips = []
    for k in range(12):
        pv, ids = island_verts(lambda r: r['part'] == 'Nozzle_' + p and r.get('piece') == 'petal' and r['index'] == k)
        assert len(ids) == 1 and len(pv) == 8, (p, k, ids, len(pv))
        rel = pv - np.array(T0p)
        h = rel @ np.array(A)
        top = pv[np.argsort(h)[:4]]                       # the petal's top (hinge) edge: 4 verts nearest the drum
        hinge = V(top.mean(0))
        radial = (hinge - T0p) - A * (hinge - T0p).dot(A)
        d = radial.normalized()
        formula = T0p + 3.9 * A + 1.45 * d
        name = '%s_Petal%02d' % (b, k)
        bone(name, b + '_Nozzle', hinge, True)
        META['petal_axis'][name] = C.r3(A.cross(d), 6)
        META['petal_hinge_vs_formula_m'][name] = round((hinge - formula).length, 4)
        tips.append(h.max())
    h_tip = float(max(tips))
    bone(b + '_Flame', b + '_Nozzle', T0p + A * h_tip, False)
    META['notes'][b + '_Flame'] = 'on the nozzle axis A at the petal tips, h = %.3f m from T0' % h_tip

# turbines
for s, sg in (('L', 1), ('R', -1)):
    fan = FR['Fan_' + s]
    b = 'Turbine_' + s
    bone(b, 'Hull', (-17.2, 5.35 * sg, 1.4), True)
    bone(b + '_Rotor', b, fan['spin_pivot'], True)
    rod, ids = island_verts(lambda r: r['part'] == 'FanHousing_' + s and r.get('piece') == 'hanging_rod')
    assert len(ids) == 1
    bone(b + '_Rod', b, (float(rod[:, 0].mean()), float(rod[:, 1].mean()), float(rod[:, 2].max())), True)
    shell, ids = island_verts(lambda r: r['part'] == 'FanHousing_' + s and r.get('piece') == 'shell')
    assert len(ids) == 1
    bone(b + '_Exhaust', b, (float(shell[:, 0].min()), fan['axis_yz'][0], fan['axis_yz'][1]), False)
    META['notes'][b + '_Exhaust'] = 'duct shell rear rim x on the duct axis'

bone('Rudder', 'Hull', (-16.364, 0.0, 0.7), True)

# search lights: posts at the contract pivots, heads on the post axis at the head's centre height
LAMP = {'AftL': (11.2, 2.8, 6.55), 'MidL': (24.6, 2.4, 7.35), 'MidR': (24.6, -2.4, 7.35), 'FwdC': (30.4, 0.9, 7.35)}
for L, piv in LAMP.items():
    b = 'SearchLight_' + L
    post, ids = island_verts(lambda r: r['part'] == b and r.get('piece') == 'post')
    head, ids2 = island_verts(lambda r: r['part'] == b and r.get('piece') == 'head')
    pc = (post[:, :2].min(0) + post[:, :2].max(0)) / 2
    assert abs(pc[0] - piv[0]) < 1e-3 and abs(pc[1] - piv[1]) < 1e-3, (L, pc)
    bone(b, 'Hull', piv, True)
    hz = float((head[:, 2].min() + head[:, 2].max()) / 2)
    bone(b + '_Head', b, (piv[0], piv[1], hz), True)

cf = FR['ChainFwd']
bone('ChainFwd', 'Hull', cf['end_b'], True)          # contract end "A" (26.545, -2.946, 4.320)
bone('ChainFwd_End', 'ChainFwd', cf['end_a'], False)  # contract end "B" (21.464, -3.353, 2.961)
bone('Winch_Fwd', 'Hull', FR['Winch_Fwd']['centre'], True)
bone('Winch_Aft', 'Hull', FR['Winch_Aft']['centre'], True)

# helm
H = P['helm']
bone('Helm', 'Hull', H['pedestal'], True)
bone('Helm_Wheel', 'Helm', H['wheel_axle'], True)
bone('PilotSeat', 'Hull', H['pilot'], False)

# cannons
CM = {}
for c in C.CANNONS:
    pc = P['cannons'][c]
    Mc = C.cannon_frame(pc['origin'], C.CANNON_SIDE[c], roll_deg=pc['roll_deg'])
    CM[c] = Mc
    b = 'Cannon_' + c
    bone(b, 'Hull', pc['origin'], True)
    bone(b + '_Barrel', b, Mc @ C.C_TRUNNION, True)
    bone(b + '_Muzzle', b + '_Barrel', Mc @ C.C_MUZZLE, False)
    bone(b + '_Quoin', b, Mc @ C.C_QUOIN, True)
    for w, wc in C.C_WHEELS.items():
        bone('%s_Wheel_%s' % (b, w), b, Mc @ wc, True)
    aim = (Mc @ C.C_MUZZLE - Mc @ C.C_TRUNNION).normalized()
    META['cannon_aim'][c] = C.r3(aim, 6)
    META['cannon_axle'][c] = C.r3(Mc.to_3x3() @ V((0, 1, 0)), 6)
    META['notes'][b] = 'roll %.3f deg about the firing axis (deck sheer), nudge inboard %.2f m' % (pc['roll_deg'], pc['nudge_inboard_m'])

print('[build] bones', len(ORDER), 'max petal hinge vs formula %.4f m' % max(META['petal_hinge_vs_formula_m'].values()))

# ------------------------------------------------------------------ armature
for o in bpy.context.view_layer.objects:
    o.select_set(False)
coll = bpy.data.collections.new('SK_Airship')
bpy.context.scene.collection.children.link(coll)
arm_data = bpy.data.armatures.new('Armature')
arm = bpy.data.objects.new('Armature', arm_data)
coll.objects.link(arm)
arm_data.display_type = 'OCTAHEDRAL'
arm.show_in_front = True
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = {}
for n in ORDER:
    d = BONES[n]
    e = arm_data.edit_bones.new(n)
    e.head = V(d['head']); e.tail = V(d['head']) + C.BONE_TAIL; e.roll = 0.0
    e.use_deform = d['deform']; e.use_connect = False
    e.inherit_scale = 'FULL'
    eb[n] = e
for n in ORDER:
    if BONES[n]['parent']:
        eb[n].parent = eb[BONES[n]['parent']]
bpy.ops.object.mode_set(mode='OBJECT')
RX90 = Matrix.Rotation(math.radians(90), 3, 'X')
for b in arm_data.bones:          # world-aligned check: matrix_local rotation = Rx(+90) (bone +Y along world +Z) for every bone
    R = b.matrix_local.to_3x3()
    assert max(abs(R[i][j] - RX90[i][j]) for i in range(3) for j in range(3)) < 1e-6, b.name
    assert (b.head_local - V(BONES[b.name]['head'])).length < 1e-5, b.name

# ------------------------------------------------------------------ props
with bpy.data.libraries.load(C.PROPS_BLEND, link=False) as (src_d, dst_d):
    dst_d.objects = [n for n in src_d.objects if n.startswith('Cannon_') or n.startswith('Helm_')]
SRC = {o.name: o for o in dst_d.objects if o is not None}
pmat = bpy.data.materials['M_AirshipProps']


def place_prop(src_name, new_name, M):
    so = SRC[src_name]
    me = so.data.copy(); me.name = new_name
    o = bpy.data.objects.new(new_name, me)
    coll.objects.link(o)
    o.matrix_world = M @ so.matrix_basis
    assert len(me.materials) == 1 and me.materials[0] == pmat, (src_name, [m.name for m in me.materials])
    return o


PROPS = {}   # object name -> bone
HM = Matrix.Translation(V(H['pedestal']))
PROPS[place_prop('Helm_Pedestal', C.prop_obj_name('Helm', 'Pedestal'), HM).name] = 'Helm'
PROPS[place_prop('Helm_Wheel', C.prop_obj_name('Helm', 'Wheel'), HM).name] = 'Helm_Wheel'
for c in C.CANNONS:
    b = 'Cannon_' + c
    for part in C.CANNON_PARTS:
        o = place_prop('Cannon_' + part, C.prop_obj_name(c, part), CM[c])
        PROPS[o.name] = b if part == 'Carriage' else '%s_%s' % (b, part)
# the appended source objects are not needed (their mesh copies were made)
for o in list(SRC.values()):
    me = o.data if o.type == 'MESH' else None
    bpy.data.objects.remove(o)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)

# pivots must sit on the placed objects' origins (helm wheel axle, cannon parts)
for on, bn in PROPS.items():
    o = bpy.data.objects[on]
    if True:
        assert (o.matrix_world.translation - V(BONES[bn]['head'])).length < 1e-4, (on, bn, o.matrix_world.translation, BONES[bn]['head'])

# ------------------------------------------------------------------ skin
if ship.name not in coll.objects:
    coll.objects.link(ship)
SKIN = {}   # mesh object -> per-bone vertex counts


def add_armature_mod(o):
    for m in list(o.modifiers):
        if m.type == 'ARMATURE':
            o.modifiers.remove(m)
    md = o.modifiers.new('Armature', 'ARMATURE')
    md.object = arm; md.use_vertex_groups = True; md.use_bone_envelopes = False
    mw = o.matrix_world.copy()
    o.parent = arm; o.parent_type = 'OBJECT'; o.matrix_parent_inverse = arm.matrix_world.inverted()
    o.matrix_world = mw


ship.vertex_groups.clear()
vb = np.array(vbones)
counts = {}
for bn in sorted(set(vbones), key=ORDER.index):
    idx = np.nonzero(vb == bn)[0].tolist()
    g = ship.vertex_groups.new(name=bn)
    g.add(idx, 1.0, 'REPLACE')
    counts[bn] = len(idx)
add_armature_mod(ship)
SKIN[ship.name] = counts
for on, bn in PROPS.items():
    o = bpy.data.objects[on]
    o.vertex_groups.clear()
    g = o.vertex_groups.new(name=bn)
    g.add(list(range(len(o.data.vertices))), 1.0, 'REPLACE')
    add_armature_mod(o)
    SKIN[on] = {bn: len(o.data.vertices)}

# every deforming bone has weights, no non-deforming bone has any; every vertex exactly one group with weight 1
used = {}
for on, cnt in SKIN.items():
    o = bpy.data.objects[on]
    n1 = 0
    for v in o.data.vertices:
        assert len(v.groups) == 1 and v.groups[0].weight == 1.0, (on, v.index)
        n1 += 1
    for bn, k in cnt.items():
        used[bn] = used.get(bn, 0) + k
for n in ORDER:
    assert (n in used) == BONES[n]['deform'], (n, n in used, BONES[n]['deform'])
assert mesh_hash(ship.data) == HASH0, 'SM_Airship geometry/UV changed'

# ------------------------------------------------------------------ materials
assert [m.name for m in ship.data.materials] == ['M_Airship']
for img in pmat.node_tree.nodes:
    if img.type == 'TEX_IMAGE' and img.image:
        print('[build] prop image', img.image.name, img.image.filepath, os.path.exists(bpy.path.abspath(img.image.filepath)))

# ------------------------------------------------------------------ store the spec on the armature + test action
spec = {'bones': BONES, 'order': ORDER, 'meta': META}
C.dump_json(spec, C.CHECKS + '/bones_spec.json')
arm['rig_contract'] = 'Docs/Airship/RIG_CONTRACT.md'

# test action: each control swept through its range, 30 fps
FPS = 30
SEG = 60
def flare(t):   # 0 -> +35 -> 0 -> -10 -> 0
    return 35 * math.sin(2 * math.pi * t) if t < 0.5 else 10 * math.sin(2 * math.pi * t)


TEST = [  # (control keys, values over the segment as a function of t in [0,1])
    (['NozzlePitchDeg_' + p for p in C.PODS], lambda t: 5 * math.sin(2 * math.pi * t)),
    (['NozzleRollDeg_' + p for p in C.PODS], lambda t: 5 * math.sin(2 * math.pi * t)),
    (['NozzleFlareDeg_' + p for p in C.PODS], flare),
    (['PodPitchDeg_' + p for p in C.PODS] + ['PodRollDeg_' + p for p in C.PODS], lambda t: 3 * math.sin(2 * math.pi * t)),
    (['TurbineYawDeg_L', 'TurbineYawDeg_R'], lambda t: 12 * math.sin(2 * math.pi * t)),
    (['RotorAngleDeg_L', 'RotorAngleDeg_R'], lambda t: 720 * t),
    (['RodSwingXDeg_L', 'RodSwingXDeg_R', 'RodSwingYDeg_L', 'RodSwingYDeg_R'], lambda t: 8 * math.sin(2 * math.pi * t)),
    (['RudderDeg'], lambda t: 30 * math.sin(2 * math.pi * t)),
    (['WheelAngleDeg'], lambda t: 540 * math.sin(math.pi * t)),
    (['CannonYawDeg_' + c for c in C.CANNONS], lambda t: 20 * math.sin(2 * math.pi * t)),
    (['CannonElevDeg_' + c for c in C.CANNONS], lambda t: 8.75 * math.sin(2 * math.pi * t) if t < 0.5 else 10 * math.sin(2 * math.pi * t)),
    (['CannonRecoilCm_' + c for c in C.CANNONS], lambda t: 60 * (t / 0.15) if t < 0.15 else 60 * (1 - (t - 0.15) / 0.85)),
    (['LampWobbleXDeg', 'LampWobbleYDeg'], lambda t: 4 * math.sin(2 * math.pi * t)),
    (['SearchLightPanDeg'], lambda t: 360 * t),
    (['ChainSwingDeg'], lambda t: 25 * math.sin(math.pi * t)),        # outward only: inward buries it in the bow wedge
    (['WinchSpinDeg'], lambda t: 360 * t),
]

NF = SEG * len(TEST)
act = bpy.data.actions.new('SK_Airship_TestSweep')
act.use_fake_user = True
arm.animation_data_create()
arm.animation_data.action = act
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'
prevq = {}
SEGS = []
for f in range(NF + 1):
    si = min(f // SEG, len(TEST) - 1)
    t = (f - si * SEG) / SEG if f < NF else 1.0
    keys, fn = TEST[si]
    ctrl = {k: fn(t) for k in keys}
    C.apply_pose(arm, spec, ctrl)
    for pb in arm.pose.bones:
        q = pb.rotation_quaternion.copy()
        if pb.name in prevq:
            q.make_compatible(prevq[pb.name])
        pb.rotation_quaternion = q
        prevq[pb.name] = q
        pb.keyframe_insert('location', frame=f + 1, group=pb.name)
        pb.keyframe_insert('rotation_quaternion', frame=f + 1, group=pb.name)
for i, (keys, fn) in enumerate(TEST):
    SEGS.append(dict(frames=[i * SEG + 1, (i + 1) * SEG + 1], controls=keys))
C.dump_json(dict(fps=FPS, frames=[1, NF + 1], segments=SEGS), C.CHECKS + '/testanim_segments.json')
sc = bpy.context.scene
sc.render.fps = FPS; sc.frame_start = 1; sc.frame_end = NF + 1
# leave the rig at rest and the action unassigned (the rest FBX has no animation; rig_export assigns it for testanim)
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
sc.frame_set(1)

# ------------------------------------------------------------------ reports
tab = []
for n in ORDER:
    d = BONES[n]
    tab.append(dict(bone=n, parent=d['parent'], head_m=d['head'], head_ue_cm=C.ue_cm(d['head']), deform=d['deform'],
                    verts=used.get(n, 0)))
C.dump_json(dict(count=len(ORDER), deform=sum(1 for n in ORDER if BONES[n]['deform']), bones=tab), C.CHECKS + '/bones_blender.json')
C.dump_json(dict(meshes={k: dict(verts=sum(v.values()), groups=v) for k, v in SKIN.items()},
                 total_verts=sum(sum(v.values()) for v in SKIN.values()), per_bone_verts=used,
                 hull_hash_unchanged=True, hull_hash=HASH0,
                 rule='every vertex exactly one vertex group, weight 1.0; one group per bone; props 100 % on their bone'),
           C.CHECKS + '/skin_report.json')
bpy.ops.wm.save_as_mainfile(filepath=C.RIG_BLEND, relative_remap=True, compress=False)
print('[build] saved', C.RIG_BLEND, 'bones', len(ORDER), 'meshes', len(SKIN), 'verts', sum(used.values()),
      'frames', NF + 1, '%.1f s' % (time.time() - T0))
