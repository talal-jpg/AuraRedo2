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
#   7. Path-follow bend (2026-11-22, RUN_NUMERIC): wave amplitudes 0, FollowYawDeg1 +-10 / FollowPitchDeg1 +-10 move
#      J4_Tail sideways (+yaw -> component -Y) / up (+pitch -> +Z) by > 30 cm; all four +5 compound past J1 alone;
#      FollowYawDeg4 turns only the tail tip; every bone matches the exact single-axis chain rotation; J0_Head and
#      Rotor stay at rest.
#   8. Death kick (2026-11-22, RUN_PHYSICS_CHECKS): the World-space ragdoll steps on a test instance without a world
#      (check 6 measures the fall), so the kick is tested here too: 10 alive + 12 dead frames with DeathVelocity
#      (2000,0,0) carry every body ~400 cm forward against DeathVelocity 0 (once, not every frame), and
#      DeathAngularVelocity (0,0,40) swings the tail toward -Y and spins the body ~+7 deg; bDeathKickDone latches.
#      Plus the graph: Kick_Branch.True chain, Add Force pin values, reset flags that would drop the kick.
#   9. World collision (2026-11-22, bw_04 deviation 29, notes_cr_world_collision.md): RagdollSolver
#      SolverSettings.WorldCollisionType == All (the hex tiles are WorldDynamic, Static gathers WorldStatic only) and
#      WorldCollisionBoundsExpansion >= 2.0 (the gathered world objects lag one frame); IncludePhysics True,
#      IncludeQuery False. Graph read-back only: there is no world here, the landing itself is PIE check (n).
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
FOLLOW_VARS = ['FollowYawDeg%d' % i for i in range(1, 5)] + ['FollowPitchDeg%d' % i for i in range(1, 5)]
EXPECT_VARS = [  # name, type as get_member_variables reports it, public (UBurrowerAnimInstance.h)
    ('RotorAngleDeg', 'float', True), ('RotorSpinSpeed', 'float', True), ('WaveTime', 'float', True),
    ('WaveAmplitudeDeg', 'float', True), ('WavePhasePerJointDeg', 'float', True),
    ('WavePitchAmplitudeDeg', 'float', True), ('Speed', 'float', True), ('bIsDead', 'bool', True),
    ('DeathTime', 'float', True)] + [(v, 'float', True) for v in FOLLOW_VARS] + [
    ('DeathVelocity', 'FVector', True), ('DeathAngularVelocity', 'FVector', True),
    ('WaveTimeToRadians', 'float', False), ('bDeathKickDone', 'bool', False)]
BODY = ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail']
HOSE_CHAINS = [('pipe_upperhose_l', 7), ('pipe_upperhose_r', 5)]
WIRE_CHAINS = [('pipe_uppercable_l', 7), ('pipe_uppercable_r', 9), ('pipe_side_l_a', 7), ('pipe_side_l_b', 7),
               ('pipe_side_r_a', 7), ('pipe_side_r_b', 7)]
CHAIN_LEN = dict(HOSE_CHAINS + WIRE_CHAINS)
# = bw_04_control_rig.WAVE_JOINTS (J2 pitch weight 0.45 since 2026-11-22, was 0.15)
WAVE_JOINTS = [('J1_Forequarters', 'J0_Head', 1, 0.40, 0.65), ('J2_Midbody', 'J1_Forequarters', 2, 0.60, 0.45),
               ('J3_Hindbody', 'J2_Midbody', 3, 0.80, 0.65), ('J4_Tail', 'J3_Hindbody', 4, 1.00, 1.00)]
