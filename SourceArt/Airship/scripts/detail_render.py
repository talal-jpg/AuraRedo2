"""Preview renders for the detail pass (round 3): before / after, the FINAL look (toon), paper, clay, any zones.

  blender_capped.sh --python detail_render.py -- --look toon|paper|clay --states before,after \
      --shots side,q34,close_flank,close_pod --out DIR [--res 1920x1080] [--samples 48] [--scale 50] \
      [--blend FILE] [--zones 1,2,3] [--base-edits all|none|z6,z7] [--turrets on|off] \
      [--turret-yaw L,R] [--turret-pitch L,R] [--cam 'name:x,y,z:tx,ty,tz:lens[:WxH]'] [--shots-file shots.json] \
      [--pose poseA|poseB|poseA:FR|'{json}'] [--tag TEXT]

Opens --blend (default: zone 1's rig/detail/zones/AirshipRig_detail_z1.blend; any zone file or rig/AirshipRig.blend)
and NEVER saves it. --zones appends the Detail_ZN collections of those zones' .blends (missing ones are skipped and
listed), so one render shows several zones (the assembler view). States: "before" = the ship as it is (no details, no
base edits); "after" = every loaded Detail_* collection + the base edits (scripts/base_edits/z*.json, applied to an
in-memory copy of SM_Airship) + the base colour overrides (scripts/base_recolor/z*.json, r3_base_recolor.py: since
2026-11-28 the keel block under the bow is rust; --base-recolor none leaves them out). The two front machine-gun turrets (separate props in rig/props/AirshipProps.blend, read
only) are placed at both mounts in every render (--turrets off leaves them out; --turret-yaw / --turret-pitch in
degrees, Blender convention: + yaw turns the muzzle toward +Y, + pitch raises it).
Looks:
  toon   THE FINAL LOOK (Talal 2026-11-28: reference 1's yellow and rust): flat colours by role / by part, three-band
         cel shading, ink weighted by size; alias: final
  paper  the old in-game look: paper white, blue-grey cel shading, navy ink (kept for comparison)
  clay   grey clay + cavity (Cycles ambient occlusion), like Talal's Burrower screenshot
Shots: the built-in SHOTS below, plus --cam (repeatable; lens 'o58' = orthographic, scale 58) and --shots-file (JSON
{name: {"loc": [..], "tgt": [..], "lens": 35 or "ortho": 58, "res": [w, h]}}). --shots lists the names to render.
Output: <out>/<shot>_<look>_<state>[_<pose>][_<tag>].jpg
Ink: heavy on silhouettes and outer contours, thin on creases and borders, none on rivets (Freestyle face marks).
"""
import bpy, sys, os, math, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V, Matrix
import rig_common as C
import detail_common as D

DETAIL_BLEND = D.zone_blend(1)          # read only; never saved
INK = (0.075, 0.085, 0.12)
BG = (0.62, 0.66, 0.74)
EXTRA = {                        # colours for the ship's own parts in the toon look (palette of reference 1)
    'hull_paint': (0.90, 0.60, 0.17),
    'deck':       (0.52, 0.46, 0.38),
    'wood':       (0.45, 0.30, 0.18),
    'glass':      (0.85, 0.85, 0.70),
    'recess':     (0.20, 0.17, 0.16),
    # palette slot of a base colour override (r3_base_recolor.py; EXPORT_R3.md slot 16): Talal 2026-11-28 made the
    # keel block rust. The registry's colour_key sets the colour (apply_toon); this is the same default.
    'keel_block': D.PALETTE['rust_red'],
}
AFTER_IDX = None                 # toon looks: material index per SM_Airship face for the 'after' state (with overrides)

