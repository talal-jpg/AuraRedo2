# as_9x_r3lib.py - shared helpers for the round 3 Unreal scripts as_90 .. as_93 (Docs/Airship/round3/EDITOR_STAGE_R3.md).
# Not run on its own: each script execs it into the inbox namespace first:
#     exec(open(os.path.join(<project>, 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())
# Everything here has the R3 / _r3 prefix (the inbox namespace is shared between scripts).
#   r3_report(name)          a PASS / FAIL / WARN / INFO line collector; r3_finish() writes Saved/Airship/<name>.json and
#                            prints the RESULT line
#   r3_inputs()              SourceArt/Airship/r3/r3_unreal_inputs.json, every staged file's md5 checked
#   r3_backup(pkgs, tag)     copies the .uasset (+ .uexp / .ubulk) of each existing package to
#                            Saved/Airship/backup_r3/<stamp>_<tag>/Content/..., with sha256 in backup.json; refuses (returns
#                            None) when one of them has unsaved changes (the file would not match what the editor holds).
#                            Restore = copy the files back over Content/ with the editor CLOSED.
#   r3_talal_state()         sha256 of Talal's assets (/Game/Assets/MyShip/M_Airship, T_Airship_*, SM_Airship): the
#                            scripts compare it before / after (never touched)
#   r3_close_editors(pkgs), r3_dirty(), r3_pkg_file(pkg), r3_pth(obj), r3_setp(obj, prop, value)
import hashlib, json, math, os, shutil, time, traceback  # unreal = inbox namespace

R3_W = os.path.abspath(unreal.Paths.project_dir())
R3_SAVED = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
R3_SRC = os.path.join(R3_W, 'SourceArt/Airship/r3')
R3_TEXSRC = os.path.join(R3_W, 'SourceArt/Airship/textures/r3')
R3_INPUTS = os.path.join(R3_SRC, 'r3_unreal_inputs.json')
R3_STAIRS = os.path.join(R3_W, 'Docs/Airship/round3/stairs_collision.json')
R3_D = '/Game/Assets/MyShip/Drivable'
R3_MATD = R3_D + '/Materials'
R3_TEXD = R3_D + '/Textures'
R3_SK, R3_SKEL, R3_PA = R3_D + '/SK_Airship', R3_D + '/SKEL_Airship', R3_D + '/PA_Airship'
R3_CR, R3_ABP, R3_BP = R3_D + '/CR_Airship', R3_D + '/ABP_Airship', R3_D + '/BP_AirshipPawn'
R3_ANIM = R3_D + '/A_Airship_TestSweep'
R3_HD = R3_D + '/SM_AirshipR3_HullDetail'
R3_TURRET = {'SM_AirshipTurret_Base': R3_D + '/Turret/SM_AirshipTurret_Base', 'SM_AirshipTurret_Gun': R3_D + '/Turret/SM_AirshipTurret_Gun'}
R3_TURRET_BP = R3_D + '/Turret/BP_AirshipTurret'
R3_MASTER = R3_MATD + '/M_AirshipR3'
R3_LOOK = R3_MATD + '/MI_AirshipR3_Look'          # the palette and ink knobs, parent of the four below
R3_MI = {'hull': R3_MATD + '/MI_AirshipR3_Hull', 'moving': R3_MATD + '/MI_AirshipR3_Moving',
         'hulldetail': R3_MATD + '/MI_AirshipR3_HullDetail', 'props': R3_MATD + '/MI_AirshipR3_Props'}
R3_TEX = {'hull': R3_TEXD + '/T_AirshipR3_HullInk', 'H': R3_TEXD + '/T_AirshipR3_DetailInk_H',
          'M': R3_TEXD + '/T_AirshipR3_DetailInk_M', 'P': R3_TEXD + '/T_AirshipR3_PropsInk',
          'comic': R3_TEXD + '/T_AirshipR3_HullComicMask'}
R3_TALAL = ['/Game/Assets/MyShip/M_Airship', '/Game/Assets/MyShip/T_Airship_ComicLines', '/Game/Assets/MyShip/T_Airship_ComicMask',
            '/Game/Assets/MyShip/SM_Airship']
R3_ROUND2_MATS = [R3_MATD + '/M_AirshipDrivable', R3_MATD + '/M_AirshipProps']
# SK slots by imported slot name (the FBX material names; r3_fbx_check: this order in the file)
R3_SLOT_MI = {'M_Airship': 'hull', 'M_AirshipProps': 'props', 'M_AirshipR3_Detail': 'moving'}
R3_PA_TS = 'PhysicsToolsets.PhysicsAssetToolset'


