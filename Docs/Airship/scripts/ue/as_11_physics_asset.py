# as_11_physics_asset.py - PA_Airship (research_control_rig.md 7e): small, all-kinematic physics asset for SK_Airship so
# the SK bounds follow the bones (debris is not culled) and traces/overlaps hit the moving parts. No constraints.
# Boxes only, axis-aligned: every bone is world-aligned (identity rest rotation, checked by as_10), so a bone-local box =
# a component-space box moved by the bone position. Part boxes come from Saved/Airship/part_bounds.json
# (as_09_part_bounds_blender.py: per-bone vertex AABBs, UE cm). Hull: 4 boxes under/around the hull skin, tops at the
# deck so nothing invisible stands on deck. Collision type on the component is set by the C++ (QueryOnly).
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

    # bone -> [(shape name, min_cs, max_cs)]
    plan = {}
    # Hull: lower hull in 3 x-slabs (tops at/below the deck), bow block; from the hull profile (x bins of 2.5 m)
    plan['Hull'] = [('HullAft', (-1760.0, -720.0, -470.0), (-1000.0, 720.0, 290.0)),
                    ('HullMid', (-1000.0, -925.0, -530.0), (750.0, 925.0, 250.0)),
                    ('HullFwd', (750.0, -580.0, -415.0), (2250.0, 580.0, 240.0)),
                    ('HullBow', (2250.0, -360.0, 60.0), (3152.0, 360.0, 850.0))]
    for p in ('FL', 'FR', 'RL', 'RR'):
        t = 'Thruster_' + p
        mn, mx = aabb(t)
        plan[t] = [(t + '_Pod', mn, mx)]
        mn, mx = aabb(*([t + '_Nozzle'] + ['%s_Petal%02d' % (t, k) for k in range(12)]))
        plan[t + '_Nozzle'] = [(t + '_NozzleBox', mn, mx)]
    for s in ('L', 'R'):
        t = 'Turbine_' + s
        mn, mx = aabb(t, t + '_Rotor')
        plan[t] = [(t + '_Nacelle', mn, mx)]
    mn, mx = aabb('Rudder')
    plan['Rudder'] = [('Rudder_Blade', mn, mx)]
    for c in ('L1', 'L2', 'R1', 'R2'):
        b = 'Cannon_' + c
        mn, mx = aabb(b, b + '_Quoin', b + '_Wheel_FL', b + '_Wheel_FR', b + '_Wheel_BL', b + '_Wheel_BR')
        plan[b] = [(b + '_Carriage', mn, mx)]
        mn, mx = aabb(b + '_Barrel')
        plan[b + '_Barrel'] = [(b + '_BarrelBox', mn, mx)]
    for L in ('AftL', 'MidL', 'MidR', 'FwdC'):
        b = 'SearchLight_' + L
        mn, mx = aabb(b)
        plan[b] = [(b + '_Post', mn, mx)]
        mn, mx = aabb(b + '_Head')
        plan[b + '_Head'] = [(b + '_HeadBox', mn, mx)]
    mn, mx = aabb('Helm')
    plan['Helm'] = [('Helm_Pedestal', mn, mx)]
    mn, mx = aabb('Helm_Wheel')
    plan['Helm_Wheel'] = [('Helm_WheelBox', mn, mx)]

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
    bcls = unreal.load_class(None, '/Script/Engine.SkeletalBodySetup')
    pp = pa.get_path_name()
    nset = 0
    for o in unreal.ObjectIterator(bcls):
        try:
            if o.get_outer() is None or o.get_outer().get_path_name() != pp:
                continue
            if str(o.get_editor_property('bone_name')) not in plan:
                continue
        except Exception:
            continue
        if unreal.ToolsetLibrary.set_object_properties(o, json.dumps({'CollisionTraceFlag': 2, 'CollisionReponse': 0,
                                                                      'PhysicsType': 1})):
            nset += 1
    out('PASS' if nset == len(plan) else 'WARN', 'trace flag / kinematic set on %d of %d body objects' % (nset, len(plan)))

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
