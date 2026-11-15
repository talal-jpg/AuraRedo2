# Mech Sentinel - Unreal Editor import helper.
# Run inside the editor: Tools > Execute Python Script... (Python Editor Script Plugin enabled), or
#   UnrealEditor-Cmd.exe Aura.uproject -run=pythonscript -script="<repo>/SourceArt/MechSentinel/ue_import_mech_sentinel.py"
#
# 1. Imports the four FBX files from Export/ into /Game/MechSentinel/Meshes (sockets SOCKET_Tentacle_XX become
#    static mesh sockets Tentacle_XX on SM_MechSentinel_Head).
# 2. Creates /Game/MechSentinel/Materials/M_MechSentinelTentacle, the ribbon tube material used by the Niagara
#    tentacle system (sleeve bands along the ribbon, glow from the particle color), also usable by the claw meshes.
# 3. Creates M_MechSentinelBody (dark gunmetal, darker when damaged, white hit flash) and M_MechSentinelEyes (red
#    emissive: brighter when attacking, flickering when stunned, off when dead). Both read the per-instance custom data
#    written by UMechSentinelVisualDataProcessor (README section 12) and are assigned to the mesh slots.
# Re-running is safe: existing materials are left as they are, only the mesh slot assignment is redone.
# The Niagara system itself is built with the recipe in MyMechEntitySystemReadme.md ("Tentacles").

import os

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "Export")
MESH_DIR = "/Game/MechSentinel/Meshes"
MATERIAL_DIR = "/Game/MechSentinel/Materials"
ASSETS = ["SM_MechSentinel_Head", "SM_MechSentinel_Far", "SM_MechSentinel_Tentacle", "SM_MechSentinel_TentacleTip"]

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary


def import_meshes():
    tasks = []
    for name in ASSETS:
        task = unreal.AssetImportTask()
        task.filename = os.path.join(EXPORT_DIR, name + ".fbx")
        task.destination_path = MESH_DIR
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = True

        options = unreal.FbxImportUI()
        options.import_mesh = True
        options.import_as_skeletal = False
        options.import_materials = False
        options.import_textures = False
        options.import_animations = False
        options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
        data = options.static_mesh_import_data
        data.combine_meshes = True
        data.auto_generate_collision = False
        data.generate_lightmap_u_vs = False
        data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        task.options = options
        tasks.append(task)

    asset_tools.import_asset_tasks(tasks)
    for task in tasks:
        unreal.log("MechSentinel import: %s -> %s" % (os.path.basename(task.filename), list(task.imported_object_paths)))

    head = unreal.load_asset(MESH_DIR + "/SM_MechSentinel_Head")
    if head:
        # UStaticMesh.Sockets is protected in Python (5.8): look the sockets up by name instead.
        sockets = ["Tentacle_%02d" % i for i in range(8) if head.find_socket("Tentacle_%02d" % i)]
        unreal.log("SM_MechSentinel_Head sockets: %s" % sockets)
        if len(sockets) < 8:
            unreal.log_warning("Expected 8 Tentacle_XX sockets on the head; the tentacles will use the built-in ring.")


def _expr(material, cls, x, y, **props):
    node = MEL.create_material_expression(material, cls, x, y)
    for key, value in props.items():
        node.set_editor_property(key, value)
    return node


