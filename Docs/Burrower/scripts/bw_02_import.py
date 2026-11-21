# bw_02_import.py - Burrower editor session step 2: import SourceArt/Burrower/Burrower_UE.fbx as
# /Game/Assets/Enemies/Burrower/SK_Burrower with a NEW skeleton SKEL_Burrower, then check the result.
#
# Run it in the CLONE's editor (never AuraRedo3) through the inbox harness, with a long timeout (the import of
# 1.24 M triangles plus the mesh build takes minutes):
#     Docs/Burrower/scripts/harness/inbox.sh 02_import Docs/Burrower/scripts/bw_02_import.py 1800
# then:  grep -E '^(PASS|FAIL|WARN|INFO|RESULT)' Saved/ClaudeInbox/bw_02_import.out
# Numbers also go to Saved/Burrower/import_report.json. Re-runnable: see EXISTING below.
# Before running: `free -g` (needs a few GB free), editor not in PIE.
#
# ROUTE NOTES (read from the 5.8 source, 2026-11-21)
# * UAssetToolsImpl::ImportAssetsInternal (Developer/AssetTools/Private/AssetTools.cpp ~3566) uses Interchange when
#   UInterchangeManager::IsInterchangeImportEnabled() (CVar Interchange.FeatureFlags.Import.Enable, switched on by the
#   InterchangeImport module) AND the task has NO factory. The FBX translator is enabled by
#   Interchange.FeatureFlags.Import.FBX (default true, InterchangeFbxTranslator.cpp:35; no ini overrides it in Engine/
#   Config or the clone's Config; the lead's probe read True at runtime). So a plain AssetImportTask of an .fbx goes
#   through Interchange in 5.8, and a UFbxImportUI in task.options is only CONVERTED to a generic pipeline
#   (InterchangeManager::ConvertImportData); its bForceFrontXAxis / bConvertScene / bConvertSceneUnit are dropped for a
#   new import.
# * With task.factory = FbxFactory and automated = True, bUseInterchangeFramework is false and the legacy
#   UFbxFactory is used directly (AssetTools.cpp:3567 and :4005); it reads task.options as UFbxImportUI
#   (FbxFactory.cpp:345). Every option below is then explicit in this script.
# * Chosen: LEGACY FbxFactory (USE_INTERCHANGE = False). Why it is the more deterministic route here:
#   - Interchange FBX translator settings (Force Front X Axis, Convert Scene, Convert Scene Unit, uFBX parser) are not
#     per-import parameters: UInterchangeFbxTranslator::GetSettings() loads them from the user's
#     EditorPerProjectUserSettings.ini (InterchangeTranslatorBase.cpp LoadSettings); only a REimport applies stored
#     ones (InterchangeManager.cpp ~1951). A tick in the import dialog once would silently change this import.
#   - Legacy: one skeletal mesh per skeleton root (FbxMainImport.cpp FillFbxSkelMeshArrayInScene / GetRootSkeleton:
#     all 45 parts share 'root' -> one SK), the Blender 'Armature' null is dropped when the file creator starts with
#     "Blender" and the node is named "armature" under the scene root (FbxMainImport.cpp ~2616; this FBX: creator
#     "Blender (stable FBX IO) - 5.0.0", node "Armature" under the scene root, identity transform), no physics asset
#     unless bCreatePhysicsAsset, skeleton named <Mesh>_Skeleton (FbxSkeletalMeshImport.cpp:2200), synchronous.
#   - No modal dialog on a fresh import with a new skeleton. Dialogs exist only for bone-merge failures with an
#     EXISTING skeleton (FbxSkeletalMeshImport.cpp:2228) and material conflicts on reimport.
# * Fallback: USE_INTERCHANGE = True runs InterchangeManager.import_asset with an InterchangeGenericAssetsPipeline
#   override (no physics asset, no animations, no materials, normals kept). It first reads the user's Interchange FBX
#   translator settings and refuses to run if Force Front X Axis is on.
# * The skeleton is created as SK_Burrower_Skeleton by either route and renamed to SKEL_Burrower BEFORE anything is
#   saved, so no redirector is left. Any redirector found in our folder is fixed by resaving its (in-folder)
#   referencers and deleting it.
import unreal
import os, json, time, math, traceback, collections

# ------------------------------------------------------------------------------------------------ flags
USE_INTERCHANGE = False      # False = legacy FbxFactory (default). True = Interchange generic assets pipeline.
EXISTING = 'reuse'           # if SK_Burrower already exists:
                             #   'reuse'    -> no import; fix-ups (skeleton name, empty slots) + checks only
                             #   'reimport' -> import over it in place (keeps SKEL_Burrower and every reference to it;
                             #                 legacy goes through the FBX reimport handler with the stored options)
                             #   'recreate' -> delete SK_Burrower + SKEL_Burrower (+ leftovers) and import fresh; refused
                             #                 if anything else references them (PA/CR/ABP/BP would break)
MATERIAL_MODE = 'grey'       # 'grey': create M_Burrower_Grey in our folder, put it on every EMPTY slot (slots that
                             #         already hold a material are left alone). 'none': leave the slots empty.
SKIN_CHECK = True            # GeometryScript skinning check (copies LOD0 source mesh into a DynamicMesh, ~0.5 GB)
SKIN_SAMPLES_PER_SLOT = 200  # vertices sampled per material slot (the two pipe slots are scanned completely)
POS_TOL_CM = 3.0
BOUNDS_TOL_CM = 3.0
MIN_FREE_GB = 2.5            # refuse to import below this MemAvailable (WARN below 4 GB)

# ------------------------------------------------------------------------------------------------ paths
CLONE = '/mnt/new_partition/UnrealProjects/_BurrowerWork'
FOLDER = '/Game/Assets/Enemies/Burrower'
SK = FOLDER + '/SK_Burrower'
SKEL = FOLDER + '/SKEL_Burrower'
AUTO_SKEL = FOLDER + '/SK_Burrower_Skeleton'
AUTO_PA = FOLDER + '/SK_Burrower_PhysicsAsset'
PA_FINAL = FOLDER + '/PA_Burrower'
GREY = FOLDER + '/M_Burrower_Grey'
FBX = CLONE + '/SourceArt/Burrower/Burrower_UE.fbx'
RIG_INFO = CLONE + '/SourceArt/Burrower/Burrower_rig_info.json'
REPORT = CLONE + '/Saved/Burrower/import_report.json'

