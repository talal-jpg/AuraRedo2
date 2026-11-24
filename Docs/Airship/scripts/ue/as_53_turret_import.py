# as_53_turret_import.py - round 2 D6/D7: imports the two turret static meshes made in Blender (SourceArt/Airship, by
# props/model_turret.py + export_turret.py) into /Game/Assets/MyShip/Drivable/Turret:
#   SM_AirshipTurret_Base  (yaw part, origin = yaw axis on the deck, z 0 = deck)    <- SourceArt/Airship/SM_AirshipTurret_Base.fbx
#   SM_AirshipTurret_Gun   (pitch part, origin = trunnion axis, fires +X)          <- SourceArt/Airship/SM_AirshipTurret_Gun.fbx
# Static mesh, legacy FbxFactory (as as_10), combine meshes, FBX normals, no collision generated (the C++ HitBox is the
# turret's collision), Nanite off, no lightmap UVs (the turret moves with the ship), pivot kept (vertices stay in the
# object's own space), material slot 0 = /Game/Assets/MyShip/Drivable/Materials/M_AirshipProps (the props ink atlas, the
# same material the helm and cannons use; re-import the atlas textures with as_02 when Blender repacked it).
# Bounds checked against SourceArt/Airship/turret_dims.json (+-2 cm where the file gives a number to compare with).
# Re-runnable: re-imports over its own two assets; refuses to touch an asset of the same name that isn't a static mesh or
# was imported from another file. Saves only these two meshes.
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 53 Docs/Airship/scripts/ue/as_53_turret_import.py 300
# Report: Saved/Airship/as_53_turret_import.json
import json, os, time, traceback  # unreal = inbox namespace

W = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(W, 'SourceArt/Airship')
DIMS = os.path.join(SRC, 'turret_dims.json')
FOLDER = '/Game/Assets/MyShip/Drivable/Turret'
MAT = '/Game/Assets/MyShip/Drivable/Materials/M_AirshipProps'
MESHES = [('SM_AirshipTurret_Base', os.path.join(SRC, 'SM_AirshipTurret_Base.fbx')),
          ('SM_AirshipTurret_Gun', os.path.join(SRC, 'SM_AirshipTurret_Gun.fbx'))]
