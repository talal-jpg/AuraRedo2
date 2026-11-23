# as_13_cr_eval.py - numeric evaluation of CR_Airship on throw-away rig instances (no PIE, no world): Construction +
# Forwards Solve frames like the AnimBP node (bones reset to the ref pose before every frame), then the affected bones'
# component-space transforms are compared with RIG_CONTRACT 5 (axis, sign, amount). Also: rig components, rest
# stability, Fx step responses (overshoot / settle), release back to the control pose, death (Wreck bodies fall + kick,
# latch), and a cross-check against the Blender test sweep A_Airship_TestSweep for the controls whose sign Blender and
# the contract share. Writes Saved/Airship/cr_eval.txt (+ cr_eval.json). Changes nothing on disk except those files
# (the test instances dirty CR_Airship in memory only: do not save it afterwards; harmless, Burrower note).
# Run:  Docs/Airship/scripts/harness/inbox.sh 13 Docs/Airship/scripts/ue/as_13_cr_eval.py 900
import importlib, json, math, os, sys, time, traceback  # unreal = inbox namespace

AS13_DIR = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue'
if AS13_DIR not in sys.path:
    sys.path.insert(0, AS13_DIR)
import as_cr_helpers as H  # noqa: E402
importlib.reload(H)

DT = 1.0 / 60.0
SETTLE = 120
LINES = []
CNT = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}
RES = {}


def out(tag, msg):
    CNT[tag] = CNT.get(tag, 0) + 1
    line = '%s: %s' % (tag, msg)
    LINES.append(line)
    print(line)


def ok(cond, msg, soft=False):
    out('PASS' if cond else ('WARN' if soft else 'FAIL'), msg)
    return cond


H._out = out


# ------------------------------------------------------------------------------------------------- maths
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def qinv(q):
    return [-q[0], -q[1], -q[2], q[3]]


def qrot(q, v):
    p = qmul(qmul(q, [v[0], v[1], v[2], 0.0]), qinv(q))
    return p[:3]


def qaxis(axis, deg):
    a = math.radians(deg) * 0.5
    n = math.sqrt(sum(x * x for x in axis))
    return [axis[0] / n * math.sin(a), axis[1] / n * math.sin(a), axis[2] / n * math.sin(a), math.cos(a)]


def angle_axis(q):
    w = max(-1.0, min(1.0, q[3]))
    if w < 0:
        q = [-x for x in q]
        w = -w
    ang = math.degrees(2.0 * math.acos(w))
    s = math.sqrt(max(0.0, 1.0 - w * w))
    ax = [q[0] / s, q[1] / s, q[2] / s] if s > 1e-9 else [0.0, 0.0, 0.0]
    return ang, ax


def qang(a, b):
    d = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def add(a, b):
    return [a[i] + b[i] for i in range(3)]


def scl(a, s):
    return [x * s for x in a]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def norm(a):
    n = math.sqrt(dot(a, a))
    return [x / n for x in a]


def length(a):
    return math.sqrt(dot(a, a))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def f3(v):
    return '(%.2f, %.2f, %.2f)' % tuple(v)


# ------------------------------------------------------------------------------------------------- rig runner
RIG = unreal.EditorAssetLibrary.load_asset(H.RIG_PATH)
PODS, FANS, CANNONS, LIGHTS = ['FL', 'FR', 'RL', 'RR'], ['L', 'R'], ['L1', 'L2', 'R1', 'R2'], ['AftL', 'MidL', 'MidR', 'FwdC']
ALL_FLOATS = ([n + p for n in ('NozzlePitchDeg_', 'NozzleRollDeg_', 'NozzleFlareDeg_', 'ThrustAlpha_') for p in PODS] +
              [n + s for n in ('TurbineYawDeg_', 'RotorAngleDeg_') for s in FANS] + ['RudderDeg', 'WheelAngleDeg'] +
              [n + c for n in ('CannonYawDeg_', 'CannonElevDeg_', 'CannonRecoilCm_') for c in CANNONS] +
              ['SearchLightPanDeg', 'DeathTime'])


def base_vars():
    d = dict((n, 0.0) for n in ALL_FLOATS)
    d['bIsDead'] = False
    return d


def run(name, vars_fn, frames, bones=None, every=None, inst_out=None):
    """vars_fn: dict or f -> dict (merged over zeros). Returns {'final': {bone: (pos, quat)}, 'track': {f: {...}}}"""
    inst = H.make_test_instance(RIG)
    if inst_out is not None:
        inst_out.append(inst)
    h = inst.get_hierarchy()
    keys = {}
    names = bones or [str(k.get_editor_property('name')) for k in h.get_bones(True)]
    for b in names:
        keys[b] = H.bone_key(b)

    def apply(f):
        d = base_vars()
        d.update(vars_fn(f) if callable(vars_fn) else vars_fn)
        for k, v in d.items():
            if not inst.set_variable_from_string(k, H._fmt(v)):
                out('WARN', '%s: set_variable_from_string(%s) False' % (name, k))

    def read():
        r = {}
        for b, k in keys.items():
            t = h.get_global_transform(k, False)
            r[b] = ([t.translation.x, t.translation.y, t.translation.z],
                    [t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w])
        return r

    apply(0)
    inst.set_absolute_and_delta_time(0.0, DT)
    if not inst.execute(H.EV_CONSTRUCTION):
        out('FAIL', '%s: Construction returned False' % name)
    track = {}
    okf = True
    for f in range(frames):
        apply(f)
        h.reset_pose_to_initial(unreal.RigElementType.BONE)
        inst.set_absolute_and_delta_time(f * DT, DT)
        if not inst.execute(H.EV_FORWARDS):
            okf = False
        if every and (f % every == 0 or f == frames - 1):
            track[f] = read()
    if not okf:
        out('FAIL', '%s: Forwards Solve returned False on some frame' % name)
    return {'final': read(), 'track': track, 'inst': inst}


REST = {}
h0 = H.rig_hierarchy(RIG)
for _k in h0.get_bones(True):
    _n = str(_k.get_editor_property('name'))
    _t = h0.get_global_transform(_k, True)
    REST[_n] = ([_t.translation.x, _t.translation.y, _t.translation.z],
                [_t.rotation.x, _t.rotation.y, _t.rotation.z, _t.rotation.w])
PARENT = dict((b, H.parent_of(RIG, b)) for b in REST)


def descendants(b):
    out_ = {b}
    changed = True
    while changed:
        changed = False
        for c, p in PARENT.items():
            if p in out_ and c not in out_:
                out_.add(c)
                changed = True
    return out_


