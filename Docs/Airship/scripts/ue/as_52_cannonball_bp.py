# as_52_cannonball_bp.py - round 2 D2: BP_AirshipCannonball for the bigger, slower ball with health. Edits the Blueprint's
# class defaults (our own asset, created by as_03_physmat_cannonball.py; it is never created or deleted here), compiles,
# reads back and saves ONLY this asset.
#   BallMesh /Engine/BasicShapes/Sphere scale = 2 x Radius / the mesh's diameter (1.0 for the 1 m ball; was 0.56)
#   Radius 50 cm, GravityScale 0.6, SplashRadius 600 cm, SentinelHitRadius 100 cm, MaxLifeSeconds 10 s, BallMaxHealth 30
#   (gun units), ImpactFXScale 3 (was 2). Written explicitly even where they equal the new C++ defaults, because
#   as_03 writes Radius 28 / SplashRadius 450 / MaxLifeSeconds 8 explicitly (as_03_physmat_cannonball.py:79-81):
#   RUN THIS AFTER ANY as_03 RUN, or as_03 puts the small ball back.
# Needs the round-2 C++ (AAirshipCannonball::BallMaxHealth, GravityScale as a property): refuses to run without it.
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 52 Docs/Airship/scripts/ue/as_52_cannonball_bp.py 120
# Report: Saved/Airship/as_52_cannonball_bp.json
import json, os, traceback  # unreal = inbox namespace

BP_PATH = '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball'
PARENT = '/Script/Aura.AirshipCannonball'
SPHERE = '/Engine/BasicShapes/Sphere'
VALUES = [('Radius', 50.0), ('GravityScale', 0.6), ('SplashRadius', 600.0), ('SentinelHitRadius', 100.0),
          ('MaxLifeSeconds', 10.0), ('BallMaxHealth', 30.0), ('ImpactFXScale', 3.0)]
R = {'lines': [], 'before': {}, 'after': {}}
CNT = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def o(tag, msg):
    CNT[tag] += 1
    R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def pth(v):
    try:
        return v.get_path_name() if v is not None else None
    except Exception:  # noqa: BLE001
        return str(v)


def snapshot(cdo):
    d = {}
    for n, _ in VALUES:
        try:
            d[n] = round(float(cdo.get_editor_property(n)), 4)
        except Exception as e:  # noqa: BLE001
            d[n] = 'unreadable: %s' % e
    ball = cdo.get_editor_property('BallMesh')
    s = ball.get_editor_property('relative_scale3d')
    d['BallMesh.mesh'] = pth(ball.get_editor_property('static_mesh'))
    d['BallMesh.scale'] = [round(s.x, 4), round(s.y, 4), round(s.z, 4)]
    d['BallMesh.material'] = pth(ball.get_material(0))
    try:
        d['CollisionSphere.radius'] = round(cdo.get_editor_property('CollisionSphere').get_unscaled_sphere_radius(), 3)
    except Exception:  # noqa: BLE001
        d['CollisionSphere.radius'] = None
    d['ImpactFX'] = pth(cdo.get_editor_property('ImpactFX'))
    return d


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE is running: nothing changed')
        return
    parent = unreal.load_class(None, PARENT)
    if parent is None:
        o('FAIL', '%s not found (AuraEditor not built?)' % PARENT)
        return
    ncdo = unreal.get_default_object(parent)
    try:
        ncdo.get_editor_property('BallMaxHealth')
        ncdo.get_editor_property('GravityScale')
    except Exception:  # noqa: BLE001
        o('FAIL', 'AAirshipCannonball has no BallMaxHealth / GravityScale: the round-2 C++ is not built into this editor')
        return
    R['class_defaults'] = dict((n, round(float(ncdo.get_editor_property(n)), 4)) for n, _ in VALUES)
    o('INFO', 'C++ class defaults: %s' % R['class_defaults'])
    eal = unreal.EditorAssetLibrary
    if not eal.does_asset_exist(BP_PATH):
        o('FAIL', '%s missing: run as_03_physmat_cannonball.py first (this script never creates it)' % BP_PATH)
        return
    bp = eal.load_asset(BP_PATH)
    cur = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
    if pth(cur) != pth(parent):
        o('FAIL', '%s has parent %s, not %s: not ours, not touched' % (BP_PATH, pth(cur), PARENT))
        return
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    R['before'] = snapshot(cdo)
    o('INFO', 'before: %s' % json.dumps(R['before']))
    bp.modify()
    want = dict(VALUES)
    for n, v in VALUES:
        cdo.set_editor_property(n, v)
    sphere = unreal.load_asset(SPHERE)
    ball = cdo.get_editor_property('BallMesh')
    ball.modify()
    if pth(ball.get_editor_property('static_mesh')) != pth(sphere):
        ball.set_editor_property('static_mesh', sphere)
    # the engine sphere is 100 cm across; scale from its bounds so a different mesh still gives a ball of 2 x Radius
    bb = sphere.get_bounding_box()
    diam = max(bb.max.x - bb.min.x, bb.max.y - bb.min.y, bb.max.z - bb.min.z)
    sc = 2.0 * want['Radius'] / diam if diam > 1.0 else 1.0
    R['mesh_diameter_cm'] = round(diam, 3)
    ball.set_editor_property('relative_scale3d', unreal.Vector(sc, sc, sc))
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    st = bp.get_editor_property('status')
    o('PASS' if st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS) else 'FAIL',
      'BP_AirshipCannonball compiled: %s (%s)' % (st, ok))
    # read back after the compile (the CDO is rebuilt)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    R['after'] = snapshot(cdo)
    for n, v in VALUES:
        got = R['after'].get(n)
        o('PASS' if isinstance(got, float) and abs(got - v) < 1e-3 else 'FAIL', '%s = %s (want %s; was %s)' % (n, got, v, R['before'].get(n)))
    s3 = R['after']['BallMesh.scale']
    o('PASS' if all(abs(x - sc) < 1e-3 for x in s3) else 'FAIL', 'BallMesh scale %s (want %.3f = 2 x %.0f / %.1f cm; was %s), ball %.0f cm across'
      % (s3, sc, want['Radius'], diam, R['before'].get('BallMesh.scale'), sc * diam))
    o('INFO', 'BallMesh mesh %s material %s, ImpactFX %s' % (R['after']['BallMesh.mesh'], R['after']['BallMesh.material'], R['after']['ImpactFX']))
    cr = R['after'].get('CollisionSphere.radius')
    o('INFO', 'CollisionSphere unscaled radius on the CDO %s (the C++ constructor / BeginPlay sizes it from Radius)' % cr)
    if CNT['FAIL']:
        o('WARN', '%d FAIL: NOT saved' % CNT['FAIL'])
        return
    saved = unreal.EditorAssetLibrary.save_asset(BP_PATH, only_if_is_dirty=False)
    o('PASS' if saved else 'FAIL', 'saved %s (only this asset)' % BP_PATH)
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    o('INFO', 'dirty packages now (not saved): %s' % dirty)


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', traceback.format_exc())
R['counts'] = CNT
os.makedirs(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship'), exist_ok=True)
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_52_cannonball_bp.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))