def r3_report(name):
    return {'name': name, 'lines': [], 'counts': {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}, 'data': {},
            'started': time.strftime('%Y-%m-%d %H:%M:%S')}


def r3_o(R, tag, msg):
    R['counts'][tag] = R['counts'].get(tag, 0) + 1
    R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def r3_finish(R):
    try:
        os.makedirs(R3_SAVED, exist_ok=True)
        with open(os.path.join(R3_SAVED, R['name'] + '.json'), 'w') as f:
            json.dump(R, f, indent=1, default=str)
    except Exception as e:  # noqa: BLE001
        print('WARN: report not written %r' % (e,))
    print('RESULT: %s %s' % ('PASS' if not R['counts'].get('FAIL') else 'FAIL', R['counts']))


def r3_sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def r3_md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def r3_pkg_file(pkg):
    return os.path.join(R3_W, 'Content', pkg[len('/Game/'):] + '.uasset')


def r3_pth(v):
    try:
        return v.get_path_name() if v is not None else None
    except Exception:  # noqa: BLE001
        return str(v)


def r3_pkg(v):
    p = r3_pth(v)
    return p.split('.')[0] if p else None


def r3_dirty():
    return [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]


def r3_pie():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()


def r3_setp(R, obj, prop, value, critical=True):
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as e:  # noqa: BLE001
        r3_o(R, 'FAIL' if critical else 'WARN', 'set %s.%s = %s: %s' % (type(obj).__name__, prop, value, e))
        return False


def r3_getp(obj, prop, default=None):
    try:
        return obj.get_editor_property(prop)
    except Exception:  # noqa: BLE001
        return default


def r3_enum(enum_cls, key):
    """enum member whose name, without underscores and case, contains key (e.g. ('MaterialExposedViewProperty',
    'tanhalffieldofview')): the Python spelling of engine enums is not always obvious"""
    e = getattr(unreal, enum_cls)
    k = key.replace('_', '').lower()
    hits = [n for n in dir(e) if not n.startswith('_') and k in n.replace('_', '').lower()]
    hits.sort(key=len)
    if not hits:
        raise RuntimeError('%s has no member like %s (%s)' % (enum_cls, key, [n for n in dir(e) if not n.startswith('_')][:30]))
    return getattr(e, hits[0])


def r3_inputs(R):
    """the staged inputs; None (with FAIL lines) when a file is missing or not the one r3_unreal_inputs.py staged"""
    if not os.path.exists(R3_INPUTS):
        r3_o(R, 'FAIL', '%s missing: run SourceArt/Airship/scripts/r3_unreal_inputs.py (export step) first' % R3_INPUTS)
        return None
    with open(R3_INPUTS) as f:
        inp = json.load(f)
    bad = []
    for rel, d in inp['files'].items():
        p = os.path.join(R3_W, 'SourceArt/Airship', rel)
        if not os.path.exists(p) or r3_md5(p) != d['md5']:
            bad.append(rel)
    r3_o(R, 'PASS' if not bad else 'FAIL', 'staged inputs (%d files) = r3_unreal_inputs.json%s' % (
        len(inp['files']), '' if not bad else ': missing or changed %s' % bad))
    return None if bad else inp


def r3_talal_state():
    return dict((p, r3_sha(r3_pkg_file(p)) if os.path.exists(r3_pkg_file(p)) else None) for p in R3_TALAL)


def r3_check_talal(R, before):
    after = r3_talal_state()
    changed = [p for p in R3_TALAL if after[p] != before[p]]
    dirty = [p for p in R3_TALAL if p in r3_dirty()]
    r3_o(R, 'PASS' if not changed and not dirty else 'FAIL', "Talal's assets untouched (files unchanged: %s, not dirty: %s)"
         % (not changed, not dirty))


def r3_close_editors(pkgs):
    aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
    eal = unreal.EditorAssetLibrary
    for p in pkgs:
        if eal.does_asset_exist(p):
            try:
                aes.close_all_editors_for_asset(eal.load_asset(p))
            except Exception:  # noqa: BLE001
                pass


