# bw_04b_cr_check.py -- checks CR_Burrower after bw_04_control_rig.py (UE 5.8 editor, inbox harness).
#
# Run:  Docs/Burrower/scripts/harness/inbox.sh 04b Docs/Burrower/scripts/bw_04b_cr_check.py 600
# grep the .out for FAIL: / WARN:, the last line is RESULT:. Summary: <project>/Saved/Burrower/bw_04b_cr_check.json,
# raw per-test data: Saved/Burrower/bw04b_*.json (one per test case, written by bw_cr_helpers.run_rig_test).
#
# Changes NOTHING on disk except those JSON files: no asset is saved, created or deleted. The rig is executed on
# throw-away UControlRig instances (rig.create_control_rig(), moved to /Engine/Transient by the helper), so no PIE
# and no frames are needed: everything runs synchronously in this one call (notes_cr_core.md section 7).
#
# What it checks:
#   1. CR_Burrower exists, is a UControlRigBlueprint, compile status, unsaved changes.
#   2. Variables: names, types, public flags (= what the AnimBP Control Rig node can expose) vs UBurrowerAnimInstance.
#   3. Graph listing: events, node counts per struct and per stage (node-name prefixes from bw_04), comment nodes,
#      links; the execution order of Construction and Forwards Solve (recipe Step 4 / 5 order).
#   4. Recipe Step 8.1 (numeric): WaveTime 0 / 0.25 / 0.5 / 0.75 (amplitude 10, phase 65, pitch 3): the local rotation
#      delta of J1..J4, seen in the parent's rest frame, must equal Rz(yaw_i) * Ry(pitch_i) with
#      theta_i = WaveTime * WaveTimeToRadians - i * Phase, yaw_i = rad(Amp * wy_i) sin(theta_i),
#      pitch_i = rad(PitchAmp * wp_i) cos(theta_i); the J4_Tail yaw must change with WaveTime; J0_Head and Rotor
#      stay at rest.
#   5. Recipe Step 8.2 (numeric): RotorAngleDeg 0 / 45 / 90: Rotor keeps its origin (~(977.9, 0, 180.5)) and is
#      rotated by exactly that angle about component +X.
#   6. Extra (RUN_PHYSICS_CHECKS): the rig components the Construction event spawns; 120 alive frames: chain ends
#      pinned, no explosion; 30 dead frames: the ragdoll falls (no world here, so no ground: in PIE it lands on the
#      tiles), the rotor stays on the dead head, re-pinned chain ends follow J1.
#   Recipe Step 8.3-8.6 (visualization in the rig editor, PIE, stat anim) stay manual.
#
# Options (send a wrapper that sets them, then exec()s this file): BW04B_RUN_NUMERIC, BW04B_RUN_PHYSICS_CHECKS.

import importlib
import math
import os
import sys
import time
import traceback

import unreal

RUN_NUMERIC = True
RUN_PHYSICS_CHECKS = True
_bw04b_g = globals()
for _bw04b_k in ('RUN_NUMERIC', 'RUN_PHYSICS_CHECKS'):
    if 'BW04B_' + _bw04b_k in _bw04b_g:
        _bw04b_g[_bw04b_k] = bool(_bw04b_g.pop('BW04B_' + _bw04b_k))

BW04B_SCRIPTS_DIR = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts'
if not os.path.isdir(BW04B_SCRIPTS_DIR):
    BW04B_SCRIPTS_DIR = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs', 'Burrower', 'scripts')
if BW04B_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, BW04B_SCRIPTS_DIR)
import bw_cr_helpers as H  # noqa: E402
importlib.reload(H)

_bw04b_counts = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def _bw04b_out(tag, msg):
    _bw04b_counts[tag] = _bw04b_counts.get(tag, 0) + 1
    print('%s: %s' % (tag, msg))


H._out = _bw04b_out
info, warn, passed, fail = H.info, H.warn, H.passed, H.fail


def _ok(cond, msg, bad=None):
    (passed if cond else (bad or fail))(msg)
    return bool(cond)


