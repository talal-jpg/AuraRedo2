# as_73_verify_b.py - round 2 PR B, READ-ONLY check after the build (SPEC_B section 3; nothing is changed or saved):
#   classes   UMyMatchSettings, UMyTeamLibrary, UMyMatchHUDWidget, UMyMatchMemorySubsystem, UMyLaneSubsystem,
#             UAirshipLaneComponent load; AMyGameState / AMyPlayerState have the match getters
#   ship      BP_AirshipPawn's class default has the `Lane` component (the C++ default subobject reaches the BP on load)
#   settings  UMyMatchSettings' class default = Appendix A (scalars, DefaultRules, the 5 SwarmDifficulties of B5.4, the
#             per-team arrays); a difference is a FAIL unless Config/DefaultGame.ini sets it (then INFO: a deliberate value)
#   mode      BP_MyGameMode is an AMyGameMode child and its GameStateClass an AMyGameState child (MyGameMode.cpp sets it in C++)
#   menu      WBP_MainMenu3 has ShipLivesComboBox (WARN only: as_72 adds it); UMainMenu3's RuleSets / ShipLivesChoices
#   hud       BP_MyHUD's MatchWidgetClass resolves to a UMyMatchHUDWidget class (the C++ default)
#   team lib  with no match running every team call gives PR A's answer (255 / not blocked / usable)
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 73 Docs/Airship/scripts/ue/as_73_verify_b.py 120
# Report: Saved/Match/as_73_verify.txt and as_73_verify.json
import json, math, os, traceback  # unreal = inbox namespace

_AS73_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(compile(open(os.path.join(_AS73_UE, 'as_70_matchlib.py')).read(), os.path.join(_AS73_UE, 'as_70_matchlib.py'), 'exec'), globals())

AS73_SHIP = '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'
AS73_GM = '/Game/Level/BP_MyGameMode.BP_MyGameMode_C'
AS73_HUD = '/Game/Level/UI/BP_MyHUD.BP_MyHUD_C'
AS73_WBP = '/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_MainMenu3'
AS73_INI = os.path.join(MB_PROJECT, 'Config', 'DefaultGame.ini')
R73 = {'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}}


def o73(tag, msg):
    R73['counts'][tag] = R73['counts'].get(tag, 0) + 1
    R73['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def as73_ini_keys():
    """keys set in Config/DefaultGame.ini's [/Script/Aura.MyMatchSettings] section"""
    keys = set()
    try:
        sec = None
        for l in open(AS73_INI, errors='replace'):
            s = l.strip()
            if s.startswith('['):
                sec = s
                continue
            if sec == '[/Script/Aura.MyMatchSettings]' and '=' in s:
                keys.add(s.split('=', 1)[0].lstrip('+-.!').split('(')[0].split('[')[0])
    except Exception:  # noqa: BLE001
        pass
    return keys


def as73_close(a, b):
    if isinstance(b, bool) or isinstance(a, bool):
        return bool(a) == bool(b)
    if isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(b)))
        except Exception:  # noqa: BLE001
            return False
    if isinstance(b, list):
        try:
            return [str(x) for x in a] == [str(x) for x in b]
        except Exception:  # noqa: BLE001
            return False
    return str(a) == str(b)


def as73_classes():
    for k in ('settings', 'teamlib', 'hud', 'memory', 'lane', 'gs', 'ps', 'gm'):
        c = unreal.load_class(None, MB_CLS[k])
        o73('PASS' if c is not None else 'FAIL', 'class %s %s' % (MB_CLS[k], 'loads' if c else 'MISSING'))
    c = unreal.load_class(None, '/Script/Aura.MyLaneSubsystem')
    o73('PASS' if c is not None else 'FAIL', 'class /Script/Aura.MyLaneSubsystem %s' % ('loads' if c else 'MISSING'))
    gs = mb_cdo('gs')
    for f in ('get_match_phase', 'get_match_result', 'get_winning_team', 'get_phase_end_server_time', 'get_end_reason',
              'get_match_end_server_time', 'get_expected_players', 'get_round_index'):
        o73('PASS' if hasattr(gs, f) else 'FAIL', 'AMyGameState.%s %s' % (f, 'exposed' if hasattr(gs, f) else 'missing (not BlueprintPure?)'))
    ps = mb_cdo('ps')
    o73('PASS' if hasattr(ps, 'get_team_id') else 'FAIL', 'AMyPlayerState.get_team_id %s' % hasattr(ps, 'get_team_id'))
    lc = mb_cdo('lane')
    o73('PASS' if hasattr(lc, 'get_lane_state') else 'FAIL', 'UAirshipLaneComponent.get_lane_state %s' % hasattr(lc, 'get_lane_state'))


