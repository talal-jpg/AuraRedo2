# as_75s_status.py - inbox: status of the as_75 PR B listen-server run (phase, test, step, game / wall time, checks so far, script
# errors, last lines). The same summary is in Saved/Match/b75*/b75_status.txt (rewritten every 2 s while the run is armed).
# Set AS75_STOP = True before exec (or run as_75x_stop.py) to end an active run (its own PIE ended, settings restored,
# TEMP actors removed after PIE, partial results written).
#   Docs/Airship/scripts/harness/inbox.sh 75s Docs/Airship/scripts/ue/as_75s_status.py 30
_r = globals().get('AS75_RUN')
if _r is None:
    print('no as_75 run in this editor session')
else:
    if globals().get('AS75_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_75x_stop.py (AS75_STOP)')
    print(_r.status_text())
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, str(c['summary'])[:500]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
