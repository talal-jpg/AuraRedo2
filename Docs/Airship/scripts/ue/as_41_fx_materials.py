# as_41_fx_materials.py - validation session 2026-11-22: material swaps ONLY on our FX copies (Talal: no new effect
# authoring; existing project materials only). Problem 2 of the first PIE smoke test:
#   * jet (JetShell / JetCore mesh renderers, SM_Thruster): its own material M_Fire renders green (it ignores the
#     particle colour) -> OverrideMaterials = AS41_JET (an existing flame material that takes the particle colour, so the
#     emitters' orange shell / yellow-white core colours show)
#   * puffs (NS_AirshipThruster Puffs, NS_AirshipFanWash Wash, NS_AirshipMuzzle Blast_Puffs): MI_Popcorn_Puff is a mesh
#     material (Popcorn_Occlusion gradient for SM_Popcorn_Puff) and draws a solid square on a sprite -> AS41_PUFF
#     (an existing soft round sprite material)
# Only renderers that still use M_Fire / SM_Thruster's own material or MI_Popcorn_Puff (or a previous AS41 choice) are
# touched. Then the system editors are opened (they compile); check each with as_check_compile.py ('request', 'read'),
# then AS41_PHASE = 'save' closes the editors and saves exactly the three systems.
# Run: inbox.sh 41 as_41_fx_materials.py 120 (apply), ..., AS41_PHASE = 'save'.
import unreal, os, json, traceback
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
AS41_JET = globals().get('AS41_JET') or '/Game/Assets/Effects/Projectiles/FireExplosion/M_ExplosionSphere.M_ExplosionSphere'
AS41_PUFF = globals().get('AS41_PUFF') or '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Ball_01.MI_Ball_01'
AS41_PHASE = globals().get('AS41_PHASE') or 'apply'
FXD = '/Game/Assets/MyShip/Drivable/FX'
POPCORN = '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Popcorn_Puff.MI_Popcorn_Puff'
JOBS = [('NS_AirshipThruster', 'JetShell', 'jet'), ('NS_AirshipThruster', 'JetCore', 'jet'), ('NS_AirshipThruster', 'Puffs', 'puff'),
        ('NS_AirshipFanWash', 'Wash', 'puff'), ('NS_AirshipMuzzle', 'Blast_Puffs', 'puff')]
OLD_PUFFS = set([POPCORN] + list(globals().get('AS41_OLD_PUFFS') or []))


def _sys(n):
    return '%s/%s.%s' % (FXD, n, n)


if AS41_PHASE == 'apply':
    out = []
    for sn, em, kind in JOBS:
        S = _sys(sn)
        try:
            topo = nt('GetEmitterTopology', emitterRef=ref(S, em))
            nr = len(topo.get('renderers', topo.get('rendererClasses', [])))
            done = False
            for i in range(nr):
                pv = fx_renderer_get(S, em, i)
                meshes = [((x.get('mesh') or {}).get('refPath')) for x in (pv.get('Meshes') or [])]
                if kind == 'jet' and any(m and m.endswith('SM_Thruster.SM_Thruster') for m in meshes):
                    fx_renderer_props(S, em, i, {'bOverrideMaterials': True,
                                                 'OverrideMaterials': [{'explicitMat': {'refPath': AS41_JET}}]})
                    pv2 = fx_renderer_get(S, em, i)
                    out.append('%s/%s r%d mesh %s: override %s -> %s' % (sn, em, i, meshes, pv.get('OverrideMaterials') and [
                        (o.get('explicitMat') or {}).get('refPath') for o in pv['OverrideMaterials']], [
                        (o.get('explicitMat') or {}).get('refPath') for o in (pv2.get('OverrideMaterials') or [])]))
                    done = True
                elif kind == 'puff' and (pv.get('Material') or {}).get('refPath') in (OLD_PUFFS | {AS41_PUFF}):
                    fx_renderer_props(S, em, i, {'Material': {'refPath': AS41_PUFF}})
                    out.append('%s/%s r%d sprite: %s -> %s' % (sn, em, i, (pv.get('Material') or {}).get('refPath'),
                                                               (fx_renderer_get(S, em, i).get('Material') or {}).get('refPath')))
                    done = True
            if not done:
                out.append('WARN %s/%s: no renderer matched (left as is)' % (sn, em))
        except Exception:  # noqa: BLE001
            out.append('FAIL %s/%s: %s' % (sn, em, traceback.format_exc()[-500:]))
    for sn in sorted(set(j[0] for j in JOBS)):
        try:
            out.append('open %s: %s' % (sn, app('OpenEditorForAsset', assetPath='%s/%s' % (FXD, sn))))
        except Exception as e:  # noqa: BLE001
            out.append('WARN open %s: %s' % (sn, e))
    print('\n'.join(out))
    print('dirty', [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
elif AS41_PHASE == 'save':
    # after as_check_compile.py (AS_CC_PHASE 'request' then 'read') showed every system UpToDate without errors
    aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
    for sn in sorted(set(j[0] for j in JOBS)):
        a = unreal.load_asset('%s/%s' % (FXD, sn))
        print(sn, 'editors closed', aes.close_all_editors_for_asset(a))
    print('saved', save_paths(['%s/%s' % (FXD, sn) for sn in sorted(set(j[0] for j in JOBS))]))
    print('dirty', [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
