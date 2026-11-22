# as_31_pie_status.py - inbox: status of the as_30 PIE smoke run (phase, game time, checks, last lines, errors).
# Set AS31_STOP = True before exec (or run as_32_pie_stop.py) to end an active run (restores, stops its PIE).
_r = globals().get('AS30_RUN')
if _r is None:
    print('no run')
else:
    if globals().get('AS31_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_31 (AS31_STOP)')
    print('phase %s game_t %.1f wall %.0f s done %s' % (_r.phase, _r.now, __import__('time').time() - _r.wall0, _r.R['done']))
    for k, c in sorted(_r.R['checks'].items()):
        print('%s %s: %s' % (c['status'], k, c['summary'][:400]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-700:]))
    for l in _r.R['lines'][-12:]:
        print('  ' + l[:300])
