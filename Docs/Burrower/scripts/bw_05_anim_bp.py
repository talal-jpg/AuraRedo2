# bw_05_anim_bp.py -- ABP_Burrower (EDITOR_SESSION.md step 5, control_rig_recipe.md Step 6), UE 5.8.
#
# What it builds (all in /Game/Assets/Enemies/Burrower/, only ABP_Burrower is saved):
#   ABP_Burrower: parent /Script/Aura.BurrowerAnimInstance, target skeleton SKEL_Burrower, preview mesh SK_Burrower,
#   multi-threaded update on, EventGraph empty, AnimGraph = Control Rig node (CR_Burrower) -> Output Pose,
#   Alpha 1, LOD threshold -1, bTransferInputPose on, plus one "Get <property>" node per rig variable, wired to the
#   Control Rig node's pin of the same name as soon as that pin exists.
#
# Route (all verified in the 5.8 source, see the report of the agent that wrote this):
#   * AnimBlueprintFactory(parent_class, target_skeleton, preview_skeletal_mesh) + AssetTools.create_asset.
#   * Nodes: unreal.BlueprintGraphEditor (BlueprintEditorLibrary module, used by the EditorToolset blueprint
#     toolsets). create_node_from_name('Misc.|ControlRig', ..., declaring_class=AnimGraphNode_ControlRig) invokes the
#     Blueprint action database spawner of the anim node in the AnimGraph; add_get_member_variable_node makes the
#     getters; BlueprintGraphPinLibrary.try_create_connection links pins (Pose -> Output Pose.Result, getters -> pins).
#   * Node settings: unreal.ToolsetLibrary.set_object_properties(node, '{"Node": {...}}'). The JSON string for
#     ControlRigAssetReference makes that struct the edited leaf, so UAnimGraphNode_ControlRig::PostEditChangeProperty
#     rebuilds the exposable variables and reconstructs the node, exactly like picking the class in the details panel.
#   * NOT scriptable in stock 5.8: exposing a rig variable as a pin. The flag lives in
#     UAnimGraphNode_CustomProperty::CustomPinProperties[i].bShowPin, a plain UPROPERTY() (no CPF_Edit), so
#     set_editor_property and ToolsetLibrary refuse it, the console "set" command is disabled in the editor
#     (UUnrealEdEngine::Exec), and the only writer is the details panel's "Use Pin" checkbox. FAnimNode_ControlRig's
#     InputMapping / OutputMapping are curve mappings (rig variable <- anim curve, float only), not property bindings,
#     so they cannot replace the pins. -> The script prints the few clicks (tick "Use Pin" x9), and a re-run then
#     wires the getters, compiles and saves.
#
# Run (inbox harness in the clone's editor, nothing else needs frames, so no state machine):
#   Docs/Burrower/scripts/harness/inbox.sh 05 Docs/Burrower/scripts/bw_05_anim_bp.py 300
# Check only (changes nothing, still compiles in memory to report errors): send a 2-line wrapper:
#   BW05_CHECK_ONLY = True
#   exec(open('/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/bw_05_anim_bp.py').read())
# Delete and recreate ABP_Burrower (loses the "Use Pin" ticks; force delete nulls in-memory references to it, e.g.
# BP_Burrower's Anim Class): same wrapper with BW05_RECREATE = True.
#
# Re-runnable: an existing ABP_Burrower is reused and repaired (parent, skeleton, node, settings, links); an existing
# Control Rig node keeps its exposed pins; existing getters are reused.
# Output lines start with PASS: / FAIL: / WARN: / INFO:, the last one with RESULT:. A summary is written to
# <project>/Saved/Burrower/bw_05_anim_bp.json.

import json
import os
import time

import unreal

CHECK_ONLY = False
RECREATE = False

_bw05_g = globals()
if 'BW05_CHECK_ONLY' in _bw05_g:
    CHECK_ONLY = bool(_bw05_g.pop('BW05_CHECK_ONLY'))
if 'BW05_RECREATE' in _bw05_g:
    RECREATE = bool(_bw05_g.pop('BW05_RECREATE'))

BW05_DIR = '/Game/Assets/Enemies/Burrower'
BW05_ABP_NAME = 'ABP_Burrower'
BW05_ABP = BW05_DIR + '/' + BW05_ABP_NAME
BW05_SKEL = BW05_DIR + '/SKEL_Burrower'
BW05_SKM = BW05_DIR + '/SK_Burrower'
BW05_CR = BW05_DIR + '/CR_Burrower'
BW05_PARENT = '/Script/Aura.BurrowerAnimInstance'
BW05_CRNODE_CLASS = '/Script/ControlRigDeveloper.AnimGraphNode_ControlRig'   # AnimGraphNode_ControlRig.h, ControlRigDeveloper
BW05_CRNODE_MENU = 'Misc.|ControlRig'   # UAnimGraphNode_Base::GetNodeCategory "Misc." | GetNodeTitle "Control Rig", spaces removed
# Rig variable name, expected kind. Names = UBurrowerAnimInstance properties = CR_Burrower public variables.
BW05_VARS = [
    ('RotorAngleDeg', 'float'),
    ('RotorSpinSpeed', 'float'),
    ('WaveTime', 'float'),
    ('WaveAmplitudeDeg', 'float'),
    ('WavePhasePerJointDeg', 'float'),
    ('WavePitchAmplitudeDeg', 'float'),
    ('Speed', 'float'),
    ('bIsDead', 'bool'),
    ('DeathTime', 'float'),
]

