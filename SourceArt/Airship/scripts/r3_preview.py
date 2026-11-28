"""Round 3 export, step 3: whole-ship previews with the Unreal-mimic material, and the colour check
(Docs/Airship/round3/EXPORT_R3.md sections 2.2 and 7).

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_preview.py -- \
      --shots q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L [--variants lit,flat,idx] [--lod 0|1|2]
      [--tex DIR] [--tag TEXT] [--res-scale 100] [--ink-px-near 2.2 --ink-px-far 1.2 --ink-far-start 40
      --ink-far-end 120] [--comic 0] [--props-palette on|off] [--cpu]

Opens rig/detail/r3export/AirshipR3_export.blend (never saved), the ink textures of r3_bake.py (default
rig/detail/r3export/textures) and renders the cameras of media/full/full_shots.json + fix_shots.json (the approved toon
renders' cameras) in EEVEE:
  lit   the planned M_AirshipR3: colour = palette[round(UV1.x)] (a 24 x 1 palette image, closest), rivet dots
        lerp(colour, palette[bolt], G), ink = 1 - smoothstep(w - px/2, w + px/2, R * dmax) with px = the world size of
        a pixel at the texel's view depth (Unreal: PixelDepth * 2 tan(fov / 2) / ViewSize.x) and w = half of 2.2 px
        near -> 1.2 px from 40 to 120 m, max(ink, B * comic) on the hull; base colour = lerp(colour, #1C2230, ink);
        Principled, roughness 0.9, sun + sky (the toon previews' sun direction), Standard view.
        -> Docs/Airship/round3/media/export/<shot>_baked[_<tag>].jpg
  flat  the same base colour as emission (no light), 1 sample  -> r3export/checks/preview/<shot>_flat.png
  idx   emission (palette index, ink, dot) as data, 1 sample    -> r3export/checks/preview/<shot>_idx.png (16 bit)
Colour check (flat + idx + the approved media/full/<shot>_toon_after.jpg): per palette slot, the flat render's colour
against the palette (8-bit sRGB) and the approved render's colour in its lit band, on pixels away from ink, dots and
edges -> r3export/checks/colour_check.json (+ a copy in Docs/Airship/round3/export_colour_check.json).
The props and the two turrets use the palette material (the approved previews' wood / dark metal / grey) unless
--props-palette off (then their in-game paper texture).
--from-fbx DIR (export step, 2026-11-28): the round trip. The export blend's SM_Airship, props, detail objects (all LODs)
and turrets are deleted in memory and replaced by a fresh import of DIR/SK_Airship[_LODn].fbx,
SM_AirshipR3_HullDetail[_LODn].fbx and the two turret FBX files (Blender's FBX importer; transforms baked, armature
modifiers dropped: the rest pose is the bind pose); the cameras, light, textures and material are the same, so the
renders compare 1:1 with the ones made from the export blend. Use it with --tag (the outputs get that suffix).
Review fixes (2026-11-28, EXPORT_R3.md section 15), all knobs mirror M_AirshipR3 v2 (as_90):
  ink line    the line's core shrinks so its anti-alias band (w +- px/2) ends at InkDistMax, and a saturated texel
              (R >= 0.996) draws no ink, so far ships get no navy tint and keep their anti-aliasing (--ink-aa capped;
              'v1' = the pass-1 formula, for the before / after check); far opacity
              fade --ink-fade-start / --ink-fade-end (m) / --ink-opacity-far (default 1 = no fade)
  look        --look default|off|lit_mix,shade_lift,lift_sat: BaseColor = c x LitMix, Emissive = max(Sat(c, LiftSat), 0) x
              ShadeLift / exposure (as_90's EyeAdaptationInverse, LiftLock 1). default = r3_look's chosen values
              (export_shade_calib.json); off = v1 (plain lit)
  light       --light preview (the toon previews' sun + grey sky, Standard view: as before) | game (StartupMap: moon
              2.24 lux (125,160,255) from its real direction, sky light hemispheres, sky #026AB5 behind; rendered
              scene-linear to EXR, then UE 5.8's Filmic + V2.1 grading + LUT through r3_look / display_model, EV100 0.5)
              [--sky-r 0.6: the unknown DaylightAmbientCubemap mean radiance]
  silhouette  --sil off|on [--sil-px 2.4 --sil-fade-start 60 --sil-fade-end 120 (m) --sil-min-slope 0.02]: the material-only
              silhouette node (with as_90's SilMinSlope gate: no line where N.V changes less than that per pixel, so a
              gently curved deck seen edge-on draws no band)
              (CN_InkSilhouette: (N.V)^2 / fwidth, N = interpolated vertex normal) as a screen-space post on a normal +
              depth pass, the derivative taken only between pixels of the same smooth surface (as a GPU quad would)
  shots       --shots-file JSON (more cameras; media/export/review/review_shots.json and review_fix_shots.json are always
              read), --lod-m / --lod-h N: SK (moving details) and HullDetail LOD separately (HullDetail is Nanite in game
              = LOD0 at any distance)
"""
import bpy, sys, os, json, math, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Vector as V, Matrix
import r3_common as RC

