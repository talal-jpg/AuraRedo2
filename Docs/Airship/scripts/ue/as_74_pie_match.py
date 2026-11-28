# as_74_pie_match.py - round 2 PR B PIE harness, STANDALONE part of the test plan (Docs/Airship/round2/SPEC_B.md section
# 4.1): one player = solo practice, fixed 30 fps game time, the test steps run frame by frame from a Slate post-tick
# callback (as_70_matchlib.MBRun; armed from the inbox like as_59, it returns at once and the world ticks between calls).
# Run (map open, no PIE, the PR B C++ built; normally through _AirshipWork_logs/run_b_pie.sh):
#   Docs/Airship/scripts/harness/inbox.sh 74 Docs/Airship/scripts/ue/as_74_pie_match.py 60
#   status: inbox.sh 74s Docs/Airship/scripts/ue/as_74s_status.py 30     stop: inbox.sh 74x Docs/Airship/scripts/ue/as_74x_stop.py 30
# Knobs (inbox globals, read at arm; they last for the editor session, so a wrapper sets every one):
#   AS74_MAP = 'StartupMap'   or 'L_AirshipTest' (the map that is open in the editor)
#   AS74_PASS = 'main'        which PIE session: 'main' (StartupMap: everything below but T2.12 / T4.1), 'easy' (T4.1:
#                             DefaultRules.SwarmDifficulty 0 before PIE), 'curved' (T2.12: the editor-level path spawner's
#                             MaxYawDeviation AS74_CURVE_YAW before PIE, put back after, never saved), 'lat' (L_AirshipTest
#                             with a TEMP MatchLaneOrigin: T1.1 / T1.2, the assist / park tests, T6.1, T8.2)
#   AS74_ONLY = ()            test-name prefixes for a short run ('settle' always runs), e.g. ('T2.4', 'T2.5')
#   AS74_SCHEME = 3           the team ship's control scheme (Point & Fly)
#   AS74_CURVE_YAW = 60.0
# Results: Saved/Match/b74_<pass>/ (b74_result.json with every check's measured values, b74_report.txt, b74_log.txt,
#   b74_status.txt, b74_restore.json, dump/ (Aura.Match.Dump files), captures/, xgrab/ (requests for xgrab_loop.sh)).
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, LevelEditorPlaySettings Standalone / 1 player,
# the UMyMatchSettings / UAirshipSettings / UBurrowerSettings class defaults (UBurrowerSettings.bEnabled off except in
# T5.2), the CVars Aura.Match.Enable (1 for the run) and Aura.Lane.Debug. TEMP_AS74_* actors in the editor level
# (SceneCapture2D, two movable BlockAll blocks parked 1 km below the map, the lat pass's MatchLaneOrigin target point) are
# removed after PIE; the map is never saved. The user's own Play ("Repeating last play command" in the log) is never stopped.
#
# Tests (main pass, in this order; game-second budgets in build_tests). Spec IDs as in section 4.1:
#  settle   T1.1 practice countdown 5.0 +-0.2 s, Teams[0] active / [1] not, player team 0 aboard team 0's ship
#           (SPEC_B_LOBBY 7.7: practice starts aboard); T1.2 one team
#           ship, team 0, at the lane spawn point +-1 m, yaw +-2 deg, Waiting / Cruising, protected
#  T2.3     Aura.Lane.Debug 1: the dump's lane points at v = +-(H + LaneClearance) within 50 cm; capture
#  T2.1     player on a platform at u 200 m: peak 27-29 m/s, settles 40 +-3 m ahead (TeamPace), overshoot <= 1 m, errors
#  T2.2     LaneMaxLead 0: settles at CruiseEndU +-3 m, <= 0.3 m/s, PathEnd, path end unchanged 20 s
#  T2.1b    player moved at 20 m/s along a row for 60 s: after 15 s the hull stays < 100 m from him
#  T2.9     the team-side platform edge walked 1 km (a spot every 50 m): gap to the hull's inner side (14-84 m, < 115 m)
#  T2.4     board a ship cruising at 6 m/s: Assist at once, 6 +-0.5 m/s for 10 s, broadside ball within 0.2 s
#  T2.5     Aura.Airship.Input 1 0 2 s: PilotedInLane within 1 frame; InputClear: Assist after 1.0 +-0.2 s
#  T2.5b    Point & Fly Q (IA_AirshipStrafe) 1 s from Assist: PilotedInLane within 2 frames, the ship turns
#  T2.6     strafe out: OutOfLane past 40 m; exit > 8 m/s: Parked + Drift, drift ends by 300 m in Hold, or the recall
#  T2.7     fly back into the zone, stop < 5 m/s, exit: Cruising within 0.5 s, 6 m/s within 3 s
#  T2.8     40 x 40 x 20 m block 150 m ahead: Waiting (Blocked) >= 5 m short, no damage; collision off: Cruising <= 1 s
#  T2.11    ship-sized block (30 x 23 x 20 m) in the lane: Bypass after 5 +-0.5 s, passes >= 5 m clear, back <= 1.5 m
#  T2.10    exit 200 m outside the lane, player 300 m away: Returning at 20 +-0.5 s (+ ShipReturning), Cruising <= 50 s
#  T5.1     board, fly 600 m ahead: no platform ahead of the player's last - 200 m destroyed, lead pawn null, path end same
#  T5.2     Burrower on, board: its target goes null, SpawnNow spawns none while aboard
#  T3.6     pilot aboard 150 m below path height 10 s: alive; off the deck: fall death within 8 s
#  T3.1     Aura.Match.KillShip 0: ShipsLost +1, ShipDestroyed, new ship +10.0 +-0.3 s at the team front +-5 m, protected
#  T3.2     pilot aboard, KillShip: ejected, fall death within 8 s, respawn 5 s later on a platform on the team's side
#  T3.4     right after a respawn: DamageShip, a free ship's turret round, a cannonball splash, the gun: no damage;
#           boarded: DamageShip -100; 15 s later unboarded: -100
#  T8.2     the Aura.Airship.Spawn ship: TeamId 255, NoLane, CanUseShip, boardable
#  T3.5     solo practice: 4 ships killed, still InProgress, ShipsLost +4, a new ship each time (HUD x grab)
#  T4.2     Aura.Match.Swarm 4: next wave Health / Damage x2.0 +-1 %, MaxAlive 500 x 1.6
#  T6.1     ship hook from the team-side platform edge onto the cruising ship: >= 4 of 5 land within 4 s, no rejection
#  T6.3     ship hook during the catch-up ramp and while easing into the cap: >= 4 of 5 each, Clamp Reel seen
#  T6.4     ship hook aimed at the own ship's turret: accepted, lands
#  T6.2     ship hook on a 25 m/s turning ship (debug input): the server ends the reel (log), no stuck root motion
#  T7.1     the match HUD widget exists; the x grabs requested through the run (match bar, LANE rows, recall, end)
#  T3.3     solo unlimited off: ships killed until Ended / PracticeOver, end panel; restart after 20 +-0.5 s with the
#           same rules (the reloaded world's dump)
# Easy pass: settle, T4.1. Curved pass: settle, T2.12 (Aura.Lane.Check >= 13 m both sides). Lat pass: settle, T2.4 ..
# T2.7, T6.1 (start platform to the lane ship), T8.2.
# Deviations from SPEC_B section 4.1 (the lead updates the spec):
#  * T2.11 uses a ship-sized block (30 x 23 x 20 m): with T2.8's 40 m wide cube, LaneBypassOffset 35 m leaves 3.7 m
#    between the hull and the cube (35 - 20 - 11.3), so ">= 5 m clear" could not pass by geometry.
#  * T3.6: Aura.Airship.Exit puts the pilot on the deck, where he rides (ship-borne, B9.6 skips him): the harness then
#    moves him 40 m off the side and times the fall death from there.
#  * T8.2 and T3.4 share the free ship (Aura.Airship.Spawn) the turret round comes from.
#  * T1.2's position is checked when the ship first exists (the countdown); a ship Waiting at TeamPace may move by the
#    start (its later position is in the data).
import json, math, os, time, traceback  # unreal = inbox namespace

_AS74_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(compile(open(os.path.join(_AS74_UE, 'as_70_matchlib.py')).read(), os.path.join(_AS74_UE, 'as_70_matchlib.py'), 'exec'), globals())

AS74_VERSION = 'as_74_pie_match 2026-11-28'
AS74_MAPS = {'StartupMap': '/Game/Maps/StartupMap', 'L_AirshipTest': '/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest'}
AS74_PARK = (0.0, 0.0, -100000.0)            # TEMP blocks wait 1 km under the map
AS74_FLOOR = (-4000.0, 4000.0, -4000.0, 4000.0)  # StartupMap's start floor (x, y bounds; Appendix C)
AS74_LAT_PLATFORM = 5000.0                   # L_AirshipTest start platform half size (as_22: 100 x 100 m, top z 0)


