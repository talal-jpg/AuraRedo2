# as_80_pie_lobby_mp.py - round 2 PR B lobby PIE harness, LISTEN-SERVER run of the lean test plan (Docs/Airship/round2/
# SPEC_B_LOBBY.md 8.4, LM1.1 .. LM1.13, plus the match checks the lead asked for: friendly fire with "a player shoots his own
# team's ship -> no damage", ship lives, the match end back to the lobby with the teams kept). ONE PIE session, 2 players
# (the host + one client, one process), StartupMap, the lobby forced by Aura.Lobby.Enable 1, fixed 30 fps game time.
# Built on as_75's B75 (listen PIE arm, worlds and players, a client acting only through its own machine: Enhanced Input
# injected into the client's subsystem, its own control rotation; ServerTravel world swaps) and as_70_matchlib.MBRun; the
# lobby readers are in as_79_lobbylib.py. Late joiners: the client's own world runs `open 127.0.0.1:<ServerPort>` (the PIE
# server's port, LevelEditorPlaySettings ServerPort, default 17777): the same server path as a late join (PreLogin, Login,
# PostLogin), tested in the lobby, the lobby countdown, InProgress and Ended. The seamless smoke test runs last (RL14).
# The play mode is set by the runner with the editor CLOSED: Docs/Airship/scripts/harness/set_play_mode.sh listen 2.
# Run (StartupMap open, no PIE, the PR B lobby C++ built, as_77 + as_78 done, `free -g` >= 6 GB available):
#   Docs/Airship/scripts/harness/inbox.sh 80 Docs/Airship/scripts/ue/as_80_pie_lobby_mp.py 60
#   status: inbox.sh 80s Docs/Airship/scripts/ue/as_80s_status.py 60     stop: inbox.sh 80x Docs/Airship/scripts/ue/as_80x_stop.py 60
# Knobs (inbox globals, read at arm): AS80_ONLY = () test-name prefixes (LM1.1 always runs); AS80_SEAMLESS = True (False
# skips LM1.13, the PIE seamless travel that can take the editor down).
# Results: Saved/Match/b80/ (b80_result.json, b80_report.txt, b80_log.txt, b80_status.txt, dump/).
# In memory only, restored at the end: fixed frame rate 30, the UMyMatchSettings / UAirshipSettings / UBurrowerSettings class
# defaults (Burrowers off), the CVars Aura.Match.Enable, Aura.Lobby.Enable, net.AllowPIESeamlessTravel, Aura.Lane.Debug,
# p.NetShowCorrections. TEMP_AS80_* in the editor level (B75's parked fireball, a SceneCapture2D) are removed after PIE.
#
# Tests (in this order; game-second budgets in scenario()):
#  LM1.1  both in phase Lobby with pawns in the lobby zone within 3 s, >= 2 m apart; teams 0 / 1; the client's teams, ready
#         flags and host flags = the server's within 0.5 s; a lobby widget on both, the panel open by itself on both; the
#         host sees START (not READY), the client READY (not START), each button's label shown or hidden with it (every
#         parent's visibility counts)
#  LM1.2  the client 100 m out of the zone (server copy and his own): back within 1.0 s; the zone message in the client's log
#  LM1.3  the host's gun on the client in the lobby: >= 1 server hit on him ("HitActor: <pawn>" log line), Health unchanged
#         (damage off)
#  LM1.4  bots: Bots 1 -> {2, 1}; Team 0 1 moves the host at once ({1, 2}); Bots 2 -> {2, 2}; the client asks for 0 ->
#         pending (RequestedTeam 0 on the client); the team 0 bot asks for 1: both swap, requests cleared; Teams=2v2
#         rebalances in join order (host, bot 1 on 0; client, bot 2 on 1); Move <client> 0 swaps him with bot 1 (the last
#         to join team 0); Teams=auto, Bots 0
#  LM1.5  Bots 1: Teams=1v1 refused (room for 2); Bots 0; the client ready; Teams=2v2 ShipLives=5 Swarm=3: the client's
#         rules equal (his Aura.Match.Status) and his ready flag cleared (team mode changed), Max Players 4; ready again,
#         ShipLives=3 alone: the flag stays
#  LM1.6  Teams=auto ShipLives=2; Start strict refused (NotReady); the client ready; Start strict: the countdown. At its start
#         both panels closed, IgnoreInput 0 and cursor 0 on both machines (the client's injected IA_Move distance is data
#         only: injection bypasses IgnoreInput); at 0 both on their own ship's deck within 1 s, teams as in the lobby
#  LMF    friendly fire (rules FF off), the ships past their spawn protection and held (Aura.Airship.Input 0 0): the host's gun
#         on his own team's ship and the client's gun on his own team's ship do NO damage; each one's gun on the other team's
#         ship does ShipDamageGunHit per hit; on foot on one platform, the host's gun on the client (enemies) does the GE value;
#         with the client moved to team 0 (teammates) none. Data: what each crosshair hit first
#  LM1.7  rejoin InProgress: the client's world opens 127.0.0.1:<port>; back within 10 s, on team 1, aboard team 1's ship
#  LMS    ship lives: Aura.Match.KillShip 1: lives 2 -> 1, ShipDestroyed, a new team 1 ship 10 +-0.5 s later; KillShip 1
#         again: TeamEliminated, Ended, TeamWon 0 on both machines
#  LM1.8  EndScreenSeconds 3: the hard ServerTravel (PIE) with Lobby=1 Round=1; both in phase Lobby; teams as before; the
#         rules kept (Teams=auto ShipLives=2); ready flags false; bLobbyRematch logged
#  LM1.9  rejoin in the lobby: a balanced team, ready false, a pawn in the zone
#  LM1.10 rejoin during the lobby countdown: no pawn until 0, then aboard with the host (both teams active at 0)
#  LM1.11 rejoin in Ended (EndScreenSeconds 12): a pawn; then carried back to the lobby by the return
#  LM1.12 Teams=1v1, Start, the client `disconnect`s at 2 s: cancelled within 0.5 s (LobbyCancelled, NeedOpponent), phase
#         Lobby, no team ship left; then the client opens the address again from his menu world
#  LM1.13 seamless smoke test, last: net.AllowPIESeamlessTravel 1; start, End 0, the return: "SeamlessTravel" in the log;
#         both in phase Lobby; the client's controller a new object with an AirshipPilotComponent and IMC_AirshipBoard still
#         mapped; teams kept; within 5 s the client's AMyHexPlatform and AAirshipPawn counts = the server's; no "not cleaned
#         up by garbage collection"; "Match: seamless arrival, N carried" with N >= 1 and 0 still arriving after 5 s
#         (Aura.Lobby.Status); a third start puts both aboard
# Deviations from SPEC_B_LOBBY 8.4 (for the lead's spec update):
#  * LMF and LMS are new (the lead's lean plan: friendly fire with own-ship hits, ship lives, the end back to the lobby).
#  * LM1.3's lobby gun test and LMF's player hits read the target's Health; a gun that never fires would also show no drop,
#    so LMF's enemy hits (which must drop) are the positive control of the same aim / fire path, and LM1.3 also needs the
#    server's "HitActor: <client pawn>" lines (GA_GunShoot's PrintString) in its window.
#  * LM1.5 reads the client's rules from his own Aura.Match.Status line (GetMatchRules is not BlueprintPure).
#  * LM1.11 uses EndScreenSeconds 12 so the rejoin completes before the return.
#  * LM1.13: "the overlay widget exists" and "the ASC has its startup abilities" are logged as data, not checked.
import json, math, os, re, time, traceback  # unreal = inbox namespace

_AS80_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
_as80_src75 = open(os.path.join(_AS80_UE, 'as_75_pie_match_mp.py')).read()
# B75 and its helpers (as_75 also execs as_70_matchlib); not as_75's own arming code at its end
exec(compile(_as80_src75[:_as80_src75.index('\n_old75 = ')], os.path.join(_AS80_UE, 'as_75_pie_match_mp.py'), 'exec'), globals())
exec(compile(open(os.path.join(_AS80_UE, 'as_79_lobbylib.py')).read(), os.path.join(_AS80_UE, 'as_79_lobbylib.py'), 'exec'), globals())
# the engine's travel lines too (log_poll reads this global)
MB_LOG_KEEP = tuple(MB_LOG_KEEP) + ('SeamlessTravel', 'ProcessServerTravel', 'not cleaned up by garbage collection', 'LogGameMode', 'Browse:')
# the server's gun hits on characters: UGA_GunShoot::MyFunc prints "HitActor: <target>" (PrintString, also to the log) once
# the target passed the friendly-fire and ship filters, before the damage-off attribute set (LM1.3's positive control)
MB_LOG_KEEP = tuple(MB_LOG_KEEP) + ('HitActor: ',)

AS80_VERSION = 'as_80_pie_lobby_mp 2026-11-28g'
AS80_RULES_RE = re.compile(r'Teams=(\S+) ShipLives=(\d+) Swarm=(\d+) TimeLimit=(\d+) FF=(\d) GrappleShips=(\d) LaneAssist=(\d)')