A = RC.argv()
SHOTS = RC.arg(A, '--shots', 'q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L').split(',')
VARIANTS = RC.arg(A, '--variants', 'lit').split(',')
LOD = RC.arg(A, '--lod', '0')
TEXD = RC.arg(A, '--tex', RC.TEX_DIR)
TAG = RC.arg(A, '--tag', '')
RES_SCALE = RC.arg(A, '--res-scale', 100, int)
INK_NEAR = RC.arg(A, '--ink-px-near', 2.2, float)
INK_FAR = RC.arg(A, '--ink-px-far', 1.2, float)
FAR0 = RC.arg(A, '--ink-far-start', 40.0, float)
FAR1 = RC.arg(A, '--ink-far-end', 120.0, float)
COMIC = RC.arg(A, '--comic', 0.0, float)
PROPS_PAL = RC.arg(A, '--props-palette', 'on') != 'off'
CPU = '--cpu' in A
LOD_M = RC.arg(A, '--lod-m', LOD)
LOD_H = RC.arg(A, '--lod-h', LOD)
SHOTS_FILE = RC.arg(A, '--shots-file', '')
NO_LODTAG = RC.arg(A, '--lodtag', 'on') == 'off'
INK_AA = RC.arg(A, '--ink-aa', 'capped')                 # capped (v2) | v1
FADE0 = RC.arg(A, '--ink-fade-start', 200.0, float)
FADE1 = RC.arg(A, '--ink-fade-end', 400.0, float)
OPA_FAR = RC.arg(A, '--ink-opacity-far', 1.0, float)
LIGHT = RC.arg(A, '--light', 'preview')
SKY_R = RC.arg(A, '--sky-r', 0.6, float)
SIL = RC.arg(A, '--sil', 'off') == 'on'
SIL_PX = RC.arg(A, '--sil-px', 2.4, float)
SIL_F0 = RC.arg(A, '--sil-fade-start', 60.0, float)
SIL_F1 = RC.arg(A, '--sil-fade-end', 120.0, float)
SIL_SLOPE = RC.arg(A, '--sil-min-slope', 0.02, float)  # N.V change per pixel below which no line (as_90 SilMinSlope; 0 = off)
import r3_look as LK
_LOOK_ARG = RC.arg(A, '--look', 'default')
if _LOOK_ARG == 'off':
    LOOK = dict(LK.LOOK_OFF)
elif _LOOK_ARG == 'default':
    LOOK = dict(RC.load_json(RC.DOCS + '/export_shade_calib.json')['chosen'])
else:
    _v = [float(x) for x in _LOOK_ARG.split(',')]
    LOOK = dict(lit_mix=_v[0], shade_lift=_v[1], lift_sat=_v[2], lift_lock=1.0)
EXPOSURE = 2.0 ** -LK.STARTUP['ev100'] if LIGHT == 'game' else 1.0     # the scene's exposure (preview: Standard view, 1)
WMIN = 0.002
PREV_DIR = RC.CHECK_DIR + '/preview'
os.makedirs(PREV_DIR, exist_ok=True)
os.makedirs(RC.MEDIA, exist_ok=True)
log = RC.Log('r3_preview')
bake_rep = RC.load_json(RC.CHECK_DIR + '/r3_bake_report.json')
DMAX = float(bake_rep['knobs']['dmax'])
DNEG = float(bake_rep['knobs'].get('dneg', 0.0))          # R = (d + dneg) / (dmax + dneg)
PROPS_PAPER = RC.RIG_DIR + '/props/textures/T_AirshipProps_ComicLines.png'

bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND)
import detail_render as R
sc, cam = R.base_scene()
arm = bpy.data.objects['Armature']
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
FROM_FBX = RC.arg(A, '--from-fbx', '')
if FROM_FBX:
    _sfx = '' if LOD == '0' else '_LOD' + LOD
    for _o in list(bpy.data.objects):
        if _o.type == 'MESH' and (_o.name == RC.HULL_OBJ or _o.name.startswith((RC.PROP_PREFIX, RC.MOVING, RC.HULLDET)) or
                                  _o.name in RC.TURRETS.values()):
            bpy.data.objects.remove(_o)
    _files = ['SK_Airship%s.fbx' % _sfx, RC.HULLDET + _sfx + '.fbx'] + [n + '.fbx' for n in RC.TURRETS.values()]
    _got = []
    for _f in _files:
        _before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(FROM_FBX, _f), automatic_bone_orientation=False,
                                 primary_bone_axis='Z', secondary_bone_axis='X', ignore_leaf_bones=False, use_anim=False)
        _new = [o for o in bpy.data.objects if o not in _before]
        for _o in _new:
            if _o.type == 'MESH':
                _M = _o.matrix_world.copy()
                _o.parent = None
                for _m in list(_o.modifiers):
                    _o.modifiers.remove(_m)
                _o.matrix_world = Matrix.Identity(4)
                _o.data.transform(_M)
                _got.append(_o.name)
        for _o in _new:
            if _o.type != 'MESH':
                bpy.data.objects.remove(_o)
    _want = sorted([RC.HULL_OBJ, RC.MOVING + _sfx, RC.HULLDET + _sfx] + list(RC.TURRETS.values()))
    assert all(n in _got for n in _want) and sum(n.startswith(RC.PROP_PREFIX) for n in _got) == 30, (_got[:5], len(_got))
    assert len(_got) == 35, len(_got)
    log('round trip: %d meshes imported from %s (%s)' % (len(_got), FROM_FBX, ', '.join(_files)))