# ------------------------------------------------------------------------------------------------ expected data
# Component-space reference positions (cm), computed offline from the FBX node transforms with the FBX->UE mapping
# UE = (x, z_fbx, y_fbx) (Y-up RH -> Z-up LH, no Force Front X); identical to control_rig_recipe.md Step 0.
EXPECTED_POS = {
    'root': (0.0, 0.0, 0.0),
    'J0_Head': (1000.0, 0.0, 180.0),
    'J1_Forequarters': (660.0, 0.0, 193.0),
    'J2_Midbody': (260.0, 0.0, 200.0),
    'J3_Hindbody': (-260.0, 0.0, 200.0),
    'J4_Tail': (-560.0, 0.0, 202.0),
    'pipe_upperhose_l_01': (700.0, -33.6, 383.8),
    'pipe_upperhose_l_02': (671.1, -33.7, 385.4),
    'pipe_upperhose_l_03': (642.4, -34.1, 389.4),
    'pipe_upperhose_l_04': (613.5, -35.3, 389.4),
    'pipe_upperhose_l_05': (584.7, -36.9, 391.1),
    'pipe_upperhose_l_06': (556.7, -38.1, 397.4),
    'pipe_upperhose_l_07': (534.8, -41.3, 416.0),
    'pipe_upperhose_l_end': (507.2, -42.0, 424.7),
    'pipe_upperhose_r_01': (700.0, 33.6, 383.8),
    'pipe_upperhose_r_02': (667.2, 33.8, 385.7),
    'pipe_upperhose_r_03': (634.7, 34.4, 390.0),
    'pipe_upperhose_r_04': (601.9, 36.0, 388.7),
    'pipe_upperhose_r_05': (569.5, 37.4, 393.4),
    'pipe_upperhose_r_end': (542.6, 40.3, 410.4),
    'pipe_uppercable_l_01': (706.3, -47.6, 384.5),
    'pipe_uppercable_l_02': (676.0, -48.8, 387.1),
    'pipe_uppercable_l_03': (645.8, -49.1, 390.6),
    'pipe_uppercable_l_04': (615.5, -50.3, 391.5),
    'pipe_uppercable_l_05': (585.3, -51.9, 393.1),
    'pipe_uppercable_l_06': (556.6, -53.4, 401.4),
    'pipe_uppercable_l_07': (533.1, -57.8, 419.6),
    'pipe_uppercable_l_end': (507.9, -66.1, 429.9),
    'pipe_uppercable_r_01': (706.3, 47.6, 384.5),
    'pipe_uppercable_r_02': (677.0, 48.8, 387.1),
    'pipe_uppercable_r_03': (647.7, 49.0, 390.3),
    'pipe_uppercable_r_04': (618.3, 50.1, 391.6),
    'pipe_uppercable_r_05': (588.9, 51.6, 392.1),
    'pipe_uppercable_r_06': (560.6, 53.1, 399.8),
    'pipe_uppercable_r_07': (537.0, 56.1, 417.1),
    'pipe_uppercable_r_08': (510.6, 56.7, 429.1),
    'pipe_uppercable_r_09': (496.4, 61.6, 453.8),
    'pipe_uppercable_r_end': (479.2, 66.1, 472.7),
    'pipe_side_l_a_01': (543.0, -169.7, 110.1),
    'pipe_side_l_a_02': (518.3, -169.1, 101.9),
    'pipe_side_l_a_03': (497.4, -161.7, 83.6),
    'pipe_side_l_a_04': (476.7, -151.0, 67.0),
    'pipe_side_l_a_05': (454.8, -139.8, 52.4),
    'pipe_side_l_a_06': (427.8, -145.2, 52.5),
    'pipe_side_l_a_07': (404.0, -158.7, 61.2),
    'pipe_side_l_a_end': (391.7, -158.3, 69.6),
    'pipe_side_l_b_01': (543.1, -180.0, 144.5),
    'pipe_side_l_b_02': (520.3, -180.0, 134.0),
    'pipe_side_l_b_03': (504.3, -173.8, 109.3),
    'pipe_side_l_b_04': (487.6, -163.6, 86.5),
    'pipe_side_l_b_05': (470.9, -149.8, 65.6),
    'pipe_side_l_b_06': (444.9, -150.1, 60.3),
    'pipe_side_l_b_07': (422.3, -164.9, 73.5),
    'pipe_side_l_b_end': (410.2, -165.7, 85.2),
    'pipe_side_r_a_01': (543.0, 169.7, 110.1),
    'pipe_side_r_a_02': (518.3, 169.1, 101.9),
    'pipe_side_r_a_03': (497.4, 161.7, 83.6),
    'pipe_side_r_a_04': (476.7, 151.0, 67.0),
    'pipe_side_r_a_05': (454.8, 139.8, 52.4),
    'pipe_side_r_a_06': (427.8, 145.2, 52.5),
    'pipe_side_r_a_07': (404.0, 158.7, 61.2),
    'pipe_side_r_a_end': (391.7, 158.3, 69.6),
    'pipe_side_r_b_01': (543.1, 180.0, 144.5),
    'pipe_side_r_b_02': (520.3, 180.0, 134.0),
    'pipe_side_r_b_03': (504.3, 173.8, 109.3),
    'pipe_side_r_b_04': (487.6, 163.6, 86.5),
    'pipe_side_r_b_05': (470.9, 149.8, 65.6),
    'pipe_side_r_b_06': (444.9, 150.1, 60.3),
    'pipe_side_r_b_07': (422.3, 164.9, 73.5),
    'pipe_side_r_b_end': (410.2, 165.7, 85.2),
    'Rotor': (977.9, 0.0, 180.5),
}
# Mesh bounds over all FBX vertices in UE space (cm).
EXPECTED_BOUNDS_MIN = (-1017.4, -207.1, -31.3)
EXPECTED_BOUNDS_MAX = (1005.8, 207.1, 628.4)
EXPECTED_TRIS = 1239170          # sum over the 45 FBX parts (triangulated)
EXPECTED_FBX_VERTS = 649399      # FBX control points over the 45 parts
# Per material slot: FBX part, its control points, body bones that dominate >= 2 % of its vertices (first = most),
# and how many pipe bones dominate at least one vertex of it (computed offline from the FBX clusters).
EXPECTED_SLOTS = {
    'M_SEG_1.1.1': ('L3_1_1_1_CutterRotor', 16090, ('Rotor',), 0),
    'M_SEG_1.1.2': ('L3_1_1_2_MawBezel', 11100, ('J0_Head',), 0),
    'M_SEG_1.2.1': ('L3_1_2_1_BrowPlate', 16980, ('J0_Head',), 0),
    'M_SEG_1.2.2': ('L3_1_2_2_CheekHousing', 27340, ('J0_Head',), 0),
    'M_SEG_1.2.3': ('L3_1_2_3_JawGuard', 10236, ('J0_Head',), 0),
    'M_SEG_1.3.1': ('L3_1_3_1_CrestSpines', 4077, ('J0_Head',), 0),
    'M_SEG_1.3.2': ('L3_1_3_2_CrestFrame', 5070, ('J0_Head',), 0),
    'M_SEG_1.4.1': ('L3_1_4_1_CranialMuscle', 19200, ('J0_Head', 'J1_Forequarters'), 0),
    'M_SEG_1.4.2': ('L3_1_4_2_CheekMuscle', 30412, ('J0_Head', 'J1_Forequarters'), 0),
    'M_SEG_2.1.1': ('L3_2_1_1_CollarPlateUpper', 20601, ('J1_Forequarters',), 0),
    'M_SEG_2.1.2': ('L3_2_1_2_CollarGrille', 11246, ('J1_Forequarters',), 0),
    'M_SEG_2.2.1': ('L3_2_2_1_ShoulderPauldron', 16730, ('J1_Forequarters',), 0),
    'M_SEG_2.2.2': ('L3_2_2_2_FlankPlates', 19864, ('J1_Forequarters',), 0),
    'M_SEG_2.3.1': ('L3_2_3_1_ShoulderJoint', 9360, ('J1_Forequarters',), 0),
    'M_SEG_2.3.2': ('L3_2_3_2_PistonCluster', 19840, ('J1_Forequarters',), 28),
    'M_SEG_2.4.1': ('L3_2_4_1_NeckMuscleUpper', 13636, ('J1_Forequarters', 'J2_Midbody'), 0),
    'M_SEG_2.4.2': ('L3_2_4_2_NeckMuscleLower', 19586, ('J1_Forequarters',), 0),
    'M_SEG_3.1.1': ('L3_3_1_1_CanisterNear', 11778, ('J1_Forequarters',), 0),
    'M_SEG_3.1.2': ('L3_3_1_2_CanisterFar', 11778, ('J1_Forequarters',), 0),
    'M_SEG_3.1.3': ('L3_3_1_3_CanisterCaps', 7526, ('J1_Forequarters',), 0),
    'M_SEG_3.2.1': ('L3_3_2_1_MountBlock', 8052, ('J1_Forequarters',), 0),
    'M_SEG_3.2.2': ('L3_3_2_2_MountCradle', 12464, ('J1_Forequarters',), 0),
    'M_SEG_3.3.1': ('L3_3_3_1_ConduitFront', 11878, ('J1_Forequarters',), 28),
    'M_SEG_3.3.2': ('L3_3_3_2_ConduitRear', 8956, ('J2_Midbody', 'J1_Forequarters'), 0),
    'M_SEG_3.4.1': ('L3_3_4_1_VentHousing', 6216, ('J2_Midbody',), 0),
    'M_SEG_3.4.2': ('L3_3_4_2_VentFins', 2784, ('J2_Midbody',), 0),
    'M_SEG_4.1.1': ('L3_4_1_1_UpperBraidFront', 21537, ('J2_Midbody', 'J1_Forequarters'), 0),
    'M_SEG_4.1.2': ('L3_4_1_2_UpperBraidRear', 31723, ('J2_Midbody',), 0),
    'M_SEG_4.2.1': ('L3_4_2_1_LowerBraidFront', 17955, ('J2_Midbody', 'J1_Forequarters'), 0),
    'M_SEG_4.2.2': ('L3_4_2_2_LowerBraidRear', 21543, ('J2_Midbody',), 0),
    'M_SEG_4.3.1': ('L3_4_3_1_RidgeNubs', 6942, ('J2_Midbody', 'J3_Hindbody'), 0),
    'M_SEG_4.3.2': ('L3_4_3_2_RidgeCables', 13100, ('J2_Midbody', 'J3_Hindbody'), 0),
    'M_SEG_5.1.1': ('L3_5_1_1_CarapaceFront', 13885, ('J3_Hindbody', 'J2_Midbody'), 0),
    'M_SEG_5.1.2': ('L3_5_1_2_CarapaceRear', 12044, ('J3_Hindbody', 'J4_Tail'), 0),
    'M_SEG_5.2.1': ('L3_5_2_1_HindFlankMuscle', 29642, ('J3_Hindbody', 'J2_Midbody', 'J4_Tail'), 0),
    'M_SEG_5.2.2': ('L3_5_2_2_HindKeelStrip', 10980, ('J3_Hindbody', 'J4_Tail'), 0),
    'M_SEG_6.1.1': ('L3_6_1_1_RootMuscle', 15648, ('J4_Tail', 'J3_Hindbody'), 0),
    'M_SEG_6.1.2': ('L3_6_1_2_RootCollar', 11264, ('J4_Tail',), 0),
    'M_SEG_6.2.1': ('L3_6_2_1_TailBladeUpper', 7980, ('J4_Tail',), 0),
    'M_SEG_6.2.2': ('L3_6_2_2_TailBladeLower', 11254, ('J4_Tail',), 0),
    'M_SEG_6.2.3': ('L3_6_2_3_TailTip', 4711, ('J4_Tail',), 0),
    'M_SEG_7.1.1': ('L3_7_1_1_GulletTeethFront', 18064, ('J0_Head',), 0),
    'M_SEG_7.1.2': ('L3_7_1_2_GulletTeethRear', 17708, ('J1_Forequarters',), 0),
    'M_SEG_7.2.1': ('L3_7_2_1_VentralPlatesFront', 10480, ('J1_Forequarters', 'J2_Midbody'), 0),
    'M_SEG_7.2.2': ('L3_7_2_2_VentralPlatesRear', 20139, ('J2_Midbody',), 0),
}
BODY_PARENTS = {'root': None, 'J0_Head': 'root', 'J1_Forequarters': 'J0_Head', 'J2_Midbody': 'J1_Forequarters',
                'J3_Hindbody': 'J2_Midbody', 'J4_Tail': 'J3_Hindbody', 'Rotor': 'root'}


