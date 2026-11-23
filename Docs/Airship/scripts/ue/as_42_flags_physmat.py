# as_42_flags_physmat.py - validation session 2026-11-22:
#  1. M_Airship (/Game/Assets/MyShip/M_Airship, our ship material, slot 0 of SK_Airship): bUsedWithSkeletalMesh was set
#     in memory at every editor start ("needed to set usage flag SkeletalMesh", MapCheck "was missing the usage flag")
#     -> set_base_material_usage + recompile + SAVE. The jet / puff materials picked by as_41 must already carry
#     their Niagara usage flags on disk (checked here, changed only if AS42_FIX_FX_FLAGS and the material is in AS42_OURS).
#  2. PM_AirshipHull (/Game/Assets/MyShip/Drivable/Physics/PM_AirshipHull): restitution 0.35 (combine Max, override) ->
#     AS42_RESTITUTION (0.08), combine Min with override, so the hull's low value wins against any other surface
#     (Chaos picks the higher-priority mode when the two differ: Max > Multiply > Min > Average; the project default is
#     Average). Friction stays 0.2. SAVED.
# Run: inbox.sh 42 Docs/Airship/scripts/ue/as_42_flags_physmat.py 300
import unreal, os, json
AS42_RESTITUTION = globals().get('AS42_RESTITUTION') or 0.08
AS42_FX_MATS = globals().get('AS42_FX_MATS') or []          # [(path, 'mesh'|'sprite')] to check (as_41 choices)
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
out = []

# ---- 1. M_Airship skeletal mesh usage
P = '/Game/Assets/MyShip/M_Airship'
m = EAL.load_asset(P)
before = m.get_editor_property('used_with_skeletal_mesh')
ok = MEL.set_base_material_usage(m, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, True)
MEL.recompile_material(m)
after = m.get_editor_property('used_with_skeletal_mesh')
out.append('%s: M_Airship used_with_skeletal_mesh %s -> %s (set_base_material_usage %s)' % ('PASS' if after else 'FAIL', before, after, ok))
if after:
    out.append('%s: saved %s' % ('PASS' if EAL.save_asset(P, only_if_is_dirty=False) else 'FAIL', P))

# ---- FX materials: Niagara usage on disk (read-only unless the material is ours)
for path, kind in AS42_FX_MATS:
    fm = EAL.load_asset(path.split('.')[0])
    b = fm if isinstance(fm, unreal.Material) else fm.get_base_material()
    prop = 'used_with_niagara_mesh_particles' if kind == 'mesh' else 'used_with_niagara_sprites'
    v = b.get_editor_property(prop)
    pkg_dirty = b.get_outermost().is_dirty() if hasattr(b.get_outermost(), 'is_dirty') else None
    out.append('%s: %s base %s %s = %s (package dirty %s)' % ('PASS' if v else 'FAIL', path, b.get_path_name(), prop, v, pkg_dirty))

# ---- 2. PM_AirshipHull
PM = '/Game/Assets/MyShip/Drivable/Physics/PM_AirshipHull'
pm = EAL.load_asset(PM)
was = {k: str(pm.get_editor_property(k)) for k in ('friction', 'restitution', 'restitution_combine_mode', 'override_restitution_combine_mode',
                                                    'friction_combine_mode', 'override_friction_combine_mode')}
pm.set_editor_property('restitution', float(AS42_RESTITUTION))
pm.set_editor_property('restitution_combine_mode', unreal.FrictionCombineMode.MIN)
pm.set_editor_property('override_restitution_combine_mode', True)
now = {k: str(pm.get_editor_property(k)) for k in was}
out.append('PM_AirshipHull %s -> %s' % (was, now))
okpm = abs(pm.get_editor_property('restitution') - float(AS42_RESTITUTION)) < 1e-4 and 'MIN' in now['restitution_combine_mode']
out.append('%s: saved %s' % ('PASS' if okpm and EAL.save_asset(PM, only_if_is_dirty=False) else 'FAIL', PM))
out.append('dirty after: %s' % [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
print('\n'.join(out))
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'val', 'as_42.txt'), 'w') as f:
    f.write('\n'.join(out) + '\n')
