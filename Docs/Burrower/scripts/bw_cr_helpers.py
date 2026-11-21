# bw_cr_helpers.py - UE 5.8 Control Rig / RigVM helpers for building and testing CR_Burrower from editor Python.
#
# Every unreal.* name used here was checked against the UE 5.8 source; file:line references are in
# notes_cr_core.md (same folder). Names that could not be checked carry an '# UNVERIFIED:' comment and a fallback.
#
# The rig is created as a LEGACY UControlRigBlueprint (ControlRigBlueprintLegacy.h:33), like the project's CR_Mech
# and like Epic's own 5.8 AnimationAssistant toolset (controlrig.py:51-70). The 5.8 content-browser default is the
# new UControlRigRuntimeAsset (CVar RigVM.BlueprintIndependentAssets=true); see notes_cr_core.md section 1.
#
# Use from an inbox script (the harness exec()s files in a shared namespace on the game thread):
#
#     import sys, importlib
#     sys.path.insert(0, '/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts')
#     import bw_cr_helpers as H
#     importlib.reload(H)                    # pick up edits when re-running
#     rig = H.get_or_create_rig()            # reuses /Game/Assets/Enemies/Burrower/CR_Burrower if it exists
#     H.core_audit(rig)                      # optional: PASS/FAIL for every core struct path and pin
#     rig.set_auto_vm_recompile(False)       # no VM recompile per edit while building (compile_rig turns it back on)
#     H.clear_rig_graphs(rig)                # idempotent rebuild: drop all nodes (variables are kept)
#     H.ensure_variable(rig, 'RotorAngleDeg', 'float', True, False, 0.0)
#     g = H.RigGraph(rig)                    # main graph 'RigVMModel'
#     ev_c = g.ensure_event(H.EV_CONSTRUCTION); ev_f = g.ensure_event(H.EV_FORWARDS)
#     n = g.node(H.S['GetTransform'], 'Rotor_J0'); g.setp(n + '.Item', H.bone('J0_Head'))
#     ...
#     H.compile_rig(rig); H.save_rig()
#     H.run_rig_test(rig, bones=['Rotor'], variables={'RotorAngleDeg': 45.0})   # no PIE, no frames needed
#
# Nothing runs at import time. All output lines start with PASS:/FAIL:/WARN:/INFO:.
# Errors raise BwError (a RuntimeError) with a hint; UE errors reported through FScriptExceptionHandler
# (RigVMController::ReportError, the RigVM compiler) arrive in Python as RuntimeError and are re-raised as BwError.

import os
import json
import math
import time
import warnings

import unreal

# --------------------------------------------------------------------------------------------------------------------
# Paths and verified struct paths
# --------------------------------------------------------------------------------------------------------------------

BURROWER_DIR = '/Game/Assets/Enemies/Burrower'
RIG_PATH = BURROWER_DIR + '/CR_Burrower'
SKM_PATH = BURROWER_DIR + '/SK_Burrower'
PA_PATH = BURROWER_DIR + '/PA_Burrower'
PA_OBJECT_PATH = PA_PATH + '.PA_Burrower'      # object pin defaults need the full object path (Package.Object)

P = '/Script/ControlRigPhysics.'
D = '/Script/ControlRigDynamics.'
CR = '/Script/ControlRig.'
VM = '/Script/RigVM.RigVMFunction_'

MAIN_GRAPH = 'RigVMModel'                      # default model name (RigVMEditorAsset.cpp:462, RigVMClient.h:340)
FUNCTION_LIBRARY = 'RigVMFunctionLibrary'

EV_CONSTRUCTION = 'Construction'               # FRigUnit_PrepareForExecution::EventName (RigUnit_PrepareForExecution.h:29)
EV_FORWARDS = 'Forwards Solve'                 # FRigUnit_BeginExecution::EventName (RigUnit_BeginExecution.h:29)

# Core Control Rig / RigVM structs, 5.8 paths verified in the headers (notes_cr_core.md section 4).
S = {
    'PrepareForExecution':      CR + 'RigUnit_PrepareForExecution',      # Construction Event, pin ExecutePin (out)
    'BeginExecution':           CR + 'RigUnit_BeginExecution',           # Forwards Solve, pin ExecutePin (out)
    'GetTransform':             CR + 'RigUnit_GetTransform',             # Item, Space, bInitial -> Transform (pure)
    'SetTransform':             CR + 'RigUnit_SetTransform',             # ExecutePin, Item, Space, bInitial, Value, Weight, bPropagateToChildren
    'SetRotation':              CR + 'RigUnit_SetRotation',              # same pins, Value is FQuat
    'SetTranslation':           CR + 'RigUnit_SetTranslation',           # same pins, Value is FVector
    'MathFloatMul':             VM + 'MathFloatMul',                     # A, B -> Result (float)
    'MathFloatSub':             VM + 'MathFloatSub',
    'MathFloatAdd':             VM + 'MathFloatAdd',
    'MathFloatDiv':             VM + 'MathFloatDiv',
    'MathFloatSin':             VM + 'MathFloatSin',                     # Value -> Result (radians in)
    'MathFloatCos':             VM + 'MathFloatCos',
    'MathFloatRad':             VM + 'MathFloatRad',                     # Value (deg) -> Result (rad)
    'MathFloatClamp':           VM + 'MathFloatClamp',                   # Value, Minimum, Maximum -> Result
    'MathBoolToFloat':          VM + 'MathBoolToFloat',                  # Value (bool) -> Result (float 0/1)
    'MathBoolOnce':             VM + 'MathBoolOnce',                     # Duration (visible) -> Result (bool)
    'MathQuaternionFromAxisAndAngle': VM + 'MathQuaternionFromAxisAndAngle',  # Axis (FVector), Angle (float, rad) -> Result (FQuat)
    'MathQuaternionMul':        VM + 'MathQuaternionMul',                # A, B -> Result = A*B (FQuat)
    'MathQuaternionInverse':    VM + 'MathQuaternionInverse',            # Value -> Result (FQuat)
    'MathQuaternionRotateVector': VM + 'MathQuaternionRotateVector',     # Transform (FQuat), Vector -> Result (FVector)
    'MathTransformMul':         VM + 'MathTransformMul',                 # A, B -> Result = A*B (FTransform)
    'MathTransformMakeRelative': VM + 'MathTransformMakeRelative',       # Global, Parent -> Local (FTransform)
    'MathTransformMakeAbsolute': VM + 'MathTransformMakeAbsolute',       # Local, Parent -> Global
    'ControlFlowBranch':        VM + 'ControlFlowBranch',                # ExecuteContext, Condition -> True / False / Completed
    'ControlFlowRunOnce':       VM + 'ControlFlowRunOnce',               # ExecuteContext -> Once / Completed
}