# ------------------------------------------------------------------------------------------------ helpers
class _Results(object):
    def __init__(self):
        self.counts = collections.OrderedDict([('PASS', 0), ('FAIL', 0), ('WARN', 0), ('INFO', 0)])
        self.checks = collections.OrderedDict()
        self.actions = []
        self.data = collections.OrderedDict()

    def out(self, kind, key, msg, **data):
        self.counts[kind] = self.counts.get(kind, 0) + 1
        print('%s: [%s] %s' % (kind, key, msg))
        entry = {'status': kind, 'msg': msg}
        for k, v in data.items():
            entry[k] = v
        self.checks.setdefault(key, []).append(entry)

    def check(self, ok, key, msg, warn_only=False, **data):
        self.out('PASS' if ok else ('WARN' if warn_only else 'FAIL'), key, msg, **data)
        return ok

    def action(self, msg):
        self.actions.append(msg)
        print('INFO: [action] ' + msg)


def _enum(enum_name, value_name):
    """unreal.<enum_name>.<value_name>; raises with a clear message if the Python name differs."""
    e = getattr(unreal, enum_name)
    return getattr(e, value_name)


def _setp(R, obj, prop, value, critical=True):
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as e:
        R.out('FAIL' if critical else 'WARN', 'options', 'could not set %s.%s = %r: %s' % (
            obj.get_class().get_name(), prop, value, e))
        return False


def _pkg(obj):
    """'/Game/A/B.B' -> '/Game/A/B' (None-safe)."""
    if obj is None:
        return None
    return obj.get_path_name().split('.')[0]


def _ours(path):
    return isinstance(path, str) and path.startswith(FOLDER + '/')


def _exists(path):
    try:
        return bool(unreal.EditorAssetLibrary.does_asset_exist(path))
    except Exception:
        return False


def _ar():
    return unreal.AssetRegistryHelpers.get_asset_registry()


def _folder_assets():
    """{package_name: AssetData} for everything (in memory or on disk) in our folder."""
    out = {}
    try:
        lst = _ar().get_assets_by_path(FOLDER, True, False) or []
        for a in lst:
            out[str(a.package_name)] = a
    except Exception as e:
        print('WARN: [registry] get_assets_by_path failed: %s' % e)
    return out


def _class_name(ad):
    try:
        c = ad.get_class()
        return c.get_name() if c else '?'
    except Exception:
        return '?'


def _referencers(pkg):
    try:
        r = _ar().get_referencers(pkg, unreal.AssetRegistryDependencyOptions())
        return [str(x) for x in (r or [])]
    except Exception as e:
        print('WARN: [registry] get_referencers(%s) failed: %s' % (pkg, e))
        return []


def _delete_ours(R, path):
    if not _ours(path):
        R.out('FAIL', 'safety', 'refused to delete %s (outside %s)' % (path, FOLDER))
        return False
    if not _exists(path):
        return True
    ok = bool(unreal.EditorAssetLibrary.delete_asset(path))
    R.check(ok, 'cleanup', 'deleted %s' % path if ok else 'could not delete %s' % path)
    if ok:
        R.action('deleted ' + path)
    return ok


def _save_ours(R, path):
    if not _ours(path):
        R.out('FAIL', 'safety', 'refused to save %s (outside %s)' % (path, FOLDER))
        return False
    try:
        ok = bool(unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False))
    except Exception as e:
        ok = False
        print('FAIL: [save] %s: %s' % (path, e))
    R.check(ok, 'save', ('saved ' if ok else 'could not save ') + path)
    return ok


def _free_gb():
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1048576.0
    except Exception:
        pass
    return -1.0


def _vec(v):
    return (float(v.x), float(v.y), float(v.z))


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _norm_slot(name):
    return str(name).replace('.', '_').strip()


# ------------------------------------------------------------------------------------------------ import routes
def _import_legacy(R, skeleton_obj):
    """Legacy UFbxFactory with an explicit UFbxImportUI. All properties verified in Classes/Factories/Fbx*.h (5.8)."""
    ui = unreal.FbxImportUI()
    ok = True
    sk_type = _enum('FBXImportType', 'FBXIT_SKELETAL_MESH')
    # order matters only for readability; UFbxImportUI has no PostEditChangeProperty
    ok &= _setp(R, ui, 'import_mesh', True)
    ok &= _setp(R, ui, 'import_as_skeletal', True)
    ok &= _setp(R, ui, 'mesh_type_to_import', sk_type)
    ok &= _setp(R, ui, 'original_import_type', sk_type)          # else bImportRigidMesh could be derived
    ok &= _setp(R, ui, 'automated_import_should_detect_type', False)
    ok &= _setp(R, ui, 'override_full_name', True)               # mesh is named exactly destination_name
    ok &= _setp(R, ui, 'create_physics_asset', False)            # PA_Burrower comes from step 3
    ok &= _setp(R, ui, 'physics_asset', None, critical=False)
    ok &= _setp(R, ui, 'import_animations', False)
    ok &= _setp(R, ui, 'import_materials', False)                # 45 slots named after the FBX materials; legacy
                                                                 # MakeName turns '.' into '_' (FbxMainImport.cpp:1872)
                                                                 # -> M_SEG_1_1_1; the checks accept both spellings
    ok &= _setp(R, ui, 'import_textures', False)
    ok &= _setp(R, ui, 'skeleton', skeleton_obj)                 # None -> new skeleton SK_Burrower_Skeleton
    smd = ui.get_editor_property('skeletal_mesh_import_data')
    ok &= _setp(R, smd, 'import_content_type', _enum('FBXImportContentType', 'FBXICT_ALL'))
    ok &= _setp(R, smd, 'normal_import_method', _enum('FBXNormalImportMethod', 'FBXNIM_IMPORT_NORMALS'))
    ok &= _setp(R, smd, 'convert_scene', True)                   # FBX Y-up -> UE Z-up (no Force Front X)
    ok &= _setp(R, smd, 'force_front_x_axis', False)
    ok &= _setp(R, smd, 'convert_scene_unit', False)             # file is cm (UnitScaleFactor 1): no unit tricks
    ok &= _setp(R, smd, 'import_uniform_scale', 1.0)
    ok &= _setp(R, smd, 'import_translation', unreal.Vector(0.0, 0.0, 0.0))
    ok &= _setp(R, smd, 'import_rotation', unreal.Rotator(0.0, 0.0, 0.0))
    ok &= _setp(R, smd, 'import_morph_targets', False)
    ok &= _setp(R, smd, 'import_mesh_lods', False)               # ScriptName of bImportMeshLODs
    ok &= _setp(R, smd, 'use_t0_as_ref_pose', False)             # bind pose from the 45 FBX BindPose nodes
    ok &= _setp(R, smd, 'update_skeleton_reference_pose', False)
    # non-critical
    _setp(R, smd, 'keep_sections_separate', False, critical=False)
    _setp(R, smd, 'preserve_smoothing_groups', True, critical=False)
    _setp(R, smd, 'import_meshes_in_bone_hierarchy', True, critical=False)
    _setp(R, smd, 'import_vertex_attributes', False, critical=False)
    _setp(R, smd, 'bake_pivot_in_vertex', False, critical=False)
    _setp(R, smd, 'reorder_material_to_fbx_order', True, critical=False)
    try:
        _setp(R, smd, 'vertex_color_import_option', _enum('VertexColorImportOption', 'IGNORE'), critical=False)
    except Exception as e:
        R.out('WARN', 'options', 'VertexColorImportOption.IGNORE not found (%s); left at default' % e)
    try:
        tex = ui.get_editor_property('texture_import_data')
        _setp(R, tex, 'material_search_location', _enum('MaterialSearchLocation', 'DO_NOT_SEARCH'), critical=False)
    except Exception as e:
        R.out('WARN', 'options', 'material_search_location not set (%s): the importer may bind slots to existing '
              'materials named M_SEG_* in this folder' % e)
    if not ok:
        R.out('FAIL', 'import', 'legacy import options incomplete, import not started (see FAIL options lines)')
        return None

    task = unreal.AssetImportTask()
    _setp(R, task, 'filename', FBX)
    _setp(R, task, 'destination_path', FOLDER)
    _setp(R, task, 'destination_name', 'SK_Burrower')
    _setp(R, task, 'replace_existing', True)
    _setp(R, task, 'replace_existing_settings', False, critical=False)
    _setp(R, task, 'automated', True)       # no dialogs; also required for the explicit factory to be used
    _setp(R, task, 'save', False)           # we save explicitly, after the skeleton rename
    _setp(R, task, 'factory', unreal.FbxFactory())   # explicit factory => legacy path, Interchange bypassed
    _setp(R, task, 'options', ui)
    t0 = time.time()
    # UNVERIFIED: running a big import (FScopedSlowTask dialogs) from the inbox's Slate post-tick callback; earlier
    # FBX imports on this PC went through editor Python too. If the editor hangs here, run this file once from
    # Tools > Execute Python Script instead (same code, same checks).
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    R.data['import_seconds'] = round(time.time() - t0, 1)
    try:
        paths = [str(p) for p in task.get_editor_property('imported_object_paths')]
    except Exception:
        paths = []
    R.out('INFO', 'import', 'legacy FbxFactory import took %.1f s, imported_object_paths=%s' % (
        R.data['import_seconds'], paths))
    R.data['imported_object_paths'] = paths
    return paths


