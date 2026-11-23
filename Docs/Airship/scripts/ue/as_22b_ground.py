# as_22b_ground.py - L_AirshipTest fix: AS_Ground was 1 m thick (scale z 1) and a fast break-off part (searchlight, ~70 m/s
# after the crash bounce) tunnelled through it in smoke run 3. Makes it 20 m thick with the top kept at z -19950 and saves
# the map (our own). Run with the map open, no PIE: inbox.sh 22b as_22b_ground.py 120
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'L_AirshipTest' in w.get_path_name() and not les.is_in_play_in_editor(), 'open L_AirshipTest, no PIE'
temps = [a.get_actor_label() for a in eas.get_all_level_actors() if 'TEMP' in a.get_actor_label()]
assert not temps, 'TEMP actors in the level: %s' % temps
g = [a for a in eas.get_all_level_actors() if a.get_actor_label() == 'AS_Ground'][0]
g.set_actor_scale3d(unreal.Vector(4000, 4000, 20))
g.set_actor_location(unreal.Vector(60000, 20000, -20950), False, False)
o, e = g.get_actor_bounds(False)
print('AS_Ground bounds z %.0f .. %.0f' % (o.z - e.z, o.z + e.z))
print('saved', les.save_current_level())
print('dirty maps after', [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()])