# ------------------------------------------------------------------------------------------------- expectations
EXPECT_VARS = [  # name, type as get_member_variables reports it, public (UBurrowerAnimInstance.h)
    ('RotorAngleDeg', 'float', True), ('RotorSpinSpeed', 'float', True), ('WaveTime', 'float', True),
    ('WaveAmplitudeDeg', 'float', True), ('WavePhasePerJointDeg', 'float', True),
    ('WavePitchAmplitudeDeg', 'float', True), ('Speed', 'float', True), ('bIsDead', 'bool', True),
    ('DeathTime', 'float', True), ('WaveTimeToRadians', 'float', False)]
BODY = ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail']
HOSE_CHAINS = [('pipe_upperhose_l', 7), ('pipe_upperhose_r', 5)]
WIRE_CHAINS = [('pipe_uppercable_l', 7), ('pipe_uppercable_r', 9), ('pipe_side_l_a', 7), ('pipe_side_l_b', 7),
               ('pipe_side_r_a', 7), ('pipe_side_r_b', 7)]
CHAIN_LEN = dict(HOSE_CHAINS + WIRE_CHAINS)
WAVE_JOINTS = [('J1_Forequarters', 'J0_Head', 1, 0.40, 0.65), ('J2_Midbody', 'J1_Forequarters', 2, 0.60, 0.15),
               ('J3_Hindbody', 'J2_Midbody', 3, 0.80, 0.65), ('J4_Tail', 'J3_Hindbody', 4, 1.00, 1.00)]
ROTOR_REST = (977.9, 0.0, 180.5)
STAGE_OF_PREFIX = [  # node-name prefix (bw_04) -> stage
    ('ConstructionEvent', 'events'), ('ForwardsSolve', 'events'), ('Comment_', 'comments'),
    ('Rag', 'ragdoll'), ('DeadAlpha', 'ragdoll'), ('StepRagdoll', 'ragdoll'), ('InstRagdoll', 'ragdoll'),
    ('Hose', 'hoses'), ('StepHoses', 'hoses'), ('InstHoses', 'hoses'),
    ('Wire', 'wires'), ('SideHoseChains', 'wires'), ('CableChains', 'wires'), ('Pin_', 'wires'),
    ('FlankCollider', 'wires'), ('StepWires', 'wires'), ('InstWires', 'wires'),
    ('Wave_', 'wave'), ('W1_', 'wave'), ('W2_', 'wave'), ('W3_', 'wave'), ('W4_', 'wave'),
    ('Rotor_', 'rotor'), ('EndPin_', 'repin')]


def chain_bones(prefix):
    return ['%s_%02d' % (prefix, i) for i in range(1, CHAIN_LEN[prefix] + 1)] + [prefix + '_end']


def _stage_of(name):
    for p, s in STAGE_OF_PREFIX:
        if name.startswith(p):
            return s
    return 'other'


# ------------------------------------------------------------------------------------------------- quaternion maths
# [x, y, z, w], Hamilton product = FQuat::operator* ((A*B).RotateVector(v) = A.RotateVector(B.RotateVector(v)))
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def qinv(q):
    n = sum(c * c for c in q) or 1.0
    return [-q[0] / n, -q[1] / n, -q[2] / n, q[3] / n]


def qaxis(axis, angle):
    s = math.sin(angle * 0.5)
    return [axis[0] * s, axis[1] * s, axis[2] * s, math.cos(angle * 0.5)]


def qrot(q, v):
    p = qmul(qmul(q, [v[0], v[1], v[2], 0.0]), qinv(q))
    return p[:3]


def vsub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def vadd(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def finite(vals):
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in vals)


def follow_pos(bone_data, point_rest_pos):
    """Where a point rigidly attached to a bone is now: p_now + R_now (R_rest^-1 (point_rest - p_rest)).
    bone_data: one run_rig_test bone entry (global_pos/global_quat now, rest_pos/rest_quat)."""
    off = qrot(qinv(bone_data['rest_quat']), vsub(point_rest_pos, bone_data['rest_pos']))
    return vadd(bone_data['global_pos'], qrot(bone_data['global_quat'], off))


