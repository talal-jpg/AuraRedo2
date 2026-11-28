# as_93_r3_verify.py - round 3, READ-ONLY check of everything as_90 .. as_92 made or changed (EDITOR_STAGE_R3.md step 6).
# Nothing is saved, nothing is re-imported or recompiled; run it in a FRESH editor (after a restart: it then reads what the
# packages hold on disk, not what a run left in memory).
#   inputs     SourceArt/Airship/r3 + textures/r3 = r3_unreal_inputs.json (md5)
#   textures   T_AirshipR3_HullInk / DetailInk_H / DetailInk_M / PropsInk (4096 / 4096 / 4096 / 2048, sRGB off, BC7, clamp),
#              T_AirshipR3_HullComicMask (sRGB off, Masks); their source files
#   material   M_AirshipR3: this version's comment, usage skeletal mesh + Nanite, shader statistics; MI_AirshipR3_Look's 24
#              palette colours = the inputs (keel block slot 16 rust) and the ink knobs; the four child MIs: parent, InkTex,
#              static switches, two sided (hull only)
#   SK         SK_Airship: SKEL_Airship, 118 bones = rig/checks/rig/bones_ue.csv (names, parents, rest +-2 cm, identity
#              rotations), the sockets as_91 recorded before its import, PA_Airship, 3 LODs with 3 sections each, source
#              triangles per LOD = the FBX (GeometryScript), full-precision UVs + ThresholdUV 1/65536 per LOD, screen sizes
#              decreasing (LOD1 ~30 m, LOD2 ~80 m), slots M_Airship / M_AirshipProps / M_AirshipR3_Detail -> MI_AirshipR3_
#              Hull / _Props / _Moving, bounds ~ the export's
#   HullDetail SM_AirshipR3_HullDetail: Nanite on, 3 LODs, MI_AirshipR3_HullDetail, 2 UV channels, no simple collision,
#              bounds = the export's; BP_AirshipPawn: HullDetail under Mesh, NoCollision, identity, compiled, Mesh without
#              material overrides
#   turrets    SM_AirshipTurret_Base / _Gun: MI_AirshipR3_Props (M_AirshipProps when as_91c ran with its keep knob), 2 UV
#              channels, full-precision UVs, Nanite off, source file = SourceArt/Airship/r3 (review fix)
#   v2 (review fixes, EXPORT_R3.md 15): ink textures trilinear, HasComic off on the hull MI, MI_AirshipR3_Look's look
#              knobs = the staged defaults and its HasSilhouette switch, SK UV channels 3 per LOD (GeometryScript),
#              HullDetail Nanite fallback PercentTriangles 1.0, slot 1 / turrets accept M_AirshipProps with the keep knobs
#   PA         PA_Airship: 35 bodies / 159 shapes / 119 on Hull, the 16 Stairs_* boxes' corners within 0.5 cm of
#              stairs_collision.json, all Kinematic, no constraints
#   untouched  Talal's /Game/Assets/MyShip/M_Airship, T_Airship_ComicLines, T_Airship_ComicMask, SM_Airship and round 2's
#              M_AirshipDrivable / M_AirshipProps: .uasset = the clone's HEAD (git LFS pointer sha256); CR_Airship,
#              ABP_Airship, A_Airship_TestSweep, IMC_Airship too
# No stills here: the PIE run's screenshots are the visual check (EDITOR_STAGE_R3.md section 4).
# Run (fresh clone editor, no PIE): Docs/Airship/scripts/harness/inbox.sh 93 Docs/Airship/scripts/ue/as_93_r3_verify.py 600
# Report: Saved/Airship/as_93_r3_verify.json
import csv, json, math, os, subprocess, traceback  # unreal = inbox namespace
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())

AS93_R = r3_report('as_93_r3_verify')
AS93_CSV = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/checks/rig/bones_ue.csv'
AS93_UNTOUCHED = R3_TALAL + R3_ROUND2_MATS + [R3_CR, R3_ABP, R3_ANIM, R3_D + '/Input/IMC_Airship']
AS93_TEX_WANT = {'hull': 4096, 'H': 4096, 'M': 4096, 'P': 2048, 'comic': 4096}
AS92_PA_OBJ = R3_PA + '.PA_Airship'
AS92_TOL = 0.5


