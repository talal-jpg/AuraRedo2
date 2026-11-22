# as_10b_props_usage.py - M_AirshipProps (session-1 asset, ours) gets bUsedWithSkeletalMesh (it is slot 1 of SK_Airship).
# Run: inbox.sh 10b Docs/Airship/scripts/ue/as_10b_props_usage.py 300
P = '/Game/Assets/MyShip/Drivable/Materials/M_AirshipProps'
m = unreal.EditorAssetLibrary.load_asset(P)
print('INFO: class %s' % m.get_class().get_name())
base = m if isinstance(m, unreal.Material) else m.get_base_material()
print('INFO: base %s used_with_skeletal_mesh=%s' % (base.get_path_name(), base.get_editor_property('used_with_skeletal_mesh')))
if base.get_path_name().split('.')[0] != P:
    print('FAIL: base material is not ours, not changed')
else:
    MEL = unreal.MaterialEditingLibrary
    ok = MEL.set_base_material_usage(base, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, True)
    print('INFO: set_base_material_usage -> %s' % ok)
    MEL.recompile_material(base)
    u = base.get_editor_property('used_with_skeletal_mesh')
    print('%s: used_with_skeletal_mesh = %s' % ('PASS' if u else 'FAIL', u))
    if u:
        print('%s: saved %s' % ('PASS' if unreal.EditorAssetLibrary.save_asset(P, only_if_is_dirty=False) else 'FAIL', P))
print('dirty packages: %s' % [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
