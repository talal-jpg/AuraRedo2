# as_57_pawn_defaults.py - round 2 D2/D6/D7: BP_AirshipPawn must not hide the new C++ defaults. The round-2 values live in
# C++ (AAirshipPawn: CannonballSpeed 7000, CannonSpawnForwardOffset 80, PilotSeatFallback = the new PilotSeat) and in
# Project Settings > Game > Airship (TurretClass, TurretMounts, ...); none of them is set on the Blueprint by as_21. This
# script compares the Blueprint's class defaults with the native class defaults and puts back the C++ value where the
# Blueprint overrides one (an override saved by hand in the editor would keep the old 12000 cm/s ball), reports
# CannonballClass, the turret project settings (TurretClass must load BP_AirshipTurret_C) and PilotSeatFallback against
# turret_dims.json. Saves BP_AirshipPawn ONLY if it changed something.
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 57 Docs/Airship/scripts/ue/as_57_pawn_defaults.py 120
# Report: Saved/Airship/as_57_pawn_defaults.json
import json, math, os, traceback  # unreal = inbox namespace

W = os.path.abspath(unreal.Paths.project_dir())
DIMS = os.path.join(W, 'SourceArt/Airship/turret_dims.json')
BP_PATH = '/Game/Assets/MyShip/Drivable/BP_AirshipPawn'
PARENT = '/Script/Aura.AirshipPawn'
BALL = '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball.BP_AirshipCannonball_C'
TURRET = '/Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret.BP_AirshipTurret_C'
PROPS = ['CannonballSpeed', 'CannonSpawnForwardOffset', 'PilotSeatFallback']
WANT = {'CannonballSpeed': 7000.0, 'CannonSpawnForwardOffset': 80.0}
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


def val(x):
    if isinstance(x, unreal.Vector):
        return [round(x.x, 3), round(x.y, 3), round(x.z, 3)]
    if isinstance(x, float):
        return round(x, 4)
    return x


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE is running: nothing changed')
        return
    parent = unreal.load_class(None, PARENT)
    if parent is None:
        o('FAIL', '%s not found' % PARENT)
        return
    eal = unreal.EditorAssetLibrary
    if not eal.does_asset_exist(BP_PATH):
        o('FAIL', '%s missing (as_21_blueprint.py)' % BP_PATH)
        return
    bp = eal.load_asset(BP_PATH)
    if pth(unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)) != pth(parent):
        o('FAIL', '%s parent is not %s: not touched' % (BP_PATH, PARENT))
        return
    ncdo = unreal.get_default_object(parent)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    changed = []
    R['values'] = {}
    for n in PROPS:
        nv, bv = ncdo.get_editor_property(n), cdo.get_editor_property(n)
        R['values'][n] = {'class': val(nv), 'blueprint': val(bv)}
        same = (nv == bv) if not isinstance(nv, float) else abs(nv - bv) < 1e-4
        if isinstance(nv, unreal.Vector):
            same = (nv - bv).length() < 1e-3
        if same:
            o('PASS', '%s: Blueprint = class default %s' % (n, val(nv)))
        else:
            if not changed:
                bp.modify()
            cdo.set_editor_property(n, nv)
            changed.append(n)
            o('WARN', '%s: Blueprint overrode %s -> reset to the class default %s' % (n, val(bv), val(nv)))
        if n in WANT:
            o('PASS' if abs(float(nv) - WANT[n]) < 1e-3 else 'FAIL', '%s class default %s (round 2 wants %s; core owns it)' % (n, val(nv), WANT[n]))
    try:
        with open(DIMS) as f:
            dims = json.load(f)
        ps = dims.get('pilot_seat_ue')
        if ps is not None:
            ps = [float(ps[k]) for k in ('x', 'y', 'z')] if isinstance(ps, dict) else [float(x) for x in ps][:3]
            fb = ncdo.get_editor_property('PilotSeatFallback')
            d = math.sqrt((fb.x - ps[0]) ** 2 + (fb.y - ps[1]) ** 2 + (fb.z - ps[2]) ** 2)
            o('PASS' if d <= 2.0 else 'FAIL', 'PilotSeatFallback %s vs turret_dims.json pilot_seat_ue %s: %.1f cm' % (val(fb), ps, d))
    except Exception as e:  # noqa: BLE001
        o('WARN', 'turret_dims.json pilot_seat_ue not compared: %s' % e)
    cb = cdo.get_editor_property('CannonballClass')
    o('PASS' if pth(cb) == BALL else 'WARN', 'CannonballClass %s (want %s)' % (pth(cb), BALL))
    # project settings (read only: the C++ constructor fills them; DefaultGame.ini has no override)
    st = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.AirshipSettings'))
    tc = st.get_editor_property('TurretClass')
    R['settings'] = {'TurretClass': str(tc), 'bSpawnTurrets': st.get_editor_property('bSpawnTurrets')}
    loaded = None
    try:
        loaded = unreal.load_class(None, TURRET)
    except Exception:  # noqa: BLE001
        loaded = None
    o('PASS' if loaded is not None and TURRET.split('.')[0] in str(tc) else 'FAIL',
      'TurretClass %s, BP_AirshipTurret_C loads: %s' % (tc, pth(loaded)))
    try:
        mounts = st.get_editor_property('TurretMounts')
        R['settings']['TurretMounts'] = [{'loc': val(m.get_editor_property('location')), 'yaw': [m.get_editor_property('yaw_min_deg'), m.get_editor_property('yaw_max_deg')],
                                          'pitch': [m.get_editor_property('pitch_min_deg'), m.get_editor_property('pitch_max_deg')]} for m in mounts]
        o('INFO', 'TurretMounts %s, bSpawnTurrets %s' % (R['settings']['TurretMounts'], R['settings']['bSpawnTurrets']))
    except Exception as e:  # noqa: BLE001
        o('WARN', 'TurretMounts not readable: %s' % e)
    if not changed:
        o('INFO', 'nothing changed: BP_AirshipPawn not saved')
        return
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
    left = [n for n in changed if val(cdo.get_editor_property(n)) != val(ncdo.get_editor_property(n))]
    o('PASS' if not left else 'FAIL', 'after compile (%s): overrides left %s' % (ok, left))
    if left:
        return
    saved = eal.save_asset(BP_PATH, only_if_is_dirty=False)
    o('PASS' if saved else 'FAIL', 'saved %s (reset %s)' % (BP_PATH, changed))


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', traceback.format_exc())
R['counts'] = CNT
os.makedirs(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship'), exist_ok=True)
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_57_pawn_defaults.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))
