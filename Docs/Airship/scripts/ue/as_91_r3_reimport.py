# as_91_r3_reimport.py - round 3 (EXPORT_R3.md sections 1, 4, 6; EDITOR_STAGE_R3.md step 2): re-imports SK_Airship from
# SourceArt/Airship/r3/SK_Airship.fbx (SM_Airship with the three base edits, the 30 props, the merged moving-part details
# SM_AirshipR3Detail_Moving: 238,430 triangles, 3 material slots, 3 UV channels) OVER the existing asset, keeping
# SKEL_Airship and PA_Airship, then imports LOD1 / LOD2 (SK_Airship_LOD1.fbx / _LOD2.fbx), sets the LOD screen sizes and
# assigns the round 3 material instances. Needs as_90 (the MIs). Does NOT touch PA_Airship (as_92 adds the stair boxes),
# CR_Airship, ABP_Airship, A_Airship_TestSweep or BP_AirshipPawn.
#   0. refuses during PIE, with SK_Airship / SKEL_Airship / PA_Airship changed in memory, or when a staged FBX is not the
#      checked export (r3_unreal_inputs.json md5); closes their editors; backs up SK, SKEL and PA (Saved/Airship/backup_r3/).
#   1. records the skeleton (118 bones: names, order, parents, component-space rest positions), the sockets, the physics
#      asset pointer and PA_Airship's file sha256.
#   2. LOD0 build settings BEFORE the import: full-precision UVs (half floats put the ink lines up to 1 texel off on a 4096
#      page, r3_fbx_check) and ThresholdUV 1/65536 (Unreal welds corners whose UVs all lie within ThresholdUV, default
#      1/1024: 234 corner pairs of SM_Airship's ink atlas would weld, up to 4 texels off). Normals from the file.
#   3. the re-import: SK_Airship carries Interchange import data since round 2's as_56, so its source file is pointed at the
#      r3 FBX and it is re-imported through the Interchange manager with the pipeline stored in it (as_56's route: an
#      AssetImportTask over an Interchange-imported mesh took the legacy re-import factory and lost the stored options);
#      legacy FBX import data -> an AssetImportTask with FbxFactory and SKEL_Airship as the skeleton (as_56 patch 1).
#      The stored "update skeleton reference pose" flag is left as it is (no bone moved).
#   4. checks: SKEL_Airship kept, no new skeleton asset, 118 bones with the same names / order / parents and rest positions
#      (+-0.01 cm), the same sockets, PA_Airship pointer kept and its file unchanged and not dirty, 3 slots named M_Airship,
#      M_AirshipProps, M_AirshipR3_Detail; the build settings re-applied if the import reset them.
#   5. LOD1 / LOD2: SkeletalMeshEditorSubsystem.import_lod (re-importing the base mesh can drop custom LODs: this step runs
#      after every re-import), their build settings, screen sizes from the imported bounds: 1.94 * R / D (FOV 85, 16:9) at
#      30 m and 80 m (AS91_LOD_DIST_M; LOD0 above LOD1), no reduction. UE 5.8 keeps a skeletal mesh's LOD infos in its
#      SourceModels array, which Python cannot get / set as a property: the sizes go in through ToolsetLibrary JSON (only
#      the ScreenSize fields; the rest of each source model is compared before / after). If that is refused, the line
#      is a WARN with the two numbers to type into the SK editor by hand. Per LOD: 3 sections, triangles = the FBX
#      (GeometryScript, when the plugin is there), render vertices ~ the export's estimate.
#   6. slots by imported slot name: M_Airship -> MI_AirshipR3_Hull, M_AirshipProps -> MI_AirshipR3_Props (the props
#      recolour; AS91_KEEP_PROPS_MATERIAL = True keeps round 2's M_AirshipProps), M_AirshipR3_Detail -> MI_AirshipR3_Moving.
#   7. saves SK_Airship (+ SKEL_Airship only if the import changed it) by explicit path; nothing when a FAIL.
# Run (clone editor, no PIE; editors of SK / SKEL / PA / CR / ABP / BP closed):
#   Docs/Airship/scripts/harness/inbox.sh 91 Docs/Airship/scripts/ue/as_91_r3_reimport.py 1200
# Report: Saved/Airship/as_91_r3_reimport.json. A FAIL after the import leaves the changes in memory, unsaved: restart the
# editor (quit_keep_lock.sh + launch.sh) before a re-run; to undo a saved run, restore the backup with the editor closed.
import json, math, os, time, traceback  # unreal = inbox namespace
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())