# Recipe names that do not exist in 5.8 (or are deprecated) -> what to use instead.
RECIPE_RENAMES = {
    VM + 'MathQuatFromAxisAndAngle': S['MathQuaternionFromAxisAndAngle'],
    VM + 'MathQuatMul': S['MathQuaternionMul'],
    VM + 'MathQuatInverse': S['MathQuaternionInverse'],
    VM + 'MathQuatRotateVector': S['MathQuaternionRotateVector'],
}
DEPRECATED = {
    VM + 'MathTransformMake': 'deprecated in 5.7 (upgrades to the FRigVMDispatch_Constant dispatch node). Instead link the '
                              'quaternion into the Rotation sub-pin of an input, e.g. "<MathTransformMul>.A.Rotation".',
}

# Expected pins of the core structs: (pin name, cpp-type substring or None, direction key, is execute pin)
# Direction keys: I=input, O=output, IO=io, V=visible, H=hidden.
CORE_PIN_SPECS = {
    S['PrepareForExecution']: [('ExecutePin', None, 'O', True)],
    S['BeginExecution']: [('ExecutePin', None, 'O', True)],
    S['GetTransform']: [('Item', 'FRigElementKey', 'I', False), ('Space', 'TransformSpace', 'I', False),
                        ('bInitial', 'bool', 'I', False), ('Transform', 'FTransform', 'O', False)],
    S['SetTransform']: [('ExecutePin', None, 'IO', True), ('Item', 'FRigElementKey', 'I', False),
                        ('Space', 'TransformSpace', 'I', False), ('bInitial', 'bool', 'I', False),
                        ('Value', 'FTransform', 'I', False), ('Weight', 'float', 'I', False),
                        ('bPropagateToChildren', 'bool', 'I', False)],
    S['SetRotation']: [('ExecutePin', None, 'IO', True), ('Item', 'FRigElementKey', 'I', False),
                       ('Space', 'TransformSpace', 'I', False), ('bInitial', 'bool', 'I', False),
                       ('Value', 'FQuat', 'I', False), ('Weight', 'float', 'I', False),
                       ('bPropagateToChildren', 'bool', 'I', False)],
    S['MathFloatMul']: [('A', 'float', 'I', False), ('B', 'float', 'I', False), ('Result', 'float', 'O', False)],
    S['MathFloatSub']: [('A', 'float', 'I', False), ('B', 'float', 'I', False), ('Result', 'float', 'O', False)],
    S['MathFloatSin']: [('Value', 'float', 'I', False), ('Result', 'float', 'O', False)],
    S['MathFloatCos']: [('Value', 'float', 'I', False), ('Result', 'float', 'O', False)],
    S['MathFloatRad']: [('Value', 'float', 'I', False), ('Result', 'float', 'O', False)],
    S['MathFloatClamp']: [('Value', 'float', 'I', False), ('Minimum', 'float', 'I', False),
                          ('Maximum', 'float', 'I', False), ('Result', 'float', 'O', False)],
    S['MathBoolToFloat']: [('Value', 'bool', 'I', False), ('Result', 'float', 'O', False)],
    S['MathQuaternionFromAxisAndAngle']: [('Axis', 'FVector', 'I', False), ('Angle', 'float', 'I', False),
                                          ('Result', 'FQuat', 'O', False)],
    S['MathQuaternionMul']: [('A', 'FQuat', 'I', False), ('B', 'FQuat', 'I', False), ('Result', 'FQuat', 'O', False)],
    S['MathQuaternionInverse']: [('Value', 'FQuat', 'I', False), ('Result', 'FQuat', 'O', False)],
    S['MathQuaternionRotateVector']: [('Transform', 'FQuat', 'I', False), ('Vector', 'FVector', 'I', False),
                                      ('Result', 'FVector', 'O', False)],
    S['MathTransformMul']: [('A', 'FTransform', 'I', False), ('B', 'FTransform', 'I', False),
                            ('Result', 'FTransform', 'O', False)],
    S['MathTransformMakeRelative']: [('Global', 'FTransform', 'I', False), ('Parent', 'FTransform', 'I', False),
                                     ('Local', 'FTransform', 'O', False)],
    S['ControlFlowBranch']: [('ExecuteContext', None, 'I', True), ('Condition', 'bool', 'I', False),
                             ('True', None, 'O', True), ('False', None, 'O', True), ('Completed', None, 'O', True)],
}

# C++ type strings accepted by add_member_variable (RigVMExternalVariable.cpp:108-148, RigVMDeveloperTypeUtils.cpp:42-58)
CPP_FLOAT = 'float'                              # single precision (FFloatProperty), matches UBurrowerAnimInstance floats
CPP_DOUBLE = 'double'
CPP_BOOL = 'bool'
CPP_INT = 'int32'
CPP_TRANSFORM = '/Script/CoreUObject.Transform'  # NOT 'FTransform' (that string finds no struct and the add fails)
CPP_VECTOR = '/Script/CoreUObject.Vector'
CPP_QUAT = '/Script/CoreUObject.Quat'
_CPP_DESC = {CPP_TRANSFORM: 'FTransform', CPP_VECTOR: 'FVector', CPP_QUAT: 'FQuat'}   # how get_member_variables reports them


# --------------------------------------------------------------------------------------------------------------------
# Output, errors, guards
# --------------------------------------------------------------------------------------------------------------------

def _out(tag, msg):
    print('%s: %s' % (tag, msg))


def info(msg):
    _out('INFO', msg)


def warn(msg):
    _out('WARN', msg)


def passed(msg):
    _out('PASS', msg)


def fail(msg):
    _out('FAIL', msg)


class BwError(RuntimeError):
    """Raised by these helpers. The message says what failed and what to try."""


