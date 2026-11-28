# as_78_lobby_hud.py - round 2 PR B lobby (Docs/Airship/round2/SPEC_B_LOBBY.md 6.1, 8.2): sets BP_MyHUD's
# LobbyWidgetClass = WBP_Lobby3_C (AMyHUD adds it for local controllers; without it the lobby falls back to the match HUD's
# strip and the pause menu's START MATCH, 6.6), compiles and saves BP_MyHUD by its path (a copy of the .uasset from
# before the change goes to Saved/Match/backup/, outside Content, never committed). Then verifies, read-only:
#   classes    UMyLobbyWidget, UMyLobbyPlayerRow, WBP_Lobby3_C, WBP_LobbyPlayerRow3_C load
#   names      WBP_Lobby3 / WBP_LobbyPlayerRow3 have the BindWidgetOptional names of 6.3 (missing ones listed)
#   row class  WBP_Lobby3's PlayerRowClass is WBP_LobbyPlayerRow3_C
#   hud        BP_MyHUD's LobbyWidgetClass is WBP_Lobby3_C (after the save: the class default read back)
#   lists      UMainMenu3's option lists (C++ class default, what the lobby reads, RL9) vs WBP_MainMenu3's class default:
#              a WBP override is a WARN (the lobby would offer something else than the host menu)
#   settings   UMyMatchSettings' lobby defaults = Appendix L-A (a difference is a FAIL unless Config/DefaultGame.ini sets it)
#   widget     UMyLobbyWidget's class defaults: TimeLimitChoices {0, 5, 10, 15, 20, 30}, RefreshInterval 0.25,
#              StartConfirmSeconds 3, RulesSendDelay 0.75
# AS78_VERIFY_ONLY = True changes nothing (no BP_MyHUD edit). Never during PIE.
# Run (editor idle, after as_77): Docs/Airship/scripts/harness/inbox.sh 78 Docs/Airship/scripts/ue/as_78_lobby_hud.py 120
# Report: Saved/Match/as_78_verify.txt (and as_78_verify.json)
import json, os, shutil, time, traceback  # unreal = inbox namespace

A78_HUD = '/Game/Level/UI/BP_MyHUD'
A78_LOBBY = '/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_Lobby3'
A78_ROW = '/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_LobbyPlayerRow3'
A78_MAIN = '/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_MainMenu3'
A78_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Match')
A78_INI = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Config', 'DefaultGame.ini')
R78 = {'lines': [], 'counts': {}}

# Appendix L-A (C++ defaults, MyMatchSettings.h category Lobby) + the two existing ones the lobby reads
A78_APPENDIX_LA = {'bLobbyWhenHosting': True, 'bSeamlessTravel': True, 'LobbySpawn': 'Auto', 'LobbyGroundTraceDepth': 5000.0,
                   'LobbyGroundMinNormalZ': 0.7, 'LobbyZoneMargin': 1500.0, 'LobbyZoneHeight': 6000.0, 'LobbyZoneDepth': 2000.0,
                   'LobbyZoneGraceSeconds': 0.5, 'LobbyCountdownSeconds': 5.0, 'LobbyArrivalTimeout': 45.0, 'LobbyPathStartWait': 10.0,
                   'bLobbyRequireReady': False, 'bLobbyTeamSwitch': True, 'bLobbyRulesClearReady': True, 'bLobbyDamage': False,
                   'LobbyOnlyActorTag': 'LobbyOnly', 'bStartAboard': True, 'EndScreenSeconds': 20.0}
A78_WIDGET_DEFAULTS = {'TimeLimitChoices': [0, 5, 10, 15, 20, 30], 'RefreshInterval': 0.25, 'StartConfirmSeconds': 3.0, 'RulesSendDelay': 0.75}
A78_LOBBY_NAMES = ['LobbyPanel', 'CompactPanel', 'CompactText', 'CountdownText', 'CountdownHintText', 'MessageText', 'TitleText',
                   'JoinCodeText', 'CopyCodeButton', 'BlueHeaderText', 'BlueList', 'OrangeHeaderText', 'OrangeList', 'SwitchTeamButton',
                   'SwitchTeamText', 'RulesPanel', 'TeamModeComboBox', 'ShipLivesComboBox', 'SwarmComboBox', 'MaxPlayersComboBox',
                   'TimeLimitComboBox', 'FriendlyFireCheckBox', 'GrappleShipsCheckBox', 'LaneAssistCheckBox', 'RulesHintText',
                   'ReadyButton', 'ReadyText', 'StartButton', 'StartText', 'StartReasonText', 'CloseButton', 'MenuButton', 'LeaveButton']
A78_ROW_NAMES = ['PlayerNameText', 'StatusText', 'PingText', 'LocalHighlight', 'MoveButton', 'MoveText']