def _import_interchange(R, skeleton_obj):
    """Fallback: Interchange with an explicit InterchangeGenericAssetsPipeline (InterchangeGenericAssetsPipeline.h,
    InterchangeGenericMeshPipeline.h, InterchangeGenericAssetsPipelineSharedSettings.h, InterchangeManager.h)."""
    # 1) the translator settings come from the user's ini; refuse if they would rotate the mesh
    try:
        ts = unreal.InterchangeFbxTranslatorSettings()
        ts.load_settings()
        ffx = bool(ts.get_editor_property('force_front_x_axis'))
        cs = bool(ts.get_editor_property('convert_scene'))
        csu = bool(ts.get_editor_property('convert_scene_unit'))
        ufbx = bool(ts.get_editor_property('use_ufbx_parser'))
        R.out('INFO', 'interchange', 'user FBX translator settings: convert_scene=%s force_front_x_axis=%s '
              'convert_scene_unit=%s use_ufbx_parser=%s' % (cs, ffx, csu, ufbx))
        if ffx or not cs:
            R.out('FAIL', 'interchange', 'Interchange FBX translator settings in EditorPerProjectUserSettings.ini have '
                  'Force Front X Axis on or Convert Scene off; the import would be rotated. Use the legacy route '
                  '(USE_INTERCHANGE = False) or reset them in an import dialog (Translator settings), then rerun.')
            return None
    except Exception as e:
        R.out('WARN', 'interchange', 'could not read InterchangeFbxTranslatorSettings (%s); defaults assumed' % e)

    p = unreal.InterchangeGenericAssetsPipeline()
    ok = True
    ok &= _setp(R, p, 'use_source_name_for_asset', False)
    ok &= _setp(R, p, 'asset_name', 'SK_Burrower')
    ok &= _setp(R, p, 'scene_name_sub_folder', False)
    ok &= _setp(R, p, 'asset_type_sub_folders', False)
    ok &= _setp(R, p, 'import_offset_translation', unreal.Vector(0.0, 0.0, 0.0))
    ok &= _setp(R, p, 'import_offset_rotation', unreal.Rotator(0.0, 0.0, 0.0))
    ok &= _setp(R, p, 'import_offset_uniform_scale', 1.0)
    cm = p.get_editor_property('common_meshes_properties')
    ok &= _setp(R, cm, 'force_all_mesh_as_type', _enum('InterchangeForceMeshType', 'IFMT_SKELETAL_MESH'))
    ok &= _setp(R, cm, 'import_lods', False)
    ok &= _setp(R, cm, 'recompute_normals', False)      # keep the FBX normals
    _setp(R, cm, 'recompute_tangents', True, critical=False)
    _setp(R, cm, 'keep_sections_separate', False, critical=False)
    _setp(R, cm, 'bake_meshes', True, critical=False)
    cs_ = p.get_editor_property('common_skeletal_meshes_and_animations_properties')
    ok &= _setp(R, cs_, 'import_only_animations', False)
    ok &= _setp(R, cs_, 'use_t0_as_ref_pose', False)
    if skeleton_obj is not None:
        ok &= _setp(R, cs_, 'skeleton', skeleton_obj)
    mp = p.get_editor_property('mesh_pipeline')
    ok &= _setp(R, mp, 'import_static_meshes', False)
    ok &= _setp(R, mp, 'import_skeletal_meshes', True)
    ok &= _setp(R, mp, 'skeletal_mesh_import_content_type', _enum('InterchangeSkeletalMeshContentType', 'ALL'))
    ok &= _setp(R, mp, 'combine_skeletal_meshes_behavior', _enum('InterchangeCombineSkeletalMeshesBehavior', 'BY_SKELETON'))
    ok &= _setp(R, mp, 'import_morph_targets', False)
    ok &= _setp(R, mp, 'update_skeleton_reference_pose', False)
    ok &= _setp(R, mp, 'create_physics_asset', False)
    ap = p.get_editor_property('animation_pipeline')
    ok &= _setp(R, ap, 'import_animations', False)
    # UNVERIFIED: with import_materials False Interchange should still create the 45 named slots (empty); the checks
    # report the slot count either way. AdjustSettingsForContext may also change some pipeline values for FBX.
    mat = p.get_editor_property('material_pipeline')
    ok &= _setp(R, mat, 'import_materials', False)
    if not ok:
        R.out('FAIL', 'import', 'Interchange pipeline options incomplete, import not started')
        return None
    params = unreal.ImportAssetParameters()
    ok &= _setp(R, params, 'is_automated', True)
    ok &= _setp(R, params, 'replace_existing', True)
    ok &= _setp(R, params, 'destination_name', 'SK_Burrower')
    # SoftObjectPath(str) uses its HasNativeMake MakeSoftObjectPath (SoftObjectPath.h:54); the transient pipeline is
    # resolved with TryLoad and duplicated (InterchangeManager.cpp:807/845), so keep 'p' alive until the import ends.
    ok &= _setp(R, params, 'override_pipelines', [unreal.SoftObjectPath(p.get_path_name())])
    if not ok:
        return None
    src = unreal.InterchangeManager.create_source_data(FBX)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    t0 = time.time()
    res = mgr.import_asset(FOLDER, src, params)    # bool + out list -> list or None (PyGenUtil PackReturnValues)
    R.data['import_seconds'] = round(time.time() - t0, 1)
    paths = [_pkg(o) for o in (res or []) if o is not None]
    R.out('INFO' if res is not None else 'FAIL', 'import', 'Interchange import took %.1f s, objects=%s' % (
        R.data['import_seconds'], paths))
    R.data['imported_object_paths'] = paths
    return paths if res is not None else None


# ------------------------------------------------------------------------------------------------ fix-ups
def _ensure_skeleton_name(R, skm):
    skel = None
    try:
        skel = skm.skeleton                       # BlueprintGetter GetSkeleton
    except Exception:
        skel = skm.get_editor_property('skeleton')
    if skel is None:
        R.out('FAIL', 'skeleton_asset', 'SK_Burrower has no skeleton')
        return None
    sp = _pkg(skel)
    if sp == SKEL:
        R.out('PASS', 'skeleton_asset', 'skeleton is %s' % SKEL)
        return skel
    if not _ours(sp):
        R.out('FAIL', 'skeleton_asset', 'skeleton %s is outside our folder; not renamed. Re-import with '
              'EXISTING=recreate (new skeleton) or fix by hand.' % sp)
        return skel
    if _exists(SKEL):
        R.out('FAIL', 'skeleton_asset', 'mesh uses %s but %s also exists; not renamed (check which one PA/CR/ABP '
              'use, delete the other, rerun)' % (sp, SKEL))
        return skel
    outside = [r for r in _referencers(sp) if not _ours(r)]
    if outside:
        R.out('FAIL', 'skeleton_asset', 'not renaming %s: referenced from outside our folder %s (the rename would '
              'save those packages)' % (sp, outside))
        return skel
    ok = bool(unreal.EditorAssetLibrary.rename_asset(sp, SKEL))
    R.check(ok, 'skeleton_asset', ('renamed %s -> %s' if ok else 'rename %s -> %s failed (FAssetRenameManager refuses '
            'while the asset registry is still scanning: wait, then rerun with EXISTING=reuse; it renames and saves)')
            % (sp, SKEL))
    if ok:
        R.action('renamed skeleton %s -> %s' % (sp, SKEL))
        skel = unreal.EditorAssetLibrary.load_asset(SKEL)
    return skel


def _fix_redirectors(R):
    fixed = []
    for pkg, ad in _folder_assets().items():
        try:
            is_redir = bool(ad.is_redirector())
        except Exception:
            is_redir = _class_name(ad) == 'ObjectRedirector'
        if not is_redir:
            continue
        refs = [r for r in _referencers(pkg) if r != pkg]
        outside = [r for r in refs if not _ours(r)]
        if outside:
            R.out('WARN', 'redirectors', 'redirector %s is referenced from outside our folder %s; left alone '
                  '(fix by hand: right-click the folder > Fix Up Redirectors)' % (pkg, outside))
            continue
        for r in refs:                       # resave in-folder referencers so they point at the real asset
            obj = unreal.EditorAssetLibrary.load_asset(r)
            if obj is not None:
                _save_ours(R, r)
        if [x for x in _referencers(pkg) if x != pkg]:
            R.out('WARN', 'redirectors', 'redirector %s still referenced after resaving %s; left alone' % (pkg, refs))
            continue
        if _delete_ours(R, pkg):
            fixed.append(pkg)
    R.out('INFO', 'redirectors', 'redirectors fixed in %s: %s' % (FOLDER, fixed or 'none'))
    return fixed


