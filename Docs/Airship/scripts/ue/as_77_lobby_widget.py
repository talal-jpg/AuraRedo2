# as_77_lobby_widget.py - round 2 PR B lobby (Docs/Airship/round2/SPEC_B_LOBBY.md 6.2, 6.3, 6.5): builds
#   /Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_Lobby3            (parent UMyLobbyWidget, /Script/Aura.MyLobbyWidget)
#   /Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_LobbyPlayerRow3   (parent UMyLobbyPlayerRow, /Script/Aura.MyLobbyPlayerRow)
# in the Menu3 yellow-and-black look: F_Anton titles, F_Bebas / F_Barlow text (Menu3/Fonts), the graffiti slab MIs
# (Menu3/Materials) behind words and chips, so FAuraMenuButtonFX pops them like the other Menu3 buttons. Styles are COPIED
# where the Menu3 widgets have them (combo boxes from WBP_MainMenu3's HostRulesComboBox and Box_HostRulesComboBox, as
# as_72 does; check boxes from WBP_MainMenu3's ShowFullLobbiesCheckBox; chip and word button styles from WBP_PauseMenu3's
# CopyCodeButton and ResumeButton; the row's name / ping fonts from WBP_SessionPlayerRow3), else the MainMenu3 builder's
# flat palette (mm3_lib, Saved/ClaudeBackups/MainMenu3_20261030T100745Z/scripts) is used.
# The widget tree is built with UMGToolSet (unreal.ToolsetRegistry.execute_tool('UMGToolSet.UMGToolSet', ...),
# synchronous; the MainMenu3 builder's method): CreateWidgetBlueprint, AddWidget, ToggleWidgetAsVariable,
# CompileWidgetBlueprint. Properties are set directly on the design-time widgets and slots.
# The names of SPEC_B_LOBBY 6.3 are the contract (BindWidgetOptional in MyLobbyWidget.h / MyLobbyPlayerRow.h): every one
# is made a variable, every other widget is not. Two extra optional names: MoveText (the row's MOVE label) and the
# Lobby3 CDO's PlayerRowClass = WBP_LobbyPlayerRow3_C. ButtonFX as WBP_PauseMenu3's.
# The Item_<key> / Wrap_<key> container names are a contract too: UMyLobbyWidget::SetButtonShown hides a button with its
# label and slab by collapsing its outermost Item_ / Wrap_ parent that holds no other button (Wrap_Code: CODE, the code, COPY).
# Idempotent: with both WBPs there it verifies the names and stops (AS77_REBUILD = True clears and rebuilds them in place:
# the old root is removed, the asset and its references stay). AS77_DRY = True only reports. Never during PIE (asset
# scripts freeze the game thread then). Copies of existing .uassets go to Saved/Match/backup/ before a rebuild (outside
# Content, never committed). Saves only the two WBPs, by path.
# Run (editor idle, no PIE, the PR B C++ with UMyLobbyWidget built into this editor):
#   Docs/Airship/scripts/harness/inbox.sh 77 Docs/Airship/scripts/ue/as_77_lobby_widget.py 180
# Then as_78_lobby_hud.py sets BP_MyHUD's LobbyWidgetClass and verifies.
# Report: Saved/Match/as_77_lobby_widget.json
import json, os, shutil, time, traceback  # unreal = inbox namespace

L77_MENU3 = '/Game/Level/UI/UserWidgets/MainMenu/Menu3'
L77_FONTS = L77_MENU3 + '/Fonts'
L77_MATS = L77_MENU3 + '/Materials'
L77_LOBBY = L77_MENU3 + '/WBP_Lobby3'
L77_ROW = L77_MENU3 + '/WBP_LobbyPlayerRow3'
L77_PARENT_LOBBY = '/Script/Aura.MyLobbyWidget'
L77_PARENT_ROW = '/Script/Aura.MyLobbyPlayerRow'
L77_MAIN = L77_MENU3 + '/WBP_MainMenu3'
L77_PAUSE = L77_MENU3 + '/WBP_PauseMenu3'
L77_SESSROW = L77_MENU3 + '/WBP_SessionPlayerRow3'
L77_UMG = 'UMGToolSet.UMGToolSet'
L77_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Match')
R77 = {'lines': [], 'steps': 0, 'copied': [], 'fallback': [], 'log': []}

# SPEC_B_LOBBY 6.3: name -> UMG class name (the C++ BindWidgetOptional type; a subclass passes)
L77_LOBBY_NAMES = {
    'LobbyPanel': 'Widget', 'CompactPanel': 'Widget', 'CompactText': 'TextBlock', 'CountdownText': 'TextBlock',
    'CountdownHintText': 'TextBlock', 'MessageText': 'TextBlock', 'TitleText': 'TextBlock', 'JoinCodeText': 'TextBlock',
    'CopyCodeButton': 'Button', 'BlueHeaderText': 'TextBlock', 'BlueList': 'PanelWidget', 'OrangeHeaderText': 'TextBlock',
    'OrangeList': 'PanelWidget', 'SwitchTeamButton': 'Button', 'SwitchTeamText': 'TextBlock', 'RulesPanel': 'Widget',
    'TeamModeComboBox': 'ComboBoxString', 'ShipLivesComboBox': 'ComboBoxString', 'SwarmComboBox': 'ComboBoxString',
    'MaxPlayersComboBox': 'ComboBoxString', 'TimeLimitComboBox': 'ComboBoxString', 'FriendlyFireCheckBox': 'CheckBox',
    'GrappleShipsCheckBox': 'CheckBox', 'LaneAssistCheckBox': 'CheckBox', 'RulesHintText': 'TextBlock', 'ReadyButton': 'Button',
    'ReadyText': 'TextBlock', 'StartButton': 'Button', 'StartText': 'TextBlock', 'StartReasonText': 'TextBlock',
    'CloseButton': 'Button', 'MenuButton': 'Button', 'LeaveButton': 'Button'}
L77_ROW_NAMES = {'PlayerNameText': 'TextBlock', 'StatusText': 'TextBlock', 'PingText': 'TextBlock', 'LocalHighlight': 'Widget',
                 'MoveButton': 'Button', 'MoveText': 'TextBlock'}