SHOTS = {
    # name: (camera location, target, lens mm or ('ortho', scale), resolution)
    'side': ((6.0, 70.0, 2.0), (6.0, 0.0, 2.0), ('ortho', 58.0), (2560, 1100)),
    'q34': ((12.25, 25.75, -9.85), (-1.5, 7.0, -0.6), 35.0, (1920, 1080)),
    'close_flank': ((-0.6, 13.8, -1.6), (-2.6, 8.3, -0.5), 28.0, (1920, 1080)),
    'close_pod': ((7.6, 9.7, -4.6), (3.9, 5.5, -2.5), 28.0, (1920, 1080)),
    'pocket': ((9.5, 12.5, -0.8), (3.9, 4.9, 0.6), 30.0, (1920, 1080)),
    'below': ((-1.5, 10.5, -10.0), (-1.5, 6.0, -1.5), 32.0, (1920, 1080)),
    'pod_low': ((7.2, 9.8, -8.6), (3.7, 5.0, -4.2), 30.0, (1920, 1080)),
    # round 3 whole-ship shots (2026-11-28)
    'side_stbd': ((6.0, -70.0, 2.0), (6.0, 0.0, 2.0), ('ortho', 58.0), (2560, 1100)),
    'top': ((6.0, -0.001, 80.0), (6.0, 0.0, 0.0), ('ortho', 58.0), (2560, 1100)),
    'bottom': ((6.0, 0.001, -80.0), (6.0, 0.0, 0.0), ('ortho', 58.0), (2560, 1100)),
    'q34_stbd': ((12.25, -25.75, -9.85), (-1.5, -7.0, -0.6), 35.0, (1920, 1080)),
    'q34_aft': ((-36.0, 21.0, 9.0), (-9.0, 2.0, 0.5), 35.0, (1920, 1080)),
    'q34_aft_stbd': ((-36.0, -21.0, 9.0), (-9.0, -2.0, 0.5), 35.0, (1920, 1080)),
    'q34_bow': ((44.0, 20.0, 6.0), (17.0, 0.0, 2.5), 35.0, (1920, 1080)),
    'q34_bow_stbd': ((44.0, -20.0, 6.0), (17.0, 0.0, 2.5), 35.0, (1920, 1080)),
    'stern': ((-48.0, 0.001, 3.0), (-16.0, 0.0, 1.2), 30.0, (1920, 1080)),
    'stern_q34': ((-36.0, 17.0, 5.0), (-17.0, 4.0, 1.2), 30.0, (1920, 1080)),
    'fan_back_L': ((-27.0, 12.5, 3.0), (-17.4, 7.6, 1.4), 32.0, (1920, 1080)),
    'fan_back_R': ((-27.0, -12.5, 3.0), (-17.4, -7.6, 1.4), 32.0, (1920, 1080)),
    'fwd_deck': ((-4.0, 9.0, 13.0), (13.0, 0.0, 4.5), 28.0, (1920, 1080)),
    'stairs_area': ((1.0, 8.5, 7.0), (9.0, 0.0, 4.0), 24.0, (1920, 1080)),
    'gantry_port': ((20.0, 22.0, 6.0), (20.0, 0.0, 4.0), 30.0, (1920, 1080)),
    'belly': ((-1.5, -9.0, -24.0), (-1.5, 0.0, -3.0), 28.0, (1920, 1080)),
    'q34_belly': ((14.0, 18.0, -20.0), (-2.0, 0.0, -3.5), 32.0, (1920, 1080)),
}


def pose_ctrl(name):
    """rig poses for renders: 'poseA' / 'poseB' (pod FL), 'poseA:FR' (any pod), or a JSON dict of control values
    (RIG_CONTRACT names, e.g. '{"TurbineYawDeg_L": 12, "RudderDeg": -30}')"""
    if name.startswith('{'):
        return json.loads(name)
    base, _, pod = name.partition(':')
    pod = pod or 'FL'
    s = {'poseA': (3.0, 3.0, -5.0, 5.0, 35.0), 'poseB': (-3.0, -3.0, 5.0, -5.0, -10.0)}[base]
    return {'PodPitchDeg_' + pod: s[0], 'PodRollDeg_' + pod: s[1], 'NozzlePitchDeg_' + pod: s[2],
            'NozzleRollDeg_' + pod: s[3], 'NozzleFlareDeg_' + pod: s[4]}


def argv_opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {'cam': []}
    for i, k in enumerate(a):
        if k.startswith('--'):
            v = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
            if k == '--cam':
                o['cam'].append(v)
            else:
                o[k[2:]] = v
    return o


