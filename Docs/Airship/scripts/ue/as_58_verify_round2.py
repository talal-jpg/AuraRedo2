# as_58_verify_round2.py - round 2, READ-ONLY check of every asset the editor steps made or changed (nothing is saved):
#   FX       NS_AirshipMuzzle (no emitter of its own life cycle loops, Blast_Puffs 0.5-0.85 s + alpha fade),
#            NS_AirshipTurretTracer (no 7500 left, 30000 found), NS_AirshipTurretMuzzle (no shells, Global Scale 1.5, loops
#            once, smoke <= 0.5 s), NS_AirshipTurretFire; compile states (background check -> Saved/Airship/as_58_compile.json)
#   ball     BP_AirshipCannonball class defaults (Radius 50, GravityScale 0.6, SplashRadius 600, SentinelHitRadius 100,
#            MaxLifeSeconds 10, BallMaxHealth 30, ImpactFXScale 3, mesh 1 m)
#   turret   SM_AirshipTurret_Base / _Gun (M_AirshipProps, no collision, Nanite off), BP_AirshipTurret (meshes, FX, tracer,
#            NDC, PivotHeight / MuzzleForward = turret_dims.json), UAirshipSettings.TurretClass loads it
#   ship     SK_Airship (118 bones, SKEL_Airship, PA_Airship, Helm_Wheel / PilotSeat = turret_dims.json), BP_AirshipPawn
#            (CannonballSpeed / CannonSpawnForwardOffset / PilotSeatFallback = the C++ defaults)
#   PA       PA_Airship, REBUILT on purpose in the editor stage (Talal 11-24 "make a proper PA for ship"; as_11_physics_asset.py
#            from part_bounds.json + pa_hull_boxes.json), so it is checked by its bodies, not by its bytes: the saved bodies
#            and boxes (read back through the PhysicsAssetToolset) = as_11's report, every bone with geometry in
#            part_bounds.json has a body, the part boxes fit their bones (+2 cm), the Helm_Wheel box fits the 140 cm wheel,
#            all Kinematic, no constraints, as many SkeletalBodySetup objects in the package as bodies (run it in a fresh
#            editor: the rebuild's removed bodies stay in memory until a restart), and the Hull boxes against the round-2
#            hull survey (as_11b's rules: no column above the top hit / below the bottom hit / without hull, each box
#            inside its region's z band) and the five removed deck pieces (no box above the deck under them).
#   frozen   IMC_Airship and the Input folder unchanged: the .uasset bytes vs the clone's committed LFS objects (git show
#            HEAD:<path> gives the pointer: sha256 + size). PR A adds no input asset.
# FX probe cost: every Niagara toolset call grows the editor by ~25 MB for good (2026-11-25), so the tracer check re-reads
#   only the modules as_54 recorded (Saved/Airship/as_54_turret_fx.json tracer_probe_before), and the muzzle checks read only
#   the life cycle module, InitializeParticle and ScaleColor of each stack (as51_probe). About 100 calls: start it in a fresh
#   editor.
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 58 Docs/Airship/scripts/ue/as_58_verify_round2.py 300
#   then (15-60 s later) the compile states are in Saved/Airship/as_58_compile.json; re-running as_58 prints them.
# Report: Saved/Airship/as_58_verify_round2.json
import hashlib, json, math, os, subprocess, traceback  # unreal = inbox namespace
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
AS54_LIB_ONLY = True
exec(open(os.path.join(_AS_UE, 'as_54_turret_fx.py')).read())     # as_51's + as_54's functions (it execs as_51 as a library)

AS58_W = os.path.abspath(unreal.Paths.project_dir())
AS58_DIMS = os.path.join(AS58_W, 'SourceArt/Airship/turret_dims.json')
D = '/Game/Assets/MyShip/Drivable'
FX = {'muzzle': D + '/FX/NS_AirshipMuzzle', 'tracer': D + '/FX/NS_AirshipTurretTracer', 'tmuzzle': D + '/FX/NS_AirshipTurretMuzzle',
      'tfire': D + '/FX/NS_AirshipTurretFire'}
