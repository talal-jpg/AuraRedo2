# as_60s_status.py - inbox: status of the as_60 round-2 listen-server PIE run (phase, game / wall time, checks so far,
# script errors, last lines). The same summary is in Saved/Airship/round2_mp/r2mp_status.txt (rewritten every 2 s while
# the run is armed). Set AS60_STOP = True before exec (or run as_60x_stop.py) to end an active run (its own PIE ended,
# settings and lag restored, TEMP_AS60_* removed after PIE, partial results written).
#   Docs/Airship/scripts/harness/inbox.sh 60s Docs/Airship/scripts/ue/as_60s_status.py 60
_r = globals().get('AS60_RUN')
if _r is None:
    print('no as_60 run in this editor session')
else:
    if globals().get('AS60_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_60x_stop.py (AS60_STOP)')
    print(_r.status_text())
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, c['summary'][:500]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
