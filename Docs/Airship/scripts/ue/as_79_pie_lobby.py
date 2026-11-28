# as_79_pie_lobby.py - round 2 PR B lobby PIE harness, STANDALONE run of the lean test plan (Docs/Airship/round2/
# SPEC_B_LOBBY.md 8.3, LB1.1 .. LB1.10): ONE PIE session on StartupMap (the clone's), one player, the lobby forced by the
# CVar Aura.Lobby.Enable 1, fixed 30 fps game time. Built on as_74's B74 (standalone PIE arm / restore, map reloads, the
# player readers) and as_70_matchlib.MBRun (generator test steps, the log tail, Aura.Match.Dump); the lobby readers are in
# as_79_lobbylib.py. LB1.7 / LB1.9 / LB1.10 load the map again inside the same PIE session.
# Run (StartupMap open, no PIE, the PR B lobby C++ built, as_77 + as_78 done so BP_MyHUD has WBP_Lobby3):
#   Docs/Airship/scripts/harness/inbox.sh 79 Docs/Airship/scripts/ue/as_79_pie_lobby.py 60
#   status: inbox.sh 79s Docs/Airship/scripts/ue/as_79s_status.py 30     stop: inbox.sh 79x Docs/Airship/scripts/ue/as_79x_stop.py 30
# Knobs (inbox globals, read at arm): AS79_MAP = 'StartupMap'; AS79_ONLY = () test-name prefixes (LB1.1 always runs);
#   AS79_HOLD = 0.0 game seconds to keep the open panel on screen after LB1.4's checks and after LB1.7's check (for window
#   grabs of the panel: xgrab_loop.sh needs ~3 s per grab of the editor window; the checks are made before the hold).
# Results: Saved/Match/b79/ (b79_result.json, b79_report.txt, b79_log.txt, b79_status.txt, dump/).
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, LevelEditorPlaySettings Standalone / 1 player,
# the UMyMatchSettings / UAirshipSettings / UBurrowerSettings class defaults (Burrowers off: the harness standard; their
# pause is read from the log line), the CVars Aura.Match.Enable (1), Aura.Lobby.Enable (1), Aura.Lane.Debug. The PIE copies
# of Floor and BP_MyHexPlatform_C_1 are destroyed in LB1.8 / LB1.9 (PIE only: the map is never saved, nothing in the
# editor level is touched except the TEMP_AS79_* capture / blocks B74 places, removed after PIE).
#
# Tests (in this order, game-second budgets in build_tests):
#  LB1.1  load with the lobby: phase Lobby within 1 s, bInLobby, the spawn log line, the zone holds (0, 0, 205) and the
#         placed platform's root, the pawn within 8 m of (0, 0, 205), no team ship, every wave spawner stopped and 0
#         sentinels at 15 s, ExpectedPlayers = DefaultExpectedPlayers, the panel opened by itself (panel 1, IgnoreInput 1)
#  LB1.2  a free ship (Aura.Airship.Spawn, then turned to face the player 100 m out so he is in its turret arcs) fires its
#         turrets at the player: >= 1 round hits him (LogAirshipTurret VeryVerbose "hit <pawn>"), Health unchanged;
#         Aura.Airship.Board 0 refused with Locked (log); BP_Potion_C_1 without collision
#  LB1.3  the pawn put on a path platform at u 50 m: back in the zone within 1.0 s (+ the zone log line); CurrentPlatform
#         spline distance -1, no ranking (the dump's lead spline distance -1)
#  LB1.4  Aura.Match.Rules Teams=practice ShipLives=5 Swarm=3: applied at once (team mode included); the game mode's
#         "Swarm difficulty 3 (Very Hard) ..." line has the preset's health / damage / max alive and count = preset x the
#         player factor, and the wave spawner's wave 1 multipliers and MaxAlive moved by preset 3 / the old preset
#  LB1.5  Aura.Lobby.Start, Aura.Lobby.Cancel at 2 s: phase Countdown 5 +-0.1 s ahead, bInLobby, a team 0 ship, panel
#         closed with game input (panel 0, IgnoreInput 0, cursor 0); after the cancel phase Lobby, no team ship, events
#         Countdown then LobbyCancelled
#  LB1.6  the beam once (a cooldown), Aura.Lobby.Start: InProgress at 5 +-0.1 s, bInLobby false, one team 0 ship at the lane
#         spawn point +-1 m, the player on its deck within 1 s with full Health and Mana, no active effect with a duration,
#         potion collision back, spawners running, the swarm resumed (log), wave 1 sentinels within 12 s
#  LB1.7  Aura.Match.Set EndScreenSeconds 3, Aura.Match.End -1: Ended; 3 +-0.5 s later the map loads again with Lobby=1;
#         phase Lobby; rules as LB1.4; RoundIndex 0
#  LB1.8  Aura.Lobby.Start; once aboard, the PIE Floor and placed platform destroyed, the player 150 m below the lane on
#         foot: fall death within 8 s, the respawn on a path platform (SplineDistance >= 0), never within 30 m of
#         (0, 0, 205); then Aura.Lobby.Return
#  LB1.9  back in the lobby: the PIE Floor and platform destroyed, Aura.Lobby.Resolve: the log picks PathStart, the pawn on
#         the platform with the smallest SplineDistance within 10 s, after 10 s there no ranking; Aura.Lobby.Start works
#         from there (aboard at 0)
#  LB1.10 console open StartupMap?Teams=auto?Players=1?Lobby=0 (the Play Solo URL; the URL beats the CVar): a practice
#         countdown at once, no pawn for 5 s, then the pawn on team 0's deck
# Deviations from SPEC_B_LOBBY 8.3 (for the lead's spec update):
#  * LB1.1 "Burrower IsSpawningPaused" is not readable from Python and the harness keeps Burrowers off: LB1.6 checks the
#    log line "Lobby: swarm resumed (..., Burrowers unpaused)" instead.
#  * LB1.4's "DifficultyScale = the Very Hard preset" is read from the game mode's log line and the spawner's wave
#    definition (DifficultyScale itself is not a UPROPERTY); the dump has no swarm block.
#  * LB1.9 waits 10 s on the path platform (not 30 s): the zone holds the player on it; nothing activates without a landing.
import json, math, os, re, time, traceback  # unreal = inbox namespace