def o77(tag, msg):
    R77['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


# ------------------------------------------------------------------------------------------------- UMGToolSet
def l77_tool(name, args):
    res = unreal.ToolsetRegistry.execute_tool(L77_UMG, name, json.dumps(args))
    if not res.is_complete:
        raise RuntimeError(name + ': not complete')
    if res.error:
        raise RuntimeError(name + ': ' + str(res.error))
    R77['steps'] += 1
    v = json.loads(res.value) if res.value else {}
    return v.get('returnValue', v)


def l77_obj(ref):
    if isinstance(ref, dict):
        ref = ref.get('refPath')
    return unreal.load_object(None, ref) if ref and ref != 'None' else None


def l77_ref(path):
    return {'refPath': path + '.' + path.split('/')[-1]}


def l77_widgets(ref):
    """name -> (widget, info) of a WBP's design-time tree"""
    out = {}
    for wi in l77_tool('GetWidgets', {'widgetBlueprint': ref}).get('widgets', []):
        w = l77_obj(wi.get('widget'))
        if w is not None:
            out[w.get_name()] = (w, wi)
    return out


class L77Ctx(object):
    def __init__(self, path):
        self.path = path
        self.ref = l77_ref(path)
        self.w = {}
        self.s = {}
        self.vars = set()


def l77_make(path, parent_class):
    """the WBP, empty: created, or (rebuild) its old root removed"""
    c = L77Ctx(path)
    folder, name = path.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.load_asset(path)
        info = l77_tool('GetWidgets', {'widgetBlueprint': c.ref})
        for wi in info.get('widgets', []):
            if wi.get('parent') in (None, 'None') and wi.get('namedSlotHost') in (None, 'None') and not wi.get('bInherited'):
                l77_tool('RemoveWidget', {'widgetBlueprint': c.ref, 'widget': wi['widget']})
        return c
    l77_tool('CreateWidgetBlueprint', {'folderPath': folder, 'assetName': name, 'parentClass': {'refPath': parent_class}})
    return c


L77_CLS = {'Canvas': '/Script/UMG.CanvasPanel', 'Overlay': '/Script/UMG.Overlay', 'VBox': '/Script/UMG.VerticalBox',
           'HBox': '/Script/UMG.HorizontalBox', 'Text': '/Script/UMG.TextBlock', 'Image': '/Script/UMG.Image',
           'Button': '/Script/UMG.Button', 'SizeBox': '/Script/UMG.SizeBox', 'Border': '/Script/UMG.Border',
           'Scroll': '/Script/UMG.ScrollBox', 'Combo': '/Script/UMG.ComboBoxString', 'Check': '/Script/UMG.CheckBox',
           'Spacer': '/Script/UMG.Spacer', 'SafeZone': '/Script/UMG.SafeZone'}


def l77_add(c, cls, name, parent=None, var=False):
    args = {'widgetBlueprint': c.ref, 'widgetClass': {'refPath': L77_CLS.get(cls, cls)}, 'widgetDisplayName': name, 'childIndex': -1}
    if parent is not None:
        args['parentWidget'] = {'refPath': c.w[parent].get_path_name()}
    info = l77_tool('AddWidget', args)
    w = l77_obj(info.get('widget'))
    if w is None:
        raise RuntimeError('AddWidget %s %s returned no widget: %s' % (cls, name, str(info)[:300]))
    if w.get_name() != name:
        R77['log'].append(('renamed', name, w.get_name()))
    c.w[name] = w
    c.s[name] = l77_obj(info.get('slot')) if info.get('slot') not in (None, 'None') else None
    if var:
        c.vars.add(name)
    return w


def l77_finish(c):
    for n, w in c.w.items():
        l77_tool('ToggleWidgetAsVariable', {'widgetBlueprint': c.ref, 'widget': {'refPath': w.get_path_name()}, 'bIsVariable': n in c.vars})
    ok = l77_tool('CompileWidgetBlueprint', {'widgetBlueprint': c.ref})
    return ok


# ------------------------------------------------------------------------------------------------- style (mm3 palette)
def l77_lc(r, g, b, a=1.0):
    return unreal.LinearColor(r, g, b, a)


L77_INK = l77_lc(0.0033, 0.0033, 0.0033)
L77_COAL = l77_lc(0.008, 0.008, 0.008)
L77_COAL2 = l77_lc(0.016, 0.016, 0.016)
L77_YELLOW = l77_lc(1.0, 0.6584, 0.0)
L77_YHOT = l77_lc(1.0, 0.7758, 0.0331)
L77_YPRESS = l77_lc(0.7913, 0.4793, 0.0)
L77_YDIM = l77_lc(0.2542, 0.1714, 0.0)
L77_PAPER = l77_lc(1, 1, 1)
L77_GREY = l77_lc(0.1559, 0.1559, 0.1559)
L77_GREYL = l77_lc(0.4564, 0.4564, 0.4564)


def l77_a(col, a):
    return l77_lc(col.r, col.g, col.b, a)


_l77_fonts = {}


def l77_font(font, size, typeface='', letter=0, skew=0.0, outline=0, outline_color=None):
    if font not in _l77_fonts:
        _l77_fonts[font] = unreal.load_asset(L77_FONTS + '/' + font)
    fi = unreal.SlateFontInfo()
    if _l77_fonts[font] is not None:
        fi.set_editor_property('font_object', _l77_fonts[font])
    else:
        R77['fallback'].append('font %s missing: engine font' % font)
    fi.set_editor_property('size', float(size))
    if typeface:
        fi.set_editor_property('typeface_font_name', typeface)
    fi.set_editor_property('letter_spacing', int(letter))
    fi.set_editor_property('skew_amount', float(skew))
    if outline:
        o = fi.get_editor_property('outline_settings')
        o.set_editor_property('outline_size', int(outline))
        o.set_editor_property('mitered_corners', True)
        o.set_editor_property('outline_color', outline_color or L77_INK)
        fi.set_editor_property('outline_settings', o)
    return fi


def l77_sc(col):
    s = unreal.SlateColor()
    s.set_editor_property('specified_color', col)
    return s


def l77_brush(color=None, draw='box', size=None, res=None):
    b = unreal.SlateBrush()
    dt = {'box': unreal.SlateBrushDrawType.BOX, 'image': unreal.SlateBrushDrawType.IMAGE,
          'none': unreal.SlateBrushDrawType.NO_DRAW_TYPE}[draw]
    b.set_editor_property('draw_as', dt)
    if color is not None:
        b.set_editor_property('tint_color', l77_sc(color))
    if size:
        v = unreal.DeprecateSlateVector2D()
        v.set_editor_property('x', float(size[0]))
        v.set_editor_property('y', float(size[1]))
        b.set_editor_property('image_size', v)
    if res is not None:
        b.set_editor_property('resource_object', res)
    return b


def l77_m(l, t=None, r_=None, b=None):
    if t is None:
        t = r_ = b = l
    return unreal.Margin(float(l), float(t), float(r_), float(b))


L77_HA = {'l': unreal.HorizontalAlignment.H_ALIGN_LEFT, 'c': unreal.HorizontalAlignment.H_ALIGN_CENTER,
          'r': unreal.HorizontalAlignment.H_ALIGN_RIGHT, 'f': unreal.HorizontalAlignment.H_ALIGN_FILL}
L77_VA = {'t': unreal.VerticalAlignment.V_ALIGN_TOP, 'c': unreal.VerticalAlignment.V_ALIGN_CENTER,
          'b': unreal.VerticalAlignment.V_ALIGN_BOTTOM, 'f': unreal.VerticalAlignment.V_ALIGN_FILL}


def l77_vis(w, v):
    w.set_visibility({'visible': unreal.SlateVisibility.VISIBLE, 'collapsed': unreal.SlateVisibility.COLLAPSED,
                      'hit': unreal.SlateVisibility.HIT_TEST_INVISIBLE, 'self': unreal.SlateVisibility.SELF_HIT_TEST_INVISIBLE}[v])


def l77_xform(w, angle=0.0, pivot=(0.5, 0.5)):
    t = unreal.WidgetTransform()
    t.set_editor_property('angle', float(angle))
    w.set_editor_property('render_transform', t)
    w.set_editor_property('render_transform_pivot', unreal.Vector2D(pivot[0], pivot[1]))


def l77_canvas(c, name, x, y, w=None, h=None, anchor=(0, 0, 0, 0), align=(0, 0), auto=False, z=0):
    sl = c.s[name]
    a = unreal.Anchors()
    a.set_editor_property('minimum', unreal.Vector2D(anchor[0], anchor[1]))
    a.set_editor_property('maximum', unreal.Vector2D(anchor[2], anchor[3]))
    sl.set_anchors(a)
    sl.set_alignment(unreal.Vector2D(align[0], align[1]))
    sl.set_auto_size(auto)
    sl.set_offsets(l77_m(x, y, w if w is not None else 0, h if h is not None else 0))
    if z:
        sl.set_z_order(z)


def l77_box(c, name, pad=None, h='f', v='f', size=None):
    """Overlay / VBox / HBox / Border / ScrollBox / SizeBox child slot"""
    sl = c.s[name]
    if sl is None:
        return
    if pad is not None:
        sl.set_padding(pad if isinstance(pad, unreal.Margin) else l77_m(*pad) if isinstance(pad, (tuple, list)) else l77_m(pad))
    try:
        sl.set_horizontal_alignment(L77_HA[h])
        sl.set_vertical_alignment(L77_VA[v])
    except Exception:  # noqa: BLE001
        pass
    if size is not None:
        cs = unreal.SlateChildSize()
        if size == 'auto':
            cs.set_editor_property('size_rule', unreal.SlateSizeRule.AUTOMATIC)
        else:
            cs.set_editor_property('size_rule', unreal.SlateSizeRule.FILL)
            cs.set_editor_property('value', float(size))
        try:
            sl.set_size(cs)
        except Exception:  # noqa: BLE001
            pass


def l77_sizebox(c, name, parent, w=None, h=None, var=False):
    sb = l77_add(c, 'SizeBox', name, parent, var)
    if w is not None:
        sb.set_width_override(float(w))
    if h is not None:
        sb.set_height_override(float(h))
    return sb


def l77_text(c, name, parent, s, font, color=None, var=False, just='left', shadow=None, hit=True, wrap=0):
    w = l77_add(c, 'Text', name, parent, var)
    w.set_editor_property('text', unreal.Text(s))
    w.set_editor_property('font', font)
    w.set_editor_property('color_and_opacity', l77_sc(color or L77_PAPER))
    w.set_editor_property('justification', {'left': unreal.TextJustify.LEFT, 'center': unreal.TextJustify.CENTER,
                                            'right': unreal.TextJustify.RIGHT}[just])
    if shadow:
        w.set_editor_property('shadow_offset', unreal.Vector2D(shadow[0], shadow[1]))
        w.set_editor_property('shadow_color_and_opacity', L77_INK)
    if wrap:
        w.set_editor_property('auto_wrap_text', False)
        w.set_editor_property('wrap_text_at', float(wrap))
    if hit:
        l77_vis(w, 'hit')
    return w


def l77_image(c, name, parent, color, var=False, size=None, hit=True):
    w = l77_add(c, 'Image', name, parent, var)
    w.set_editor_property('brush', l77_brush(color=L77_PAPER, size=size))
    w.set_editor_property('color_and_opacity', color)
    if hit:
        l77_vis(w, 'hit')
    return w


def l77_bstyle(normal=None, hovered=None, pressed=None, disabled=None, pad=(0, 0, 0, 0), fg=None, hfg=None, pfg=None, dfg=None):
    st = unreal.ButtonStyle()

    def br(cv):
        return l77_brush(draw='none') if cv is None else (cv if isinstance(cv, unreal.SlateBrush) else l77_brush(cv))
    st.set_editor_property('normal', br(normal))
    st.set_editor_property('hovered', br(hovered))
    st.set_editor_property('pressed', br(pressed))
    st.set_editor_property('disabled', br(disabled))
    st.set_editor_property('normal_padding', l77_m(*pad))
    st.set_editor_property('pressed_padding', l77_m(*pad))
    for k, v in (('normal_foreground', fg), ('hovered_foreground', hfg), ('pressed_foreground', pfg), ('disabled_foreground', dfg)):
        if v is not None:
            st.set_editor_property(k, l77_sc(v))
    return st


# styles copied from the Menu3 widgets (filled by l77_sources)
L77_SRC = {}


def l77_copy(src, dst, names, what):
    done = []
    for n in names:
        try:
            dst.set_editor_property(n, src.get_editor_property(n))
            done.append(n)
        except Exception:  # noqa: BLE001
            pass
    if done:
        R77['copied'].append('%s <- %s.%s' % (dst.get_name(), src.get_name(), '/'.join(done)))
    return done


def l77_sources():
    """the Menu3 widgets whose looks the lobby copies (SPEC_B_LOBBY 6.5); missing ones fall back to the mm3 palette"""
    for path, names in ((L77_MAIN, ('HostRulesComboBox', 'Box_HostRulesComboBox', 'Txt_HostRules', 'ShowFullLobbiesCheckBox')),
                        (L77_PAUSE, ('ResumeButton', 'CopyCodeButton', 'Label_CopyCode', 'Graffiti_CopyCode', 'Graffiti_Resume')),
                        (L77_SESSROW, ('PlayerNameText', 'PingText', 'Img_RowPlate'))):
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            R77['fallback'].append('%s missing: mm3 palette' % path)
            continue
        try:
            unreal.load_asset(path)
            W = l77_widgets(l77_ref(path))
            for n in names:
                if n in W:
                    L77_SRC[path.split('/')[-1] + '.' + n] = W[n][0]
                else:
                    R77['fallback'].append('%s has no %s' % (path.split('/')[-1], n))
        except Exception:  # noqa: BLE001
            R77['fallback'].append('%s: %s' % (path, traceback.format_exc().strip().splitlines()[-1]))


L77_SLABS = {}


def l77_slabs():
    for k, n in (('word', 'MI_UI_Slab_Word_A'), ('ring', 'MI_UI_Slab_Ring'), ('tag', 'MI_UI_Slab_Tag')):
        p = L77_MATS + '/' + n
        L77_SLABS[k] = unreal.load_asset(p) if unreal.EditorAssetLibrary.does_asset_exist(p) else None


def l77_graffiti(c, key, parent, kind, inset):
    """the Image FAuraMenuButtonFX drives (Graffiti_<key>, the button's sibling)"""
    g = l77_add(c, 'Image', 'Graffiti_' + key, parent)
    mi = L77_SLABS.get(kind)
    g.set_editor_property('brush', l77_brush(L77_PAPER, draw='image', size=(1, 1), res=mi) if mi is not None else l77_brush(draw='none'))
    l77_vis(g, 'hit')
    l77_box(c, 'Graffiti_' + key, pad=l77_m(-inset[0], -inset[1], -inset[2], -inset[3]))
    return g


def l77_button(c, name, parent, style, var=True):
    b = l77_add(c, 'Button', name, parent, var)
    b.set_editor_property('widget_style', style)
    b.set_editor_property('background_color', L77_PAPER)
    b.set_editor_property('color_and_opacity', L77_PAPER)
    return b


def l77_word(c, key, parent, label, button_name, size=48, color=None, h=88, label_name=None):
    """archetype A (mm3 word): Wrap_<key> SizeBox > Item_<key> Overlay > Graffiti_, label, Button (last)"""
    l77_sizebox(c, 'Wrap_' + key, parent, h=h)
    l77_add(c, 'Overlay', 'Item_' + key, 'Wrap_' + key)
    l77_xform(c.w['Item_' + key], pivot=(0.15, 0.5))
    l77_graffiti(c, key, 'Item_' + key, 'word', (30, 18, 30, 18))
    ln = label_name or ('Label_' + key)
    l77_text(c, ln, 'Item_' + key, label, l77_font('F_Anton', size, letter=20, skew=0.21), color or L77_YELLOW, var=bool(label_name), shadow=(3, 3))
    l77_box(c, ln, pad=l77_m(22, 0, 22, 0), h='l', v='c')
    src = L77_SRC.get('WBP_PauseMenu3.ResumeButton')
    b = l77_button(c, button_name, 'Item_' + key, l77_bstyle(None, None, l77_a(L77_PAPER, 0.35), l77_a(L77_INK, 0.7)))
    if src is not None:
        l77_copy(src, b, ('widget_style',), 'word')
    l77_box(c, button_name, h='f', v='f')
    return b


def l77_chip(c, key, parent, label, button_name, size=24, label_name=None):
    """archetype C (mm3 chip): Item_<key> Overlay > Graffiti_ (ring), Button with its TextBlock (Use Foreground)"""
    l77_add(c, 'Overlay', 'Item_' + key, parent)
    l77_xform(c.w['Item_' + key])
    l77_graffiti(c, key, 'Item_' + key, 'ring', (14, 8, 14, 8))
    b = l77_button(c, button_name, 'Item_' + key, l77_bstyle(l77_brush(L77_INK), l77_brush(L77_YHOT), l77_brush(L77_YPRESS), l77_brush(L77_COAL),
                                                              pad=(18, 6, 22, 6), fg=L77_YELLOW, hfg=L77_INK, pfg=L77_INK, dfg=L77_GREY))
    src = L77_SRC.get('WBP_PauseMenu3.CopyCodeButton')
    if src is not None:
        l77_copy(src, b, ('widget_style',), 'chip')
    l77_box(c, button_name, h='f', v='f')
    ln = label_name or ('Label_' + key)
    t = l77_text(c, ln, button_name, label, l77_font('F_Bebas', size, letter=40), L77_YELLOW, var=bool(label_name), just='center', hit=True)
    lsrc = L77_SRC.get('WBP_PauseMenu3.Label_CopyCode')
    if lsrc is not None:
        l77_copy(lsrc, t, ('color_and_opacity',), 'chip label')
    else:
        sc = unreal.SlateColor()
        sc.set_editor_property('color_use_rule', unreal.SlateColorStylingMode.USE_COLOR_FOREGROUND)
        t.set_editor_property('color_and_opacity', sc)
    return b


def l77_combo(c, name, parent, w=300, h=52):
    l77_sizebox(c, 'Box_' + name, parent, w=w, h=h)
    cb = l77_add(c, 'Combo', name, 'Box_' + name, True)
    src = L77_SRC.get('WBP_MainMenu3.HostRulesComboBox')
    if src is not None and l77_copy(src, cb, ('font', 'foreground_color', 'content_padding', 'max_list_height', 'enable_gamepad_navigation_mode',
                                              'widget_style', 'item_style'), 'combo'):
        return cb
    R77['fallback'].append('%s: mm3 flat combo style' % name)
    cb.set_editor_property('font', l77_font('F_Barlow', 22, 'SemiBold'))
    cb.set_editor_property('foreground_color', l77_sc(L77_PAPER))
    cb.set_editor_property('content_padding', l77_m(20, 8, 12, 8))
    cb.set_editor_property('max_list_height', 420.0)
    try:
        ws = cb.get_editor_property('widget_style')
        bs = ws.get_editor_property('combo_button_style')
        bb = bs.get_editor_property('button_style')
        for k, col in (('normal', L77_INK), ('hovered', L77_COAL2), ('pressed', L77_YELLOW), ('disabled', L77_COAL)):
            bb.set_editor_property(k, l77_brush(col))
        bb.set_editor_property('disabled_foreground', l77_sc(L77_GREY))
        bs.set_editor_property('button_style', bb)
        bs.set_editor_property('menu_border_brush', l77_brush(L77_INK))
        ws.set_editor_property('combo_button_style', bs)
        cb.set_editor_property('widget_style', ws)
        ist = cb.get_editor_property('item_style')
        ist.set_editor_property('even_row_background_brush', l77_brush(L77_INK))
        ist.set_editor_property('odd_row_background_brush', l77_brush(L77_COAL))
        ist.set_editor_property('even_row_background_hovered_brush', l77_brush(L77_YDIM))
        ist.set_editor_property('odd_row_background_hovered_brush', l77_brush(L77_YDIM))
        ist.set_editor_property('active_brush', l77_brush(L77_YELLOW))
        ist.set_editor_property('active_hovered_brush', l77_brush(L77_YHOT))
        ist.set_editor_property('text_color', l77_sc(L77_PAPER))
        ist.set_editor_property('selected_text_color', l77_sc(L77_INK))
        cb.set_editor_property('item_style', ist)
    except Exception:  # noqa: BLE001
        R77['log'].append(('combo style', name, traceback.format_exc().strip().splitlines()[-1]))
    return cb


def l77_check(c, name, parent):
    l77_sizebox(c, 'Box_' + name, parent, w=40, h=40)
    cb = l77_add(c, 'Check', name, 'Box_' + name, True)
    src = L77_SRC.get('WBP_MainMenu3.ShowFullLobbiesCheckBox')
    if src is not None and l77_copy(src, cb, ('widget_style',), 'check'):
        return cb
    R77['fallback'].append('%s: mm3 flat check style' % name)
    try:
        st = cb.get_editor_property('widget_style')
        for k, col in (('unchecked_image', L77_INK), ('unchecked_hovered_image', L77_COAL2), ('unchecked_pressed_image', L77_YPRESS),
                       ('checked_image', L77_YELLOW), ('checked_hovered_image', L77_YHOT), ('checked_pressed_image', L77_YPRESS)):
            st.set_editor_property(k, l77_brush(col, size=(40, 40)))
        cb.set_editor_property('widget_style', st)
    except Exception:  # noqa: BLE001
        R77['log'].append(('check style', name, traceback.format_exc().strip().splitlines()[-1]))
    return cb


def l77_scroll(c, name, parent):
    s = l77_add(c, 'Scroll', name, parent)
    try:
        s.set_editor_property('scrollbar_thickness', unreal.Vector2D(6, 6))
        bs = s.get_editor_property('widget_bar_style')
        bs.set_editor_property('normal_thumb_image', l77_brush(L77_YELLOW))
        bs.set_editor_property('hovered_thumb_image', l77_brush(L77_YHOT))
        bs.set_editor_property('vertical_background_image', l77_brush(L77_COAL2))
        s.set_editor_property('widget_bar_style', bs)
    except Exception:  # noqa: BLE001
        R77['log'].append(('scroll style', name, traceback.format_exc().strip().splitlines()[-1]))
    return s


def l77_label(c, name, parent, s):
    """a rules cell's label (Txt_HostRules' look when WBP_MainMenu3 has it)"""
    t = l77_text(c, name, parent, s, l77_font('F_Bebas', 24, letter=40), L77_YELLOW)
    src = L77_SRC.get('WBP_MainMenu3.Txt_HostRules')
    if src is not None:
        l77_copy(src, t, ('shadow_offset', 'shadow_color_and_opacity'), 'label')
    return t


def l77_cell(c, key, parent, label, combo_name, w):
    """one rules cell: the label above its combo box"""
    l77_add(c, 'VBox', 'Cell_' + key, parent)
    l77_box(c, 'Cell_' + key, pad=l77_m(0, 0, 28, 0), v='t', size='auto')
    l77_label(c, 'Txt_' + key, 'Cell_' + key, label)
    l77_box(c, 'Txt_' + key, pad=l77_m(0, 0, 0, 4), h='l')
    l77_combo(c, combo_name, 'Cell_' + key, w=w)
    l77_box(c, 'Box_' + combo_name, h='l')


def l77_checkcell(c, key, parent, label, check_name):
    l77_add(c, 'HBox', 'Cell_' + key, parent)
    l77_box(c, 'Cell_' + key, pad=l77_m(0, 0, 40, 0), v='c', size='auto')
    l77_check(c, check_name, 'Cell_' + key)
    l77_box(c, 'Box_' + check_name, v='c', size='auto')
    l77_label(c, 'Txt_' + key, 'Cell_' + key, label)
    l77_box(c, 'Txt_' + key, pad=l77_m(12, 0, 0, 0), v='c', size='auto')


# ------------------------------------------------------------------------------------------------- the two WBPs
def l77_build_row():
    """WBP_LobbyPlayerRow3 (H 60), after WBP_SessionPlayerRow3"""
    c = l77_make(L77_ROW, L77_PARENT_ROW)
    l77_sizebox(c, 'RowSize', None, h=60)
    l77_add(c, 'Overlay', 'RowRoot', 'RowSize')
    plate = l77_image(c, 'Img_RowPlate', 'RowRoot', L77_COAL)
    src = L77_SRC.get('WBP_SessionPlayerRow3.Img_RowPlate')
    if src is not None:
        l77_copy(src, plate, ('brush', 'color_and_opacity'), 'row plate')
    l77_box(c, 'Img_RowPlate')
    l77_add(c, 'Overlay', 'LocalHighlight', 'RowRoot', var=True)
    l77_box(c, 'LocalHighlight')
    l77_vis(c.w['LocalHighlight'], 'hit')
    l77_image(c, 'Img_LocalFill', 'LocalHighlight', l77_a(L77_YELLOW, 0.14))
    l77_box(c, 'Img_LocalFill')
    l77_image(c, 'Img_LocalNotch', 'LocalHighlight', L77_YELLOW, size=(8, 60))
    l77_box(c, 'Img_LocalNotch', h='l')
    l77_add(c, 'HBox', 'Cols', 'RowRoot')
    l77_box(c, 'Cols', pad=l77_m(22, 0, 10, 0), v='c')
    for n, w, s, fnt, col, sname in (('PlayerNameText', 250, 'Player name', l77_font('F_Barlow', 26, 'Bold'), L77_PAPER, 'PlayerNameText'),
                                     ('StatusText', 160, 'NOT READY', l77_font('F_Bebas', 24, letter=40), L77_YELLOW, None),
                                     ('PingText', 80, '42 ms', l77_font('F_Barlow', 20, 'SemiBold'), L77_GREYL, 'PingText')):
        l77_sizebox(c, 'Col_' + n, 'Cols', w=w)
        l77_box(c, 'Col_' + n, v='c', size='auto')
        t = l77_text(c, n, 'Col_' + n, s, fnt, col, var=True)
        if sname and L77_SRC.get('WBP_SessionPlayerRow3.' + sname) is not None:
            l77_copy(L77_SRC['WBP_SessionPlayerRow3.' + sname], t, ('font',), 'row text')
    l77_add(c, 'Spacer', 'Gap', 'Cols')
    l77_box(c, 'Gap', size=1.0)
    l77_chip(c, 'Move', 'Cols', 'TO ORANGE', 'MoveButton', size=20, label_name='MoveText')
    l77_box(c, 'Item_Move', v='c', size='auto')
    ok = l77_finish(c)
    return c, ok


def l77_build_lobby():
    """WBP_Lobby3: canvas root; CompactPanel / CountdownText / CountdownHintText / MessageText over the game; LobbyPanel
    a 1640 x 960 card in the middle (6.2's layout)"""
    c = l77_make(L77_LOBBY, L77_PARENT_LOBBY)
    l77_add(c, 'Canvas', 'Root', None)
    l77_vis(c.w['Root'], 'self')

    # --- the compact strip, top centre (the match HUD's bar hides in phase Lobby; the strip hides in the countdown, when the
    #     bar shows there)
    b = l77_add(c, 'Border', 'CompactPanel', 'Root', var=True)
    l77_canvas(c, 'CompactPanel', 0, 20, anchor=(0.5, 0, 0.5, 0), align=(0.5, 0), auto=True)
    b.set_editor_property('background', l77_brush(l77_a(L77_INK, 0.88)))
    b.set_editor_property('padding', l77_m(26, 8, 26, 8))
    l77_vis(b, 'hit')
    l77_text(c, 'CompactText', 'CompactPanel', 'LOBBY   BLUE 2 - ORANGE 1   1 NOT READY   Esc: lobby', l77_font('F_Bebas', 28, letter=40), L77_YELLOW, var=True)

    # --- the countdown, large, centre (both views)
    l77_text(c, 'CountdownText', 'Root', 'MATCH STARTS IN 5', l77_font('F_Anton', 110, letter=20, outline=4), L77_YELLOW, var=True, just='center')
    l77_canvas(c, 'CountdownText', 0, 0, anchor=(0.5, 0.28, 0.5, 0.28), align=(0.5, 0.5), auto=True, z=2)
    l77_text(c, 'CountdownHintText', 'Root', 'Esc: lobby', l77_font('F_Bebas', 32, letter=40), L77_PAPER, var=True, just='center', shadow=(2, 2))
    l77_canvas(c, 'CountdownHintText', 0, 90, anchor=(0.5, 0.28, 0.5, 0.28), align=(0.5, 0), auto=True, z=2)

    # --- the lobby message (refusals, the zone, swaps)
    l77_text(c, 'MessageText', 'Root', 'Stay in the lobby', l77_font('F_Barlow', 28, 'Bold'), L77_YELLOW, var=True, just='center', shadow=(2, 2))
    l77_canvas(c, 'MessageText', 0, 0, anchor=(0.5, 0.86, 0.5, 0.86), align=(0.5, 0.5), auto=True, z=3)

    # --- the panel: a tilted-free card (yellow shadow, yellow edge, ink fill), content upright on top
    p = l77_add(c, 'Overlay', 'LobbyPanel', 'Root', var=True)
    l77_canvas(c, 'LobbyPanel', 0, 0, 1640, 960, anchor=(0.5, 0.5, 0.5, 0.5), align=(0.5, 0.5), z=1)
    l77_image(c, 'Img_PanelShadow', 'LobbyPanel', L77_YELLOW)
    l77_box(c, 'Img_PanelShadow', pad=l77_m(14, 14, -14, -14))
    e = l77_add(c, 'Border', 'Img_PanelEdge', 'LobbyPanel')
    l77_box(c, 'Img_PanelEdge')
    e.set_editor_property('background', l77_brush(L77_YELLOW))
    e.set_editor_property('padding', l77_m(6))
    # Visible: the plate takes the clicks (they must not reach the game while the panel has the input)
    f = l77_image(c, 'Img_PanelFill', 'Img_PanelEdge', l77_a(L77_INK, 0.96), hit=False)
    l77_add(c, 'VBox', 'PanelContent', 'LobbyPanel')
    l77_box(c, 'PanelContent', pad=l77_m(48, 34, 48, 30))

    # header: LOBBY tag, lobby name, join code + COPY
    l77_add(c, 'HBox', 'HeaderRow', 'PanelContent')
    l77_box(c, 'HeaderRow', size='auto')
    l77_add(c, 'Overlay', 'Wrap_LobbyTag', 'HeaderRow')
    l77_box(c, 'Wrap_LobbyTag', v='c', size='auto')
    l77_xform(c.w['Wrap_LobbyTag'], angle=-3)
    l77_image(c, 'Img_LobbyTag', 'Wrap_LobbyTag', L77_YELLOW)
    l77_box(c, 'Img_LobbyTag')
    l77_text(c, 'Txt_LobbyTitle', 'Wrap_LobbyTag', 'LOBBY', l77_font('F_Anton', 54, letter=20), L77_INK)
    l77_box(c, 'Txt_LobbyTitle', pad=l77_m(24, 2, 28, 2))
    l77_text(c, 'TitleText', 'HeaderRow', "Talal's lobby", l77_font('F_Barlow', 30, 'Bold'), L77_PAPER, var=True)
    l77_box(c, 'TitleText', pad=l77_m(30, 0, 20, 0), v='c', size=1.0)
    # Wrap_Code holds the CODE label, the code and COPY: UMyLobbyWidget::SetButtonShown(CopyCodeButton) hides all three
    # without a session (it collapses the button's outermost Item_ / Wrap_ parent that holds no other button)
    l77_add(c, 'HBox', 'Wrap_Code', 'HeaderRow')
    l77_box(c, 'Wrap_Code', v='c', size='auto')
    l77_text(c, 'Txt_Code', 'Wrap_Code', 'CODE', l77_font('F_Bebas', 26, letter=40), L77_YELLOW)
    l77_box(c, 'Txt_Code', pad=l77_m(0, 0, 12, 0), v='c', size='auto')
    l77_text(c, 'JoinCodeText', 'Wrap_Code', 'K7Q2PX', l77_font('F_RubikMono', 32), L77_PAPER, var=True)
    l77_box(c, 'JoinCodeText', pad=l77_m(0, 0, 18, 0), v='c', size='auto')
    l77_chip(c, 'CopyCode', 'Wrap_Code', 'COPY', 'CopyCodeButton')
    l77_box(c, 'Item_CopyCode', v='c', size='auto')

    # teams: two columns
    l77_add(c, 'HBox', 'TeamsRow', 'PanelContent')
    l77_box(c, 'TeamsRow', pad=l77_m(0, 22, 0, 0), size='auto')
    for i, (team, label) in enumerate((('Blue', 'BLUE  2 / 2'), ('Orange', 'ORANGE  1 / 2'))):
        col = team + 'Column'
        l77_add(c, 'VBox', col, 'TeamsRow')
        l77_box(c, col, pad=l77_m(0 if i == 0 else 12, 0, 12 if i == 0 else 0, 0), size=1.0)
        l77_text(c, team + 'HeaderText', col, label, l77_font('F_Anton', 38, letter=20), L77_PAPER, var=True)
        l77_box(c, team + 'HeaderText', pad=l77_m(0, 0, 0, 6), h='l')
        l77_sizebox(c, 'Box_' + team + 'List', col, h=272)
        l77_box(c, 'Box_' + team + 'List', h='f')
        l77_scroll(c, 'Scroll_' + team, 'Box_' + team + 'List')
        l77_add(c, 'VBox', team + 'List', 'Scroll_' + team, var=True)
    l77_add(c, 'HBox', 'SwitchRow', 'PanelContent')
    l77_box(c, 'SwitchRow', pad=l77_m(0, 10, 0, 0), size='auto')
    l77_chip(c, 'SwitchTeam', 'SwitchRow', 'SWITCH TO ORANGE', 'SwitchTeamButton', label_name='SwitchTeamText')
    l77_box(c, 'Item_SwitchTeam', v='c', size='auto')

    # rules
    l77_add(c, 'VBox', 'RulesPanel', 'PanelContent', var=True)
    l77_box(c, 'RulesPanel', pad=l77_m(0, 22, 0, 0), size='auto')
    l77_add(c, 'HBox', 'RulesHeaderRow', 'RulesPanel')
    l77_box(c, 'RulesHeaderRow', pad=l77_m(0, 0, 0, 8), size='auto')
    l77_text(c, 'Txt_Rules', 'RulesHeaderRow', 'RULES', l77_font('F_Anton', 34, letter=20), L77_YELLOW)
    l77_box(c, 'Txt_Rules', v='c', size='auto')
    l77_text(c, 'RulesHintText', 'RulesHeaderRow', 'Set by the host', l77_font('F_Barlow', 20, 'Medium'), L77_GREYL, var=True)
    l77_box(c, 'RulesHintText', pad=l77_m(22, 0, 0, 0), v='c', size=1.0)
    l77_add(c, 'HBox', 'RulesCells', 'RulesPanel')
    l77_box(c, 'RulesCells', size='auto')
    for key, label, name, w in (('TeamMode', 'TEAMS', 'TeamModeComboBox', 400), ('ShipLives', 'SHIP LIVES', 'ShipLivesComboBox', 150),
                                ('Swarm', 'SWARM', 'SwarmComboBox', 230), ('MaxPlayers', 'MAX PLAYERS', 'MaxPlayersComboBox', 150),
                                ('TimeLimit', 'TIME LIMIT', 'TimeLimitComboBox', 190)):
        l77_cell(c, key, 'RulesCells', label, name, w)
    l77_add(c, 'HBox', 'ChecksRow', 'RulesPanel')
    l77_box(c, 'ChecksRow', pad=l77_m(0, 14, 0, 0), size='auto')
    for key, label, name in (('FriendlyFire', 'FRIENDLY FIRE', 'FriendlyFireCheckBox'), ('GrappleShips', 'SHIP HOOK', 'GrappleShipsCheckBox'),
                             ('LaneAssist', 'LANE ASSIST', 'LaneAssistCheckBox')):
        l77_checkcell(c, key, 'ChecksRow', label, name)

    # actions: READY (clients) CLOSE MENU LEAVE ........ START (host) + its reason
    l77_add(c, 'Spacer', 'ActionsGap', 'PanelContent')
    l77_box(c, 'ActionsGap', size=1.0)
    l77_add(c, 'HBox', 'ActionsRow', 'PanelContent')
    l77_box(c, 'ActionsRow', pad=l77_m(0, 12, 0, 0), size='auto')
    l77_word(c, 'Ready', 'ActionsRow', 'READY', 'ReadyButton', size=46, color=L77_PAPER, h=84, label_name='ReadyText')
    l77_box(c, 'Wrap_Ready', pad=l77_m(0, 0, 30, 0), v='c', size='auto')
    for key, label, name in (('Close', 'CLOSE', 'CloseButton'), ('Menu', 'MENU', 'MenuButton'), ('Leave', 'LEAVE', 'LeaveButton')):
        l77_chip(c, key, 'ActionsRow', label, name, size=26)
        l77_box(c, 'Item_' + key, pad=l77_m(0, 0, 20, 0), v='c', size='auto')
    l77_add(c, 'Spacer', 'StartGap', 'ActionsRow')
    l77_box(c, 'StartGap', size=1.0)
    l77_add(c, 'VBox', 'StartColumn', 'ActionsRow')
    l77_box(c, 'StartColumn', h='r', v='c', size='auto')
    l77_word(c, 'Start', 'StartColumn', 'START 2v1', 'StartButton', size=56, color=L77_PAPER, h=96, label_name='StartText')
    l77_box(c, 'Wrap_Start', h='r', size='auto')
    l77_text(c, 'StartReasonText', 'StartColumn', '1 not ready - click again to start anyway', l77_font('F_Barlow', 20, 'Medium'), L77_PAPER,
             var=True, just='right')
    l77_box(c, 'StartReasonText', pad=l77_m(0, 2, 6, 0), h='r', size='auto')
    ok = l77_finish(c)
    return c, ok


def l77_set_cdo(path, values):
    bp = unreal.load_asset(path)
    cdo = unreal.get_default_object(bp.generated_class())
    return unreal.ToolsetLibrary.set_object_properties(cdo, json.dumps(values))


def l77_verify(path, names):
    """the 6.3 names in the WBP: (missing, wrong class, not variables); a variable flag the tool doesn't report counts as unknown"""
    W = l77_widgets(l77_ref(path))
    miss, wrong, novar = [], [], []
    for n, cls in names.items():
        if n not in W:
            miss.append(n)
            continue
        w, info = W[n]
        want = getattr(unreal, cls, None)
        if want is not None and not isinstance(w, want):
            wrong.append('%s is %s, want %s' % (n, w.get_class().get_name(), cls))
        isvar = info.get('bIsVariable', info.get('isVariable'))
        if isvar is None:
            try:
                isvar = bool(w.get_editor_property('is_variable'))
            except Exception:  # noqa: BLE001
                isvar = None
        if isvar is False:
            novar.append(n)
    return miss, wrong, novar


def l77_backup(path):
    a = unreal.load_asset(path)
    src = unreal.SystemLibrary.get_system_path(a) if a is not None else ''
    if src and os.path.exists(src):
        os.makedirs(os.path.join(L77_OUT, 'backup'), exist_ok=True)
        bk = os.path.join(L77_OUT, 'backup', '%s_before_as77_%s.uasset' % (path.split('/')[-1], time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())))
        shutil.copyfile(src, bk)
        R77.setdefault('backups', []).append(bk)
        o77('INFO', 'backup %s' % bk)


