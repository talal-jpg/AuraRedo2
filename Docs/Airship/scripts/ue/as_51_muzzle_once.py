# as_51_muzzle_once.py - round 2 D1: the cannon smoke stops within 1 s. Edits /Game/Assets/MyShip/Drivable/FX/NS_AirshipMuzzle
# IN PLACE (our own asset, built by as_06 + as_07; nothing else is touched or saved).
# Why: its Blast_Puffs emitter (added by as_06 from the engine Fountain template) kept the template's own looping cycle
# (EmitterState Loop Behavior Infinite, Loop Duration 2 s) and puffs living 1.2-2.2 s, so the system never completed and every
# bAutoDestroy component that HandleCannonsFired attached to a muzzle socket re-burst every 2 s.
#   1. probe: every emitter's EmitterUpdateScript/EmitterState inputs (and the system's SystemState), the enum identifiers of
#      Life Cycle Mode / Loop Behavior exactly as the toolset returns them, Blast_Puffs' InitializeParticle lifetimes
#      -> Saved/Airship/as_51_probe.json. No enum identifier is hard-coded: "Once" is found by its display name among the
#      probed values, else by setting each NewEnumerator<i> in turn and reading the display name back.
#   2. every emitter whose Loop Behavior is not Once (Life Cycle Mode Self): Loop Behavior Once, Loop Duration 0.2 s.
#      Emitters in Life Cycle Mode System follow the system state (it is set to Once 0.2 s too if it isn't Once).
#   3. Blast_Puffs: InitializeParticle Lifetime Min/Max 1.2/2.2 -> 0.5/0.85; alpha 1 -> 0 over the particle's life
#      (ScaleColor Scale Alpha = 1.0 - Particles.NormalizedAge; the module is added if the emitter has none).
#   4. Muzzle_Smoke lifetimes stay (0.2-0.3 s).
#   5. every changed input read back, saved (only this asset), then a background compile check: the Niagara system editor is
#      opened (compile errors only show with it open), GetSystemCompileState + GetStackIssues are read on later editor ticks,
#      the editor is closed again -> Saved/Airship/as_51_compile.json (about 5-20 s after this call returns).
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 51 Docs/Airship/scripts/ue/as_51_muzzle_once.py 300
#   then: cat Saved/Airship/as_51_compile.json   (or as_58_verify_round2.py, which reads it too)
# Report: Saved/Airship/as_51_muzzle_once.json. Re-runnable (a second run finds everything Once and changes nothing).
# Library use (as_06_muzzle.py, as_54_turret_fx.py): set AS51_LIB_ONLY = True before exec; only the functions are defined.
# The C++ cap (UAirshipSettings::MuzzleFXMaxSeconds, DeactivateImmediate after 1 s) is the safety net on top of this.
import os, re, json, time, traceback  # unreal = inbox namespace
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())

AS51_SYSTEM = '/Game/Assets/MyShip/Drivable/FX/NS_AirshipMuzzle.NS_AirshipMuzzle'
AS51_PUFFS = 'Blast_Puffs'
AS51_PUFF_LIFE = (0.5, 0.85)
AS51_LOOP_S = 0.2
AS51_FADE_EXPR = '1.0 - Particles.NormalizedAge'
AS51_SCALE_COLOR = '/Niagara/Modules/Update/Color/ScaleColor.ScaleColor'
_AS51_ES, _AS51_EU, _AS51_PS, _AS51_PU = 'EmitterSpawnScript', 'EmitterUpdateScript', 'ParticleSpawnScript', 'ParticleUpdateScript'


# ------------------------------------------------------------------------------------------------ small readers
def as51_emitters(S):
    return [e['emitterName'] for e in nt('GetSystemSummary', system=sref(S))['emitters']]


