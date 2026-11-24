# as_56_reimport_airship.py - round 2 D7: re-imports SK_Airship from the new SourceArt/Airship/SK_Airship.fbx (wheel at
# character size, five deck pieces removed, wider cannon bore, repacked props atlas UVs) OVER the existing asset, keeping
# its skeleton SKEL_Airship, so CR_Airship / ABP_Airship / A_Airship_TestSweep keep working. Wrapper around as_10_import.py
# (AS10_EXISTING = 'reimport'), run unedited except for three checked text patches applied in memory before the exec:
#   1. import_mesh() passes the existing SKEL_Airship as the import skeleton. as_10 passes None, and the FBX importer then
#      makes a NEW "<mesh>_Skeleton" on a re-import too (FbxSkeletalMeshImport.cpp: the LOD 0 block creates one whenever
#      ImportOptions->SkeletonForAnimation is null, after RestoreExistingSkelMeshData has put the old one back).
#   2. update_skeleton_reference_pose True: Helm_Wheel / PilotSeat moved; the skeleton's reference pose follows the mesh
#      (same bones, same hierarchy, so the bone merge needs no dialog).
#   3. the triangle check expects the new FBX's count (rig/checks/verify/fbx_verify.json total_tris, from verify_all.sh)
#      instead of the old 104730.
# Each patch must match exactly once, else nothing runs. Then (as_56's own checks): 118 bones (as_10), no new Skeleton
# asset, SK_Airship still uses SKEL_Airship and PA_Airship, PA_Airship untouched (its .uasset bytes unchanged, not dirty,
# not saved: PA is NOT rebuilt here), Helm_Wheel / PilotSeat rest positions = turret_dims.json (helm_wheel_ue,
# pilot_seat_ue, +-2 cm), and it prints the PilotSeat rest position for AAirshipPawn::PilotSeatFallback.
# as_10 saves SK_Airship + SKEL_Airship only when it has no FAIL. Editors of SK / SKEL / CR / ABP / PA are closed first
# (rebuilding or reimporting under an open editor crashed UE on 11-22). Afterwards: as_09 (headless Blender) -> as_12_reuse
# -> as_13_cr_eval (CR_Airship rebuilt in place for the moved wheel), as the spec's editor steps say.
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 56 Docs/Airship/scripts/ue/as_56_reimport_airship.py 900
# Report: Saved/Airship/as_56_reimport_airship.json (as_10's own report: Saved/Airship/as_10_import.json)
import hashlib, json, math, os, traceback  # unreal = inbox namespace

