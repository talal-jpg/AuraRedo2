# as_50x_stop.py - inbox: ends an active as_50 run (its own PIE ended, settings restored, TEMP_AS50_* removed after PIE, partial
# results written). With no active run it removes any TEMP_AS50_* actors left in the editor level (only when no PIE runs).
#   Docs/Airship/scripts/harness/inbox.sh 50x Docs/Airship/scripts/ue/as_50x_stop.py 30
_r = globals().get('AS50_RUN')
if _r is not None and _r.phase not in ('ending', 'finished'):
    AS50_STOP = True
    exec(open('/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_50s_status.py').read())
    AS50_STOP = False
    print('stop requested: poll as_50s_status.py until the phase is finished (PIE ends within a few seconds)')
else:
    _les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if _les.is_in_play_in_editor():
        print('no active as_50 run, but PIE is running (yours?): TEMP_AS50_* actors left alone; run this again after PIE')
    else:
        _eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        _n = 0
        for _a in _eas.get_all_level_actors():
            try:
                if _a.get_actor_label().startswith('TEMP_AS50_'):
                    _eas.destroy_actor(_a)
                    _n += 1
            except Exception:  # noqa: BLE001
                pass
        print('no active as_50 run; removed %d leftover TEMP_AS50_* actors from the editor level' % _n)
