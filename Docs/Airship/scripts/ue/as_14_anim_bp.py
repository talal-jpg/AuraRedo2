# as_14_anim_bp.py -- ABP_Airship (CPP_NOTES.md section 2; research_control_rig.md 7d), the Burrower bw_05 route without
# pins: parent /Script/Aura.AirshipAnimInstance, target skeleton SKEL_Airship, preview mesh SK_Airship, multi-threaded
# update on, EventGraph empty, AnimGraph = Control Rig node (CR_Airship) -> Output Pose, Alpha 1, LOD threshold -1,
# bTransferInputPose on, Source unlinked (ref pose each frame). NO exposed rig-variable pins: UAirshipAnimInstance writes
# the RIG_CONTRACT 5 variables straight into the node's rig instance. (Fallback if that fails in PIE: expose + wire the
# pins like bw_05 + bw_05b_use_pin_ui.)
# Route (verified for ABP_Burrower in 5.8): AnimBlueprintFactory + AssetTools.create_asset; BlueprintGraphEditor
# create_node_from_name('Misc.|ControlRig', ..., AnimGraphNode_ControlRig); ToolsetLibrary.set_object_properties for the
# node struct (ControlRigAssetReference makes PostEditChangeProperty rebuild the node); BlueprintGraphPinLibrary links.
# Re-runnable (reuses ABP_Airship and repairs it). Saves only ABP_Airship. Closes its editor at the end.
# Run:  Docs/Airship/scripts/harness/inbox.sh 14 Docs/Airship/scripts/ue/as_14_anim_bp.py 300
import json, os, time, traceback  # unreal = inbox namespace

A14_DIR = '/Game/Assets/MyShip/Drivable'
A14_ABP = A14_DIR + '/ABP_Airship'
A14_SKEL = A14_DIR + '/SKEL_Airship'
A14_SKM = A14_DIR + '/SK_Airship'
A14_CR = A14_DIR + '/CR_Airship'
A14_PARENT = '/Script/Aura.AirshipAnimInstance'
A14_NODE_CLASS = '/Script/ControlRigDeveloper.AnimGraphNode_ControlRig'
A14_MENU = 'Misc.|ControlRig'
A14 = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def a14_out(tag, msg):
    A14[tag] = A14.get(tag, 0) + 1
    print('%s: %s' % (tag, msg))


def a14_ok(c, msg, bad='FAIL'):
    a14_out('PASS' if c else bad, msg)
    return bool(c)


def a14_path(o):
    try:
        return o.get_path_name()
    except Exception:
        return str(o)


def a14_cname(o):
    try:
        return o.get_class().get_name()
    except Exception:
        return '?'


def a14_pins(node, out=False):
    L = unreal.BlueprintEditorLibrary
    return list(L.list_output_pins(node) if out else L.list_input_pins(node))


def a14_pin(node, name, out=False):
    for p in a14_pins(node, out):
        if str(unreal.BlueprintGraphPinLibrary.get_pin_name(p)) == name:
            return p
    return None


def a14_linked_to(pin, node, pin_name):
    for q in unreal.BlueprintGraphPinLibrary.list_connected_pins(pin):
        if a14_path(unreal.BlueprintGraphPinLibrary.get_owning_node(q)) == a14_path(node) and \
                str(unreal.BlueprintGraphPinLibrary.get_pin_name(q)) == pin_name:
            return True
    return False


