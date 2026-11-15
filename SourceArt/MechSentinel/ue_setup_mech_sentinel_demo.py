# Mech Sentinel - demo setup: gameplay effects, swarm rules, entity config, demo GameMode and demo map.
# Run inside the editor after ue_import_mech_sentinel.py (Tools > Execute Python Script...).
# Re-running is safe: existing assets are loaded and their values set again; the demo map is rebuilt in place.
# The values are the ones quoted in MyMechEntitySystemReadme.md ("Spawning sentinels in a level").

import json

import unreal

ROOT = "/Game/MechSentinel"
GAS_DIR = ROOT + "/GAS"
DATA_DIR = ROOT + "/Data"
DEMO_DIR = ROOT + "/Demo"
MAP_PATH = DEMO_DIR + "/L_MechSentinelDemo"
TEMPLATE_MAP = "/Engine/Maps/Templates/Template_Default"  # the "Basic" level template
PROJECT_GAME_MODE = "/Game/Level/BP_MyGameMode"  # the GameMode Blueprint the project's maps use (AMyGameMode)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary


def log(msg):
    unreal.log("MechSentinel demo: " + msg)


def import_struct(struct_type, text):
    value = struct_type()
    if not value.import_text(text):
        raise RuntimeError("could not import %s from %s" % (struct_type.__name__, text))
    return value


def blueprint(name, folder, parent_class):
    path = folder + "/" + name
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent_class)
    asset = asset_tools.create_asset(name, folder, unreal.Blueprint, factory)
    log("created " + path)
    return asset


def data_asset(name, folder, asset_class):
    path = folder + "/" + name
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", asset_class)
    asset = asset_tools.create_asset(name, folder, asset_class, factory)
    log("created " + path)
    return asset


def cdo(bp):
    return unreal.get_default_object(bp.generated_class())


def save(asset):
    EAL.save_loaded_asset(asset, False)


# --------------------------------------------------------------------------------------------------------------------
# Gameplay effects
# --------------------------------------------------------------------------------------------------------------------

def make_damage_effect():
    """GE_SentinelDamage: Instant, Executions = ExecCalc_SentinelDamage (damage taken by sentinels)."""
    bp = blueprint("GE_SentinelDamage", GAS_DIR, unreal.GameplayEffect)
    ge = cdo(bp)
    ge.set_editor_property("duration_policy", unreal.GameplayEffectDurationType.INSTANT)
    # CalculationClass is EditDefaultsOnly, so the struct is built from text instead of set_editor_property.
    execution = import_struct(unreal.GameplayEffectExecutionDefinition,
                              "(CalculationClass=\"/Script/CoreUObject.Class'/Script/Aura.ExecCalc_SentinelDamage'\")")
    ge.set_editor_property("executions", [execution])
    save(bp)
    return bp


def make_attack_effect():
    """GE_SentinelAttack: Instant, MyAttributeSet.IncomingDamage Add (Base), Set by Caller tag SetDamageByCaller.
    The sentinel attack sets that magnitude to its AttackDamage; MyAttributeSet turns IncomingDamage into Health loss."""
    bp = blueprint("GE_SentinelAttack", GAS_DIR, unreal.GameplayEffect)
    ge = cdo(bp)
    ge.set_editor_property("duration_policy", unreal.GameplayEffectDurationType.INSTANT)
    # Built from text: FGameplayAttribute (a field path) and the EditDefaultsOnly magnitude fields can't be set from Python.
    modifier = import_struct(
        unreal.GameplayModifierInfo,
        "(Attribute=(AttributeName=\"IncomingDamage\",Attribute=/Script/Aura.MyAttributeSet:IncomingDamage,"
        "AttributeOwner=\"/Script/CoreUObject.Class'/Script/Aura.MyAttributeSet'\"),ModifierOp=AddBase,"
        "ModifierMagnitude=(MagnitudeCalculationType=SetByCaller,SetByCallerMagnitude=(DataTag=(TagName=\"SetDamageByCaller\"))))")
    ge.set_editor_property("modifiers", [modifier])
    save(bp)
    return bp


def make_stun_effect():
    """GE_SentinelStun: Has Duration 2 s, grants State.Sentinel.Stunned to the target."""
    bp = blueprint("GE_SentinelStun", GAS_DIR, unreal.GameplayEffect)
    ge = cdo(bp)
    ge.set_editor_property("duration_policy", unreal.GameplayEffectDurationType.HAS_DURATION)
    ge.set_editor_property("duration_magnitude", import_struct(
        unreal.GameplayEffectModifierMagnitude,
        "(MagnitudeCalculationType=ScalableFloat,ScalableFloatMagnitude=(Value=2.000000))"))
    # "Grant Tags to Target Actor" component. Python does not export the GE component classes, so the class is
    # loaded by path and its property is set through the toolset JSON setter.
    component = None
    for existing in ge.get_editor_property("ge_components") or []:
        if existing and existing.get_class().get_name() == "TargetTagsGameplayEffectComponent":
            component = existing
    if component is None:
        component_class = unreal.load_class(None, "/Script/GameplayAbilities.TargetTagsGameplayEffectComponent")
        component = unreal.new_object(component_class, ge, "TargetTagsGameplayEffectComponent_0")
    set_json(component, {"InheritableGrantedTagsContainer": '(Added=(GameplayTags=((TagName="State.Sentinel.Stunned"))))'})
    ge.set_editor_property("ge_components", [component])
    save(bp)
    return bp


