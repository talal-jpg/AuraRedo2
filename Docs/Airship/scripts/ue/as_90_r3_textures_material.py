# as_90_r3_textures_material.py - round 3 (Docs/Airship/round3/EXPORT_R3.md section 2, EDITOR_STAGE_R3.md step 1):
# the ink textures and the palette + ink material of the detailed ship. Run it FIRST (as_91 .. as_93 need its assets).
#   1. imports SourceArt/Airship/textures/r3/*.png (staged by SourceArt/Airship/scripts/r3_unreal_inputs.py, md5 checked) as
#      /Game/Assets/MyShip/Drivable/Textures/T_AirshipR3_HullInk / _DetailInk_H / _DetailInk_M / _PropsInk (linear: sRGB
#      off, TC_BC7 [AS90_INK_COMPRESSION], clamp, World group, mips) and T_AirshipR3_HullComicMask (Talal's round 2 comic
#      mask on his UVs: linear, TC_Masks, clamp). Re-imports over its own textures; refuses an asset of that name that is
#      not a Texture2D or came from another file.
#   2. builds the master material /Game/Assets/MyShip/Drivable/Materials/M_AirshipR3 (opaque, Default Lit) with
#      MaterialEditingLibrary:
#        colour = 24 vector parameters Pal_00_paint_yellow .. Pal_23_spare_23, picked by round(TexCoord[1].x) (Custom node
#                 R3Palette; the palette index the export wrote per face into UV1);
#        ink    = texture InkTex on TexCoord[0] (static switch InkOnUV2: TexCoord[2], the hull MI), signed distance
#                 d = R * (InkDistMax + InkDistNeg) - InkDistNeg (cm), drawn InkPxNear 2.2 px near -> InkPxFar 1.2 px from
#                 InkFarStart 4000 to InkFarEnd 12000 cm, at least InkMinHalfWidth 0.2 cm, from PixelDepth and the view's
#                 TanHalfFieldOfView / ViewSize (Custom node R3InkLine: works under Nanite, no DDX/DDY);
#        dots   = G (static switch HasDots) lerps to Pal_10_bolt; Talal's comic mask (static switch HasComic, ComicAmount
#                 0) on TexCoord[0]; c = lerp(colour, InkColor #1C2230, max(line, comic, silhouette) * InkOpacity);
#        Roughness 0.9 (M_Airship's value, a parameter), Specular 0.5, Metallic 0; usage: skeletal mesh + Nanite.
#      v2 (2026-11-28, review fixes; EXPORT_R3.md section 15):
#        line   the core shrinks so the anti-alias band w +- px/2 ends at InkDistMax (far ships got a navy tint: a texel
#               with no line within 12 cm drew 45 % ink at 200 m), a saturated texel (R >= 0.996) draws none, and an
#               optional far fade InkFadeStart / InkFadeEnd -> InkOpacityFar (default 1 = no fade);
#        look   BaseColor = c * LitMix; Emissive = EyeAdaptationInverse(max(Sat(c, LiftSat), 0) * ShadeLift, LiftLock):
#               StartupMap's blue moon and cyan sky light turned the plain lit yellow green and the rust slate grey;
#               defaults LitMix 0.5, ShadeLift 0.55, LiftSat 1.3 from r3_shade_calib.py (export_shade_calib.json, = the
#               inputs' 'look'); LitMix 1 + ShadeLift 0 = v1;
#        silhouette  static switch HasSilhouette (default OFF, on MI_AirshipR3_Look: one switch for the whole ship): the
#               project's material-only silhouette (icelook CN_InkSilhouette: (N.V)^2 / fwidth on the vertex normal),
#               SilWidthPx 2.4 px (the approved renders' Freestyle width), faded out between SilFadeStart 6000 and
#               SilFadeEnd 12000 cm, SilMinSlope 0.02 (no line where N.V changes less per pixel: the deck rim seen
#               edge-on drew a thick jagged band);
#        textures  the four ink textures sample TRILINEAR (AS90_INK_FILTER): TEXTUREGROUP_World is aniso + MipFilter=point
#               (BaseDeviceProfiles.ini), which Vulkan maps to VK_SAMPLER_MIPMAP_MODE_NEAREST, so the decoded distance
#               jumped at mip boundaries; HasComic is OFF on MI_AirshipR3_Hull (the mask is not re-baked at the base
#               edits; turn it on together with ComicAmount > 0).
#      A comment box carries the version (AS90_VERSION). If M_AirshipR3 exists with this version it is only checked; with
#      another version or edits the script stops (FAIL) and says how to rebuild it (move the .uasset aside with the editor
#      closed: deleting the expressions of a material loaded from disk is the call that crashed UE for functions).
#   3. material instances: MI_AirshipR3_Look (child of M_AirshipR3: the palette and ink knobs, every value set explicitly so
#      Talal tunes the colours in ONE place) and its four children (textures + static switches only):
#        MI_AirshipR3_Hull       T_AirshipR3_HullInk on UV2, dots, comic mask switch OFF (v2), TWO SIDED (FULL.md: the
#                                base model shows backfaces round the pods)    -> SK_Airship slot 0 (as_91)
#        MI_AirshipR3_Moving     T_AirshipR3_DetailInk_M, dots                 -> SK_Airship slot 2 (as_91)
#        MI_AirshipR3_HullDetail T_AirshipR3_DetailInk_H, dots                 -> SM_AirshipR3_HullDetail (as_91b)
#        MI_AirshipR3_Props      T_AirshipR3_PropsInk, no dots                 -> SK_Airship slot 1 + both turrets (as_91 /
#                                                                                  as_91c; the props recolour, slots 17-19)
#      Palette defaults = r3_unreal_inputs.json (= manifest.json, linear, Blender's values 1:1); keel block slot 16 rust.
#   4. compiles (errors FAIL), reads every parameter back, saves ONLY these 10 assets by explicit path (nothing when a FAIL),
#      checks Talal's M_Airship / T_Airship_* / SM_Airship untouched. Backups first: Saved/Airship/backup_r3/.
# Knobs (globals set before the exec, or edit here): AS90_INK_COMPRESSION ('TC_BC7'; 'TC_VECTOR_DISPLACEMENTMAP' = 8-bit
# uncompressed, 4x the memory, if BC7 blocks show on the lines); AS90_INK_FILTER ('TF_TRILINEAR'; 'TF_DEFAULT' = the
# texture group's filter, e.g. with AS90_INK_LOD_GROUP = 'TEXTUREGROUP_PROJECT01' once Config/DefaultDeviceProfiles.ini
# defines that group as MinMagFilter=aniso, MipFilter=linear: anisotropic AND blended mips, EDITOR_STAGE_R3.md 3).
# Run (clone editor, no PIE): Docs/Airship/scripts/harness/inbox.sh 90 Docs/Airship/scripts/ue/as_90_r3_textures_material.py 600
# Report: Saved/Airship/as_90_r3_textures_material.json
import json, os, traceback  # unreal = inbox namespace
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_9x_r3lib.py')).read())