def dpos(r, b):
    return sub(r['final'][b][0], REST[b][0])


def drot(r, b):
    """global rotation delta cur * rest^-1 -> (angle deg, axis)"""
    return angle_axis(qmul(r['final'][b][1], qinv(REST[b][1])))


def moved(r, tol_cm=0.05, tol_deg=0.05):
    m = set()
    for b, (p, q) in r['final'].items():
        if length(sub(p, REST[b][0])) > tol_cm or qang(q, REST[b][1]) > tol_deg:
            m.add(b)
    return m


def check_moved(label, r, controlled):
    want = set()
    for b in controlled:
        want |= descendants(b)
    got = moved(r)
    extra = sorted(got - want)
    miss = sorted(want - got)
    # sockets / children without own motion may legitimately not move (e.g. a rotor child on its spin axis)
    ok(not extra, '%s: only the controlled bones (+children) moved%s' % (
        label, '' if not extra else '; ALSO moved: %s' % extra[:12]))
    return got, miss


def rot_check(label, r, b, axis, deg, tol_deg=0.05, axis_tol=0.999):
    ang, ax = drot(r, b)
    if deg < 0:
        deg, axis = -deg, scl(axis, -1)
    good = abs(ang - deg) <= tol_deg and (deg < 1e-6 or dot(ax, norm(axis)) >= axis_tol)
    ok(good, '%s: %s turned %.3f deg (want %.3f) about %s (want %s)' % (label, b, ang, deg, f3(ax), f3(norm(axis))))
    return ang, ax


def point_after(r, b, p_rest):
    """where a point rigidly attached to bone b (rest position p_rest) is now"""
    pos, q = r['final'][b]
    rp, rq = REST[b]
    return add(pos, qrot(qmul(q, qinv(rq)), sub(p_rest, rp)))


# ------------------------------------------------------------------------------------------------- tests
def t_components():
    rr = []
    r = run('components', {}, 1, bones=['Hull'], inst_out=rr)
    inst = rr[0]
    keys = []
    for ck in inst.get_hierarchy().get_all_component_keys():
        ek = ck.get_editor_property('element_key')
        keys.append((str(ek.get_editor_property('name')), str(ck.get_editor_property('name'))))
    names = {}
    for b, c in keys:
        names[c] = names.get(c, 0) + 1
    RES['components'] = sorted('%s/%s' % k for k in keys)
    out('INFO', 'rig components after Construction: %d: %s' % (len(keys), sorted(names.items())))
    have = set(keys)
    wreck = ['Hull'] + ['Thruster_' + p for p in PODS] + ['Turbine_' + s for s in FANS] + ['Rudder'] + \
        ['Cannon_' + c for c in CANNONS] + ['Cannon_%s_Barrel' % c for c in CANNONS] + ['SearchLight_' + L for L in LIGHTS]
    # session 3 (R6): the turbine rods have a Wreck body too, so their Fx bodies are PhysicsBody_2 like the others
    wreck = wreck + ['Turbine_%s_Rod' % s for s in FANS]
    exp = [('Hull', 'PhysicsSolver'), ('root', 'PhysicsSolver')] + [(b, 'PhysicsBody') for b in wreck] + \
          [(b, 'PhysicsBody_2') for b in wreck]
    miss = [k for k in exp if k not in have]
    ok(not miss, 'expected solver/body components present (Wreck = PhysicsBody, Fx on the same bones = PhysicsBody_2)%s'
       % ('' if not miss else ' MISSING %s' % miss))
    nj = len([k for k in keys if k[1].startswith('PhysicsJoint')])
    ok(nj == 10 + 21, '%d joint components (want 10 Wreck + 21 Fx)' % nj)
    try:
        v = inst.get_variable_as_string('bDeathKickDone')
        ok(v.lower() == 'false', 'bDeathKickDone after 1 alive frame = %s' % v)
    except Exception as e:  # noqa: BLE001
        out('WARN', 'cannot read bDeathKickDone: %s' % e)


def t_rest():
    r = run('rest', {}, SETTLE)
    worst = max((length(dpos(r, b)), b) for b in REST)
    worstr = max((qang(r['final'][b][1], REST[b][1]), b) for b in REST)
    RES['rest'] = {'worst_cm': worst, 'worst_deg': worstr}
    ok(worst[0] < 0.05 and worstr[0] < 0.05, 'all controls 0, alive, %d frames: every bone at rest (worst %.4f cm %s, '
       '%.4f deg %s)' % (SETTLE, worst[0], worst[1], worstr[0], worstr[1]))


def t_nozzles():
    r = run('pitch', dict(('NozzlePitchDeg_' + p, 5.0) for p in PODS), SETTLE)
    check_moved('NozzlePitchDeg +5', r, ['Thruster_%s_Nozzle' % p for p in PODS])
    rp = {}
    for p in PODS:
        rot_check('NozzlePitchDeg_%s +5' % p, r, 'Thruster_%s_Nozzle' % p, (0, 1, 0), 5.0)
        d = dpos(r, 'Thruster_%s_Flame' % p)
        ok(d[0] < -1.0, 'NozzlePitchDeg_%s +5: nozzle exit (Flame) moved %s -> aft (x %.2f)' % (p, f3(d), d[0]))
        rp[p] = d
    r = run('roll', dict(('NozzleRollDeg_' + p, 5.0) for p in PODS), SETTLE)
    check_moved('NozzleRollDeg +5', r, ['Thruster_%s_Nozzle' % p for p in PODS])
    rr = {}
    for p in PODS:
        rot_check('NozzleRollDeg_%s +5' % p, r, 'Thruster_%s_Nozzle' % p, (1, 0, 0), 5.0)
        d = dpos(r, 'Thruster_%s_Flame' % p)
        ok(d[1] > 1.0, 'NozzleRollDeg_%s +5: nozzle exit moved %s -> toward +Y (y %.2f)' % (p, f3(d), d[1]))
        rr[p] = d
    RES['nozzle'] = {'pitch_flame_delta': rp, 'roll_flame_delta': rr}


def petal_geo(p, k):
    nz, fl = REST['Thruster_%s_Nozzle' % p][0], REST['Thruster_%s_Flame' % p][0]
    A = norm(sub(fl, nz))
    hp = REST['Thruster_%s_Petal%02d' % (p, k)][0]
    rel = sub(hp, nz)
    d = norm(sub(rel, scl(A, dot(rel, A))))
    return A, d, norm(cross(A, d)), hp


