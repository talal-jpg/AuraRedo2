# as_22_test_map.py - test map /Game/Assets/MyShip/Drivable/Maps/L_AirshipTest for the drivable airship (session 3).
# Run: Docs/Airship/scripts/harness/inbox.sh 22 Docs/Airship/scripts/ue/as_22_test_map.py 600
# New level from /Engine/Maps/Templates/Template_Default (its sky, sun, fog, clouds kept; its floor and player start
# removed), GameMode override = /Game/Level/BP_MyGameMode (the player spawns as BP_MyCharMech with GAS), then (cm):
#   * start platform: cube 100 x 100 x 2 m, top at z 0, a PlayerStart on it at (-2500, -2500)
#   * BP_AirshipPawn at (0, 2500, 1600), bow +X: its nozzle exits (z -594 in the ship) hang 10 m above the platform
#   * cannon target walls 120 m to port (y -9500) and to starboard (y +14500) of the ship, 60 x 4 x 30 m
#   * 8 floating obstacles (cubes / cylinders, static, collision on) spread over ~1.5 km at heights -10..+60 m, kept off
#     the straight flight line (y 0..+5000 to x 600 m) and the right turn after it
#   * ground block 4 x 4 km, 20 m thick, top at z -199.5 m, so a dying ship has something to crash on (session 3: the
#     first 1 m thick plane let a fast searchlight tunnel through after the crash bounce; as_22b_ground.py thickened it)
# Saves only this new map (and refuses to touch a map it did not create). Writes Saved/Airship/as_22_test_map.json.
import json, os, traceback  # unreal = inbox namespace

MAP = '/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest'
TEMPLATE = '/Engine/Maps/Templates/Template_Default'
GAME_MODE = '/Game/Level/BP_MyGameMode.BP_MyGameMode_C'
SHIP = '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'
CUBE = '/Engine/BasicShapes/Cube'
CYL = '/Engine/BasicShapes/Cylinder'
R = {'lines': [], 'actors': []}
CNT = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def o(tag, msg):
    CNT[tag] += 1
    R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


# (label, mesh, location, scale, yaw)
SOLIDS = [
    ('AS_StartPlatform', CUBE, (0, 0, -100), (100, 100, 2), 0),
    ('AS_CannonWall_Port', CUBE, (0, -9500, 1600), (60, 4, 30), 0),
    ('AS_CannonWall_Stbd', CUBE, (0, 14500, 1600), (60, 4, 30), 0),
    ('AS_Obstacle_1', CUBE, (35000, -12000, 2500), (40, 40, 4), 20),
    ('AS_Obstacle_2', CYL, (55000, -20000, 1000), (30, 30, 30), 0),
    ('AS_Obstacle_3', CUBE, (80000, -8000, 4500), (60, 25, 8), -15),
    ('AS_Obstacle_4', CYL, (100000, -30000, 3000), (25, 25, 50), 0),
    ('AS_Obstacle_5', CUBE, (120000, -15000, -1000), (50, 50, 6), 35),
    ('AS_Obstacle_6', CUBE, (140000, 10000, 6000), (40, 60, 5), 0),
    ('AS_Obstacle_7', CYL, (60000, 40000, 5500), (35, 35, 10), 0),
    ('AS_Obstacle_8', CUBE, (150000, 45000, 2000), (30, 30, 40), 10),
    ('AS_Ground', CUBE, (60000, 20000, -20950), (4000, 4000, 20), 0),     # 20 m thick (1 m let debris tunnel), top -19950
]


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE running: nothing changed')
        return
    if unreal.EditorAssetLibrary.does_asset_exist(MAP):
        o('FAIL', '%s already exists: not overwritten (delete it by hand or edit it in place)' % MAP)
        return
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        o('FAIL', 'the open level has unsaved changes %s: not switching levels' % dirty)
        return
    ok = les.new_level_from_template(MAP, TEMPLATE)
    o('PASS' if ok else 'FAIL', 'new level %s from %s' % (MAP, TEMPLATE))
    if not ok:
        return
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    o('INFO', 'editor world now %s' % world.get_path_name())
    if not world.get_path_name().startswith(MAP + '.'):
        o('FAIL', 'the editor world is not the new map: stopping')
        return
    # template actors: keep the sky, drop its floor and player start
    for a in eas.get_all_level_actors():
        lab, cls = a.get_actor_label(), a.get_class().get_name()
        R['actors'].append(('template', lab, cls))
        if cls == 'PlayerStart' or (cls == 'StaticMeshActor' and 'floor' in lab.lower()):
            eas.destroy_actor(a)
            o('INFO', 'removed template %s (%s)' % (lab, cls))
        else:
            o('INFO', 'kept template %s (%s)' % (lab, cls))
    # GameMode override
    ws = world.get_world_settings()
    gm = unreal.load_class(None, GAME_MODE)
    ws.set_editor_property('default_game_mode', gm)
    o('PASS' if ws.get_editor_property('default_game_mode') == gm else 'FAIL', 'GameMode override = %s' % GAME_MODE)
    # solids
    meshes = {CUBE: unreal.EditorAssetLibrary.load_asset(CUBE), CYL: unreal.EditorAssetLibrary.load_asset(CYL)}
    for lab, mp, loc, sc, yaw in SOLIDS:
        a = eas.spawn_actor_from_object(meshes[mp], unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)))
        a.set_actor_label(lab)
        a.set_actor_scale3d(unreal.Vector(*sc))
        smc = a.static_mesh_component
        smc.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
        smc.set_collision_profile_name('BlockAll')
        R['actors'].append((lab, mp, loc, sc, yaw))
    o('PASS', 'placed %d solids (start platform, 2 cannon walls, 8 obstacles, ground)' % len(SOLIDS))
    ps = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(-2500, -2500, 120), unreal.Rotator(0, 0, 0))
    ps.set_actor_label('AS_PlayerStart')
    ship_cls = unreal.load_class(None, SHIP)
    ship = eas.spawn_actor_from_class(ship_cls, unreal.Vector(0, 2500, 1600), unreal.Rotator(0, 0, 0))
    o('PASS' if ship else 'FAIL', 'placed BP_AirshipPawn %s at (0, 2500, 1600)' % (ship.get_name() if ship else None))
    if ship:
        ship.set_actor_label('AS_Airship')
    ok = les.save_current_level()
    o('PASS' if ok else 'FAIL', 'saved %s' % MAP)
    o('INFO', 'dirty map packages after save: %s' % [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()])


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', traceback.format_exc())
R['counts'] = CNT
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_22_test_map.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))