def create_tentacle_material():
    path = MATERIAL_DIR + "/M_MechSentinelTentacle"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.log("M_MechSentinelTentacle already exists, left as is.")
        return unreal.load_asset(path)

    material = asset_tools.create_asset("M_MechSentinelTentacle", MATERIAL_DIR, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property("used_with_niagara_ribbons", True)
    # Also used by the optional claw mesh renderer at the ribbon tips.
    material.set_editor_property("used_with_niagara_mesh_particles", True)

    # Sleeve bands: U runs along the ribbon (0 at the root), 11 sleeves; a sharp mask at every groove.
    uv = _expr(material, unreal.MaterialExpressionTextureCoordinate, -1400, 0)
    u = _expr(material, unreal.MaterialExpressionComponentMask, -1250, 0, r=True, g=False, b=False, a=False)
    bands = _expr(material, unreal.MaterialExpressionMultiply, -1100, 0, const_b=11.0)
    frac = _expr(material, unreal.MaterialExpressionFrac, -950, 0)
    centered = _expr(material, unreal.MaterialExpressionSubtract, -800, 0, const_b=0.5)
    absolute = _expr(material, unreal.MaterialExpressionAbs, -650, 0)
    doubled = _expr(material, unreal.MaterialExpressionMultiply, -500, 0, const_b=2.0)
    groove = _expr(material, unreal.MaterialExpressionPower, -350, 0, const_exponent=8.0)
    MEL.connect_material_expressions(uv, "", u, "")
    MEL.connect_material_expressions(u, "", bands, "A")
    MEL.connect_material_expressions(bands, "", frac, "")
    MEL.connect_material_expressions(frac, "", centered, "A")
    MEL.connect_material_expressions(centered, "", absolute, "")
    MEL.connect_material_expressions(absolute, "", doubled, "A")
    MEL.connect_material_expressions(doubled, "", groove, "Base")

    # Dark gunmetal, darker and rougher in the grooves.
    metal = _expr(material, unreal.MaterialExpressionConstant3Vector, -350, -250, constant=unreal.LinearColor(0.045, 0.05, 0.058, 1.0))
    dark = _expr(material, unreal.MaterialExpressionConstant3Vector, -350, -150, constant=unreal.LinearColor(0.01, 0.011, 0.013, 1.0))
    base = _expr(material, unreal.MaterialExpressionLinearInterpolate, -100, -200)
    MEL.connect_material_expressions(metal, "", base, "A")
    MEL.connect_material_expressions(dark, "", base, "B")
    MEL.connect_material_expressions(groove, "", base, "Alpha")
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    roughness = _expr(material, unreal.MaterialExpressionLinearInterpolate, -100, 50, const_a=0.42, const_b=0.75)
    MEL.connect_material_expressions(groove, "", roughness, "Alpha")
    MEL.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)

    metallic = _expr(material, unreal.MaterialExpressionConstant, -100, 200, r=0.85)
    MEL.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)

    # Glow: the Niagara system writes Particles.Color (rgb = glow color, a = intensity).
    particle_color = _expr(material, unreal.MaterialExpressionParticleColor, -350, 350)
    emissive = _expr(material, unreal.MaterialExpressionMultiply, -100, 350)
    MEL.connect_material_expressions(particle_color, "", emissive, "A")
    MEL.connect_material_expressions(particle_color, "A", emissive, "B")
    MEL.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    MEL.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    unreal.log("Created %s" % path)
    return material


def _picd(material, index, x, y, default):
    """PerInstanceCustomData[index]; default is used outside instanced meshes (material preview, plain mesh)."""
    return _expr(material, unreal.MaterialExpressionPerInstanceCustomData, x, y, data_index=index, const_default_value=default)


