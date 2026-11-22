# as_10_import.py - airship UE session 2 step 1: import SK_Airship.fbx as /Game/Assets/MyShip/Drivable/SK_Airship with a
# new skeleton SKEL_Airship (legacy FbxFactory, the Burrower bw_02 route), assign the two materials, import the test
# sweep SK_Airship_testanim.fbx onto SKEL_Airship as A_Airship_TestSweep, then check everything against
# rig/checks/rig/bones_ue.csv (README_rig.md). Re-runnable: EXISTING 'reuse' (default) only fixes up + checks.
# Run:  Docs/Airship/scripts/harness/inbox.sh 10 Docs/Airship/scripts/ue/as_10_import.py 900
# Output lines PASS:/FAIL:/WARN:/INFO:, last line RESULT:. Report: Saved/Airship/as_10_import.json
import os, json, math, time, traceback  # unreal = the inbox namespace (pt_guard proxy)


def _as10():
    import os, json, math, time, traceback
    W = os.path.abspath(unreal.Paths.project_dir())
    FBX = os.path.join(W, 'SourceArt/Airship/SK_Airship.fbx')
    FBX_ANIM = os.path.join(W, 'SourceArt/Airship/SK_Airship_testanim.fbx')
    CSV = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/checks/rig/bones_ue.csv'
    FOLDER = '/Game/Assets/MyShip/Drivable'
    SK = FOLDER + '/SK_Airship'
    SKEL = FOLDER + '/SKEL_Airship'
    ANIM = FOLDER + '/A_Airship_TestSweep'
    MAT0 = '/Game/Assets/MyShip/M_Airship'
    MAT1 = FOLDER + '/Materials/M_AirshipProps'
    g = globals()
    EXISTING = g.pop('AS10_EXISTING', 'reuse')     # 'reuse' | 'reimport'
    POS_TOL = 2.0
    ROT_TOL_DEG = 0.01
    R = {'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}, 'data': {}}

    def out(tag, msg):
        R['counts'][tag] = R['counts'].get(tag, 0) + 1
        print('%s: %s' % (tag, msg))

    def check(ok, msg, warn_only=False):
        out('PASS' if ok else ('WARN' if warn_only else 'FAIL'), msg)
        return ok

    def en(enum_name, value):
        return getattr(getattr(unreal, enum_name), value)

    def setp(obj, prop, value, critical=True):
        try:
            obj.set_editor_property(prop, value)
            return True
        except Exception as e:
            out('FAIL' if critical else 'WARN', 'set %s.%s: %s' % (obj.get_class().get_name(), prop, e))
            return False

    def pkg(o):
        try:
            return o.get_path_name().split('.')[0] if o else None
        except Exception:
            return None

    eal = unreal.EditorAssetLibrary

    def folder_assets():
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        res = {}
        for ad in ar.get_assets_by_path(FOLDER, recursive=False):
            res[str(ad.package_name)] = str(ad.asset_class_path.asset_name)
        return res

    def common_ui(ui):
        smd = ui.get_editor_property('skeletal_mesh_import_data')
        ok = True
        ok &= setp(smd, 'import_content_type', en('FBXImportContentType', 'FBXICT_ALL'))
        ok &= setp(smd, 'normal_import_method', en('FBXNormalImportMethod', 'FBXNIM_IMPORT_NORMALS'))
        for d in (smd, ui.get_editor_property('anim_sequence_import_data')):
            ok &= setp(d, 'convert_scene', True)
            ok &= setp(d, 'force_front_x_axis', False)
            ok &= setp(d, 'convert_scene_unit', False)
            ok &= setp(d, 'import_uniform_scale', 1.0)
            ok &= setp(d, 'import_translation', unreal.Vector(0.0, 0.0, 0.0))
            ok &= setp(d, 'import_rotation', unreal.Rotator(0.0, 0.0, 0.0))
        ok &= setp(smd, 'import_morph_targets', False)
        ok &= setp(smd, 'import_mesh_lods', False)
        ok &= setp(smd, 'use_t0_as_ref_pose', False)
        ok &= setp(smd, 'update_skeleton_reference_pose', False)
        setp(smd, 'keep_sections_separate', False, False)
        setp(smd, 'preserve_smoothing_groups', True, False)
        setp(smd, 'import_meshes_in_bone_hierarchy', True, False)
        setp(smd, 'import_vertex_attributes', False, False)
        setp(smd, 'bake_pivot_in_vertex', False, False)
        setp(smd, 'reorder_material_to_fbx_order', True, False)
        try:
            setp(smd, 'vertex_color_import_option', en('VertexColorImportOption', 'IGNORE'), False)
        except Exception as e:
            out('WARN', 'vertex color option: %s' % e)
        try:
            tex = ui.get_editor_property('texture_import_data')
            setp(tex, 'material_search_location', en('MaterialSearchLocation', 'DO_NOT_SEARCH'), False)
        except Exception as e:
            out('WARN', 'material_search_location: %s' % e)
        return ok

    def run_task(fname, dest_name, ui):
        task = unreal.AssetImportTask()
        setp(task, 'filename', fname)
        setp(task, 'destination_path', FOLDER)
        setp(task, 'destination_name', dest_name)
        setp(task, 'replace_existing', True)
        setp(task, 'replace_existing_settings', False, False)
        setp(task, 'automated', True)
        setp(task, 'save', False)
        setp(task, 'factory', unreal.FbxFactory())   # explicit legacy factory: Interchange bypassed
        setp(task, 'options', ui)
        t0 = time.time()
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        try:
            paths = [str(p) for p in task.get_editor_property('imported_object_paths')]
        except Exception:
            paths = []
        out('INFO', 'import %s took %.1f s -> %s' % (os.path.basename(fname), time.time() - t0, paths))
        return paths

    def import_mesh():
        ui = unreal.FbxImportUI()
        t = en('FBXImportType', 'FBXIT_SKELETAL_MESH')
        ok = True
        ok &= setp(ui, 'import_mesh', True)
        ok &= setp(ui, 'import_as_skeletal', True)
        ok &= setp(ui, 'mesh_type_to_import', t)
        ok &= setp(ui, 'original_import_type', t)
        ok &= setp(ui, 'automated_import_should_detect_type', False)
        ok &= setp(ui, 'override_full_name', True)
        ok &= setp(ui, 'create_physics_asset', False)
        setp(ui, 'physics_asset', None, False)
        ok &= setp(ui, 'import_animations', False)
        ok &= setp(ui, 'import_materials', False)
        ok &= setp(ui, 'import_textures', False)
        ok &= setp(ui, 'skeleton', None)
        ok &= common_ui(ui)
        if not ok:
            out('FAIL', 'mesh import options incomplete: import not started')
            return None
        return run_task(FBX, 'SK_Airship', ui)

    def import_anim(skel):
        ui = unreal.FbxImportUI()
        t = en('FBXImportType', 'FBXIT_ANIMATION')
        ok = True
        ok &= setp(ui, 'import_mesh', False)
        ok &= setp(ui, 'import_as_skeletal', True)
        ok &= setp(ui, 'mesh_type_to_import', t)
        ok &= setp(ui, 'original_import_type', t)
        ok &= setp(ui, 'automated_import_should_detect_type', False)
        ok &= setp(ui, 'override_full_name', True)
        ok &= setp(ui, 'create_physics_asset', False)
        ok &= setp(ui, 'import_animations', True)
        ok &= setp(ui, 'import_materials', False)
        ok &= setp(ui, 'import_textures', False)
        ok &= setp(ui, 'skeleton', skel)
        ok &= common_ui(ui)
        ad = ui.get_editor_property('anim_sequence_import_data')
        setp(ad, 'import_bone_tracks', True, False)
        setp(ad, 'import_custom_attribute', False, False)
        setp(ad, 'import_meshes_in_bone_hierarchy', True, False)
        try:
            setp(ad, 'animation_length', en('FBXAnimationLengthImportType', 'FBXALIT_EXPORTED_TIME'), False)
        except Exception as e:
            out('WARN', 'animation_length: %s' % e)
        if not ok:
            out('FAIL', 'anim import options incomplete: import not started')
            return None
        return run_task(FBX_ANIM, 'A_Airship_TestSweep', ui)

    # ------------------------------------------------------------------------------------------- run
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        out('FAIL', 'PIE running: nothing done')
        return R
    out('INFO', 'FBX %s (%d bytes), EXISTING=%s, Interchange FBX flag=%s' % (
        FBX, os.path.getsize(FBX), EXISTING,
        unreal.SystemLibrary.get_console_variable_bool_value('Interchange.FeatureFlags.Import.FBX')))
    before = folder_assets()
    skm = eal.load_asset(SK) if eal.does_asset_exist(SK) else None
    if skm is None or EXISTING == 'reimport':
        if skm is not None:
            out('INFO', 'reimporting over the existing SK_Airship (skeleton kept)')
        import_mesh()
        skm = eal.load_asset(SK) if eal.does_asset_exist(SK) else None
        if skm is None:
            out('FAIL', 'SK_Airship not created (see LogFbx in Saved/Logs/Aura.log)')
            return R
    else:
        out('INFO', 'SK_Airship exists: reuse (no import), fix-ups + checks only')
    # new assets of this import that must not exist
    for p, cls in folder_assets().items():
        if p not in before and cls in ('PhysicsAsset', 'AnimSequence'):
            out('WARN', 'the import made %s %s although off: deleting it' % (cls, p))
            if cls == 'PhysicsAsset' and pkg(skm.get_editor_property('physics_asset')) == p:
                skm.set_editor_property('physics_asset', None)
            eal.delete_asset(p)

    # skeleton -> SKEL_Airship
    skel = skm.get_editor_property('skeleton')
    sp = pkg(skel)
    if sp != SKEL:
        if not sp or not sp.startswith(FOLDER + '/'):
            out('FAIL', 'skeleton %s is not ours; not renamed' % sp)
        elif eal.does_asset_exist(SKEL):
            out('FAIL', 'mesh uses %s but %s exists too: not renamed' % (sp, SKEL))
        else:
            ok = eal.rename_asset(sp, SKEL)
            check(ok, 'renamed skeleton %s -> %s' % (sp, SKEL))
            skel = eal.load_asset(SKEL)
    else:
        out('PASS', 'skeleton is %s' % SKEL)
    skm = eal.load_asset(SK)
    skel = skm.get_editor_property('skeleton')

    # materials: slot 0 M_Airship, slot 1 M_AirshipProps (attribute setter = no mesh rebuild)
    m0, m1 = eal.load_asset(MAT0), eal.load_asset(MAT1)
    mats = skm.materials
    names = []
    for m in mats:
        nm = str(m.get_editor_property('imported_material_slot_name'))
        if nm in ('None', ''):
            nm = str(m.get_editor_property('material_slot_name'))
        names.append(nm)
    R['data']['slot_names'] = names
    check(len(mats) == 2, 'material slots %d: %s (want 2: M_Airship, M_AirshipProps)' % (len(mats), names))
    changed = False
    for i, m in enumerate(mats):
        want = m0 if i == 0 else m1
        if pkg(m.get_editor_property('material_interface')) != pkg(want):
            m.set_editor_property('material_interface', want)
            mats[i] = m
            changed = True
    if changed:
        try:
            skm.materials = mats
        except Exception as e:
            out('WARN', 'materials setter: %s; set_editor_property notify NEVER' % e)
            skm.set_editor_property('materials', mats, en('PropertyAccessChangeNotifyMode', 'NEVER'))
        skm.modify()
        out('INFO', 'assigned slot 0 = %s, slot 1 = %s' % (MAT0, MAT1))
    mats = skm.materials
    got = [pkg(m.get_editor_property('material_interface')) for m in mats]
    check(len(got) == 2 and got[0] == MAT0 and got[1] == MAT1 and 'M_Airship' in names[0] and 'Props' in names[1],
          'slots: %s -> %s' % (names, got))
    for p, m in ((MAT0, m0), (MAT1, m1)):
        try:
            u = m.get_editor_property('used_with_skeletal_mesh')
            out('PASS' if u else 'WARN', '%s used_with_skeletal_mesh = %s' % (p, u))
            R['data']['skel_usage_' + p.rsplit('/', 1)[1]] = bool(u)
        except Exception as e:
            out('WARN', 'cannot read used_with_skeletal_mesh on %s: %s' % (p, e))

    # ------------------------------------------------------------------------------------------- checks
    rows = []
    with open(CSV) as f:
        hdr = f.readline().strip().split(',')
        for line in f:
            c = line.strip().split(',')
            if len(c) >= 5:
                rows.append({'bone': c[0], 'parent': c[1] or None, 'pos': (float(c[2]), float(c[3]), float(c[4]))})
    exp = dict((r['bone'], r) for r in rows)
    APE = unreal.AnimPoseExtensions
    pose = APE.get_reference_pose(skel)
    bnames = [str(n) for n in APE.get_bone_names(pose)]
    R['data']['bone_count'] = len(bnames)
    check(len(bnames) == 118 and len(rows) == 118, 'bones %d (csv %d, want 118)' % (len(bnames), len(rows)))
    missing = [b for b in exp if b not in bnames]
    extra = [b for b in bnames if b not in exp]
    check(not missing and not extra, 'bone names vs csv: missing %s extra %s' % (missing, extra))
    SMES = unreal.SkeletalMeshEditorSubsystem
    par = {}
    for b in bnames:
        p = str(SMES.get_bone_parent(skm, b))
        par[b] = None if p in ('None', '') else p
    roots = [b for b in bnames if par[b] is None]
    check(roots == ['root'], 'root bone(s) %s (want [root], no Armature bone above it)' % roots)
    badp = [(b, par[b], exp[b]['parent']) for b in bnames if b in exp and par[b] != exp[b]['parent']]
    check(not badp, '%d/%d parents as in the contract csv%s' % (len(bnames) - len(badp), len(bnames),
                                                               '' if not badp else ' wrong: %s' % badp[:10]))
    W_ = en('AnimPoseSpaces', 'WORLD')
    worst, worst_b, worst_rot, worst_rb = 0.0, None, 0.0, None
    bad = []
    pos = {}
    for b in bnames:
        t = APE.get_ref_bone_pose(pose, b, W_)
        p = (t.translation.x, t.translation.y, t.translation.z)
        pos[b] = p
        q = t.rotation
        ang = math.degrees(2.0 * math.acos(min(1.0, abs(q.w))))
        if ang > worst_rot:
            worst_rot, worst_rb = ang, b
        if b in exp:
            e = exp[b]['pos']
            d = math.sqrt(sum((p[i] - e[i]) ** 2 for i in range(3)))
            if d > worst:
                worst, worst_b = d, b
            if d > POS_TOL:
                bad.append((b, [round(x, 2) for x in p], e, round(d, 2)))
        ts = t.scale3d
        if max(abs(ts.x - 1), abs(ts.y - 1), abs(ts.z - 1)) > 1e-4:
            bad.append((b, 'scale', (ts.x, ts.y, ts.z)))
    R['data']['positions'] = dict((k, [round(x, 3) for x in v]) for k, v in pos.items())
    R['data']['worst_pos_cm'] = [worst_b, round(worst, 4)]
    R['data']['worst_rot_deg'] = [worst_rb, worst_rot]
    check(not bad, 'rest positions within %.0f cm of bones_ue.csv (worst %s %.4f cm)%s' % (
        POS_TOL, worst_b, worst, '' if not bad else ' off: %s' % bad[:10]))
    check(worst_rot <= ROT_TOL_DEG, 'every bone component-space rest rotation identity (worst %s %.5f deg)' % (
        worst_rb, worst_rot))
    for b in ('Cannon_L1', 'Thruster_FL', 'Helm_Wheel', 'Cannon_R2_Muzzle', 'Turbine_L_Rotor', 'SearchLight_FwdC_Head'):
        out('INFO', '%-22s at (%.2f, %.2f, %.2f)' % ((b,) + tuple(pos[b])))
    check(pos['SearchLight_FwdC'][0] > 2500 and pos['Rudder'][0] < -1500 and pos['Thruster_FL'][0] > pos['Thruster_RL'][0],
          'bow +X (FwdC searchlight x %.0f, rudder x %.0f)' % (pos['SearchLight_FwdC'][0], pos['Rudder'][0]))
    port = [pos['Cannon_L1_Muzzle'][1], pos['Cannon_L2_Muzzle'][1], pos['Thruster_FL'][1], pos['Turbine_L'][1]]
    check(all(y < 0 for y in port) and pos['Cannon_R1_Muzzle'][1] > 0,
          'port (L) parts at -Y: L muzzles y %.1f / %.1f, Thruster_FL %.1f, Turbine_L %.1f; R1 muzzle %.1f' % (
              tuple(port) + (pos['Cannon_R1_Muzzle'][1],)))
    try:
        bb = skm.get_imported_bounds()
        o, e = bb.origin, bb.box_extent
        mn = (o.x - e.x, o.y - e.y, o.z - e.z)
        mx = (o.x + e.x, o.y + e.y, o.z + e.z)
        size = tuple(mx[i] - mn[i] for i in range(3))
        R['data']['bounds_min'], R['data']['bounds_max'] = [round(x, 1) for x in mn], [round(x, 1) for x in mx]
        check(abs(size[0] - 5190) < 150 and abs(size[1] - 2390) < 150 and abs(size[2] - 1700) < 150,
              'bounds %.0f x %.0f x %.0f cm (want ~5190 x 2390 x 1700); x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f' % (
                  size + (mn[0], mx[0], mn[1], mx[1], mn[2], mx[2])))
    except Exception as ex:
        out('FAIL', 'bounds: %s' % ex)
    try:
        smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        nsec = smes.get_num_sections(skm, 0)
        R['data']['lod0_sections'] = nsec
        R['data']['lod_count'] = SMES.get_lod_count(skm)
        R['data']['lod0_verts'] = smes.get_num_verts(skm, 0)
        out('INFO', 'LODs %d, LOD0 sections %d, render verts %d' % (R['data']['lod_count'], nsec, R['data']['lod0_verts']))
        bs = SMES.get_lod_build_settings(skm, 0)
        check(not bs.get_editor_property('recompute_normals'), 'LOD0 recompute_normals False (FBX normals kept)')
    except Exception as ex:
        out('WARN', 'sections/build settings: %s' % ex)
    try:
        ad = unreal.AssetRegistryHelpers.create_asset_data(skm)
        tags = {}
        for t in ('Triangles', 'Vertices', 'Bones', 'NaniteEnabled', 'MorphTargets'):
            v = ad.get_tag_value(t)
            tags[t] = None if v is None else str(v)
        R['data']['tags'] = tags
        check(tags.get('Triangles') and abs(int(tags['Triangles']) - 104730) <= 600,
              'triangles %s (FBX 104730)' % tags.get('Triangles'))
        out('INFO', 'tags %s' % tags)
    except Exception as ex:
        out('WARN', 'tags: %s' % ex)
    try:
        aid = skm.get_editor_property('asset_import_data')
        vals = dict((k, str(aid.get_editor_property(k))) for k in ('force_front_x_axis', 'convert_scene',
                                                                    'convert_scene_unit', 'normal_import_method'))
        R['data']['import_options'] = vals
        check(vals['force_front_x_axis'] == 'False' and vals['convert_scene'] == 'True', 'stored import options %s' % vals)
    except Exception as ex:
        out('WARN', 'import data: %s' % ex)

    # ------------------------------------------------------------------------------------------- test animation
    anim = eal.load_asset(ANIM) if eal.does_asset_exist(ANIM) else None
    if anim is None:
        if pkg(skel) != SKEL:
            out('FAIL', 'skeleton not %s yet: test anim not imported' % SKEL)
        else:
            import_anim(skel)
            anim = eal.load_asset(ANIM) if eal.does_asset_exist(ANIM) else None
    if anim is None:
        new = [p for p, c in folder_assets().items() if c == 'AnimSequence']
        out('FAIL', 'A_Airship_TestSweep not found (anim sequences in the folder: %s)' % new)
    else:
        try:
            ln = anim.get_editor_property('sequence_length') if hasattr(anim, 'sequence_length') else None
        except Exception:
            ln = None
        try:
            ln = unreal.AnimationLibrary.get_sequence_length(anim)
        except Exception:
            pass
        try:
            nk = unreal.AnimationLibrary.get_num_frames(anim)
        except Exception:
            nk = None
        R['data']['anim_length_s'] = ln
        R['data']['anim_frames'] = nk
        check(pkg(anim.get_editor_property('skeleton')) == SKEL, 'A_Airship_TestSweep skeleton %s' % pkg(
            anim.get_editor_property('skeleton')))
        check(ln is not None and abs(ln - 32.0) < 0.2, 'test sweep length %s s, frames %s (want 32 s, 960/961)' % (ln, nk))
        for p, c in folder_assets().items():
            if c == 'AnimSequence' and p != ANIM:
                out('WARN', 'extra animation %s' % p)

    # ------------------------------------------------------------------------------------------- save
    fails = R['counts']['FAIL']
    to_save = [SK, SKEL] + ([ANIM] if anim is not None else [])
    if fails:
        out('WARN', '%d FAIL: NOT saving (assets stay in memory)' % fails)
    else:
        for p in to_save:
            ok = eal.save_asset(p, only_if_is_dirty=False)
            check(ok, 'saved %s' % p)
    R['data']['folder'] = folder_assets()
    return R


try:
    _as10_r = _as10()
except Exception:
    print('FAIL: as_10 crashed: %s' % traceback.format_exc())
    _as10_r = {'counts': {'FAIL': 1}}
try:
    _d = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
    os.makedirs(_d, exist_ok=True)
    with open(os.path.join(_d, 'as_10_import.json'), 'w') as _f:
        json.dump(_as10_r, _f, indent=1, default=str)
except Exception as _e:
    print('WARN: report not written %r' % (_e,))
print('RESULT: %s %s' % ('PASS' if not _as10_r['counts'].get('FAIL') else 'FAIL', _as10_r['counts']))