_bw05_counts = {'PASS': 0, 'FAIL': 0, 'WARN': 0}
_bw05_summary = {'check_only': CHECK_ONLY, 'time': time.strftime('%Y-%m-%d %H:%M:%S')}


def _bw05_out(tag, msg):
    if tag in _bw05_counts:
        _bw05_counts[tag] += 1
    print('%s: %s' % (tag, msg))


def _bw05_ok(cond, what, fail_tag='FAIL'):
    _bw05_out('PASS' if cond else fail_tag, what)
    return bool(cond)


def _bw05_cname(o):
    try:
        return o.get_class().get_name()
    except Exception:
        return '?'


def _bw05_path(o):
    try:
        return o.get_path_name()
    except Exception:
        return str(o)


# ---------------------------------------------------------------- pins / nodes (BlueprintEditorLibrary, BlueprintGraphPinLibrary)

def _bw05_pin_name(p):
    return str(unreal.BlueprintGraphPinLibrary.get_pin_name(p))


def _bw05_pins(node, out=False):
    try:
        if out:
            return list(unreal.BlueprintEditorLibrary.list_output_pins(node))
        return list(unreal.BlueprintEditorLibrary.list_input_pins(node))
    except Exception as e:
        _bw05_out('WARN', 'listing pins of %s failed: %r' % (_bw05_path(node), e))
        return []


def _bw05_find_pin(node, name, out=False):
    # List and match by name (FindInputPin logs a warning for every miss).
    pins = _bw05_pins(node, out)
    for p in pins:
        if _bw05_pin_name(p) == name:
            return p
    for p in pins:
        if _bw05_pin_name(p).lower() == name.lower():
            return p
    return None


def _bw05_links(pin):
    try:
        return list(unreal.BlueprintGraphPinLibrary.list_connected_pins(pin))
    except Exception:
        return []


def _bw05_linked_to(pin, node, pin_name):
    np = _bw05_path(node)
    for q in _bw05_links(pin):
        try:
            if _bw05_path(unreal.BlueprintGraphPinLibrary.get_owning_node(q)) == np and _bw05_pin_name(q) == pin_name:
                return True
        except Exception:
            pass
    return False


def _bw05_connect(a, b, what):
    try:
        ok = unreal.BlueprintGraphPinLibrary.try_create_connection(a, b)
    except Exception as e:
        _bw05_out('FAIL', 'connect %s raised %r' % (what, e))
        return False
    if not ok:
        try:
            can = unreal.BlueprintGraphPinLibrary.can_create_connection(a, b)
        except Exception:
            can = '?'
        _bw05_out('FAIL', 'connect %s refused (can_create_connection=%s). Hint: connect it by hand in the AnimGraph.' % (what, can))
    return bool(ok)


def _bw05_pos(node):
    try:
        p = unreal.BlueprintEditorLibrary.get_node_pos(node)
        return int(p.x), int(p.y)
    except Exception:
        return 0, 0


def _bw05_set_pos(node, x, y):
    try:
        unreal.BlueprintEditorLibrary.set_node_pos(node, unreal.IntPoint(int(x), int(y)))
    except Exception as e:
        _bw05_out('WARN', 'set_node_pos failed on %s: %r' % (_bw05_path(node), e))


def _bw05_title(node):
    try:
        return unreal.BlueprintEditorLibrary.get_node_title(node)
    except Exception:
        return _bw05_cname(node)


def _bw05_graph_editor(graph):
    ge = unreal.BlueprintGraphEditor.get_graph_editor(graph)
    if ge is None:
        raise RuntimeError('BlueprintGraphEditor.get_graph_editor returned None for %s' % _bw05_path(graph))
    return ge


def _bw05_nodes(graph):
    try:
        return list(_bw05_graph_editor(graph).list_all_nodes())
    except Exception as e:
        _bw05_out('WARN', 'list_all_nodes failed on %s: %r' % (_bw05_path(graph), e))
        return []


# ---------------------------------------------------------------- control rig node settings (ToolsetLibrary + node struct)

def _bw05_node_struct(cr_node):
    # FAnimNode_ControlRig is exported to Python (AnimNode_ControlRig); its fields are EditAnywhere.
    try:
        return cr_node.get_editor_property('node')
    except Exception as e:
        _bw05_out('WARN', 'reading the node struct failed: %r' % (e,))
        return None


def _bw05_node_field(ns, name, default=None):
    try:
        return ns.get_editor_property(name)
    except Exception:
        return default


def _bw05_ref_text(ns):
    ref = _bw05_node_field(ns, 'control_rig_asset_reference')
    if ref is None:
        return ''
    try:
        return ref.export_text()
    except Exception:
        return str(ref)