def radial(p, pt):
    nz, fl = REST['Thruster_%s_Nozzle' % p][0], REST['Thruster_%s_Flame' % p][0]
    A = norm(sub(fl, nz))
    rel = sub(pt, nz)
    return length(sub(rel, scl(A, dot(rel, A))))


def t_flare():
    res = {}
    for val in (35.0, -10.0):
        r = run('flare%+d' % val, dict(('NozzleFlareDeg_' + p, val) for p in PODS), SETTLE)
        check_moved('NozzleFlareDeg %+.0f' % val, r, ['Thruster_%s_Petal%02d' % (p, k) for p in PODS for k in range(12)])
        worst_a, worst_ax, dr = 0.0, 1.0, []
        for p in PODS:
            for k in range(12):
                b = 'Thruster_%s_Petal%02d' % (p, k)
                A, d, hax, hp = petal_geo(p, k)
                ang, ax = drot(r, b)
                if val < 0:
                    ax = scl(ax, -1)
                worst_a = max(worst_a, abs(ang - abs(val)))
                worst_ax = min(worst_ax, dot(ax, hax))
                tip = add(hp, scl(A, 45.0))       # petal tip: 0.45 m further along A (Flame at h 4.35, hinge 3.90)
                dr.append(radial(p, point_after(r, b, tip)) - radial(p, tip))
        if val > 0:
            ok(min(dr) > 0.5, 'NozzleFlareDeg +35: all 48 petal tips moved OUTWARD (radial +%.2f .. +%.2f cm)' % (min(dr), max(dr)))
        else:
            ok(max(dr) < -0.5, 'NozzleFlareDeg -10: all 48 petal tips moved INWARD (radial %.2f .. %.2f cm)' % (min(dr), max(dr)))
        ok(worst_a < 0.05 and worst_ax > 0.999, 'NozzleFlareDeg %+.0f: every petal turned %.0f deg about its hinge A x d '
           '(worst angle error %.4f deg, worst axis dot %.6f)' % (val, abs(val), worst_a, worst_ax))
        res[str(val)] = {'tip_radial_cm': [min(dr), max(dr)], 'worst_angle_err': worst_a, 'worst_axis_dot': worst_ax}
    RES['flare'] = res


def t_turbines():
    r = run('turbine', {'TurbineYawDeg_L': 12.0, 'TurbineYawDeg_R': 12.0}, SETTLE)
    check_moved('TurbineYawDeg +12', r, ['Turbine_L', 'Turbine_R'])
    res = {}
    for s in FANS:
        rot_check('TurbineYawDeg_%s +12 (Fx body, settled)' % s, r, 'Turbine_' + s, (0, 0, 1), 12.0, tol_deg=0.1)
        fan = qrot(qmul(r['final']['Turbine_' + s][1], qinv(REST['Turbine_' + s][1])), [1, 0, 0])
        ok(fan[1] > 0.2, 'TurbineYawDeg_%s +12: fan axis %s turned from +X toward +Y (sin 12 = 0.208)' % (s, f3(fan)))
        res[s] = fan
    r = run('rotor', {'RotorAngleDeg_L': 90.0, 'RotorAngleDeg_R': 45.0}, 3)
    check_moved('RotorAngleDeg', r, ['Turbine_L_Rotor', 'Turbine_R_Rotor'])
    rot_check('RotorAngleDeg_L 90', r, 'Turbine_L_Rotor', (1, 0, 0), 90.0)
    rot_check('RotorAngleDeg_R 45', r, 'Turbine_R_Rotor', (1, 0, 0), 45.0)
    d = length(dpos(r, 'Turbine_L_Rotor'))
    ok(d < 0.05, 'rotor hub stays on its axis (%.4f cm)' % d)
    r = run('rotor_yaw', {'RotorAngleDeg_L': 90.0, 'TurbineYawDeg_L': 12.0}, SETTLE)
    ang, ax = angle_axis(qmul(qinv(r['final']['Turbine_L'][1]), r['final']['Turbine_L_Rotor'][1]))
    ok(abs(ang - 90) < 0.1 and ax[0] > 0.999, 'rotor spin follows the yawed duct: rotor relative to nacelle %.2f deg about '
       'nacelle-local %s' % (ang, f3(ax)))
    RES['turbine_fan_axis'] = res


def t_steer():
    r = run('rudder', {'RudderDeg': 20.0}, SETTLE)
    check_moved('RudderDeg +20', r, ['Rudder'])
    rot_check('RudderDeg +20 (Fx body, settled)', r, 'Rudder', (0, 0, 1), 20.0, tol_deg=0.1)
    te = [-2000.0, 0.0, 161.0]                 # trailing edge, 3.6 m aft of the hinge
    d = sub(point_after(r, 'Rudder', te), te)
    ok(d[1] < -50.0, 'RudderDeg +20: trailing edge moved %s -> toward -Y (port)' % f3(d))
    RES['rudder_te_delta'] = d
    r = run('wheel', {'WheelAngleDeg': 90.0}, 3)
    check_moved('WheelAngleDeg 90', r, ['Helm_Wheel'])
    rot_check('WheelAngleDeg 90', r, 'Helm_Wheel', (1, 0, 0), 90.0)
    r = run('wheel400', {'WheelAngleDeg': 400.0}, 3)
    rot_check('WheelAngleDeg 400 (multi-turn = 40)', r, 'Helm_Wheel', (1, 0, 0), 40.0)
    d = length(dpos(r, 'Helm_Wheel'))
    ok(d < 0.05, 'helm wheel stays on its axle (%.4f cm)' % d)


def cannon_geo(c):
    b = 'Cannon_' + c
    aim = norm(sub(REST[b + '_Muzzle'][0], REST[b + '_Barrel'][0]))
    ax = sub(REST[b + '_Wheel_FL'][0], REST[b + '_Wheel_FR'][0])
    e = norm(sub(ax, scl(aim, dot(ax, aim))))
    if dot(e, cross(aim, [0, 0, 1])) < 0:
        e = scl(e, -1)
    return aim, e