AS90_VERSION = 'as_90 M_AirshipR3 v2 (2026-11-28 review fixes)'
AS90_INK_COMPRESSION = globals().pop('AS90_INK_COMPRESSION', 'TC_BC7')
AS90_INK_FILTER = globals().pop('AS90_INK_FILTER', 'TF_TRILINEAR')
AS90_INK_LOD_GROUP = globals().pop('AS90_INK_LOD_GROUP', 'TEXTUREGROUP_WORLD')
AS90_LOOK_DEFAULT = {'LitMix': 0.5, 'ShadeLift': 0.55, 'LiftSat': 1.3, 'LiftLock': 1.0}   # = inputs['look'] (checked)
AS90_R = r3_report('as_90_r3_textures_material')
AS90_TEXFILES = {'hull': 'T_AirshipR3_HullInk.png', 'H': 'T_AirshipR3_DetailInk_H.png', 'M': 'T_AirshipR3_DetailInk_M.png',
                 'P': 'T_AirshipR3_PropsInk.png', 'comic': 'T_AirshipR3_HullComicMask.png'}
AS90_SCALARS = [('InkDistMax', 12.0, 'Ink'), ('InkDistNeg', 2.0, 'Ink'), ('InkPxNear', 2.2, 'Ink'), ('InkPxFar', 1.2, 'Ink'),
                ('InkFarStart', 4000.0, 'Ink'), ('InkFarEnd', 12000.0, 'Ink'), ('InkMinHalfWidth', 0.2, 'Ink'),
                ('InkOpacity', 1.0, 'Ink'), ('ComicAmount', 0.0, 'Ink'), ('Roughness', 0.9, 'Shading'),
                ('Specular', 0.5, 'Shading'), ('Metallic', 0.0, 'Shading'),
                ('InkFadeStart', 20000.0, 'Ink'), ('InkFadeEnd', 40000.0, 'Ink'), ('InkOpacityFar', 1.0, 'Ink'),
                ('LitMix', AS90_LOOK_DEFAULT['LitMix'], 'Look'), ('ShadeLift', AS90_LOOK_DEFAULT['ShadeLift'], 'Look'),
                ('LiftSat', AS90_LOOK_DEFAULT['LiftSat'], 'Look'), ('LiftLock', AS90_LOOK_DEFAULT['LiftLock'], 'Look'),
                ('SilWidthPx', 2.4, 'Silhouette'), ('SilFadeStart', 6000.0, 'Silhouette'), ('SilFadeEnd', 12000.0, 'Silhouette'),
                ('SilMinSlope', 0.02, 'Silhouette')]