def parse_cam(spec):
    """'name:x,y,z:tx,ty,tz:lens[:WxH]' (lens 'o58' = orthographic, scale 58)"""
    parts = spec.split(':')
    name = parts[0]
    loc = tuple(float(v) for v in parts[1].split(','))
    tgt = tuple(float(v) for v in parts[2].split(','))
    lens = ('ortho', float(parts[3][1:])) if parts[3].startswith('o') else float(parts[3])
    res = tuple(int(v) for v in parts[4].split('x')) if len(parts) > 4 else (1920, 1080)
    return name, (loc, tgt, lens, res)


def load_shots(o):
    shots = dict(SHOTS)
    if o.get('shots-file'):
        for k, v in json.load(open(o['shots-file'])).items():
            lens = ('ortho', float(v['ortho'])) if 'ortho' in v else float(v.get('lens', 35.0))
            shots[k] = (tuple(v['loc']), tuple(v['tgt']), lens, tuple(v.get('res', (1920, 1080))))
    for spec in o.get('cam', []):
        k, v = parse_cam(spec)
        shots[k] = v
    return shots


# ------------------------------------------------------------------ materials
def toon_material(name, col, paper=False):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    dif = nt.nodes.new('ShaderNodeBsdfDiffuse')
    dif.inputs['Color'].default_value = (1, 1, 1, 1)
    s2r = nt.nodes.new('ShaderNodeShaderToRGB')
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'CONSTANT'
    el = ramp.color_ramp.elements
    if paper:       # the in-game comic look: paper, a blue-grey shade, a darker blue-grey core shadow
        el[0].position = 0.0; el[0].color = (0.66, 0.70, 0.80, 1)
        el[1].position = 0.12; el[1].color = (0.82, 0.85, 0.91, 1)
    else:
        el[0].position = 0.0; el[0].color = (0.40, 0.40, 0.46, 1)
        el[1].position = 0.12; el[1].color = (0.70, 0.70, 0.74, 1)
    e3 = el.new(0.45); e3.color = (1.0, 1.0, 1.0, 1)
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    mix.inputs[6].default_value = tuple(col) + (1.0,)
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    nt.links.new(s2r.outputs['Color'], bw.inputs[0])
    nt.links.new(bw.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs['Color'], mix.inputs[7])
    nt.links.new(mix.outputs[2], em.inputs['Color'])
    nt.links.new(em.outputs[0], out.inputs['Surface'])
    m.diffuse_color = tuple(col) + (1.0,)
    return m


def clay_material():
    m = bpy.data.materials.get('M_PreviewClay') or bpy.data.materials.new('M_PreviewClay')
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    ao = nt.nodes.new('ShaderNodeAmbientOcclusion')
    ao.samples = 12
    ao.inputs['Distance'].default_value = 0.35
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0; ramp.color_ramp.elements[0].color = (0.10, 0.10, 0.11, 1)
    ramp.color_ramp.elements[1].position = 0.9; ramp.color_ramp.elements[1].color = (0.62, 0.62, 0.62, 1)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bs.inputs['Roughness'].default_value = 0.65
    nt.links.new(ao.outputs['AO'], ramp.inputs[0])
    nt.links.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    nt.links.new(bs.outputs[0], out.inputs['Surface'])
    return m


def ship_face_classes(recolor='all'):
    """palette key per SM_Airship polygon: the research island classifier, then the registered base colour overrides
    (r3_base_recolor.py; recolor 'none' = the ship as it is). The round 3 export takes its palette from here too."""
    ship, out = _part_classes()
    if recolor not in (None, 'none'):
        import r3_base_recolor as BR
        for k, sl in enumerate(BR.face_slots(ship, recolor)):
            if sl is not None:
                out[k] = sl
    return ship, out


