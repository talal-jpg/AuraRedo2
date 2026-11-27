# as_61_hull_ink.py - round 2 hull ink fix (risk 7 of NOTES_assets.md): the drivable ship's hull gets its own comic
# texture, re-baked without the five deck pieces round 2 removed (no more black rectangles / bar where they stood).
#   1. imports SourceArt/Airship/textures/T_AirshipDrivable_ComicLines.png (made by
#      SourceArt/Airship/scripts/hull_ink_drivable.py) as /Game/Assets/MyShip/Drivable/Textures/T_AirshipDrivable_ComicLines
#      and gives it the settings of Talal's /Game/Assets/MyShip/T_Airship_ComicLines, read at run time (compression,
#      sRGB, mip generation, LOD group, address X/Y, filter, streaming / VT, ...);
#   2. makes the drivable hull material: M_Airship is a Material -> duplicate it to
#      /Game/Assets/MyShip/Drivable/Materials/M_AirshipDrivable and point only the sample that holds T_Airship_ComicLines
#      at the new texture (matched by expression name, as as_02b does; every other expression untouched); if M_Airship
#      were a material instance -> MI copy MI_AirshipDrivable with the texture parameter that holds T_Airship_ComicLines
#      set to the new texture. bUsedWithSkeletalMesh checked (set on our copy if missing);
#   3. assigns it to SK_Airship's material slot 0 (slot 1 M_AirshipProps unchanged; attribute setter as as_10, no mesh
#      rebuild);
#   4. saves only those three assets by explicit path (nothing when anything FAILs) and verifies: texture size and
#      settings = the original's, source file = the PNG, the material uses the new texture and no longer Talal's,
#      SK_Airship slots, Talal's M_Airship / T_Airship_ComicLines / T_Airship_ComicMask / SM_Airship not dirty and their
#      .uasset files unchanged.
# as_10_import.py (and so as_56) assigns slot 0 = M_AirshipDrivable once it exists, so a later SK re-import keeps it.
# Re-runnable: re-imports over its own texture (refuses an asset of that name that isn't a Texture2D or came from another
# file), reuses its material copy (refuses one whose expressions don't match M_Airship's).
# Run (clone editor, no PIE): Docs/Airship/scripts/harness/inbox.sh 61 Docs/Airship/scripts/ue/as_61_hull_ink.py 300
# Report: Saved/Airship/as_61_hull_ink.json
import hashlib, json, os, struct, traceback  # unreal = inbox namespace
try:
    unreal
except NameError:  # run outside the inbox
    import unreal

AS61_W = os.path.abspath(unreal.Paths.project_dir())
AS61_PNG = os.path.join(AS61_W, 'SourceArt/Airship/textures/T_AirshipDrivable_ComicLines.png')
AS61_BAKE_REPORT = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/checks/hull_ink/hull_ink_report.json'
AS61_SRC_TEX = '/Game/Assets/MyShip/T_Airship_ComicLines'
AS61_SRC_MAT = '/Game/Assets/MyShip/M_Airship'
AS61_TALAL = ['/Game/Assets/MyShip/M_Airship', '/Game/Assets/MyShip/T_Airship_ComicLines',
              '/Game/Assets/MyShip/T_Airship_ComicMask', '/Game/Assets/MyShip/SM_Airship']
AS61_TEX_DIR = '/Game/Assets/MyShip/Drivable/Textures'
AS61_TEX_NAME = 'T_AirshipDrivable_ComicLines'
AS61_TEX = AS61_TEX_DIR + '/' + AS61_TEX_NAME
AS61_MAT_DIR = '/Game/Assets/MyShip/Drivable/Materials'
AS61_SK = '/Game/Assets/MyShip/Drivable/SK_Airship'
AS61_PROPS_MAT = AS61_MAT_DIR + '/M_AirshipProps'
# texture settings copied from Talal's texture: the first six must match (FAIL), the rest are copied when both have them
AS61_TEX_CORE = ['compression_settings', 'srgb', 'mip_gen_settings', 'lod_group', 'address_x', 'address_y']
AS61_TEX_MORE = ['filter', 'never_stream', 'virtual_texture_streaming', 'compression_no_alpha', 'compression_quality',
                 'max_texture_size', 'lod_bias', 'power_of_two_mode', 'lossy_compression_amount', 'mip_load_options',
                 'preserve_border', 'flip_green_channel', 'adjust_brightness', 'adjust_brightness_curve',
                 'adjust_vibrance', 'adjust_saturation', 'adjust_rgb_curve', 'adjust_hue', 'adjust_min_alpha',
                 'adjust_max_alpha']