# --------------------------------------------------------------------------------------------------------------------
# Swarm rules and entity config
# --------------------------------------------------------------------------------------------------------------------

def make_rules(damage_effect, attack_effect_class):
    rules = data_asset("DA_MechSentinelSwarmRules", DATA_DIR, unreal.MechSentinelSwarmRules)
    rules.set_editor_property("default_sentinel_damage_effect", damage_effect.generated_class())
    rules.set_editor_property("sentinel_attack_effect", attack_effect_class)
    rules.set_editor_property("max_attackers_per_player", 10)
    save(rules)
    return rules


def new_trait(config_asset, trait_class):
    return unreal.new_object(trait_class, config_asset)


def make_entity_config():
    config_asset = data_asset("DA_MechSentinelConfig", DATA_DIR, unreal.MassEntityConfigAsset)
    meshes = ROOT + "/Meshes/"

    sentinel = new_trait(config_asset, unreal.MechSentinelTrait)
    sentinel.set_editor_property("swarm_group", "Sentinels")
    sentinel.set_editor_property("attributes", import_struct(
        unreal.MechSentinelAttributeDefaults,
        "(MaxHealth=120.000000,Armor=4.000000,AttackDamage=3.000000,AttackSpeed=0.600000)"))
    sentinel.set_editor_property("movement_speed", 900.0)

    movement = new_trait(config_asset, unreal.MassMovementTrait_Copy)
    avoidance = new_trait(config_asset, unreal.MassObstacleAvoidanceTrait_Copy)
    orientation = new_trait(config_asset, unreal.MassSmoothOrientationTrait_Copy)

    visualization = new_trait(config_asset, unreal.MassVisualizationTrait_Copy)
    desc = visualization.get_editor_property("static_mesh_instance_desc")
    desc.set_editor_property("mesh", unreal.load_asset(meshes + "SM_MechSentinel_Head"))
    desc.set_editor_property("low_lod_mesh", unreal.load_asset(meshes + "SM_MechSentinel_Far"))
    desc.set_editor_property("num_custom_data_floats", 4)
    desc.set_editor_property("cast_shadows", True)
    visualization.set_editor_property("static_mesh_instance_desc", desc)
    set_json(visualization, {"LODParams": {"HighDistance": 4000.0, "MediumDistance": 9000.0, "LowDistance": 25000.0}})

    tentacles = new_trait(config_asset, unreal.MechSentinelTentacleTrait)
    tentacle_desc = tentacles.get_editor_property("tentacles")
    tentacle_desc.set_editor_property("niagara_system", unreal.load_asset(ROOT + "/FX/NS_MechSentinelTentacles"))
    tentacles.set_editor_property("tentacles", tentacle_desc)

    replication = new_trait(config_asset, unreal.MassReplicationTrait)
    # Fixed arrays are per EMassLOD (High, Medium, Low, Off); the Off entries of the max counts stay at the engine default 0.
    set_json(replication, {"Params": {
        "LODDistance": [0.0, 2500.0, 7000.0, 20000.0],
        "LODMaxCountPerViewer": [150, 300, 1000, 0],
        "UpdateInterval": [0.1, 0.2, 0.4, 0.5],
        "BubbleInfoClass": "/Script/Aura.MechSentinelClientBubbleInfo",
        "ReplicatorClass": "/Script/Aura.MechSentinelReplicator",
    }})

    config = config_asset.get_editor_property("config")
    config.set_editor_property("traits", [sentinel, movement, avoidance, orientation, visualization, tentacles, replication])
    config_asset.set_editor_property("config", config)
    save(config_asset)
    return config_asset


def set_json(obj, values):
    """Sets properties from JSON through the Toolsets plugin (AllToolsets, enabled in Aura.uproject).
    Used for the structs and fixed-size arrays Python does not expose (LOD and replication parameters)."""
    if not unreal.ToolsetLibrary.set_object_properties(obj, json.dumps(values)):
        raise RuntimeError("could not set %s on %s" % (list(values), obj.get_name()))


# --------------------------------------------------------------------------------------------------------------------
# Demo GameMode and map
# --------------------------------------------------------------------------------------------------------------------

def make_game_mode(rules):
    parent = unreal.load_asset(PROJECT_GAME_MODE)
    bp = blueprint("BP_MechSentinelDemoGameMode", DEMO_DIR, parent.generated_class())
    cdo(bp).set_editor_property("sentinel_swarm_rules", rules)
    save(bp)
    return bp