def _part_classes():
    import detail_ship as S
    ship = S.Ship(bpy)
    me = ship.ob.data
    nrm = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
    cen = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
    # pocket walls / roofs (the Boolean cut faces) are dark recesses, as with M_Recess in Talal's file
    pockets = [ship.pod_frame(p) for p in C.PODS]
    recess = np.zeros(len(cen), bool)
    for (O, T0, A, NP) in pockets:
        rel = cen - T0
        h = rel @ A
        d = np.linalg.norm(rel - np.outer(h, A), axis=1)
        recess |= (np.abs(d - 2.85) < 0.06) & (h > -2.85) & (h < 1.25)
        recess |= (np.abs(h + 2.8) < 0.04) & (d < 2.86)
    out = []
    for k in range(len(me.polygons)):
        src, piece, bone, isl = ship.p_src[k], ship.p_piece[k], ship.p_bone[k], ship.p_island[k]
        if isl == S.SKIN and recess[k]:
            key = 'recess'
        elif isl == S.SKIN:
            key = 'deck' if (nrm[k][2] > 0.9 and cen[k][2] > 1.5) else 'hull_paint'
        elif src == 'SteamPipes':
            key = 'copper'
        elif src in ('SteamBands', 'DeckRails', 'Gantry'):
            key = 'dark_metal'
        elif src == 'DeckProps':
            key = 'wood'
        elif src in ('BowWedge', 'Rudder'):
            key = 'rust_red'
        elif src == 'Underside_Front':
            key = 'machinery'
        elif bone.startswith('Thruster_') and ('Nozzle' in bone or 'Petal' in bone):
            key = 'dark_metal'
        elif bone.startswith('Thruster_'):
            key = {'drum': 'machinery', 'rib': 'dark_metal', 'mount_collar': 'dark_metal', 'bolt': 'bolt',
                   'pipe': 'copper', 'clamp': 'dark_metal', 'side_box': 'machinery'}.get(piece, 'rust_red')
        elif bone.startswith('Turbine_') and 'Rotor' in bone:
            key = 'dark_metal'
        elif bone.startswith('Turbine_'):
            key = 'paint_orange'
        elif bone.startswith('SearchLight') or bone.startswith('Winch') or bone.startswith('Chain'):
            key = 'brass' if 'Head' in bone else 'dark_metal'
        elif src == 'Hull':
            key = 'rust_red'
        else:
            key = 'dark_metal'
        out.append(key)
    return ship, out


PAPER = (0.953, 0.933, 0.894)
NAVY = (0.11, 0.13, 0.19)


def ink_lines(scene, heavy, fine, color, material_boundary):
    """two Freestyle line sets, both skipping faces with a Freestyle mark (rivets): heavy = silhouettes, outer contours
    and open borders; fine = creases (and material boundaries in the palette look)"""
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = 'ABSOLUTE'
    scene.render.line_thickness = 1.0
    vl = scene.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.crease_angle = math.radians(138)
    fs.use_culling = True
    while len(fs.linesets):
        fs.linesets.remove(fs.linesets[0])
    for name, th, kinds in (('InkHeavy', heavy, ('silhouette', 'border', 'external_contour')),
                            ('InkFine', fine, ('crease',) + (('material_boundary',) if material_boundary else ()))):
        ls = fs.linesets.new(name)
        ls.select_by_visibility = True
        ls.visibility = 'VISIBLE'
        ls.select_by_edge_types = True
        for a in ('silhouette', 'border', 'crease', 'external_contour', 'material_boundary', 'contour'):
            setattr(ls, 'select_' + a, a in kinds)
        ls.select_by_face_marks = True
        ls.face_mark_negation = 'EXCLUSIVE'
        ls.face_mark_condition = 'ONE'
        st = ls.linestyle or bpy.data.linestyles.new(name)
        ls.linestyle = st
        st.color = color
        st.thickness = th
        st.thickness_position = 'CENTER'


