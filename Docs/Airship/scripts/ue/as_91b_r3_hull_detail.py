# as_91b_r3_hull_detail.py - round 3 (EXPORT_R3.md sections 1.2, 4, 6; EDITOR_STAGE_R3.md step 3): the 12 Hull-bone detail
# objects as ONE static mesh on the ship, so Nanite draws their 258k triangles (a skinned mesh would draw and skin every
# triangle in every pass, for 4 ships).
#   1. imports SourceArt/Airship/r3/SM_AirshipR3_HullDetail.fbx as /Game/Assets/MyShip/Drivable/SM_AirshipR3_HullDetail
#      (legacy FbxFactory as as_53: combine meshes, FBX normals, transform_vertex_to_absolute (the Y-up -> Z-up conversion
#      baked into the vertices; the node is the identity, so vertex = Mesh component space), no collision, no lightmap
#      UVs); re-imports over its own asset (Interchange data: the manager with the stored pipeline; legacy data: its stored
#      options set like this run first, the as_53 lesson);
#   2. LOD0 build settings: full-precision UVs (the non-Nanite fallback; Nanite keeps 14-bit UV mantissas), FBX normals;
#      LOD1 / LOD2 from SM_AirshipR3_HullDetail_LOD1/2.fbx (StaticMeshEditorSubsystem.import_lod) with the same settings,
#      screen sizes 1.94 * R / D at 30 m / 80 m from its bounds; Nanite ON (AS91B_NANITE False = off: then the LODs draw);
#   3. slot 0 = MI_AirshipR3_HullDetail (as_90), no simple collision;
#   4. checks: bounds = the export's (r3_unreal_inputs.json, +-1 cm: the mesh sits in Mesh component space, so in the
#      ship), source triangles per LOD = the FBX (GeometryScript, when there), 2 UV channels, 1 section;
#   5. BP_AirshipPawn: a StaticMeshComponent "HullDetail" under the inherited "Mesh" (SubobjectDataSubsystem), mesh =
#      SM_AirshipR3_HullDetail, collision profile NoCollision (UMechSentinelObstacleComponent and
#      UAirshipSubsystem::RepairPhysicsState skip components without collision; AirshipLaneComponent's bounds use
#      colliding components only), no overlap events, does not affect navigation, casts shadows, relative transform
#      identity. Parent socket: Python cannot set a Blueprint node's AttachToName (USCS_Node::AttachToName has no
#      editor flags), so the component sits on the Mesh component's origin. That is where the Hull bone is: rest pose at
#      the origin with no rotation (checked here) and kinematic (CR_Airship drives only the part bones; the wreck solver
#      is owned by Hull), so the result is the same. Optional by hand: BP editor -> HullDetail -> Sockets -> Parent
#      Socket: Hull. Re-runnable: an existing HullDetail component is reused and set again.
#   6. compiles BP_AirshipPawn; saves SM_AirshipR3_HullDetail and BP_AirshipPawn only (explicit paths); backups first.
# Run (clone editor, no PIE, BP_AirshipPawn editor closed):
#   Docs/Airship/scripts/harness/inbox.sh 91b Docs/Airship/scripts/ue/as_91b_r3_hull_detail.py 900
# Report: Saved/Airship/as_91b_r3_hull_detail.json
import json, os, time, traceback  # unreal = inbox namespace
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())

AS91B_R = r3_report('as_91b_r3_hull_detail')
AS91B_NANITE = globals().pop('AS91B_NANITE', True)
AS91B_LOD_DIST_M = (30.0, 80.0)
AS91B_FBX = {0: os.path.join(R3_SRC, 'SM_AirshipR3_HullDetail.fbx'), 1: os.path.join(R3_SRC, 'SM_AirshipR3_HullDetail_LOD1.fbx'),
             2: os.path.join(R3_SRC, 'SM_AirshipR3_HullDetail_LOD2.fbx')}
AS91B_COMP = 'HullDetail'


