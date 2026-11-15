# Mech Sentinel - Unreal Editor import helper.
# Run inside the editor: Tools > Execute Python Script... (Python Editor Script Plugin enabled), or
#   UnrealEditor-Cmd.exe Aura.uproject -run=pythonscript -script="<repo>/SourceArt/MechSentinel/ue_import_mech_sentinel.py"
#
# 1. Imports the four FBX files from Export/ into /Game/MechSentinel/Meshes (sockets SOCKET_Tentacle_XX become
#    static mesh sockets Tentacle_XX on SM_MechSentinel_Head).
# 2. Creates /Game/MechSentinel/Materials/M_MechSentinelTentacle, the ribbon tube material used by the Niagara
#    tentacle system (sleeve bands along the ribbon, glow from the particle color), also usable by the claw meshes.
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


import_meshes()
create_tentacle_material()
unreal.log("MechSentinel: next, build NS_MechSentinelTentacles (README, section Tentacles) and assign the meshes on the entity config.")
