# as_50s_status.py - inbox: status of the as_50 control-scheme PIE run (phase, scheme, run, game / wall time, ETA, errors,
# last lines). The same text is in Saved/Airship/controls/status.txt (rewritten every 2 s while the run is armed).
# Set AS50_STOP = True before exec (or run as_50x_stop.py) to end an active run: it ends its own PIE, restores the in-memory
# settings, removes the TEMP_AS50_* actors and writes the partial results.
#   Docs/Airship/scripts/harness/inbox.sh 50s Docs/Airship/scripts/ue/as_50s_status.py 30
_r = globals().get('AS50_RUN')
if _r is None:
    print('no as_50 run in this editor session')
else:
    if globals().get('AS50_STOP') and _r.phase not in ('ending', 'finished'):
        _r.finish('stopped by as_50x_stop.py')
    print(_r.status_text())
    if _r.phase == 'finished':
        print('finished: %s; results in Saved/Airship/controls (compare.md, <scheme>/metrics.json)%s' % (
            _r.R.get('reason'), ('; post step: ' + _r.post_cmd) if _r.post_cmd else ''))