AS90_SWITCHES = {'InkOnUV2': False, 'HasDots': True, 'HasComic': False, 'HasSilhouette': False}
AS90_LOOK_SWITCHES = {'HasSilhouette': False}     # set on MI_AirshipR3_Look: the four children inherit it
AS90_MI_SETUP = {   # key: (ink texture key, switches, two sided)
    'hull': ('hull', {'InkOnUV2': True, 'HasDots': True, 'HasComic': False}, True),
    'moving': ('M', {'InkOnUV2': False, 'HasDots': True, 'HasComic': False}, False),
    'hulldetail': ('H', {'InkOnUV2': False, 'HasDots': True, 'HasComic': False}, False),
    'props': ('P', {'InkOnUV2': False, 'HasDots': False, 'HasComic': False}, False),
}


def _o90(tag, msg):
    r3_o(AS90_R, tag, msg)


def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


AS90_INK_LIN = [_srgb_to_lin(int('1C2230'[i:i + 2], 16) / 255.0) for i in (0, 2, 4)]


def _pal_name(i, slot):
    return 'Pal_%02d_%s' % (i, slot)


def as90_textures(eal, inp):
    out = {}
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    for key, fn in AS90_TEXFILES.items():
        path = R3_TEX[key]
        png = os.path.join(R3_TEXSRC, fn)
        if eal.does_asset_exist(path):
            old = eal.load_asset(path)
            if not isinstance(old, unreal.Texture2D):
                _o90('FAIL', '%s exists and is a %s: not touched' % (path, type(old).__name__))
                return None
            src = ''
            try:
                src = old.get_editor_property('asset_import_data').get_first_filename()
            except Exception:  # noqa: BLE001
                pass
            if src and os.path.basename(src) != fn:
                _o90('FAIL', '%s was imported from %s, not %s: not ours, not touched' % (path, src, fn))
                return None
        t = unreal.AssetImportTask()
        for k, v in (('filename', png), ('destination_path', R3_TEXD), ('destination_name', path.rsplit('/', 1)[1]),
                     ('automated', True), ('replace_existing', True), ('save', False)):
            t.set_editor_property(k, v)
        tools.import_asset_tasks([t])
        tex = eal.load_asset(path) if eal.does_asset_exist(path) else None
        if not isinstance(tex, unreal.Texture2D):
            _o90('FAIL', 'import of %s failed (%s)' % (fn, list(t.get_editor_property('imported_object_paths'))))
            return None
        comp = 'TC_MASKS' if key == 'comic' else AS90_INK_COMPRESSION
        want = [('srgb', False), ('compression_settings', getattr(unreal.TextureCompressionSettings, comp)),
                ('address_x', unreal.TextureAddress.TA_CLAMP), ('address_y', unreal.TextureAddress.TA_CLAMP),
                ('lod_group', getattr(unreal.TextureGroup, AS90_INK_LOD_GROUP) if key != 'comic' else unreal.TextureGroup.TEXTUREGROUP_WORLD),
                ('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP),
                ('virtual_texture_streaming', False), ('compression_no_alpha', True), ('never_stream', False)]
        if key != 'comic':     # v2: blended mips (the World group's MipFilter=point = nearest mip on Vulkan)
            want.append(('filter', getattr(unreal.TextureFilter, AS90_INK_FILTER)))
        for k, v in want:
            if str(r3_getp(tex, k)) != str(v):
                r3_setp(AS90_R, tex, k, v, critical=k in ('srgb', 'compression_settings', 'address_x', 'address_y'))
        got = dict((k, str(r3_getp(tex, k))) for k, _ in want)
        size = [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()]
        want_size = (inp['textures'].get(path.rsplit('/', 1)[1]) or {}).get('size')
        ok = all(got[k] == str(v) for k, v in want[:4]) and (want_size is None or size == [want_size, want_size]) and \
            all(got[k] == str(v) for k, v in want if k == 'filter')
        _o90('PASS' if ok else 'FAIL', '%s from %s: %s, %s' % (path.rsplit('/', 1)[1], fn, size, got))
        out[key] = tex
    return out


# ------------------------------------------------------------------------------------------------ the master material
AS90_PAL_CODE = ('float i = clamp(round(UV1.x), 0.0, 23.0);\nfloat3 c = P0;\n' +
                 ''.join('c = (i == %d.0) ? P%d : c;\n' % (k, k) for k in range(1, 24)) + 'return c;')
AS90_INK_CODE = ('float d = S.r * (DMax + DNeg) - DNeg;\n'
                 'float px = PixelDepth * 2.0 * TanHalfFov.x / max(ViewSize.x, 1.0);\n'
                 'float k = saturate((PixelDepth - FarStart) / max(FarEnd - FarStart, 1.0));\n'
                 'float inkpx = lerp(PxNear, PxFar, k);\n'
                 'float aa = 0.5 * px;\n'
                 '// v2: the band w +- aa ends at DMax (a texel with no line within DMax never gets ink); the core shrinks\n'
                 '// instead of the anti-aliasing, so far lines fade out smoothly\n'
                 'float w = min(max(0.5 * inkpx * px, MinHalfWidth), DMax - aa);\n'
                 'float ln = (1.0 - smoothstep(w - aa, w + aa, d)) * step(S.r, 0.996);   // (line is an HLSL keyword)\n'
                 'float f = saturate((PixelDepth - FadeStart) / max(FadeEnd - FadeStart, 1.0));\n'
                 'return ln * lerp(1.0, OpacityFar, f);')
AS90_SIL_CODE = ('// the project\'s material-only silhouette (icelook outline/hlsl/CN_InkSilhouette.hlsl, Soft 0, FacetSil 0):\n'
                 '// (N.V)^2 over its own screen derivative = the distance in pixels from a curved silhouette\n'
                 'float ndv = abs(dot(normalize(N), normalize(V)));\n'
                 'float q = ndv * ndv;\n'
                 'float pxd = q / max(fwidth(q), 1e-6);\n'
                 '// a gently curved surface seen edge-on (the deck rim at eye height) keeps N.V near 0 over many pixels and\n'
                 '// drew a thick jagged band: no line where N.V changes less than MinSlope per pixel (r3_preview mimic)\n'
                 'float curv = smoothstep(0.5 * MinSlope, MinSlope, fwidth(ndv));\n'
                 'float f = 1.0 - smoothstep(FadeStart, max(FadeEnd, FadeStart + 1.0), PixelDepth);\n'
                 'return f > 0.0 ? saturate(WidthPx * f + 0.5 - pxd) * curv : 0.0;')
AS90_FINAL_CODE = ('float3 c = lerp(Col, Bolt, saturate(Dot));\n'
                   'float l = saturate(max(max(Line, Comic), Sil) * Opacity);\n'
                   'return lerp(c, Ink, l);')
AS90_LIFT_CODE = ('// v2 look: the colour that holds under any level light (emissive, before EyeAdaptationInverse)\n'
                  'float y = dot(C, float3(0.2126, 0.7152, 0.0722));\n'
                  'return max(y + (C - y) * LiftSat, 0.0) * ShadeLift;')


def _expr(mat, cls, x, y):
    return unreal.MaterialEditingLibrary.create_material_expression(mat, cls, x, y)


def _connect(a, aout, b, bin_):
    ok = unreal.MaterialEditingLibrary.connect_material_expressions(a, aout, b, bin_)
    if not ok:
        raise RuntimeError('connect %s.%s -> %s.%s failed' % (type(a).__name__, aout, type(b).__name__, bin_))


def _custom(mat, x, y, desc, code, out_type, inputs):
    c = _expr(mat, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property('description', desc)
    c.set_editor_property('code', code)
    c.set_editor_property('output_type', getattr(unreal.CustomMaterialOutputType, out_type))
    arr = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property('input_name', n)
        arr.append(ci)
    c.set_editor_property('inputs', arr)
    return c


def _scalar(mat, name, val, group, x, y, prio=0):
    s = _expr(mat, unreal.MaterialExpressionScalarParameter, x, y)
    s.set_editor_property('parameter_name', name)
    s.set_editor_property('default_value', float(val))
    s.set_editor_property('group', group)
    s.set_editor_property('sort_priority', prio)
    return s


def _switch(mat, name, default, x, y):
    s = _expr(mat, unreal.MaterialExpressionStaticSwitchParameter, x, y)
    s.set_editor_property('parameter_name', name)
    s.set_editor_property('default_value', bool(default))
    s.set_editor_property('group', 'Switches')
    return s


def as90_build_master(mat, tex, inp):
    MEL = unreal.MaterialEditingLibrary
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', False)
    try:
        mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    except Exception:  # noqa: BLE001
        pass
    cm = _expr(mat, unreal.MaterialExpressionComment, -2600, -1400)
    cm.set_editor_property('text', AS90_VERSION + ': palette by UV1 + signed-distance ink (EXPORT_R3.md 2.2). Built by '
                           'Docs/Airship/scripts/ue/as_90_r3_textures_material.py: edit the MI_AirshipR3_Look values, not '
                           'this graph.')
    cm.set_editor_property('size_x', 400)
    cm.set_editor_property('size_y', 120)
    # UVs
    uv = {}
    for k in (0, 1, 2):
        t = _expr(mat, unreal.MaterialExpressionTextureCoordinate, -2400, -600 + 160 * k)
        t.set_editor_property('coordinate_index', k)
        uv[k] = t
    # palette
    pal = []
    for i, p in enumerate(inp['palette']):
        v = _expr(mat, unreal.MaterialExpressionVectorParameter, -2000, -1200 + 110 * i)
        v.set_editor_property('parameter_name', _pal_name(i, p['slot']))
        c = p['linear']
        v.set_editor_property('default_value', unreal.LinearColor(float(c[0]), float(c[1]), float(c[2]), 1.0))
        v.set_editor_property('group', 'Palette')
        v.set_editor_property('sort_priority', i)
        pal.append(v)
    cpal = _custom(mat, -1500, -600, 'R3Palette', AS90_PAL_CODE, 'CMOT_FLOAT3', ['UV1'] + ['P%d' % k for k in range(24)])
    _connect(uv[1], '', cpal, 'UV1')
    for k, v in enumerate(pal):
        _connect(v, '', cpal, 'P%d' % k)
    # ink texture
    sw_uv = _switch(mat, 'InkOnUV2', AS90_SWITCHES['InkOnUV2'], -2150, -150)
    _connect(uv[2], '', sw_uv, 'True')
    _connect(uv[0], '', sw_uv, 'False')
    ti = _expr(mat, unreal.MaterialExpressionTextureSampleParameter2D, -1900, -150)
    ti.set_editor_property('parameter_name', 'InkTex')
    ti.set_editor_property('texture', tex['H'])
    ti.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    ti.set_editor_property('group', 'Textures')
    _connect(sw_uv, '', ti, 'UVs')
    # ink line width
    pd = _expr(mat, unreal.MaterialExpressionPixelDepth, -1900, 150)
    vfov = _expr(mat, unreal.MaterialExpressionViewProperty, -1900, 230)
    vfov.set_editor_property('property', r3_enum('MaterialExposedViewProperty', 'tanhalffieldofview'))
    vsz = _expr(mat, unreal.MaterialExpressionViewProperty, -1900, 330)
    vsz.set_editor_property('property', r3_enum('MaterialExposedViewProperty', 'viewsize'))
    sc = {}
    for k, (n, val, grp) in enumerate(AS90_SCALARS):
        sc[n] = _scalar(mat, n, val, grp, -1650, 450 + 90 * k, k)
    cink = _custom(mat, -1300, 150, 'R3InkLine', AS90_INK_CODE, 'CMOT_FLOAT1',
                   ['S', 'PixelDepth', 'TanHalfFov', 'ViewSize', 'DMax', 'DNeg', 'PxNear', 'PxFar', 'FarStart', 'FarEnd',
                    'MinHalfWidth', 'FadeStart', 'FadeEnd', 'OpacityFar'])
    _connect(ti, 'RGBA', cink, 'S')
    _connect(pd, '', cink, 'PixelDepth')
    _connect(vfov, '', cink, 'TanHalfFov')
    _connect(vsz, '', cink, 'ViewSize')
    for n, pin in (('InkDistMax', 'DMax'), ('InkDistNeg', 'DNeg'), ('InkPxNear', 'PxNear'), ('InkPxFar', 'PxFar'),
                   ('InkFarStart', 'FarStart'), ('InkFarEnd', 'FarEnd'), ('InkMinHalfWidth', 'MinHalfWidth')):
        _connect(sc[n], '', cink, pin)
    # dots
    zero = _expr(mat, unreal.MaterialExpressionConstant, -1300, -250)
    zero.set_editor_property('r', 0.0)
    sw_dot = _switch(mat, 'HasDots', AS90_SWITCHES['HasDots'], -1300, -150)
    _connect(ti, 'G', sw_dot, 'True')
    _connect(zero, '', sw_dot, 'False')
    # Talal's comic mask (UV0, his UVs)
    tc = _expr(mat, unreal.MaterialExpressionTextureSampleParameter2D, -1900, 1500)
    tc.set_editor_property('parameter_name', 'ComicMaskTex')
    tc.set_editor_property('texture', tex['comic'])
    tc.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    tc.set_editor_property('group', 'Textures')
    _connect(uv[0], '', tc, 'UVs')
    mul = _expr(mat, unreal.MaterialExpressionMultiply, -1500, 1500)
    _connect(tc, 'R', mul, 'A')
    _connect(sc['ComicAmount'], '', mul, 'B')
    sw_com = _switch(mat, 'HasComic', AS90_SWITCHES['HasComic'], -1300, 1500)
    _connect(mul, '', sw_com, 'True')
    _connect(zero, '', sw_com, 'False')
    # silhouette (static switch HasSilhouette, default off)
    vn = _expr(mat, unreal.MaterialExpressionVertexNormalWS, -1900, 2000)
    cv = _expr(mat, unreal.MaterialExpressionCameraVectorWS, -1900, 2100)
    csil = _custom(mat, -1500, 2000, 'R3Silhouette', AS90_SIL_CODE, 'CMOT_FLOAT1', ['N', 'V', 'PixelDepth', 'WidthPx', 'FadeStart', 'FadeEnd',
                                                                                  'MinSlope'])
    for src, pin in ((vn, 'N'), (cv, 'V'), (pd, 'PixelDepth'), (sc['SilWidthPx'], 'WidthPx'), (sc['SilFadeStart'], 'FadeStart'),
                     (sc['SilFadeEnd'], 'FadeEnd'), (sc['SilMinSlope'], 'MinSlope')):
        _connect(src, '', csil, pin)
    sw_sil = _switch(mat, 'HasSilhouette', AS90_SWITCHES['HasSilhouette'], -1300, 2000)
    _connect(csil, '', sw_sil, 'True')
    _connect(zero, '', sw_sil, 'False')
    # final colour
    ink = _expr(mat, unreal.MaterialExpressionVectorParameter, -1300, 900)
    ink.set_editor_property('parameter_name', 'InkColor')
    ink.set_editor_property('default_value', unreal.LinearColor(AS90_INK_LIN[0], AS90_INK_LIN[1], AS90_INK_LIN[2], 1.0))
    ink.set_editor_property('group', 'Ink')
    cfin = _custom(mat, -900, 0, 'R3Final', AS90_FINAL_CODE, 'CMOT_FLOAT3', ['Col', 'Dot', 'Line', 'Comic', 'Sil', 'Bolt', 'Ink', 'Opacity'])
    _connect(cpal, '', cfin, 'Col')
    _connect(sw_dot, '', cfin, 'Dot')
    _connect(cink, '', cfin, 'Line')
    _connect(sw_com, '', cfin, 'Comic')
    _connect(sw_sil, '', cfin, 'Sil')
    _connect(pal[10], '', cfin, 'Bolt')
    _connect(ink, '', cfin, 'Ink')
    _connect(sc['InkOpacity'], '', cfin, 'Opacity')
    for n, pin in (('InkFadeStart', 'FadeStart'), ('InkFadeEnd', 'FadeEnd'), ('InkOpacityFar', 'OpacityFar')):
        _connect(sc[n], '', cink, pin)
    # v2 look: BaseColor = c * LitMix; Emissive = EyeAdaptationInverse(max(Sat(c, LiftSat), 0) * ShadeLift, LiftLock)
    base = _expr(mat, unreal.MaterialExpressionMultiply, -600, 0)
    _connect(cfin, '', base, 'A')
    _connect(sc['LitMix'], '', base, 'B')
    clift = _custom(mat, -600, 250, 'R3Lift', AS90_LIFT_CODE, 'CMOT_FLOAT3', ['C', 'LiftSat', 'ShadeLift'])
    _connect(cfin, '', clift, 'C')
    _connect(sc['LiftSat'], '', clift, 'LiftSat')
    _connect(sc['ShadeLift'], '', clift, 'ShadeLift')
    eai = _expr(mat, unreal.MaterialExpressionEyeAdaptationInverse, -350, 250)
    if not any(MEL.connect_material_expressions(clift, '', eai, n) for n in ('LightValueInput', 'LightValue')):
        raise RuntimeError('connect R3Lift -> EyeAdaptationInverse.LightValueInput failed')
    if not any(MEL.connect_material_expressions(sc['LiftLock'], '', eai, n) for n in ('AlphaInput', 'Alpha')):
        raise RuntimeError('connect LiftLock -> EyeAdaptationInverse.AlphaInput failed')
    for e, prop in ((base, 'MP_BASE_COLOR'), (eai, 'MP_EMISSIVE_COLOR'), (sc['Roughness'], 'MP_ROUGHNESS'),
                    (sc['Specular'], 'MP_SPECULAR'), (sc['Metallic'], 'MP_METALLIC')):
        if not MEL.connect_material_property(e, '', getattr(unreal.MaterialProperty, prop)):
            raise RuntimeError('connect to %s failed' % prop)
    for u in ('MATUSAGE_SKELETAL_MESH', 'MATUSAGE_NANITE'):
        try:
            MEL.set_material_usage(mat, getattr(unreal.MaterialUsage, u))
        except Exception as e:  # noqa: BLE001
            _o90('WARN', 'usage %s: %s' % (u, e))


def as90_master(eal, tex, inp):
    """returns the master material (built now or checked), or None"""
    MEL = unreal.MaterialEditingLibrary
    if eal.does_asset_exist(R3_MASTER):
        mat = eal.load_asset(R3_MASTER)
        if not isinstance(mat, unreal.Material):
            _o90('FAIL', '%s exists and is a %s: not touched' % (R3_MASTER, type(mat).__name__))
            return None
        notes = [e.get_editor_property('text') for e in MEL.get_material_expressions(mat)
                 if isinstance(e, unreal.MaterialExpressionComment)]
        if not any(str(t).startswith(AS90_VERSION) for t in notes):
            _o90('FAIL', '%s exists but is not this script\'s version (%s; comments %s): not rebuilt in place. To rebuild: '
                 'quit the editor, move Content/Assets/MyShip/Drivable/Materials/M_AirshipR3.uasset aside (a backup is in '
                 'Saved/Airship/backup_r3/), start the editor, run as_90 again (the MIs keep their parent path)'
                 % (R3_MASTER, AS90_VERSION, [str(t)[:40] for t in notes]))
            return None
        _o90('INFO', '%s exists with this version: checked, not rebuilt' % R3_MASTER)
        return mat
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat = tools.create_asset('M_AirshipR3', R3_MATD, unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        _o90('FAIL', 'could not create %s' % R3_MASTER)
        return None
    as90_build_master(mat, tex, inp)
    _o90('INFO', 'built %s: %d expressions' % (R3_MASTER, MEL.get_num_material_expressions(mat)))
    return mat


def as90_mi(eal, path, parent):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
        if not isinstance(mi, unreal.MaterialInstanceConstant):
            _o90('FAIL', '%s exists and is a %s: not touched' % (path, type(mi).__name__))
            return None
    else:
        folder, name = path.rsplit('/', 1)
        mi = tools.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if mi is None:
            _o90('FAIL', 'could not create %s' % path)
            return None
    unreal.MaterialEditingLibrary.set_material_instance_parent(mi, parent)
    return mi


def as90_run():
    if r3_pie():
        _o90('FAIL', 'PIE is running: nothing done')
        return
    eal = unreal.EditorAssetLibrary
    MEL = unreal.MaterialEditingLibrary
    inp = r3_inputs(AS90_R)
    if inp is None:
        return
    pal = inp['palette']
    lk_in = inp.get('look')
    if lk_in is None:
        _o90('WARN', 'r3_unreal_inputs.json has no look defaults (staged before the review fixes?): using as_90\'s %s' % AS90_LOOK_DEFAULT)
    else:
        same = all(abs(float(lk_in[n]) - v) < 1e-6 for n, v in AS90_LOOK_DEFAULT.items())
        _o90('PASS' if same else 'FAIL', 'look defaults %s = the staged export_shade_calib.json choice %s' % (
            AS90_LOOK_DEFAULT, dict((n, lk_in[n]) for n in AS90_LOOK_DEFAULT)))
    _o90('PASS' if len(pal) == 24 and [p['index'] for p in pal] == list(range(24)) else 'FAIL', 'palette: 24 slots (%s ... %s), '
         'keel_block %s' % (pal[0]['slot'], pal[23]['slot'], pal[16]))
    talal0 = r3_talal_state()
    ours = list(R3_TEX.values()) + [R3_MASTER, R3_LOOK] + list(R3_MI.values())
    r3_close_editors(ours)
    if r3_backup(AS90_R, ours, 'as_90') is None:
        return
    tex = as90_textures(eal, inp)
    if tex is None:
        return
    mat = as90_master(eal, tex, inp)
    if mat is None:
        return
    errs = MEL.recompile_material(mat)
    _o90('PASS' if not errs else 'FAIL', 'M_AirshipR3 compiles%s' % ('' if not errs else ': %s' % list(errs)[:6]))
    try:
        st = MEL.get_statistics(mat)
        AS90_R['data']['statistics'] = dict((k, r3_getp(st, k)) for k in ('num_vertex_shader_instructions',
                                                                          'num_pixel_shader_instructions', 'num_samplers'))
        _o90('PASS' if (AS90_R['data']['statistics'].get('num_pixel_shader_instructions') or 0) > 0 else 'WARN',
             'M_AirshipR3 statistics %s' % AS90_R['data']['statistics'])
    except Exception as e:  # noqa: BLE001
        _o90('WARN', 'statistics unreadable: %s' % e)
    for u in ('MATUSAGE_SKELETAL_MESH', 'MATUSAGE_NANITE'):
        try:
            _o90('PASS' if MEL.has_material_usage(mat, getattr(unreal.MaterialUsage, u)) else 'FAIL', 'M_AirshipR3 usage %s' % u)
        except Exception as e:  # noqa: BLE001
            _o90('WARN', 'usage %s unreadable: %s' % (u, e))
    # defaults read back from the master
    bad = []
    for i, p in enumerate(pal):
        c = MEL.get_material_default_vector_parameter_value(mat, _pal_name(i, p['slot']))
        if max(abs(c.r - p['linear'][0]), abs(c.g - p['linear'][1]), abs(c.b - p['linear'][2])) > 1e-4:
            bad.append((i, p['slot'], [c.r, c.g, c.b], p['linear']))
    for n, v, _ in AS90_SCALARS:
        if abs(MEL.get_material_default_scalar_parameter_value(mat, n) - v) > 1e-4:
            bad.append((n, MEL.get_material_default_scalar_parameter_value(mat, n), v))
    _o90('PASS' if not bad else 'FAIL', 'master defaults: 24 palette colours + %d scalars as the inputs%s' % (
        len(AS90_SCALARS), '' if not bad else ': %s' % bad[:6]))
    # MI_AirshipR3_Look: every palette / ink value set explicitly (the one place to tune them)
    look = as90_mi(eal, R3_LOOK, mat)
    if look is None:
        return
    for i, p in enumerate(pal):
        c = p['linear']
        MEL.set_material_instance_vector_parameter_value(look, _pal_name(i, p['slot']), unreal.LinearColor(c[0], c[1], c[2], 1.0))
    MEL.set_material_instance_vector_parameter_value(look, 'InkColor', unreal.LinearColor(AS90_INK_LIN[0], AS90_INK_LIN[1], AS90_INK_LIN[2], 1.0))
    for n, v, _ in AS90_SCALARS:
        MEL.set_material_instance_scalar_parameter_value(look, n, v)
    for n, v in AS90_LOOK_SWITCHES.items():
        MEL.set_material_instance_static_switch_parameter_value(look, n, v)
    MEL.update_material_instance(look)
    got_ls = dict((n, MEL.get_material_instance_static_switch_parameter_value(look, n)) for n in AS90_LOOK_SWITCHES)
    got_lk = dict((n, round(MEL.get_material_instance_scalar_parameter_value(look, n), 4)) for n in AS90_LOOK_DEFAULT)
    _o90('PASS' if got_ls == AS90_LOOK_SWITCHES and all(abs(got_lk[n] - v) < 1e-4 for n, v in AS90_LOOK_DEFAULT.items())
         else 'FAIL', 'MI_AirshipR3_Look: look %s, switches %s (HasSilhouette off = no silhouette lines; on = the option for '
         'Talal, question 3)' % (got_lk, got_ls))
    # the four children
    for key, (tk, sw, two) in AS90_MI_SETUP.items():
        mi = as90_mi(eal, R3_MI[key], look)
        if mi is None:
            return
        MEL.set_material_instance_texture_parameter_value(mi, 'InkTex', tex[tk])
        if sw['HasComic']:
            MEL.set_material_instance_texture_parameter_value(mi, 'ComicMaskTex', tex['comic'])
        for n, v in sw.items():
            MEL.set_material_instance_static_switch_parameter_value(mi, n, v)
        ov = mi.get_editor_property('base_property_overrides')
        ov.set_editor_property('override_two_sided', bool(two))
        ov.set_editor_property('two_sided', bool(two))
        mi.set_editor_property('base_property_overrides', ov)
        MEL.update_material_instance(mi)
    # read back
    for key, (tk, sw, two) in AS90_MI_SETUP.items():
        mi = eal.load_asset(R3_MI[key])
        got_t = r3_pkg(MEL.get_material_instance_texture_parameter_value(mi, 'InkTex'))
        got_s = dict((n, MEL.get_material_instance_static_switch_parameter_value(mi, n)) for n in sw)
        ov = mi.get_editor_property('base_property_overrides')
        got_two = bool(ov.get_editor_property('override_two_sided')) and bool(ov.get_editor_property('two_sided'))
        par = r3_pkg(mi.get_editor_property('parent'))
        ok = got_t == R3_TEX[tk] and got_s == sw and got_two == two and par == R3_LOOK
        _o90('PASS' if ok else 'FAIL', '%s: parent %s, InkTex %s, switches %s, two sided %s' % (
            R3_MI[key].rsplit('/', 1)[1], par, got_t, got_s, got_two))
    bad = []
    for i, p in enumerate(pal):
        c = MEL.get_material_instance_vector_parameter_value(eal.load_asset(R3_MI['hull']), _pal_name(i, p['slot']))
        if max(abs(c.r - p['linear'][0]), abs(c.g - p['linear'][1]), abs(c.b - p['linear'][2])) > 1e-4:
            bad.append((i, [c.r, c.g, c.b]))
    _o90('PASS' if not bad else 'FAIL', 'MI_AirshipR3_Hull sees the palette of MI_AirshipR3_Look (24 slots, keel block %s)%s'
         % (pal[16]['linear'], '' if not bad else ': %s' % bad[:5]))
    AS90_R['data']['palette'] = dict((_pal_name(i, p['slot']), p['linear']) for i, p in enumerate(pal))
    if AS90_R['counts'].get('FAIL'):
        _o90('WARN', '%d FAIL: NOT saved (restart the editor before a re-run)' % AS90_R['counts']['FAIL'])
        return
    r3_save(AS90_R, ours)
    r3_check_talal(AS90_R, talal0)
    _o90('INFO', 'NEXT: as_91_r3_reimport.py (SK_Airship + LODs + slots)')


try:
    as90_run()
except Exception:  # noqa: BLE001
    _o90('FAIL', 'as_90 crashed: %s' % traceback.format_exc())
r3_finish(AS90_R)