FROZEN = ['Content/Assets/MyShip/Drivable/Input/IMC_Airship.uasset']     # PA_Airship is rebuilt on purpose: check_pa()
AS58_SAVED = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
AS58_PA_OBJ = D + '/PA_Airship.PA_Airship'
AS58_PA_TS = 'PhysicsToolsets.PhysicsAssetToolset'
AS58_REMOVALS = os.path.join(AS58_W, 'SourceArt/Airship/scripts/deck_removals.json')
AS58_PAD = 2.0          # as_11's pad on every side of a part AABB (cm)
INPUT_DIR = 'Content/Assets/MyShip/Drivable/Input'
R = {'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}}


def o(tag, msg):
    R['counts'][tag] = R['counts'].get(tag, 0) + 1
    R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def pth(v):
    try:
        return v.get_path_name() if v is not None else None
    except Exception:  # noqa: BLE001
        return str(v)


def full(p):
    return '%s.%s' % (p, p.rsplit('/', 1)[1])


def load(p, what):
    eal = unreal.EditorAssetLibrary
    a = eal.load_asset(p) if eal.does_asset_exist(p) else None
    o('PASS' if a is not None else 'FAIL', '%s loads: %s (%s)' % (what, p, a.get_class().get_name() if a else 'missing'))
    return a


def dims():
    try:
        with open(AS58_DIMS) as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        o('WARN', 'turret_dims.json not readable: %s' % e)
        return {}


def v3(x):
    if isinstance(x, dict):
        return [float(x[k]) for k in ('x', 'y', 'z')]
    return [float(a) for a in x][:3]


# ------------------------------------------------------------------------------------------------ FX
def loops_left(S):
    pr = as51_probe(S)
    left = []
    for em, d in pr['emitters'].items():
        lcm = d.get('Life Cycle Mode') if isinstance(d.get('Life Cycle Mode'), dict) else {}
        lb = d.get('Loop Behavior') if isinstance(d.get('Loop Behavior'), dict) else {}
        ldm = d.get('Loop Duration Mode') if isinstance(d.get('Loop Duration Mode'), dict) else {}
        if em != 'None' and (lcm.get('display') or '').lower() == 'system':
            continue
        if as51_never_ends(d):      # not Once, or Once with Loop Duration Mode Infinite (never completes)
            left.append((em, lb.get('display'), ldm.get('display')))
    return pr, left


def check_fx():
    for k, p in FX.items():
        if load(p, k) is None:
            return False
    S = full(FX['muzzle'])
    pr, left = loops_left(S)
    o('PASS' if not left else 'FAIL', 'NS_AirshipMuzzle: stacks still looping %s' % left)
    bp = pr['emitters'].get('Blast_Puffs', {})
    life = bp.get('lifetime') or {}
    lo, hi = life.get('Lifetime Min'), life.get('Lifetime Max')
    o('PASS' if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and abs(lo - 0.5) < 1e-3 and abs(hi - 0.85) < 1e-3 else 'FAIL',
      'NS_AirshipMuzzle Blast_Puffs lifetime %s - %s (want 0.5 - 0.85)' % (lo, hi))
    sa = str(bp.get('scale_alpha'))
    o('PASS' if 'NormalizedAge' in sa else 'FAIL', 'NS_AirshipMuzzle Blast_Puffs Scale Alpha %s (want 1.0 - Particles.NormalizedAge)' % sa)
    o('INFO', 'NS_AirshipMuzzle Muzzle_Smoke lifetime %s (kept)' % (pr['emitters'].get('Muzzle_Smoke', {}).get('lifetime')))
    # tracer: the probe of as_54 (7500 -> 30000)
    T = full(FX['tracer'])
    if 'as54_tracer_probe' in globals():
        only = None
        try:
            with open(os.path.join(AS58_SAVED, 'as_54_turret_fx.json')) as f:
                only = set((h['emitter'], h['script'], h['module']) for h in
                           ((json.load(f).get('tracer_probe_before') or {}).get('hits') or []))
        except Exception as e:  # noqa: BLE001
            o('WARN', 'as_54_turret_fx.json not readable (%s): the tracer probe scans every SetVariables module' % e)
        if only:
            o('INFO', 'tracer: re-reading the %d modules where as_54 found the speed (as_54_turret_fx.json)' % len(only))
        hits, speeds, users = as54_tracer_probe(T, only=only or None)
        old = [h for h in hits if (h['kind'] == 'float' and abs(h['value'] - 7500.0) < 0.5) or (h['kind'] == 'expr' and '7500' in h['value'])]
        old += [u for u in users if abs(u['value'] - 7500.0) < 0.5]
        new = [h for h in hits if h not in old] + [u for u in users if abs(u['value'] - 30000.0) < 0.5]
        o('PASS' if not old and new else ('WARN' if not old else 'FAIL'), 'NS_AirshipTurretTracer: 7500 left %s, 30000 at %s%s' % (
            old, [(h.get('emitter'), h.get('module'), h.get('path')) if 'emitter' in h else h.get('name') for h in new],
            '' if new else ' (as_54 found no tracer speed input: tracer left as the gun\'s)'))
    else:
        o('WARN', 'tracer probe not loaded from as_54_turret_fx.py')
    M = full(FX['tmuzzle'])
    pr2, left2 = loops_left(M)
    o('PASS' if not left2 else 'FAIL', 'NS_AirshipTurretMuzzle: stacks still looping %s' % left2)
    o('PASS' if 'Bullet_Shell_Eject' not in pr2['emitters'] else 'FAIL', 'NS_AirshipTurretMuzzle emitters %s (no Bullet_Shell_Eject)' % list(pr2['emitters']))
    uv = dict(pr2.get('user') or [])
    gs = (uv.get('User.Global Scale') or {}).get('value') if isinstance(uv.get('User.Global Scale'), dict) else uv.get('User.Global Scale')
    sh = (uv.get('User.Use Bullet Shell') or {}).get('value') if isinstance(uv.get('User.Use Bullet Shell'), dict) else uv.get('User.Use Bullet Shell')
    o('PASS' if gs is not None and abs(float(gs) - 1.5) < 1e-3 and not sh else 'FAIL', 'NS_AirshipTurretMuzzle Global Scale %s (1.5), Use Bullet Shell %s (0)' % (gs, sh))
    long_smoke = []
    for em, d in pr2['emitters'].items():
        if 'smoke' in em.lower():
            for k in ('Lifetime Min', 'Lifetime Max', 'Lifetime'):
                x = (d.get('lifetime') or {}).get(k)
                if isinstance(x, (int, float)) and x > 0.5 + 1e-4:
                    long_smoke.append((em, k, x))
    o('PASS' if not long_smoke else 'FAIL', 'NS_AirshipTurretMuzzle smoke lifetimes over 0.5 s: %s' % long_smoke)
    o('INFO', 'NS_AirshipTurretFire emitters %s' % as51_emitters(full(FX['tfire'])))
    return True


# ------------------------------------------------------------------------------------------------ ball, turret, ship
def check_ball():
    bp = load(D + '/BP_AirshipCannonball', 'cannonball')
    if bp is None:
        return
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    want = [('Radius', 50.0), ('GravityScale', 0.6), ('SplashRadius', 600.0), ('SentinelHitRadius', 100.0), ('MaxLifeSeconds', 10.0),
            ('BallMaxHealth', 30.0), ('ImpactFXScale', 3.0)]
    bad = []
    got = {}
    for n, v in want:
        try:
            got[n] = float(cdo.get_editor_property(n))
        except Exception as e:  # noqa: BLE001
            got[n] = 'unreadable %s' % e
        if not isinstance(got[n], float) or abs(got[n] - v) > 1e-3:
            bad.append(n)
    s = cdo.get_editor_property('BallMesh').get_editor_property('relative_scale3d')
    got['BallMesh.scale'] = [round(s.x, 3), round(s.y, 3), round(s.z, 3)]
    if any(abs(x - 1.0) > 1e-3 for x in got['BallMesh.scale']):
        bad.append('BallMesh.scale')
    o('PASS' if not bad else 'FAIL', 'BP_AirshipCannonball %s%s' % (got, (' wrong: %s' % bad) if bad else ''))


def check_turret(dm):
    for n in ('SM_AirshipTurret_Base', 'SM_AirshipTurret_Gun'):
        sm = load(D + '/Turret/' + n, n)
        if sm is None:
            continue
        mats = [pth(m.get_editor_property('material_interface')) for m in sm.get_editor_property('static_materials')]
        nc = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).get_simple_collision_count(sm)
        nan = bool(sm.get_editor_property('nanite_settings').get_editor_property('enabled'))
        bb = sm.get_bounding_box()
        ok = mats and all(m and 'M_AirshipProps' in m for m in mats) and nc == 0 and not nan
        o('PASS' if ok else 'FAIL', '%s materials %s, simple collision %d, Nanite %s, bounds (%.1f %.1f %.1f)..(%.1f %.1f %.1f)' % (
            n, mats, nc, nan, bb.min.x, bb.min.y, bb.min.z, bb.max.x, bb.max.y, bb.max.z))
    bp = load(D + '/Turret/BP_AirshipTurret', 'turret blueprint')
    if bp is None:
        return
    par = pth(unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp))
    o('PASS' if par == '/Script/Aura.AirshipTurret' else 'FAIL', 'BP_AirshipTurret parent %s' % par)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    g = cdo.get_editor_property
    v = {'BaseMesh': pth(g('BaseMesh').get_editor_property('static_mesh')), 'GunMesh': pth(g('GunMesh').get_editor_property('static_mesh')),
         'MuzzleFX': pth(g('MuzzleFXComponent').get_editor_property('asset')), 'DestroyedFX': pth(g('DestroyedFXComponent').get_editor_property('asset')),
         'TracerSystem': pth(g('TracerSystem')), 'TracerDataChannel': pth(g('TracerDataChannel')), 'DestroyedExplosionFX': pth(g('DestroyedExplosionFX')),
         'PivotHeight': float(g('PivotHeight')), 'MuzzleForward': float(g('MuzzleForward'))}
    ok = (v['BaseMesh'] or '').endswith('SM_AirshipTurret_Base') and (v['GunMesh'] or '').endswith('SM_AirshipTurret_Gun') and \
        (v['MuzzleFX'] or '').endswith('NS_AirshipTurretMuzzle') and (v['DestroyedFX'] or '').endswith('NS_AirshipTurretFire') and \
        (v['TracerSystem'] or '').endswith('NS_AirshipTurretTracer') and (v['TracerDataChannel'] or '').endswith('NDC_GunShootHit') and \
        (v['DestroyedExplosionFX'] or '').endswith('NS_FireExplosion')
    o('PASS' if ok else 'FAIL', 'BP_AirshipTurret %s' % v)
    for k, key in (('PivotHeight', 'pivot_height_cm'), ('MuzzleForward', 'muzzle_forward_cm')):
        if isinstance(dm.get(key), (int, float)):
            o('PASS' if abs(v[k] - float(dm[key])) < 0.05 else 'FAIL', 'BP_AirshipTurret %s %.1f vs turret_dims.json %s %.1f' % (k, v[k], key, dm[key]))
    st = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.AirshipSettings'))
    tc = str(st.get_editor_property('TurretClass'))
    cls = unreal.load_class(None, '/Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret.BP_AirshipTurret_C')
    o('PASS' if cls is not None and 'BP_AirshipTurret' in tc else 'FAIL', 'UAirshipSettings.TurretClass %s loads %s' % (tc, pth(cls)))