def t_cannons():
    res = {}
    r = run('cyaw', dict(('CannonYawDeg_' + c, 15.0) for c in CANNONS), SETTLE)
    check_moved('CannonYawDeg +15', r, ['Cannon_' + c for c in CANNONS])
    for c in CANNONS:
        aim, e = cannon_geo(c)
        rot_check('CannonYawDeg_%s +15 (Fx body, settled)' % c, r, 'Cannon_' + c, (0, 0, 1), 15.0, tol_deg=0.1)
        d = dpos(r, 'Cannon_%s_Muzzle' % c)
        off = sub(REST['Cannon_%s_Muzzle' % c][0], REST['Cannon_' + c][0])     # muzzle about the carriage pivot
        want = sub(qrot(qaxis([0, 0, 1], 15.0), off), off)
        ok(length(sub(d, want)) < 1.0, 'CannonYawDeg_%s +15: muzzle moved %s (standard rotation about +Z: want %s)' % (
            c, f3(d), f3(want)))
        res['yaw_' + c] = d
    r = run('celev', dict(('CannonElevDeg_' + c, 8.0) for c in CANNONS), SETTLE)
    check_moved('CannonElevDeg +8', r, ['Cannon_%s_Barrel' % c for c in CANNONS] + ['Cannon_%s_Quoin' % c for c in CANNONS])
    for c in CANNONS:
        aim, e = cannon_geo(c)
        rot_check('CannonElevDeg_%s +8 (Fx body, settled)' % c, r, 'Cannon_%s_Barrel' % c, e, 8.0, tol_deg=0.1)
        d = dpos(r, 'Cannon_%s_Muzzle' % c)
        ok(d[2] > 20.0, 'CannonElevDeg_%s +8: muzzle raised %.2f cm (156 sin 8 = 21.7)' % (c, d[2]))
        dq = dpos(r, 'Cannon_%s_Quoin' % c)
        ok(length(sub(dq, scl(aim, -15.0))) < 0.1, 'CannonElevDeg_%s +8: quoin slid %s = 15 cm (clamped from 19.2) along -aim'
           % (c, f3(dq)))
        res['elev_' + c] = {'muzzle': d, 'quoin': dq}
    r = run('celev_m10', dict(('CannonElevDeg_' + c, -10.0) for c in CANNONS), SETTLE)
    for c in CANNONS:
        d = dpos(r, 'Cannon_%s_Muzzle' % c)
        dq = length(dpos(r, 'Cannon_%s_Quoin' % c))
        ok(d[2] < -20.0 and dq < 0.05, 'CannonElevDeg_%s -10: muzzle lowered %.2f cm, quoin stays (%.3f cm)' % (c, d[2], dq))
    r = run('celev_5', {'CannonElevDeg_L1': 5.0}, SETTLE)
    aim, e = cannon_geo('L1')
    dq = dpos(r, 'Cannon_L1_Quoin')
    ok(length(sub(dq, scl(aim, -12.0))) < 0.1, 'CannonElevDeg_L1 +5: quoin slid %s = 2.4 x 5 = 12 cm along -aim' % f3(dq))
    r = run('recoil', dict(('CannonRecoilCm_' + c, 60.0) for c in CANNONS), SETTLE)
    check_moved('CannonRecoilCm 60', r, ['Cannon_' + c for c in CANNONS])
    for c in CANNONS:
        aim, e = cannon_geo(c)
        d = dpos(r, 'Cannon_' + c)
        ok(length(sub(d, scl(aim, -60.0))) < 0.3, 'CannonRecoilCm_%s 60: carriage moved %s (want 60 cm along -aim %s)' % (
            c, f3(d), f3(scl(aim, -60.0))))
        for w in ('FL', 'BR'):
            ang, ax = angle_axis(qmul(qinv(r['final']['Cannon_' + c][1]), r['final']['Cannon_%s_Wheel_%s' % (c, w)][1]))
            want = math.degrees(60.0 / 22.0)
            ok(abs(ang - want) < 0.2 and dot(ax, e) > 0.999, 'CannonRecoilCm_%s 60: wheel %s rolled %.2f deg (want %.2f) '
               'about %s (axle e %s)' % (c, w, ang, want, f3(ax), f3(e)))
        res['recoil_' + c] = d
    # rolling without slipping: tiny recoil, the wheel bottom (contact) point stays put
    r = run('recoil2', {'CannonRecoilCm_L1': 2.0, 'CannonRecoilCm_R2': 2.0}, SETTLE)
    for c in ('L1', 'R2'):
        wb = 'Cannon_%s_Wheel_FL' % c
        bottom = add(REST[wb][0], [0.0, 0.0, -22.0])
        dc = length(dpos(r, wb))
        db = length(sub(point_after(r, wb, bottom), bottom))
        ok(dc > 1.9 and db < 0.1, 'CannonRecoilCm_%s 2: wheel centre moved %.3f cm, contact point %.4f cm (rolls backward, '
           'no slip)' % (c, dc, db))
    r = run('yaw_recoil', {'CannonYawDeg_L1': 15.0, 'CannonRecoilCm_L1': 60.0, 'CannonYawDeg_R1': -15.0,
                           'CannonRecoilCm_R1': 60.0}, SETTLE)
    for c, y in (('L1', 15.0), ('R1', -15.0)):
        aim, e = cannon_geo(c)
        want = qrot(qaxis([0, 0, 1], y), scl(aim, -60.0))
        d = dpos(r, 'Cannon_' + c)
        ok(length(sub(d, want)) < 0.5, 'Cannon_%s yaw %+.0f + recoil 60: slide %s follows the yawed aim (want %s)' % (
            c, y, f3(d), f3(want)))
    RES['cannons'] = res


def t_lights():
    r = run('pan', {'SearchLightPanDeg': 30.0}, 3)
    check_moved('SearchLightPanDeg 30', r, ['SearchLight_%s_Head' % L for L in LIGHTS])
    for L in LIGHTS:
        s = 1.0 if L in ('AftL', 'MidL') else -1.0
        rot_check('SearchLightPanDeg 30 (%s, sign %+.0f)' % (L, s), r, 'SearchLight_%s_Head' % L, (0, 0, s), 30.0)


def settle_stats(track, b, getter, target):
    fr = sorted(track)
    vals = [getter(track[f][b]) for f in fr]
    peak = max(vals) if target > 0 else min(vals)
    over = (peak - target) / target * 100.0
    st = None
    for i in range(len(fr)):
        if all(abs(v - target) <= 0.02 * abs(target) for v in vals[i:]):
            st = fr[i] * DT
            break
    return over, st, vals