def _ensure_grey_material(R):
    if _exists(GREY):
        m = unreal.EditorAssetLibrary.load_asset(GREY)
        if isinstance(m, unreal.MaterialInterface):
            return m, False
        R.out('FAIL', 'materials', '%s exists but is not a material; slots left empty' % GREY)
        return None, False
    try:
        at = unreal.AssetToolsHelpers.get_asset_tools()
        m = at.create_asset('M_Burrower_Grey', FOLDER, unreal.Material, unreal.MaterialFactoryNew())
        MEL = unreal.MaterialEditingLibrary
        c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -500, -150)
        c.set_editor_property('constant', unreal.LinearColor(0.30, 0.31, 0.33, 1.0))
        MEL.connect_material_property(c, '', unreal.MaterialProperty.MP_BASE_COLOR)
        r = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -500, 50)
        r.set_editor_property('r', 0.55)
        MEL.connect_material_property(r, '', unreal.MaterialProperty.MP_ROUGHNESS)
        mt = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -500, 200)
        mt.set_editor_property('r', 0.25)
        MEL.connect_material_property(mt, '', unreal.MaterialProperty.MP_METALLIC)
        try:   # MaterialEditingLibrary.h:204 SetBaseMaterialUsage (SetMaterialUsage is deprecated in 5.8)
            MEL.set_base_material_usage(m, _enum('MaterialUsage', 'MATUSAGE_SKELETAL_MESH'), True)
        except Exception as e:
            R.out('WARN', 'materials', 'set_base_material_usage(SkeletalMesh) failed (%s); the editor sets the flag '
                  'on first use and marks the material dirty - save it then' % e)
        MEL.recompile_material(m)
        R.action('created ' + GREY)
        return m, True
    except Exception as e:
        R.out('FAIL', 'materials', 'could not create %s: %s' % (GREY, e))
        return None, False


def _fill_empty_slots(R, skm, mat):
    """Assign mat to every slot without a material. Uses the BlueprintSetter SetMaterials (attribute assignment),
    which does not run PostEditChangeProperty, so the 1.24 M triangle mesh is not rebuilt (SkeletalMesh.cpp:1525)."""
    mats = skm.materials
    n = 0
    for i in range(len(mats)):
        m = mats[i]
        if m.get_editor_property('material_interface') is None:
            m.set_editor_property('material_interface', mat)
            mats[i] = m
            n += 1
    if n:
        try:
            skm.materials = mats
        except Exception as e:
            R.out('WARN', 'materials', 'attribute setter failed (%s); using set_editor_property(notify NEVER)' % e)
            skm.set_editor_property('materials', mats, _enum('PropertyAccessChangeNotifyMode', 'NEVER'))
        try:
            skm.modify()
        except Exception:
            pass
        R.action('put %s on %d empty slot(s)' % (GREY, n))
    return n


def _cleanup_new_assets(R, before, skm):
    """Delete physics assets / animations that THIS import created in our folder (never anything else)."""
    after = _folder_assets()
    new = [p for p in after if p not in before]
    R.out('INFO', 'new_assets', 'created by this import: %s' % sorted(new))
    R.data['new_assets'] = sorted(new)
    for p in new:
        cn = _class_name(after[p])
        if cn in ('PhysicsAsset', 'AnimSequence', 'AnimMontage', 'PoseAsset'):
            if cn == 'PhysicsAsset':
                try:
                    if _pkg(skm.physics_asset) == p:
                        skm.set_editor_property('physics_asset', None,
                                                _enum('PropertyAccessChangeNotifyMode', 'NEVER'))
                        skm.modify()
                except Exception as e:
                    R.out('WARN', 'cleanup', 'could not clear physics_asset on the mesh: %s' % e)
            R.out('WARN', 'cleanup', 'the import created %s %s although it was switched off; deleting it' % (cn, p))
            _delete_ours(R, p)


