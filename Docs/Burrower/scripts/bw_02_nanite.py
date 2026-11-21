# bw_02_nanite.py - OPTIONAL (not part of the default run): enable Nanite on /Game/Assets/Enemies/Burrower/SK_Burrower.
# Use it only if the 1.24 M triangle mesh is too heavy in the editor or in PIE (EDITOR_SESSION.md step 2) and say so in
# the report. Run after bw_02_import.py, editor not in PIE, a few GB of free memory (the Nanite build is heavy):
#     Docs/Burrower/scripts/harness/inbox.sh 02_nanite Docs/Burrower/scripts/bw_02_nanite.py 1800
# Undo: set ENABLE = False and run it again.
#
# 5.8 source facts used:
# * USkeletalMesh::NaniteSettings is UPROPERTY(EditAnywhere) FMeshNaniteSettings (SkeletalMesh.h:963), bEnabled is
#   BlueprintReadWrite (EngineTypes.h ~3286) -> python 'nanite_settings' / 'enabled'.
# * set_editor_property notifies PostEditChangeProperty, which calls Build() for every non-interactive change
#   (SkeletalMesh.cpp:1525): that is the Nanite rebuild. Saving waits for the async build (SkeletalMesh.cpp:2024).
# * r.Nanite.AllowSkinnedMeshes defaults to 1 (NaniteResources.cpp:106, read-only CVar); the clone's DefaultEngine.ini
#   sets r.Nanite.ProjectEnabled=True.
# * Registry tags NaniteEnabled / NaniteTriangles come from USkeletalMesh::GetAssetRegistryTags (SkeletalMesh.cpp ~4613).
# * MATUSAGE_Nanite exists in EMaterialUsage (MaterialInterface.h); MaterialEditingLibrary.set_base_material_usage.
import unreal
import os, json, time, traceback

ENABLE = True
SET_MATERIAL_USAGE = True        # also tick "Used with Nanite" on our M_Burrower_Grey (only that material)

CLONE = '/mnt/new_partition/UnrealProjects/_BurrowerWork'
FOLDER = '/Game/Assets/Enemies/Burrower'
SK = FOLDER + '/SK_Burrower'
GREY = FOLDER + '/M_Burrower_Grey'
REPORT = CLONE + '/Saved/Burrower/nanite_report.json'


def _bw02n_main():
    res = {'enable': ENABLE, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}
    counts = {'PASS': 0, 'FAIL': 0, 'WARN': 0}

    def out(kind, msg):
        if kind in counts:
            counts[kind] += 1
        print('%s: [nanite] %s' % (kind, msg))

    try:
        try:
            proj = os.path.normpath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
        except Exception:
            proj = os.path.normpath(os.path.abspath(unreal.Paths.project_dir()))
        if proj != os.path.normpath(CLONE):
            out('FAIL', 'editor project is %s, not the clone %s; nothing done' % (proj, CLONE))
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les is not None and les.is_in_play_in_editor():
            out('FAIL', 'PIE is running; stop it first. Nothing done.')
            return
        if not unreal.EditorAssetLibrary.does_asset_exist(SK):
            out('FAIL', '%s does not exist; run bw_02_import.py first' % SK)
            return
        skm = unreal.EditorAssetLibrary.load_asset(SK)
        try:
            print('INFO: [nanite] r.Nanite.ProjectEnabled=%s r.Nanite.AllowSkinnedMeshes=%s' % (
                unreal.SystemLibrary.get_console_variable_int_value('r.Nanite.ProjectEnabled'),
                unreal.SystemLibrary.get_console_variable_int_value('r.Nanite.AllowSkinnedMeshes')))
        except Exception:
            pass
        ns = skm.get_editor_property('nanite_settings')
        before = bool(ns.get_editor_property('enabled'))
        res['enabled_before'] = before
        print('INFO: [nanite] nanite_settings.enabled was %s' % before)
        changed = False
        if before != ENABLE:
            ns.set_editor_property('enabled', ENABLE)
            t0 = time.time()
            skm.set_editor_property('nanite_settings', ns)      # PostEditChangeProperty -> Build()
            res['set_seconds'] = round(time.time() - t0, 1)
            print('INFO: [nanite] set enabled=%s (%.1f s; the build may continue asynchronously)' % (
                ENABLE, res['set_seconds']))
            changed = True
        if SET_MATERIAL_USAGE and ENABLE and unreal.EditorAssetLibrary.does_asset_exist(GREY):
            try:
                mat = unreal.EditorAssetLibrary.load_asset(GREY)
                usage = unreal.MaterialUsage.MATUSAGE_NANITE
                if not unreal.MaterialEditingLibrary.has_material_usage(mat, usage):
                    unreal.MaterialEditingLibrary.set_base_material_usage(mat, usage, True)
                    unreal.MaterialEditingLibrary.recompile_material(mat)
                    ok = bool(unreal.EditorAssetLibrary.save_asset(GREY, only_if_is_dirty=False))
                    out('PASS' if ok else 'FAIL', 'M_Burrower_Grey: Used with Nanite set, saved=%s' % ok)
            except Exception as e:
                out('WARN', 'material usage not set (%s); the editor sets it on first use (then save the material)' % e)
        if changed:
            t0 = time.time()
            ok = bool(unreal.EditorAssetLibrary.save_asset(SK, only_if_is_dirty=False))   # waits for the build
            res['save_seconds'] = round(time.time() - t0, 1)
            out('PASS' if ok else 'FAIL', 'saved %s (%.1f s)' % (SK, res['save_seconds']))
        ad = unreal.AssetRegistryHelpers.create_asset_data(skm)
        tags = {}
        for t in ('NaniteEnabled', 'NaniteTriangles', 'NaniteVertices', 'Triangles', 'EstNaniteCompressedSize'):
            v = ad.get_tag_value(t)
            tags[t] = None if v is None else str(v)
        res['tags'] = tags
        now = bool(skm.get_editor_property('nanite_settings').get_editor_property('enabled'))
        res['enabled_after'] = now
        if ENABLE:
            ntri = int(tags.get('NaniteTriangles') or 0)
            if now and ntri > 0:
                out('PASS', 'Nanite enabled, NaniteTriangles=%d (LOD0 triangles %s)' % (ntri, tags.get('Triangles')))
            elif now:
                out('WARN', 'Nanite enabled but NaniteTriangles=%s: the build may still be running; rerun this script '
                    'in a minute (it only reads the tags when nothing changes)' % tags.get('NaniteTriangles'))
            else:
                out('FAIL', 'nanite_settings.enabled is still False')
        else:
            out('PASS' if not now else 'FAIL', 'Nanite disabled=%s' % (not now))
        print('INFO: [nanite] tags %s' % tags)
    except Exception as e:
        out('FAIL', 'exception %s\n%s' % (e, traceback.format_exc()))
    finally:
        res['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
        res['summary'] = counts
        try:
            os.makedirs(os.path.dirname(REPORT), exist_ok=True)
            with open(REPORT, 'w') as f:
                json.dump(res, f, indent=1, default=str)
            print('INFO: [nanite] wrote ' + REPORT)
        except Exception as e:
            print('WARN: [nanite] report not written: %s' % e)
        print('RESULT: bw_02_nanite %d PASS, %d FAIL, %d WARN' % (counts['PASS'], counts['FAIL'], counts['WARN']))


_bw02n_main()