def as93_keep_props(report):
    """True when as_91 / as_91c ran with the documented keep-M_AirshipProps knob (their reports record it)"""
    try:
        return bool(json.load(open(os.path.join(R3_SAVED, report + '.json')))['data'].get('keep_props_material'))
    except Exception:  # noqa: BLE001
        return False


AS93_PROPS_MAT = R3_MATD + '/M_AirshipProps'


def _o(tag, msg):
    r3_o(AS93_R, tag, msg)


def as93_git(*args):
    return subprocess.run(['git', '-C', R3_W] + list(args), capture_output=True, text=True, timeout=60)


def as93_untouched():
    for pkg in AS93_UNTOUCHED:
        rel = os.path.relpath(r3_pkg_file(pkg), R3_W)
        p = r3_pkg_file(pkg)
        r = as93_git('show', 'HEAD:' + rel)
        if r.returncode != 0:
            _o('WARN', '%s: not in HEAD (%s)' % (rel, r.stderr.strip()[:120]))
            continue
        oid = next((l.split(':', 1)[1].strip() for l in r.stdout.splitlines() if l.startswith('oid sha256:')), None)
        if oid is None:
            d = as93_git('diff', '--quiet', 'HEAD', '--', rel)
            _o('PASS' if d.returncode == 0 else 'FAIL', '%s unchanged vs HEAD (git diff)' % rel)
            continue
        cur = r3_sha(p) if os.path.exists(p) else None
        _o('PASS' if cur == oid else 'FAIL', '%s unchanged vs HEAD (LFS %s.., now %s..)' % (rel, oid[:12], (cur or 'missing')[:12]))
    dirty = [p for p in AS93_UNTOUCHED if p in r3_dirty()]
    talal_dirty = [p for p in dirty if p in R3_TALAL]
    # CR_Airship / ABP_Airship can come up dirty after a load or a PIE run (seen in round 2) without anything changing:
    # only Talal's assets FAIL here; the file checks above are what counts
    _o('PASS' if not dirty else ('FAIL' if talal_dirty else 'WARN'), 'none of them changed in memory%s' % (
        '' if not dirty else ': %s (never save them from this session)' % dirty))


def as93_textures(eal, inp):
    for k, p in R3_TEX.items():
        t = eal.load_asset(p) if eal.does_asset_exist(p) else None
        if not isinstance(t, unreal.Texture2D):
            _o('FAIL', '%s missing' % p)
            continue
        comp = str(r3_getp(t, 'compression_settings'))
        size = [t.blueprint_get_size_x(), t.blueprint_get_size_y()]
        src = ''
        try:
            src = t.get_editor_property('asset_import_data').get_first_filename()
        except Exception:  # noqa: BLE001
            pass
        flt, grp = str(r3_getp(t, 'filter')), str(r3_getp(t, 'lod_group'))
        # review fix: the ink pages must blend mips (TEXTUREGROUP_World = aniso + MipFilter=point = nearest mip on Vulkan):
        # TF_TRILINEAR, or TF_DEFAULT with a project texture group defined with MipFilter=linear (EDITOR_STAGE_R3 3)
        filt_ok = k == 'comic' or 'TRILINEAR' in flt.upper() or ('DEFAULT' in flt.upper() and 'WORLD' not in grp.upper())
        ok = not r3_getp(t, 'srgb') and size == [AS93_TEX_WANT[k]] * 2 and \
            ('MASKS' in comp.upper() if k == 'comic' else ('BC7' in comp.upper() or 'DISPLACEMENT' in comp.upper())) and \
            'CLAMP' in str(r3_getp(t, 'address_x')).upper() and os.path.basename(src or '') == p.rsplit('/', 1)[1] + '.png' and filt_ok
        _o('PASS' if ok else 'FAIL', '%s %s sRGB %s %s address %s filter %s group %s from %s' % (
            p.rsplit('/', 1)[1], size, r3_getp(t, 'srgb'), comp, r3_getp(t, 'address_x'), flt, grp, src))