def a14_main():
    eal = unreal.EditorAssetLibrary
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        a14_out('FAIL', 'PIE running')
        return
    parent = unreal.load_class(None, A14_PARENT)
    if parent is None or not unreal.MathLibrary.class_is_child_of(parent, unreal.AnimInstance.static_class()):
        a14_out('FAIL', '%s not loaded (build the C++)' % A14_PARENT)
        return
    cdo = unreal.get_default_object(parent)
    try:
        a14_out('INFO', 'AirshipAnimInstance CDO: bWriteRigVariables=%s, NozzlePitchDeg_FL=%s' % (
            cdo.get_editor_property('bWriteRigVariables') if False else unreal.ToolsetLibrary.get_object_properties(
                cdo, ['bWriteRigVariables']), cdo.get_editor_property('NozzlePitchDeg_FL')))
    except Exception as e:
        a14_out('INFO', 'CDO read: %s' % e)
    skel, skm, cr = eal.load_asset(A14_SKEL), eal.load_asset(A14_SKM), eal.load_asset(A14_CR)
    if not isinstance(skel, unreal.Skeleton) or not isinstance(skm, unreal.SkeletalMesh) or cr is None:
        a14_out('FAIL', 'SKEL/SK/CR missing')
        return
    gen = unreal.BlueprintEditorLibrary.generated_class(cr)
    cr_ref = '(BlueprintRigClass="%s")' % a14_path(gen)
    a14_ok(cr.get_editor_property('status') in (unreal.BlueprintStatus.BS_UP_TO_DATE,
                                                unreal.BlueprintStatus.BS_UP_TO_DATE_WITH_WARNINGS),
           'CR_Airship compiled (%s), class %s' % (cr.get_editor_property('status'), a14_path(gen)))
    node_cls = unreal.load_class(None, A14_NODE_CLASS)

    bp = eal.load_asset(A14_ABP) if eal.does_asset_exist(A14_ABP) else None
    if bp is not None and not isinstance(bp, unreal.AnimBlueprint):
        a14_out('FAIL', '%s exists and is a %s' % (A14_ABP, a14_cname(bp)))
        return
    if bp is None:
        fac = unreal.AnimBlueprintFactory()
        fac.set_editor_property('parent_class', parent)
        fac.set_editor_property('target_skeleton', skel)
        fac.set_editor_property('preview_skeletal_mesh', skm)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset('ABP_Airship', A14_DIR, unreal.AnimBlueprint, fac)
        if not isinstance(bp, unreal.AnimBlueprint):
            a14_out('FAIL', 'create_asset ABP_Airship failed')
            return
        a14_out('INFO', 'created %s' % A14_ABP)
    else:
        a14_out('INFO', 'reusing %s' % A14_ABP)
    L = unreal.BlueprintEditorLibrary
    if a14_path(L.get_blueprint_parent_class(bp)) != a14_path(parent):
        L.reparent_blueprint(bp, parent)
    if a14_path(bp.get_editor_property('target_skeleton')) != a14_path(skel):
        bp.set_editor_property('target_skeleton', skel)
    if not bp.get_editor_property('use_multi_threaded_animation_update'):
        bp.set_editor_property('use_multi_threaded_animation_update', True)
    eg = L.find_event_graph(bp)
    if eg is not None:
        en = list(unreal.BlueprintGraphEditor.get_graph_editor(eg).list_all_nodes())
        if en:
            a14_out('INFO', 'removing %d EventGraph nodes (the C++ parent updates)' % len(en))
            unreal.BlueprintGraphEditor.get_graph_editor(eg).remove_nodes(en)
    g = L.find_graph(bp, 'AnimGraph')
    ge = unreal.BlueprintGraphEditor.get_graph_editor(g)
    nodes = list(ge.list_all_nodes())
    roots = [n for n in nodes if a14_cname(n) == 'AnimGraphNode_Root']
    crs = [n for n in nodes if a14_cname(n) == 'AnimGraphNode_ControlRig']
    other = [n for n in nodes if n not in roots and n not in crs]
    if len(roots) != 1:
        a14_out('FAIL', '%d Output Pose nodes' % len(roots))
        return
    root = roots[0]
    rp = a14_pin(root, 'Result')
    cr_node = None
    for n in crs:
        if a14_linked_to(rp, n, 'Pose'):
            cr_node = n
    if cr_node is None and crs:
        cr_node = crs[0]
    extra = [n for n in crs if n is not cr_node] + other
    if extra:
        a14_out('INFO', 'removing %d other AnimGraph node(s)' % len(extra))
        ge.remove_nodes(extra)
    rpos = L.get_node_pos(root)
    if cr_node is None:
        cr_node = ge.create_node_from_name(A14_MENU, unreal.Vector2D(rpos.x - 420.0, rpos.y), [], node_cls)
        if cr_node is None or a14_cname(cr_node) != 'AnimGraphNode_ControlRig':
            a14_out('FAIL', 'could not spawn the Control Rig node (%s)' % a14_cname(cr_node))
            return
        L.set_node_pos(cr_node, unreal.IntPoint(int(rpos.x) - 420, int(rpos.y)))
        a14_out('INFO', 'spawned Control Rig node %s' % cr_node.get_name())
    ns = cr_node.get_editor_property('node')
    reftxt = ns.get_editor_property('control_rig_asset_reference').export_text()
    if a14_path(gen) not in reftxt:
        ok = unreal.ToolsetLibrary.set_object_properties(cr_node, json.dumps({'Node': {'ControlRigAssetReference': cr_ref}}))
        a14_out('INFO' if ok else 'WARN', 'set ControlRigAssetReference -> %s' % ok)
    want = {'Alpha': 1.0, 'LODThreshold': -1, 'bTransferInputPose': True}
    unreal.ToolsetLibrary.set_object_properties(cr_node, json.dumps({'Node': want}))
    ap = a14_pin(cr_node, 'Alpha')
    if ap is not None and not list(unreal.BlueprintGraphPinLibrary.list_connected_pins(ap)):
        unreal.BlueprintGraphPinLibrary.set_pin_value(ap, '1.0')
    po = a14_pin(cr_node, 'Pose', out=True)
    if not a14_linked_to(rp, cr_node, 'Pose'):
        a14_ok(unreal.BlueprintGraphPinLibrary.try_create_connection(po, rp), 'connect Control Rig.Pose -> Output Pose.Result')

    # ---- report
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    ns = cr_node.get_editor_property('node')
    a14_ok(a14_path(L.get_blueprint_parent_class(bp)) == a14_path(parent), 'parent class %s' % a14_path(
        L.get_blueprint_parent_class(bp)))
    a14_ok(a14_path(bp.get_editor_property('target_skeleton')) == a14_path(skel), 'target skeleton %s' % a14_path(
        bp.get_editor_property('target_skeleton')))
    a14_ok(bp.get_editor_property('use_multi_threaded_animation_update'), 'multi-threaded animation update on')
    a14_ok(a14_path(gen) in ns.get_editor_property('control_rig_asset_reference').export_text(),
           'Control Rig class %s' % ns.get_editor_property('control_rig_asset_reference').export_text())
    a14_ok(abs(ns.get_editor_property('alpha') - 1.0) < 1e-6, 'Node.Alpha %s' % ns.get_editor_property('alpha'))
    a14_ok(int(ns.get_editor_property('lod_threshold')) == -1, 'LOD threshold %s' % ns.get_editor_property('lod_threshold'))
    a14_ok(bool(ns.get_editor_property('transfer_input_pose')), 'bTransferInputPose %s' % ns.get_editor_property(
        'transfer_input_pose'))
    a14_ok(a14_linked_to(a14_pin(root, 'Result'), cr_node, 'Pose'), 'Control Rig.Pose -> Output Pose.Result')
    sp = a14_pin(cr_node, 'Source')
    a14_ok(sp is None or not list(unreal.BlueprintGraphPinLibrary.list_connected_pins(sp)), 'Source unlinked (ref pose)')
    ins = [str(unreal.BlueprintGraphPinLibrary.get_pin_name(p)) for p in a14_pins(cr_node)]
    a14_ok(set(ins) <= {'Source', 'Alpha'}, 'no exposed rig-variable pins (input pins: %s)' % ins)
    nodes = list(ge.list_all_nodes())
    a14_ok(len(nodes) == 2, 'AnimGraph nodes: %s' % [(a14_cname(n), L.get_node_title(n)) for n in nodes])
    en = list(unreal.BlueprintGraphEditor.get_graph_editor(eg).list_all_nodes()) if eg else []
    a14_ok(not en, 'EventGraph empty', 'WARN')
    try:
        tags = unreal.EditorAssetLibrary.get_tag_values(A14_ABP)
        pm = [str(tags[k]) for k in tags if str(k) == 'PreviewSkeletalMesh']
        a14_ok(pm and 'SK_Airship' in pm[0], 'preview mesh tag %s' % pm, 'WARN')
    except Exception as e:
        a14_out('WARN', 'preview tag: %s' % e)
    st = bp.get_editor_property('status')
    for gg in (g, eg):
        if gg is None:
            continue
        gge = unreal.BlueprintGraphEditor.get_graph_editor(gg)
        for n in list(gge.list_nodes_with_errors()):
            a14_out('FAIL', 'compile error on %s: %s' % (L.get_node_title(n), n.get_editor_property('error_msg')))
        for n in list(gge.list_nodes_with_warnings()):
            a14_out('WARN', 'compile warning on %s: %s' % (L.get_node_title(n), n.get_editor_property('error_msg')))
    a14_ok(st == unreal.BlueprintStatus.BS_UP_TO_DATE, 'ABP_Airship compile status %s' % st,
           'FAIL' if st == unreal.BlueprintStatus.BS_ERROR else 'WARN')
    if st != unreal.BlueprintStatus.BS_ERROR:
        a14_ok(eal.save_asset(A14_ABP, only_if_is_dirty=False), 'saved %s' % A14_ABP)
    try:
        n = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(bp)
        a14_out('INFO', 'closed %s asset editor(s) of ABP_Airship' % n)
    except Exception as e:
        a14_out('WARN', 'close editors: %s' % e)


try:
    a14_main()
except Exception:
    a14_out('FAIL', traceback.format_exc())
print('RESULT: %s %s' % ('PASS' if not A14['FAIL'] else 'FAIL', A14))
