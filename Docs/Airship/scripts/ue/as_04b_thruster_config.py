# as_04b_thruster_config.py - step 2 of NS_AirshipThruster (run once on the fresh skeleton from as_04_thruster_create.py).
# A downward lift-thruster jet for an ink-on-paper comic airship. The component sits at socket Thruster_*_Flame (rest
# rotation world-aligned), so everything points along the component's local -Z.
#   User.Thrust   (float, 0..1.5: 0 idle pilot flame, 1 hover, 1.5 full)   set every frame by AAirshipPawn::UpdateFX
#   User.Boost    (float, 0..1)                                              set every frame by AAirshipPawn::UpdateFX
#   User.JetScale (float, 1) size multiplier for every emitter (per-component override in BP_AirshipPawn if the nozzles differ)
# Emitters
#   JetShell  local space, one persistent SM_Thruster mesh particle (override M_ExplosionSphere since 2026-11-22: masked
#             unlit, crisp noise-eroded edges, emissive = particle colour; SM_Thruster's own M_Fire drew green), orange,
#             length/width/brightness from Thrust/Boost + flicker
#   JetCore   same, smaller hot yellow-white core inside the shell
#   Puffs     world space comic smoke puffs (MI_Ball_01 (validation 2026-11-22: MI_Popcorn_Puff is a mesh material, a square on a sprite)) from the jet's lower half, rate/speed/size from Thrust/Boost
import unreal, os, json
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())

S = '/Game/Assets/MyShip/Drivable/FX/NS_AirshipThruster.NS_AirshipThruster'
ES, EU, PS, PU = 'EmitterSpawnScript', 'EmitterUpdateScript', 'ParticleSpawnScript', 'ParticleUpdateScript'
CS = '/Niagara/Enums/ENiagaraCoordinateSpace.ENiagaraCoordinateSpace'
log = []

# shared expressions (T = thrust, B = boost, J = scale, P = per-particle random phase)
L = '((0.18 + 0.82 * User.Thrust) * (1.0 + 0.4 * User.Boost))'
W = '((0.55 + 0.45 * min(User.Thrust, 1.2)) * (1.0 + 0.15 * User.Boost))'
Q_DOWN = 'float4(-0.70710678, 0.0, 0.0, 0.70710678)'   # SM_Thruster's +Y (flame axis) -> local -Z

fx_user_vars(S, [('Thrust', T_FLOAT, {'value': 1.0}, '0 idle, 1 hover, 1.5 full (AAirshipPawn FXThrustParam)'),
                 ('Boost', T_FLOAT, {'value': 0.0}, '0..1 boost (AAirshipPawn FXBoostParam)'),
                 ('JetScale', T_FLOAT, {'value': 1.0}, 'size multiplier for the whole jet')])
log.append('user vars: %s' % [u['name'] for u in nt('GetUserVariables', system=sref(S))['userVariables']])


def _jet(em, wcm, lcm, color_expr, fa, fb, fc):
    """wcm/lcm: width and length in cm at hover; the flicker frequencies fa/fb/fc differ per layer."""
    fx_emitter_props(S, em, {'bLocalSpace': True})
    ri = fx_mesh_renderer(S, em, '/Game/Assets/Effects/MyThruster/SM_Thruster.SM_Thruster')
    # validation 2026-11-22 (as_41): SM_Thruster's own M_Fire has a constant green emissive and ignores the particle colour;
    # M_ExplosionSphere (NS_FireExplosion's masked unlit fireball, emissive = particle colour) shows the colours set below
    fx_renderer_props(S, em, ri, {'bOverrideMaterials': True, 'OverrideMaterials': [
        {'explicitMat': {'refPath': '/Game/Assets/Effects/Projectiles/FireExplosion/M_ExplosionSphere.M_ExplosionSphere'}}]})
    sx = wcm / 2.3     # SM_Thruster: 2.3 cm wide (X, Z), 14.85 cm long (+Y, base at the origin)
    sy = lcm / 14.85
    fl = '(1.0 + 0.07 * sin(Engine.Time * %.1f + Particles.Phase * 6.283) + 0.05 * sin(Engine.Time * %.1f + Particles.Phase * 17.0))' % (fa, fb)
    fw = '(1.0 + 0.05 * sin(Engine.Time * %.1f + Particles.Phase * 9.1))' % fc
    scale = 'float3(%.3f * %s * %s, %.3f * %s * %s, %.3f * %s * %s) * User.JetScale' % (sx, W, fw, sy, L, fl, sx, W, fw)
    fx_setparams(S, em, PS, [('Particles.Phase', T_FLOAT, 'rand(1.0)', None),
                             ('Particles.MeshOrientation', T_QUAT, Q_DOWN, None)])
    fx_setparams(S, em, PU, [('Particles.Scale', T_VEC3, scale, {'x': 1, 'y': 1, 'z': 1}),
                             ('Particles.MeshOrientation', T_QUAT, Q_DOWN, None),
                             ('Particles.Color', T_COLOR, color_expr, None)])
    log.append('%s: modules %s' % (em, {s: fx_modules(S, em, s) for s in (EU, PS, PU)}))


