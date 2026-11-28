# as_72_menu_lives.py - round 2 PR B: the host menu's SHIP LIVES row (SPEC_B B5.2, section 3). Adds to WBP_MainMenu3
# (/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_MainMenu3) a WBP_OptionRow `Row_ShipLives` right after `Row_HostRules` in
# HostForm: its Label slot a TextBlock in Txt_HostRules' style, its Control slot an HBox with a SizeBox and a
# ComboBoxString named `ShipLivesComboBox` (UMainMenu3's BindWidgetOptional; the C++ fills it from ShipLivesChoices), all
# styled as the Rules row (fonts, colours, the combo's widget and item styles, the slots' padding / size / alignment
# copied from Ctl_HostRules / Box_HostRulesComboBox), and grows HostForm's canvas slot by one row. Then compiles and
# saves WBP_MainMenu3 by its path (and nothing else). The widget tree is built with UMGToolSet
# (unreal.ToolsetRegistry.execute_tool('UMGToolSet.UMGToolSet', ...), synchronous; the MainMenu3 builder's method).
# Idempotent: with ShipLivesComboBox already there it reports and stops (AS72_REBUILD = True removes Row_ShipLives and adds
# it again). AS72_DRY = True only reports what it would do. Never during PIE (asset scripts freeze the game thread then).
# A copy of the .uasset from before the change goes to Saved/Match/backup/ (outside Content, never committed).
# Run: Docs/Airship/scripts/harness/inbox.sh 72 Docs/Airship/scripts/ue/as_72_menu_lives.py 120
# Report: Saved/Match/as_72_menu_lives.json
import json, os, shutil, time, traceback  # unreal = inbox namespace

AS72_WBP = '/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_MainMenu3'
AS72_ROW = '/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_OptionRow.WBP_OptionRow_C'
AS72_UMG = 'UMGToolSet.UMGToolSet'
AS72_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Match')
R72 = {'lines': [], 'steps': []}