def _o(tag, msg):
    r3_o(AS91B_R, tag, msg)


def as91b_ui():
    ui = unreal.FbxImportUI()
    E = unreal.FBXImportType.FBXIT_STATIC_MESH
    ok = True
    for k, v in (('import_mesh', True), ('import_as_skeletal', False), ('mesh_type_to_import', E), ('original_import_type', E),
                 ('automated_import_should_detect_type', False), ('override_full_name', True), ('import_materials', False),
                 ('import_textures', False), ('import_animations', False), ('create_physics_asset', False)):
        ok &= r3_setp(AS91B_R, ui, k, v)
    smd = ui.get_editor_property('static_mesh_import_data')
    for k, v in (('convert_scene', True), ('force_front_x_axis', False), ('convert_scene_unit', False), ('import_uniform_scale', 1.0),
                 ('import_translation', unreal.Vector(0.0, 0.0, 0.0)), ('import_rotation', unreal.Rotator(0.0, 0.0, 0.0)),
                 ('combine_meshes', True), ('auto_generate_collision', False),
                 ('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS),
                 ('transform_vertex_to_absolute', True), ('bake_pivot_in_vertex', False)):
        ok &= r3_setp(AS91B_R, smd, k, v)
    for k, v in (('build_nanite', bool(AS91B_NANITE)), ('generate_lightmap_u_vs', False), ('remove_degenerates', True),
                 ('reorder_material_to_fbx_order', True), ('vertex_color_import_option', unreal.VertexColorImportOption.IGNORE)):
        r3_setp(AS91B_R, smd, k, v, critical=False)
    try:
        r3_setp(AS91B_R, ui.get_editor_property('texture_import_data'), 'material_search_location',
                unreal.MaterialSearchLocation.DO_NOT_SEARCH, critical=False)
    except Exception:  # noqa: BLE001
        pass
    return ui, ok


def as91b_import(eal):
    fbx = AS91B_FBX[0]
    if eal.does_asset_exist(R3_HD):
        old = eal.load_asset(R3_HD)
        if not isinstance(old, unreal.StaticMesh):
            _o('FAIL', '%s exists and is a %s: not touched' % (R3_HD, type(old).__name__))
            return None
        ad = old.get_editor_property('asset_import_data')
        src = ''
        try:
            src = ad.get_first_filename()
        except Exception:  # noqa: BLE001
            pass
        if src and os.path.basename(src) != os.path.basename(fbx):
            _o('FAIL', '%s was imported from %s: not ours, not touched' % (R3_HD, src))
            return None
        if ad is not None and type(ad).__name__ == 'InterchangeAssetImportData':
            ad.scripted_add_filename(fbx, 0, '')
            params = unreal.ImportAssetParameters()
            params.set_editor_property('is_automated', True)
            params.set_editor_property('replace_existing', True)
            r = unreal.InterchangeManager.get_interchange_manager_scripted().reimport_asset(old, params)
            ok = bool(r[0]) if isinstance(r, tuple) else bool(r)
            _o('PASS' if ok else 'FAIL', 're-imported %s through the Interchange manager (stored pipeline): %s' % (R3_HD, ok))
            return eal.load_asset(R3_HD) if ok else None
        if ad is not None and type(ad).__name__ == 'FbxStaticMeshImportData':
            for k, v in (('transform_vertex_to_absolute', True), ('bake_pivot_in_vertex', False), ('convert_scene', True),
                         ('force_front_x_axis', False), ('convert_scene_unit', False), ('combine_meshes', True),
                         ('auto_generate_collision', False), ('build_nanite', bool(AS91B_NANITE)),
                         ('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)):
                r3_setp(AS91B_R, ad, k, v, critical=False)
            _o('INFO', 'stored import options of %s set like this run' % R3_HD)
    ui, ok = as91b_ui()
    if not ok:
        _o('FAIL', 'import options incomplete: not imported')
        return None
    task = unreal.AssetImportTask()
    for k, v in (('filename', fbx), ('destination_path', R3_D), ('destination_name', R3_HD.rsplit('/', 1)[1]), ('replace_existing', True),
                 ('replace_existing_settings', True), ('automated', True), ('save', False), ('factory', unreal.FbxFactory()), ('options', ui)):
        r3_setp(AS91B_R, task, k, v, critical=k != 'replace_existing_settings')
    t0 = time.time()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = [str(p) for p in task.get_editor_property('imported_object_paths')]
    sm = eal.load_asset(R3_HD) if eal.does_asset_exist(R3_HD) else None
    _o('PASS' if isinstance(sm, unreal.StaticMesh) else 'FAIL', 'imported %s in %.1f s -> %s' % (os.path.basename(fbx), time.time() - t0, paths))
    return sm if isinstance(sm, unreal.StaticMesh) else None


def as91b_build(sms, sm, lod):
    bs = sms.get_lod_build_settings(sm, lod)
    ch = []
    for k, v in (('use_full_precision_u_vs', True), ('recompute_normals', False), ('generate_lightmap_u_vs', False)):
        cur = r3_getp(bs, k)
        if cur is not None and bool(cur) != v:
            bs.set_editor_property(k, v)
            ch.append((k, cur, v))
    if ch:
        sms.set_lod_build_settings(sm, lod, bs)
    bs = sms.get_lod_build_settings(sm, lod)
    got = dict((k, r3_getp(bs, k)) for k in ('use_full_precision_u_vs', 'recompute_normals', 'recompute_tangents', 'generate_lightmap_u_vs'))
    _o('PASS' if got['use_full_precision_u_vs'] and not got['recompute_normals'] and not got['generate_lightmap_u_vs'] else 'FAIL',
       'LOD%d build settings %s%s' % (lod, got, ' (changed %s)' % ch if ch else ''))


def as91b_mesh(eal, inp):
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    sm = as91b_import(eal)
    if sm is None:
        return None
    as91b_build(sms, sm, 0)
    for lod in (1, 2):
        r = sms.import_lod(sm, lod, AS91B_FBX[lod])
        _o('PASS' if r == lod else 'FAIL', 'LOD%d from %s (returned %s)' % (lod, os.path.basename(AS91B_FBX[lod]), r))
        if r != lod:
            return None
        as91b_build(sms, sm, lod)
    n = sms.get_lod_count(sm)
    _o('PASS' if n == 3 else 'FAIL', '%d LODs (want 3)' % n)
    try:
        # review fix: with Nanite on, LOD0's render data is the Nanite fallback cut (StaticMeshBuilder.cpp: "replace the
        # output VertexBuffers ... with the fractional Nanite cut ... as LOD0 RenderData"); the default FallbackTarget Auto
        # / FallbackRelativeError 1.0 reduces it, so r.Nanite 0, an SM5 target and ray tracing would draw a simplified
        # detail mesh up close. PercentTriangles 1.0 keeps all of our LOD0 as the fallback (LOD1 / LOD2 from 30 / 80 m).
        ns = sms.get_nanite_settings(sm)
        want_ns = (('enabled', bool(AS91B_NANITE)), ('fallback_target', unreal.NaniteFallbackTarget.PERCENT_TRIANGLES),
                   ('fallback_percent_triangles', 1.0))
        if any(str(r3_getp(ns, k)) != str(v) for k, v in want_ns):
            for k, v in want_ns:
                ns.set_editor_property(k, v)
            sms.set_nanite_settings(sm, ns, True)
        ns = sms.get_nanite_settings(sm)
        got_ns = dict((k, str(r3_getp(ns, k))) for k, _ in want_ns)
        _o('PASS' if all(got_ns[k] == str(v) for k, v in want_ns) else 'FAIL',
           'Nanite %s, fallback %s (want Nanite %s, fallback PercentTriangles 1.0 = the full LOD0)' % (
               got_ns['enabled'], got_ns, AS91B_NANITE))
    except Exception as e:  # noqa: BLE001
        _o('FAIL', 'Nanite settings: %s' % e)
    bb = sm.get_bounding_box()
    rad = 0.5 * ((bb.max.x - bb.min.x) ** 2 + (bb.max.y - bb.min.y) ** 2 + (bb.max.z - bb.min.z) ** 2) ** 0.5
    s1, s2 = r3_screen_size(rad, AS91B_LOD_DIST_M[0]), r3_screen_size(rad, AS91B_LOD_DIST_M[1])
    # SetLodScreenSizes keeps them strictly decreasing (and turns auto-compute off): LOD0 goes above LOD1 (its own value is
    # not a threshold); 1.0 for LOD0 would clamp LOD1's 1.7 down to 1.0 (= 47 m instead of 30 m)
    sizes = [s1 + 0.5, s1, s2]
    sms.set_lod_screen_sizes(sm, sizes)
    got = [round(x, 4) for x in sms.get_lod_screen_sizes(sm)]
    _o('PASS' if len(got) == 3 and all(abs(got[i] - sizes[i]) < 1e-3 for i in (1, 2)) else 'FAIL',
       'LOD screen sizes %s (radius %.0f cm: 30 m / 80 m at FOV 85; used when Nanite is off)' % (got, rad))
    mi = eal.load_asset(R3_MI['hulldetail'])
    for i in range(len(sm.get_editor_property('static_materials'))):
        sm.set_material(i, mi)
    mats = [r3_pkg(m.get_editor_property('material_interface')) for m in sm.get_editor_property('static_materials')]
    _o('PASS' if mats == [R3_MI['hulldetail']] else 'FAIL', 'material slots %s (want [MI_AirshipR3_HullDetail])' % mats)
    nc = sms.get_simple_collision_count(sm)
    if nc:
        sms.remove_collisions(sm)
    _o('PASS' if sms.get_simple_collision_count(sm) == 0 else 'FAIL', 'simple collision shapes %d (removed %d)' % (sms.get_simple_collision_count(sm), nc))
    want_b = inp['hull_detail']['bounds_ue_cm']
    mn, mx = [bb.min.x, bb.min.y, bb.min.z], [bb.max.x, bb.max.y, bb.max.z]
    d = max(max(abs(mn[i] - want_b['min_cm'][i]), abs(mx[i] - want_b['max_cm'][i])) for i in range(3))
    _o('PASS' if d <= 1.0 else 'FAIL', 'bounds min %s max %s vs the export %s: %.2f cm (Mesh component space = the ship)'
       % ([round(x, 1) for x in mn], [round(x, 1) for x in mx], want_b, d))
    want_t = dict((int(k), v) for k, v in inp['hull_detail']['tris'].items())
    for lod in range(n):
        st = r3_geo_tris(sm, lod)
        nuv = sms.get_num_uv_channels(sm, lod)
        nsec = None
        try:
            nsec = sm.get_num_sections(lod)
        except Exception:  # noqa: BLE001
            pass
        ok = nuv == 2 and (st is None or st == want_t[lod]) and nsec in (None, 1)
        _o('PASS' if ok else 'FAIL', 'LOD%d: source triangles %s (FBX %d), UV channels %d (want 2), sections %s, render vertices %s'
           % (lod, st, want_t[lod], nuv, nsec, sms.get_number_verts(sm, lod)))
    return sm


def as91b_component(eal, sm):
    """BP_AirshipPawn: HullDetail under Mesh; returns the blueprint or None"""
    bp = eal.load_asset(R3_BP)
    if bp is None:
        _o('FAIL', '%s missing' % R3_BP)
        return None
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    by_name = {}
    for h in handles:
        d = lib.get_data(h)
        by_name[str(lib.get_variable_name(d))] = (h, d)
    if 'Mesh' not in by_name:
        _o('FAIL', 'BP_AirshipPawn has no Mesh subobject (found %s)' % sorted(by_name))
        return None
    mesh_h = by_name['Mesh'][0]
    if AS91B_COMP in by_name:
        h, d = by_name[AS91B_COMP]
        _o('INFO', 'reusing the existing %s component' % AS91B_COMP)
    else:
        p = unreal.AddNewSubobjectParams()
        p.set_editor_property('parent_handle', mesh_h)
        p.set_editor_property('new_class', unreal.StaticMeshComponent)
        p.set_editor_property('blueprint_context', bp)
        r = sds.add_new_subobject(p)
        h = r[0] if isinstance(r, tuple) else r
        if not lib.is_handle_valid(h):
            _o('FAIL', 'add_new_subobject failed: %s' % (r,))
            return None
        ok = sds.rename_subobject(h, unreal.Text(AS91B_COMP))
        _o('PASS' if ok else 'FAIL', 'added a StaticMeshComponent under Mesh, renamed %s: %s' % (AS91B_COMP, ok))
        d = lib.get_data(h)
    comp = lib.get_object_for_blueprint(d, bp) if hasattr(lib, 'get_object_for_blueprint') else lib.get_object(d)
    if comp is None:
        comp = lib.get_object(d)
    if not isinstance(comp, unreal.StaticMeshComponent):
        _o('FAIL', '%s is a %s, not a StaticMeshComponent' % (AS91B_COMP, type(comp).__name__))
        return None
    parent_ok = lib.is_attached_to(lib.get_data(h), mesh_h)
    if not parent_ok:
        rp = unreal.ReparentSubobjectParams()
        rp.set_editor_property('new_parent_handle', mesh_h)
        rp.set_editor_property('blueprint_context', bp)
        sds.reparent_subobject(rp, h)
        parent_ok = lib.is_attached_to(lib.get_data(h), mesh_h)
    _o('PASS' if parent_ok else 'FAIL', '%s attached to Mesh' % AS91B_COMP)
    comp.modify()
    comp.set_editor_property('static_mesh', sm)
    for k, v in (('relative_location', unreal.Vector(0.0, 0.0, 0.0)), ('relative_rotation', unreal.Rotator(0.0, 0.0, 0.0)),
                 ('relative_scale3d', unreal.Vector(1.0, 1.0, 1.0)), ('generate_overlap_events', False),
                 ('can_ever_affect_navigation', False), ('cast_shadow', True)):
        r3_setp(AS91B_R, comp, k, v, critical=k.startswith('relative'))
    try:
        comp.set_collision_profile_name('NoCollision')
    except Exception as e:  # noqa: BLE001
        _o('WARN', 'set_collision_profile_name: %s; set_collision_enabled NO_COLLISION' % e)
    try:
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    except Exception as e:  # noqa: BLE001
        _o('WARN', 'set_collision_enabled: %s' % e)
    _o('INFO', 'parent socket: not settable from Python (USCS_Node::AttachToName); the component sits on the Mesh origin = '
       'the Hull bone (checked below). Optional by hand: BP_AirshipPawn -> %s -> Sockets -> Parent Socket: Hull' % AS91B_COMP)
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    st = bp.get_editor_property('status')
    _o('PASS' if st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS) else 'FAIL',
       'BP_AirshipPawn compiled: %s' % st)
    return bp


def as91b_check_component(eal):
    bp = eal.load_asset(R3_BP)
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    found = None
    mesh_h = None
    for h in sds.k2_gather_subobject_data_for_blueprint(bp):
        d = lib.get_data(h)
        n = str(lib.get_variable_name(d))
        if n == 'Mesh':
            mesh_h = h
        if n == AS91B_COMP:
            found = (h, d)
    if found is None:
        _o('FAIL', 'after compile: no %s component' % AS91B_COMP)
        return
    comp = lib.get_object(found[1])
    info = {'static_mesh': r3_pkg(r3_getp(comp, 'static_mesh')), 'collision_profile': str(comp.get_collision_profile_name()),
            'collision_enabled': str(comp.get_collision_enabled()), 'overlaps': r3_getp(comp, 'generate_overlap_events'),
            'nav': r3_getp(comp, 'can_ever_affect_navigation'), 'cast_shadow': r3_getp(comp, 'cast_shadow'),
            'attached_to_mesh': bool(mesh_h is not None and lib.is_attached_to(found[1], mesh_h)),
            'relative': [str(r3_getp(comp, 'relative_location')), str(r3_getp(comp, 'relative_rotation')), str(r3_getp(comp, 'relative_scale3d'))]}
    AS91B_R['data']['component'] = info
    rl, rr, rs = r3_getp(comp, 'relative_location'), r3_getp(comp, 'relative_rotation'), r3_getp(comp, 'relative_scale3d')
    ident = rl.length() < 0.01 and abs(rr.pitch) + abs(rr.yaw) + abs(rr.roll) < 0.01 and abs(rs.x - 1) + abs(rs.y - 1) + abs(rs.z - 1) < 1e-4
    ok = info['static_mesh'] == R3_HD and 'NO_COLLISION' in info['collision_enabled'].upper().replace(' ', '_') and \
        info['attached_to_mesh'] and ident and not info['overlaps'] and not info['nav']
    _o('PASS' if ok else 'FAIL', 'BP_AirshipPawn.%s %s' % (AS91B_COMP, info))
    # the Hull bone is where the component sits
    sk = eal.load_asset(R3_SK)
    pose = unreal.AnimPoseExtensions.get_reference_pose(sk.get_editor_property('skeleton'))
    t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, 'Hull', unreal.AnimPoseSpaces.WORLD)
    off = (t.translation.length(), abs(abs(t.rotation.w) - 1.0))
    _o('PASS' if off[0] < 0.01 and off[1] < 1e-6 else 'FAIL', 'Hull bone rest at the component origin, no rotation '
       '(%.4f cm, |q.w| - 1 = %.2e): HullDetail without a socket = HullDetail on the Hull bone' % off)
    try:
        mesh_comp = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp)).get_editor_property('Mesh')
        ov = [r3_pth(m) for m in (r3_getp(mesh_comp, 'override_materials') or [])]
        _o('PASS' if not [m for m in ov if m] else 'WARN', 'Mesh component material overrides %s (none: the SK slots apply)' % ov)
    except Exception as e:  # noqa: BLE001
        _o('WARN', 'Mesh overrides unreadable: %s' % e)