def t_dynamics():
    res = {}
    cases = [('Cannon_L1', 'CannonYawDeg_L1', 15.0, 'yaw'), ('Turbine_L', 'TurbineYawDeg_L', 12.0, 'yaw'),
             ('Rudder', 'RudderDeg', 20.0, 'yaw'), ('Cannon_L1_Barrel', 'CannonElevDeg_L1', 8.0, 'elev'),
             ('Cannon_L1', 'CannonRecoilCm_L1', 60.0, 'recoil')]
    aim, e = cannon_geo('L1')
    for b, var, val, kind in cases:
        r = run('step_' + var, lambda f, var=var, val=val: {var: val if f < SETTLE else 0.0}, 2 * SETTLE, bones=[b],
                every=1)
        if kind == 'yaw':
            g = lambda x, b=b: angle_axis(qmul(x[1], qinv(REST[b][1])))[0] * (1 if angle_axis(qmul(x[1], qinv(REST[b][1])))[1][2] >= 0 else -1)
        elif kind == 'elev':
            g = lambda x, b=b: angle_axis(qmul(x[1], qinv(REST[b][1])))[0]
        else:
            g = lambda x, b=b: dot(sub(x[0], REST[b][0]), scl(aim, -1))
        tr1 = dict((f, v) for f, v in r['track'].items() if f < SETTLE)
        over, st, vals = settle_stats(tr1, b, g, val)
        back = abs(g(r['final'][b]))
        unit = 'cm' if kind == 'recoil' else 'deg'
        ok(st is not None and st < 1.6, '%s step 0 -> %g: %s overshoot %.1f %%, within 2 %% after %s s; frame-1 value %.2f %s'
           % (var, val, b, over, ('%.3f' % st) if st is not None else 'never', vals[1], unit))
        ok(back < 0.02 * val, '%s back to 0 at frame %d: %s settles back to the control (rest) pose, %.4f %s left after '
           '%d frames' % (var, SETTLE, b, back, unit, SETTLE))
        res[var] = {'overshoot_pct': over, 'settle_s': st, 'release_residual': back, 'peak': max(vals) if val > 0 else min(vals),
                    'first_frames': [round(v, 3) for v in vals[:12]]}
    # session 3 (R1, R2): the nacelle must not pass its 12 deg inboard stop, the barrel not its 8.75 deg carriage stop
    ok(res['TurbineYawDeg_L']['peak'] <= 12.3, 'R1: TurbineYawDeg_L step to the 12 deg limit peaks at %.2f deg (stop 12, '
       'was 15.1 with damping 0.4 and no joint limit)' % res['TurbineYawDeg_L']['peak'])
    # fix round 2: the anim instance clamps the elevation at CannonElevMaxDeg 8.5 and eases it in
    # (UAirshipAnimInstance: FInterpConstantTo at min(CannonAimSlewDegPerSec 45, |error| x CannonElevSettleRate 8) deg/s)
    elev = eased_elev(ELEV_MAX, SETTLE)
    r = run('ramp_elev_max', lambda f: {'CannonElevDeg_L1': elev[f]}, SETTLE,
            bones=['Cannon_L1', 'Cannon_L1_Barrel'], every=1)
    vals = [angle_axis(qmul(r['track'][f]['Cannon_L1_Barrel'][1], qinv(REST['Cannon_L1_Barrel'][1])))[0] for f in sorted(r['track'])]
    rel0 = qmul(qinv(REST['Cannon_L1'][1]), REST['Cannon_L1_Barrel'][1])
    rels = [qang(qmul(qinv(r['track'][f]['Cannon_L1'][1]), r['track'][f]['Cannon_L1_Barrel'][1]), rel0) for f in sorted(r['track'])]
    car = [qang(r['track'][f]['Cannon_L1'][1], REST['Cannon_L1'][1]) for f in sorted(r['track'])]
    # what can clip is the barrel against ITS carriage (relative angle); the global angle adds the carriage's own rock
    ok(max(rels) <= 8.75, 'R2: CannonElevDeg_L1 eased in to the %.2f clamp like the anim instance: barrel vs its carriage '
       'peaks at %.2f deg (carriage contact at 8.75; offline model 8.50-8.55); global %.2f deg incl. the carriage rocking '
       'back %.2f deg (reaction torque on its 4 Hz drive); WARN up to 9.0 = a few mm, a tuning item'
       % (ELEV_MAX, max(rels), max(vals), max(car)), soft=max(rels) <= 9.0)
    res['elev_eased_ramp_peak'] = {'clamp': ELEV_MAX, 'barrel_vs_carriage': max(rels), 'global': max(vals), 'carriage_rock': max(car)}
    RES['dynamics'] = res


ELEV_MAX = 8.5  # = AAirshipPawn / UAirshipAnimInstance::CannonElevMaxDeg (fix round 2)


def eased_elev(target, frames, slew=45.0, rate=8.0):
    """CannonElevDeg per frame as UAirshipAnimInstance makes it from 0 (FInterpConstantTo, ElevSlew = min(slew, |err| x rate))."""
    e, out_ = 0.0, []
    for _ in range(frames):
        out_.append(e)
        step = min(slew, abs(target - e) * rate) * DT
        e = min(target, e + step) if target >= e else max(target, e - step)
    return out_


KICK_BASE = {  # must equal as_12_control_rig.KICK_BASE (linear cm/s, angular rad/s, component axes)
    'Thruster_FL': ((60, -260, -120), (-1.2, 0.8, 0.6)), 'Thruster_FR': ((60, 260, -120), (1.2, 0.8, -0.6)),
    'Thruster_RL': ((-60, -260, -120), (-1.0, -0.9, 0.5)), 'Thruster_RR': ((-60, 260, -120), (1.0, -0.9, -0.5)),
    'Turbine_L': ((-180, -320, 160), (-1.5, 0.6, 1.0)), 'Turbine_R': ((-180, 320, 160), (1.5, 0.6, -1.0)),
    'Rudder': ((-220, 0, 120), (0.0, -1.2, 1.6)),   # session 3: -Y spin, the top tips aft (+1.2 flipped it onto the stern deck)
    'SearchLight_AftL': ((0, -150, 380), (-2.0, 0.5, 0.0)), 'SearchLight_MidL': ((60, -170, 400), (-1.8, -0.6, 0.0)),
    'SearchLight_MidR': ((60, 170, 400), (1.8, -0.6, 0.0)), 'SearchLight_FwdC': ((120, -60, 420), (-0.6, -1.9, 0.0)),
}
KICK_LIN_SCALE, KICK_ANG_SCALE = 0.5, 0.6   # validation 2026-11-22 (as_12 V1): KICK = KICK_BASE scaled, as in as_12
# Per-part extra linear scale (empty). Tried in the validation session (V3): the searchlight posts x0.5 more, because after
# V1 they landed 40-60 m from a wreck that fell 279 m (pods / nacelles / rudder 7.5-32 m). Reverted: with a 0.95-1.05 m/s
# up-kick the posts no longer leave their gantry slabs on a ship that dies at rest (as_13 t_death: |d| 2-9 cm, 4 FAIL).
KICK_PART_LIN_SCALE = {}
KICK = dict((k, (tuple(round(x * KICK_LIN_SCALE * KICK_PART_LIN_SCALE.get(k, 1.0), 3) for x in lin),
                 tuple(round(x * KICK_ANG_SCALE, 3) for x in ang)))
            for k, (lin, ang) in KICK_BASE.items())