# ------------------------------------------------------------------------------------------------- checks
def _check_asset():
    rig = H.load_asset(H.RIG_PATH)
    if rig is None:
        fail('%s does not exist: run bw_04_control_rig.py first' % H.RIG_PATH)
        return None
    if not isinstance(rig, unreal.ControlRigBlueprint):
        fail('%s is a %s, not a ControlRigBlueprint' % (H.RIG_PATH, rig.get_class().get_name()))
        return None
    passed('%s is a ControlRigBlueprint' % H.RIG_PATH)
    try:
        dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
        # A WARN here is expected after an earlier bw_04b run in the same editor session: make_test_instance's
        # rename (Python passes REN_None, PyWrapperObject.cpp:744) calls Modify(true) -> MarkPackageDirty on the old
        # outer's package = CR_Burrower (Obj.cpp:399-414). Nothing on disk changes; it only clears with a save/restart.
        _ok(H.RIG_PATH not in dirty, 'CR_Burrower has no unsaved changes%s' % (
            '' if H.RIG_PATH not in dirty else ' (expected if bw_04b already ran in this session: its test '
            'instances dirty the package when moved to /Engine/Transient; harmless)'), warn)
    except Exception as e:  # noqa: BLE001
        warn('cannot list dirty packages: %s' % e)
    status = rig.get_editor_property('status')
    good = (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS)
    if status in good:
        passed('compile status %s' % status)
    else:
        warn('compile status %s: compiling in memory (nothing is saved) to report errors' % status)
        if not H.compile_rig(rig):
            fail('CR_Burrower does not compile: numeric checks would be meaningless')
            return None
    return rig


def _check_variables(rig, summary):
    have = H.member_variables(rig)
    out = {}
    for name in sorted(have):
        v = have[name]
        try:
            pub = bool(v.get_editor_property('public'))
        except Exception:  # noqa: BLE001
            pub = None
        out[name] = {'type': str(v.get_editor_property('cpp_type')), 'default': str(v.get_editor_property('default_value')),
                     'public': pub}
        info('variable %-24s %-12s public=%-5s default=%r' % (name, out[name]['type'], pub, out[name]['default']))
    for name, cpp, pub in EXPECT_VARS:
        v = out.get(name)
        if v is None:
            fail('variable %s missing' % name)
            continue
        _ok(v['type'] == cpp, 'variable %s type %s (expected %s)' % (name, v['type'], cpp))
        if v['public'] is not None:
            _ok(v['public'] == pub, 'variable %s public=%s (expected %s)' % (name, v['public'], pub))
    try:
        inst = H.make_test_instance(rig)
        acc = set(str(n) for n in inst.get_script_accessible_variables())   # RigVMHost.h:165-166 (IsPublic)
        for name, _, pub in EXPECT_VARS:
            if pub:
                _ok(name in acc, 'instance exposes %s as public (AnimBP node input)' % name)
            else:
                _ok(name not in acc, 'instance keeps %s private' % name)
    except H.BwError as e:
        fail('could not create a test instance: %s' % e)
    summary['variables'] = out


def _exec_chain(gr, start):
    order, seen, cur = [], set(), start
    while cur and cur not in seen:
        seen.add(cur)
        order.append(cur)
        try:
            pin = gr.pin(gr.exec_out(cur))
        except H.BwError:
            break
        targets = list(pin.get_linked_target_pins())
        if len(targets) > 1:
            warn('node %s has %d execute links; following the first' % (cur, len(targets)))
        cur = targets[0].get_node().get_name() if targets else None
    return order


def _check_order(order, expected, label):
    present = [n for n in expected if n in order]
    idx = [order.index(n) for n in present]
    ok = all(idx[i] < idx[i + 1] for i in range(len(idx) - 1))
    _ok(ok, '%s order: %d key nodes in recipe order (%s ... %s)'
        % (label, len(present), present[0] if present else '-', present[-1] if present else '-'))
    if not ok:
        info('%s actual order: %s' % (label, ' > '.join(order)))
    return ok