FOLLOW_JOINTS = ['J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail']
TAIL_TIP_REST = (-1017.4, 0.0, 202.0)   # component space, rigidly on J4_Tail (mesh bounds min x)
ACTOR_ORIGIN_CS = (830.0, 0.0, 187.0)   # mesh relative (-830, 0, -187): = PA J0_Head capsule centre = kick pivot c_0
ROTOR_REST = (977.9, 0.0, 180.5)
STAGE_OF_PREFIX = [  # node-name prefix (bw_04) -> stage
    ('ConstructionEvent', 'events'), ('ForwardsSolve', 'events'), ('Comment_', 'comments'),
    ('Rag', 'ragdoll'), ('DeadAlpha', 'ragdoll'), ('StepRagdoll', 'ragdoll'), ('InstRagdoll', 'ragdoll'),
    ('Kick_', 'ragdoll'),
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


def _branch_chains(gr, order, depth=0):
    """Execution sub-chains hanging off the extra exec outputs (e.g. Kick_Branch.True) of the nodes in `order`:
    {'<node>.<pin>': [nodes]}. _exec_chain follows only exec_out(), which prefers a branch's Completed pin."""
    out = {}
    if depth > 4:
        return out
    d = gr._dirs
    for n in order:
        try:
            main = gr.exec_out(n)
        except H.BwError:
            continue
        for p in gr._exec_pins(n):
            path = p.get_pin_path()
            if path == main or p.get_direction() != d['O']:
                continue
            targets = list(p.get_linked_target_pins())
            if not targets:
                continue
            sub = _exec_chain(gr, targets[0].get_node().get_name())
            out[path] = sub
            out.update(_branch_chains(gr, sub, depth + 1))
    return out


def _pin_default(gr, path):
    try:
        return str(gr.pin(path).get_default_value())
    except H.BwError:
        return None


def _enum_is(value, name):
    # enum pin defaults are the value name; accept a qualified 'EType::Name' too
    return value is not None and str(value).split('::')[-1].strip('"') == name


def _pin_linked_from(gr, path):
    try:
        return [s.get_pin_path() for s in gr.pin(path).get_linked_source_pins()]
    except H.BwError:
        return None


def _check_kick_graph(gr, present, branches):
    """Death kick block (bw_04 deviation 25) and the solver settings that would drop it."""
    if 'Kick_Branch' not in present:
        warn('no death kick nodes (Kick_Branch missing: bw_04 with DEATH_KICK False or an old CR_Burrower): the '
             'ragdoll will not inherit the travel velocity')
        return
    want = ['Kick_%d_Force' % k for k in range(len(BODY))] + ['Kick_SetDone']
    got = branches.get('Kick_Branch.True', [])
    _ok(got == want, 'Kick_Branch.True runs %s (got %s)' % (' > '.join(want), ' > '.join(got) or 'nothing'))
    tgt = []
    try:
        tgt = [t.get_node().get_name() for t in gr.pin('Kick_Branch.Completed').get_linked_target_pins()]
    except H.BwError:
        pass
    _ok(tgt == ['StepRagdoll'], 'Kick_Branch.Completed -> StepRagdoll (%s)' % (tgt or 'not linked'))
    _ok(_pin_linked_from(gr, 'Kick_Branch.Condition') == ['Kick_Fire.Result'], 'Kick_Branch.Condition <- Kick_Fire')
    sd = _pin_default(gr, 'Kick_SetDone.Value')
    _ok(sd is not None and sd.lower() == 'true', 'Kick_SetDone sets bDeathKickDone = %s' % sd)
    for k, bn in enumerate(BODY):
        f = 'Kick_%d_Force' % k
        if f not in present:
            fail('%s missing' % f)
            continue
        key = _pin_default(gr, f + '.PhysicsBodyComponentKey') or ''
        vals = dict((p, _pin_default(gr, f + '.ForceAndTorque.' + p)) for p in ('Type', 'ForceAndTorqueSpace',
                                                                                'LocationSpace'))
        lin = _pin_linked_from(gr, f + '.ForceAndTorque.Linear') or []
        ang = _pin_linked_from(gr, f + '.ForceAndTorque.Angular') or []
        want_lin = 'Kick_Get_V.Value' if k == 0 else 'Kick_%d_Lin.Result' % k
        ok = (bn in key and _enum_is(vals['Type'], 'VelocityChange') and
              _enum_is(vals['ForceAndTorqueSpace'], 'World') and _enum_is(vals['LocationSpace'], 'Body') and
              lin == [want_lin] and ang == ['Kick_WRad.Result'])
        _ok(ok, '%s: body %s, %s, Linear <- %s, Angular <- %s' % (f, bn, vals, lin, ang))
    # settings that make the kick vanish silently (notes_cr_death_velocity.md 5.4) or undo it (5.1)
    for flag in ('bResetFromPosition', 'bResetFromKinematicSpeed', 'bResetFromKinematicAcceleration',
                 'bResetFromEvaluationInterval'):
        v = _pin_default(gr, 'RagdollSolver.SolverSettings.' + flag)
        if v is not None:
            _ok(v.lower() == 'false', 'RagdollSolver.SolverSettings.%s = %s (must be False for the kick)' % (flag, v))
    dto = _pin_default(gr, 'StepRagdoll.DeltaTimeOverride')
    try:
        _ok(float(dto) >= 0.0, 'StepRagdoll.DeltaTimeOverride = %s (not negative)' % dto)
    except (TypeError, ValueError):
        warn('StepRagdoll.DeltaTimeOverride unreadable (%r)' % dto)
    if 'WireSolver' in present:
        thr = _pin_default(gr, 'WireSolver.Settings.PositionThresholdForReset')
        try:
            _ok(float(thr) >= 100000.0, 'WireSolver.Settings.PositionThresholdForReset = %s (>= 1 km: the kicked '
                'corpse leaves the stationary component)' % thr, warn)
        except (TypeError, ValueError):
            warn('WireSolver.Settings.PositionThresholdForReset unreadable (%r)' % thr)


def _check_world_collision(gr):
    """RagdollSolver world collision (bw_04 deviation 29): corpses must land on the WorldDynamic hex tiles."""
    base = 'RagdollSolver.SolverSettings.'
    wct = _pin_default(gr, base + 'WorldCollisionType')
    _ok(_enum_is(wct, 'All'), 'RagdollSolver.SolverSettings.WorldCollisionType = %s (must be All: the hex tiles are '
        'object type WorldDynamic, Static gathers WorldStatic only; notes_cr_world_collision.md)' % wct)
    exp = _pin_default(gr, base + 'WorldCollisionBoundsExpansion')
    try:
        _ok(float(exp) >= 2.0, 'RagdollSolver.SolverSettings.WorldCollisionBoundsExpansion = %s (>= 2.0: world objects '
            'are gathered from the previous frame\'s box, 1.1 lets a fast corpse pass a tile before it is added)' % exp)
    except (TypeError, ValueError):
        fail('RagdollSolver.SolverSettings.WorldCollisionBoundsExpansion unreadable (%r)' % exp)
    for flag, want in (('bWorldCollisionIncludePhysics', 'true'), ('bWorldCollisionIncludeQuery', 'false')):
        v = _pin_default(gr, base + flag)
        _ok(v is not None and v.lower() == want, 'RagdollSolver.SolverSettings.%s = %s (want %s)' % (flag, v, want),
            warn)


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
    branches = {}
    for label in list(chains):
        branches.update(_branch_chains(gr, chains[label]))
    for pin_path, sub in sorted(branches.items()):
        info('branch %s: %d nodes: %s' % (pin_path, len(sub), ' > '.join(sub)))
    on_chain = set(n for c in list(chains.values()) + list(branches.values()) for n in c)
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
    exp_f = (['ForwardsSolve', 'W1_Set', 'W2_Set', 'W3_Set', 'W4_Set', 'Kick_Branch', 'StepRagdoll', 'Rotor_Set',
              'Rotor_SetRot'] +
             ['EndPin_Store_' + c for c in repin] + ['StepHoses', 'StepWires'] + ['EndPin_Set_' + c for c in repin])
    if 'Construction' in chains:
        _check_order(chains['Construction'], exp_c, 'Construction')
    if 'Forwards Solve' in chains:
        _check_order(chains['Forwards Solve'], exp_f, 'Forwards Solve')
    present = set(n.get_name() for n in nodes)
    if 'W4_Set' in present:
        miss = [n for i in range(1, 5) for n in ('W%d_YawTotal' % i, 'W%d_PitchTotal' % i,
                                                 'W%d_Get_FollowYawDeg%d' % (i, i), 'W%d_Get_FollowPitchDeg%d' % (i, i))
                if n not in present]
        _ok(not miss, 'wave adds FollowYawDeg/FollowPitchDeg on J1..J4%s' % ((' (missing: %s)' % ', '.join(miss))
                                                                           if miss else ''))
    if 'StepRagdoll' in present:
        _check_kick_graph(gr, present, branches)
    if 'RagdollSolver' in present:
        _check_world_collision(gr)
    summary['graph'] = {'nodes': len(nodes), 'links': len(links), 'events': events, 'by_struct': by_struct,
                        'by_stage': by_stage, 'chains': chains, 'branches': branches}
    return present


# ---------------------------------------------------------------------------- numeric (recipe Step 8.1 / 8.2)
def _var_default(rig, name, fallback):
    try:
        return float(str(H.member_variables(rig)[name].get_editor_property('default_value')))
    except Exception:  # noqa: BLE001
        return fallback


_BW04B_RIG_VARS = set()        # filled in _bw04b_main: the rig's variable names


def _vtext(v):
    # FVector text for URigVMHost::SetVariableFromString -> FBlueprintEditorUtils::PropertyValueFromString ->
    # FDefaultValueHelper::ParseVector, whose native form is 'x,y,z' (Core/Private/Misc/DefaultValueHelper.cpp:444-486)
    return '%r,%r,%r' % (float(v[0]), float(v[1]), float(v[2]))


def _quiet(d):
    """d + every 2026-11-22 input the rig has set to 0 (path-follow angles, death velocities), so the older checks
    see exactly the inputs they were written for whatever the variable defaults are."""
    out = dict((n, 0.0) for n in FOLLOW_VARS if n in _BW04B_RIG_VARS)
    for n in ('DeathVelocity', 'DeathAngularVelocity'):
        if n in _BW04B_RIG_VARS:
            out[n] = _vtext((0.0, 0.0, 0.0))
    out.update(d)
    return out


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
                 _quiet({'WaveTime': t, 'WaveAmplitudeDeg': amp, 'WavePhasePerJointDeg': phase,
                         'WavePitchAmplitudeDeg': pamp, 'RotorAngleDeg': 0.0, 'bIsDead': False}))
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
                 _quiet({'RotorAngleDeg': a, 'WaveAmplitudeDeg': 0.0, 'WavePitchAmplitudeDeg': 0.0, 'WaveTime': 0.0,
                         'bIsDead': False}))
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