def _ue(desc, fn, *args, **kwargs):
    """Call an unreal function. UE errors reported through FScriptExceptionHandler become a Python RuntimeError
    (PyUtil.cpp:617-641) and are re-raised as BwError; UE warnings arrive as Python RuntimeWarning and are printed."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        err = None
        try:
            result = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - we want every UE error with context
            result, err = None, e
    for w in caught:
        warn('%s: UE warning: %s' % (desc, w.message))
    if err is not None:
        raise BwError('%s: %s' % (desc, err))
    return result


def _is_ours(path):
    return path.startswith(BURROWER_DIR + '/')


def _require_ours(path):
    if not _is_ours(path):
        raise BwError('refusing to create/save/delete %s: only assets under %s/ are ours' % (path, BURROWER_DIR))


def pie_running():
    try:
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        return bool(les.is_in_play_in_editor())      # LevelEditorSubsystem.h:83-84
    except Exception as e:  # noqa: BLE001
        warn('cannot query PIE state (%s); assuming PIE is not running' % e)
        return False


def _require_no_pie(what):
    if pie_running():
        raise BwError('%s: PIE is running. Stop PIE first (asset saves are refused while PIE runs).' % what)


def saved_dir():
    d = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Burrower')
    os.makedirs(d, exist_ok=True)
    return d


def write_json(name, data):
    path = os.path.join(saved_dir(), name if name.endswith('.json') else name + '.json')
    with open(path, 'w') as f:
        json.dump(data, f, indent=1, sort_keys=True)
    info('wrote %s' % path)
    return path


def read_json(name):
    path = os.path.join(saved_dir(), name if name.endswith('.json') else name + '.json')
    with open(path) as f:
        return json.load(f)


def _transient_package():
    # unreal.get_transient_package() does not exist in 5.8 (PyCore.cpp:2055-2100 method table); the transient
    # package is '/Engine/Transient' (Obj.cpp:5912).
    pkg = unreal.find_package('/Engine/Transient')
    if pkg is None:
        fn = getattr(unreal, 'get_transient_package', None)   # UNVERIFIED: older API, fallback only
        pkg = fn() if fn else None
    if pkg is None:
        raise BwError('cannot find the transient package /Engine/Transient')
    return pkg


# --------------------------------------------------------------------------------------------------------------------
# Value text
# --------------------------------------------------------------------------------------------------------------------

def _fmt(v):
    """Python value -> RigVM pin default text. Bools must be exactly 'True'/'False' (RigVMPin.cpp:1336-1342)."""
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, int):
        return str(v)
    if hasattr(v, 'export_text'):            # unreal structs (PyWrapperStruct.cpp:1310)
        return v.export_text()
    return str(v)


def _same_value(a, b):
    a = '' if a is None else str(a).strip()
    b = '' if b is None else str(b).strip()
    if a == b:
        return True
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= 1e-5 * max(1.0, abs(fb))
    except ValueError:
        pass
    return a.strip('"').lower() == b.strip('"').lower()


def bone(name):
    """FRigElementKey text for a bone pin default."""
    return '(Type=Bone,Name="%s")' % name


def comp(bone_name, component):
    """FRigComponentKey text (fields ElementKey, Name: RigHierarchyDefines.h:1927-1931)."""
    return '(ElementKey=(Type=Bone,Name="%s"),Name="%s")' % (bone_name, component)


def arr(items):
    """Array pin default text; set_pin_default_value is called with resize_arrays=True so the array is resized."""
    return '(' + ','.join(items) + ')'


def vec(x, y, z):
    return '(X=%r,Y=%r,Z=%r)' % (float(x), float(y), float(z))


# --------------------------------------------------------------------------------------------------------------------
# Rig asset
# --------------------------------------------------------------------------------------------------------------------

def load_asset(path, cls=None):
    eal = unreal.EditorAssetLibrary
    if not eal.does_asset_exist(path):
        return None
    obj = eal.load_asset(path)
    if obj is not None and cls is not None and not isinstance(obj, cls):
        raise BwError('%s is a %s, expected %s' % (path, obj.get_class().get_name(), cls.__name__))
    return obj


def close_editors(asset):
    try:
        unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(asset)  # AssetEditorSubsystem.h:169-170
    except Exception as e:  # noqa: BLE001
        warn('close_all_editors_for_asset failed (%s); close the asset editor by hand if it is open' % e)


def _create_rig_asset(rig_path):
    try:
        unreal.load_module('ControlRigDeveloper')      # what the engine's own generated Python does (ControlRigBlueprintLegacy.cpp:393)
    except Exception:  # noqa: BLE001
        pass
    rig = None
    try:
        # ControlRigBlueprintFactory.h:43-44 -> ControlRigBlueprintActions.cpp:229-247 (AssetTools.create_asset with the
        # factory, unique name, no dialog). Creates an EMPTY rig: no bones, no events.
        rig = _ue('ControlRigBlueprintFactory.create_new_control_rig_asset',
                  unreal.ControlRigBlueprintFactory.create_new_control_rig_asset, rig_path, False)
    except BwError as e:
        warn('%s - falling back to AssetTools.create_asset with a ControlRigBlueprintFactory' % e)
    if rig is None:
        folder, name = rig_path.rsplit('/', 1)
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        rig = _ue('AssetTools.create_asset', tools.create_asset, name, folder, unreal.ControlRigBlueprint,
                  unreal.ControlRigBlueprintFactory())
    if rig is None:
        raise BwError('could not create %s. Create it by hand: right-click SK_Burrower > Create > Control Rig, '
                      'rename to CR_Burrower, then re-run.' % rig_path)
    name = rig_path.rsplit('/', 1)[1]
    if rig.get_path_name() != '%s.%s' % (rig_path, name):
        raise BwError('created %s instead of %s (name taken? CreateUniqueAssetName adds a suffix). It was NOT saved; '
                      'delete it by hand.' % (rig.get_path_name(), rig_path))
    if not isinstance(rig, unreal.ControlRigBlueprint):
        raise BwError('created %s is a %s, not a ControlRigBlueprint' % (rig_path, rig.get_class().get_name()))
    passed('created %s (UControlRigBlueprint)' % rig_path)
    return rig


def import_bones_from_mesh(rig, skm):
    """(Re-)imports the skeletal mesh's bones into the rig hierarchy; replaces existing, removes obsolete."""
    hc = _ue('get_hierarchy_controller', rig.get_hierarchy_controller)   # ControlRigBlueprintLegacy.h:247-248
    if hc is None:
        raise BwError('rig.get_hierarchy_controller() returned None')
    try:
        # RigHierarchyController.h:489-497 (InNameSpace has no default -> pass '')
        _ue('import_bones_from_skeletal_mesh', hc.import_bones_from_skeletal_mesh, skm, '', True, True, False, False, False)
    except BwError as e:
        warn('%s - trying import_bones(skeleton)' % e)
        skel = skm.get_editor_property('skeleton')
        _ue('import_bones', hc.import_bones, skel, '', True, True, False, False, False)   # RigHierarchyController.h:469-477
    names = bone_names(rig)
    info('rig hierarchy has %d bones after import (first: %s)' % (len(names), ', '.join(names[:4])))
    return names


