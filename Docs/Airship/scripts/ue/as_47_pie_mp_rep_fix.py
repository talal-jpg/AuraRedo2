# as_47_pie_mp_rep_fix.py - multiplayer PIE run after the C++ every-frame replication fix (AAirshipPawn::bReplicateEveryFrame,
# 2026-11-22): as_46 in 'property' mode, results Saved/Airship/mp/mp3_result.json / mp3_report.txt.
#   v0a/v0b  bReplicateEveryFrame False (the engine's own schedule, as before the fix), no lag / Net PktLag
#   v1a/v1b  bReplicateEveryFrame True (the new default), no lag / Net PktLag
#   v2a      Aura.Airship.RepMode 1 requested + every frame: the new guard keeps Default (no Physics Prediction) and warns
# Run (L_AirshipTest open, no PIE): inbox.sh 47 Docs/Airship/scripts/ue/as_47_pie_mp_rep_fix.py 60
# every hard snap of the physics replication is logged (counted per phase in the report's log segments)
unreal.SystemLibrary.execute_console_command(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), 'p.LogPhysicsReplicationHardSnaps 1')
AS46_FNU_MODE = 'property'
AS46_TAG = 'mp3'
AS46_VARIANTS = [('v0a', 0, False, False), ('v0b', 0, False, True), ('v1a', 0, True, False), ('v1b', 0, True, True), ('v2a', 1, True, False)]
exec(compile(open('/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_46_pie_mp_rep.py').read(),
             '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_46_pie_mp_rep.py', 'exec'), globals())
