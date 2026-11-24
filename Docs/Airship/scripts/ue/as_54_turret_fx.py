# as_54_turret_fx.py - round 2 D6: the turrets' three Niagara systems, copies of existing project effects in
# /Game/Assets/MyShip/Drivable/FX (only the copies are changed; Talal 11-22: no new effect authoring):
#   NS_AirshipTurretTracer  <- /Game/Assets/Effects/AppreiticeFx/GunShootHit/PS_06_Flipbook_Sprites_my (the character gun's
#       tracer). AAirshipTurret writes NDC_GunShootHit (MuzzlePos / HitLocation) with SystemToSpawn = this copy, never a new
#       channel (a copy's reader still points at the original channel). Every module input (dynamic input chains included)
#       and user parameter holding the fixed 7500 cm/s tracer speed is set to 30000 (at 250 m the bullet would land 3 s
#       before a 75 m/s tracer); what was found is printed; nothing found -> WARN and the copy is left as it is.
#   NS_AirshipTurretMuzzle  <- /Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash (the mech gun's flash):
#       Bullet_Shell_Eject removed, User.Use Bullet Shell 0, User.Global Scale 1.5, every emitter of its own life cycle
#       Loop Behavior Once 0.2 s (as_51), smoke lifetimes <= 0.5 s. The turret re-activates it per shot batch and cuts it
#       MuzzleFlashMaxSeconds (1 s) after the last shot.
#   NS_AirshipTurretFire    <- /Game/Assets/Effects/Fire/NS_Fire, unchanged (a destroyed turret burns until the ship goes;
#       BP_AirshipTurret's DestroyedFXComponent scales it to 0.3).
# A copy is made only when missing; an existing copy (ours by name and folder) is edited in place, so a re-run changes
# nothing that is already right. Saves only these three. Then a background compile check of the three ->
# Saved/Airship/as_54_compile.json (about 15-60 s after this call returns).
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 54 Docs/Airship/scripts/ue/as_54_turret_fx.py 300
# Report: Saved/Airship/as_54_turret_fx.json (incl. the tracer probe)
# Library use (as_58_verify_round2.py): AS54_LIB_ONLY = True before exec; only the as54_* functions are defined.
import os, re, json, traceback  # unreal = inbox namespace
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
AS51_LIB_ONLY = True
exec(open(os.path.join(_AS_UE, 'as_51_muzzle_once.py')).read())     # as_nh + as_fxlib + the as51_* / as5x_* functions