def _bw05_set_props(obj, data, what):
    # WARN only: the values are read back afterwards and those checks are the PASS/FAIL.
    s = json.dumps(data)
    try:
        ok = unreal.ToolsetLibrary.set_object_properties(obj, s)
    except Exception as e:
        _bw05_out('WARN', '%s: ToolsetLibrary.set_object_properties raised %r (json %s)' % (what, e, s))
        return False
    if not ok:
        _bw05_out('WARN', '%s: ToolsetLibrary.set_object_properties returned False (json %s); see the Output Log for the property it refused' % (what, s))
    return bool(ok)


# ---------------------------------------------------------------- dependencies

def _bw05_load_deps():
    d = {}
    try:
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les is not None and les.is_in_play_in_editor():
            _bw05_out('FAIL', 'PIE is running: stop Play first (assets cannot be saved during PIE). Nothing was changed.')
            return None
    except Exception as e:
        _bw05_out('WARN', 'could not query PIE state: %r' % (e,))

    for nm in ('BlueprintGraphEditor', 'BlueprintGraphPinLibrary', 'BlueprintEditorLibrary', 'ToolsetLibrary'):
        if not hasattr(unreal, nm):
            if nm != 'ToolsetLibrary':
                try:
                    unreal.load_module('BlueprintEditorLibrary')
                except Exception:
                    pass
            if not hasattr(unreal, nm):
                _bw05_out('FAIL', 'unreal.%s is missing (BlueprintEditorLibrary module / ToolsetRegistry plugin of AllToolsets not loaded?)' % nm)
                return None

    parent = None
    try:
        parent = unreal.load_class(None, BW05_PARENT)
    except Exception as e:
        _bw05_out('INFO', 'load_class(%s) raised %r' % (BW05_PARENT, e))
    if parent is None or not unreal.MathLibrary.class_is_child_of(parent, unreal.AnimInstance.static_class()):
        _bw05_out('FAIL', '%s not found or not an AnimInstance: build AuraEditor with the Burrower C++ and restart the editor' % BW05_PARENT)
        return None
    d['parent'] = parent
    cdo = unreal.get_default_object(parent)
    missing = []
    for v, _k in BW05_VARS:
        try:
            cdo.get_editor_property(v)
        except Exception:
            missing.append(v)
    if not _bw05_ok(not missing, 'BurrowerAnimInstance has the 9 properties%s' % ((' (missing: %s)' % missing) if missing else '')):
        return None

    skel = unreal.EditorAssetLibrary.load_asset(BW05_SKEL) if unreal.EditorAssetLibrary.does_asset_exist(BW05_SKEL) else None
    if not isinstance(skel, unreal.Skeleton):
        _bw05_out('FAIL', '%s missing or not a Skeleton: run the FBX import step (bw_02) first' % BW05_SKEL)
        return None
    d['skel'] = skel
    skm = unreal.EditorAssetLibrary.load_asset(BW05_SKM) if unreal.EditorAssetLibrary.does_asset_exist(BW05_SKM) else None
    if not isinstance(skm, unreal.SkeletalMesh):
        _bw05_out('FAIL', '%s missing or not a SkeletalMesh: run the FBX import step first' % BW05_SKM)
        return None
    d['skm'] = skm
    try:
        ms = skm.get_editor_property('skeleton')
        _bw05_ok(ms is not None and _bw05_path(ms) == _bw05_path(skel), 'SK_Burrower uses SKEL_Burrower (%s)' % _bw05_path(ms), 'WARN')
    except Exception as e:
        _bw05_out('WARN', 'could not read SK_Burrower.skeleton: %r' % (e,))

    cr = unreal.EditorAssetLibrary.load_asset(BW05_CR) if unreal.EditorAssetLibrary.does_asset_exist(BW05_CR) else None
    if cr is None:
        _bw05_out('FAIL', '%s missing: run the Control Rig step (bw_04) first' % BW05_CR)
        return None
    d['cr'] = cr
    # 5.8 has two Control Rig asset kinds; FControlRigAssetStrongReference has one field for each.
    if isinstance(cr, unreal.Blueprint):
        gen = unreal.BlueprintEditorLibrary.generated_class(cr)
        if gen is None:
            _bw05_out('FAIL', 'CR_Burrower (Control Rig Blueprint) has no generated class: compile it in the rig editor')
            return None
        d['cr_kind'] = 'blueprint'
        d['cr_ref'] = '(BlueprintRigClass="%s")' % _bw05_path(gen)
        d['cr_key'] = _bw05_path(gen)
        try:
            st = cr.get_editor_property('status')
            _bw05_ok(st in (unreal.BlueprintStatus.BS_UP_TO_DATE, unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS),
                     'CR_Burrower compiled (status %s)' % st, 'WARN')
        except Exception:
            pass
    elif 'ControlRigRuntimeAsset' in _bw05_cname(cr):
        d['cr_kind'] = 'runtime_asset'
        d['cr_ref'] = '(ControlRigAsset="%s")' % _bw05_path(cr)
        d['cr_key'] = _bw05_path(cr)
    else:
        _bw05_out('FAIL', 'CR_Burrower is a %s, expected ControlRigBlueprint or ControlRigRuntimeAsset' % _bw05_cname(cr))
        return None
    _bw05_out('INFO', 'CR_Burrower kind %s, reference text %s' % (d['cr_kind'], d['cr_ref']))

    # Rig variables: public ones become exposable inputs of the AnimGraph node (FControlRigIOMapping::GetVariables).
    descs = None
    for fn in ('get_member_variables', 'get_asset_variables'):
        f = getattr(cr, fn, None)
        if f is not None:
            try:
                descs = list(f())
                break
            except Exception:
                descs = None
    rig = {}
    if descs is None:
        _bw05_out('WARN', 'could not list CR_Burrower variables (get_member_variables / get_asset_variables)')
    else:
        for de in descs:
            try:
                rig[str(de.get_editor_property('name'))] = (str(de.get_editor_property('cpp_type')), bool(de.get_editor_property('public')))
            except Exception:
                pass
        for v, kind in BW05_VARS:
            if v not in rig:
                _bw05_out('FAIL', 'CR_Burrower has no variable %s (names must match the anim instance properties)' % v)
            else:
                cpp, pub = rig[v]
                okt = (cpp == 'bool') if kind == 'bool' else (cpp in ('float', 'double'))
                _bw05_ok(pub and okt, 'rig variable %s: type %s, public %s' % (v, cpp, pub))
    d['rig_vars'] = rig
    d['node_cls'] = None
    try:
        d['node_cls'] = unreal.load_class(None, BW05_CRNODE_CLASS)
    except Exception:
        pass
    if d['node_cls'] is None:
        _bw05_out('FAIL', '%s not found (ControlRig plugin editor modules not loaded?)' % BW05_CRNODE_CLASS)
        return None
    return d


