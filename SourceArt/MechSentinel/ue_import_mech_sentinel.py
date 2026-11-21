# Mech Sentinel - Unreal Editor import helper.
# Run inside the editor: Tools > Execute Python Script... (Python Editor Script Plugin enabled), or
#   UnrealEditor-Cmd.exe Aura.uproject -run=pythonscript -script="<repo>/SourceArt/MechSentinel/ue_import_mech_sentinel.py"
#
# 1. Imports the four FBX files from Export/ into /Game/MechSentinel/Meshes (sockets SOCKET_Tentacle_XX become
#    static mesh sockets Tentacle_XX on SM_MechSentinel_Head).
# 2. Creates /Game/MechSentinel/Materials/M_MechSentinelTentacle, the ribbon tube material used by the Niagara
#    tentacle system (sleeve bands along the ribbon, glow from the particle color), also usable by the claw meshes.
# 3. Creates M_MechSentinelBody (dark gunmetal, darker when damaged, white hit flash, a coloured rim per active
#    self-buff) and M_MechSentinelEyes (red emissive: brighter when attacking, flickering when stunned, off when dead,
#    tinted toward the active self-buff's colour). Both read the per-instance custom data written by
#    UMechSentinelVisualDataProcessor (README section 12) and are assigned to the mesh slots.
# Re-running is safe: existing materials are left as they are, only the mesh slot assignment is redone. To bring
# existing materials up to date with the graphs below, run ue_update_mech_sentinel_buff_visuals.py (it rebuilds them in
# place). Importing this file as a module (import ue_import_mech_sentinel) runs nothing; call main().
# The Niagara system itself is built with the recipe in MyMechEntitySystemReadme.md ("Tentacles").

import os

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "Export")
MESH_DIR = "/Game/MechSentinel/Meshes"
MATERIAL_DIR = "/Game/MechSentinel/Materials"
ASSETS = ["SM_MechSentinel_Head", "SM_MechSentinel_Far", "SM_MechSentinel_Tentacle", "SM_MechSentinel_TentacleTip"]

# Self-buffs: custom data 4 armor, 5 speed, 6 damage, each a 0..1 fade (UMechSentinelVisualDataProcessor). Their
# PerInstanceCustomData default is 0, which is also what an ISM with fewer floats reads, and with all three at 0 both
# materials compute exactly what they did before the buffs.
BUFF_CUSTOM_DATA = (4, 5, 6)
# Body rim colours, emissive on top of the hit flash: armor steel blue, speed cyan-white, damage orange.
BODY_BUFF_COLORS = ((0.25, 0.45, 1.0), (0.55, 1.0, 1.0), (1.0, 0.35, 0.04))
BODY_BUFF_RIM_INTENSITY = 3.0
BODY_BUFF_RIM_FLOOR = 0.12  # share of the rim colour on surfaces facing the camera (the silhouette gets all of it)
BODY_BUFF_RIM_EXPONENT = 3.0
# Colours the eye red tints toward (same brightness range as the red 6 / 0.18 / 0.06), same buff order.
EYE_BUFF_COLORS = ((0.6, 1.5, 6.0), (2.2, 5.0, 6.0), (6.0, 1.9, 0.08))
EYE_BUFF_TINT = 0.85  # how far the red goes toward the buff colour at full fade

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


def _color(rgb):
    return unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0)


def _buff_fades(material, x, y):
    """The three self-buff fades: PerInstanceCustomData 4 / 5 / 6, default 0."""
    return [_picd(material, index, x, y + 150 * i, 0.0) for i, index in enumerate(BUFF_CUSTOM_DATA)]


def _sum(material, nodes, x, y):
    """nodes[0] + nodes[1] + ... as a chain of Add nodes."""
    total = nodes[0]
    for i, node in enumerate(nodes[1:]):
        add = _expr(material, unreal.MaterialExpressionAdd, x + 150 * i, y)
        MEL.connect_material_expressions(total, "", add, "A")
        MEL.connect_material_expressions(node, "", add, "B")
        total = add
    return total


def _buff_color_sum(material, fades, colors, x, y):
    """sum(fade_i * colour_i): black while no buff is on."""
    tinted = []
    for i, (fade, rgb) in enumerate(zip(fades, colors)):
        color = _expr(material, unreal.MaterialExpressionConstant3Vector, x, y + 150 * i + 60, constant=_color(rgb))
        tint = _expr(material, unreal.MaterialExpressionMultiply, x + 200, y + 150 * i)
        MEL.connect_material_expressions(fade, "", tint, "A")
        MEL.connect_material_expressions(color, "", tint, "B")
        tinted.append(tint)
    return _sum(material, tinted, x + 400, y + 150)