# outer orange shell: 250 cm wide, 800 cm long at hover; dims at idle (pilot flame)
_jet('JetShell', 250.0, 800.0,
     'float4(float3(1.0, 0.36, 0.06) * (0.9 + 0.9 * min(User.Thrust, 1.0) + 2.0 * User.Boost), 1.0)', 41.0, 27.3, 33.0)
# inner hot core: 150 cm wide, 520 cm long; yellow-white, toward pale blue-white with boost
_jet('JetCore', 150.0, 520.0,
     'float4(lerp(float3(1.0, 0.86, 0.45), float3(0.8, 0.92, 1.0), User.Boost) * (1.2 + 1.2 * min(User.Thrust, 1.0) + 2.5 * User.Boost), 1.0)',
     53.0, 31.7, 47.0)

# ---- Puffs (world space) ----
E = 'Puffs'
fx_set(S, E, EU, 'SpawnRate', 'SpawnRate', f_expr('1.5 + 9.0 * User.Thrust + 10.0 * User.Boost'))
fx_set(S, E, PS, 'InitializeParticle', 'Lifetime Min', f_float(1.0))
fx_set(S, E, PS, 'InitializeParticle', 'Lifetime Max', f_float(1.8))
fx_set(S, E, PS, 'InitializeParticle', 'Color', fx_val(T_COLOR, {'r': 0.92, 'g': 0.92, 'b': 0.95, 'a': 0.9}))
fx_set(S, E, PS, 'InitializeParticle', 'Uniform Sprite Size Min', f_expr('140.0 * User.JetScale'))
fx_set(S, E, PS, 'InitializeParticle', 'Uniform Sprite Size Max', f_expr('240.0 * User.JetScale'))
fx_set(S, E, PS, 'InitializeParticle', 'UsePositionOffset', fx_val(T_BOOL, {'value': -1}))
fx_set(S, E, PS, 'InitializeParticle', 'Position Offset', f_expr('float3(0.0, 0.0, -420.0 * %s) * User.JetScale' % L))
fx_set(S, E, PS, 'InitializeParticle', 'Position Offset Coordinate Space', fx_enum(CS, 'ENiagaraCoordinateSpace::Local'))
fx_set(S, E, PS, 'ShapeLocation', 'Sphere Radius', f_expr('70.0 * User.JetScale'))
fx_remove_module(S, E, PS, 'AddVelocity')
# velocity: a 20 deg-ish cone around local -Z, rotated into world space (the emitter simulates in world space)
vel = ('mul(float4(normalize(float3((rand(2.0) - 1.0) * 0.35, (rand(2.0) - 1.0) * 0.35, -1.0)) * '
       '(350.0 + 500.0 * User.Thrust) * (1.0 + 0.5 * User.Boost) * (0.7 + 0.6 * rand(1.0)) * User.JetScale, 0.0), '
       'Engine.Owner.SystemLocalToWorldNoScale).xyz')
fx_setparams(S, E, PS, [('Particles.Velocity', T_VEC3, vel, None),
                        ('Particles.SpriteRotation', T_FLOAT, 'rand(360.0)', None)])
fx_set(S, E, PU, 'GravityForce', 'Gravity', fx_val(T_VEC3, {'x': 0, 'y': 0, 'z': 80}))
fx_set(S, E, PU, 'Drag', 'Drag', f_float(2.2))
# Particles.Initial.SpriteSize is not written by the Fountain stack ("hasn't been encountered yet"): keep our own copy
fx_setparams(S, E, PS, [('Particles.BaseSize', T_VEC2, 'Particles.SpriteSize', {'x': 100, 'y': 100})])
fx_setparams(S, E, PU, [('Particles.SpriteSize', T_VEC2,
                         'Particles.BaseSize * (0.4 + 1.6 * sqrt(Particles.NormalizedAge))', {'x': 100, 'y': 100})])
fx_renderer_props(S, E, 0, {'Material': {'refPath': '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Ball_01.MI_Ball_01'},
                            'SortMode': 'ViewDepth'})
log.append('Puffs: modules %s' % {s: fx_modules(S, E, s) for s in (EU, PS, PU)})

for l in log:
    print(l)
compile_request(S)  # read with as_check_compile.py in a later inbox call
print('saved', save_paths(['/Game/Assets/MyShip/Drivable/FX/NS_AirshipThruster']))
