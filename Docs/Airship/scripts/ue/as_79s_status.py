# as_79s_status.py - inbox: status of the as_79 PR B lobby standalone run (SPEC_B_LOBBY 8.3) (phase, test, step, game / wall time, checks so far, script
# errors, last lines). The same summary is in Saved/Match/b79/b79_status.txt (rewritten every 2 s while the run is armed).
# Set AS79_STOP = True before exec (or run as_79x_stop.py) to end an active run (its own PIE ended, settings restored,
# TEMP actors removed after PIE, partial results written).
#   Docs/Airship/scripts/harness/inbox.sh 79s Docs/Airship/scripts/ue/as_79s_status.py 30
_r = globals().get('AS79_RUN')
if _r is None:
    print('no as_79 run in this editor session')
else:
    if globals().get('AS79_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_79x_stop.py (AS79_STOP)')
    print(_r.status_text())
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, str(c['summary'])[:500]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