# ------------------------------------------------------------------------------------------------ checks
def _check_all(R, skm, rig):
    SMES = unreal.SkeletalMeshEditorSubsystem
    smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    bone_order = list(rig.get('bone_order', []))
    exp_parent = dict(BODY_PARENTS)
    for ch in rig.get('chains', []):
        prev = ch['parent']
        for b in list(ch['bones']) + [ch['end_bone']]:
            exp_parent[b] = prev
            prev = b

    # ---- skeleton asset / bones
    try:
        skel = skm.skeleton
    except Exception:
        skel = skm.get_editor_property('skeleton')
    R.check(_pkg(skel) == SKEL, 'skeleton_asset', 'mesh skeleton = %s (want %s)' % (_pkg(skel), SKEL))
    names, pose, wspace = [], None, None
    try:
        APE = unreal.AnimPoseExtensions
        pose = APE.get_reference_pose(skel)          # AnimPose.h:329, built from the skeleton's ref skeleton
        names = [str(n) for n in APE.get_bone_names(pose)]
        wspace = _enum('AnimPoseSpaces', 'WORLD')     # EAnimPoseSpaces::World = component space
    except Exception as e:
        R.out('FAIL', 'bones', 'AnimPoseExtensions failed (%s); bone checks skipped' % e)
    R.data['bone_count'] = len(names)
    R.check(len(names) == 71, 'bone_count', 'reference skeleton has %d bones (want 71)' % len(names), count=len(names))
    missing = [b for b in bone_order if b not in names]
    extra = [b for b in names if b not in bone_order]
    R.check(not missing and not extra, 'bone_names', 'vs rig_info bone_order: missing=%s extra=%s' % (missing, extra),
            missing=missing, extra=extra)
    if names == bone_order:
        R.out('PASS', 'bone_order', 'bone order identical to rig_info bone_order')
    else:
        R.out('INFO', 'bone_order', 'bone order differs from rig_info (allowed, UE only needs parents first): %s'
              % names)
    R.data['bone_names'] = names

    # ---- hierarchy (mesh ref skeleton; SkeletalMeshEditorSubsystem.h:234/242, static, null-safe)
    parent_of = {}
    for n in names:
        try:
            p = str(SMES.get_bone_parent(skm, n))
        except Exception as e:
            p = '?err %s' % e
        parent_of[n] = None if p in ('None', '') else p
    roots = [n for n in names if parent_of.get(n) is None]
    R.data['roots'] = roots
    if roots == ['root']:
        R.out('PASS', 'root_bone', 'root bone = root (the FBX "Armature" node did not become a bone)')
    else:
        R.out('FAIL', 'root_bone', 'root bone(s) = %s, want [\'root\']. A bone above root (e.g. the FBX "Armature" '
              'node) was imported. Either re-import (both importers drop it only if it is named "Armature" directly '
              'under the scene root and the FBX creator string starts with "Blender"), or accept it and adjust the '
              'rig: everything in the recipe hangs below root, and component positions are unchanged while that '
              'extra bone is identity.' % roots)
    try:
        kids = sorted(str(c) for c in SMES.get_bone_children(skm, 'root'))
    except Exception as e:
        kids = []
        R.out('WARN', 'root_children', 'get_bone_children failed: %s' % e)
    R.check('J0_Head' in kids and 'Rotor' in kids, 'root_children', 'root children = %s (want J0_Head and Rotor)' % kids,
            children=kids)
    bad_par = []
    for b, want in exp_parent.items():
        if b not in parent_of:
            continue
        if parent_of[b] != want:
            bad_par.append((b, parent_of[b], want))
    R.check(not bad_par, 'parents', '%d/%d parents as expected (J1->J0_Head, J2->J1, J3->J2, J4->J3, Rotor->root, '
            'every pipe _01 -> J1_Forequarters, chains in order)%s' % (
                len([b for b in exp_parent if b in parent_of]) - len(bad_par), len(exp_parent),
                '' if not bad_par else '; wrong (bone, got, want): %s' % bad_par), wrong=bad_par)
    pipe01 = sorted(set(parent_of.get(b) for b in names if b.startswith('pipe_') and b.endswith('_01')))
    R.out('INFO', 'parents', 'parents of the pipe _01 bones: %s' % pipe01)

    # ---- reference pose, component space
    pos = {}
    if pose is not None:
        for n in names:
            try:
                t = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, n, wspace)
                pos[n] = _vec(t.translation)
            except Exception as e:
                R.out('WARN', 'positions', 'get_ref_bone_pose(%s) failed: %s' % (n, e))
    R.data['positions'] = {k: [round(c, 2) for c in v] for k, v in pos.items()}
    worst, bad = 0.0, []
    worst_m, bad_m = 0.0, []
    for b, e in EXPECTED_POS.items():
        if b not in pos:
            continue
        d = _dist(pos[b], e)
        dm = _dist(pos[b], (e[0], -e[1], e[2]))
        worst, worst_m = max(worst, d), max(worst_m, dm)
        if d > POS_TOL_CM:
            bad.append((b, [round(c, 1) for c in pos[b]], e, round(d, 1)))
        if dm > POS_TOL_CM:
            bad_m.append(b)
    for b in ('J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail', 'Rotor',
              'pipe_upperhose_l_01', 'pipe_upperhose_l_end', 'pipe_upperhose_r_01', 'pipe_upperhose_r_end',
              'pipe_uppercable_l_01', 'pipe_uppercable_l_end', 'pipe_uppercable_r_01', 'pipe_uppercable_r_end',
              'pipe_side_l_a_01', 'pipe_side_l_a_end', 'pipe_side_l_b_01', 'pipe_side_l_b_end',
              'pipe_side_r_a_01', 'pipe_side_r_a_end', 'pipe_side_r_b_01', 'pipe_side_r_b_end'):
        if b in pos:
            p = pos[b]
            R.out('INFO', 'positions', '%-22s (%8.1f, %7.1f, %6.1f)  want (%7.1f, %6.1f, %6.1f)  d=%.1f' % (
                b, p[0], p[1], p[2], EXPECTED_POS[b][0], EXPECTED_POS[b][1], EXPECTED_POS[b][2],
                _dist(p, EXPECTED_POS[b])))
    n_cmp = len([b for b in EXPECTED_POS if b in pos])
    if not bad and n_cmp:
        R.out('PASS', 'positions', '%d/%d bones within %.0f cm of the expected component-space ref pose (worst %.2f cm)'
              % (n_cmp, len(EXPECTED_POS), POS_TOL_CM, worst), worst_cm=round(worst, 2), compared=n_cmp)
    elif n_cmp and not bad_m:
        R.out('WARN', 'positions', 'all bones match only with Y MIRRORED (worst %.2f cm): the import flipped Y. The '
              'rig is Y-symmetric (recipe Step 0), so this is acceptable; note it in the report.' % worst_m,
              worst_cm_mirrored=round(worst_m, 2))
    else:
        R.out('FAIL', 'positions', '%d bone(s) off by more than %.0f cm (bone, got, want, d): %s' % (
            len(bad), POS_TOL_CM, bad[:12]), wrong=bad, worst_cm=round(worst, 2))
    ly = [pos[b][1] for b in pos if b.startswith('pipe_') and '_l_' in b]
    ry = [pos[b][1] for b in pos if b.startswith('pipe_') and '_r_' in b]
    if ly:
        sign = 'NEGATIVE' if max(ly) < 0 else ('POSITIVE' if min(ly) > 0 else 'MIXED')
        R.data['l_chain_y_sign'] = sign
        R.check(sign == 'NEGATIVE', 'l_chain_y_sign', '_l chains are at %s UE Y (y range %.1f..%.1f; _r %.1f..%.1f). '
                'Expected negative (UE Y = -Blender Y); positive is acceptable (symmetric rig) but must be noted.' % (
                    sign, min(ly), max(ly), min(ry) if ry else 0, max(ry) if ry else 0), warn_only=True)
    if 'J0_Head' in pos:
        R.check(pos['J0_Head'][0] > 900, 'head_forward', 'J0_Head x = %.1f (head toward +X)' % pos['J0_Head'][0])

    # ---- bounds
    try:
        b = skm.get_imported_bounds()
        o, e = _vec(b.origin), _vec(b.box_extent)
        mn = tuple(o[i] - e[i] for i in range(3))
        mx = tuple(o[i] + e[i] for i in range(3))
        R.data['bounds_min'] = [round(c, 1) for c in mn]
        R.data['bounds_max'] = [round(c, 1) for c in mx]
        dev = max([abs(mn[i] - EXPECTED_BOUNDS_MIN[i]) for i in range(3)] +
                  [abs(mx[i] - EXPECTED_BOUNDS_MAX[i]) for i in range(3)])
        R.check(dev <= BOUNDS_TOL_CM, 'bounds', 'imported bounds x %.1f..%.1f, y %.1f..%.1f, z %.1f..%.1f (want x '
                '-1017.4..1005.8, y -207.1..207.1, z -31.3..628.4; worst dev %.1f cm; length %.1f cm)' % (
                    mn[0], mx[0], mn[1], mx[1], mn[2], mx[2], dev, mx[0] - mn[0]), worst_cm=round(dev, 2))
        R.check(mx[2] - mn[2] < 700 and mx[0] - mn[0] > 1900, 'upright', 'height %.0f cm, length %.0f cm (upright, '
                'long axis X)' % (mx[2] - mn[2], mx[0] - mn[0]))
    except Exception as ex:
        R.out('FAIL', 'bounds', 'get_imported_bounds failed: %s' % ex)

    # ---- material slots
    slot_names = []
    try:
        mats = skm.materials
        for m in mats:
            nm = str(m.get_editor_property('imported_material_slot_name'))
            if nm in ('None', ''):
                nm = str(m.get_editor_property('material_slot_name'))
            slot_names.append(nm)
        mats_assigned = [_pkg(m.get_editor_property('material_interface')) for m in mats]
    except Exception as ex:
        mats_assigned = []
        R.out('FAIL', 'slots', 'reading materials failed: %s' % ex)
    R.data['slot_names'] = slot_names
    R.check(len(slot_names) == 45, 'slots', '%d material slots (want 45)' % len(slot_names), count=len(slot_names))
    want = set(_norm_slot(s) for s in EXPECTED_SLOTS)
    got = set(_norm_slot(s) for s in slot_names)
    R.check(want == got, 'slot_names', 'slot names vs FBX M_SEG_<id>: missing=%s extra=%s' % (
        sorted(want - got), sorted(got - want)))
    R.data['slot_materials'] = collections.Counter(str(x) for x in mats_assigned)
    R.out('INFO', 'slot_materials', 'materials on slots: %s' % dict(R.data['slot_materials']))
    if MATERIAL_MODE == 'grey':
        R.check(all(x is not None for x in mats_assigned), 'slot_materials', 'every slot has a material',
                warn_only=True)

    # ---- LOD0 sections / triangles / vertices
    try:
        nsec = smes.get_num_sections(skm, 0)
        used = set(smes.get_lod_material_slot(skm, 0, i) for i in range(max(nsec, 0)))
        R.data['lod0_sections'] = nsec
        R.data['lod0_section_slots'] = len(used)
        R.check(nsec >= 45 and len(used) == len(slot_names) == 45, 'sections', 'LOD0 has %d sections using %d distinct '
                'slots (want >= 45 sections covering all 45 slots: all parts in ONE mesh)' % (nsec, len(used)))
        R.data['lod0_render_vertices'] = smes.get_num_verts(skm, 0)
        R.out('INFO', 'vertices', 'LOD0 render vertices %d (FBX control points %d; render data splits at seams)' % (
            R.data['lod0_render_vertices'], EXPECTED_FBX_VERTS))
        R.data['lod_count'] = SMES.get_lod_count(skm)
        R.out('INFO', 'lods', 'LOD count %d' % R.data['lod_count'])
    except Exception as ex:
        R.out('FAIL', 'sections', 'section query failed: %s' % ex)
    try:
        ad = unreal.AssetRegistryHelpers.create_asset_data(skm)    # FAssetData(UObject*) gathers the tags
        tags = {}
        for t in ('Triangles', 'Vertices', 'Bones', 'LODs', 'MorphTargets', 'NaniteEnabled'):
            v = ad.get_tag_value(t)
            tags[t] = None if v is None else str(v)
        R.data['tags'] = tags
        tri = int(tags['Triangles']) if tags.get('Triangles') else -1
        R.data['lod0_triangles'] = tri
        R.check(abs(tri - EXPECTED_TRIS) <= EXPECTED_TRIS * 0.005, 'triangles', 'LOD0 triangles %d (FBX %d)' % (
            tri, EXPECTED_TRIS), count=tri)
        R.check(tags.get('MorphTargets') in ('0', None), 'morphs', 'morph targets: %s' % tags.get('MorphTargets'),
                warn_only=True)
        R.out('INFO', 'nanite', 'NaniteEnabled tag = %s (enable with bw_02_nanite.py if needed)' % tags.get('NaniteEnabled'))
    except Exception as ex:
        R.out('FAIL', 'triangles', 'asset tags failed: %s' % ex)

    # ---- import options as stored on the mesh, normals
    try:
        bs = SMES.get_lod_build_settings(skm, 0)
        rn = bool(bs.get_editor_property('recompute_normals'))
        R.check(not rn, 'normals', 'LOD0 build settings recompute_normals=%s (False = FBX normals kept)' % rn)
    except Exception as ex:
        R.out('WARN', 'normals', 'get_lod_build_settings failed: %s' % ex)
    try:
        aid = skm.get_editor_property('asset_import_data')
        cn = aid.get_class().get_name() if aid else 'None'
        if aid is not None and cn == 'FbxSkeletalMeshImportData':
            vals = dict((k, aid.get_editor_property(k)) for k in (
                'force_front_x_axis', 'convert_scene', 'convert_scene_unit', 'import_uniform_scale',
                'normal_import_method'))
            R.data['import_data'] = dict((k, str(v)) for k, v in vals.items())
            okv = (not vals['force_front_x_axis'] and vals['convert_scene'] and not vals['convert_scene_unit']
                   and abs(float(vals['import_uniform_scale']) - 1.0) < 1e-6
                   and vals['normal_import_method'] == _enum('FBXNormalImportMethod', 'FBXNIM_IMPORT_NORMALS'))
            R.check(okv, 'import_options', 'stored FBX import options: %s' % R.data['import_data'])
        else:
            R.out('INFO', 'import_options', 'asset import data is %s (Interchange or unknown); stored options not '
                  'checked' % cn)
    except Exception as ex:
        R.out('WARN', 'import_options', 'reading asset_import_data failed: %s' % ex)

    # ---- physics asset, animations, folder content
    try:
        pa = _pkg(skm.physics_asset)
    except Exception:
        pa = _pkg(skm.get_editor_property('physics_asset'))
    R.check(pa in (None, PA_FINAL), 'physics_asset', 'mesh physics asset = %s (want none until step 3 makes %s)' % (
        pa, PA_FINAL))
    fa = _folder_assets()
    kinds = collections.defaultdict(list)
    for p, ad in fa.items():
        kinds[_class_name(ad)].append(p)
    R.data['folder'] = dict((k, sorted(v)) for k, v in kinds.items())
    R.out('INFO', 'folder', 'assets in %s: %s' % (FOLDER, R.data['folder']))
    anims = kinds.get('AnimSequence', [])
    R.check(not anims, 'animations', 'no AnimSequence in our folder' if not anims else 'AnimSequence(s) present: %s'
            % anims, warn_only=True)
    pas = [p for p in kinds.get('PhysicsAsset', []) if p != PA_FINAL]
    R.check(not pas, 'physics_asset_folder', 'no auto physics asset in our folder' if not pas else
            'physics asset(s) other than PA_Burrower: %s' % pas, warn_only=True)
    redirs = kinds.get('ObjectRedirector', [])
    R.check(not redirs, 'redirectors', 'no redirectors left in our folder' if not redirs else 'redirectors: %s' % redirs,
            warn_only=True)

    # ---- skinning
    if SKIN_CHECK:
        _skin_check(R, skm, slot_names, names)
    R.out('INFO', 'skin_manual', 'manual check: open SK_Burrower > Skeleton Tree, select J4_Tail and rotate it '
          '(tail plates follow), Rotor (rotate about X: only the cutter disc turns), pipe_upperhose_l_04 and '
          'pipe_side_l_a_04 (the hose bends), then Ctrl+Z / close without saving.')


