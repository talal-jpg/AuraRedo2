# as_45a_mp_probe.py - short listen-server PIE probe for the multiplayer test (2026-11-22): which PIE worlds exist and their
# roles, the player controllers / pawns / ships / pilot components / Enhanced Input subsystems / widgets per world, the
# real frame rate under the fixed 30 fps game time. Starts PIE with the play settings as loaded from the ini (must be
# PIE_ListenServer, 2 players: harness/set_play_mode.sh listen), probes at 2 s and 6 s of game time, ends its own PIE at
# 8 s. Nothing is saved. Output: Saved/Airship/mp/probe.json + the inbox .out.
# Run (L_AirshipTest open, no PIE): inbox.sh 45a Docs/Airship/scripts/ue/as_45a_mp_probe.py 30; then inbox.sh 45s with
# a one-liner printing AS45A['log'] (or read probe.json).
import json, os, time  # unreal = inbox namespace

AS45A_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'mp')
os.makedirs(AS45A_OUT, exist_ok=True)
AS45A = {'log': [], 'probes': [], 'frames': 0, 'wall0': time.time(), 'done': False}


def _a45_tlget(obj, names):
    return json.loads(unreal.ToolsetLibrary.get_object_properties(obj, names))


def _a45_tlset(obj, values):
    return unreal.ToolsetLibrary.set_object_properties(obj, json.dumps(values))


def _a45_role(w):
    try:
        if unreal.SystemLibrary.is_standalone(w):
            return 'standalone'
        return 'server' if unreal.SystemLibrary.is_server(w) else 'client'
    except Exception as e:  # noqa: BLE001
        return '? %r' % e


def _a45_probe(label):
    P = {'label': label, 'wall': round(time.time() - AS45A['wall0'], 1), 'frames': AS45A['frames'], 'worlds': []}
    ship_cls = unreal.load_class(None, '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C')
    subs = list(unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem))
    for w in unreal.EditorLevelLibrary.get_pie_worlds(False):
        W = {'path': w.get_path_name(), 'role': _a45_role(w), 'time': round(unreal.GameplayStatics.get_time_seconds(w), 2)}
        try:
            W['net_mode'] = str(unreal.SystemLibrary.get_net_mode(w)) if hasattr(unreal.SystemLibrary, 'get_net_mode') else None
        except Exception as e:  # noqa: BLE001
            W['net_mode'] = repr(e)
        pcs = []
        for pc in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.PlayerController):
            d = {'name': pc.get_name(), 'local': bool(pc.is_local_controller())}
            p = pc.get_controlled_pawn()
            d['pawn'] = (p.get_name(), p.get_class().get_name(), [round(x) for x in (p.get_actor_location().x, p.get_actor_location().y, p.get_actor_location().z)]) if p else None
            try:
                cls = unreal.load_class(None, '/Script/Aura.AirshipPilotComponent')
                comp = pc.get_component_by_class(cls)
                d['pilot_comp'] = comp.get_name() if comp else None
                d['pilot_comp_methods'] = [m for m in ('request_board', 'request_exit', 'find_boardable_airship') if comp and hasattr(comp, m)]
            except Exception as e:  # noqa: BLE001
                d['pilot_comp'] = repr(e)
            pcs.append(d)
        W['pcs'] = pcs
        chars = []
        for c in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Character):
            l = c.get_actor_location()
            chars.append((c.get_name(), c.get_class().get_name(), str(c.get_local_role()), [round(l.x), round(l.y), round(l.z)],
                          bool(c.is_locally_controlled())))
        W['chars'] = chars
        ships = []
        for s in unreal.GameplayStatics.get_all_actors_of_class(w, ship_cls):
            l = s.get_actor_location()
            ships.append((s.get_name(), s.get_actor_label() if hasattr(s, 'get_actor_label') else None, str(s.get_local_role()),
                          [round(l.x), round(l.y), round(l.z)], bool(s.has_pilot())))
        W['ships'] = ships
        W['subsystems'] = []
        for sb in subs:
            try:
                lp = sb.get_outer()
                if lp.get_world() == w:
                    W['subsystems'].append((sb.get_name(), lp.get_name(), lp.get_class().get_name()))
            except Exception as e:  # noqa: BLE001
                W['subsystems'].append(repr(e))
        caps = [a.get_actor_label() for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.SceneCapture2D)]
        W['scene_captures'] = caps
        gm = unreal.GameplayStatics.get_game_mode(w)
        W['game_mode'] = gm.get_class().get_name() if gm else None
        ps = unreal.GameplayStatics.get_all_actors_of_class(w, unreal.PlayerStart)
        W['player_starts'] = [(a.get_name(), [round(a.get_actor_location().x), round(a.get_actor_location().y), round(a.get_actor_location().z)]) for a in ps]
        P['worlds'].append(W)
    wl = []
    for uw in unreal.ObjectIterator(unreal.UserWidget):
        try:
            pn = uw.get_path_name()
            if 'UEDPIE' not in pn and 'GameInstance' not in pn:
                continue
            if not uw.is_in_viewport():
                continue
            op = uw.get_owning_player()
            wl.append((uw.get_class().get_name(), op.get_name() if op else None, op.get_world().get_path_name() if op else None,
                       str(uw.get_visibility())))
        except Exception as e:  # noqa: BLE001
            wl.append(repr(e))
    P['viewport_widgets'] = wl
    acts = {}
    for n in ('IA_AirshipBoard', 'IA_AirshipFire', 'IA_AirshipThrottle', 'IA_AirshipSteer', 'IA_AirshipExit'):
        acts[n] = bool(unreal.load_asset('/Game/Assets/MyShip/Drivable/Input/' + n))
    acts['IA_LMB'] = bool(unreal.load_asset('/Game/Level/PlayerInput/IA_LMB'))
    P['actions'] = acts
    P['has_inject_vector'] = hasattr(unreal.EnhancedInputLocalPlayerSubsystem, 'inject_input_vector_for_action')
    P['has_make_value'] = hasattr(unreal, 'EnhancedInputLibrary') and hasattr(unreal.EnhancedInputLibrary, 'make_input_action_value_of_type')
    AS45A['probes'].append(P)
    AS45A['log'].append('probe %s done: %d worlds' % (label, len(P['worlds'])))
    with open(os.path.join(AS45A_OUT, 'probe.json'), 'w') as f:
        json.dump(AS45A, f, indent=1, default=str)


