# as_62s_status.py - inbox: status of the as_62 swarm PIE run (phase, game / wall time, alive sentinels, checks so far,
# script errors, last lines). The same summary is in Saved/Airship/round2_swarm/sw_status.txt (rewritten every 2 s while
# the run is armed). Set AS62_STOP = True before exec (or run as_62x_stop.py) to end an active run (its own PIE ended,
# settings restored, TEMP_AS62_* removed after PIE, partial results written).
#   Docs/Airship/scripts/harness/inbox.sh 62s Docs/Airship/scripts/ue/as_62s_status.py 30
_r = globals().get('AS62_RUN')
if _r is None:
    print('no as_62 run in this editor session')
else:
    if globals().get('AS62_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_62x_stop.py (AS62_STOP)')
    print(_r.status_text())
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, c['summary'][:500]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