class B80(LobbyMix, B75):
    TAG = 'b80'
    VERSION = AS80_VERSION
    TEMP = 'TEMP_AS80_'
    SKIPPED = {'LM.host_crash': 'the host crashing: manual (SPEC_B_LOBBY 8.5)',
               'LM.steam_seamless': 'the real test of the seamless return is two packaged Steam machines (8.5, RL4): PIE uses the IP driver',
               'LM.menu_end_to_end': 'MM_MainMenu -> Host -> the lobby panel, the host edits rules in the panel, LEAVE: manual (8.5)'}

    def __init__(self):
        g = globals()
        self.cfg_in = {'players': 2, 'scenarios': ('lobby',), 'only': tuple(g.get('AS80_ONLY') or ()), 'scheme': 3,
                       'seamless': bool(g.get('AS80_SEAMLESS', True))}
        self.OUTDIR = os.path.join(MB_MATCH, 'b80')
        MBRun.__init__(self)
        self.cfg.update(self.cfg_in)
        self.R['cfg'] = self.cfg
        self.R['lobbylib'] = LB_VERSION
        self.sw = None
        self.cws = []
        self.P = []
        self.si = -1
        self.scen = None
        self.scen_wall = 0.0
        self.ptl = []
        self.gun_base = 1.0
        self.refused_seen = False
        self.port = 17777
        self.lobby_teams = {}

    # ------------------------------------------------------------------------------------------------- scenario
    def scenario(self, name):
        t = [('LM1.1_lobby', 40, self.t_lobby), ('LM1.2_zone', 15, self.t_zone), ('LM1.3_no_damage', 20, self.t_no_damage),
             ('LM1.4_teams', 45, self.t_teams), ('LM1.5_rules', 30, self.t_rules), ('LM1.6_start', 35, self.t_start),
             ('LMF_friendly_fire', 110, self.t_friendly_fire), ('LM1.7_rejoin_match', 45, self.t_rejoin_match),
             ('LMS_ship_lives', 50, self.t_ship_lives), ('LM1.8_return', 60, self.t_return), ('LM1.9_rejoin_lobby', 35, self.t_rejoin_lobby),
             ('LM1.10_rejoin_countdown', 40, self.t_rejoin_countdown), ('LM1.11_rejoin_ended', 70, self.t_rejoin_ended),
             ('LM1.12_cancel_disconnect', 60, self.t_cancel_disconnect)]
        if self.cfg.get('seamless'):
            t.append(('LM1.13_seamless', 120, self.t_seamless))
        return {'DefaultExpectedPlayers': 2}, t

    def snapshot_settings(self):
        MBRun.snapshot_settings(self)
        for n in ('Aura.Lobby.Enable', 'net.AllowPIESeamlessTravel', 'core.EnsureAlwaysEnabled'):
            self.orig['cvars'][n] = mb_cvar_int(n)
        if self.orig['cvars'].get('Aura.Lobby.Enable') is None:
            self.orig['cvars']['Aura.Lobby.Enable'] = -1
        if self.orig['cvars'].get('net.AllowPIESeamlessTravel') is None:
            self.orig['cvars']['net.AllowPIESeamlessTravel'] = 0
        if self.orig['cvars'].get('core.EnsureAlwaysEnabled') is None:
            self.orig['cvars']['core.EnsureAlwaysEnabled'] = 1

    def apply_scenario_settings(self, sets):
        B75.apply_scenario_settings(self, sets)
        mb_editor_cmd('Aura.Lobby.Enable 1')
        mb_editor_cmd('net.AllowPIESeamlessTravel 0')
        # The engine's PIE-only ensureAlways in FNetGUIDCache::SupportsObject (PackageMapClient.cpp:3145) fires on every
        # client move while the client's old world waits for the hard travel (its net driver is gone, InstanceID -1). Its
        # callstack dump took PIE to 3 fps, the server's ServerTravelPause to 2 min, and the client never got back in
        # (b80 2026-11-28, LM1.8 to LM1.11). Reported once, then silent; no check reads it.
        mb_editor_cmd('core.EnsureAlwaysEnabled 0')
        self.line('INFO', 'Aura.Lobby.Enable 1, net.AllowPIESeamlessTravel 0, core.EnsureAlwaysEnabled 0 for the run')

    def arm(self):
        try:
            ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
            v = tl_get(ps, ['ServerPort']).get('ServerPort')
            self.port = int(v) if v not in (None, '') else 17777
        except Exception:  # noqa: BLE001
            self.port = 17777
        self.R['setup']['server_port'] = self.port
        return B75.arm(self)

    # ------------------------------------------------------------------------------------------------- helpers
    def host(self):
        return self.P[0]

    def cl(self):
        return self.P[1]

    def aidx(self, p):
        """the player's index in the server's PlayerArray (Aura.Lobby.* PlayerIndex)"""
        ids = [mb_pid(x) for x in self.player_states(self.sw)]
        return ids.index(p['id']) if p['id'] in ids else p['i']

    def counts(self, st):
        return (st or {}).get('teams')

    def wt(self, w):
        try:
            return self.wtime(w)
        except Exception:  # noqa: BLE001
            return None

    def same_world(self, w, old, old_t):
        """w is still the old world: the same object, its clock not gone back. A new world can come back behind the old
        world's Python wrapper (same path, same address): its clock starts again at 0."""
        if not mb_same(w, old):
            return False
        t = self.wt(w) if old_t is not None else None
        return t is None or t >= old_t - 0.01

    def worlds_ok(self):
        """B75's test, plus the server world's clock: after the hard lobby ServerTravel the old server world's wrapper came
        back as the new UEDPIE_0 world, and B75 never saw the swap (b80 2026-11-28: LM1.8 waited 60 s for new worlds while
        the game time had gone back from 62 s to 1 s). While B75 handles a swap (_gone_wall) it stays false until B75 has
        mapped the new worlds and players."""
        if '_gone_wall' in self.D:
            return False
        if not B75.worlds_ok(self):
            self.D.pop('_sw_t', None)
            return False
        t = self.wt(self.sw)
        last = self.D.get('_sw_t')
        if t is not None and last is not None and t < last - 0.5:
            self.line('INFO', 'the server world\'s clock went back %.1f -> %.1f s: a new world behind the old wrapper (travel)' % (last, t))
            self.D.pop('_sw_t', None)
            return False
        if t is not None:
            self.D['_sw_t'] = t
        return True

    def remap(self, timeout=20.0, old_world=None, old_t=None):
        """yield: the worlds and players again (after a client's open / disconnect); the client's world must be a new one when
        old_world is given (old_t: its clock when it was left)"""
        def ok():
            if not self.find_worlds():
                return False
            if old_world is not None and any(self.same_world(w, old_world, old_t) for w in self.cws):
                return False
            return self.map_players()
        got = yield from self.until(ok, timeout)
        if got:
            self.subs = {}
            self.dump_cache = {}
        return bool(got)

    def rejoin(self, key, timeout=20.0):
        """yield: the client's own world opens the server's address; True once he is mapped again in a new world"""
        old = self.cl()['w']
        old_id = self.cl()['id']
        old_t = self.wt(old)
        t0 = self.now
        self.cmd(old, 'open 127.0.0.1:%d' % self.port)
        got = yield from self.remap(timeout, old_world=old, old_t=old_t)
        dt = (self.now - t0) if got else None
        self.event('rejoin', key=key, ok=got, dt=r(dt, 2), old_id=old_id, new_id=self.cl()['id'] if got else None)
        if not got:
            self.check(key, 'FAIL', 'the client did not come back within %.0f s of open 127.0.0.1:%d (worlds %s)' % (
                timeout, self.port, [(w.get_path_name(), self.role(w)) for w in self.pie_worlds(AS75_MAP)]))
        return dt

    def pc_count(self, w):
        """player controllers in that world (a seamless travel swaps each one for a new one: for a while both are there)"""
        try:
            return len(unreal.GameplayStatics.get_all_actors_of_class(w, unreal.PlayerController))
        except Exception:  # noqa: BLE001
            return None

    def player_imc(self, pc):
        """the controller's own IMC_PlayerInputMappingContext (AMyPlayerController2::SetupInputComponent always adds it)"""
        for n in ('IMC_PlayerInputMappingContext', 'imc_player_input_mapping_context'):
            try:
                v = pc.get_editor_property(n)
                if v is not None:
                    return v
            except Exception:  # noqa: BLE001
                pass
        return None

    def imc_probe(self, w, pc):
        """data for LM1.13: what the local Enhanced Input subsystem of world w has mapped: IMC_AirshipBoard and, as the
        positive control, the controller's IMC_PlayerInputMappingContext; the raw return; the controller's input components
        (the pilot component makes AirshipBoardInput right before it adds IMC_AirshipBoard)"""
        out = {'pc': pc.get_name() if pc is not None else None}
        try:
            sub = self.subsystem(w)
            out['sub_lp'] = sub.get_outer().get_name() if sub is not None else None
            for key, imc in (('board', unreal.load_asset(LB_IMC_BOARD)), ('player', self.player_imc(pc) if pc is not None else None)):
                if sub is None or imc is None:
                    out[key] = None
                    continue
                raw = sub.has_mapping_context(imc)
                # None when not mapped, else the priority (0 for both contexts): see LobbyMix.has_board_mapping
                out[key] = raw is not None
                out[key + '_raw'] = repr(raw)[:40]
            out['input_components'] = sorted(c.get_name() for c in pc.get_components_by_class(unreal.InputComponent)) if pc is not None else None
        except Exception as e:  # noqa: BLE001
            out['error'] = repr(e)[:200]
        return out

    def other_world(self):
        """a PIE world that is neither the server's nor a StartupMap client (a client sent to the menu by `disconnect`)"""
        try:
            for w in unreal.EditorLevelLibrary.get_pie_worlds(False):
                if mb_same(w, self.sw) or any(mb_same(w, c) for c in self.cws):
                    continue
                if AS75_MAP in w.get_path_name() and self.role(w) == 'client':
                    continue
                return w
        except Exception:  # noqa: BLE001
            self.err('other_world')
        return None

    def rules_of(self, w, timeout=1.5):
        """yield: that machine's rules from its Aura.Match.Status line -> dict"""
        t0 = self.now
        unreal.SystemLibrary.execute_console_command(w, 'Aura.Match.Status')
        t1 = self.now
        while True:
            for _, l in self.log_since(t0, 'LogMatch', 'Match: phase', 'Teams='):
                m = AS80_RULES_RE.search(l)
                if m:
                    return {'teams': mb_nz(m.group(1)), 'ship_lives': int(m.group(2)), 'swarm': int(m.group(3)), 'time_limit': int(m.group(4)),
                            'ff': m.group(5) == '1', 'hook': m.group(6) == '1', 'assist': m.group(7) == '1'}
            if self.now - t1 >= timeout:
                return None
            yield

    def views_equal(self):
        """the client's player states (id, team, ready, request, host) = the server's"""
        sv = sorted((x.get('id'), x.get('team'), x.get('ready'), x.get('request'), x.get('host')) for x in self.lobby_players(self.sw))
        cv = sorted((x.get('id'), x.get('team'), x.get('ready'), x.get('request'), x.get('host')) for x in self.lobby_players(self.cl()['w']))
        return sv == cv, sv, cv

    def in_zone_all(self, st):
        return [self.zone_has(st, self.loc(self.schar(p))) if self.schar(p) else None for p in self.P]

    def ensure_panels(self, open_=True):
        for p in self.P:
            self.cmd(p['w'], 'Aura.Lobby.Panel %d' % (1 if open_ else 0))

    def wait_phase(self, ph, timeout, w=None):
        return (yield from self.until(lambda: self.phase_of(w or self.sw) == ph, timeout))

    def ship_hp_track(self, ship, seconds, pre):
        return (yield from self.watch_health(lambda: self.ship_hp(ship) if valid(ship) else None, seconds, pre))

    def fire_at(self, p, target_fn, rec=None):
        """one frame: player p's own machine aims at target_fn() (server coordinates) and holds the gun. rec (a list): every
        6th frame the actor his crosshair sweep hits first (data)"""
        try:
            self.aim(p['w'], p['lpc'], target_fn())
            self.inject(p['w'], 'IA_LMB')
            if rec is not None and self.frames % 6 == 0:
                rec.append(self.aim_hit(p))
        except Exception:  # noqa: BLE001
            self.err('fire_at')

    def gun_hits(self, t0, target):
        """the server's GA_GunShoot hits on target (a server pawn) since t0: its "HitActor: <name>" log lines"""
        n = target.get_name() if target is not None else None
        if not n:
            return []
        return [l for _, l in self.log_since(t0, 'HitActor: ' + n) if re.search(r'HitActor: %s\s*$' % re.escape(n), l)]

    def settle_aim(self, p, target_fn, seconds=0.6):
        """yield: player p's view on target_fn() for seconds without firing (the camera lags the control rotation: the first
        shots of a window went where the last window looked, b80 2026-11-28)"""
        t0 = self.now
        while self.now - t0 < seconds:
            try:
                self.aim(p['w'], p['lpc'], target_fn())
            except Exception:  # noqa: BLE001
                self.err('settle_aim')
            yield

    def turret_hp(self, s):
        """data: the sum of a ship's living turrets' health (server)"""
        try:
            return r(sum(float(t.get_health()) for t in (s.get_editor_property('Turrets') or []) if valid(t)), 2)
        except Exception:  # noqa: BLE001
            return None

    def aim_hit(self, p):
        """data: what player p's crosshair hits first on his own machine, as AMyPlayerController2::Tick finds it (a 10 cm
        Visibility sphere from the view along its centre, his own pawn ignored) -> 'actor/component' or None"""
        try:
            w = p['w']
            pawn = self.schar(p) if mb_same(w, self.sw) else self.ochar(p)
            loc, rot = self.cam(w)
            f = rot.get_forward_vector()
            res = unreal.SystemLibrary.sphere_trace_single(w, loc + f * 10.0, loc + f * 2000000.0, 10.0, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                           True, [pawn] if pawn is not None else [], unreal.DrawDebugTrace.NONE, True)
            hit = res
            if isinstance(res, tuple):
                hit = next((x for x in res if isinstance(x, unreal.HitResult)), None)
            if hit is None:
                return None
            t = tuple(hit.to_tuple())
            if not [x for x in t if isinstance(x, bool)][:1] == [True]:
                return None
            act = next((x for x in t if isinstance(x, unreal.Actor)), None)
            comp = next((x for x in t if isinstance(x, unreal.PrimitiveComponent)), None)
            if act is None and comp is not None:
                act = comp.get_owner()
            name = mb_name(act)
            # a ship or turret by the team ship it is (or rides) nearest to: replicated actors have other names on a client
            cn = act.get_class().get_name() if act is not None else ''
            if 'AirshipPawn' in cn or 'AirshipTurret' in cn:
                q = self.loc(act)
                ships = [(t, self.ship(t)) for t in (0, 1) if self.ship(t) is not None]
                if ships:
                    t = min(ships, key=lambda x: dist(self.loc(x[1]), q))[0]
                    name = ('turret@ship%d' if 'Turret' in cn else 'ship%d') % t
            return '%s/%s' % (name, mb_name(comp))
        except Exception:  # noqa: BLE001
            self.err('aim_hit')
            return 'error'

    @staticmethod
    def hits_summary(rec):
        out = {}
        for h in rec:
            out[str(h)] = out.get(str(h), 0) + 1
        return out

    def stage_info(self, s0, s1):
        """data: where the LMF stage put everyone (server copies): hull-space positions on team 0's ship, movement bases,
        the ships' lane states and gap"""
        out = {}
        try:
            for k, p, s in (('host', self.host(), s0), ('client', self.cl(), s1)):
                c = self.schar(p)
                if c is not None and s is not None:
                    d = unreal.MathLibrary.inverse_transform_location(s.get_actor_transform(), unreal.Vector(*self.loc(c)))
                    out[k] = {'hull_own': r([d.x, d.y, d.z], 0), 'base': mb_name(self.base_owner(c)), 'on_own_deck': self.on_deck(c, s),
                              'alive': self.alive(c)}
            d = self.dump(self.sw, 'lmf_stage', 0.0)
            out['lanes'] = [(mb_get(d, 'ships', i, 'name'), mb_get(d, 'ships', i, 'lane_state'), mb_get(d, 'ships', i, 'speed_ms'))
                            for i in range(len(mb_get(d, 'ships') or []))]
            out['gap_m'] = r(dist(self.loc(s0), self.loc(s1)) / 100.0, 1) if s0 is not None and s1 is not None else None
        except Exception:  # noqa: BLE001
            self.err('stage_info')
        return out

    def put_on_deck(self, p, ship, hx, hy):
        """player p (on foot, both copies) onto ship's deck at hull-space (hx, hy)"""
        c = self.schar(p)
        if c is None or ship is None:
            return False
        if self.piloting(p):
            self.scmd('Aura.Airship.Exit %d' % p['i'])
        dp, _ = self.deck_point(ship, hx, hy, c)
        self.tp(p, dp, self.yaw(ship))
        return True

    # ================================================================================================= tests
    def t_lobby(self):
        """LM1.1"""
        host, cl = self.host(), self.cl()
        lob = yield from self.until(lambda: self.phase_of(self.sw) == 'lobby' and self.phase_of(cl['w']) == 'lobby', 5.0)
        t0 = self.now
        pawns = yield from self.until(lambda: all(self.alive(self.schar(p)) for p in self.P), 3.0)
        dt = (self.now - t0) if pawns else None
        st = yield from self.lobby_status(self.sw)
        zone = self.in_zone_all(st)
        locs = [self.loc(self.schar(p)) if self.schar(p) else None for p in self.P]
        gap = dist(locs[0], locs[1]) if all(locs) else None
        teams = [self.team(p) for p in self.P]
        eq = yield from self.until(lambda: self.views_equal()[0], 0.5)
        _, sv, cv = self.views_equal()
        ok = lob and pawns and all(zone) and gap is not None and gap >= 200.0 and teams == [0, 1] and eq
        self.check('LM1.1_lobby', self.ok(ok), 'both in phase Lobby %s; pawns %s s after (want <= 3), in the zone %s, %s cm apart (want >= 200); teams '
                   '%s (want 0, 1); the client\'s (id, team, ready, request, host) = the server\'s %s (server %s, client %s)' % (
                       bool(lob), r(dt, 2), zone, r(gap, 0), teams, bool(eq), sv, cv), {'status': st})
        self.lobby_teams = dict((p['id'], self.team(p)) for p in self.P)
        both = yield from self.until(lambda: all(self.panel_view(p['w']).get('open') for p in self.P), 3.0)
        hv, cv2 = self.panel_view(self.sw), self.panel_view(cl['w'])
        # shown = the widget and all its parents (the label and slab live beside the button in its Item_ overlay)
        ok = both and hv.get('widget') and cv2.get('widget') and hv.get('StartButton') and hv.get('StartText') and not hv.get('ReadyButton') \
            and not hv.get('ReadyText') and cv2.get('ReadyButton') and cv2.get('ReadyText') and not cv2.get('StartButton') and not cv2.get('StartText')
        self.check('LM1.1_panels', self.ok(ok), 'lobby widget host %s / client %s, open by itself on both %s; the host: START %s / label %s ("%s"), '
                   'READY %s / label %s; the client: READY %s / label %s ("%s"), START %s / label %s, reason "%s" (want the host START only, the '
                   'client READY only, labels with their buttons)' % (
                       hv.get('widget'), cv2.get('widget'), bool(both), hv.get('StartButton'), hv.get('StartText'), hv.get('StartText_text'),
                       hv.get('ReadyButton'), hv.get('ReadyText'), cv2.get('ReadyButton'), cv2.get('ReadyText'), cv2.get('ReadyText_text'),
                       cv2.get('StartButton'), cv2.get('StartText'), cv2.get('StartReasonText_text')), {'host': hv, 'client': cv2})

    def t_zone(self):
        """LM1.2"""
        cl = self.cl()
        st = yield from self.lobby_status(self.sw)
        c = self.schar(cl)
        if c is None:
            self.check('LM1.2_zone', 'FAIL', 'no client pawn')
            return
        p = self.loc(c)
        t0 = self.now
        self.tp(cl, [p[0] + 10000.0, p[1], p[2] + 200.0])
        back = yield from self.until(lambda: self.schar(cl) is not None and self.zone_has(st, self.loc(self.schar(cl))), 2.0)
        dt = (self.now - t0) if back else None
        yield from self.wait(0.5)
        msg = [l[-180:] for _, l in self.log_since(t0, 'Lobby message (client')]
        ok = dt is not None and dt <= 1.0 and msg
        self.check('LM1.2_zone', self.ok(ok), 'client 100 m out of the zone: back after %s s (want <= 1.0); the message on the client %s' % (r(dt, 2), msg[:1]))

    def t_no_damage(self):
        """LM1.3"""
        host, cl = self.host(), self.cl()
        hc = self.schar(host)
        if hc is None or self.schar(cl) is None:
            self.check('LM1.3_no_damage', 'FAIL', 'no pawns')
            return
        # the client 15 m in front of the host, on the lobby ground (inside the zone)
        p = self.loc(hc)
        yaw = math.radians(self.yaw(hc))
        q = [p[0] + 1500.0 * math.cos(yaw), p[1] + 1500.0 * math.sin(yaw), p[2] + 50.0]
        self.tp(cl, q)
        yield from self.wait(0.8)
        yield from self.settle_aim(host, lambda: self.loc(self.schar(cl)))
        h0 = self.health(self.schar(cl))
        t0 = self.now
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 1.5,
                                          lambda: self.fire_at(host, lambda: self.loc(self.schar(cl))))
        dr = self.drops(tr)
        # The positive control (review 2026-11-28): "no drop" alone passes when every shot misses. The server's hit lines on
        # the client's pawn (they reach the log file a frame or more later: the b79 log lag)
        yield from self.until(lambda: self.gun_hits(t0, self.schar(cl)), 1.0)
        hits = self.gun_hits(t0, self.schar(cl))
        self.check('LM1.3_no_damage', self.ok(h0 is not None and hits and not dr), 'the host\'s gun on the client in the lobby for 1.5 s: %d server hits '
                   'on him (want >= 1: "HitActor: %s"), Health %s, drops %s (want none: damage off in the lobby)' % (
                       len(hits), mb_name(self.schar(cl)), h0, dr))

    def t_teams(self):
        """LM1.4"""
        host, cl = self.host(), self.cl()
        res = {}

        def cnt():
            return (yield from self.lobby_status(self.sw))
        self.scmd('Aura.Lobby.Bots 1')
        yield from self.wait(0.6)
        st = yield from cnt()
        res['bots1'] = self.counts(st)
        self.scmd('Aura.Lobby.Team %d 1' % self.aidx(host))
        yield from self.wait(0.5)
        st = yield from cnt()
        res['host_to_1'] = (self.counts(st), self.team(host))
        self.scmd('Aura.Lobby.Bots 2')
        yield from self.wait(0.6)
        st = yield from cnt()
        res['bots2'] = self.counts(st)
        # teams full (2 / 2, the host and the client on 1): the client asks for 0 -> pending; a team 0 bot asks for 1 -> the swap
        cteam = self.team(cl)
        want = 1 - cteam if cteam in (0, 1) else 0
        self.scmd('Aura.Lobby.Team %d %d' % (self.aidx(cl), want))
        pend = yield from self.until(lambda: self.lps(cl['lpc'].get_editor_property('player_state')).get('request') == want, 0.5)
        res['client_pending'] = (bool(pend), want, self.team(cl))
        st = yield from cnt()
        bot = next((x for x in (st or {}).get('players', []) if x['bot'] and x['team'] == want), None)
        if bot is not None:
            self.scmd('Aura.Lobby.Team %d %d' % (bot['i'], cteam))
            yield from self.wait(0.6)
        st = yield from cnt()
        res['swap'] = (self.counts(st), self.team(cl), [(x['name'], x['team'], x['request']) for x in (st or {}).get('players', [])])
        ok_a = (res['bots1'] == [2, 1] and res['host_to_1'][0] == [1, 2] and res['host_to_1'][1] == 1 and res['bots2'] == [2, 2]
                and pend and res['swap'][1] == want and all(x[2] == 255 for x in res['swap'][2]) and res['swap'][0] == [2, 2])
        self.check('LM1.4_switch', self.ok(ok_a), 'Bots 1 -> %s (want 2 / 1); Team <host> 1 -> %s (want 1 / 2, host on 1); Bots 2 -> %s (want 2 / 2); '
                   'the client asks for %d: pending %s; the bot of team %d asks back: client on %s, requests %s, counts %s (want a swap, '
                   'requests cleared, 2 / 2)' % (res['bots1'], res['host_to_1'], res['bots2'], want, res['client_pending'], want,
                                                  res['swap'][1], [x[2] for x in res['swap'][2]], res['swap'][0]), res)
        # 2v2: every team again in join order
        self.scmd('Aura.Match.Rules Teams=2v2')
        yield from self.wait(0.6)
        st = yield from cnt()
        pl = (st or {}).get('players', [])
        res['rebalance'] = [(x['i'], x['name'], x['team']) for x in pl]
        jo = [x['team'] for x in sorted(pl, key=lambda x: x['i'])]
        ok_b = jo == [0, 1, 0, 1]
        # the host's MOVE into a full team: a swap with the last to join it (bot 1)
        self.scmd('Aura.Lobby.Move %d 0' % self.aidx(cl))
        yield from self.wait(0.6)
        st = yield from cnt()
        pl2 = (st or {}).get('players', [])
        res['move'] = [(x['i'], x['name'], x['team']) for x in pl2]
        b1 = next((x for x in sorted(pl2, key=lambda x: x['i']) if x['bot']), None)
        ok_c = self.team(cl) == 0 and self.counts(st) == [2, 2] and b1 is not None and b1['team'] == 1
        self.check('LM1.4_2v2', self.ok(ok_b and ok_c), 'Teams=2v2 rebalance (index, name, team) %s (want join order 0 1 0 1); Move <client> 0 into the '
                   'full team 0: %s (want the client on 0, bot 1 on 1, 2 / 2)' % (res['rebalance'], res['move']))
        self.scmd('Aura.Match.Rules Teams=auto')
        yield from self.wait(0.4)
        self.scmd('Aura.Lobby.Bots 0')
        yield from self.wait(0.6)
        st = yield from cnt()
        self.lobby_teams = dict((p['id'], self.team(p)) for p in self.P)
        self.line('INFO', 'after LM1.4: counts %s, teams %s' % (self.counts(st), self.lobby_teams))

    def t_rules(self):
        """LM1.5"""
        host, cl = self.host(), self.cl()
        t0 = self.now
        self.scmd('Aura.Lobby.Bots 1')
        yield from self.wait(0.6)
        self.scmd('Aura.Match.Rules Teams=1v1')
        yield from self.wait(0.4)
        refused = [l[-200:] for _, l in self.log_since(t0, 'Lobby: rules refused')]
        d = self.dump(self.sw, 'lm1_5a', 0.0)
        still = mb_nz(mb_get(d, 'rules', 'teams'))
        self.scmd('Aura.Lobby.Bots 0')
        yield from self.wait(0.6)
        self.scmd('Aura.Lobby.Ready %d 1' % self.aidx(cl))
        yield from self.until(lambda: self.lps(cl['pss']).get('ready'), 1.0)
        t1 = self.now
        self.scmd('Aura.Match.Rules Teams=2v2 ShipLives=5 Swarm=3')
        cr = None
        t2 = self.now
        while self.now - t2 < 1.5:
            cr = yield from self.rules_of(cl['w'])
            if cr and cr.get('teams') == '2v2' and cr.get('ship_lives') == 5 and cr.get('swarm') == 3:
                break
            yield
        dt = self.now - t1
        ready_after = self.lps(cl['lpc'].get_editor_property('player_state')).get('ready')
        g = self.lgs(self.sw)
        ok1 = refused and still == 'auto' and cr and cr.get('teams') == '2v2' and cr.get('ship_lives') == 5 and cr.get('swarm') == 3 \
            and not ready_after and g.get('expected') == 4
        self.check('LM1.5_rules', self.ok(ok1), 'with 3 players Teams=1v1: %s, rules still %s (want refused, auto); Teams=2v2 ShipLives=5 Swarm=3: the '
                   'client\'s rules %s after %.2f s (want 2v2 / 5 / 3 within 0.5 s), his ready flag %s (want false: team mode changed), Max Players %s '
                   '(want 4)' % (refused[:1], still, cr, dt, ready_after, g.get('expected')))
        self.scmd('Aura.Lobby.Ready %d 1' % self.aidx(cl))
        yield from self.until(lambda: self.lps(cl['pss']).get('ready'), 1.0)
        tu = self.now
        self.scmd('Aura.Match.Rules ShipLives=3')
        yield from self.wait(0.8)
        kept = self.lps(cl['lpc'].get_editor_property('player_state')).get('ready')
        upd = [l[-160:] for _, l in self.log_since(t1, 'Lobby: no session to advertise')] + [l[-160:] for _, l in self.log_since(t1, 'UpdateHostSettings')]
        self.check('LM1.5_ready_kept', self.ok(bool(kept)), 'ShipLives=3 alone: the client\'s ready flag %s (want true: only a team mode or Max Players '
                   'change clears it); session updates logged %d (PIE: "no session to advertise", one per request)' % (kept, len(upd)))

    def t_start(self):
        """LM1.6"""
        host, cl = self.host(), self.cl()
        self.scmd('Aura.Match.Rules Teams=auto ShipLives=2')
        yield from self.wait(0.6)
        yield from self.until(lambda: self.team(host) == 0 and self.team(cl) == 1, 1.0)
        self.lobby_teams = dict((p['id'], self.team(p)) for p in self.P)
        self.ensure_panels(True)
        yield from self.wait(0.4)
        t0 = self.now
        self.scmd('Aura.Lobby.Start strict')
        yield from self.wait(0.4)
        refused = [l[-200:] for _, l in self.log_since(t0, 'Lobby: start ') if 'NotReady' in l and ('refused' in l or 'second click' in l)]
        not_started = self.phase_of(self.sw) == 'lobby'
        self.check('LM1.6_strict', self.ok(refused and not_started), 'Start strict with the client not ready: %s, phase %s (want refused, Lobby)' % (
            refused[:1], self.phase_of(self.sw)))
        self.scmd('Aura.Lobby.Ready %d 1' % self.aidx(cl))
        yield from self.until(lambda: self.lps(cl['pss']).get('ready'), 1.0)
        self.scmd('Aura.Lobby.Start strict')
        cd = yield from self.wait_phase('countdown', 1.0)
        yield from self.until(lambda: self.phase_of(cl['w']) == 'countdown', 0.5)
        yield from self.wait(0.3)
        views = []
        for p in self.P:
            st = yield from self.lobby_status(p['w'])
            loc0 = ((st or {}).get('local') or [{}])[0]
            views.append({'panel_widget_open': self.panel_view(p['w']).get('open'), 'panel': loc0.get('panel'), 'ignore_input': loc0.get('ignore_input'),
                          'cursor': loc0.get('cursor')})
        c0 = self.ochar(cl)
        p0 = self.loc(c0) if c0 else None
        tm = self.now
        while self.now - tm < 1.0:
            self.inject(cl['w'], 'IA_Move', (1.0, 0.0, 0.0))
            yield
        moved = dist(p0, self.loc(self.ochar(cl))) if p0 and self.ochar(cl) else None
        # The flags are the check. An injected IA_Move goes into UEnhancedPlayerInput directly and moves the pawn even with
        # UI-only input (IgnoreInput gates only UGameViewportClient::InputKey / InputAxis): data only
        ok1 = cd and all(not v['panel_widget_open'] and not v['panel'] and not v['ignore_input'] and not v['cursor'] for v in views)
        self.check('LM1.6_input', self.ok(ok1), 'the lobby countdown %s: (panel widget open, panel, IgnoreInput, cursor) host %s, client %s (want all 0: game '
                   'input, M2); data: the client\'s injected IA_Move moved his pawn %s cm in 1 s (moves with UI-only input too, not checked)' % (
                       bool(cd), views[0], views[1], r(moved, 0)))
        if not moved or moved < 1.0:
            # the flags decide; a pawn that did not move at all is worth a look (b80 run 1: 0.0 cm, fix 1: 522 cm), not a FAIL
            self.line('WARN', 'LM1.6_input: the client\'s injected IA_Move moved his pawn %s cm in 1 s during the countdown' % r(moved, 0))
        ip = yield from self.wait_phase('inprogress', 7.0)
        t_ip = self.now
        on = yield from self.until(lambda: all(self.on_deck(self.schar(p), self.ship(self.team(p))) for p in self.P), 1.0)
        dt = (self.now - t_ip) if on else None
        teams = dict((p['id'], self.team(p)) for p in self.P)
        self.check('LM1.6_aboard', self.ok(ip and dt is not None and teams == self.lobby_teams), 'InProgress %s; both on their own ship\'s deck %s s after '
                   '(want <= 1); teams %s (want the lobby\'s %s)' % (bool(ip), r(dt, 2), teams, self.lobby_teams))
        for t in (0, 1):
            s = self.ship(t)
            if s is not None:
                self.wind_off(s)

    def t_friendly_fire(self):
        """LMF"""
        host, cl = self.host(), self.cl()
        got = yield from self.need_ships('LMF_friendly_fire')
        if not got:
            return
        s0, s1 = got
        self.say('waiting for both ships to lose their spawn protection')
        unp = yield from self.until(lambda: not self.protected(self.ship(0)) and not self.protected(self.ship(1)), 30.0)
        s0, s1 = self.ship(0), self.ship(1)
        gd = float(self.setting('ShipDamageGunHit', 5.0))
        res = {'unprotected': bool(unp), 'rules_ff': mb_get(self.dump(self.sw, 'lmf', 0.0), 'rules', 'friendly_fire')}
        # The stage: each player where the match put him, aboard his own team's ship (LM1.6_aboard); the ships held, and team
        # 1's ship brought 50 m beside team 0's on the outer side (only sky behind it), its crew carried along on its deck.
        # b80 2026-11-28: both players put on team 0's deck by a hull-top trace stood in the air (the hull ignores Pawn since
        # the deck collision rebuild, the walkable deck is the Mesh's physics asset) and fell off, the client 500 m away.
        # Debug input parks every lane (AirshipLaneComponent, B2.3) and stops its recall clock: a cruising team 1 ship
        # steered straight back across team 0's lane, bow first ("lane blocked", "bow contact"). Cleared below.
        self.scmd('Aura.Airship.Input 0 0')
        yield from self.wait(0.5)
        # team 0's ship stopped where it is (parked, it drifts on at its cruise speed and would leave team 1's behind it)
        self.teleport(s0, self.loc(s0), self.yaw(s0))
        aboard = yield from self.until(lambda: self.on_deck(self.schar(host), s0) and self.on_deck(self.schar(cl), s1), 3.0)
        res['aboard_before'] = bool(aboard)
        # The client's spot aboard team 1's ship in its hull space: a teleported ship does not carry the players on its deck
        # (b80 step 4 run 1: the client was left 91 m beside it and 7 m below, falling, and his shots at team 0's hull went
        # into the platforms), so he is put back on the same spot after the move
        c1 = self.schar(cl)
        hp1 = v3(unreal.MathLibrary.inverse_transform_location(s1.get_actor_transform(), unreal.Vector(*self.loc(c1)))) if c1 is not None else None
        res['client_hull_before'] = r(hp1, 0)
        u0, v0, z0 = self.uv(self.loc(s0))
        self.teleport(s1, self.world(u0, v0 + self.side_of(0) * 5000.0, z0), self.yaw(s0))
        yield
        if hp1 is not None:
            self.tp(cl, v3(unreal.MathLibrary.transform_location(s1.get_actor_transform(), unreal.Vector(*hp1))), self.yaw(s1))
        yield from self.wait(1.5)
        res['stage'] = self.stage_info(s0, s1)
        hits, thp = {}, {}
        # Every shot at a hull's body below its deck plane (z 150): a hull hit above it goes on to a turret behind it
        # (AAirshipPawn::FindTurretBehindHullHit), and the turret, not the hull, takes it. Each window first settles the view.
        wins = (('host_own_ship', host, s0), ('client_own_ship', cl, s1), ('host_enemy_ship', host, s1), ('client_enemy_ship', cl, s0))
        for key, p, tgt in wins:
            # a player's gun on his OWN team's ship: no damage (Talal: "players of the same team shouldn't be able to damage
            # the ship of the same team"); on the other team's ship: ShipDamageGunHit per hit (the positive control)
            def tfn(p=p, tgt=tgt):
                return self.hull_aim(tgt, self.loc(self.schar(p)), z=150.0)
            yield from self.settle_aim(p, tfn)
            rec = hits[key] = []
            t0hp = self.turret_hp(tgt)
            tr = yield from self.ship_hp_track(tgt, 1.5, lambda: self.fire_at(p, tfn, rec))
            thp[key] = (t0hp, self.turret_hp(tgt))
            res[key] = self.drops(tr) if 'own' in key else sorted(set(self.drops(tr)))
        res['aim_hits'] = dict((k, self.hits_summary(v)) for k, v in hits.items())
        res['turret_hp'] = thp
        self.line('INFO', 'LMF stage %s; crosshair hits %s; turret health (before, after) %s' % (res['stage'], res['aim_hits'], thp))
        own_ok = unp and not res['host_own_ship'] and not res['client_own_ship']
        enemy_ok = res['host_enemy_ship'] == [round(gd, 3)] and res['client_enemy_ship'] == [round(gd, 3)]
        self.check('LMF_own_ship', self.ok(own_ok and enemy_ok), 'ships unprotected %s, rules FF %s; hull drops: the host on his own team\'s ship %s, the '
                   'client on his own team\'s ship %s (want none); the host on the other team\'s ship %s, the client on the other team\'s ship %s (want '
                   '[%s] each: ShipDamageGunHit)' % (unp, res['rules_ff'], res['host_own_ship'], res['client_own_ship'], res['host_enemy_ship'],
                                                    res['client_enemy_ship'], gd), res)
        # players: enemies hurt, teammates not. On foot on one platform 15 m apart (as_75 M3.1's stage): on team 0's ship the
        # deckhouse stands between its forward and aft decks, and a hit on it is a hit on the host's own ship
        got = yield from self.pair_on_platform(host, cl)
        res['players_stage'] = {'paired': bool(got), 'gap_m': r(dist(self.loc(self.schar(host)), self.loc(self.schar(cl))) / 100.0, 1)
                                if self.schar(host) is not None and self.schar(cl) is not None else None}
        rec_e, rec_t = [], []
        yield from self.settle_aim(host, lambda: self.loc(self.schar(cl)))
        t_e = self.now
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 1.5, lambda: self.fire_at(host, lambda: self.loc(self.schar(cl)), rec_e))
        res['enemy_player'] = sorted(set(self.drops(tr)))
        self.scmd('Aura.Match.Team %d 0' % cl['i'])
        yield from self.until(lambda: self.team(cl) == 0, 1.0)
        # data: the server's hit lines on the client in the enemy window (a teammate's hit stops at the friendly-fire filter
        # before the line)
        res['server_hits'] = {'enemy': len(self.gun_hits(t_e, self.schar(cl)))}
        yield from self.settle_aim(host, lambda: self.loc(self.schar(cl)))
        t_t = self.now
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 1.5, lambda: self.fire_at(host, lambda: self.loc(self.schar(cl)), rec_t))
        res['teammate_player'] = self.drops(tr)
        yield from self.wait(0.3)
        res['server_hits']['teammate'] = len(self.gun_hits(t_t, self.schar(cl)))
        self.scmd('Aura.Match.Team %d 1' % cl['i'])
        yield from self.until(lambda: self.team(cl) == 1, 1.0)
        res['aim_hits_players'] = {'enemy': self.hits_summary(rec_e), 'teammate': self.hits_summary(rec_t)}
        ok = res['enemy_player'] == [round(self.gun_base, 3)] and not res['teammate_player'] and self.team(cl) == 1
        self.check('LMF_players', self.ok(ok), 'the host\'s gun on the client: enemies %s (want [%s]: the GE value), teammates (Aura.Match.Team %d 0) %s '
                   '(want none); the client back on team %s; on one platform %s; crosshair hits (data) %s; the server\'s HitActor lines on the client '
                   '(data) %s' % (res['enemy_player'], self.gun_base, cl['i'], res['teammate_player'], self.team(cl), res['players_stage'],
                                  res['aim_hits_players'], res.get('server_hits')))
        # the ships free again, team 1's ship back into its lane, the client back aboard it (team 0's ship, parked in its
        # lane, cruises again after LaneParkSettleTime)
        self.scmd('Aura.Airship.InputClear')
        yield from self.wait(0.2)
        self.scmd('Aura.Lane.Teleport 1 %.1f' % (u0 / 100.0))
        yield from self.wait(1.0)
        s1 = self.ship(1)
        hp = mb_get(res, 'stage', 'client', 'hull_own')
        if s1 is not None and hp:
            # where he stood aboard it (a hull-top trace point is in the air, see the stage above)
            self.tp(cl, v3(unreal.MathLibrary.transform_location(s1.get_actor_transform(), unreal.Vector(*hp))), self.yaw(s1))
        yield from self.wait(0.6)

    def t_rejoin_match(self):
        """LM1.7"""
        cl0 = self.cl()
        old_team = self.team(cl0)
        dt = yield from self.rejoin('LM1.7_rejoin_match', 20.0)
        if dt is None:
            return
        cl = self.cl()
        pawn = yield from self.until(lambda: self.alive(self.schar(cl)), 10.0)
        on = yield from self.until(lambda: self.on_deck(self.schar(cl), self.ship(1)), 2.0)
        arr = [l[-200:] for _, l in self.log_since(self.now - dt - 1.0, 'arrives (hard)')]
        ok = dt <= 10.0 and self.team(cl) == 1 and pawn and on
        self.check('LM1.7_rejoin_match', self.ok(ok), 'open 127.0.0.1:%d InProgress: back after %s s (want <= 10), team %s (want 1, was %s), pawn %s, aboard '
                   'team 1\'s ship %s; log %s' % (self.port, r(dt, 2), self.team(cl), old_team, bool(pawn), bool(on), arr[:1]))

    def t_ship_lives(self):
        """LMS"""
        d = self.dump(self.sw, 'lms_0', 0.0)
        l0 = mb_get(d, 'teams', 1, 'lives_left')
        lost0 = mb_get(d, 'teams', 1, 'ships_lost')
        s1 = self.ship(1)
        n1 = mb_name(s1)
        t0 = self.now
        self.scmd('Aura.Match.KillShip 1')
        yield from self.wait(0.5)
        d = self.dump(self.sw, 'lms_1', 0.0)
        l1 = mb_get(d, 'teams', 1, 'lives_left')
        lost1 = mb_get(d, 'teams', 1, 'ships_lost')
        ev = [e['event'] for e in self.events_since(t0, 'ShipDestroyed', team=1)]
        back = yield from self.until(lambda: self.ship(1) is not None and mb_name(self.ship(1)) != n1, 14.0)
        dt = (self.now - t0) if back else None
        want_delay = float(self.setting('ShipRespawnDelay', 10.0))
        ok1 = l0 is not None and l1 == l0 - 1 and lost1 == (lost0 or 0) + 1 and ev and dt is not None and abs(dt - want_delay) <= 0.8
        self.check('LMS_lives', self.ok(ok1), 'KillShip 1: team 1 lives %s -> %s, ships lost %s -> %s (want -1 / +1), ShipDestroyed %s, a new ship %s s later '
                   '(want %.0f +-0.5)' % (l0, l1, lost0, lost1, bool(ev), r(dt, 2), want_delay))
        self.scmd('Aura.Match.Set EndScreenSeconds 3')
        # KillShip sets the health directly: spawn protection doesn't stop it (MyMatchConsole.cpp)
        yield from self.wait(0.5)
        t1 = self.now
        self.scmd('Aura.Match.KillShip 1')
        end = yield from self.until(lambda: self.phase_of(self.sw) == 'ended' and self.phase_of(self.cl()['w']) == 'ended', 3.0)
        rs, rc = self.result_of(self.sw), self.result_of(self.cl()['w'])
        # the event line reaches the log file a frame or more after the phase change (the b79 log lag): wait up to 1 s for it
        # (the end screen lasts 3 s)
        elim = yield from self.until(lambda: self.events_since(t1, 'TeamEliminated', team=1), 1.0)
        elim = [e['event'] for e in (elim or [])]
        ok2 = end and rs.get('result') == 'teamwon' and rs.get('winner') == 0 and rc.get('result') == 'teamwon' and rc.get('winner') == 0 and elim
        self.check('LMS_eliminated', self.ok(ok2), 'the last KillShip 1: Ended on both %s, result server %s / client %s (want TeamWon 0 on both), '
                   'TeamEliminated %s, lobby round %s (the end panel says "Back to the lobby")' % (
                       bool(end), (rs.get('result'), rs.get('winner')), (rc.get('result'), rc.get('winner')), bool(elim), self.lgs(self.sw).get('lobby_round')))
        self.xgrab('lms_end_panel')

    def t_return(self):
        """LM1.8"""
        before = dict((p['join'], (p['name'], self.team(p))) for p in self.P)
        d0 = self.dump(self.sw, 'lm1_8_before', 0.0)
        rules0 = mb_get(d0, 'rules')
        t0 = self.now
        self.D.pop('new_worlds', None)
        back = yield from self.until(lambda: self.D.get('new_worlds'), 60.0)
        if not back:
            self.check('LM1.8_return', 'FAIL', 'no new worlds within 60 s of the end (PIE ServerTravel)')
            return
        lob = yield from self.until(lambda: self.phase_of(self.sw) == 'lobby' and self.phase_of(self.cl()['w']) == 'lobby', 15.0)
        yield from self.until(lambda: all(self.alive(self.schar(p)) for p in self.P), 5.0)
        trav = [l[-240:] for _, l in self.log_since(t0, 'Match: back to the lobby')]
        d1 = self.dump(self.sw, 'lm1_8_after', 0.0)
        after = dict((p['join'], (p['name'], self.team(p))) for p in self.P)
        same = all(after.get(j, (None, None))[1] == t for j, (_, t) in before.items())
        g = self.lgs(self.sw)
        ready = [self.lps(p['pss']).get('ready') for p in self.P]
        ok = (lob and trav and 'Lobby=1' in trav[0] and 'Round=1' in trav[0] and same and mb_get(d1, 'rules') == rules0 and not any(ready[1:]))
        self.check('LM1.8_return', self.ok(ok), 'the end -> travel %s (want Lobby=1, Round=1, hard in PIE); both in phase Lobby %s; teams by join order before '
                   '%s after %s (want the same; join order where PIE gives no net ids); rules kept %s; ready flags %s (want false); rematch %s (true only '
                   'with valid net ids)' % (trav[:1], bool(lob), before, after, mb_get(d1, 'rules') == rules0, ready, g.get('rematch')))
        self.lobby_teams = dict((p['id'], self.team(p)) for p in self.P)

    def t_rejoin_lobby(self):
        """LM1.9"""
        dt = yield from self.rejoin('LM1.9_rejoin_lobby', 20.0)
        if dt is None:
            return
        cl = self.cl()
        pawn = yield from self.until(lambda: self.alive(self.schar(cl)), 6.0)
        st = yield from self.lobby_status(self.sw)
        ok = self.counts(st) == [1, 1] and not self.lps(cl['pss']).get('ready') and pawn and self.zone_has(st, self.loc(self.schar(cl)))
        self.check('LM1.9_rejoin_lobby', self.ok(ok), 'rejoin in the lobby after %s s: counts %s (want 1 / 1), ready %s (want false), a pawn %s in the zone '
                   '%s' % (r(dt, 2), self.counts(st), self.lps(cl['pss']).get('ready'), bool(pawn),
                           self.zone_has(st, self.loc(self.schar(cl))) if self.schar(cl) else None))

    def t_rejoin_countdown(self):
        """LM1.10"""
        self.scmd('Aura.Lobby.Start')
        cd = yield from self.wait_phase('countdown', 1.0)
        yield from self.wait(1.0)
        dt = yield from self.rejoin('LM1.10_rejoin_countdown', 15.0)
        if dt is None:
            return
        cl = self.cl()
        early = []
        while self.phase_of(self.sw) == 'countdown' and self.now - self.t_test0 < 30.0:
            if self.schar(cl) is not None:
                early.append(r(self.now, 2))
            yield
        ip = self.phase_of(self.sw) == 'inprogress'
        t_ip = self.now
        on = yield from self.until(lambda: self.on_deck(self.schar(cl), self.ship(self.team(cl))) and self.on_deck(self.schar(self.host()), self.ship(0)), 2.0)
        d = self.dump(self.sw, 'lm1_10', 0.0)
        act = [mb_get(d, 'teams', t, 'active') for t in (0, 1)]
        ok = cd and ip and not early and on and act == [True, True]
        self.check('LM1.10_rejoin_countdown', self.ok(ok), 'rejoin 1 s into the lobby countdown (back after %s s): a pawn before 0 at %s (want none); '
                   'InProgress %s; both aboard their ships %s s after it; teams active %s (want both: the empty team comes back at 0)' % (
                       r(dt, 2), early[:3], ip, r(self.now - t_ip, 2) if on else None, act))

    def t_rejoin_ended(self):
        """LM1.11"""
        self.scmd('Aura.Match.Set EndScreenSeconds 12')
        self.scmd('Aura.Match.End 0')
        end = yield from self.wait_phase('ended', 2.0)
        yield from self.wait(1.0)
        dt = yield from self.rejoin('LM1.11_rejoin_ended', 9.0)
        if dt is None:
            return
        cl = self.cl()
        pawn = yield from self.until(lambda: self.alive(self.schar(cl)), 5.0)
        self.D.pop('new_worlds', None)
        back = yield from self.until(lambda: self.D.get('new_worlds'), 40.0)
        lob = yield from self.until(lambda: self.phase_of(self.sw) == 'lobby' and self.phase_of(self.cl()['w']) == 'lobby', 15.0)
        ok = end and pawn and back and lob
        self.check('LM1.11_rejoin_ended', self.ok(ok), 'rejoin in Ended (back after %s s): a pawn %s (want one, as InProgress); the return took him to the '
                   'lobby: new worlds %s, both in phase Lobby %s' % (r(dt, 2), bool(pawn), bool(back), bool(lob)))
        self.scmd('Aura.Match.Set EndScreenSeconds 3')

    def t_cancel_disconnect(self):
        """LM1.12"""
        yield from self.until(lambda: all(self.alive(self.schar(p)) for p in self.P), 5.0)
        self.scmd('Aura.Match.Rules Teams=1v1')
        yield from self.wait(0.5)
        t0 = self.now
        self.scmd('Aura.Lobby.Start')
        cd = yield from self.wait_phase('countdown', 1.0)
        yield from self.wait(2.0)
        old = self.cl()['w']
        old_t = self.wt(old)
        td = self.now
        self.cmd(old, 'disconnect')
        canc = yield from self.until(lambda: self.phase_of(self.sw) == 'lobby', 1.5)
        dt = (self.now - td) if canc else None
        yield from self.wait(0.5)
        # read after the wait: the event line reaches the log file a frame or more after the phase change (the b79 log lag)
        ev = [(e['event'], e['value']) for e in self.events_since(td, 'LobbyCancelled')]
        ships = [mb_name(s) for s in self.team_ships(self.sw)]
        ok = cd and dt is not None and dt <= 0.5 + 0.25 and ev and ev[0][1] == LB_BLOCKS.index('NeedOpponent') and not ships
        self.check('LM1.12_cancel', self.ok(ok), 'Teams=1v1, Start, the client disconnects 2 s in: cancelled after %s s (want <= 0.5 + one 0.25 s tick), '
                   'events %s (want LobbyCancelled, value NeedOpponent = %d), team ships left %s (want none)' % (
                       r(dt, 2), ev, LB_BLOCKS.index('NeedOpponent'), ships))
        # back in: the client's menu world opens the address
        mw = yield from self.until(self.other_world, 15.0)
        if mw is None:
            self.check('LM1.12_reopen', 'FAIL', 'no menu world for the disconnected client within 15 s')
            return
        yield from self.wait(1.0)
        # the menu world's name first: the open replaces that world, and its wrapper is dead after it (b80 2026-11-28, step 4:
        # "World: Internal Error - ObjectInstance is null!" from this check's text, 0.2 s after the open)
        mw_name = mw.get_path_name()
        t_open = self.now
        self.cmd(mw, 'open 127.0.0.1:%d' % self.port)
        got = yield from self.remap(25.0, old_world=old, old_t=old_t)
        self.check('LM1.12_reopen', self.ok(got), 'the client opened 127.0.0.1:%d from %s: mapped again %s after %s s' % (
            self.port, mw_name, got, r(self.now - t_open, 2)))
        self.scmd('Aura.Match.Rules Teams=auto')
        yield from self.wait(0.5)

    def t_seamless(self):
        """LM1.13"""
        if len(self.P) < 2:
            self.check('LM1.13_seamless', 'FAIL', 'the client is not mapped (LM1.12 did not bring him back)')
            return
        mb_editor_cmd('net.AllowPIESeamlessTravel 1')
        self.line('INFO', 'net.AllowPIESeamlessTravel 1 (RL14: a PIE seamless travel can take the editor down)')
        yield from self.until(lambda: all(self.alive(self.schar(p)) for p in self.P), 5.0)
        # teams by player NAME: the join order (PlayerArray) changes in a seamless travel, while the name is copied over
        # (APlayerState::CopyProperties)
        names0 = [p['name'] for p in self.P]
        cl_name = self.cl()['name']
        teams0 = dict((p['name'], self.team(p)) for p in self.P)
        lpc0_obj = self.cl()['lpc']
        lpc0 = lpc0_obj.get_path_name()
        # IMC_AirshipBoard before the travel, with the controller's own IMC as the positive control (data)
        imc_before = {'client': self.imc_probe(self.cl()['w'], self.cl()['lpc']), 'host': self.imc_probe(self.sw, self.host()['lpc'])}
        self.scmd('Aura.Lobby.Start')
        yield from self.wait_phase('inprogress', 8.0)
        yield from self.wait(1.0)
        self.scmd('Aura.Match.Set EndScreenSeconds 3')
        cw_old = self.cl()['w']
        t_cw_old = self.wt(cw_old)
        t0 = self.now
        self.D.pop('new_worlds', None)
        self.scmd('Aura.Match.End 0')
        back = yield from self.until(lambda: self.D.get('new_worlds'), 80.0)
        # The server's new world is found as soon as it loads, and the client's OLD world is still in the PIE world list then
        # (a seamless travel keeps it until the client's own travel ends): B75 mapped the client to it, and every read of
        # it failed once it was gone (b80 step 4 run 2: 601 phase_of errors, "World: Internal Error"). Map him again once
        # his new world is there
        remapped = False
        if back:
            remapped = yield from self.remap(30.0, old_world=cw_old, old_t=t_cw_old)
        # That first map is too early as well (final run 2026-11-28: the client's controller "the same object", no pilot
        # component, teams {1: 0, 0: 0}, the third start "both aboard False"). AGameModeBase::HandleSeamlessTravelPlayer
        # (GameModeBase.cpp:607-641) spawns a NEW controller for every player: for the host in PostSeamlessTravel, for the
        # client only when his ServerNotifyLoadedWorld comes in ("Team: <name> arrives (seamless)"). Until then the
        # server's list holds the client's carried old controller, and until the client acknowledges the swap (NMT_PCSwap,
        # NetConnection.cpp HandleClientPlayer) his world holds the old one too. So: wait for every player's arrival line,
        # then for one controller per player on the server and one on the client, then map everyone again.
        arrived = swapped = mapped2 = False
        if back:
            arrived = yield from self.until(lambda: all(self.log_since(t0, 'Team: %s arrives (seamless)' % n) for n in names0), 30.0)
        if arrived:
            swapped = yield from self.until(lambda: self.pc_count(self.sw) == len(names0) and all(self.pc_count(w) == 1 for w in self.cws), 20.0)
        if swapped:
            yield from self.wait(1.0)
            mapped2 = yield from self.remap(20.0)
            if mapped2 and self.P and not self.P[0]['pcs'].is_local_controller():
                self.P.sort(key=lambda p: 0 if p['pcs'].is_local_controller() else 1)
                self.line('INFO', 'the host is not the server\'s first controller after the travel: players reordered, host first')
        self.R.setdefault('lm1_13_pre', {}).update({'client_remapped': bool(remapped), 'arrived': bool(arrived), 'swapped': bool(swapped),
                                                    'mapped_after_swap': bool(mapped2), 'client_name': (cl_name, self.cl()['name'] if len(self.P) > 1 else None)})
        self.line('INFO', 'LM1.13: mapped at the new worlds %s; every arrival line %s; one controller per player (server %s, client %s) %s; mapped '
                  'again %s; the client %s -> %s' % (bool(remapped), bool(arrived), self.pc_count(self.sw), [self.pc_count(w) for w in self.cws],
                                                     bool(swapped), bool(mapped2), cl_name, self.cl()['name'] if len(self.P) > 1 else None))
        lob = yield from self.until(lambda: self.phase_of(self.sw) == 'lobby' and self.phase_of(self.cl()['w']) == 'lobby', 20.0)
        seam = [l[-200:] for _, l in self.log_since(t0, 'SeamlessTravel')]
        trav = [l[-200:] for _, l in self.log_since(t0, 'Match: back to the lobby')]
        cl = self.cl()
        lpc1 = cl['lpc'].get_path_name() if cl.get('lpc') else None
        new_pc = cl.get('lpc') is not None and not mb_same(cl['lpc'], lpc0_obj)
        comp_srv = self.has_pilot_component(cl['pcs'])
        comp_cl = self.has_pilot_component(cl['lpc'])
        imc_at_once = {'client': self.imc_probe(cl['w'], cl['lpc']), 'host': self.imc_probe(self.sw, self.host()['lpc'])}
        teams1 = dict((p['name'], self.team(p)) for p in self.P)
        yield from self.wait(5.0)
        # IMC_AirshipBoard is read 5 s after the players were mapped again, like the counts: the pilot component retries its
        # local setup every 0.25 s while its controller has no local player yet (AirshipPilotComponent.cpp:47-55, :80-90)
        imc_5s = {'client': self.imc_probe(cl['w'], cl['lpc']), 'host': self.imc_probe(self.sw, self.host()['lpc'])}
        imc = imc_5s['client'].get('board')
        self.R['lm1_13_imc'] = {'before': imc_before, 'at_once': imc_at_once, 'after_5s': imc_5s}
        self.line('INFO', 'LM1.13 IMC reads (board / the controller\'s own IMC / input components): before the travel %s; at once %s; after 5 s %s' % (
            imc_before, imc_at_once, imc_5s))
        counts = {}
        for key, k in (('platforms', 'platform'), ('ships', 'ship')):
            counts[key] = (len(unreal.GameplayStatics.get_all_actors_of_class(self.sw, mb_cls(k))),
                           len(unreal.GameplayStatics.get_all_actors_of_class(cl['w'], mb_cls(k))))
        gc = [l[-200:] for _, l in self.log_since(t0, 'not cleaned up by garbage collection')]
        tl = [l[-160:] for _, l in self.log_since(t0, 'fall death')]
        overlay = any('Overlay' in o.get_class().get_name() for o in unreal.ObjectIterator(unreal.UserWidget)
                      if mb_same(o.get_world(), cl['w']))
        # the carried player states were marked arriving (AMyGameMode::PostSeamlessTravel) and are all replaced 5 s later
        arr = [l[-160:] for _, l in self.log_since(t0, 'Match: seamless arrival')]
        m_arr = re.search(r'seamless arrival, (\d+) carried', arr[-1]) if arr else None
        n_arr = int(m_arr.group(1)) if m_arr else None
        st_arr = yield from self.lobby_status(self.sw)
        left_arr = (st_arr or {}).get('arriving')
        self.R['lm1_13'] = {'seamless_lines': seam[:6], 'travel': trav[:2], 'overlay_widget': overlay, 'arrival': arr[:2], 'arriving_after_5s': left_arr}
        ok = (back and swapped and mapped2 and lob and seam and trav and 'seamless' in trav[0] and new_pc and comp_srv and comp_cl is True and imc is True
              and teams1 == teams0 and all(a == b for a, b in counts.values()) and not gc and not tl
              and n_arr is not None and n_arr >= 1 and left_arr == 0)
        self.check('LM1.13_seamless', self.ok(ok), 'net.AllowPIESeamlessTravel 1, start, End 0: new worlds %s, every seamless arrival and the controller swap done %s, mapped again %s, both in phase Lobby %s; log %s / %s (want '
                   '"SeamlessTravel" lines and a seamless return); the client\'s controller %s -> %s, a new object %s (want true, 5.4 row 6), pilot component server %s / client %s, '
                   'IMC_AirshipBoard mapped %s (5 s after the map; at once %s; the controller\'s own IMC %s); teams %s -> %s (want kept); (server, client) counts after 5 s %s (want equal); GC errors %s, fall deaths %s '
                   '(want none); carried player states marked arriving %s (want >= 1, log %s), still arriving after 5 s %s (want 0); overlay widget %s '
                   '(data)' % (
                       bool(back), bool(swapped), bool(mapped2), bool(lob), seam[:2], trav[:1], lpc0, lpc1, new_pc, comp_srv, comp_cl, imc, imc_at_once['client'].get('board'), imc_5s['client'].get('player'), teams0, teams1, counts, gc[:1], tl[:1],
                       n_arr, arr[:1], left_arr, overlay))
        self.scmd('Aura.Lobby.Start')
        ip = yield from self.wait_phase('inprogress', 8.0)
        on = yield from self.until(lambda: all(self.on_deck(self.schar(p), self.ship(self.team(p))) for p in self.P), 2.0)
        self.check('LM1.13_third_start', self.ok(ip and on), 'a third start after the seamless return: InProgress %s, both aboard %s' % (bool(ip), bool(on)))
        mb_editor_cmd('net.AllowPIESeamlessTravel 0')


_old80 = globals().get('AS80_RUN')
if _old80 is not None and _old80.phase not in ('finished',):
    print('an as_80 run is active (phase %s): stop it first (as_80x_stop.py)' % _old80.phase)
else:
    AS80_RUN = B80()
    _ok80 = AS80_RUN.arm()
    if not _ok80:
        AS80_RUN.restore()
        AS80_RUN.remove_temp()
        AS80_RUN.phase = 'finished'
    for _l in AS80_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_80s_status.py; results in %s)' % AS80_RUN.OUTDIR if _ok80 else 'FAIL: not armed'))