# ---------------------------------------------------------------- the anim blueprint

def _bw05_get_or_create_abp(d):
    exists = unreal.EditorAssetLibrary.does_asset_exist(BW05_ABP)
    bp = unreal.EditorAssetLibrary.load_asset(BW05_ABP) if exists else None
    if exists and (RECREATE or not isinstance(bp, unreal.AnimBlueprint)):
        why = 'RECREATE=True' if RECREATE else ('existing asset is a %s, not an AnimBlueprint' % _bw05_cname(bp))
        if not RECREATE:
            _bw05_out('FAIL', '%s exists but %s. Re-run with BW05_RECREATE = True to delete and recreate it.' % (BW05_ABP, why))
            return None
        _bw05_out('INFO', 'deleting our own %s (%s)' % (BW05_ABP, why))
        if not unreal.EditorAssetLibrary.delete_asset(BW05_ABP):
            _bw05_out('FAIL', 'delete_asset(%s) failed (open in an editor? referenced?)' % BW05_ABP)
            return None
        bp, exists = None, False
    if bp is not None:
        _bw05_out('INFO', 'reusing existing %s' % BW05_ABP)
        return bp
    try:
        fac = unreal.AnimBlueprintFactory()
    except Exception:
        fac = unreal.new_object(unreal.load_class(None, '/Script/UnrealEd.AnimBlueprintFactory'))
    fac.set_editor_property('parent_class', d['parent'])
    fac.set_editor_property('target_skeleton', d['skel'])
    fac.set_editor_property('preview_skeletal_mesh', d['skm'])
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(BW05_ABP_NAME, BW05_DIR, unreal.AnimBlueprint, fac)
    if not isinstance(bp, unreal.AnimBlueprint):
        _bw05_out('FAIL', 'create_asset(%s) failed' % BW05_ABP)
        return None
    _bw05_out('INFO', 'created %s' % BW05_ABP)
    return bp


def _bw05_fix_class_settings(bp, d):
    par = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
    if _bw05_path(par) != _bw05_path(d['parent']):
        _bw05_out('INFO', 'reparenting %s from %s to BurrowerAnimInstance' % (BW05_ABP, _bw05_path(par)))
        unreal.BlueprintEditorLibrary.reparent_blueprint(bp, d['parent'])
    sk = bp.get_editor_property('target_skeleton')
    if _bw05_path(sk) != _bw05_path(d['skel']):
        _bw05_out('INFO', 'setting target skeleton (was %s)' % _bw05_path(sk))
        bp.set_editor_property('target_skeleton', d['skel'])
    if not bp.get_editor_property('use_multi_threaded_animation_update'):
        bp.set_editor_property('use_multi_threaded_animation_update', True)


def _bw05_anim_graph(bp):
    g = None
    try:
        g = unreal.BlueprintEditorLibrary.find_graph(bp, 'AnimGraph')   # UEdGraphSchema_K2::GN_AnimGraph
    except Exception:
        g = None
    if g is None:
        for gg in unreal.BlueprintEditorLibrary.list_graphs(bp):
            if _bw05_cname(gg) == 'AnimationGraph' and gg.get_name() == 'AnimGraph':
                g = gg
    return g


def _bw05_classify(nodes):
    roots, crs, getters, other = [], [], {}, []
    for n in nodes:
        c = _bw05_cname(n)
        if c == 'AnimGraphNode_Root':
            roots.append(n)
        elif c == 'AnimGraphNode_ControlRig':
            crs.append(n)
        elif c == 'K2Node_VariableGet':
            outs = _bw05_pins(n, out=True)
            nm = _bw05_pin_name(outs[0]) if outs else ''
            if nm in dict(BW05_VARS):
                getters.setdefault(nm, []).append(n)
            else:
                other.append(n)
        else:
            other.append(n)
    return roots, crs, getters, other