AS61_R = {'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}}


def _o61(tag, msg):
    AS61_R['counts'][tag] = AS61_R['counts'].get(tag, 0) + 1
    AS61_R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def _sha61(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _md5_61(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _pkg_file61(pkg):
    return os.path.join(AS61_W, 'Content', pkg[len('/Game/'):] + '.uasset')


def _pkg61(o):
    try:
        return o.get_path_name().split('.')[0] if o else None
    except Exception:  # noqa: BLE001
        return None


def _dirty61():
    return [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]


def _png_header61(p):
    """(width, height, bit depth, colour type) from the PNG's IHDR"""
    with open(p, 'rb') as f:
        head = f.read(33)
    if head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
        return None
    w, h = struct.unpack('>II', head[16:24])
    return w, h, head[24], head[25]


def _source_file61(asset):
    try:
        aid = asset.get_editor_property('asset_import_data')
        fn = aid.get_first_filename() if hasattr(aid, 'get_first_filename') else None
        if not fn and hasattr(aid, 'extract_filenames') and aid.extract_filenames():
            fn = str(aid.extract_filenames()[0])
        return fn
    except Exception:  # noqa: BLE001
        return None


def _getp61(obj, prop):
    try:
        return True, obj.get_editor_property(prop)
    except Exception:  # noqa: BLE001
        return False, None


def _texture_expressions61(mat):
    return [e for e in unreal.ObjectIterator(unreal.MaterialExpressionTextureBase) if e.get_outer() == mat]


def _all_expressions61(mat):
    return [e for e in unreal.ObjectIterator(unreal.MaterialExpression) if e.get_outer() == mat]


def as61_import_texture(eal):
    """import (or re-import over our own) T_AirshipDrivable_ComicLines; returns the texture or None"""
    if eal.does_asset_exist(AS61_TEX):
        old = eal.load_asset(AS61_TEX)
        if not isinstance(old, unreal.Texture2D):
            _o61('FAIL', '%s exists and is a %s, not a Texture2D: not touched' % (AS61_TEX, old.get_class().get_name()))
            return None
        src = _source_file61(old)
        if src and os.path.basename(src) != os.path.basename(AS61_PNG):
            _o61('FAIL', '%s was imported from %s, not %s: not ours, not touched' % (AS61_TEX, src, os.path.basename(AS61_PNG)))
            return None
        _o61('INFO', 're-importing over %s (was from %s)' % (AS61_TEX, src))
    t = unreal.AssetImportTask()
    for k, v in (('filename', AS61_PNG), ('destination_path', AS61_TEX_DIR), ('destination_name', AS61_TEX_NAME),
                 ('automated', True), ('replace_existing', True), ('save', False)):
        t.set_editor_property(k, v)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    paths = [str(p) for p in t.get_editor_property('imported_object_paths')]
    tex = eal.load_asset(AS61_TEX) if eal.does_asset_exist(AS61_TEX) else None
    ok = isinstance(tex, unreal.Texture2D)
    _o61('PASS' if ok else 'FAIL', 'imported %s -> %s %s' % (os.path.basename(AS61_PNG), AS61_TEX, paths))
    return tex if ok else None


def as61_copy_settings(src, tex):
    """Talal's texture settings onto ours; only the values that differ are set (each set rebuilds the texture)"""
    res = {}
    for p in AS61_TEX_CORE + AS61_TEX_MORE:
        core = p in AS61_TEX_CORE
        ok_s, want = _getp61(src, p)
        ok_t, have = _getp61(tex, p)
        if not (ok_s and ok_t):
            if core:
                _o61('FAIL', 'texture setting %s not readable (source %s, ours %s)' % (p, ok_s, ok_t))
            continue
        if str(have) != str(want):
            try:
                tex.set_editor_property(p, want)
            except Exception as e:  # noqa: BLE001
                _o61('FAIL' if core else 'WARN', 'set %s = %s: %s' % (p, want, e))
                continue
        res[p] = {'original': str(want), 'before': str(have), 'now': str(tex.get_editor_property(p))}
    return res


def as61_material(eal, tex, src_tex):
    """the drivable hull material (Material copy or MI copy); returns (material, its path) or (None, None)"""
    MEL = unreal.MaterialEditingLibrary
    src = eal.load_asset(AS61_SRC_MAT)
    if src is None:
        _o61('FAIL', '%s missing' % AS61_SRC_MAT)
        return None, None
    AS61_R['source_material_class'] = src.get_class().get_name()
    if isinstance(src, unreal.Material):
        path = AS61_MAT_DIR + '/M_AirshipDrivable'
        src_map = dict((e.get_name(), (_pkg61(e.get_editor_property('texture')), e.get_editor_property('sampler_type')))
                       for e in _texture_expressions61(src))
        hold = [n for n, (tp, _) in src_map.items() if tp == AS61_SRC_TEX]
        _o61('PASS' if len(hold) == 1 else 'FAIL', 'M_Airship (Material): texture samples %s; the one with T_Airship_ComicLines: %s'
             % (dict((n, tp) for n, (tp, _) in src_map.items()), hold))
        if len(hold) != 1:
            return None, None
        if eal.does_asset_exist(path):
            m = eal.load_asset(path)
            if not isinstance(m, unreal.Material):
                _o61('FAIL', '%s exists and is a %s, not a Material: not touched' % (path, m.get_class().get_name()))
                return None, None
            _o61('INFO', 'reusing %s' % path)
        else:
            m = eal.duplicate_asset(AS61_SRC_MAT, path)
            _o61('PASS' if m else 'FAIL', 'duplicated %s -> %s' % (AS61_SRC_MAT, path))
            if not m:
                return None, None
        names_src = sorted(e.get_name() for e in _all_expressions61(src))
        names_dup = sorted(e.get_name() for e in _all_expressions61(m))
        if names_src != names_dup:
            _o61('FAIL', '%s expressions differ from M_Airship (%d vs %d): not ours or edited, not touched'
                 % (path, len(names_dup), len(names_src)))
            return None, None
        for e in _texture_expressions61(m):
            tp, st = src_map[e.get_name()]
            if e.get_name() == hold[0]:
                e.set_editor_property('texture', tex)
                e.set_editor_property('sampler_type', st)
            elif _pkg61(e.get_editor_property('texture')) != tp:
                e.set_editor_property('texture', eal.load_asset(tp))      # a re-run never leaves another sample changed
                e.set_editor_property('sampler_type', st)
            AS61_R.setdefault('samples', {})[e.get_name()] = [_pkg61(e.get_editor_property('texture')),
                                                              str(e.get_editor_property('sampler_type'))]
        _o61('INFO', 'samples of %s: %s' % (path, AS61_R['samples']))
        # skeletal mesh usage on our copy (M_Airship has it since as_42; the duplicate keeps the flags)
        u = m.get_editor_property('used_with_skeletal_mesh')
        if not u:
            ok = MEL.set_base_material_usage(m, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, True)
            _o61('INFO', 'set bUsedWithSkeletalMesh on %s: %s' % (path, ok))
        MEL.recompile_material(m)
        flags = {}
        for k in ('used_with_skeletal_mesh', 'used_with_morph_targets', 'used_with_static_lighting', 'used_with_instanced_static_meshes',
                  'used_with_nanite'):
            ok_s, vs = _getp61(src, k)
            ok_m, vm = _getp61(m, k)
            if ok_s and ok_m:
                flags[k] = [bool(vs), bool(vm)]
        AS61_R['usage_flags_source_copy'] = flags
        _o61('PASS' if m.get_editor_property('used_with_skeletal_mesh') else 'FAIL',
             '%s bUsedWithSkeletalMesh = %s (usage flags M_Airship / copy: %s)' % (path, m.get_editor_property('used_with_skeletal_mesh'), flags))
        diffs = [k for k, (a, b) in flags.items() if a and not b]
        if diffs:
            _o61('WARN', 'usage flags M_Airship has but the copy lost: %s' % diffs)
        for k in ('shading_model', 'blend_mode', 'two_sided'):
            a, b = _getp61(src, k)[1], _getp61(m, k)[1]
            _o61('PASS' if str(a) == str(b) else 'FAIL', '%s: M_Airship %s, copy %s' % (k, a, b))
        return m, path
    if isinstance(src, unreal.MaterialInstanceConstant):
        path = AS61_MAT_DIR + '/MI_AirshipDrivable'
        names = [str(n) for n in MEL.get_texture_parameter_names(src)]
        hold = [n for n in names if _pkg61(MEL.get_material_instance_texture_parameter_value(src, n)) == AS61_SRC_TEX]
        _o61('PASS' if len(hold) == 1 else 'FAIL', 'M_Airship (material instance): texture parameters %s; holding T_Airship_ComicLines: %s'
             % (names, hold))
        if len(hold) != 1:
            return None, None
        if eal.does_asset_exist(path):
            m = eal.load_asset(path)
            if not isinstance(m, unreal.MaterialInstanceConstant) or _pkg61(m.get_editor_property('parent')) != _pkg61(src.get_editor_property('parent')):
                _o61('FAIL', '%s exists but is not an MI of the same parent: not touched' % path)
                return None, None
        else:
            m = eal.duplicate_asset(AS61_SRC_MAT, path)
            _o61('PASS' if m else 'FAIL', 'duplicated %s -> %s' % (AS61_SRC_MAT, path))
            if not m:
                return None, None
        MEL.set_material_instance_texture_parameter_value(m, hold[0], tex)
        MEL.update_material_instance(m)
        got = _pkg61(MEL.get_material_instance_texture_parameter_value(m, hold[0]))
        _o61('PASS' if got == AS61_TEX else 'FAIL', '%s parameter %s = %s' % (path, hold[0], got))
        base = m.get_base_material()
        u = base.get_editor_property('used_with_skeletal_mesh')
        _o61('PASS' if u else 'FAIL', 'base material %s bUsedWithSkeletalMesh = %s (not ours: not changed here)' % (_pkg61(base), u))
        return m, path
    _o61('FAIL', 'M_Airship is a %s: neither a Material nor a material instance' % src.get_class().get_name())
    return None, None


def as61_assign(eal, mat, mat_path):
    """SK_Airship slot 0 = mat; returns True when the slots read back as wanted"""
    sk = eal.load_asset(AS61_SK)
    mats = sk.materials
    names = []
    for m in mats:
        nm = str(m.get_editor_property('imported_material_slot_name'))
        if nm in ('None', ''):
            nm = str(m.get_editor_property('material_slot_name'))
        names.append(nm)
    before = [_pkg61(m.get_editor_property('material_interface')) for m in mats]
    AS61_R['sk_slots_before'] = list(zip(names, before))
    if len(mats) != 2 or 'M_Airship' not in names[0]:
        _o61('FAIL', 'SK_Airship slots %s: want 2 with slot 0 = the hull (M_Airship slot)' % AS61_R['sk_slots_before'])
        return False
    if before[0] != mat_path:
        m0 = mats[0]          # an unreal.Array of structs hands out COPIES: change the copy, then write it back (as as_10
        m0.set_editor_property('material_interface', mat)   # does); mats[0].set_editor_property(..) alone changed nothing
        mats[0] = m0          # (first editor run 2026-11-27: the slot read back as M_Airship)
        try:
            sk.materials = mats
        except Exception as e:  # noqa: BLE001
            _o61('WARN', 'materials setter: %s; set_editor_property notify NEVER' % e)
            sk.set_editor_property('materials', mats, unreal.PropertyAccessChangeNotifyMode.NEVER)
        sk.modify()
        _o61('INFO', 'SK_Airship slot 0 %s -> %s' % (before[0], mat_path))
    after = [_pkg61(m.get_editor_property('material_interface')) for m in sk.materials]
    AS61_R['sk_slots_after'] = list(zip(names, after))
    ok = after[0] == mat_path and after[1] == before[1]
    _o61('PASS' if ok else 'FAIL', 'SK_Airship slots %s (slot 1 unchanged: %s)' % (AS61_R['sk_slots_after'], after[1] == before[1]))
    return ok


def as61_run():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        _o61('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    # the PNG: what hull_ink_drivable.py wrote (size and format of Talal's texture)
    if not os.path.exists(AS61_PNG):
        _o61('FAIL', '%s missing: run SourceArt/Airship/scripts/hull_ink_drivable.py (headless Blender) first' % AS61_PNG)
        return
    hdr = _png_header61(AS61_PNG)
    AS61_R['png'] = {'path': AS61_PNG, 'sha256': _sha61(AS61_PNG), 'md5': _md5_61(AS61_PNG), 'bytes': os.path.getsize(AS61_PNG),
                     'header': hdr}
    _o61('PASS' if hdr == (4096, 4096, 8, 2) else 'FAIL', 'PNG %s: %s (want 4096 x 4096, 8-bit RGB like T_Airship_ComicLines.png)'
         % (os.path.basename(AS61_PNG), hdr))
    if hdr != (4096, 4096, 8, 2):
        return
    try:
        with open(AS61_BAKE_REPORT) as f:
            bake = json.load(f)
        same = bake.get('output_md5') == AS61_R['png']['md5']
        _o61('PASS' if same else 'WARN', 'PNG md5 %s the hull_ink_report.json output (%s texels changed, %s groups)'
             % ('=' if same else '!=', bake.get('texels_changed'), len(bake.get('groups') or [])))
    except Exception as e:  # noqa: BLE001
        _o61('WARN', 'bake report %s not readable (%s): PNG not cross-checked' % (AS61_BAKE_REPORT, e))
    for p in (AS61_SRC_TEX, AS61_SRC_MAT, AS61_SK, AS61_PROPS_MAT):
        if not eal.does_asset_exist(p):
            _o61('FAIL', '%s missing' % p)
            return
    talal_sha0 = dict((p, _sha61(_pkg_file61(p)) if os.path.exists(_pkg_file61(p)) else None) for p in AS61_TALAL)
    dirty0 = _dirty61()
    ours = [AS61_TEX, AS61_SK]
    busy = [p for p in ours + [AS61_MAT_DIR + '/M_AirshipDrivable', AS61_MAT_DIR + '/MI_AirshipDrivable'] if p in dirty0]
    if busy:
        _o61('FAIL', 'changed in memory already (an earlier run that did not save?): %s; restart the editor and run again' % busy)
        return
    aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
    for p in (AS61_SK, AS61_TEX, AS61_MAT_DIR + '/M_AirshipDrivable', AS61_MAT_DIR + '/MI_AirshipDrivable', AS61_SRC_MAT):
        if eal.does_asset_exist(p):
            try:
                aes.close_all_editors_for_asset(eal.load_asset(p))
            except Exception:  # noqa: BLE001
                pass
    src_tex = eal.load_asset(AS61_SRC_TEX)
    AS61_R['source_texture'] = {'size': [src_tex.blueprint_get_size_x(), src_tex.blueprint_get_size_y()],
                                'source_file': _source_file61(src_tex)}
    _o61('INFO', 'T_Airship_ComicLines %s, from %s' % (AS61_R['source_texture']['size'], AS61_R['source_texture']['source_file']))
    # 1. texture
    tex = as61_import_texture(eal)
    if tex is None:
        return
    AS61_R['texture_settings'] = as61_copy_settings(src_tex, tex)
    tex = eal.load_asset(AS61_TEX)
    bad = [p for p in AS61_TEX_CORE if str(tex.get_editor_property(p)) != str(src_tex.get_editor_property(p))]
    _o61('PASS' if not bad else 'FAIL', 'texture settings = T_Airship_ComicLines for %s%s' % (AS61_TEX_CORE, '' if not bad else ': OFF %s' % bad))
    more = [p for p in AS61_TEX_MORE if p in AS61_R['texture_settings']
            and AS61_R['texture_settings'][p]['now'] != AS61_R['texture_settings'][p]['original']]
    _o61('PASS' if not more else 'WARN', 'other settings copied: %s%s' % (
        dict((p, v['now']) for p, v in AS61_R['texture_settings'].items() if p in AS61_TEX_MORE), '' if not more else ': OFF %s' % more))
    size = [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()]
    _o61('PASS' if size == AS61_R['source_texture']['size'] == [4096, 4096] else 'FAIL', 'texture size %s (original %s)'
         % (size, AS61_R['source_texture']['size']))
    sf = _source_file61(tex)
    _o61('PASS' if sf and os.path.abspath(sf) == os.path.abspath(AS61_PNG) else 'WARN', 'texture source file %s' % sf)
    # 2. material
    mat, mat_path = as61_material(eal, tex, src_tex)
    if mat is None:
        return
    used = [_pkg61(t) for t in unreal.MaterialEditingLibrary.get_used_textures(mat)]
    AS61_R['material_used_textures'] = used
    if isinstance(mat, unreal.Material):
        _o61('PASS' if AS61_TEX in used and AS61_SRC_TEX not in used else 'FAIL', '%s uses %s' % (mat_path, used))
    else:   # an MI: the parameter read-back above is the check
        _o61('INFO', '%s uses %s' % (mat_path, used))
    # 3. SK_Airship slot 0
    if not as61_assign(eal, mat, mat_path):
        return
    # 4. save ours only
    if AS61_R['counts'].get('FAIL'):
        _o61('WARN', '%d FAIL: NOT saved (changes stay in memory; restart the editor before a re-run)' % AS61_R['counts']['FAIL'])
        return
    for p in (AS61_TEX, mat_path, AS61_SK):
        ok = eal.save_asset(p, only_if_is_dirty=False)
        _o61('PASS' if ok else 'FAIL', 'saved %s' % p)
    # verify
    dirty1 = _dirty61()
    left = [p for p in (AS61_TEX, mat_path, AS61_SK) if p in dirty1]
    _o61('PASS' if not left else 'FAIL', 'our assets clean after the save%s' % ('' if not left else ': still dirty %s' % left))
    talal_dirty = [p for p in AS61_TALAL if p in dirty1 and p not in dirty0]
    talal_sha1 = dict((p, _sha61(_pkg_file61(p)) if os.path.exists(_pkg_file61(p)) else None) for p in AS61_TALAL)
    changed = [p for p in AS61_TALAL if talal_sha1[p] != talal_sha0[p]]
    _o61('PASS' if not talal_dirty and not changed else 'FAIL', "Talal's assets untouched (not dirtied here: %s, files unchanged: %s)"
         % (not talal_dirty, not changed))
    sk = eal.load_asset(AS61_SK)
    slot0 = _pkg61(sk.materials[0].get_editor_property('material_interface'))
    _o61('PASS' if slot0 == mat_path else 'FAIL', 'SK_Airship slot 0 after the save: %s' % slot0)
    for p in (AS61_TEX, mat_path, AS61_SK):
        f = _pkg_file61(p)
        AS61_R.setdefault('saved_files', {})[p] = {'exists': os.path.exists(f), 'bytes': os.path.getsize(f) if os.path.exists(f) else None}
    _o61('INFO', 'dirty packages now (not saved): %s' % dirty1)
    _o61('INFO', 'look check: the round-2 stills (_AirshipWork_logs/scratch/r2/stills/r2_stills.py) or as_59 phase t7_caps '
         '(t7_top_top.png): no black rectangles / bar on the deck where the five pieces stood')


try:
    as61_run()
except Exception:  # noqa: BLE001
    _o61('FAIL', 'as_61 crashed: %s' % traceback.format_exc())
try:
    _d61 = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
    os.makedirs(_d61, exist_ok=True)
    with open(os.path.join(_d61, 'as_61_hull_ink.json'), 'w') as _f61:
        json.dump(AS61_R, _f61, indent=1, default=str)
except Exception as _e61:  # noqa: BLE001
    print('WARN: report not written %r' % (_e61,))
print('RESULT: %s %s' % ('PASS' if not AS61_R['counts'].get('FAIL') else 'FAIL', AS61_R['counts']))
