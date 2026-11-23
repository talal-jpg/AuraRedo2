# as_06_muzzle.py - NS_AirshipMuzzle: cannon muzzle blast + smoke puff along local +X (socket Cannon_*_Muzzle).
# NOTE: run as_07_fix_muzzle_compile.py right after this script (Blast_Puffs HLSL used "User.Global Scale", which does not compile).
# Copy of /Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash (the mech gun's flash) without the bullet shells,
# scaled up for the 2.6 m cannon with its own User.Global Scale (drives sprite sizes, offsets, velocities, light radius),
# denser smoke, plus Blast_Puffs: a burst of comic smoke puffs (MI_Ball_01 (validation 2026-11-22: MI_Popcorn_Puff is a mesh material, a square on a sprite)) in world space so they hang in the air.
# Recreates the asset from scratch on every run (our own asset only).
import os, unreal, json
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
AS_MUZZLE_SCALE = globals().get('AS_MUZZLE_SCALE') or 5.0
P = '/Game/Assets/MyShip/Drivable/FX/NS_AirshipMuzzle'
S = P + '.NS_AirshipMuzzle'
eal = unreal.EditorAssetLibrary
if eal.does_asset_exist(P):
    eal.delete_asset(P)
print('dup', eal.duplicate_asset('/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash', P).get_path_name())
nt('RemoveEmitter', emitterToRemove=ref(S, 'Bullet_Shell_Eject'))
fx_user_vars(S, [('Use Bullet Shell', T_BOOL, {'value': 0}, 'no shells for a cannon'),
                 ('Global Scale', T_FLOAT, {'value': AS_MUZZLE_SCALE}, 'x%.1f of the gun flash for the 2.6 m cannon' % AS_MUZZLE_SCALE),
                 ('Smoke Color', T_COLOR, {'r': 0.75, 'g': 0.75, 'b': 0.75, 'a': 0.5}, 'denser cannon smoke')])
nt('AddEmitter', system=sref(S), templateEmitter={'refPath': '/Niagara/DefaultAssets/Templates/Emitters/Fountain.Fountain'}, emitterName='Blast_Puffs')
print('Blast_Puffs', fx_fountain_to(
    S, 'Blast_Puffs', None, (1.2, 2.2), {'r': 0.93, 'g': 0.93, 'b': 0.95, 'a': 0.95},
    '30.0 * User.Global Scale', '52.0 * User.Global Scale', 'float3(1.0, (rand(2.0) - 1.0) * 0.45, (rand(2.0) - 1.0) * 0.45)',
    '(180.0 + 200.0 * rand(1.0)) * User.Global Scale', 60.0, 3.5,
    '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Ball_01.MI_Ball_01',
    growth='0.45 + 1.4 * sqrt(Particles.NormalizedAge)', shape_radius='8.0 * User.Global Scale', burst=12,
    pos_offset_expr='float3(10.0 * User.Global Scale, 0.0, 0.0)'))
print('emitters', [e['emitterName'] for e in nt('GetSystemSummary', system=sref(S))['emitters']])
print('user', [(u['name'], u['defaultValue']['value']) for u in nt('GetUserVariables', system=sref(S))['userVariables']])
print('saved', save_paths([P]))
