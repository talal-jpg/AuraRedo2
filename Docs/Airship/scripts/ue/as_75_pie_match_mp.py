# as_75_pie_match_mp.py - round 2 PR B PIE harness, LISTEN-SERVER part of the test plan (Docs/Airship/round2/SPEC_B.md
# section 4.2): Play As Listen Server with AS75_PLAYERS players (the host + clients, one process) on StartupMap, fixed
# 30 fps game time. One arm runs several PIE sessions one after the other (scenarios), each with its own class-default
# settings applied before its PIE starts (they act in InitGame / StartPlay), all restored at the end. Built on
# as_70_matchlib.MBRun (generator test steps, the match readers, the log tail) and driven like as_60: both PIE worlds from
# the editor's Python, the clients act only through their own machine (Enhanced Input injected into the CLIENT's
# subsystem, its own control rotation), server-only console commands in the server world.
# The play mode is set by the runner with the editor CLOSED (Docs/Airship/scripts/harness/set_play_mode.sh listen <n>;
# a value set from Python is not kept), so as_75 only checks it and refuses another one; _AirshipWork_logs/run_b_listen.sh
# runs 2, 3 and 4 players (one editor session each) and puts Standalone back at the end.
# Run (StartupMap open, no PIE, the PR B C++ built, the ini in listen mode with AS75_PLAYERS players):
#   Docs/Airship/scripts/harness/inbox.sh 75 Docs/Airship/scripts/ue/as_75_pie_match_mp.py 60
#   status: inbox.sh 75s Docs/Airship/scripts/ue/as_75s_status.py 60     stop: inbox.sh 75x Docs/Airship/scripts/ue/as_75x_stop.py 60
# Knobs (inbox globals, read at arm; a wrapper sets every one):
#   AS75_PLAYERS = 2            must equal the ini's PlayNumberOfClients
#   AS75_SCENARIOS = ()         scenario names (default by player count: 2 -> wait3 versus practice leave forfeit,
#                               3 -> three full1v1, 4 -> four)
#   AS75_ONLY = ()              test-name prefixes inside the scenarios (each scenario's setup test always runs)
#   AS75_SCHEME = 3
# Results: Saved/Match/b75_<players>p/ (b75_result.json, b75_report.txt, b75_log.txt, b75_status.txt, dump/, xgrab/).
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, UMyMatchSettings / UAirshipSettings /
# UBurrowerSettings class defaults (Burrower off), the CVars Aura.Match.Enable (1) / Aura.Lane.Debug, p.NetShowCorrections
# (1 for the run), LogBeam verbosity. TEMP_AS75_* in the editor level (a parked BP_MyProjectile for the fireball test, a
# SceneCapture2D) are removed after PIE; the map is never saved. The user's own Play is never stopped.
#
# Scenarios -> tests (spec IDs of section 4.2):
#  wait3 (2 players, DefaultExpectedPlayers 3)   M1.0 WaitingToStart, no pawns on either machine; Aura.Match.Start: 5 s
#                                                countdown, InProgress 1v1
#  versus (2 players, DefaultExpectedPlayers 2)  M1.1 countdown once the client is in, pawns on their own decks, teams 0 / 1,
#      ships at both lanes, the client's team states = the server's; M6.1 lane state / lateral on the client; M2.1 F on the
#      enemy ship refused (+ the client's refusal log), Mount picks the own ship, F on the own ship boards; M2.3 console
#      Board and the client's prompt never pick the enemy ship; M2.2 the enemy deck rider is hit by turret rounds, the own
#      rider not; M3.1 gun on the enemy (GE value), on the enemy hull / turret (ShipDamageGunHit), teammates (Aura.Match.Team
#      1 0): gun, beam hit, beam splash, cannonball splash (also with the firing ship destroyed in flight), turret rounds,
#      fireball, beam knockback < 0.5 m, crew share 25 %; M3.2 Rules FF=1: teammates hurt again; M4.1 sentinel bullets on
#      the undriven / driven enemy ship and turret, tags kept with the pilot's character destroyed; M8.1 the host 300-450 m
#      away exists on the client and the client's gun reaches him; M8.2 sentinels near the driven lane ship on the client;
#      M7.2 client ship hook onto its own ship (>= 4 of 5, corrections <= 3 per reel); M9.1 teammates aboard 150 m below
#      path height stay alive; M5.1 team 1's ship killed 3 times: TeamWon 0 on both machines; M7.1 Aura.Match.Restart: both
#      back, teams kept, sides swapped, RoundIndex 1, rules kept; M5.3 (round 1) TimeLimit=1 + DamageShip 1 500: Ended by
#      the time limit 60 +-1 s later, team 0 wins, one TimeWarning
#  practice (2 players, DefaultRules.TeamMode Practice)   M1.1 practice variant: pawns aboard team 0's ship within the
#                                                countdown + 1 s (SPEC_B_LOBBY 7.7), >= 2 m apart
#  leave (2 players)                             M1.4 the client disconnects in the countdown: WaitingToStart, team 1
#                                                inactive, no team 1 ship
#  forfeit (2 players)                           M5.2 the client pilots team 1's ship and disconnects: the ship stays, lives
#                                                unchanged; 30 s later team 1 forfeits, team 0 wins
#  three (3 players, DefaultExpectedPlayers 3)   M1.2 teams {2, 1}, join order 0 1 0, the solo team's LivesLeft 4
#  full1v1 (3 players, DefaultRules.TeamMode OneVsOne)   M1.3 the third join refused with "That match is full (1v1)."
#  four (4 players, DefaultExpectedPlayers 4)    M1.2 teams {2, 2}, join order 0 1 0 1; M6.2 every client's team / lives
#                                                view = the server's, lane update <= 0.05 ms per ship (dump lane_update_ms)
# Deviations from SPEC_B section 4 (the lead updates the spec):
#  * The play mode is written by the runner (set_play_mode.sh, editor closed), not by as_75: an inbox script runs inside
#    the editor, which writes its own copy of the ini back when it quits.
#  * A client "leaves" (M1.4, M5.2) with the console command `disconnect` in its own world (the same Logout /
#    PawnLeavingGame path as closing the window; PIE has no call to close one client window).
#  * M7.1 restarts with Aura.Match.Restart 2 s after Ended instead of waiting EndScreenSeconds (T3.3 times the automatic
#    restart in standalone).
#  * M8.2 counts sentinels from their Mass representation: instances of the world's instanced static mesh components
#    whose mesh or owner names "Sentinel", within 50 m of the ship, on each machine.
import json, math, os, re, time, traceback  # unreal = inbox namespace

_AS75_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(compile(open(os.path.join(_AS75_UE, 'as_70_matchlib.py')).read(), os.path.join(_AS75_UE, 'as_70_matchlib.py'), 'exec'), globals())

AS75_VERSION = 'as_75_pie_match_mp 2026-11-25'
AS75_MAP = 'StartupMap'
AS75_DEFAULT_SCENARIOS = {2: ('wait3', 'versus', 'practice', 'leave', 'forfeit'), 3: ('three', 'full1v1'), 4: ('four',)}
AS75_PARK = (0.0, -60000.0, -100000.0)
AS75_PILOT_COMP = '/Script/Aura.AirshipPilotComponent'
AS75_FLOOR = (-4000.0, 4000.0, -4000.0, 4000.0)