def as93_material(eal, inp):
    MEL = unreal.MaterialEditingLibrary
    m = eal.load_asset(R3_MASTER)
    if not isinstance(m, unreal.Material):
        _o('FAIL', '%s missing' % R3_MASTER)
        return
    notes = [str(e.get_editor_property('text')) for e in MEL.get_material_expressions(m) if isinstance(e, unreal.MaterialExpressionComment)]
    _o('PASS' if any(n.startswith('as_90 M_AirshipR3 v') for n in notes) else 'FAIL', 'M_AirshipR3 built by as_90 (%s)' % [n[:40] for n in notes])
    for u in ('MATUSAGE_SKELETAL_MESH', 'MATUSAGE_NANITE'):
        _o('PASS' if MEL.has_material_usage(m, getattr(unreal.MaterialUsage, u)) else 'FAIL', 'M_AirshipR3 usage %s' % u)
    try:
        st = MEL.get_statistics(m)
        n = r3_getp(st, 'num_pixel_shader_instructions')
        _o('PASS' if (n or 0) > 0 else 'WARN', 'M_AirshipR3 pixel shader instructions %s, samplers %s' % (n, r3_getp(st, 'num_samplers')))
    except Exception as e:  # noqa: BLE001
        _o('WARN', 'statistics: %s' % e)
    look = eal.load_asset(R3_LOOK)
    bad = []
    for i, p in enumerate(inp['palette']):
        c = MEL.get_material_instance_vector_parameter_value(look, 'Pal_%02d_%s' % (i, p['slot']))
        if max(abs(c.r - p['linear'][0]), abs(c.g - p['linear'][1]), abs(c.b - p['linear'][2])) > 1e-4:
            bad.append((i, p['slot'], [round(c.r, 3), round(c.g, 3), round(c.b, 3)], p['linear']))
    _o('PASS' if not bad else 'WARN', 'MI_AirshipR3_Look palette = the export\'s 24 colours%s' % (
        '' if not bad else ' except %s (tuned by hand since? fine if on purpose)' % bad))
    ink = dict((n, MEL.get_material_instance_scalar_parameter_value(look, n)) for n in ('InkDistMax', 'InkDistNeg', 'InkPxNear', 'InkPxFar',
                                                                                     'InkFarStart', 'InkFarEnd', 'ComicAmount', 'Roughness'))
    AS93_R['data']['ink'] = ink
    _o('PASS' if abs(ink['InkDistMax'] - inp['ink']['InkDistMax_cm']) < 1e-4 and abs(ink['InkDistNeg'] - inp['ink']['InkDistNeg_cm']) < 1e-4
       else 'FAIL', 'ink decode InkDistMax %s / InkDistNeg %s = the bake\'s %s / %s cm (must match); knobs %s' % (
           ink['InkDistMax'], ink['InkDistNeg'], inp['ink']['InkDistMax_cm'], inp['ink']['InkDistNeg_cm'], ink))
    lk = dict((n, round(MEL.get_material_instance_scalar_parameter_value(look, n), 4)) for n in ('LitMix', 'ShadeLift', 'LiftSat', 'LiftLock',
                                                                                              'InkOpacityFar', 'SilWidthPx'))
    sil = MEL.get_material_instance_static_switch_parameter_value(look, 'HasSilhouette')
    AS93_R['data']['look'] = dict(lk, HasSilhouette=sil)
    want_lk = inp.get('look') or {}
    same_lk = all(abs(lk[n] - float(want_lk[n])) < 1e-3 for n in ('LitMix', 'ShadeLift', 'LiftSat', 'LiftLock') if n in want_lk)
    _o('PASS' if same_lk else 'WARN', 'MI_AirshipR3_Look look %s (staged defaults %s%s), HasSilhouette %s (off = default; on = the '
       'silhouette option)' % (lk, dict((n, want_lk.get(n)) for n in ('LitMix', 'ShadeLift', 'LiftSat', 'LiftLock')),
                               '' if same_lk else ': tuned by hand since? fine if on purpose', sil))
    setup = {'hull': ('hull', {'InkOnUV2': True, 'HasDots': True, 'HasComic': False}, True),
             'moving': ('M', {'InkOnUV2': False, 'HasDots': True, 'HasComic': False}, False),
             'hulldetail': ('H', {'InkOnUV2': False, 'HasDots': True, 'HasComic': False}, False),
             'props': ('P', {'InkOnUV2': False, 'HasDots': False, 'HasComic': False}, False)}
    for k, (tk, sw, two) in setup.items():
        mi = eal.load_asset(R3_MI[k])
        if mi is None:
            _o('FAIL', '%s missing' % R3_MI[k])
            continue
        got_s = dict((n, MEL.get_material_instance_static_switch_parameter_value(mi, n)) for n in sw)
        ov = mi.get_editor_property('base_property_overrides')
        g2 = bool(ov.get_editor_property('override_two_sided')) and bool(ov.get_editor_property('two_sided'))
        tex = r3_pkg(MEL.get_material_instance_texture_parameter_value(mi, 'InkTex'))
        ok = r3_pkg(mi.get_editor_property('parent')) == R3_LOOK and tex == R3_TEX[tk] and got_s == sw and g2 == two
        _o('PASS' if ok else 'FAIL', '%s: InkTex %s, switches %s, two sided %s' % (R3_MI[k].rsplit('/', 1)[1], tex, got_s, g2))