def _check_graph(rig, summary):
    gr = H.RigGraph(rig)
    graph = gr.g
    nodes = list(graph.get_nodes())
    links = list(graph.get_links())
    events, by_struct, by_stage, mutable = [], {}, {}, []
    for n in nodes:
        name = n.get_name()
        if isinstance(n, unreal.RigVMCommentNode):
            kind = 'Comment'
        elif isinstance(n, unreal.RigVMVariableNode):
            kind = 'Variable%s %s' % ('Get' if n.is_getter() else 'Set', n.get_variable_name())
        else:
            try:
                s = n.get_script_struct()
                kind = s.get_name() if s else n.get_class().get_name()
            except Exception:  # noqa: BLE001
                kind = n.get_class().get_name()
        by_struct[kind] = by_struct.get(kind, 0) + 1
        st = _stage_of(name)
        by_stage[st] = by_stage.get(st, 0) + 1
        try:
            if n.is_event():
                events.append((name, str(n.get_event_name())))
        except Exception:  # noqa: BLE001
            pass
        if not isinstance(n, unreal.RigVMCommentNode) and any(p.is_execute_context() for p in n.get_pins()):
            mutable.append(name)
    info('graph %s: %d nodes, %d links, events %s' % (graph.get_name(), len(nodes), len(links), events))
    for k in sorted(by_struct):
        info('  %4d x %s' % (by_struct[k], k))
    for k in sorted(by_stage):
        info('  stage %-9s %4d nodes' % (k, by_stage[k]))
    ev_names = dict((e, n) for n, e in events)
    _ok(H.EV_CONSTRUCTION in ev_names, 'Construction event present')
    _ok(H.EV_FORWARDS in ev_names, 'Forwards Solve event present')
    _ok(len(events) == 2, 'exactly 2 events (%d)' % len(events), warn)
    for m in H.root_models(rig):
        if m.get_name() != graph.get_name():
            warn('extra graph %s with %d nodes (not built by bw_04)' % (m.get_name(), len(m.get_nodes())))

    chains = {}
    for ev, label in ((H.EV_CONSTRUCTION, 'Construction'), (H.EV_FORWARDS, 'Forwards Solve')):
        if ev in ev_names:
            chains[label] = _exec_chain(gr, ev_names[ev])
            info('%s chain: %d nodes: %s' % (label, len(chains[label]), ' > '.join(chains[label][:60])
                                             + (' ...' if len(chains[label]) > 60 else '')))
    on_chain = set(n for c in chains.values() for n in c)
    off = [n for n in mutable if n not in on_chain]
    _ok(not off, 'every mutable node is on an execution chain%s' % ((' (not: %s)' % ', '.join(off)) if off else ''))

    hose_c = []
    for ch, _ in HOSE_CHAINS:
        for k, b in enumerate(chain_bones(ch)):
            hose_c.append('HoseBody_' + b)
            if k:
                hose_c.append('HoseJoint_' + b)
    wire_names = [c for c, _ in WIRE_CHAINS]
    side_first = [c for c in wire_names if c.startswith('pipe_side')] + [c for c in wire_names if not c.startswith('pipe_side')]
    exp_c = (['ConstructionEvent', 'RagdollSolver', 'RagdollFromPA'] +
             [x for b in BODY for x in ('RagSim_' + b, 'RagDamp_' + b)] + ['HoseSolver'] + hose_c +
             ['WireSolver', 'SideHoseChains', 'CableChains'] +
             [x for c in side_first for x in ('Pin_' + c + '_01', 'Pin_' + c + '_end')] +
             ['FlankCollider', 'InstRagdoll', 'InstHoses', 'InstWires'])
    repin = [c for c, _ in HOSE_CHAINS] + wire_names
    exp_f = (['ForwardsSolve', 'W1_Set', 'W2_Set', 'W3_Set', 'W4_Set', 'StepRagdoll', 'Rotor_Set', 'Rotor_SetRot'] +
             ['EndPin_Store_' + c for c in repin] + ['StepHoses', 'StepWires'] + ['EndPin_Set_' + c for c in repin])
    if 'Construction' in chains:
        _check_order(chains['Construction'], exp_c, 'Construction')
    if 'Forwards Solve' in chains:
        _check_order(chains['Forwards Solve'], exp_f, 'Forwards Solve')
    summary['graph'] = {'nodes': len(nodes), 'links': len(links), 'events': events, 'by_struct': by_struct,
                        'by_stage': by_stage, 'chains': chains}
    present = set(n.get_name() for n in nodes)
    return present


