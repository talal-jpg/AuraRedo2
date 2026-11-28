# as_92_r3_pa_stairs.py - round 3 (FULL.md section 6 "Stairs collision", EXPORT_R3.md section 6; EDITOR_STAGE_R3.md step 5):
# adds the 16 boxes of Docs/Airship/round3/stairs_collision.json to PA_Airship's Hull body, so players walk up the new
# stairs to the turret deck instead of through them: 2 walkable ramps (36.1 deg, top face through the tread nosings), the
# landing and the top step (walkable), 12 blocking boxes (hand rails, the four landing columns, the two new guard rails on
# the platform's aft edge). Nothing else in PA_Airship changes.
#   * Each box: PhysicsAssetToolset SetBox on body Hull (as_11's route through unreal.ToolsetRegistry), centre = the
#     json centre minus the Hull bone's rest position (at the origin, checked), rotation = the json's (pitch, yaw, roll in
#     Unreal's FRotator sense: +pitch lifts the box's +X end, which the json's corners show), extents = its full sizes.
#     The four "Stairs_Column" entries share a name in the json: they get Stairs_Column_0 .. _3 here (SetBox replaces a
#     shape of the same name). Shape names all start with "Stairs_" (AS92_PREFIX).
#   * Idempotent: a re-run sets the same names again (SetBox removes a same-named shape first) and removes any older
#     Stairs_* shape on Hull that the json no longer has. as_11_physics_asset.py rebuilds PA_Airship WITHOUT these boxes:
#     run as_92 again after any as_11 run.
#   * Checks after: every box read back (GetBodyShapes) has its 8 corners within 0.5 cm of the json's, the other Hull
#     shapes and every other body are unchanged (names, centres, extents, rotations), Hull stays Kinematic, no
#     constraints, 35 bodies / 159 shapes / 119 on Hull (as_58's round 2 counts were 35 / 143 / 103: as_58's PA section
#     will now report the new boxes, rotated and counted; as_93 is the round 3 check).
#   * Backup of PA_Airship first (Saved/Airship/backup_r3/); saves PA_Airship only, by explicit path, nothing when a FAIL.
# Run (clone editor, no PIE, PA_Airship editor closed):
#   Docs/Airship/scripts/harness/inbox.sh 92 Docs/Airship/scripts/ue/as_92_r3_pa_stairs.py 300
# Report: Saved/Airship/as_92_r3_pa_stairs.json
import json, math, os, traceback  # unreal = inbox namespace
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())

AS92_R = r3_report('as_92_r3_pa_stairs')
AS92_PA_OBJ = R3_PA + '.PA_Airship'
AS92_PREFIX = 'Stairs_'
AS92_TOL = 0.5


def _o(tag, msg):
    r3_o(AS92_R, tag, msg)