_PB = H.read_json('part_bounds.json')['bones']


def com_rest(b):
    """centre of the Wreck body's box (uniform box = its centre of mass), component rest space (as_12 _part_plan)"""
    parts = {'Turbine_L': ['Turbine_L', 'Turbine_L_Rotor'], 'Turbine_R': ['Turbine_R', 'Turbine_R_Rotor']}.get(b, [b])
    if b.startswith('SearchLight_'):
        parts = [b, b + '_Head']
    mn = [min(_PB[x]['min'][i] for x in parts) for i in range(3)]
    mx = [max(_PB[x]['max'][i] for x in parts) for i in range(3)]
    return [0.5 * (mn[i] + mx[i]) for i in range(3)]


def pt_at(rec, b, p_rest):
    pos, q = rec[b]
    rp, rq = REST[b]
    return add(pos, qrot(qmul(q, qinv(rq)), sub(p_rest, rp)))


def t_death():
    alive_n, dead_n = 30, 30
    br = ['Thruster_' + p for p in PODS] + ['Turbine_' + s for s in FANS] + ['Rudder'] + ['SearchLight_' + L for L in LIGHTS]
    cn = ['Cannon_' + c for c in CANNONS] + ['Cannon_%s_Barrel' % c for c in CANNONS]
    rr = []
    r = run('death', lambda f: {'bIsDead': f >= alive_n}, alive_n + dead_n, bones=br + cn + ['Hull', 'Helm_Wheel'],
            every=1, inst_out=rr)
    inst = rr[0]
    tr = r['track']
    pre = tr[alive_n - 1]
    a0 = max(length(sub(pre[b][0], REST[b][0])) for b in br + cn)
    ok(a0 < 0.05, 'alive frames 0..%d: Wreck pass-through leaves the pose alone (max %.4f cm)' % (alive_n - 1, a0))
    res = {}
    t = dead_n * DT
    last = alive_n + dead_n - 1
    for b in br:
        c0 = com_rest(b)
        com = [pt_at(tr[f], b, c0) for f in range(alive_n - 1, last + 1)]     # index 0 = last alive frame
        d = sub(com[-1], c0)
        v1 = scl(sub(com[1], com[0]), 1.0 / DT)                 # first dead frame (kick + one step of gravity)
        va = (com[6][2] - com[1][2]) / (5 * DT)
        vb = (com[-1][2] - com[-6][2]) / (5 * DT)
        az = (vb - va) / ((len(com) - 6 - 1) * DT)
        kick = KICK[b][0]
        if b.startswith('Turbine_'):
            # session 3 (R6): the limp rod (1 kg) hangs on the 6 kg nacelle and takes its share of the kick
            kick = scl(list(kick), 6.0 / 7.0)
        dk = length(sub(v1, add(list(kick), [0.0, 0.0, -981.0 * DT])))
        # validation 2026-11-22: the halved kick (as_12 V1) brings SearchLight_FwdC back near its start after 0.5 s (up
        # 105 cm, down 123), so 'moved > 40 cm' became 'moved > 20 cm and on its ballistic path kick t - g t^2 / 2'
        exp_d = add(scl(list(kick), t), [0.0, 0.0, -0.5 * 981.0 * t * t])
        dev = length(sub(d, exp_d))
        res[b] = {'com_disp': d, 'v_first_dead': v1, 'z_accel': az, 'ballistic_dev': dev}
        ok(length(d) > 20.0 and dev < max(25.0, 0.2 * length(exp_d)) and -1050.0 < az < -900.0 and dk < 40.0,
           'dead %.2f s: break-off %s COM moved %s (|d| %.0f cm; ballistic %s, off by %.1f cm); first dead frame v %s (kick %s); '
           'z accel %.0f cm/s2' % (t, b, f3(d), length(d), f3(exp_d), dev, f3(v1), f3(kick), az))
    for b in cn:
        d = sub(r['final'][b][0], REST[b][0])
        ang = qang(r['final'][b][1], REST[b][1])
        res[b] = {'d': d, 'deg': ang}
        out('INFO', 'dead %.2f s: cannon part %s pivot moved %s, turned %.1f deg (limp joint, no drive)' % (t, b, f3(d), ang))
    car = [length(sub(r['final']['Cannon_' + c][0], REST['Cannon_' + c][0])) for c in CANNONS]
    ok(max(car) < 2.0, 'dead: cannon carriages stay jointed to the hull (pivot offset max %.2f cm)' % max(car))
    tilt = [qang(r['final']['Cannon_' + c][1], REST['Cannon_' + c][1]) for c in CANNONS]
    ok(max(tilt) < 5.0, 'dead 0.50 s, ship level: limp carriages rest on their deck pads (tilt %s deg, want < 5)' % (
        ', '.join('%.2f' % x for x in tilt)))
    hull = length(sub(r['final']['Hull'][0], REST['Hull'][0]))
    ok(hull < 0.01, 'kinematic Hull stays put (%.4f cm; no world here, the real ship falls with its actor)' % hull)
    v = inst.get_variable_as_string('bDeathKickDone')
    ok(v.lower() == 'true', 'death kick latch bDeathKickDone = %s after the first dead frame' % v)
    RES['death'] = res
    # no kick: latch pre-set -> plain free fall of the COM
    r2 = run('death_nokick', lambda f: {'bIsDead': f >= alive_n, 'bDeathKickDone': True}, alive_n + dead_n,
             bones=['Thruster_FL', 'SearchLight_FwdC', 'Turbine_L'])
    c0 = com_rest('SearchLight_FwdC')
    d = sub(pt_at(r2['final'], 'SearchLight_FwdC', c0), c0)
    ok(length(d) < 5.0, 'no kick (latch pre-set): SearchLight_FwdC stays standing on its gantry slab (moved %s)' % f3(d))
    for b in ('Thruster_FL', 'Turbine_L'):
        c0 = com_rest(b)
        d = sub(pt_at(r2['final'], b, c0), c0)
        fall = 0.5 * 981.0 * t * t
        ok(abs(d[2] + fall) < 0.05 * fall and math.hypot(d[0], d[1]) < 1.0, 'no kick (latch pre-set): %s COM falls %.1f cm '
           'in %.2f s (0.5 g t^2 = %.1f; damping 0.05/s), sideways %.2f cm' % (b, -d[2], t, fall, math.hypot(d[0], d[1])))