# ---------------------------------------------------------------------------- numeric (recipe Step 8.1 / 8.2)
def _var_default(rig, name, fallback):
    try:
        return float(str(H.member_variables(rig)[name].get_editor_property('default_value')))
    except Exception:  # noqa: BLE001
        return fallback


def _run(rig, out_name, bones, variables, frames=1, instance=None):
    r = H.run_rig_test(rig, bones=bones, variables=variables, frames=frames, out_name=out_name, instance=instance)
    if r['errors'] or not r['forwards_ok'] or not all(r['forwards_ok']) or r['construction_ok'] is False:
        fail('%s: rig did not run cleanly (construction_ok %s, forwards_ok %s, errors %s)'
             % (out_name, r['construction_ok'], r['forwards_ok'][-3:], r['errors'][:3]))
        return None
    return r


def _at_rest(r, b, tol_cm, tol_deg, label):
    d = r['bones'][b]
    e_pos = H.dist(d['global_pos'], d['rest_pos'])
    e_ang = H.quat_angle_deg(d['global_quat'], d['rest_quat'])
    return _ok(e_pos <= tol_cm and e_ang <= tol_deg, '%s: %s at rest (%.3f cm, %.3f deg)' % (label, b, e_pos, e_ang))


def _wave_tests(rig, summary, present):
    if 'W4_Set' not in present:
        warn('no wave nodes (stage wave off?): Step 8.1 skipped')
        return
    k = _var_default(rig, 'WaveTimeToRadians', 2.0 * math.pi)
    amp, phase, pamp = 10.0, 65.0, 3.0
    info('Step 8.1 wave: WaveAmplitudeDeg %.0f, WavePhasePerJointDeg %.0f, WavePitchAmplitudeDeg %.0f, '
         'WaveTimeToRadians %.6f' % (amp, phase, pamp, k))
    bones = BODY + ['Rotor']
    yaw4 = []
    res = []
    for t in (0.0, 0.25, 0.5, 0.75):
        r = _run(rig, 'bw04b_wave_t%03d' % int(round(t * 100)), bones,
                 {'WaveTime': t, 'WaveAmplitudeDeg': amp, 'WavePhasePerJointDeg': phase,
                  'WavePitchAmplitudeDeg': pamp, 'RotorAngleDeg': 0.0, 'bIsDead': False})
        if r is None:
            continue
        B = r['bones']
        _at_rest(r, 'J0_Head', 0.05, 0.05, 'WaveTime %.2f' % t)
        _at_rest(r, 'Rotor', 0.1, 0.1, 'WaveTime %.2f' % t)
        for bn, parent, i, wy, wp in WAVE_JOINTS:
            theta = t * k - i * math.radians(phase)
            yaw = math.radians(amp * wy) * math.sin(theta)
            pitch = math.radians(pamp * wp) * math.cos(theta)
            rp = B[parent]['rest_quat']
            local_rest = qmul(qinv(rp), B[bn]['rest_quat'])
            delta = qmul(B[bn]['local_quat'], qinv(local_rest))          # NewLocal * Local^-1 = QDelta
            dc = qmul(qmul(rp, delta), qinv(rp))                         # in the parent's rest (= body) frame
            want = qmul(qaxis((0.0, 0.0, 1.0), yaw), qaxis((0.0, 1.0, 0.0), pitch))
            err = H.quat_angle_deg(dc, want)
            fx = qrot(dc, (1.0, 0.0, 0.0))
            m_yaw = math.degrees(math.atan2(fx[1], fx[0]))
            m_pitch = math.degrees(math.atan2(-fx[2], math.hypot(fx[0], fx[1])))
            _ok(err < 0.05, 'WaveTime %.2f %s: yaw %+.3f deg (expected %+.3f), pitch %+.3f deg (expected %+.3f), '
                'error %.4f deg' % (t, bn, m_yaw, math.degrees(yaw), m_pitch, math.degrees(pitch), err))
            res.append({'t': t, 'bone': bn, 'yaw': m_yaw, 'pitch': m_pitch, 'yaw_expected': math.degrees(yaw),
                        'pitch_expected': math.degrees(pitch), 'error_deg': err})
            if bn == 'J4_Tail':
                yaw4.append(m_yaw)
    if len(yaw4) == 4:
        spread = max(yaw4) - min(yaw4)
        _ok(spread > 2.0, 'J4_Tail local yaw changes with WaveTime: %s deg (spread %.2f)'
            % (', '.join('%+.2f' % y for y in yaw4), spread))
    summary['wave'] = res