class B75(MBRun):
    TAG = 'b75'
    VERSION = AS75_VERSION
    TEMP = 'TEMP_AS75_'
    SKIPPED = {'M1.x_late_join': 'a PIE client cannot join an already running session (manual test, section 4.2)',
               'menu_end_to_end': 'host menu options and the pause menu buttons: manual (section 4.2)'}

    def __init__(self):
        g = globals()
        n = int(g.get('AS75_PLAYERS') or 2)
        self.cfg_in = {'players': n, 'scenarios': tuple(g.get('AS75_SCENARIOS') or AS75_DEFAULT_SCENARIOS.get(n, ())),
                       'only': tuple(g.get('AS75_ONLY') or ()), 'scheme': int(g.get('AS75_SCHEME', 3) if g.get('AS75_SCHEME') is not None else 3)}
        self.OUTDIR = os.path.join(MB_MATCH, 'b75_%dp' % n)
        MBRun.__init__(self)
        self.cfg.update(self.cfg_in)
        self.R['cfg'] = self.cfg
        self.sw = None
        self.cws = []
        self.P = []
        self.si = -1
        self.scen = None
        self.scen_wall = 0.0
        self.ptl = []
        self.gun_base = 1.0
        self.refused_seen = False

    # ------------------------------------------------------------------------------------------------- scenarios
    def scenario(self, name):
        """(class-default settings applied before this PIE, tests)"""
        n = self.cfg['players']
        if name == 'wait3':
            return {'DefaultExpectedPlayers': 3}, [('M1.0_waiting', 45, self.t_waiting)]
        if name == 'versus':
            return {'DefaultExpectedPlayers': n}, [
                ('M1.1_versus_start', 40, self.t_versus_start), ('M6.1_lane_replication', 15, self.t_lane_rep),
                ('M2.1_enemy_ship_f', 30, self.t_enemy_f), ('M2.3_console_board', 20, self.t_console_board),
                ('M2.2_rider_rule', 20, self.t_rider_rule), ('M3.1_friendly_fire', 150, self.t_ff),
                ('M4.1_sentinel_bullets', 40, self.t_bullets), ('M8.1_relevancy', 30, self.t_relevancy),
                ('M8.2_sentinels_seen', 70, self.t_sentinels), ('M7.2_client_hook', 130, self.t_client_hook),
                ('M9.1_teammates_low', 45, self.t_low_crew), ('M5.1_eliminated', 60, self.t_eliminate),
                ('M7.1_restart', 80, self.t_restart), ('M5.3_time_limit', 110, self.t_time_limit)]
        if name == 'practice':
            return {'DefaultRules.TeamMode': mb_team_mode('Practice')}, [('M1.1_practice', 30, self.t_practice)]
        if name == 'leave':
            return {'DefaultExpectedPlayers': 2}, [('M1.4_leave_countdown', 30, self.t_leave)]
        if name == 'forfeit':
            return {'DefaultExpectedPlayers': 2}, [('M5.2_forfeit', 90, self.t_forfeit)]
        if name == 'three':
            return {'DefaultExpectedPlayers': 3}, [('M1.2_three', 40, self.t_sizes)]
        if name == 'full1v1':
            return {'DefaultRules.TeamMode': mb_team_mode('OneVsOne')}, [('M1.3_full', 40, self.t_full)]
        if name == 'four':
            return {'DefaultExpectedPlayers': 4}, [('M1.2_four', 40, self.t_sizes), ('M6.2_four_huds', 40, self.t_four)]
        return {}, []

    def expected_clients(self):
        # full1v1: the third PIE client is refused at PreLogin
        return 1 if self.scen == 'full1v1' else self.cfg['players'] - 1

    # ------------------------------------------------------------------------------------------------- arm
    def arm(self):
        os.makedirs(self.OUTDIR, exist_ok=True)
        with open(self.path('log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (self.VERSION, self.R['armed_utc'], self.cfg))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = mb_editor_world()
        if AS75_MAP not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open /Game/Maps/StartupMap first' % (ew.get_path_name(), AS75_MAP))
            return False
        for k in ('gs', 'lane', 'settings', 'teamlib', 'ship', 'hud'):
            if unreal.load_class(None, MB_CLS[k]) is None:
                self.line('FAIL', '%s not found: the PR B C++ is not built into this editor' % MB_CLS[k])
                return False
        ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
        pls = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
        self.R['play_settings'] = pls
        if 'ListenServer' not in str(pls.get('PlayNetMode')) or int(pls.get('PlayNumberOfClients', 0)) != self.cfg['players'] or \
                str(pls.get('RunUnderOneProcess', True)).lower() in ('false', '0'):
            self.line('FAIL', 'play settings %s: want PIE_ListenServer, %d players, one process (set_play_mode.sh listen %d with the '
                              'editor closed)' % (pls, self.cfg['players'], self.cfg['players']))
            return False
        if not self.cfg['scenarios']:
            self.line('FAIL', 'no scenarios for %d players' % self.cfg['players'])
            return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 5 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        self.cfg['burrower'] = False
        self.snapshot_settings()
        try:
            cdo = unreal.get_default_object(unreal.load_class(None, MB_CLS['gun_ge']))
            self.gun_base = sum(float(m.get_editor_property('modifier_magnitude').get_editor_property('scalable_float_magnitude')
                                      .get_editor_property('value')) for m in cdo.get_editor_property('modifiers')) or 1.0
        except Exception:  # noqa: BLE001
            self.gun_base = 1.0
        self.R['setup']['gun_base_damage'] = self.gun_base
        mb_editor_cmd('Aura.Match.Enable 1')
        mb_editor_cmd('Aura.Lane.Debug 0')
        mb_editor_cmd('p.NetShowCorrections 1')
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(self.TEMP):
                    eas.destroy_actor(a)
            self.place_capture()
        except Exception:  # noqa: BLE001
            self.err('temp_capture')
        try:
            pc = unreal.load_class(None, MB_CLS['projectile_bp'])
            if pc is not None:
                fb = eas.spawn_actor_from_class(pc, unreal.Vector(*AS75_PARK), unreal.Rotator(0, 0, 0))
                fb.set_actor_label(self.TEMP + 'Fireball')
                fb.set_editor_property('initial_life_span', 0.0)
                pm = fb.get_editor_property('ProjectileMovementComponent')
                for n, v in (('initial_speed', 0.0), ('max_speed', 0.0), ('projectile_gravity_scale', 0.0), ('auto_activate', False)):
                    try:
                        pm.set_editor_property(n, v)
                    except Exception:  # noqa: BLE001
                        self.err('fireball_' + n)
        except Exception:  # noqa: BLE001
            self.err('temp_fireball')
        self.phase = 'next_scenario'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed: %d players, scenarios %s' % (self.cfg['players'], self.cfg['scenarios']))
        return True

    def restore(self):
        MBRun.restore(self)
        try:
            mb_editor_cmd('p.NetShowCorrections 0')
            mb_editor_cmd('log LogBeam Log')
        except Exception:  # noqa: BLE001
            self.err('restore_cvar')

    def apply_scenario_settings(self, sets):
        # every scenario starts from the arm snapshot, then its own values
        self.restore_settings()
        mb_editor_cmd('Aura.Match.Enable 1')
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS})
        except Exception:  # noqa: BLE001
            self.err('fixed_fps')
        mb_cdo('burrower_settings').set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
        for k, v in sets.items():
            self.set_setting(k, v)

    # ------------------------------------------------------------------------------------------------- loop
    def _tick(self):
        if self.phase == 'finished':
            return
        if self.phase == 'ending':
            self.end_tick()
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.phase == 'next_scenario':
            if les.is_in_play_in_editor():
                return
            self.si += 1
            if self.si >= len(self.cfg['scenarios']):
                self.finish('all scenarios done')
                return
            self.scen = self.cfg['scenarios'][self.si]
            sets, tests = self.scenario(self.scen)
            only = self.cfg.get('only')
            if only:
                tests = [t for i, t in enumerate(tests) if i == 0 or any(t[0].startswith(o) for o in only)]
            self.tests, self.ti, self.gen = tests, -1, None
            self.apply_scenario_settings(sets)
            self.R.setdefault('scenarios', []).append({'name': self.scen, 'settings': dict((k, str(v)) for k, v in sets.items()),
                                                       'tests': [t[0] for t in tests], 't': r(self.now)})
            self.line('INFO', '==== scenario %s: settings %s, tests %s' % (self.scen, sets, [t[0] for t in tests]))
            self.sw, self.cws, self.P, self.ptl, self.t_world0 = None, [], [], [], None
            self.subs, self.cap, self.cap_dead, self.dump_cache = {}, {}, {}, {}
            self.scen_wall = time.time()
            les.editor_request_begin_play()
            self.phase = 'wait_pie'
            return
        if self.phase == 'scenario_end':
            if les.is_in_play_in_editor():
                if time.time() - self.end_wall > 25.0:
                    self.finish('PIE did not stop after scenario %s' % self.scen)
                return
            self.t_base = self.now
            self.phase = 'next_scenario'
            return
        if self.phase == 'wait_pie':
            if self.find_worlds():
                self.phase = 'wait_actors'
                self.line('INFO', 'PIE worlds: server %s, clients %s' % (self.sw.get_path_name(), [w.get_path_name() for w in self.cws]))
            elif time.time() - self.scen_wall > 300:
                self.finish('listen PIE did not start in 300 s (%s)' % [(w.get_path_name(), self.role(w)) for w in self.pie_worlds(AS75_MAP)])
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        if not self.worlds_ok():
            # ServerTravel (M7.1): wait for the new server world and its clients
            self.D.setdefault('_gone_wall', time.time())
            if time.time() - self.D['_gone_wall'] > 150:
                self.finish('the worlds went away and did not come back in 150 s')
                return
            if self.find_worlds() and self.map_players():
                self.line('INFO', 'new worlds after travel: server %s, clients %s' % (self.sw.get_path_name(), [w.get_path_name() for w in self.cws]))
                self.t_base = self.now
                self.t_world0 = None
                self.subs, self.cap, self.cap_dead, self.dump_cache = {}, {}, {}, {}
                self.D.pop('_gone_wall', None)
                self.D['new_worlds'] = True
            return
        tw = self.wtime(self.sw)
        if self.t_world0 is None:
            self.t_world0 = tw
        self.now = self.t_base + tw - self.t_world0
        self.frames += 1
        self.log_poll()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        self.track(tw)
        if self.phase == 'wait_actors':
            if self.map_players() and self.set_lane_frame():
                self.phase = 'running'
                self.R['setup'][self.scen] = [dict((k, v if isinstance(v, (int, float, str, type(None))) else mb_name(v)) for k, v in p.items())
                                              for p in self.P]
            elif self.now > 45:
                self.check(self.scen + '_setup', 'FAIL', 'players not found after 45 s: %s' % self.R.get('setup_try'))
                self.end_scenario('players not found')
            return
        self.sample()
        self.run_tests()

    def run_tests(self):
        if self.gen is None and self.ti + 1 >= len(self.tests):
            self.end_scenario('tests done')
            return
        MBRun.run_tests(self)

    def finish(self, reason):
        MBRun.finish(self, reason)

    def end_scenario(self, why):
        self.line('INFO', 'scenario %s ends: %s' % (self.scen, why))
        self.cleanup_pie()
        self.write(True)
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and not self.user_play:
            les.editor_request_end_play()
        self.end_wall = time.time()
        self.phase = 'scenario_end'
        self.test = None

    def cleanup_pie(self):
        if self.sw is None or not valid(self.sw):
            return
        for c in ('Aura.Airship.InputClear', 'Aura.Airship.TurretFire 0', 'Aura.Lane.Debug 0'):
            try:
                unreal.SystemLibrary.execute_console_command(self.sw, c)
            except Exception:  # noqa: BLE001
                pass

    def write_skips(self):
        MBRun.write_skips(self)
        for s in self.cfg['scenarios'][self.si + 1:] if self.si >= 0 else self.cfg['scenarios']:
            self.R['checks'].setdefault('scenario_%s_not_run' % s, {'status': 'SKIP', 'summary': 'not reached (%s)' % self.R.get('reason'),
                                                                     'data': None, 't': r(self.now), 'test': '-'})

    # ------------------------------------------------------------------------------------------------- worlds and players
    def find_worlds(self):
        ws = self.pie_worlds(AS75_MAP)
        sv = [w for w in ws if self.role(w) == 'server']
        cl = sorted([w for w in ws if self.role(w) == 'client'], key=lambda w: w.get_path_name())
        if sv and len(cl) >= self.expected_clients():
            self.sw, self.cws = sv[0], cl
            return True
        return False

    def worlds_ok(self):
        if not valid(self.sw):
            return False
        ws = self.pie_worlds(AS75_MAP)
        return any(mb_same(w, self.sw) for w in ws)

    def map_players(self):
        """self.P: one dict per server player controller (index = Aura.Airship.* PlayerIndex): its world, local controller,
        player id, join order"""
        try:
            arr = self.player_states(self.sw)
            ids = [mb_pid(p) for p in arr]
            P = []
            for i in range(8):
                pc = unreal.GameplayStatics.get_player_controller(self.sw, i)
                if pc is None:
                    break
                ps = pc.get_editor_property('player_state')
                if ps is None:
                    return False
                pid = mb_pid(ps)
                rec = {'i': i, 'pcs': pc, 'pss': ps, 'id': pid, 'join': ids.index(pid) if pid in ids else None, 'name': ps.get_player_name()}
                if pc.is_local_controller():
                    rec['w'], rec['lpc'] = self.sw, pc
                else:
                    for cw in self.cws:
                        lpc = unreal.GameplayStatics.get_player_controller(cw, 0)
                        lps = lpc.get_editor_property('player_state') if lpc else None
                        if lps is not None and mb_pid(lps) == pid:
                            rec['w'], rec['lpc'] = cw, lpc
                            break
                if 'w' not in rec:
                    self.R['setup_try'] = 'no client world for player %d (id %s)' % (i, pid)
                    return False
                P.append(rec)
            if len(P) < 1 + self.expected_clients():
                self.R['setup_try'] = '%d player controllers, want %d' % (len(P), 1 + self.expected_clients())
                return False
            self.P = P
            return True
        except Exception:  # noqa: BLE001
            self.err('map_players')
            return False

    def set_lane_frame(self):
        if self.frame is not None:
            return True
        sps = unreal.GameplayStatics.get_all_actors_of_class(self.sw, mb_cls('spawner'))
        if not sps:
            self.R['setup_try'] = 'no path spawner'
            return False
        sp = sps[0]
        self.set_frame(self.loc(sp), self.yaw(sp), float(sp.get_editor_property('SegmentBoundsHalfWidth')) * float(sp.get_layout_scale()), sp.get_name())
        return True

    def track(self, tw):
        try:
            ph = self.phase_of(self.sw)
            if not self.ptl or self.ptl[-1][2] != ph:
                self.ptl.append((r(self.now, 3), r(tw, 3), ph, self.scen))
                self.R.setdefault('phase_timeline', []).append((r(self.now, 3), r(tw, 3), ph, self.scen))
        except Exception:  # noqa: BLE001
            self.err('track')

    def sample(self):
        if self.now - self.last_sample < 0.5:
            return
        self.last_sample = self.now
        try:
            s = {'t': r(self.now, 2), 'scen': self.scen, 'test': self.test, 'ph': self.ptl[-1][2] if self.ptl else None, 'ships': [], 'p': []}
            for sh in self.ships(self.sw, alive=True):
                t = self.tele(sh)
                s['ships'].append((sh.get_name()[-6:], self.ship_team(sh), r(self.uv(self.loc(sh)), 0), r(t.get('ForwardSpeedMS'), 1),
                                   self.lane_state(sh), r(t.get('Health'), 0)))
            for p in self.P:
                c = self.schar(p)
                s['p'].append((p['i'], self.ps_team(p['pss']), r(self.uv(self.loc(c)), 0) if c else None, self.health(c) if c else None))
            self.R['series'].append(s)
            if len(self.R['series']) > 6000:
                self.R['series'] = self.R['series'][::2]
        except Exception:  # noqa: BLE001
            self.err('sample')

    # ------------------------------------------------------------------------------------------------- per-player helpers
    def scmd(self, c):
        self.cmd(self.sw, c)

    def schar(self, p):
        """server copy of the player's character (the ship's pilot while he flies)"""
        try:
            pw = p['pcs'].get_controlled_pawn()
            if isinstance(pw, unreal.Character):
                return pw
            if pw is not None and isinstance(pw, unreal.AirshipPawn):
                return pw.get_pilot()
        except Exception:  # noqa: BLE001
            self.err('schar')
        return None

    def ochar(self, p):
        """the player's own machine's copy"""
        try:
            pw = p['lpc'].get_controlled_pawn()
            if isinstance(pw, unreal.Character):
                return pw
            if pw is not None and isinstance(pw, unreal.AirshipPawn):
                return pw.get_pilot()
        except Exception:  # noqa: BLE001
            self.err('ochar')
        return None

    def piloting(self, p, ship=None):
        try:
            pw = p['pcs'].get_controlled_pawn()
            return pw is not None and isinstance(pw, unreal.AirshipPawn) and (ship is None or mb_same(pw, ship))
        except Exception:  # noqa: BLE001
            return False

    def team(self, p):
        return self.ps_team(p['pss'])

    def tp(self, p, loc, yaw=None):
        """teleport both copies (the server's and the player's own) of an on-foot character"""
        yaw = self.frame['yaw'] if yaw is None else yaw
        for c in (self.schar(p), self.ochar(p) if not mb_same(p['w'], self.sw) else None):
            if c is not None:
                self.tp_char(c, loc, yaw)

    def foot(self, p, u=None, side=None, edge=False):
        """yield: player p alive, on foot, on a platform at u (default his own) on side (default his team's)"""
        c = yield from self.until(lambda: self.schar(p) if self.alive(self.schar(p)) else None, 20.0)
        if not c:
            return None
        if self.piloting(p):
            self.scmd('Aura.Airship.Exit %d' % p['i'])
            yield from self.wait(0.6)
        self.scmd('Aura.Airship.Dismount %d' % p['i'])
        yield from self.wait(0.2)
        c = self.schar(p)
        uu = self.uv(self.loc(c))[0] if u is None else u
        sd = side if side is not None else self.side_of(self.team(p))
        spot, _ = self.platform_spot(self.sw, uu, side=sd, edge=edge, c=c) if edge else self.platform_spot(self.sw, uu, near_v=sd * 8000.0, c=c)
        if spot is None:
            got = yield from self.until(lambda: self.platform_spot(self.sw, uu, near_v=sd * 8000.0, c=c)[0], 8.0)
            spot = got or None
        if spot is not None:
            self.tp(p, spot)
            yield from self.wait(0.6)
        return self.schar(p)

    def side_of(self, team):
        """the team's lane side this round (the dump's lane_side; before the countdown sets it: TeamLaneSide, swapped on odd
        rounds with bAlternateSides)"""
        d = self.dump(self.sw, 'state', 2.0)
        s = mb_get(d, 'teams', team, 'lane_side') if team in (0, 1) else None
        if not s:
            base = [1, -1][team] if team in (0, 1) else 1
            ri = mb_get(d, 'round') or 0
            s = -base if (ri % 2 and self.setting('bAlternateSides', True)) else base
        return int(s)

    def ship(self, team, w=None):
        """the team's living ship on the server (w None) or its copy in world w"""
        s = self.team_ship(self.sw, team)
        if w is None or s is None or mb_same(w, self.sw):
            return s
        return self.copy_in(w, s)

    def copy_in(self, w, a):
        try:
            cls = a.get_class()
            xs = list(unreal.GameplayStatics.get_all_actors_of_class(w, cls))
            m = next((x for x in xs if x.get_name() == a.get_name()), None)
            if m is not None:
                return m
            p = self.loc(a)
            return min(xs, key=lambda x: dist(self.loc(x), p)) if xs else None
        except Exception:  # noqa: BLE001
            self.err('copy_in')
            return None

    def char_copy_in(self, w, c):
        """the copy of a character in another world: the Character nearest its server location (within 5 m)"""
        try:
            p = self.loc(c)
            xs = [x for x in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Character) if dist(self.loc(x), p) < 500.0]
            return min(xs, key=lambda x: dist(self.loc(x), p)) if xs else None
        except Exception:  # noqa: BLE001
            return None

    def both_ships(self, timeout=15.0):
        """yield: both team ships alive on the server (a destroyed one comes back after ShipRespawnDelay); (s0, s1) or None"""
        ok = yield from self.until(lambda: self.ship(0) is not None and self.ship(1) is not None, timeout)
        return (self.ship(0), self.ship(1)) if ok else None

    def need_ships(self, key):
        """yield: both ships, or a FAIL for test key and None"""
        got = yield from self.both_ships()
        if not got:
            self.check(key, 'FAIL', 'no living ship for both teams within 15 s (team 0 %s, team 1 %s)' % (mb_name(self.ship(0)), mb_name(self.ship(1))))
        return got

    def on_deck(self, c, s):
        if c is None or s is None:
            return False
        if mb_same(self.base_owner(c), s) or mb_same(c.get_attach_parent_actor(), s):
            return True
        o, e = s.get_actor_bounds(True)
        p = self.loc(c)
        return abs(p[0] - o.x) <= e.x + 50.0 and abs(p[1] - o.y) <= e.y + 50.0 and abs(p[2] - o.z) <= e.z + 300.0

    def hull_aim(self, s, toward=None, z=250.0):
        loc = [0.0, 0.0, z]
        if toward is not None:
            d = unreal.MathLibrary.inverse_transform_location(s.get_actor_transform(), unreal.Vector(*toward))
            loc[1] = max(-600.0, min(600.0, d.y))
        return v3(unreal.MathLibrary.transform_location(s.get_actor_transform(), unreal.Vector(*loc)))

    def fire_gun(self, p, target_fn, seconds):
        """player p's own machine fires GA_GunShoot (IA_LMB held) with its view on target_fn()"""
        t0 = self.now
        while self.now - t0 < seconds:
            self.aim(p['w'], p['lpc'], target_fn())
            self.inject(p['w'], 'IA_LMB')
            yield

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

    def team_keys(self, ts):
        """the replicated team fields both views carry (server dump / a machine's Aura.Match.Status lines)"""
        keys = ('active', 'players', 'lives_left', 'bonus_lives', 'ships_lost', 'lane_side', 'eliminated')
        return [tuple((t or {}).get(k) for k in keys) for t in (ts or [])]

    def view_matches(self, p, tries=2):
        """yield: player p's machine's team view (Aura.Match.Status there) equals the server's dump; (equal, server, client)"""
        sv = cv = None
        for _ in range(tries):
            sv = self.team_keys(mb_get(self.dump(self.sw, 'view', 0.0), 'teams'))
            cv = self.team_keys((yield from self.status_teams(p['w'])))
            if sv and sv == cv:
                return True, sv, cv
            yield from self.wait(0.5)
        return False, sv, cv

    # ================================================================================================= tests
    def t_waiting(self):
        """M1.0"""
        host, cl = self.P[0], self.P[1]
        yield from self.wait(4.0)
        ph_s, ph_c = self.phase_of(self.sw), self.phase_of(cl['w'])
        pawns = [mb_name(p['pcs'].get_controlled_pawn()) for p in self.P]
        exp = self.result_of(self.sw).get('expected')
        self.xgrab('m1_0_waiting')
        self.scmd('Aura.Match.Start')
        ts = self.now
        cd = yield from self.until(lambda: self.phase_of(self.sw) == 'countdown', 2.0)
        ip = yield from self.until(lambda: self.phase_of(self.sw) == 'inprogress', 9.0)
        dt = self.now - ts if ip else None
        yield from self.wait(1.0)
        d = self.dump(self.sw, 'm1_0', 0.0)
        act = [mb_get(d, 'teams', i, 'active') for i in (0, 1)]
        teams = [self.team(p) for p in self.P]
        ok = (ph_s == 'waitingtostart' and ph_c == 'waitingtostart' and all(x is None for x in pawns) and exp == 3 and cd and dt is not None
              and abs(dt - float(self.setting('MatchStartDelay', 5.0))) <= 0.3 and act == [True, True] and sorted(teams) == [0, 1])
        self.check('M1.0_waiting', self.ok(ok), 'DefaultExpectedPlayers 3 with 2 in: phase server %s / client %s (want WaitingToStart), pawns %s '
                   '(want none), expected players %s; Aura.Match.Start: Countdown %s, InProgress %s s later (want 5 +-0.3), teams active %s, '
                   'player teams %s (want 1v1); match bar text in the x grab' % (ph_s, ph_c, pawns, exp, bool(cd), r(dt, 2), act, teams))

    def t_versus_start(self):
        """M1.1"""
        cd = next((x for x in self.ptl if x[2] == 'countdown'), None)
        ip = yield from self.until(lambda: self.phase_of(self.sw) == 'inprogress', 15.0)
        t_ip = self.now
        on = yield from self.until(lambda: all(self.on_deck(self.schar(p), self.ship(self.team(p))) for p in self.P), 1.0)
        dt_on = (self.now - t_ip) if on else None
        teams = [self.team(p) for p in self.P]
        sh = dict((t, self.ship(t)) for t in (0, 1))
        vs = dict((t, r(self.uv(self.loc(s))[1], 0) if s else None) for t, s in sh.items())
        want = dict((t, self.lane_v(self.side_of(t))) for t in (0, 1))
        same, sv, cv = yield from self.view_matches(self.P[1])
        for t, s in sh.items():
            if s is not None:
                self.wind_off(s)
                self.set_scheme(s, self.cfg['scheme'])
        self.xgrab('m1_1_versus_start')
        ok = (cd is not None and ip and dt_on is not None and teams[:2] == [0, 1] and all(sh.values())
              and all(vs[t] is not None and abs(vs[t] - want[t]) <= 200.0 for t in (0, 1)) and bool(same))
        self.check('M1.1_versus_start', self.ok(ok), 'countdown seen at %s, InProgress %s; every player on his own ship\'s deck %s s after the start '
                   '(want <= 1); teams by player index %s (want 0, 1); ships v %s (want %s: y +12500 / -32500 in round 0); the client\'s team '
                   'states = the server\'s within 0.5 s: %s (server %s, client %s)' % (
                       cd, bool(ip), r(dt_on, 2), teams, vs, dict((k, r(v, 0)) for k, v in want.items()), bool(same), sv, cv))

    def t_lane_rep(self):
        """M6.1"""
        if not (yield from self.need_ships('M6.1_lane_replication')):
            return
        cl = self.P[1]
        rows = []
        t0 = self.now
        while self.now - t0 < 4.0:
            for t in (0, 1):
                s = self.ship(t)
                c = self.copy_in(cl['w'], s) if s else None
                if s is None or c is None:
                    continue
                ts, tc = self.tele(s), self.tele(c)
                rows.append((t, self.lane_state(s), self.lane_state(c), ts.get('LaneLateralErrorM'), tc.get('LaneLateralErrorM')))
            yield
        st_eq = [x[1] == x[2] for x in rows]
        lat = [abs(float(x[3]) - float(x[4])) for x in rows if x[3] is not None and x[4] is not None]
        ok = rows and sum(st_eq) >= 0.9 * len(st_eq) and lat and max(lat) <= 0.5
        self.check('M6.1_lane_replication', self.ok(ok), 'client copies of both ships over 4 s: lane state equal in %d / %d samples (want ~all; one '
                   'hint interval of lag), lateral error difference max %s m (want <= 0.5)' % (sum(st_eq), len(st_eq), r(max(lat), 3) if lat else None),
                   {'rows': rows[::10]})

    def t_enemy_f(self):
        """M2.1"""
        if not (yield from self.need_ships('M2.1_enemy_ship_f')):
            return
        host, cl = self.P[0], self.P[1]
        s0, s1 = self.ship(0), self.ship(1)
        yield from self.foot(cl)
        c = self.schar(cl)
        dp, _ = self.deck_point(s0, -600.0, 250.0, c)
        self.tp(cl, dp, self.yaw(s0))
        yield from self.wait(0.6)
        t0 = self.now
        for _ in range(3):
            self.inject(cl['w'], 'IA_AirshipBoard')
            yield
        yield from self.wait(1.0)
        boarded_enemy = self.piloting(cl, s0)
        refl = [l[-160:] for _, l in self.log_since(t0, 'refused')]
        self.xgrab('m2_1_refused')
        self.scmd('Aura.Airship.Mount %d 0' % cl['i'])
        yield from self.wait(0.6)
        g0, g1 = mb_name(s0.get_station_gunner(0)), mb_name(s1.get_station_gunner(0)) if s1 else None
        mine = mb_same(s1.get_station_gunner(0), self.schar(cl)) if s1 else False
        self.scmd('Aura.Airship.Dismount %d' % cl['i'])
        yield from self.wait(0.6)
        c = self.schar(cl)
        dp, _ = self.deck_point(s1, -600.0, 250.0, c)
        self.tp(cl, dp, self.yaw(s1))
        yield from self.wait(0.6)
        for _ in range(3):
            self.inject(cl['w'], 'IA_AirshipBoard')
            yield
        own = yield from self.until(lambda: self.piloting(cl, s1), 2.0)
        self.scmd('Aura.Airship.Exit %d' % cl['i'])
        yield from self.wait(0.6)
        ok = not boarded_enemy and bool(refl) and mine and not mb_same(s0.get_station_gunner(0), c) and own
        self.check('M2.1_enemy_ship_f', self.ok(ok), 'client F on team 0\'s deck: boarded it %s (want no), refusal log %s (the server\'s "-> refused" line; the client\'s toast '
                   'line too once ClientUseRefused logs); Aura.Airship.Mount %d 0 next to team 0\'s ship: station 0 gunner team 0 %s / team 1 %s (want his own '
                   'ship\'s); F on his own deck boarded it %s' % (boarded_enemy, refl[:2], cl['i'], g0, g1, bool(own)))

    def t_console_board(self):
        """M2.3"""
        if not (yield from self.need_ships('M2.3_console_board')):
            return
        cl = self.P[1]
        s0, s1 = self.ship(0), self.ship(1)
        yield from self.foot(cl)
        c = self.schar(cl)
        dp, _ = self.deck_point(s0, -300.0, -250.0, c)
        self.tp(cl, dp, self.yaw(s0))
        yield from self.wait(0.6)
        prompts = []
        try:
            comp = cl['lpc'].get_component_by_class(unreal.load_class(None, AS75_PILOT_COMP))
            for _ in range(3):
                prompts.append(mb_name(comp.find_boardable_airship()))
                yield from self.wait(0.2)
        except Exception:  # noqa: BLE001
            self.err('find_boardable')
        s0c = self.copy_in(cl['w'], s0)
        self.scmd('Aura.Airship.Board %d' % cl['i'])
        on1 = yield from self.until(lambda: self.piloting(cl, s1), 1.5)
        on0 = self.piloting(cl, s0)
        self.scmd('Aura.Airship.Exit %d' % cl['i'])
        yield from self.wait(0.6)
        ok = bool(on1) and not on0 and not any(x is not None and s0c is not None and x == s0c.get_name() for x in prompts)
        self.check('M2.3_console_board', self.ok(ok), 'client standing on team 0\'s deck: Aura.Airship.Board %d took team 1\'s ship %s, team 0\'s %s '
                   '(want team 1\'s); the client\'s FindBoardableAirship %s (want never team 0\'s %s)' % (
                       cl['i'], bool(on1), on0, prompts, mb_name(s0c)))

    def t_rider_rule(self):
        """M2.2"""
        if not (yield from self.need_ships('M2.2_rider_rule')):
            return
        host, cl = self.P[0], self.P[1]
        s0 = self.ship(0)
        yield from self.foot(cl)
        c = self.schar(cl)
        dp, _ = self.deck_point(s0, 2850.0, 0.0, c)      # ahead of the turrets (mounts at hull x 2100)
        self.tp(cl, dp, self.yaw(s0))
        yield from self.wait(0.8)
        h0 = self.health(c)
        self.scmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.loc(c)))
        yield from self.wait(0.6)
        self.scmd('Aura.Airship.TurretFire 0')
        yield from self.wait(0.5)
        h1 = self.health(c)
        yield from self.foot(cl)
        yield from self.foot(host)
        hc = self.schar(host)
        self.tp(host, dp, self.yaw(s0))
        yield from self.wait(0.8)
        g0 = self.health(hc)
        self.scmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.loc(hc)))
        yield from self.wait(0.6)
        self.scmd('Aura.Airship.TurretFire 0')
        yield from self.wait(0.5)
        g1 = self.health(hc)
        ok = h0 is not None and h1 is not None and h1 < h0 and g0 == g1
        self.check('M2.2_rider_rule', self.ok(ok), 'enemy (client) on team 0\'s forward deck, TurretFire at him 0.6 s: health %s -> %s (want hit); '
                   'the host at the same spot on his own deck: %s -> %s (want unchanged)' % (h0, h1, g0, g1))

    def pair_on_platform(self, a, b, gap=1500.0):
        """yield: players a and b on foot on the same platform about gap apart (b ahead of a along u)"""
        ca = yield from self.foot(a)
        if ca is None:
            return None
        p = self.loc(ca)
        q = self.world(self.uv(p)[0] + gap, self.uv(p)[1], self.uv(p)[2])
        g = self.ground_at(self.sw, q[0], q[1], p[2] + 500.0, p[2] - 3000.0)
        if g is None:
            q = [p[0] + 400.0, p[1], p[2]]
        else:
            q = [g['p'][0], g['p'][1], g['p'][2] + self.hh(ca) + 20.0]
        yield from self.until(lambda: self.alive(self.schar(b)), 15.0)
        if self.piloting(b):
            self.scmd('Aura.Airship.Exit %d' % b['i'])
            yield from self.wait(0.6)
        self.tp(b, q)
        yield from self.wait(0.8)
        return self.schar(a), self.schar(b)

    def t_ff(self):
        """M3.1 + M3.2"""
        self.say('friendly fire: enemies, then teammates')
        host, cl = self.P[0], self.P[1]
        res = {}
        # (a) enemies: gun on the client = the GE value per hit
        got = yield from self.pair_on_platform(host, cl)
        if not got:
            self.check('M3.1_friendly_fire', 'FAIL', 'could not put the two players on a platform')
            return
        hc, cc = got
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 1.5,
                                          lambda: (self.aim(self.sw, host['pcs'], self.loc(self.schar(cl))), self.inject(self.sw, 'IA_LMB')))
        res['enemy_gun_drops'] = sorted(set(self.drops(tr)))
        # (b) the enemy hull and turret: the host on team 0's forward deck, team 1's ship (unpiloted, unprotected by now)
        # brought 50 m beside it on the outer side, where there is only sky
        s0, s1 = self.ship(0), self.ship(1)
        if s1 is not None and s0 is not None:
            dp, _ = self.deck_point(s0, 2850.0, 0.0, self.schar(host))
            self.tp(host, dp, self.yaw(s0))
            q0 = self.loc(s0)
            u0, v0, z0 = self.uv(q0)
            self.teleport(s1, self.world(u0, v0 + self.side_of(0) * 5000.0, z0), self.yaw(s0))
            yield from self.wait(0.8)
            p = self.loc(self.schar(host))
            res['ship1_protected'] = self.protected(s1)
            tr = yield from self.watch_health(lambda: self.ship_hp(s1), 1.5,
                                              lambda: (self.aim(self.sw, host['pcs'], self.hull_aim(s1, self.loc(self.schar(host)))), self.inject(self.sw, 'IA_LMB')))
            res['hull_drops'] = sorted(set(self.drops(tr)))
            ts = [t for t in (s1.get_editor_property('Turrets') or []) if valid(t)]
            if ts:
                t = min(ts, key=lambda x: dist(self.loc(x), self.loc(self.schar(host))))
                tr = yield from self.watch_health(lambda: t.get_health(), 1.5,
                                                  lambda: (self.aim(self.sw, host['pcs'], self.loc(t)), self.inject(self.sw, 'IA_LMB')))
                res['turret_drops'] = sorted(set(self.drops(tr)))
            self.scmd('Aura.Lane.Teleport 1 %.1f' % (u0 / 100.0))
        # (c) teammates
        self.scmd('Aura.Match.Team %d 0' % cl['i'])
        yield from self.wait(0.6)
        res['client_team'] = self.team(cl)
        got = yield from self.pair_on_platform(host, cl)
        hc, cc = got if got else (self.schar(host), self.schar(cl))
        tm = {}
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 1.5,
                                          lambda: (self.aim(self.sw, host['pcs'], self.loc(self.schar(cl))), self.inject(self.sw, 'IA_LMB')))
        tm['gun'] = self.drops(tr)
        self.scmd('log LogBeam Verbose')
        p0 = self.loc(self.schar(cl))
        tb = self.now
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 2.5,
                                          lambda: (self.aim(self.sw, host['pcs'], self.loc(self.schar(cl))),
                                                   self.inject(self.sw, 'IA_RMB') if self.now - tb < 1.5 else None))
        tm['beam_hit'] = self.drops(tr)
        tm['beam_moved_cm'] = r(dist(self.loc(self.schar(cl)), p0), 1)
        tm['beam_log'] = [l[-160:] for _, l in self.log_since(tb, 'LogBeam')][:2]
        q = self.loc(self.schar(cl))
        g = self.ground_at(self.sw, q[0] + 300.0, q[1], q[2], q[2] - 2000.0)
        tb = self.now
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 2.5,
                                          lambda: (self.aim(self.sw, host['pcs'], g['p'] if g else [q[0] + 300.0, q[1], q[2] - 90.0]),
                                                   self.inject(self.sw, 'IA_RMB') if self.now - tb < 1.5 else None))
        tm['beam_splash'] = self.drops(tr)
        self.scmd('log LogBeam Log')
        s0 = self.ship(0)
        if s0 is not None:
            for k, kill in (('ball_splash', False), ('ball_splash_ship_gone', True)):
                q = self.loc(self.schar(cl))
                src = s0 if not kill else self.ship(0)
                if src is None:
                    break
                start = [q[0] + 300.0, q[1] + 2000.0, q[2] + 300.0]
                hit = [q[0] + 300.0, q[1], q[2] - 80.0]
                v = [(hit[i] - start[i]) * (1.0 if kill else 2.0) for i in range(3)]
                try:
                    unreal.AirshipCannonball.spawn_test_cannonball(self.sw, mb_cls('ball_bp') or mb_cls('ball'), unreal.Vector(*start),
                                                                   unreal.Vector(*v), src, 60.0, 0.0)
                except Exception:  # noqa: BLE001
                    self.err('spawn_test_cannonball')
                if kill:
                    yield
                    src.destroy_actor()
                tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 2.0)
                tm[k] = self.drops(tr)
        # turret rounds from the team's own ship: the teammate 40 m ahead of its bow, in the air at lane height (he falls
        # about 5 m in the second of fire; the fall death needs 80 m below path height)
        s0 = yield from self.until(lambda: self.ship(0), 14.0)
        if s0 is not None:
            q = v3(unreal.MathLibrary.transform_location(s0.get_actor_transform(), unreal.Vector(4000.0, 0.0, 600.0)))
            self.tp(cl, q, self.yaw(s0) + 180.0)
            yield
            self.scmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.loc(self.schar(cl))))
            tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 0.8)
            self.scmd('Aura.Airship.TurretFire 0')
            tm['turret'] = self.drops(tr)
            yield from self.foot(cl)
        # the fireball: a parked BP_MyProjectile moved through the teammate with the host as its instigator
        fb = self.pie_temp(self.sw, 'Fireball')
        tm['fireball'] = None if fb is not None else 'no TEMP_AS75_Fireball in the server world'
        if fb is not None:
            yield from self.pair_on_platform(host, cl)
            try:
                fb.set_editor_property('instigator', self.schar(host))
            except Exception:  # noqa: BLE001
                self.err('fireball_instigator')
            q = self.loc(self.schar(cl))
            h0 = self.health(self.schar(cl))
            for k in range(-6, 7):
                fb.set_actor_location(unreal.Vector(q[0] + 100.0 * k, q[1], q[2]), False, True)
                yield
            tm['fireball'] = (h0, self.health(self.schar(cl)), 'projectile still there (not stopped)' if valid(fb) else 'projectile destroyed')
            if valid(fb):
                fb.set_actor_location(unreal.Vector(*AS75_PARK), False, True)
        # crew share: the host pilots team 0's ship, DamageShip 0 100
        s0 = yield from self.until(lambda: self.ship(0), 14.0)
        hc = self.schar(host)
        if s0 is not None and hc is not None:
            dp, _ = self.deck_point(s0, -300.0, 300.0, hc)
            self.tp(host, dp, self.yaw(s0))
            yield from self.wait(0.4)
            self.scmd('Aura.Airship.Board 0')
            yield from self.until(lambda: self.piloting(host, s0), 1.5)
            yield from self.until(lambda: not self.protected(s0), 16.0)
            ph0 = self.health(self.schar(host))
            self.scmd('Aura.Match.DamageShip 0 100')
            yield from self.wait(0.5)
            tm['crew_share'] = (ph0, self.health(self.schar(host)))
            self.scmd('Aura.Airship.Exit 0')
            yield from self.wait(0.6)
        res['teammates'] = tm
        none_hurt = all(not tm.get(k) for k in ('gun', 'beam_hit', 'beam_splash', 'ball_splash', 'ball_splash_ship_gone', 'turret'))
        fire_ok = isinstance(tm.get('fireball'), tuple) and tm['fireball'][0] == tm['fireball'][1] and 'still' in tm['fireball'][2]
        crew = tm.get('crew_share')
        crew_ok = crew is not None and crew[0] is not None and crew[1] is not None and abs((crew[0] - crew[1]) - 25.0) <= 0.5
        gd = float(self.setting('ShipDamageGunHit', 5.0))
        ok = (res['enemy_gun_drops'] == [round(self.gun_base, 3)] and res.get('hull_drops') == [round(gd, 3)] and res.get('turret_drops') == [round(gd, 3)]
              and res['client_team'] == 0 and none_hurt and fire_ok and (tm.get('beam_moved_cm') or 0.0) < 50.0 and crew_ok)
        self.check('M3.1_friendly_fire', self.ok(ok), 'enemies: host gun on the client drops %s (want the GE value %s each), on team 1\'s hull %s and '
                   'its turret %s (want %s each); teammates (Aura.Match.Team %d 0 -> %s): damage gun %s, beam hit %s (log %s), beam splash %s, '
                   'cannonball splash 3 m %s, with its ship destroyed in flight %s, team 0 turret rounds %s, fireball %s, beam knockback %s cm '
                   '(want < 50), crew share (host health before / after DamageShip 0 100 as pilot) %s (want -25)' % (
                       res['enemy_gun_drops'], self.gun_base, res.get('hull_drops'), res.get('turret_drops'), gd, cl['i'], res['client_team'],
                       tm.get('gun'), tm.get('beam_hit'), tm.get('beam_log'), tm.get('beam_splash'), tm.get('ball_splash'),
                       tm.get('ball_splash_ship_gone'), tm.get('turret'), tm.get('fireball'), tm.get('beam_moved_cm'), crew), res)
        # M3.2: friendly fire on, the same pair
        self.scmd('Aura.Match.Rules FF=1')
        yield from self.wait(0.5)
        got = yield from self.pair_on_platform(host, cl)
        tr = yield from self.watch_health(lambda: self.health(self.schar(cl)), 1.5,
                                          lambda: (self.aim(self.sw, host['pcs'], self.loc(self.schar(cl))), self.inject(self.sw, 'IA_LMB')))
        ff = self.drops(tr)
        self.scmd('Aura.Match.Rules FF=0')
        self.scmd('Aura.Match.Team %d 1' % cl['i'])
        yield from self.wait(0.6)
        self.check('M3.2_ff_on', self.ok(bool(ff) and all(abs(x - self.gun_base) < 1e-3 for x in ff)), 'Aura.Match.Rules FF=1: the teammate takes '
                   'the host\'s gun again: drops %s (want the GE value %s); FF=0 and the client back on team %s' % (ff, self.gun_base, self.team(cl)))

    def bullet(self, target_pt, side_dir):
        frm = [target_pt[0] + side_dir[0] * 2500.0, target_pt[1] + side_dir[1] * 2500.0, target_pt[2] + 300.0]
        self.scmd('Aura.MechSentinel.TestBullet %.0f %.0f %.0f %.0f %.0f %.0f 3' % tuple(frm + list(target_pt)))

    def t_bullets(self):
        """M4.1"""
        self.say('sentinel test bullets on team 1')
        if not (yield from self.need_ships('M4.1_sentinel_bullets')):
            return
        host, cl = self.P[0], self.P[1]
        s1 = self.ship(1)
        if s1 is None:
            self.check('M4.1_sentinel_bullets', 'FAIL', 'no team 1 ship')
            return
        side = self.side_of(1)
        out = [-math.sin(math.radians(self.frame['yaw'])) * side, math.cos(math.radians(self.frame['yaw'])) * side]
        ts = [t for t in (s1.get_editor_property('Turrets') or []) if valid(t)]
        t0 = ts[0] if ts else None
        res = {'tags_undriven': (s1.actor_has_tag('MechSentinelBulletTarget'), [t.actor_has_tag('MechSentinelBulletTarget') for t in ts])}
        h = self.ship_hp(s1)
        self.bullet(self.hull_aim(s1, None, 0.0), out)
        yield from self.wait(1.0)
        res['undriven_hull'] = (h, self.ship_hp(s1))
        if t0 is not None:
            h = t0.get_health()
            self.bullet(self.loc(t0), out)
            yield from self.wait(1.0)
            res['undriven_turret'] = (h, t0.get_health())
        yield from self.foot(cl)
        c = self.schar(cl)
        dp, _ = self.deck_point(s1, -300.0, 300.0, c)
        self.tp(cl, dp, self.yaw(s1))
        yield from self.wait(0.5)
        self.scmd('Aura.Airship.Board %d' % cl['i'])
        yield from self.until(lambda: self.piloting(cl, s1), 1.5)
        yield from self.wait(0.5)
        res['tags_driven'] = (s1.actor_has_tag('MechSentinelBulletTarget'), [t.actor_has_tag('MechSentinelBulletTarget') for t in ts])
        h = self.ship_hp(s1)
        self.bullet(self.hull_aim(s1, None, 0.0), out)
        yield from self.wait(1.0)
        res['driven_hull'] = (h, self.ship_hp(s1))
        if t0 is not None and valid(t0):
            h = t0.get_health()
            self.bullet(self.loc(t0), out)
            yield from self.wait(1.0)
            res['driven_turret'] = (h, t0.get_health())
        pc = self.schar(cl)
        if pc is not None:
            pc.destroy_actor()
            yield from self.wait(0.5)
            res['tags_pilot_char_destroyed'] = (s1.actor_has_tag('MechSentinelBulletTarget'), [t.actor_has_tag('MechSentinelBulletTarget') for t in ts if valid(t)])
            res['controller_on_ship'] = self.piloting(cl, s1)
        yield from self.until(lambda: self.alive(self.schar(cl)), 12.0)
        u = res
        ok = (u['undriven_hull'][0] == u['undriven_hull'][1] and (t0 is None or u.get('undriven_turret', (0, 0))[0] == u.get('undriven_turret', (0, 1))[1])
              and u['driven_hull'][0] is not None and abs(u['driven_hull'][0] - u['driven_hull'][1] - 3.0) <= 0.01
              and (t0 is None or (u.get('driven_turret') and u['driven_turret'][1] < u['driven_turret'][0]))
              and u.get('tags_pilot_char_destroyed', (False,))[0])
        self.check('M4.1_sentinel_bullets', self.ok(ok), 'team 1 ship undriven: tags %s, hull %s, turret %s (want unchanged); driven by the client: '
                   'tags %s, hull %s (want -3), turret %s (want damaged); pilot character destroyed on the server: tags %s (want on), controller '
                   'still on the ship %s' % (u['tags_undriven'], u['undriven_hull'], u.get('undriven_turret'), u.get('tags_driven'), u.get('driven_hull'),
                                              u.get('driven_turret'), u.get('tags_pilot_char_destroyed'), u.get('controller_on_ship')), u)

    def t_relevancy(self):
        """M8.1"""
        if not (yield from self.need_ships('M8.1_relevancy')):
            return
        host, cl = self.P[0], self.P[1]
        s0, s1 = self.ship(0), self.ship(1)
        yield from self.foot(cl)
        c = self.schar(cl)
        dp, _ = self.deck_point(s1, -300.0, 0.0, c)
        self.tp(cl, dp, self.yaw(s1))
        yield from self.foot(host)
        hc = self.schar(host)
        dp0, _ = self.deck_point(s0, 1200.0, 0.0, hc)
        self.tp(host, dp0, self.yaw(s0))
        yield from self.wait(2.0)
        d = dist(self.loc(self.schar(host)), self.loc(self.schar(cl)))
        exists = yield from self.until(lambda: self.char_copy_in(cl['w'], self.schar(host)), 3.0)
        h0 = self.health(self.schar(host))
        tgt = lambda: self.loc(self.char_copy_in(cl['w'], self.schar(host)) or self.schar(host))  # noqa: E731
        tr = yield from self.watch_health(lambda: self.health(self.schar(host)), 2.0,
                                          lambda: (self.aim(cl['w'], cl['lpc'], tgt()), self.inject(cl['w'], 'IA_LMB')))
        hits = self.drops(tr)
        ok = 30000.0 <= d <= 45500.0 and bool(exists) and bool(hits)
        self.check('M8.1_relevancy', self.ok(ok), 'host on team 0\'s deck %.0f m from the client on team 1\'s deck (want 300-450, +5 m for the '
                   'deck spots): the host\'s '
                   'character exists in the client\'s world %s; the client\'s gun on him: drops %s (want hits)' % (d / 100.0, bool(exists), hits))

    def sentinels_near(self, w, p, radius):
        """instances of the world's sentinel representation meshes within radius of p"""
        n = 0
        t = getattr(unreal, 'InstancedStaticMeshComponent', None)
        if t is None:
            return None
        for comp in unreal.ObjectIterator(t):
            try:
                if not mb_same(comp.get_world(), w):
                    continue
                gsm = getattr(comp, 'get_static_mesh', None)
                nm = (mb_name(comp.get_owner()) or '') + ' ' + (mb_name(gsm() if gsm else None) or '')
                if 'entinel' not in nm:
                    continue
                for i in range(min(int(comp.get_instance_count()), 3000)):
                    tr = comp.get_instance_transform(i, True)
                    if isinstance(tr, tuple):
                        tr = next((x for x in tr if isinstance(x, unreal.Transform)), None)
                    if tr is not None and dist(v3(tr.translation), p) <= radius:
                        n += 1
            except Exception:  # noqa: BLE001
                continue
        return n

    def t_sentinels(self):
        """M8.2"""
        self.say('host boards team 0, the client at the path centre, counting sentinels')
        if not (yield from self.need_ships('M8.2_sentinels_seen')):
            return
        host, cl = self.P[0], self.P[1]
        s0 = self.ship(0)
        yield from self.foot(host)
        hc = self.schar(host)
        dp, _ = self.deck_point(s0, -300.0, 300.0, hc)
        self.tp(host, dp, self.yaw(s0))
        yield from self.wait(0.4)
        self.scmd('Aura.Airship.Board 0')
        yield from self.until(lambda: self.piloting(host, s0), 1.5)
        yield from self.foot(cl, u=self.uv(self.loc(s0))[0], side=1)
        c = self.schar(cl)
        q = self.world(self.uv(self.loc(s0))[0], 0.0, 0.0)
        spot, _ = self.platform_spot(self.sw, self.uv(q)[0], near_v=0.0, c=c)
        if spot:
            self.tp(cl, spot)
        best = (0, None)
        t0 = self.now
        while self.now - t0 < 30.0:
            if int(self.now - t0) != self.D.get('_k'):
                self.D['_k'] = int(self.now - t0)
                ns = self.sentinels_near(self.sw, self.loc(s0), 5000.0)
                sc = self.copy_in(cl['w'], s0)
                nc = self.sentinels_near(cl['w'], self.loc(sc), 5000.0) if sc else None
                if (nc or 0) > best[0] or best[1] is None:
                    best = (nc or 0, ns)
                if nc:
                    break
            yield
        self.scmd('Aura.Airship.Exit 0')
        yield from self.wait(0.5)
        self.check('M8.2_sentinels_seen', self.ok(best[0] > 0), 'host flies team 0\'s ship in its lane, the client at the path centre (%.0f m '
                   'away): sentinels within 50 m of the ship, client %s / server %s (want > 0 on the client; R13)' % (
                       dist(self.loc(self.schar(cl)), self.loc(s0)) / 100.0, best[0], best[1]))

    def t_client_hook(self):
        """M7.2"""
        self.say('client ship hooks onto team 1')
        cl = self.P[1]
        tries = []
        for i in range(5):
            c = yield from self.foot(cl, edge=True)
            s1 = self.ship(1)
            if c is None or s1 is None:
                tries.append({'i': i, 'landed': False, 'why': 'no setup'})
                continue
            self.scmd('Aura.Lane.Teleport 1 %.1f' % ((self.uv(self.loc(c))[0] + 1000.0) / 100.0))
            yield from self.wait(1.5)
            s1 = self.ship(1)
            oc = self.ochar(cl)
            p = self.loc(oc)
            self.tp(cl, [p[0], p[1], p[2] + 300.0], self.yaw(oc))
            t0 = self.now
            landed = None
            s1c = self.copy_in(cl['w'], s1)
            while self.now - t0 < 4.0:
                self.aim(cl['w'], cl['lpc'], self.hull_aim(s1c or s1, self.loc(oc)))
                self.inject(cl['w'], 'IA_Shift')
                if self.on_deck(self.schar(cl), s1) and mb_same(self.base_owner(self.schar(cl)), s1):
                    landed = r(self.now - t0, 2)
                    break
                yield
            yield from self.wait(0.5)
            corr = len(self.log_since(t0, '*** Client: Error for'))
            rej = [l[-150:] for _, l in self.log_since(t0, 'ship hook', 'rejected')]
            tries.append({'i': i, 'landed': landed is not None, 't': landed, 'corrections': corr, 'rejected': rej})
            if i == 0:
                self.xgrab('m7_2_client_hook')
        land = [t for t in tries if t.get('landed')]
        ok = len(land) >= 4 and all(t.get('corrections', 0) <= 3 for t in tries)
        self.check('M7.2_client_hook', self.ok(ok), 'client ship hook onto its own cruising ship: %d / 5 landed (want >= 4), corrections per reel %s '
                   '(want <= 3), rejections %s' % (len(land), [t.get('corrections') for t in tries], [len(t.get('rejected') or []) for t in tries]), tries)

    def t_low_crew(self):
        """M9.1"""
        if not (yield from self.need_ships('M9.1_teammates_low')):
            return
        host, cl = self.P[0], self.P[1]
        self.scmd('Aura.Match.Team %d 0' % cl['i'])
        yield from self.wait(0.6)
        s0 = self.ship(0)
        yield from self.foot(cl)
        c = self.schar(cl)
        dp, _ = self.deck_point(s0, -600.0, 0.0, c)
        self.tp(cl, dp, self.yaw(s0))
        yield from self.wait(0.4)
        self.scmd('Aura.Airship.Mount %d 0' % cl['i'])
        yield from self.foot(host)
        hc = self.schar(host)
        dp, _ = self.deck_point(s0, 900.0, 0.0, hc)
        self.tp(host, dp, self.yaw(s0))
        yield from self.wait(0.6)
        self.scmd('Aura.Lane.Teleport 0 %.1f -150' % (self.uv(self.loc(s0))[0] / 100.0))
        a1 = []
        t0 = self.now
        while self.now - t0 < 10.0:
            a1.append((self.alive(self.schar(host)), self.alive(self.schar(cl))))
            yield
        self.scmd('Aura.Airship.Board 0')
        self.scmd('Aura.Airship.Dismount %d' % cl['i'])
        a2 = []
        t0 = self.now
        while self.now - t0 < 10.0:
            a2.append((self.alive(self.schar(host)), self.alive(self.schar(cl))))
            yield
        self.scmd('Aura.Airship.Exit 0')
        self.scmd('Aura.Match.Team %d 1' % cl['i'])
        self.scmd('Aura.Lane.Teleport 0 %.1f' % (self.uv(self.loc(s0))[0] / 100.0))
        yield from self.wait(0.6)
        ok = a1 and all(x[0] and x[1] for x in a1) and a2 and all(x[0] and x[1] for x in a2)
        self.check('M9.1_teammates_low', self.ok(ok), 'teammates, ship 150 m below path height: client gunner + host deck rider alive for 10 s %s; '
                   'host at the helm + client on the deck alive for 10 s %s' % (all(x[0] and x[1] for x in a1), all(x[0] and x[1] for x in a2)))

    def t_eliminate(self):
        """M5.1"""
        self.say('killing team 1 three times')
        host, cl = self.P[0], self.P[1]
        for p in self.P:
            yield from self.foot(p)
        kills = []
        for k in range(3):
            s1 = yield from self.until(lambda: self.ship(1) or self.phase_of(self.sw) == 'ended', 14.0)
            if self.phase_of(self.sw) == 'ended':
                break
            self.scmd('Aura.Match.KillShip 1')
            kills.append(r(self.now, 1))
            yield from self.wait(1.0)
        end_s = yield from self.until(lambda: self.phase_of(self.sw) == 'ended', 3.0)
        t_e = self.now
        end_c = yield from self.until(lambda: self.phase_of(cl['w']) == 'ended', 1.0)
        rs, rc = self.result_of(self.sw), self.result_of(cl['w'])
        yield from self.wait(1.0)
        self.xgrab('m5_1_victory_defeat')
        ok = end_s and end_c and rs.get('result') == 'teamwon' and rs.get('winner') == 0 and rc.get('winner') == 0 and rs.get('reason') == 'eliminated'
        self.check('M5.1_eliminated', self.ok(ok), 'team 1\'s ship killed at %s: Ended on the server %s, on the client within 1 s %s; server %s, '
                   'client %s (want TeamWon, team 0, Eliminated); VICTORY / DEFEAT in the x grabs' % (kills, bool(end_s), bool(end_c), rs, rc))

    def t_restart(self):
        """M7.1"""
        self.say('Aura.Match.Restart')
        if self.phase_of(self.sw) != 'ended':
            self.check('M7.1_restart', 'FAIL', 'the match is not Ended (M5.1 did not end it)')
            return
        before = dict((p['join'], (p['name'], self.team(p))) for p in self.P)
        d0 = self.dump(self.sw, 'before_restart', 0.0)
        rules0 = mb_get(d0, 'rules')
        yield from self.wait(2.0)
        self.scmd('Aura.Match.Restart')
        back = yield from self.until(lambda: self.D.get('new_worlds'), 70.0)
        if not back:
            self.check('M7.1_restart', 'FAIL', 'no new worlds within 70 s of Aura.Match.Restart (ServerTravel in listen PIE, R6: check by hand)')
            return
        ip = yield from self.until(lambda: self.phase_of(self.sw) in ('countdown', 'inprogress'), 30.0)
        yield from self.until(lambda: self.phase_of(self.sw) == 'inprogress', 15.0)
        yield from self.wait(1.0)
        d1 = self.dump(self.sw, 'after_restart', 0.0)
        after = dict((p['join'], (p['name'], self.team(p))) for p in self.P)
        nets = [mb_get(x, 'name') for x in (mb_get(d1, 'players') or [])]
        same_team = all(after.get(j, (None, None))[1] == t for j, (_, t) in before.items())
        s0 = self.ship(0)
        v0 = self.uv(self.loc(s0))[1] if s0 else None
        ok = (same_team and v0 is not None and v0 < 0.0 and mb_get(d1, 'round') == 1 and mb_get(d1, 'rules') == rules0)
        self.check('M7.1_restart', self.ok(ok), 'Aura.Match.Restart: both back %s; teams by join order before %s after %s (want the same; the '
                   'memory keys them by net id, join order where PIE gives none; players %s); team 0\'s ship at v %s (want < 0: sides swapped, y -32500); RoundIndex %s (want 1); '
                   'rules kept %s' % (bool(back), before, after, nets, r(v0, 0), mb_get(d1, 'round'), mb_get(d1, 'rules') == rules0))
        for t in (0, 1):
            s = self.ship(t)
            if s is not None:
                self.wind_off(s)

    def t_time_limit(self):
        """M5.3 (round 1, after M7.1)"""
        self.say('time limit 1 min')
        yield from self.until(lambda: self.phase_of(self.sw) == 'inprogress', 20.0)
        s1 = yield from self.until(lambda: self.ship(1), 15.0)
        yield from self.until(lambda: s1 is not None and not self.protected(s1), 17.0)
        self.scmd('Aura.Match.Rules TimeLimit=1')
        t_r = self.now
        self.scmd('Aura.Match.DamageShip 1 500')
        yield from self.wait(0.5)
        hp = self.ship_hp(s1) if s1 else None
        end = yield from self.until(lambda: self.phase_of(self.sw) == 'ended', 70.0)
        dt = (self.now - t_r) if end else None
        rs = self.result_of(self.sw)
        tw = [e for e in self.events_since(t_r, 'TimeWarning') if e['role'] in ('', 'server', 'listenserver', 'server-line')]
        ok = dt is not None and abs(dt - 60.0) <= 1.0 and rs.get('reason') == 'timelimit' and rs.get('winner') == 0 and len(tw) == 1
        self.check('M5.3_time_limit', self.ok(ok), 'Rules TimeLimit=1 then DamageShip 1 500 (hull %s): Ended %s s after the rule change (want 60 +-1), '
                   '%s (want TimeLimit, team 0); TimeWarning events on the server %d (want 1, at once) %s' % (hp, r(dt, 2), rs, len(tw), tw[:2]))

    def t_practice(self):
        """M1.1 practice variant"""
        yield from self.until(lambda: self.phase_of(self.sw) in ('countdown', 'inprogress'), 10.0)
        t0 = self.now
        got = yield from self.until(lambda: all(self.alive(self.schar(p)) for p in self.P), 10.0)
        dt = (self.now - t0) if got else None
        locs = [self.loc(self.schar(p)) if self.schar(p) else None for p in self.P]
        # SPEC_B_LOBBY 7.7: practice starts aboard team 0's ship (no pawn during the 5 s countdown)
        floor = [self.on_deck(self.schar(p), self.ship(0)) for p in self.P]
        gaps = [dist(locs[i], locs[j]) for i in range(len(locs)) for j in range(i + 1, len(locs)) if locs[i] and locs[j]]
        teams = [self.team(p) for p in self.P]
        ships = [self.ship_team(s) for s in self.ships(self.sw, alive=True)]
        ok = dt is not None and dt <= float(self.setting('MatchStartDelay', 5.0)) + 1.0 and all(floor) and gaps and min(gaps) >= 200.0 and all(t == 0 for t in teams)
        self.check('M1.1_practice', self.ok(ok), 'Teams=practice: every player has a pawn %s s after the countdown began (want <= the countdown + 1 s: '
                   'no pawn during it, SPEC_B_LOBBY 7.7), aboard team 0\'s ship %s, smallest gap %s cm (want >= 200), teams %s (want all 0), ship teams %s' % (
                       r(dt, 2), floor, r(min(gaps), 0) if gaps else None, teams, ships))

    def t_leave(self):
        """M1.4"""
        cl = self.P[1]
        cd = yield from self.until(lambda: self.phase_of(self.sw) == 'countdown', 10.0)
        yield from self.wait(1.0)
        self.cmd(cl['w'], 'disconnect')
        tl = self.now
        back = yield from self.until(lambda: self.phase_of(self.sw) == 'waitingtostart', 5.0)
        dt = (self.now - tl) if back else None
        yield from self.wait(1.0)
        d = self.dump(self.sw, 'm1_4', 0.0)
        a1 = mb_get(d, 'teams', 1, 'active')
        s1 = [s for s in self.ships(self.sw, alive=True) if self.ship_team(s) == 1]
        ok = cd and back and a1 is False and not s1
        self.check('M1.4_leave_countdown', self.ok(ok), 'Countdown %s; the client disconnects: WaitingToStart again %s s later, team 1 active %s '
                   '(want false), team 1 ships %d (want 0)' % (bool(cd), r(dt, 2), a1, len(s1)))

    def t_forfeit(self):
        """M5.2"""
        self.say('client pilots, then disconnects')
        cl = self.P[1]
        yield from self.until(lambda: self.phase_of(self.sw) == 'inprogress', 15.0)
        yield from self.wait(1.0)
        s1 = self.ship(1)
        self.scmd('Aura.Airship.Board %d' % cl['i'])
        on = yield from self.until(lambda: self.piloting(cl, s1), 2.0)
        ts0 = self.team_state(self.sw, 1, 0.0) or {}
        self.cmd(cl['w'], 'disconnect')
        tl = self.now
        yield from self.wait(2.0)
        still = valid(s1) and not s1.is_airship_dead()
        st = self.lane_state(s1) if still else None
        ts1 = self.team_state(self.sw, 1, 0.0) or {}
        end = yield from self.until(lambda: self.phase_of(self.sw) == 'ended', 40.0)
        dt = (self.now - tl) if end else None
        rs = self.result_of(self.sw)
        warn = self.events_since(tl, 'ForfeitWarning')
        ok = (on and still and st in ('parked', 'cruising', 'waiting') and ts0.get('lives_left') == ts1.get('lives_left') and end
              and rs.get('winner') == 0 and rs.get('reason') == 'forfeit' and dt is not None and abs(dt - float(self.setting('TeamEmptyForfeitSeconds', 30.0))) <= 2.0)
        self.check('M5.2_forfeit', self.ok(ok), 'client piloting team 1\'s ship %s disconnects: ship still there %s, lane state %s (want Parked / '
                   'Cruising), LivesLeft %s -> %s (want unchanged); Ended %s s later (want 30, +- the 0.5 s check), %s (want team 0, Forfeit); '
                   'ForfeitWarning %s' % (bool(on), still, st, ts0.get('lives_left'), ts1.get('lives_left'), r(dt, 1), rs, len(warn)))

    def t_sizes(self):
        """M1.2"""
        yield from self.until(lambda: self.phase_of(self.sw) == 'inprogress', 25.0)
        yield from self.wait(1.0)
        d = self.dump(self.sw, 'm1_2', 0.0)
        by_join = [t for _, t in sorted((p['join'], self.team(p)) for p in self.P if p['join'] is not None)]
        n = len(self.P)
        sizes = [by_join.count(0), by_join.count(1)]
        want_order = [0, 1, 0, 1][:n]
        lives = [mb_get(d, 'teams', i, 'lives_left') for i in (0, 1)]
        bonus = [mb_get(d, 'teams', i, 'bonus_lives') for i in (0, 1)]
        base = int(self.setting('DefaultRules.ShipLives', 3))
        if n == 3:
            ok = by_join == want_order and sizes == [2, 1] and lives == [base, base + 1] and bonus == [0, 1]
        else:
            ok = by_join == want_order and sizes == [2, 2] and lives == [base, base] and bonus == [0, 0]
        self.xgrab('m1_2_%dp' % n)
        self.check('M1.2_%dp_teams' % n, self.ok(ok), '%d players: teams by join order %s (want %s), sizes %s, LivesLeft %s, BonusLives %s (want the '
                   'smaller team +1 life with 3 players)' % (n, by_join, want_order, sizes, lives, bonus))

    def t_full(self):
        """M1.3"""
        t0 = self.now
        msg = yield from self.until(lambda: self.log_since(0.0, 'That match is full'), 25.0)
        n = len(self.player_states(self.sw))
        self.check('M1.3_full', self.ok(bool(msg) and n == 2), 'TeamMode OneVsOne, 3 PIE players: refusal %s (want "That match is full (1v1)."), '
                   'players in the match %d (want 2)' % ([l[-160:] for _, l in (msg or [])][:2], n))
        yield

    def t_four(self):
        """M6.2"""
        views = []
        for p in self.P[1:]:
            lps = p['lpc'].get_editor_property('player_state')
            eq, sv, cv = yield from self.view_matches(p)
            views.append({'i': p['i'], 'own_team_client': self.ps_team(lps), 'own_team_server': self.team(p), 'teams_equal': eq, 'client': cv})
        yield from self.wait(5.0)
        d = self.dump(self.sw, 'm6_2_timing', 0.0)
        lu = [(mb_get(s, 'name'), mb_get(s, 'lane_state'), mb_get(s, 'lane_update_ms')) for s in (mb_get(d, 'ships') or [])]
        ms = [x[2] for x in lu if x[2] is not None]
        self.xgrab('m6_2_four_huds')
        ok = all(v['own_team_client'] == v['own_team_server'] and v['teams_equal'] for v in views) and ms and max(ms) <= 0.05
        self.check('M6.2_four_huds', self.ok(ok), 'every client: own team on its machine vs the server and its team states vs the server\'s %s; lane '
                   'update per ship (name, state, ms) %s (want <= 0.05 ms); the four HUDs in the x grabs' % (views, lu))


_old75 = globals().get('AS75_RUN')
if _old75 is not None and _old75.phase not in ('finished',):
    print('an as_75 run is active (phase %s): stop it first (as_75x_stop.py)' % _old75.phase)
else:
    AS75_RUN = B75()
    _ok75 = AS75_RUN.arm()
    if not _ok75:
        AS75_RUN.restore()
        AS75_RUN.remove_temp()
        AS75_RUN.phase = 'finished'
    for _l in AS75_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_75s_status.py; results in %s)' % AS75_RUN.OUTDIR if _ok75 else 'FAIL: not armed'))
