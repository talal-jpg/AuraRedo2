# as_21_blueprint.py - BP_AirshipPawn (parent /Script/Aura.AirshipPawn) per CPP_NOTES.md section 2, the Burrower bw_06 way:
# create (or reuse, never delete) the Blueprint, edit the native components on its CDO, compile, save ONLY this asset.
# Run: Docs/Airship/scripts/harness/inbox.sh 21 Docs/Airship/scripts/ue/as_21_blueprint.py 300
#   Mesh: SK_Airship (its physics asset PA_Airship is checked), Animation Blueprint mode, AnimClass ABP_Airship_C, relative
#         transform identity under HullCollision (C++ default kept).
#   HullCollision: the C++ default /Game/Assets/MyShip/SM_Airship is checked: 8 convex hulls (UCX) as its simple collision.
#   ThrusterFX_FL/FR/RL/RR = NS_AirshipThruster, TurbineFX_L/R = NS_AirshipFanWash (sockets from C++).
#   CDO: MuzzleFX NS_AirshipMuzzle, DeathExplosionFX NS_FireExplosion, DeathFireFX NS_Fire, CannonballClass
#        BP_AirshipCannonball_C, HullPhysicalMaterial PM_AirshipHull. Input assets: unset (Project Settings defaults).
# Writes Saved/Airship/as_21_blueprint.json.
import json, os, traceback  # unreal = inbox namespace

D = '/Game/Assets/MyShip/Drivable'
BP_PATH = D + '/BP_AirshipPawn'
PARENT = '/Script/Aura.AirshipPawn'
A = {
    'sk': D + '/SK_Airship', 'pa': D + '/PA_Airship', 'abp': D + '/ABP_Airship.ABP_Airship_C',
    'hull': '/Game/Assets/MyShip/SM_Airship',
    'thruster': D + '/FX/NS_AirshipThruster', 'fanwash': D + '/FX/NS_AirshipFanWash', 'muzzle': D + '/FX/NS_AirshipMuzzle',
    'explosion': '/Game/Assets/Effects/Projectiles/FireExplosion/NS_FireExplosion', 'fire': '/Game/Assets/Effects/Fire/NS_Fire',
    'ball': D + '/BP_AirshipCannonball.BP_AirshipCannonball_C', 'pm': D + '/Physics/PM_AirshipHull',
}
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


def sp(obj, name, value, label):
    try:
        obj.set_editor_property(name, value)
        got = obj.get_editor_property(name)
        good = (pth(got) == pth(value)) if hasattr(value, 'get_path_name') else (got == value)
        o('PASS' if good else 'FAIL', '%s.%s = %s' % (label, name, pth(got) if hasattr(got, 'get_path_name') else got))
        return good
    except Exception as e:  # noqa: BLE001
        o('FAIL', '%s.%s: %s' % (label, name, e))
        return False