def check_ship(dm):
    sk = load(D + '/SK_Airship', 'SK_Airship')
    if sk is not None:
        skel = sk.get_editor_property('skeleton')
        pa = sk.get_editor_property('physics_asset')
        o('PASS' if pth(skel) == D + '/SKEL_Airship.SKEL_Airship' else 'FAIL', 'SK_Airship skeleton %s' % pth(skel))
        o('PASS' if pth(pa) == D + '/PA_Airship.PA_Airship' else 'FAIL', 'SK_Airship physics asset %s' % pth(pa))
        pose = unreal.AnimPoseExtensions.get_reference_pose(skel)
        names = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
        o('PASS' if len(names) == 118 else 'FAIL', 'SK_Airship %d bones (118)' % len(names))
        # as_61 (2026-11-27): slot 0 = the drivable hull material (ink without the 5 removed deck pieces), slot 1 the props
        try:
            slots = [pth(m.get_editor_property('material_interface')) for m in sk.materials]
            want = [D + '/Materials/M_AirshipDrivable.M_AirshipDrivable', D + '/Materials/M_AirshipProps.M_AirshipProps']
            o('PASS' if slots == want else 'FAIL', 'SK_Airship material slots %s (want M_AirshipDrivable, M_AirshipProps)' % slots)
            md = unreal.EditorAssetLibrary.load_asset(D + '/Materials/M_AirshipDrivable')
            used = [pth(t) for t in unreal.MaterialEditingLibrary.get_used_textures(md)] if md else []
            okt = any(u.endswith('T_AirshipDrivable_ComicLines') for u in used) and not any(u.endswith('.T_Airship_ComicLines') for u in used)
            o('PASS' if okt else 'FAIL', 'M_AirshipDrivable textures %s (T_AirshipDrivable_ComicLines, not T_Airship_ComicLines)' % used)
        except Exception as e:  # noqa: BLE001
            o('FAIL', 'SK_Airship material slots not read (%s)' % e)
        for b, key in (('Helm_Wheel', 'helm_wheel_ue'), ('PilotSeat', 'pilot_seat_ue')):
            if b in names:
                t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD).translation
                p = [round(t.x, 2), round(t.y, 2), round(t.z, 2)]
                if dm.get(key) is not None:
                    w = v3(dm[key])
                    d = math.sqrt(sum((p[i] - w[i]) ** 2 for i in range(3)))
                    o('PASS' if d <= 2.0 else 'FAIL', '%s rest %s vs turret_dims.json %s: %.2f cm' % (b, p, w, d))
                else:
                    o('INFO', '%s rest %s' % (b, p))
    bp = load(D + '/BP_AirshipPawn', 'BP_AirshipPawn')
    if bp is not None:
        ncdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.AirshipPawn'))
        cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
        for n in ('CannonballSpeed', 'CannonSpawnForwardOffset', 'PilotSeatFallback'):
            a, b = ncdo.get_editor_property(n), cdo.get_editor_property(n)
            same = (a - b).length() < 1e-3 if isinstance(a, unreal.Vector) else abs(float(a) - float(b)) < 1e-4
            o('PASS' if same else 'FAIL', 'BP_AirshipPawn %s %s = class default %s' % (n, b, a))