def r3_backup(R, pkgs, tag):
    """copies the files of every existing package in pkgs to Saved/Airship/backup_r3/<stamp>_<tag>/Content/...;
    returns the folder, or None when a package has unsaved changes (FAIL) or a copy failed"""
    dirty = r3_dirty()
    busy = [p for p in pkgs if p in dirty]
    if busy:
        r3_o(R, 'FAIL', 'unsaved changes in %s: the files would not match the editor (an earlier run that did not save?): '
             'restart the editor (quit_keep_lock.sh + launch.sh) and run again' % busy)
        return None
    stamp = time.strftime('%Y%m%d_%H%M%S')
    root = os.path.join(R3_SAVED, 'backup_r3', '%s_%s' % (stamp, tag))
    rec = {'tag': tag, 'stamp': stamp, 'files': {}, 'restore': 'editor CLOSED: copy <this folder>/Content/... over '
           '<project>/Content/... (the same relative paths), then start the editor'}
    for p in pkgs:
        base = r3_pkg_file(p)[:-len('.uasset')]
        for ext in ('.uasset', '.uexp', '.ubulk'):
            src = base + ext
            if not os.path.exists(src):
                continue
            rel = os.path.relpath(src, R3_W)
            dst = os.path.join(root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            sha = r3_sha(dst)
            if sha != r3_sha(src):
                r3_o(R, 'FAIL', 'backup copy of %s differs from the source' % rel)
                return None
            rec['files'][rel] = {'sha256': sha, 'bytes': os.path.getsize(dst)}
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, 'backup.json'), 'w') as f:
        json.dump(rec, f, indent=1)
    r3_o(R, 'PASS', 'backup of %d existing file(s) of %s -> %s' % (len(rec['files']), [p.rsplit('/', 1)[1] for p in pkgs], root))
    R['data']['backup'] = {'folder': root, 'files': rec['files']}
    return root


def r3_save(R, pkgs):
    """saves exactly these packages (explicit paths); never a map"""
    ok = True
    for p in pkgs:
        if p.endswith('.umap') or '/Maps/' in p:
            r3_o(R, 'FAIL', 'refusing to save a map: %s' % p)
            ok = False
            continue
        s = unreal.EditorAssetLibrary.save_asset(p, only_if_is_dirty=False)
        r3_o(R, 'PASS' if s else 'FAIL', 'saved %s' % p)
        ok &= bool(s)
    left = [p for p in pkgs if p in r3_dirty()]
    if left:
        r3_o(R, 'FAIL', 'still dirty after the save: %s' % left)
        ok = False
    return ok


def r3_tool(fn, **params):
    """a PhysicsAssetToolset tool through the ToolsetRegistry (as_11's route); returns its value"""
    js = json.dumps(params)
    res = unreal.ToolsetRegistry.execute_tool(R3_PA_TS, fn, js)
    err = str(res.get_editor_property('error') or '')
    if err:
        raise RuntimeError('%s(%s) -> %s' % (fn, js[:200], err))
    raw = str(res.get_editor_property('value') or '')
    if not raw:
        return None
    d = json.loads(raw)
    if isinstance(d, dict):
        for k in d:
            if k.lower() == 'returnvalue':
                return d[k]
    return d


def r3_kget(d, name, default=None):
    for k, v in (d or {}).items():
        if k.lower() == name.lower():
            return v
    return default


def r3_bone_table(sk):
    """[(name, parent, (x, y, z) component-space rest position, rotation angle deg)] from the mesh's skeleton"""
    skel = sk.get_editor_property('skeleton')
    pose = unreal.AnimPoseExtensions.get_reference_pose(skel)
    out = []
    for n in unreal.AnimPoseExtensions.get_bone_names(pose):
        n = str(n)
        t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, n, unreal.AnimPoseSpaces.WORLD)
        q = t.rotation
        import math
        ang = math.degrees(2.0 * math.acos(min(1.0, abs(q.w))))
        p = str(unreal.SkeletalMeshEditorSubsystem.get_bone_parent(sk, n))
        out.append((n, None if p in ('None', '') else p, (round(t.translation.x, 3), round(t.translation.y, 3),
                                                           round(t.translation.z, 3)), round(ang, 5)))
    return out


def r3_sockets(sk):
    out = []
    try:
        for i in range(sk.num_sockets()):
            s = sk.get_socket_by_index(i)
            loc = s.get_editor_property('relative_location')
            rot = s.get_editor_property('relative_rotation')
            out.append((str(s.get_editor_property('socket_name')), str(s.get_editor_property('bone_name')),
                        (round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)), (round(rot.pitch, 3), round(rot.yaw, 3), round(rot.roll, 3))))
    except Exception as e:  # noqa: BLE001
        out.append(('unreadable', str(e), None, None))
    return out


def r3_slot_names(mesh_materials):
    names = []
    for m in mesh_materials:
        nm = str(r3_getp(m, 'imported_material_slot_name', ''))
        if nm in ('None', ''):
            nm = str(r3_getp(m, 'material_slot_name', ''))
        names.append(nm)
    return names


