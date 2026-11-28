# as_76_regress.py - round 2 PR B regression of PR A's PIE harnesses with the match off and on (SPEC_B section 3, T8.1).
# One arm runs PR A's harnesses one after the other in this editor session (each arms its own PIE; as_76's Slate callback
# waits for each to finish, files its results and arms the next), then compares every check's status:
#   off stages (Aura.Match.Enable 0): the result must equal PR A's own last result (the baseline copied at arm time from
#     Saved/Airship/..., before the first stage overwrites it): T8.1 "the same result as before PR B"
#   on stages (Aura.Match.Enable 1, L_AirshipTest, a TEMP_AS76_LaneOrigin MatchLaneOrigin at (0, 60000, 1400) so the solo
#     practice team ship gets its lane 525-675 m away from every PR A test spot, FallbackLaneHalfWidth 5000): the result
#     must equal the same harness's off stage apart from the expected differences listed in AS76_EXPECTED (an extra team
#     ship in the world that the every-ship console commands also reach, the sentinel bullet tag rule)
# Standalone stages (L_AirshipTest open, the ini Standalone): as59_off, as43_off, as59_on (default).
# Listen stages (L_AirshipTest open, the ini listen 2): as45_off, as60_off, as60_on (run_b_listen.sh B_REGRESS=1).
# The fall death is off in the on stages (UMyMatchSettings.FallDeathDepth 0): L_AirshipTest's ground is 200 m below the
# fallback lane, and PR A's ejection tests expect their characters to land there (a StartupMap rule, B9.6).
# Run: Docs/Airship/scripts/harness/inbox.sh 76 Docs/Airship/scripts/ue/as_76_regress.py 60 (or _AirshipWork_logs/run_b_pie.sh)
#   status: inbox.sh 76s Docs/Airship/scripts/ue/as_76s_status.py 30    stop: inbox.sh 76x Docs/Airship/scripts/ue/as_76x_stop.py 30
# Knobs: AS76_STAGES = (...), AS76_BASELINES = {'as59': <json path>, ...} (default: PR A's result files), the child
#   harnesses' own knobs (AS59_*, AS43_*, AS45_*, AS60_*) are set to their defaults before each stage unless AS76_KEEP_KNOBS.
# Results: Saved/Match/b76/ (b76_result.json, b76_report.txt, b76_log.txt, b76_status.txt, <stage>/ = the child's files,
#   baseline_<harness>.json).
import json, os, re, shutil, time, traceback  # unreal = inbox namespace

_AS76_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(compile(open(os.path.join(_AS76_UE, 'as_70_matchlib.py')).read(), os.path.join(_AS76_UE, 'as_70_matchlib.py'), 'exec'), globals())

AS76_VERSION = 'as_76_regress 2026-11-25'
AS76_AIRSHIP = os.path.join(MB_SAVED, 'Airship')
# harness -> (script, run object name, results folder under Saved/Airship, result json, play mode, default knobs)
AS76_HARNESS = {
    'as59': ('as_59_pie_round2.py', 'AS59_RUN', 'round2', 'r2_result.json', 'standalone',
             {'AS59_ONLY': (), 'AS59_SCHEME': 3, 'AS59_AIM_SCHEME': 0, 'AS59_DRIFT_SCHEMES': (3, 1, 0)}),
    'as43': ('as_43_pie_validate.py', 'AS43_RUN', 'val', 'val_result.json', 'standalone', {}),
    'as45': ('as_45_pie_mp.py', 'AS45_RUN', 'mp', 'mp_result.json', 'listen', {}),
    'as60': ('as_60_pie_mp_round2.py', 'AS60_RUN', 'round2_mp', 'r2mp_result.json', 'listen',
             {'AS60_ONLY': (), 'AS60_LAG_MS': 100.0, 'AS60_SCHEME': 3, 'AS60_AIM_SCHEME': 0, 'AS60_CRUISE_THROTTLE': 1.0}),
}
AS76_BASELINE_DEFAULT = {'as59': ['round2_final_sa/r2_result.json', 'round2/r2_result.json'], 'as43': ['val/val_result.json'],
                         'as45': ['mp/mp_result.json'], 'as60': ['round2_mp/r2mp_result.json']}
