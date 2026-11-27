# as_55_turret_bp.py - round 2 D6: /Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret, the class every ship spawns at
# its two forward mounts (UAirshipSettings::TurretClass points here). Parent /Script/Aura.AirshipTurret; created or reused,
# never deleted (the as_21 way: the native components are edited on the generated class's CDO, then compiled):
#   BaseMesh SM_AirshipTurret_Base (yaw part), GunMesh SM_AirshipTurret_Gun (pitch part) at (0, 0, PivotHeight),
#   Muzzle at (MuzzleForward, 0, 0); PivotHeight / MuzzleForward from SourceArt/Airship/turret_dims.json
#   (pivot_height_cm, muzzle_forward_cm; the C++ defaults 150 / 180 stay when the file has none);
#   MuzzleFXComponent NS_AirshipTurretMuzzle, DestroyedFXComponent NS_AirshipTurretFire at relative scale 0.3,
#   TracerSystem NS_AirshipTurretTracer, TracerDataChannel NDC_GunShootHit (the gun's channel: copies are written to it with
#   SystemToSpawn), DestroyedExplosionFX NS_FireExplosion;
#   HitBox sized to the imported base mesh: half width = the footprint's half size + 10 cm (at least 60), half height =
#   (PivotHeight + 40) / 2 (at least 95, covering the gun's receiver), standing on the deck (centre z = half height).
# Needs the built C++ (AAirshipTurret), as_53 (meshes) and as_54 (FX). Saves only this Blueprint.
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 55 Docs/Airship/scripts/ue/as_55_turret_bp.py 300
# Report: Saved/Airship/as_55_turret_bp.json
import json, math, os, traceback  # unreal = inbox namespace

W = os.path.abspath(unreal.Paths.project_dir())
DIMS = os.path.join(W, 'SourceArt/Airship/turret_dims.json')
D = '/Game/Assets/MyShip/Drivable'
BP_PATH = D + '/Turret/BP_AirshipTurret'
PARENT = '/Script/Aura.AirshipTurret'
A = {'base': D + '/Turret/SM_AirshipTurret_Base', 'gun': D + '/Turret/SM_AirshipTurret_Gun',
     'muzzle': D + '/FX/NS_AirshipTurretMuzzle', 'fire': D + '/FX/NS_AirshipTurretFire', 'tracer': D + '/FX/NS_AirshipTurretTracer',
     'ndc': '/Game/Assets/Effects/AppreiticeFx/GunShootHit/NDC_GunShootHit',
     'explosion': '/Game/Assets/Effects/Projectiles/FireExplosion/NS_FireExplosion'}
FIRE_SCALE = 0.3
R = {'lines': []}
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


def comp(cdo, name):
    try:
        c = cdo.get_editor_property(name)
    except Exception as e:  # noqa: BLE001
        o('FAIL', 'AAirshipTurret has no component property %s (%s)' % (name, e))
        return None
    if c is None:
        o('FAIL', 'component %s is null on the CDO' % name)
    return c


def sp(obj, name, value, label):
    try:
        obj.set_editor_property(name, value)
        got = obj.get_editor_property(name)
        if hasattr(value, 'get_path_name'):
            good = pth(got) == pth(value)
        elif isinstance(value, float):
            good = abs(float(got) - value) < 1e-3
        else:
            good = got == value
        o('PASS' if good else 'FAIL', '%s.%s = %s' % (label, name, pth(got) if hasattr(got, 'get_path_name') else got))
        return good
    except Exception as e:  # noqa: BLE001
        o('FAIL', '%s.%s: %s' % (label, name, e))
        return False