def l77_main():
    g = globals()
    dry, rebuild = bool(g.get('AS77_DRY')), bool(g.get('AS77_REBUILD'))
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        o77('FAIL', 'PIE is running: asset scripts freeze the game thread then; run it with the editor idle')
        return False
    for cls in (L77_PARENT_LOBBY, L77_PARENT_ROW):
        if unreal.load_class(None, cls) is None:
            o77('FAIL', '%s not found: the PR B lobby C++ (UMyLobbyWidget) is not built into this editor' % cls)
            return False
    have = [unreal.EditorAssetLibrary.does_asset_exist(p) for p in (L77_LOBBY, L77_ROW)]
    if all(have) and not rebuild:
        for p, names in ((L77_LOBBY, L77_LOBBY_NAMES), (L77_ROW, L77_ROW_NAMES)):
            unreal.load_asset(p)
            miss, wrong, novar = l77_verify(p, names)
            R77[p.split('/')[-1]] = {'missing': miss, 'wrong_class': wrong, 'not_variable': novar}
            o77('PASS' if not (miss or wrong or novar) else 'WARN', '%s exists: missing %s, wrong class %s, not variables %s' % (p, miss, wrong, novar))
        o77('INFO', 'both widgets exist: nothing built (AS77_REBUILD = True rebuilds them in place)')
        return True
    if dry:
        o77('INFO', 'DRY RUN: would build %s (exists %s) and %s (exists %s) with the 6.3 names, set PlayerRowClass and ButtonFX, '
                    'compile and save both' % (L77_ROW, have[1], L77_LOBBY, have[0]))
        return True
    for p, h in zip((L77_LOBBY, L77_ROW), have):
        if h:
            l77_backup(p)
    l77_sources()
    l77_slabs()
    o77('INFO', 'style sources %s; slabs %s' % (sorted(L77_SRC), dict((k, v is not None) for k, v in L77_SLABS.items())))
    rc, rok = l77_build_row()
    lc, lok = l77_build_lobby()
    cdo = l77_set_cdo(L77_LOBBY, {'PlayerRowClass': L77_ROW + '.' + L77_ROW.split('/')[-1] + '_C',
                                  'ButtonFX': {'HoverScale': 1.12, 'HoverKick': 4.0, 'RestTilt': 1.5, 'Wobble': 0.6,
                                               'HoverTextColor': {'r': 0.0033, 'g': 0.0033, 'b': 0.0033, 'a': 1.0}}})
    lok2 = l77_tool('CompileWidgetBlueprint', {'widgetBlueprint': lc.ref})
    saved = [unreal.EditorAssetLibrary.save_asset(p, only_if_is_dirty=False) for p in (L77_ROW, L77_LOBBY)]
    R77.update({'row_compiled': rok, 'lobby_compiled': [lok, lok2], 'cdo_set': cdo, 'saved': saved,
                'row_widgets': len(rc.w), 'lobby_widgets': len(lc.w)})
    bad = False
    for p, names in ((L77_LOBBY, L77_LOBBY_NAMES), (L77_ROW, L77_ROW_NAMES)):
        miss, wrong, novar = l77_verify(p, names)
        R77[p.split('/')[-1]] = {'missing': miss, 'wrong_class': wrong, 'not_variable': novar}
        bad = bad or bool(miss or wrong)
        o77('PASS' if not (miss or wrong or novar) else 'FAIL', '%s: %d names of 6.3, missing %s, wrong class %s, not variables %s' % (
            p, len(names), miss, wrong, novar))
    try:
        cls = unreal.load_class(None, L77_LOBBY + '.' + L77_LOBBY.split('/')[-1] + '_C')
        prc = unreal.get_default_object(cls).get_editor_property('PlayerRowClass') if cls else None
        R77['player_row_class'] = prc.get_path_name() if prc else None
        o77('PASS' if prc else 'FAIL', 'WBP_Lobby3 PlayerRowClass = %s' % R77['player_row_class'])
        bad = bad or not prc
    except Exception:  # noqa: BLE001
        o77('WARN', 'PlayerRowClass not readable: %s' % traceback.format_exc().strip().splitlines()[-1])
    o77('INFO', 'copied styles: %d, fallbacks: %s' % (len(R77['copied']), R77['fallback']))
    o77('PASS' if all(saved) and not bad else 'FAIL', 'built %s (%d widgets) and %s (%d widgets), saved %s' % (
        L77_LOBBY, len(lc.w), L77_ROW, len(rc.w), saved))
    return all(saved) and not bad


try:
    os.makedirs(L77_OUT, exist_ok=True)
    _ok77 = l77_main()
    with open(os.path.join(L77_OUT, 'as_77_lobby_widget.json'), 'w') as _f:
        json.dump(R77, _f, indent=1, default=str)
    print('RESULT: %s' % ('OK' if _ok77 else 'FAIL'))
except Exception:  # noqa: BLE001
    R77['error'] = traceback.format_exc()
    with open(os.path.join(L77_OUT, 'as_77_lobby_widget.json'), 'w') as _f:
        json.dump(R77, _f, indent=1, default=str)
    print('RESULT: FAIL %s' % R77['error'])
