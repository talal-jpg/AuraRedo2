# as_45s_mp_status.py - inbox: status of the as_45 multiplayer PIE run (phase, game time, checks, script errors, last lines).
# Set AS45_STOP = True before exec (or run as_45x_mp_stop.py) to end an active run (restores, stops its own PIE).
_r = globals().get('AS45_RUN')
if _r is None:
    print('no run')
else:
    if globals().get('AS45_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_45s (AS45_STOP)')
    print('phase %s game_t %.1f wall %.0f s frames %d done %s' % (_r.phase, _r.now, __import__('time').time() - _r.wall0, _r.frames, _r.R['done']))
    for k, c in _r.R['checks'].items():
        print('%s %s: %s' % (c['status'], k, c['summary'][:600]))
    print('errors %s' % dict((k, v['n']) for k, v in _r.R['errors'].items()))
    for k, v in _r.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-800:]))
    for l in _r.R['lines'][-14:]:
        print('  ' + l[:400])