AS91_R = r3_report('as_91_r3_reimport')
AS91_FBX = {0: os.path.join(R3_SRC, 'SK_Airship.fbx'), 1: os.path.join(R3_SRC, 'SK_Airship_LOD1.fbx'),
            2: os.path.join(R3_SRC, 'SK_Airship_LOD2.fbx')}
AS91_LOD_DIST_M = globals().pop('AS91_LOD_DIST_M', (30.0, 80.0))
AS91_KEEP_PROPS_MATERIAL = globals().pop('AS91_KEEP_PROPS_MATERIAL', False)
AS91_SKIP_SCREEN_SIZES = globals().pop('AS91_SKIP_SCREEN_SIZES', False)     # True: type the two sizes by hand instead
AS91_THRESHOLD_UV = 1.0 / 65536
AS91_SLOTS = ['M_Airship', 'M_AirshipProps', 'M_AirshipR3_Detail']


def _o91(tag, msg):
    r3_o(AS91_R, tag, msg)


def as91_build_settings(sk, lod):
    """full-precision UVs, ThresholdUV 1/65536, FBX normals / tangents kept; returns True when it changed something"""
    smes = unreal.SkeletalMeshEditorSubsystem
    bs = smes.get_lod_build_settings(sk, lod)
    want = {'use_full_precision_u_vs': True, 'threshold_uv': AS91_THRESHOLD_UV, 'recompute_normals': False}
    changed = []
    for k, v in want.items():
        cur = r3_getp(bs, k)
        if cur is None:
            _o91('WARN', 'LOD%d build setting %s not readable' % (lod, k))
            continue
        if (abs(float(cur) - v) > 1e-9) if isinstance(v, float) else (bool(cur) != v):
            bs.set_editor_property(k, v)
            changed.append((k, cur, v))
    if changed:
        smes.set_lod_build_settings(sk, lod, bs)
    return changed


def as91_check_build(sk, lod):
    bs = unreal.SkeletalMeshEditorSubsystem.get_lod_build_settings(sk, lod)
    got = dict((k, r3_getp(bs, k)) for k in ('use_full_precision_u_vs', 'threshold_uv', 'recompute_normals',
                                              'recompute_tangents', 'use_mikk_t_space', 'use_high_precision_tangent_basis'))
    ok = bool(got['use_full_precision_u_vs']) and abs(float(got['threshold_uv']) - AS91_THRESHOLD_UV) < 1e-9 and not got['recompute_normals']
    _o91('PASS' if ok else 'FAIL', 'LOD%d build settings %s (want full-precision UVs, ThresholdUV %.3g, FBX normals)' % (
        lod, got, AS91_THRESHOLD_UV))
    return got


def as91_stored_pipeline(sk):
    """the Interchange pipeline stored in SK_Airship drives a re-import's build settings (UInterchangeGenericSkeletalMesh
    Pipeline: SetCustomUseFullPrecisionUVs / SetCustomThresholdUV): set full-precision UVs and ThresholdUV there too, so this
    and any later re-import keep them. Returns [(where, setting, before, after)]."""
    res = []
    ad = sk.get_editor_property('asset_import_data')
    if ad is None or type(ad).__name__ != 'InterchangeAssetImportData':
        return res
    for p in (ad.get_pipelines() or []):
        for sub, k, v in (('common_meshes_properties', 'use_full_precision_u_vs', True),
                          ('common_meshes_properties', 'recompute_normals', False),
                          ('mesh_pipeline', 'threshold_uv', AS91_THRESHOLD_UV)):
            o = r3_getp(p, sub)
            if o is None:
                continue
            cur = r3_getp(o, k)
            if cur is None:
                continue
            if (abs(float(cur) - v) > 1e-9) if isinstance(v, float) else bool(cur) != v:
                o.set_editor_property(k, v)
            res.append(('%s.%s' % (p.get_name(), sub), k, cur, r3_getp(o, k)))
    return res


