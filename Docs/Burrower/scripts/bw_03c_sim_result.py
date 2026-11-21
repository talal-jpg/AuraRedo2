# bw_03c_sim_result.py - judge Saved/Burrower/pa_sim.json written by bw_03b_sim_test.py; prints PASS/FAIL/WARN/INFO.
# Run in the editor (inbox harness) or with plain python3 (no unreal needed):
#   Docs/Burrower/scripts/harness/inbox.sh 03c Docs/Burrower/scripts/bw_03c_sim_result.py
#   python3 Docs/Burrower/scripts/bw_03c_sim_result.py
# Thresholds below can be changed and the script re-run without repeating the simulation.
import json, os, time


def _bw03c_module():
    """All code lives in this function scope: the inbox harness execs every script in one shared namespace."""
    import json, os, time  # local: closures below never see names rebound by other inbox scripts

    FALLBACK_JSON = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower/pa_sim.json'
    MAX_SPEED_FAIL = 3000.0          # cm/s; a 5 m drop lands at ~1000 cm/s
    JOINT_GAP_WARN, JOINT_GAP_FAIL = 5.0, 20.0           # cm, child bone origin vs parent's joint frame
    NEIGHBOUR_DEV_WARN, NEIGHBOUR_DEV_FAIL = 5.0, 20.0   # cm, neighbour bone distance vs rest
    SINK_FAIL = -30.0                # cm, lowest capsule below the floor top at the end
    FLOAT_WARN = 50.0                # cm, lowest capsule still above the floor at the end
    MIN_FALL = 200.0                 # cm, the body must have dropped at least this much
    DRIFT_WARN = 1500.0              # cm, horizontal travel of any body centre
    BONE_COM_WARN = 10.0             # cm, bone-derived capsule centre vs physics COM (stale bones?)
    MIN_PHYSICS_TIME_FRAC = 0.8
    STALE_RUNNING_S = 900.0

    _n = {'FAIL': 0, 'WARN': 0}


    def _p(tag, msg):
        if tag in _n:
            _n[tag] += 1
        print('%s: %s' % (tag, msg))


    def _path():
        try:
            import unreal
            return os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Burrower', 'pa_sim.json')
        except Exception:
            return FALLBACK_JSON


    def _bw03c_main():
        path = _path()
        if not os.path.exists(path):
            _p('FAIL', '%s not found: run bw_03b_sim_test.py first' % path)
            return
        with open(path) as f:
            d = json.load(f)
        age = time.time() - os.path.getmtime(path)
        st = d.get('status')
        _p('INFO', 'pa_sim.json: status %s, phase %s, mode %s, written %s UTC (%.0f s ago)'
           % (st, d.get('phase'), d.get('mode'), d.get('written_utc'), age))
        for w in d.get('warnings', []):
            _p('WARN', 'sim: %s' % w)
        for e in d.get('errors', []):
            _p('FAIL' if st == 'error' else 'WARN', 'sim error: %s' % str(e)[:600])
        if st == 'running':
            if age > STALE_RUNNING_S:
                _p('FAIL', 'still "running" but not updated for %.0f s: the editor or the state machine died. Stop PIE by '
                           'hand, remove TEMP_BurrowerSimTest if left, run bw_03b again.' % age)
            else:
                _p('INFO', 'still running: physics %.2f s of %.1f, game time %.2f s, %s samples. Run bw_03c again later.'
                   % (d.get('physics_time_est', 0), d.get('params', {}).get('sim_seconds', 0), d.get('game_time', 0),
                      len(d.get('samples', []))))
            return
        if st != 'done' or not d.get('samples'):
            _p('FAIL', 'no usable simulation result (status %s)' % st)
            return

        sim_s = float(d.get('params', {}).get('sim_seconds', 6.0))
        pt = float(d.get('physics_time_est', 0))
        _p('PASS' if pt >= MIN_PHYSICS_TIME_FRAC * sim_s else 'WARN', 'simulated %.2f s physics time (%.2f s game time, %s frames, %.1f fps)'
           % (pt, d.get('game_time', 0), d.get('frames'), d.get('avg_fps', 0)))
        sim = d.get('simulating_at_start') or {}
        _p('PASS' if sim and all(sim.values()) else 'WARN', 'all bodies simulating at the first PIE frame: %s%s'
           % (sim, '' if sim and all(sim.values()) else ' (bw_03b then called set_simulate_physics(True); the drop check below decides)'))

        pc = d.get('profile_check') or {}
        if pc.get('ok') is True:
            _p('PASS', 'runtime constraints (DefaultProfile = saved data): 4 joints, 20 deg limited swing1/swing2/twist, '
                       'linear locked, collision disabled')
        elif pc.get('ok') is False:
            _p('FAIL', 'runtime constraints differ from the asset intent (DefaultProfile not in sync?): before %s after %s'
               % (pc.get('before_apply'), pc.get('after_apply')))
        else:
            _p('WARN', 'runtime constraint check not available: %s' % pc.get('error'))

        _p('FAIL' if d.get('nan_found') else 'PASS', 'NaN/inf in body state: %s' % (d.get('nan_first') or 'none'))
        ms = d.get('max_speed', {})
        _p('PASS' if float(ms.get('value', 1e9)) < MAX_SPEED_FAIL else 'FAIL',
           'max body speed %.0f cm/s (%s at %s s; limit %.0f)' % (float(ms.get('value', -1)), ms.get('body'), ms.get('t'), MAX_SPEED_FAIL))

        g = d.get('max_joint_gap_cm')
        if g is None:
            _p('WARN', 'no joint gap data')
        else:
            tag = 'PASS' if g <= JOINT_GAP_WARN else ('WARN' if g <= JOINT_GAP_FAIL else 'FAIL')
            _p(tag, 'max joint gap %.2f cm (constraints hold if small): %s' % (g, d.get('joint_gap_cm')))
        nd = d.get('max_neighbour_dev_cm')
        if nd is not None:
            tag = 'PASS' if nd <= NEIGHBOUR_DEV_WARN else ('WARN' if nd <= NEIGHBOUR_DEV_FAIL else 'FAIL')
            _p(tag, 'max neighbour bone distance change %.2f cm vs rest: %s' % (nd, d.get('neighbour_bone_dist')))
        _p('INFO', 'body centre distance ranges (bend changes these a little): %s' % d.get('com_dist_range_cm'))
        bce = d.get('bone_vs_com_max_err_cm')
        if bce is not None:
            _p('PASS' if bce <= BONE_COM_WARN else 'WARN', 'bone transforms follow the bodies (capsule centre vs COM max %.2f cm)%s'
               % (bce, '' if bce <= BONE_COM_WARN else ': bones stale, gap/distance numbers unreliable'))

        fin = d.get('final_min_bottom_above_floor_cm')
        if fin is None:
            _p('FAIL', 'no height data')
        else:
            off = d.get('off_floor_bodies') or []
            tag = 'FAIL' if fin < SINK_FAIL else ('WARN' if fin > FLOAT_WARN else 'PASS')
            if tag == 'FAIL' and off:
                tag = 'WARN'  # hanging over / off the template floor edge, not sinking through it
            _p(tag, 'final lowest capsule %.1f cm above the floor top (start %.1f, lowest ever %.1f)%s'
               % (fin, d.get('start_min_bottom_above_floor_cm', float('nan')), d.get('min_bottom_ever_above_floor_cm', float('nan')),
                  ('; bodies past the floor edge: %s (floor too small; move or enlarge it, re-run)' % off) if off else ''))
            fell = float(d.get('fell_cm', 0))
            _p('PASS' if fell >= MIN_FALL else 'FAIL', 'dropped %.0f cm (needs >= %.0f: the simulation ran)' % (fell, MIN_FALL))
        _p('INFO', 'final body centres above the floor: %s' % d.get('final_com_above_floor_cm'))
        dr = d.get('drift_xy_max_cm')
        if dr is not None:
            _p('PASS' if dr <= DRIFT_WARN else 'WARN', 'max horizontal travel %.0f cm' % dr)
        rest = d.get('rest') or {}
        if rest:
            _p('PASS' if rest.get('came_to_rest') else 'WARN', 'came to rest: %s (max speed %.1f cm/s in the last %.1f s)'
               % (rest.get('came_to_rest'), rest.get('max_speed_in_window', -1), rest.get('window_s', 0)))
        _p('INFO', 'TEMP actors removed after the run: %s' % d.get('temp_actors_removed'))
        if _n['FAIL']:
            _p('FAIL', 'PA_Burrower simulation check: %d FAIL, %d WARN' % (_n['FAIL'], _n['WARN']))
        else:
            _p('PASS', 'PA_Burrower simulation does not explode (%d WARN)' % _n['WARN'])


    def _bw03c_run():
        try:
            _bw03c_main()
        except Exception as e:
            import traceback
            print('FAIL: bw_03c crashed: %r\n%s' % (e, traceback.format_exc()))
    return _bw03c_run


try:
    _bw03c_module()()
except Exception as _e:
    print('FAIL: bw_03c could not start: %r' % (_e,))