def as91b_run():
    if r3_pie():
        _o('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    inp = r3_inputs(AS91B_R)
    if inp is None:
        return
    for p in (R3_MI['hulldetail'], R3_BP, R3_SK):
        if not eal.does_asset_exist(p):
            _o('FAIL', '%s missing (run as_90 / as_91 first)' % p)
            return
    talal0 = r3_talal_state()
    r3_close_editors([R3_HD, R3_BP])
    if r3_backup(AS91B_R, [R3_HD, R3_BP], 'as_91b') is None:
        return
    sm = as91b_mesh(eal, inp)
    if sm is None:
        return
    if AS91B_R['counts'].get('FAIL'):
        _o('WARN', 'mesh FAIL: component not added, nothing saved')
        return
    bp = as91b_component(eal, sm)
    if bp is None:
        return
    as91b_check_component(eal)
    if AS91B_R['counts'].get('FAIL'):
        _o('WARN', '%d FAIL: NOT saved (restart the editor before a re-run)' % AS91B_R['counts']['FAIL'])
        return
    r3_save(AS91B_R, [R3_HD, R3_BP])
    r3_check_talal(AS91B_R, talal0)
    _o('INFO', 'NEXT: as_91c_r3_turrets.py, then as_92_r3_pa_stairs.py')


try:
    as91b_run()
except Exception:  # noqa: BLE001
    _o('FAIL', 'as_91b crashed: %s' % traceback.format_exc())
r3_finish(AS91B_R)
