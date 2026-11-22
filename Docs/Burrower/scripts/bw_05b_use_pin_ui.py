# bw_05b_use_pin_ui.py - ticks "Use Pin" for the 19 rig variables on ABP_Burrower's Control Rig node by driving the
# editor UI with the SlateInspector toolset (the flag, UAnimGraphNode_CustomProperty::CustomPinProperties[i].bShowPin,
# has no CPF_Edit, so no property API can set it; the Details panel checkbox is the only writer).
# Worked on 2026-11-21 in the clone editor (UE 5.8) with 9 rows; 2026-11-22: 19 rows (+ FollowYawDeg1..4,
# FollowPitchDeg1..4, DeathVelocity, DeathAngularVelocity), rows matched by EXACT name. Run it via bw_05b_use_pin_ui.sh,
# which sends one phase per inbox call, because Slate must tick between UI actions. Phases (global BW05B_PHASE set by
# the wrapper):
#   open   : opens the ABP editor (own window "ABP_Burrower")
#   select : clicks the "Control Rig" node title in the AnimGraph to select it
#   tick   : prints the Use Pin state; ticks one unticked row per call: first the row the last filter was typed for,
#            else the first unticked VISIBLE row (rows below the short Details panel are clipped, size 0); if none is
#            visible, types the first unticked variable name into the Input list's Search box (character events only,
#            keyboard focus set directly on the box) so its row comes to the top. The node rebuilds after every tick
#            and the filter clears. Repeat until it prints ALL_TICKED.
#   save   : saves ABP_Burrower (explicit path), closes the ABP editor (an open ABP editor crashed UE at shutdown)
# Afterwards re-run bw_05_anim_bp.py: it wires the 19 Get nodes to the new pins, compiles and saves.
#
# Exact rows. The Input filter keeps every row whose name CONTAINS the typed text (FControlRigIOMapping::
# CreateVariableMapping, ControlRigIOMapping.cpp:435-462, FString::Contains, case-insensitive), so 'Speed' also shows
# RotorSpinSpeed, and DeathTime / DeathVelocity / DeathAngularVelocity / FollowYawDeg1.. share prefixes. So:
#   * a row is identified only by the full name in its label (regex: quote, name, then the literal '\nUse Pin' the
#     snapshot prints for the row's "Use Pin " text), never by a prefix or the filter text;
#   * its checkbox is the first 'checkbox' line after that label, before the next row label;
#   * the checked state is read from the flag list ('[checked]', '[focused, checked]', '[disabled, unchecked]' ...,
#     SlateInspectorToolsetSnapshotRenderer.cpp ExtractStateFlags), not by a '[checked]' substring;
#   * after a filter the typed name's own row is ticked first (exact match), then any other visible unticked row.
# The search box label is always its hint text "Search" (SEditableTextBox::GetDefaultAccessibleText returns the hint),
# so a filter left in the box cannot be read back; the last typed text is kept in the global _BW05B_FILTER (the inbox
# runs every request in one namespace) and cleared (End + BackSpace) before a new name is typed.
# Already exposed pins stay ticked when the rig gains variables (RebuildExposedProperties keeps OldExposedPinNames),
# so after the 2026-11-22 rig rebuild only the 10 new rows need work (<= 2 calls each). bw_05b_use_pin_ui.sh runs the
# tick phase at most 25 times: if it ends without ALL_TICKED (e.g. 19 rows on a fresh ABP), run it again, it resumes.
import unreal, json, re

ABP = '/Game/Assets/Enemies/Burrower/ABP_Burrower'
# = bw_05_anim_bp.BW05_VARS names = UBurrowerAnimInstance properties = CR_Burrower public variables
VARS = (['RotorAngleDeg', 'RotorSpinSpeed', 'WaveTime', 'WaveAmplitudeDeg', 'WavePhasePerJointDeg',
         'WavePitchAmplitudeDeg', 'Speed', 'bIsDead', 'DeathTime'] +
        ['FollowYawDeg%d' % i for i in range(1, 5)] + ['FollowPitchDeg%d' % i for i in range(1, 5)] +
        ['DeathVelocity', 'DeathAngularVelocity'])
_SI = 'SlateInspectorToolset.SlateInspectorToolset'

_RE_ROW = re.compile(r'generic "(\w+)\\nUse Pin')                 # full row name, then the escaped newline + "Use Pin"
_RE_CHECKBOX = re.compile(r'^\s*checkbox\b')
_RE_TEXTBOX = re.compile(r'^\s*textbox\b')
_RE_FLAGS = re.compile(r'\[((?:disabled|focused|checked|unchecked|indeterminate)'
                       r'(?:, (?:disabled|focused|checked|unchecked|indeterminate))*)\]')