def get_or_create_rig(rig_path=RIG_PATH, skm_path=SKM_PATH, recreate=False, import_bones=True):
    """Returns the UControlRigBlueprint at rig_path.
    Exists + is a ControlRigBlueprint + recreate False -> REUSED (graphs and variables untouched; call
    clear_rig_graphs() for a rebuild). Otherwise our own asset is deleted (ForceDelete, no dialog; referencers such as
    ABP_Burrower lose their reference) and created again. Bones are (re-)imported from the skeletal mesh and the
    preview mesh is set."""
    _require_ours(rig_path)
    _require_no_pie('get_or_create_rig')
    skm = load_asset(skm_path, unreal.SkeletalMesh)
    if skm is None:
        raise BwError('skeletal mesh %s not found: import the FBX first' % skm_path)
    eal = unreal.EditorAssetLibrary
    rig = None
    if eal.does_asset_exist(rig_path):
        existing = eal.load_asset(rig_path)
        if isinstance(existing, unreal.ControlRigBlueprint) and not recreate:
            rig = existing
            info('reusing existing %s (UControlRigBlueprint)' % rig_path)
        else:
            why = 'recreate=True' if isinstance(existing, unreal.ControlRigBlueprint) else \
                'it is a %s, not a ControlRigBlueprint' % (existing.get_class().get_name() if existing else 'None')
            warn('deleting our own %s (%s) and creating it again' % (rig_path, why))
            if existing is not None:
                close_editors(existing)
            existing = None
            if not _ue('EditorAssetLibrary.delete_asset', eal.delete_asset, rig_path):
                raise BwError('delete_asset(%s) failed; delete it by hand in the Content Browser' % rig_path)
    if rig is None:
        rig = _create_rig_asset(rig_path)
    if import_bones:
        import_bones_from_mesh(rig, skm)
    _ue('set_preview_mesh', rig.set_preview_mesh, skm, True)            # ControlRigBlueprintLegacy.h:142-143
    skel = skm.get_editor_property('skeleton')
    for prop in ('source_hierarchy_import', 'source_curve_import'):   # EditAnywhere (ControlRigBlueprintLegacy.h:282-287)
        try:
            rig.set_editor_property(prop, skel)
        except Exception as e:  # noqa: BLE001
            warn('could not set %s (%s); cosmetic only (used by "refresh hierarchy" in the rig editor)' % (prop, e))
    return rig


def get_controller(rig, model=None):
    """RigVMController for a model (default: main graph 'RigVMModel')."""
    if model is None:
        model = rig.get_default_model()                                # RigVMBlueprintLegacy.h:287
    if model is None:
        raise BwError('rig has no default model')
    c = None
    try:
        c = rig.get_controller_by_name(model.get_name())              # returns None if no controller exists yet
    except Exception:  # noqa: BLE001
        c = None
    if c is None:
        c = _ue('get_or_create_controller', rig.get_or_create_controller, model)   # RigVMBlueprintLegacy.h:316
    if c is None:
        raise BwError('no RigVMController for model %s' % model.get_name())
    return c


def root_models(rig):
    """Top-level graphs except the function library."""
    out = []
    for m in rig.get_all_models():
        try:
            if m.get_name() == FUNCTION_LIBRARY or not m.is_root_graph():
                continue
            lib_cls = getattr(unreal, 'RigVMFunctionLibrary', None)
            if lib_cls is not None and isinstance(m, lib_cls):
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append(m)
    return out


def clear_rig_graphs(rig):
    """Removes every node from every top-level graph (events included). Variables are kept, so AnimBP bindings to
    them survive a rebuild."""
    total = 0
    for m in root_models(rig):
        names = [n.get_fname() for n in m.get_nodes()]
        if names:
            c = get_controller(rig, m)
            _ue('remove_nodes_by_name(%s)' % m.get_name(), c.remove_nodes_by_name, names, False, False)
            total += len(names)
    info('cleared %d nodes from %d graph(s)' % (total, len(root_models(rig))))
    return total


# --------------------------------------------------------------------------------------------------------------------
# Variables
# --------------------------------------------------------------------------------------------------------------------

def member_variables(rig):
    """name -> FRigVMGraphVariableDescription (fields name, cpp_type, default_value: RigVMVariableDescription.h:35-63)."""
    try:
        vs = rig.get_member_variables()                                # RigVMBlueprintLegacy.h:424
    except Exception:  # noqa: BLE001
        vs = rig.get_asset_variables()                                 # UNVERIFIED on the legacy class; fallback only
    return {str(v.get_editor_property('name')): v for v in vs}


def ensure_variable(rig, name, cpp_type, is_public, is_read_only=False, default='', recreate_if_mismatch=False):
    """Adds a member variable or keeps an existing one of the same type.
    is_public True = 'Instance Editable' = visible as an input on the AnimBP Control Rig node
    (clears CPF_DisableEditOnInstance, RigVMBlueprintLegacy.cpp:1450-1460).
    add_member_variable compiles the blueprint synchronously (RigVMBlueprintLegacy.cpp:1221-1236)."""
    want_desc = _CPP_DESC.get(cpp_type, cpp_type)
    default_text = '' if default == '' or default is None else _fmt(default)
    have = member_variables(rig)
    if name in have:
        v = have[name]
        cur_type = str(v.get_editor_property('cpp_type'))
        cur_def = str(v.get_editor_property('default_value'))
        if cur_type == want_desc:
            if default_text and not _same_value(cur_def, default_text):
                warn('variable %s exists with default %r (wanted %r); kept. Change it in the rig editor if it matters '
                     '(defaults only matter for private variables or the editor preview).' % (name, cur_def, default_text))
            try:
                # BlueprintEditorLibrary.h:414-415 (works on NewVariables, which RigVM blueprints use)
                unreal.BlueprintEditorLibrary.set_blueprint_variable_instance_editable(rig, name, bool(is_public))
            except Exception as e:  # noqa: BLE001
                warn('could not set Instance Editable on %s (%s); tick it by hand (eye icon)' % (name, e))
            info('variable %s exists (%s) - kept' % (name, cur_type))
            return name
        if not recreate_if_mismatch:
            raise BwError('variable %s is %s, wanted %s. Re-run with recreate_if_mismatch=True (AnimBP pins bound '
                          'to it must then be re-bound).' % (name, cur_type, want_desc))
        warn('variable %s is %s, wanted %s: removing and adding it again' % (name, cur_type, want_desc))
        _ue('remove_member_variable', rig.remove_member_variable, name)
    got = _ue('add_member_variable(%s)' % name, rig.add_member_variable, name, cpp_type, bool(is_public),
              bool(is_read_only), default_text)
    got = '' if got is None else str(got)
    if got != name:
        raise BwError('add_member_variable(%r, %r) returned %r. Empty = type string not understood (use float/double/'
                      'bool/int32 or a struct path like %s); a suffixed name = a name clash.' % (name, cpp_type, got, CPP_TRANSFORM))
    passed('variable %s : %s public=%s default=%r' % (name, want_desc, bool(is_public), default_text))
    return got