# check keys (regular expressions) whose status may change with the match on, and why
AS76_EXPECTED = [
    (r'^T10\.1', 'the console scan sees the extra team ship\'s lines (Kill / Damage / TurretFire reach every ship)'),
    (r'^T3\.[123]', 'sentinel bullet tags: an undriven team ship carries none (B6.4); free ships keep PR A\'s tags'),
    (r'^T6\.[45]', 'TurretFire reaches every ship\'s unmanned turrets, the team ship\'s too (out of range of the targets)'),
    (r'^T5\.11|^T4\.2', 'Aura.Airship.Kill / Damage hit the team ship as well (it respawns in solo practice)'),
    (r'^setup_ship2$', 'the ship list holds the team ship as well'),
]
AS76_LANE_ORIGIN = (0.0, 60000.0, 1400.0)


def as76_checks(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return dict((k, v.get('status')) for k, v in (d.get('checks') or {}).items()), d.get('reason'), d.get('version')
    except Exception:  # noqa: BLE001
        return None, None, None


class B76(MBRun):
    TAG = 'b76'
    VERSION = AS76_VERSION
    TEMP = 'TEMP_AS76_'
    OUTDIR = os.path.join(MB_MATCH, 'b76')

    def __init__(self):
        MBRun.__init__(self)
        g = globals()
        self.cfg['stages'] = tuple(g.get('AS76_STAGES') or ('as59_off', 'as43_off', 'as59_on'))
        self.cfg['baselines'] = dict(g.get('AS76_BASELINES') or {})
        self.cfg['keep_knobs'] = bool(g.get('AS76_KEEP_KNOBS'))
        self.R['cfg'] = self.cfg
        self.si = -1
        self.stage = None
        self.child = None
        self.stage_wall = 0.0
        self.results = {}

    def status_text(self):
        c = self.child_run()
        return 'b76 phase %s stage %s (%d/%d) wall %.0f s, results %s, done %s, reason %s | child: %s' % (
            self.phase, self.stage, self.si + 1, len(self.cfg['stages']), time.time() - self.wall0,
            dict((k, v.get('verdict')) for k, v in self.results.items()), self.R['done'], self.R.get('reason'),
            c.status_text() if c is not None and hasattr(c, 'status_text') else None)

    def child_run(self):
        if self.stage is None:
            return None
        return globals().get(AS76_HARNESS[self.stage.split('_')[0]][1])

    def arm(self):
        os.makedirs(self.OUTDIR, exist_ok=True)
        with open(self.path('log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (self.VERSION, self.R['armed_utc'], self.cfg))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running: not armed')
            return False
        if 'L_AirshipTest' not in mb_editor_world().get_path_name():
            self.line('FAIL', 'open /Game/Assets/MyShip/Drivable/Maps/L_AirshipTest first (editor world %s)' % mb_editor_world().get_path_name())
            return False
        for st in self.cfg['stages']:
            if st.split('_')[0] not in AS76_HARNESS or st.split('_')[-1] not in ('off', 'on'):
                self.line('FAIL', 'unknown stage %s' % st)
                return False
            if not os.path.exists(os.path.join(MB_UE, AS76_HARNESS[st.split('_')[0]][0])):
                self.line('FAIL', '%s is missing (PR A not merged here?)' % AS76_HARNESS[st.split('_')[0]][0])
                return False
        ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
        pls = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients'])
        modes = set(AS76_HARNESS[st.split('_')[0]][4] for st in self.cfg['stages'])
        if 'listen' in modes and 'ListenServer' not in str(pls.get('PlayNetMode')):
            self.line('FAIL', 'listen stages need the ini in listen mode with 2 players (set_play_mode.sh listen 2): %s' % pls)
            return False
        if 'listen' in modes and 'standalone' in modes:
            self.line('FAIL', 'standalone and listen stages need different play modes: run them in two editor sessions')
            return False
        # PR A's own results, before the first stage overwrites them
        for h in sorted(set(st.split('_')[0] for st in self.cfg['stages'])):
            cands = [self.cfg['baselines'][h]] if h in self.cfg['baselines'] else [os.path.join(AS76_AIRSHIP, p) for p in AS76_BASELINE_DEFAULT[h]]
            src = next((p for p in cands if os.path.exists(p)), None)
            dst = os.path.join(self.OUTDIR, 'baseline_%s.json' % h)
            if src:
                shutil.copyfile(src, dst)
                self.line('INFO', 'baseline for %s: %s' % (h, src))
            else:
                self.line('WARN', 'no baseline result for %s (looked at %s): the off stage is only reported' % (h, cands))
            self.R['setup']['baseline_' + h] = src
        self.snapshot_settings()
        self.phase = 'next_stage'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed: stages %s' % (self.cfg['stages'],))
        return True

    def _tick(self):
        if self.phase == 'finished':
            return
        if self.phase == 'ending':
            self.end_tick()
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.log_poll()
        if self.user_play:
            self.finish('the user pressed Play: stopping')
            return
        if self.phase == 'next_stage':
            if les.is_in_play_in_editor():
                return
            self.si += 1
            if self.si >= len(self.cfg['stages']):
                self.compare()
                self.finish('all stages done')
                return
            self.stage = self.cfg['stages'][self.si]
            self.start_stage()
            return
        if self.phase == 'stage_running':
            c = self.child_run()
            if c is None or getattr(c, 'phase', None) == 'finished':
                self.end_stage()
            elif time.time() - self.stage_wall > 3600:
                self.line('FAIL', 'stage %s still running after 60 min: stopping it' % self.stage)
                try:
                    c.finish('stopped by as_76 (60 min)')
                except Exception:  # noqa: BLE001
                    self.err('stop_child')
                self.stage_wall = time.time() + 1e9
            return

    def start_stage(self):
        h, on = self.stage.split('_')[0], self.stage.endswith('_on')
        script, run_name, folder, res, mode, knobs = AS76_HARNESS[h]
        self.restore_settings()
        mb_editor_cmd('Aura.Match.Enable %d' % (1 if on else 0))
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for a in eas.get_all_level_actors():
            if a.get_actor_label().startswith(self.TEMP):
                eas.destroy_actor(a)
        if on:
            tp = eas.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(*AS76_LANE_ORIGIN), unreal.Rotator(0, 0, 0))
            tp.set_actor_label(self.TEMP + 'LaneOrigin')
            tp.tags = [unreal.Name('MatchLaneOrigin')]
            self.set_setting('FallbackLaneHalfWidth', 5000.0)
            self.set_setting('FallDeathDepth', 0.0)
        if not self.cfg['keep_knobs']:
            for k, v in knobs.items():
                globals()[k] = v
        self.line('INFO', '==== stage %s: Aura.Match.Enable %d, %s' % (self.stage, 1 if on else 0, script))
        buf = []
        try:
            import io, contextlib
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exec(compile(open(os.path.join(MB_UE, script)).read(), os.path.join(MB_UE, script), 'exec'), globals())
            buf = out.getvalue().splitlines()
        except Exception:  # noqa: BLE001
            self.err('arm_' + self.stage)
        armed = any('RESULT: ARMED' in l for l in buf)
        self.R.setdefault('stage_arm', {})[self.stage] = buf[-6:]
        if not armed:
            self.line('FAIL', 'stage %s did not arm: %s' % (self.stage, buf[-4:]))
            self.results[self.stage] = {'verdict': 'NOT ARMED', 'arm': buf[-6:]}
            self.phase = 'next_stage'
            return
        self.stage_wall = time.time()
        self.phase = 'stage_running'

    def end_stage(self):
        h = self.stage.split('_')[0]
        folder, res = AS76_HARNESS[h][2], AS76_HARNESS[h][3]
        src = os.path.join(AS76_AIRSHIP, folder)
        dst = os.path.join(self.OUTDIR, self.stage)
        try:
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('stills', 'xgrab', '*.png'))
        except Exception:  # noqa: BLE001
            self.err('copy_' + self.stage)
        checks, reason, ver = as76_checks(os.path.join(dst, res))
        self.results[self.stage] = {'checks': checks, 'reason': reason, 'version': ver}
        self.line('INFO', 'stage %s finished (%s): %s' % (self.stage, reason, self.count(checks)))
        if self.stage.endswith('_on'):
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(self.TEMP):
                    eas.destroy_actor(a)
        self.restore_settings()
        self.write(True)
        self.phase = 'next_stage'

    def count(self, checks):
        c = {}
        for v in (checks or {}).values():
            c[v] = c.get(v, 0) + 1
        return c

    def diff(self, a, b, expected=None):
        """checks whose status differs between two runs (a = reference): (key, a, b, why-expected or None)"""
        out = []
        for k in sorted(set(a) | set(b)):
            sa, sb = a.get(k), b.get(k)
            if sa == sb:
                continue
            why = None
            for pat, w in (expected or []):
                if re.search(pat, k):
                    why = w
                    break
            out.append((k, sa, sb, why))
        return out

    def compare(self):
        for st, rr in self.results.items():
            if rr.get('checks') is None:
                self.check(st, 'FAIL', 'stage %s gave no result (%s)' % (st, rr.get('verdict') or rr.get('reason')))
                rr['verdict'] = rr.get('verdict') or 'NO RESULT'
                continue
            h = st.split('_')[0]
            if st.endswith('_off'):
                base, _, bver = as76_checks(os.path.join(self.OUTDIR, 'baseline_%s.json' % h))
                if base is None:
                    self.check('T8.1_%s' % st, 'INFO', 'match off: %s (no PR A baseline to compare)' % self.count(rr['checks']))
                    rr['verdict'] = 'NO BASELINE'
                    continue
                d = self.diff(base, rr['checks'])
                worse = [x for x in d if x[1] == 'PASS' and x[2] != 'PASS']
                rr['diff'], rr['verdict'] = d, 'SAME' if not d else ('WORSE' if worse else 'CHANGED')
                self.check('T8.1_%s' % st, 'PASS' if not worse else 'FAIL', 'match off (Aura.Match.Enable 0) vs PR A\'s result (%s): %d checks '
                           'differ, %d were PASS before: %s' % (bver, len(d), len(worse), d[:20]), {'diff': d})
            else:
                off = self.results.get(h + '_off', {}).get('checks')
                if off is None:
                    off, _, _ = as76_checks(os.path.join(self.OUTDIR, 'baseline_%s.json' % h))
                if off is None:
                    self.check('T8.1_%s' % st, 'INFO', 'match on: %s (nothing to compare with)' % self.count(rr['checks']))
                    rr['verdict'] = 'NO REFERENCE'
                    continue
                d = self.diff(off, rr['checks'], AS76_EXPECTED)
                bad = [x for x in d if x[3] is None and x[1] == 'PASS' and x[2] != 'PASS']
                rr['diff'], rr['verdict'] = d, 'SAME' if not d else ('UNEXPECTED' if bad else 'EXPECTED ONLY')
                self.check('T8.1_%s' % st, 'PASS' if not bad else 'FAIL', 'match on (solo practice team ship on a far fallback lane) vs off: %d '
                           'checks differ, %d unexpected PASS -> not PASS: %s; expected ones %s' % (
                               len(d), len(bad), bad[:20], [(x[0], x[1], x[2]) for x in d if x[3]][:20]), {'diff': d})
        self.R['stages'] = self.results

    def restore(self):
        MBRun.restore(self)


_old76 = globals().get('AS76_RUN')
if _old76 is not None and _old76.phase not in ('finished',):
    print('an as_76 run is active (phase %s): stop it first (as_76x_stop.py)' % _old76.phase)
else:
    AS76_RUN = B76()
    _ok76 = AS76_RUN.arm()
    if not _ok76:
        AS76_RUN.restore()
        AS76_RUN.phase = 'finished'
    for _l in AS76_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_76s_status.py; results in %s)' % AS76_RUN.OUTDIR if _ok76 else 'FAIL: not armed'))
