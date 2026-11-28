# as_76x_stop.py - inbox: ends an active as_76 PR B run (its own PIE ended, the in-memory settings restored, TEMP_AS76_*
# removed after PIE, partial results written). With no active run it removes any TEMP_AS76_* actors left in the editor
# level (only when no PIE runs).
#   Docs/Airship/scripts/harness/inbox.sh 76x Docs/Airship/scripts/ue/as_76x_stop.py 30
import os
_r = globals().get('AS76_RUN')
if _r is not None and _r.phase not in ('ending', 'finished'):
    AS76_STOP = True
    _p = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_76s_status.py')
    exec(open(_p).read())
    AS76_STOP = False
    print('stop requested: poll as_76s_status.py until the phase is finished (PIE ends within a few seconds)')
else:
    _les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if _les.is_in_play_in_editor():
        print('no active as_76 run, but PIE is running (yours?): TEMP_AS76_* actors left alone; run this again after PIE')
    else:
        _eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        _n = 0
        for _a in _eas.get_all_level_actors():
            try:
                if _a.get_actor_label().startswith('TEMP_AS76_'):
                    _eas.destroy_actor(_a)
                    _n += 1
            except Exception:  # noqa: BLE001
                pass
        print('no active as_76 run; removed %d leftover TEMP_AS76_* actors from the editor level' % _n)