def r3_geo_tris(asset, lod):
    """source triangles of a skeletal / static mesh LOD through GeometryScript (None if the plugin is not there)"""
    try:
        dm = unreal.DynamicMesh()
        opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        rl = unreal.GeometryScriptMeshReadLOD()
        rl.set_editor_property('lod_type', r3_enum('GeometryScriptLODType', 'SourceModel'))
        rl.set_editor_property('lod_index', lod)
        if isinstance(asset, unreal.SkeletalMesh):
            r = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(asset, dm, opts, rl)
        else:
            r = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh_v2(asset, dm, opts, rl)
        out = r[0] if isinstance(r, tuple) else dm
        return int(unreal.GeometryScript_MeshQueries.get_num_triangle_ids(out if out is not None else dm))
    except Exception:  # noqa: BLE001
        return None


def r3_uv_sets(asset, lod):
    """number of UV channels of a skeletal / static mesh LOD through GeometryScript (GetNumUVSets on a copy of the
    source model; USkeletalMesh has no UV-channel query of its own). None if the plugin is not there (review fix: the
    hull MI reads TexCoord[2], so SK_Airship must keep 3 channels per LOD)"""
    try:
        dm = unreal.DynamicMesh()
        opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        rl = unreal.GeometryScriptMeshReadLOD()
        rl.set_editor_property('lod_type', r3_enum('GeometryScriptLODType', 'SourceModel'))
        rl.set_editor_property('lod_index', lod)
        if isinstance(asset, unreal.SkeletalMesh):
            r = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(asset, dm, opts, rl)
        else:
            r = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh_v2(asset, dm, opts, rl)
        out = r[0] if isinstance(r, tuple) else dm
        return int(unreal.GeometryScript_MeshQueries.get_num_uv_sets(out if out is not None else dm))
    except Exception:  # noqa: BLE001
        return None


def r3_mesh_ref_bones(sk, names):
    """{bone: (x, y, z) component-space rest} from the MESH's own reference skeleton (SkeletonModifier, read only:
    nothing is committed; as_56's _as56_mesh_rest). r3_bone_table reads SKEL_Airship's reference pose, which diverged
    from the mesh's in round 2. {} when the modifier is not available."""
    out = {}
    try:
        m = unreal.SkeletonModifier()
        if not m.set_skeletal_mesh(sk):
            return out
        for b in names:
            t = m.get_bone_transform(b, True).translation
            out[b] = (round(t.x, 3), round(t.y, 3), round(t.z, 3))
    except Exception:  # noqa: BLE001
        return {}
    return out


def _r3_strip_screen_size(x):
    if isinstance(x, dict):
        return dict((k, _r3_strip_screen_size(v)) for k, v in x.items() if k.lower() != 'screensize')
    if isinstance(x, list):
        return [_r3_strip_screen_size(v) for v in x]
    return x


def r3_sk_screen_sizes(sk):
    """per-LOD screen sizes (default platform) of a skeletal mesh. UE 5.8 keeps the LOD infos in the SourceModels array
    (FSkeletalMeshSourceModel, not copyable, so Python cannot get / set it as a property); ToolsetLibrary reads it as
    JSON. Returns ([sizes], json dict) or (None, error text)."""
    try:
        d = json.loads(str(unreal.ToolsetLibrary.get_object_properties(sk, ['SourceModels'])))
        arr = r3_kget(d, 'SourceModels')
        out = []
        for e in arr:
            ss = r3_kget(e, 'ScreenSize')
            out.append(float(r3_kget(ss, 'Default') if isinstance(ss, dict) else ss))
        return out, d
    except Exception as e:  # noqa: BLE001
        return None, '%s' % e


def _r3_diff_paths(a, b, path='', out=None, limit=12):
    """paths where two JSON values differ (for the report)"""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            _r3_diff_paths(a.get(k), b.get(k), '%s.%s' % (path, k), out, limit)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _r3_diff_paths(x, y, '%s[%d]' % (path, i), out, limit)
    elif a != b:
        out.append(path or '.')
    return out


