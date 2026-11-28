# as_79_lobbylib.py - shared lobby readers of the PR B lobby harnesses (Docs/Airship/round2/SPEC_B_LOBBY.md section 8):
# as_79_pie_lobby.py (standalone) and as_80_pie_lobby_mp.py (listen server). Not run on its own: each execs it into the
# editor inbox namespace AFTER as_70_matchlib (it uses MBRun's log tail, cmd, gs, player_states, ...).
#  * LobbyMix.lobby_status(w): `Aura.Lobby.Status` on that machine (MyLobbyConsole.cpp) parsed from the log: the game
#    state's lobby line, the server's spawn / ground / zones line, one line per player, one per local player (panel open,
#    IgnoreInput, mouse capture, cursor, pause menu)
#  * the lobby widget of a world (WBP_Lobby3 / any UMyLobbyWidget) and its named children (LobbyPanel's visibility = the
#    panel is open; StartButton / ReadyButton visibility = the host / client view)
#  * the game state's and the player states' lobby getters (BlueprintPure in MyGameState.h / MyPlayerState.h)
import re  # unreal = inbox namespace

LB_VERSION = 'as_79_lobbylib 2026-11-28c'
LB_WIDGET_CLASS = '/Script/Aura.MyLobbyWidget'
LB_PILOT_COMP = '/Script/Aura.AirshipPilotComponent'
LB_IMC_BOARD = '/Game/Assets/MyShip/Drivable/Input/IMC_AirshipBoard'
LB_BLOCKS = ['None', 'Arriving', 'Counting', 'Traveling', 'NeedOpponent', 'NotReady', 'NeedTwoPerTeam', 'Uneven', 'OneShip']
LB_HEAD_RE = re.compile(r'Lobby status \((client|server|standalone) ([^)]*)\): phase (\w+), in lobby (\d), counting (\d), countdown (-?[\d.]+) s, '
                        r'lobby round (\d), start block (\w+), not ready (\d+), rematch (\d), arriving (\d+), expected (\d+), teams (\d+) / (\d+), '
                        r'rules Teams=(\S+)')
LB_SERVER_RE = re.compile(r'LogMatch:\s+server: spawn (\w+) \(request (\w+)\), ground (.*), ground ready (\d), zones (\d+), bots (\d+), '
                          r'will return to the lobby (\d)')
LB_ZONE_RE = re.compile(r'LogMatch:\s+zone (\d+): min \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\) max \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\)')
LB_PLAYER_RE = re.compile(r'LogMatch:\s+player (\d+) (.*?): id (-?\d+), team (\d+), ready (\d), request (\d+), host (\d), arriving (\d), '
                          r'bot (\d), pawn (\S+)')
LB_LOCAL_RE = re.compile(r'LogMatch:\s+local (\d+) (\S+): panel (\d) \(widget (\d)\), IgnoreInput (\d), capture (-?\d+), cursor (\d), '
                         r'pause menu (\d)')


