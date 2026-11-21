# Mech Sentinel - brings the existing body and eye materials up to date with the self-buff visuals.
# Run inside the editor (Tools > Execute Python Script..., Python Editor Script Plugin enabled), with PIE stopped.
#
# M_MechSentinelBody gets a coloured rim per active self-buff (armor steel blue, speed cyan-white, damage orange) on top
# of the hit flash, and M_MechSentinelEyes tints its red toward the active buff's colour. Both read the buff fades from
# PerInstanceCustomData 4 / 5 / 6 (UMechSentinelVisualDataProcessor, NumCustomDataFloats 7). With no buff on, both look
# exactly as before.
#
# ue_import_mech_sentinel.py builds these graphs for new materials but leaves existing ones alone. This script rebuilds
# the EXISTING assets in place with the same graph builders: every expression is deleted and the graph is built again,
# then the material is recompiled and saved. The assets are not deleted or recreated, so every reference to them (the
# mesh slots) stays. Re-running is safe: the result is the same graph again.
# Afterwards git status should show only the two .uasset files of /Game/MechSentinel/Materials as modified.

import importlib.util
import os

import unreal

MATERIAL_DIR = "/Game/MechSentinel/Materials"
# Asset name -> graph builder in ue_import_mech_sentinel.py.
MATERIALS = [("M_MechSentinelBody", "build_body_graph"), ("M_MechSentinelEyes", "build_eyes_graph")]
CONFIG_PATH = "/Game/MechSentinel/Data/DA_MechSentinelConfig"
REQUIRED_CUSTOM_DATA_FLOATS = 7
IMPORT_SCRIPT = "ue_import_mech_sentinel.py"
PACKAGE_TAG = b"\xC1\x83\x2A\x9E"  # first bytes of every .uasset / .umap package (a Git LFS pointer starts with "vers")


class Abort(Exception):
    pass


def log(msg):
    unreal.log("MechSentinel buff visuals: " + msg)


def script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:  # executed without a file name (e.g. by a tool): the repo layout
        return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), "SourceArt", "MechSentinel")


def check_editor():
    for name in ("EditorAssetLibrary", "MaterialEditingLibrary", "Paths", "LevelEditorSubsystem"):
        if not hasattr(unreal, name):
            raise Abort("unreal.%s is missing: run this inside the Unreal Editor with the Python Editor Script Plugin." % name)


def is_playing():
    """True while Play In Editor (or Simulate) runs."""
    try:
        if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
            return True
    except AttributeError:
        pass
    try:
        return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world() is not None
    except AttributeError:
        return False


def package_file(asset_path):
    content_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
    return os.path.normpath(os.path.join(content_dir, asset_path[len("/Game/"):] + ".uasset"))


def check_real_package(asset_path):
    """The asset's file must be a real package, not a Git LFS pointer: saving over a pointer would lose the asset."""
    path = package_file(asset_path)
    if not os.path.isfile(path):
        raise Abort("%s not found at %s: run ue_import_mech_sentinel.py first." % (asset_path, path))
    with open(path, "rb") as handle:
        head = handle.read(4)
    if head == b"vers":
        raise Abort("%s is a Git LFS pointer, not the asset: run 'git lfs pull', restart the editor, then run this again." % path)
    if head != PACKAGE_TAG:
        raise Abort("%s does not start like an Unreal package (%r)." % (path, head))


