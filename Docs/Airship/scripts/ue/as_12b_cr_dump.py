# as_12b_cr_dump.py - dumps CR_Airship (every node, pin, default, link, variable, event execution order) to
# Saved/Airship/cr_dump.json for the offline reviewer. Read-only: nothing is changed or saved.
# Run:  Docs/Airship/scripts/harness/inbox.sh 12b Docs/Airship/scripts/ue/as_12b_cr_dump.py 300
import json, os, time, traceback  # unreal = inbox namespace

def _as12b():
    import json, os, time
    RIG = '/Game/Assets/MyShip/Drivable/CR_Airship'
    rig = unreal.EditorAssetLibrary.load_asset(RIG)
    model = rig.get_default_model()
    D = unreal.RigVMPinDirection
    dname = {D.INPUT: 'in', D.OUTPUT: 'out', D.IO: 'io', D.VISIBLE: 'visible', D.HIDDEN: 'hidden'}

    def pin_rec(p, linked_paths):
        r = {'name': p.get_name(), 'cpp': p.get_cpp_type(), 'dir': dname.get(p.get_direction(), str(p.get_direction())),
             'default': p.get_default_value()}
        if p.is_execute_context():
            r['exec'] = True
        subs = list(p.get_sub_pins())
        # sub-pins only when something below them is linked (the parent default text already holds every field)
        kids = [pin_rec(s, linked_paths) for s in subs if any(lp.startswith(s.get_pin_path()) for lp in linked_paths)]
        if kids:
            r['sub_linked'] = kids
        return r

    links = []
    linked = set()
    for lk in model.get_links():
        s, t = lk.get_source_pin(), lk.get_target_pin()
        links.append([s.get_pin_path(), t.get_pin_path()])
        linked.add(s.get_pin_path())
        linked.add(t.get_pin_path())
    nodes = []
    for n in model.get_nodes():
        rec = {'name': n.get_name(), 'class': n.get_class().get_name(),
               'pos': [round(n.get_position().x), round(n.get_position().y)]}
        try:
            st = n.get_script_struct()
            rec['struct'] = st.get_path_name() if st else None
        except Exception:
            pass
        if isinstance(n, unreal.RigVMCommentNode):
            rec['comment'] = n.get_comment_text()
        if isinstance(n, unreal.RigVMVariableNode):
            rec['variable'] = str(n.get_variable_name())
            rec['getter'] = bool(n.is_getter())
        try:
            if n.is_event():
                rec['event'] = str(n.get_event_name())
        except Exception:
            pass
        rec['pins'] = [pin_rec(p, linked) for p in n.get_pins()]
        nodes.append(rec)
    # execution order per event: follow exec links depth-first (branch outputs in pin order)
    by_src = {}
    for s, t in links:
        by_src.setdefault(s.split('.', 1)[0], []).append((s, t))
    exec_pins = set()
    for n in model.get_nodes():
        for p in n.get_pins():
            if p.is_execute_context():
                exec_pins.add(p.get_pin_path())
    order = {}
    for n in nodes:
        if 'event' not in n:
            continue
        seq, seen = [], set()

        def walk(name, depth, via):
            if name in seen:
                return
            seen.add(name)
            seq.append(('  ' * depth) + name + ((' [' + via + ']') if via else ''))
            outs = [(s, t) for s, t in by_src.get(name, []) if s in exec_pins and t in exec_pins]
            branch = len(outs) > 1
            for s, t in outs:
                walk(t.split('.', 1)[0], depth + (1 if branch else 0), s.split('.', 1)[1] if branch else '')
        walk(n['name'], 0, '')
        order[n['event']] = seq
    vars_ = []
    for v in rig.get_member_variables():
        vars_.append({'name': str(v.get_editor_property('name')), 'cpp_type': str(v.get_editor_property('cpp_type')),
                      'public': bool(v.get_editor_property('public')),
                      'default': str(v.get_editor_property('default_value'))})
    hier = []
    h = rig.get_hierarchy()
    for k in h.get_bones(True):
        nm = str(k.get_editor_property('name'))
        t = h.get_global_transform(k, True)
        par = h.get_first_parent(k)
        hier.append({'bone': nm, 'parent': str(par.get_editor_property('name')),
                     'pos': [round(t.translation.x, 3), round(t.translation.y, 3), round(t.translation.z, 3)],
                     'quat': [round(t.rotation.x, 6), round(t.rotation.y, 6), round(t.rotation.z, 6), round(t.rotation.w, 6)]})
    counts = {}
    for n in nodes:
        k = (n.get('struct') or n['class']).rsplit('.', 1)[-1]
        counts[k] = counts.get(k, 0) + 1
    out = {'asset': RIG, 'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'status': str(rig.get_editor_property('status')),
           'graph': model.get_name(), 'node_count': len(nodes), 'link_count': len(links), 'node_counts_by_struct': counts,
           'variables': vars_, 'execution_order': order, 'hierarchy_bones': hier, 'nodes': nodes, 'links': links}
    p = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'cr_dump.json')
    with open(p, 'w') as f:
        json.dump(out, f, indent=1)
    print('PASS: wrote %s: %d nodes, %d links, %d variables, events %s (Construction %d / Forwards %d steps)' % (
        p, len(nodes), len(links), len(vars_), list(order),
        len(order.get('Construction', [])), len(order.get('Forwards Solve', []))))
    print('INFO: node counts %s' % sorted(counts.items(), key=lambda x: -x[1]))


try:
    _as12b()
except Exception:
    print('FAIL: %s' % traceback.format_exc())