def as93_sk(eal, inp):
    smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    sk = eal.load_asset(R3_SK)
    _o('PASS' if r3_pkg(sk.get_editor_property('skeleton')) == R3_SKEL else 'FAIL', 'SK_Airship skeleton %s' % r3_pth(sk.get_editor_property('skeleton')))
    _o('PASS' if r3_pkg(sk.get_editor_property('physics_asset')) == R3_PA else 'FAIL', 'SK_Airship physics asset %s' % r3_pth(sk.get_editor_property('physics_asset')))
    rows = {}
    with open(AS93_CSV) as f:
        f.readline()
        for line in f:
            c = line.strip().split(',')
            if len(c) >= 5:
                rows[c[0]] = (c[1] or None, (float(c[2]), float(c[3]), float(c[4])))
    bt = r3_bone_table(sk)
    worst = max((max(abs(b[2][i] - rows[b[0]][1][i]) for i in range(3)) for b in bt if b[0] in rows), default=99)
    ok = len(bt) == 118 and set(b[0] for b in bt) == set(rows) and all(b[1] == rows[b[0]][0] for b in bt) and worst <= 2.0 and \
        max(b[3] for b in bt) <= 0.01
    _o('PASS' if ok else 'FAIL', '%d bones = bones_ue.csv (names, parents, rest within %.3f cm, rotations identity)' % (len(bt), worst))
    mr = r3_mesh_ref_bones(sk, list(rows))
    if mr:
        wm = max(max(abs(mr[n][i] - rows[n][1][i]) for i in range(3)) for n in mr)
        _o('PASS' if len(mr) == len(rows) and wm <= 2.0 else 'FAIL', 'SK_Airship\'s own reference skeleton (SkeletonModifier) = '
           'bones_ue.csv: %d bones, rest within %.3f cm' % (len(mr), wm))
    else:
        _o('WARN', 'SK_Airship\'s own reference skeleton not readable (SkeletonModifier): SKEL_Airship\'s reference pose only')
    try:
        r91 = json.load(open(os.path.join(R3_SAVED, 'as_91_r3_reimport.json')))
        s0 = [tuple(tuple(y) if isinstance(y, list) else y for y in x) for x in r91['data']['before']['sockets']]
        s1 = r3_sockets(sk)
        _o('PASS' if s1 == s0 else 'FAIL', 'sockets = as_91\'s record before the import (%d)' % len(s1))
    except Exception as e:  # noqa: BLE001
        _o('WARN', 'as_91 report not readable (%s): sockets only listed: %s' % (e, r3_sockets(sk)))
    n = smes.get_lod_count(sk)
    _o('PASS' if n == 3 else 'FAIL', 'SK_Airship %d LODs (want 3)' % n)
    want_t = dict((int(k), v) for k, v in inp['sk']['tris'].items())
    ss, _raw = r3_sk_screen_sizes(sk)
    ss = [round(x, 3) for x in ss] if ss else []
    for lod in range(n):
        bs = unreal.SkeletalMeshEditorSubsystem.get_lod_build_settings(sk, lod)
        st = r3_geo_tris(sk, lod)
        nuv = r3_uv_sets(sk, lod)
        sec = smes.get_num_sections(sk, lod)
        slots = sorted(smes.get_lod_material_slot(sk, lod, s) for s in range(sec))
        ok = sec == 3 and slots == [0, 1, 2] and (st is None or st == want_t.get(lod)) and r3_getp(bs, 'use_full_precision_u_vs') and \
            abs(float(r3_getp(bs, 'threshold_uv', 1)) - 1.0 / 65536) < 1e-9 and (nuv is None or nuv == inp['sk'].get('uv_channels', 3))
        _o('PASS' if ok else 'FAIL', 'LOD%d: %d sections -> slots %s, source triangles %s (FBX %s), UV channels %s (want %s), render vertices %d, '
           'full-precision UVs %s, ThresholdUV %s, screen size %s' % (lod, sec, slots, st, want_t.get(lod), nuv, inp['sk'].get('uv_channels', 3),
                                                                     smes.get_num_verts(sk, lod), r3_getp(bs, 'use_full_precision_u_vs'),
                                                                     r3_getp(bs, 'threshold_uv'), ss[lod] if lod < len(ss) else None))
    rad = float(sk.get_imported_bounds().sphere_radius)
    want_ss = [r3_screen_size(rad, 30.0), r3_screen_size(rad, 80.0)]
    _o('PASS' if len(ss) == 3 and abs(ss[1] - want_ss[0]) < 0.01 and abs(ss[2] - want_ss[1]) < 0.01 else 'WARN',
       'screen sizes %s (30 m / 80 m at FOV 85 = %s for the bounds radius %.0f cm; WARN = tuned by hand?)' % (ss, [round(x, 3) for x in want_ss], rad))
    got = [(nm, r3_pkg(m.get_editor_property('material_interface'))) for nm, m in zip(r3_slot_names(sk.materials), sk.materials)]
    keep = as93_keep_props('as_91_r3_reimport')

    def _want(nm):
        key = R3_SLOT_MI.get(nm)
        return AS93_PROPS_MAT if (key == 'props' and keep) else R3_MI.get(key)
    ok = len(got) == 3 and all(p == _want(nm) for nm, p in got)
    _o('PASS' if ok else 'FAIL', 'SK_Airship slots %s%s' % (got, ' (as_91 ran with AS91_KEEP_PROPS_MATERIAL: slot 1 keeps M_AirshipProps)' if keep else ''))
    bb = sk.get_imported_bounds()
    o_, e_ = bb.origin, bb.box_extent
    mn = [o_.x - e_.x, o_.y - e_.y, o_.z - e_.z]
    mx = [o_.x + e_.x, o_.y + e_.y, o_.z + e_.z]
    wb = inp['sk']['bounds_ue_cm']
    d = max(max(abs(mn[i] - wb['min_cm'][i]), abs(mx[i] - wb['max_cm'][i])) for i in range(3))
    _o('PASS' if d <= 2.0 else 'WARN', 'SK_Airship imported bounds %s .. %s vs the export %s: %.1f cm' % (
        [round(x) for x in mn], [round(x) for x in mx], wb, d))


