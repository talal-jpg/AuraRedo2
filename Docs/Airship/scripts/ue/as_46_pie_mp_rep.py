# as_46_pie_mp_rep.py - multiplayer PIE run 2 (2026-11-22): (1) the client's cannon volleys again with the fixed ball
# tracker (port, starboard, port), (2) the client's ship replication compared under 4 variants x {no lag, Net PktLag}:
#   v0  RepMode 0 (EPhysicsReplicationMode::Default), the engine's own net update schedule (NetUpdateFrequency 60 with
#       the random delay of UNetDriver::ServerReplicateActors: at a 30 Hz server about every other frame)
#   v1  RepMode 0 + ForceNetUpdate on the server copy every frame (from Python: what a C++ fix would do)
#   v2  RepMode 1 (PredictiveInterpolation), engine schedule
#   v3  RepMode 1 + ForceNetUpdate every frame
# Before each flight the server ship is put back at (0, 2500, 1600) yaw 0 at rest, and the settings are switched; each
# flight is the same client DebugSetInput schedule (throttle 1 at 0.5 s, steer right at 5 s, left at 8 s, brake at
# 10 s). Built on as_45_pie_mp.py (its MpRun class, exec'd without its arm block). Listen server, 2 players (the ini).
# Run (L_AirshipTest open, no PIE): inbox.sh 46 Docs/Airship/scripts/ue/as_46_pie_mp_rep.py 60; status: inbox.sh 46s
# with AS45_RUN -> as_45s_mp_status.py works on this run too (it is stored as AS45_RUN).
# Results: Saved/Airship/mp/mp2_result.json, mp2_report.txt (the variant table at the top), mp_log.txt.
import json, math, os, time, traceback  # unreal = inbox namespace

AS46_AS45 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_45_pie_mp.py'
_as46_src = open(AS46_AS45).read()
exec(compile(_as46_src[:_as46_src.index("\nif 'AS45_RUN' in globals()")], AS46_AS45, 'exec'), globals())

AS46_VERSION = 'as_46_pie_mp_rep 2026-11-22'
START = (0.0, 2500.0, 1600.0)
# (name, Aura.Airship.RepMode, every-frame replication, Net PktLag). Every-frame replication comes from Python
# (ForceNetUpdate each frame, the emulation used in run 2) or, with AS46_FNU_MODE = 'property' (set before exec, the
# runs after the C++ fix), from AAirshipPawn::bReplicateEveryFrame on the server copy. AS46_VARIANTS overrides the list.
VARIANTS = globals().get('AS46_VARIANTS') or [('v0a', 0, False, False), ('v0b', 0, False, True), ('v1a', 0, True, False), ('v1b', 0, True, True),
            ('v2a', 1, False, False), ('v2b', 1, False, True), ('v3a', 1, True, False), ('v3b', 1, True, True)]
AS46_MODE = globals().get('AS46_FNU_MODE') or 'python'
AS46_TAG = globals().get('AS46_TAG') or 'mp2'          # result files <tag>_result.json / <tag>_report.txt
PHASES = [('settle', 3.0), ('board_tp', 3.0), ('board', 3.0), ('hover', 2.0), ('cannons', 12.0)]
for _v in VARIANTS:
    PHASES += [('g' + _v[0][1:], 3.0), (_v[0], 12.0)]
PER_FRAME = tuple(['hover', 'cannons'] + [p for p, d in PHASES if p[0] in 'gv' and p[1:2].isdigit()])
FLY = [(0.0, 'start', NEUTRAL), (0.5, 'E1_throttle', (1.0, 0.0, 0.0, 0.0, False, False)),
       (5.0, 'E2_steer_right', (1.0, 1.0, 0.0, 0.0, False, False)), (8.0, 'E3_steer_left', (1.0, -1.0, 0.0, 0.0, False, False)),
       (10.0, 'E4_brake', BRAKE), (11.5, 'neutral', NEUTRAL)]
VOLLEYS = [(1.6, 'port', 'p1'), (5.2, 'stbd', 's1'), (8.8, 'port', 'p2')]