# ------------------------------------------------------------------------------------------------ PA_Airship (rebuilt by as_11)
def pa_tool(fn, **params):
    res = unreal.ToolsetRegistry.execute_tool(AS58_PA_TS, fn, json.dumps(params))
    err = str(res.get_editor_property('error') or '')
    if err:
        raise RuntimeError('%s -> %s' % (fn, err))
    raw = str(res.get_editor_property('value') or '')
    if not raw:
        return None
    d = json.loads(raw)
    if isinstance(d, dict):
        for k in d:
            if k.lower() == 'returnvalue':
                return d[k]
    return d


def kget(d, name, default=None):
    for k, v in (d or {}).items():
        if k.lower() == name.lower():
            return v
    return default


def pa_boxes(names, pose):
    """{body: [(shape, min_cs, max_cs)]} read back from the saved PA (bone-local centre + full extents -> component space;
    every airship bone is world-aligned, checked here too). Non-box shapes / rotated boxes are listed in 'odd'."""
    out, odd = {}, []
    for b in names:
        t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD)
        q = t.rotation
        if abs(abs(q.w) - 1.0) > 1e-5:
            odd.append((b, 'bone not world-aligned'))
        bp = (t.translation.x, t.translation.y, t.translation.z)
        for s in (pa_tool('GetBodyShapes', PhysicsAsset=AS58_PA_OBJ, BoneName=b) or []):
            c = kget(s, 'Center') or {}
            c = [float(kget(c, k, 0.0)) for k in ('X', 'Y', 'Z')]
            e = [float(kget(s, 'Extent' + k, 0.0)) for k in ('X', 'Y', 'Z')]
            rot = kget(s, 'Rotation') or {}
            st = str(kget(s, 'ShapeType', ''))
            is_box = 'box' in st.lower() or st == '2'       # EPhysicsShapeType::Box (by name or by value)
            if not is_box or any(abs(float(kget(rot, k, 0.0))) > 1e-3 for k in ('Pitch', 'Yaw', 'Roll')):
                odd.append((b, kget(s, 'ShapeName'), kget(s, 'ShapeType'), rot))
            out.setdefault(b, []).append((str(kget(s, 'ShapeName')), [bp[i] + c[i] - 0.5 * e[i] for i in range(3)],
                                          [bp[i] + c[i] + 0.5 * e[i] for i in range(3)], c, e))
    return out, odd