def as93_hull_detail(eal, inp):
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    sm = eal.load_asset(R3_HD)
    if not isinstance(sm, unreal.StaticMesh):
        _o('FAIL', '%s missing' % R3_HD)
        return
    ns_ = sms.get_nanite_settings(sm)
    nan = bool(ns_.get_editor_property('enabled'))
    fb = (str(r3_getp(ns_, 'fallback_target')), r3_getp(ns_, 'fallback_percent_triangles'))
    _o('PASS' if 'PERCENT_TRIANGLES' in fb[0].upper() and abs(float(fb[1] or 0) - 1.0) < 1e-6 else 'FAIL',
       'SM_AirshipR3_HullDetail Nanite fallback %s %s (want PercentTriangles 1.0: the full LOD0 without Nanite)' % fb)
    n = sms.get_lod_count(sm)
    mats = [r3_pkg(m.get_editor_property('material_interface')) for m in sm.get_editor_property('static_materials')]
    bb = sm.get_bounding_box()
    wb = inp['hull_detail']['bounds_ue_cm']
    d = max(max(abs([bb.min.x, bb.min.y, bb.min.z][i] - wb['min_cm'][i]), abs([bb.max.x, bb.max.y, bb.max.z][i] - wb['max_cm'][i])) for i in range(3))
    want_t = dict((int(k), v) for k, v in inp['hull_detail']['tris'].items())
    tris = [r3_geo_tris(sm, l) for l in range(n)]
    ok = nan and n == 3 and mats == [R3_MI['hulldetail']] and d <= 1.0 and sms.get_simple_collision_count(sm) == 0 and \
        all(sms.get_num_uv_channels(sm, l) == 2 for l in range(n)) and all(t is None or t == want_t[l] for l, t in enumerate(tris))
    _o('PASS' if ok else 'FAIL', 'SM_AirshipR3_HullDetail: Nanite %s, %d LODs, source triangles %s (FBX %s), slots %s, bounds vs export %.2f cm, '
       'screen sizes %s, simple collision %d' % (nan, n, tris, want_t, mats, d, [round(x, 3) for x in sms.get_lod_screen_sizes(sm)],
                                                 sms.get_simple_collision_count(sm)))
    bp = eal.load_asset(R3_BP)
    st = bp.get_editor_property('status')
    _o('PASS' if st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS) else 'FAIL', 'BP_AirshipPawn status %s' % st)
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    hs = dict((str(lib.get_variable_name(lib.get_data(h))), h) for h in sds.k2_gather_subobject_data_for_blueprint(bp))
    if 'HullDetail' not in hs:
        _o('FAIL', 'BP_AirshipPawn has no HullDetail component (%s)' % sorted(hs))
        return
    d_ = lib.get_data(hs['HullDetail'])
    comp = lib.get_object(d_)
    rl, rr, rs = r3_getp(comp, 'relative_location'), r3_getp(comp, 'relative_rotation'), r3_getp(comp, 'relative_scale3d')
    ident = rl.length() < 0.01 and abs(rr.pitch) + abs(rr.yaw) + abs(rr.roll) < 0.01 and abs(rs.x - 1) + abs(rs.y - 1) + abs(rs.z - 1) < 1e-4
    ok = r3_pkg(r3_getp(comp, 'static_mesh')) == R3_HD and 'NO_COLLISION' in str(comp.get_collision_enabled()).upper().replace(' ', '_') and \
        lib.is_attached_to(d_, hs['Mesh']) and ident and not r3_getp(comp, 'generate_overlap_events')
    _o('PASS' if ok else 'FAIL', 'BP_AirshipPawn.HullDetail: mesh %s, collision %s, under Mesh %s, identity %s, socket %s (none = the Hull bone, '
       'which rests at the origin)' % (r3_pkg(r3_getp(comp, 'static_mesh')), comp.get_collision_enabled(), lib.is_attached_to(d_, hs['Mesh']),
                                       ident, comp.get_attach_socket_name()))