# ---------------------------------------------------------------------------- path-follow bend (2026-11-22)
def _chain_expect(rest, axis, angles_deg):
    """Exact positions for a one-axis bend: everything behind joint i (J1..J4, then the tail tip) turns about the
    component axis through joint i by angles_deg[i], UE FQuat sign (qaxis). Exact because rotations about one fixed
    axis keep that axis, so each joint's body-up / body-side axis stays the component axis."""
    order = FOLLOW_JOINTS + ['tip']
    pts = dict((k, list(v)) for k, v in rest.items())
    for i, jn in enumerate(FOLLOW_JOINTS):
        if not angles_deg[i]:
            continue
        q = qaxis(axis, math.radians(angles_deg[i]))
        c = list(pts[jn])
        for later in order[i + 1:]:
            pts[later] = vadd(c, qrot(q, vsub(pts[later], c)))
    return pts


def _vlen(v):
    return math.sqrt(sum(c * c for c in v))


def _follow_tests(rig, summary, present):
    if 'W4_Set' not in present:
        warn('no wave nodes (stage wave off?): path-follow checks skipped')
        return
    if 'W1_YawTotal' not in present or any(v not in _BW04B_RIG_VARS for v in FOLLOW_VARS):
        fail('the wave does not read FollowYawDeg1..4 / FollowPitchDeg1..4 (old CR_Burrower?): rebuild it with '
             'bw_04_control_rig.py')
        return
    info('path follow: WaveAmplitudeDeg = WavePitchAmplitudeDeg = 0; +FollowYawDeg turns about component +Z and swings '
         'the segments behind the joint toward -Y, +FollowPitchDeg turns about +Y and lifts them toward +Z')
    cases = [  # name, FollowYawDeg1..4, FollowPitchDeg1..4
        ('yaw1_p10', (10, 0, 0, 0), (0, 0, 0, 0)),
        ('yaw1_m10', (-10, 0, 0, 0), (0, 0, 0, 0)),
        ('pitch1_p10', (0, 0, 0, 0), (10, 0, 0, 0)),
        ('pitch1_m10', (0, 0, 0, 0), (-10, 0, 0, 0)),
        ('yaw1_p5', (5, 0, 0, 0), (0, 0, 0, 0)),
        ('yawall_p5', (5, 5, 5, 5), (0, 0, 0, 0)),
        ('pitchall_p5', (0, 0, 0, 0), (5, 5, 5, 5)),
        ('yaw4_p10', (0, 0, 0, 10), (0, 0, 0, 0)),
    ]
    d = {}
    for name, yaw, pitch in cases:
        v = {'WaveTime': 0.0, 'WaveAmplitudeDeg': 0.0, 'WavePitchAmplitudeDeg': 0.0, 'RotorAngleDeg': 0.0,
             'bIsDead': False}
        for i in range(4):
            v['FollowYawDeg%d' % (i + 1)] = float(yaw[i])
            v['FollowPitchDeg%d' % (i + 1)] = float(pitch[i])
        r = _run(rig, 'bw04b_follow_' + name, BODY + ['Rotor'], _quiet(v))
        if r is None:
            continue
        B = r['bones']
        label = 'follow %s' % name
        _at_rest(r, 'J0_Head', 0.05, 0.05, label)
        _at_rest(r, 'Rotor', 0.1, 0.1, label)
        rest = dict((b, B[b]['rest_pos']) for b in FOLLOW_JOINTS)
        rest['tip'] = list(TAIL_TIP_REST)
        now = dict((b, B[b]['global_pos']) for b in FOLLOW_JOINTS)
        now['tip'] = follow_pos(B['J4_Tail'], TAIL_TIP_REST)
        axis, ang = ((0.0, 0.0, 1.0), yaw) if any(yaw) else ((0.0, 1.0, 0.0), pitch)
        want = _chain_expect(rest, axis, ang)
        err = max(H.dist(now[k], want[k]) for k in now)
        _ok(err < 0.5, '%s: J1..J4 and the tail tip on the exact chain rotation (max error %.3f cm)' % (label, err))
        d4 = vsub(now['J4_Tail'], rest['J4_Tail'])
        dtip = vsub(now['tip'], rest['tip'])
        d[name] = {'J4': d4, 'tip': dtip, 'max_error_cm': err}
        info('%s: J4_Tail moved (%+.1f, %+.1f, %+.1f) cm, tail tip (%+.1f, %+.1f, %+.1f) cm'
             % ((label,) + tuple(d4) + tuple(dtip)))
    if 'yaw1_p10' in d:
        y = d['yaw1_p10']['J4'][1]
        _ok(y < -30.0, 'FollowYawDeg1 +10: J4_Tail Y %+.1f cm vs rest (< -30: + swings the tail toward -Y)' % y)
    if 'yaw1_m10' in d:
        y = d['yaw1_m10']['J4'][1]
        _ok(y > 30.0, 'FollowYawDeg1 -10: J4_Tail Y %+.1f cm vs rest (> +30)' % y)
    if 'pitch1_p10' in d:
        z = d['pitch1_p10']['J4'][2]
        _ok(z > 30.0, 'FollowPitchDeg1 +10: J4_Tail Z %+.1f cm vs rest (> +30: + lifts the tail)' % z)
    if 'pitch1_m10' in d:
        z = d['pitch1_m10']['J4'][2]
        _ok(z < -30.0, 'FollowPitchDeg1 -10: J4_Tail Z %+.1f cm vs rest (< -30)' % z)
    if 'yaw1_p5' in d and 'yawall_p5' in d:
        a, c = d['yaw1_p5']['J4'][1], d['yawall_p5']['J4'][1]
        _ok(c < a - 20.0, 'FollowYawDeg1..4 all +5 compound: J4_Tail Y %+.1f cm vs %+.1f cm with only J1 +5' % (c, a))
    if 'yaw4_p10' in d:
        m, y = _vlen(d['yaw4_p10']['J4']), d['yaw4_p10']['tip'][1]
        _ok(m < 0.5 and y < -30.0, 'FollowYawDeg4 +10 turns only the last segment: J4_Tail moved %.3f cm, tail tip Y '
            '%+.1f cm' % (m, y))
    summary['follow'] = d


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
    alive = _quiet({'WaveAmplitudeDeg': 0.0, 'WavePitchAmplitudeDeg': 0.0, 'WaveTime': 0.0, 'RotorAngleDeg': 0.0,
                    'bIsDead': False})
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
    if r is not None and 'Kick_Branch' in present:
        done = _var_text(inst, 'bDeathKickDone')
        _ok(done.lower() == 'false', '120 alive frames: death kick not fired (bDeathKickDone = %s)' % done)
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


