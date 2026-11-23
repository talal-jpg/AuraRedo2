# as_02b_fix_mask_sample.py - M_AirshipProps keeps M_Airship's graph: the texture sample that holds T_Airship_ComicLines in
# M_Airship (-> Base Color) gets T_AirshipProps_ComicLines, the one that holds T_Airship_ComicMask (Masks sampler, unconnected
# in M_Airship) gets T_AirshipProps_ComicMask. Matched by expression object name (duplicate_asset keeps the names).
import unreal
src = unreal.load_asset('/Game/Assets/MyShip/M_Airship')
m = unreal.load_asset('/Game/Assets/MyShip/Drivable/Materials/M_AirshipProps')
lines = unreal.load_asset('/Game/Assets/MyShip/Drivable/Textures/T_AirshipProps_ComicLines')
mask = unreal.load_asset('/Game/Assets/MyShip/Drivable/Textures/T_AirshipProps_ComicMask')
src_map = {e.get_name(): (e.get_editor_property('texture').get_name(), e.get_editor_property('sampler_type'))
           for e in unreal.ObjectIterator(unreal.MaterialExpressionTextureBase) if e.get_outer() == src}
print('M_Airship samples', src_map)
for e in [e for e in unreal.ObjectIterator(unreal.MaterialExpressionTextureBase) if e.get_outer() == m]:
    tex_name, st = src_map[e.get_name()]
    if tex_name == 'T_Airship_ComicMask':
        e.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        e.set_editor_property('texture', mask)
    else:
        e.set_editor_property('sampler_type', st)
        e.set_editor_property('texture', lines)
    print('M_AirshipProps', e.get_name(), e.get_editor_property('sampler_type'), '->', e.get_editor_property('texture').get_name())
unreal.MaterialEditingLibrary.recompile_material(m)
print('used textures', [t.get_name() for t in unreal.MaterialEditingLibrary.get_used_textures(m)])
for tx in (lines, mask):
    print(tx.get_name(), tx.blueprint_get_size_x(), tx.blueprint_get_size_y(), 'srgb', tx.get_editor_property('srgb'), tx.get_editor_property('compression_settings'))
print('saved', unreal.EditorAssetLibrary.save_asset('/Game/Assets/MyShip/Drivable/Materials/M_AirshipProps', only_if_is_dirty=False))
