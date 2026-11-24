# as_59s_status.py - inbox: status of the as_59 round-2 PIE run (phase, game / wall time, checks so far, script errors,
# last lines). The same summary is in Saved/Airship/round2/r2_status.txt (rewritten every 2 s while the run is armed).
# Set AS59_STOP = True before exec (or run as_59x_stop.py) to end an active run (its own PIE ended, settings restored,
# TEMP_AS59_* removed after PIE, partial results written).
#   Docs/Airship/scripts/harness/inbox.sh 59s Docs/Airship/scripts/ue/as_59s_status.py 30
_r = globals().get('AS59_RUN')
if _r is None:
    print('no as_59 run in this editor session')
else:
    if globals().get('AS59_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_59x_stop.py (AS59_STOP)')
    print(_r.status_text())
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, c['summary'][:500]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