def load(p, cls=None):
    if p.endswith('_C'):
        return unreal.load_class(None, p)
    a = unreal.EditorAssetLibrary.load_asset(p)
    if a is None or (cls is not None and not isinstance(a, cls)):
        o('FAIL', 'missing asset %s (%s)' % (p, a))
        return None
    return a


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE is running: nothing changed')
        return
    parent = unreal.load_class(None, PARENT)
    if parent is None:
        o('FAIL', '%s not found (AuraEditor not built?)' % PARENT)
        return
    v = dict((k, load(p)) for k, p in A.items())
    if any(x is None for x in v.values()):
        o('FAIL', 'missing: %s' % [k for k, x in v.items() if x is None])
        return
    # SK_Airship's physics asset
    pa = v['sk'].get_editor_property('physics_asset')
    o('PASS' if pth(pa) == pth(v['pa']) else 'WARN', 'SK_Airship physics asset = %s (want PA_Airship)' % pth(pa))
    # SM_Airship simple collision: 8 convex hulls
    try:
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        n_cvx = sms.get_convex_collision_count(v['hull'])
        n_box = sms.get_simple_collision_count(v['hull'])
        R['hull_convex'] = n_cvx
        o('PASS' if n_cvx == 8 else 'FAIL', 'SM_Airship simple collision: %d convex hulls (UCX, want 8), %d simple shapes in all'
          % (n_cvx, n_box))
        ctf = v['hull'].get_editor_property('body_setup').get_editor_property('collision_trace_flag')
        o('INFO', 'SM_Airship collision complexity %s' % ctf)
    except Exception as e:  # noqa: BLE001
        o('WARN', 'convex count unreadable: %s' % e)

    bp = None
    if unreal.EditorAssetLibrary.does_asset_exist(BP_PATH):
        bp = unreal.EditorAssetLibrary.load_asset(BP_PATH)
        cur = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
        if pth(cur) != pth(parent):
            o('FAIL', 'existing BP_AirshipPawn has parent %s' % pth(cur))
            return
        o('INFO', 'REUSING %s' % BP_PATH)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    else:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(BP_PATH, parent)
        if bp is None:
            o('FAIL', 'could not create %s' % BP_PATH)
            return
        o('INFO', 'CREATED %s (parent %s)' % (BP_PATH, PARENT))
    gen = unreal.BlueprintEditorLibrary.generated_class(bp)
    cdo = unreal.get_default_object(gen)
    bp.modify()
    # Mesh
    mesh = cdo.get_editor_property('Mesh')
    mesh.modify()
    if not sp(mesh, 'skeletal_mesh_asset', v['sk'], 'Mesh'):
        mesh.set_skeletal_mesh_asset(v['sk'])
    sp(mesh, 'animation_mode', unreal.AnimationMode.ANIMATION_BLUEPRINT, 'Mesh')
    sp(mesh, 'anim_class', v['abp'], 'Mesh')
    rl, rr, rs = mesh.get_editor_property('relative_location'), mesh.get_editor_property('relative_rotation'), mesh.get_editor_property('relative_scale3d')
    ident = rl.length() < 0.01 and abs(rr.pitch) + abs(rr.yaw) + abs(rr.roll) < 0.01 and abs(rs.x - 1) + abs(rs.y - 1) + abs(rs.z - 1) < 1e-4
    o('PASS' if ident else 'FAIL', 'Mesh relative transform identity under HullCollision (%s %s %s)' % (rl, rr, rs))
    o('INFO', 'Mesh attach parent %s socket %s' % (pth(mesh.get_attach_parent()), mesh.get_attach_socket_name()))
    # Hull
    hull = cdo.get_editor_property('HullCollision')
    o('PASS' if pth(hull.get_editor_property('static_mesh')) == pth(v['hull']) else 'FAIL',
      'HullCollision static mesh = %s' % pth(hull.get_editor_property('static_mesh')))
    # Niagara components
    for comp, ns in (('ThrusterFX_FL', 'thruster'), ('ThrusterFX_FR', 'thruster'), ('ThrusterFX_RL', 'thruster'),
                     ('ThrusterFX_RR', 'thruster'), ('TurbineFX_L', 'fanwash'), ('TurbineFX_R', 'fanwash')):
        c = cdo.get_editor_property(comp)
        c.modify()
        if not sp(c, 'asset', v[ns], comp):
            c.set_asset(v[ns])
        o('INFO', '%s attached to %s socket %s' % (comp, pth(c.get_attach_parent()), c.get_attach_socket_name()))
    # class defaults
    sp(cdo, 'MuzzleFX', v['muzzle'], 'CDO')
    sp(cdo, 'DeathExplosionFX', v['explosion'], 'CDO')
    sp(cdo, 'DeathFireFX', v['fire'], 'CDO')
    sp(cdo, 'CannonballClass', v['ball'], 'CDO')
    sp(cdo, 'HullPhysicalMaterial', v['pm'], 'CDO')
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    st = bp.get_editor_property('status')
    o('PASS' if st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS) else 'FAIL',
      'BP_AirshipPawn compiled: %s' % st)
    # re-read after compile (the CDO is rebuilt)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    m = cdo.get_editor_property('Mesh')
    R['after'] = {'mesh': pth(m.get_editor_property('skeletal_mesh_asset')), 'anim_class': pth(m.get_editor_property('anim_class')),
                  'fx': dict((c, pth(cdo.get_editor_property(c).get_editor_property('asset'))) for c in (
                      'ThrusterFX_FL', 'ThrusterFX_FR', 'ThrusterFX_RL', 'ThrusterFX_RR', 'TurbineFX_L', 'TurbineFX_R')),
                  'cdo': dict((k, pth(cdo.get_editor_property(k))) for k in (
                      'MuzzleFX', 'DeathExplosionFX', 'DeathFireFX', 'CannonballClass', 'HullPhysicalMaterial')),
                  'CannonElevMaxDeg': cdo.get_editor_property('CannonElevMaxDeg')}
    good = (R['after']['mesh'] == pth(v['sk']) and R['after']['anim_class'] == pth(v['abp']) and
            all(x is not None for x in R['after']['fx'].values()) and all(x is not None for x in R['after']['cdo'].values()))
    o('PASS' if good else 'FAIL', 'after compile: %s' % json.dumps(R['after']))
    # fix round 2: 8.5 (the barrel meets its carriage at 8.75; the anim instance eases the elevation in, CannonElevSettleRate 8)
    o('PASS' if abs(R['after']['CannonElevMaxDeg'] - 8.5) < 1e-4 else 'FAIL',
      'CannonElevMaxDeg (C++ default, fix round 2) = %s (want 8.5)' % R['after']['CannonElevMaxDeg'])
    abp_cdo = unreal.get_default_object(v['abp'])
    o('PASS' if abs(abp_cdo.get_editor_property('CannonElevMaxDeg') - 8.5) < 1e-4 else 'FAIL',
      'ABP_Airship CannonElevMaxDeg = %s (want 8.5, = the pawn)' % abp_cdo.get_editor_property('CannonElevMaxDeg'))
    o('PASS' if abs(abp_cdo.get_editor_property('CannonElevSettleRate') - 8.0) < 1e-4 else 'FAIL',
      'ABP_Airship CannonElevSettleRate = %s (want 8)' % abp_cdo.get_editor_property('CannonElevSettleRate'))
    saved = unreal.EditorAssetLibrary.save_asset(BP_PATH, only_if_is_dirty=False)
    o('PASS' if saved else 'FAIL', 'saved %s (only this asset)' % BP_PATH)
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    o('INFO', 'dirty packages now (not saved): %s' % dirty)


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', traceback.format_exc())
R['counts'] = CNT
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_21_blueprint.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))