_RE_REF = re.compile(r'\[ref=(\w+)\]')


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
            return _RE_REF.search(l).group(1)
    raise RuntimeError('no "ABP_Burrower" window: run phase open first')


def _tree(ref):
    return _ret(_si('Snapshot', Ref=ref, MaxDepth=80)).splitlines()


def _state(lines):
    """exact row name -> (checked, visible, checkbox ref, enabled). Rows of other names are kept too (never ticked)."""
    state, cur = {}, None
    for l in lines:
        m = _RE_ROW.search(l)
        if m:
            cur = m.group(1)
            continue
        if cur and _RE_CHECKBOX.match(l):
            fm = _RE_FLAGS.search(l)
            flags = [f.strip() for f in fm.group(1).split(',')] if fm else []
            rm = _RE_REF.search(l)
            if rm:
                state[cur] = ('checked' in flags, 'size=0,0' not in l, rm.group(1), 'disabled' not in flags)
            cur = None
    return state


def _search_box(lines):
    """Ref of the Input list's search box: within 12 lines after the "Input" category row, the textbox labelled
    "Search" (its hint text), else the first textbox there."""
    i0 = [i for i, l in enumerate(lines) if 'generic "Input"' in l]
    near = [l for l in (lines[i0[0]:i0[0] + 12] if i0 else []) if _RE_TEXTBOX.match(l) and _RE_REF.search(l)]
    for l in [l for l in near if 'textbox "Search"' in l] + near:
        return _RE_REF.search(l).group(1)
    return None


def _clear_filter(tb):
    """Removes text an earlier call typed (the box label cannot show it): focus via an empty Type, End, BackSpace xN."""
    old = globals().get('_BW05B_FILTER') or ''
    if not old:
        return
    _si('Type', Ref=tb, Text='', Submit=False)
    _si('PressKey', Key='End')
    for _ in range(len(old) + 2):
        _si('PressKey', Key='BackSpace')
    globals()['_BW05B_FILTER'] = None
    print('INFO: cleared filter %r' % old)


def _tick(name, st):
    print('INFO: tick', name, _si('Click', Ref=st[name][2]))
    globals()['_BW05B_FILTER'] = None        # the node rebuilds after the tick and the filter clears


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
                ref = _RE_REF.search(l).group(1)
                print('INFO: click node title', ref, _si('Click', Ref=ref))
                return
        print('FAIL: no "Control Rig" node title in the ABP window')
        return
    if phase == 'tick':
        st = _state(lines)
        target = globals().get('_BW05B_FILTER')
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
            tb = _search_box(lines) if target else None
            if tb:
                _clear_filter(tb)              # a filter left in the box can hide every row
                return
            print('FAIL: no Use Pin rows: is the Control Rig node selected and the Input section expanded?')
            return
        todo = [v for v in VARS if v in st and not st[v][0]]
        absent = [v for v in VARS if v not in st]
        print('REMAINING %d: %s' % (len(todo) + len(absent), ', '.join(todo + absent)))
        dis = [v for v in todo if not st[v][3]]
        if dis:
            print('FAIL: "Use Pin" is disabled on %s (not an input of the rig? bw_04b checks the public variables)' % dis)
            return
        if not todo and not absent:
            globals()['_BW05B_FILTER'] = None
            print('ALL_TICKED')
            return
        # 1. the exact row the last filter was typed for
        if target in todo and st[target][1]:
            _tick(target, st)
            return
        # 2. any other visible unticked row of ours (matched by its full name, never by the filter text)
        vis = [v for v in todo if st[v][1]]
        if vis:
            _tick(vis[0], st)
            return
        tb = _search_box(lines)
        if not tb:
            print('FAIL: Input search box not found')
            return
        if not todo:
            # every row on screen is ticked but some of ours are missing: a filter left in the box may hide them
            if target:
                _clear_filter(tb)
                return
            print('FAIL: no Use Pin row for %s: CR_Burrower lacks these public variables (rebuild it with bw_04, then '
                  'phase select again so the node rebuilds its exposable variables)' % absent)
            return
        # 3. bring the first unticked row to the top with the search box (a stale filter is removed first)
        _clear_filter(tb)
        print('INFO: filter', todo[0], _si('Type', Ref=tb, Text=todo[0], Submit=False))
        globals()['_BW05B_FILTER'] = todo[0]
        return
    if phase == 'save':
        print('INFO: save', unreal.EditorAssetLibrary.save_asset(ABP, only_if_is_dirty=False))
        abp = unreal.load_asset(ABP)
        print('INFO: asset editors closed', unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(abp))
        globals()['_BW05B_FILTER'] = None
        return
    print('FAIL: unknown phase %r' % phase)


try:
    _run(globals().get('BW05B_PHASE', 'tick'))
except Exception as _e:  # noqa: BLE001
    print('FAIL: %r' % (_e,))