class MpRep(MpRun):
    def __init__(self):
        MpRun.__init__(self)
        self.R['version'] = AS46_VERSION
        self.R['variants'] = {}
        self.R['fnu_mode'] = AS46_MODE
        self.fnu = False
        self.fnu_calls = 0

    def write(self, force=False):
        if not force:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        try:
            with open(os.path.join(MP, AS46_TAG + '_result.json'), 'w') as f:
                json.dump(self.R, f, default=str)
        except Exception:  # noqa: BLE001
            pass

    def end_tick(self):
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and time.time() - self.end_wall < 20.0 and not self.user_play:
            return
        self.restore()
        try:
            ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            unreal.SystemLibrary.execute_console_command(ew, 'Aura.Airship.RepMode 0')
        except Exception:  # noqa: BLE001
            self.err('restore_repmode')
        if not les.is_in_play_in_editor():
            self.remove_temp()
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        self.phase = 'finished'
        self.R['done'] = True
        self.write(True)
        write_rep_report(self.R)
        self.line('INFO', 'done; results in mp/%s_result.json / _report.txt' % AS46_TAG)

    def _tick(self):
        MpRun._tick(self)
        # the emulated C++ fix: replicate the ship every server frame
        if self.fnu and self.phase not in ('ending', 'finished') and valid(self.ship_s):
            try:
                self.ship_s.force_net_update()
                self.fnu_calls += 1
            except Exception:  # noqa: BLE001
                self.err('force_net_update')

    # ---- cannons: three volleys, the impact is where a ball stops
    def start_cannons(self):
        self.D['vol'] = {}

    def ph_cannons(self, el):
        for t, side, lab in VOLLEYS:
            if t - 1.6 <= el < t:
                self.look(side)
            if el >= t and lab not in self.D['vol']:
                n0 = {'server': set(self.balls['server']), 'client': set(self.balls['client'])}
                self.D['side'] = lab
                self.D['vol'][lab] = {'t': r(self.now, 3), 'side': side, 'n0': n0,
                                      'mz_old': {'server': set(self.muzzle_comps(self.ship_s)), 'client': set(self.muzzle_comps(self.ship_c))},
                                      'mz': {'server': set(), 'client': set()}}
                self.inject('client', 'IA_AirshipFire')
                self.line('INFO', 'client fire %s (%s) injected' % (lab, side))
            v = self.D['vol'].get(lab)
            if v is not None and self.now - v['t'] <= 1.6:
                for key, ship in (('server', self.ship_s), ('client', self.ship_c)):
                    for c in self.muzzle_comps(ship):
                        if c not in v['mz_old'][key]:
                            v['mz'][key].add(c)
                if self.now - v['t'] >= 0.12 and 'cap' not in v:
                    v['cap'] = True
                    self.capture(self.sw, 'rep_cannons_' + lab, side, self.ship_s)

    def end_cannons(self):
        self.track_balls()
        ok, msgs, res = True, [], {}
        for t, side, lab in VOLLEYS:
            v = self.D['vol'].get(lab)
            if v is None:
                ok = False
                msgs.append('%s: not fired' % lab)
                continue
            wall_y = -9500.0 + 200.0 if side == 'port' else 14500.0 - 200.0
            out = {}
            for key in ('server', 'client'):
                bs = [b for k, b in self.balls[key].items() if k not in v['n0'][key] and b.get('side') == lab]
                hits = [b for b in bs if (b.get('hidden_at') or b.get('last')) and abs((b.get('hidden_at') or b['last'])[1] - wall_y) < 600.0]
                out[key] = {'balls': len(bs), 'at_wall': len(hits), 'stops': [b.get('hidden_at') or b.get('last') for b in bs],
                            'flight_s': [r((b.get('t_hit') or -1) - b['t0'], 2) for b in bs],
                            'hidden_first': [(b.get('t_hidden'), b['t0']) for b in bs], 'muzzle_fx': len(v['mz'][key])}
            vok = out['server']['balls'] == 2 and out['server']['at_wall'] == 2 and out['client']['balls'] == 2 and out['server']['muzzle_fx'] == 2 and out['client']['muzzle_fx'] == 2
            ok = ok and vok
            res[lab] = out
            msgs.append('%s (%s): %s' % (lab, side, out))
        self.check('c2_cannons_rerun', 'PASS' if ok else 'FAIL', 'three client volleys, impact = where the ball stops (wall y -9300 / '
                   '14300): ' + '; '.join(msgs), res)

    # ---- variant gaps / flights
    def start_gap(self, lab):
        cfg = [v for v in VARIANTS if v[0][1:] == lab[1:]][0]
        name, rep, fnu, lag = cfg
        self.ship_c.debug_set_input(*BRAKE)
        # back to the start at rest (server copy; the client copy is corrected toward it)
        self.ship_s.set_actor_location_and_rotation(unreal.Vector(*START), unreal.Rotator(0.0, 0.0, 0.0), False, True)
        h = self.ship_s.get_editor_property('HullCollision')
        h.set_physics_linear_velocity(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
        h.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
        self.cmd(self.sw, 'Aura.Airship.RepMode %d' % rep)
        if AS46_MODE == 'property':
            self.fnu = False
            self.ship_s.set_editor_property('bReplicateEveryFrame', bool(fnu))
            self.R['variants'].setdefault(name, {})['property_read'] = bool(self.ship_s.get_editor_property('bReplicateEveryFrame'))
        else:
            self.fnu = fnu
        n = self.R['mp'].get('pktlag') or int(round(max(100.0, min(1000.0, LAG_GAME_MS * FIXED_FPS / max(1.0, self.R['mp'].get('real_fps_hover') or 30.0)))))
        self.R['mp']['pktlag'] = n
        self.cmd(self.cw, 'Net PktLag=%d' % (n if lag else 0))
        self.cmd(self.sw, 'Net PktLag=%d' % (n if lag else 0))
        self.D['cfg'] = cfg
        self.D['fnu0'] = self.fnu_calls

    def ph_gap(self, el):
        if el >= 1.5 and 'neutral' not in self.D:
            self.D['neutral'] = True
            self.ship_c.debug_set_input(*NEUTRAL)

    def end_gap(self, lab):
        try:
            self.R['variants'].setdefault('v' + lab[1:], {})['rep_mode'] = {
                'server': en(self.ship_s.get_physics_replication_mode()), 'client': en(self.ship_c.get_physics_replication_mode())}
        except Exception:  # noqa: BLE001
            self.err('rep_mode_read')

    def ph_var(self, el):
        for t, name, inp in FLY:
            if el >= t and name not in self.D:
                self.D[name] = r(self.now, 3)
                self.ship_c.debug_set_input(*inp)
        self.host_aim(self.ship_s.get_actor_location())

    def end_var(self, lab):
        self.fly_eval(lab)
        e = self.R['mp'].get('err_' + lab)
        lat = self.R['mp'].get('lat_' + lab)
        cfg = [v for v in VARIANTS if v[0] == lab][0]
        rec = self.R['variants'].setdefault(lab, {})
        rec.update({'rep_mode_cvar': cfg[1], 'force_net_update': cfg[2], 'lag': cfg[3], 'pktlag_ms': self.R['mp'].get('pktlag') if cfg[3] else 0,
                    'err': e, 'lat': lat})
        # the as_45 check line (a4_<lab>) is kept; an INFO summary on top
        self.check('rep_' + lab, 'INFO', 'RepMode %d, ForceNetUpdate %s, lag %s: pos err mean/p95/max %s cm, lag fit %s frames -> residual %s, '
                   'client accel %s vs server %s, view accel %s (cm/frame^2), snaps %s'
                   % (cfg[1], cfg[2], cfg[3], e and [e['pos']['mean'], e['pos']['p95'], e['pos']['max']], e and e['lag_frames'],
                      e and [e['residual']['mean'], e['residual']['p95']], e and [e['acc_client']['mean'], e['acc_client']['p95'], e['acc_client']['max']],
                      e and [e['acc_server']['mean'], e['acc_server']['p95']], e and e.get('acc_view') and [e['acc_view']['mean'], e['acc_view']['p95'], e['acc_view']['max']],
                      e and e['snaps']['n_over_10cm_per_frame2']), rec)


def _as46_bind():
    for name, rep, fnu, lag in VARIANTS:
        g = 'g' + name[1:]
        setattr(MpRep, 'start_' + g, lambda self, _g=g: self.start_gap(_g))
        setattr(MpRep, 'ph_' + g, lambda self, el: self.ph_gap(el))
        setattr(MpRep, 'end_' + g, lambda self, _g=g: self.end_gap(_g))
        setattr(MpRep, 'ph_' + name, lambda self, el: self.ph_var(el))
        setattr(MpRep, 'end_' + name, lambda self, _n=name: self.end_var(_n))


_as46_bind()


def write_rep_report(R):
    try:
        L = ['Airship multiplayer replication comparison (%s), armed %s, game time %.1f s, wall %.0f s, reason: %s' % (
            R['version'], R['armed_utc'], R.get('game_t', 0), R.get('wall_s', 0), R.get('reason'))]
        L.append('mp: %s' % dict((k, v) for k, v in R['mp'].items() if not k.startswith(('lat_', 'err_'))))
        L.append('')
        L.append('variant | RepMode | ForceNetUpdate | lag | pos err mean/p95/max cm | lag fit fr | residual mean/p95 | client accel mean/p95/max | '
                 'server accel mean/p95 | view accel mean/p95/max | snaps>10 | server_controls E1/E2 s | client_physics E1/E2 s | rep mode read')
        for lab, v in R['variants'].items():
            e = v.get('err') or {}
            lat = v.get('lat') or {}

            def g(d, *ks):
                for k in ks:
                    d = (d or {}).get(k)
                return d
            L.append('%s | %s | %s | %s | %s/%s/%s | %s | %s/%s | %s/%s/%s | %s/%s | %s/%s/%s | %s | %s/%s | %s/%s | %s' % (
                lab, v.get('rep_mode_cvar'), v.get('force_net_update'), v.get('pktlag_ms'), g(e, 'pos', 'mean'), g(e, 'pos', 'p95'), g(e, 'pos', 'max'),
                e.get('lag_frames'), g(e, 'residual', 'mean'), g(e, 'residual', 'p95'), g(e, 'acc_client', 'mean'), g(e, 'acc_client', 'p95'),
                g(e, 'acc_client', 'max'), g(e, 'acc_server', 'mean'), g(e, 'acc_server', 'p95'), g(e, 'acc_view', 'mean'), g(e, 'acc_view', 'p95'),
                g(e, 'acc_view', 'max'), g(e, 'snaps', 'n_over_10cm_per_frame2'), g(lat, 'E1_throttle', 'server_controls'), g(lat, 'E2_steer_right', 'server_controls'),
                g(lat, 'E1_throttle', 'client_physics'), g(lat, 'E2_steer_right', 'client_physics'), v.get('rep_mode')))
        L.append('')
        for k, c in R['checks'].items():
            L.append('%s %s [t %s]: %s' % (c['status'], k, c['t'], c['summary']))
            L.append('')
        L.append('script errors %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        for k, v in R['errors'].items():
            L.append('--- %s\n%s' % (k, v['last'][-900:]))
        for k, v in (R.get('log_scan') or {}).items():
            L.append('log %s: %d' % (k, v['count']))
            for s in v['sample'][:6]:
                L.append('    %s' % s[:300])
        L.append('log per phase: %s' % json.dumps(R.get('log_segments')))
        L.append('captures: %s' % [s['file'] for s in R['shots']])
        with open(os.path.join(MP, AS46_TAG + '_report.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        with open(os.path.join(MP, AS46_TAG + '_report.txt'), 'w') as f:
            f.write('report failed: %s' % traceback.format_exc())


if 'AS45_RUN' in globals() and AS45_RUN is not None and AS45_RUN.phase not in ('finished',):
    print('FAIL: a run is active (phase %s): not armed again' % AS45_RUN.phase)
else:
    AS45_RUN = MpRep()
    if not AS45_RUN.arm():
        AS45_RUN.restore()
        AS45_RUN.remove_temp()
        AS45_RUN.phase = 'finished'
    print('\n'.join(AS45_RUN.R['lines']))
