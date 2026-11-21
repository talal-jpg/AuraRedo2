# bw_05b_use_pin_ui.py - ticks "Use Pin" for the 9 rig variables on ABP_Burrower's Control Rig node by driving the
# editor UI with the SlateInspector toolset (the flag, UAnimGraphNode_CustomProperty::CustomPinProperties[i].bShowPin,
# has no CPF_Edit, so no property API can set it; the Details panel checkbox is the only writer).
# Worked on 2026-11-21 in the clone editor (UE 5.8). Run it via bw_05b_use_pin_ui.sh, which sends one phase per inbox
# call, because Slate must tick between UI actions. Phases (global BW05B_PHASE set by the wrapper):
#   open   : opens the ABP editor (own window "ABP_Burrower")
#   select : clicks the "Control Rig" node title in the AnimGraph to select it
#   tick   : prints the Use Pin state; ticks the first unticked VISIBLE row (rows below the short Details panel are
#            clipped, size 0); if none is visible, types the first unticked variable name into the Input list's Search
#            box (character events only, keyboard focus set directly on the box) so its row comes to the top.
#            The node rebuilds after every tick and the filter clears. Repeat until it prints ALL_TICKED.
#   save   : saves ABP_Burrower (explicit path), closes the ABP editor (an open ABP editor crashed UE at shutdown)
# Afterwards re-run bw_05_anim_bp.py: it wires the 9 Get nodes to the new pins, compiles and saves.
import unreal, json, re

ABP = '/Game/Assets/Enemies/Burrower/ABP_Burrower'
VARS = ['RotorAngleDeg', 'RotorSpinSpeed', 'WaveTime', 'WaveAmplitudeDeg', 'WavePhasePerJointDeg',
        'WavePitchAmplitudeDeg', 'Speed', 'bIsDead', 'DeathTime']
_SI = 'SlateInspectorToolset.SlateInspectorToolset'


def _si(tool, **params):
    res = unreal.ToolsetRegistry.execute_tool(_SI, tool, json.dumps(params))
    err = str(res.get_editor_property('error') or '')
    if err:
        raise RuntimeError('%s: %s' % (tool, err))
    return str(res.get_editor_property('value') or '')


def _ret(raw):
    try:
        return json.loads(raw)['returnValue']
    except Exception:  # noqa: BLE001
        return raw


def _abp_window_ref():
    tree = _ret(_si('Snapshot', Ref='', MaxDepth=2))
    for l in tree.splitlines():
        if l.lstrip().startswith('window "ABP_Burrower"'):
            return re.search(r'\[ref=(\w+)\]', l).group(1)
    raise RuntimeError('no "ABP_Burrower" window: run phase open first')


def _tree(ref):
    return _ret(_si('Snapshot', Ref=ref, MaxDepth=80)).splitlines()


def _state(lines):
    state, cur = {}, None
    for l in lines:
        m = re.search(r'generic "(\w+)\\nUse Pin', l)
        if m:
            cur = m.group(1)
            continue
        if cur and 'checkbox' in l:
            state[cur] = ('[checked]' in l, 'size=0,0' not in l, re.search(r'\[ref=(\w+)\]', l).group(1))
            cur = None
    return state


def _run(phase):
    if phase == 'open':
        abp = unreal.load_asset(ABP)
        print('INFO: open', unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([abp]))
        return
    w = _abp_window_ref()
    lines = _tree(w)
    if phase == 'select':
        for l in lines:
            if re.search(r'text "Control Rig" \[pos=', l):
                ref = re.search(r'\[ref=(\w+)\]', l).group(1)
                print('INFO: click node title', ref, _si('Click', Ref=ref))
                return
        print('FAIL: no "Control Rig" node title in the ABP window')
        return
    if phase == 'tick':
        st = _state(lines)
        print('STATE', {v: (st[v][0] if v in st else None) for v in VARS})
        if not st:
            # The Details panel is short: with "Settings" expanded the Input rows are not built at all. Collapse it
            # once (its expander is the first button under the category row), then the next tick sees the rows.
            for i, l in enumerate(lines):
                if 'generic "Settings"' in l and globals().get('_BW05B_COLLAPSED') is None:
                    for l2 in lines[i + 1:i + 3]:
                        m = re.search(r'button \[pos=.*\[ref=(\w+)\]', l2)
                        if m:
                            globals()['_BW05B_COLLAPSED'] = True
                            print('INFO: collapse Settings', _si('Click', Ref=m.group(1)))
                            return
            print('FAIL: no Use Pin rows: is the Control Rig node selected and the Input section expanded?')
            return
        todo = [v for v in VARS if v in st and not st[v][0]]
        if not todo:
            print('ALL_TICKED')
            return
        vis = [v for v in todo if st[v][1]]
        if vis:
            print('INFO: tick', vis[0], _si('Click', Ref=st[vis[0]][2]))
            return
        i0 = [i for i, l in enumerate(lines) if 'generic "Input"' in l]
        tb = None
        for l in (lines[i0[0]:i0[0] + 12] if i0 else []):
            if 'textbox "Search"' in l:
                tb = re.search(r'\[ref=(\w+)\]', l).group(1)
                break
        if not tb:
            print('FAIL: Input search box not found')
            return
        print('INFO: filter', todo[0], _si('Type', Ref=tb, Text=todo[0], Submit=False))
        return
    if phase == 'save':
        print('INFO: save', unreal.EditorAssetLibrary.save_asset(ABP, only_if_is_dirty=False))
        abp = unreal.load_asset(ABP)
        print('INFO: asset editors closed', unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(abp))
        return
    print('FAIL: unknown phase %r' % phase)


try:
    _run(globals().get('BW05B_PHASE', 'tick'))
except Exception as _e:  # noqa: BLE001
    print('FAIL: %r' % (_e,))