TOL = 2.0
R = {'lines': [], 'meshes': {}}
CNT = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def o(tag, msg):
    CNT[tag] += 1
    R['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def setp(obj, prop, value, critical=True):
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as e:  # noqa: BLE001
        o('FAIL' if critical else 'WARN', 'set %s.%s: %s' % (obj.get_class().get_name(), prop, e))
        return False


def en(enum_name, value):
    return getattr(getattr(unreal, enum_name), value)


def load_dims():
    try:
        with open(DIMS) as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        o('WARN', 'turret_dims.json not readable (%s): bounds only reported' % e)
        return {}


def num(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def box_of(d, *keys):
    """{'min': [x,y,z], 'max': [x,y,z]} (UE cm, the mesh's own space) from the dims file, else None."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict) and isinstance(v.get('min'), list) and isinstance(v.get('max'), list):
            return [float(x) for x in v['min']], [float(x) for x in v['max']]
    return None


def import_ui():
    ui = unreal.FbxImportUI()
    t = en('FBXImportType', 'FBXIT_STATIC_MESH')
    ok = True
    ok &= setp(ui, 'import_mesh', True)
    ok &= setp(ui, 'import_as_skeletal', False)
    ok &= setp(ui, 'mesh_type_to_import', t)
    ok &= setp(ui, 'original_import_type', t)
    ok &= setp(ui, 'automated_import_should_detect_type', False)
    ok &= setp(ui, 'override_full_name', True)
    ok &= setp(ui, 'import_materials', False)
    ok &= setp(ui, 'import_textures', False)
    ok &= setp(ui, 'import_animations', False)
    ok &= setp(ui, 'create_physics_asset', False)
    smd = ui.get_editor_property('static_mesh_import_data')
    ok &= setp(smd, 'convert_scene', True)
    ok &= setp(smd, 'force_front_x_axis', False)
    ok &= setp(smd, 'convert_scene_unit', False)
    ok &= setp(smd, 'import_uniform_scale', 1.0)
    ok &= setp(smd, 'import_translation', unreal.Vector(0.0, 0.0, 0.0))
    ok &= setp(smd, 'import_rotation', unreal.Rotator(0.0, 0.0, 0.0))
    ok &= setp(smd, 'combine_meshes', True)
    ok &= setp(smd, 'auto_generate_collision', False)
    ok &= setp(smd, 'normal_import_method', en('FBXNormalImportMethod', 'FBXNIM_IMPORT_NORMALS'))
    # the pivot stays at the object origin (yaw axis / trunnion axis): the node's transform is not baked in
    ok &= setp(smd, 'transform_vertex_to_absolute', False)
    ok &= setp(smd, 'bake_pivot_in_vertex', False)
    setp(smd, 'build_nanite', False, False)
    setp(smd, 'generate_lightmap_u_vs', False, False)
    setp(smd, 'remove_degenerates', True, False)
    setp(smd, 'one_convex_hull_per_ucx', False, False)
    setp(smd, 'reorder_material_to_fbx_order', True, False)
    try:
        setp(smd, 'vertex_color_import_option', en('VertexColorImportOption', 'IGNORE'), False)
    except Exception as e:  # noqa: BLE001
        o('WARN', 'vertex colour option: %s' % e)
    try:
        tex = ui.get_editor_property('texture_import_data')
        setp(tex, 'material_search_location', en('MaterialSearchLocation', 'DO_NOT_SEARCH'), False)
    except Exception as e:  # noqa: BLE001
        o('WARN', 'material_search_location: %s' % e)
    return ui, ok


def source_file(sm):
    try:
        aid = sm.get_editor_property('asset_import_data')
        fn = aid.get_first_filename() if hasattr(aid, 'get_first_filename') else None
        if not fn:
            fn = str(aid.extract_filenames()[0]) if aid.extract_filenames() else None
        return fn
    except Exception:  # noqa: BLE001
        return None


def import_one(name, fbx):
    path = '%s/%s' % (FOLDER, name)
    eal = unreal.EditorAssetLibrary
    if not os.path.exists(fbx):
        o('FAIL', '%s missing (Blender step D7: export_turret.py)' % fbx)
        return None
    if eal.does_asset_exist(path):
        old = eal.load_asset(path)
        if not isinstance(old, unreal.StaticMesh):
            o('FAIL', '%s exists and is a %s, not a static mesh: not touched' % (path, old.get_class().get_name()))
            return None
        src = source_file(old)
        if src and os.path.basename(src) != os.path.basename(fbx):
            o('FAIL', '%s was imported from %s, not %s: not ours, not touched' % (path, src, os.path.basename(fbx)))
            return None
        o('INFO', 're-importing over %s (was from %s)' % (path, src))
    ui, ok = import_ui()
    if not ok:
        o('FAIL', 'import options incomplete: %s not imported' % name)
        return None
    task = unreal.AssetImportTask()
    setp(task, 'filename', fbx)
    setp(task, 'destination_path', FOLDER)
    setp(task, 'destination_name', name)
    setp(task, 'replace_existing', True)
    setp(task, 'replace_existing_settings', True, False)
    setp(task, 'automated', True)
    setp(task, 'save', False)
    setp(task, 'factory', unreal.FbxFactory())   # explicit legacy factory, as as_10 (Interchange bypassed)
    setp(task, 'options', ui)
    t0 = time.time()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    try:
        paths = [str(p) for p in task.get_editor_property('imported_object_paths')]
    except Exception:  # noqa: BLE001
        paths = []
    o('INFO', 'import %s took %.1f s -> %s' % (os.path.basename(fbx), time.time() - t0, paths))
    sm = eal.load_asset(path) if eal.does_asset_exist(path) else None
    if not isinstance(sm, unreal.StaticMesh):
        o('FAIL', '%s not created (see LogFbx in Saved/Logs/Aura.log)' % path)
        return None
    return sm


def fix_up(name, sm):
    d = {}
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    mat = unreal.load_asset(MAT)
    if mat is None:
        o('FAIL', '%s missing (as_02)' % MAT)
        return d
    n_slots = len(sm.get_editor_property('static_materials'))
    d['slots'] = n_slots
    o('PASS' if n_slots == 1 else 'WARN', '%s material slots %d (want 1: M_AirshipProps)' % (name, n_slots))
    for i in range(n_slots):
        sm.set_material(i, mat)
    d['materials'] = [m.get_editor_property('material_interface').get_path_name() if m.get_editor_property('material_interface') else None
                      for m in sm.get_editor_property('static_materials')]
    o('PASS' if all(p and p.startswith(MAT) for p in d['materials']) else 'FAIL', '%s materials %s' % (name, d['materials']))
    # no simple collision (the C++ HitBox is the collision; the components are NoCollision)
    nc = sms.get_simple_collision_count(sm)
    if nc:
        sms.remove_collisions(sm)
        o('INFO', '%s: removed %d simple collision shape(s)' % (name, nc))
    d['simple_collision'] = sms.get_simple_collision_count(sm)
    o('PASS' if d['simple_collision'] == 0 else 'FAIL', '%s simple collision shapes %d (want 0)' % (name, d['simple_collision']))
    try:
        ns = sm.get_editor_property('nanite_settings')
        if ns.get_editor_property('enabled'):
            ns.set_editor_property('enabled', False)
            sm.set_editor_property('nanite_settings', ns)
            o('INFO', '%s: Nanite turned off' % name)
        d['nanite'] = bool(sm.get_editor_property('nanite_settings').get_editor_property('enabled'))
        o('PASS' if not d['nanite'] else 'FAIL', '%s Nanite %s (want off)' % (name, d['nanite']))
    except Exception as e:  # noqa: BLE001
        o('WARN', '%s nanite settings: %s' % (name, e))
    bb = sm.get_bounding_box()
    d['bounds_min'] = [round(bb.min.x, 2), round(bb.min.y, 2), round(bb.min.z, 2)]
    d['bounds_max'] = [round(bb.max.x, 2), round(bb.max.y, 2), round(bb.max.z, 2)]
    try:
        d['verts'] = sms.get_number_verts(sm, 0)
    except Exception:  # noqa: BLE001
        pass
    o('INFO', '%s bounds min %s max %s (cm, the mesh space; verts %s)' % (name, d['bounds_min'], d['bounds_max'], d.get('verts')))
    return d


def check_dims(dims, res):
    pivot = num(dims, 'pivot_height_cm')
    muzzle = num(dims, 'muzzle_forward_cm')
    base_r = num(dims, 'base_radius_cm')
    gun_len = num(dims, 'gun_length_cm')
    R['dims_used'] = {'pivot_height_cm': pivot, 'muzzle_forward_cm': muzzle, 'base_radius_cm': base_r, 'gun_length_cm': gun_len}
    b = res.get('SM_AirshipTurret_Base') or {}
    g = res.get('SM_AirshipTurret_Gun') or {}
    for key, name, d in (('base_bounds_cm', 'SM_AirshipTurret_Base', b), ('gun_bounds_cm', 'SM_AirshipTurret_Gun', g)):
        box = box_of(dims, key)
        if box and d.get('bounds_min'):
            dev = max(max(abs(d['bounds_min'][i] - box[0][i]), abs(d['bounds_max'][i] - box[1][i])) for i in range(3))
            o('PASS' if dev <= TOL else 'FAIL', '%s bounds vs turret_dims.json %s: worst %.2f cm (tol %.0f)' % (name, key, dev, TOL))
    if b.get('bounds_min'):
        o('PASS' if abs(b['bounds_min'][2]) <= TOL else 'FAIL', 'base bottom z %.2f cm (origin on the deck: want 0 +-%.0f)' % (b['bounds_min'][2], TOL))
        half = max(abs(b['bounds_min'][0]), abs(b['bounds_max'][0]), abs(b['bounds_min'][1]), abs(b['bounds_max'][1]))
        o('PASS' if half <= 45.0 + TOL else 'WARN', 'base footprint half size %.1f cm (spec: inside 0.9 x 0.9 m)' % half)
        if base_r is not None:
            o('INFO', 'base_radius_cm %.1f (pedestal), footprint half size %.1f (with shield / ammo box)' % (base_r, half))
        if pivot is not None:
            o('PASS' if b['bounds_max'][2] >= pivot - TOL else 'WARN', 'base top z %.1f cm reaches the trunnion pivot %.1f (yoke cheeks)'
              % (b['bounds_max'][2], pivot))
    if g.get('bounds_min'):
        if muzzle is not None:
            dx = g['bounds_max'][0] - muzzle
            o('PASS' if -TOL <= dx <= 10.0 else 'WARN', 'gun front x %.1f cm vs muzzle_forward_cm %.1f (%+.1f; the muzzle point sits at the '
              'barrel ends)' % (g['bounds_max'][0], muzzle, dx))
        if gun_len is not None:
            ln = g['bounds_max'][0] - g['bounds_min'][0]
            o('PASS' if abs(ln - gun_len) <= TOL else 'WARN', 'gun length (x extent) %.1f cm vs gun_length_cm %.1f' % (ln, gun_len))
        o('PASS' if g['bounds_min'][0] >= -45.0 - TOL else 'WARN', 'gun rear x %.1f cm (spec: receiver <= 0.45 m behind the trunnion)'
          % g['bounds_min'][0])


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o('FAIL', 'PIE is running: nothing done')
        return
    dims = load_dims()
    R['dims'] = dims
    res = {}
    for name, fbx in MESHES:
        sm = import_one(name, fbx)
        if sm is None:
            continue
        res[name] = fix_up(name, sm)
        res[name]['fbx'] = fbx
        res[name]['fbx_bytes'] = os.path.getsize(fbx)
    R['meshes'] = res
    check_dims(dims, res)
    if CNT['FAIL']:
        o('WARN', '%d FAIL: NOT saved (assets stay in memory)' % CNT['FAIL'])
        return
    for name, _ in MESHES:
        p = '%s/%s' % (FOLDER, name)
        ok = unreal.EditorAssetLibrary.save_asset(p, only_if_is_dirty=False)
        o('PASS' if ok else 'FAIL', 'saved %s' % p)
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    o('INFO', 'dirty packages now (not saved): %s' % dirty)


try:
    main()
except Exception:  # noqa: BLE001
    o('FAIL', traceback.format_exc())
R['counts'] = CNT
os.makedirs(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship'), exist_ok=True)
with open(os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'as_53_turret_import.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print('RESULT: %s %s' % ('PASS' if not CNT['FAIL'] else 'FAIL', CNT))