def as93_turrets(eal, inp):
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for name, p in R3_TURRET.items():
        sm = eal.load_asset(p)
        mats = [r3_pkg(m.get_editor_property('material_interface')) for m in sm.get_editor_property('static_materials')]
        full = bool(r3_getp(sms.get_lod_build_settings(sm, 0), 'use_full_precision_u_vs'))
        nan = bool(sms.get_nanite_settings(sm).get_editor_property('enabled'))
        keep = as93_keep_props('as_91c_r3_turrets')
        srcf = ''
        try:
            srcf = sm.get_editor_property('asset_import_data').get_first_filename()
        except Exception:  # noqa: BLE001
            pass
        from_r3 = os.path.abspath(srcf or '') == os.path.abspath(os.path.join(R3_SRC, name + '.fbx'))
        ok = mats == [AS93_PROPS_MAT if keep else R3_MI['props']] and sms.get_num_uv_channels(sm, 0) == 2 and full and not nan and from_r3
        _o('PASS' if ok else 'FAIL', '%s: slots %s%s, UV channels %d, full-precision UVs %s, Nanite %s, source %s (r3 %s)' % (
            name, mats, ' (AS91C_KEEP_PROPS_MATERIAL)' if keep else '', sms.get_num_uv_channels(sm, 0), full, nan, srcf, from_r3))