def _a45_tick(dt):
    try:
        if AS45A['done']:
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
        if not ws:
            if time.time() - AS45A['wall0'] > 150:
                AS45A['log'].append('no PIE world after 150 s')
                _a45_end()
            return
        AS45A['frames'] += 1
        if 'w0' not in AS45A:
            AS45A['w0'] = time.time()
            AS45A['log'].append('PIE worlds %s' % [w.get_path_name() for w in ws])
        t = min(unreal.GameplayStatics.get_time_seconds(w) for w in ws)
        AS45A['t'] = t
        if t >= 2.0 and 'p2' not in AS45A:
            AS45A['p2'] = (time.time(), AS45A['frames'])
            _a45_probe('t2')
        if t >= 6.0 and 'p6' not in AS45A:
            AS45A['p6'] = (time.time(), AS45A['frames'])
            fps = (AS45A['p6'][1] - AS45A['p2'][1]) / max(0.01, AS45A['p6'][0] - AS45A['p2'][0])
            AS45A['real_fps'] = round(fps, 2)
            AS45A['log'].append('real fps 2..6 s: %.2f' % fps)
            _a45_probe('t6')
        if t >= 8.0:
            _a45_end()
    except Exception as e:  # noqa: BLE001
        AS45A['log'].append('tick error %r' % e)
        AS45A['errors'] = AS45A.get('errors', 0) + 1
        if AS45A['errors'] > 50:
            _a45_end()


def _a45_end():
    AS45A['done'] = True
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        les.editor_request_end_play()
    try:
        unreal.unregister_slate_post_tick_callback(AS45A['handle'])
    except Exception:  # noqa: BLE001
        pass
    try:
        eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
        _a45_tlset(eng, AS45A['orig_engine'])
    except Exception as e:  # noqa: BLE001
        AS45A['log'].append('restore engine failed %r' % e)
    AS45A['log'].append('ended')
    with open(os.path.join(AS45A_OUT, 'probe.json'), 'w') as f:
        json.dump(AS45A, f, indent=1, default=str)


_les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if _les.is_in_play_in_editor():
    print('FAIL: PIE already running')
else:
    _ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
    AS45A['play_settings'] = _a45_tlget(_ps, ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
    print('play settings %s' % AS45A['play_settings'])
    _eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
    AS45A['orig_engine'] = _a45_tlget(_eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
    _a45_tlset(_eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': 30.0})
    try:
        _bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
        AS45A['burrower_enabled'] = bool(_bcdo.get_editor_property('bEnabled'))
        print('BurrowerSettings.bEnabled %s (left as is for the probe)' % AS45A['burrower_enabled'])
    except Exception as e:  # noqa: BLE001
        print('burrower settings: %r' % e)
    if 'ListenServer' not in str(AS45A['play_settings'].get('PlayNetMode')):
        print('FAIL: PlayNetMode is not listen server: not started')
        _a45_tlset(_eng, AS45A['orig_engine'])
    else:
        AS45A['handle'] = unreal.register_slate_post_tick_callback(_a45_tick)
        _les.editor_request_begin_play()
        print('PIE requested (listen server); probe at 2 s and 6 s game time, ends at 8 s')