def _rotor_tests(rig, summary, present):
    if 'Rotor_Set' not in present:
        warn('no rotor nodes (stage rotor off?): Step 8.2 skipped')
        return
    res = []
    for a in (0.0, 45.0, 90.0):
        r = _run(rig, 'bw04b_rotor_%03d' % int(a), ['Rotor', 'J0_Head'],
                 {'RotorAngleDeg': a, 'WaveAmplitudeDeg': 0.0, 'WavePitchAmplitudeDeg': 0.0, 'WaveTime': 0.0,
                  'bIsDead': False})
        if r is None:
            continue
        R = r['bones']['Rotor']
        e_pos = H.dist(R['global_pos'], R['rest_pos'])
        e_rest = H.dist(R['rest_pos'], ROTOR_REST)
        dq = qmul(R['global_quat'], qinv(R['rest_quat']))
        ang = H.quat_angle_deg(R['global_quat'], R['rest_quat'])
        v = dq[:3]
        n = math.sqrt(sum(c * c for c in v))
        sgn = 1.0 if dq[3] >= 0.0 else -1.0
        axis = [sgn * c / n for c in v] if n > 1e-9 else [0.0, 0.0, 0.0]
        _ok(e_pos < 0.1, 'RotorAngleDeg %.0f: Rotor origin fixed (moved %.3f cm, at (%.1f, %.1f, %.1f))'
            % ((a, e_pos) + tuple(R['global_pos'])))
        _ok(e_rest < 2.0, 'RotorAngleDeg %.0f: Rotor origin %.2f cm from the rotor centre %s' % (a, e_rest, ROTOR_REST))
        _ok(abs(ang - a) < 0.2, 'RotorAngleDeg %.0f: rotated %.3f deg' % (a, ang))
        if a > 0.0:
            _ok(axis[0] > 0.999, 'RotorAngleDeg %.0f: about component +X (axis (%.4f, %.4f, %.4f))' % ((a,) + tuple(axis)))
        _at_rest(r, 'J0_Head', 0.05, 0.05, 'RotorAngleDeg %.0f' % a)
        res.append({'angle': a, 'moved_cm': e_pos, 'rotated_deg': ang, 'axis': axis})
    summary['rotor'] = res


# ---------------------------------------------------------------------------- physics (extra)
def _expected_components(present):
    exp = []
    if 'RagdollSolver' in present:
        exp.append(('root', 'PhysicsSolver'))
        exp += [(b, 'PhysicsBody') for b in BODY]
        exp += [(b, 'PhysicsJoint') for b in BODY[1:]]
    if 'HoseSolver' in present:
        exp.append(('J1_Forequarters', 'PhysicsSolver'))
        for ch, _ in HOSE_CHAINS:
            bs = chain_bones(ch)
            exp += [(b, 'PhysicsBody') for b in bs]
            exp += [(b, 'PhysicsJoint') for b in bs[1:]]
    if 'WireSolver' in present:
        exp.append(('root', 'DynamicsSolver'))
        for ch, _ in WIRE_CHAINS:
            exp += [(b, 'DynamicsParticle') for b in chain_bones(ch)]
        if 'FlankCollider' in present:
            exp.append(('J1_Forequarters', 'DynamicsCollider'))
    return exp