_AS79_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
_as79_src74 = open(os.path.join(_AS79_UE, 'as_74_pie_match.py')).read()
# B74 and its helpers (as_74 also execs as_70_matchlib); not as_74's own arming code at its end
exec(compile(_as79_src74[:_as79_src74.index('\n_old74 = ')], os.path.join(_AS79_UE, 'as_74_pie_match.py'), 'exec'), globals())
exec(compile(open(os.path.join(_AS79_UE, 'as_79_lobbylib.py')).read(), os.path.join(_AS79_UE, 'as_79_lobbylib.py'), 'exec'), globals())

AS79_VERSION = 'as_79_pie_lobby 2026-11-28d'
AS79_START = (0.0, 0.0, 205.0)            # PlayerStart_0 (SPEC_B_LOBBY 1, decoded)
AS79_PLATFORM_ROOT = (16.0, -199.0, 1678.0)  # BP_MyHexPlatform_C_1's root
AS79_POTION = 'BP_Potion_C'


class B79(LobbyMix, B74):
    TAG = 'b79'
    VERSION = AS79_VERSION
    TEMP = 'TEMP_AS79_'
    SKIPPED = {'LB1.1_burrower_paused': 'UBurrowerSpawnSubsystem::IsSpawningPaused is not a UFUNCTION and this harness keeps Burrowers '
                                        'off; LB1.6 reads the "swarm resumed (..., Burrowers unpaused)" log line'}

    def __init__(self):
        g = globals()
        self.cfg_in = {'map': str(g.get('AS79_MAP') or 'StartupMap'), 'pass': 'lobby', 'only': tuple(g.get('AS79_ONLY') or ()),
                       'scheme': 3, 'curve_yaw': 60.0, 'hold': float(g.get('AS79_HOLD') or 0.0)}
        self.OUTDIR = os.path.join(MB_MATCH, 'b79')
        MBRun.__init__(self)
        self.cfg.update(self.cfg_in)
        self.R['cfg'] = self.cfg
        self.R['lobbylib'] = LB_VERSION
        self.map_name = self.cfg['map']
        self.lat = False
        self.pc = None
        self.ptl = []
        self.first_ship = None
        self.free = None
        self.side0 = 1
        self.ball_seen = set()

    def build_tests(self):
        t = [('LB1.1_load', 45, self.t_load), ('LB1.2_locks', 25, self.t_locks), ('LB1.3_zone', 15, self.t_zone),
             ('LB1.4_rules', 10, self.t_rules), ('LB1.5_cancel', 15, self.t_cancel), ('LB1.6_start', 35, self.t_start),
             ('LB1.7_return', 45, self.t_return), ('LB1.8_no_floor', 60, self.t_no_floor), ('LB1.9_path_lobby', 60, self.t_path_lobby),
             ('LB1.10_play_solo', 40, self.t_play_solo)]
        only = self.cfg.get('only')
        if only:
            t = [x for x in t if x[0].startswith('LB1.1_') or any(x[0].startswith(o) for o in only)]
        return t

    def snapshot_settings(self):
        """B74's snapshot, plus the lobby CVar (restored at the end), then the lobby on for this PIE"""
        MBRun.snapshot_settings(self)
        for n in ('Aura.Lobby.Enable', 'net.AllowPIESeamlessTravel'):
            self.orig['cvars'][n] = mb_cvar_int(n)
        if self.orig['cvars'].get('Aura.Lobby.Enable') is None:
            self.orig['cvars']['Aura.Lobby.Enable'] = -1
        mb_editor_cmd('Aura.Lobby.Enable 1')
        self.line('INFO', 'Aura.Lobby.Enable 1 for the run (was %s)' % self.orig['cvars'].get('Aura.Lobby.Enable'))

    # ------------------------------------------------------------------------------------------------- helpers
    def new_world_after(self, key, timeout):
        """yield: a map reload (B74.on_new_world sets D['new_world']) within timeout harness seconds; the world path"""
        self.D.pop('new_world', None)
        t0 = self.now
        got = yield from self.until(lambda: self.D.get('new_world'), timeout)
        if not got:
            self.check(key, 'FAIL', 'no map reload within %.0f s' % timeout)
        return got

    def placed(self, w):
        """the PIE copies of Floor and BP_MyHexPlatform_C_1 (the lobby ground Talal will delete)"""
        out = []
        for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Actor):
            try:
                lab = a.get_actor_label()
            except Exception:  # noqa: BLE001
                lab = a.get_name()
            # exact names: a prefix match also took the path spawner's BP_MyHexPlatform_C_10 .. _19 (b79 run 2026-11-28, LB1.8)
            if lab in ('Floor', 'BP_MyHexPlatform_C_1') or a.get_name() == 'BP_MyHexPlatform_C_1':
                out.append(a)
        return out

    def path_platforms(self, w):
        return [p for p in self.platforms(w) if p['sd'] is not None and p['sd'] >= 0.0]

    def potion_collision(self, w):
        """(name, collision enabled) of the potions"""
        out = []
        for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Actor):
            try:
                if AS79_POTION in a.get_class().get_name():
                    out.append((a.get_name(), bool(a.get_actor_enable_collision())))
            except Exception:  # noqa: BLE001
                continue
        return out

    def ps0(self):
        try:
            return self.pc.get_editor_property('player_state') if self.pc else None
        except Exception:  # noqa: BLE001
            return None

    def full_vitals(self, c):
        return self.attr(c, 'Health'), self.attr(c, 'MaxHealth'), self.mana(c)

    def phase_world_time(self, ph, after=None):
        x = next((p for p in self.ptl if p[2] == ph and (after is None or p[0] >= after)), None)
        return x

    # ================================================================================================= tests
    def t_load(self):
        """LB1.1"""
        w = self.w
        yield from self.until(lambda: self.phase_of(w) == 'lobby', 5.0)
        first = next((x for x in self.ptl if x[2] not in (None, 'none')), None)
        g = self.lgs(w)
        spawn_lines = [l[-200:] for _, l in self.log_since(-1.0, 'Lobby: spawn ')]
        st = yield from self.lobby_status(w)
        c = self.me()
        p = self.loc(c) if c is not None else None
        d0 = dist(p, AS79_START) if p else None
        zone = {'start': self.zone_has(st, AS79_START), 'platform_root': self.zone_has(st, AS79_PLATFORM_ROOT)}
        ships = [(s.get_name(), self.ship_team(s)) for s in self.team_ships(w)]
        ok = (first is not None and first[2] == 'lobby' and first[1] <= 1.0 and g.get('in_lobby') and g.get('lobby_round')
              and any('PlayerStarts' in l and 'Floor' in l for l in spawn_lines) and all(zone.values()) and d0 is not None and d0 <= 800.0 and not ships)
        self.check('LB1.1_lobby', self.ok(ok), 'first phase %s (want Lobby at world <= 1 s); game state %s; spawn log %s (want PlayerStarts, ground '
                   'Floor (+ BP_MyHexPlatform_C_1)); zones %s hold PlayerStart %s and the placed platform %s; pawn %s at %s cm from (0, 0, 205) (want '
                   '<= 800); team ships %s (want none)' % (first, g, spawn_lines[:2], (st or {}).get('zones'), zone['start'], zone['platform_root'],
                                                             mb_name(c), r(d0, 0), ships), {'status': st})
        exp = int(self.setting('DefaultExpectedPlayers', 2))
        self.check('LB1.1_expected', self.ok(g.get('expected') == exp), 'ExpectedPlayers %s (want DefaultExpectedPlayers %d: PIE has no '
                   'Players option)' % (g.get('expected'), exp))
        # the panel opens by itself once the lobby pawn exists
        pv = yield from self.until(lambda: self.panel_view(w) if self.panel_view(w).get('open') else None, 3.0)
        st2 = yield from self.lobby_status(w)
        loc0 = ((st2 or {}).get('local') or [{}])[0]
        pv = pv or self.panel_view(w)
        ok = pv.get('widget') and pv.get('open') and loc0.get('panel') and loc0.get('ignore_input') and loc0.get('cursor')
        self.check('LB1.1_panel', self.ok(ok), 'lobby widget %s (%s), panel open %s; Aura.Lobby.Status local: panel %s, IgnoreInput %s, cursor %s '
                   '(want 1 1 1: UI-only input); the host view: START shown %s (%s), READY shown %s' % (
                       pv.get('widget'), pv.get('class'), pv.get('open'), loc0.get('panel'), loc0.get('ignore_input'), loc0.get('cursor'),
                       pv.get('StartButton'), pv.get('StartText_text'), pv.get('ReadyButton')), pv)
        # the swarm at 15 s after the lobby began
        t_l = first[0] if first else self.t_test0
        yield from self.wait(max(0.0, 15.0 - (self.now - t_l)))
        sp = self.spawners_stopped(w)
        alive = self.sentinels_alive(w)
        ok = sp and all(x[1] for x in sp) and alive == 0
        self.check('LB1.1_swarm', self.ok(ok), 'wave spawners (name, stopped, alive, wave) %s (want every one stopped), sentinels alive %s at 15 s '
                   '(want 0)' % (sp, alive))

    def t_locks(self):
        """LB1.2"""
        w = self.w
        c = self.me()
        before = set(s.get_name() for s in self.ships(w))
        self.cmd(w, 'Aura.Airship.Spawn')
        free = yield from self.until(lambda: next((s for s in self.ships(w) if s.get_name() not in before), None), 3.0)
        self.free = free
        tr = []
        hits = []
        stage = {}
        if free is not None and c is not None:
            yield from self.wait(1.0)
            # Aura.Airship.Spawn puts the ship 60 m ahead of the pawn, 15 m up, facing his way: he is behind its stern, outside
            # both turret arcs (yaw -110 .. 30 / -30 .. 110 deg from the bow, pitch -20 .. 40), so its turrets never fired at
            # him and "no drop" proved nothing (review 2026-11-28: "TurretFire: fire at" then "stop", no hit). Turned to face
            # him 100 m out at the same height: he is ahead of its bow, about 16 deg down from the forward-deck turrets.
            p, q = self.loc(c), self.loc(free)
            d = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
            ux, uy = (q[0] - p[0]) / d, (q[1] - p[1]) / d
            self.teleport(free, [p[0] + ux * 10000.0, p[1] + uy * 10000.0, q[2]], math.degrees(math.atan2(-uy, -ux)))
            yield from self.wait(0.5)
            stage = {'ship': r(self.loc(free), 0), 'yaw': r(self.yaw(free), 1), 'pawn': r(p, 0)}
            # the positive control: the rounds that reach the pawn (AAirshipTurret::ApplyBulletDamage logs "<turret>: hit <target>
            # for <damage>." at VeryVerbose once the target passed the turret's filter, before the damage-off attribute set)
            self.cmd(w, 'log LogAirshipTurret VeryVerbose')
            t_fire = self.now
            self.cmd(w, 'Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.loc(c)))
            tr = yield from self.watch_health(lambda: self.health(self.me()), 2.5)
            self.cmd(w, 'Aura.Airship.TurretFire 0')
            hits = yield from self.log_wait(t_fire, 1.0, 'LogAirshipTurret', ': hit %s for' % c.get_name())
            self.cmd(w, 'log LogAirshipTurret Log')
        drops = self.drops(tr)
        tb = self.now
        self.cmd(w, 'Aura.Airship.Board 0')
        yield from self.wait(0.6)
        refused = [l[-160:] for _, l in self.log_since(tb, 'refused (Locked')]
        flying = self.piloting()
        pots = self.potion_collision(w)
        ok = free is not None and hits and not drops and refused and not flying and pots and not any(x[1] for x in pots)
        self.check('LB1.2_locks', self.ok(ok), 'free ship %s %s; its turret rounds at the player: %d hit him (want >= 1: the rounds reach him; '
                   'first %s), health drops %s (want none: damage off); Aura.Airship.Board 0 -> %s, flying %s (want a Locked refusal, not '
                   'flying); potions (name, collision) %s (want no collision)' % (
                       mb_name(free), stage, len(hits), [l[-110:] for _, l in hits[:1]], drops, refused[:1], flying, pots))
        if free is not None and valid(free):
            free.destroy_actor()

    def t_zone(self):
        """LB1.3"""
        w = self.w
        c = self.me()
        pp = sorted(self.path_platforms(w), key=lambda p: abs(p['u'] - 5000.0))
        if c is None or not pp:
            self.check('LB1.3_zone', 'FAIL', 'no pawn (%s) or no path platform (%d)' % (mb_name(c), len(pp)))
            return
        p = pp[0]
        g = self.ground_at(w, self.loc(p['a'])[0], self.loc(p['a'])[1], p['ztop'], p['zbot'])
        spot = [g['p'][0], g['p'][1], g['p'][2] + self.hh(c) + 20.0] if g else [self.loc(p['a'])[0], self.loc(p['a'])[1], p['ztop'] + 200.0]
        st = yield from self.lobby_status(w)
        tz = self.now
        self.tp_char(c, spot, self.frame['yaw'])
        back = yield from self.until(lambda: self.me() is not None and self.zone_has(st, self.loc(self.me())), 2.0)
        dt = (self.now - tz) if back else None
        got = yield from self.log_wait(tz, 1.0, 'back to the lobby (')
        lines = [l[-180:] for _, l in got]
        psd = None
        try:
            psd = float(self.ps0().get_platform_spline_distance())
        except Exception:  # noqa: BLE001
            self.err('psd')
        d = self.dump(w, 'lb1_3', 0.0)
        lead = mb_get(d, 'lead_spline_distance')
        ok = dt is not None and dt <= 1.0 and lines and psd is not None and psd < 0.0 and (lead is None or float(lead) < 0.0)
        self.check('LB1.3_zone', self.ok(ok), 'put on path platform %s (SplineDistance %s) at %s: back in the zone after %s s (want <= 1.0: 0.5 s '
                   'grace + the 0.25 s tick); log %s; PlatformSplineDistance %s (want -1: no ranking); lead spline distance %s (want -1)' % (
                       mb_name(p['a']), p['sd'], r(spot, 0), r(dt, 2), lines[:1], psd, lead))

    def swarm_preset(self, i):
        """UMyMatchSettings.SwarmDifficulties[i] as a dict (Count, Health, Damage, MaxAlive), or None"""
        try:
            p = list(self.setting('SwarmDifficulties') or [])[int(i)]
            return dict((k, float(p.get_editor_property(k))) for k in ('Count', 'Health', 'Damage', 'MaxAlive'))
        except Exception:  # noqa: BLE001
            self.err('swarm_preset')
            return None

    def spawner_numbers(self, sp):
        """(wave 1's Health / Damage multipliers, MaxAlive) of a wave spawner as the difficulty scaled them; None if unreadable"""
        if sp is None:
            return None, None, None
        wd = self.wave_def(sp, 1) or {}
        hm = dm = ma = None
        try:
            hm, dm = float(wd['HealthMultiplier']), float(wd['DamageMultiplier'])
        except Exception:  # noqa: BLE001
            pass
        try:
            ma = float(sp.get_editor_property('MaxAlive'))
        except Exception:  # noqa: BLE001
            pass
        return hm, dm, ma

    def t_rules(self):
        """LB1.4"""
        w = self.w
        d0 = self.dump(w, 'lb1_4_before', 0.0)
        old_sw = (mb_get(d0, 'rules') or {}).get('swarm')
        sps = unreal.GameplayStatics.get_all_actors_of_class(w, mb_cls('waves'))
        sp = sps[0] if sps else None
        before = self.spawner_numbers(sp)
        t0 = self.now
        self.cmd(w, 'Aura.Match.Rules Teams=practice ShipLives=5 Swarm=3')
        yield from self.wait(0.5)
        d = self.dump(w, 'lb1_4', 0.0)
        ru = mb_get(d, 'rules') or {}
        applied = [l[-160:] for _, l in self.log_since(t0, 'Lobby: rules applied')]
        ok = mb_nz(ru.get('teams')) == 'practice' and ru.get('ship_lives') == 5 and ru.get('swarm') == 3 and applied
        self.check('LB1.4_rules', self.ok(ok), 'Aura.Match.Rules Teams=practice ShipLives=5 Swarm=3 in the lobby: rules %s (want practice / 5 / 3 at '
                   'once, team mode included); log %s' % (ru, applied[:1]))
        # The host screen's swarm difficulty reaches the swarm: the game mode's line (ApplySwarmDifficulty), then the spawner
        sw = self.swarm_line(t0) or {}
        vh = self.swarm_preset(3)
        old = self.swarm_preset(old_sw) if old_sw is not None else None
        after = self.spawner_numbers(sp)

        def near(a, b, tol=0.011):
            return a is not None and b is not None and abs(float(a) - float(b)) <= tol

        line_ok = (vh is not None and sw.get('difficulty') == 3.0 and near(sw.get('health'), vh['Health']) and near(sw.get('damage'), vh['Damage'])
                   and near(sw.get('max_alive'), vh['MaxAlive']) and sw.get('count_factor') is not None
                   and near(sw.get('count'), vh['Count'] * sw['count_factor'], 0.02))
        rat = {}
        for k, i, f in (('health', 0, 'Health'), ('damage', 1, 'Damage'), ('max_alive', 2, 'MaxAlive')):
            if old is not None and vh is not None and before[i] and after[i] is not None and old[f] > 0.0:
                rat[k] = (r(after[i] / before[i], 3), r(vh[f] / old[f], 3))
        spawner_ok = all(abs(a - b) <= 0.01 for a, b in rat.values())
        self.R['lb1_4'] = {'rules': ru, 'swarm_line': sw, 'preset_3': vh, 'preset_before': old, 'spawner_before': before, 'spawner_after': after}
        self.check('LB1.4_swarm', self.ok(line_ok and spawner_ok), 'Swarm=3 from the lobby: log %s; parsed difficulty %s, health x%s, damage x%s, max alive '
                   'x%s, count x%s (= preset count x players %s) (want 3 and the Very Hard preset %s); wave spawner %s (after / before, want = '
                   'preset 3 / preset %s): %s%s' % (
                       (sw.get('line') or '')[-200:] or None, sw.get('difficulty'), sw.get('health'), sw.get('damage'), sw.get('max_alive'),
                       sw.get('count'), sw.get('count_factor'), vh, mb_name(sp), old_sw, rat,
                       '' if rat else ' (spawner numbers not readable: the log line is the check)'))
        yield from self.hold_panel('lb1_4_rules')

    def hold_panel(self, label):
        """AS79_HOLD (default 0): keep the open panel on screen for window grabs, after the test's checks"""
        h = float(self.cfg.get('hold') or 0.0)
        if h > 0.0:
            self.say('holding %.1f s for window grabs (%s)' % (h, label))
            yield from self.wait(h)

    def t_cancel(self):
        """LB1.5"""
        w = self.w
        self.cmd(w, 'Aura.Lobby.Panel 1')
        yield from self.wait(0.3)
        t0 = self.now
        self.cmd(w, 'Aura.Lobby.Start')
        cd = yield from self.until(lambda: self.phase_of(w) == 'countdown', 1.0)
        g = self.lgs(w)
        left = g.get('phase_end', 0.0) - (self.stime(w) or 0.0)
        ship = yield from self.until(lambda: [s for s in self.team_ships(w) if self.ship_team(s) == 0], 1.0)
        yield from self.wait(0.2)
        st = yield from self.lobby_status(w)
        loc0 = ((st or {}).get('local') or [{}])[0]
        ok1 = cd and abs(left - float(self.setting('LobbyCountdownSeconds', 5.0))) <= 0.35 and g.get('in_lobby') and ship and \
            not loc0.get('panel') and not loc0.get('ignore_input') and not loc0.get('cursor')
        self.check('LB1.5_start', self.ok(ok1), 'Aura.Lobby.Start: phase Countdown %s, %.2f s left (want 5 +-0.1 at the start), bInLobby %s, team 0 '
                   'ship %s; panel %s, IgnoreInput %s, cursor %s (want 0 0 0: game input, M2)' % (
                       bool(cd), left, g.get('in_lobby'), [mb_name(s) for s in (ship or [])], loc0.get('panel'), loc0.get('ignore_input'),
                       loc0.get('cursor')))
        yield from self.wait(max(0.0, 2.0 - (self.now - t0)))
        tc = self.now
        self.cmd(w, 'Aura.Lobby.Cancel')
        back = yield from self.until(lambda: self.phase_of(w) == 'lobby' and not self.team_ships(w), 1.5)
        yield from self.event_wait(tc, 'LobbyCancelled', 1.0)
        ev = [(e['event'], e['t']) for e in self.events_since(t0) if e['event'] in ('Countdown', 'LobbyCancelled')]
        names = [e[0] for e in ev]
        ok = bool(back) and 'Countdown' in names and 'LobbyCancelled' in names and names.index('Countdown') < names.index('LobbyCancelled')
        self.check('LB1.5_cancel', self.ok(ok), 'Aura.Lobby.Cancel at 2 s: phase Lobby with no team ship %s (want within 1.5 s); events %s (want '
                   'Countdown then LobbyCancelled)' % (bool(back), ev))

    def t_start(self):
        """LB1.6"""
        w = self.w
        c = self.me()
        # the beam once: its cooldown is a timed effect the round start removes
        t_b = self.now
        while self.now - t_b < 0.4:
            self.inject(w, 'IA_RMB')
            yield
        yield from self.wait(0.3)
        n_fx = self.effects_with_duration(c)
        self.cmd(w, 'Aura.Lobby.Panel 0')
        t0 = self.now
        self.cmd(w, 'Aura.Lobby.Start')
        ip = yield from self.until(lambda: self.phase_of(w) == 'inprogress', 7.0)
        t_ip = self.now
        cdw = self.phase_world_time('countdown', t0)
        ipw = self.phase_world_time('inprogress', t0)
        delay = (ipw[1] - cdw[1]) if (cdw and ipw) else None
        s = yield from self.until(lambda: self.ship0(), 1.0)
        on = yield from self.until(lambda: self.aboard(self.me(), self.ship0()), 1.0)
        dt_on = (self.now - t_ip) if on else None
        yield from self.wait(0.3)
        c = self.me()
        g = self.lgs(w)
        want = self.lane_point(self.side0, float(self.setting('LaneSpawnU', 0.0)))
        ships = [x for x in self.team_ships(w)]
        off = dist(self.loc(s), want) if s is not None else None
        h, mh, mana = self.full_vitals(c)
        n_fx2 = self.effects_with_duration(c)
        pots = self.potion_collision(w)
        ok = (ip and delay is not None and abs(delay - float(self.setting('LobbyCountdownSeconds', 5.0))) <= 0.1 and not g.get('in_lobby')
              and len(ships) == 1 and self.ship_team(ships[0]) == 0 and off is not None and off <= 100.0 and dt_on is not None and dt_on <= 1.0
              and h is not None and mh is not None and abs(h - mh) <= 0.5 and n_fx2 == 0 and pots and all(x[1] for x in pots))
        self.check('LB1.6_start', self.ok(ok), 'Aura.Lobby.Start: countdown %s s (want 5 +-0.1), bInLobby %s (want false); team ships %s (want one, '
                   'team 0) %s cm from the lane spawn point %s (want <= 100); aboard %s s after InProgress (want <= 1); Health %s / %s, Mana %s; '
                   'timed effects before the start %s (the beam cooldown), after %s (want 0); potions %s (want collision back)' % (
                       r(delay, 2), g.get('in_lobby'), [(mb_name(x), self.ship_team(x)) for x in ships], r(off, 0), r(want, 0), r(dt_on, 2),
                       h, mh, mana, n_fx, n_fx2, pots))
        resumed = [l[-160:] for _, l in self.log_since(t0, 'Lobby: swarm resumed')]
        taken = [l[-160:] for _, l in self.log_since(t0, 'lobby pawn(s) taken back')]
        got = yield from self.until(lambda: (self.sentinels_alive(w) or 0) > 0, 12.0)
        sp = self.spawners_stopped(w)
        ok = resumed and 'Burrowers unpaused' in resumed[0] and sp and not any(x[1] for x in sp) and got
        self.check('LB1.6_swarm', self.ok(ok), 'log %s (want the spawners resumed and Burrowers unpaused), %s; spawners (name, stopped, alive, wave) %s '
                   '(want running); sentinels alive within 12 s %s' % (resumed[:1], taken[:1], sp, self.sentinels_alive(w)))

    def t_return(self):
        """LB1.7"""
        w = self.w
        self.cmd(w, 'Aura.Match.Set EndScreenSeconds 3')
        t0 = self.now
        self.cmd(w, 'Aura.Match.End -1')
        ended = yield from self.until(lambda: self.phase_of(w) == 'ended', 2.0)
        t_end = self.now
        g_end = self.lgs(w)
        nw = yield from self.new_world_after('LB1.7_return', 20.0)
        dt = (self.now - t_end) if nw else None
        lob = yield from self.until(lambda: self.phase_of(self.w) == 'lobby', 6.0)
        trav = [l[-220:] for _, l in self.log_since(t0, 'Match: back to the lobby')]
        d = self.dump(self.w, 'lb1_7', 0.0)
        ru = mb_get(d, 'rules') or {}
        g = self.lgs(self.w)
        ok = (ended and g_end.get('lobby_round') and nw and dt is not None and abs(dt - 3.0) <= 0.5 and lob and trav and 'Lobby=1' in trav[0]
              and mb_nz(ru.get('teams')) == 'practice' and ru.get('ship_lives') == 5 and ru.get('swarm') == 3 and g.get('round') == 0)
        self.check('LB1.7_return', self.ok(ok), 'Aura.Match.End -1: Ended %s (lobby round %s: the end panel says "Back to the lobby"); the map loads '
                   'again %s s later (want 3 +-0.5); travel log %s (want Lobby=1, OpenLevel in standalone); phase Lobby %s; rules %s (want LB1.4\'s: '
                   'practice / 5 / 3); RoundIndex %s (want 0: practice keeps the round)' % (
                       bool(ended), g_end.get('lobby_round'), r(dt, 2), trav[:1], bool(lob), ru, g.get('round')))
        yield from self.hold_panel('lb1_7_back_in_lobby')

    def t_no_floor(self):
        """LB1.8"""
        w = self.w
        yield from self.until(lambda: self.me() is not None, 5.0)
        self.cmd(w, 'Aura.Lobby.Start')
        ip = yield from self.until(lambda: self.phase_of(w) == 'inprogress', 8.0)
        on = yield from self.until(lambda: self.aboard(self.me(), self.ship0()), 2.0)
        gone = []
        for a in self.placed(w):
            gone.append(a.get_name())
            a.destroy_actor()
        yield
        c = self.me()
        s = self.ship0()
        if c is None or s is None:
            self.check('LB1.8_no_floor', 'FAIL', 'no pawn (%s) or no team ship (%s) after the start' % (mb_name(c), mb_name(s)))
            return
        q = self.loc(s)
        # straight under the ship: the lane runs beside the field, nothing below it
        self.tp_char(c, [q[0], q[1], q[2] - 15000.0], self.frame['yaw'])
        t_tp = self.now
        old = c.get_name()
        died = yield from self.until(lambda: self.me() is None or self.me().get_name() != old or not self.alive(self.me()), 8.0)
        dt_die = (self.now - t_tp) if died else None
        fall = [l[-160:] for _, l in self.log_since(t_tp, 'fall death')]
        newc = yield from self.until(lambda: self.me() if (self.me() is not None and self.me().get_name() != old and self.alive(self.me())) else None, 25.0)
        p = self.loc(newc) if newc is not None else None
        yield from self.wait(1.0)
        # the platform the new pawn stands on: its movement base, else a trace down that ignores the pawn (the b79 run of
        # 2026-11-28 traced without the ignore and hit the pawn's own capsule: "on BP_MyCharMech_C_2"), else the path
        # platform whose bounds hold him (FindRespawnTile puts him on a path tile, where a bridge end can be his base:
        # the next run stood "on BP_MyHexBridge2_C_26")
        base = self.base_owner(newc) if newc is not None else None
        pf = base
        if p is not None and not (pf is not None and mb_isa(pf, 'platform')):
            g = self.ground_at(w, p[0], p[1], p[2], p[2] - 3000.0, ignore=[newc])
            pf = g['actor'] if g else pf
        how = 'base / trace'
        if newc is not None and not (pf is not None and mb_isa(pf, 'platform')):
            q = self.loc(newc)
            inside = sorted([x for x in self.path_platforms(w) if self.on_platform(newc, x['a'])],
                            key=lambda x: math.hypot(self.loc(x['a'])[0] - q[0], self.loc(x['a'])[1] - q[1]))
            if inside:
                pf, how = inside[0]['a'], 'bounds (base %s)' % mb_name(base)
        sd = self.spline_d(pf) if pf is not None and mb_isa(pf, 'platform') else None
        d0 = dist(p, AS79_START) if p else None
        ok = ip and gone and died and dt_die is not None and dt_die <= 8.0 and newc is not None and sd is not None and sd >= 0.0 and d0 > 3000.0
        self.check('LB1.8_no_floor', self.ok(ok), 'started %s, aboard %s; PIE copies destroyed %s; 150 m below the lane: fall death %s s later (want '
                   '<= 8; log %s); respawn %s at %s on %s by %s (SplineDistance %s, want >= 0), %s cm from (0, 0, 205) (want > 3000)' % (
                       bool(ip), bool(on), gone, r(dt_die, 2), fall[:1], mb_name(newc), r(p, 0), mb_name(pf), how, sd, r(d0, 0)))
        self.cmd(w, 'Aura.Lobby.Return')
        yield from self.new_world_after('LB1.8_return', 20.0)
        yield from self.until(lambda: self.phase_of(self.w) == 'lobby', 6.0)

    def t_path_lobby(self):
        """LB1.9"""
        w = self.w
        yield from self.until(lambda: self.me() is not None, 6.0)
        gone = []
        for a in self.placed(w):
            gone.append(a.get_name())
            a.destroy_actor()
        t0 = self.now
        self.cmd(w, 'Aura.Lobby.Resolve')
        pp = yield from self.until(lambda: sorted(self.path_platforms(w), key=lambda p: p['sd']), 10.0)
        first = pp[0] if pp else None
        on = yield from self.until(lambda: first is not None and self.me() is not None and self.on_platform(self.me(), first['a']), 10.0)
        dt = (self.now - t0) if on else None
        got = yield from self.log_wait(t0, 2.0, 'Lobby: spawn PathStart')
        picked = [l[-200:] for _, l in got]
        yield from self.wait(10.0)
        psd = None
        try:
            psd = float(self.ps0().get_platform_spline_distance())
        except Exception:  # noqa: BLE001
            self.err('psd')
        d = self.dump(w, 'lb1_9', 0.0)
        lead = mb_get(d, 'lead_spline_distance')
        still = self.me() is not None and first is not None and self.on_platform(self.me(), first['a'])
        ok = gone and picked and dt is not None and dt <= 10.0 and still and psd is not None and psd < 0.0 and (lead is None or float(lead) < 0.0)
        self.check('LB1.9_path_lobby', self.ok(ok), 'floor and placed platform destroyed %s; Aura.Lobby.Resolve log %s (want PathStart); the pawn on %s '
                   '(smallest SplineDistance %s) after %s s (want <= 10), still there 10 s later %s; PlatformSplineDistance %s, lead %s (want -1: '
                   'no ranking)' % (gone, picked[:1], mb_name(first['a']) if first else None, first['sd'] if first else None, r(dt, 2), still, psd, lead))
        ts = self.now
        self.cmd(w, 'Aura.Lobby.Start')
        ip = yield from self.until(lambda: self.phase_of(w) == 'inprogress', 8.0)
        on = yield from self.until(lambda: self.aboard(self.me(), self.ship0()), 1.5)
        self.check('LB1.9_start', self.ok(ip and on), 'Aura.Lobby.Start from the path lobby: InProgress %s, aboard team 0\'s ship %s' % (bool(ip), bool(on)))

    def on_platform(self, c, plat):
        p = self.loc(c)
        b = self.base_owner(c)
        if mb_same(b, plat):
            return True
        o, e = plat.get_actor_bounds(True)
        return abs(p[0] - o.x) <= e.x + 100.0 and abs(p[1] - o.y) <= e.y + 100.0 and o.z - e.z - 100.0 <= p[2] <= o.z + e.z + 400.0

    def t_play_solo(self):
        """LB1.10"""
        w = self.w
        self.cmd(w, 'open /Game/Maps/StartupMap?Teams=auto?Players=1?Lobby=0')
        nw = yield from self.new_world_after('LB1.10_play_solo', 25.0)
        if not nw:
            return
        t0 = self.now
        first = yield from self.until(lambda: next((x for x in self.ptl if x[0] >= t0 - 0.01 and x[2] not in (None, 'none')), None), 3.0)
        g = self.lgs(self.w)
        pawn_seen = []
        t1 = self.now
        while self.now - t1 < 4.5 and self.phase_of(self.w) == 'countdown':
            if self.me() is not None:
                pawn_seen.append(r(self.now - t1, 2))
            yield
        ip = yield from self.until(lambda: self.phase_of(self.w) == 'inprogress', 3.0)
        t_ip = self.now
        on = yield from self.until(lambda: self.aboard(self.me(), self.ship0()), 1.0)
        dt_on = (self.now - t_ip) if on else None
        ok = first is not None and first[2] == 'countdown' and not g.get('lobby_round') and not pawn_seen and ip and dt_on is not None
        self.check('LB1.10_play_solo', self.ok(ok), 'open StartupMap?Teams=auto?Players=1?Lobby=0 (Lobby=0 beats Aura.Lobby.Enable 1): first phase %s '
                   '(want Countdown at once), lobby round %s (want false); a pawn during the countdown at %s s (want none); InProgress %s; on '
                   'team 0\'s deck %s s after it (want <= 1)' % (first, g.get('lobby_round'), pawn_seen[:3], bool(ip), r(dt_on, 2)))


_old79 = globals().get('AS79_RUN')
if _old79 is not None and _old79.phase not in ('finished',):
    print('an as_79 run is active (phase %s): stop it first (as_79x_stop.py)' % _old79.phase)
else:
    AS79_RUN = B79()
    _ok79 = AS79_RUN.arm()
    if not _ok79:
        AS79_RUN.restore()
        AS79_RUN.remove_temp()
        AS79_RUN.phase = 'finished'
    for _l in AS79_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_79s_status.py; results in %s)' % AS79_RUN.OUTDIR if _ok79 else 'FAIL: not armed'))