def load_import_script():
    """ue_import_mech_sentinel.py as a module: its graph builders, without running its import (see its last lines)."""
    path = os.path.join(script_dir(), IMPORT_SCRIPT)
    if not os.path.isfile(path):
        raise Abort("%s not found next to this script (%s)." % (IMPORT_SCRIPT, path))
    try:
        spec = importlib.util.spec_from_file_location("ue_import_mech_sentinel", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # loaded fresh on every run, so edits to the import script are picked up
    except Exception as error:
        raise Abort("could not load %s: %s" % (path, error))
    for _, builder in MATERIALS:
        if not hasattr(module, builder):
            raise Abort("%s has no %s(): it is older than this script." % (IMPORT_SCRIPT, builder))
    return module


def dry_run(importer):
    """Builds both graphs into a throwaway transient material first: an API mismatch fails before any asset is touched."""
    try:
        scratch = unreal.new_object(unreal.Material)
        for _, builder in MATERIALS:
            unreal.MaterialEditingLibrary.delete_all_material_expressions(scratch)
            getattr(importer, builder)(scratch)
    except Exception as error:
        raise Abort("the graph builders failed on a scratch material, no asset was touched: %s" % error)


def close_editors(asset):
    """An open material editor works on its own copy and would overwrite the rebuilt graph on Apply (best effort)."""
    try:
        unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(asset)
    except Exception:  # not exposed in every version: then just close the material editors by hand first
        pass


def rebuild(importer, name, builder):
    path = MATERIAL_DIR + "/" + name
    material = unreal.load_asset(path)
    if not isinstance(material, unreal.Material):
        raise Abort("%s did not load as a Material (%r)." % (path, material))

    close_editors(material)
    mel = unreal.MaterialEditingLibrary
    before = mel.get_num_material_expressions(material)
    material.modify()
    # Deleting an expression also clears the material outputs and inputs it fed, so the graph starts empty.
    mel.delete_all_material_expressions(material)
    try:
        getattr(importer, builder)(material)
    except Exception as error:
        raise Abort("building %s failed (%s). Its graph is incomplete in memory: do not save it, restart the editor." % (path, error))
    after = mel.get_num_material_expressions(material)
    mel.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise Abort("could not save %s (checked out / read only?)." % path)
    log("rebuilt %s: %d -> %d expressions, recompiled and saved." % (path, before, after))


def check_custom_data_floats():
    """Warns when the entity config sends fewer than 7 custom data floats (the buff colours would never show)."""
    try:
        config_asset = unreal.load_asset(CONFIG_PATH) if unreal.EditorAssetLibrary.does_asset_exist(CONFIG_PATH) else None
        if not config_asset:
            log("note: %s not loaded, check NumCustomDataFloats (%d) in your entity config's Visualization trait." % (CONFIG_PATH, REQUIRED_CUSTOM_DATA_FLOATS))
            return
        for trait in config_asset.get_editor_property("config").get_editor_property("traits") or []:
            if trait and trait.get_class().get_name() == "MassVisualizationTrait_Copy":
                count = trait.get_editor_property("static_mesh_instance_desc").get_editor_property("num_custom_data_floats")
                if count < REQUIRED_CUSTOM_DATA_FLOATS:
                    unreal.log_warning("MechSentinel buff visuals: %s sends %d custom data floats; set NumCustomDataFloats to %d "
                                       "in its Visualization trait (or re-run ue_setup_mech_sentinel_demo.py)." % (CONFIG_PATH, count, REQUIRED_CUSTOM_DATA_FLOATS))
                return
    except Exception as error:  # informational only
        log("note: could not read NumCustomDataFloats from %s (%s)." % (CONFIG_PATH, error))


def main():
    try:
        check_editor()
        if is_playing():
            raise Abort("stop Play In Editor first.")
        for name, _ in MATERIALS:
            check_real_package(MATERIAL_DIR + "/" + name)
        importer = load_import_script()
        dry_run(importer)
        for name, builder in MATERIALS:
            rebuild(importer, name, builder)
    except Abort as error:
        unreal.log_error("MechSentinel buff visuals: aborted, nothing more was changed: %s" % error)
        return False

    check_custom_data_floats()
    log("done. git status should show Content%s/%s.uasset and %s.uasset as modified." % (MATERIAL_DIR[len("/Game"):], MATERIALS[0][0], MATERIALS[1][0]))
    return True


# Tools > Execute Python Script runs this as __main__; a plain exec by a tool gets another __name__ and runs it too.
# Importing it as a module (import ue_update_mech_sentinel_buff_visuals) runs nothing: call main().
if __name__ != "ue_update_mech_sentinel_buff_visuals":
    main()
