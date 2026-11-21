# bw_pie_cleanup.py - inbox script: ends / undoes a bw_pie_test.py run in this editor. Safe to run any time, twice.
#  * a run still active: finished now (restores everything, stops PIE only if it is the test's own session)
#  * no live run but Saved/Burrower/pie_restore.json left behind (the run died): restores from that file
#  * PIE not running: removes the TEMP_BW_ actors from the editor level (never saves anything)
# Set BW_CLEANUP_STOP_PIE = True before exec to also stop a PIE session the run did not stop (only if it is yours).
import json, os

BW_CLEAN_OUT = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower'
_bwc_les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
_bwc_eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
_bwc_run = globals().get('BW_RUN')
_bwc_stop = bool(globals().pop('BW_CLEANUP_STOP_PIE', False))

if _bwc_run is not None and not _bwc_run.done:
    print('WARN: run %s still active (phase %s): finishing it now' % (_bwc_run.cfg['run_name'], _bwc_run.phase))
    try:
        _bwc_run.finish('cleanup requested (bw_pie_cleanup.py)')
        print('INFO: restored %s' % json.dumps(_bwc_run.R.get('restore'), default=str)[:800])
    except Exception as e:
        print('FAIL: finishing the run raised %r' % e)
else:
    _bwc_rp = os.path.join(BW_CLEAN_OUT, 'pie_restore.json')
    if os.path.isfile(_bwc_rp):
        print('WARN: %s exists: a run did not restore its in-memory changes; restoring from the file' % _bwc_rp)
        try:
            with open(_bwc_rp) as f:
                _bwc_o = json.load(f)
            _NM = unreal.PropertyAccessChangeNotifyMode.NEVER
            _cdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
            for k, v in (_bwc_o.get('settings') or {}).items():
                if isinstance(v, str) and v.startswith('ERROR'):
                    continue
                try:
                    if k == 'BurrowerClass':
                        _cdo.set_editor_property(k, unreal.load_class(None, v) if v else None, _NM)
                    else:
                        _cdo.set_editor_property(k, v, _NM)
                except Exception as e:
                    print('WARN: settings %s not restored: %r' % (k, e))
            eng = _bwc_o.get('engine')
            if eng:
                unreal.ToolsetLibrary.set_object_properties(unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0'), json.dumps(
                    {'bUseFixedFrameRate': bool(eng.get('bUseFixedFrameRate', False)), 'FixedFrameRate': float(eng.get('FixedFrameRate', 30.0))}))
            pl = _bwc_o.get('play')
            if pl:
                unreal.ToolsetLibrary.set_object_properties(unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings')), json.dumps(
                    {'PlayNetMode': str(pl.get('PlayNetMode')), 'PlayNumberOfClients': int(pl.get('PlayNumberOfClients', 1)), 'RunUnderOneProcess': bool(pl.get('RunUnderOneProcess', True))}))
            unreal.SystemLibrary.execute_console_command(None, 'Aura.Burrower.DebugRotorBox %d' % int(_bwc_o.get('cvar_debug_rotor_box', 0) or 0))
            os.replace(_bwc_rp, _bwc_rp + '.restored')
            print('PASS: restored settings, fixed frame rate, play settings and CVar from the file')
        except Exception as e:
            print('FAIL: restore from %s raised %r (restart the editor: all of it is in memory only)' % (_bwc_rp, e))
    else:
        print('INFO: nothing to restore (no active run, no pie_restore.json)')

if _bwc_les.is_in_play_in_editor():
    if _bwc_run is not None and _bwc_run.R.get('pie_stop_requested'):
        print('INFO: the run asked its own PIE session to end; it removes the TEMP_BW_ actor itself once PIE is gone (check with this script again)')
    elif _bwc_stop:
        _bwc_les.editor_request_end_play()
        print('WARN: PIE stop requested (BW_CLEANUP_STOP_PIE); run this script again after PIE ended to remove the TEMP_BW_ actor')
    else:
        print('WARN: PIE is running (the test stops only its own session; the user may be playing): TEMP_BW_ actors are left; run again after PIE ends, or set BW_CLEANUP_STOP_PIE = True')
else:
    _bwc_n = []
    for a in _bwc_eas.get_all_level_actors():
        try:
            if a.get_actor_label().startswith('TEMP_BW_'):
                _bwc_n.append(a.get_actor_label())
                _bwc_eas.destroy_actor(a)
        except Exception:
            pass
    print('INFO: removed TEMP_BW_ actors %s' % _bwc_n)
    if _bwc_run is not None and _bwc_run.done and not _bwc_run.ended:
        try:
            _bwc_run.post_end()
        except Exception:
            pass
    _bwc_other = [a.get_actor_label() for a in _bwc_eas.get_all_level_actors() if 'TEMP_' in a.get_actor_label()]
    if _bwc_other:
        print('WARN: other TEMP_ actors in the level (not ours, left alone): %s' % _bwc_other)

try:
    print('INFO: dirty content %s, dirty maps %s (never save the maps; quitting with bw_quit_clean.py discards them)' % (
        [x.get_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
        [x.get_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]))
except Exception as e:
    print('WARN: dirty package list: %r' % e)