shots = dict(R.SHOTS)
for f in (RC.MEDIA_FULL + '/full_shots.json', RC.MEDIA_FULL + '/fix_shots.json', RC.MEDIA + '/spike_shots.json',
          RC.MEDIA + '/review/review_shots.json', RC.MEDIA + '/review_fix_shots.json') + ((SHOTS_FILE,) if SHOTS_FILE else ()):
    if not os.path.isfile(f):
        continue
    for k, v in RC.load_json(f).items():
        if not isinstance(v, dict) or 'loc' not in v:
            continue
        shots[k] = (tuple(v['loc']), tuple(v['tgt']), ('ortho', float(v['ortho'])) if 'ortho' in v else
                    float(v.get('lens', 35.0)), tuple(v.get('res', (1920, 1080))))

# ------------------------------------------------------------------ what renders
det_names = {'M': RC.MOVING + ('' if LOD_M == '0' else '_LOD' + LOD_M), 'H': RC.HULLDET + ('' if LOD_H == '0' else '_LOD' + LOD_H)}
if FROM_FBX:
    det_names = {g: [RC.MOVING, RC.HULLDET][k] + ('' if LOD == '0' else '_LOD' + LOD) for k, g in enumerate(('M', 'H'))}
for o in bpy.data.objects:
    if o.type == 'MESH':
        o.hide_render = not (o.name == RC.HULL_OBJ or o.name.startswith(RC.PROP_PREFIX) or o.name in det_names.values())
# turrets at both mounts (detail_render.add_turrets: base on the deck at the mount, gun at the trunnion 1.5 m above)
tcoll = bpy.data.collections.new('R3_PreviewTurrets')
sc.collection.children.link(tcoll)
turrets = []
for s in ('L', 'R'):
    Mb = Matrix.Translation(V(tuple(RC_m for RC_m in (21.0, 2.45 if s == 'L' else -2.45)) + (6.55,)))
    for src, M in ((RC.TURRETS['Turret_Base'], Mb), (RC.TURRETS['Turret_Gun'], Mb @ Matrix.Translation(V((0, 0, 1.5))))):
        o = bpy.data.objects[src].copy()
        o.name = src + '_' + s
        o.matrix_world = M
        o.hide_render = False
        tcoll.objects.link(o)
        turrets.append(o)

# ------------------------------------------------------------------ images
def load_tex(name):
    p = os.path.join(TEXD, name)
    im = bpy.data.images.load(p, check_existing=False)
    im.colorspace_settings.name = 'Non-Color'
    return im


TEXS = {g: load_tex(RC.PAGES[g]['tex']) for g in ('hull', 'H', 'M', 'P')}
pal_img = bpy.data.images.new('_r3_palette', 24, 1, float_buffer=True)
pal_img.colorspace_settings.name = 'Non-Color'
px = np.ones((1, 24, 4), np.float32); px[0, :, :3] = RC.PAL
pal_img.pixels.foreach_set(px.ravel())
INK = RC.hex_lin(RC.INK_HEX)

# ------------------------------------------------------------------ the line width group (Unreal: PixelDepth, view size)
ng = bpy.data.node_groups.new('R3InkWidth', 'ShaderNodeTree')
ng.interface.new_socket(name='Dist01', in_out='INPUT', socket_type='NodeSocketFloat')
ng.interface.new_socket(name='Ink', in_out='OUTPUT', socket_type='NodeSocketFloat')
gi = ng.nodes.new('NodeGroupInput'); go = ng.nodes.new('NodeGroupOutput')


def gval(name, v):
    n_ = ng.nodes.new('ShaderNodeValue'); n_.name = name; n_.outputs[0].default_value = v
    return n_.outputs[0]


