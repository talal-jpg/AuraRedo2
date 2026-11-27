# as_11_physics_asset.py - PA_Airship (research_control_rig.md 7e): small, all-kinematic physics asset for SK_Airship so
# the SK bounds follow the bones (debris is not culled) and traces/overlaps hit the moving parts. No constraints.
# Boxes only, axis-aligned: every bone is world-aligned (identity rest rotation, checked by as_10), so a bone-local box =
# a component-space box moved by the bone position. Part boxes come from Saved/Airship/part_bounds.json
# (as_09_part_bounds_blender.py: per-bone vertex AABBs, UE cm). Collision type on the component is set by the C++
# (QueryOnly Pawn, blocks Visibility: sentinel bullets' Pawn sweeps and Visibility traces hit these boxes).
# Round 2 (2026-11-25, Talal 11-24 "make a proper PA for ship"; the round-2 rig: 140 cm wheel, 5 deck pieces removed):
#   Hull: the boxes fitted by as_11b_hull_boxes.py (Saved/Airship/pa_hull_boxes.json, from the as_11a column survey of
#     the new rig): stacked boxes per 2 m slab, none above the hull's top surface or below its bottom in any 25 cm column
#     it covers, none over a column without hull (the round-1 4 hand-made boxes stood up to 5.2 m above it). The open
#     truss under the forward platform and the removed deck pieces get nothing. Required: run as_11a + as_11b first.
#   ChainFwd: one box per chain link (as_11b). Winch_Aft / Winch_Fwd / Turbine_*_Rod: their AABB + 2 cm (they had no
#     body in round 1). Every bone with geometry in part_bounds.json is covered by a body (own or merged: petals into the
#     nozzle, rotor into the nacelle, quoin/wheels into the carriage); the script FAILs otherwise.
#   Report (Saved/Airship/as_11_physics_asset.json): per body its bones, boxes and the union of its boxes vs the bones'
#   part_bounds union (+-PAD); Helm_Wheel's box must fit the 140 cm wheel.
# Route = Burrower bw_03: AssetTools.create_asset (no factory, no dialog) + PhysicsToolsets.PhysicsAssetToolset tools
# through unreal.ToolsetRegistry (AddBody/SetBox/SetBodyPhysicsMode/RemoveBody), CollisionTraceFlag via ToolsetLibrary.
# Re-runnable: an existing PA_Airship is cleared and rebuilt. Saves PA_Airship + SK_Airship (physics_asset set).
# Run:  Docs/Airship/scripts/harness/inbox.sh 11 Docs/Airship/scripts/ue/as_11_physics_asset.py 300
import os, json, math, time, traceback  # unreal = inbox namespace (pt_guard proxy)