def _physics_tests(rig, summary, present):
    res = {}
    alive = {'WaveAmplitudeDeg': 0.0, 'WavePitchAmplitudeDeg': 0.0, 'WaveTime': 0.0, 'RotorAngleDeg': 0.0,
             'bIsDead': False}
    chain_all = [b for ch in CHAIN_LEN for b in chain_bones(ch)]
    # 1. components spawned by Construction + 120 alive frames
    try:
        inst = H.make_test_instance(rig)
    except H.BwError as e:
        fail('test instance: %s' % e)
        return
    r = _run(rig, 'bw04b_alive_120', ['J1_Forequarters'] + chain_all, alive, frames=120, instance=inst)
    keys = []
    try:
        for ck in inst.get_hierarchy().get_all_component_keys():      # RigHierarchy UFUNCTION (stub L251222)
            ek = ck.get_editor_property('element_key')
            keys.append((str(ek.get_editor_property('name')), str(ck.get_editor_property('name'))))
    except Exception as e:  # noqa: BLE001
        warn('cannot list rig components: %s' % e)
    if keys:
        have = set(keys)
        exp = _expected_components(present)
        miss = [k for k in exp if k not in have]
        _ok(not miss, 'Construction spawned %d components; all %d expected ones exist%s'
            % (len(keys), len(exp), (' - MISSING: %s' % ', '.join('%s/%s' % k for k in miss[:12])) if miss else ''))
        extra = sorted(set(k[1] for k in keys) - set(k[1] for k in exp))
        if extra:
            info('other component names present: %s' % ', '.join(extra))
        res['components'] = len(keys)
    if r is not None and (('HoseSolver' in present) or ('WireSolver' in present)):
        B = r['bones']
        bad = [b for b in B if not finite(B[b]['global_pos'] + B[b]['global_quat'])]
        _ok(not bad, '120 alive frames: all chain bones finite%s' % ((' (NaN/inf: %s)' % ', '.join(bad[:8])) if bad else ''))
        for ch in sorted(CHAIN_LEN):
            on = ('HoseSolver' in present) if ch.startswith('pipe_upperhose') else ('WireSolver' in present)
            if not on:
                continue
            bs = chain_bones(ch)
            d01 = H.dist(B[bs[0]]['global_pos'], B[bs[0]]['rest_pos'])
            dend = H.dist(B[bs[-1]]['global_pos'], B[bs[-1]]['rest_pos'])
            dmid = max(H.dist(B[x]['global_pos'], B[x]['rest_pos']) for x in bs[1:-1])
            _ok(d01 < 0.5, '%s: _01 stays on its anchor (%.3f cm)' % (ch, d01))
            if ('EndPin_Set_' + ch) in present:
                _ok(dend < 0.05, '%s: _end re-pinned to its anchor (%.4f cm)' % (ch, dend))
            else:
                _ok(dend < 5.0, '%s: _end near its anchor without re-pin (%.2f cm)' % (ch, dend), warn)
            _ok(dmid < 100.0, '%s: middle bones settle (max offset from rest %.2f cm)' % (ch, dmid))
            res['alive_' + ch] = {'d01': d01, 'dend': dend, 'dmid': dmid}
    # 2. dead: the ragdoll falls, rotor stays on the head, re-pinned ends follow J1
    if 'StepRagdoll' not in present:
        warn('no ragdoll nodes (stage ragdoll off?): dead test skipped')
        summary['physics'] = res
        return
    dead = dict(alive)
    dead['bIsDead'] = True
    ends = [ch + '_end' for ch in CHAIN_LEN]
    r = _run(rig, 'bw04b_dead_30', BODY + ['Rotor'] + ends, dead, frames=30)
    if r is not None:
        B = r['bones']
        bad = [b for b in B if not finite(B[b]['global_pos'] + B[b]['global_quat'])]
        _ok(not bad, '30 dead frames: all bones finite%s' % ((' (NaN/inf: %s)' % ', '.join(bad)) if bad else ''))
        drop = B['J0_Head']['rest_pos'][2] - B['J0_Head']['global_pos'][2]
        info('dead 0.5 s: J0_Head dropped %.1f cm, J4_Tail %.1f cm (free fall would be ~122 cm; no world = no ground)'
             % (drop, B['J4_Tail']['rest_pos'][2] - B['J4_Tail']['global_pos'][2]))
        _ok(drop > 30.0, 'ragdoll simulates when bIsDead (J0_Head dropped %.1f cm)' % drop, warn)
        if drop <= 30.0:
            info('hint: a World-space ragdoll might need a world to step; check it in PIE (Aura.Burrower.KillAll)')
        if 'Rotor_Set' in present:
            want = follow_pos(B['J0_Head'], B['Rotor']['rest_pos'])
            e = H.dist(B['Rotor']['global_pos'], want)
            want_q = qmul(qmul(B['J0_Head']['global_quat'], qinv(B['J0_Head']['rest_quat'])), B['Rotor']['rest_quat'])
            ea = H.quat_angle_deg(B['Rotor']['global_quat'], want_q)
            _ok(e < 1.0 and ea < 0.5, 'dead: Rotor stays on the falling head (%.3f cm, %.3f deg off)' % (e, ea))
        for ch in sorted(CHAIN_LEN):
            if ('EndPin_Set_' + ch) not in present:
                continue
            want = follow_pos(B['J1_Forequarters'], B[ch + '_end']['rest_pos'])
            e = H.dist(B[ch + '_end']['global_pos'], want)
            _ok(e < 0.5, 'dead: %s_end follows J1_Forequarters (%.3f cm off)' % (ch, e))
        res['dead_drop_cm'] = drop
    summary['physics'] = res


