# as_02_textures_material.py - imports the prop atlas textures and makes M_AirshipProps (a copy of M_Airship with the
# props texture). Re-runnable (reimports over the existing textures, re-duplicates the material only when missing).
#   /Game/Assets/MyShip/Drivable/Textures/T_AirshipProps_ComicLines  (sRGB, TC_Default)
#   /Game/Assets/MyShip/Drivable/Textures/T_AirshipProps_ComicMask   (linear: sRGB off, TC_Masks)
#   /Game/Assets/MyShip/Drivable/Materials/M_AirshipProps            (M_Airship graph: ComicLines -> Base Color, roughness 0.9, lit)
import unreal

AS_SRC = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/props/textures'
AS_TEX = '/Game/Assets/MyShip/Drivable/Textures'
AS_MAT = '/Game/Assets/MyShip/Drivable/Materials'
_eal = unreal.EditorAssetLibrary


def _as02_expressions(mat):
    return [e for e in unreal.ObjectIterator(unreal.MaterialExpression) if e.get_outer() == mat]


def _as02_describe(mat):
    out = []
    for e in _as02_expressions(mat):
        d = type(e).__name__
        for p in ('texture', 'r', 'constant', 'sampler_type', 'parameter_name', 'default_value'):
            try:
                v = e.get_editor_property(p)
                d += ' %s=%s' % (p, v.get_path_name() if hasattr(v, 'get_path_name') else v)
            except Exception:
                pass
        out.append(d)
    return out


def as02_run():
    rep = []
    tasks = []
    for n in ('T_AirshipProps_ComicLines', 'T_AirshipProps_ComicMask'):
        t = unreal.AssetImportTask()
        t.set_editor_property('filename', '%s/%s.png' % (AS_SRC, n))
        t.set_editor_property('destination_path', AS_TEX)
        t.set_editor_property('destination_name', n)
        t.set_editor_property('automated', True)
        t.set_editor_property('replace_existing', True)
        t.set_editor_property('save', False)
        tasks.append(t)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    for t in tasks:
        rep.append('import %s -> %s' % (t.get_editor_property('filename'), list(t.get_editor_property('imported_object_paths'))))
    ref = unreal.load_asset('/Game/Assets/MyShip/T_Airship_ComicMask')
    rep.append('reference T_Airship_ComicMask: srgb=%s compression=%s' % (ref.get_editor_property('srgb'), ref.get_editor_property('compression_settings')))
    lines = unreal.load_asset(AS_TEX + '/T_AirshipProps_ComicLines')
    lines.set_editor_property('srgb', True)
    lines.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
    mask = unreal.load_asset(AS_TEX + '/T_AirshipProps_ComicMask')
    mask.set_editor_property('srgb', False)
    mask.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
    for tx in (lines, mask):
        rep.append('%s: %dx%d srgb=%s compression=%s' % (tx.get_name(), tx.blueprint_get_size_x(), tx.blueprint_get_size_y(),
                                                         tx.get_editor_property('srgb'), tx.get_editor_property('compression_settings')))
    src = unreal.load_asset('/Game/Assets/MyShip/M_Airship')
    rep.append('M_Airship: ' + ' | '.join(_as02_describe(src)))
    mp = AS_MAT + '/M_AirshipProps'
    if not _eal.does_asset_exist(mp):
        m = _eal.duplicate_asset('/Game/Assets/MyShip/M_Airship', mp)
        rep.append('duplicated M_Airship -> %s' % m.get_path_name())
    m = unreal.load_asset(mp)
    # texture samples: matched to M_Airship's by expression name (setting a Color texture on the Masks sample silently
    # flips its sampler type, so a type-based match fails on a rerun)
    import os
    exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_02b_fix_mask_sample.py')).read(), {'unreal': unreal})
    rep.append('M_AirshipProps: ' + ' | '.join(_as02_describe(m)))
    rep.append('used textures: %s' % [t.get_path_name() for t in unreal.MaterialEditingLibrary.get_used_textures(m)])
    rep.append('shading=%s blend=%s two_sided=%s' % (m.get_editor_property('shading_model'), m.get_editor_property('blend_mode'),
                                                     m.get_editor_property('two_sided')))
    for p in (AS_TEX + '/T_AirshipProps_ComicLines', AS_TEX + '/T_AirshipProps_ComicMask', mp):
        rep.append('saved %s %s' % (p, _eal.save_asset(p, only_if_is_dirty=False)))
    return rep


for l in as02_run():
    print(l)