def _skin_check(R, skm, slot_names, skel_names):
    """GeometryScript (GeometryScripting plugin, enabled through SkeletalMeshModelingTools EnabledByDefault):
    CopyMeshFromSkeletalMesh (MeshAssetFunctions.h:410) copies the LOD0 MeshDescription incl. skin weights; material
    IDs are its polygon groups (MeshDescriptionToDynamicMesh.cpp:887) = slot indices for this import (checked
    against the FBX vertex counts below)."""
    t0 = time.time()
    try:
        GA = unreal.GeometryScript_AssetUtils
        GB = unreal.GeometryScript_BoneWeights
        GS = unreal.GeometryScript_MeshSelection
        GM = unreal.GeometryScript_Materials
        GQ = unreal.GeometryScript_MeshQueries
    except Exception as e:
        R.out('INFO', 'skinning', 'GeometryScript not available (%s): use the manual check below' % e)
        return
    dm = unreal.DynamicMesh()
    try:
        opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        opts.set_editor_property('request_tangents', False)
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property('lod_type', _enum('GeometryScriptLODType', 'SOURCE_MODEL'))
        lod.set_editor_property('lod_index', 0)
        res = GA.copy_mesh_from_skeletal_mesh(skm, dm, opts, lod)   # -> (DynamicMesh, Outcome)
        outcome = res[1] if isinstance(res, tuple) else None
        if outcome != _enum('GeometryScriptOutcomePins', 'SUCCESS'):
            R.out('FAIL', 'skinning', 'copy_mesh_from_skeletal_mesh outcome %s; use the manual check' % outcome)
            return
        ntri = dm.get_triangle_count()
        nvert = GQ.get_vertex_count(dm)
        R.data['skin_mesh'] = {'triangles': ntri, 'vertices': nvert}
        R.out('INFO', 'skinning', 'source mesh copied: %d triangles, %d vertices (FBX %d / %d)' % (
            ntri, nvert, EXPECTED_TRIS, EXPECTED_FBX_VERTS))
        has = GB.mesh_has_bone_weights(dm)           # -> (DynamicMesh, bool)
        has = has[1] if isinstance(has, tuple) else bool(has)
        if not R.check(bool(has), 'skinning', 'source mesh has bone weights (default profile)'):
            return
        idx2name = {}
        try:
            # UNVERIFIED: whether the legacy-imported MeshDescription carries bone attributes; if not, the list is
            # empty and the skeleton order is used (identical for a skeleton created from this mesh).
            r = GB.get_all_bones_info(dm)            # -> (DynamicMesh, [GeometryScriptBoneInfo])
            infos = r[1] if isinstance(r, tuple) else r
            for bi in infos or []:
                idx2name[int(bi.get_editor_property('index'))] = str(bi.get_editor_property('name'))
        except Exception as e:
            R.out('INFO', 'skinning', 'get_all_bones_info failed (%s); bone indices mapped by skeleton order' % e)
        if not idx2name:
            idx2name = dict(enumerate(skel_names))
            R.out('INFO', 'skinning', 'bone index -> name taken from the skeleton order (same order as the mesh for '
                  'a skeleton created from this mesh)')
        r = GM.get_max_material_id(dm)               # -> (int, bool)
        max_id = r[0] if isinstance(r, tuple) else int(r)
        vsel = _enum('GeometryScriptMeshSelectionType', 'VERTICES')
        per_slot = collections.OrderedDict()
        pipe_found_total = set()
        body_found = set()
        n_fail = 0
        n_map_ok = 0
        for mid in range(max_id + 1):
            slot = slot_names[mid] if mid < len(slot_names) else 'id%d' % mid
            exp = EXPECTED_SLOTS.get(slot)
            if exp is None:
                for k, v in EXPECTED_SLOTS.items():
                    if _norm_slot(k) == _norm_slot(slot):
                        exp = v
                        break
            r = GS.select_mesh_elements_by_material_id(dm, mid, vsel)        # -> (DynamicMesh, Selection)
            sel = r[1] if isinstance(r, tuple) else r
            r2 = GS.convert_mesh_selection_to_index_array(dm, sel)          # -> (DynamicMesh, [int], type)
            verts = list(r2[1]) if isinstance(r2, tuple) else []
            if not verts:
                continue
            if exp is not None and abs(len(verts) - exp[1]) <= 0.15 * exp[1]:
                n_map_ok += 1
            full = exp is not None and exp[3] > 0
            step = 1 if full else max(1, len(verts) // max(1, SKIN_SAMPLES_PER_SLOT))
            hist = collections.Counter()
            unweighted = 0
            for v in verts[::step]:
                rr = GB.get_largest_vertex_bone_weight(dm, v)          # -> (DynamicMesh, BoneWeight, bool)
                bw, okw = rr[1], rr[2]
                if not okw or bw.get_editor_property('weight') <= 0.0:
                    unweighted += 1
                    continue
                hist[idx2name.get(int(bw.get_editor_property('bone_index')), '#%d' % bw.get_editor_property('bone_index'))] += 1
            top = hist.most_common(1)[0][0] if hist else None
            pipes = sorted(b for b in hist if b.startswith('pipe_'))
            pipe_found_total.update(pipes)
            body_found.update(b for b in hist if not b.startswith('pipe_'))
            status = 'PASS'
            why = []
            if unweighted:
                status = 'FAIL'
                why.append('%d sampled vertices without weights' % unweighted)
            if 'root' in hist:
                status = 'FAIL'
                why.append('%d sampled vertices bound to root (= not skinned)' % hist['root'])
            if exp is not None:
                if top not in exp[2] and not (top or '').startswith('pipe_'):
                    status = 'FAIL' if status == 'FAIL' else 'WARN'
                    why.append('dominant bone %s, FBX says %s' % (top, exp[2]))
                if exp[3] and len(pipes) != exp[3]:
                    status = 'FAIL'
                    why.append('%d pipe bones drive this part, FBX has %d' % (len(pipes), exp[3]))
            if status == 'FAIL':
                n_fail += 1
            per_slot[slot] = {'material_id': mid, 'part': exp[0] if exp else None, 'vertices': len(verts),
                              'fbx_vertices': exp[1] if exp else None, 'sampled': sum(hist.values()) + unweighted,
                              'dominant': hist.most_common(4), 'pipe_bones': len(pipes), 'status': status,
                              'why': why}
            R.out(status if status != 'PASS' else 'INFO', 'skinning_slot', '%-12s id %2d %-28s %6d verts (FBX %s), '
                  'sampled %d, dominant %s, pipe bones %d%s' % (
                      slot, mid, exp[0] if exp else '?', len(verts), exp[1] if exp else '?',
                      per_slot[slot]['sampled'], hist.most_common(3), len(pipes),
                      '' if not why else ' -> ' + '; '.join(why)))
        R.data['skin_per_slot'] = per_slot
        R.out('INFO', 'skinning', 'material id -> slot mapping matches the FBX part sizes for %d/%d ids (by index)' % (
            n_map_ok, max_id + 1))
        n_slots = len(per_slot)
        R.check(n_slots == 45 and n_fail == 0, 'skinning', '%d/%d parts (material ids) bound to the expected bones, no '
                'root-only or unweighted vertices in the samples' % (n_slots - n_fail, n_slots))
        exp_pipes = sorted(b for b in EXPECTED_POS if b.startswith('pipe_') and not b.endswith('_end'))
        missing = sorted(set(exp_pipes) - pipe_found_total)
        R.check(not missing, 'skinning_pipes', '%d/%d pipe bones (all but _end) drive vertices%s' % (
            len(pipe_found_total), len(exp_pipes), '' if not missing else '; none for %s' % missing))
        body = ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail', 'Rotor']
        R.check(all(b in body_found for b in body), 'skinning_body', 'body bones driving vertices: %s' % sorted(
            body_found))
    except Exception as e:
        R.out('FAIL', 'skinning', 'GeometryScript skin check raised %s; use the manual check. %s' % (
            e, traceback.format_exc().splitlines()[-3:]))
    finally:
        try:
            dm.reset()
        except Exception:
            pass
        R.out('INFO', 'skinning', 'skin check took %.1f s' % (time.time() - t0))


# ------------------------------------------------------------------------------------------------ main
def _bw02_main():
    R = _Results()
    R.data['started'] = time.strftime('%Y-%m-%d %H:%M:%S')
    R.data['route'] = 'interchange' if USE_INTERCHANGE else 'legacy_fbxfactory'
    R.data['flags'] = {'USE_INTERCHANGE': USE_INTERCHANGE, 'EXISTING': EXISTING, 'MATERIAL_MODE': MATERIAL_MODE,
                       'SKIN_CHECK': SKIN_CHECK}
    report_written = [False]

    def _write_report():
        try:
            os.makedirs(os.path.dirname(REPORT), exist_ok=True)
            R.data['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(REPORT, 'w') as f:
                json.dump({'summary': R.counts, 'data': R.data, 'actions': R.actions, 'checks': R.checks}, f,
                          indent=1, default=str)
            report_written[0] = True
            print('INFO: [report] wrote ' + REPORT)
        except Exception as e:
            print('WARN: [report] could not write %s: %s' % (REPORT, e))

    try:
        # ---- preflight
        try:
            proj = os.path.normpath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
        except Exception:
            proj = os.path.normpath(os.path.abspath(unreal.Paths.project_dir()))
        if proj != os.path.normpath(CLONE):
            R.out('FAIL', 'preflight', 'this editor runs project %s, not the clone %s. Stopped (nothing done).' % (
                proj, CLONE))
            return
        try:
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if les is not None and les.is_in_play_in_editor():
                R.out('FAIL', 'preflight', 'PIE is running; stop it first (saving refuses during PIE). Nothing done.')
                return
        except Exception as e:
            R.out('WARN', 'preflight', 'PIE check failed: %s' % e)
        if not os.path.isfile(FBX):
            R.out('FAIL', 'preflight', 'FBX not found: %s (git lfs pull?)' % FBX)
            return
        sz = os.path.getsize(FBX)
        R.data['fbx_bytes'] = sz
        if not R.check(sz > 10 * 1024 * 1024, 'preflight', 'FBX %s, %.1f MB%s' % (
                FBX, sz / 1048576.0, '' if sz > 10 * 1024 * 1024 else ' - too small, probably an LFS pointer: run '
                'git lfs pull in the clone. Stopped.')):
            return
        rig = json.load(open(RIG_INFO))
        R.check(len(rig.get('bone_order', [])) == 71, 'preflight', 'rig_info bone_order has %d bones' % len(
            rig.get('bone_order', [])))
        free = _free_gb()
        R.data['mem_available_gb'] = round(free, 1)
        try:
            R.out('INFO', 'preflight', 'Interchange.FeatureFlags.Import.Enable=%s Import.FBX=%s; route = %s' % (
                unreal.SystemLibrary.get_console_variable_bool_value('Interchange.FeatureFlags.Import.Enable'),
                unreal.SystemLibrary.get_console_variable_bool_value('Interchange.FeatureFlags.Import.FBX'),
                R.data['route']))
        except Exception:
            pass
        try:
            dirty0 = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
        except Exception:
            dirty0 = []
        R.data['dirty_before'] = dirty0

        # ---- existing state
        sk_exists, skel_exists = _exists(SK), _exists(SKEL)
        R.out('INFO', 'state', 'before: SK_Burrower=%s SKEL_Burrower=%s SK_Burrower_Skeleton=%s '
              'SK_Burrower_PhysicsAsset=%s M_Burrower_Grey=%s; EXISTING=%s' % (
                  sk_exists, skel_exists, _exists(AUTO_SKEL), _exists(AUTO_PA), _exists(GREY), EXISTING))
        do_import = True
        skeleton_for_import = None
        if sk_exists:
            if EXISTING == 'reuse':
                do_import = False
                R.action('SK_Burrower exists: reused, no import (EXISTING=reuse)')
            elif EXISTING == 'reimport':
                # UNVERIFIED: legacy routes an existing SkeletalMesh to UReimportFbxSkeletalMeshFactory
                # (FbxFactory.cpp:236), which uses the options stored on the mesh, not the ones built here.
                if skel_exists:
                    skeleton_for_import = unreal.EditorAssetLibrary.load_asset(SKEL)
                R.action('SK_Burrower exists: importing over it in place (EXISTING=reimport). If a "FAILED TO MERGE '
                         'BONES" dialog appears, answer No/Cancel and rerun with EXISTING=recreate.')
            elif EXISTING == 'recreate':
                ours = [SK, SKEL, AUTO_SKEL, AUTO_PA]
                blockers = {}
                for a in ours:
                    if _exists(a):
                        refs = [r for r in _referencers(a) if r not in ours]
                        if refs:
                            blockers[a] = refs
                if blockers:
                    R.out('FAIL', 'recreate', 'refused: other assets reference them %s. Use EXISTING=reimport (keeps '
                          'the references), or delete those assets first.' % blockers)
                    return
                for a in ours:
                    if not _delete_ours(R, a):
                        R.out('FAIL', 'recreate', 'could not delete %s; stopped' % a)
                        return
                skel_exists = False
            else:
                R.out('FAIL', 'flags', 'EXISTING must be reuse, reimport or recreate (got %r)' % EXISTING)
                return
        elif skel_exists:
            refs = [r for r in _referencers(SKEL) if r != SKEL]
            if refs:
                skeleton_for_import = unreal.EditorAssetLibrary.load_asset(SKEL)
                R.out('WARN', 'state', 'SK_Burrower missing but SKEL_Burrower exists and is used by %s: importing onto '
                      'that skeleton (a bone-merge dialog may appear if the bones differ)' % refs)
            else:
                _delete_ours(R, SKEL)
                skel_exists = False

        # ---- import
        if do_import:
            if 0 <= free < MIN_FREE_GB:
                R.out('FAIL', 'preflight', 'only %.1f GB memory available (< %.1f): close other programs or restart '
                      'the editor, then rerun. Nothing imported.' % (free, MIN_FREE_GB))
                return
            if 0 <= free < 4.0:
                R.out('WARN', 'preflight', 'only %.1f GB memory available; the import may be slow' % free)
            before = _folder_assets()
            try:
                if USE_INTERCHANGE:
                    paths = _import_interchange(R, skeleton_for_import)
                else:
                    paths = _import_legacy(R, skeleton_for_import)
            except Exception as e:
                R.out('FAIL', 'import', 'import raised %s\n%s' % (e, traceback.format_exc()))
                return
            if paths is None:
                return
            if not _exists(SK):
                R.out('FAIL', 'import', 'SK_Burrower was not created (imported: %s). Check the Output Log '
                      '(LogFbx / LogInterchange).' % paths)
                return
            skm = unreal.EditorAssetLibrary.load_asset(SK)
            _cleanup_new_assets(R, before, skm)
            imported = True
        else:
            skm = unreal.EditorAssetLibrary.load_asset(SK)
            imported = False
        if not isinstance(skm, unreal.SkeletalMesh):
            R.out('FAIL', 'import', '%s is not a SkeletalMesh (%s)' % (SK, skm))
            return

        # ---- fix-ups (only inside our folder), then save explicitly
        to_save = []
        try:
            skel_before = _pkg(skm.skeleton)
        except Exception:
            skel_before = None
        skel = _ensure_skeleton_name(R, skm)
        if imported or _pkg(skel) != skel_before:
            to_save += [SK, SKEL]
        if MATERIAL_MODE == 'grey':
            grey, created = _ensure_grey_material(R)
            if grey is not None:
                if created:
                    to_save.append(GREY)
                if _fill_empty_slots(R, skm, grey):
                    if SK not in to_save:
                        to_save.append(SK)
        for p in to_save:
            if _exists(p):
                _save_ours(R, p)
        _fix_redirectors(R)
        try:
            dirty1 = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
            new_dirty = [p for p in dirty1 if p not in dirty0]
            ours_dirty = [p for p in new_dirty if _ours(p)]
            other_dirty = [p for p in new_dirty if not _ours(p)]
            R.data['dirty_after_ours'] = ours_dirty
            R.data['dirty_after_other'] = other_dirty
            if ours_dirty:
                R.out('WARN', 'dirty', 'still dirty in our folder (not saved): %s' % ours_dirty)
            if other_dirty:
                R.out('WARN', 'dirty', 'packages outside our folder became dirty and were NOT saved (do not save them; '
                      'close the editor without saving or revert): %s' % other_dirty)
        except Exception:
            pass

        # ---- checks
        _check_all(R, skm, rig)
    except Exception as e:
        R.out('FAIL', 'script', 'unexpected exception %s\n%s' % (e, traceback.format_exc()))
    finally:
        _write_report()
        print('RESULT: bw_02_import %d PASS, %d FAIL, %d WARN (route %s, EXISTING=%s)' % (
            R.counts['PASS'], R.counts['FAIL'], R.counts['WARN'], R.data.get('route'), EXISTING))


_bw02_main()
