# as_91c_r3_turrets.py - round 3 (EXPORT_R3.md 13.7 "Turrets"; EDITOR_STAGE_R3.md step 4): the two machine-gun turret
# meshes get the props recolour (palette slots 18 / 19 in their new UV1, MI_AirshipR3_Props), like the cannons and the
# helm in SK_Airship's slot 1. Wrapper around as_53_turret_import.py, run with checked in-memory text patches (each must
# match exactly once, else nothing runs; as_56's way of reusing as_10):
#   1. the FBX folder SourceArt/Airship -> SourceArt/Airship/r3 (r3_export_static.py: the same frames, pivots and UV0 as
#      round 2's export_turret.py, checked by r3_fbx_check.py against round 2's FBX; plus UV1 R3Palette);
#   2. turret_dims.json still read from SourceArt/Airship (unchanged: same geometry);
#   3. the material: M_AirshipProps -> MI_AirshipR3_Props (as_90);
#   4. as_53 does not save and writes its own report as Saved/Airship/as_91c_as53_turret_import.json (round 2's report
#      is left as it is); its RESULT line is renamed "as_53 part".
# as_53 itself: legacy FbxFactory re-import over its own assets (their stored options set first), combine meshes, FBX
# normals, transform_vertex_to_absolute, no collision, Nanite off, bounds against turret_dims.json.
# Then this script: LOD0 build settings full-precision UVs (the props page is 2048: half floats are 0.5 texel off),
# 2 UV channels, slot = MI_AirshipR3_Props, bounds = the export's (+-0.5 cm), BP_AirshipTurret's mesh components have no
# material overrides (read only), saves the two meshes by explicit path. Backups first (Saved/Airship/backup_r3/).
# AS91C_KEEP_PROPS_MATERIAL = True keeps M_AirshipProps (then only the UV1 / precision change lands).
# Review fix (2026-11-28, EXPORT_R3.md 15): both turret meshes carry InterchangeAssetImportData (round 2) whose source is
# SourceArt/Airship/SM_AirshipTurret_*.fbx, and as_53 re-imports such a mesh with the STORED source file, so patch 1 alone
# re-imported round 2's FBX (1 UV layer). Before as_53 runs, each Interchange-imported turret's source file is pointed at
# SourceArt/Airship/r3/<name>.fbx (scripted_add_filename, as as_91 / as_91b do) and checked; full-precision UVs also go
# into its stored pipeline; after as_53 the source file must still be the r3 one.
# Run (clone editor, no PIE): Docs/Airship/scripts/harness/inbox.sh 91c Docs/Airship/scripts/ue/as_91c_r3_turrets.py 300
# Report: Saved/Airship/as_91c_r3_turrets.json
import json, os, traceback  # unreal = inbox namespace
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())

AS91C_R = r3_report('as_91c_r3_turrets')
AS91C_KEEP_PROPS_MATERIAL = globals().pop('AS91C_KEEP_PROPS_MATERIAL', False)
AS91C_AS53 = os.path.join(R3_W, 'Docs/Airship/scripts/ue/as_53_turret_import.py')


def _o(tag, msg):
    r3_o(AS91C_R, tag, msg)


def as91c_patched_as53():
    mat = R3_MATD + '/M_AirshipProps' if AS91C_KEEP_PROPS_MATERIAL else R3_MI['props']
    src = open(AS91C_AS53).read()
    patches = [
        ("SRC = os.path.join(W, 'SourceArt/Airship')\n", "SRC = os.path.join(W, 'SourceArt/Airship/r3')   # as_91c\n"),
        ("DIMS = os.path.join(SRC, 'turret_dims.json')\n", "DIMS = os.path.join(W, 'SourceArt/Airship/turret_dims.json')   # as_91c\n"),
        ("MAT = '/Game/Assets/MyShip/Drivable/Materials/M_AirshipProps'\n", "MAT = '%s'   # as_91c\n" % mat),
        ("    for name, _ in MESHES:\n        p = '%s/%s' % (FOLDER, name)\n        ok = unreal.EditorAssetLibrary.save_asset(p, only_if_is_dirty=False)\n"
         "        o('PASS' if ok else 'FAIL', 'saved %s' % p)\n",
         "    o('INFO', 'as_91c: not saved here (as_91c saves after its own steps)')\n"),
        ("'as_53_turret_import.json'", "'as_91c_as53_turret_import.json'"),
        ("print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))", "print('as_53 part: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))"),
    ]
    for old, new in patches:
        n = src.count(old)
        if n != 1:
            raise RuntimeError('as_53_turret_import.py changed: patch target found %d times (want 1): %r' % (n, old.strip()[:80]))
        src = src.replace(old, new)
    return src, mat