def gmath(op, a_, b_=None, clamp=False):
    n_ = ng.nodes.new('ShaderNodeMath'); n_.operation = op; n_.use_clamp = clamp
    for k_, x in enumerate((a_, b_)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n_.inputs[k_].default_value = x
        else:
            ng.links.new(x, n_.inputs[k_])
    return n_.outputs[0]


camd = ng.nodes.new('ShaderNodeCameraData')
depth = camd.outputs['View Z Depth']
pxs = gmath('ADD', gmath('MULTIPLY', depth, gval('KPX', 0.001)), gval('KC', 0.0))        # world size of a pixel (m)
fade = gmath('MULTIPLY', gmath('SUBTRACT', depth, gval('FAR0', FAR0)), gval('INVFAR', 1.0 / (FAR1 - FAR0)), clamp=True)
fade = gmath('MULTIPLY', fade, gval('FADEON', 1.0))
inkpx = gmath('ADD', gval('NEAR', INK_NEAR), gmath('MULTIPLY', fade, INK_FAR - INK_NEAR))
w0 = gmath('MAXIMUM', gmath('MULTIPLY', gmath('MULTIPLY', inkpx, 0.5), pxs), WMIN)
dd = gmath('SUBTRACT', gmath('MULTIPLY', gi.outputs['Dist01'], DMAX + DNEG), DNEG)
mr = ng.nodes.new('ShaderNodeMapRange'); mr.interpolation_type = 'SMOOTHSTEP'; mr.clamp = True
ng.links.new(dd, mr.inputs['Value'])
aa = gmath('MULTIPLY', pxs, 0.5)
if INK_AA == 'v1':          # pass 1: w <= 0.95 DMax, but the band w + px/2 can pass DMax (far ships turn navy, review 7)
    w = gmath('MINIMUM', w0, 0.95 * DMAX)
else:                       # v2 (as_90 R3InkLine): the core shrinks so the band w +- px/2 ends at DMax (AA kept)
    w = gmath('MINIMUM', w0, gmath('SUBTRACT', DMAX, aa))
ng.links.new(gmath('SUBTRACT', w, aa), mr.inputs['From Min'])
ng.links.new(gmath('ADD', w, aa), mr.inputs['From Max'])
mr.inputs['To Min'].default_value = 1.0; mr.inputs['To Max'].default_value = 0.0
line_ = mr.outputs['Result']
if INK_AA != 'v1':
    line_ = gmath('MULTIPLY', line_, gmath('LESS_THAN', gi.outputs['Dist01'], 0.996))       # saturated texel: no line
    ofade = gmath('MULTIPLY', gmath('MULTIPLY', gmath('SUBTRACT', depth, gval('FADE0', FADE0)),
                                    gval('INVFADE', 1.0 / max(FADE1 - FADE0, 1e-3)), clamp=True), gval('FADEON2', 1.0))
    line_ = gmath('MULTIPLY', line_, gmath('ADD', 1.0, gmath('MULTIPLY', ofade, OPA_FAR - 1.0)))   # far opacity fade
ng.links.new(line_, go.inputs['Ink'])


def set_shot_ink(cam_, res_x):
    if cam_.data.type == 'ORTHO':
        ng.nodes['KPX'].outputs[0].default_value = 0.0
        ng.nodes['KC'].outputs[0].default_value = cam_.data.ortho_scale / res_x
        ng.nodes['FADEON'].outputs[0].default_value = 0.0
        if 'FADEON2' in ng.nodes:
            ng.nodes['FADEON2'].outputs[0].default_value = 0.0
    else:
        ng.nodes['KPX'].outputs[0].default_value = cam_.data.sensor_width / cam_.data.lens / res_x
        ng.nodes['KC'].outputs[0].default_value = 0.0
        ng.nodes['FADEON'].outputs[0].default_value = 1.0
        if 'FADEON2' in ng.nodes:
            ng.nodes['FADEON2'].outputs[0].default_value = 1.0


# ------------------------------------------------------------------ materials
def r3_material(name, ink_img, variant, comic=0.0, ink_uv=RC.UV_INK, comic_img=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    uvp = nt.nodes.new('ShaderNodeUVMap'); uvp.uv_map = RC.UV_PAL
    sxy = nt.nodes.new('ShaderNodeSeparateXYZ'); L(uvp.outputs[0], sxy.inputs[0])

    def math(op, a_, b_=None):
        n_ = nt.nodes.new('ShaderNodeMath'); n_.operation = op
        for k_, x in enumerate((a_, b_)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n_.inputs[k_].default_value = x
            else:
                L(x, n_.inputs[k_])
        return n_.outputs[0]
    idx = math('ROUND', sxy.outputs['X'])
    u = math('DIVIDE', math('ADD', idx, 0.5), 24.0)
    cxyz = nt.nodes.new('ShaderNodeCombineXYZ'); L(u, cxyz.inputs['X']); cxyz.inputs['Y'].default_value = 0.5
    pt = nt.nodes.new('ShaderNodeTexImage'); pt.image = pal_img; pt.interpolation = 'Closest'; pt.extension = 'EXTEND'
    L(cxyz.outputs[0], pt.inputs['Vector'])
    col = pt.outputs['Color']
    uvi = nt.nodes.new('ShaderNodeUVMap'); uvi.uv_map = ink_uv
    tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = ink_img; tx.interpolation = 'Linear'; tx.extension = 'EXTEND'
    L(uvi.outputs[0], tx.inputs['Vector'])
    sep = nt.nodes.new('ShaderNodeSeparateColor'); L(tx.outputs['Color'], sep.inputs[0])
    bolt = nt.nodes.new('ShaderNodeRGB'); bolt.outputs[0].default_value = tuple(RC.PAL[RC.SLOT['bolt']]) + (1.0,)
    mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'
    L(sep.outputs[1], mx.inputs['Factor']); L(col, mx.inputs[6]); L(bolt.outputs[0], mx.inputs[7])
    col = mx.outputs[2]
    gn = nt.nodes.new('ShaderNodeGroup'); gn.node_tree = ng
    L(sep.outputs[0], gn.inputs['Dist01'])
    ink = gn.outputs['Ink']
    if comic > 0:
        cb = sep.outputs[2]
        if comic_img is not None:                   # Talal's comic mask as its own texture on UV0
            u0 = nt.nodes.new('ShaderNodeUVMap'); u0.uv_map = RC.UV_INK
            ct = nt.nodes.new('ShaderNodeTexImage'); ct.image = comic_img; L(u0.outputs[0], ct.inputs['Vector'])
            cs = nt.nodes.new('ShaderNodeSeparateColor'); L(ct.outputs['Color'], cs.inputs[0])
            cb = cs.outputs[0]
        ink = math('MAXIMUM', ink, math('MULTIPLY', cb, comic))
    ik = nt.nodes.new('ShaderNodeRGB'); ik.outputs[0].default_value = tuple(INK) + (1.0,)
    mx2 = nt.nodes.new('ShaderNodeMix'); mx2.data_type = 'RGBA'
    L(ink, mx2.inputs['Factor']); L(col, mx2.inputs[6]); L(ik.outputs[0], mx2.inputs[7])
    base = mx2.outputs[2]
    if variant == 'lit':
        sh = nt.nodes.new('ShaderNodeBsdfPrincipled')
        sh.inputs['Roughness'].default_value = 0.9
        if LOOK['lit_mix'] != 1.0 or LOOK['shade_lift'] > 0:       # M_AirshipR3 v2 look (r3_look.py)
            bm = nt.nodes.new('ShaderNodeMix'); bm.data_type = 'RGBA'; bm.blend_type = 'MULTIPLY'
            bm.inputs['Factor'].default_value = 1.0; L(base, bm.inputs[6]); bm.inputs[7].default_value = (LOOK['lit_mix'],) * 3 + (1.0,)
            L(bm.outputs[2], sh.inputs['Base Color'])
            # Sat(c, s) = lum + (c - lum) * s, clamped at 0; strength = ShadeLift / exposure (exposure-locked emissive)
            lum = nt.nodes.new('ShaderNodeRGBToBW'); L(base, lum.inputs[0])
            gray = nt.nodes.new('ShaderNodeCombineColor')
            for k_ in range(3):
                L(lum.outputs[0], gray.inputs[k_])
            sm = nt.nodes.new('ShaderNodeMix'); sm.data_type = 'RGBA'; sm.clamp_result = False
            sm.inputs['Factor'].default_value = LOOK['lift_sat']; sm.clamp_factor = False
            L(gray.outputs[0], sm.inputs[6]); L(base, sm.inputs[7])
            mz = nt.nodes.new('ShaderNodeVectorMath'); mz.operation = 'MAXIMUM'; mz.inputs[1].default_value = (0.0, 0.0, 0.0)
            L(sm.outputs[2], mz.inputs[0])
            L(mz.outputs[0], sh.inputs['Emission Color'])
            sh.inputs['Emission Strength'].default_value = LOOK['shade_lift'] / EXPOSURE
        else:
            L(base, sh.inputs['Base Color'])
    elif variant == 'nrm':                          # data: shading normal (interpolated vertex normal) * 0.5 + 0.5
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        vm = nt.nodes.new('ShaderNodeVectorMath'); vm.operation = 'MULTIPLY_ADD'
        L(geo.outputs['Normal'], vm.inputs[0]); vm.inputs[1].default_value = (0.5, 0.5, 0.5); vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        sh = nt.nodes.new('ShaderNodeEmission'); L(vm.outputs[0], sh.inputs['Color'])
    elif variant == 'dep':                          # data: view Z depth (m) in R, object index hash in G
        cd = nt.nodes.new('ShaderNodeCameraData')
        oi = nt.nodes.new('ShaderNodeObjectInfo')
        cc = nt.nodes.new('ShaderNodeCombineColor')
        L(cd.outputs['View Z Depth'], cc.inputs[0]); L(oi.outputs['Random'], cc.inputs[1])
        sh = nt.nodes.new('ShaderNodeEmission'); L(cc.outputs[0], sh.inputs['Color'])
    elif variant == 'flat':
        sh = nt.nodes.new('ShaderNodeEmission'); L(base, sh.inputs['Color'])
    else:                                           # idx: (palette index / 32, ink, dot) as data
        cc = nt.nodes.new('ShaderNodeCombineColor')
        L(math('DIVIDE', math('ADD', idx, 0.5), 32.0), cc.inputs[0]); L(ink, cc.inputs[1]); L(sep.outputs[1], cc.inputs[2])
        sh = nt.nodes.new('ShaderNodeEmission'); L(cc.outputs[0], sh.inputs['Color'])
    L(sh.outputs[0], out.inputs['Surface'])
    return m


def paper_material(name, variant):
    img = bpy.data.images.load(PROPS_PAPER, check_existing=True)
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img
    sh = nt.nodes.new('ShaderNodeBsdfPrincipled' if variant == 'lit' else 'ShaderNodeEmission')
    if variant == 'lit':
        sh.inputs['Roughness'].default_value = 0.9
    nt.links.new(tx.outputs['Color'], sh.inputs['Base Color' if variant == 'lit' else 'Color'])
    nt.links.new(sh.outputs[0], out.inputs['Surface'])
    return m


def assign(variant):
    hme = bpy.data.objects[RC.HULL_OBJ].data
    huv = RC.page_uv(hme, 'hull')
    cimg = None
    if COMIC > 0 and huv != RC.UV_INK:
        cimg = bpy.data.images.load(RC.HULL_MASK_R2, check_existing=True); cimg.colorspace_settings.name = 'Non-Color'
    mats = {g: r3_material('R3_%s_%s' % (g, variant), TEXS[g], variant, COMIC if g == 'hull' else 0.0,
                           huv if g == 'hull' else RC.UV_INK, cimg if g == 'hull' else None)
            for g in ('hull', 'H', 'M', 'P')}
    pmat = mats['P'] if PROPS_PAL else paper_material('R3_paper_' + variant, variant)
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.hide_render:
            continue
        if o.name == RC.HULL_OBJ:
            m = mats['hull']
        elif o.name.startswith(RC.MOVING):
            m = mats['M']
        elif o.name.startswith(RC.HULLDET):
            m = mats['H']
        else:
            m = pmat
        o.data.materials.clear()
        o.data.materials.append(m)


# ------------------------------------------------------------------ world (the spike's Unreal-like light)
R.toon_world(sc)
sun = bpy.data.objects['PreviewSunToon']; sun.data.energy = 3.2
for n_ in sc.world.node_tree.nodes:
    if n_.type == 'BACKGROUND':
        n_.inputs['Strength'].default_value = 0.55 if n_.inputs['Strength'].default_value < 0.5 else 1.0
if LIGHT == 'game':
    # StartupMap (r3_look.STARTUP): moon at lux = Blender W/m2 (same E/pi on a white Lambert), from its real direction;
    # sky light = two hemispheres in scene units; the camera sees the sky sphere (#026AB5 on screen)
    _L = LK.startup_lights(SKY_R)
    sun.data.color = tuple(float(x) for x in LK.s2l8(LK.STARTUP['moon_rgb8']))
    sun.data.energy = LK.STARTUP['moon_lux']
    sun.data.angle = math.radians(2.0)
    sun.rotation_euler = V(tuple(LK.moon_dir_blender())).to_track_quat('-Z', 'Y').to_euler()
    _bgcol = LK.dm().inverse(LK.dm().hex2rgb(LK.STARTUP['sky_display_hex']), LK.startup_pp(), LK.STARTUP['ev100'])['lin']
    wt = sc.world.node_tree; wt.nodes.clear()
    wout = wt.nodes.new('ShaderNodeOutputWorld'); lp = wt.nodes.new('ShaderNodeLightPath')
    tc = wt.nodes.new('ShaderNodeTexCoord'); sz = wt.nodes.new('ShaderNodeSeparateXYZ'); wt.links.new(tc.outputs['Generated'], sz.inputs[0])
    hm = wt.nodes.new('ShaderNodeMix'); hm.data_type = 'RGBA'
    gt = wt.nodes.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.0
    wt.links.new(sz.outputs['Z'], gt.inputs[0]); wt.links.new(gt.outputs[0], hm.inputs['Factor'])
    hm.inputs[6].default_value = tuple(float(x) for x in _L['lower']) + (1.0,)
    hm.inputs[7].default_value = tuple(float(x) for x in _L['upper']) + (1.0,)
    amb = wt.nodes.new('ShaderNodeBackground'); wt.links.new(hm.outputs[2], amb.inputs['Color'])
    camb = wt.nodes.new('ShaderNodeBackground'); camb.inputs['Color'].default_value = tuple(float(x) for x in _bgcol) + (1.0,)
    mxw = wt.nodes.new('ShaderNodeMixShader')
    wt.links.new(lp.outputs['Is Camera Ray'], mxw.inputs[0]); wt.links.new(amb.outputs[0], mxw.inputs[1]); wt.links.new(camb.outputs[0], mxw.inputs[2])
    wt.links.new(mxw.outputs[0], wout.inputs['Surface'])
    log('light: StartupMap moon %s lux %.2f dir %s, sky R %.2f upper %s lower %s, sky behind %s, look %s' % (
        tuple(round(x, 3) for x in sun.data.color), sun.data.energy, LK.moon_dir_blender().round(3), SKY_R,
        _L['upper'].round(3), _L['lower'].round(3), _bgcol.round(4), LOOK))
sc.render.use_freestyle = False
sc.render.resolution_percentage = RES_SCALE
if CPU:
    pass


def read_exr(p):
    im = bpy.data.images.load(p, check_existing=False)
    w_, h_ = im.size
    a = np.empty(w_ * h_ * 4, np.float32); im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h_, w_, 4)[::-1]          # top row first


def write_jpg(p, rgb01):
    """rgb01: (h, w, 3) display-referred 0..1, top row first; written as is (Non-Color: no view transform)"""
    h_, w_ = rgb01.shape[:2]
    img = bpy.data.images.new('_r3_out', w_, h_, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    px_ = np.ones((h_, w_, 4), np.float32); px_[:, :, :3] = rgb01[::-1]
    img.pixels.foreach_set(px_.ravel())
    sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 92
    img.save_render(RC.check_out_path(p), scene=sc)
    bpy.data.images.remove(img)


def view_dirs(cam_, w_, h_):
    """per pixel: unit vector from the surface toward the camera (CameraVector), top row first"""
    Mw = np.array(cam_.matrix_world)[:3, :3]
    if cam_.data.type == 'ORTHO':
        d = np.broadcast_to(Mw @ np.array([0.0, 0.0, -1.0]), (h_, w_, 3))
    else:
        s = cam_.data.sensor_width / cam_.data.lens / w_
        xs = (np.arange(w_) - w_ / 2.0 + 0.5) * s
        ys = (h_ / 2.0 - np.arange(h_) - 0.5) * s
        X, Y = np.meshgrid(xs, ys)
        d = np.stack([X, Y, -np.ones_like(X)], -1) @ Mw.T
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    return -d


def silhouette(nrm_rgba, dep_rgba, cam_):
    """CN_InkSilhouette (Soft 0, FacetSil 0) on the normal pass: ink = saturate(w + 0.5 - q / fwidth(q)), q = (N.V)^2,
    w = SilWidthPx x the distance fade; derivatives only between pixels of the same smooth surface (same object, depth
    within 3 %, normals within 60 deg), one-sided where the other side is not (a GPU quad extrapolates its triangle)"""
    h_, w_ = nrm_rgba.shape[:2]
    fg = nrm_rgba[:, :, 3] > 0.5
    N = nrm_rgba[:, :, :3] * 2.0 - 1.0
    N = N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    Vd = view_dirs(cam_, w_, h_)
    q = (N * Vd).sum(-1) ** 2
    z = dep_rgba[:, :, 0]; ob = dep_rgba[:, :, 1]

    def same(a, b):
        return fg[a] & fg[b] & (np.abs(ob[a] - ob[b]) < 1e-4) & (np.abs(z[a] - z[b]) < 0.03 * np.maximum(z[a], 1e-3)) & \
            ((N[a] * N[b]).sum(-1) > 0.5)

    def deriv(axis, q=q):
        dq = np.full((h_, w_), np.nan)
        if axis == 1:
            okf = same((slice(None), slice(0, -1)), (slice(None), slice(1, None)))
            df = q[:, 1:] - q[:, :-1]
            fwd = np.full((h_, w_), np.nan); fwd[:, :-1] = np.where(okf, df, np.nan)
            bwd = np.full((h_, w_), np.nan); bwd[:, 1:] = np.where(okf, df, np.nan)
        else:
            okf = same((slice(0, -1), slice(None)), (slice(1, None), slice(None)))
            df = q[1:, :] - q[:-1, :]
            fwd = np.full((h_, w_), np.nan); fwd[:-1, :] = np.where(okf, df, np.nan)
            bwd = np.full((h_, w_), np.nan); bwd[1:, :] = np.where(okf, df, np.nan)
        dq = np.where(np.isnan(fwd), bwd, fwd)
        return np.abs(np.nan_to_num(dq, nan=0.0))
    fw = deriv(0) + deriv(1)
    pxd = q / np.maximum(fw, 1e-6)
    ndv = np.sqrt(q)
    fwn = deriv(0, ndv) + deriv(1, ndv)
    t2 = np.clip((fwn - 0.5 * SIL_SLOPE) / max(0.5 * SIL_SLOPE, 1e-9), 0, 1)
    curv = t2 * t2 * (3 - 2 * t2) if SIL_SLOPE > 0 else np.ones_like(q)
    if cam_.data.type == 'ORTHO':
        fade = np.ones_like(z)
    else:
        t_ = np.clip((z - SIL_F0) / max(SIL_F1 - SIL_F0, 1e-3), 0, 1)
        fade = 1.0 - t_ * t_ * (3 - 2 * t_)
    ink = np.clip(SIL_PX * fade + 0.5 - pxd, 0, 1) * fg * (fade > 0) * curv
    return ink


MAT_CACHE = {}


def use_variant(variant):
    if variant not in MAT_CACHE:
        assign(variant)
        MAT_CACHE[variant] = {o.name: o.data.materials[0] for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render}
    else:
        for o in bpy.data.objects:
            if o.name in MAT_CACHE[variant]:
                o.data.materials.clear(); o.data.materials.append(MAT_CACHE[variant][o.name])


def render_to(p, variant, fmt):
    try:
        sc.eevee.taa_render_samples = 32 if variant == 'lit' else 1
    except Exception:
        pass
    sc.render.filter_size = 1.5 if variant == 'lit' else 0.01
    sc.render.dither_intensity = 1.0 if (variant == 'lit' and fmt == 'JPEG') else 0.0
    sun.hide_render = variant != 'lit'
    sc.render.film_transparent = variant in ('nrm', 'dep')
    if fmt == 'JPEG':
        sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 92
    elif fmt == 'EXR':
        sc.render.image_settings.file_format = 'OPEN_EXR'; sc.render.image_settings.color_mode = 'RGBA'
        sc.render.image_settings.color_depth = '32'; sc.render.image_settings.exr_codec = 'ZIP'
    else:
        sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGB'
        sc.render.image_settings.color_depth = '16' if variant == 'idx' else '8'
    sc.render.filepath = RC.check_out_path(p)
    bpy.ops.render.render(write_still=True)


POST = LIGHT == 'game' or SIL
INK_SIL = RC.hex_lin(RC.INK_HEX)
out = {}
rendered = []
for variant in VARIANTS:
    use_variant(variant)
    for sh in SHOTS:
        R.set_shot(sc, cam, sh, None, shots)
        set_shot_ink(cam, sc.render.resolution_x * RES_SCALE / 100.0)
        t = time.time()
        if variant == 'lit':
            lodtag = '' if (LOD_M == '0' and LOD_H == '0') else ('_lod' + LOD if LOD_M == LOD_H else '_lodm%sh%s' % (LOD_M, LOD_H))
            if NO_LODTAG:                   # review shots at a fixed distance: the LOD is part of the camera's definition
                lodtag = ''
            p = '%s/%s_baked%s%s.jpg' % (RC.MEDIA, sh, lodtag, ('_' + TAG) if TAG else '')
            if not POST:
                render_to(p, 'lit', 'JPEG')
            else:
                tmp = '%s/_post_%s_lit.exr' % (PREV_DIR, sh)
                render_to(tmp, 'lit', 'EXR')
                lin = read_exr(tmp)[:, :, :3].astype(np.float64)
                os.remove(tmp)
                if SIL:
                    use_variant('nrm'); tn = '%s/_post_%s_nrm.exr' % (PREV_DIR, sh); render_to(tn, 'nrm', 'EXR')
                    use_variant('dep'); td = '%s/_post_%s_dep.exr' % (PREV_DIR, sh); render_to(td, 'dep', 'EXR')
                    nrm, dep = read_exr(tn), read_exr(td)
                    os.remove(tn); os.remove(td)
                    use_variant('lit')
                    ink_s = silhouette(nrm, dep, cam)
                    iv = INK_SIL * (LOOK['lit_mix'] * (0.6 if LIGHT != 'game' else 0.15) + LOOK['shade_lift'] / EXPOSURE)
                    lin = lin * (1 - ink_s[:, :, None]) + iv[None, None, :] * ink_s[:, :, None]
                    out.setdefault('silhouette', {})[sh] = dict(ink_pixels=int((ink_s > 0.5).sum()))
                if LIGHT == 'game':
                    disp = LK.dm().forward(lin.reshape(-1, 3), LK.startup_pp(), LK.STARTUP['ev100']).reshape(lin.shape) / 255.0
                else:
                    disp = LK.l2s(lin)
                write_jpg(p, disp)
        else:
            p = '%s/%s_%s%s.png' % (PREV_DIR, sh, variant, ('_' + TAG) if TAG else '')
            render_to(p, variant, 'PNG')
        rendered.append(p)
        log('render', p, '%.1fs' % (time.time() - t))


# ------------------------------------------------------------------ colour check
def load_px(p):
    im = bpy.data.images.load(p, check_existing=False)
    im.colorspace_settings.name = 'Non-Color'
    w_, h_ = im.size
    a = np.empty(w_ * h_ * 4, np.float32); im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h_, w_, 4)[:, :, :3]


if 'flat' in VARIANTS and 'idx' in VARIANTS:
    srgb_pal = RC.lin_to_srgb(RC.PAL)
    res = {}
    for sh in SHOTS:
        tg = ('_' + TAG) if TAG else ''
        flat = load_px('%s/%s_flat%s.png' % (PREV_DIR, sh, tg))
        idr = load_px('%s/%s_idx%s.png' % (PREV_DIR, sh, tg))
        lin = RC.srgb_to_lin(idr)
        idx_f = lin[:, :, 0] * 32.0 - 0.5
        idx = np.round(idx_f).astype(np.int64)
        good = (np.abs(idx_f - idx) < 0.15) & (lin[:, :, 1] < 0.004) & (lin[:, :, 2] < 0.004) & (idx >= 0) & (idx < 24)
        # away from edges: the 3x3 neighbourhood has the same index and is clean too
        g2 = good.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                g2 &= np.roll(np.roll(good & (idx == idx), dy, 0), dx, 1) & (np.roll(np.roll(idx, dy, 0), dx, 1) == idx)
        tp = '%s/%s_toon_after.jpg' % (RC.MEDIA_FULL, sh)
        toon = load_px(tp) if os.path.isfile(tp) else None
        per = {}
        for k in np.unique(idx[g2]):
            m = g2 & (idx == k)
            n = int(m.sum())
            if n < 50:
                continue
            exp = srgb_pal[k]
            fe = np.abs(flat[m] - exp).max(1) * 255.0
            r_ = dict(pixels=n, flat_err_8bit=dict(median=round(float(np.median(fe)), 2), p99=round(float(np.percentile(fe, 99)), 2),
                                                   max=round(float(fe.max()), 2)))
            if toon is not None and toon.shape == flat.shape:
                tl = RC.srgb_to_lin(toon[m])
                bands = {}
                for bname, mul in (('lit_1.0', 1.0), ('mid_0.70', 0.70), ('shade_0.40', 0.40)):
                    e = np.abs(RC.lin_to_srgb(RC.PAL[k] * mul) - toon[m]).max(1) * 255.0
                    bands[bname] = round(float((e <= 6.0).mean()), 3)
                ratio = np.median(tl / np.maximum(RC.PAL[k], 1e-4), axis=0)
                r_['approved_toon'] = dict(share_within_6_of_band=bands, any_band=round(sum(bands.values()), 3),
                                           median_ratio_to_palette=np.round(ratio, 3).tolist())
            per[RC.PALETTE_SLOTS[k][0]] = r_
        res[sh] = per
        log('colour check', sh, {k: (v['pixels'], v['flat_err_8bit']['max'], v.get('approved_toon', {}).get('any_band'))
                                 for k, v in per.items()})
    allmax = max((v['flat_err_8bit']['max'] for s in res.values() for v in s.values()), default=None)
    cc = dict(about='Per palette slot: the preview\'s flat render (base colour as emission, no light) against the palette '
                    '(8-bit sRGB), on pixels with no ink, no dot, away from edges (the index pass); and the approved toon '
                    'render of the same camera at those pixels: share within 6/255 of the palette colour times each '
                    'cel band (1.0 lit, 0.70, 0.40), and its median linear ratio to the palette.',
              shots=res, flat_max_err_8bit=allmax, spare_slot_pixels=int(sum(v['pixels'] for s in res.values()
                                                                               for k, v in s.items() if k.startswith('spare'))))
    RC.dump_json(cc, RC.CHECK_DIR + '/colour_check.json')
    RC.dump_json(cc, RC.DOCS + '/export_colour_check.json')
    log('colour check: flat max error %s / 255' % allmax)
RC.dump_json(dict(rendered=rendered, shots=SHOTS, variants=VARIANTS, lod=LOD, lod_m=LOD_M, lod_h=LOD_H, tex=TEXD,
                  props_palette=PROPS_PAL, light=LIGHT, sky_r=SKY_R if LIGHT == 'game' else None, look=LOOK,
                  silhouette=dict(on=SIL, px=SIL_PX, fade=[SIL_F0, SIL_F1], min_slope=SIL_SLOPE, **out.get('silhouette', {})) if SIL else None,
                  ink=dict(near=INK_NEAR, far=INK_FAR, far_start=FAR0, far_end=FAR1, dmax=DMAX, dneg=DNEG, comic=COMIC,
                           aa=INK_AA, fade=[FADE0, FADE1], opacity_far=OPA_FAR),
                  textures={g: RC.md5_file(os.path.join(TEXD, RC.PAGES[g]['tex'])) for g in RC.PAGES}),
             '%s/preview_%s%s.json' % (PREV_DIR, '_'.join(VARIANTS), ('_' + TAG) if TAG else ''))
sys.stdout.flush()
os._exit(0)