def as51_inputs(S, em, scr, mod):
    """{input name: value dict} of one module (GetModuleInputValues)."""
    vals = nt('GetModuleInputValues', moduleRef=ref(S, em, scr, mod))
    return dict((i['name'], i.get('value') or {}) for i in (vals or {}).get('inputs', []))


def as51_kind(v):
    return (v.get('struct') or {}).get('refPath', '').split('.')[-1]


def as51_enum(v):
    """(enum path, enum name, display name) of an enum input value, else None."""
    if as51_kind(v) != 'NiagaraExt_StackInputData_Enum':
        return None
    x = v.get('value') or {}
    return ((x.get('enum') or {}).get('refPath'), x.get('enumName'), x.get('displayName'))


def as51_float(v):
    """the float of a plain float input, else None (dynamic inputs, links and expressions are not plain floats)."""
    if as51_kind(v) != 'NiagaraFloat':
        return None
    try:
        return float((v.get('value') or {}).get('value'))
    except Exception:  # noqa: BLE001
        return None


def as51_short(v):
    """a short readable form of an input value for the reports."""
    k = as51_kind(v)
    x = v.get('value') or {}
    if k == 'NiagaraExt_StackInputData_Enum':
        return '%s (%s)' % (x.get('displayName'), x.get('enumName'))
    if k == 'NiagaraExt_StackInputData_HlslExpression':
        return 'expr: %s' % x.get('hlslExpression')
    if k == 'NiagaraExt_StackInputData_Linked':
        return 'link: %s' % (x.get('linkedVariable') or {}).get('name')
    if k == 'NiagaraExt_StackInputData_DynamicInput':
        return 'dynamic: %s' % (x.get('dynamicInputAsset') or {}).get('refPath')
    if k in ('NiagaraFloat', 'NiagaraInt32', 'NiagaraBool'):
        return x.get('value')
    return '%s %s' % (k, json.dumps(x)[:120])


def as51_state_module(S, em):
    """(script, module) holding the life cycle inputs: SystemUpdateScript/SystemState for the system ('None'), else
    EmitterUpdateScript/EmitterState. None if the stack has no such module."""
    scr = 'SystemUpdateScript' if em == 'None' else _AS51_EU
    want = 'SystemState' if em == 'None' else 'EmitterState'
    mods = fx_modules(S, em, scr)
    if want in mods:
        return scr, want
    for m in mods:
        if want.lower() in m.lower():
            return scr, m
    return None


# ------------------------------------------------------------------------------------------------ probe
def as51_probe(S, seen=None):
    """Life cycle inputs of the system and of every emitter, InitializeParticle lifetimes, module lists. seen (optional,
    filled): {enum path: {display name: enum name}} from every enum value met (the identifiers the toolset uses)."""
    seen = seen if seen is not None else {}
    out = {'system': S, 'emitters': {}, 'user': []}
    try:
        out['user'] = [(u['name'], u['defaultValue'].get('value')) for u in nt('GetUserVariables', system=sref(S))['userVariables']]
    except Exception:  # noqa: BLE001
        out['user_error'] = traceback.format_exc().strip().splitlines()[-1]
    for em in ['None'] + as51_emitters(S):
        d = {}
        sm = as51_state_module(S, em)
        if sm:
            ins = as51_inputs(S, em, sm[0], sm[1])
            d['state_module'] = '%s/%s' % sm
            d['state'] = dict((k, as51_short(v)) for k, v in ins.items() if as51_kind(v) != 'NiagaraExt_StackInputData_Unsupported')
            for k, v in ins.items():
                e = as51_enum(v)
                if e and e[0]:
                    seen.setdefault(e[0], {})[e[2]] = e[1]
            for k in ('Life Cycle Mode', 'Loop Behavior', 'Loop Duration Mode', 'Loop Duration'):
                if k in ins:
                    e = as51_enum(ins[k])
                    d[k] = {'display': e[2], 'enumName': e[1], 'enum': e[0]} if e else as51_short(ins[k])
        if em != 'None':
            try:
                d['modules'] = dict((scr, fx_modules(S, em, scr)) for scr in (_AS51_EU, _AS51_PS, _AS51_PU))
                if 'InitializeParticle' in d['modules'][_AS51_PS]:
                    ip = as51_inputs(S, em, _AS51_PS, 'InitializeParticle')
                    d['lifetime'] = dict((k, as51_short(ip[k])) for k in ('Lifetime Mode', 'Lifetime Min', 'Lifetime Max', 'Lifetime') if k in ip)
                    for k, v in ip.items():
                        e = as51_enum(v)
                        if e and e[0]:
                            seen.setdefault(e[0], {})[e[2]] = e[1]
                if 'ScaleColor' in d['modules'][_AS51_PU]:
                    sc = as51_inputs(S, em, _AS51_PU, 'ScaleColor')
                    d['scale_alpha'] = as51_short(sc.get('Scale Alpha', {}))
            except Exception:  # noqa: BLE001
                d['error'] = traceback.format_exc().strip().splitlines()[-1]
        out['emitters'][em] = d
    out['enum_identifiers_seen'] = seen
    return out