def _bw05_create_cr_node(ge, d, x, y):
    loc = unreal.Vector2D(float(x), float(y))
    try:
        n = ge.create_node_from_name(BW05_CRNODE_MENU, loc, [], d['node_cls'])
    except Exception as e:
        _bw05_out('WARN', 'create_node_from_name(%s) raised %r' % (BW05_CRNODE_MENU, e))
        n = None
    if n is None:
        # Fallback: look the action up by its title among everything the AnimGraph offers.
        try:
            names = [str(s) for s in ge.list_available_nodes([])]
        except Exception as e:
            names = []
            _bw05_out('WARN', 'list_available_nodes raised %r' % (e,))
        cands = [s for s in names if s.lower().endswith('|controlrig')]
        _bw05_out('INFO', 'AnimGraph actions ending in |ControlRig: %s' % cands)
        for s in cands:
            try:
                n = ge.create_node_from_name(s, loc, [], d['node_cls'])
            except Exception:
                n = None
            if n is not None:
                break
    if n is not None and _bw05_cname(n) != 'AnimGraphNode_ControlRig':
        _bw05_out('FAIL', 'spawned node is a %s, not AnimGraphNode_ControlRig' % _bw05_cname(n))
        return None
    return n


def _bw05_apply_node_settings(cr_node, d):
    ns = _bw05_node_struct(cr_node)
    if ns is None or d['cr_key'] not in _bw05_ref_text(ns):
        # Leaf = ControlRigAssetReference (JSON string -> ImportText) -> PostEditChangeProperty rebuilds + reconstructs.
        if not _bw05_set_props(cr_node, {'Node': {'ControlRigAssetReference': d['cr_ref']}}, 'set Control Rig class'):
            # Fallback: Python struct copy, then force a reconstruct through the AlphaInputType branch of
            # UAnimGraphNode_ControlRig::PostEditChangeProperty (CreateCustomPins rebuilds the exposable variables).
            try:
                ns = cr_node.get_editor_property('node')
                ref = unreal.ControlRigAssetStrongReference()
                if not ref.import_text(d['cr_ref']):
                    raise RuntimeError('import_text refused %s' % d['cr_ref'])
                ns.set_editor_property('control_rig_asset_reference', ref)
                cr_node.set_editor_property('node', ns)
                _bw05_set_props(cr_node, {'Node': {'AlphaInputType': 'Float'}}, 'force node reconstruct')
            except Exception as e:
                _bw05_out('FAIL', 'fallback class set failed: %r. By hand: select the Control Rig node, Details > Control Rig Class = CR_Burrower' % (e,))
        ns = _bw05_node_struct(cr_node)
    _bw05_ok(ns is not None and d['cr_key'] in _bw05_ref_text(ns), 'Control Rig node class = CR_Burrower (%s)' % (_bw05_ref_text(ns) if ns is not None else '?'))
    want = {}
    if ns is None or abs(float(_bw05_node_field(ns, 'alpha', 0.0)) - 1.0) > 1e-6:
        want['Alpha'] = 1.0
    if ns is None or int(_bw05_node_field(ns, 'lod_threshold', 0)) != -1:
        want['LODThreshold'] = -1
    if ns is None or not _bw05_node_field(ns, 'transfer_input_pose', False):
        want['bTransferInputPose'] = True
    if want:
        _bw05_set_props(cr_node, {'Node': want}, 'node settings %s' % sorted(want))
    # Alpha is a shown pin (PinShownByDefault): the compiled value comes from the pin default.
    ap = _bw05_find_pin(cr_node, 'Alpha')
    if ap is not None and not _bw05_links(ap):
        try:
            if str(unreal.BlueprintGraphPinLibrary.get_pin_value(ap)) not in ('1', '1.0', '1.000000'):
                unreal.BlueprintGraphPinLibrary.set_pin_value(ap, '1.0')
        except Exception as e:
            _bw05_out('WARN', 'setting the Alpha pin to 1.0 failed: %r' % (e,))


# ---------------------------------------------------------------- report (also the CHECK_ONLY mode)