def toon_world(scene):
    sun = bpy.data.lights.get('PreviewSunToon') or bpy.data.lights.new('PreviewSunToon', 'SUN')
    sun.energy = 4.0
    sun.angle = math.radians(0.5)
    so = bpy.data.objects.get('PreviewSunToon') or bpy.data.objects.new('PreviewSunToon', sun)
    if so.name not in scene.collection.objects:
        scene.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), math.radians(-12), math.radians(150))
    world = scene.world or bpy.data.worlds.new('W')
    scene.world = world
    world.use_nodes = True
    wt = world.node_tree
    wt.nodes.clear()
    wout = wt.nodes.new('ShaderNodeOutputWorld')
    lp = wt.nodes.new('ShaderNodeLightPath')
    amb = wt.nodes.new('ShaderNodeBackground'); amb.inputs['Color'].default_value = BG + (1.0,); amb.inputs['Strength'].default_value = 0.35
    cam = wt.nodes.new('ShaderNodeBackground'); cam.inputs['Color'].default_value = BG + (1.0,); cam.inputs['Strength'].default_value = 1.0
    mx = wt.nodes.new('ShaderNodeMixShader')
    wt.links.new(lp.outputs['Is Camera Ray'], mx.inputs[0])
    wt.links.new(amb.outputs[0], mx.inputs[1]); wt.links.new(cam.outputs[0], mx.inputs[2])
    wt.links.new(mx.outputs[0], wout.inputs['Surface'])
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'


def apply_toon(scene, look='toon'):
    global AFTER_IDX
    import r3_base_recolor as BR
    pal = dict(D.PALETTE); pal.update(EXTRA)
    pal.update({sl: D.PALETTE[ck] for sl, ck in BR.slot_colours().items() if ck in D.PALETTE})
    if look == 'paper':
        dark = {'recess'}
        mats = {k: toon_material('MP_' + k, (0.20, 0.22, 0.30) if k in dark else PAPER, paper=True) for k in pal}
    else:
        mats = {k: toon_material('MT_' + k, c) for k, c in pal.items()}
    ship, keys = ship_face_classes('none')            # the ship as it is ('before')
    slots = BR.face_slots(ship, 'all')
    keys1 = [sl if sl is not None else k for k, sl in zip(keys, slots)]    # with the overrides ('after')
    me = ship.ob.data
    me.materials.clear()
    order = sorted(set(keys) | set(keys1))
    for k in order:
        me.materials.append(mats[k])
    idx = np.array([order.index(k) for k in keys], np.int32)
    me.polygons.foreach_set('material_index', idx)
    me.update()
    idx1 = np.array([order.index(k) for k in keys1], np.int32)
    AFTER_IDX = idx1 if (idx1 != idx).any() else None
    # detail objects: swap the role materials for their toon versions
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        if ob.name.startswith('SM_AirshipDetail_'):
            for i, m in enumerate(ob.data.materials):
                k = m.get('palette_key') if m else None
                if k:
                    ob.data.materials[i] = mats[k]
        elif ob.name.startswith('SM_AirshipProp_'):
            k = 'wood' if 'Wheel' in ob.name or 'Carriage' in ob.name else \
                ('machinery' if ob.name.endswith('_Gun') else 'dark_metal')
            ob.data.materials.clear(); ob.data.materials.append(mats[k])
    toon_world(scene)
    if look == 'paper':
        ink_lines(scene, 2.6, 1.1, NAVY, material_boundary=False)
    else:
        ink_lines(scene, 2.4, 1.2, INK, material_boundary=True)
    return ship


def apply_clay(scene, samples):
    m = clay_material()
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            ob.data.materials.clear()
            ob.data.materials.append(m)
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    dev = None
    for t in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = t
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type == t]
            if gpus:
                for d in prefs.devices:
                    d.use = d.type == t
                dev = t
                break
        except Exception:
            continue
    scene.cycles.device = 'GPU' if dev else 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 3
    sun = bpy.data.lights.get('PreviewSunClay') or bpy.data.lights.new('PreviewSunClay', 'SUN')
    sun.energy = 3.0
    sun.angle = math.radians(3)
    so = bpy.data.objects.get('PreviewSunClay') or bpy.data.objects.new('PreviewSunClay', sun)
    if so.name not in scene.collection.objects:
        scene.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), math.radians(-12), math.radians(150))
    world = scene.world or bpy.data.worlds.new('W')
    scene.world = world
    world.use_nodes = True
    wt = world.node_tree
    wt.nodes.clear()
    wout = wt.nodes.new('ShaderNodeOutputWorld')
    bgn = wt.nodes.new('ShaderNodeBackground')
    bgn.inputs['Color'].default_value = (0.55, 0.56, 0.58, 1.0)
    bgn.inputs['Strength'].default_value = 0.9
    wt.links.new(bgn.outputs[0], wout.inputs['Surface'])
    scene.render.use_freestyle = False
    scene.view_settings.view_transform = 'Standard'
    return dev