def wave(count, delay, duration, time_limit, health, armor, damage, attack_speed, move_speed):
    w = unreal.MechSentinelWave()
    w.set_editor_property("count", count)
    w.set_editor_property("delay_before", delay)
    w.set_editor_property("spawn_duration", duration)
    w.set_editor_property("time_limit", time_limit)
    w.set_editor_property("health_multiplier", health)
    w.set_editor_property("armor_multiplier", armor)
    w.set_editor_property("damage_multiplier", damage)
    w.set_editor_property("attack_speed_multiplier", attack_speed)
    w.set_editor_property("move_speed_multiplier", move_speed)
    return w


def make_map(game_mode, entity_config):
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if EAL.does_asset_exist(MAP_PATH):
        level_editor.load_level(MAP_PATH)
    else:
        level_editor.new_level_from_template(MAP_PATH, TEMPLATE_MAP)
        log("created " + MAP_PATH + " from " + TEMPLATE_MAP)

    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    all_actors = actors.get_all_level_actors()

    # Floor: scale the template floor to about 200 x 200 m.
    floor = next((a for a in all_actors if isinstance(a, unreal.StaticMeshActor) and "floor" in a.get_actor_label().lower()), None)
    if floor:
        mesh = floor.static_mesh_component.static_mesh
        extent = mesh.get_bounding_box().max - mesh.get_bounding_box().min
        floor.set_actor_scale3d(unreal.Vector(20000.0 / extent.x, 20000.0 / extent.y, 1.0))
        floor.set_actor_location(unreal.Vector(0, 0, floor.get_actor_location().z), False, False)

    # Navigation (Aura's click-to-move needs a nav mesh).
    for a in all_actors:
        if isinstance(a, unreal.NavMeshBoundsVolume):
            actors.destroy_actor(a)
    # Spawning the class goes through the editor's box volume factory (a 200 cm cube brush); scale it over the floor.
    nav = actors.spawn_actor_from_class(unreal.NavMeshBoundsVolume, unreal.Vector(0, 0, 0))
    nav.set_actor_label("NavMeshBoundsVolume")
    nav_origin, nav_extent = nav.get_actor_bounds(False)
    nav.set_actor_scale3d(unreal.Vector(10200.0 / max(nav_extent.x, 1.0), 10200.0 / max(nav_extent.y, 1.0), 2000.0 / max(nav_extent.z, 1.0)))

    # PlayerStart.
    starts = [a for a in all_actors if isinstance(a, unreal.PlayerStart)]
    start = starts[0] if starts else actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, -2500, 100))
    start.set_actor_location(unreal.Vector(0, -2500, 100), False, False)
    start.set_actor_rotation(unreal.Rotator(0, 0, 90), False)  # face +Y, towards the spawner

    # GameMode override.
    world.get_world_settings().set_editor_property("default_game_mode", game_mode.generated_class())

    # The wave spawner.
    for a in all_actors:
        if isinstance(a, unreal.MechSentinelWaveSpawner):
            actors.destroy_actor(a)
    spawner = actors.spawn_actor_from_class(unreal.MechSentinelWaveSpawner, unreal.Vector(0, 0, 800))
    spawner.set_actor_label("MechSentinelWaveSpawner")
    spawner.set_editor_property("entity_config", entity_config)
    spawner.set_editor_property("advance_mode", unreal.MechSentinelWaveAdvance.CLEARED_OR_TIMER)
    spawner.set_editor_property("auto_start", True)
    spawner.set_editor_property("repeat_last_wave", True)
    spawner.set_editor_property("extra_count_per_repeat", 25)
    spawner.set_editor_property("stat_scale_per_repeat", 1.1)
    spawner.set_editor_property("count_multiplier", 1.0)
    spawner.set_editor_property("max_alive", 400)
    spawner.set_editor_property("spawn_batch_size", 25)
    spawner.set_editor_property("spawn_extent", unreal.Vector(1500, 1500, 400))
    spawner.set_editor_property("spawner_is_fallback_target", True)
    spawner.set_editor_property("waves", [
        wave(12, 3, 4, 45, 1.0, 1.0, 1.0, 1.0, 1.0),
        wave(30, 5, 6, 50, 1.25, 1.25, 1.0, 1.0, 1.0),
        wave(60, 6, 8, 60, 1.5, 1.5, 1.2, 1.1, 1.05),
        wave(120, 8, 10, 75, 2.0, 2.0, 1.5, 1.2, 1.1),
    ])

    level_editor.save_current_level()
    return spawner


def main():
    damage = make_damage_effect()
    attack = make_attack_effect()
    make_stun_effect()
    rules = make_rules(damage, attack.generated_class())
    config = make_entity_config()
    game_mode = make_game_mode(rules)
    make_map(game_mode, config)
    log("done: open %s and press Play" % MAP_PATH)


# Tools > Execute Python Script runs this as __main__; import it (or exec with another __name__) to call single steps.
if __name__ == "__main__":
    main()
