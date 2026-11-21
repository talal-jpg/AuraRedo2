# bw_pie_report.py - prints the result of a bw_pie_test.py run as PASS:/FAIL:/WARN:/INFO: lines.
# Plain Python 3 (no unreal needed): python3 bw_pie_report.py [pie_result.json] [--full]
# Also works through the inbox (harness/inbox.sh rep bw_pie_report.py); then it reads BW_REPORT_PATH or the default.
import json, os, sys

BW_REPORT_DEFAULT = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower/pie_result.json'
BW_REPORT_ORDER = ['setup', 'a_spawn', 'b_follow', 'c_wave', 'd_rotor', 'e_tiles', 'f_pipes', 'g_damage', 'h_death', 'i_respawn']
BW_REPORT_NAMES = {'setup': 'setup (listen server + client, pawns)', 'a_spawn': '(a) one Burrower per player, behind it',
                   'b_follow': '(b) follows its player', 'c_wave': '(c) body wave (J4 sideways vs J0)',
                   'd_rotor': '(d) rotor spins about X, stays in place', 'e_tiles': '(e) tiles collapse at the rotor box, client matches',
                   'f_pipes': '(f) pipe ends stay on J1, middle bones move', 'g_damage': '(g) damage lowers Health (server + client)',
                   'h_death': '(h) KillAll: dead on both, ragdoll moves bones, actor stays', 'i_respawn': '(i) new Burrower after SpawnInterval'}


def bw_report(path, full=False):
    if not os.path.isfile(path):
        print('FAIL: %s does not exist (was bw_pie_test.py armed?)' % path)
        return 2
    try:
        with open(path) as f:
            R = json.load(f)
    except Exception as e:
        print('WARN: %s is being written or broken (%r); try again' % (path, e))
        return 2
    print('INFO: run %s (%s), armed %s UTC, phase %s, game t %s s, fps est %s, done %s, reason %s' % (
        R.get('run_name'), R.get('script'), R.get('armed_utc'), R.get('phase'), R.get('game_t'), R.get('fps_est'), R.get('done'), R.get('reason')))
    for ln in R.get('preflight', []):
        if not ln.startswith('PASS') and not ln.startswith('INFO'):
            print('    preflight ' + ln)
    checks = R.get('checks', {})
    worst = 0
    for k in BW_REPORT_ORDER:
        c = checks.get(k)
        if not c:
            print('INFO: %s: pending' % BW_REPORT_NAMES[k])
            continue
        st = c.get('status')
        word = {'PASS': 'PASS', 'FAIL': 'FAIL', 'WARN': 'WARN', 'SKIP': 'WARN'}.get(st, 'INFO')
        worst = max(worst, {'PASS': 0, 'WARN': 1, 'SKIP': 1, 'FAIL': 2}.get(st, 0))
        print('%s: %s: %s%s' % (word, BW_REPORT_NAMES[k], '(skipped) ' if st == 'SKIP' else '', c.get('summary')))
        if full and c.get('data'):
            print('      ' + json.dumps(c['data'], default=str)[:4000])
    errs = R.get('errors', [])
    if errs:
        print('WARN: %d script errors inside the state machine (first ones below; full list in the JSON "errors")' % len(errs))
        for e in errs[:3]:
            print('      ' + e.strip().replace('\n', '\n      ')[:900])
    L = R.get('log_scan', {})
    if L:
        def cnt(k):
            return (L.get(k) or {}).get('count', 0)
        print('INFO: editor log since arming: gun hits on a Burrower %d (HitActor lines %d), LogBurrowerSpawn %d, LogBurrower %d, Ensure %d, Assertion %d, "Error:" %d, NO PLAYERSTART %d, user Play %d' % (
            cnt('hit_burrower'), cnt('hit_actor'), cnt('burrower_spawn'), cnt('burrower'), cnt('ensure'), cnt('assert'), cnt('error'), cnt('no_playerstart'), cnt('user_play')))
        for k in ('ensure', 'assert', 'burrower'):
            for ln in (L.get(k) or {}).get('lines', [])[:3]:
                print('      %s: %s' % (k, ln))
    shots = R.get('shots', [])
    if shots:
        n = sum(len(s.get('files', [])) for s in shots)
        print('INFO: %d scene captures in %d shots under %s/pie_shots/%s (X window grabs x_*.png next to them if xgrab_loop.sh ran)' % (
            n, len(shots), os.path.dirname(path), R.get('run_name')))
        if full:
            for s in shots:
                print('      %s t=%s %s' % (s.get('label'), s.get('t'), s.get('files')))
    rs = R.get('restore', {})
    if R.get('done'):
        print('INFO: restored in memory: cvar %s, engine %s, play %s; TEMP removed %s; PIE stop requested %s' % (
            rs.get('cvar'), rs.get('engine'), rs.get('play'), R.get('temp_removed'), R.get('pie_stop_requested')))
    else:
        ev = R.get('events', [])[-4:]
        print('INFO: still running; last events %s' % json.dumps(ev, default=str)[:600])
    print('%s: overall %s' % (['PASS', 'WARN', 'FAIL'][worst], 'all checks passed' if worst == 0 else 'see the lines above'))
    return worst


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    sys.exit(bw_report(args[0] if args else BW_REPORT_DEFAULT, '--full' in sys.argv))
else:
    bw_report(globals().get('BW_REPORT_PATH') or BW_REPORT_DEFAULT, bool(globals().get('BW_REPORT_FULL')))