class B74(MBRun):
    TAG = 'b74'
    VERSION = AS74_VERSION
    TEMP = 'TEMP_AS74_'
    SKIPPED = {'T7.1_hud_text': 'NativePaint text is not readable from Python: the x grabs (xgrab/) are for the eye'}

    def __init__(self):
        g = globals()
        self.cfg_in = {'map': str(g.get('AS74_MAP') or 'StartupMap'), 'pass': str(g.get('AS74_PASS') or 'main'),
                       'only': tuple(g.get('AS74_ONLY') or ()), 'scheme': int(g.get('AS74_SCHEME', 3) if g.get('AS74_SCHEME') is not None else 3),
                       'curve_yaw': float(g.get('AS74_CURVE_YAW') or 60.0)}
        self.OUTDIR = os.path.join(MB_MATCH, 'b74_' + self.cfg_in['pass'])
        MBRun.__init__(self)
        self.cfg.update(self.cfg_in)
        self.R['cfg'] = self.cfg
        self.map_name = self.cfg['map']
        self.lat = self.map_name == 'L_AirshipTest'
        self.pc = None
        self.ptl = []
        self.first_ship = None
        self.free = None
        self.side0 = 1
        self.ball_seen = set()

    # ------------------------------------------------------------------------------------------------- tests
    def build_tests(self):
        p = self.cfg['pass']
        if p == 'easy':
            t = [('settle', 25, self.t_settle), ('T4.1_easy', 70, self.t_easy)]
        elif p == 'curved':
            t = [('settle', 25, self.t_settle), ('T2.12_curve', 150, self.t_curve)]
        elif p == 'lat':
            t = [('settle', 25, self.t_settle), ('T2.4_assist', 30, self.t_assist), ('T2.5_input', 20, self.t_input),
                 ('T2.6_out', 50, self.t_out), ('T2.7_park', 50, self.t_park), ('T6.1_hook', 100, self.t_hook),
                 ('T8.2_free', 25, self.t_free)]
        else:
            t = [('settle', 25, self.t_settle), ('T2.3_debug', 10, self.t_debug), ('T2.1_pace', 75, self.t_pace),
                 ('T2.2_end', 70, self.t_end), ('T2.1b_run', 90, self.t_run), ('T2.9_edge', 160, self.t_edge),
                 ('T2.4_assist', 30, self.t_assist), ('T2.5_input', 20, self.t_input), ('T2.5b_strafe', 15, self.t_strafe),
                 ('T2.6_out', 50, self.t_out), ('T2.7_park', 50, self.t_park), ('T2.8_block', 75, self.t_block),
                 ('T2.11_bypass', 110, self.t_bypass), ('T2.10_recall', 95, self.t_recall), ('T5.1_lead', 50, self.t_lead),
                 ('T5.2_burrower', 45, self.t_burrower), ('T3.6_low', 50, self.t_low), ('T3.1_kill', 45, self.t_kill),
                 ('T3.2_eject', 50, self.t_eject), ('T3.4_protect', 100, self.t_protect), ('T8.2_free', 25, self.t_free),
                 ('T3.5_unlimited', 80, self.t_unlimited), ('T4.2_swarm', 12, self.t_swarm4), ('T6.1_hook', 100, self.t_hook),
                 ('T6.3_reel_lane', 170, self.t_reel_lane), ('T6.4_turret', 60, self.t_hook_turret),
                 ('T6.2_drift', 45, self.t_hook_drift), ('T7.1_hud', 8, self.t_hud), ('T3.3_over', 130, self.t_over)]
        only = self.cfg.get('only')
        if only:
            t = [x for x in t if x[0] == 'settle' or any(x[0].startswith(o) for o in only)]
        return t

    # ------------------------------------------------------------------------------------------------- arm / restore
    def arm(self):
        os.makedirs(self.OUTDIR, exist_ok=True)
        with open(self.path('log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (self.VERSION, self.R['armed_utc'], self.cfg))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = mb_editor_world()
        if self.map_name not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open %s first' % (ew.get_path_name(), self.map_name, AS74_MAPS.get(self.map_name)))
            return False
        for k in ('gs', 'lane', 'settings', 'teamlib', 'ship', 'hud'):
            if unreal.load_class(None, MB_CLS[k]) is None:
                self.line('FAIL', '%s not found: the PR B C++ is not built into this editor' % MB_CLS[k])
                return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 4 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        self.tests = self.build_tests()
        self.R['test_plan'] = [(n, b) for n, b, _ in self.tests]
        self.cfg['burrower'] = False
        self.snapshot_settings()
        try:
            ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
            self.orig['play'] = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients'])
            tl_set(ps, {'PlayNetMode': 'PIE_Standalone', 'PlayNumberOfClients': 1})
        except Exception:  # noqa: BLE001
            self.err('play_settings')
        mb_editor_cmd('Aura.Match.Enable 1')
        mb_editor_cmd('Aura.Lane.Debug 0')
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(self.TEMP):
                    eas.destroy_actor(a)
            self.place_capture()
            self.place_block('Block40', (40.0, 40.0, 20.0), AS74_PARK)
            self.place_block('BlockShip', (30.0, 23.0, 20.0), (0.0, 30000.0, -100000.0))
            if self.lat:
                tp = eas.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(0.0, 0.0, 1400.0), unreal.Rotator(0, 0, 0))
                tp.set_actor_label(self.TEMP + 'LaneOrigin')
                tp.tags = [unreal.Name('MatchLaneOrigin')]
                self.set_setting('FallbackLaneHalfWidth', 5000.0)
        except Exception:  # noqa: BLE001
            self.err('temp_actors')
        if self.cfg['pass'] == 'easy':
            self.set_setting('DefaultRules.SwarmDifficulty', 0)
        if self.cfg['pass'] == 'curved':
            try:
                sp = [a for a in eas.get_all_level_actors() if mb_isa(a, 'spawner')]
                self.orig['curve'] = [(a.get_path_name(), float(a.get_editor_property('MaxYawDeviation'))) for a in sp]
                for a in sp:
                    a.set_editor_property('MaxYawDeviation', float(self.cfg['curve_yaw']))
                self.line('INFO', 'editor-level spawner MaxYawDeviation %s -> %.0f (TEMP, put back after PIE, not saved): %s' % (
                    [x[1] for x in self.orig['curve']], self.cfg['curve_yaw'], [x[0] for x in self.orig['curve']]))
            except Exception:  # noqa: BLE001
                self.err('curve_setup')
        with open(self.path('restore.json'), 'w') as f:
            json.dump(dict((k, str(v)) for k, v in self.orig.items()), f, indent=1)
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed (%s pass on %s); standalone PIE requested; %d tests, at most %d game s' % (
            self.cfg['pass'], self.map_name, len(self.tests), sum(b for _, b, _ in self.tests)))
        return True

    def restore(self):
        MBRun.restore(self)
        try:
            if 'play' in self.orig:
                ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
                tl_set(ps, {'PlayNetMode': str(self.orig['play'].get('PlayNetMode', 'PIE_Standalone')).split('.')[-1],
                            'PlayNumberOfClients': int(self.orig['play'].get('PlayNumberOfClients', 1))})
        except Exception:  # noqa: BLE001
            self.err('restore_play')
        try:
            for p, v in self.orig.get('curve') or []:
                a = unreal.find_object(None, p)
                if a is not None:
                    a.set_editor_property('MaxYawDeviation', v)
            if self.orig.get('curve'):
                self.line('INFO', 'editor-level spawner MaxYawDeviation put back: %s' % [x[1] for x in self.orig['curve']])
        except Exception:  # noqa: BLE001
            self.err('restore_curve')

    def cleanup_pie(self):
        if self.w is None or not valid(self.w):
            return
        for c in ('Aura.Airship.InputClear', 'Aura.Airship.TurretFire 0', 'Aura.Lane.Debug 0'):
            try:
                unreal.SystemLibrary.execute_console_command(self.w, c)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------------------------------------- loop
    def _tick(self):
        if self.phase == 'finished':
            return
        if self.phase == 'ending':
            self.end_tick()
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.phase == 'wait_pie':
            ws = self.pie_worlds(self.map_name)
            if ws:
                self.w = ws[0]
                self.phase = 'wait_actors'
                self.line('INFO', 'PIE world %s' % self.w.get_path_name())
            elif time.time() - self.wall0 > 300:
                self.finish('PIE did not start in 300 s')
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        ws = self.pie_worlds(self.map_name)
        if not valid(self.w) or not any(mb_same(x, self.w) for x in ws):
            # a map reload (T3.3's restart): wait for the new world; the harness clock stands still in between
            if not ws:
                self.D.setdefault('_gone_wall', time.time())
                if time.time() - self.D['_gone_wall'] > 120:
                    self.finish('the PIE world went away and none came back in 120 s')
                return
            self.on_new_world(ws[0])
        tw = self.wtime(self.w)
        if self.t_world0 is None:
            self.t_world0 = tw
            self.R['setup'].setdefault('world_time_at_first_frame', []).append(r(tw, 3))
        self.now = self.t_base + tw - self.t_world0
        self.frames += 1
        self.log_poll()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        self.track(tw)
        if self.phase == 'wait_actors':
            if self.find_actors():
                self.phase = 'running'
            elif self.now > 45:
                self.finish('actors not found after 45 s: %s' % self.R.get('setup_try'))
            return
        self.sample()
        self.run_tests()

    def on_new_world(self, w):
        self.line('INFO', 'new PIE world %s (map reload)' % w.get_path_name())
        self.t_base = self.now
        self.t_world0 = None
        self.w = w
        self.subs, self.cap, self.cap_dead, self.dump_cache = {}, {}, {}, {}
        self.pc = None
        self.D.pop('_gone_wall', None)
        self.D['new_world'] = w.get_path_name()

    def track(self, tw):
        """phase timeline (T1.1) and the first sight of each ship"""
        try:
            ph = self.phase_of(self.w)
            if not self.ptl or self.ptl[-1][2] != ph:
                self.ptl.append((r(self.now, 3), r(tw, 3), ph))
            for s in self.ships(self.w):
                n = s.get_name()
                if n not in self.seen_ships:
                    self.seen_ships.add(n)
                    rec = {'name': n, 't': r(self.now, 3), 'wt': r(tw, 3), 'team': self.ship_team(s), 'loc': r(self.loc(s), 1),
                           'yaw': r(self.yaw(s), 2), 'phase': ph, 'lane': self.lane_state(s), 'protected': self.protected(s)}
                    self.R.setdefault('ships_seen', []).append(rec)
                    if rec['team'] == 0 and self.first_ship is None:
                        self.first_ship = rec
        except Exception:  # noqa: BLE001
            self.err('track')

    def find_actors(self):
        try:
            self.pc = unreal.GameplayStatics.get_player_controller(self.w, 0)
            c = self.me()
            gs = self.gs(self.w)
            if self.lat:
                o = self.pie_temp(self.w, 'LaneOrigin')
                fr = (self.loc(o), self.yaw(o), float(self.setting('FallbackLaneHalfWidth', 5000.0)), 'TEMP MatchLaneOrigin') if o else None
            else:
                sps = unreal.GameplayStatics.get_all_actors_of_class(self.w, mb_cls('spawner'))
                sp = sps[0] if sps else None
                fr = None
                if sp is not None:
                    H = float(sp.get_editor_property('SegmentBoundsHalfWidth')) * float(sp.get_layout_scale())
                    fr = (self.loc(sp), self.yaw(sp), H, sp.get_name())
            self.R['setup_try'] = {'pc': bool(self.pc), 'char': bool(c), 'gs': bool(gs), 'frame': bool(fr)}
            if self.pc and c and gs and fr:
                self.set_frame(*fr)
                try:
                    self.side0 = int(mb_get(self.dump(self.w, 'setup'), 'teams', 0, 'lane_side') or 0) or 1
                except Exception:  # noqa: BLE001
                    self.side0 = 1
                self.R['setup'].update({'world': self.w.get_path_name(), 'char': c.get_name(), 'side0': self.side0,
                                        'char_loc': r(self.loc(c), 0)})
                return True
        except Exception:  # noqa: BLE001
            self.err('find_actors')
        return False

    def sample(self):
        if self.now - self.last_sample < 0.2:
            return
        self.last_sample = self.now
        try:
            s = {'t': r(self.now, 2), 'test': self.test, 'ph': self.ptl[-1][2] if self.ptl else None}
            sh = self.ship0()
            if sh is not None:
                t = self.tele(sh)
                s['S'] = {'n': sh.get_name()[-6:], 'uv': r(self.uv(self.loc(sh)), 0), 'v': r(t.get('ForwardSpeedMS'), 2),
                          'ls': self.lane_state(sh), 'cl': t.get('LaneClampName'), 'lat': r(t.get('LaneLateralErrorM'), 2),
                          'vert': r(t.get('LaneVerticalErrorM'), 2), 'tgt': r(t.get('LaneTargetSpeedMS'), 2), 'hp': r(t.get('Health'), 1),
                          'mode': t.get('UnpilotedModeName'), 'rec': r(t.get('RecallInS'), 1), 'prot': r(t.get('ProtectionLeftS'), 1)}
            c = self.me()
            if c is not None:
                p = self.loc(c)
                s['C'] = {'uv': r(self.uv(p), 0), 'hp': self.health(c), 'att': mb_name(c.get_attach_parent_actor()),
                          'base': mb_name(self.base_owner(c)), 'mm': self.move_mode(c)}
            self.R['series'].append(s)
            if len(self.R['series']) > 9000:
                self.R['series'] = self.R['series'][::2]
        except Exception:  # noqa: BLE001
            self.err('sample')

    # ------------------------------------------------------------------------------------------------- helpers
    def me(self):
        """the player's character (the ship's pilot while he flies)"""
        try:
            if self.pc is None or not valid(self.pc):
                self.pc = unreal.GameplayStatics.get_player_controller(self.w, 0)
            p = self.pc.get_controlled_pawn()
            if isinstance(p, unreal.Character):
                return p
            if p is not None and isinstance(p, unreal.AirshipPawn):
                return p.get_pilot()
        except Exception:  # noqa: BLE001
            self.err('me')
        return None

    def piloting(self):
        try:
            return isinstance(self.pc.get_controlled_pawn(), unreal.AirshipPawn)
        except Exception:  # noqa: BLE001
            return False

    def ship0(self):
        return self.team_ship(self.w, 0)

    def aboard(self, c, s):
        """c rides ship s (its base, its attach parent, or inside its bounds): practice starts aboard (SPEC_B_LOBBY 7.7)"""
        if c is None or s is None:
            return False
        if mb_same(self.base_owner(c), s) or mb_same(c.get_attach_parent_actor(), s):
            return True
        o, e = s.get_actor_bounds(True)
        p = self.loc(c)
        return abs(p[0] - o.x) <= e.x + 50.0 and abs(p[1] - o.y) <= e.y + 50.0 and abs(p[2] - o.z) <= e.z + 300.0

    def u_of(self, a):
        return self.uv(self.loc(a))[0]

    def lat_of(self, s, t=None):
        """ship minus lane, sideways (cm): the telemetry's, else from the straight lane"""
        t = t if t is not None else self.tele(s)
        if t.get('LaneLateralErrorM') is not None:
            return float(t['LaneLateralErrorM']) * 100.0
        return self.uv(self.loc(s))[1] - self.lane_v(self.side0)

    def lanes(self, max_age=1.0):
        """LaneStartU / PathEndU / CruiseEndU (cm) from the server's dump"""
        return self.lanes_of(self.dump(self.w, 'state', max_age))

    def stand_spot(self, u, edge=False):
        """a point to stand on at progress u: a real platform (StartupMap) or the start platform (L_AirshipTest)"""
        c = self.me()
        if self.lat:
            hh = self.hh(c) if c is not None else 90.0
            x = max(-AS74_LAT_PLATFORM + 500.0, min(AS74_LAT_PLATFORM - 500.0, u))
            y = self.side0 * (AS74_LAT_PLATFORM - 150.0) if edge else -2500.0
            return [x, y, 0.0 + hh + 20.0], None
        return self.platform_spot(self.w, u, side=self.side0 if edge else None, edge=edge, c=c)

    def foot(self, u=None, edge=False):
        """yield until the player is alive and on foot on a platform at u (his own u by default); returns the character"""
        c = yield from self.until(lambda: self.me() if self.alive(self.me()) else None, 20.0)
        if not c:
            return None
        if self.piloting():
            self.cmd(self.w, 'Aura.Airship.Exit 0')
            yield from self.wait(0.6)
            c = self.me()
        uu = self.u_of(c) if u is None else u
        spot, _ = self.stand_spot(uu, edge)
        if spot is None:
            # the platforms there may still be generating (PCG)
            got = yield from self.until(lambda: self.stand_spot(uu, edge)[0], 8.0)
            spot = got if got else None
        if spot is not None:
            self.tp_char(c, spot, self.frame['yaw'])
            yield from self.wait(0.5)
        else:
            self.line('WARN', 'no platform to stand on near u %.0f m' % (uu / 100.0))
        return c

    def board(self):
        """yield: Aura.Airship.Board 0, True once the player flies a ship"""
        self.cmd(self.w, 'Aura.Airship.Board 0')
        ok = yield from self.until(self.piloting, 1.5)
        return bool(ok)

    def lane_teleport(self, u_cm, dz_m=None):
        self.cmd(self.w, 'Aura.Lane.Teleport 0 %.1f%s' % (u_cm / 100.0, '' if dz_m is None else ' %.1f' % dz_m))

    def new_ship(self, team, before):
        ss = [s for s in self.ships(self.w, alive=True) if self.ship_team(s) == team and s.get_name() not in before]
        return ss[-1] if ss else None

    def names(self):
        return set(s.get_name() for s in self.ships(self.w))

    def balls(self):
        try:
            return [b for b in unreal.GameplayStatics.get_all_actors_of_class(self.w, mb_cls('ball')) if valid(b)]
        except Exception:  # noqa: BLE001
            return []

    def kill_and_respawn(self, timeout=14.0):
        """yield: Aura.Match.KillShip 0, then the new team 0 ship; returns (old, new, kill time, new time)"""
        old = self.ship0()
        before = self.names()
        t_k = self.now
        self.cmd(self.w, 'Aura.Match.KillShip 0')
        new = yield from self.until(lambda: self.new_ship(0, before), timeout)
        return old, new, t_k, (self.now if new else None)

    def hook_try(self, c, s, aim_fn, limit=4.0):
        """one ship hook: the character in the air, the view at aim_fn(), IA_Shift held until he stands on s or limit.
        Returns {landed, t, rejected, ended, clamp_reel}"""
        t0 = self.now
        p = self.loc(c)
        self.tp_char(c, [p[0], p[1], p[2] + 300.0], self.yaw(c))
        res = {'landed': False, 't': None, 'start_gap_cm': r(self.hull_gap(s, p), 0) if valid(s) else None, 'clamp_reel': False}
        while self.now - t0 < limit:
            if not valid(s):
                break
            self.aim(self.w, self.pc, aim_fn())
            self.inject(self.w, 'IA_Shift')
            if mb_nz(self.tele(s).get('LaneClampName')) == 'reel':
                res['clamp_reel'] = True
            if mb_same(self.base_owner(c), s) or mb_same(c.get_attach_parent_actor(), s):
                res['landed'], res['t'] = True, r(self.now - t0, 2)
                break
            yield
        yield from self.wait(0.4)
        res['rejected'] = [l[-160:] for _, l in self.log_since(t0, 'ship hook', 'rejected')]
        res['ended'] = [l[-160:] for _, l in self.log_since(t0, 'ship reel', 'ended by the server')]
        res['mode_after'] = self.move_mode(c)
        return res

    def hull_aim(self, s, c=None, local=(0.0, 0.0, 250.0)):
        """a hull point (hull space) toward the character's side, for the crosshair"""
        loc = list(local)
        if c is not None:
            d = unreal.MathLibrary.inverse_transform_location(s.get_actor_transform(), unreal.Vector(*self.loc(c)))
            loc[1] = max(-600.0, min(600.0, d.y))
        return v3(unreal.MathLibrary.transform_location(s.get_actor_transform(), unreal.Vector(*loc)))

    # ================================================================================================= tests
    def t_settle(self):
        """T1.1 / T1.2"""
        self.say('waiting for InProgress')
        yield from self.until(lambda: self.ptl and self.ptl[-1][2] == 'inprogress', 15.0)
        yield from self.wait(1.0)
        s = self.ship0()
        if s is not None:
            self.wind_off(s)
            self.set_scheme(s, self.cfg['scheme'])
        d = self.dump(self.w, 'settle')
        self.keep_dump('settle', d)
        delay = float(self.setting('MatchStartDelay', 5.0))
        cd = next((x for x in self.ptl if x[2] == 'countdown'), None)
        ip = next((x for x in self.ptl if x[2] == 'inprogress'), None)
        first = self.ptl[0] if self.ptl else None
        c = self.me()
        p = self.loc(c) if c is not None else None
        # SPEC_B_LOBBY 7.7: practice starts aboard team 0's ship (bStartAboard), no pawn during the countdown
        on_floor = self.aboard(c, s)
        t0s = mb_get(d, 'teams', 0) or {}
        t1s = mb_get(d, 'teams', 1) or {}
        team = self.ps_team(self.pc.get_editor_property('player_state')) if self.pc else None
        ok = (first is not None and first[2] == 'countdown' and first[1] <= 1.0 and ip is not None and abs(ip[1] - delay) <= 0.2
              and t0s.get('active') is True and t1s.get('active') is False and team == 0 and on_floor)
        self.check('T1.1_practice_start', self.ok(ok), 'phase timeline (game t, world t, phase) %s: first %s, InProgress at world %.2f s (want '
                   'Countdown from the load, InProgress at %.1f +-0.2 s); Teams[0] active %s, Teams[1] active %s (want true / false); '
                   'player team %s (want 0), at %s aboard team 0\'s ship 1 s after InProgress %s (SPEC_B_LOBBY 7.7)' % (
                       self.ptl[:6], first, ip[1] if ip else -1, delay, t0s.get('active'), t1s.get('active'), team, r(p, 0) if p else None, on_floor),
                   {'timeline': self.ptl, 'teams': mb_get(d, 'teams'), 'rules': mb_get(d, 'rules')})
        ships = [x for x in self.ships(self.w, alive=True) if self.ship_team(x) == 0]
        fs = self.first_ship or {}
        want = self.lane_point(self.side0, float(self.setting('LaneSpawnU', 0.0)))
        off = dist(fs['loc'], want) if fs.get('loc') else None
        yerr = abs(wrap180(fs.get('yaw', 999.0) - self.frame['yaw'])) if fs else None
        st = self.lane_state(s) if s is not None else None
        prot = (self.protected(s) or (self.tele(s).get('ProtectionLeftS') or 0.0) > 0.0) if s is not None else None
        ok = (len(ships) == 1 and off is not None and off <= 100.0 and yerr is not None and yerr <= 2.0 and st in ('waiting', 'cruising') and prot)
        self.check('T1.2_team_ship', self.ok(ok), 'team 0 ships alive %d (want 1); first seen %s at world %s, %s cm from the lane spawn point %s '
                   '(want <= 100), yaw error %s deg (want <= 2); now at %s, lane state %s (want Waiting / Cruising), protected %s' % (
                       len(ships), fs.get('name'), fs.get('wt'), r(off, 1), r(want, 0), r(yerr, 2), r(self.loc(s), 0) if s else None, st, prot),
                   {'first': fs, 'all_ships': self.R.get('ships_seen')})
        self.xgrab('settle_match_bar')
        if s is not None:
            sp = self.loc(s)
            self.capture(self.w, 'settle_ship', [sp[0] - 4500.0, sp[1] - self.side0 * 3500.0, sp[2] + 1800.0], sp)

    def t_debug(self):
        """T2.3: the lane polylines (debug draw) are where the lanes are: the lane build line's offset, and the lane
        point under the ship (ship minus its lateral / vertical error) sampled while it moves"""
        self.cmd(self.w, 'Aura.Lane.Debug 1')
        built = [l for _, l in self.log_since(0.0, 'LogLane', 'Lanes built from')]
        off = None
        if built:
            m = re.search(r'lanes at \+-(-?[\d.]+) cm', built[-1])
            off = float(m.group(1)) if m else None
        want = self.lane_v(1)
        samples = []
        t0 = self.now
        while self.now - t0 < 3.0:
            s = self.ship0()
            if s is not None and int((self.now - t0) * 5) != self.D.get('_k'):
                self.D['_k'] = int((self.now - t0) * 5)
                t = self.tele(s)
                p = self.uv(self.loc(s))
                lv = p[1] - self.lat_of(s, t)
                lz = p[2] - float(t.get('LaneVerticalErrorM') or 0.0) * 100.0
                samples.append((r(p[0], 0), r(lv, 1), r(lz, 1)))
            yield
        le = [abs(x[1] - self.lane_v(self.side0)) for x in samples]
        ze = [abs(x[2] - float(self.setting('LaneHeight', 200.0))) for x in samples]
        s = self.ship0()
        if s is not None:
            sp = self.loc(s)
            self.capture(self.w, 't2_3_lanes', [sp[0] - 9000.0, sp[1], sp[2] + 12000.0], [sp[0] + 6000.0, sp[1] - self.side0 * 15000.0, sp[2]], 75.0)
        self.xgrab('t2_3_lane_debug')
        ok = off is not None and abs(off - want) <= 50.0 and le and max(le) <= 50.0 and max(ze) <= 50.0
        self.check('T2.3_lane_debug', self.ok(ok), 'Aura.Lane.Debug 1; lane build line: lanes at +-%s cm (want %.0f = H + LaneClearance, '
                   'StartupMap y +12500 / -32500, within 50 cm) %s; the lane point under the team ship (v, z) off by max %s / %s cm over %d samples; '
                   'capture + x grab of the drawn lines' % (off, want, [l[-200:] for l in built[-1:]], r(max(le), 1) if le else None,
                                                             r(max(ze), 1) if ze else None, len(samples)), {'samples (u, lane v, lane z)': samples})
        self.cmd(self.w, 'Aura.Lane.Debug 0')

    def t_pace(self):
        """T2.1"""
        c = yield from self.foot(20000.0)
        if c is None:
            self.check('T2.1_pace', 'FAIL', 'no living player to stand at u 200 m')
            return
        up = self.u_of(c)
        lead_cap = float(self.setting('LaneMaxLead', 4000.0))
        self.say('player at u %.1f m; following the ship' % (up / 100.0))
        trk, tg = [], []
        settled = None
        t0 = self.now
        while self.now - t0 < 60.0:
            s = self.ship0()
            if s is None:
                yield
                continue
            t = self.tele(s)
            us = self.u_of(s)
            sp = float(t.get('ForwardSpeedMS') or 0.0)
            hd = abs(wrap180(self.yaw(s) - float(t.get('LaneYawDeg') if t.get('LaneYawDeg') is not None else self.frame['yaw'])))
            trk.append((r(self.now - t0, 2), r(us - up, 1), r(sp, 2), t.get('LaneClampName'), r(self.lat_of(s, t), 1),
                        r(float(t.get('LaneVerticalErrorM') or 0.0) * 100.0, 1), r(hd, 2), self.lane_state(s)))
            tg.append((self.now, float(t.get('LaneTargetSpeedMS') or 0.0)))
            if abs(sp) < 0.3 and self.now - t0 > 5.0:
                settled = settled or self.now
                if self.now - settled >= 2.0:
                    break
            else:
                settled = None
            yield
        peak = max((x[2] for x in trk), default=None)
        moving = [x for x in trk if x[2] > 1.0]
        lat = max((abs(x[4]) for x in moving), default=None)
        vert = max((abs(x[5]) for x in moving), default=None)
        hd = max((x[6] for x in moving), default=None)
        final = trk[-1] if trk else None
        over = max((x[1] for x in trk), default=0.0) - lead_cap
        ramp = 0.0
        for i in range(3, len(tg)):
            dtt = tg[i][0] - tg[i - 3][0]
            if dtt > 0.05:
                ramp = max(ramp, abs(tg[i][1] - tg[i - 3][1]) / dtt)
        ok = (peak is not None and 27.0 <= peak <= 29.0 and final is not None and abs(final[1] - lead_cap) <= 300.0 and over <= 100.0
              and settled is not None and final[3] == 'teampace' and lat is not None and lat <= 150.0 and vert <= 100.0 and hd <= 3.0 and ramp <= 2.6)
        self.check('T2.1_pace', self.ok(ok), 'player at u %.0f m: peak %s m/s (want 28 +-1), settled %s at %s m ahead (want %.0f +-3, Clamp '
                   'TeamPace: %s), overshoot past the cap %.2f m (want <= 1), while moving lateral <= %s cm (1.5 m), vertical <= %s cm (1.0 m), '
                   'heading <= %s deg (3), target speed ramp <= %.2f m/s^2 (2.6)' % (
                       up / 100.0, peak, settled is not None, r(final[1] / 100.0, 2) if final else None, lead_cap / 100.0,
                       final[3] if final else None, over / 100.0, r(lat, 0), r(vert, 0), r(hd, 2), ramp),
                   {'track (t, ship-player u cm, speed, clamp, lat, vert, heading, state)': trk[::3]})

    def t_end(self):
        """T2.2"""
        self.cmd(self.w, 'Aura.Match.Set LaneMaxLead 0')
        trk, ends = [], []
        settled = None
        t0 = self.now
        while self.now - t0 < 45.0:
            s = self.ship0()
            if s is None:
                yield
                continue
            t = self.tele(s)
            ln = self.lanes(1.0)
            sp = float(t.get('ForwardSpeedMS') or 0.0)
            trk.append((r(self.now - t0, 2), r(self.u_of(s), 0), r(sp, 2), t.get('LaneClampName'), ln.get('cruise_end_u'), ln.get('path_end_u')))
            if abs(sp) < 0.3 and self.now - t0 > 3.0:
                settled = settled or self.now
            else:
                settled = None
            if settled is not None:
                ends.append((self.now, ln.get('path_end_u')))
                if self.now - settled >= 20.0:
                    break
            yield
        self.cmd(self.w, 'Aura.Match.Set LaneMaxLead %.0f' % float(MB_APPENDIX_A['LaneMaxLead']))
        last = trk[-1] if trk else None
        ce = last[4] if last else None
        over = (max(x[1] for x in trk) - ce) if (trk and ce is not None) else None
        pe = set(x[1] for x in ends if x[1] is not None)
        ok = (settled is not None and ce is not None and abs(last[1] - ce) <= 300.0 and over is not None and over <= 100.0 and abs(last[2]) <= 0.3
              and last[3] == 'pathend' and len(pe) == 1 and self.now - settled >= 19.5)
        self.check('T2.2_path_end', self.ok(ok), 'LaneMaxLead 0: settled %s, ship u %s cm vs CruiseEndU %s (want +-300), overshoot %s cm (<= 100), '
                   'speed %s m/s (<= 0.3), clamp %s (PathEnd), path end u while settled %s (want one value for 20 s)' % (
                       settled is not None, last[1] if last else None, ce, r(over, 0), last[2] if last else None, last[3] if last else None,
                       sorted(pe)), {'track (t, u, speed, clamp, cruise end, path end)': trk[::3]})

    def t_run(self):
        """T2.1b"""
        c = yield from self.foot()
        if c is None:
            self.check('T2.1b_runner', 'FAIL', 'no living player')
            return
        p0 = self.loc(c)
        u0, v0 = self.uv(p0)[0], self.uv(p0)[1]
        z = self.frame['O'][2] + 300.0 + self.hh(c)
        gaps = []
        t0 = self.now
        while self.now - t0 < 60.0:
            u = u0 + 2000.0 * (self.now - t0)
            q = self.world(u, v0, 0.0)
            c = self.me()
            if c is None or not self.alive(c):
                self.line('WARN', 'the runner died at %.1f s' % (self.now - t0))
                break
            c.set_actor_location(unreal.Vector(q[0], q[1], z), False, True)
            s = self.ship0()
            if s is not None and self.now - t0 >= 15.0:
                gaps.append((r(self.now - t0, 1), r(self.hull_gap(s, [q[0], q[1], z]), 0), r(self.u_of(s) - u, 0)))
            yield
        yield from self.foot()
        mx = max((g[1] for g in gaps), default=None)
        self.check('T2.1b_runner', self.ok(mx is not None and mx < 10000.0 and len(gaps) > 100), 'player moved at 20 m/s for %.0f s from u %.0f m: '
                   'from 15 s on the hull\'s nearest point stayed within %s m of him (want < 100), median %s m, %d samples' % (
                       self.now - t0, u0 / 100.0, r(mx / 100.0, 1) if mx else None, r((mb_median([g[1] for g in gaps]) or 0) / 100.0, 1), len(gaps)),
                   {'gaps (t, cm, ship u - player u)': gaps[::10]})

    def t_edge(self):
        """T2.9"""
        c = yield from self.foot()
        if c is None:
            self.check('T2.9_edge_gap', 'FAIL', 'no living player')
            return
        u0 = self.u_of(c)
        side = self.side0
        rows = []
        for k in range(21):
            u = u0 + 5000.0 * k
            spot, pl = self.stand_spot(u, edge=True)
            if spot is None:
                got = yield from self.until(lambda: self.stand_spot(u, edge=True)[0], 4.0)
                spot, pl = self.stand_spot(u, edge=True) if got else (None, None)
            if spot is None:
                rows.append((r(u / 100.0, 0), None, None))
                continue
            c = self.me()
            self.tp_char(c, spot, self.frame['yaw'])
            yield from self.wait(0.5)
            sv = self.uv(spot)[1]
            gap = side * (self.lane_v(side) - sv) - MB_HULL_HALF_WIDTH
            edge = (pl['vmax'] if side > 0 else pl['vmin']) if pl else None
            rows.append((r(u / 100.0, 0), r(gap / 100.0, 1), r((side * (self.lane_v(side) - edge) - MB_HULL_HALF_WIDTH) / 100.0, 1) if edge is not None else None))
        g = [x[1] for x in rows if x[1] is not None]
        ok = len(g) >= 15 and max(g) <= 115.0
        self.check('T2.9_edge_gap', self.ok(ok), 'team-side platform edge walked from u %.0f m, %d of 21 spots found: 2D gap from the player '
                   'to the lane hull\'s inner side min %s / median %s / max %s m (want no gap > 115 m; expected 14-84 m, flag 2)' % (
                       u0 / 100.0, len(g), min(g) if g else None, mb_median(g), max(g) if g else None),
                   {'rows (u m, gap from the player m, gap from the platform bounds m)': rows})

    def t_assist(self):
        """T2.4"""
        c = yield from self.foot()
        if c is None:
            self.check('T2.4_assist', 'FAIL', 'no living player')
            return
        up = self.u_of(c)
        self.lane_teleport(up + 1800.0)
        sp = yield from self.until(lambda: self.ship0() is not None and self.lane_state(self.ship0()) == 'cruising'
                                   and float(self.tele(self.ship0()).get('ForwardSpeedMS') or 0.0) >= 5.5, 8.0)
        s = self.ship0()
        pre = (self.lane_state(s), r(self.tele(s).get('ForwardSpeedMS'), 2)) if s else None
        self.cmd(self.w, 'Aura.Airship.Board 0')
        states = []
        for _ in range(4):
            yield
            states.append(self.lane_state(s) if s else None)
        boarded = self.piloting()
        speeds = []
        t0 = self.now
        while self.now - t0 < 10.0:
            t = self.tele(s)
            speeds.append((r(self.now - t0, 2), r(t.get('ForwardSpeedMS'), 2), self.lane_state(s)))
            if abs(self.now - t0 - 5.0) < 0.02:
                self.xgrab('t2_4_lane_assist')
            yield
        # The view off the bow first: since round 2 part A the pilot's Fire in the bow arc (UAirshipSettings
        # DriverTurretArcDeg, 50 deg) drives the unmanned turrets and RequestFire fires no broadside (AirshipPawn.cpp
        # RequestFire / IsDriverTurretArc). The speed samples above are taken before this. The camera lags the control
        # rotation, so the view is aimed (MBRun.aim, as_59's aim_at) at a point 200 m abeam until the camera itself is at
        # least 75 deg off the bow (2 s at most); `aim` is that camera yaw off the bow.
        aim = None
        if self.pc is not None:
            sy = math.radians(self.yaw(s) + 90.0 * self.side0)
            q = self.loc(s)
            pt = [q[0] + 20000.0 * math.cos(sy), q[1] + 20000.0 * math.sin(sy), q[2] - 1000.0]
            t_a = self.now
            while self.now - t_a < 2.0:
                self.aim(self.w, self.pc, pt)
                if abs(wrap180(self.cam(self.w)[1].yaw - self.yaw(s))) >= 75.0:
                    break
                yield
            aim = r(abs(wrap180(self.cam(self.w)[1].yaw - self.yaw(s))), 1)
        nb = set(b.get_name() for b in self.balls())
        tf = self.now
        try:
            s.request_fire()
        except Exception:  # noqa: BLE001
            self.err('request_fire')
        ball = yield from self.until(lambda: [b for b in self.balls() if b.get_name() not in nb], 0.5)
        dt_ball = (self.now - tf) if ball else None
        sv = [x[1] for x in speeds if x[0] >= 0.5 and x[1] is not None]
        ok = (sp is not None and boarded and 'assist' in states[:3] and sv and min(sv) >= 5.5 and max(sv) <= 6.5
              and all(x[2] == 'assist' for x in speeds) and dt_ball is not None and dt_ball <= 0.2)
        self.check('T2.4_assist', self.ok(ok), 'before Board %s; Board 0: boarded %s, lane state in the first frames %s (want Assist at once); '
                   'speed over 10 s with no input %s..%s m/s (want 6 +-0.5), always Assist %s; broadside RequestFire (camera %s deg off the bow, outside the '
                   'bow arc): ball after %s s (want <= 0.2)' % (pre, boarded, states, min(sv) if sv else None, max(sv) if sv else None,
                                                             all(x[2] == 'assist' for x in speeds), aim, r(dt_ball, 3)), {'speeds': speeds[::5]})

    def t_input(self):
        """T2.5"""
        s = self.ship0()
        if not self.piloting():
            ok = yield from self.board()
        yield from self.until(lambda: self.lane_state(s) == 'assist', 4.0)
        st0 = self.lane_state(s)
        self.cmd(self.w, 'Aura.Airship.Input 1 0')
        seq = []
        t0 = self.now
        while self.now - t0 < 2.0:
            seq.append(self.lane_state(s))
            if len(seq) == 15:
                self.xgrab('t2_5_piloted_in_lane')
            yield
        f_pil = next((i for i, x in enumerate(seq) if x == 'pilotedinlane'), None)
        spd = r(self.tele(s).get('ForwardSpeedMS'), 2)
        self.cmd(self.w, 'Aura.Airship.InputClear')
        tc = self.now
        back = yield from self.until(lambda: self.lane_state(s) == 'assist', 8.0)
        dt = (self.now - tc) if back else None
        ok = st0 == 'assist' and f_pil is not None and f_pil <= 1 and dt is not None and abs(dt - 1.0) <= 0.2
        self.check('T2.5_input', self.ok(ok), 'from %s: Aura.Airship.Input 1 0 for 2 s: PilotedInLane at frame %s (want <= 1), speed then %s m/s; '
                   'InputClear: Assist again after %s s (want 1.0 +-0.2; needs <= LaneAssistMaxSpeed 15 m/s)' % (st0, f_pil, spd, r(dt, 2)),
                   {'states': seq[:12]})

    def t_strafe(self):
        """T2.5b"""
        s = self.ship0()
        self.set_scheme(s, 3)
        if not self.piloting():
            yield from self.board()
        a = yield from self.until(lambda: self.lane_state(s) == 'assist', 8.0)
        y0 = self.yaw(s)
        seq = []
        t0 = self.now
        while self.now - t0 < 1.0:
            self.inject(self.w, 'IA_AirshipStrafe', (-1.0, 0.0, 0.0))
            yield
            seq.append(self.lane_state(s))
        yield from self.wait(0.5)
        dy = abs(wrap180(self.yaw(s) - y0))
        f = next((i for i, x in enumerate(seq) if x == 'pilotedinlane'), None)
        ok = a and f is not None and f <= 1 and dy >= 2.0
        self.check('T2.5b_pf_q_key', self.ok(ok), 'Point & Fly in Assist %s; IA_AirshipStrafe (Q) held 1 s: PilotedInLane at frame %s after the '
                   'first press (want within 2 frames), the ship\'s yaw changed %.1f deg on the server (want it turns, >= 2)' % (bool(a), f, dy),
                   {'states': seq[:10]})
        self.cmd(self.w, 'Aura.Airship.InputClear')

    def t_out(self):
        """T2.6"""
        s = self.ship0()
        if not self.piloting():
            yield from self.board()
        side = self.side0
        sgn = side
        self.cmd(self.w, 'Aura.Airship.Input 0 0 0 %d' % sgn)
        t0 = self.now
        lat0 = self.lat_of(s)
        t_out = t_state = None
        flipped = False
        while self.now - t0 < 12.0:
            lat = self.lat_of(s)
            if not flipped and self.now - t0 > 1.5 and (lat - lat0) * side < 0.0:
                sgn = -sgn
                flipped = True
                self.cmd(self.w, 'Aura.Airship.Input 0 0 0 %d' % sgn)
            if t_out is None and abs(lat) > 4000.0:
                t_out = self.now
            if t_state is None and self.lane_state(s) == 'outoflane':
                t_state = self.now
                self.xgrab('t2_6_out_of_lane')
            if t_out is not None and t_state is not None and float(self.tele(s).get('SpeedMS') or 0.0) > 8.5:
                break
            yield
        spd = float(self.tele(s).get('SpeedMS') or 0.0)
        self.cmd(self.w, 'Aura.Airship.InputClear')
        self.cmd(self.w, 'Aura.Airship.Exit 0')
        te = self.now
        pe = self.loc(s)
        yield from self.wait(0.3)
        st_after = (self.lane_state(s), self.tele(s).get('UnpilotedModeName'))
        hold = ret = None
        maxd = 0.0
        while self.now - te < 26.0:
            t = self.tele(s)
            d2 = math.hypot(self.loc(s)[0] - pe[0], self.loc(s)[1] - pe[1])
            maxd = max(maxd, d2)
            if hold is None and t.get('UnpilotedModeName') == 'hold':
                hold = (r(self.now - te, 2), r(d2, 0), r(t.get('SpeedMS'), 2))
            if ret is None and self.lane_state(s) == 'returning':
                ret = r(self.now - te, 2)
            if hold or ret:
                break
            yield
        ok = (t_state is not None and t_out is not None and t_state >= t_out - 0.1 and spd > 8.0 and st_after == ('parked', 'drift')
              and ((hold is not None and hold[1] <= 30500.0 and hold[2] <= 3.0) or ret is not None))
        self.check('T2.6_out_of_lane', self.ok(ok), 'strafe %s: lateral > 40 m at %s s, OutOfLane at %s s; exit at %.1f m/s (want > 8): %s (want '
                   'Parked + Drift); then Hold %s (t s, distance cm from the exit, speed: want <= 300 m and slow) or Returning at %s s first; '
                   'max drift distance %.0f m' % ('out' if not flipped else 'out (sign flipped)', r(t_out - t0, 2) if t_out else None,
                                                   r(t_state - t0, 2) if t_state else None, spd, st_after, hold, ret, maxd / 100.0))

    def t_park(self):
        """T2.7"""
        s = self.ship0()
        if not self.piloting():
            yield from self.board()
        side = self.side0
        if abs(self.lat_of(s)) < 4500.0:
            p = self.loc(s)
            u = self.u_of(s)
            q = self.world(u, self.lane_v(side) + side * 6000.0, self.uv(p)[2])
            self.teleport(s, q, self.yaw(s))
            yield from self.wait(0.5)
        st_out = self.lane_state(s)
        self.cmd(self.w, 'Aura.Airship.Input 0 0 0 %d' % (-side))
        seq = []
        inz = yield from self.until(lambda: seq.append(self.lane_state(s)) or abs(self.lat_of(s)) <= 1500.0, 20.0)
        self.cmd(self.w, 'Aura.Airship.Input 0 0 0 0 0 1')
        slow = yield from self.until(lambda: float(self.tele(s).get('SpeedMS') or 99.0) < 5.0, 10.0)
        self.cmd(self.w, 'Aura.Airship.InputClear')
        yield from self.wait(0.3)
        lat_exit, spd_exit = self.lat_of(s), r(self.tele(s).get('SpeedMS'), 2)
        self.cmd(self.w, 'Aura.Airship.Exit 0')
        te = self.now
        cru = yield from self.until(lambda: self.lane_state(s) == 'cruising', 2.0)
        dt_c = (self.now - te) if cru else None
        six = yield from self.until(lambda: float(self.tele(s).get('ForwardSpeedMS') or 0.0) >= 5.7, 5.0)
        dt_6 = (self.now - te) if six else None
        states = sorted(set(x for x in seq if x))
        ok = (inz and slow and dt_c is not None and dt_c <= 0.5 and dt_6 is not None and dt_6 <= 3.0)
        self.check('T2.7_park_in_lane', self.ok(ok), 'out of the lane (%s), flew back (states %s) to lateral %.0f cm, %s m/s, exit: Cruising after '
                   '%s s (want <= 0.5), 6 m/s after %s s (want <= 3)' % (st_out, states, lat_exit, spd_exit, r(dt_c, 2), r(dt_6, 2)))

    def t_block(self):
        """T2.8"""
        s = self.ship0()
        b = self.pie_temp(self.w, 'Block40')
        if b is None or s is None:
            self.check('T2.8_blocked', 'FAIL', 'no TEMP_AS74_Block40 PIE copy (%s) or no team ship (%s)' % (b, s))
            return
        if self.lane_state(s) not in ('cruising', 'waiting'):
            yield from self.until(lambda: self.lane_state(s) in ('cruising', 'waiting'), 10.0)
        hp0 = self.ship_hp(s)
        u = self.u_of(s) + 15000.0
        q = self.lane_point(self.side0, u)
        b.set_actor_enable_collision(True)
        b.set_actor_location(unreal.Vector(*q), False, True)
        self.say('block 40 m at u %.0f m' % (u / 100.0))
        bl = yield from self.until(lambda: self.lane_state(s) == 'waiting' and self.tele(s).get('LaneClampName') == 'blocked', 45.0)
        t_b = self.now if bl else None
        stop = yield from self.until(lambda: abs(float(self.tele(s).get('ForwardSpeedMS') or 9.0)) < 0.3, 6.0)
        gap = self.aabb_gap2d(s, b) if bl else None
        blocker = [l[-200:] for _, l in self.log_since(self.t_test0, 'LogLane', 'block')][:3]
        yield from self.wait(max(0.0, 3.0 - (self.now - (t_b or self.now))))
        b.set_actor_enable_collision(False)
        toff = self.now
        cru = yield from self.until(lambda: self.lane_state(s) == 'cruising', 3.0)
        dt = (self.now - toff) if cru else None
        hp1 = self.ship_hp(s)
        b.set_actor_location(unreal.Vector(*AS74_PARK), False, True)
        b.set_actor_enable_collision(True)
        ok = bl and gap is not None and gap >= 500.0 and hp0 == hp1 and dt is not None and dt <= 1.0
        self.check('T2.8_blocked', self.ok(ok), 'Waiting + Clamp Blocked %s after %s s, stopped %s, %.0f cm short of the block (want >= 500 hull '
                   'bounds), health %s -> %s (no damage); collision off: Cruising after %s s (want <= 1); LogLane %s' % (
                       bool(bl), r(t_b - self.t_test0, 1) if t_b else None, bool(stop), gap or -1, hp0, hp1, r(dt, 2), blocker))

    def t_bypass(self):
        """T2.11"""
        s = self.ship0()
        b = self.pie_temp(self.w, 'BlockShip')
        if b is None or s is None:
            self.check('T2.11_bypass', 'FAIL', 'no TEMP_AS74_BlockShip PIE copy or no team ship')
            return
        yield from self.until(lambda: self.lane_state(s) in ('cruising', 'waiting'), 10.0)
        ub = self.u_of(s) + 8000.0
        b.set_actor_location(unreal.Vector(*self.lane_point(self.side0, ub)), False, True)
        bl = yield from self.until(lambda: self.tele(s).get('LaneClampName') == 'blocked', 30.0)
        t_b = self.now if bl else None
        bp = yield from self.until(lambda: self.tele(s).get('LaneClampName') == 'bypass', 15.0)
        t_bp = self.now if bp else None
        gaps = []
        passed = yield from self.until(lambda: gaps.append(self.aabb_gap2d(s, b)) or self.u_of(s) > ub + 1500.0 + MB_HULL_HALF_LENGTH + 3000.0, 45.0)
        t_pass = self.now if passed else None
        back = yield from self.until(lambda: self.tele(s).get('LaneClampName') != 'bypass' and abs(self.lat_of(s)) <= 150.0, 30.0)
        dt_back = (self.now - t_pass) if (back and t_pass) else None
        b.set_actor_location(unreal.Vector(0.0, 30000.0, -100000.0), False, True)
        mg = min(gaps) if gaps else None
        dbp = (t_bp - t_b) if (t_b and t_bp) else None
        ok = dbp is not None and abs(dbp - float(self.setting('LaneBlockedTimeout', 5.0))) <= 0.5 and mg is not None and mg >= 500.0 and dt_back is not None
        self.check('T2.11_bypass', self.ok(ok), 'ship-sized block (30 x 23 x 20 m) in the lane: Blocked %s, Bypass %s s later (want 5 +-0.5), '
                   'smallest hull-to-block gap while passing %s cm (want >= 500), clamp off Bypass and lateral <= 1.5 m %s s after passing '
                   '(want within 30)' % (bool(bl), r(dbp, 2), r(mg, 0), r(dt_back, 1)))

    def t_recall(self):
        """T2.10"""
        s = self.ship0()
        if not self.piloting():
            yield from self.board()
        side = self.side0
        u = self.u_of(s)
        self.teleport(s, self.world(u, self.lane_v(side) + side * 20000.0, float(self.setting('LaneHeight', 200.0))), self.yaw(s))
        out = yield from self.until(lambda: self.lane_state(s) == 'outoflane', 3.0)
        yield from self.wait(0.5)
        self.cmd(self.w, 'Aura.Airship.Exit 0')
        te = self.now
        yield from self.wait(0.4)
        c = self.me()
        spot, _ = self.stand_spot(u)
        if spot is not None and c is not None:
            self.tp_char(c, spot, self.frame['yaw'])
        dist_p = dist(self.loc(c), self.loc(s)) if c is not None else None
        hp0 = self.ship_hp(s)
        st0 = self.lane_state(s)
        t_ret = None
        grabbed = False
        while self.now - te < 26.0:
            if not grabbed and self.now - te > 10.0:
                grabbed = True
                self.xgrab('t2_10_recall_timer')
            if self.lane_state(s) == 'returning':
                t_ret = self.now - te
                break
            yield
        cru = yield from self.until(lambda: self.lane_state(s) == 'cruising', 52.0 - (self.now - te))
        t_cru = (self.now - te) if cru else None
        # read after the wait: the event line reaches the log file a frame or more after the state change, so a read in that
        # frame finds none (the 2026-11-28 lane run: the line was in the log at the same frame as Parked -> Returning)
        ev = self.events_since(te, 'ShipReturning', 0)
        hp1 = self.ship_hp(s)
        ok = (out and st0 == 'parked' and t_ret is not None and abs(t_ret - float(self.setting('ShipRecallDelay', 20.0))) <= 0.5 and ev
              and t_cru is not None and t_cru <= 50.0 and hp0 == hp1)
        self.check('T2.10_recall', self.ok(ok), 'exit 200 m outside the lane (OutOfLane %s), player %s m away on a platform: %s at the exit (want '
                   'Parked), Returning %s s after the exit (want 20 +-0.5), event ShipReturning %s, Cruising at %s s (want <= 50), health %s -> %s' % (
                       bool(out), r(dist_p / 100.0, 0) if dist_p else None, st0, r(t_ret, 2), [(e['t'], e['role']) for e in ev][:2], r(t_cru, 1), hp0, hp1))

    def t_lead(self):
        """T5.1"""
        c = yield from self.foot()
        if c is None:
            self.check('T5.1_lead_ship_borne', 'FAIL', 'no living player')
            return
        ps = self.pc.get_editor_property('player_state')
        last = float(ps.get_platform_spline_distance())
        plats = dict((p['a'].get_name(), (p['a'], p['sd'])) for p in self.platforms(self.w) if p['sd'] is not None)
        br = mb_objects('bridges', self.w)
        br = br[0] if br else None
        pe0 = self.lanes(0.0).get('path_end_u')
        yield from self.board()
        s = self.ship0()
        u0 = self.u_of(s)
        self.cmd(self.w, 'Aura.Airship.Input 1 0')
        leads, gone_ahead, pes = [], [], []
        braking = False
        t0 = self.now
        while self.now - t0 < 30.0:
            if not braking and self.u_of(s) >= u0 + 60000.0:
                self.cmd(self.w, 'Aura.Airship.Input 0 0 0 0 0 1')
                braking = True
            if int((self.now - t0) * 2) != self.D.get('_k'):
                self.D['_k'] = int((self.now - t0) * 2)
                if br is not None and self.now - t0 > 1.0:
                    leads.append(mb_name(br.get_lead_pawn()))
                for n, (a, sd) in list(plats.items()):
                    if not valid(a):
                        if sd > last - 20000.0:
                            gone_ahead.append((n, sd))
                        del plats[n]
                if int(self.now - t0) % 3 == 0:
                    pes.append(self.lanes(0.0).get('path_end_u'))
            yield
        self.cmd(self.w, 'Aura.Airship.InputClear')
        flown = self.u_of(s) - u0
        ok = flown >= 55000.0 and not gone_ahead and leads and all(x is None for x in leads) and all(p == pe0 for p in pes if p is not None)
        self.check('T5.1_lead_ship_borne', self.ok(ok), 'boarded and flew %.0f m ahead for 30 s: platforms ahead of the last landed one - 200 m '
                   'destroyed %d (want 0) %s; lead pawn while aboard %s (want null); path end u %s -> %s (want unchanged)' % (
                       flown / 100.0, len(gone_ahead), gone_ahead[:4], sorted(set(str(x) for x in leads)), pe0, sorted(set(pes))))

    def t_burrower(self):
        """T5.2"""
        c = yield from self.foot()
        if c is None:
            self.check('T5.2_burrower', 'FAIL', 'no living player')
            return
        bst = mb_cdo('burrower_settings')
        bst.set_editor_property('bEnabled', True, unreal.PropertyAccessChangeNotifyMode.NEVER)

        def burrowers():
            return [b for b in unreal.GameplayStatics.get_all_actors_of_class(self.w, mb_cls('burrower')) if valid(b) and not b.is_burrower_dead()]
        self.cmd(self.w, 'Aura.Burrower.SpawnNow 0')
        bur = yield from self.until(lambda: [b for b in burrowers() if mb_same(b.get_target_player(), self.me())], 6.0)
        n0 = len(burrowers())
        yield from self.board()
        yield from self.wait(2.0)
        tg = [mb_name(b.get_target_player()) for b in burrowers()]
        ts = self.now
        self.cmd(self.w, 'Aura.Burrower.SpawnNow 0')
        yield from self.wait(1.5)
        n1 = len(burrowers())
        sl = [l[-120:] for _, l in self.log_since(ts, 'Aura.Burrower.SpawnNow')]
        self.cmd(self.w, 'Aura.Burrower.KillAll')
        bst.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
        ok = bool(bur) and all(t is None for t in tg) and n1 <= n0
        self.check('T5.2_burrower', self.ok(ok), 'on foot a Burrower hunts him %s; aboard 2 s: targets %s (want none); SpawnNow while aboard: '
                   'Burrowers %d -> %d (want no new one) %s' % (bool(bur), tg, n0, n1, sl))

    def t_low(self):
        """T3.6"""
        if not self.piloting():
            yield from self.board()
        s = self.ship0()
        self.lane_teleport(self.u_of(s), -150.0)
        alive, att = [], []
        t0 = self.now
        while self.now - t0 < 10.0:
            c = self.me()
            alive.append(self.alive(c))
            att.append(self.piloting())
            yield
        self.cmd(self.w, 'Aura.Airship.Exit 0')
        yield from self.wait(1.0)
        c = self.me()
        rider_alive = self.alive(c)
        o, e = s.get_actor_bounds(True)
        p = self.loc(c)
        self.tp_char(c, self.world(self.u_of(s), self.uv([o.x, o.y, o.z])[1] + self.side0 * (e.y + 4000.0), self.uv(p)[2]), self.frame['yaw'])
        tp = self.now
        dead = yield from self.until(lambda: not self.alive(c) or not valid(c), 10.0)
        dt = (self.now - tp) if dead else None
        fl = [l[-160:] for _, l in self.log_since(tp, 'fall death')]
        ok = all(alive) and rider_alive and dt is not None and dt <= 8.0
        self.check('T3.6_below_lane', self.ok(ok), 'pilot aboard 150 m below path height for 10 s: alive %s (attached %s); exit onto the deck: '
                   'alive %s (rider); moved 40 m off the side: fall death after %s s (want <= 8) %s' % (
                       all(alive), all(att), rider_alive, r(dt, 2), fl[:1]))
        yield from self.until(lambda: self.alive(self.me()) and not mb_same(self.me(), c), 12.0)

    def t_kill(self):
        """T3.1"""
        c = yield from self.foot()
        if c is None:
            self.check('T3.1_kill_respawn', 'FAIL', 'no living player')
            return
        up = self.u_of(c)
        ts0 = self.team_state(self.w, 0) or {}
        old, new, t_k, t_n = yield from self.kill_and_respawn()
        yield from self.wait(0.5)
        ts1 = self.team_state(self.w, 0) or {}
        ev = self.events_since(t_k, 'ShipDestroyed', 0)
        ln = self.lanes(0.0)
        want_u = max(float(ln.get('lane_start_u') or -1e9), min(float(ln.get('cruise_end_u') or 1e9), up))
        res = {}
        if new is not None:
            res = {'dt': r(t_n - t_k, 2), 'team': self.ship_team(new), 'du': r(self.u_of(new) - want_u, 0), 'lat': r(self.lat_of(new), 0),
                   'state': self.lane_state(new), 'protected': self.protected(new)}
            self.wind_off(new)
        lost = (ts1.get('ships_lost') or 0) - (ts0.get('ships_lost') or 0)
        ok = (lost == 1 and ev and new is not None and abs(res['dt'] - float(self.setting('ShipRespawnDelay', 10.0))) <= 0.3 and res['team'] == 0
              and abs(res['du']) <= 500.0 and abs(res['lat']) <= 500.0 and res['state'] in ('cruising', 'waiting') and res['protected'])
        self.check('T3.1_kill_respawn', self.ok(ok), 'KillShip 0 with the player on foot at u %.0f m: ShipsLost +%s, event ShipDestroyed %s; new ship %s '
                   '(want +10.0 +-0.3 s, team 0, u at the team front +-5 m, on the lane, Cruising / Waiting, protected)' % (
                       up / 100.0, lost, bool(ev), res))

    def t_eject(self):
        """T3.2"""
        c = yield from self.until(lambda: self.me() if self.alive(self.me()) else None, 15.0)
        yield from self.until(lambda: self.ship0(), 14.0)
        if not (yield from self.board()):
            self.check('T3.2_eject_fall_death', 'FAIL', 'could not board the team ship')
            return
        yield from self.wait(1.0)
        pilot = self.me()
        old, new, t_k, t_n = yield from self.kill_and_respawn(timeout=1.0)
        ej = yield from self.until(lambda: valid(pilot) and pilot.get_attach_parent_actor() is None, 3.0)
        t_ej = self.now if ej else None
        dead = yield from self.until(lambda: not self.alive(pilot), 10.0)
        t_d = self.now if dead else None
        fl = [l[-160:] for _, l in self.log_since(t_k, 'fall death')]
        resp = yield from self.until(lambda: self.me() if (self.alive(self.me()) and not mb_same(self.me(), pilot)) else None, 12.0)
        t_r = self.now if resp else None
        where = None
        if resp:
            yield from self.wait(1.5)
            p = self.loc(resp)
            g = self.ground_at(self.w, p[0], p[1], p[2], p[2] - 2000.0)
            on = g['actor'] if g else None
            where = {'uv': r(self.uv(p), 0), 'side_ok': self.uv(p)[1] * self.side0 > 0.0, 'on': mb_name(on),
                     'platform': bool(on is not None and (mb_isa(on, 'platform') or mb_isa(on.get_attach_parent_actor(), 'platform')))}
        ok = (t_ej is not None and t_d is not None and t_d - t_ej <= 8.0 and bool(fl) and t_r is not None and 4.0 <= t_r - t_d <= 6.5
              and where and where['side_ok'] and where['platform'])
        self.check('T3.2_eject_fall_death', self.ok(ok), 'pilot aboard, KillShip 0: ejected %s s after, fall death %s s after the ejection (want <= 8, '
                   '5.5-7 expected) %s, respawn %s s after the death (want 5), at %s (want a platform on the team\'s side)' % (
                       r(t_ej - t_k, 2) if t_ej else None, r(t_d - t_ej, 2) if (t_d and t_ej) else None, fl[:1],
                       r(t_r - t_d, 2) if (t_r and t_d) else None, where))

    def t_protect(self):
        """T3.4 (+ the free ship for T8.2)"""
        c = yield from self.foot()
        s = self.ship0() or (yield from self.until(self.ship0, 14.0))
        if self.free is None or not valid(self.free):
            before = self.names()
            self.cmd(self.w, 'Aura.Airship.Spawn')
            self.free = yield from self.until(lambda: next((x for x in self.ships(self.w) if x.get_name() not in before), None), 3.0)
            if self.free is not None:
                self.wind_off(self.free)
        # a fresh respawn: kill, then everything inside its 15 s of protection
        old, s, t_k, t_n = yield from self.kill_and_respawn()
        res = {'respawned': s is not None}
        if s is None or self.free is None:
            self.check('T3.4_spawn_protection', 'FAIL', 'no respawned ship (%s) or no free ship (%s)' % (s is not None, self.free is not None))
            return
        self.wind_off(s)
        side = self.side0
        sp = self.loc(s)
        fpos = self.world(self.u_of(s), self.uv(sp)[1] + side * 7000.0, self.uv(sp)[2])
        self.teleport(self.free, fpos, wrap180(math.degrees(math.atan2(sp[1] - fpos[1], sp[0] - fpos[0]))))
        res['protected_at_spawn'] = self.protected(s)
        hp = self.ship_hp(s)
        self.cmd(self.w, 'Aura.Match.DamageShip 0 100')
        yield from self.wait(0.4)
        res['damage_cmd'] = (hp, self.ship_hp(s))
        shots0 = sum(x.get_shot_count() for x in (self.free.get_editor_property('Turrets') or []) if valid(x))
        aimp = self.hull_aim(s, None, (0.0, 0.0, 200.0))
        self.cmd(self.w, 'Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(aimp))
        yield from self.wait(1.0)
        self.cmd(self.w, 'Aura.Airship.TurretFire 0')
        yield from self.wait(0.4)
        shots1 = sum(x.get_shot_count() for x in (self.free.get_editor_property('Turrets') or []) if valid(x))
        res['turret'] = (self.ship_hp(s), shots1 - shots0)
        bp = self.world(self.u_of(s), self.uv(sp)[1] + side * 1900.0, self.uv(sp)[2] + 200.0)
        try:
            unreal.AirshipCannonball.spawn_test_cannonball(self.w, mb_cls('ball_bp') or mb_cls('ball'), unreal.Vector(*bp),
                                                           unreal.Vector(*[(sp[i] - bp[i]) * 3.0 for i in range(3)]), self.free, 60.0, 0.0)
        except Exception:  # noqa: BLE001
            self.err('spawn_test_cannonball')
        yield from self.wait(1.2)
        res['cannonball'] = self.ship_hp(s)
        c = self.me()
        dp, _ = self.deck_point(self.free, -300.0, 0.0, c)
        self.tp_char(c, dp, self.yaw(self.free))
        yield from self.wait(0.5)
        t0 = self.now
        while self.now - t0 < 2.0:
            self.aim(self.w, self.pc, self.hull_aim(s, None, (0.0, 0.0, 150.0)))
            self.inject(self.w, 'IA_LMB')
            yield
        yield from self.wait(0.3)
        res['gun'] = self.ship_hp(s)
        res['still_protected'] = self.protected(s)
        res['since_spawn_s'] = r(self.now - t_n, 1)
        dp, _ = self.deck_point(s, -300.0, 300.0, c)
        self.tp_char(c, dp, self.yaw(s))
        yield from self.wait(0.3)
        yield from self.board()
        yield from self.wait(0.3)
        res['protected_after_board'] = self.protected(s)
        hp = self.ship_hp(s)
        php = self.health(self.me())
        self.cmd(self.w, 'Aura.Match.DamageShip 0 100')
        yield from self.wait(0.4)
        res['boarded'] = (hp, self.ship_hp(s), php, self.health(self.me()))
        self.cmd(self.w, 'Aura.Airship.Exit 0')
        yield from self.wait(0.5)
        c = yield from self.foot()
        old, s2, t_k2, t_n2 = yield from self.kill_and_respawn()
        if s2 is not None:
            self.wind_off(s2)
            yield from self.wait(float(self.setting('ShipSpawnProtection', 15.0)) + 0.5)
            hp = self.ship_hp(s2)
            res['protected_after_15s'] = self.protected(s2)
            self.cmd(self.w, 'Aura.Match.DamageShip 0 100')
            yield from self.wait(0.4)
            res['after_15s'] = (hp, self.ship_hp(s2))
        h0 = res['damage_cmd'][0]
        ok = (res['protected_at_spawn'] and res['damage_cmd'][1] == h0 and res['turret'][0] == h0 and res['turret'][1] > 0
              and res['cannonball'] == h0 and res['gun'] == h0 and res['since_spawn_s'] < 15.0 and not res['protected_after_board']
              and abs((res['boarded'][0] or 0) - (res['boarded'][1] or 0) - 100.0) <= 1.0
              and res.get('after_15s') and abs(res['after_15s'][0] - res['after_15s'][1] - 100.0) <= 1.0)
        self.check('T3.4_spawn_protection', self.ok(ok), 'respawned ship %s: hull health stays %s for DamageShip 100 %s, a free ship\'s turret '
                   'round (hp, shots) %s, a cannonball splash %s, the player\'s gun %s (team 0 on team 0: friendly fire blocks it too), %s s after '
                   'the respawn; boarded: protected %s, DamageShip 100 (hull, pilot) %s (want -100 hull; crew share on the pilot); 15.5 s '
                   'after another respawn without boarding: protected %s, %s (want -100)' % (
                       res['protected_at_spawn'], h0, res['damage_cmd'], res['turret'], res['cannonball'], res['gun'], res['since_spawn_s'],
                       res['protected_after_board'], res['boarded'], res.get('protected_after_15s'), res.get('after_15s')), res)

    def t_free(self):
        """T8.2"""
        if self.free is None or not valid(self.free):
            before = self.names()
            c = yield from self.foot()
            self.cmd(self.w, 'Aura.Airship.Spawn')
            self.free = yield from self.until(lambda: next((x for x in self.ships(self.w) if x.get_name() not in before), None), 3.0)
        f = self.free
        if f is None:
            self.check('T8.2_free_ship', 'FAIL', 'Aura.Airship.Spawn made no ship')
            return
        if self.piloting():
            self.cmd(self.w, 'Aura.Airship.Exit 0')
            yield from self.wait(0.5)
        c = self.me()
        team, ls = self.ship_team(f), self.lane_state(f)
        can = unreal.MyTeamLibrary.can_use_ship(c, f)
        dp, _ = self.deck_point(f, -300.0, 0.0, c)
        self.tp_char(c, dp, self.yaw(f))
        yield from self.wait(0.4)
        self.cmd(self.w, 'Aura.Airship.Board 0')
        on = yield from self.until(lambda: mb_same(self.pc.get_controlled_pawn(), f), 1.5)
        self.cmd(self.w, 'Aura.Airship.Exit 0')
        yield from self.wait(0.5)
        ok = team == 255 and ls == 'nolane' and can and bool(on)
        self.check('T8.2_free_ship', self.ok(ok), 'Aura.Airship.Spawn in the match: %s team %s (want 255), lane state %s (want NoLane), '
                   'CanUseShip(team 0 player) %s, Board took it %s' % (f.get_name(), team, ls, can, bool(on)))
        try:
            f.destroy_actor()
        except Exception:  # noqa: BLE001
            self.err('destroy_free')
        self.free = None
        yield from self.foot()

    def t_unlimited(self):
        """T3.5"""
        c = yield from self.foot()
        ts0 = self.team_state(self.w, 0) or {}
        news = []
        for k in range(4):
            yield from self.until(self.ship0, 14.0)
            old, new, t_k, t_n = yield from self.kill_and_respawn()
            news.append((mb_name(new), r(t_n - t_k, 2) if t_n else None))
        yield from self.wait(1.0)
        ts1 = self.team_state(self.w, 0) or {}
        ph = self.phase_of(self.w)
        self.xgrab('t3_5_ships_lost')
        lost = (ts1.get('ships_lost') or 0) - (ts0.get('ships_lost') or 0)
        ok = ph == 'inprogress' and lost == 4 and all(n for n, _ in news)
        self.check('T3.5_solo_unlimited', self.ok(ok), 'solo practice, 4 ships killed: phase %s (want InProgress), ShipsLost %s -> %s (+%d, want +4), '
                   'new ships (name, s after the kill) %s; HUD "SHIPS LOST" in the x grab' % (
                       ph, ts0.get('ships_lost'), ts1.get('ships_lost'), lost, news), {'team_before': ts0, 'team_after': ts1})

    def wave_def(self, sp, n):
        try:
            return mb_parse_export(sp.get_wave_definition(n).export_text())
        except Exception:  # noqa: BLE001
            self.err('wave_def')
            return {}

    def max_alive(self, sp):
        d = self.dump(self.w, 'state', 0.0)
        v = mb_get(d, 'swarm', 'spawners', 0, 'max_alive')
        if v is None:
            try:
                v = sp.get_editor_property('MaxAlive')
            except Exception:  # noqa: BLE001
                v = None
        return v

    def t_swarm4(self):
        """T4.2"""
        sps = unreal.GameplayStatics.get_all_actors_of_class(self.w, mb_cls('waves'))
        if not sps:
            self.check('T4.2_swarm_live', 'FAIL', 'no MechSentinelWaveSpawner in the world')
            return
        sp = sps[0]
        n = int(sp.get_current_wave_number()) + 1
        base, ma0 = self.wave_def(sp, n), self.max_alive(sp)
        self.cmd(self.w, 'Aura.Match.Swarm 4')
        yield from self.wait(0.5)
        hi, ma1 = self.wave_def(sp, n), self.max_alive(sp)
        self.keep_dump('t4_2_swarm_line', self.swarm_line(self.t_test0))
        self.cmd(self.w, 'Aura.Match.Swarm %d' % int(self.setting('DefaultRules.SwarmDifficulty', 1)))
        rat = {}
        for k in ('HealthMultiplier', 'DamageMultiplier'):
            try:
                rat[k] = r(float(hi[k]) / float(base[k]), 4)
            except Exception:  # noqa: BLE001
                rat[k] = None
        ok = all(v is not None and abs(v - 2.0) <= 0.02 for v in rat.values()) and ma1 is not None and abs(float(ma1) - 800.0) <= 1.0
        self.check('T4.2_swarm_live', self.ok(ok), 'Aura.Match.Swarm 4: wave %d multipliers / Normal %s (want 2.0 +-1 %%), MaxAlive %s -> %s (want '
                   '500 x 1.6 = 800)' % (n, rat, ma0, ma1), {'before': base, 'after': hi})

    def hook_series(self, label, n, prep, aim_fn=None):
        """n ship hooks; prep() is a generator that positions the player / ship and returns (character, ship)"""
        tries = []
        for i in range(n):
            got = yield from prep(i)
            if not got:
                tries.append({'i': i, 'landed': False, 'why': 'no setup'})
                continue
            c, s = got
            res = yield from self.hook_try(c, s, (lambda: aim_fn(s, c)) if aim_fn else (lambda: self.hull_aim(s, c)))
            res['i'] = i
            tries.append(res)
            if i == 0:
                self.xgrab('%s_hook' % label)
            yield from self.wait(0.5)
        return tries

    def prep_edge(self, i):
        c = yield from self.foot(edge=True)
        if c is None:
            return None
        s = self.ship0()
        if s is None:
            return None
        self.lane_teleport(self.u_of(c) + 1000.0)
        yield from self.wait(1.5)
        return c, self.ship0()

    def t_hook(self):
        """T6.1"""
        tries = yield from self.hook_series('t6_1', 5, self.prep_edge)
        land = [t for t in tries if t.get('landed') and t['t'] is not None and t['t'] <= 4.0]
        rej = [t for t in tries if t.get('rejected')]
        self.check('T6.1_ship_hook', self.ok(len(land) >= 4 and not rej), 'ship hook from the team-side platform edge onto the cruising ship: '
                   '%d of %d landed within 4 s (want >= 4 of 5), server rejections %d (want 0); per try %s' % (
                       len(land), len(tries), len(rej), [(t['i'], t.get('landed'), t.get('t'), t.get('start_gap_cm')) for t in tries]), tries)

    def t_reel_lane(self):
        """T6.3"""
        def prep_ramp(i):
            c = yield from self.foot(edge=True)
            if c is None:
                return None
            self.lane_teleport(self.u_of(c) - 6000.0)
            ok = yield from self.until(lambda: self.ship0() is not None and float(self.tele(self.ship0()).get('ForwardSpeedMS') or 0.0) >= 8.0, 8.0)
            return (c, self.ship0()) if ok else None

        def prep_cap(i):
            c = yield from self.foot(edge=True)
            if c is None:
                return None
            self.lane_teleport(self.u_of(c) + 1000.0)
            cap = self.u_of(c) + float(self.setting('LaneMaxLead', 4000.0))
            ok = yield from self.until(lambda: self.ship0() is not None and 0.0 < cap - self.u_of(self.ship0()) < 2500.0
                                       and float(self.tele(self.ship0()).get('ForwardSpeedMS') or 0.0) > 1.0, 10.0)
            return (c, self.ship0()) if ok else None
        a = yield from self.hook_series('t6_3a', 5, prep_ramp)
        b = yield from self.hook_series('t6_3b', 5, prep_cap)
        la = [t for t in a if t.get('landed')]
        lb = [t for t in b if t.get('landed')]
        rej = [t for t in a + b if t.get('rejected')]
        reel = any(t.get('clamp_reel') for t in a + b)
        self.check('T6.3_reel_lane', self.ok(len(la) >= 4 and len(lb) >= 4 and not rej and reel), 'ship hook on a lane ship (a) in the catch-up '
                   'ramp: %d / 5 landed, (b) easing into the cap: %d / 5 landed (want >= 4 each), rejections %d (want 0), Clamp Reel seen %s' % (
                       len(la), len(lb), len(rej), reel), {'ramp': a, 'cap': b})

    def t_hook_turret(self):
        """T6.4"""
        def aim_turret(s, c):
            ts = [t for t in (s.get_editor_property('Turrets') or []) if valid(t)]
            if not ts:
                return self.hull_aim(s, c)
            t = min(ts, key=lambda x: dist(self.loc(x), self.loc(c)))
            return self.loc(t)
        tries = yield from self.hook_series('t6_4', 3, self.prep_edge, aim_turret)
        land = [t for t in tries if t.get('landed')]
        rej = [t for t in tries if t.get('rejected')]
        self.check('T6.4_hook_turret', self.ok(len(land) >= 2 and not rej), 'crosshair on the own ship\'s nearest turret: %d / 3 landed (want '
                   'accepted and landing), rejections %d' % (len(land), len(rej)), tries)

    def t_hook_drift(self):
        """T6.2"""
        c = yield from self.foot(edge=True)
        s = self.ship0()
        if c is None or s is None:
            self.check('T6.2_hook_drift', 'FAIL', 'no player / ship')
            return
        self.lane_teleport(self.u_of(c) - 4000.0)
        yield from self.wait(0.5)
        self.cmd(self.w, 'Aura.Airship.Input 0.7 0.6')
        fast = yield from self.until(lambda: float(self.tele(s).get('SpeedMS') or 0.0) >= 23.0, 12.0)
        res = yield from self.hook_try(c, s, lambda: self.hull_aim(s, c), limit=5.0)
        self.cmd(self.w, 'Aura.Airship.InputClear')
        stuck = yield from self.until(lambda: self.move_mode(c) not in ('custom', None) or not self.alive(c), 6.0)
        ok = bool(fast) and (res['ended'] or res['rejected'] or res['landed']) and bool(stuck)
        self.check('T6.2_hook_drift', self.ok(ok), 'ship at %s m/s turning (debug input): hook %s; server ended the reel %s / rejected %s (want the '
                   'drift end: 6 m + 0.3 s x speed), movement mode after %s (not stuck in root motion: %s)' % (
                       r(self.tele(s).get('SpeedMS'), 1), {'landed': res['landed'], 't': res['t']}, res['ended'][:1], res['rejected'][:1],
                       res['mode_after'], bool(stuck)), res)

    def t_hud(self):
        """T7.1"""
        ws = []
        try:
            for x in mb_objects('hud', self.w):
                try:
                    ws.append((x.get_name(), bool(x.is_in_viewport()), mb_nz(x.get_visibility())))
                except Exception:  # noqa: BLE001
                    ws.append((x.get_name(), None, None))
        except Exception:  # noqa: BLE001
            self.err('hud')
        self.xgrab('t7_1_hud')
        yield from self.wait(0.5)
        self.check('T7.1_hud', self.ok(any(w[1] for w in ws)), 'UMyMatchHUDWidget in this world %s (want one in the viewport); x grabs asked so '
                   'far %s (match bar, LANE rows Assist / PilotedInLane / OutOfLane, recall timer, ships lost; T3.3 adds the end panel)' % (
                       ws, [x['label'] for x in self.R['xgrabs']]))

    def t_over(self):
        """T3.3"""
        c = yield from self.foot()
        d0 = self.dump(self.w, 'before_end', 0.0)
        self.keep_dump('t3_3_before', d0)
        self.cmd(self.w, 'Aura.Match.Set bSoloPracticeUnlimitedShips 0')
        kills = []
        for k in range(6):
            if self.phase_of(self.w) == 'ended':
                break
            s = yield from self.until(lambda: self.ship0() or self.phase_of(self.w) == 'ended', 14.0)
            if self.phase_of(self.w) == 'ended':
                break
            old, new, t_k, t_n = yield from self.kill_and_respawn(timeout=float(self.setting('ShipRespawnDelay', 10.0)) + 2.0)
            kills.append((r(t_k, 1), mb_name(new), self.phase_of(self.w)))
        t_end = self.now
        ended = yield from self.until(lambda: self.phase_of(self.w) == 'ended', 3.0)
        res = self.result_of(self.w)
        ts = self.team_state(self.w, 0, 0.0) or {}
        yield from self.wait(1.0)
        self.xgrab('t3_3_end_panel')
        d1 = self.dump(self.w, 'ended', 0.0)
        old_world = self.w.get_path_name()
        rules0 = mb_get(d1, 'rules')
        es = float(self.setting('EndScreenSeconds', 20.0))
        # Ended as first seen by the per-frame phase track; the harness clock stops while the old world goes away, so the
        # first frame of the new world carries the restart time
        t_e = next((x[0] for x in self.ptl if x[2] == 'ended' and x[0] >= self.t_test0 - 1e-3), self.now)
        gone = yield from self.until(lambda: self.D.get('new_world'), es + 15.0)
        t_gone = self.now
        back = yield from self.until(lambda: valid(self.w) and self.D.get('new_world') and self.phase_of(self.w) not in (None,), 30.0)
        yield from self.wait(1.0)
        d2 = self.dump(self.w, 'after_restart', 0.0) if valid(self.w) else None
        self.keep_dump('t3_3_after', d2)
        same_rules = rules0 is not None and mb_get(d2, 'rules') == rules0
        ok = (ended and res.get('result') == 'practiceover' and ts.get('lives_left') == 0 and gone and abs(t_gone - t_e - es) <= 0.6 and back
              and same_rules)
        self.check('T3.3_practice_over', self.ok(ok), 'solo unlimited off, kills %s: Ended %s, result %s (want PracticeOver), LivesLeft %s (want 0); '
                   'end panel x grab; the map reloaded %.1f s later (want %.0f +-0.5; the world went away at the restart), new world %s, rules '
                   'kept %s (%s -> %s), round %s' % (
                       kills, bool(ended), res, ts.get('lives_left'), t_gone - t_e, es, self.D.get('new_world'), same_rules, rules0,
                       mb_get(d2, 'rules'), mb_get(d2, 'round')), {'old_world': old_world})

    # ------------------------------------------------------------------------------------------------- other passes
    def swarm_line(self, t0=0.0):
        """the game mode's last 'Swarm difficulty ...' line since t0, parsed"""
        ls = [l for _, l in self.log_since(t0, 'LogMatch', 'Swarm difficulty')]
        if not ls:
            return None
        l = ls[-1]
        out = {'line': l[-300:]}
        for k, pat in (('difficulty', r'Swarm difficulty (\d+)'), ('players', r'for (\d+) player'), ('count', r'count x([\d.]+)'),
                       ('count_factor', r'x players ([\d.]+)'), ('health', r'health x([\d.]+)'), ('damage', r'damage x([\d.]+)'),
                       ('max_alive', r'max alive x([\d.]+)'), ('attackers', r'attackers/player (\w+)'),
                       ('burrower_interval', r'Burrower interval x([\d.]+)'), ('burrower_level', r'level (\d+)')):
            m = re.search(pat, l)
            out[k] = (m.group(1) if k == 'attackers' else float(m.group(1))) if m else None
        return out

    def t_easy(self):
        """T4.1 (difficulty 0 from before PIE)"""
        sps = unreal.GameplayStatics.get_all_actors_of_class(self.w, mb_cls('waves'))
        if not sps:
            self.check('T4.1_easy', 'FAIL', 'no MechSentinelWaveSpawner in the world')
            return
        sp = sps[0]
        w1 = yield from self.until(lambda: int(sp.get_current_wave_number()) >= 1 and int(sp.get_current_wave_total()) > 0, 30.0)
        total = int(sp.get_current_wave_total()) if w1 else None
        n = int(sp.get_current_wave_number())
        easy = self.wave_def(sp, n)
        sw = self.swarm_line() or {}
        self.keep_dump('t4_1_swarm_line', sw)
        ma = self.max_alive(sp)
        bint = float(mb_cdo('burrower_settings').get_editor_property('SpawnInterval'))
        self.cmd(self.w, 'Aura.Match.Swarm 1')
        yield from self.wait(0.5)
        base = self.wave_def(sp, n)
        cf = float(sw.get('count_factor') or 1.0)
        want_total = round(float(base.get('Count') or 0.0) * 0.6 * cf) if base.get('Count') is not None else None
        rat = {}
        for k in ('HealthMultiplier', 'DamageMultiplier', 'ArmorMultiplier', 'SelfBuffChanceMultiplier'):
            try:
                rat[k] = r(float(easy[k]) / float(base[k]), 3) if float(base[k]) else None
            except Exception:  # noqa: BLE001
                rat[k] = None
        biv = (sw['burrower_interval'] * bint) if sw.get('burrower_interval') is not None else None
        ok = (total is not None and want_total is not None and abs(total - want_total) <= 1 and rat.get('HealthMultiplier') is not None
              and abs(rat['HealthMultiplier'] - 0.7) <= 0.01 and rat.get('SelfBuffChanceMultiplier') in (None, 0.5)
              and sw.get('difficulty') == 0 and str(sw.get('attackers')) == '6' and biv is not None and abs(biv - 45.0) <= 0.1)
        self.check('T4.1_easy', self.ok(ok), 'DefaultRules.SwarmDifficulty 0 before PIE: wave %d planned total %s (want round(base %s x 0.6 x count '
                   'factor %s) = %s +-1), multipliers Easy / Normal %s (want Health 0.7, SelfBuffChance 0.5 = the rules\' x 0.5), spawner '
                   'MaxAlive %s, the swarm line: difficulty %s, attackers/player %s (want 6), Burrower interval %s s (want 45 = %.0f x 1.5); %s' % (
                       n, total, base.get('Count'), cf, want_total, rat, ma, sw.get('difficulty'), sw.get('attackers'), r(biv, 1), bint,
                       sw.get('line')), {'easy': easy, 'normal': base, 'swarm': sw})

    def t_curve(self):
        """T2.12 (MaxYawDeviation 60 before PIE)"""
        sps = unreal.GameplayStatics.get_all_actors_of_class(self.w, mb_cls('spawner'))
        sp = sps[0] if sps else None
        c = yield from self.foot()
        if sp is None or c is None:
            self.check('T2.12_curved_lane', 'FAIL', 'no path spawner / player')
            return
        yaw = float(sp.get_editor_property('MaxYawDeviation'))
        spl = sp.get_path_spline()
        d = 0.0
        t0 = self.now
        while d < 110000.0 and self.now - t0 < 100.0:
            L = float(spl.get_spline_length())
            d = min(d + 5000.0, max(0.0, L - 3000.0))
            q = v3(spl.get_location_at_distance_along_spline(d, unreal.SplineCoordinateSpace.WORLD))
            c = self.me()
            if c is None:
                yield
                continue
            spot, _ = self.platform_spot(self.w, self.uv(q)[0], near_v=self.uv(q)[1], c=c)
            self.tp_char(c, spot or [q[0], q[1], q[2] + 300.0], self.frame['yaw'])
            yield from self.wait(1.0)
        L = float(spl.get_spline_length())
        tc = self.now
        self.cmd(self.w, 'Aura.Lane.Check')
        yield from self.wait(0.5)
        lines = [l for _, l in self.log_since(tc, 'Aura.Lane.Check')]
        gaps = {}
        for l in lines:
            m = re.search(r'side ([+-]?\d+): smallest hull-to-field gap (-?[\d.]+) m at u (-?[\d.]+) m', l)
            if m:
                gaps[int(m.group(1))] = (float(m.group(2)), float(m.group(3)))
        self.keep_dump('t2_12_lanes', self.lanes_of(self.dump(self.w, 'curve', 0.0)))
        ok = yaw >= 59.0 and L >= 100000.0 and len(gaps) == 2 and all(g[0] >= 13.0 for g in gaps.values())
        self.check('T2.12_curved_lane', self.ok(ok), 'MaxYawDeviation %.0f, path %.0f m long: Aura.Lane.Check smallest hull-to-field gap per side '
                   '(m, at u m) %s (want >= 13 m both sides); log %s' % (yaw, L / 100.0, gaps, [l[-200:] for l in lines[:3]]))


_old74 = globals().get('AS74_RUN')
if _old74 is not None and _old74.phase not in ('finished',):
    print('an as_74 run is active (phase %s): stop it first (as_74x_stop.py)' % _old74.phase)
else:
    AS74_RUN = B74()
    _ok74 = AS74_RUN.arm()
    if not _ok74:
        AS74_RUN.restore()
        AS74_RUN.remove_temp()
        AS74_RUN.phase = 'finished'
    for _l in AS74_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_74s_status.py; results in %s)' % AS74_RUN.OUTDIR if _ok74 else 'FAIL: not armed'))