# ---------------------------------------------------------------------------- death kick (2026-11-22)
KICK_ALIVE, KICK_DEAD = 10, 12          # frames (dt 1/60): alive pass-through first, as in the game, then dead


def _var_text(inst, name):
    try:
        return str(inst.get_variable_as_string(name))       # RigVMHost.h GetVariableAsString (editor builds)
    except Exception as e:  # noqa: BLE001
        return '<%s>' % e


def _kick_run(rig, name, v_dead, w_dead):
    base = _quiet({'WaveTime': 0.0, 'WaveAmplitudeDeg': 0.0, 'WavePitchAmplitudeDeg': 0.0, 'RotorAngleDeg': 0.0})

    def per_frame(f):
        dead = f >= KICK_ALIVE
        d = dict(base)
        d['bIsDead'] = dead
        d['DeathVelocity'] = _vtext(v_dead if dead else (0.0, 0.0, 0.0))        # C++: zero while alive
        d['DeathAngularVelocity'] = _vtext(w_dead if dead else (0.0, 0.0, 0.0))
        return d
    try:
        inst = H.make_test_instance(rig)
    except H.BwError as e:
        fail('kick %s: test instance: %s' % (name, e))
        return None, None
    r = _run(rig, 'bw04b_kick_' + name, BODY, per_frame, frames=KICK_ALIVE + KICK_DEAD, instance=inst)
    return r, inst


