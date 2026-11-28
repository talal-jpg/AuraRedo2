"""Preview renders for the detail pass (round 3): before / after, flat palette + ink (toon) or clay + cavity.

  blender -b --factory-startup --python detail_render.py -- --look toon|clay --states before,after \
      --shots side,q34,close_flank,close_pod --out DIR [--res 1920x1080] [--samples 48]

Opens rig/detail/AirshipRig_detail.blend and never saves it. "before" hides every Detail_* collection; "after" shows
them. Looks:
  toon   reference 1's palette by part (hull paint, bands, pipes, pods, nozzles ...), three-band cel shading, ink
  paper  the in-game look: paper white everywhere, blue-grey cel shading, navy ink, dark recesses
  clay   grey clay + cavity (Cycles ambient occlusion), like Talal's Burrower screenshot
Ink (toon, paper) is weighted by size: a heavy line on silhouettes and outer contours, a thin one on creases and borders,
none on rivets (their faces carry a Freestyle face mark; comic artists draw rivet rows as dots, which the bake will do).
"""
import bpy, sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
import rig_common as C
import detail_common as D

DETAIL_BLEND = C.RIG + '/detail/AirshipRig_detail.blend'
INK = (0.075, 0.085, 0.12)
BG = (0.62, 0.66, 0.74)
EXTRA = {                        # colours for the ship's own parts in the toon look (palette of reference 1)
    'hull_paint': (0.90, 0.60, 0.17),
    'deck':       (0.52, 0.46, 0.38),
    'wood':       (0.45, 0.30, 0.18),
    'glass':      (0.85, 0.85, 0.70),
    'recess':     (0.20, 0.17, 0.16),
}

SHOTS = {
    # name: (camera location, target, lens mm or ('ortho', scale), resolution)
    'side': ((6.0, 70.0, 2.0), (6.0, 0.0, 2.0), ('ortho', 58.0), (2560, 1100)),
    'q34': ((12.25, 25.75, -9.85), (-1.5, 7.0, -0.6), 35.0, (1920, 1080)),
    'close_flank': ((-0.6, 13.8, -1.6), (-2.6, 8.3, -0.5), 28.0, (1920, 1080)),
    'close_pod': ((7.6, 9.7, -4.6), (3.9, 5.5, -2.5), 28.0, (1920, 1080)),
    'pocket': ((9.5, 12.5, -0.8), (3.9, 4.9, 0.6), 30.0, (1920, 1080)),
    'below': ((-1.5, 10.5, -10.0), (-1.5, 6.0, -1.5), 32.0, (1920, 1080)),
    'pod_low': ((7.2, 9.8, -8.6), (3.7, 5.0, -4.2), 30.0, (1920, 1080)),
}
POSES = {   # rig check poses (RIG_CONTRACT limits): pod pitch/roll +-3, nozzle pitch/roll +-5, petal flare -10..+35
    'poseA': {'PodPitchDeg_FL': 3.0, 'PodRollDeg_FL': 3.0, 'NozzlePitchDeg_FL': -5.0, 'NozzleRollDeg_FL': 5.0,
              'NozzleFlareDeg_FL': 35.0},
    'poseB': {'PodPitchDeg_FL': -3.0, 'PodRollDeg_FL': -3.0, 'NozzlePitchDeg_FL': 5.0, 'NozzleRollDeg_FL': -5.0,
              'NozzleFlareDeg_FL': -10.0},
}


def argv_opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


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


def ship_face_classes():
    """palette key per SM_Airship polygon, from the research island classifier"""
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


def apply_toon(scene, look='toon'):
    pal = dict(D.PALETTE); pal.update(EXTRA)
    if look == 'paper':
        dark = {'recess'}
        mats = {k: toon_material('MP_' + k, (0.20, 0.22, 0.30) if k in dark else PAPER, paper=True) for k in pal}
    else:
        mats = {k: toon_material('MT_' + k, c) for k, c in pal.items()}
    ship, keys = ship_face_classes()
    me = ship.ob.data
    me.materials.clear()
    order = sorted(set(keys))
    for k in order:
        me.materials.append(mats[k])
    idx = np.array([order.index(k) for k in keys], np.int32)
    me.polygons.foreach_set('material_index', idx)
    me.update()
    # detail objects: swap the placeholder palette materials for their toon versions
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        if ob.name.startswith('SM_AirshipDetail_'):
            for i, m in enumerate(ob.data.materials):
                k = m.get('palette_key') if m else None
                if k:
                    ob.data.materials[i] = mats[k]
        elif ob.name.startswith('SM_AirshipProp_'):
            k = 'wood' if 'Wheel' in ob.name or 'Carriage' in ob.name else 'dark_metal'
            ob.data.materials.clear(); ob.data.materials.append(mats[k])
    # light + world + ink
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
    if look == 'paper':
        ink_lines(scene, 2.6, 1.1, NAVY, material_boundary=False)
    else:
        ink_lines(scene, 2.4, 1.2, INK, material_boundary=True)
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'


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


def set_shot(sc, cam, name, res=None):
    loc, tgt, lens, rs = SHOTS[name]
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


def main():
    o = argv_opts()
    look = o.get('look', 'toon')
    states = o.get('states', 'before,after').split(',')
    shots = o.get('shots', 'side,q34,close_flank,close_pod').split(',')
    out = o.get('out', '/tmp')
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=o.get('blend', DETAIL_BLEND))
    sc, cam = base_scene()
    if look in ('toon', 'paper'):
        apply_toon(sc, look)
    else:
        dev = apply_clay(sc, int(o.get('samples', 48)))
        print('[render] cycles device', dev)
    pose = o.get('pose')
    if pose:
        arm = bpy.data.objects['Armature']
        spec = C.load_json(C.CHECKS + '/bones_spec.json')
        C.apply_pose(arm, spec, POSES[pose])
        bpy.context.view_layer.update()
    for st in states:
        show_details(st == 'after')
        for sh in shots:
            t0 = time.time()
            set_shot(sc, cam, sh)
            sc.render.filepath = os.path.join(out, '%s_%s_%s%s.jpg' % (sh, look, st, '_' + pose if pose else ''))
            bpy.ops.render.render(write_still=True)
            print('[render]', sc.render.filepath, '%.1f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