def check_pa():
    try:
        r11 = json.load(open(os.path.join(AS58_SAVED, 'as_11_physics_asset.json')))
        pb = json.load(open(os.path.join(AS58_SAVED, 'part_bounds.json')))['bones']
        hb = json.load(open(os.path.join(AS58_SAVED, 'pa_hull_boxes.json')))
    except Exception as e:  # noqa: BLE001
        o('FAIL', 'PA: as_11_physics_asset.json / part_bounds.json / pa_hull_boxes.json not readable (%s): run as_09, as_11a, as_11b, as_11' % e)
        return
    pa = load(D + '/PA_Airship', 'PA_Airship')
    sk = unreal.EditorAssetLibrary.load_asset(D + '/SK_Airship')
    if pa is None or sk is None:
        return
    o('PASS' if pth(sk.get_editor_property('physics_asset')) == AS58_PA_OBJ else 'FAIL', 'PA: SK_Airship uses %s' % pth(sk.get_editor_property('physics_asset')))
    names = sorted(str(n) for n in (pa_tool('GetBodyNames', PhysicsAsset=AS58_PA_OBJ) or []))
    want = sorted(r11.get('bodies') or {})
    o('PASS' if names == want and names else 'FAIL', 'PA: %d bodies, = as_11\'s plan (%d)%s' % (len(names), len(want), '' if names == want else
      ': missing %s, extra %s' % (sorted(set(want) - set(names)), sorted(set(names) - set(want)))))
    # saved body setups: a fresh editor has only what the package holds
    try:
        n_obj = 0
        for ob in unreal.ObjectIterator(unreal.load_class(None, '/Script/Engine.SkeletalBodySetup')):
            try:
                if ob.get_outer() is not None and ob.get_outer().get_path_name() == AS58_PA_OBJ:
                    n_obj += 1
            except Exception:  # noqa: BLE001
                continue
        o('PASS' if n_obj == len(names) else 'WARN', 'PA: %d SkeletalBodySetup objects in PA_Airship for %d bodies%s' % (
            n_obj, len(names), '' if n_obj == len(names) else ' (more = removed bodies still in memory or saved: re-check in a fresh editor)'))
    except Exception as e:  # noqa: BLE001
        o('WARN', 'PA: body setup objects not counted (%s)' % e)
    modes = {}
    for b in names:
        m = str(pa_tool('GetBodyPhysicsMode', PhysicsAsset=AS58_PA_OBJ, BoneName=b))
        modes[m] = modes.get(m, 0) + 1
    o('PASS' if len(modes) == 1 and ('kinematic' in list(modes)[0].lower() or list(modes) == ['1']) else 'FAIL', 'PA: physics modes %s (all Kinematic)' % modes)
    cons = pa_tool('GetConstraints', PhysicsAsset=AS58_PA_OBJ) or []
    o('PASS' if not cons else 'FAIL', 'PA: %d constraints (want 0)' % len(cons))
    pose = unreal.AnimPoseExtensions.get_reference_pose(sk.get_editor_property('skeleton'))
    rb, odd = pa_boxes(names, pose)
    o('PASS' if not odd else 'FAIL', 'PA: every shape an axis-aligned box on a world-aligned bone%s' % ('' if not odd else ': %s' % odd[:6]))
    # = as_11's report (shape names, bone-local centres and sizes; the report rounds to 0.1 cm)
    diff = []
    nshape = 0
    for b in names:
        rep = dict((s['shape'], s) for s in (r11['bodies'].get(b) or []))
        got = dict((s[0], s) for s in rb.get(b, []))
        nshape += len(got)
        if sorted(rep) != sorted(got):
            diff.append((b, 'shapes', sorted(set(rep) ^ set(got))[:4]))
            continue
        for n, s in got.items():
            d = max(max(abs(s[3][i] - rep[n]['centre_local'][i]), abs(s[4][i] - rep[n]['size'][i])) for i in range(3))
            if d > 0.2:
                diff.append((b, n, round(d, 2)))
    o('PASS' if not diff else 'FAIL', 'PA: %d boxes read back = as_11_physics_asset.json (centre / size within 0.2 cm)%s' % (nshape, '' if not diff else ': %s' % diff[:6]))
    # the walkable-deck fit (as_11b refit 2026-11-25 13:33: no hole at hull x 1995..2255 or aft of x -1570): 35 bodies, 136 boxes
    # (96 hull, 7 chain links); the 02:16 build had 119 / 79 with the two holes a walker fell through
    # 2026-11-27 (review, should fix 4): as_11b adds 7 boxes for the crates and barrels on the main deck (Hull_Props_NN) and
    # closes the 10 cm slots between the deck slabs (the same 96 boxes, their sides moved): 35 bodies, 143 boxes, 103 hull
    nh = len(rb.get('Hull', []))
    nprop = len([x for x in rb.get('Hull', []) if x[0].startswith('Hull_Props_')])
    o('PASS' if len(names) == 35 and nshape == 143 and nh == 103 and nprop == 7 else 'FAIL', 'PA: %d bodies / %d boxes / %d hull boxes, %d of them deck '
      'props (want 35 / 143 / 103 / 7)' % (len(names), nshape, nh, nprop))
    # no slot between the deck slabs: along the centre line (y 12.5) every cm of x from -1600 to 2600 (main deck, well, bow
    # wedge) and from 1060 to 3100 (forward deck) is under a Hull box of that level (as_11b closed 19 + 7 slots of 10 cm)
    def _slots(xa, xb, zlo, zhi):
        out, x, g0 = [], xa, None
        while x <= xb:
            cov = any(mn[0] <= x <= mx[0] and mn[1] <= 12.5 <= mx[1] and zlo <= mx[2] < zhi for _, mn, mx, _, _ in rb.get('Hull', []))
            if not cov and g0 is None:
                g0 = x
            if cov and g0 is not None:
                out.append((g0, x))
                g0 = None
            x += 1.0
        return out + ([(g0, xb)] if g0 is not None else [])
    sl = _slots(-1600.0, 2600.0, 150.0, 560.0) + _slots(1060.0, 3100.0, 560.0, 800.0)
    o('PASS' if not sl else 'FAIL', 'PA: no slot between the deck boxes along the centre line (main deck x -1600..2600, forward deck x 1060..3100)%s' % (
        '' if not sl else ': %d open stretches %s' % (len(sl), sl[:6])))
    # every bone with geometry has a body; part boxes fit their bones' part_bounds (+PAD)
    members = dict((b, v['bones']) for b, v in (r11.get('bodies_vs_part_bounds') or {}).items())
    members['Hull'] = ['Hull']
    cov = set(x for b in names for x in members.get(b, [b]))
    miss = sorted(b for b in pb if b not in cov)
    o('PASS' if not miss else 'FAIL', 'PA: %d of %d bones with geometry (part_bounds.json) have a body%s' % (len(pb) - len(miss), len(pb), '' if not miss else '; none: %s' % miss))
    worst, wb = 0.0, None
    for b in names:
        if b == 'Hull' or b not in members:
            continue
        bn = [x for x in members[b] if x in pb]
        if not bn:
            continue
        pmn = [min(pb[x]['min'][i] for x in bn) - AS58_PAD for i in range(3)]
        pmx = [max(pb[x]['max'][i] for x in bn) + AS58_PAD for i in range(3)]
        umn = [min(s[1][i] for s in rb[b]) for i in range(3)]
        umx = [max(s[2][i] for s in rb[b]) for i in range(3)]
        if b == 'ChainFwd':     # link boxes: inside the chain's padded AABB
            d = max(max(pmn[i] - umn[i], umx[i] - pmx[i], 0.0) for i in range(3))
        else:
            d = max(max(abs(umn[i] - pmn[i]), abs(umx[i] - pmx[i])) for i in range(3))
        if d > worst:
            worst, wb = d, b
    o('PASS' if worst <= 0.5 else 'FAIL', 'PA: part boxes = their bones\' part_bounds + %.0f cm: worst %.2f cm (%s)' % (AS58_PAD, worst, wb))
    if 'Helm_Wheel' in rb and 'Helm_Wheel' in pb:
        s = rb['Helm_Wheel']
        sz = [max(x[2][i] for x in s) - min(x[1][i] for x in s) for i in range(3)]
        wz = [pb['Helm_Wheel']['max'][i] - pb['Helm_Wheel']['min'][i] for i in range(3)]
        o('PASS' if max(wz[1], wz[2]) <= 142.0 and max(sz[1], sz[2]) <= max(wz[1], wz[2]) + 2 * AS58_PAD + 0.5 else 'FAIL',
          'PA: Helm_Wheel box %.1f x %.1f x %.1f cm around the wheel %.1f x %.1f x %.1f cm (140 cm across the tips)' % (tuple(sz) + tuple(wz)))
    if 'Helm' in rb:
        s = rb['Helm']
        o('INFO', 'PA: Helm pedestal box %s..%s' % ([round(x, 1) for x in s[0][1]], [round(x, 1) for x in s[0][2]]))
    # Hull boxes = pa_hull_boxes.json, then as_11b's rules against the hull survey (exec'd as a library, no main)
    hull = rb.get('Hull') or []
    ref_hb = dict((b['name'], b) for b in hb.get('hull_boxes') or [])
    hd = [n for n, mn, mx, _, _ in hull if n not in ref_hb or max(max(abs(mn[i] - ref_hb[n]['min'][i]), abs(mx[i] - ref_hb[n]['max'][i])) for i in range(3)) > 0.2]
    o('PASS' if hull and not hd and len(hull) == len(ref_hb) else 'FAIL', 'PA: %d Hull boxes = pa_hull_boxes.json (%d)%s' % (len(hull), len(ref_hb), '' if not hd else ': off %s' % hd[:6]))
    ns = {'__name__': 'as11b_lib'}
    exec(open(os.path.join(_AS_UE, 'as_11b_hull_boxes.py')).read(), ns)
    _, cols = ns['load']()
    boxes = [{'name': n, 'min': mn, 'max': mx} for n, mn, mx, _, _ in hull]
    bad = [c for c in ns['check'](cols, boxes) if c['above_top'] or c['below_bottom'] or c['no_hull']]
    o('PASS' if not bad else 'FAIL', 'PA: no Hull box column above the hull\'s top hit or below its bottom hit (+-2 cm) or over no hull%s' % ('' if not bad else ': %s' % bad[:5]))
    regs = dict((r[0], r) for r in list(ns['REGIONS']) + list(ns.get('EXTRA_REGIONS') or []))
    step = ns['STEP']
    band_bad = []
    for b in boxes:
        reg = regs.get(b['name'].split('_')[1]) if b['name'].count('_') >= 2 else None
        if reg is None:
            band_bad.append((b['name'], 'no region'))
            continue
        _, x0, x1, lo, hi = reg
        mn, mx = b['min'], b['max']
        # x: a region owns the survey columns whose CENTRES lie in [x0, x1), and a box covers its columns' whole cells, so it
        # may reach half a cell (12.5 cm) past the limit (the Well starts at 2130 between the columns 2112.5 and 2137.5: its
        # cells start at 2125; as_11b's 5 cm shrink used to hide that, the boxes that now meet their neighbours do not)
        if mn[0] < x0 - step / 2 - 1 or mx[0] > x1 + step / 2 + 1 or mn[2] < min(lo, 1e8) - 2 or mx[2] > hi + 2:
            band_bad.append((b['name'], 'outside region %s' % reg[0]))
        x = (int(mn[0] // step)) * step + step / 2
        while x < mx[0]:
            y = (int(mn[1] // step) - 1) * step + step / 2
            while y < mx[1]:
                if mn[0] <= x <= mx[0] and mn[1] <= y <= mx[1]:
                    zs = [z for z in cols.get((round(x, 1), round(y, 1))) or [] if lo <= z < hi]
                    if not zs:
                        band_bad.append((b['name'], x, y, 'no hull in band'))
                    elif mx[2] > max(zs) + 2.05 or mn[2] < min(zs) - 2.05:      # 0.05: box limits are rounded to 0.1 cm (a prop's bottom is its deck hit - 2.0)
                        band_bad.append((b['name'], x, y, 'top %.1f / bottom %.1f vs band hull %.1f..%.1f' % (mx[2], mn[2], min(zs), max(zs))))
                y += step
            x += step
    o('PASS' if not band_bad else 'FAIL', 'PA: every Hull box inside its region\'s z band and under the hull top in that band in every column '
      '(nothing in the open truss under the forward platform)%s' % ('' if not band_bad else ': %d cells, %s' % (len(band_bad), band_bad[:5])))
    # the five removed deck pieces (Blender m, +Y port -> UE cm): no body stands where they were
    try:
        pieces = json.load(open(AS58_REMOVALS))['pieces']
    except Exception as e:  # noqa: BLE001
        o('WARN', 'PA: deck_removals.json not readable (%s)' % e)
        pieces = []
    rem = []
    for p in pieces:
        mn = [100.0 * p['bbox_min'][0], -100.0 * p['bbox_max'][1], 100.0 * p['bbox_min'][2]]
        mx = [100.0 * p['bbox_max'][0], -100.0 * p['bbox_min'][1], 100.0 * p['bbox_max'][2]]
        tops = [c for (x, y), c in cols.items() if mn[0] <= x <= mx[0] and mn[1] <= y <= mx[1] and c]
        deck = max(c[0] for c in tops) if tops else None
        over = []
        for b, shapes in rb.items():
            for n, smn, smx, _, _ in shapes:
                if all(min(smx[i], mx[i]) - max(smn[i], mn[i]) > 0 for i in range(3)):
                    if b != 'Hull' or deck is None or smx[2] > deck + 2.0:
                        over.append((b, n, round(smx[2], 1)))
        rem.append({'arrow': p['arrow'], 'deck_top_cm': deck, 'bodies_in_piece_volume': over})
    R['pa_removed_pieces'] = rem
    o('PASS' if pieces and not any(r['bodies_in_piece_volume'] for r in rem) else 'FAIL', 'PA: no body where the %d removed deck pieces were '
      '(hull boxes stay under the deck there: deck tops %s cm)%s' % (len(pieces), [round(r['deck_top_cm'], 1) if r['deck_top_cm'] is not None else None for r in rem],
                                                                    '' if not any(r['bodies_in_piece_volume'] for r in rem) else ': %s' % rem))
    hz = max((s[2][2] for s in hull), default=None)
    o('INFO', 'PA: %d boxes on %d bodies; highest Hull box top z %.1f cm' % (nshape, len(names), hz if hz is not None else float('nan')))


# ------------------------------------------------------------------------------------------------ frozen assets vs git HEAD
def git(*args):
    return subprocess.run(['git', '-C', AS58_W] + list(args), capture_output=True, text=True, timeout=30)


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def check_frozen():
    for rel in FROZEN:
        p = os.path.join(AS58_W, rel)
        r = git('show', 'HEAD:' + rel)
        if r.returncode != 0:
            o('WARN', '%s: not in HEAD (%s)' % (rel, r.stderr.strip()[:200]))
            continue
        txt = r.stdout
        oid = next((l.split(':', 1)[1].strip() for l in txt.splitlines() if l.startswith('oid sha256:')), None)
        size = next((int(l.split()[1]) for l in txt.splitlines() if l.startswith('size ')), None)
        if oid is None:
            o('WARN', '%s: HEAD blob is not an LFS pointer; compared by git diff' % rel)
            d = git('diff', '--quiet', 'HEAD', '--', rel)
            o('PASS' if d.returncode == 0 else 'FAIL', '%s unchanged vs HEAD' % rel)
            continue
        cur = sha256(p) if os.path.exists(p) else None
        o('PASS' if cur == oid and os.path.getsize(p) == size else 'FAIL', '%s unchanged vs HEAD (LFS %s.. %d bytes; now %s.. %s bytes)' % (
            rel, oid[:12], size, (cur or 'missing')[:12], os.path.getsize(p) if os.path.exists(p) else None))
    r = git('ls-tree', '--name-only', 'HEAD', INPUT_DIR + '/')
    head = sorted(os.path.basename(x) for x in r.stdout.split())
    now = sorted(x for x in os.listdir(os.path.join(AS58_W, INPUT_DIR)) if x.endswith('.uasset'))
    o('PASS' if head == now else 'FAIL', 'Input folder: %d assets, same as HEAD%s' % (len(now), '' if head == now else ': added %s removed %s' % (
        sorted(set(now) - set(head)), sorted(set(head) - set(now)))))


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE is running: not checked (it opens Niagara editors)')
        return
    dm = dims()
    for name, fn in (('fx', check_fx), ('ball', check_ball), ('turret', lambda: check_turret(dm)), ('ship', lambda: check_ship(dm)),
                     ('pa', check_pa), ('frozen', check_frozen)):
        try:
            fn()
        except Exception:  # noqa: BLE001
            o('FAIL', '%s checks crashed: %s' % (name, traceback.format_exc()[-600:]))
    for prev in ('as_51_compile.json', 'as_54_compile.json', 'as_58_compile.json'):
        p = os.path.join(AS_SAVED, prev)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    c = json.load(f)
                o('INFO', 'previous %s (%s, done %s, all_ok %s): %s' % (prev, c.get('started_utc'), c.get('done'), c.get('all_ok'),
                                                                     dict((k.rsplit('/', 1)[-1], v.get('status')) for k, v in (c.get('systems') or {}).items())))
            except Exception:  # noqa: BLE001
                pass
    eal = unreal.EditorAssetLibrary
    systems = [full(p) for p in FX.values() if eal.does_asset_exist(p)]
    out = as5x_bg_compile(systems, 'as_58_compile.json', 'as58')
    o('INFO', 'compile check of %d systems running in the background -> %s' % (len(systems), out))


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', 'as_58 crashed: %s' % traceback.format_exc())
as_dump('as_58_verify_round2.json', json.dumps(R, indent=1, default=str))
print('RESULT: %s %s' % ('PASS' if not R['counts'].get('FAIL') else 'FAIL', R['counts']))