# ------------------------------------------------------------------------------------------------ enum by display name
def as51_find_enum(S, em, scr, mod, inp, want_display, seen, rep):
    """The enum name whose display name is want_display for this input. First from the probed values (seen); else every
    NewEnumerator<i> of the input's enum is set in turn and its display name read back (the matching one stays set; if
    none matches the original value is put back). Returns (enum path, enum name) or (None, None)."""
    cur = as51_enum(as51_inputs(S, em, scr, mod).get(inp, {}))
    if cur is None:
        return None, None
    path = cur[0]
    for disp, name in (seen.get(path) or {}).items():
        if (disp or '').strip().lower() == want_display.lower():
            return path, name
    stem = (cur[1] or '').split('::')[0] or path.split('.')[-1]
    for i in range(8):
        cand = '%s::NewEnumerator%d' % (stem, i)
        try:
            set_input(S, em, scr, mod, [inp], fx_enum(path, cand))
            got = as51_enum(as51_inputs(S, em, scr, mod).get(inp, {}))
        except Exception:  # noqa: BLE001
            continue
        if got:
            seen.setdefault(path, {})[got[2]] = got[1]
            if (got[2] or '').strip().lower() == want_display.lower():
                rep.append('INFO: %s/%s/%s %s: "%s" = %s (found by setting each NewEnumerator and reading it back)' % (
                    em, scr, mod, inp, want_display, got[1]))
                return path, got[1]
    set_input(S, em, scr, mod, [inp], fx_enum(path, cur[1]))
    rep.append('FAIL: %s/%s/%s %s: no enumerator reads back as "%s"; put back %s' % (em, scr, mod, inp, want_display, cur[1]))
    return None, None


# ------------------------------------------------------------------------------------------------ edits
def as51_never_ends(d):
    """True when a probed stack (as51_probe's per-emitter dict) never completes: Loop Behavior not Once, or Once with
    Loop Duration Mode Infinite (EmitterState: the loop then never ends, and Loop Duration is hidden by that switch)."""
    lb = d.get('Loop Behavior') if isinstance(d.get('Loop Behavior'), dict) else {}
    ldm = d.get('Loop Duration Mode') if isinstance(d.get('Loop Duration Mode'), dict) else {}
    if lb and (lb.get('display') or '').strip().lower() != 'once':
        return True
    return bool(ldm) and (ldm.get('display') or '').strip().lower() != 'fixed'