def _bw05_report(bp, d, compile_now):
    st = {'abp': BW05_ABP}
    par = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(bp)
    _bw05_ok(_bw05_path(par) == _bw05_path(d['parent']), 'parent class = %s' % _bw05_path(par))
    sk = bp.get_editor_property('target_skeleton')
    _bw05_ok(_bw05_path(sk) == _bw05_path(d['skel']), 'target skeleton = %s' % _bw05_path(sk))
    try:
        tags = unreal.EditorAssetLibrary.get_tag_values(BW05_ABP)
        pm = ''
        for k in tags:
            if str(k) == 'PreviewSkeletalMesh':
                pm = str(tags[k])
        # Only the factory sets it from script (PreviewSkeletalMesh is not an editable property). Editor-only, the
        # game does not need it. By hand: ABP editor > Preview Scene Settings > Preview Mesh = SK_Burrower.
        _bw05_ok('SK_Burrower' in pm, 'preview mesh tag = %s' % (pm or '(none)'), 'WARN')
    except Exception as e:
        _bw05_out('WARN', 'could not read the PreviewSkeletalMesh tag: %r' % (e,))
    _bw05_ok(bool(bp.get_editor_property('use_multi_threaded_animation_update')), 'Use Multi-Threaded Animation Update on')

    eg = unreal.BlueprintEditorLibrary.find_event_graph(bp)
    en = _bw05_nodes(eg) if eg is not None else []
    _bw05_ok(not en, 'EventGraph empty%s' % ('' if not en else (' (has %s)' % [_bw05_title(n) for n in en])), 'WARN')

    g = _bw05_anim_graph(bp)
    if g is None:
        _bw05_out('FAIL', 'no AnimGraph in %s' % BW05_ABP)
        return st
    nodes = _bw05_nodes(g)
    for n in nodes:
        x, y = _bw05_pos(n)
        _bw05_out('INFO', 'AnimGraph node %s "%s" at (%d, %d) [%s]' % (_bw05_cname(n), _bw05_title(n), x, y, n.get_name()))
        for out in (False, True):
            for p in _bw05_pins(n, out):
                try:
                    ty = str(unreal.BlueprintGraphPinLibrary.get_pin_type_display_string(p))
                    val = str(unreal.BlueprintGraphPinLibrary.get_pin_value(p))
                except Exception:
                    ty, val = '?', ''
                lk = ['%s.%s' % (_bw05_title(unreal.BlueprintGraphPinLibrary.get_owning_node(q)), _bw05_pin_name(q)) for q in _bw05_links(p)]
                _bw05_out('INFO', '    %s %s [%s]%s%s' % ('out' if out else 'in ', _bw05_pin_name(p), ty,
                                                        (' = %r' % val) if (val and not out) else '',
                                                        (' %s %s' % ('->' if out else '<-', lk)) if lk else ''))
    roots, crs, getters, other = _bw05_classify(nodes)
    _bw05_ok(len(roots) == 1, 'one Output Pose node (%d)' % len(roots))
    _bw05_ok(len(crs) == 1, 'one Control Rig node (%d)' % len(crs))
    if other:
        _bw05_out('WARN', 'other AnimGraph nodes (spec says nothing else): %s' % [(_bw05_cname(n), _bw05_title(n)) for n in other])
    st['cr_nodes'] = len(crs)
    exposed, linked = [], []
    if roots and crs:
        root, cr_node = roots[0], crs[0]
        rp = _bw05_find_pin(root, 'Result')
        _bw05_ok(rp is not None and _bw05_linked_to(rp, cr_node, 'Pose'), 'Control Rig.Pose -> Output Pose.Result')
        sp = _bw05_find_pin(cr_node, 'Source')
        if sp is not None and _bw05_links(sp):
            _bw05_out('WARN', 'Control Rig.Source is linked (spec: leave it unlinked = reference pose)')
        ns = _bw05_node_struct(cr_node)
        if ns is not None:
            _bw05_ok(d['cr_key'] in _bw05_ref_text(ns), 'CR class %s' % _bw05_ref_text(ns))
            _bw05_ok(abs(float(_bw05_node_field(ns, 'alpha', 0.0)) - 1.0) < 1e-6, 'Node.Alpha = %s' % _bw05_node_field(ns, 'alpha'))
            _bw05_ok(int(_bw05_node_field(ns, 'lod_threshold', 0)) == -1, 'LOD threshold = %s' % _bw05_node_field(ns, 'lod_threshold'))
            _bw05_ok(bool(_bw05_node_field(ns, 'transfer_input_pose', False)), 'bTransferInputPose = %s' % _bw05_node_field(ns, 'transfer_input_pose'))
            _bw05_out('INFO', 'bResetInputPoseToInitial = %s, bTransferInputCurves = %s, AlphaInputType = %s' % (
                _bw05_node_field(ns, 'reset_input_pose_to_initial'), _bw05_node_field(ns, 'transfer_input_curves'),
                _bw05_node_field(ns, 'alpha_input_type')))
            # Node.InputMapping / OutputMapping (curve <-> rig variable) are UPROPERTY() only, read them via the
            # ToolsetLibrary JSON of the whole struct; they should be empty here.
            try:
                js = json.loads(unreal.ToolsetLibrary.get_object_properties(cr_node, ['Node'])).get('Node', {})
                low = dict((k.lower(), v) for k, v in js.items())
                _bw05_out('INFO', 'curve mappings InputMapping=%s OutputMapping=%s (empty = variables come from pins only)' % (
                    low.get('inputmapping'), low.get('outputmapping')))
            except Exception as e:
                _bw05_out('INFO', 'node JSON not readable: %r' % (e,))
        ap = _bw05_find_pin(cr_node, 'Alpha')
        if ap is not None:
            _bw05_ok(str(unreal.BlueprintGraphPinLibrary.get_pin_value(ap)) in ('1', '1.0', '1.000000') or bool(_bw05_links(ap)),
                     'Alpha pin = %s' % unreal.BlueprintGraphPinLibrary.get_pin_value(ap))
        for v, _k in BW05_VARS:
            p = _bw05_find_pin(cr_node, v)
            if p is None:
                _bw05_out('WARN', 'rig variable %s is not exposed as a pin yet (needs the "Use Pin" tick)' % v)
                continue
            exposed.append(v)
            gs = getters.get(v, [])
            ok = any(_bw05_linked_to(p, gn, v) for gn in gs)
            if ok:
                linked.append(v)
            _bw05_ok(ok, 'pin %s <- Get %s' % (v, v))
    st['exposed'] = exposed
    st['linked'] = linked

    if compile_now:
        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        except Exception as e:
            _bw05_out('FAIL', 'compile_blueprint raised %r' % (e,))
    status = bp.get_editor_property('status')
    st['status'] = str(status)
    if status == unreal.BlueprintStatus.BS_ERROR:
        _bw05_out('FAIL', 'ABP_Burrower compile status %s' % status)
    elif status == unreal.BlueprintStatus.BS_UP_TO_DATE:
        _bw05_out('PASS', 'ABP_Burrower compiles without errors or warnings')
    else:
        _bw05_out('WARN', 'ABP_Burrower compile status %s' % status)
    for gg in [g, eg]:
        if gg is None:
            continue
        try:
            ge = _bw05_graph_editor(gg)
            for n in list(ge.list_nodes_with_errors()):
                _bw05_out('FAIL', 'compile error on "%s": %s' % (_bw05_title(n), n.get_editor_property('error_msg')))
            for n in list(ge.list_nodes_with_warnings()):
                _bw05_out('WARN', 'compile warning on "%s": %s' % (_bw05_title(n), n.get_editor_property('error_msg')))
        except Exception as e:
            _bw05_out('INFO', 'node messages not readable: %r' % (e,))
    return st