def as91c_run():
    if r3_pie():
        _o('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    inp = r3_inputs(AS91C_R)
    if inp is None:
        return
    if not eal.does_asset_exist(R3_MI['props']) and not AS91C_KEEP_PROPS_MATERIAL:
        _o('FAIL', '%s missing: run as_90 first' % R3_MI['props'])
        return
    talal0 = r3_talal_state()
    pk = list(R3_TURRET.values())
    r3_close_editors(pk + [R3_TURRET_BP])
    if r3_backup(AS91C_R, pk, 'as_91c') is None:
        return
    # review fix: point each Interchange-imported turret at the r3 FBX before as_53's re-import (it uses the stored source)
    for name, path in R3_TURRET.items():
        want = os.path.join(R3_SRC, name + '.fbx')
        sm = eal.load_asset(path) if eal.does_asset_exist(path) else None
        ad = sm.get_editor_property('asset_import_data') if sm is not None else None
        kind = type(ad).__name__ if ad is not None else None
        if kind == 'InterchangeAssetImportData':
            before = ad.get_first_filename()
            ad.scripted_add_filename(want, 0, '')
            got = ad.get_first_filename()
            okp = os.path.abspath(got) == os.path.abspath(want)
            _o('PASS' if okp else 'FAIL', '%s source file %s -> %s (Interchange data: as_53 re-imports the stored source)' % (name, before, got))
            if not okp:
                return
            for p_ in (ad.get_pipelines() or []):
                cm = r3_getp(p_, 'common_meshes_properties')
                if cm is not None and r3_getp(cm, 'use_full_precision_u_vs') is not None:
                    cm.set_editor_property('use_full_precision_u_vs', True)
                    _o('INFO', '%s stored pipeline %s: use_full_precision_u_vs %s' % (name, p_.get_name(), r3_getp(cm, 'use_full_precision_u_vs')))
        else:
            _o('INFO', '%s import data %s: as_53 imports the patched path %s directly' % (name, kind, want))
    AS91C_R['data']['keep_props_material'] = bool(AS91C_KEEP_PROPS_MATERIAL)
    src, mat = as91c_patched_as53()
    _o('INFO', 'running as_53_turret_import.py (patched: r3 FBX, material %s, no save) ------------------------' % mat)
    g = {'unreal': unreal, '__name__': '__as53__'}
    exec(compile(src, AS91C_AS53 + ' (as_91c patched)', 'exec'), g)
    c53 = g.get('CNT') or {}
    _o('PASS' if not c53.get('FAIL') else 'FAIL', '---- as_53 counts %s' % c53)
    if c53.get('FAIL'):
        return
    for name, path in R3_TURRET.items():
        sm = eal.load_asset(path)
        bs = sms.get_lod_build_settings(sm, 0)
        if not r3_getp(bs, 'use_full_precision_u_vs'):
            bs.set_editor_property('use_full_precision_u_vs', True)
            sms.set_lod_build_settings(sm, 0, bs)
        full = bool(r3_getp(sms.get_lod_build_settings(sm, 0), 'use_full_precision_u_vs'))
        nuv = sms.get_num_uv_channels(sm, 0)
        mats = [r3_pkg(m.get_editor_property('material_interface')) for m in sm.get_editor_property('static_materials')]
        bb = sm.get_bounding_box()
        want = inp['turrets'][name]['bounds_ue_cm']
        d = max(max(abs([bb.min.x, bb.min.y, bb.min.z][i] - want['min_cm'][i]), abs([bb.max.x, bb.max.y, bb.max.z][i] - want['max_cm'][i]))
                for i in range(3))
        srcf = ''
        try:
            srcf = sm.get_editor_property('asset_import_data').get_first_filename()
        except Exception:  # noqa: BLE001
            pass
        from_r3 = os.path.abspath(srcf or '') == os.path.abspath(os.path.join(R3_SRC, name + '.fbx'))
        ok = full and nuv == 2 and mats == [mat] and d <= 0.5 and from_r3
        _o('PASS' if ok else 'FAIL', '%s: full-precision UVs %s, UV channels %d (want 2), slots %s, bounds vs the export %.2f cm, '
           'render vertices %d, source file %s (r3: %s)' % (name, full, nuv, mats, d, sms.get_number_verts(sm, 0), srcf, from_r3))
    try:
        bp = eal.load_asset(R3_TURRET_BP)
        cdo = unreal.get_default_object(unreal.BlueprintEditorLibrary.generated_class(bp))
        ov = {}
        for c in ('BaseMesh', 'GunMesh'):
            comp = cdo.get_editor_property(c)
            ov[c] = (r3_pkg(r3_getp(comp, 'static_mesh')), [r3_pth(m) for m in (r3_getp(comp, 'override_materials') or []) if m])
        good = all(not v[1] for v in ov.values()) and ov['BaseMesh'][0] == R3_TURRET['SM_AirshipTurret_Base'] and \
            ov['GunMesh'][0] == R3_TURRET['SM_AirshipTurret_Gun']
        _o('PASS' if good else 'WARN', 'BP_AirshipTurret components (mesh, material overrides) %s: no overrides = the MI shows' % ov)
    except Exception as e:  # noqa: BLE001
        _o('WARN', 'BP_AirshipTurret not readable: %s' % e)
    if AS91C_R['counts'].get('FAIL'):
        _o('WARN', '%d FAIL: NOT saved (restart the editor before a re-run)' % AS91C_R['counts']['FAIL'])
        return
    r3_save(AS91C_R, pk)
    r3_check_talal(AS91C_R, talal0)
    _o('INFO', 'NEXT: as_92_r3_pa_stairs.py')


try:
    as91c_run()
except Exception:  # noqa: BLE001
    _o('FAIL', 'as_91c crashed: %s' % traceback.format_exc())
r3_finish(AS91C_R)
