# bw_06_blueprint.py -- Burrower editor session, EDITOR_SESSION.md step 6 and cpp_notes.md
# "What the editor session must create or set" items 3 and 4 (+ the GameMode / player checks from "Test").
#
# Run inside the running UE 5.8 editor of the clone, through the inbox harness:
#   D=/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts; $D/harness/inbox.sh 06bp $D/bw_06_blueprint.py 300
# Then grep the output for '^FAIL:' / '^WARN:'. A copy of every PASS/FAIL/WARN/INFO line is written to
# Saved/Burrower/bw_06_blueprint.json.
#
# What it does (all synchronous, no frames needed):
#   1. Creates /Game/Assets/Enemies/Burrower/BP_Burrower with parent /Script/Aura.BurrowerCharacter, or REUSES it if it
#      exists (re-parents it to BurrowerCharacter if the parent differs; never deletes it). Every value below is
#      re-applied on each run, so the script is idempotent.
#   2. Edits the INHERITED NATIVE component templates (Mesh, HealthBar widget) and the class defaults:
#      Mesh: Skeletal Mesh = SK_Burrower, Animation Mode = Use Animation Blueprint, Anim Class = ABP_Burrower_C (only if
#      ABP_Burrower exists, else WARN and leave it for a re-run), relative transform = the C++ one (-830,0,-187), rot 0.
#      HealthBar: Widget Class = WBP_HealthBar_C, Draw Size = the one BP_GoblinSpear's HealthBar uses (100 x 20,
#      read from its .uasset), Space stays Screen (C++). StartupAbilities = []. DissolveMaterialInstance = None.
#      bUseMeshRagdollFallback = RAGDOLL_FALLBACK. Collision presets are NOT touched (compared with the C++ CDO only).
#      No graph nodes are added (no InitializeEnemyAttributes call).
#   3. Compiles, saves ONLY BP_Burrower, then verifies: after compile (new CDO), on disk (parses the saved .uasset), and
#      after a package reload (RELOAD_AFTER_SAVE).
#   4. Read-only checks: DA_CharClassInfo has an entry for the Burrower's CharacterClass with an XPReward curve table +
#      row; the GameMode of /Game/Maps/StartupMap and its DA_MyEnemyCharacterClassInfo; DebugDieAfterBeginPlaySeconds
#      of BP_MyCharMech (and of the GameMode's default pawn). Nothing outside /Game/Assets/Enemies/Burrower/ is modified.
#
# How inherited native components are edited (checked in the 5.8 source):
#   * USubobjectDataSubsystem::K2_GatherSubobjectDataForBlueprint gathers from Blueprint->GeneratedClass->GetDefaultObject()
#     (SubobjectDataSubsystem.cpp:147-153); native components are the CDO's own components (:316-347).
#   * FSubobjectData::GetObjectForBlueprint only creates an InheritableComponentHandler override template for
#     NON-native inherited SCS nodes; for a native component it returns the object itself (SubobjectData.cpp:256-289), and
#     USubobjectDataBlueprintFunctionLibrary::GetAssociatedObject resolves it in the CDO (SubobjectDataBlueprintFunctionLibrary.cpp:24-46).
#     So the archetype the Blueprint editor's Details panel edits is the generated class CDO's default subobject.
#   * Compiling re-creates the CDO and copies the old CDO and its default subobjects into it
#     (BlueprintCompilationManager.cpp:2955-2972: PreCreateSubObjectsForReinstantiation + CopyPropertiesForUnrelatedObjects),
#     and saving writes them in the BP package as subobjects of Default__BP_Burrower_C (delta against the C++ archetype).
#   => edit unreal.get_default_object(generated class).get_editor_property('Mesh') etc., compile, save. The script also
#      cross-checks that the SubobjectDataSubsystem hands out the very same objects.
#
# Property names: C++ names are passed to get/set_editor_property ('SkeletalMeshAsset', 'bUseMeshRagdollFallback', ...).
# FPyWrapperObjectMetaData::ResolvePropertyName returns the given name unchanged when it is not a mapped Python name
# (PyWrapperObject.cpp:1223-1240) and FindEditorPropertyImpl then looks it up with Class->FindPropertyByName
# (PyWrapperObject.cpp:749-797). That also works for classes Python does not export (DA_MyEnemyCharacterClassInfo,
# BurrowerSettings), where snake_case names fail (Saved/ClaudeInbox/bw_probe1.out: "Failed to find property 'enabled'").

import unreal
import os
import json
import struct
import traceback

# ---------------------------------------------------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------------------------------------------------
RAGDOLL_FALLBACK = True     # bUseMeshRagdollFallback. Set False (and re-run) once CR_Burrower's ragdoll is verified.
RELOAD_AFTER_SAVE = True    # Reload the BP_Burrower package after saving and verify again (Asset > Reload path).
DO_BLUEPRINT = True         # Create/update/save BP_Burrower.
DO_CHECKS = True            # Read-only checks (DA_CharClassInfo, GameMode, BP_MyCharMech).

# ---------------------------------------------------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------------------------------------------------
BW06_FOLDER = '/Game/Assets/Enemies/Burrower'
BW06_BP_PATH = BW06_FOLDER + '/BP_Burrower'
BW06_SK_PATH = BW06_FOLDER + '/SK_Burrower'
BW06_ABP_PATH = BW06_FOLDER + '/ABP_Burrower'
BW06_PARENT_CLASS = '/Script/Aura.BurrowerCharacter'
BW06_ANIM_PARENT_CLASS = '/Script/Aura.BurrowerAnimInstance'
BW06_WBP_CLASS = '/Game/Level/UI/UserWidgets/Enemy/WBP_HealthBar.WBP_HealthBar_C'   # Content/Level/UI/UserWidgets/Enemy/WBP_HealthBar.uasset, parent /Script/Aura.MyUserWidget
BW06_MYUSERWIDGET_CLASS = '/Script/Aura.MyUserWidget'
BW06_REF_ENEMY_FILE = 'Content/Level/Goblin_Spear/BP_GoblinSpear.uasset'          # the only enemy BP with a HealthBar set up
BW06_REF_ENEMY_CLASS = '/Game/Level/Goblin_Spear/BP_GoblinSpear.BP_GoblinSpear_C'
BW06_DRAW_SIZE_FALLBACK = (100, 20)   # BP_GoblinSpear HealthBar DrawSize, read offline on 2026-11-21
BW06_DA_PATH = '/Game/Level/GAS/Data/DA_CharClassInfo'
BW06_MAP_PACKAGE = '/Game/Maps/StartupMap'
BW06_MAP_FILE = 'Content/Maps/StartupMap.umap'
BW06_MYGAMEMODE_CLASS = '/Script/Aura.MyGameMode'
BW06_MYCHARPLAYER_CLASS = '/Script/Aura.MyCharPlayer'
BW06_MECH_CLASS = '/Game/Level/MechChar/BP_MyCharMech.BP_MyCharMech_C'
BW06_CHAR_CLASS_ENUM = ['Elemental', 'Warrior', 'Ranger']   # ECharacterClass order (DA_MyEnemyCharacterClassInfo.h)

BW06_PROJECT_DIR = os.path.abspath(unreal.Paths.project_dir())
BW06_RESULT_JSON = os.path.join(BW06_PROJECT_DIR, 'Saved', 'Burrower', 'bw_06_blueprint.json')

BW06_R = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0, 'lines': []}


# ---------------------------------------------------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------------------------------------------------
def bw06_out(tag, msg):
    line = '%s: %s' % (tag, msg)
    print(line)
    BW06_R[tag] = BW06_R.get(tag, 0) + 1
    BW06_R['lines'].append(line)


def bw06_check(cond, what, hint=''):
    if cond:
        bw06_out('PASS', what)
    else:
        bw06_out('FAIL', what + ((' -- ' + hint) if hint else ''))
    return bool(cond)