BW05_MANUAL = [
    'Content Browser: double-click /Game/Assets/Enemies/Burrower/ABP_Burrower (AnimGraph tab opens).',
    'Click the "Control Rig" node (between the green Get nodes and Output Pose).',
    'Details panel, section "Input": tick "Use Pin" on each row: RotorAngleDeg, RotorSpinSpeed, WaveTime, '
    'WaveAmplitudeDeg, WavePhasePerJointDeg, WavePitchAmplitudeDeg, Speed, bIsDead, DeathTime (leave "Use Curve" empty).',
    'Ctrl+S in the ABP editor, then re-run bw_05_anim_bp.py: it wires the 9 Get nodes to the new pins, compiles and saves. '
    '(Or drag each Get node output onto the pin of the same name yourself, Compile, Save.)',
]


# ---------------------------------------------------------------- main

def _bw05_build(bp, d):
    _bw05_fix_class_settings(bp, d)

    eg = unreal.BlueprintEditorLibrary.find_event_graph(bp)
    if eg is not None:
        en = _bw05_nodes(eg)
        if en:
            _bw05_out('INFO', 'removing EventGraph nodes %s (the parent C++ class does the update)' % [_bw05_title(n) for n in en])
            _bw05_graph_editor(eg).remove_nodes(en)

    g = _bw05_anim_graph(bp)
    if g is None:
        _bw05_out('FAIL', 'no AnimGraph in %s' % BW05_ABP)
        return False
    ge = _bw05_graph_editor(g)
    roots, crs, getters, other = _bw05_classify(_bw05_nodes(g))
    if len(roots) != 1:
        _bw05_out('FAIL', 'expected one Output Pose node in AnimGraph, found %d' % len(roots))
        return False
    root = roots[0]
    rx, ry = _bw05_pos(root)
    rp = _bw05_find_pin(root, 'Result')

    # Control Rig node: keep the one feeding Output Pose (it carries the "Use Pin" ticks), drop unlinked extras.
    cr_node = None
    for n in crs:
        if rp is not None and _bw05_linked_to(rp, n, 'Pose'):
            cr_node = n
    if cr_node is None and crs:
        cr_node = crs[0]
    extra = [n for n in crs if n is not cr_node and _bw05_path(n) != _bw05_path(cr_node)]
    if extra:
        _bw05_out('INFO', 'removing %d extra Control Rig node(s)' % len(extra))
        ge.remove_nodes(extra)
    if cr_node is None:
        cr_node = _bw05_create_cr_node(ge, d, rx - 420, ry)
        if cr_node is None:
            _bw05_out('FAIL', 'could not spawn the Control Rig node from script')
            _bw05_out('INFO', 'MANUAL A. AnimGraph: right-click empty space, type "Control Rig", pick Misc. > Control Rig.')
            _bw05_out('INFO', 'MANUAL B. Details: Control Rig Class = CR_Burrower. Drag its output pose onto Output Pose "Result".')
            _bw05_out('INFO', 'MANUAL C. Re-run bw_05_anim_bp.py for the rest.')
            return False
        _bw05_out('INFO', 'spawned Control Rig node %s' % cr_node.get_name())
        _bw05_set_pos(cr_node, rx - 420, ry)
    _bw05_apply_node_settings(cr_node, d)

    po = _bw05_find_pin(cr_node, 'Pose', out=True)
    rp = _bw05_find_pin(root, 'Result')
    if po is None or rp is None:
        _bw05_out('FAIL', 'pose pins not found (Control Rig.Pose %s, Output Pose.Result %s)' % (po is not None, rp is not None))
    elif not _bw05_linked_to(rp, cr_node, 'Pose'):
        _bw05_connect(po, rp, 'Control Rig.Pose -> Output Pose.Result')

    # One getter per anim instance property (C++ parent members, fast-path in the AnimGraph).
    cx, cy = _bw05_pos(cr_node)
    for i, (v, _k) in enumerate(BW05_VARS):
        gs = getters.get(v, [])
        if len(gs) > 1:
            _bw05_out('WARN', '%d Get %s nodes, using the first' % (len(gs), v))
        gn = gs[0] if gs else None
        if gn is None:
            try:
                gn = ge.add_get_member_variable_node(v)
            except Exception as e:
                gn = None
                _bw05_out('WARN', 'add_get_member_variable_node(%s) raised %r' % (v, e))
            if gn is None:
                _bw05_out('FAIL', 'could not create Get %s (property not on the skeleton class? compile the ABP once)' % v)
                continue
            _bw05_set_pos(gn, cx - 380, cy - 40 + 56 * i)
            getters[v] = [gn]
        pin = _bw05_find_pin(cr_node, v)
        if pin is None:
            continue
        if _bw05_linked_to(pin, gn, v):
            continue
        if _bw05_links(pin):
            _bw05_out('WARN', 'pin %s is linked to something else, left as is' % v)
            continue
        outs = _bw05_pins(gn, out=True)
        if outs:
            _bw05_connect(outs[0], pin, 'Get %s -> Control Rig.%s' % (v, v))
    return True


