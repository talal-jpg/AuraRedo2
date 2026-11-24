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
#   frozen   IMC_Airship and the Input folder unchanged, PA_Airship unchanged: the .uasset bytes vs the clone's committed
#            LFS objects (git show HEAD:<path> gives the pointer: sha256 + size). PR A adds no input asset and does not
#            rebuild PA_Airship.
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
FROZEN = ['Content/Assets/MyShip/Drivable/Input/IMC_Airship.uasset', 'Content/Assets/MyShip/Drivable/PA_Airship.uasset']
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
        if em != 'None' and (lcm.get('display') or '').lower() == 'system':
            continue
        if lb and (lb.get('display') or '').lower() != 'once':
            left.append((em, lb.get('display')))
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
        hits, speeds, users = as54_tracer_probe(T)
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
                     ('frozen', check_frozen)):
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
