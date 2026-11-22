# Editor-side command inbox for the Airship editor session (runtime only, nothing is saved).
# Every 0.3 s it execs each <project>/Saved/ClaudeInbox/*.py in one shared namespace and writes <name>.out.
# Started from the editor command line: -ExecCmds="py <this file>" (see launch.sh).
import unreal, os, io, time, traceback, contextlib
_PT_INBOX = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'ClaudeInbox')
os.makedirs(_PT_INBOX, exist_ok=True)
_PT_NS = {'unreal': unreal, '__name__': '__pt__'}
_PT_LAST = [0.0]
# pt_guard.py blocks a few editor calls that crashed UE 5.8 on this machine.
try:
    _PT_GUARD = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/harness/pt_guard.py')
    exec(compile(open(_PT_GUARD).read(), _PT_GUARD, 'exec'), _PT_NS)
except Exception as _e:
    unreal.log_warning('[PT] guard not loaded: %r' % _e)

def _pt_tick(dt):
    if time.time() - _PT_LAST[0] < 0.3:
        return
    _PT_LAST[0] = time.time()
    for name in sorted(os.listdir(_PT_INBOX)):
        if not name.endswith('.py'):
            continue
        path = os.path.join(_PT_INBOX, name)
        try:
            src = open(path).read()
            os.rename(path, path + '.taken')
        except Exception:
            continue
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exec(compile(src, path, 'exec'), _PT_NS)
        except Exception:
            buf.write(traceback.format_exc())
        with open(path[:-3] + '.out', 'w') as f:
            f.write(buf.getvalue())

_PT_HANDLE = unreal.register_slate_post_tick_callback(_pt_tick)
unreal.log('[PT] inbox ready: ' + _PT_INBOX)