def bw06_path(v):
    """Readable path of an object/class (or 'None')."""
    if v is None:
        return 'None'
    try:
        return v.get_path_name()
    except Exception:
        return str(v)


def bw06_enum_name(v):
    n = getattr(v, 'name', None)
    if n is None:
        return str(v)
    return str(n)


def bw06_norm(s):
    return str(s).replace('_', '').replace(' ', '').lower()


def bw06_gp(obj, name):
    """get_editor_property by C++ name, then by the snake_case name. Returns (ok, value_or_error)."""
    if obj is None:
        return False, 'object is None'
    names = [name]
    sn = ''.join(['_' + c.lower() if c.isupper() else c for c in name]).lstrip('_')
    if name.startswith('b') and len(name) > 1 and name[1].isupper():
        sn = ''.join(['_' + c.lower() if c.isupper() else c for c in name[1:]]).lstrip('_')
    if sn not in names:
        names.append(sn)
    err = None
    for n in names:
        try:
            return True, obj.get_editor_property(n)
        except Exception as e:
            err = e
    return False, err


def bw06_sp(obj, name, value, label):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:
        bw06_out('FAIL', '%s: set_editor_property(%r) failed: %s' % (label, name, e))
        return False


def bw06_near(a, b, tol=0.01):
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


def bw06_vec(v):
    try:
        return (float(v.x), float(v.y), float(v.z))
    except Exception:
        return None


def bw06_rot(v):
    try:
        return (float(v.roll), float(v.pitch), float(v.yaw))
    except Exception:
        return None


def bw06_same3(a, b, tol=0.01):
    return a is not None and b is not None and all(bw06_near(x, y, tol) for x, y in zip(a, b))


def bw06_is_child(cls, parent):
    if cls is None or parent is None:
        return False
    try:
        return bool(unreal.MathLibrary.class_is_child_of(cls, parent))
    except Exception:
        return cls == parent


def bw06_load_class(path):
    try:
        return unreal.load_class(None, path)
    except Exception:
        return None


def bw06_gen_class(bp):
    try:
        c = unreal.BlueprintEditorLibrary.generated_class(bp)
        if c:
            return c
    except Exception:
        pass
    try:
        return unreal.load_class(None, bp.get_path_name() + '_C')
    except Exception:
        return None


def bw06_pie_running():
    try:
        return bool(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor())
    except Exception as e:
        bw06_out('WARN', 'could not ask LevelEditorSubsystem.is_in_play_in_editor (%s); make sure PIE is not running' % e)
        return False


def bw06_dirty_packages():
    names = set()
    try:
        for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages():
            names.add(p.get_name())
        for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages():
            names.add(p.get_name())
    except Exception as e:
        bw06_out('WARN', 'could not list dirty packages: %s' % e)
    return names