class LobbyMix(object):
    """mixed into the B74 / B75 based lobby harnesses"""

    # ------------------------------------------------------------------------------------------------- log waits
    def log_wait(self, t0, timeout, *pats):
        """yield: the kept log lines since t0 with every pattern, waiting up to timeout game s for the first one. The log
        tail reads the editor log FILE, which gets a C++ line a frame or more after it is logged: a check made in the frame
        the state changed finds no line yet (b79 run 2026-11-28: LB1.3, LB1.5_cancel, LB1.9 had their lines in the log)."""
        got = yield from self.until(lambda: self.log_since(t0, *pats), timeout)
        return got or []

    def event_wait(self, t0, name, timeout):
        """yield: the match events `name` since t0, waiting up to timeout game s for the first one (same log lag)"""
        got = yield from self.until(lambda: self.events_since(t0, name), timeout)
        return got or []

    # ------------------------------------------------------------------------------------------------- Aura.Lobby.Status
    def lobby_status(self, w, timeout=2.0):
        """yield: Aura.Lobby.Status on that machine, its lines from the log -> dict (None without the head line)"""
        t0 = self.now
        role = self.role(w)
        unreal.SystemLibrary.execute_console_command(w, 'Aura.Lobby.Status')
        t1 = self.now
        out = None
        while True:
            lines = [l for _, l in self.log_since(t0, 'LogMatch')]
            head = None
            for i, l in enumerate(lines):
                m = LB_HEAD_RE.search(l)
                if m and (m.group(1) == role or role == '?'):
                    head = i
            if head is not None:
                m = LB_HEAD_RE.search(lines[head])
                out = {'role': m.group(1), 'world': m.group(2), 'phase': mb_nz(m.group(3)), 'in_lobby': m.group(4) == '1',
                       'counting': m.group(5) == '1', 'countdown': float(m.group(6)), 'lobby_round': m.group(7) == '1',
                       'block': mb_nz(m.group(8)), 'not_ready': int(m.group(9)), 'rematch': m.group(10) == '1', 'arriving': int(m.group(11)),
                       'expected': int(m.group(12)), 'teams': [int(m.group(13)), int(m.group(14))], 'rules_teams': m.group(15),
                       'server': None, 'zones': [], 'players': [], 'local': []}
                for l in lines[head + 1:]:
                    if LB_HEAD_RE.search(l):
                        break
                    ms = LB_SERVER_RE.search(l)
                    if ms:
                        out['server'] = {'spawn': ms.group(1), 'request': ms.group(2), 'ground': ms.group(3), 'ground_ready': ms.group(4) == '1',
                                         'zones': int(ms.group(5)), 'bots': int(ms.group(6)), 'will_return': ms.group(7) == '1'}
                        continue
                    mz = LB_ZONE_RE.search(l)
                    if mz:
                        v = [float(x) for x in mz.groups()[1:]]
                        out['zones'].append((v[:3], v[3:]))
                        continue
                    mp = LB_PLAYER_RE.search(l)
                    if mp:
                        out['players'].append({'i': int(mp.group(1)), 'name': mp.group(2), 'id': int(mp.group(3)), 'team': int(mp.group(4)),
                                               'ready': mp.group(5) == '1', 'request': int(mp.group(6)), 'host': mp.group(7) == '1',
                                               'arriving': mp.group(8) == '1', 'bot': mp.group(9) == '1', 'pawn': mp.group(10)})
                        continue
                    ml = LB_LOCAL_RE.search(l)
                    if ml:
                        out['local'].append({'i': int(ml.group(1)), 'pc': ml.group(2), 'panel': ml.group(3) == '1', 'widget': ml.group(4) == '1',
                                             'ignore_input': ml.group(5) == '1', 'capture': int(ml.group(6)), 'cursor': ml.group(7) == '1',
                                             'pause_menu': ml.group(8) == '1'})
                # the local lines come last: wait for them (one per local player) unless the time is up
                if out['local'] or self.now - t1 >= timeout:
                    return out
            if self.now - t1 >= timeout:
                return out
            yield

    def zone_has(self, st, p, margin=0.0):
        """point p inside one of the status's zone boxes"""
        for lo, hi in (st or {}).get('zones') or []:
            if all(lo[i] - margin <= p[i] <= hi[i] + margin for i in range(3)):
                return True
        return False

    # ------------------------------------------------------------------------------------------------- the lobby widget
    def lobby_widget(self, w):
        """the lobby widget of world w (WBP_Lobby3 or any UMyLobbyWidget child); None without one"""
        base = unreal.load_class(None, LB_WIDGET_CLASS)
        best = None
        for o in unreal.ObjectIterator(unreal.UserWidget):
            try:
                if 'Default__' in o.get_name() or not mb_same(o.get_world(), w):
                    continue
                if base is not None and unreal.MathLibrary.class_is_child_of(o.get_class(), base):
                    best = o
                    if o.get_class().get_name() == 'WBP_Lobby3_C':
                        return o
            except Exception:  # noqa: BLE001
                continue
        return best

    def wchild(self, root, name):
        """a named widget of a user widget's tree (WidgetTree or WidgetTree_0)"""
        if root is None:
            return None
        for t in ('WidgetTree', 'WidgetTree_0'):
            try:
                o = unreal.find_object(None, '%s.%s.%s' % (root.get_path_name(), t, name))
                if o is not None:
                    return o
            except Exception:  # noqa: BLE001
                pass
        return None

    def wvis(self, widget):
        """'visible' / 'collapsed' / 'hidden' / 'hittestinvisible' / 'selfhittestinvisible' / None"""
        try:
            return mb_nz(widget.get_visibility()) if widget is not None else None
        except Exception:  # noqa: BLE001
            return None

    def wshown(self, widget):
        """shown on screen: the widget and every parent up to the tree's root (UMyLobbyWidget::SetButtonShown collapses a
        button's Item_ / Wrap_ parent, the button itself stays Visible)"""
        v = self.wvis(widget)
        if v is None or v in ('collapsed', 'hidden'):
            return False
        p = widget
        for _ in range(32):
            try:
                p = p.get_parent()
            except Exception:  # noqa: BLE001
                break
            if p is None:
                break
            pv = self.wvis(p)
            if pv in ('collapsed', 'hidden'):
                return False
        return True

    def wtext(self, widget):
        try:
            return str(widget.get_text()) if widget is not None else None
        except Exception:  # noqa: BLE001
            return None

    def panel_view(self, w):
        """what the lobby widget of world w shows: widget found, panel open, the host's START / the client's READY, texts"""
        lw = self.lobby_widget(w)
        if lw is None:
            return {'widget': False}
        v = {'widget': True, 'class': lw.get_class().get_name()}
        for n in ('LobbyPanel', 'CompactPanel', 'CountdownText', 'StartButton', 'ReadyButton', 'SwitchTeamButton', 'MessageText',
                  'StartText', 'ReadyText', 'CopyCodeButton', 'JoinCodeText'):
            v[n] = self.wshown(self.wchild(lw, n))
        for n in ('StartText', 'StartReasonText', 'ReadyText', 'CompactText', 'CountdownText', 'BlueHeaderText', 'OrangeHeaderText'):
            v[n + '_text'] = self.wtext(self.wchild(lw, n))
        v['open'] = v.get('LobbyPanel')
        return v

    # ------------------------------------------------------------------------------------------------- state getters
    def lgs(self, w):
        """the game state's lobby getters on that machine"""
        try:
            g = self.gs(w)
            return {'phase': mb_nz(g.get_match_phase(), MB_PHASE), 'in_lobby': bool(g.is_in_lobby()), 'counting': bool(g.is_lobby_counting_down()),
                    'lobby_round': bool(g.is_lobby_round()), 'block': mb_nz(g.get_lobby_start_block(), LB_BLOCKS),
                    'not_ready': int(g.get_lobby_not_ready()), 'rematch': bool(g.is_lobby_rematch()), 'expected': int(g.get_expected_players()),
                    'round': int(g.get_round_index()), 'phase_end': float(g.get_phase_end_server_time())}
        except Exception:  # noqa: BLE001
            self.err('lgs')
            return {}

    def lps(self, ps):
        try:
            return {'name': ps.get_player_name(), 'id': mb_pid(ps), 'team': int(ps.get_team_id()), 'ready': bool(ps.is_lobby_ready()),
                    'request': int(ps.get_requested_team()), 'host': bool(ps.is_host())}
        except Exception:  # noqa: BLE001
            self.err('lps')
            return {}

    def lobby_players(self, w):
        return [self.lps(p) for p in self.player_states(w)]

    def team_ships(self, w):
        return [s for s in self.ships(w) if self.ship_team(s) in (0, 1)]

    def spawners_stopped(self, w):
        out = []
        try:
            for sp in unreal.GameplayStatics.get_all_actors_of_class(w, mb_cls('waves')):
                try:
                    out.append((sp.get_name(), bool(sp.is_stopped()), int(sp.get_alive_count()), int(sp.get_current_wave_number())))
                except Exception:  # noqa: BLE001
                    out.append((sp.get_name(), None, None, None))
        except Exception:  # noqa: BLE001
            self.err('spawners_stopped')
        return out

    def sentinels_alive(self, w):
        """UMechSentinelSwarmSubsystem::GetNumAliveSentinels (authority only), else the spawners' alive counts"""
        try:
            sub = unreal.SubsystemBlueprintLibrary.get_world_subsystem(w, mb_cls('swarm'))
            if sub is not None:
                return int(sub.get_num_alive_sentinels())
        except Exception:  # noqa: BLE001
            pass
        sp = self.spawners_stopped(w)
        return sum(x[2] or 0 for x in sp) if sp else None

    def has_pilot_component(self, pc):
        try:
            cls = unreal.load_class(None, LB_PILOT_COMP)
            return bool(pc.get_components_by_class(cls))
        except Exception:  # noqa: BLE001
            return None

    def has_board_mapping(self, w):
        """the local player's Enhanced Input subsystem maps IMC_AirshipBoard (5.4 row 10)"""
        try:
            imc = unreal.load_asset(LB_IMC_BOARD)
            sub = self.subsystem(w)
            if sub is None or imc is None:
                return None
            # HasMappingContext(Context, OutFoundPriority) returns a bool with an out parameter: UE Python gives None when
            # the C++ returns false and the out value (the priority) when it returns true (PyGenUtil.cpp:2669-2674). The
            # board context's priority is 0 (UAirshipSettings::BoardMappingPriority), so bool() of the result read a mapped
            # context as False (as_80 LM1.13, 2026-11-28).
            return sub.has_mapping_context(imc) is not None
        except Exception:  # noqa: BLE001
            return None

    def effects_with_duration(self, c):
        """active gameplay effects with a duration on the character's ASC (player state owned): count, or None"""
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(c)
            if asc is None:
                return None
            hs = asc.get_active_effects(unreal.GameplayEffectQuery())
            n = 0
            for h in hs:
                du = None
                try:
                    res = unreal.AbilitySystemLibrary.get_active_gameplay_effect_remaining_and_total_time(h)
                    du = res[1] if isinstance(res, tuple) else None
                except Exception:  # noqa: BLE001
                    try:
                        du = unreal.AbilitySystemLibrary.get_active_gameplay_effect_total_duration(h)
                    except Exception:  # noqa: BLE001
                        du = None
                if du is not None and float(du) > 0.0:
                    n += 1
            return n
        except Exception:  # noqa: BLE001
            self.err('effects_with_duration')
            return None

    def attr(self, a, name):
        """a MyAttributeSet value of the actor's ASC (MBRun.health's method)"""
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            if asc is None:
                return None
            at = unreal.GameplayAttribute()
            at.import_text('(AttributeName="%s",Attribute=/Script/Aura.MyAttributeSet:%s,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")' % (name, name))
            x = asc.get_gameplay_attribute_value(at)
            return round(float(x[0] if isinstance(x, tuple) else x), 3)
        except Exception:  # noqa: BLE001
            self.err('attr_' + name)
            return None

    def mana(self, a):
        return self.attr(a, 'Mana')

    # ------------------------------------------------------------------------------------------------- tracks
    def drops(self, track):
        return [round(track[i][1] - track[i + 1][1], 3) for i in range(len(track) - 1)
                if track[i][1] is not None and track[i + 1][1] is not None and track[i + 1][1] < track[i][1]]

    def watch_health(self, fn, seconds, pre=None):
        """yield: sample fn() (a health) every frame for seconds; pre() runs each frame first. Returns the change track."""
        tr = []
        t0 = self.now
        while self.now - t0 < seconds:
            if pre is not None:
                pre()
            h = fn()
            if not tr or tr[-1][1] != h:
                tr.append((r(self.now - t0, 3), h))
            yield
        return tr
