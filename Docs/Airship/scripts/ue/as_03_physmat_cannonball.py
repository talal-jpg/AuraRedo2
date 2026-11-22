# as_03_physmat_cannonball.py - creates (re-runnable, reuses existing assets):
#   /Game/Assets/MyShip/Drivable/Physics/PM_AirshipHull          Friction 0.2, Restitution 0.08, restitution combine Min (override)
#        (validation session 2026-11-22, as_42; was 0.35 Max: the hull bounced 12 m at a 68 m/s crash)
#   /Game/Assets/MyShip/Drivable/Materials/M_AirshipCannonball   dark iron, lit (base 0.02, metallic 0.5, roughness 0.5)
#   /Game/Assets/MyShip/Drivable/BP_AirshipCannonball            parent /Script/Aura.AirshipCannonball:
#        BallMesh = /Engine/BasicShapes/Sphere (100 cm) scaled 0.56 -> 56 cm, M_AirshipCannonball, no collision (C++)
#        TrailFX = AS_TRAIL_FX, ImpactFX = NS_FireExplosion (ImpactFXScale AS_IMPACT_SCALE), Radius 28, SplashRadius 450,
#        MaxLifeSeconds 8.
# Inherited native components are edited on the generated class's CDO (Burrower bw_06 pattern), then compiled and saved.
import unreal

AS_ROOT = '/Game/Assets/MyShip/Drivable'
AS_TRAIL_FX = globals().get('AS_TRAIL_FX') or '/Game/Assets/Effects/Combat/Trail/NS_CombatTrail'
AS_IMPACT_FX = '/Game/Assets/Effects/Projectiles/FireExplosion/NS_FireExplosion'
AS_IMPACT_SCALE = 2.0
_eal = unreal.EditorAssetLibrary
_at = unreal.AssetToolsHelpers.get_asset_tools()
_mel = unreal.MaterialEditingLibrary


def _as03_physmat(rep):
    p = AS_ROOT + '/Physics/PM_AirshipHull'
    pm = _eal.load_asset(p) if _eal.does_asset_exist(p) else _at.create_asset('PM_AirshipHull', AS_ROOT + '/Physics',
                                                                               unreal.PhysicalMaterial, unreal.PhysicalMaterialFactoryNew())
    pm.set_editor_property('friction', 0.2)
    pm.set_editor_property('restitution', 0.08)
    pm.set_editor_property('restitution_combine_mode', unreal.FrictionCombineMode.MIN)
    pm.set_editor_property('override_restitution_combine_mode', True)
    rep.append('PM_AirshipHull friction=%.2f restitution=%.2f restitution_combine=%s override=%s friction_combine=%s override=%s' % (
        pm.get_editor_property('friction'), pm.get_editor_property('restitution'), pm.get_editor_property('restitution_combine_mode'),
        pm.get_editor_property('override_restitution_combine_mode'), pm.get_editor_property('friction_combine_mode'),
        pm.get_editor_property('override_friction_combine_mode')))
    return p


def _as03_ball_material(rep):
    p = AS_ROOT + '/Materials/M_AirshipCannonball'
    if _eal.does_asset_exist(p):
        rep.append('reusing ' + p)
        return p
    m = _at.create_asset('M_AirshipCannonball', AS_ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    c = _mel.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -400, 0)
    c.set_editor_property('constant', unreal.LinearColor(0.02, 0.02, 0.024, 1.0))
    met = _mel.create_material_expression(m, unreal.MaterialExpressionConstant, -400, 200)
    met.set_editor_property('r', 0.5)
    rough = _mel.create_material_expression(m, unreal.MaterialExpressionConstant, -400, 300)
    rough.set_editor_property('r', 0.5)
    _mel.connect_material_property(c, '', unreal.MaterialProperty.MP_BASE_COLOR)
    _mel.connect_material_property(met, '', unreal.MaterialProperty.MP_METALLIC)
    _mel.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    _mel.recompile_material(m)
    rep.append('created %s (expressions %d)' % (p, _mel.get_num_material_expressions(m)))
    return p


def _as03_bp(rep, mat_path):
    p = AS_ROOT + '/BP_AirshipCannonball'
    parent = unreal.load_class(None, '/Script/Aura.AirshipCannonball')
    if parent is None:
        raise RuntimeError('/Script/Aura.AirshipCannonball not found (C++ not built?)')
    if _eal.does_asset_exist(p):
        bp = _eal.load_asset(p)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        rep.append('reusing ' + p)
    else:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(p, parent)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        rep.append('created %s parent %s' % (p, unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp).get_path_name()))
    cdo = unreal.get_default_object(bp.generated_class())
    ball = cdo.get_editor_property('BallMesh')
    ball.set_editor_property('static_mesh', unreal.load_asset('/Engine/BasicShapes/Sphere'))
    ball.set_editor_property('relative_scale3d', unreal.Vector(0.56, 0.56, 0.56))
    ball.set_material(0, unreal.load_asset(mat_path))
    ball.set_editor_property('cast_shadow', True)
    trail = cdo.get_editor_property('TrailFX')
    trail.set_editor_property('asset', unreal.load_asset(AS_TRAIL_FX))
    cdo.set_editor_property('ImpactFX', unreal.load_asset(AS_IMPACT_FX))
    cdo.set_editor_property('ImpactFXScale', AS_IMPACT_SCALE)
    cdo.set_editor_property('Radius', 28.0)
    cdo.set_editor_property('SplashRadius', 450.0)
    cdo.set_editor_property('MaxLifeSeconds', 8.0)
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    rep.append('compile -> %s' % ok)
    return p, bp


def _as03_read(bp):
    cdo = unreal.get_default_object(bp.generated_class())
    ball = cdo.get_editor_property('BallMesh')
    trail = cdo.get_editor_property('TrailFX')
    sph = cdo.get_editor_property('CollisionSphere')
    m = ball.get_material(0)
    return ['BP_AirshipCannonball CDO: BallMesh mesh=%s scale=%s mat=%s collision=%s | TrailFX=%s | ImpactFX=%s scale=%.2f | '
            'Radius=%.1f SplashRadius=%.1f MaxLifeSeconds=%.1f | CollisionSphere r=%.1f' % (
                ball.get_editor_property('static_mesh').get_path_name(), ball.get_editor_property('relative_scale3d'),
                m.get_path_name() if m else None, ball.get_collision_enabled(),
                trail.get_editor_property('asset').get_path_name() if trail.get_editor_property('asset') else None,
                cdo.get_editor_property('ImpactFX').get_path_name() if cdo.get_editor_property('ImpactFX') else None,
                cdo.get_editor_property('ImpactFXScale'), cdo.get_editor_property('Radius'), cdo.get_editor_property('SplashRadius'),
                cdo.get_editor_property('MaxLifeSeconds'), sph.get_unscaled_sphere_radius())]


def as03_run():
    rep = []
    pm = _as03_physmat(rep)
    mp = _as03_ball_material(rep)
    bpp, bp = _as03_bp(rep, mp)
    rep += _as03_read(bp)
    for p in (pm, mp, bpp):
        rep.append('saved %s %s' % (p, _eal.save_asset(p, only_if_is_dirty=False)))
    return rep


for l in as03_run():
    print(l)
