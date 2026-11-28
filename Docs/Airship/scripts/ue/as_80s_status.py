# as_80s_status.py - inbox: status of the as_80 PR B lobby listen run (SPEC_B_LOBBY 8.4) (phase, test, step, game / wall time, checks so far, script
# errors, last lines). The same summary is in Saved/Match/b80/b80_status.txt (rewritten every 2 s while the run is armed).
# Set AS80_STOP = True before exec (or run as_80x_stop.py) to end an active run (its own PIE ended, settings restored,
# TEMP actors removed after PIE, partial results written).
#   Docs/Airship/scripts/harness/inbox.sh 80s Docs/Airship/scripts/ue/as_80s_status.py 30
_r = globals().get('AS80_RUN')
if _r is None:
    print('no as_80 run in this editor session')
else:
    if globals().get('AS80_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_80x_stop.py (AS80_STOP)')
    print(_r.status_text())
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, str(c['summary'])[:500]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