def as91_reimport(sk):
    """the LOD0 re-import over SK_Airship; returns True on success"""
    ad = sk.get_editor_property('asset_import_data')
    kind = type(ad).__name__ if ad is not None else None
    AS91_R['data']['import_data'] = kind
    src0 = ''
    try:
        src0 = ad.get_first_filename()
    except Exception:  # noqa: BLE001
        pass
    _o91('INFO', 'SK_Airship import data %s, source %s' % (kind, src0))
    t0 = time.time()
    if kind == 'InterchangeAssetImportData':
        ad.scripted_add_filename(AS91_FBX[0], 0, '')
        src1 = ad.get_first_filename()
        _o91('PASS' if os.path.abspath(src1) == os.path.abspath(AS91_FBX[0]) else 'FAIL', 'source file -> %s' % src1)
        if os.path.abspath(src1) != os.path.abspath(AS91_FBX[0]):
            return False
        mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
        params = unreal.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        params.set_editor_property('replace_existing', True)
        r = mgr.reimport_asset(sk, params)
        ok = bool(r[0]) if isinstance(r, tuple) else (len(r) > 0 if isinstance(r, (list, unreal.Array)) else bool(r))
        _o91('PASS' if ok else 'FAIL', 'SK_Airship re-imported through the Interchange manager (stored pipeline) in %.1f s: %s'
             % (time.time() - t0, r))
        return ok
    # legacy FBX import data (or none): as_10's options through FbxFactory, the existing skeleton kept (as_56 patch 1)
    ui = unreal.FbxImportUI()
    E = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    for k, v in (('import_mesh', True), ('import_as_skeletal', True), ('mesh_type_to_import', E), ('original_import_type', E),
                 ('automated_import_should_detect_type', False), ('override_full_name', True), ('create_physics_asset', False),
                 ('import_animations', False), ('import_materials', False), ('import_textures', False),
                 ('skeleton', unreal.EditorAssetLibrary.load_asset(R3_SKEL))):
        r3_setp(AS91_R, ui, k, v)
    smd = ui.get_editor_property('skeletal_mesh_import_data')
    for k, v in (('import_content_type', unreal.FBXImportContentType.FBXICT_ALL),
                 ('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS), ('convert_scene', True),
                 ('force_front_x_axis', False), ('convert_scene_unit', False), ('import_uniform_scale', 1.0),
                 ('import_morph_targets', False), ('import_mesh_lods', False), ('use_t0_as_ref_pose', False),
                 ('update_skeleton_reference_pose', False), ('reorder_material_to_fbx_order', True),
                 ('import_meshes_in_bone_hierarchy', True)):
        r3_setp(AS91_R, smd, k, v, critical=False)
    if kind == 'FbxSkeletalMeshImportData':        # importing over it uses the STORED options (as_56 / as_53 lesson)
        for k, v in (('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS), ('convert_scene', True),
                     ('force_front_x_axis', False), ('convert_scene_unit', False), ('import_meshes_in_bone_hierarchy', True)):
            r3_setp(AS91_R, ad, k, v, critical=False)
    task = unreal.AssetImportTask()
    for k, v in (('filename', AS91_FBX[0]), ('destination_path', R3_D), ('destination_name', 'SK_Airship'),
                 ('replace_existing', True), ('automated', True), ('save', False), ('factory', unreal.FbxFactory()), ('options', ui)):
        task.set_editor_property(k, v)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = [str(p) for p in task.get_editor_property('imported_object_paths')]
    _o91('PASS' if paths else 'FAIL', 'SK_Airship re-imported with FbxFactory (legacy data) in %.1f s: %s' % (time.time() - t0, paths))
    return bool(paths)


def as91_folder_assets():
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    return dict((str(a.package_name), str(a.asset_class_path.asset_name)) for a in ar.get_assets_by_path(R3_D, recursive=False))


def as91_run():
    if r3_pie():
        _o91('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    inp = r3_inputs(AS91_R)
    if inp is None:
        return
    for p in [R3_SK, R3_SKEL, R3_PA] + list(R3_MI.values()):
        if not eal.does_asset_exist(p):
            _o91('FAIL', '%s missing (%s)' % (p, 'run as_90 first' if '/Materials/' in p else 'this is a RE-import'))
            return
    talal0 = r3_talal_state()
    r3_close_editors([R3_SK, R3_SKEL, R3_PA, R3_CR, R3_ABP, R3_BP])
    if r3_backup(AS91_R, [R3_SK, R3_SKEL, R3_PA], 'as_91') is None:
        return
    # 1. before
    sk = eal.load_asset(R3_SK)
    bones0 = r3_bone_table(sk)
    mesh_rest0 = r3_mesh_ref_bones(sk, [b[0] for b in bones0])
    sockets0 = r3_sockets(sk)
    pa0 = r3_pth(sk.get_editor_property('physics_asset'))
    pa_sha0 = r3_sha(r3_pkg_file(R3_PA))
    skel_sha0 = r3_sha(r3_pkg_file(R3_SKEL))
    folder0 = as91_folder_assets()
    AS91_R['data']['before'] = {'bones': len(bones0), 'sockets': sockets0, 'physics_asset': pa0, 'pa_sha256': pa_sha0,
                                'skeleton': r3_pth(sk.get_editor_property('skeleton')), 'lods': smes.get_lod_count(sk),
                                'slots': r3_slot_names(sk.materials)}
    _o91('INFO', 'before: %d bones, %d sockets, %d LODs, slots %s, PA %s' % (len(bones0), len(sockets0),
         smes.get_lod_count(sk), AS91_R['data']['before']['slots'], pa0))
    if len(bones0) != 118:
        _o91('FAIL', 'SK_Airship has %d bones before the import (want 118): not the round 2 asset' % len(bones0))
        return
    # 2. LOD0 build settings first (and in the stored Interchange pipeline, which a re-import applies)
    ch = as91_build_settings(sk, 0)
    _o91('INFO', 'LOD0 build settings set before the import: %s' % (ch or 'already right'))
    sp = as91_stored_pipeline(sk)
    AS91_R['data']['stored_pipeline'] = sp
    if sp:
        okp = all((abs(float(a) - AS91_THRESHOLD_UV) < 1e-9) if k == 'threshold_uv' else (bool(a) == (k == 'use_full_precision_u_vs'))
                  for _, k, _b, a in sp)
        _o91('PASS' if okp else 'FAIL', 'stored Interchange pipeline: %s' % [(k, b_, a) for _, k, b_, a in sp])
    else:
        _o91('INFO', 'no stored Interchange pipeline settings (legacy import data): the build settings carry the values')
    # 3. re-import
    if not as91_reimport(sk):
        return
    sk = eal.load_asset(R3_SK)
    # 4. checks
    folder1 = as91_folder_assets()
    new = dict((p, c) for p, c in folder1.items() if p not in folder0)
    _o91('PASS' if not [p for p, c in new.items() if c in ('Skeleton', 'PhysicsAsset')] else 'FAIL',
         'no new skeleton / physics asset (new assets: %s)' % new)
    skel = sk.get_editor_property('skeleton')
    _o91('PASS' if r3_pkg(skel) == R3_SKEL else 'FAIL', 'skeleton %s' % r3_pth(skel))
    bones1 = r3_bone_table(sk)
    same_names = [b[0] for b in bones1] == [b[0] for b in bones0]
    same_par = [b[1] for b in bones1] == [b[1] for b in bones0]
    dpos = max((max(abs(a[2][i] - b[2][i]) for i in range(3)) for a, b in zip(bones0, bones1)), default=99.0)
    drot = max(b[3] for b in bones1)
    _o91('PASS' if len(bones1) == 118 and same_names and same_par and dpos <= 0.01 and drot <= 0.01 else 'FAIL',
         'skeleton unchanged: %d bones, names / order %s, parents %s, rest positions within %.4f cm, rotations <= %.4f deg'
         % (len(bones1), same_names, same_par, dpos, drot))
    # review fix: r3_bone_table reads SKEL_Airship's reference pose; the MESH's own reference skeleton is what skins
    # (they diverged in round 2: as_56 _as56_mesh_rest)
    mesh_rest1 = r3_mesh_ref_bones(sk, [b[0] for b in bones1])
    AS91_R['data']['mesh_ref_skeleton'] = {'before': len(mesh_rest0), 'after': len(mesh_rest1)}
    if mesh_rest0 and mesh_rest1:
        dm_ = max((max(abs(mesh_rest0[n][i] - mesh_rest1[n][i]) for i in range(3)) for n in mesh_rest0 if n in mesh_rest1), default=99.0)
        dsk = max((max(abs(mesh_rest1[b[0]][i] - b[2][i]) for i in range(3)) for b in bones1 if b[0] in mesh_rest1), default=99.0)
        _o91('PASS' if len(mesh_rest1) == 118 and set(mesh_rest1) == set(mesh_rest0) and dm_ <= 0.01 and dsk <= 0.5 else 'FAIL',
             'mesh reference skeleton unchanged: %d bones, rest positions within %.4f cm of before; vs SKEL_Airship\'s '
             'reference pose %.3f cm' % (len(mesh_rest1), dm_, dsk))
    else:
        _o91('WARN', 'mesh reference skeleton not readable (SkeletonModifier): only SKEL_Airship\'s reference pose was compared')
    sockets1 = r3_sockets(sk)
    _o91('PASS' if sockets1 == sockets0 else 'FAIL', 'sockets unchanged (%d)%s' % (len(sockets1), '' if sockets1 == sockets0 else
         ': before %s after %s' % (sockets0, sockets1)))
    pa1 = r3_pth(sk.get_editor_property('physics_asset'))
    pa_dirty = R3_PA in r3_dirty()
    _o91('PASS' if pa1 == pa0 and r3_sha(r3_pkg_file(R3_PA)) == pa_sha0 and not pa_dirty else 'FAIL',
         'PA_Airship kept: pointer %s, file %s, dirty %s' % (pa1, 'unchanged' if r3_sha(r3_pkg_file(R3_PA)) == pa_sha0 else 'CHANGED', pa_dirty))
    names = r3_slot_names(sk.materials)
    AS91_R['data']['slots_after_import'] = names
    _o91('PASS' if sorted(names) == sorted(AS91_SLOTS) and len(names) == 3 else 'FAIL', 'material slots %s (want %s)' % (names, AS91_SLOTS))
    ch = as91_build_settings(sk, 0)
    if ch:
        _o91('WARN', 'the import reset LOD0 build settings %s: set again (mesh rebuilt)' % ch)
    as91_check_build(sk, 0)
    # 5. LODs
    for lod in (1, 2):
        t0 = time.time()
        r = smes.import_lod(sk, lod, AS91_FBX[lod])
        _o91('PASS' if r == lod else 'FAIL', 'LOD%d imported from %s in %.1f s (returned %s)' % (lod, os.path.basename(AS91_FBX[lod]), time.time() - t0, r))
        if r != lod:
            return
        sk = eal.load_asset(R3_SK)
        as91_build_settings(sk, lod)
        as91_check_build(sk, lod)
    nl = smes.get_lod_count(sk)
    _o91('PASS' if nl == 3 else 'FAIL', '%d LODs (want 3)' % nl)
    try:
        lods = sk.get_editor_property('lod_settings')
        _o91('PASS' if lods is None else 'WARN', 'no LOD settings asset (%s): the screen sizes below are the ones used' % r3_pth(lods))
    except Exception:  # noqa: BLE001
        pass
    bb = sk.get_imported_bounds()
    rad = float(bb.sphere_radius)
    sizes = {1: r3_screen_size(rad, AS91_LOD_DIST_M[0]), 2: r3_screen_size(rad, AS91_LOD_DIST_M[1])}
    sizes[0] = sizes[1] + 0.5      # LOD0's own value is not a threshold; kept above LOD1 so the editor's order rule holds
    if AS91_SKIP_SCREEN_SIZES:
        _o91('WARN', 'AS91_SKIP_SCREEN_SIZES: the JSON route is skipped. BY HAND: SK_Airship editor -> LOD1 -> LOD Info -> '
             'Screen Size %.3f, LOD2 -> %.3f, save' % (sizes[1], sizes[2]))
    ok_ss, msg, got, other_changed = r3_sk_set_screen_sizes(sk, sizes) if not AS91_SKIP_SCREEN_SIZES else (False, 'skipped', None, [])
    AS91_R['data']['screen_sizes'] = {'radius_cm': round(rad, 1), 'distances_m': AS91_LOD_DIST_M, 'want': sizes, 'now': got, 'how': msg,
                                      'other_source_model_fields_changed': other_changed}
    if other_changed:
        # review fix: the JSON route is not transactional; a source model also holds the build settings (full-precision
        # UVs, ThresholdUV), reduction settings and LODMaterialMap: never save an unexpected change there
        _o91('FAIL', 'the screen-size JSON route changed other SourceModels fields %s: NOT saved. Restart the editor without '
             'saving, run as_91 with AS91_SKIP_SCREEN_SIZES = True and type the sizes by hand (LOD1 %.3f, LOD2 %.3f)'
             % (other_changed, sizes[1], sizes[2]))
    elif not AS91_SKIP_SCREEN_SIZES:
        # WARN, not FAIL: refused with nothing changed; the LOD screen size is a draw-distance knob, two fields by hand
        _o91('PASS' if ok_ss else 'WARN', 'LOD screen sizes now %s, want %s (bounds radius %.0f cm: LOD1 from %.0f m, LOD2 from %.0f m at '
             'FOV 85); %s%s' % (got, [round(sizes[1], 3), round(sizes[2], 3)], rad, AS91_LOD_DIST_M[0], AS91_LOD_DIST_M[1], msg,
                               '' if ok_ss else '. BY HAND: SK_Airship editor -> LOD1 -> LOD Info -> Screen Size %.3f, LOD2 -> %.3f, save'
                               % (sizes[1], sizes[2])))
    want_tris = dict((int(k), v) for k, v in inp['sk']['tris'].items())
    per = {}
    for lod in range(nl):
        d = {'sections': smes.get_num_sections(sk, lod), 'render_verts': smes.get_num_verts(sk, lod),
             'source_tris': r3_geo_tris(sk, lod), 'uv_channels': r3_uv_sets(sk, lod)}
        per[lod] = d
        # review fix: USkeletalMesh has no UV-channel query (the old hasattr test was always False); GeometryScript's
        # GetNumUVSets on a copy of the LOD: MI_AirshipR3_Hull reads TexCoord[2], so every LOD must have 3
        ok = d['sections'] == 3 and (d['source_tris'] is None or d['source_tris'] == want_tris[lod]) and \
            (d['uv_channels'] is None or d['uv_channels'] == inp['sk'].get('uv_channels', 3))
        _o91('PASS' if ok else 'FAIL', 'LOD%d: %d sections (want 3), source triangles %s (FBX %d), render vertices %d, UV channels %s (want %d)'
             % (lod, d['sections'], d['source_tris'], want_tris[lod], d['render_verts'], d['uv_channels'], inp['sk'].get('uv_channels', 3)))
        if d['source_tris'] is None and lod == 0:
            _o91('WARN', 'GeometryScript not available: source triangles and UV channels not counted (the asset registry tag '
                 'below is LOD0; check UV channels 3 by hand in the SK editor: LOD Info -> UV channels)')
    AS91_R['data']['lods'] = per
    est = inp['sk'].get('render_vertices_est_lod0')
    if est:
        _o91('INFO', 'LOD0 render vertices %d; export estimate for SM_Airship + Moving %d (+ the props ~25k)' % (per[0]['render_verts'], est))
    try:
        ad_ = unreal.AssetRegistryHelpers.create_asset_data(sk)
        tags = dict((t, str(ad_.get_tag_value(t))) for t in ('Triangles', 'Vertices', 'Bones', 'MaterialSlots'))
        AS91_R['data']['tags'] = tags
        _o91('INFO', 'asset registry tags %s' % tags)
    except Exception as e:  # noqa: BLE001
        _o91('WARN', 'tags: %s' % e)
    # 6. material slots by name
    mats = sk.materials
    names = r3_slot_names(mats)
    for i, n in enumerate(names):
        key = R3_SLOT_MI.get(n)
        if key is None:
            _o91('FAIL', 'unexpected slot %d %s' % (i, n))
            continue
        want = R3_MATD + '/M_AirshipProps' if (key == 'props' and AS91_KEEP_PROPS_MATERIAL) else R3_MI[key]
        m = mats[i]
        if r3_pkg(m.get_editor_property('material_interface')) != want:
            m.set_editor_property('material_interface', eal.load_asset(want))
            mats[i] = m       # unreal.Array of structs hands out copies: write it back (as_61 lesson)
    try:
        sk.materials = mats
    except Exception as e:  # noqa: BLE001
        _o91('WARN', 'materials setter: %s; set_editor_property notify NEVER' % e)
        sk.set_editor_property('materials', mats, unreal.PropertyAccessChangeNotifyMode.NEVER)
    sk.modify()
    got = [(n, r3_pkg(m.get_editor_property('material_interface'))) for n, m in zip(r3_slot_names(sk.materials), sk.materials)]
    AS91_R['data']['slots'] = got
    AS91_R['data']['keep_props_material'] = bool(AS91_KEEP_PROPS_MATERIAL)
    ok = all(p == (R3_MATD + '/M_AirshipProps' if (R3_SLOT_MI[n] == 'props' and AS91_KEEP_PROPS_MATERIAL) else R3_MI[R3_SLOT_MI[n]])
             for n, p in got)
    _o91('PASS' if ok else 'FAIL', 'slots %s' % got)
    for lod in range(nl):
        try:
            sl = [smes.get_lod_material_slot(sk, lod, s) for s in range(smes.get_num_sections(sk, lod))]
            _o91('PASS' if sorted(sl) == [0, 1, 2] else 'FAIL', 'LOD%d sections -> slots %s' % (lod, sl))
        except Exception as e:  # noqa: BLE001
            _o91('WARN', 'LOD%d section slots: %s' % (lod, e))
    # 7. save
    if AS91_R['counts'].get('FAIL'):
        _o91('WARN', '%d FAIL: NOT saved (changes stay in memory: restart the editor before a re-run; restore the backup to undo)'
             % AS91_R['counts']['FAIL'])
        return
    save = [R3_SK] + ([R3_SKEL] if R3_SKEL in r3_dirty() else [])
    r3_save(AS91_R, save)
    _o91('PASS' if r3_sha(r3_pkg_file(R3_PA)) == pa_sha0 else 'FAIL', 'PA_Airship file unchanged after the save')
    _o91('INFO', 'SKEL_Airship %s' % ('saved (the import touched it)' if R3_SKEL in save else 'not changed, not saved'))
    r3_check_talal(AS91_R, talal0)
    _o91('INFO', 'NEXT: as_91b_r3_hull_detail.py (static mesh + BP component), as_91c_r3_turrets.py, as_92_r3_pa_stairs.py')


try:
    as91_run()
except Exception:  # noqa: BLE001
    _o91('FAIL', 'as_91 crashed: %s' % traceback.format_exc())
r3_finish(AS91_R)