def _body_buff_rim(material, x, y):
    """Self-buff rim: sum(fade x colour) x lerp(floor, 1, fresnel) x intensity. 0 while no buff is on."""
    fades = _buff_fades(material, x, y)
    colors = _buff_color_sum(material, fades, BODY_BUFF_COLORS, x + 200, y)
    fresnel = _expr(material, unreal.MaterialExpressionFresnel, x + 500, y + 550,
                    exponent=BODY_BUFF_RIM_EXPONENT, base_reflect_fraction=0.0)
    rim = _expr(material, unreal.MaterialExpressionLinearInterpolate, x + 700, y + 550, const_a=BODY_BUFF_RIM_FLOOR, const_b=1.0)
    MEL.connect_material_expressions(fresnel, "", rim, "Alpha")
    rim_color = _expr(material, unreal.MaterialExpressionMultiply, x + 950, y + 300)
    MEL.connect_material_expressions(colors, "", rim_color, "A")
    MEL.connect_material_expressions(rim, "", rim_color, "B")
    lit = _expr(material, unreal.MaterialExpressionMultiply, x + 1100, y + 300, const_b=BODY_BUFF_RIM_INTENSITY)
    MEL.connect_material_expressions(rim_color, "", lit, "A")
    return lit


def create_body_material():
    material, created = _new_material("M_MechSentinelBody")
    if not created:
        return material
    build_body_graph(material)
    _finish(material)
    return material


def build_body_graph(material):
    """The body graph, built into a material without expressions (ue_update_mech_sentinel_buff_visuals.py uses it too)."""
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

    # Custom data 4 / 5 / 6 = self-buff fades: a coloured rim added to the flash (adds 0 while no buff is on).
    buff_rim = _body_buff_rim(material, -1700, 550)
    emissive = _expr(material, unreal.MaterialExpressionAdd, -200, 450)
    MEL.connect_material_expressions(flash_emissive, "", emissive, "A")
    MEL.connect_material_expressions(buff_rim, "", emissive, "B")
    MEL.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)


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


def _eye_buff_tint(material, red, x, y):
    """lerp(red, fade-weighted average of the active buffs' colours, saturate(sum of fades) x tint). Red while no buff is on."""
    fades = _buff_fades(material, x, y)
    colors = _buff_color_sum(material, fades, EYE_BUFF_COLORS, x + 200, y)
    total = _sum(material, fades, x + 200, y + 550)
    # Max: no 0 / 0 while no buff is on (colors is 0 then, so the average is 0 and the lerp keeps the red).
    safe_total = _expr(material, unreal.MaterialExpressionMax, x + 550, y + 550, const_b=0.0001)
    MEL.connect_material_expressions(total, "", safe_total, "A")
    average = _expr(material, unreal.MaterialExpressionDivide, x + 750, y + 300)
    MEL.connect_material_expressions(colors, "", average, "A")
    MEL.connect_material_expressions(safe_total, "", average, "B")
    amount = _expr(material, unreal.MaterialExpressionSaturate, x + 550, y + 700)
    MEL.connect_material_expressions(total, "", amount, "")
    tint = _expr(material, unreal.MaterialExpressionMultiply, x + 750, y + 700, const_b=EYE_BUFF_TINT)
    MEL.connect_material_expressions(amount, "", tint, "A")
    color = _expr(material, unreal.MaterialExpressionLinearInterpolate, x + 950, y + 300)
    MEL.connect_material_expressions(red, "", color, "A")
    MEL.connect_material_expressions(average, "", color, "B")
    MEL.connect_material_expressions(tint, "", color, "Alpha")
    return color


def create_eyes_material():
    material, created = _new_material("M_MechSentinelEyes")
    if not created:
        return material
    build_eyes_graph(material)
    _finish(material)
    return material


def build_eyes_graph(material):
    """The eye graph, built into a material without expressions (ue_update_mech_sentinel_buff_visuals.py uses it too)."""
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
    # Custom data 4 / 5 / 6 = self-buff fades: the red tints toward the active buff's colour (stays red while none is on).
    eye_color = _eye_buff_tint(material, red, -1400, -1100)
    emissive = _expr(material, unreal.MaterialExpressionMultiply, -100, 0)
    MEL.connect_material_expressions(eye_color, "", emissive, "A")
    MEL.connect_material_expressions(glow, "", emissive, "B")
    MEL.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    lens = _expr(material, unreal.MaterialExpressionConstant3Vector, -100, -250, constant=unreal.LinearColor(0.3, 0.01, 0.005, 1.0))
    MEL.connect_material_property(lens, "", unreal.MaterialProperty.MP_BASE_COLOR)
    roughness = _expr(material, unreal.MaterialExpressionConstant, -100, 250, r=0.2)
    MEL.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)


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


def main():
    import_meshes()
    create_tentacle_material()
    assign_mesh_materials(create_body_material(), create_eyes_material())
    unreal.log("MechSentinel: next, build NS_MechSentinelTentacles (README section 15) and the entity config (README section 1).")


# Run as a script (Tools > Execute Python Script, -run=pythonscript, or executed by a tool): do the import.
# ue_update_mech_sentinel_buff_visuals.py loads this file as the module "ue_import_mech_sentinel" for its graph builders,
# and then nothing runs.
if __name__ != "ue_import_mech_sentinel":
    main()