def t_death_s3():
    """session 3: R3 kick gate (late join), R6 rods do not snap at death, R5 parts land on the deck / gantry slabs"""
    alive_n, dead_n = 30, 30
    t = dead_n * DT
    rr = []
    bl = ['Thruster_FL', 'SearchLight_FwdC', 'Turbine_L']
    r = run('death_late', lambda f: {'bIsDead': f >= alive_n, 'DeathTime': 3.0 if f >= alive_n else 0.0}, alive_n + dead_n,
            bones=bl, inst_out=rr)
    c0 = com_rest('SearchLight_FwdC')
    d = sub(pt_at(r['final'], 'SearchLight_FwdC', c0), c0)
    ok(length(d) < 5.0, 'R3 late join: SearchLight_FwdC gets no kick and stays standing on its gantry slab (moved %s)' % f3(d))
    for b in ('Thruster_FL', 'Turbine_L'):
        c0 = com_rest(b)
        d = sub(pt_at(r['final'], b, c0), c0)
        fall = 0.5 * 981.0 * t * t
        ok(abs(d[2] + fall) < 0.05 * fall and math.hypot(d[0], d[1]) < 1.0, 'R3 late join (dead with DeathTime 3 s from the '
           'first frame): %s gets no kick, COM falls %.1f cm in %.2f s (free fall %.1f), sideways %.2f cm'
           % (b, -d[2], t, fall, math.hypot(d[0], d[1])))
    v = rr[0].get_variable_as_string('bDeathKickDone')
    ok(v.lower() == 'false', 'R3 late join: latch bDeathKickDone stays %s (the kick branch never ran)' % v)
    # fresh death with a running DeathTime: kicks as before
    r = run('death_fresh', lambda f: {'bIsDead': f >= alive_n, 'DeathTime': max(0.0, (f - alive_n) * DT)}, alive_n + 3,
            bones=['SearchLight_FwdC'], every=1)
    c0 = com_rest('SearchLight_FwdC')
    v1 = scl(sub(pt_at(r['track'][alive_n], 'SearchLight_FwdC', c0), pt_at(r['track'][alive_n - 1], 'SearchLight_FwdC', c0)), 1.0 / DT)
    kz = KICK['SearchLight_FwdC'][0][2]
    ok(v1[2] > 0.7 * kz, 'R3 fresh death (DeathTime 0, 1/60, ...): SearchLight_FwdC first dead frame v %s (kick %s, want vz > %.0f)'
       % (f3(v1), f3(KICK['SearchLight_FwdC'][0]), 0.7 * kz))
    # rods: wobble from a nacelle yaw step, then die mid-wobble: no snap of the rod relative to its nacelle
    die = 24
    r = run('rod_pop', lambda f: {'TurbineYawDeg_L': 12.0 if f >= 2 else 0.0, 'bIsDead': f >= die,
                                  'DeathTime': max(0.0, (f - die) * DT), 'bDeathKickDone': True},
            die + 12, bones=['Turbine_L', 'Turbine_L_Rod'], every=1)
    rel0 = qmul(qinv(REST['Turbine_L'][1]), REST['Turbine_L_Rod'][1])

    def rel(f):
        x = r['track'][f]
        return qmul(qinv(x['Turbine_L'][1]), x['Turbine_L_Rod'][1])
    wob = qang(rel(die - 1), rel0)
    steps = [qang(rel(f), rel(f - 1)) for f in range(die - 6, die + 6)]
    jump = qang(rel(die), rel(die - 1))
    before = max(steps[:5])
    ok(jump <= before + 1.0, 'R6 rods at death: rod vs nacelle turns %.2f deg in the first dead frame (alive frames up to %.2f '
       'per frame; wobble at death %.2f deg off its rest; per-frame steps %s)' % (jump, before, wob,
                                                                               ', '.join('%.2f' % x for x in steps)),
       soft=wob < 0.5)
    RES['rod_pop'] = {'wobble_at_death': wob, 'jump': jump, 'steps': steps}
    # landing: 3 s dead, ship level and still (no world), latch pre-set (no kick): the posts must stay standing on
    # their gantry slabs and the cannons on their deck pads, the pods / nacelles / rudder (under or beside the hull) fall
    bl = ['SearchLight_' + L for L in LIGHTS] + ['Thruster_FL', 'Turbine_L', 'Rudder']
    n = 5 + 180
    r = run('landing', lambda f: {'bIsDead': f >= 5, 'DeathTime': max(0.0, (f - 5) * DT), 'bDeathKickDone': True}, n,
            bones=bl, every=15)
    res = {}
    for b in bl:
        c0 = com_rest(b)
        zs = [pt_at(r['track'][f], b, c0)[2] for f in sorted(r['track'])]
        p_end = pt_at(r['final'], b, c0)
        vz = (zs[-1] - zs[-3]) / (30 * DT)
        res[b] = {'com_end': p_end, 'drop': c0[2] - p_end[2], 'vz_end': vz, 'z_track': [round(z, 1) for z in zs]}
        out('INFO', 'no kick, dead 3 s: %s COM %s -> %s (drop %.1f cm), vz at the end %.0f cm/s' % (b, f3(c0), f3(p_end), c0[2] - p_end[2], vz))
    drops = [res['SearchLight_' + L]['drop'] for L in LIGHTS]
    ok(max(drops) < 5.0, 'R5: unkicked searchlight posts stay standing on their gantry slabs for 3 s (COM drop %s cm; '
       'without slabs they fell 44 m)' % ', '.join('%.1f' % x for x in drops))
    RES['landing'] = res