AS54_FX = '/Game/Assets/MyShip/Drivable/FX'
AS54_TRACER = (AS54_FX + '/NS_AirshipTurretTracer', '/Game/Assets/Effects/AppreiticeFx/GunShootHit/PS_06_Flipbook_Sprites_my')
AS54_MUZZLE = (AS54_FX + '/NS_AirshipTurretMuzzle', '/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash')
AS54_FIRE = (AS54_FX + '/NS_AirshipTurretFire', '/Game/Assets/Effects/Fire/NS_Fire')
AS54_SPEED_OLD, AS54_SPEED_NEW = 7500.0, 30000.0
AS54_GLOBAL_SCALE = 1.5
AS54_SMOKE_MAX = 0.5
AS54_SCRIPTS = ('EmitterSpawnScript', 'EmitterUpdateScript', 'ParticleSpawnScript', 'ParticleUpdateScript')
AS54_SYS_SCRIPTS = ('SystemSpawnScript', 'SystemUpdateScript')
_AS54_NUM = re.compile(r'(?<![\w.])7500(?:\.0*)?(?![\w.])')
_AS54_NUM_NEW = re.compile(r'(?<![\w.])30000(?:\.0*)?(?![\w.])')
AS54_R = {'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}}


def _o54(line):
    tag = line.split(':', 1)[0]
    if tag in AS54_R['counts']:
        AS54_R['counts'][tag] += 1
    AS54_R['lines'].append(line)
    print(line)


def _full54(p):
    return '%s.%s' % (p, p.rsplit('/', 1)[1])


def as54_ensure_copy(dst, src):
    eal = unreal.EditorAssetLibrary
    if eal.does_asset_exist(dst):
        a = eal.load_asset(dst)
        if not isinstance(a, unreal.NiagaraSystem):
            _o54('FAIL: %s exists and is a %s: not touched' % (dst, a.get_class().get_name()))
            return None
        _o54('INFO: %s exists: edited in place (copy of %s)' % (dst, src))
        as51_close_editors(_full54(dst))
        return _full54(dst)
    if not eal.does_asset_exist(src):
        _o54('FAIL: source %s missing' % src)
        return None
    d = eal.duplicate_asset(src, dst)
    if d is None:
        _o54('FAIL: could not duplicate %s -> %s' % (src, dst))
        return None
    _o54('INFO: duplicated %s -> %s' % (src, d.get_path_name()))
    return _full54(dst)


# ------------------------------------------------------------------------------------------------ tracer speed probe
def _as54_walk_chain(node, path, out):
    """node: a NiagaraExt_DynamicInputChain value dict; records (path, kind, value) of every leaf float / expression."""
    v = node.get('value') or {}
    k = as51_kind(v)
    if k == 'NiagaraFloat':
        try:
            out.append((path, 'float', float((v.get('value') or {}).get('value'))))
        except Exception:  # noqa: BLE001
            pass
    elif k == 'NiagaraExt_StackInputData_HlslExpression':
        out.append((path, 'expr', (v.get('value') or {}).get('hlslExpression') or ''))
    for c in node.get('inputs') or []:
        cv = c.get('value') or {}
        _as54_walk_chain(cv, path + [cv.get('name')], out)


def as54_tracer_probe(S):
    """Every input holding the tracer speed (7500, or 30000 after a first run) and every input named like a speed."""
    hits, speeds = [], []
    for em in ['None'] + as51_emitters(S):
        for scr in (AS54_SYS_SCRIPTS if em == 'None' else AS54_SCRIPTS):
            try:
                mods = fx_modules(S, em, scr)
            except Exception:  # noqa: BLE001
                continue
            for mod in mods:
                try:
                    ins = as51_inputs(S, em, scr, mod)
                except Exception:  # noqa: BLE001
                    continue
                for name, v in ins.items():
                    leaves = []
                    k = as51_kind(v)
                    if k == 'NiagaraExt_StackInputData_DynamicInput':
                        try:
                            ch = nt('GetDynamicInputChain', stackInputRef=ref(S, em, scr, mod, [name]))
                            _as54_walk_chain(ch.get('value') or {}, [name], leaves)
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        _as54_walk_chain({'value': v}, [name], leaves)
                    for p, kind, val in leaves:
                        loc = {'emitter': em, 'script': scr, 'module': mod, 'path': p, 'kind': kind, 'value': val}
                        if kind == 'float' and (abs(val - AS54_SPEED_OLD) < 0.5 or abs(val - AS54_SPEED_NEW) < 0.5):
                            hits.append(loc)
                        elif kind == 'expr' and (_AS54_NUM.search(val) or _AS54_NUM_NEW.search(val)):
                            hits.append(loc)
                        elif 'speed' in ' '.join(str(x) for x in p).lower() or 'velocity' in ' '.join(str(x) for x in p).lower():
                            speeds.append(loc)
    users = []
    for u in nt('GetUserVariables', system=sref(S))['userVariables']:
        try:
            val = float((u.get('defaultValue') or {}).get('value', {}).get('value'))
        except Exception:  # noqa: BLE001
            continue
        if abs(val - AS54_SPEED_OLD) < 0.5 or abs(val - AS54_SPEED_NEW) < 0.5 or 'speed' in u['name'].lower():
            users.append({'name': u['name'], 'value': val})
    return hits, speeds, users


def as54_tracer_fix(S):
    hits, speeds, users = as54_tracer_probe(S)
    AS54_R['tracer_probe_before'] = {'hits': hits, 'speed_like_inputs': speeds, 'user': users}
    for h in hits:
        _o54('INFO: tracer speed candidate %s/%s/%s %s (%s) = %s' % (h['emitter'], h['script'], h['module'], h['path'], h['kind'], h['value']))
    for s in speeds:
        _o54('INFO: speed-like input (not 7500, left) %s/%s/%s %s = %s' % (s['emitter'], s['script'], s['module'], s['path'], s['value']))
    for u in users:
        _o54('INFO: user parameter %s = %s' % (u['name'], u['value']))
    n_set = n_done = 0
    for h in hits:
        if h['kind'] == 'float':
            if abs(h['value'] - AS54_SPEED_NEW) < 0.5:
                n_done += 1
                continue
            set_input(S, h['emitter'], h['script'], h['module'], h['path'], f_float(AS54_SPEED_NEW))
            n_set += 1
        else:
            new = _AS54_NUM.sub('30000.0', h['value'])
            if new == h['value']:
                n_done += 1
                continue
            set_input(S, h['emitter'], h['script'], h['module'], h['path'], f_expr(new))
            n_set += 1
    for u in users:
        nm = u['name'][5:] if u['name'].startswith('User.') else u['name']
        if abs(u['value'] - AS54_SPEED_OLD) < 0.5:
            fx_user_vars(S, [(nm, T_FLOAT, {'value': AS54_SPEED_NEW}, 'turret tracer speed (cm/s); the gun tracer is 7500')])
            n_set += 1
        elif abs(u['value'] - AS54_SPEED_NEW) < 0.5:
            n_done += 1
    hits2, _, users2 = as54_tracer_probe(S)
    AS54_R['tracer_probe_after'] = {'hits': hits2, 'user': users2}
    left = [h for h in hits2 if (h['kind'] == 'float' and abs(h['value'] - AS54_SPEED_OLD) < 0.5) or
            (h['kind'] == 'expr' and _AS54_NUM.search(h['value']))] + [u for u in users2 if abs(u['value'] - AS54_SPEED_OLD) < 0.5]
    if not hits and not [u for u in users if abs(u['value'] - AS54_SPEED_OLD) < 0.5 or abs(u['value'] - AS54_SPEED_NEW) < 0.5]:
        _o54('WARN: no input or user parameter of %s holds 7500 (the tracer speed may live inside a scratch module or the material):'
          ' tracer left as it is; at long range it reaches the hit after the bullet' % S)
        return
    _o54('%s: tracer speed: %d input(s) set to %.0f, %d already %.0f, %d still at 7500 %s' % (
        'PASS' if not left else 'FAIL', n_set, AS54_SPEED_NEW, n_done, AS54_SPEED_NEW, len(left), left))


# ------------------------------------------------------------------------------------------------ muzzle
def as54_smoke_lifetimes(S, rep):
    for em in as51_emitters(S):
        if 'smoke' not in em.lower():
            continue
        for mod in fx_modules(S, em, 'ParticleSpawnScript'):
            ins = as51_inputs(S, em, 'ParticleSpawnScript', mod)
            for name in [n for n in ins if n in ('Lifetime Min', 'Lifetime Max', 'Lifetime', 'Particles.Lifetime')]:
                if as51_kind(ins[name]) == 'NiagaraExt_StackInputData_Unsupported':
                    continue        # hidden by the module's mode
                val = as51_float(ins[name])
                if val is not None and val <= AS54_SMOKE_MAX + 1e-4:
                    rep.append('INFO: %s/%s %s = %.3f s (<= %.2f, kept)' % (em, mod, name, val, AS54_SMOKE_MAX))
                    continue
                # too long, or not a plain number (a curve / dynamic input we can't bound): a fixed short life, Min below Max
                want = 0.3 if name == 'Lifetime Min' else AS54_SMOKE_MAX
                set_input(S, em, 'ParticleSpawnScript', mod, [name], f_float(want))
                got = as51_float(as51_inputs(S, em, 'ParticleSpawnScript', mod).get(name, {}))
                ok = got is not None and abs(got - want) < 1e-4
                rep.append('%s: %s/%s %s %s -> %s s (smoke <= %.2f s)' % ('PASS' if ok else 'FAIL', em, mod, name,
                                                                      as51_short(ins[name]), got, AS54_SMOKE_MAX))


def as54_muzzle_fix(S):
    ems = as51_emitters(S)
    if 'Bullet_Shell_Eject' in ems:
        nt('RemoveEmitter', emitterToRemove=ref(S, 'Bullet_Shell_Eject'))
        _o54('INFO: removed emitter Bullet_Shell_Eject')
    else:
        _o54('INFO: no Bullet_Shell_Eject emitter (already removed)')
    fx_user_vars(S, [('Use Bullet Shell', T_BOOL, {'value': 0}, 'no shells for the airship machine gun'),
                     ('Global Scale', T_FLOAT, {'value': AS54_GLOBAL_SCALE}, 'x%.1f of the mech gun flash for the twin turret barrels' % AS54_GLOBAL_SCALE)])
    rep = []
    as51_one_shot(S, rep)
    as54_smoke_lifetimes(S, rep)
    for l in rep:
        _o54(l)
    uv = dict((u['name'], (u.get('defaultValue') or {}).get('value')) for u in nt('GetUserVariables', system=sref(S))['userVariables'])
    gs = (uv.get('User.Global Scale') or {}).get('value')
    sh = (uv.get('User.Use Bullet Shell') or {}).get('value')
    _o54('%s: user Global Scale %s (want %.1f), Use Bullet Shell %s (want 0)' % (
        'PASS' if gs is not None and abs(float(gs) - AS54_GLOBAL_SCALE) < 1e-4 and not sh else 'FAIL', gs, AS54_GLOBAL_SCALE, sh))
    _o54('%s: emitters now %s' % ('PASS' if 'Bullet_Shell_Eject' not in as51_emitters(S) else 'FAIL', as51_emitters(S)))
    AS54_R['muzzle_probe'] = as51_probe(S)


def as54_main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        _o54('FAIL: PIE is running: nothing changed')
        return
    done = []
    tr = as54_ensure_copy(*AS54_TRACER)
    if tr:
        as54_tracer_fix(tr)
        done.append(tr)
    mz = as54_ensure_copy(*AS54_MUZZLE)
    if mz:
        as54_muzzle_fix(mz)
        done.append(mz)
    fi = as54_ensure_copy(*AS54_FIRE)
    if fi:
        _o54('INFO: %s: emitters %s (unchanged copy)' % (fi, as51_emitters(fi)))
        done.append(fi)
    if AS54_R['counts']['FAIL']:
        _o54('WARN: %d FAIL: NOT saved (the edits stay in memory)' % AS54_R['counts']['FAIL'])
        return
    for p, ok in save_paths([s.split('.')[0] for s in done]):
        _o54('%s: saved %s' % ('PASS' if ok else 'FAIL', p))
    out = as5x_bg_compile(done, 'as_54_compile.json', 'as54')
    _o54('INFO: compile check of %d systems started in the background -> %s' % (len(done), out))


if not globals().pop('AS54_LIB_ONLY', False):
    try:
        as54_main()
    except Exception:  # noqa: BLE001
        _o54('FAIL: as_54 crashed: %s' % traceback.format_exc())
    as_dump('as_54_turret_fx.json', json.dumps(AS54_R, indent=1, default=str))
    print('RESULT: %s %s' % ('PASS' if not AS54_R['counts']['FAIL'] else 'FAIL', AS54_R['counts']))