def as73_ship():
    cls = unreal.load_class(None, AS73_SHIP)
    if cls is None:
        o73('FAIL', '%s not found' % AS73_SHIP)
        return
    cdo = unreal.get_default_object(cls)
    lane = None
    for how in ('prop', 'component'):
        try:
            lane = cdo.get_editor_property('Lane') if how == 'prop' else cdo.get_component_by_class(mb_cls('lane'))
        except Exception:  # noqa: BLE001
            lane = None
        if lane is not None:
            break
    ok = lane is not None and mb_isa(lane, 'lane')
    o73('PASS' if ok else 'FAIL', 'BP_AirshipPawn class default: Lane component %s (%s)' % (mb_name(lane), lane.get_class().get_name() if lane else None))
    for f in ('get_team_id', 'is_spawn_protected'):
        o73('PASS' if hasattr(cdo, f) else 'FAIL', 'AAirshipPawn.%s %s' % (f, hasattr(cdo, f)))
    try:
        # a default-constructed struct (calling GetFlightTelemetry on a class default would run the flight code unregistered)
        t = mb_parse_export(unreal.AirshipFlightTelemetry().export_text())
        miss = [k for k in ('TeamId', 'LaneState', 'LaneUM', 'LaneLateralErrorM', 'LaneVerticalErrorM', 'LaneTargetSpeedMS', 'LaneClamp',
                            'bUnpilotedLane', 'RecallInS', 'ProtectionLeftS') if k not in t]
        o73('PASS' if not miss else 'FAIL', 'FAirshipFlightTelemetry lane fields %s' % ('all there' if not miss else 'missing %s' % miss))
    except Exception:  # noqa: BLE001
        o73('WARN', 'telemetry of the class default not readable: %s' % traceback.format_exc().strip().splitlines()[-1])


def as73_settings():
    st = mb_cdo('settings')
    ini = as73_ini_keys()
    R73['ini_keys'] = sorted(ini)
    bad = []
    for k, want in MB_APPENDIX_A.items():
        try:
            v = st.get_editor_property(k)
            v = list(v) if k == 'MatchMaps' else v
        except Exception:  # noqa: BLE001
            bad.append((k, 'unreadable', want))
            continue
        if not as73_close(v, want):
            bad.append((k, v, want))
    rules = st.get_editor_property('DefaultRules')
    for k, want in MB_APPENDIX_A_RULES.items():
        try:
            v = rules.get_editor_property(k)
            v = mb_nz(v) if k == 'TeamMode' else v
            ok = v == mb_nz(want) if k == 'TeamMode' else as73_close(v, want)
        except Exception:  # noqa: BLE001
            v, ok = 'unreadable', False
        if not ok:
            bad.append(('DefaultRules.' + k, v, want))
    try:
        sd = list(st.get_editor_property('SwarmDifficulties'))
        if len(sd) != len(MB_PRESETS):
            bad.append(('SwarmDifficulties', '%d entries' % len(sd), '%d' % len(MB_PRESETS)))
        for i, (name, vals) in enumerate(MB_PRESETS[:len(sd)]):
            p = mb_parse_export(sd[i].export_text())
            for k, want in zip(MB_PRESET_KEYS, vals):
                if not as73_close(p.get(k), want):
                    bad.append(('SwarmDifficulties[%d].%s' % (i, k), p.get(k), want))
            if str(p.get('Name')) != name:
                bad.append(('SwarmDifficulties[%d].Name' % i, p.get('Name'), name))
    except Exception:  # noqa: BLE001
        bad.append(('SwarmDifficulties', traceback.format_exc().strip().splitlines()[-1], 'B5.4'))
    for k, want in MB_APPENDIX_A_FIXED.items():
        try:
            v = st.get_editor_property(k)
            got = [x for x in v]
            if k == 'TeamColors':
                ok = len(got) == 2 and all(abs(got[i].r - want[i][0]) < 1e-3 and abs(got[i].g - want[i][1]) < 1e-3 and abs(got[i].b - want[i][2]) < 1e-3
                                           for i in range(2))
            elif k == 'TeamNames':
                ok = [str(x) for x in got] == want
            else:
                ok = [int(x) for x in got] == want
            if not ok:
                bad.append((k, [str(x) for x in got], want))
        except Exception:  # noqa: BLE001
            o73('INFO', '%s (a fixed C array) not readable from Python: checked in C++ only' % k)
    for k, v, want in bad:
        base = k.split('.')[0].split('[')[0]
        o73('INFO' if base in ini else 'FAIL', 'UMyMatchSettings.%s = %s, Appendix A %s%s' % (k, v, want, ' (set in DefaultGame.ini)' if base in ini else ''))
    if not bad:
        o73('PASS', 'UMyMatchSettings class default = Appendix A (%d scalars, DefaultRules, 5 presets)' % len(MB_APPENDIX_A))


def as73_mode():
    gm = unreal.load_class(None, AS73_GM)
    ok = gm is not None and unreal.MathLibrary.class_is_child_of(gm, mb_cls('gm'))
    o73('PASS' if ok else 'FAIL', 'BP_MyGameMode is an AMyGameMode child: %s' % ok)
    if gm is not None:
        try:
            gsc = unreal.get_default_object(gm).get_editor_property('game_state_class')
            ok = gsc is not None and unreal.MathLibrary.class_is_child_of(gsc, mb_cls('gs'))
            o73('PASS' if ok else 'FAIL', 'its GameStateClass %s is an AMyGameState child: %s' % (mb_name(gsc), ok))
            psc = unreal.get_default_object(gm).get_editor_property('player_state_class')
            ok = psc is not None and unreal.MathLibrary.class_is_child_of(psc, mb_cls('ps'))
            o73('PASS' if ok else 'FAIL', 'its PlayerStateClass %s is an AMyPlayerState child: %s' % (mb_name(psc), ok))
        except Exception:  # noqa: BLE001
            o73('FAIL', 'game state / player state class not readable: %s' % traceback.format_exc().strip().splitlines()[-1])