def as93_pa(eal):
    names = sorted(str(n) for n in (r3_tool('GetBodyNames', PhysicsAsset=AS92_PA_OBJ) or []))
    shapes = dict((b, r3_body_shapes(b)) for b in names)
    nsh = sum(len(v) for v in shapes.values())
    nh = len(shapes.get('Hull', {}))
    _o('PASS' if (len(names), nsh, nh) == (35, 159, 119) else 'FAIL', 'PA_Airship %d bodies / %d shapes / %d on Hull (want 35 / 159 / 119)' % (len(names), nsh, nh))
    boxes = r3_stairs_boxes()
    worst, miss = 0.0, []
    for n, c, size, rot, corners, kind in boxes:
        s = shapes.get('Hull', {}).get(n)
        if s is None:
            miss.append(n)
            continue
        worst = max(worst, r3_corner_match(r3_box_corners(s['center'], s['ext'], s['rot']), corners))
    _o('PASS' if not miss and worst <= AS92_TOL else 'FAIL', '16 stair boxes on Hull, corners within %.3f cm of stairs_collision.json%s' % (
        worst, '' if not miss else '; missing %s' % miss))
    modes = {}
    for b in names:
        m = str(r3_tool('GetBodyPhysicsMode', PhysicsAsset=AS92_PA_OBJ, BoneName=b))
        modes[m] = modes.get(m, 0) + 1
    _o('PASS' if len(modes) == 1 and ('kinematic' in list(modes)[0].lower() or list(modes) == ['1']) else 'FAIL', 'physics modes %s' % modes)
    cons = r3_tool('GetConstraints', PhysicsAsset=AS92_PA_OBJ) or []
    _o('PASS' if not cons else 'FAIL', '%d constraints' % len(cons))


def as93_run():
    if r3_pie():
        _o('FAIL', 'PIE is running: not checked')
        return
    eal = unreal.EditorAssetLibrary
    inp = r3_inputs(AS93_R)
    if inp is None:
        return
    for f in (as93_textures, as93_material, as93_sk, as93_hull_detail, as93_turrets):
        try:
            f(eal, inp)
        except Exception:  # noqa: BLE001
            _o('FAIL', '%s crashed: %s' % (f.__name__, traceback.format_exc()))
    try:
        as93_pa(eal)
    except Exception:  # noqa: BLE001
        _o('FAIL', 'as93_pa crashed: %s' % traceback.format_exc())
    as93_untouched()
    d = [p for p in r3_dirty()]
    _o('INFO', 'dirty packages now (this script saves nothing): %s' % d)


try:
    as93_run()
except Exception:  # noqa: BLE001
    _o('FAIL', 'as_93 crashed: %s' % traceback.format_exc())
r3_finish(AS93_R)