def as51_fixed_duration(S, em, scr, mod, who, seen, rep):
    """Loop Duration Mode -> Fixed when the stack has that input and it isn't Fixed (found by display name like Once).
    Must run after Loop Behavior Once and before Loop Duration is set: with Loop Duration Mode Infinite the Loop
    Duration input is hidden (SetStackInputData refuses it) and a Once loop never ends. Returns True if changed,
    False if already Fixed / no such input, None if Fixed could not be set."""
    ldm = as51_enum(as51_inputs(S, em, scr, mod).get('Loop Duration Mode', {}))
    if ldm is None or (ldm[2] or '').strip().lower() == 'fixed':
        return False
    path, fixed = as51_find_enum(S, em, scr, mod, 'Loop Duration Mode', 'Fixed', seen, rep)
    if fixed is None:
        return None
    set_input(S, em, scr, mod, ['Loop Duration Mode'], fx_enum(path, fixed))
    b = as51_enum(as51_inputs(S, em, scr, mod).get('Loop Duration Mode', {}))
    ok = b is not None and (b[2] or '').strip().lower() == 'fixed'
    rep.append('%s: %s: Loop Duration Mode %s (%s) -> %s (%s)' % ('PASS' if ok else 'FAIL', who, ldm[2], ldm[1], b and b[2], b and b[1]))
    return True if ok else None


def as51_one_shot(S, rep, loop_s=AS51_LOOP_S, seen=None):
    """Every emitter whose own life cycle (Self) loops: Loop Behavior Once + Loop Duration Mode Fixed (when the module has
    it) + Loop Duration loop_s. A stack already Once but with Loop Duration Mode Infinite gets Fixed + loop_s too (it
    would never end). Emitters in Life Cycle Mode System follow the system state, which gets the same if it isn't Once.
    Returns the number of changed stacks."""
    seen = seen if seen is not None else {}
    as51_probe(S, seen)
    n = 0
    for em in ['None'] + as51_emitters(S):
        sm = as51_state_module(S, em)
        who = 'system' if em == 'None' else em
        if not sm:
            rep.append('WARN: %s: no %s module: left as it is' % (who, 'SystemState' if em == 'None' else 'EmitterState'))
            continue
        scr, mod = sm
        ins = as51_inputs(S, em, scr, mod)
        lcm = as51_enum(ins.get('Life Cycle Mode', {}))
        if em != 'None' and lcm and (lcm[2] or '').strip().lower() == 'system':
            rep.append('INFO: %s: Life Cycle Mode System (%s): follows the system state' % (who, lcm[1]))
            continue
        lb = as51_enum(ins.get('Loop Behavior', {}))
        if lb is None:
            rep.append('WARN: %s: Loop Behavior not readable as an enum (%s): left as it is' % (who, as51_short(ins.get('Loop Behavior', {}))))
            continue
        if (lb[2] or '').strip().lower() == 'once':
            fd = as51_fixed_duration(S, em, scr, mod, who, seen, rep)
            if fd is None:
                continue
            if not fd:
                rep.append('INFO: %s: Loop Behavior already Once (%s), Loop Duration %s: unchanged' % (
                    who, lb[1], as51_short(ins.get('Loop Duration', {}))))
                continue
            set_input(S, em, scr, mod, ['Loop Duration'], f_float(loop_s))
            b_ld = as51_float(as51_inputs(S, em, scr, mod).get('Loop Duration', {}))
            ok = b_ld is not None and abs(b_ld - loop_s) < 1e-4
            rep.append('%s: %s: Loop Behavior already Once, Loop Duration Mode was not Fixed: Loop Duration -> %s' % (
                'PASS' if ok else 'FAIL', who, b_ld))
            n += 1
            continue
        path, once = as51_find_enum(S, em, scr, mod, 'Loop Behavior', 'Once', seen, rep)
        if once is None:
            continue
        set_input(S, em, scr, mod, ['Loop Behavior'], fx_enum(path, once))
        if as51_fixed_duration(S, em, scr, mod, who, seen, rep) is None:
            continue
        set_input(S, em, scr, mod, ['Loop Duration'], f_float(loop_s))
        back = as51_inputs(S, em, scr, mod)
        b_lb, b_ld = as51_enum(back.get('Loop Behavior', {})), as51_float(back.get('Loop Duration', {}))
        ok = b_lb is not None and (b_lb[2] or '').strip().lower() == 'once' and b_ld is not None and abs(b_ld - loop_s) < 1e-4
        rep.append('%s: %s: Loop Behavior %s (%s) -> %s (%s), Loop Duration %s -> %s' % (
            'PASS' if ok else 'FAIL', who, lb[2], lb[1], b_lb and b_lb[2], b_lb and b_lb[1],
            as51_short(ins.get('Loop Duration', {})), b_ld))
        n += 1
    return n