# ---------------------------------------------------------------------------------------------------------------------
# Minimal offline .uasset/.umap reader (pure Python file read, nothing is loaded or written). UE 5.8 package layout,
# FileVersionUE5 >= 1016 (PACKAGE_SAVED_HASH), tagged properties with complete type names (>= 1012).
# ---------------------------------------------------------------------------------------------------------------------
class _BW06Rd(object):
    def __init__(self, b, o=0):
        self.b = b
        self.o = o

    def i32(self):
        v = struct.unpack_from('<i', self.b, self.o)[0]; self.o += 4; return v

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.o)[0]; self.o += 4; return v

    def i64(self):
        v = struct.unpack_from('<q', self.b, self.o)[0]; self.o += 8; return v

    def u8(self):
        v = self.b[self.o]; self.o += 1; return v

    def raw(self, n):
        v = self.b[self.o:self.o + n]; self.o += n; return v

    def fstr(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            return self.raw(-n * 2).decode('utf-16-le', 'replace')[:-1]
        return self.raw(n).decode('latin-1')[:-1]


def bw06_pkg_read(path):
    b = open(path, 'rb').read()
    r = _BW06Rd(b)
    if r.u32() != 0x9E2A83C1:
        raise RuntimeError('not a UE package: %s' % path)
    r.i32(); r.i32(); r.i32()
    ue5 = r.i32(); r.i32()
    if ue5 < 1016:
        raise RuntimeError('FileVersionUE5 %d < 1016 not supported by this reader' % ue5)
    r.raw(20); r.i32()                      # SavedHash, TotalHeaderSize
    n = r.i32(); r.raw(20 * n)              # custom versions
    r.fstr(); flags = r.u32()               # PackageName, PackageFlags
    name_count = r.i32(); name_off = r.i32()
    r.i32(); r.i32()                        # soft object paths
    if not (flags & 0x80000000):            # PKG_FilterEditorOnly not set: LocalizationId
        r.fstr()
    r.i32(); r.i32()                        # gatherable text
    exp_count = r.i32(); exp_off = r.i32(); imp_count = r.i32(); imp_off = r.i32()
    names = []
    rr = _BW06Rd(b, name_off)
    for _ in range(name_count):
        names.append(rr.fstr()); rr.u32()
    imps = []
    rr = _BW06Rd(b, imp_off)
    for _ in range(imp_count):
        rr.raw(8); cn = rr.i32(); rr.i32(); outer = rr.i32(); on = rr.i32(); rr.i32(); rr.raw(8); rr.u32()
        imps.append((names[cn], names[on], outer))
    exps = []
    rr = _BW06Rd(b, exp_off)
    for _ in range(exp_count):
        cls = rr.i32(); rr.i32(); rr.i32(); outer = rr.i32(); nm = rr.i32(); num = rr.i32(); rr.u32()
        rr.i64(); sof = rr.i64(); rr.raw(12); rr.u32(); rr.u32(); rr.raw(12); rr.raw(20); s0 = rr.i64(); s1 = rr.i64()
        exps.append({'cls': cls, 'outer': outer, 'name': names[nm] + ('_%d' % (num - 1) if num else ''),
                     'so': sof, 's0': s0, 's1': s1})
    return {'b': b, 'names': names, 'imps': imps, 'exps': exps}


def bw06_pkg_ref(pkg, idx):
    """FPackageIndex -> readable path (imports: full path, exports: name)."""
    if idx == 0:
        return None
    if idx > 0:
        return pkg['exps'][idx - 1]['name']
    parts = []
    i = idx
    while i < 0:
        _c, n, o = pkg['imps'][-i - 1]
        parts.append(n)
        i = o
    return '.'.join(reversed(parts))


def bw06_pkg_class_name(pkg, e):
    i = e['cls']
    if i < 0:
        return pkg['imps'][-i - 1][1]
    if i > 0:
        return pkg['exps'][i - 1]['name']
    return 'None'


def _bw06_fname(r, names):
    i = r.i32(); n = r.i32()
    return names[i] + ('_%d' % (n - 1) if n else '')


def _bw06_tname(r, names):
    nm = _bw06_fname(r, names); k = r.i32()
    inner = [_bw06_tname(r, names) for _ in range(k)]
    return nm + ('(' + ','.join(inner) + ')' if inner else '')


def _bw06_value(pkg, tn, flags, b, start, size):
    names = pkg['names']
    if tn.startswith('BoolProperty'):
        return bool(flags & 0x10)
    if tn.startswith('StructProperty'):
        if not (flags & 0x08):
            return _bw06_tagged(pkg, _BW06Rd(b, start), start + size)
        if 'IntPoint' in tn and size == 8:
            return struct.unpack_from('<ii', b, start)
        if ('(Vector(' in tn or '(Rotator(' in tn) and size == 24:
            return struct.unpack_from('<ddd', b, start)
        return b[start:start + size].hex()
    if tn.startswith('EnumProperty') or tn.startswith('NameProperty') or (tn.startswith('ByteProperty') and size == 8):
        return _bw06_fname(_BW06Rd(b, start), names)
    if tn.startswith('ObjectProperty') or tn.startswith('ClassProperty'):
        return bw06_pkg_ref(pkg, struct.unpack_from('<i', b, start)[0])
    if tn.startswith('FloatProperty'):
        return struct.unpack_from('<f', b, start)[0]
    if tn.startswith('DoubleProperty'):
        return struct.unpack_from('<d', b, start)[0]
    if tn.startswith('IntProperty'):
        return struct.unpack_from('<i', b, start)[0]
    if tn.startswith('StrProperty'):
        return _BW06Rd(b, start).fstr()
    if tn.startswith('ArrayProperty('):
        inner = tn[len('ArrayProperty('):]
        rr = _BW06Rd(b, start)
        count = rr.i32()
        if inner.startswith('StructProperty'):
            out = []
            for _ in range(count):
                out.append(_bw06_tagged(pkg, rr, start + size))
            return out
        if inner.startswith('ObjectProperty') or inner.startswith('ClassProperty'):
            return [bw06_pkg_ref(pkg, rr.i32()) for _ in range(count)]
        return {'count': count, 'hex': b[start + 4:start + size].hex()[:64]}
    return b[start:start + size].hex()[:64]


def _bw06_tagged(pkg, r, end):
    names = pkg['names']
    out = {}
    while r.o < end:
        nm = _bw06_fname(r, names)
        if nm == 'None':
            break
        tn = _bw06_tname(r, names); size = r.i32(); fl = r.u8()
        if fl & 0x01:
            r.i32()
        if fl & 0x02:
            r.raw(16)
        if fl & 0x04:
            ext = r.u8()
            if ext & 0x02:
                r.u8()
        start = r.o
        try:
            out[nm] = _bw06_value(pkg, tn, fl, r.b, start, size)
        except Exception as e:
            out[nm] = 'ERR %s' % e
        r.o = start + size
    return out


def bw06_pkg_props(pkg, e):
    r = _BW06Rd(pkg['b'], e['so'] + e['s0'])
    end = e['so'] + e['s1']
    ext = r.u8()                            # EClassSerializationControlExtension
    if ext & 0x02:
        r.u8()
    return _bw06_tagged(pkg, r, end)


def bw06_pkg_find(pkg, name, outer_name=None, class_name=None):
    for e in pkg['exps']:
        if e['name'] != name:
            continue
        if outer_name is not None and bw06_pkg_ref(pkg, e['outer']) != outer_name:
            continue
        if class_name is not None and bw06_pkg_class_name(pkg, e) != class_name:
            continue
        return e
    return None


# ---------------------------------------------------------------------------------------------------------------------
# BP_Burrower
# ---------------------------------------------------------------------------------------------------------------------
def bw06_ref_draw_size():
    """DrawSize of the other enemies' health bar: BP_GoblinSpear's HealthBar (offline read, then editor read)."""
    try:
        pkg = bw06_pkg_read(os.path.join(BW06_PROJECT_DIR, BW06_REF_ENEMY_FILE))
        e = bw06_pkg_find(pkg, 'HealthBar', outer_name='Default__BP_GoblinSpear_C')
        if e:
            props = bw06_pkg_props(pkg, e)
            ds = props.get('DrawSize')
            if isinstance(ds, tuple) and len(ds) == 2:
                bw06_out('INFO', 'BP_GoblinSpear HealthBar on disk: DrawSize=%s WidgetClass=%s (Space not saved = World)'
                         % (ds, props.get('WidgetClass')))
                return (int(ds[0]), int(ds[1])), 'BP_GoblinSpear.uasset'
            bw06_out('INFO', 'BP_GoblinSpear HealthBar has no DrawSize override on disk (engine default)')
    except Exception as e:
        bw06_out('WARN', 'offline read of %s failed: %s' % (BW06_REF_ENEMY_FILE, e))
    try:
        cls = bw06_load_class(BW06_REF_ENEMY_CLASS)
        ok, hb = bw06_gp(unreal.get_default_object(cls), 'HealthBarWidgetComponent') if cls else (False, None)
        if ok and hb:
            ok2, ds = bw06_gp(hb, 'DrawSize')
            if ok2:
                return (int(ds.x), int(ds.y)), 'BP_GoblinSpear CDO'
    except Exception as e:
        bw06_out('WARN', 'editor read of BP_GoblinSpear HealthBar failed: %s' % e)
    return BW06_DRAW_SIZE_FALLBACK, 'fallback constant (BP_GoblinSpear value read on 2026-11-21)'


def bw06_find_or_create(parent_cls):
    """Returns (blueprint, created). Never deletes anything."""
    exists = False
    try:
        exists = unreal.EditorAssetLibrary.does_asset_exist(BW06_BP_PATH)
    except Exception as e:
        bw06_out('WARN', 'does_asset_exist failed: %s' % e)
    if exists:
        bp = unreal.EditorAssetLibrary.load_asset(BW06_BP_PATH)
        if not isinstance(bp, unreal.Blueprint):
            bw06_out('FAIL', '%s exists but is not a Blueprint (%s). Delete it by hand in the Content Browser and re-run.'
                     % (BW06_BP_PATH, bp.get_class().get_name() if bp else None))
            return None, False
        try:
            cur_parent = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
        except Exception:
            cur_parent = None
        if bw06_path(cur_parent) != bw06_path(parent_cls):
            bw06_out('WARN', 'existing BP_Burrower parent is %s: re-parenting to %s (our own asset)'
                     % (bw06_path(cur_parent), BW06_PARENT_CLASS))
            try:
                unreal.BlueprintEditorLibrary.reparent_blueprint(bp, parent_cls)
            except Exception as e:
                bw06_out('FAIL', 'reparent_blueprint failed: %s. Reparent BP_Burrower to BurrowerCharacter by hand '
                         '(Class Settings > Parent Class) and re-run.' % e)
                return None, False
        bw06_out('INFO', 'REUSING existing %s (not deleted; every value is re-applied)' % BW06_BP_PATH)
        return bp, False
    bp = None
    try:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(BW06_BP_PATH, parent_cls)
    except Exception as e:
        bw06_out('WARN', 'create_blueprint_asset_with_parent failed (%s), trying AssetTools + BlueprintFactory' % e)
    if not bp:
        # AssetTools.create_asset opens a MODAL "already exists" dialog when the package is still in memory (a deleted
        # asset before GC), which would block the editor tick: only use it when nothing of that name is loaded.
        try:
            stale = unreal.find_object(None, BW06_BP_PATH)
        except Exception:
            stale = None
        if stale is not None:
            bw06_out('FAIL', 'a package %s is still in memory but no asset exists (deleted earlier?): restart the editor and '
                     're-run' % BW06_BP_PATH)
            return None, False
        try:
            fac = unreal.BlueprintFactory()
            fac.set_editor_property('ParentClass', parent_cls)
            bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset('BP_Burrower', BW06_FOLDER, unreal.Blueprint, fac)
        except Exception as e:
            bw06_out('FAIL', 'AssetTools.create_asset failed: %s' % e)
            bp = None
    if not bp:
        bw06_out('FAIL', 'could not create %s (see the log: LogBlueprintEditorLib)' % BW06_BP_PATH)
        return None, False
    bw06_out('INFO', 'CREATED %s (parent %s)' % (BW06_BP_PATH, BW06_PARENT_CLASS))
    return bp, True


def bw06_sds_crosscheck(bp, cdo):
    """The SubobjectDataSubsystem (what the BP editor uses) must hand out the same component objects as the CDO."""
    try:
        sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        lib = unreal.SubobjectDataBlueprintFunctionLibrary
        found = {}
        for h in sds.k2_gather_subobject_data_for_blueprint(bp):
            d = lib.get_data(h)
            if not lib.is_component(d):
                continue
            found[str(lib.get_variable_name(d))] = (lib.get_associated_object(d), lib.is_native_component(d),
                                                    lib.is_inherited_component(d))
        for prop in ('CapsuleComponent', 'Mesh', 'HealthBarWidgetComponent', 'RotorBox'):
            ok, comp = bw06_gp(cdo, prop)
            ent = found.get(prop)
            if ent is None:
                bw06_out('WARN', 'SDS: no subobject with variable name %s (found: %s)' % (prop, sorted(found.keys())))
            elif ok and ent[0] == comp:
                bw06_out('INFO', 'SDS: %s -> %s native=%s inherited=%s, same object as the CDO component'
                         % (prop, bw06_path(comp), ent[1], ent[2]))
            else:
                bw06_out('WARN', 'SDS: %s object %s differs from the CDO component %s' % (prop, bw06_path(ent[0]), bw06_path(comp)))
    except Exception as e:
        bw06_out('WARN', 'SubobjectDataSubsystem cross-check failed (not needed for the edit): %s' % e)


def bw06_coll_sig(comp):
    sig = {}
    for fn in ('get_collision_profile_name', 'get_collision_enabled', 'get_collision_object_type'):
        try:
            sig[fn] = str(getattr(comp, fn)())
        except Exception as e:
            sig[fn] = 'ERR %s' % e
    ok, v = bw06_gp(comp, 'bGenerateOverlapEvents')
    sig['bGenerateOverlapEvents'] = str(v) if ok else 'ERR'
    try:
        sig['BodyInstance'] = comp.get_editor_property('BodyInstance').export_text()
    except Exception as e:
        sig['BodyInstance'] = 'ERR %s' % e
    return sig


def bw06_collision_compare(cdo, ncdo, stage):
    for prop in ('CapsuleComponent', 'Mesh', 'RotorBox'):
        ok, c = bw06_gp(cdo, prop)
        okn, n = bw06_gp(ncdo, prop)
        if not (ok and okn and c and n):
            bw06_out('WARN', '[%s] collision compare: %s not found' % (stage, prop))
            continue
        a = bw06_coll_sig(c)
        b = bw06_coll_sig(n)
        main_same = all(a[k] == b[k] for k in ('get_collision_profile_name', 'get_collision_enabled',
                                                'get_collision_object_type', 'bGenerateOverlapEvents'))
        if main_same and a['BodyInstance'] == b['BodyInstance']:
            bw06_out('PASS', '[%s] %s collision = inherited C++ settings (profile %s, %s, %s)'
                     % (stage, prop, a['get_collision_profile_name'], a['get_collision_enabled'], a['get_collision_object_type']))
        elif main_same:
            i = next((k for k in range(min(len(a['BodyInstance']), len(b['BodyInstance'])))
                      if a['BodyInstance'][k] != b['BodyInstance'][k]), 0)
            bw06_out('WARN', '[%s] %s BodyInstance text differs from the C++ CDO near: BP ...%s... / C++ ...%s... '
                     '(check Details > Collision for an override; reset it with the yellow arrow)'
                     % (stage, prop, a['BodyInstance'][max(0, i - 40):i + 60], b['BodyInstance'][max(0, i - 40):i + 60]))
        else:
            bw06_out('FAIL', '[%s] %s collision is overridden in BP_Burrower: BP %s vs C++ %s -- reset Collision Presets '
                     'to the inherited value in the BP Details (yellow reset arrow), save, re-run'
                     % (stage, prop, {k: a[k] for k in a if k != 'BodyInstance'}, {k: b[k] for k in b if k != 'BodyInstance'}))


def bw06_expected(parent_cls):
    """Everything the BP must end up with."""
    exp = {'parent': parent_cls, 'sk': None, 'abp_cls': None, 'wbp_cls': None, 'draw': None}
    # SK_Burrower
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(BW06_SK_PATH):
            exp['sk'] = unreal.EditorAssetLibrary.load_asset(BW06_SK_PATH)
    except Exception as e:
        bw06_out('WARN', 'loading %s failed: %s' % (BW06_SK_PATH, e))
    if exp['sk'] is None or not isinstance(exp['sk'], unreal.SkeletalMesh):
        bw06_out('FAIL', '%s not found (or not a SkeletalMesh): the mesh stays unset. Run the FBX import step, then re-run '
                 'this script.' % BW06_SK_PATH)
        exp['sk'] = None
    else:
        ok, skel = bw06_gp(exp['sk'], 'Skeleton')
        okp, pa = bw06_gp(exp['sk'], 'PhysicsAsset')
        bw06_out('INFO', 'SK_Burrower: skeleton %s, physics asset %s' % (bw06_path(skel) if ok else '?', bw06_path(pa) if okp else '?'))
        exp['skel'] = bw06_path(skel) if ok else None
        if okp and pa is None:
            bw06_out('WARN', 'SK_Burrower has no physics asset: hits (Visibility traces) and the fallback ragdoll need '
                     'PA_Burrower set on the mesh (physics asset step)')
    # ABP_Burrower
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(BW06_ABP_PATH):
            abp = unreal.EditorAssetLibrary.load_asset(BW06_ABP_PATH)
            cls = bw06_gen_class(abp) if abp else None
            anim_parent = bw06_load_class(BW06_ANIM_PARENT_CLASS)
            if cls is None:
                bw06_out('WARN', 'ABP_Burrower exists but has no generated class (compile it), Anim Class left as is')
            elif not bw06_is_child(cls, anim_parent):
                bw06_out('FAIL', 'ABP_Burrower_C is not a child of BurrowerAnimInstance (parent %s): Anim Class left as is'
                         % bw06_path(unreal.BlueprintEditorLibrary.get_blueprint_parent_class(abp)))
            else:
                exp['abp_cls'] = cls
                ok, tskel = bw06_gp(abp, 'TargetSkeleton')
                tsk = bw06_path(tskel) if ok else None
                if exp.get('skel') and tsk and tsk != exp['skel']:
                    bw06_out('FAIL', 'ABP_Burrower target skeleton %s != SK_Burrower skeleton %s' % (tsk, exp['skel']))
                else:
                    bw06_out('INFO', 'ABP_Burrower_C ok (parent BurrowerAnimInstance, target skeleton %s)' % tsk)
        else:
            bw06_out('WARN', '%s does not exist yet: Anim Class is left as is. Re-run this script after the AnimBP step.'
                     % BW06_ABP_PATH)
    except Exception as e:
        bw06_out('WARN', 'ABP_Burrower lookup failed (%s): Anim Class left as is' % e)
    # WBP_HealthBar
    exp['wbp_cls'] = bw06_load_class(BW06_WBP_CLASS)
    if exp['wbp_cls'] is None:
        bw06_out('FAIL', 'could not load %s: HealthBar Widget Class stays unset (BeginPlay then uses an empty UMyUserWidget)'
                 % BW06_WBP_CLASS)
    elif not bw06_is_child(exp['wbp_cls'], bw06_load_class(BW06_MYUSERWIDGET_CLASS)):
        bw06_out('WARN', 'WBP_HealthBar_C is not a UMyUserWidget child: AMyEnemyChar::BeginPlay would dereference null')
    exp['draw'], src = bw06_ref_draw_size()
    bw06_out('INFO', 'HealthBar Draw Size to use: %s (from %s)' % (exp['draw'], src))
    return exp


def bw06_apply(bp, exp):
    gen = bw06_gen_class(bp)
    if gen is None:
        bw06_out('FAIL', 'BP_Burrower has no generated class')
        return False
    cdo = unreal.get_default_object(gen)
    ncdo = unreal.get_default_object(exp['parent'])
    bw06_sds_crosscheck(bp, cdo)
    try:
        bp.modify()
    except Exception:
        pass

    # --- Mesh (inherited native SkeletalMeshComponent 'CharacterMesh0', property ACharacter::Mesh) ---
    ok, mesh = bw06_gp(cdo, 'Mesh')
    okn, nmesh = bw06_gp(ncdo, 'Mesh')
    if not (ok and mesh):
        bw06_out('FAIL', 'BP CDO has no Mesh component: %s' % mesh)
        return False
    mesh.modify()
    if exp['sk'] is not None:
        if not bw06_sp(mesh, 'SkeletalMeshAsset', exp['sk'], 'Mesh'):
            try:
                mesh.set_skeletal_mesh_asset(exp['sk'])     # UFUNCTION fallback (SkeletalMeshComponent.h:368-369)
                bw06_out('INFO', 'Mesh: set via set_skeletal_mesh_asset() fallback')
            except Exception as e:
                bw06_out('FAIL', 'Mesh: set_skeletal_mesh_asset failed too: %s' % e)
    am = getattr(unreal, 'AnimationMode', None)
    if am is not None:
        bw06_sp(mesh, 'AnimationMode', am.ANIMATION_BLUEPRINT, 'Mesh')
    else:
        bw06_out('WARN', 'unreal.AnimationMode not exported; AnimationMode left as is (the engine default is Use Animation Blueprint)')
    if exp['abp_cls'] is not None:
        bw06_sp(mesh, 'AnimClass', exp['abp_cls'], 'Mesh')
    # keep the C++ relative transform (-830, 0, -187), rotation 0, scale 1
    if okn and nmesh:
        for prop, conv in (('RelativeLocation', bw06_vec), ('RelativeRotation', bw06_rot), ('RelativeScale3D', bw06_vec)):
            okb, vb = bw06_gp(mesh, prop)
            okc, vc = bw06_gp(nmesh, prop)
            if okb and okc and not bw06_same3(conv(vb), conv(vc)):
                bw06_out('WARN', 'Mesh %s was %s in the BP, resetting to the C++ value %s' % (prop, conv(vb), conv(vc)))
                bw06_sp(mesh, prop, vc, 'Mesh')

    # --- HealthBar (inherited native UWidgetComponent 'HealthBar', property AMyEnemyChar::HealthBarWidgetComponent) ---
    ok, hb = bw06_gp(cdo, 'HealthBarWidgetComponent')
    if ok and hb:
        hb.modify()
        if exp['wbp_cls'] is not None:
            bw06_sp(hb, 'WidgetClass', exp['wbp_cls'], 'HealthBar')
        if exp['draw'] is not None:
            bw06_sp(hb, 'DrawSize', unreal.IntPoint(int(exp['draw'][0]), int(exp['draw'][1])), 'HealthBar')
    else:
        bw06_out('FAIL', 'BP CDO has no HealthBarWidgetComponent: %s' % hb)

    # --- Class defaults ---
    bw06_sp(cdo, 'StartupAbilities', [], 'CDO')
    okd, dmi = bw06_gp(cdo, 'DissolveMaterialInstance')
    if okd and dmi is not None:
        bw06_out('WARN', 'DissolveMaterialInstance was %s, clearing it (the base dissolves slot 0 only)' % bw06_path(dmi))
        bw06_sp(cdo, 'DissolveMaterialInstance', None, 'CDO')
    bw06_sp(cdo, 'bUseMeshRagdollFallback', bool(RAGDOLL_FALLBACK), 'CDO')
    return True


def bw06_read(stage, exp):
    """Re-loads BP_Burrower by path, prints PASS/FAIL for every value. Returns the Burrower CharacterClass name."""
    char_class = None
    bp = unreal.EditorAssetLibrary.load_asset(BW06_BP_PATH)
    if not isinstance(bp, unreal.Blueprint):
        bw06_out('FAIL', '[%s] %s could not be loaded' % (stage, BW06_BP_PATH))
        return None
    try:
        parent = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
    except Exception:
        parent = None
    bw06_check(bw06_path(parent) == bw06_path(exp['parent']), '[%s] parent class = %s' % (stage, bw06_path(parent)))
    gen = bw06_gen_class(bp)
    cdo = unreal.get_default_object(gen) if gen else None
    ncdo = unreal.get_default_object(exp['parent'])
    if cdo is None:
        bw06_out('FAIL', '[%s] no CDO' % stage)
        return None
    ok, mesh = bw06_gp(cdo, 'Mesh')
    okn, nmesh = bw06_gp(ncdo, 'Mesh')
    if ok and mesh:
        try:
            cur = mesh.get_skeletal_mesh_asset()
        except Exception:
            _o, cur = bw06_gp(mesh, 'SkeletalMeshAsset')
        if exp['sk'] is not None:
            bw06_check(bw06_path(cur) == bw06_path(exp['sk']), '[%s] Mesh skeletal mesh = %s' % (stage, bw06_path(cur)), 'expected ' + BW06_SK_PATH)
        else:
            bw06_out('WARN', '[%s] Mesh skeletal mesh = %s (SK_Burrower missing, not set)' % (stage, bw06_path(cur)))
        _o, mode = bw06_gp(mesh, 'AnimationMode')
        bw06_check(bw06_enum_name(mode) == 'ANIMATION_BLUEPRINT' or getattr(mode, 'value', mode) == 0,
                   '[%s] Mesh animation mode = %s' % (stage, bw06_enum_name(mode)))
        _o, ac = bw06_gp(mesh, 'AnimClass')
        if exp['abp_cls'] is not None:
            bw06_check(bw06_path(ac) == bw06_path(exp['abp_cls']), '[%s] Mesh anim class = %s' % (stage, bw06_path(ac)), 'expected ABP_Burrower_C')
        else:
            bw06_out('WARN', '[%s] Mesh anim class = %s (ABP_Burrower not available yet: re-run after the AnimBP step)'
                     % (stage, bw06_path(ac)))
        if okn and nmesh:
            for prop, conv in (('RelativeLocation', bw06_vec), ('RelativeRotation', bw06_rot), ('RelativeScale3D', bw06_vec)):
                _a, vb = bw06_gp(mesh, prop)
                _b, vc = bw06_gp(nmesh, prop)
                bw06_check(bw06_same3(conv(vb), conv(vc)), '[%s] Mesh %s = %s (C++ %s)' % (stage, prop, conv(vb), conv(vc)))
    else:
        bw06_out('FAIL', '[%s] Mesh component missing' % stage)
    ok, hb = bw06_gp(cdo, 'HealthBarWidgetComponent')
    if ok and hb:
        _o, wc = bw06_gp(hb, 'WidgetClass')
        if exp['wbp_cls'] is not None:
            bw06_check(bw06_path(wc) == bw06_path(exp['wbp_cls']), '[%s] HealthBar widget class = %s' % (stage, bw06_path(wc)))
        _o, ds = bw06_gp(hb, 'DrawSize')
        try:
            dsv = (int(ds.x), int(ds.y))
        except Exception:
            dsv = str(ds)
        if exp['draw'] is not None:
            bw06_check(dsv == tuple(exp['draw']), '[%s] HealthBar draw size = %s' % (stage, dsv))
        _o, sp = bw06_gp(hb, 'Space')
        bw06_out('INFO', '[%s] HealthBar space = %s (C++ sets Screen; the goblin uses World)' % (stage, bw06_enum_name(sp)))
    else:
        bw06_out('FAIL', '[%s] HealthBar component missing' % stage)
    ok, rb = bw06_gp(cdo, 'RotorBox')
    if ok and rb:
        try:
            par = rb.get_attach_parent()
            sock = str(rb.get_attach_socket_name())
        except Exception as e:
            par, sock = None, 'ERR %s' % e
        _o, loc = bw06_gp(rb, 'RelativeLocation')
        bw06_check(par is not None and bw06_path(par) == bw06_path(mesh) and sock in ('None', ''),
                   '[%s] RotorBox on the mesh, no socket (parent %s, socket %s, rel %s)' % (stage, bw06_path(par), sock, bw06_vec(loc)),
                   'do not give RotorBox a Parent Socket (cpp_notes.md item 3)')
    _o, sa = bw06_gp(cdo, 'StartupAbilities')
    bw06_check(_o and len(sa) == 0, '[%s] StartupAbilities empty (%s)' % (stage, [bw06_path(x) for x in sa] if _o else sa))
    _o, psa = bw06_gp(cdo, 'PassiveStartupAbilities')
    if _o and len(psa):
        bw06_out('WARN', '[%s] PassiveStartupAbilities not empty: %s (not changed by this script)' % (stage, [bw06_path(x) for x in psa]))
    _o, dmi = bw06_gp(cdo, 'DissolveMaterialInstance')
    bw06_check(_o and dmi is None, '[%s] DissolveMaterialInstance unset (%s)' % (stage, bw06_path(dmi)))
    _o, rf = bw06_gp(cdo, 'bUseMeshRagdollFallback')
    bw06_check(_o and bool(rf) == bool(RAGDOLL_FALLBACK), '[%s] bUseMeshRagdollFallback = %s (flag RAGDOLL_FALLBACK=%s)'
               % (stage, rf, RAGDOLL_FALLBACK))
    _o, cc = bw06_gp(cdo, 'CharacterClass')
    if _o:
        char_class = bw06_class_name(cc)
    else:
        try:
            js = json.loads(unreal.ToolsetLibrary.get_object_properties(cdo, ['CharacterClass']))
            char_class = bw06_class_name(js.get('CharacterClass'))
        except Exception as e:
            bw06_out('WARN', '[%s] could not read CharacterClass (%s); assuming the C++ default Warrior' % (stage, e))
            char_class = 'Warrior'
    _o, lvl = bw06_gp(cdo, 'CharacterLevel')
    _o2, ls = bw06_gp(cdo, 'LifeSpan')
    bw06_out('INFO', '[%s] CharacterClass=%s CharacterLevel=%s LifeSpan=%s' % (stage, char_class, lvl, ls))
    bw06_collision_compare(cdo, ncdo, stage)
    return char_class, (int(lvl) if _o else 1)


def bw06_disk_check(exp):
    """Parses the saved BP_Burrower.uasset: proves the values are in the package, and that no graph calls
    InitializeEnemyAttributes. Values equal to the C++ archetype are not written (delta serialization)."""
    path = os.path.join(BW06_PROJECT_DIR, 'Content', BW06_BP_PATH[len('/Game/'):] + '.uasset')
    try:
        pkg = bw06_pkg_read(path)
    except Exception as e:
        bw06_out('WARN', '[disk] could not parse %s: %s' % (path, e))
        return
    cdo_name = 'Default__%s_C' % BW06_BP_PATH.rsplit('/', 1)[-1]
    m = bw06_pkg_find(pkg, 'CharacterMesh0', outer_name=cdo_name)
    mp = bw06_pkg_props(pkg, m) if m else {}
    bw06_out('INFO', '[disk] CharacterMesh0 saved properties: %s' % sorted(mp.keys()))
    if exp['sk'] is not None:
        v = mp.get('SkinnedAsset') or mp.get('SkeletalMesh')
        bw06_check(v and 'SK_Burrower' in str(v), '[disk] CharacterMesh0 SkinnedAsset = %s' % v)
    if exp['abp_cls'] is not None:
        bw06_check('ABP_Burrower_C' in str(mp.get('AnimClass')), '[disk] CharacterMesh0 AnimClass = %s' % mp.get('AnimClass'))
    for k in ('RelativeLocation', 'RelativeRotation', 'RelativeScale3D'):
        if k in mp:
            bw06_out('WARN', '[disk] CharacterMesh0 has a saved %s = %s (differs from the C++ archetype)' % (k, mp[k]))
    h = bw06_pkg_find(pkg, 'HealthBar', outer_name=cdo_name)
    hp = bw06_pkg_props(pkg, h) if h else {}
    if exp['wbp_cls'] is not None:
        bw06_check('WBP_HealthBar_C' in str(hp.get('WidgetClass')), '[disk] HealthBar WidgetClass = %s' % hp.get('WidgetClass'))
    if exp['draw'] is not None:
        bw06_check(tuple(hp.get('DrawSize') or ()) == tuple(exp['draw']), '[disk] HealthBar DrawSize = %s' % (hp.get('DrawSize'),))
    for comp in ('CollisionCylinder', 'CharacterMesh0', 'RotorBox'):
        e = bw06_pkg_find(pkg, comp, outer_name=cdo_name)
        p = bw06_pkg_props(pkg, e) if e else {}
        over = [k for k in p if k in ('BodyInstance', 'bGenerateOverlapEvents', 'CollisionProfileName')]
        if over:
            bw06_out('WARN', '[disk] %s has saved collision properties %s: possible override of the C++ preset '
                     '(the editor-side compare above is the authority)' % (comp, over))
    c = bw06_pkg_find(pkg, cdo_name)
    cp = bw06_pkg_props(pkg, c) if c else {}
    bw06_out('INFO', '[disk] %s saved properties: %s' % (cdo_name, sorted(cp.keys())))
    sa = cp.get('StartupAbilities')
    bw06_check(not sa, '[disk] StartupAbilities empty (%s)' % (sa,))
    bw06_check(not cp.get('DissolveMaterialInstance'), '[disk] DissolveMaterialInstance unset (%s)' % cp.get('DissolveMaterialInstance'))
    rf = cp.get('bUseMeshRagdollFallback', True)       # absent = C++ default true
    bw06_check(bool(rf) == bool(RAGDOLL_FALLBACK), '[disk] bUseMeshRagdollFallback = %s%s'
               % (rf, '' if 'bUseMeshRagdollFallback' in cp else ' (not saved = C++ default)'))
    bad = [n for n in pkg['names'] if 'InitializeEnemyAttributes' in n]
    bw06_check(not bad, '[disk] no graph references InitializeEnemyAttributes', 'remove that node from BP_Burrower: the C++ '
               'already applies the attribute effects (twice stacks them)')
    nodes = [e['name'] for e in pkg['exps'] if bw06_pkg_class_name(pkg, e).startswith('K2Node')]
    bw06_out('INFO', '[disk] graph nodes in BP_Burrower: %s (a new BP only has the 3 disabled default event nodes)' % nodes)


def bw06_reload():
    bp = unreal.EditorAssetLibrary.load_asset(BW06_BP_PATH)
    pkg = bp.get_outermost()
    try:
        n = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(bp)
        if n:
            bw06_out('INFO', 'closed %d editor(s) of BP_Burrower before the reload' % n)
    except Exception as e:
        bw06_out('WARN', 'close_all_editors_for_asset failed: %s' % e)
    del bp
    res = unreal.EditorLoadingAndSavingUtils.reload_packages([pkg], unreal.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
    bw06_out('INFO', 'reload_packages(BP_Burrower) -> %s' % (res,))


def bw06_blueprint():
    """Returns (char_class_name, level) of BP_Burrower, or (None, 1)."""
    parent_cls = bw06_load_class(BW06_PARENT_CLASS)
    if parent_cls is None:
        bw06_out('FAIL', '%s not found: build AuraEditor with the Burrower code and restart the editor' % BW06_PARENT_CLASS)
        return None, 1
    exp = bw06_expected(parent_cls)
    dirty_before = bw06_dirty_packages()
    bp, created = bw06_find_or_create(parent_cls)
    if bp is None:
        return None, 1
    if not created:
        # the CDO must be current before editing (re-parent / stale class)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    if not bw06_apply(bp, exp):
        return None, 1
    ok = unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    bw06_check(ok, 'BP_Burrower compiled without errors', 'open BP_Burrower and read the compiler results')
    del bp
    char_class, lvl = bw06_read('after compile', exp) or (None, 1)
    # nothing outside our folder may have been dirtied by this script; never saved here anyway
    new_dirty = sorted(p for p in bw06_dirty_packages() - dirty_before if not p.startswith(BW06_FOLDER + '/'))
    if new_dirty:
        bw06_out('WARN', 'packages outside %s became dirty during this script (NOT saved; discard them, do not Save All): %s'
                 % (BW06_FOLDER, new_dirty))
    saved = False
    try:
        saved = unreal.EditorAssetLibrary.save_asset(BW06_BP_PATH, only_if_is_dirty=False)
    except Exception as e:
        bw06_out('FAIL', 'save_asset raised: %s' % e)
    bw06_check(saved, 'saved %s (only this asset)' % BW06_BP_PATH)
    if saved:
        bw06_disk_check(exp)
    if saved and RELOAD_AFTER_SAVE:
        try:
            bw06_reload()
            r = bw06_read('after reload', exp)
            if r:
                char_class, lvl = r
        except Exception as e:
            bw06_out('WARN', 'reload/verify failed (%s); the after-compile and on-disk checks above still hold. %s'
                     % (e, traceback.format_exc().splitlines()[-1]))
    return char_class, lvl


# ---------------------------------------------------------------------------------------------------------------------
# Read-only checks
# ---------------------------------------------------------------------------------------------------------------------
def bw06_k(d, key):
    """Case-insensitive dict lookup (FJsonObjectConverter lower-cases the first letter: XPReward -> xPReward)."""
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return None


def bw06_ref(v):
    if v is None:
        return None
    if isinstance(v, dict):
        r = bw06_k(v, 'refPath')
        if r:
            return r
        for x in v.values():
            if isinstance(x, str) and x.startswith('/'):
                return x
        return None
    s = str(v)
    return None if s in ('', 'None', 'null') else s


def bw06_class_name(v):
    """ECharacterClass value (enum, 'WARRIOR', 'Warrior', 'ECharacterClass::Warrior', 1) -> 'Warrior'."""
    s = bw06_enum_name(v).split('::')[-1].split('.')[-1]
    if s.isdigit() and int(s) < len(BW06_CHAR_CLASS_ENUM):
        return BW06_CHAR_CLASS_ENUM[int(s)]
    for n in BW06_CHAR_CLASS_ENUM:
        if bw06_norm(n) == bw06_norm(s):
            return n
    return s


def bw06_class_info_entries(da):
    """Normalised EnemyCharClassInfos: [{'class','primary','xp_value','table','row'}], plus the source used."""
    # 1) ToolsetLibrary JSON (FEnemyCharClassInfo is not exported to Python)
    try:
        d = json.loads(unreal.ToolsetLibrary.get_object_properties(da, ['EnemyCharClassInfos']))
        if not isinstance(d.get('EnemyCharClassInfos'), list):
            raise RuntimeError('no EnemyCharClassInfos array in %s' % str(d)[:200])
        out = []
        for e in d.get('EnemyCharClassInfos') or []:
            xp = bw06_k(e, 'XPReward') or {}
            cv = bw06_k(xp, 'Curve') or {}
            row = bw06_k(cv, 'RowName')
            out.append({'class': bw06_class_name(bw06_k(e, 'Class')), 'primary': bw06_ref(bw06_k(e, 'PrimaryAttributesEffect')),
                        'xp_value': float(bw06_k(xp, 'Value') or 0.0), 'table': bw06_ref(bw06_k(cv, 'CurveTable')),
                        'row': None if row in (None, 'None', '') else str(row)})
        return out, 'ToolsetLibrary.get_object_properties'
    except Exception as e:
        bw06_out('WARN', 'ToolsetLibrary read of %s failed (%s), trying get_editor_property' % (bw06_path(da), e))
    # 2) plain Python
    try:
        out = []
        for e in da.get_editor_property('EnemyCharClassInfos'):
            xp = e.get_editor_property('XPReward')
            cv = xp.get_editor_property('Curve')
            row = str(cv.get_editor_property('RowName'))
            out.append({'class': bw06_class_name(e.get_editor_property('Class')),
                        'primary': bw06_path(e.get_editor_property('PrimaryAttributesEffect')),
                        'xp_value': float(xp.get_editor_property('Value')),
                        'table': bw06_ref(bw06_path(cv.get_editor_property('CurveTable'))),
                        'row': None if row in ('None', '') else row})
        return out, 'get_editor_property'
    except Exception as e:
        bw06_out('WARN', 'get_editor_property read of %s failed (%s), reading the .uasset on disk' % (bw06_path(da), e))
    # 3) the saved file
    path = os.path.join(BW06_PROJECT_DIR, 'Content', da.get_outermost().get_name()[len('/Game/'):] + '.uasset')
    pkg = bw06_pkg_read(path)
    e = bw06_pkg_find(pkg, da.get_name())
    out = []
    for x in (bw06_pkg_props(pkg, e).get('EnemyCharClassInfos') or []):
        xp = x.get('XPReward') or {}
        cv = xp.get('Curve') or {}
        cls = bw06_class_name(x.get('Class', 'ECharacterClass::Warrior'))
        out.append({'class': cls, 'primary': x.get('PrimaryAttributesEffect'), 'xp_value': float(xp.get('Value', 0.0)),
                    'table': cv.get('CurveTable'), 'row': None if cv.get('RowName') in (None, 'None') else cv.get('RowName')})
    return out, 'disk (%s)' % path


def bw06_check_class_info(da, char_class, level):
    if da is None:
        bw06_out('FAIL', 'no enemy class info data asset to check')
        return
    bw06_out('INFO', 'checking %s (%s)' % (bw06_path(da), da.get_class().get_name()))
    try:
        entries, src = bw06_class_info_entries(da)
    except Exception as e:
        bw06_out('FAIL', 'could not read EnemyCharClassInfos of %s: %s' % (bw06_path(da), e))
        return
    for i, e in enumerate(entries):
        bw06_out('INFO', '  [%d] Class=%s PrimaryAttributesEffect=%s XPReward: Value=%s CurveTable=%s Row=%s'
                 % (i, e['class'], e['primary'], e['xp_value'], e['table'], e['row']))
    bw06_out('INFO', '  (read via %s)' % src)
    for prop in ('SecondaryAttributesEffect', 'VitalAttributesEffect'):
        ok, v = bw06_gp(da, prop)
        if not ok:
            try:
                v = bw06_ref(json.loads(unreal.ToolsetLibrary.get_object_properties(da, [prop])).get(prop))
                ok = True
            except Exception:
                pass
        if not ok:
            bw06_out('WARN', '  %s not readable' % prop)
        elif v:
            bw06_out('INFO', '  %s = %s' % (prop, v if isinstance(v, str) else bw06_path(v)))
        else:
            bw06_out('WARN', '  %s is unset: the Burrower gets no %s (MaxHealth may stay 0)' % (prop, prop))
    char_class = bw06_class_name(char_class or 'Warrior')
    want = bw06_norm(char_class)
    match = next((e for e in entries if bw06_norm(e['class']) == want), None)   # GetInfoForClass returns the first match
    fix = ('add an EnemyCharClassInfos entry Class=%s with XPReward Value=1 (or the XP wanted), Curve = CT_XPRewardForEnemy '
           '/ row %s, in %s. That asset is OUTSIDE /Game/Assets/Enemies/Burrower/: the lead must OK the change'
           % (char_class, char_class, bw06_path(da)))
    if match is None:
        bw06_out('FAIL', 'no class info entry for the Burrower CharacterClass %s: UMyBPFuncLib::GetXPRewardForCharacterClass '
                 'hits checkf on the kill -- %s' % (char_class, fix))
        return
    if not match['primary']:
        bw06_out('WARN', 'the %s entry has no PrimaryAttributesEffect (the Burrower then has no primary attributes)' % char_class)
    if not match['row']:
        bw06_out('WARN', 'the %s entry XPReward has no curve row: a static value %s (valid, no checkf) but not a curve -- %s'
                 % (char_class, match['xp_value'], fix))
        return
    if not match['table']:
        bw06_out('FAIL', 'the %s entry XPReward has row %s but no CurveTable: IsValid() is false, checkf on the kill -- %s'
                 % (char_class, match['row'], fix))
        return
    try:
        ct = unreal.load_asset(match['table'])
        res = unreal.DataTableFunctionLibrary.evaluate_curve_table_row(ct, match['row'], float(level), 'bw_06')
        result, val = res if isinstance(res, tuple) else (res, None)
        found = ('ROW_FOUND' in bw06_enum_name(result)) or getattr(result, 'value', result) == 0
        bw06_check(found, 'DA class info: %s entry XPReward = Value %s x %s[%s](level %s = %s) -> %s XP per kill'
                   % (char_class, match['xp_value'], bw06_path(ct), match['row'], level, val,
                      (match['xp_value'] * val) if (found and val is not None) else '?'),
                   'row %s is missing in %s: checkf on the kill -- %s' % (match['row'], bw06_path(ct), fix))
    except Exception as e:
        bw06_out('WARN', 'could not evaluate %s row %s (%s); entry present with table + row, so IsValid() should hold'
                 % (match['table'], match['row'], e))


def bw06_ini_value(ini, section, key):
    try:
        cur = None
        val = None
        for line in open(os.path.join(BW06_PROJECT_DIR, 'Config', ini), encoding='latin-1'):
            s = line.strip()
            if s.startswith('[') and s.endswith(']'):
                cur = s[1:-1]
            elif cur == section and s.split('=', 1)[0].strip() == key:
                val = s.split('=', 1)[1].strip()
        return val
    except Exception:
        return None


def bw06_map_game_mode_override():
    """(class path or None, source). Open level first, else StartupMap.umap on disk (no map is loaded)."""
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if world and world.get_outermost().get_name() == BW06_MAP_PACKAGE:
            gm = world.get_world_settings().get_editor_property('DefaultGameMode')
            return (bw06_path(gm) if gm else None), 'World Settings of the open StartupMap'
    except Exception as e:
        bw06_out('WARN', 'reading the open level World Settings failed: %s' % e)
    pkg = bw06_pkg_read(os.path.join(BW06_PROJECT_DIR, BW06_MAP_FILE))
    for e in pkg['exps']:
        if bw06_pkg_class_name(pkg, e) == 'WorldSettings':
            return bw06_pkg_props(pkg, e).get('DefaultGameMode'), 'WorldSettings in %s on disk' % BW06_MAP_FILE
    return None, '%s on disk (no WorldSettings export found)' % BW06_MAP_FILE


def bw06_check_debug_die(cls, label):
    if cls is None:
        bw06_out('WARN', '%s: class not found' % label)
        return
    ok, v = bw06_gp(unreal.get_default_object(cls), 'DebugDieAfterBeginPlaySeconds')
    if not ok:
        bw06_out('WARN', '%s: DebugDieAfterBeginPlaySeconds not readable: %s' % (label, v))
        return
    bw06_check(float(v) == 0.0, '%s DebugDieAfterBeginPlaySeconds = %s' % (label, v),
               'players die every %s s and the spawner keeps pausing: set it to 0 in %s (outside our folder, needs the '
               "lead's OK)" % (v, label))


def bw06_checks(char_class, level):
    bw06_out('INFO', '--- read-only checks (nothing is modified or saved) ---')
    # GameMode of StartupMap
    gm_cls = None
    try:
        override, src = bw06_map_game_mode_override()
        default = bw06_ini_value('DefaultEngine.ini', '/Script/EngineSettings.GameMapsSettings', 'GlobalDefaultGameMode')
        bw06_out('INFO', 'StartupMap GameMode Override = %s (%s); project GlobalDefaultGameMode = %s (DefaultEngine.ini)'
                 % (override, src, default))
        eff = override or default
        bw06_out('INFO', 'GameMode used by %s = %s (%s)' % (BW06_MAP_PACKAGE, eff, 'World Settings override' if override else 'project default'))
        gm_cls = bw06_load_class(eff) if eff else None
    except Exception as e:
        bw06_out('FAIL', 'could not determine the StartupMap GameMode: %s' % e)
    da_checked = []
    if gm_cls is not None:
        bw06_check(bw06_is_child(gm_cls, bw06_load_class(BW06_MYGAMEMODE_CLASS)), 'GameMode %s is an AMyGameMode' % bw06_path(gm_cls),
                   'the spawner refuses to spawn and the kill path dereferences AMyGameMode')
        gcdo = unreal.get_default_object(gm_cls)
        ok, da = bw06_gp(gcdo, 'DA_MyEnemyCharacterClassInfo')
        bw06_check(ok and da is not None, 'GameMode CDO DA_MyEnemyCharacterClassInfo = %s' % (bw06_path(da) if ok else da),
                   'set it in the GameMode BP (outside our folder): the kill path dereferences it')
        if ok and da is not None:
            bw06_check_class_info(da, char_class, level)
            da_checked.append(da.get_path_name())
        ok, pawn = bw06_gp(gcdo, 'DefaultPawnClass')
        if ok and pawn is not None:
            bw06_out('INFO', 'GameMode DefaultPawnClass = %s' % bw06_path(pawn))
            if bw06_is_child(pawn, bw06_load_class(BW06_MYCHARPLAYER_CLASS)) and bw06_path(pawn) != BW06_MECH_CLASS:
                bw06_check_debug_die(pawn, bw06_path(pawn))
    else:
        bw06_out('FAIL', 'GameMode class could not be loaded')
    # DA_CharClassInfo itself (if the GameMode uses another one, check both)
    try:
        da = unreal.EditorAssetLibrary.load_asset(BW06_DA_PATH)
        if da is None:
            bw06_out('FAIL', '%s not found' % BW06_DA_PATH)
        elif da.get_path_name() not in da_checked:
            if da_checked:
                bw06_out('WARN', 'the GameMode uses %s, not %s; checking %s as well' % (da_checked, BW06_DA_PATH, BW06_DA_PATH))
            bw06_check_class_info(da, char_class, level)
    except Exception as e:
        bw06_out('FAIL', 'DA_CharClassInfo check failed: %s' % e)
    # BP_MyCharMech
    bw06_check_debug_die(bw06_load_class(BW06_MECH_CLASS), BW06_MECH_CLASS)


# ---------------------------------------------------------------------------------------------------------------------
def bw06_main():
    bw06_out('INFO', 'bw_06_blueprint: RAGDOLL_FALLBACK=%s RELOAD_AFTER_SAVE=%s DO_BLUEPRINT=%s DO_CHECKS=%s'
             % (RAGDOLL_FALLBACK, RELOAD_AFTER_SAVE, DO_BLUEPRINT, DO_CHECKS))
    if bw06_pie_running():
        bw06_out('FAIL', 'PIE is running: stop Play first (saving is refused during PIE). Nothing was changed.')
        return
    char_class, level = None, 1
    if DO_BLUEPRINT:
        try:
            char_class, level = bw06_blueprint()
        except Exception as e:
            bw06_out('FAIL', 'BP_Burrower step raised %s\n%s' % (e, traceback.format_exc()))
    if char_class is None:
        try:
            cls = bw06_load_class(BW06_BP_PATH + '.BP_Burrower_C') or bw06_load_class(BW06_PARENT_CLASS)
            ok, cc = bw06_gp(unreal.get_default_object(cls), 'CharacterClass')
            char_class = bw06_class_name(cc) if ok else 'Warrior'
        except Exception:
            char_class = 'Warrior'
    if DO_CHECKS:
        try:
            bw06_checks(char_class, level)
        except Exception as e:
            bw06_out('FAIL', 'checks raised %s\n%s' % (e, traceback.format_exc()))


try:
    bw06_main()
except Exception as _bw06_e:
    bw06_out('FAIL', 'bw_06_blueprint raised %s\n%s' % (_bw06_e, traceback.format_exc()))
finally:
    print('SUMMARY: %d PASS, %d WARN, %d FAIL' % (BW06_R['PASS'], BW06_R['WARN'], BW06_R['FAIL']))
    try:
        os.makedirs(os.path.dirname(BW06_RESULT_JSON), exist_ok=True)
        with open(BW06_RESULT_JSON, 'w') as _f:
            json.dump(BW06_R, _f, indent=1)
        print('INFO: results written to %s' % BW06_RESULT_JSON)
    except Exception as _e:
        print('WARN: could not write %s: %s' % (BW06_RESULT_JSON, _e))