def as92_run():
    if r3_pie():
        _o('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    if not os.path.exists(R3_STAIRS):
        _o('FAIL', '%s missing' % R3_STAIRS)
        return
    boxes = r3_stairs_boxes()
    _o('PASS' if len(boxes) == 16 and len(set(b[0] for b in boxes)) == 16 and all(b[0].startswith(AS92_PREFIX) for b in boxes) else 'FAIL',
       'stairs_collision.json: %d boxes, unique names %s' % (len(boxes), [b[0] for b in boxes]))
    # the json's own corners against its centre / size / rotation (proves the rotation convention before writing)
    worst = max(r3_corner_match(r3_box_corners(b[1], b[2], b[3]), b[4]) for b in boxes)
    _o('PASS' if worst <= AS92_TOL else 'FAIL', 'json corners = centre + size + FRotator(pitch, yaw, roll): worst %.3f cm' % worst)
    if AS92_R['counts'].get('FAIL'):
        return
    sk = eal.load_asset(R3_SK)
    pa = eal.load_asset(R3_PA)
    if pa is None or r3_pth(sk.get_editor_property('physics_asset')) != AS92_PA_OBJ:
        _o('FAIL', 'PA_Airship missing or not SK_Airship\'s physics asset (%s)' % r3_pth(sk.get_editor_property('physics_asset')))
        return
    pose = unreal.AnimPoseExtensions.get_reference_pose(sk.get_editor_property('skeleton'))
    t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, 'Hull', unreal.AnimPoseSpaces.WORLD)
    hull = (t.translation.x, t.translation.y, t.translation.z)
    _o('PASS' if max(abs(x) for x in hull) < 0.01 and abs(abs(t.rotation.w) - 1) < 1e-6 else 'FAIL',
       'Hull bone rest %s, no rotation: json (component space) = Hull body space' % [round(x, 3) for x in hull])
    talal0 = r3_talal_state()
    r3_close_editors([R3_PA, R3_SK])
    if r3_backup(AS92_R, [R3_PA], 'as_92') is None:
        return
    names0 = sorted(str(n) for n in (r3_tool('GetBodyNames', PhysicsAsset=AS92_PA_OBJ) or []))
    if 'Hull' not in names0:
        _o('FAIL', 'PA_Airship has no Hull body (bodies %s): run as_11 first' % names0)
        return
    before = dict((b, r3_body_shapes(b)) for b in names0)
    old_stairs = sorted(n for n in before['Hull'] if n.startswith(AS92_PREFIX))
    AS92_R['data']['before'] = {'bodies': len(names0), 'shapes': sum(len(v) for v in before.values()),
                                'hull_shapes': len(before['Hull']), 'stairs_before': old_stairs}
    _o('INFO', 'before: %d bodies, %d shapes, %d on Hull (%d Stairs_* from an earlier run)' % (
        len(names0), AS92_R['data']['before']['shapes'], len(before['Hull']), len(old_stairs)))
    want = set(b[0] for b in boxes)
    for n in old_stairs:
        if n not in want:
            r3_tool('RemoveShape', PhysicsAsset=AS92_PA_OBJ, BoneName='Hull', ShapeName=n)
            _o('INFO', 'removed the stale %s' % n)
    for n, c, size, rot, corners, kind in boxes:
        lc = [c[i] - hull[i] for i in range(3)]
        r3_tool('SetBox', PhysicsAsset=AS92_PA_OBJ, BoneName='Hull', ShapeName=n, Center={'X': lc[0], 'Y': lc[1], 'Z': lc[2]},
                Rotation={'Pitch': rot[0], 'Yaw': rot[1], 'Roll': rot[2]}, ExtentX=size[0], ExtentY=size[1], ExtentZ=size[2])
    # read back
    names1 = sorted(str(n) for n in (r3_tool('GetBodyNames', PhysicsAsset=AS92_PA_OBJ) or []))
    after = dict((b, r3_body_shapes(b)) for b in names1)
    _o('PASS' if names1 == names0 else 'FAIL', 'bodies unchanged (%d)' % len(names1))
    res = {}
    worst = 0.0
    for n, c, size, rot, corners, kind in boxes:
        s = after['Hull'].get(n)
        if s is None:
            _o('FAIL', '%s not on Hull after SetBox' % n)
            continue
        got = r3_box_corners([s['center'][i] + hull[i] for i in range(3)], s['ext'], s['rot'])
        d = r3_corner_match(got, corners)
        worst = max(worst, d)
        res[n] = {'kind': kind, 'corner_err_cm': round(d, 3), 'center': s['center'], 'rot': s['rot'], 'ext': s['ext'], 'type': s['type']}
    AS92_R['data']['boxes'] = res
    _o('PASS' if len(res) == 16 and worst <= AS92_TOL else 'FAIL', '16 stair boxes on Hull, corners within %.3f cm of the json (tol %.1f)'
       % (worst, AS92_TOL))
    other = [(b, n) for b in names0 for n, s in before[b].items() if not (b == 'Hull' and n.startswith(AS92_PREFIX))
             and after.get(b, {}).get(n) != s]
    extra = [(b, n) for b in names1 for n in after[b] if not n.startswith(AS92_PREFIX) and n not in before.get(b, {})]
    _o('PASS' if not other and not extra else 'FAIL', 'every other shape unchanged%s' % ('' if not other and not extra else
       ': changed %s, new %s' % (other[:6], extra[:6])))
    mode = str(r3_tool('GetBodyPhysicsMode', PhysicsAsset=AS92_PA_OBJ, BoneName='Hull'))
    _o('PASS' if 'kinematic' in mode.lower() or mode == '1' else 'FAIL', 'Hull body physics mode %s (want Kinematic)' % mode)
    cons = r3_tool('GetConstraints', PhysicsAsset=AS92_PA_OBJ) or []
    _o('PASS' if not cons else 'FAIL', '%d constraints (want 0)' % len(cons))
    nsh = sum(len(v) for v in after.values())
    nh = len(after['Hull'])
    AS92_R['data']['after'] = {'bodies': len(names1), 'shapes': nsh, 'hull_shapes': nh}
    _o('PASS' if (len(names1), nsh, nh) == (35, 159, 119) else 'WARN', '%d bodies / %d shapes / %d on Hull (round 2 + 16: want 35 / 159 / 119; '
       'other numbers mean PA_Airship was not the round 2 one)' % (len(names1), nsh, nh))
    if AS92_R['counts'].get('FAIL'):
        _o('WARN', '%d FAIL: NOT saved (restart the editor before a re-run)' % AS92_R['counts']['FAIL'])
        return
    r3_save(AS92_R, [R3_PA])
    r3_check_talal(AS92_R, talal0)
    _o('INFO', 'NEXT: as_93_r3_verify.py, then the PIE checks (EDITOR_STAGE_R3.md)')


try:
    as92_run()
except Exception:  # noqa: BLE001
    _o('FAIL', 'as_92 crashed: %s' % traceback.format_exc())
r3_finish(AS92_R)