def o72(tag, msg):
    R72['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def as72_tool(name, args):
    res = unreal.ToolsetRegistry.execute_tool(AS72_UMG, name, json.dumps(args))
    if not res.is_complete:
        raise RuntimeError(name + ': not complete')
    if res.error:
        raise RuntimeError(name + ': ' + str(res.error))
    v = json.loads(res.value) if res.value else {}
    R72['steps'].append(name)
    return v.get('returnValue', v)


def as72_obj(ref):
    if isinstance(ref, dict):
        ref = ref.get('refPath')
    return unreal.load_object(None, ref) if ref and ref != 'None' else None


def as72_widgets(ref):
    out = {}
    for wi in as72_tool('GetWidgets', {'widgetBlueprint': ref}).get('widgets', []):
        w = as72_obj(wi.get('widget'))
        if w is not None:
            out[w.get_name()] = (w, wi)
    return out


def as72_copy(src, dst, names):
    for n in names:
        try:
            dst.set_editor_property(n, src.get_editor_property(n))
        except Exception:  # noqa: BLE001
            o72('WARN', 'could not copy %s from %s' % (n, src.get_name()))


def as72_main():
    g = globals()
    dry, rebuild = bool(g.get('AS72_DRY')), bool(g.get('AS72_REBUILD'))
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        o72('FAIL', 'PIE is running: asset scripts freeze the game thread then; run it with the editor idle')
        return False
    if not unreal.EditorAssetLibrary.does_asset_exist(AS72_WBP):
        o72('FAIL', '%s not found' % AS72_WBP)
        return False
    unreal.load_asset(AS72_WBP)
    ref = {'refPath': AS72_WBP + '.' + AS72_WBP.split('/')[-1]}
    W = as72_widgets(ref)
    R72['before'] = sorted(W)
    if 'ShipLivesComboBox' in W and not rebuild:
        o72('INFO', 'ShipLivesComboBox is already in WBP_MainMenu3: nothing to do (AS72_REBUILD = True to add it again)')
        return True
    need = ['HostForm', 'Row_HostRules', 'Txt_HostRules', 'Ctl_HostRules', 'Box_HostRulesComboBox', 'HostRulesComboBox']
    miss = [n for n in need if n not in W]
    if miss:
        o72('FAIL', 'WBP_MainMenu3 has no %s (widgets: %s): built differently from the MainMenu3 builder' % (miss, sorted(W)[:60]))
        return False
    if dry:
        o72('INFO', 'DRY RUN: would add Row_ShipLives (WBP_OptionRow) after Row_HostRules in HostForm with Txt_ShipLives / Ctl_ShipLives / '
                    'Box_ShipLivesComboBox / ShipLivesComboBox in the Rules row\'s style, grow HostForm by one row, compile and save')
        return True
    src = unreal.SystemLibrary.get_system_path(unreal.load_asset(AS72_WBP))
    if src and os.path.exists(src):
        os.makedirs(os.path.join(AS72_OUT, 'backup'), exist_ok=True)
        bk = os.path.join(AS72_OUT, 'backup', 'WBP_MainMenu3_before_as72_%s.uasset' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
        shutil.copyfile(src, bk)
        R72['backup'] = bk
        o72('INFO', 'backup %s' % bk)
    if rebuild:
        for n in ('Row_ShipLives',):
            if n in W:
                as72_tool('RemoveWidget', {'widgetBlueprint': ref, 'widget': {'refPath': W[n][0].get_path_name()}})
        W = as72_widgets(ref)
    form, row_r = W['HostForm'][0], W['Row_HostRules'][0]
    try:
        idx = int(form.get_child_index(row_r)) + 1
    except Exception:  # noqa: BLE001
        idx = -1
    n_rows = int(form.get_children_count()) if hasattr(form, 'get_children_count') else 4
    info = as72_tool('AddWidget', {'widgetBlueprint': ref, 'widgetClass': {'refPath': AS72_ROW}, 'widgetDisplayName': 'Row_ShipLives',
                                   'childIndex': idx, 'parentWidget': {'refPath': form.get_path_name()}})
    row = as72_obj(info.get('widget'))
    slot = as72_obj(info.get('slot'))
    if row is None:
        raise RuntimeError('AddWidget Row_ShipLives returned no widget: %s' % str(info)[:300])
    if slot is not None and row_r.slot is not None:
        as72_copy(row_r.slot, slot, ('padding', 'horizontal_alignment', 'vertical_alignment', 'size'))
    t_src = W['Txt_HostRules'][0]
    info = as72_tool('SetNamedSlotContent', {'widgetBlueprint': ref, 'hostWidget': {'refPath': row.get_path_name()}, 'slotName': 'Label',
                                              'widgetClass': {'refPath': '/Script/UMG.TextBlock'}, 'widgetName': 'Txt_ShipLives'})
    txt = as72_obj(info.get('widget'))
    as72_copy(t_src, txt, ('font', 'color_and_opacity', 'justification', 'shadow_offset', 'shadow_color_and_opacity'))
    label = str(t_src.get_editor_property('text'))
    txt.set_editor_property('text', unreal.Text('SHIP LIVES' if label.isupper() else 'Ship lives'))
    info = as72_tool('SetNamedSlotContent', {'widgetBlueprint': ref, 'hostWidget': {'refPath': row.get_path_name()}, 'slotName': 'Control',
                                              'widgetClass': {'refPath': '/Script/UMG.HorizontalBox'}, 'widgetName': 'Ctl_ShipLives'})
    ctl = as72_obj(info.get('widget'))
    info = as72_tool('AddWidget', {'widgetBlueprint': ref, 'widgetClass': {'refPath': '/Script/UMG.SizeBox'}, 'widgetDisplayName': 'Box_ShipLivesComboBox',
                                   'childIndex': -1, 'parentWidget': {'refPath': ctl.get_path_name()}})
    box, box_slot = as72_obj(info.get('widget')), as72_obj(info.get('slot'))
    b_src = W['Box_HostRulesComboBox'][0]
    for k in ('width_override', 'height_override'):
        # SetWidthOverride / SetHeightOverride also set the bOverride_ flag (Python: override_width_override)
        try:
            if b_src.get_editor_property('override_' + k):
                getattr(box, 'set_' + k)(float(b_src.get_editor_property(k)))
        except Exception:  # noqa: BLE001
            o72('WARN', 'could not copy %s from %s' % (k, b_src.get_name()))
    if box_slot is not None and b_src.slot is not None:
        as72_copy(b_src.slot, box_slot, ('padding', 'size', 'horizontal_alignment', 'vertical_alignment'))
    info = as72_tool('AddWidget', {'widgetBlueprint': ref, 'widgetClass': {'refPath': '/Script/UMG.ComboBoxString'}, 'widgetDisplayName': 'ShipLivesComboBox',
                                   'childIndex': -1, 'parentWidget': {'refPath': box.get_path_name()}})
    cb = as72_obj(info.get('widget'))
    c_src = W['HostRulesComboBox'][0]
    as72_copy(c_src, cb, ('font', 'foreground_color', 'content_padding', 'max_list_height', 'enable_gamepad_navigation_mode', 'widget_style', 'item_style'))
    cbs = as72_obj(info.get('slot'))
    if cbs is not None and c_src.slot is not None:
        as72_copy(c_src.slot, cbs, ('padding', 'horizontal_alignment', 'vertical_alignment'))
    as72_tool('ToggleWidgetAsVariable', {'widgetBlueprint': ref, 'widget': {'refPath': cb.get_path_name()}, 'bIsVariable': True})
    for w in (row, txt, ctl, box):
        as72_tool('ToggleWidgetAsVariable', {'widgetBlueprint': ref, 'widget': {'refPath': w.get_path_name()}, 'bIsVariable': False})
    try:
        fs = form.slot
        off = fs.get_offsets()
        h = float(off.bottom)
        if h > 0.0 and n_rows > 0:
            fs.set_offsets(unreal.Margin(off.left, off.top, off.right, h * (n_rows + 1) / float(n_rows)))
            o72('INFO', 'HostForm canvas slot height %.0f -> %.0f (%d -> %d rows)' % (h, h * (n_rows + 1) / float(n_rows), n_rows, n_rows + 1))
    except Exception:  # noqa: BLE001
        o72('WARN', 'HostForm slot not grown: %s' % traceback.format_exc().strip().splitlines()[-1])
    ok = as72_tool('CompileWidgetBlueprint', {'widgetBlueprint': ref})
    saved = unreal.EditorAssetLibrary.save_asset(AS72_WBP, only_if_is_dirty=False)
    R72['after'] = sorted(as72_widgets(ref))
    R72['compiled'], R72['saved'] = ok, saved
    o72('PASS' if saved and 'ShipLivesComboBox' in R72['after'] else 'FAIL', 'Row_ShipLives added at HostForm index %d, compiled %s, saved %s' % (idx, ok, saved))
    return bool(saved)


try:
    os.makedirs(AS72_OUT, exist_ok=True)
    _ok72 = as72_main()
    with open(os.path.join(AS72_OUT, 'as_72_menu_lives.json'), 'w') as _f:
        json.dump(R72, _f, indent=1, default=str)
    print('RESULT: %s' % ('OK' if _ok72 else 'FAIL'))
except Exception:  # noqa: BLE001
    R72['error'] = traceback.format_exc()
    with open(os.path.join(AS72_OUT, 'as_72_menu_lives.json'), 'w') as _f:
        json.dump(R72, _f, indent=1, default=str)
    print('RESULT: FAIL %s' % R72['error'])