def r3_sk_set_screen_sizes(sk, sizes):
    """sets {lod: screen size} through ToolsetLibrary.set_object_properties on SourceModels (only the ScreenSize field of
    each element in the JSON, so the rest of each source model stays); checks that nothing but the screen sizes changed.
    Returns (ok, message, sizes now, other_changed): other_changed lists the SourceModels paths besides ScreenSize that
    differ after the call ([] = none). ToolsetLibrary's set is not transactional and can write part of a JSON, and a
    source model holds the build settings (full-precision UVs, ThresholdUV), reduction settings and LODMaterialMap, so
    the caller must FAIL (not save) when other_changed is not empty (review fix, EXPORT_R3.md 15)."""
    cur, d0 = r3_sk_screen_sizes(sk)
    if cur is None:
        return False, 'SourceModels not readable (%s)' % d0, None, []
    arr = [{'ScreenSize': {'Default': float(sizes.get(i, cur[i]))}} for i in range(len(cur))]
    try:
        ok = unreal.ToolsetLibrary.set_object_properties(sk, json.dumps({'SourceModels': arr}))
    except Exception as e:  # noqa: BLE001
        new, d1 = r3_sk_screen_sizes(sk)
        changed = _r3_diff_paths(_r3_strip_screen_size(d0), _r3_strip_screen_size(d1)) if new is not None else ['unreadable']
        return False, 'set_object_properties raised %s' % e, new if new is not None else cur, changed
    new, d1 = r3_sk_screen_sizes(sk)
    if new is None:
        return False, 'not readable after the set (%s)' % d1, None, ['unreadable after the set']
    changed = _r3_diff_paths(_r3_strip_screen_size(d0), _r3_strip_screen_size(d1))
    good = bool(ok) and not changed and all(abs(new[i] - sizes[i]) < 1e-3 for i in sizes)
    return good, 'set_object_properties %s, other source model fields unchanged %s%s' % (
        ok, not changed, '' if not changed else ' (changed: %s)' % changed), new, changed


def r3_screen_size(radius_cm, dist_m, fov_deg=85.0, aspect=16.0 / 9.0):
    """Unreal's ComputeBoundsScreenSize: max(P[0][0], P[1][1]) * R / D, horizontal FOV, 16:9"""
    import math
    p00 = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    return max(p00, p00 * aspect) * radius_cm / (100.0 * dist_m)


# ------------------------------------------------------------------ PA stair boxes (as_92, as_93)
def r3_stairs_boxes():
    """the json's 16 boxes with unique names: [(name, centre, size, (pitch, yaw, roll), corners, kind)]"""
    d = json.load(open(R3_STAIRS))
    out, seen = [], {}
    for b in d['boxes']:
        n = b['name']
        cnt = sum(1 for x in d['boxes'] if x['name'] == n)
        if cnt > 1:
            k = seen.get(n, 0)
            seen[n] = k + 1
            n = '%s_%d' % (n, k)
        r = b['rotation']
        out.append((n, b['center'], b['size'], (float(r['pitch']), float(r['yaw']), float(r['roll'])), b['corners'], b['kind']))
    return out


def r3_box_corners(c, size, rot):
    """the 8 corners of a box (centre c, full sizes, FRotator pitch / yaw / roll) in the same space as c"""
    rr = unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1])
    t = unreal.Transform(location=unreal.Vector(c[0], c[1], c[2]), rotation=rr, scale=unreal.Vector(1.0, 1.0, 1.0))
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                v = t.transform_location(unreal.Vector(sx * size[0] / 2.0, sy * size[1] / 2.0, sz * size[2] / 2.0))
                pts.append((v.x, v.y, v.z))
    return pts


def r3_corner_match(a, b):
    """largest distance between two corner sets, matched nearest-first (order free)"""
    left = list(b)
    worst = 0.0
    for p in a:
        dd = [math.sqrt(sum((p[i] - q[i]) ** 2 for i in range(3))) for q in left]
        k = min(range(len(dd)), key=lambda i: dd[i])
        worst = max(worst, dd[k])
        left.pop(k)
    return worst


def r3_body_shapes(bone, pa_obj=R3_PA + '.PA_Airship'):
    out = {}
    for s in (r3_tool('GetBodyShapes', PhysicsAsset=pa_obj, BoneName=bone) or []):
        c = r3_kget(s, 'Center') or {}
        rot = r3_kget(s, 'Rotation') or {}
        out[str(r3_kget(s, 'ShapeName'))] = {
            'type': str(r3_kget(s, 'ShapeType')), 'center': [round(float(r3_kget(c, k, 0.0)), 3) for k in ('X', 'Y', 'Z')],
            'rot': [round(float(r3_kget(rot, k, 0.0)), 4) for k in ('Pitch', 'Yaw', 'Roll')],
            'ext': [round(float(r3_kget(s, 'Extent' + k, 0.0)), 3) for k in ('X', 'Y', 'Z')]}
    return out