def _kick_tests(rig, summary, present):
    """No world is needed: the World-space ragdoll steps on a test instance (check 6 measures its fall) and the
    instance's ToWorldSpaceTransform is identity, so world = component here."""
    if 'StepRagdoll' not in present:
        warn('no ragdoll nodes (stage ragdoll off?): death kick checks skipped')
        return
    if 'Kick_Branch' not in present:
        warn('no death kick nodes (bw_04 DEATH_KICK False?): death kick checks skipped')
        return
    if 'DeathVelocity' not in _BW04B_RIG_VARS or 'DeathAngularVelocity' not in _BW04B_RIG_VARS:
        fail('CR_Burrower has no DeathVelocity / DeathAngularVelocity variables: rebuild it with bw_04_control_rig.py')
        return
    V, W = (2000.0, 0.0, 0.0), (0.0, 0.0, 40.0)
    r0, i0 = _kick_run(rig, 'none', (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    rv, iv = _kick_run(rig, 'v2000', V, (0.0, 0.0, 0.0))
    rw, iw = _kick_run(rig, 'w40', (0.0, 0.0, 0.0), W)
    if r0 is None:
        return
    T = KICK_DEAD * r0['dt']
    res = {'dead_seconds': T}
    # The comparison only means something if the World-space ragdoll steps on a test instance (no world). Check 6
    # measured that on 2026-11-21 (J0_Head fell 124.5 cm in 0.5 s). If a later build needs a world to step, the checks
    # below would FAIL for the wrong reason, so this becomes a WARN and the check moves to PIE.
    drop0 = r0['bones']['J0_Head']['rest_pos'][2] - r0['bones']['J0_Head']['global_pos'][2]
    res['no_kick_drop_cm'] = drop0
    if drop0 < 5.0:
        warn('death kick: needs PIE - the ragdoll did not simulate on the test instance (J0_Head dropped %.1f cm in '
             '%.2f s dead, free fall ~21 cm), so the kick cannot be measured here. In PIE: Aura.Burrower.KillAll on a '
             'flying Burrower, the corpse must keep flying forward' % (drop0, T))
        summary['death_kick'] = res
        return
    for r, inst, label in ((r0, i0, 'none'), (rv, iv, 'v2000'), (rw, iw, 'w40')):
        if r is None:
            continue
        B = r['bones']
        bad = [b for b in B if not finite(B[b]['global_pos'] + B[b]['global_quat'])]
        _ok(not bad, 'kick %s: all body bones finite%s' % (label, (' (NaN/inf: %s)' % ', '.join(bad)) if bad else ''))
        done = _var_text(inst, 'bDeathKickDone')
        _ok(done.lower() == 'true', 'kick %s: bDeathKickDone = %s after the dead frames (latched)' % (label, done))
    if rv is not None:
        txt = _var_text(iv, 'DeathVelocity')
        try:
            vx = float(txt.split(',')[0])
        except ValueError:
            vx = None
        _ok(vx is not None and abs(vx - V[0]) < 1.0, 'DeathVelocity on the instance = %s (set as %s)'
            % (txt, _vtext(V)))
        E = V[0] * T
        B0, BV = r0['bones'], rv['bones']
        res['v'] = {}
        for b in BODY:
            dd = vsub(BV[b]['global_pos'], B0[b]['global_pos'])
            res['v'][b] = dd
            _ok(0.7 * E < dd[0] < 1.3 * E and abs(dd[1]) < 0.1 * E and abs(dd[2]) < 0.1 * E,
                'DeathVelocity (2000,0,0): %s carried (%+.1f, %+.1f, %+.1f) cm against DeathVelocity 0 after %.2f s '
                'dead (expected about (+%.0f, 0, 0): applied once, 0.7..1.3)' % ((b,) + tuple(dd) + (T, E)))
        j2 = res['v']['J2_Midbody'][0]
        if j2 < 0.05 * E:
            info('hint: the kick was dropped. On the firing frame StepRagdoll needs Alpha > 0, dt > 0 and dynamic '
                 'bodies (no reset flags on RagdollSolver): notes_cr_death_velocity.md 5.4')
        elif j2 > 1.5 * E:
            info('hint: the kick was applied on more than one frame: is Kick_SetDone on Kick_Branch.True?')
    if rw is not None:
        wz = math.radians(W[2])
        B0, BW = r0['bones'], rw['bones']
        d4 = vsub(BW['J4_Tail']['global_pos'], B0['J4_Tail']['global_pos'])
        d0 = vsub(BW['J0_Head']['global_pos'], B0['J0_Head']['global_pos'])
        e4 = wz * (B0['J4_Tail']['rest_pos'][0] - ACTOR_ORIGIN_CS[0]) * T      # (W x r).y = wz * r.x, undamped
        e0 = wz * (B0['J0_Head']['rest_pos'][0] - ACTOR_ORIGIN_CS[0]) * T
        _ok(1.5 * e4 < d4[1] < 0.4 * e4, 'DeathAngularVelocity (0,0,40): J4_Tail Y %+.1f cm against 0 (undamped rigid '
            'turn about the actor origin %+.1f cm: the tail swings toward -Y)' % (d4[1], e4))
        _ok(d0[1] > 0.0, 'DeathAngularVelocity (0,0,40): J0_Head Y %+.1f cm (undamped %+.1f: the head, ahead of the '
            'pivot, swings toward +Y)' % (d0[1], e0), warn)
        dq = qmul(BW['J2_Midbody']['global_quat'], qinv(B0['J2_Midbody']['global_quat']))
        fx = qrot(dq, (1.0, 0.0, 0.0))
        yaw = math.degrees(math.atan2(fx[1], fx[0]))
        ey = W[2] * T
        _ok(0.4 * ey < yaw < 1.3 * ey, 'DeathAngularVelocity (0,0,40): J2_Midbody turned %+.2f deg about +Z against 0 '
            '(undamped %.1f; RagDamp AngularDamping 1.0/s takes about %.0f %% in %.2f s)'
            % (yaw, ey, 100.0 * (1.0 - (1.0 - math.exp(-T)) / T), T))
        res['w'] = {'J4_dY': d4[1], 'J4_dY_undamped': e4, 'J0_dY': d0[1], 'J2_yaw_deg': yaw, 'yaw_undamped': ey}
    summary['death_kick'] = res


# ------------------------------------------------------------------------------------------------- main
def _bw04b_main():
    summary = {'time': time.strftime('%Y-%m-%d %H:%M:%S')}
    if H.pie_running():
        warn('PIE is running; the checks do not need it and do not save anything')
    rig = _check_asset()
    if rig is None:
        return summary
    _check_variables(rig, summary)
    _BW04B_RIG_VARS.clear()
    _BW04B_RIG_VARS.update(H.member_variables(rig))
    present = _check_graph(rig, summary)
    if RUN_NUMERIC:
        for fn in (_wave_tests, _rotor_tests, _follow_tests):
            try:
                fn(rig, summary, present)
            except Exception as e:  # noqa: BLE001
                fail('numeric checks (%s) crashed: %r' % (fn.__name__, e))
                for line in traceback.format_exc().rstrip().split('\n'):
                    print('INFO:   ' + line)
    if RUN_PHYSICS_CHECKS:
        for fn in (_physics_tests, _kick_tests):
            try:
                fn(rig, summary, present)
            except Exception as e:  # noqa: BLE001
                fail('physics checks (%s) crashed: %r' % (fn.__name__, e))
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