def vec(v):
    return [round(v.x, 2), round(v.y, 2), round(v.z, 2)]


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE is running: nothing changed')
        return
    parent = unreal.load_class(None, PARENT)
    if parent is None:
        o('FAIL', '%s not found (AuraEditor not built with the round-2 C++?)' % PARENT)
        return
    eal = unreal.EditorAssetLibrary
    v = {}
    for k, p in A.items():
        v[k] = eal.load_asset(p) if eal.does_asset_exist(p) else None
        if v[k] is None:
            o('FAIL', 'missing %s (%s: run %s first)' % (p, k, 'as_53' if k in ('base', 'gun') else 'as_54' if k in ('muzzle', 'fire', 'tracer') else '?'))
    if any(x is None for x in v.values()):
        return
    try:
        with open(DIMS) as f:
            dims = json.load(f)
    except Exception as e:  # noqa: BLE001
        dims = {}
        o('WARN', 'turret_dims.json not readable (%s): PivotHeight / MuzzleForward keep the C++ defaults' % e)
    R['dims'] = dims
    ncdo = unreal.get_default_object(parent)
    pivot = dims.get('pivot_height_cm') if isinstance(dims.get('pivot_height_cm'), (int, float)) else None
    muzzle = dims.get('muzzle_forward_cm') if isinstance(dims.get('muzzle_forward_cm'), (int, float)) else None
    pivot = float(pivot) if pivot is not None else float(ncdo.get_editor_property('PivotHeight'))
    muzzle = float(muzzle) if muzzle is not None else float(ncdo.get_editor_property('MuzzleForward'))
    o('INFO', 'PivotHeight %.1f cm, MuzzleForward %.1f cm (%s)' % (pivot, muzzle, 'turret_dims.json' if dims else 'C++ defaults'))
    bb = v['base'].get_bounding_box()
    half = max(abs(bb.min.x), abs(bb.max.x), abs(bb.min.y), abs(bb.max.y))
    ext_xy = max(60.0, math.ceil(half + 10.0))
    ext_z = max(95.0, math.ceil((pivot + 40.0) / 2.0))
    R['hitbox'] = {'base_half_footprint': round(half, 2), 'extent': [ext_xy, ext_xy, ext_z], 'centre_z': ext_z}
    o('INFO', 'HitBox from the base mesh (half footprint %.1f cm) and the pivot: extent (%.0f, %.0f, %.0f) at z %.0f' % (half, ext_xy, ext_xy, ext_z, ext_z))

    if eal.does_asset_exist(BP_PATH):
        bp = eal.load_asset(BP_PATH)
        cur = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
        if pth(cur) != pth(parent):
            o('FAIL', 'existing %s has parent %s: not ours, not touched' % (BP_PATH, pth(cur)))
            return
        o('INFO', 'REUSING %s' % BP_PATH)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    else:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(BP_PATH, parent)
        if bp is None:
            o('FAIL', 'could not create %s' % BP_PATH)
            return
        o('INFO', 'CREATED %s (parent %s)' % (BP_PATH, PARENT))
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    bp.modify()
    base, gun, mz, mfx, dfx, box = (comp(cdo, n) for n in ('BaseMesh', 'GunMesh', 'Muzzle', 'MuzzleFXComponent', 'DestroyedFXComponent', 'HitBox'))
    if None in (base, gun, mz, mfx, dfx, box):
        return
    for c in (base, gun, mz, mfx, dfx, box):
        c.modify()
    sp(base, 'static_mesh', v['base'], 'BaseMesh')
    sp(gun, 'static_mesh', v['gun'], 'GunMesh')
    # the C++ BeginPlay places GunMesh / Muzzle from PivotHeight / MuzzleForward (BP values win); set here too so the
    # Blueprint viewport shows the assembled turret
    gun.set_editor_property('relative_location', unreal.Vector(0.0, 0.0, pivot))
    mz.set_editor_property('relative_location', unreal.Vector(muzzle, 0.0, 0.0))
    sp(mfx, 'asset', v['muzzle'], 'MuzzleFXComponent')
    sp(dfx, 'asset', v['fire'], 'DestroyedFXComponent')
    dfx.set_editor_property('relative_scale3d', unreal.Vector(FIRE_SCALE, FIRE_SCALE, FIRE_SCALE))
    box.set_editor_property('box_extent', unreal.Vector(ext_xy, ext_xy, ext_z))
    box.set_editor_property('relative_location', unreal.Vector(0.0, 0.0, ext_z))
    sp(cdo, 'PivotHeight', pivot, 'CDO')
    sp(cdo, 'MuzzleForward', muzzle, 'CDO')
    sp(cdo, 'TracerSystem', v['tracer'], 'CDO')
    sp(cdo, 'TracerDataChannel', v['ndc'], 'CDO')
    sp(cdo, 'DestroyedExplosionFX', v['explosion'], 'CDO')
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    st = bp.get_editor_property('status')
    o('PASS' if st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS) else 'FAIL',
      'BP_AirshipTurret compiled: %s (%s)' % (st, ok))
    # read back after the compile (the CDO is rebuilt)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    g = lambda n: cdo.get_editor_property(n)  # noqa: E731
    after = {'BaseMesh': pth(g('BaseMesh').get_editor_property('static_mesh')), 'GunMesh': pth(g('GunMesh').get_editor_property('static_mesh')),
             'GunMesh.loc': vec(g('GunMesh').get_editor_property('relative_location')),
             'Muzzle.loc': vec(g('Muzzle').get_editor_property('relative_location')),
             'MuzzleFX': pth(g('MuzzleFXComponent').get_editor_property('asset')),
             'MuzzleFX.auto_activate': bool(g('MuzzleFXComponent').get_editor_property('auto_activate')),
             'DestroyedFX': pth(g('DestroyedFXComponent').get_editor_property('asset')),
             'DestroyedFX.scale': vec(g('DestroyedFXComponent').get_editor_property('relative_scale3d')),
             'DestroyedFX.auto_activate': bool(g('DestroyedFXComponent').get_editor_property('auto_activate')),
             'HitBox.extent': vec(g('HitBox').get_editor_property('box_extent')), 'HitBox.loc': vec(g('HitBox').get_editor_property('relative_location')),
             'HitBox.collision': str(g('HitBox').get_collision_enabled()),
             'PivotHeight': float(g('PivotHeight')), 'MuzzleForward': float(g('MuzzleForward')),
             'TracerSystem': pth(g('TracerSystem')), 'TracerDataChannel': pth(g('TracerDataChannel')),
             'DestroyedExplosionFX': pth(g('DestroyedExplosionFX'))}
    R['after'] = after
    good = (after['BaseMesh'] == pth(v['base']) and after['GunMesh'] == pth(v['gun']) and after['MuzzleFX'] == pth(v['muzzle'])
            and after['DestroyedFX'] == pth(v['fire']) and after['TracerSystem'] == pth(v['tracer'])
            and after['TracerDataChannel'] == pth(v['ndc']) and after['DestroyedExplosionFX'] == pth(v['explosion'])
            and abs(after['PivotHeight'] - pivot) < 1e-3 and abs(after['MuzzleForward'] - muzzle) < 1e-3
            and all(abs(x - FIRE_SCALE) < 1e-4 for x in after['DestroyedFX.scale'])
            and abs(after['HitBox.extent'][0] - ext_xy) < 0.01 and abs(after['HitBox.extent'][2] - ext_z) < 0.01)
    o('PASS' if good else 'FAIL', 'after compile: %s' % json.dumps(after))
    o('PASS' if not after['MuzzleFX.auto_activate'] and not after['DestroyedFX.auto_activate'] else 'WARN',
      'muzzle / destroyed FX auto activate %s / %s (want off: the C++ activates them)' % (after['MuzzleFX.auto_activate'], after['DestroyedFX.auto_activate']))
    o('INFO', 'HitBox collision %s (C++: QueryOnly, WorldDynamic, blocks Visibility)' % after['HitBox.collision'])
    if CNT['FAIL']:
        o('WARN', '%d FAIL: NOT saved' % CNT['FAIL'])
        return
    saved = eal.save_asset(BP_PATH, only_if_is_dirty=False)
    o('PASS' if saved else 'FAIL', 'saved %s (only this asset)' % BP_PATH)
    # the project setting that spawns it (read only; the C++ default points here)
    try:
        st = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.AirshipSettings'))
        tc = st.get_editor_property('TurretClass')
        o('INFO', 'UAirshipSettings.TurretClass = %s' % tc)
    except Exception as e:  # noqa: BLE001
        o('WARN', 'TurretClass not readable: %s' % e)
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    o('INFO', 'dirty packages now (not saved): %s' % dirty)


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', traceback.format_exc())
R['counts'] = CNT
os.makedirs(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship'), exist_ok=True)
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_55_turret_bp.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))