def o78(tag, msg):
    R78['counts'][tag] = R78['counts'].get(tag, 0) + 1
    R78['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def a78_cls(path):
    return unreal.load_class(None, path + '.' + path.split('/')[-1] + '_C')


def a78_name(x):
    try:
        return x.get_path_name()
    except Exception:  # noqa: BLE001
        return str(x)


def a78_ini_keys():
    keys = set()
    try:
        sec = None
        for l in open(A78_INI, errors='replace'):
            s = l.strip()
            if s.startswith('['):
                sec = s
                continue
            if sec == '[/Script/Aura.MyMatchSettings]' and '=' in s:
                keys.add(s.split('=', 1)[0].lstrip('+-.!').split('(')[0].split('[')[0])
    except Exception:  # noqa: BLE001
        pass
    return keys


def a78_same(a, b):
    if isinstance(b, bool):
        return bool(a) == b
    if isinstance(b, float):
        try:
            return abs(float(a) - b) <= 1e-4 * max(1.0, abs(b))
        except Exception:  # noqa: BLE001
            return False
    if isinstance(b, list):
        try:
            return [int(x) for x in a] == b
        except Exception:  # noqa: BLE001
            return False
    # an unreal enum prints '<MyLobbySpawn.AUTO: 0>' (PyWrapperEnum.cpp Str): compare its .name; names and FNames as
    # text, lower case without '_' (AUTO, Auto, EMyLobbySpawn::Auto)
    n = getattr(a, 'name', None)
    s = n if isinstance(n, str) else str(a)
    s = s.split('::')[-1].split('.')[-1].strip('<> ')
    s = s.split(':')[0] if ':' in s else s
    return s == b or s.replace('_', '').lower() == str(b).replace('_', '').lower()


def a78_names(path):
    """the widget names of a WBP's design-time tree (UMGToolSet GetWidgets), or None"""
    try:
        res = unreal.ToolsetRegistry.execute_tool('UMGToolSet.UMGToolSet', 'GetWidgets',
                                                  json.dumps({'widgetBlueprint': {'refPath': path + '.' + path.split('/')[-1]}}))
        v = json.loads(res.value) if res.value else {}
        v = v.get('returnValue', v)
        out = set()
        for wi in v.get('widgets', []):
            ref = wi.get('widget')
            ref = ref.get('refPath') if isinstance(ref, dict) else ref
            out.add(str(ref).split('.')[-1])
        return out
    except Exception:  # noqa: BLE001
        o78('WARN', 'GetWidgets %s failed: %s' % (path, traceback.format_exc().strip().splitlines()[-1]))
        return None


def a78_set_hud():
    lc = a78_cls(A78_LOBBY)
    bp = unreal.load_asset(A78_HUD)
    if bp is None or lc is None:
        o78('FAIL', 'BP_MyHUD (%s) or WBP_Lobby3_C (%s) not found: run as_77 first' % (bp is not None, lc is not None))
        return False
    cdo = unreal.get_default_object(bp.generated_class())
    try:
        cur = cdo.get_editor_property('LobbyWidgetClass')
    except Exception:  # noqa: BLE001
        o78('FAIL', 'BP_MyHUD has no LobbyWidgetClass: the PR B lobby C++ (AMyHUD) is not built into this editor')
        return False
    if cur is not None and a78_name(cur) == a78_name(lc):
        o78('INFO', 'BP_MyHUD LobbyWidgetClass is already %s: not changed' % a78_name(lc))
        return True
    src = unreal.SystemLibrary.get_system_path(bp)
    if src and os.path.exists(src):
        os.makedirs(os.path.join(A78_OUT, 'backup'), exist_ok=True)
        bk = os.path.join(A78_OUT, 'backup', 'BP_MyHUD_before_as78_%s.uasset' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        shutil.copyfile(src, bk)
        R78['backup'] = bk
        o78('INFO', 'backup %s' % bk)
    cdo.set_editor_property('LobbyWidgetClass', lc)
    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    except Exception:  # noqa: BLE001
        o78('WARN', 'compile_blueprint: %s' % traceback.format_exc().strip().splitlines()[-1])
    saved = unreal.EditorAssetLibrary.save_asset(A78_HUD, only_if_is_dirty=False)
    o78('PASS' if saved else 'FAIL', 'BP_MyHUD LobbyWidgetClass %s -> %s, saved %s' % (a78_name(cur), a78_name(lc), saved))
    return bool(saved)


def a78_verify():
    for p in ('/Script/Aura.MyLobbyWidget', '/Script/Aura.MyLobbyPlayerRow'):
        o78('PASS' if unreal.load_class(None, p) is not None else 'FAIL', '%s loads' % p)
    lc, rc = a78_cls(A78_LOBBY), a78_cls(A78_ROW)
    o78('PASS' if lc is not None else 'FAIL', 'WBP_Lobby3_C loads: %s' % (lc is not None))
    o78('PASS' if rc is not None else 'FAIL', 'WBP_LobbyPlayerRow3_C loads: %s' % (rc is not None))
    for path, names in ((A78_LOBBY, A78_LOBBY_NAMES), (A78_ROW, A78_ROW_NAMES)):
        have = a78_names(path)
        if have is None:
            continue
        miss = [n for n in names if n not in have]
        o78('PASS' if not miss else 'FAIL', '%s: %d of the %d names of 6.3; missing %s' % (path.split('/')[-1], len(names) - len(miss), len(names), miss))
    if lc is not None:
        try:
            cdo = unreal.get_default_object(lc)
            prc = cdo.get_editor_property('PlayerRowClass')
            o78('PASS' if prc is not None and rc is not None and a78_name(prc) == a78_name(rc) else 'FAIL',
                'WBP_Lobby3 PlayerRowClass = %s (want %s)' % (a78_name(prc), a78_name(rc)))
            for k, want in A78_WIDGET_DEFAULTS.items():
                v = cdo.get_editor_property(k)
                v = [int(x) for x in v] if isinstance(want, list) else v
                o78('PASS' if a78_same(v, want) else 'WARN', 'WBP_Lobby3 %s = %s (C++ default %s)' % (k, v, want))
        except Exception:  # noqa: BLE001
            o78('WARN', 'WBP_Lobby3 class defaults not readable: %s' % traceback.format_exc().strip().splitlines()[-1])
    hc = unreal.load_class(None, A78_HUD + '.BP_MyHUD_C')
    try:
        lw = unreal.get_default_object(hc).get_editor_property('LobbyWidgetClass') if hc else None
        o78('PASS' if lw is not None and lc is not None and a78_name(lw) == a78_name(lc) else 'FAIL',
            'BP_MyHUD LobbyWidgetClass = %s (want %s)' % (a78_name(lw), a78_name(lc)))
    except Exception:  # noqa: BLE001
        o78('FAIL', 'BP_MyHUD LobbyWidgetClass not readable: %s' % traceback.format_exc().strip().splitlines()[-1])
    # RL9: the lobby reads UMainMenu3's C++ class default; a value set only on WBP_MainMenu3 would not reach it
    try:
        cpp = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.MainMenu3'))
        mc = a78_cls(A78_MAIN)
        wbp = unreal.get_default_object(mc) if mc else None
        for n in ('RuleSets', 'DifficultyNames', 'MaxPlayerChoices', 'ShipLivesChoices'):
            a = [str(x) for x in cpp.get_editor_property(n)]
            b = [str(x) for x in wbp.get_editor_property(n)] if wbp else None
            o78('PASS' if b is None or a == b else 'WARN', 'UMainMenu3.%s C++ %s, WBP_MainMenu3 %s%s' % (
                n, a, b, '' if b is None or a == b else ': the WBP overrides it, the lobby offers the C++ list (RL9)'))
    except Exception:  # noqa: BLE001
        o78('WARN', 'UMainMenu3 lists not readable: %s' % traceback.format_exc().strip().splitlines()[-1])
    try:
        st = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.MyMatchSettings'))
        ini = a78_ini_keys()
        for k, want in A78_APPENDIX_LA.items():
            try:
                v = st.get_editor_property(k)
            except Exception:  # noqa: BLE001
                o78('FAIL', 'UMyMatchSettings.%s not found' % k)
                continue
            if a78_same(v, want):
                o78('PASS', 'UMyMatchSettings.%s = %s' % (k, v))
            else:
                o78('INFO' if k in ini else 'FAIL', 'UMyMatchSettings.%s = %s (Appendix L-A %s)%s' % (k, v, want, ', set in DefaultGame.ini' if k in ini else ''))
    except Exception:  # noqa: BLE001
        o78('FAIL', 'UMyMatchSettings not readable: %s' % traceback.format_exc().strip().splitlines()[-1])


def a78_main():
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        o78('FAIL', 'PIE is running: asset scripts freeze the game thread then; run it with the editor idle')
        return False
    ok = True
    if not globals().get('AS78_VERIFY_ONLY'):
        ok = a78_set_hud()
    a78_verify()
    return ok and not R78['counts'].get('FAIL')


try:
    os.makedirs(A78_OUT, exist_ok=True)
    _ok78 = a78_main()
except Exception:  # noqa: BLE001
    R78['error'] = traceback.format_exc()
    o78('FAIL', 'script error: %s' % R78['error'].strip().splitlines()[-1])
    _ok78 = False
with open(os.path.join(A78_OUT, 'as_78_verify.txt'), 'w') as _f:
    _f.write('\n'.join(R78['lines']) + '\ncounts %s\n' % R78['counts'])
with open(os.path.join(A78_OUT, 'as_78_verify.json'), 'w') as _f:
    json.dump(R78, _f, indent=1, default=str)
print('RESULT: %s %s' % ('OK' if _ok78 else 'FAIL', R78['counts']))