def as51_set_lifetimes(S, em, lo, hi, rep):
    """InitializeParticle lifetimes of one emitter: Min/Max in Random mode, the single Lifetime in Direct Set mode."""
    ip = as51_inputs(S, em, _AS51_PS, 'InitializeParticle')
    mode = as51_enum(ip.get('Lifetime Mode', {}))
    before = dict((k, as51_short(ip[k])) for k in ('Lifetime Min', 'Lifetime Max', 'Lifetime') if k in ip)
    if mode and 'direct' in (mode[2] or '').lower():
        set_input(S, em, _AS51_PS, 'InitializeParticle', ['Lifetime'], f_float(hi))
        b = as51_float(as51_inputs(S, em, _AS51_PS, 'InitializeParticle').get('Lifetime', {}))
        ok = b is not None and abs(b - hi) < 1e-4
        rep.append('%s: %s lifetime (Direct Set) %s -> %s' % ('PASS' if ok else 'FAIL', em, before, b))
        return ok
    fx_set(S, em, _AS51_PS, 'InitializeParticle', 'Lifetime Min', f_float(lo))
    fx_set(S, em, _AS51_PS, 'InitializeParticle', 'Lifetime Max', f_float(hi))
    back = as51_inputs(S, em, _AS51_PS, 'InitializeParticle')
    bmin, bmax = as51_float(back.get('Lifetime Min', {})), as51_float(back.get('Lifetime Max', {}))
    ok = bmin is not None and bmax is not None and abs(bmin - lo) < 1e-4 and abs(bmax - hi) < 1e-4
    rep.append('%s: %s lifetime (%s) %s -> Min %s Max %s' % ('PASS' if ok else 'FAIL', em, mode and mode[2], before, bmin, bmax))
    return ok


def as51_alpha_fade(S, em, rep, expr=AS51_FADE_EXPR):
    """Alpha 1 at age 0 -> 0 at age 1: ScaleColor's Scale Alpha (a curve in the Fountain template) becomes expr; the
    module is added when the emitter has none."""
    mods = fx_modules(S, em, _AS51_PU)
    mod = 'ScaleColor' if 'ScaleColor' in mods else next((m for m in mods if m.startswith('ScaleColor')), None)
    if mod is None:
        mod = fx_add_module(S, em, _AS51_PU, AS51_SCALE_COLOR)
        rep.append('INFO: %s: no ScaleColor module: added %s' % (em, mod))
    before = as51_short(as51_inputs(S, em, _AS51_PU, mod).get('Scale Alpha', {}))
    fx_set(S, em, _AS51_PU, mod, 'Scale Alpha', f_expr(expr))
    back = as51_inputs(S, em, _AS51_PU, mod).get('Scale Alpha', {})
    got = (back.get('value') or {}).get('hlslExpression') if as51_kind(back) == 'NiagaraExt_StackInputData_HlslExpression' else None
    ok = got is not None and got.strip() == expr.strip()
    rep.append('%s: %s/%s Scale Alpha %s -> %s' % ('PASS' if ok else 'FAIL', em, mod, before, got))
    return ok


def as51_close_editors(asset_path):
    """Closes every asset editor of this asset (toolset edits made while the system editor is open don't recompile it)."""
    try:
        a = unreal.load_asset(asset_path.split('.')[0])
        if a is not None:
            return unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(a)
    except Exception:  # noqa: BLE001
        pass
    return None