# ---- cross-check with the Blender test sweep (A_Airship_TestSweep, 30 fps, segments of 2 s, value at t = 0.25)
SWEEP = [  # (label, segment index, t, {var: value}, bones, sign: +1 Blender = contract, -1 opposite)
    ('NozzlePitchDeg +5', 0, 0.25, dict(('NozzlePitchDeg_' + p, 5.0) for p in PODS), ['Thruster_%s_Nozzle' % p for p in PODS], 1),
    ('NozzleRollDeg +5', 1, 0.25, dict(('NozzleRollDeg_' + p, 5.0) for p in PODS), ['Thruster_%s_Nozzle' % p for p in PODS], 1),
    ('NozzleFlareDeg +35', 2, 0.25, dict(('NozzleFlareDeg_' + p, 35.0) for p in PODS),
     ['Thruster_%s_Petal%02d' % (p, k) for p in PODS for k in range(12)], 1),
    ('TurbineYawDeg +12', 4, 0.25, {'TurbineYawDeg_L': 12.0, 'TurbineYawDeg_R': 12.0}, ['Turbine_L', 'Turbine_R'], 1),
    ('RotorAngleDeg 108', 5, 0.15, {'RotorAngleDeg_L': 108.0, 'RotorAngleDeg_R': 108.0}, ['Turbine_L_Rotor', 'Turbine_R_Rotor'], -1),
    ('RudderDeg +30', 7, 0.25, {'RudderDeg': 30.0}, ['Rudder'], -1),
    ('WheelAngleDeg 381.8', 8, 0.25, {'WheelAngleDeg': 540.0 * math.sin(math.pi * 0.25)}, ['Helm_Wheel'], -1),
    ('CannonYawDeg +20', 9, 0.25, dict(('CannonYawDeg_' + c, 20.0) for c in CANNONS), ['Cannon_' + c for c in CANNONS], -1),
    # 8.75 = the Blender test anim's key here (rig_build.py: 8.75 sin(2 pi t) at t = 0.25), not the C++ clamp (8.5):
    # a settled pose compared bone by bone, so it must stay the anim's value
    ('CannonElevDeg +8.75', 10, 0.25, dict(('CannonElevDeg_' + c, 8.75) for c in CANNONS),
     ['Cannon_%s_Barrel' % c for c in CANNONS] + ['Cannon_%s_Muzzle' % c for c in CANNONS] + ['Cannon_%s_Quoin' % c for c in CANNONS], 1),
    ('CannonRecoilCm 60', 11, 0.15, dict(('CannonRecoilCm_' + c, 60.0) for c in CANNONS),
     ['Cannon_' + c for c in CANNONS] + ['Cannon_%s_Wheel_%s' % (c, w) for c in CANNONS for w in ('FL', 'FR', 'BL', 'BR')], 1),
    ('SearchLightPanDeg 90', 13, 0.25, {'SearchLightPanDeg': 90.0}, ['SearchLight_%s_Head' % L for L in ('AftL', 'MidL')], -1),
]


def t_sweep():
    anim = unreal.EditorAssetLibrary.load_asset('/Game/Assets/MyShip/Drivable/A_Airship_TestSweep')
    if anim is None:
        out('WARN', 'A_Airship_TestSweep missing: sweep cross-check skipped')
        return
    APE = unreal.AnimPoseExtensions
    opts = unreal.AnimPoseEvaluationOptions()
    res = {}
    for label, seg, tt, vals, bones, sign in SWEEP:
        time_s = (60 * seg + 60 * tt) / 30.0
        try:
            pose = APE.get_anim_pose_at_time(anim, time_s, opts)
        except Exception as e:  # noqa: BLE001
            out('WARN', 'get_anim_pose_at_time failed (%s): sweep cross-check skipped' % e)
            return
        anim_tf = {}
        for b in bones:
            t_ = APE.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD)
            anim_tf[b] = ([t_.translation.x, t_.translation.y, t_.translation.z],
                          [t_.rotation.x, t_.rotation.y, t_.rotation.z, t_.rotation.w])
        rig_vals = dict((k, v * sign) for k, v in vals.items())
        r = run('sweep_' + label, rig_vals, SETTLE, bones=bones)
        wp = max(length(sub(r['final'][b][0], anim_tf[b][0])) for b in bones)
        wr = max(qang(r['final'][b][1], anim_tf[b][1]) for b in bones)
        # what the anim itself did (to state the sign difference)
        moved_anim = max(qang(anim_tf[b][1], REST[b][1]) for b in bones)
        txt = 'test sweep t=%.2f s %s: rig with %s value matches the Blender anim on %d bones (worst %.3f cm, %.3f deg; ' \
              'the anim turns them up to %.1f deg)' % (time_s, label, 'the SAME' if sign > 0 else 'the NEGATED', len(bones),
                                                     wp, wr, moved_anim)
        ok(wp < 0.5 and wr < 0.2, txt)
        res[label] = {'time': time_s, 'sign': sign, 'worst_cm': wp, 'worst_deg': wr}
    RES['sweep'] = res
    out('INFO', 'sign note: the Blender test sweep turns RudderDeg, WheelAngleDeg, CannonYawDeg, SearchLightPanDeg and RotorAngleDeg the '
        'opposite way to RIG_CONTRACT 5 (Blender +Z/+X rotations = UE -Z/-X after the Y flip); the rig follows the '
        'contract (and the C++: AAirshipPawn::GetCannonDirLocal = FQuat(UpVector, Yaw)).')


def main():
    t0 = time.time()
    if RIG is None:
        out('FAIL', 'no CR_Airship')
        return
    st = RIG.get_editor_property('status')
    ok(st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS),
       'CR_Airship status %s' % st)
    pub = set(str(n) for n in H.make_test_instance(RIG).get_script_accessible_variables())
    want = set(ALL_FLOATS + ['bIsDead'])
    ok(want <= pub and 'bDeathKickDone' not in pub, 'public rig variables: %d, all 37 of RIG_CONTRACT 5 present%s' % (
        len(pub), '' if want <= pub else ' MISSING %s' % sorted(want - pub)))
    for fn in (t_components, t_rest, t_nozzles, t_flare, t_turbines, t_steer, t_cannons, t_lights, t_dynamics, t_death,
               t_death_s3, t_sweep):
        ts = time.time()
        try:
            fn()
        except Exception:  # noqa: BLE001
            out('FAIL', '%s crashed: %s' % (fn.__name__, traceback.format_exc()))
        out('INFO', '%s took %.1f s' % (fn.__name__, time.time() - ts))
    out('INFO', 'eval took %.1f s' % (time.time() - t0))


try:
    main()
except Exception:  # noqa: BLE001
    out('FAIL', traceback.format_exc())
_d = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
with open(os.path.join(_d, 'cr_eval.txt'), 'w') as _f:
    _f.write('CR_Airship in-editor evaluation (as_13_cr_eval.py), %s, dt %.4f s, settle %d frames\n' % (
        time.strftime('%Y-%m-%d %H:%M:%S'), DT, SETTLE))
    _f.write('\n'.join(LINES) + '\n')
    _f.write('RESULT: %s %s\n' % ('PASS' if not CNT.get('FAIL') else 'FAIL', CNT))
with open(os.path.join(_d, 'cr_eval.json'), 'w') as _f:
    json.dump(RES, _f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT.get('FAIL') else 'FAIL', CNT))