def check_public_variables(rig, expected_public):
    """After a compile: checks which variables are public on a rig instance (URigVMHost::GetScriptAccessibleVariables,
    RigVMHost.h:165-166, = IsPublic, RigVMHost.cpp:502-508)."""
    inst = make_test_instance(rig)
    names = set(str(n) for n in inst.get_script_accessible_variables())
    ok = True
    for n in expected_public:
        if n in names:
            passed('variable %s is public' % n)
        else:
            fail('variable %s is NOT public (tick Instance Editable / eye icon on it)' % n)
            ok = False
    return ok


# --------------------------------------------------------------------------------------------------------------------
# Graph building
# --------------------------------------------------------------------------------------------------------------------

def _dir_enum():
    d = unreal.RigVMPinDirection                                        # RigVMFunction.h:39-48 (UENUM BlueprintType)
    return {'I': d.INPUT, 'O': d.OUTPUT, 'IO': d.IO, 'V': d.VISIBLE, 'H': d.HIDDEN}


class RigGraph(object):
    """Wraps one RigVM graph (default: the main 'RigVMModel') and its controller.
    All edits are made with setup_undo_redo=False (no transaction per edit). Node names are returned as actually
    created (the controller suffixes a name that is already taken; a WARN says so)."""

    def __init__(self, rig, model=None, columns=10, step=(340.0, 260.0), origin=(0.0, 0.0)):
        self.rig = rig
        self.model = model if model is not None else rig.get_default_model()
        self.c = get_controller(rig, self.model)
        self.g = self.c.get_graph()
        self._i = 0
        self._cols = columns
        self._step = step
        self._origin = origin
        self._dirs = _dir_enum()

    # ---- layout / lookup ----
    def next_pos(self):
        x = self._origin[0] + self._step[0] * (self._i % self._cols)
        y = self._origin[1] + self._step[1] * (self._i // self._cols)
        self._i += 1
        return unreal.Vector2D(x, y)

    def set_origin(self, x, y):
        self._origin = (float(x), float(y))
        self._i = 0

    def node_obj(self, name):
        n = self.g.find_node_by_name(name)                              # RigVMGraph.h UFUNCTION FindNodeByName
        if n is None:
            raise BwError('no node %r in graph %s' % (name, self.g.get_name()))
        return n

    def has_node(self, name):
        return self.g.find_node_by_name(name) is not None

    def struct_of(self, name):
        n = self.node_obj(name)
        try:
            s = n.get_script_struct()                                   # RigVMTemplateNode.h UFUNCTION GetScriptStruct
            return s.get_name() if s else ''
        except Exception:  # noqa: BLE001
            return ''

    def pin(self, path):
        p = self.g.find_pin(path)                                       # RigVMGraph.h UFUNCTION FindPin
        if p is None:
            node = path.split('.', 1)[0]
            pins = []
            if self.has_node(node):
                pins = [x.get_name() for x in self.node_obj(node).get_pins()]
            raise BwError('no pin %r (node %r pins: %s)' % (path, node, pins))
        return p

    def pins(self, name):
        out = []
        for p in self.node_obj(name).get_pins():
            out.append({'name': p.get_name(), 'cpp': p.get_cpp_type(), 'dir': p.get_direction(),
                        'exec': p.is_execute_context(), 'sub': [s.get_name() for s in p.get_sub_pins()]})
        return out

    # ---- nodes ----
    def node(self, struct_path, name, pos=None):
        if struct_path in RECIPE_RENAMES:
            raise BwError('%s does not exist in 5.8; use %s' % (struct_path, RECIPE_RENAMES[struct_path]))
        if struct_path in DEPRECATED:
            warn('%s is %s' % (struct_path, DEPRECATED[struct_path]))
        pos = pos if pos is not None else self.next_pos()
        # RigVMController.h:363-364: (struct path, method, position, node name, setup_undo_redo, print_python)
        n = _ue('add_unit_node_from_struct_path(%s, %s)' % (struct_path, name),
                self.c.add_unit_node_from_struct_path, struct_path, 'Execute', pos, name, False, False)
        if n is None:
            raise BwError('add_unit_node_from_struct_path(%s) returned None. Wrong path, plugin not enabled, or an '
                          'event that already exists (use ensure_event).' % struct_path)
        got = n.get_name()
        if got != name:
            warn('node %r was created as %r (name taken)' % (name, got))
        return got

    def remove(self, name):
        if self.has_node(name):
            _ue('remove_node_by_name(%s)' % name, self.c.remove_node_by_name, name, False, False)

    def var_get(self, var, name='', pos=None):
        """Getter node; returns its output pin path '<node>.Value' (RigVMVariableNode.h:95)."""
        cpp = self._var_cpp(var)
        pos = pos if pos is not None else self.next_pos()
        # RigVMController.h:399-400: (variable, cpp type, cpp type object, is_getter, default, position, node name, undo, python)
        n = _ue('add_variable_node(get %s)' % var, self.c.add_variable_node, var, cpp, None, True, '', pos, name, False, False)
        if n is None:
            raise BwError('add_variable_node(%s) returned None; does the variable exist?' % var)
        return n.get_name() + '.Value'

    def var_set(self, var, name='', pos=None):
        """Setter node; returns the node name. Pins: ExecuteContext (IO), Value (input)."""
        cpp = self._var_cpp(var)
        pos = pos if pos is not None else self.next_pos()
        n = _ue('add_variable_node(set %s)' % var, self.c.add_variable_node, var, cpp, None, False, '', pos, name, False, False)
        if n is None:
            raise BwError('add_variable_node(set %s) returned None' % var)
        return n.get_name()

    def _var_cpp(self, var):
        vs = member_variables(self.rig)
        if var not in vs:
            raise BwError('variable %r does not exist; add it with ensure_variable() first' % var)
        return str(vs[var].get_editor_property('cpp_type'))

    # ---- pin values and links ----
    def setp(self, pin_path, value):
        text = _fmt(value)
        p = self.pin(pin_path)
        if text.startswith('/Game/') or text.startswith('/Script/'):
            # object pin defaults are validated with FindObject (RigVMPin.cpp:1243): the object must be loaded
            try:
                if unreal.load_object(None, text) is None:
                    warn('object %s could not be loaded; the pin default will be refused' % text)
            except Exception as e:  # noqa: BLE001
                warn('load_object(%s) failed: %s' % (text, e))
        # RigVMController.h:919-920: (pin path, value, resize_arrays, setup_undo_redo, merge_undo, print_python, set_on_linked)
        ok = _ue('set_pin_default_value(%s)' % pin_path, self.c.set_pin_default_value, pin_path, text,
                 True, False, False, False, True)
        if ok:
            return True
        cur = p.get_default_value()
        if _same_value(cur, text):
            return True        # 5.8 returns False when a leaf pin already has this value (RigVMController.cpp:10423-10467)
        raise BwError('set_pin_default_value refused %s = %r (pin type %s, current %r). Hints: bools exactly '
                      'True/False; enums by value name (GlobalSpace/LocalSpace); vectors (X=..,Y=..,Z=..); keys '
                      '(Type=Bone,Name="x"); arrays (a,b,c); objects: full path of a LOADED object /Game/P/A.A'
                      % (pin_path, text, p.get_cpp_type(), cur))

    def link(self, src, dst):
        # RigVMController.h:1041-1042: (output pin path, input pin path, setup_undo_redo, print_python, ...)
        ok = _ue('add_link %s -> %s' % (src, dst), self.c.add_link, src, dst, False, False)
        if not ok:
            raise BwError('add_link %s -> %s returned False' % (src, dst))
        return True

    # ---- execution ----
    def _exec_pins(self, name):
        return [p for p in self.node_obj(name).get_pins() if p.is_execute_context()]   # RigVMPin.cpp:807-817

    def exec_out(self, name, which=None):
        d = self._dirs
        pins = [p for p in self._exec_pins(name) if p.get_direction() in (d['O'], d['IO'])]
        if which:
            pins = [p for p in pins if p.get_name() == which]
            if not pins:
                raise BwError('node %s has no execute output %r' % (name, which))
            return pins[0].get_pin_path()
        if not pins:
            raise BwError('node %s has no execute output (pure node?)' % name)
        for pref in ('Completed', 'ExecutePin', 'ExecuteContext'):
            for p in pins:
                if p.get_name() == pref:
                    return p.get_pin_path()
        return pins[0].get_pin_path()

    def exec_in(self, name):
        d = self._dirs
        pins = [p for p in self._exec_pins(name) if p.get_direction() in (d['I'], d['IO'])]
        if not pins:
            raise BwError('node %s has no execute input (event or pure node?)' % name)
        return pins[0].get_pin_path()

    def chain(self, start, out_pin=None):
        return Chain(self, start, out_pin)

    # ---- events ----
    def find_event(self, event_name, all_graphs=True):
        models = [self.model] + ([m for m in root_models(self.rig) if m.get_name() != self.model.get_name()]
                                 if all_graphs else [])
        for m in models:
            for n in m.get_nodes():
                try:
                    if n.is_event() and str(n.get_event_name()) == event_name:
                        return m.get_name(), n.get_name()
                except Exception:  # noqa: BLE001
                    continue
        return None

    def ensure_event(self, event_name, name=None, pos=None):
        """Returns the node name of the event in THIS graph, adding it if the rig has none.
        A freshly created rig has no events at all (Forwards Solve is only added when the rig editor opens an empty
        graph: RigVMEditor.cpp:320-325, ControlRigEditor.cpp:282-284)."""
        struct = {EV_CONSTRUCTION: S['PrepareForExecution'], EV_FORWARDS: S['BeginExecution']}.get(event_name)
        if struct is None:
            raise BwError('unknown event %r (use EV_CONSTRUCTION or EV_FORWARDS)' % event_name)
        found = self.find_event(event_name)
        if found:
            if found[0] != self.model.get_name():
                raise BwError('event %r already exists in graph %s, not in %s; build there or remove it'
                              % (event_name, found[0], self.model.get_name()))
            info('event %r exists: node %s' % (event_name, found[1]))
            return found[1]
        default_name = {EV_CONSTRUCTION: 'ConstructionEvent', EV_FORWARDS: 'ForwardsSolve'}[event_name]
        return self.node(struct, name or default_name, pos)

    # ---- checks ----
    def probe(self, struct_path, tmp_name='BW_Probe'):
        """Adds a throw-away node, returns (resolved struct name, pins), removes the node."""
        self.remove(tmp_name)
        name = self.node(struct_path, tmp_name, unreal.Vector2D(-3000.0, -3000.0))
        try:
            return self.struct_of(name), self.pins(name)
        finally:
            self.remove(name)

    def verify_struct(self, name, struct_short):
        got = self.struct_of(name)
        if got != struct_short:
            raise BwError('node %s resolved to %s, expected %s (a template node re-resolved after a link of the '
                          'wrong type?)' % (name, got, struct_short))
        return True


class Chain(object):
    """Links mutable nodes in execution order (exec out of the previous node -> exec in of the next)."""

    def __init__(self, graph, start, out_pin=None):
        self.gr = graph
        self.last = start
        self.out_pin = out_pin

    def add(self, node_name, out_pin=None):
        self.gr.link(self.gr.exec_out(self.last, self.out_pin), self.gr.exec_in(node_name))
        self.last = node_name
        self.out_pin = out_pin
        return node_name


def check_struct_paths(paths=None):
    """PASS/FAIL per struct path (load_object on /Script/... paths)."""
    paths = list(paths) if paths is not None else list(S.values())
    res = {}
    for p in paths:
        if p in RECIPE_RENAMES:
            fail('%s does not exist in 5.8 -> use %s' % (p, RECIPE_RENAMES[p]))
            res[p] = False
            continue
        try:
            o = unreal.load_object(None, p)
        except Exception:  # noqa: BLE001
            o = None
        res[p] = o is not None
        if o is None:
            fail('struct %s not found (plugin disabled or name wrong)' % p)
        elif p in DEPRECATED:
            warn('struct %s exists but is %s' % (p, DEPRECATED[p]))
        else:
            passed('struct %s' % p)
    return res


def verify_core_pins(rig, specs=None):
    """Probes each core struct in the rig's main graph and compares pins with CORE_PIN_SPECS. Events that already
    exist are checked on the existing node instead of a probe."""
    gr = RigGraph(rig)
    d = gr._dirs
    specs = specs if specs is not None else CORE_PIN_SPECS
    all_ok = True
    for path, spec in specs.items():
        short = path.rsplit('.', 1)[1]
        try:
            ev = {S['PrepareForExecution']: EV_CONSTRUCTION, S['BeginExecution']: EV_FORWARDS}.get(path)
            found = gr.find_event(ev, all_graphs=False) if ev else None
            if found:
                pins = gr.pins(found[1])
                got_struct = gr.struct_of(found[1])
            else:
                got_struct, pins = gr.probe(path)
        except BwError as e:
            fail('%s: %s' % (short, e))
            all_ok = False
            continue
        by = dict((p['name'], p) for p in pins)
        ok = got_struct == short
        if not ok:
            fail('%s: node resolved to %s' % (short, got_struct))
        for pname, cpp, dkey, is_exec in spec:
            p = by.get(pname)
            if p is None:
                fail('%s: missing pin %s (has %s)' % (short, pname, sorted(by)))
                ok = False
                continue
            if cpp and cpp not in p['cpp']:
                fail('%s.%s: cpp type %s, expected *%s*' % (short, pname, p['cpp'], cpp))
                ok = False
            if p['dir'] != d[dkey]:
                fail('%s.%s: direction %s, expected %s' % (short, pname, p['dir'], dkey))
                ok = False
            if bool(p['exec']) != bool(is_exec):
                fail('%s.%s: is_execute_context %s, expected %s' % (short, pname, p['exec'], is_exec))
                ok = False
        if ok:
            passed('%s pins: %s' % (short, ', '.join('%s:%s' % (p['name'], p['cpp']) for p in pins)))
        all_ok = all_ok and ok
    return all_ok


def core_audit(rig=None, extra_paths=None):
    """The recipe's Step 3 check for the core structs: struct paths, then pins probed in the rig's main graph
    (probe nodes are removed again; the rig is not saved). extra_paths: e.g. the recipe's VERIFIED Physics/Dynamics
    list. Without a rig only the paths are checked."""
    paths = list(S.values()) + list(RECIPE_RENAMES.keys()) + list(DEPRECATED.keys()) + list(extra_paths or [])
    res = check_struct_paths(paths)
    ok = all(v for k, v in res.items() if k not in RECIPE_RENAMES)
    if rig is None:
        rig = load_asset(RIG_PATH, unreal.ControlRigBlueprint)
    if rig is None:
        warn('no rig at %s: pin probes skipped (create it with get_or_create_rig() first)' % RIG_PATH)
        return ok
    return verify_core_pins(rig) and ok


# --------------------------------------------------------------------------------------------------------------------
# Hierarchy (rest pose)
# --------------------------------------------------------------------------------------------------------------------

def bone_key(name):
    return unreal.RigElementKey(type=unreal.RigElementType.BONE, name=name)   # RigHierarchyDefines.h:1762-1774


def rig_hierarchy(obj):
    """URigHierarchy of a ControlRigBlueprint (property 'hierarchy', ControlRigBlueprintLegacy.h:244-245) or of a
    UControlRig instance (get_hierarchy)."""
    if isinstance(obj, unreal.ControlRig):
        return obj.get_hierarchy()
    h = None
    try:
        h = obj.get_editor_property('hierarchy')
    except Exception:  # noqa: BLE001
        h = None
    if h is None:
        h = obj.get_hierarchy()          # interface UFUNCTION (ControlRigEditorAsset.h:61-62)
    if h is None:
        raise BwError('no hierarchy on %s' % obj.get_name())
    return h


def bone_names(obj):
    h = rig_hierarchy(obj)
    return [str(k.get_editor_property('name')) for k in h.get_bones(True)]   # ScriptName GetBones (RigHierarchy.h:1143-1144)


def global_tf(obj, bone_name, initial=True):
    """Global (= component space) transform; initial=True is the rest/ref pose (RigHierarchy.h:2276-2277)."""
    h = rig_hierarchy(obj)
    k = bone_key(bone_name)
    if not h.contains(k):                # ScriptName Contains (RigHierarchy.h:400-401)
        raise BwError('bone %s not in hierarchy' % bone_name)
    return h.get_global_transform(k, initial)


def local_tf(obj, bone_name, initial=True):
    h = rig_hierarchy(obj)
    return h.get_local_transform(bone_key(bone_name), initial)     # RigHierarchy.h:2180-2181


def parent_of(obj, bone_name):
    k = rig_hierarchy(obj).get_first_parent(bone_key(bone_name))   # RigHierarchy.h:3455-3456
    return str(k.get_editor_property('name'))


def tf_pos(t):
    v = t.translation
    return [v.x, v.y, v.z]


def tf_quat(t):
    q = t.rotation
    return [q.x, q.y, q.z, q.w]


def comp_to_bone_local(obj, tm_comp, bone_name):
    """Component-space transform -> transform in the bone's rest frame (tm_comp * inverse(bone_rest_global))."""
    return unreal.MathLibrary.make_relative_transform(tm_comp, global_tf(obj, bone_name, True))   # KismetMathLibrary.h:4017-4018


def capsule_tm_along(axis_comp, centre_comp):
    """Component-space transform whose +Z points along axis_comp (capsule main axis), at centre_comp."""
    rot = unreal.MathLibrary.make_rot_from_z(axis_comp)                                          # KismetMathLibrary.h:2266-2268
    return unreal.Transform(location=centre_comp, rotation=rot, scale=unreal.Vector(1.0, 1.0, 1.0))


def rest_pose_report(obj, bones, expected=None, tol=5.0):
    """Prints INFO with the rest-pose global position of each bone; with expected {bone: (x, y, z)} also PASS/FAIL."""
    ok = True
    out = {}
    for b in bones:
        try:
            p = tf_pos(global_tf(obj, b, True))
        except BwError as e:
            fail(str(e))
            ok = False
            continue
        out[b] = p
        msg = '%s rest global (%.1f, %.1f, %.1f)' % (b, p[0], p[1], p[2])
        if expected and b in expected:
            e = expected[b]
            dist = sum((p[i] - e[i]) ** 2 for i in range(3)) ** 0.5
            if dist <= tol:
                passed('%s, expected (%.1f, %.1f, %.1f)' % (msg, e[0], e[1], e[2]))
            else:
                fail('%s, expected (%.1f, %.1f, %.1f), off by %.1f cm' % (msg, e[0], e[1], e[2], dist))
                ok = False
        else:
            info(msg)
    return ok, out


# --------------------------------------------------------------------------------------------------------------------
# Compile and save
# --------------------------------------------------------------------------------------------------------------------

def compile_rig(rig, set_auto_recompile=True):
    """Recompiles the VM and the blueprint. Errors/warnings from the RigVM compiler arrive as RuntimeError /
    RuntimeWarning (RigVMEditorAsset.cpp:2077-2136); the blueprint status is read afterwards (Blueprint.h:507-508,
    mapped from the RigVM asset status in RigVMBlueprintLegacy.cpp:260-271)."""
    errors = []
    if set_auto_recompile:
        try:
            rig.set_auto_vm_recompile(True)                             # RigVMBlueprintLegacy.h:276
        except Exception as e:  # noqa: BLE001
            warn('set_auto_vm_recompile: %s' % e)
    try:
        _ue('recompile_vm', rig.recompile_vm)                           # RigVMBlueprintLegacy.h:270
    except BwError as e:
        errors.append(str(e))
    try:
        _ue('BlueprintEditorLibrary.compile_blueprint', unreal.BlueprintEditorLibrary.compile_blueprint, rig)   # BlueprintEditorLibrary.h:200
    except BwError as e:
        errors.append(str(e))
    status = rig.get_editor_property('status')
    good = (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS)
    for e in errors:
        fail(e)
    if status in good and not errors:
        passed('compiled %s (status %s)' % (rig.get_name(), status))
        return True
    fail('compile %s: status %s, %d error(s). Open the rig, read the Compiler Results tab / Output Log (LogRigVM, '
         'LogControlRig) for the node named in the error.' % (rig.get_name(), status, len(errors)))
    return False


def save_rig(rig_path=RIG_PATH):
    _require_ours(rig_path)
    _require_no_pie('save_rig')
    ok = _ue('EditorAssetLibrary.save_asset(%s)' % rig_path, unreal.EditorAssetLibrary.save_asset, rig_path, False)
    (passed if ok else fail)('save %s' % rig_path)
    return bool(ok)


def describe_rig(rig):
    for name, v in sorted(member_variables(rig).items()):
        info('var %s : %s default %r' % (name, v.get_editor_property('cpp_type'), v.get_editor_property('default_value')))
    for m in root_models(rig):
        nodes = m.get_nodes()
        events = [str(n.get_event_name()) for n in nodes if n.is_event()]
        info('graph %s: %d nodes, %d links, events %s' % (m.get_name(), len(nodes), len(m.get_links()), events))


# --------------------------------------------------------------------------------------------------------------------
# Automated test without PIE
# --------------------------------------------------------------------------------------------------------------------

def make_test_instance(rig):
    """A UControlRig instance of the compiled rig, initialised from the CDO (hierarchy copied), moved to the transient
    package so it can never be saved into CR_Burrower's package.
    rig.create_control_rig(): ControlRigBlueprintLegacy.h:135-136 -> RecompileVMIfRequired + NewObject(outer = the
    blueprint) + Initialize(true) (RigVMEditorAsset.cpp:3154-3161, RigVMBlueprintLegacy.cpp:326-329)."""
    inst = _ue('create_control_rig', rig.create_control_rig)
    if inst is None:
        raise BwError('create_control_rig returned None (rig not compiled?)')
    tp = _transient_package()
    name = None
    for i in range(1000):
        cand = 'BW_CRTest_%d_%d' % (int(time.time() * 1000) % 100000000, i)
        if unreal.find_object(tp, cand) is None:   # renaming onto an existing name is Fatal (Obj.cpp:383)
            name = cand
            break
    if name is None:
        raise BwError('no free transient name for the test instance')
    # Side effect: Python's rename passes REN_None (PyWrapperObject.cpp:744), so UObject::Rename calls Modify(true),
    # which marks the OLD outer's package (CR_Burrower) dirty (Obj.cpp:399-414). Nothing is written to disk.
    try:
        if not inst.rename(name, tp):
            warn('rename of the test instance to the transient package returned False; do not save the rig while '
                 'this instance is alive')
    except Exception as e:  # noqa: BLE001
        warn('rename of the test instance failed (%s); do not save the rig while it is alive' % e)
    return inst


def run_rig_test(rig, bones=None, variables=None, frames=1, dt=1.0 / 60.0, reset_bones_each_frame=True,
                 out_name='cr_test', instance=None, run_construction=True):
    """Runs Construction once and Forwards Solve `frames` times on a test instance, reads bone transforms back,
    writes Saved/Burrower/<out_name>.json and returns the dict. Synchronous: no PIE and no ticks are needed.
    variables: dict {name: value} applied before Construction, or a callable frame -> dict applied before each frame.
    reset_bones_each_frame: resets bones to the rest pose before each Forwards Solve, like the AnimBP node feeding the
    reference pose (Transfer Input Pose) does every frame.
    No world: physics solvers still step, world collision is skipped (RigPhysicsSolver_WorldObjects.cpp:211)."""
    inst = instance if instance is not None else make_test_instance(rig)
    h = inst.get_hierarchy()                                            # ControlRig.h UFUNCTION GetHierarchy
    bones = list(bones) if bones else bone_names(inst)
    result = {'rig': rig.get_path_name(), 'frames': frames, 'dt': dt, 'construction_ok': None,
              'forwards_ok': [], 'variables': {}, 'bones': {}, 'errors': []}

    def apply_vars(vals):
        for k, v in (vals or {}).items():
            text = _fmt(v)
            ok = inst.set_variable_from_string(k, text)                 # RigVMHost.h:177-178, RigVMHost.cpp:583-593
            result['variables'][k] = text
            if not ok:
                warn('set_variable_from_string(%s, %s) returned False (unknown variable or bad text)' % (k, text))

    if variables is not None and not callable(variables):
        apply_vars(variables)
    elif callable(variables):
        apply_vars(variables(0))
    try:
        inst.set_absolute_and_delta_time(0.0, dt)                       # RigVMHost.h:85-86
        if run_construction:
            result['construction_ok'] = bool(_ue('execute(Construction)', inst.execute, EV_CONSTRUCTION))   # RigVMHost.h:217-218
        for f in range(int(frames)):
            if callable(variables) and f > 0:
                apply_vars(variables(f))
            if reset_bones_each_frame:
                h.reset_pose_to_initial(unreal.RigElementType.BONE)    # RigHierarchy.h:291-292
            inst.set_absolute_and_delta_time(f * dt, dt)
            ok = bool(_ue('execute(Forwards Solve) frame %d' % f, inst.execute, EV_FORWARDS))
            result['forwards_ok'].append(ok)
            if not ok:
                break
    except BwError as e:
        result['errors'].append(str(e))
        fail(str(e))
    for b in bones:
        k = bone_key(b)
        if not h.contains(k):
            result['errors'].append('missing bone %s' % b)
            continue
        cur = h.get_global_transform(k, False)
        ini = h.get_global_transform(k, True)
        loc = h.get_local_transform(k, False)
        result['bones'][b] = {'global_pos': tf_pos(cur), 'global_quat': tf_quat(cur),
                              'local_quat': tf_quat(loc), 'rest_pos': tf_pos(ini), 'rest_quat': tf_quat(ini)}
    if result['construction_ok'] is False:
        fail('Construction event returned False (VM failed to initialise: compile errors?)')
    if result['forwards_ok'] and not all(result['forwards_ok']):
        fail('Forwards Solve returned False')
    elif result['forwards_ok'] and not result['errors']:
        passed('ran Construction + %d Forwards Solve frame(s) on %s' % (len(result['forwards_ok']), inst.get_name()))
    write_json(out_name, result)
    return result


def quat_angle_deg(q1, q2):
    """Angle between two quaternions given as [x, y, z, w] lists (for test assertions)."""
    dot = abs(sum(a * b for a, b in zip(q1, q2)))
    dot = min(1.0, max(-1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def dist(p1, p2):
    return sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
