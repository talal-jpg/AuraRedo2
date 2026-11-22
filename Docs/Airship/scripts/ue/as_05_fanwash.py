# as_05_fanwash.py - NS_AirshipFanWash: subtle comic air/steam wake behind each rear fan. Component at socket
# Turbine_*_Exhaust (rest rotation world-aligned): the wake blows along the component's local -X.
#   User.Thrust (0..1+, |fan thrust|), User.Boost (0..1), User.JetScale (size multiplier, 1)
#   Streaks: thin velocity-aligned white air lines (M_DefaultSprite_trans), world space
#   Wash:    faint steam puffs (MI_Ball_01 (validation 2026-11-22: MI_Popcorn_Puff is a mesh material, a square on a sprite)), world space
# Recreates the asset from scratch on every run (our own asset only).
AS_FX = {'name': 'NS_AirshipFanWash', 'recreate': True, 'emitters': [
    ('Streaks', '/Niagara/DefaultAssets/Templates/Emitters/Fountain.Fountain'),
    ('Wash', '/Niagara/DefaultAssets/Templates/Emitters/Fountain.Fountain')]}
import os, unreal, json
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_04a_fx_create.py')).read())
AS_FX = None
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
S = '/Game/Assets/MyShip/Drivable/FX/NS_AirshipFanWash.NS_AirshipFanWash'
fx_user_vars(S, [('Thrust', T_FLOAT, {'value': 1.0}, '|fan thrust| (AAirshipPawn FXThrustParam)'),
                 ('Boost', T_FLOAT, {'value': 0.0}, '0..1 boost (AAirshipPawn FXBoostParam)'),
                 ('JetScale', T_FLOAT, {'value': 1.0}, 'size multiplier')])
print('Streaks', fx_fountain_to(
    S, 'Streaks', '1.0 + 22.0 * User.Thrust + 14.0 * User.Boost', (0.3, 0.55), {'r': 1, 'g': 1, 'b': 1, 'a': 0.45},
    '10.0', '10.0', 'float3(-1.0, (rand(2.0) - 1.0) * 0.12, (rand(2.0) - 1.0) * 0.12)',
    '(500.0 + 1500.0 * User.Thrust) * (1.0 + 0.6 * User.Boost) * (0.8 + 0.4 * rand(1.0)) * User.JetScale', 0.0, 1.2,
    '/Game/Assets/Effects/Shared/M_DefaultSprite_trans.M_DefaultSprite_trans', growth=None, sort='None',
    alignment='VelocityAligned', shape_radius='100.0 * User.JetScale',
    size_vec_expr='float2(6.0 + 6.0 * rand(1.0), 120.0 + 220.0 * rand(1.0)) * User.JetScale'))
print('Wash', fx_fountain_to(
    S, 'Wash', '0.5 + 6.0 * User.Thrust + 6.0 * User.Boost', (0.8, 1.4), {'r': 0.95, 'g': 0.96, 'b': 1.0, 'a': 0.35},
    '70.0 * User.JetScale', '130.0 * User.JetScale', 'float3(-1.0, (rand(2.0) - 1.0) * 0.3, (rand(2.0) - 1.0) * 0.3)',
    '(350.0 + 900.0 * User.Thrust) * (1.0 + 0.5 * User.Boost) * (0.7 + 0.6 * rand(1.0)) * User.JetScale', 40.0, 2.0,
    '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Ball_01.MI_Ball_01',
    growth='0.5 + 1.7 * sqrt(Particles.NormalizedAge)', shape_radius='80.0 * User.JetScale'))
print('saved', save_paths(['/Game/Assets/MyShip/Drivable/FX/NS_AirshipFanWash']))