AS56_W = os.path.abspath(unreal.Paths.project_dir())
AS56_AS10 = os.path.join(AS56_W, 'Docs/Airship/scripts/ue/as_10_import.py')
AS56_FBX = os.path.join(AS56_W, 'SourceArt/Airship/SK_Airship.fbx')
AS56_RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
AS56_RIG_FBX = AS56_RIG + '/export/SK_Airship.fbx'
AS56_VERIFY = AS56_RIG + '/checks/verify/fbx_verify.json'
AS56_DIMS = os.path.join(AS56_W, 'SourceArt/Airship/turret_dims.json')
AS56_FOLDER = '/Game/Assets/MyShip/Drivable'
AS56_SK, AS56_SKEL, AS56_PA = AS56_FOLDER + '/SK_Airship', AS56_FOLDER + '/SKEL_Airship', AS56_FOLDER + '/PA_Airship'
AS56_EDITED = [AS56_SK, AS56_SKEL, AS56_PA, AS56_FOLDER + '/CR_Airship', AS56_FOLDER + '/ABP_Airship']
AS56_R = {'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}}


def _o56(tag, msg):
    AS56_R['counts'][tag] = AS56_R['counts'].get(tag, 0) + 1
    AS56_R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def _sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _pkg_file(pkg):
    return os.path.join(AS56_W, 'Content', pkg[len('/Game/'):] + '.uasset')


def _folder_assets():
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    return dict((str(ad.package_name), str(ad.asset_class_path.asset_name)) for ad in ar.get_assets_by_path(AS56_FOLDER, recursive=False))


def _vec3(x):
    if isinstance(x, dict):
        return [float(x.get(k, 0.0)) for k in ('x', 'y', 'z')]
    return [float(v) for v in x][:3]


def _patched_as10(expected_tris):
    src = open(AS56_AS10).read()
    patches = [
        ("        ok &= setp(ui, 'skeleton', None)\n",
         "        ok &= setp(ui, 'skeleton', eal.load_asset(SKEL) if eal.does_asset_exist(SKEL) else None)   # as_56: keep SKEL_Airship\n"),
        ("        ok &= setp(smd, 'update_skeleton_reference_pose', False)\n",
         "        ok &= setp(smd, 'update_skeleton_reference_pose', True)   # as_56: Helm_Wheel / PilotSeat moved\n"),
        ("abs(int(tags['Triangles']) - 104730) <= 600", "abs(int(tags['Triangles']) - %d) <= 600" % expected_tris),
        ("'triangles %s (FBX 104730)'", "'triangles %%s (FBX %d)'" % expected_tris),
    ]
    for old, new in patches:
        n = src.count(old)
        if n != 1:
            raise RuntimeError('as_10_import.py changed: patch target found %d times (want 1): %r' % (n, old.strip()))
        src = src.replace(old, new)
    return src


def as56_run():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        _o56('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    for p in (AS56_FBX, AS56_AS10, AS56_VERIFY):
        if not os.path.exists(p):
            _o56('FAIL', '%s missing (D7: rig_all.sh + verify_all.sh, then copy export/SK_Airship.fbx into SourceArt/Airship)' % p)
            return
    if not eal.does_asset_exist(AS56_SK) or not eal.does_asset_exist(AS56_SKEL):
        _o56('FAIL', 'SK_Airship / SKEL_Airship missing: this is a RE-import (first import: as_10_import.py)')
        return
    # the FBX in the repo is the one verify_all.sh checked
    sha_src = _sha(AS56_FBX)
    sha_rig = _sha(AS56_RIG_FBX) if os.path.exists(AS56_RIG_FBX) else None
    with open(AS56_VERIFY) as f:
        ver = json.load(f)
    AS56_R['fbx'] = {'sourceart': AS56_FBX, 'sha256': sha_src, 'bytes': os.path.getsize(AS56_FBX), 'rig_export_sha256': sha_rig,
                     'verify_fbx': ver.get('fbx'), 'verify_mtime': os.path.getmtime(AS56_VERIFY),
                     'rig_fbx_mtime': os.path.getmtime(AS56_RIG_FBX) if sha_rig else None}
    if sha_rig != sha_src:
        _o56('FAIL', 'SourceArt/Airship/SK_Airship.fbx is not the rig export (%s): copy rig/export/SK_Airship.fbx after verify_all.sh' % AS56_RIG_FBX)
        return
    if os.path.getmtime(AS56_VERIFY) < os.path.getmtime(AS56_RIG_FBX):
        _o56('FAIL', 'fbx_verify.json is older than rig/export/SK_Airship.fbx: run verify_all.sh first')
        return
    tris = int(ver.get('total_tris') or 0)
    defects = ver.get('defects') or []
    _o56('PASS' if tris > 0 and not defects else 'FAIL', 'verify_all.sh on this FBX: %d triangles, %d vertices, defects %s'
         % (tris, int(ver.get('total_verts') or 0), defects[:5]))
    if tris <= 0 or defects:
        return
    try:
        with open(AS56_DIMS) as f:
            dims = json.load(f)
    except Exception as e:  # noqa: BLE001
        dims = {}
        _o56('WARN', 'turret_dims.json not readable (%s): Helm_Wheel / PilotSeat only printed' % e)
    # PA_Airship must come out untouched (the reimport restores the mesh's physics asset pointer; PA is not rebuilt)
    pa_file = _pkg_file(AS56_PA)
    pa_sha0 = _sha(pa_file) if os.path.exists(pa_file) else None
    sk0 = eal.load_asset(AS56_SK)
    pa0 = sk0.get_editor_property('physics_asset')
    AS56_R['before'] = {'physics_asset': pa0.get_path_name() if pa0 else None, 'pa_sha256': pa_sha0,
                        'skeleton': sk0.get_editor_property('skeleton').get_path_name()}
    _o56('INFO', 'before: %s' % AS56_R['before'])
    aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
    for p in AS56_EDITED:
        if eal.does_asset_exist(p):
            try:
                aes.close_all_editors_for_asset(eal.load_asset(p))
            except Exception:  # noqa: BLE001
                pass
    folder0 = _folder_assets()
    src = _patched_as10(tris)
    _o56('INFO', 'running as_10_import.py (AS10_EXISTING reimport, skeleton kept, triangles %d) ---------------------------' % tris)
    g = globals()
    g['AS10_EXISTING'] = 'reimport'
    exec(compile(src, AS56_AS10 + ' (as_56 patched)', 'exec'), g)
    g.pop('AS10_EXISTING', None)          # as_10 pops it itself; never leave a reimport armed for a later run
    r10 = g.get('_as10_r') or {}
    _o56('PASS' if not (r10.get('counts') or {}).get('FAIL') else 'FAIL', '---- as_10 counts %s' % r10.get('counts'))
    # as_56's own checks
    folder1 = _folder_assets()
    new = dict((p, c) for p, c in folder1.items() if p not in folder0)
    new_skel = [p for p, c in new.items() if c == 'Skeleton']
    _o56('PASS' if not new_skel else 'FAIL', 'no new skeleton asset (new assets in the folder: %s)' % new)
    sk = eal.load_asset(AS56_SK)
    skel = sk.get_editor_property('skeleton')
    _o56('PASS' if skel and skel.get_path_name().startswith(AS56_SKEL + '.') else 'FAIL', 'SK_Airship skeleton %s' % (skel.get_path_name() if skel else None))
    for p in new_skel:
        if skel is None or not skel.get_path_name().startswith(p + '.'):
            ok = eal.delete_asset(p)
            _o56('WARN', 'deleted the stray skeleton this import made (unused): %s -> %s' % (p, ok))
    pa = sk.get_editor_property('physics_asset')
    _o56('PASS' if (pa.get_path_name() if pa else None) == AS56_R['before']['physics_asset'] else 'FAIL',
         'SK_Airship physics asset %s (was %s)' % (pa.get_path_name() if pa else None, AS56_R['before']['physics_asset']))
    pa_sha1 = _sha(pa_file) if os.path.exists(pa_file) else None
    pa_dirty = AS56_PA in [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    _o56('PASS' if pa_sha1 == pa_sha0 and not pa_dirty else 'FAIL', 'PA_Airship untouched: file %s, dirty %s (never saved here)'
         % ('unchanged' if pa_sha1 == pa_sha0 else 'CHANGED', pa_dirty))
    # rest positions of the moved bones (component space = hull space)
    pose = unreal.AnimPoseExtensions.get_reference_pose(skel)
    ws = unreal.AnimPoseSpaces.WORLD
    names = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
    _o56('PASS' if len(names) == 118 else 'FAIL', '%d bones (want 118, names unchanged: as_10 checked them against bones_ue.csv)' % len(names))
    pos = {}
    for b in ('Helm', 'Helm_Wheel', 'PilotSeat'):
        if b in names:
            t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, b, ws).translation
            pos[b] = [round(t.x, 2), round(t.y, 2), round(t.z, 2)]
    AS56_R['rest'] = pos
    for b, key in (('Helm_Wheel', 'helm_wheel_ue'), ('PilotSeat', 'pilot_seat_ue')):
        if b not in pos:
            _o56('FAIL', 'bone %s missing' % b)
            continue
        if dims.get(key) is None:
            _o56('WARN', '%s rest %s (turret_dims.json has no %s)' % (b, pos[b], key))
            continue
        want = _vec3(dims[key])
        d = math.sqrt(sum((pos[b][i] - want[i]) ** 2 for i in range(3)))
        _o56('PASS' if d <= 2.0 else 'FAIL', '%s rest %s vs turret_dims.json %s %s: %.2f cm' % (b, pos[b], key, want, d))
    if 'PilotSeat' in pos:
        p = pos['PilotSeat']
        _o56('INFO', 'AAirshipPawn::PilotSeatFallback should be FVector(%.1f, %.1f, %.1f) (AirshipPawn.h; core)' % tuple(p))
    try:
        nat = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.AirshipPawn'))
        fb = nat.get_editor_property('PilotSeatFallback')
        if 'PilotSeat' in pos:
            d = math.sqrt((fb.x - pos['PilotSeat'][0]) ** 2 + (fb.y - pos['PilotSeat'][1]) ** 2 + (fb.z - pos['PilotSeat'][2]) ** 2)
            _o56('PASS' if d <= 2.0 else 'WARN', 'C++ PilotSeatFallback (%.1f, %.1f, %.1f): %.1f cm from the new PilotSeat' % (fb.x, fb.y, fb.z, d))
    except Exception as e:  # noqa: BLE001
        _o56('INFO', 'PilotSeatFallback not readable from Python (%s)' % e)
    saved = (r10.get('counts') or {}).get('FAIL', 0) == 0
    _o56('INFO', 'as_10 %s SK_Airship + SKEL_Airship. NEXT: as_09_part_bounds_blender.py (headless Blender), as_12_reuse.py, '
         'as_13_cr_eval.py' % ('saved' if saved else 'did NOT save'))


try:
    as56_run()
except Exception:  # noqa: BLE001
    _o56('FAIL', 'as_56 crashed: %s' % traceback.format_exc())
try:
    _d56 = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
    os.makedirs(_d56, exist_ok=True)
    with open(os.path.join(_d56, 'as_56_reimport_airship.json'), 'w') as _f56:
        json.dump(AS56_R, _f56, indent=1, default=str)
except Exception as _e56:  # noqa: BLE001
    print('WARN: report not written %r' % (_e56,))
print('RESULT: %s %s' % ('PASS' if not AS56_R['counts'].get('FAIL') else 'FAIL', AS56_R['counts']))