def base_scene():
    sc = bpy.context.scene
    for c in bpy.data.collections:
        if c.name in ('Airship_Parts', 'Airship_Cutters', 'Airship_Backups'):
            c.hide_render = True
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and not o.name.startswith('Preview'):
            o.hide_render = True
        if o.name.startswith('UCX_'):
            o.hide_render = True
    for n in ('PreviewSun',):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_render = True
    cam = bpy.data.objects.get('DetailCam') or bpy.data.objects.new('DetailCam', bpy.data.cameras.new('DetailCam'))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.image_settings.file_format = 'JPEG'
    sc.render.image_settings.quality = 92
    sc.render.resolution_percentage = 100
    return sc, cam


def set_shot(sc, cam, name, res=None, shots=None):
    loc, tgt, lens, rs = (shots or SHOTS)[name]
    cam.location = V(loc)
    cam.rotation_euler = (V(tgt) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    if isinstance(lens, tuple):
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = lens[1]
    else:
        cam.data.type = 'PERSP'
        cam.data.lens = lens
    cam.data.clip_start = 0.1
    cam.data.clip_end = 400
    w, h = res or rs
    sc.render.resolution_x, sc.render.resolution_y = w, h


def show_details(on):
    for c in bpy.data.collections:
        if c.name.startswith('Detail_'):
            c.hide_render = not on
            c.hide_viewport = not on


# ------------------------------------------------------------------ turrets (separate props, read only)
def add_turrets(yaw=(0.0, 0.0), pitch=(0.0, 0.0)):
    """append Turret_Base / Turret_Gun from rig/props/AirshipProps.blend and place a pair at each mount (UE (2100,
    -+245, 655) cm = Blender (21, +-2.45, 6.55); base origin = yaw axis on the deck top, gun origin = trunnion 1.5 m
    above it). yaw / pitch per (L, R) in degrees (Blender: + yaw turns the muzzle toward +Y, + pitch raises it)."""
    with bpy.data.libraries.load(C.PROPS_BLEND, link=False) as (src, dst):
        dst.objects = [n for n in ('Turret_Base', 'Turret_Gun') if n in src.objects]
    got = {o.name.split('.')[0]: o for o in dst.objects if o is not None}
    if len(got) < 2:
        print('[render] turrets not found in', C.PROPS_BLEND)
        return []
    tb, tg = got['Turret_Base'], got['Turret_Gun']
    # trunnion 1.50 m above the yaw axis (turret_dims.json pivot_height_cm 150; model_turret.py PIVOT_H). Appended
    # objects are not in the scene yet, so their matrix_world is not evaluated: never derive the pivot from it.
    pivot = V((0.0, 0.0, 1.50))
    coll = bpy.data.collections.get('Preview_Turrets') or bpy.data.collections.new('Preview_Turrets')
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    out = []
    for k, s in enumerate(('L', 'R')):
        mount = V(tuple(C.TURRET_MOUNTS[s]) + (6.55,))
        Mb = Matrix.Translation(mount) @ Matrix.Rotation(math.radians(yaw[k]), 4, 'Z')
        Mg = Mb @ Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(-pitch[k]), 4, 'Y')
        for src_ob, M, nm in ((tb, Mb, 'Base'), (tg, Mg, 'Gun')):
            ob = src_ob.copy()
            ob.name = 'SM_AirshipProp_Turret_%s_%s' % (s, nm)
            ob.parent = None
            ob.matrix_world = M
            coll.objects.link(ob)
            out.append(ob)
    for o in (tb, tg):
        bpy.data.objects.remove(o)
    return out