# ------------------------------------------------------------------------------------------------ background compile check
def _as5x_cc_parse(cs, si):
    errs = []
    for s in (cs or {}).get('scripts', []):
        for ev in s.get('compileEvents', []):
            if ev.get('severity') in ('Error', 'Warning'):
                errs.append('%s/%s %s: %s' % (s.get('emitterName'), s.get('scriptName'), ev.get('severity'), str(ev.get('message', ''))[:300]))
    iss = []
    for i in (si or {}).get('issues', []):
        if i.get('severity') in ('Error', 'Warning') and not i.get('bIsDismissed'):
            loc = i.get('location') or {}
            iss.append('%s %s/%s/%s: %s' % (i.get('severity'), loc.get('emitterName'), loc.get('scriptName'), loc.get('moduleName'),
                                            i.get('shortDescription')))
    ok = bool(cs) and not cs.get('bHasErrors') and not (si or {}).get('numErrors')
    return {'status': (cs or {}).get('aggregateStatus'), 'errors': (cs or {}).get('bHasErrors'), 'warnings': (cs or {}).get('bHasWarnings'),
            'events': errs, 'numIssueErrors': (si or {}).get('numErrors'), 'numIssueWarnings': (si or {}).get('numWarnings'),
            'issues': iss, 'ok': ok}


def _as5x_latent_value(res):
    if res is None or not res.get_editor_property('is_complete'):
        return None, False
    err = str(res.get_editor_property('error') or '')
    if err:
        return {'_error': err}, True
    d = json.loads(str(res.get_editor_property('value') or 'null'))
    return (d.get('returnValue', d) if isinstance(d, dict) else d), True


AS5X_SETTLE_S = 5.0