def _new_material(name):
    path = MATERIAL_DIR + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.log("%s already exists, left as is." % name)
        return unreal.load_asset(path), False
    material = asset_tools.create_asset(name, MATERIAL_DIR, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property("used_with_instanced_static_meshes", True)
    return material, True


def _finish(material):
    MEL.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    unreal.log("Created %s" % material.get_path_name())


def create_body_material():
    material, created = _new_material("M_MechSentinelBody")
    if not created:
        return material

    # Custom data 1 = health fraction (1 = full), 2 = hit flash (1 -> 0 in ~0.25 s).
    health = _picd(material, 1, -900, -100, 1.0)
    flash = _picd(material, 2, -900, 350, 0.0)

    metal = _expr(material, unreal.MaterialExpressionConstant3Vector, -650, -300, constant=unreal.LinearColor(0.045, 0.05, 0.058, 1.0))
    damage_dim = _expr(material, unreal.MaterialExpressionLinearInterpolate, -650, -100, const_a=0.45, const_b=1.0)
    MEL.connect_material_expressions(health, "", damage_dim, "Alpha")
    base = _expr(material, unreal.MaterialExpressionMultiply, -400, -200)
    MEL.connect_material_expressions(metal, "", base, "A")
    MEL.connect_material_expressions(damage_dim, "", base, "B")
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    metallic = _expr(material, unreal.MaterialExpressionConstant, -400, 0, r=0.85)
    MEL.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)

    roughness = _expr(material, unreal.MaterialExpressionLinearInterpolate, -400, 150, const_a=0.7, const_b=0.42)
    MEL.connect_material_expressions(health, "", roughness, "Alpha")
    MEL.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)

    flash_emissive = _expr(material, unreal.MaterialExpressionMultiply, -400, 350, const_b=4.0)
    MEL.connect_material_expressions(flash, "", flash_emissive, "A")
    MEL.connect_material_property(flash_emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    _finish(material)
    return material


def _state_is(material, state, value, x, y):
    """1 when the state custom data equals value (0 Seeking, 1 Attacking, 2 Stunned, 3 Dead), else 0."""
    delta = _expr(material, unreal.MaterialExpressionSubtract, x, y, const_b=float(value))
    MEL.connect_material_expressions(state, "", delta, "A")
    absolute = _expr(material, unreal.MaterialExpressionAbs, x + 150, y)
    MEL.connect_material_expressions(delta, "", absolute, "")
    clamped = _expr(material, unreal.MaterialExpressionSaturate, x + 300, y)
    MEL.connect_material_expressions(absolute, "", clamped, "")
    result = _expr(material, unreal.MaterialExpressionOneMinus, x + 450, y)
    MEL.connect_material_expressions(clamped, "", result, "")
    return result


def create_eyes_material():
    material, created = _new_material("M_MechSentinelEyes")
    if not created:
        return material

    # Custom data 0 = state, 3 = attack glow (1 -> 0 in ~0.4 s).
    state = _picd(material, 0, -1700, 0, 0.0)
    attack_glow = _picd(material, 3, -1700, 300, 0.0)

    attacking = _state_is(material, state, 1, -1450, -200)
    stunned = _state_is(material, state, 2, -1450, 0)
    dead_delta = _expr(material, unreal.MaterialExpressionSubtract, -1450, 200, const_b=2.0)
    MEL.connect_material_expressions(state, "", dead_delta, "A")
    dead = _expr(material, unreal.MaterialExpressionSaturate, -1300, 200)
    MEL.connect_material_expressions(dead_delta, "", dead, "")

    # glow = (1 + 1.5 * attacking + 4 * attack glow) * (stunned ? square-wave flicker : 1) * (1 - dead)
    attack_boost = _expr(material, unreal.MaterialExpressionMultiply, -900, -200, const_b=1.5)
    MEL.connect_material_expressions(attacking, "", attack_boost, "A")
    pulse = _expr(material, unreal.MaterialExpressionMultiply, -900, 300, const_b=4.0)
    MEL.connect_material_expressions(attack_glow, "", pulse, "A")
    boosts = _expr(material, unreal.MaterialExpressionAdd, -750, 0)
    MEL.connect_material_expressions(attack_boost, "", boosts, "A")
    MEL.connect_material_expressions(pulse, "", boosts, "B")
    level = _expr(material, unreal.MaterialExpressionAdd, -600, 0, const_b=1.0)
    MEL.connect_material_expressions(boosts, "", level, "A")

    time = _expr(material, unreal.MaterialExpressionTime, -1150, 450)
    fast = _expr(material, unreal.MaterialExpressionMultiply, -1000, 450, const_b=9.0)
    MEL.connect_material_expressions(time, "", fast, "A")
    wave = _expr(material, unreal.MaterialExpressionFrac, -850, 450)
    MEL.connect_material_expressions(fast, "", wave, "")
    flicker = _expr(material, unreal.MaterialExpressionRound, -700, 450)
    MEL.connect_material_expressions(wave, "", flicker, "")
    stun_mul = _expr(material, unreal.MaterialExpressionLinearInterpolate, -550, 300, const_a=1.0)
    MEL.connect_material_expressions(flicker, "", stun_mul, "B")
    MEL.connect_material_expressions(stunned, "", stun_mul, "Alpha")

    lit = _expr(material, unreal.MaterialExpressionMultiply, -450, 0)
    MEL.connect_material_expressions(level, "", lit, "A")
    MEL.connect_material_expressions(stun_mul, "", lit, "B")
    alive = _expr(material, unreal.MaterialExpressionOneMinus, -1150, 200)
    MEL.connect_material_expressions(dead, "", alive, "")
    glow = _expr(material, unreal.MaterialExpressionMultiply, -300, 100)
    MEL.connect_material_expressions(lit, "", glow, "A")
    MEL.connect_material_expressions(alive, "", glow, "B")

    red = _expr(material, unreal.MaterialExpressionConstant3Vector, -300, -150, constant=unreal.LinearColor(6.0, 0.18, 0.06, 1.0))
    emissive = _expr(material, unreal.MaterialExpressionMultiply, -100, 0)
    MEL.connect_material_expressions(red, "", emissive, "A")
    MEL.connect_material_expressions(glow, "", emissive, "B")
    MEL.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    lens = _expr(material, unreal.MaterialExpressionConstant3Vector, -100, -250, constant=unreal.LinearColor(0.3, 0.01, 0.005, 1.0))
    MEL.connect_material_property(lens, "", unreal.MaterialProperty.MP_BASE_COLOR)
    roughness = _expr(material, unreal.MaterialExpressionConstant, -100, 250, r=0.2)
    MEL.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)

    _finish(material)
    return material


def assign_mesh_materials(body, eyes):
    """Slots come from the Blender material names: [0] MI_MechSentinel_Body, [1] MI_MechSentinel_Eyes."""
    for name in ASSETS:
        mesh = unreal.load_asset(MESH_DIR + "/" + name)
        if not mesh:
            continue
        body_index = mesh.get_material_index("MI_MechSentinel_Body")
        eyes_index = mesh.get_material_index("MI_MechSentinel_Eyes")
        if body_index < 0:
            body_index = 0
        mesh.set_material(body_index, body)
        if eyes_index >= 0:
            mesh.set_material(eyes_index, eyes)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        unreal.log("%s: body -> slot %d, eyes -> slot %d" % (name, body_index, eyes_index))


import_meshes()
create_tentacle_material()
assign_mesh_materials(create_body_material(), create_eyes_material())
unreal.log("MechSentinel: next, build NS_MechSentinelTentacles (README section 15) and the entity config (README section 1).")
