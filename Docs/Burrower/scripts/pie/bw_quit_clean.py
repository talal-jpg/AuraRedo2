# bw_quit_clean.py - inbox script: quits the Burrower clone editor without saving, after the PIE test.
# Refuses while PIE runs, while a bw_pie_test.py run is still active, or while one of OUR assets
# (/Game/Assets/Enemies/Burrower/) has unsaved changes (save those first by explicit path; BW_FORCE_QUIT = True overrides).
# SystemLibrary.quit_editor() = CloseEditor -> RequestEngineExit: no save prompt, every dirty package is discarded
# (the StartupMap shows as dirty from the TEMP_BW_ actor: that is wanted, it must not be saved).
# After the process exits, restore the ini: bash Docs/Burrower/scripts/pie/bw_ini_playmode.sh restore
_bwq_les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
_bwq_eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
_bwq_run = globals().get('BW_RUN')
_bwq_force = bool(globals().pop('BW_FORCE_QUIT', False))
_bwq_ok = True
if _bwq_les.is_in_play_in_editor():
    print('FAIL: PIE is running: stop it first (bw_pie_cleanup.py with BW_CLEANUP_STOP_PIE = True if it is the test)')
    _bwq_ok = False
if _bwq_run is not None and not _bwq_run.done:
    print('FAIL: run %s still active (phase %s): run bw_pie_cleanup.py first' % (_bwq_run.cfg['run_name'], _bwq_run.phase))
    _bwq_ok = False
if _bwq_ok:
    _bwq_n = []
    for a in _bwq_eas.get_all_level_actors():
        try:
            if a.get_actor_label().startswith('TEMP_BW_'):
                _bwq_n.append(a.get_actor_label())
                _bwq_eas.destroy_actor(a)
        except Exception:
            pass
    print('INFO: removed TEMP_BW_ actors %s' % _bwq_n)
    _bwq_dc = [x.get_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    _bwq_dm = [x.get_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    _bwq_ours = [p for p in _bwq_dc if p.startswith('/Game/Assets/Enemies/Burrower/')]
    print('INFO: dirty content %s, dirty maps %s' % (_bwq_dc, _bwq_dm))
    if _bwq_ours and not _bwq_force:
        print('FAIL: unsaved Burrower assets %s: save them by explicit path first (or set BW_FORCE_QUIT = True to discard)' % _bwq_ours)
    else:
        if _bwq_dc:
            print('WARN: these content packages are discarded: %s' % _bwq_dc)
        unreal.SystemLibrary.quit_editor()
        print('INFO: quit requested (no save). After the process is gone: bash Docs/Burrower/scripts/pie/bw_ini_playmode.sh restore')
