# OBSOLETE (2026-11-22): superseded by as_05_fanwash.py + as_06_muzzle.py + as_07_fix_muzzle_compile.py (the assets kept). Do not run.
# as_05_fanwash_muzzle.py - (scope 2026-11-22 from Talal: copy existing effects, only hook up the controls, no new styling)
#   NS_AirshipFanWash = copy of /Game/Assets/MyPlatform/VFX/NS_HexDust (continuous, local-space dust motes)
#       + User.Thrust (0..1.5) / User.Boost (0..1); SpawnRate = 30 * Thrust * (1 + Boost) (no wake while the fan idles);
#       one SetParameters (particle spawn) gives the motes a speed along local -X (socket Turbine_*_Exhaust blows toward -X):
#       (250 + 750 * Thrust) * (1 + 0.6 * Boost) cm/s. Everything else (box/sphere spawn volume, curl noise, drag, sprites) as in NS_HexDust.
#   NS_AirshipMuzzle  = copy of /Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash with User.Use Bullet Shell = false
#       (forward is local +X like the socket Cannon_*_Muzzle). Not rescaled (User.Global Scale only drives the side-flash ring radius).
# Re-runnable: skips the copy when the asset exists and only re-applies the settings (the SetParameters module is added once).
import unreal, os, json
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
_eal = unreal.EditorAssetLibrary
FXD = '/Game/Assets/MyShip/Drivable/FX'
log = []


def _copy(src, name):
    dst = '%s/%s' % (FXD, name)
    if not _eal.does_asset_exist(dst):
        log.append('duplicated %s -> %s: %s' % (src, dst, _eal.duplicate_asset(src, dst) is not None))
    return '%s.%s' % (dst, name)


# ---- fan wash ----
F = _copy('/Game/Assets/MyPlatform/VFX/NS_HexDust', 'NS_AirshipFanWash')
fx_user_vars(F, [('Thrust', T_FLOAT, {'value': 1.0}, 'fan thrust 0..1.5 (AAirshipPawn FXThrustParam)'),
                 ('Boost', T_FLOAT, {'value': 0.0}, '0..1 boost (AAirshipPawn FXBoostParam)')])
E = 'HangingParticulates'
fx_set(F, E, 'EmitterUpdateScript', 'SpawnRate', 'SpawnRate', f_expr('30.0 * User.Thrust * (1.0 + User.Boost)'))
_ps = fx_modules(F, E, 'ParticleSpawnScript')
_vel = 'float3(-(250.0 + 750.0 * User.Thrust) * (1.0 + 0.6 * User.Boost), 0.0, 0.0)'
_have = [m for m in _ps if m.startswith('SetVariables_')]
if _have:
    fx_set(F, E, 'ParticleSpawnScript', _have[-1], 'Particles.Velocity', f_expr(_vel))
else:
    fx_setparams(F, E, 'ParticleSpawnScript', [('Particles.Velocity', T_VEC3, _vel, None)])
log.append('fan wash user vars %s' % [u['name'] for u in nt('GetUserVariables', system=sref(F))['userVariables']])
log.append('fan wash particle spawn %s' % fx_modules(F, E, 'ParticleSpawnScript'))

# ---- muzzle ----
M = _copy('/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash', 'NS_AirshipMuzzle')
fx_user_vars(M, [('Use Bullet Shell', T_BOOL, {'value': 0}, 'off for the airship cannons')])
log.append('muzzle user vars %s' % [(u['name'], u['defaultValue']['value']) for u in nt('GetUserVariables', system=sref(M))['userVariables']
                                    if u['name'] in ('User.Use Bullet Shell', 'User.Global Scale', 'User.Use Smoke')])

for l in log:
    print(l)
print('saved', save_paths([F.split('.')[0], M.split('.')[0]]))