def as5x_bg_compile(systems, out_name, label):
    """Background compile check of Niagara systems (Slate post-tick callback, one system at a time): close its editors,
    open the system editor, wait 3 s, request GetSystemCompileState + GetStackIssues (latent), wait for both (60 s at
    most), then settle: wait AS5X_SETTLE_S, confirm the system is idle (a fresh GetSystemCompileState, bIsCompiling
    false; up to 6 tries), wait 2 s, close the editor (closing it right after the reads hung UE in
    WaitForCompilationComplete on 2026-11-25). Writes Saved/Airship/<out_name> when every system is done. A check
    already running for the same label is replaced. Returns at once."""
    reg = globals().setdefault('AS5X_BG_CC', {})
    old = reg.get(label)
    if old is not None and old.get('handle') is not None:
        try:
            unreal.unregister_slate_post_tick_callback(old['handle'])
        except Exception:  # noqa: BLE001
            pass
    st = {'queue': list(systems), 'cur': None, 'step': None, 't': 0.0, 'res': {}, 'out': os.path.join(AS_SAVED, out_name),
          'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'handle': None, 'done': False}
    reg[label] = st

    def write():
        os.makedirs(AS_SAVED, exist_ok=True)
        with open(st['out'], 'w') as f:
            json.dump({'label': label, 'started_utc': st['started_utc'], 'done': st['done'],
                       'all_ok': st['done'] and all(r.get('ok') for r in st['res'].values()), 'systems': st['res']}, f, indent=1, default=str)

    def tick(dt):
        try:
            now = time.time()
            if st['cur'] is None:
                if not st['queue']:
                    st['done'] = True
                    write()
                    unreal.unregister_slate_post_tick_callback(st['handle'])
                    st['handle'] = None
                    unreal.log('[as5x] compile check %s done -> %s' % (label, st['out']))
                    return
                st['cur'] = st['queue'].pop(0)
                as51_close_editors(st['cur'])
                app('OpenEditorForAsset', assetPath=st['cur'].split('.')[0])
                st['step'], st['t'] = 'opened', now
                return
            S = st['cur']
            if st['step'] == 'opened' and now - st['t'] >= 3.0:
                st['cs'] = unreal.ToolsetRegistry.execute_tool(AS_NS_TS, 'GetSystemCompileState', json.dumps({'system': sref(S)}))
                st['si'] = unreal.ToolsetRegistry.execute_tool(AS_NS_TS, 'GetStackIssues', json.dumps({'system': sref(S)}))
                st['step'], st['t'] = 'requested', now
                return
            if st['step'] == 'requested':
                cs, a = _as5x_latent_value(st['cs'])
                si, b = _as5x_latent_value(st['si'])
                if (a and b) or now - st['t'] > 60.0:
                    r = _as5x_cc_parse(cs if isinstance(cs, dict) else None, si if isinstance(si, dict) else None)
                    if not (a and b):
                        r['ok'], r['timeout'] = False, True
                    for x in (cs, si):
                        if isinstance(x, dict) and x.get('_error'):
                            r['ok'], r['tool_error'] = False, x['_error']
                    st['res'][S] = r
                    write()
                    # Do NOT close the editor yet. Closing a Niagara system editor right after the compile-state reads
                    # (2026-11-25, NS_AirshipMuzzle) hung the game thread for good inside FNiagaraSystemViewModel::
                    # NotifyPreClose -> UNiagaraSystem::WaitForCompilationComplete (a compile the reads/editor had
                    # just requested). Settle first: wait, confirm the system is idle, wait again, then close.
                    st['step'], st['t'], st['idle_tries'] = 'settle', now, 0
                return
            if st['step'] == 'settle' and now - st['t'] >= AS5X_SETTLE_S:
                st['idle'] = unreal.ToolsetRegistry.execute_tool(AS_NS_TS, 'GetSystemCompileState', json.dumps({'system': sref(S)}))
                st['step'], st['t'] = 'idlecheck', now
                return
            if st['step'] == 'idlecheck':
                v, done = _as5x_latent_value(st['idle'])
                if not done and now - st['t'] <= 60.0:
                    return
                busy = (not done) or (not isinstance(v, dict)) or bool(v.get('bIsCompiling')) or bool(v.get('_error'))
                st['idle_tries'] += 1
                if busy and st['idle_tries'] < 6:
                    st['step'], st['t'] = 'settle', now
                    return
                st['res'][S]['close_after_idle_checks'] = st['idle_tries']
                if busy:
                    st['res'][S]['editor_left_open'] = 'still compiling after %d idle checks' % st['idle_tries']
                    st['cur'] = None
                    write()
                    return
                st['step'], st['t'] = 'close_wait', now
                return
            if st['step'] == 'close_wait' and now - st['t'] >= 2.0:
                as51_close_editors(S)
                st['cur'] = None
                write()
        except Exception:  # noqa: BLE001
            st['res'][st.get('cur') or '?'] = {'ok': False, 'script_error': traceback.format_exc()[-800:]}
            st['cur'] = None
            write()

    write()
    st['handle'] = unreal.register_slate_post_tick_callback(tick)
    return st['out']


# ------------------------------------------------------------------------------------------------ main
def as51_main():
    R = {'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}}

    def o(line):
        tag = line.split(':', 1)[0]
        if tag in R['counts']:
            R['counts'][tag] += 1
        R['lines'].append(line)
        print(line)

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL: PIE is running: nothing changed')
        return R
    if not unreal.EditorAssetLibrary.does_asset_exist(AS51_SYSTEM.split('.')[0]):
        o('FAIL: %s missing (run as_06_muzzle.py + as_07_fix_muzzle_compile.py first)' % AS51_SYSTEM)
        return R
    as51_close_editors(AS51_SYSTEM)
    S = AS51_SYSTEM
    seen = {}
    R['probe_before'] = as51_probe(S, seen)
    as_dump('as_51_probe.json', R['probe_before'])
    o('INFO: probe -> Saved/Airship/as_51_probe.json; emitters %s' % list(R['probe_before']['emitters'].keys()))
    for em, d in R['probe_before']['emitters'].items():
        o('INFO: %-18s state %s: Life Cycle Mode %s | Loop Behavior %s | Loop Duration %s | lifetime %s' % (
            'system' if em == 'None' else em, d.get('state_module'), d.get('Life Cycle Mode'), d.get('Loop Behavior'),
            d.get('Loop Duration'), d.get('lifetime')))
        if isinstance(d.get('Loop Duration Mode'), dict):
            o('INFO: %-18s Loop Duration Mode %s' % ('system' if em == 'None' else em, d['Loop Duration Mode'].get('display')))
    o('INFO: enum identifiers as the toolset returns them: %s' % json.dumps(seen))
    if AS51_PUFFS not in R['probe_before']['emitters']:
        o('FAIL: no %s emitter in %s' % (AS51_PUFFS, S))
        return R
    rep = []
    n = as51_one_shot(S, rep, AS51_LOOP_S, seen)
    as51_set_lifetimes(S, AS51_PUFFS, AS51_PUFF_LIFE[0], AS51_PUFF_LIFE[1], rep)
    as51_alpha_fade(S, AS51_PUFFS, rep)
    for l in rep:
        o(l)
    o('INFO: %d life cycle stack(s) changed to Loop Once %.2f s' % (n, AS51_LOOP_S))
    R['probe_after'] = as51_probe(S, seen)
    ms = R['probe_after']['emitters'].get('Muzzle_Smoke', {}).get('lifetime')
    o('INFO: Muzzle_Smoke lifetime kept: %s' % ms)
    # read back: no emitter of its own life cycle still loops
    loops = []
    for em, d in R['probe_after']['emitters'].items():
        lcm = (d.get('Life Cycle Mode') or {}) if isinstance(d.get('Life Cycle Mode'), dict) else {}
        lb = (d.get('Loop Behavior') or {}) if isinstance(d.get('Loop Behavior'), dict) else {}
        ldm = (d.get('Loop Duration Mode') or {}) if isinstance(d.get('Loop Duration Mode'), dict) else {}
        if em != 'None' and (lcm.get('display') or '').lower() == 'system':
            continue
        if as51_never_ends(d):
            loops.append((em, lb.get('display'), ldm.get('display')))
    o('%s: read back: stacks still looping %s' % ('PASS' if not loops else 'FAIL', loops))
    pl = R['probe_after']['emitters'][AS51_PUFFS]
    o('INFO: %s after: lifetime %s, Scale Alpha %s' % (AS51_PUFFS, pl.get('lifetime'), pl.get('scale_alpha')))
    if R['counts']['FAIL']:
        o('WARN: %d FAIL: NOT saved (the edits stay in memory; fix and re-run, or reload the asset to drop them)' % R['counts']['FAIL'])
        return R
    for p, ok in save_paths([S.split('.')[0]]):
        o('%s: saved %s' % ('PASS' if ok else 'FAIL', p))
    out = as5x_bg_compile([S], 'as_51_compile.json', 'as51')
    o('INFO: compile check started in the background -> %s (done in about 5-20 s: "done": true, "all_ok")' % out)
    return R


if not globals().pop('AS51_LIB_ONLY', False):
    try:
        _as51_r = as51_main()
    except Exception:  # noqa: BLE001
        print('FAIL: as_51 crashed: %s' % traceback.format_exc())
        _as51_r = {'counts': {'FAIL': 1}}
    try:
        as_dump('as_51_muzzle_once.json', json.dumps(_as51_r, indent=1, default=str))
    except Exception as _e:  # noqa: BLE001
        print('WARN: report not written %r' % (_e,))
    print('RESULT: %s %s' % ('PASS' if not _as51_r['counts'].get('FAIL') else 'FAIL', _as51_r['counts']))