def edited_ship(which, recolor=False):
    """an in-memory copy of SM_Airship minus the faces the registered base edits delete (None if there are none and
    no colour override applies). recolor: give the copy the 'after' classes of apply_toon (AFTER_IDX)"""
    import detail_base_edits as BE
    import detail_ship as S
    rep = {}
    ship_ob = bpy.data.objects[C.HULL_OBJ]
    m = np.zeros(len(ship_ob.data.polygons), bool)
    if which not in (None, 'none'):
        ship = S.Ship(bpy)
        m = BE.deleted_mask(ship, which, rep)
    if not m.any() and not (recolor and AFTER_IDX is not None):
        return None, rep
    ed = BE.edited_copy(bpy, ship_ob, m)
    if recolor and AFTER_IDX is not None:
        ed.data.polygons.foreach_set('material_index', AFTER_IDX[~m].astype(np.int32))
        ed.data.update()
    return ed, rep


def setup(o):
    """open the base file, add zones / turrets / base edits, apply the look. Returns (scene, camera, info, edited)"""
    look = o.get('look', 'toon')
    look = 'toon' if look == 'final' else look
    bpy.ops.wm.open_mainfile(filepath=o.get('blend', DETAIL_BLEND))
    sc, cam = base_scene()
    info = dict(blend=o.get('blend', DETAIL_BLEND), zones_loaded=[], zones_missing=[])
    arm = bpy.data.objects['Armature']
    for z in [z for z in str(o.get('zones', '')).split(',') if z.strip()]:
        c = D.append_zone(z.strip(), arm)
        (info['zones_loaded'] if c else info['zones_missing']).append(z.strip())
    info['detail_collections'] = sorted(c.name for c in bpy.data.collections if c.name.startswith('Detail_'))
    if str(o.get('turrets', 'on')) != 'off':
        ty = tuple(float(v) for v in str(o.get('turret-yaw', '0,0')).split(','))
        tp = tuple(float(v) for v in str(o.get('turret-pitch', '0,0')).split(','))
        info['turrets'] = [t.name for t in add_turrets(ty, tp)]
    if look in ('toon', 'paper'):
        apply_toon(sc, look)
    else:
        info['cycles_device'] = apply_clay(sc, int(o.get('samples', 48)))
    rc = look in ('toon', 'paper') and str(o.get('base-recolor', 'all')) != 'none'
    ed, rep = edited_ship(o.get('base-edits', 'all'), recolor=rc)
    info['base_edits'] = rep
    info['edited'] = ed is not None
    info['base_recolor'] = (sorted({sl for sl in __import__('r3_base_recolor').slot_colours()}) if rc and
                            AFTER_IDX is not None else [])
    pose = o.get('pose')
    if pose:
        spec = C.load_json(C.CHECKS + '/bones_spec.json')
        C.apply_pose(arm, spec, pose_ctrl(pose))
        bpy.context.view_layer.update()
    return sc, cam, info, ed


def show_state(st, ed):
    show_details(st == 'after')
    ship = bpy.data.objects[C.HULL_OBJ]
    if ed is not None:
        ship.hide_render = st == 'after'
        ed.hide_render = st != 'after'


def main():
    o = argv_opts()
    look = o.get('look', 'toon')
    look = 'toon' if look == 'final' else look
    states = o.get('states', 'before,after').split(',')
    shots_all = load_shots(o)
    shots = o.get('shots', 'side,q34,close_flank,close_pod').split(',')
    out = o.get('out', D.TMP_DIR + '/renders')
    res = tuple(int(v) for v in o['res'].split('x')) if o.get('res') else None
    os.makedirs(out, exist_ok=True)
    sc, cam, info, ed = setup(o)
    if o.get('scale'):
        sc.render.resolution_percentage = int(o['scale'])
    print('[render] setup', json.dumps(info))
    pose = o.get('pose')
    ptag = ('_' + pose.replace(':', '')) if pose and not pose.startswith('{') else ('_pose' if pose else '')
    tag = ('_' + o['tag']) if o.get('tag') else ''
    for st in states:
        show_state(st, ed)
        for sh in shots:
            t0 = time.time()
            set_shot(sc, cam, sh, res, shots_all)
            sc.render.filepath = os.path.join(out, '%s_%s_%s%s%s.jpg' % (sh, look, st, ptag, tag))
            bpy.ops.render.render(write_still=True)
            print('[render]', sc.render.filepath, '%.1f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