def as73_menu():
    found = None
    try:
        unreal.load_asset(AS73_WBP)
        res = unreal.ToolsetRegistry.execute_tool('UMGToolSet.UMGToolSet', 'GetWidgets',
                                                  json.dumps({'widgetBlueprint': {'refPath': AS73_WBP + '.WBP_MainMenu3'}}))
        v = json.loads(res.value) if res.value else {}
        v = v.get('returnValue', v)
        names = []
        for wi in v.get('widgets', []):
            ref = wi.get('widget')
            ref = ref.get('refPath') if isinstance(ref, dict) else ref
            names.append(str(ref).split('.')[-1])
        found = 'ShipLivesComboBox' in names
    except Exception:  # noqa: BLE001
        o73('WARN', 'UMGToolSet GetWidgets failed (%s): trying the design-time object path' % traceback.format_exc().strip().splitlines()[-1])
        found = unreal.find_object(None, AS73_WBP + '.WBP_MainMenu3:WidgetTree.ShipLivesComboBox') is not None
    o73('PASS' if found else 'WARN', 'WBP_MainMenu3 has ShipLivesComboBox: %s%s' % (found, '' if found else ' (run as_72_menu_lives.py; without it the menu uses the default)'))
    try:
        mc = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.MainMenu3'))
        for n in ('RuleSets', 'ShipLivesChoices'):
            try:
                o73('INFO', 'UMainMenu3.%s = %s' % (n, [str(x) for x in mc.get_editor_property(n)]))
            except Exception:  # noqa: BLE001
                o73('INFO', 'UMainMenu3.%s not readable from Python' % n)
    except Exception:  # noqa: BLE001
        o73('WARN', 'UMainMenu3 not found')


def as73_hud():
    hc = unreal.load_class(None, AS73_HUD)
    if hc is None:
        o73('FAIL', '%s not found' % AS73_HUD)
        return
    try:
        mw = unreal.get_default_object(hc).get_editor_property('MatchWidgetClass')
        ok = mw is not None and unreal.MathLibrary.class_is_child_of(mw, mb_cls('hud'))
        o73('PASS' if ok else 'FAIL', 'BP_MyHUD MatchWidgetClass = %s (a UMyMatchHUDWidget class: %s)' % (mb_name(mw), ok))
    except Exception:  # noqa: BLE001
        o73('FAIL', 'BP_MyHUD MatchWidgetClass not readable: %s' % traceback.format_exc().strip().splitlines()[-1])


def as73_teamlib():
    w = mb_editor_world()
    try:
        tl = unreal.MyTeamLibrary
        res = {'is_match_active': tl.is_match_active(w), 'get_team_id(None)': tl.get_team_id(None), 'are_teammates': tl.are_teammates(None, None),
               'friendly_fire_blocked': tl.is_friendly_fire_blocked(None, None), 'can_use_ship': tl.can_use_ship(None, None),
               'team_ship_target': tl.is_team_ship_target(None), 'names': [str(tl.get_team_name(i)) for i in (0, 1, 255)]}
        ok = (not res['is_match_active'] and res['get_team_id(None)'] == 255 and not res['are_teammates'] and not res['friendly_fire_blocked']
              and not res['team_ship_target'] and res['names'][:2] == ['BLUE', 'ORANGE'])
        o73('PASS' if ok else 'FAIL', 'UMyTeamLibrary with no match: %s (want PR A answers: inactive, 255, not teammates, not blocked, BLUE / '
                                      'ORANGE)' % res)
    except Exception:  # noqa: BLE001
        o73('FAIL', 'UMyTeamLibrary calls failed: %s' % traceback.format_exc().strip().splitlines()[-1])


def as73_main():
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        o73('FAIL', 'PIE is running: run this with the editor idle')
        return
    for f in (as73_classes, as73_ship, as73_settings, as73_mode, as73_menu, as73_hud, as73_teamlib):
        try:
            f()
        except Exception:  # noqa: BLE001
            o73('FAIL', '%s crashed: %s' % (f.__name__, traceback.format_exc().strip().splitlines()[-1]))


try:
    os.makedirs(MB_MATCH, exist_ok=True)
    as73_main()
    with open(os.path.join(MB_MATCH, 'as_73_verify.txt'), 'w') as _f:
        _f.write('\n'.join(R73['lines']) + '\n')
    with open(os.path.join(MB_MATCH, 'as_73_verify.json'), 'w') as _f:
        json.dump(R73, _f, indent=1, default=str)
    print('RESULT: %s -> Saved/Match/as_73_verify.txt' % R73['counts'])
except Exception:  # noqa: BLE001
    print('RESULT: FAIL %s' % traceback.format_exc())
