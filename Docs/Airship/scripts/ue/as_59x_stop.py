# as_59x_stop.py - inbox: ends an active as_59 round-2 run (its own PIE ended, the in-memory settings restored, TEMP_AS59_*
# removed after PIE, partial results written). With no active run it removes any TEMP_AS59_* actors left in the editor
# level (only when no PIE runs).
#   Docs/Airship/scripts/harness/inbox.sh 59x Docs/Airship/scripts/ue/as_59x_stop.py 30
_r = globals().get('AS59_RUN')
if _r is not None and _r.phase not in ('ending', 'finished'):
    AS59_STOP = True
    exec(open('/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_59s_status.py').read())
    AS59_STOP = False
    print('stop requested: poll as_59s_status.py until the phase is finished (PIE ends within a few seconds)')
else:
    _les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if _les.is_in_play_in_editor():
        print('no active as_59 run, but PIE is running (yours?): TEMP_AS59_* actors left alone; run this again after PIE')
    else:
        _eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        _n = 0
        for _a in _eas.get_all_level_actors():
            try:
                if _a.get_actor_label().startswith('TEMP_AS59_'):
                    _eas.destroy_actor(_a)
                    _n += 1
            except Exception:  # noqa: BLE001
                pass
        print('no active as_59 run; removed %d leftover TEMP_AS59_* actors from the editor level' % _n)