def _bw05_main():
    _bw05_out('INFO', 'bw_05_anim_bp CHECK_ONLY=%s RECREATE=%s' % (CHECK_ONLY, RECREATE))
    _bw05_out('INFO', 'route: AnimBlueprintFactory + BlueprintGraphEditor (node spawn, getters, links) + ToolsetLibrary '
                      '(node settings); rig variable pins need the "Use Pin" tick by hand (CustomPinProperties is not '
                      'script-writable in 5.8), then a re-run wires them')
    d = _bw05_load_deps()
    if d is None:
        return 'FAILED'
    if CHECK_ONLY:
        if not unreal.EditorAssetLibrary.does_asset_exist(BW05_ABP):
            _bw05_out('FAIL', '%s does not exist yet: run without CHECK_ONLY' % BW05_ABP)
            return 'FAILED'
        bp = unreal.EditorAssetLibrary.load_asset(BW05_ABP)
        if not isinstance(bp, unreal.AnimBlueprint):
            _bw05_out('FAIL', '%s is a %s' % (BW05_ABP, _bw05_cname(bp)))
            return 'FAILED'
        st = _bw05_report(bp, d, compile_now=True)
    else:
        bp = _bw05_get_or_create_abp(d)
        if bp is None:
            return 'FAILED'
        try:
            built = _bw05_build(bp, d)
        except Exception as e:
            import traceback
            _bw05_out('FAIL', 'build raised %r\n%s' % (e, traceback.format_exc()))
            built = False
        st = _bw05_report(bp, d, compile_now=True)
        try:
            unreal.BlueprintEditorLibrary.refresh_open_editors_for_blueprint(bp)
        except Exception:
            pass
        if st.get('status') == str(unreal.BlueprintStatus.BS_ERROR):
            _bw05_out('FAIL', 'not saving %s: it does not compile (fix the errors above, then re-run)' % BW05_ABP)
        elif unreal.EditorAssetLibrary.save_asset(BW05_ABP, only_if_is_dirty=False):
            _bw05_out('PASS', 'saved %s' % BW05_ABP)
        else:
            _bw05_out('FAIL', 'save_asset(%s) failed' % BW05_ABP)
        if not built:
            _bw05_out('WARN', 'build step incomplete, see FAIL lines above')
    _bw05_summary.update(st)
    missing = [v for v, _k in BW05_VARS if v not in st.get('exposed', [])]
    if missing:
        _bw05_out('WARN', 'MANUAL step needed: %d rig variable pin(s) not exposed: %s' % (len(missing), missing))
        for i, s in enumerate(BW05_MANUAL):
            _bw05_out('INFO', 'MANUAL %d. %s' % (i + 1, s))
    if _bw05_counts['FAIL']:
        return 'FAILED'
    if missing:
        return 'NEEDS_MANUAL_PIN_EXPOSE'
    if len(st.get('linked', [])) != len(BW05_VARS):
        return 'INCOMPLETE'
    return 'COMPLETE'


try:
    _bw05_res = _bw05_main()
except Exception as _bw05_e:
    import traceback
    _bw05_out('FAIL', 'unhandled %r\n%s' % (_bw05_e, traceback.format_exc()))
    _bw05_res = 'FAILED'
_bw05_summary['result'] = _bw05_res
_bw05_summary['counts'] = dict(_bw05_counts)
try:
    _bw05_dir = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Burrower')
    os.makedirs(_bw05_dir, exist_ok=True)
    with open(os.path.join(_bw05_dir, 'bw_05_anim_bp.json'), 'w') as _bw05_f:
        json.dump(_bw05_summary, _bw05_f, indent=1, default=str)
except Exception as _bw05_e:
    _bw05_out('WARN', 'summary JSON not written: %r' % (_bw05_e,))
print('RESULT: %s (PASS %d, FAIL %d, WARN %d)' % (_bw05_res, _bw05_counts['PASS'], _bw05_counts['FAIL'], _bw05_counts['WARN']))