def _as11():
    import os, json, math, time, traceback
    FOLDER = '/Game/Assets/MyShip/Drivable'
    SK = FOLDER + '/SK_Airship'
    PA_NAME = 'PA_Airship'
    PA = FOLDER + '/' + PA_NAME
    PA_OBJ = PA + '.' + PA_NAME
    TS = 'PhysicsToolsets.PhysicsAssetToolset'
    BOUNDS = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'part_bounds.json')
    PAD = 2.0          # cm added on every side of a part AABB
    R = {'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}, 'bodies': {}}

    def out(tag, msg):
        R['counts'][tag] = R['counts'].get(tag, 0) + 1
        print('%s: %s' % (tag, msg))

    def tool(fn, **params):
        js = json.dumps(params)
        res = unreal.ToolsetRegistry.execute_tool(TS, fn, js)
        err = str(res.get_editor_property('error') or '')
        if err:
            raise RuntimeError('%s(%s) -> %s' % (fn, js[:200], err))
        raw = str(res.get_editor_property('value') or '')
        if not raw:
            return None
        d = json.loads(raw)
        if isinstance(d, dict):
            for k in d:
                if k.lower() == 'returnvalue':
                    return d[k]
        return d

    def vj(v):
        return {'X': float(v[0]), 'Y': float(v[1]), 'Z': float(v[2])}

    eal = unreal.EditorAssetLibrary
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        out('FAIL', 'PIE running')
        return R
    skm = eal.load_asset(SK)
    if not isinstance(skm, unreal.SkeletalMesh):
        out('FAIL', 'no %s (run as_10)' % SK)
        return R
    pb = json.load(open(BOUNDS))['bones']
    skel = skm.get_editor_property('skeleton')
    pose = unreal.AnimPoseExtensions.get_reference_pose(skel)
    WS = unreal.AnimPoseSpaces.WORLD

    def bone_pos(b):
        t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, b, WS)
        q = t.rotation
        if abs(abs(q.w) - 1.0) > 1e-5:
            raise RuntimeError('bone %s is not world-aligned (q %s): boxes would be wrong' % (b, q))
        return (t.translation.x, t.translation.y, t.translation.z)

    def aabb(*bones):
        mn = [1e9] * 3
        mx = [-1e9] * 3
        for b in bones:
            for i in range(3):
                mn[i] = min(mn[i], pb[b]['min'][i])
                mx[i] = max(mx[i], pb[b]['max'][i])
        return [mn[i] - PAD for i in range(3)], [mx[i] + PAD for i in range(3)]

    # bone -> [(shape name, min_cs, max_cs)]; members: body bone -> the part_bounds bones its boxes cover
    plan = {}
    members = {}
    HB = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'pa_hull_boxes.json')
    try:
        hb = json.load(open(HB))
    except Exception as e:
        out('FAIL', '%s not readable (%s): run as_11a_hull_survey_blender.py (headless Blender) + as_11b_hull_boxes.py' % (HB, e))
        return R
    if hb.get('check_failures') or not hb.get('hull_boxes'):
        out('FAIL', 'pa_hull_boxes.json has check failures %s or no hull boxes: re-run as_11b' % hb.get('check_failures'))
        return R
    plan['Hull'] = [(b['name'], tuple(b['min']), tuple(b['max'])) for b in hb['hull_boxes']]
    members['Hull'] = ['Hull']
    out('INFO', 'Hull: %d boxes from pa_hull_boxes.json (regions %s)' % (len(plan['Hull']), dict(
        (k, v.get('coverage')) for k, v in (hb.get('regions') or {}).items())))
    if 'ChainFwd' in pb and hb.get('chain_boxes'):
        plan['ChainFwd'] = [(b['name'], tuple(b['min']), tuple(b['max'])) for b in hb['chain_boxes']]
        members['ChainFwd'] = ['ChainFwd']
    for b in ('Winch_Aft', 'Winch_Fwd', 'Turbine_L_Rod', 'Turbine_R_Rod'):
        if b in pb:
            mn, mx = aabb(b)
            plan[b] = [(b + '_Box', mn, mx)]
            members[b] = [b]
    def part(body, shape, *bones):
        mn, mx = aabb(*bones)
        plan[body] = [(shape, mn, mx)]
        members[body] = list(bones)

    for p in ('FL', 'FR', 'RL', 'RR'):
        t = 'Thruster_' + p
        part(t, t + '_Pod', t)
        part(t + '_Nozzle', t + '_NozzleBox', *([t + '_Nozzle'] + ['%s_Petal%02d' % (t, k) for k in range(12)]))
    for sd in ('L', 'R'):
        t = 'Turbine_' + sd
        part(t, t + '_Nacelle', t, t + '_Rotor')
    part('Rudder', 'Rudder_Blade', 'Rudder')
    for c in ('L1', 'L2', 'R1', 'R2'):
        b = 'Cannon_' + c
        part(b, b + '_Carriage', b, b + '_Quoin', b + '_Wheel_FL', b + '_Wheel_FR', b + '_Wheel_BL', b + '_Wheel_BR')
        part(b + '_Barrel', b + '_BarrelBox', b + '_Barrel')
    for L in ('AftL', 'MidL', 'MidR', 'FwdC'):
        b = 'SearchLight_' + L
        part(b, b + '_Post', b)
        part(b + '_Head', b + '_HeadBox', b + '_Head')
    part('Helm', 'Helm_Pedestal', 'Helm')
    part('Helm_Wheel', 'Helm_WheelBox', 'Helm_Wheel')
    # every bone with geometry is covered by a body; every body's boxes span its bones (+-PAD)
    cov = set(b for v in members.values() for b in v)
    miss = sorted(b for b in pb if b not in cov)
    out('PASS' if not miss else 'FAIL', '%d of %d bones with geometry (part_bounds.json) covered by %d bodies%s' % (
        len(pb) - len(miss), len(pb), len(plan), '' if not miss else '; NOT covered: %s' % miss))
    R['bodies_vs_part_bounds'] = {}
    worst = 0.0
    for body, shapes in plan.items():
        if body == 'Hull':
            continue
        bmn, bmx = aabb(*members[body])
        umn = [min(sh[1][i] for sh in shapes) for i in range(3)]
        umx = [max(sh[2][i] for sh in shapes) for i in range(3)]
        d = max(max(abs(umn[i] - bmn[i]), abs(umx[i] - bmx[i])) for i in range(3))
        if body == 'ChainFwd':      # link boxes: inside the chain's AABB, ends at its ends
            d = max(max(bmn[i] - umn[i], umx[i] - bmx[i], 0.0) for i in range(3))
        worst = max(worst, d)
        R['bodies_vs_part_bounds'][body] = {'bones': members[body], 'boxes': len(shapes), 'union_min': [round(x, 1) for x in umn],
                                            'union_max': [round(x, 1) for x in umx], 'part_bounds_padded_min': [round(x, 1) for x in bmn],
                                            'part_bounds_padded_max': [round(x, 1) for x in bmx], 'max_diff_cm': round(d, 2)}
    out('PASS' if worst <= 0.5 else 'FAIL', 'part bodies match their bones\' part_bounds (+%.0f cm pad): worst %.2f cm' % (PAD, worst))
    wmn, wmx = plan['Helm_Wheel'][0][1], plan['Helm_Wheel'][0][2]
    wsz = [wmx[i] - wmn[i] for i in range(3)]
    out('PASS' if wsz[1] <= 140.0 + 2 * PAD + 1.0 and wsz[2] <= 140.0 + 2 * PAD + 1.0 else 'FAIL',
        'Helm_Wheel box %.1f x %.1f x %.1f cm (the 140 cm wheel + %.0f cm each side), z %.1f..%.1f' % (
            wsz[0], wsz[1], wsz[2], PAD, wmn[2], wmx[2]))

    # PA asset
    pa = eal.load_asset(PA) if eal.does_asset_exist(PA) else None
    if pa is not None and not isinstance(pa, unreal.PhysicsAsset):
        out('FAIL', '%s exists and is a %s' % (PA, pa.get_class().get_name()))
        return R
    if pa is None:
        pa = unreal.AssetToolsHelpers.get_asset_tools().create_asset(PA_NAME, FOLDER, unreal.PhysicsAsset, None)
        if pa is None:
            out('FAIL', 'create_asset PA_Airship failed')
            return R
        out('INFO', 'created %s' % PA)
    else:
        out('INFO', 'reusing %s: bodies removed and rebuilt' % PA)
    try:
        unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(pa)
    except Exception as e:
        out('WARN', 'close editors: %s' % e)
    for n in (tool('GetBodyNames', PhysicsAsset=PA_OBJ) or []):
        tool('RemoveBody', PhysicsAsset=PA_OBJ, BoneName=str(n))
    for c in (tool('GetConstraints', PhysicsAsset=PA_OBJ) or []):
        try:
            cl = dict((k.lower(), v) for k, v in c.items())
            tool('RemoveConstraint', PhysicsAsset=PA_OBJ, Bone1Name=cl.get('bone1name'), Bone2Name=cl.get('bone2name'))
        except Exception as e:
            out('WARN', 'remove constraint: %s' % e)
    left = tool('GetBodyNames', PhysicsAsset=PA_OBJ) or []
    if left:
        out('FAIL', 'could not clear bodies: %s' % left)
        return R

    nshapes = 0
    for bone, shapes in plan.items():
        bp = bone_pos(bone)
        tool('AddBody', PhysicsAsset=PA_OBJ, BoneName=bone)
        for name, mn, mx in shapes:
            c = [0.5 * (mn[i] + mx[i]) - bp[i] for i in range(3)]
            e = [mx[i] - mn[i] for i in range(3)]
            tool('SetBox', PhysicsAsset=PA_OBJ, BoneName=bone, ShapeName=name, Center=vj(c),
                 Rotation={'Pitch': 0.0, 'Yaw': 0.0, 'Roll': 0.0}, ExtentX=e[0], ExtentY=e[1], ExtentZ=e[2])
            R['bodies'].setdefault(bone, []).append({'shape': name, 'centre_local': [round(x, 1) for x in c],
                                                     'size': [round(x, 1) for x in e]})
            nshapes += 1
        tool('SetBodyPhysicsMode', PhysicsAsset=PA_OBJ, BoneName=bone, Mode=1)    # EBodyPhysicsMode::Kinematic
    out('INFO', 'added %d bodies, %d boxes' % (len(plan), nshapes))

    # per body: UseSimpleAsComplex trace flag (complex traces hit the boxes), collision response enabled
    # the PA's own body setups (the ObjectIterator route also met the removed bodies, still in memory until GC:
    # "65 of 35" on the 2026-11-25 rebuild)
    try:
        live = list(pa.get_editor_property('skeletal_body_setups'))
    except Exception:
        live = None
    if live is None:
        try:
            unreal.SystemLibrary.collect_garbage()      # the removed bodies' setups would be met too
        except Exception:
            pass
        bcls = unreal.load_class(None, '/Script/Engine.SkeletalBodySetup')
        pp = pa.get_path_name()
        live = []
        for o in unreal.ObjectIterator(bcls):
            try:
                if o.get_outer() is not None and o.get_outer().get_path_name() == pp:
                    live.append(o)
            except Exception:
                continue
    nset = 0
    done = set()
    for o in live:
        try:
            bn = str(o.get_editor_property('bone_name'))
        except Exception:
            continue
        if bn not in plan:
            continue
        if unreal.ToolsetLibrary.set_object_properties(o, json.dumps({'CollisionTraceFlag': 2, 'CollisionReponse': 0,
                                                                      'PhysicsType': 1})):
            nset += 1
            done.add(bn)
    out('PASS' if len(done) == len(plan) else 'WARN', 'trace flag / kinematic set on the bodies of %d of %d bones (%d body '
        'objects met; more than the bones = removed bodies not yet garbage-collected)' % (len(done), len(plan), nset))

    # verify through the toolset
    names = sorted(str(n) for n in (tool('GetBodyNames', PhysicsAsset=PA_OBJ) or []))
    ok_b = names == sorted(plan)
    out('PASS' if ok_b else 'FAIL', '%d bodies %s' % (len(names), '' if ok_b else 'want %s' % sorted(plan)))
    modes = {}
    for b in names:
        m = tool('GetBodyPhysicsMode', PhysicsAsset=PA_OBJ, BoneName=b)
        modes[str(m)] = modes.get(str(m), 0) + 1
    out('PASS' if len(modes) == 1 and 'kinematic' in list(modes)[0].lower() or list(modes) == ['1'] else 'FAIL',
        'physics modes %s (want all Kinematic)' % modes)
    nb = 0
    for b in names:
        sh = tool('GetBodyShapes', PhysicsAsset=PA_OBJ, BoneName=b) or []
        nb += len(sh)
    out('PASS' if nb == nshapes else 'FAIL', '%d shapes read back (built %d)' % (nb, nshapes))
    cons = tool('GetConstraints', PhysicsAsset=PA_OBJ) or []
    out('PASS' if not cons else 'FAIL', '%d constraints (want 0)' % len(cons))

    smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    try:
        ok = smes.assign_physics_asset(skm, pa)
        if not ok:
            out('WARN', 'assign_physics_asset False: set_editor_property')
            skm.set_editor_property('physics_asset', pa)
    except Exception as e:
        out('WARN', 'assign_physics_asset raised %r: set_editor_property' % (e,))
        skm.set_editor_property('physics_asset', pa)
    cur = skm.get_editor_property('physics_asset')
    out('PASS' if cur is not None and cur.get_path_name() == PA_OBJ else 'FAIL', 'SK_Airship.physics_asset = %s' % (
        cur.get_path_name() if cur else None))
    if R['counts']['FAIL']:
        out('WARN', 'not saved (FAIL above)')
        return R
    for p in (PA, SK):
        out('PASS' if eal.save_asset(p, only_if_is_dirty=False) else 'FAIL', 'saved %s' % p)
    return R


try:
    _as11_r = _as11()
except Exception:
    print('FAIL: as_11 crashed: %s' % traceback.format_exc())
    _as11_r = {'counts': {'FAIL': 1}}
try:
    with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_11_physics_asset.json'), 'w') as _f:
        json.dump(_as11_r, _f, indent=1, default=str)
except Exception as _e:
    print('WARN: report not written %r' % (_e,))
print('RESULT: %s %s' % ('PASS' if not _as11_r['counts'].get('FAIL') else 'FAIL', _as11_r['counts']))