# ------------------------------------------------------------------------------------------------- main
def _bw04b_main():
    summary = {'time': time.strftime('%Y-%m-%d %H:%M:%S')}
    if H.pie_running():
        warn('PIE is running; the checks do not need it and do not save anything')
    rig = _check_asset()
    if rig is None:
        return summary
    _check_variables(rig, summary)
    present = _check_graph(rig, summary)
    if RUN_NUMERIC:
        try:
            _wave_tests(rig, summary, present)
            _rotor_tests(rig, summary, present)
        except Exception as e:  # noqa: BLE001
            fail('numeric checks crashed: %r' % (e,))
            for line in traceback.format_exc().rstrip().split('\n'):
                print('INFO:   ' + line)
    if RUN_PHYSICS_CHECKS:
        try:
            _physics_tests(rig, summary, present)
        except Exception as e:  # noqa: BLE001
            fail('physics checks crashed: %r' % (e,))
            for line in traceback.format_exc().rstrip().split('\n'):
                print('INFO:   ' + line)
    info('recipe Step 8.3-8.6 stay manual: visualization flags on StepHoses/StepWires/StepRagdoll in the rig editor '
         '(Alpha > 0 only; bIsDead default True to see the ragdoll), PIE listen server + client, stat anim')
    return summary


_bw04b_summary = {}
try:
    _bw04b_summary = _bw04b_main() or {}
except Exception as _bw04b_e:  # noqa: BLE001
    fail('unexpected error: %r' % (_bw04b_e,))
    for _bw04b_line in traceback.format_exc().rstrip().split('\n'):
        print('INFO:   ' + _bw04b_line)
_bw04b_summary['counts'] = dict(_bw04b_counts)
try:
    H.write_json('bw_04b_cr_check', _bw04b_summary)
except Exception as _bw04b_e:  # noqa: BLE001
    print('WARN: could not write the summary json: %r' % (_bw04b_e,))
print('RESULT: %s (%d FAIL, %d WARN, %d PASS)' % ('PASS' if _bw04b_counts.get('FAIL', 0) == 0 else 'FAIL',
                                                 _bw04b_counts.get('FAIL', 0), _bw04b_counts.get('WARN', 0),
                                                 _bw04b_counts.get('PASS', 0)))
