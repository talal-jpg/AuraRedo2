"""One shared comic-ink texture for the airship props (helm + cannon + front turret), in the ship's look.

Headless, re-runnable (never touches Helm.blend, Cannon.blend, Turret.blend or Talal's StylizedAirship.blend):

  blender -b --factory-startup --python rig/scripts/bake_props_comic.py -- [--stages assemble,atlas,bake,render]
          [--cpu] [--tag _t1] [--set key=value ...]

Stages (default: all four, in order):
  assemble  append the "Helm", "Cannon" and "Turret" collections of rig/props/Helm.blend + Cannon.blend +
            Turret.blend (round 2) into rig/props/AirshipProps.blend. Names, mesh data, origins, transforms and the
            Cannon_Muzzle -> Cannon_Barrel and Turret_Muzzle -> Turret_Gun parenting are kept. Every mesh gets one material slot M_AirshipProps and a face
            attribute part_kind (0 wood, 1 iron, 2 brass, 3 rope, 4 bore; the cannon's comes from its old
            M_Cannon_* / M_Turret_* slots). The helm's preview colour attribute PartColor is dropped.
  atlas     one atlas in the first (only) UV channel "UVMap" of every mesh. The modellers' islands keep their
            shape and seams; each island is scaled so texel density is equal across all meshes (WEIGHTS:
            barrel, carriage cheeks, helm wheel rim + spokes x1.25; hidden islands keep their reduced share),
            then all islands are packed together (Blender packer, PACK_TRIES, biggest result kept) with a
            0.002 margin (4 px at 2048). Checked with an exact triangle-overlap test (SAT) across all
            objects + a 2048 raster (shared pixels, island gaps). Report: rig/checks/props_atlas/atlas.json.
  bake      the ship's comic ink shader (StylizedAirship/scripts/comic_lines.py: navy ink #1C2230 on paper
            #F3EEE4, Bevel outlines heavier on the shadow side of key light (0.30, 0.35, 0.89), AO crease
            lines, AO spotted blacks, tapered hatch strokes along the shadow edge) with its lengths scaled
            for 1-3 m props (P below), baked with Cycles (EMIT) into one 2048 mask. AO and Bevel only see
            the object itself, so every prop part is inked standalone (no ship, no neighbour part: moving
            parts carry no contact shadows). Key light per prop (LIGHT_OF / BIAS_OF): the helm uses the
            ship's; the cannon bake is shared by 4 copies facing port and starboard, so it uses the mean of
            the two, light from above, plus a +0.2 fill. The multi-turn helm wheel uses a constant N.L (no
            light-bound hatching that would turn with it) and an axle-view outline on its round spokes and
            handles. Post-process: the ship's (2 x [1,2,1] blur, smoothstep 0.38..0.52), after growing the
            raw ink by dilate_px texels inside each island (see "Line weight" below). Colour = flat per-kind
            wash (wood paper, iron light cool grey, brass light warm, rope a little darker, bore ink) with
            the ink on top; texels outside the islands are paper.
            -> rig/props/textures/T_AirshipProps_ComicLines.png (sRGB), T_AirshipProps_ComicMask.png (linear)
            M_AirshipProps: ComicLines -> Base Color (roughness 0.9, like M_Airship), ComicMask unplugged.
  render    previews that use only the baked colour map (Workbench flat texture, like renders/comic5_*.png):
            studio side by side, close-ups, on the ship (SM_Airship from a copy of StylizedAirship.blend)
            at 10 m, 30 m and the 65 m game camera with x4 crops, one lit view (Cycles, Principled
            roughness 0.9 as in Unreal). -> rig/renders/props/baked<tag>_*.png. Never saves.

Line weight (measured 2026-11-22, renders/props/baked_iter/): the hull's comic strokes are wide in world space
(Bevel 0.08 on a 39 px/m texture, then blur + threshold: about 6-15 cm). Prop lines baked with radii scaled
down (Bevel 0.03, t1) came out about 1.3 cm wide, a third of the hull's on screen at the same distance, and the
helm vanished at 30 m. The final set (Bevel 0.055 + 3 texel growth at ~225-280 px/m, about 3 cm median
strokes, 7 cm on the heavy shadow-side edges) matches the hull's weight from 8 m to the 65 m game camera and
stays crisp up close (comic5_podclose has the same bold-brush scale).
"""
import bpy, bmesh, math, os, sys, json, time, hashlib, shutil
import numpy as np
from mathutils import Vector as V, Matrix

RIG = "/mnt/new_partition/BlenderProjects/StylizedAirship/rig/"
PROPS = RIG + "props/"
SRC = {"Helm": PROPS + "Helm.blend", "Cannon": PROPS + "Cannon.blend", "Turret": PROPS + "Turret.blend"}
OUT_BLEND = PROPS + "AirshipProps.blend"
TEXDIR = PROPS + "textures/"
CHECKS = RIG + "checks/props_atlas/"
RENDERS = RIG + "renders/props/"
TALAL_SHIP = "/mnt/new_partition/BlenderProjects/StylizedAirship/StylizedAirship.blend"  # read only
SHIP_COPY = CHECKS + "Ship_copy.blend"
RES = 2048
MARGIN = 0.002                      # island gap as a fraction of the atlas: ~4 px at 2048
KIND = {"wood": 0, "iron": 1, "brass": 2, "rope": 3, "bore": 4}
# multi-turn helm wheel: constant N.L (light-bound hatching would turn with it and dash the round spokes);
# its spokes and handles get an axle-view outline instead (AXIAL, see build_bake_material)
SPIN = ("Helm_Wheel",)
AXIAL = ("Helm_Wheel",)
# ink lengths (bevel radius, AO crease / spot distances, hatch spacing, stroke growth) are tuned for 1-3 m props; the
# round 2 helm is smaller (wheel x 0.45, pedestal x 0.6 of its old size), so its ink is drawn at the same scale to keep
# the look it had (with the full lengths the 15 cm hub flange inks solid)
INK_SCALE = {"Helm_Wheel": 0.45, "Helm_Pedestal": 0.6}

# texel weight (linear) per island, decided by WEIGHT_RULES below
W_HI = 1.25

# ---------------------------------------------------------------- comic ink parameters
# Ship (comic_lines.py, hull parts 10-50 m): bevel 0.08, AO crease 0.15, AO spots 1.2, hatch 2.4 /m,
# wobble noise 1.6, dash 0.7, panel lines every 2.2 m. Props are 1-3 m: lengths scaled down, stroke weight
# brought back up with dilate_px so the lines are as heavy on screen as the hull's (see "Line weight").
P = dict(
    bevel=0.055,           # Bevel radius (m) for the outlines
    bevel_samples=16,
    edge_thr=0.26,         # outline threshold on the lit side (ship 0.26) ...
    edge_shadow=0.14,      # ... lowered by this much on the shadow side (heavier lines there)
    crease_dist=0.08,      # short AO = crease lines in concave corners
    crease_thr=0.68,
    spot_dist=0.30,        # long AO < spot_lo..spot_hi = solid "spotted black"
    spot_lo=0.22, spot_hi=0.26,
    hatch_freq=5.0,        # hatch strokes per metre across the shadow edge
    hatch_halfw=0.05,      # stroke half width as a fraction of the stroke spacing (ship 0.07; grown by dilate)
    dash_scale=1.9,        # dash noise along a stroke (ship 0.7)
    wobble_scale=4.3,      # hand wobble noise (ship 1.6)
    panel_spacing=0.0,     # m between broken panel lines (0 = off; ship 2.2)
    spin_ndl=0.35,         # constant N.L for parts in SPIN (lit side: no light-bound hatching)
    cannon_fill=0.2,       # N.L bias for the cannon parts (see BIAS_OF)
    axial_lo=0.62, axial_hi=0.70,         # |N.X| band for the AXIAL outline (ink below lo)
    samples=256,           # Cycles samples for the mask bake
    ink_lo=0.38, ink_hi=0.52, smooth=2,   # post-process, same as the ship
    margin_px=8,           # bake margin (extend)
    edge_vd_lo=0.8, edge_vd_hi=0.985,     # Bevel-vs-shading normal range that maps to the edge term (ship)
    dilate_px=3,           # stroke weight: grow the raw ink by this many texels (inside its own island)
                           # before the ship's blur + threshold (x the object's INK_SCALE, at least 1 texel)
)
PAPER_HEX, INK_HEX = "F3EEE4", "1C2230"
TONE_HEX = {0: PAPER_HEX,      # wood: plain paper
            1: "D9DCE1",       # iron: light cool-grey wash
            2: "EEDFBC",       # brass: light warm wash
            3: "E3DCCD",       # rope: a little darker than paper
            4: INK_HEX}        # bore: solid ink (also forced into the mask)
LIGHT = V((0.30, 0.35, 0.89)).normalized()


def LIGHT_OF(name):
    """Key light per prop in its own frame. The helm sits in the ship frame: the ship's key light. The cannon
    bake is shared by 4 copies that face +Y (port) and -Y (starboard); the ship light seen from the cannon
    frame is (0.35, -0.30, 0.89) on one side and (-0.35, 0.30, 0.89) on the other, so the shared bake uses
    their mean, light from straight above."""
    return tuple(LIGHT) if name.startswith("Helm") else (0.0, 0.0, 1.0)


def INK_SCALE_OF(name):
    return next((v for k, v in INK_SCALE.items() if name.startswith(k)), 1.0)


def BIAS_OF(name):
    """Added to N.L. The cannon's straight-down light puts every vertical face on the terminator (band
    hatching all over the cheeks and wheels): a fill of +0.2 keeps vertical faces on the lit side."""
    return 0.0 if name.startswith("Helm") else P["cannon_fill"]


def srgb(h):
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def lin(h):
    f = lambda x: x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return tuple(float(f(c)) for c in srgb(h)) + (1.0,)


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def log(*a):
    print("[props]", *a, flush=True)


T0 = time.time()


# ================================================================ args
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = dict(stages=["assemble", "atlas", "bake", "render"], cpu=False, tag="", sets={})
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--stages":
            a["stages"] = argv[i + 1].split(","); i += 2
        elif k == "--cpu":
            a["cpu"] = True; i += 1
        elif k == "--tag":
            a["tag"] = argv[i + 1]; i += 2
        elif k == "--set":
            kk, vv = argv[i + 1].split("=")
            a["sets"][kk] = vv; i += 2
        else:
            raise SystemExit(f"unknown arg {k}")
    for kk, vv in a["sets"].items():
        assert kk in P, kk
        P[kk] = type(P[kk])(float(vv)) if not isinstance(P[kk], int) else int(float(vv))
    return a


def mesh_objects():
    return sorted((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: o.name)


def open_props():
    bpy.ops.wm.open_mainfile(filepath=OUT_BLEND)


def save_props():
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, check_existing=False, compress=True)
    log("saved", OUT_BLEND)


# ================================================================ 1 assemble
def kind_of_material(name):
    n = name.lower()
    for k in ("bore", "iron", "wood", "brass", "rope"):
        if k in n:
            return KIND[k]
    raise ValueError(f"no part kind for material {name}")


def props_material():
    m = bpy.data.materials.get("M_AirshipProps") or bpy.data.materials.new("M_AirshipProps")
    m.use_nodes = True
    m.diffuse_color = lin(PAPER_HEX)
    bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bs.inputs["Roughness"].default_value = 0.9
    bs.inputs["Base Color"].default_value = lin(PAPER_HEX)
    return m


def stage_assemble():
    src_md5 = {k: md5(p) for k, p in SRC.items()}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    for cname, path in SRC.items():
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            assert cname in src.collections, (cname, src.collections)
            dst.collections = [cname]
        sc.collection.children.link(dst.collections[0])
    mat = props_material()
    rep = {}
    for ob in mesh_objects():
        me = ob.data
        nf = len(me.polygons)
        if "part_kind" in me.attributes:
            kinds = np.zeros(nf, np.int32)
            me.attributes["part_kind"].data.foreach_get("value", kinds)
        else:
            mi = np.zeros(nf, np.int32)
            me.polygons.foreach_get("material_index", mi)
            lut = np.array([kind_of_material(m.name) for m in me.materials], np.int32)
            kinds = lut[mi]
            me.attributes.new("part_kind", "INT", "FACE").data.foreach_set("value", kinds)
        if "PartColor" in me.attributes:
            me.attributes.remove(me.attributes["PartColor"])
        me.materials.clear()
        me.materials.append(mat)
        me.polygons.foreach_set("material_index", np.zeros(nf, np.int32))
        me.update()
        assert [u.name for u in me.uv_layers] == ["UVMap"], (ob.name, [u.name for u in me.uv_layers])
        co = np.zeros(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        rep[ob.name] = dict(verts=len(me.vertices), tris=sum(len(p.vertices) - 2 for p in me.polygons),
                            loc=[round(x, 4) for x in ob.location], kinds=np.bincount(kinds, minlength=5).tolist(),
                            co_md5=hashlib.md5(co.tobytes()).hexdigest())
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    # append leaves empty Library references behind: everything is local, drop them
    assert all(i.library is None for i in list(bpy.data.objects) + list(bpy.data.meshes) + list(bpy.data.collections))
    for lib in list(bpy.data.libraries):
        bpy.data.libraries.remove(lib)
    bpy.context.view_layer.update()
    mu = bpy.data.objects["Cannon_Muzzle"]
    assert mu.parent and mu.parent.name == "Cannon_Barrel"
    mw = tuple(round(x, 4) for x in mu.matrix_world.translation)
    log("muzzle world", mw)
    assert max(abs(a - b) for a, b in zip(mw, (1.86, 0.0, 0.80))) < 1e-3, mw
    tm = bpy.data.objects["Turret_Muzzle"]
    assert tm.parent and tm.parent.name == "Turret_Gun", tm.parent
    log("turret muzzle local", tuple(round(x, 4) for x in tm.location), "gun origin",
        tuple(round(x, 4) for x in bpy.data.objects["Turret_Gun"].location))
    os.makedirs(CHECKS, exist_ok=True)
    save_props()
    for k, p in SRC.items():
        assert md5(p) == src_md5[k], f"{p} changed!"
    rep["_src_md5"] = src_md5
    json.dump(rep, open(CHECKS + "assemble.json", "w"), indent=1)
    log("assembled", {k: v["tris"] for k, v in rep.items() if not k.startswith("_")})


# ================================================================ 2 atlas
def mesh_arrays(me):
    nl, nf = len(me.loops), len(me.polygons)
    lv = np.zeros(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
    ls = np.zeros(nf, np.int32); me.polygons.foreach_get("loop_start", ls)
    lt = np.zeros(nf, np.int32); me.polygons.foreach_get("loop_total", lt)
    co = np.zeros(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co)
    uv = np.zeros(nl * 2, np.float32); me.uv_layers["UVMap"].data.foreach_get("uv", uv)
    fa = np.zeros(nf, np.float32); me.polygons.foreach_get("area", fa)
    fc = np.zeros(nf * 3, np.float32); me.polygons.foreach_get("center", fc)
    fn = np.zeros(nf * 3, np.float32); me.polygons.foreach_get("normal", fn)
    kinds = np.zeros(nf, np.int32); me.attributes["part_kind"].data.foreach_get("value", kinds)
    return dict(lv=lv, ls=ls, lt=lt, co=co.reshape(-1, 3).astype(np.float64), uv=uv.reshape(-1, 2).astype(np.float64),
                fa=fa.astype(np.float64), fc=fc.reshape(-1, 3), fn=fn.reshape(-1, 3), kinds=kinds,
                fol=np.repeat(np.arange(nf), lt))


def face_islands(d):
    """UV islands: faces joined where they share a mesh vertex with the same UV (like the packer)."""
    nf = len(d["ls"])
    q = np.round(d["uv"] * 2 ** 20).astype(np.int64)
    keys = np.stack([d["lv"].astype(np.int64), q[:, 0], q[:, 1]], 1)
    kid = np.unique(keys, axis=0, return_inverse=True)[1].ravel()
    fol = d["fol"]
    lab = np.arange(nf)
    for _ in range(10000):
        kmin = np.full(kid.max() + 1, nf, np.int64)
        np.minimum.at(kmin, kid, lab[fol])
        new = lab.copy()
        np.minimum.at(new, fol, kmin[kid])
        new = new[new]
        if (new == lab).all():
            break
        lab = new
    _, isl = np.unique(lab, return_inverse=True)
    return isl.ravel()


def uv_face_areas(d, signed=False):
    uv, ls, lt = d["uv"], d["ls"], d["lt"]
    nxt = np.arange(len(uv)) + 1
    ends = ls + lt
    nxt[ends - 1] = ls
    cr = uv[:, 0] * uv[nxt, 1] - uv[nxt, 0] * uv[:, 1]
    a = np.zeros(len(ls)); np.add.at(a, d["fol"], cr)
    return 0.5 * a if signed else 0.5 * np.abs(a)


def island_table(ob, d, isl):
    n = isl.max() + 1
    a3 = np.bincount(isl, d["fa"], n)
    a2 = np.bincount(isl, uv_face_areas(d), n)
    cen = np.stack([np.bincount(isl, d["fc"][:, k] * d["fa"], n) for k in range(3)], 1) / np.maximum(a3, 1e-12)[:, None]
    kind = np.array([np.bincount(d["kinds"][isl == i], d["fa"][isl == i], 5).argmax() for i in range(n)])
    dens = np.sqrt(a2 / np.maximum(a3, 1e-12))
    return dict(a3=a3, a2=a2, cen=cen, kind=kind, dens=dens)


def weight_rules(name, t):
    """Linear texel weight per island: barrel, carriage cheeks and helm wheel rim + spokes get more."""
    n = len(t["a3"])
    w = np.ones(n)
    group = np.array(["other"] * n, dtype=object)
    if name == "Cannon_Barrel":
        hi = t["kind"] != KIND["bore"]
        w[hi] = W_HI; group[hi] = "barrel"
        group[~hi] = "bore"
    elif name == "Cannon_Carriage":
        y = np.abs(t["cen"][:, 1])
        hi = (t["kind"] == KIND["wood"]) & (y > 0.30) & (y < 0.46)
        w[hi] = W_HI; group[hi] = "carriage_cheeks"
    elif name == "Helm_Wheel":
        r = np.hypot(t["cen"][:, 1], t["cen"][:, 2])  # local: axle = X through the origin
        hi = r > HELM_RIM_SPOKES_R
        w[hi] = W_HI; group[hi] = "helm_rim_spokes"
    elif name == "Turret_Gun":                        # the gunner looks at it from 1 m
        hi = t["kind"] != KIND["bore"]
        w[hi] = W_HI; group[hi] = "turret_gun"
    return w, group


# Helm_Wheel islands farther than this from the axle get W_HI (rim, outer spokes, handles, bands): 0.36 for the v2
# 3.1 m wheel, scaled with it (v3 tips at 0.70 m)
HELM_RIM_SPOKES_R = 0.36 * 0.70 / 1.55


def hull_area(pts):
    pts = np.unique(np.round(pts, 9), axis=0)
    if len(pts) < 3:
        return 0.0
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(ps):
        h = []
        for q in ps:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h
    hl = half(pts)[:-1] + half(pts[::-1])[:-1]
    x, y = np.array(hl).T
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


SPLIT_FILL = 0.40   # islands filling less of their convex hull than this (rings, long arcs) ...
SPLIT_MIN = 0.0001  # ... and bigger than this (UV area after scaling) are cut into arcs for the packer


def split_hollow(d, isl, i, uv):
    """Cut a hollow island (ring / long arc) into 2 or 4 sectors around its centre, moving the pieces apart
    so the packer sees separate islands (the packer leaves ring holes empty). UVs keep their shape."""
    fol = d["fol"]
    fi = np.where(isl == i)[0]
    if len(fi) < 8:
        return 0
    li = np.where(isl[fol] == i)[0]
    sub = dict(d, uv=uv)
    fa = uv_face_areas(sub)[fi]
    area = fa.sum()
    if area < SPLIT_MIN:
        return 0
    fill = area / max(hull_area(uv[li]), 1e-12)
    if fill >= SPLIT_FILL:
        return 0
    k = 4 if fill < 0.22 else 2
    # face centres in UV, sector by angle around the area-weighted centre
    fc = np.zeros((len(d["ls"]), 2)); np.add.at(fc, fol, uv); fc /= d["lt"][:, None]
    cen = (fc[fi] * fa[:, None]).sum(0) / area
    ang = np.arctan2(fc[fi, 1] - cen[1], fc[fi, 0] - cen[0])
    sec = np.floor((ang + math.pi) / (2 * math.pi) * k).astype(int) % k
    for j in range(1, k):
        fj = fi[sec == j]
        lj = np.concatenate([np.arange(d["ls"][f], d["ls"][f] + d["lt"][f]) for f in fj]) if len(fj) else []
        uv[lj] += (0.031 * j, 0.017 * j)
    return 1


PACK_TRIES = [dict(rotate=True, rotate_method="ANY", shape_method="CONCAVE"),
              dict(rotate=True, rotate_method="CARDINAL", shape_method="CONCAVE"),
              dict(rotate=True, rotate_method="AXIS_ALIGNED", shape_method="CONCAVE"),
              dict(rotate=True, rotate_method="ANY", shape_method="CONVEX")]


def pack_all(obs):
    sc = bpy.context.scene
    vl = bpy.context.view_layer
    for o in sc.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    vl.objects.active = obs[0]
    sc.tool_settings.use_uv_select_sync = True
    base = {}
    for o in obs:
        b = np.zeros(len(o.data.loops) * 2, np.float32)
        o.data.uv_layers["UVMap"].data.foreach_get("uv", b)
        base[o.name] = b
    best, tries = None, []
    for cfg in PACK_TRIES:
        for o in obs:  # re-fetch after every mode switch (holding uv data across a toggle can crash)
            bpy.data.objects[o.name].data.uv_layers["UVMap"].data.foreach_set("uv", base[o.name])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.reveal(select=False)
        bpy.ops.mesh.select_all(action="SELECT")
        t = time.time()
        try:
            bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=cfg["rotate"], rotate_method=cfg["rotate_method"],
                                    scale=True, merge_overlap=False, margin_method="FRACTION", margin=MARGIN,
                                    pin=False, shape_method=cfg["shape_method"])
        except (TypeError, RuntimeError) as e:
            log("pack setting skipped", cfg, e)
            bpy.ops.object.mode_set(mode="OBJECT")
            continue
        bpy.ops.object.mode_set(mode="OBJECT")
        res, area = {}, 0.0
        for o in obs:
            me = bpy.data.objects[o.name].data
            u = np.zeros(len(me.loops) * 2, np.float32)
            me.uv_layers["UVMap"].data.foreach_get("uv", u)
            res[o.name] = u
            d = mesh_arrays(me)
            area += uv_face_areas(d).sum()
        lo = min(r.reshape(-1, 2).min(0).min() for r in res.values())
        hi = max(r.reshape(-1, 2).max(0).max() for r in res.values())
        log(f"PACK {cfg} uv area {area:.4f}  bounds {lo:.4f}..{hi:.4f}  {time.time() - t:.1f}s")
        tries.append(dict(cfg=cfg, uv_area=round(float(area), 5), bounds=[float(lo), float(hi)]))
        if lo >= -1e-6 and hi <= 1 + 1e-6 and (best is None or area > best[0]):
            best = (area, res, cfg)
    assert best, "no pack setting fit the 0-1 square"
    for o in obs:
        bpy.data.objects[o.name].data.uv_layers["UVMap"].data.foreach_set("uv", best[1][o.name])
        bpy.data.objects[o.name].data.update()
    log("PACK best", best[2], f"uv area {best[0]:.4f}")
    return best[2], tries


def all_uv_tris(obs):
    """All UV triangles: (T (n,3,2) float64, object index, global island id)."""
    Ts, oid, iid = [], [], []
    base = 0
    for k, ob in enumerate(obs):
        me = ob.data
        me.calc_loop_triangles()
        tl = np.zeros(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("loops", tl)
        tp = np.zeros(len(me.loop_triangles), np.int32)
        me.loop_triangles.foreach_get("polygon_index", tp)
        d = mesh_arrays(me)
        isl = face_islands(d)
        Ts.append(d["uv"][tl].reshape(-1, 3, 2))
        oid.append(np.full(len(tp), k))
        iid.append(isl[tp] + base)
        base += isl.max() + 1
    return np.concatenate(Ts), np.concatenate(oid), np.concatenate(iid)


def sat_overlap(T, pairs, eps=1e-7):
    A, B = T[pairs[:, 0]], T[pairs[:, 1]]
    sep = np.zeros(len(pairs), bool)
    for Pt in (A, B):
        for i in range(3):
            e = Pt[:, (i + 1) % 3] - Pt[:, i]
            ax = np.stack([-e[:, 1], e[:, 0]], 1)
            ax /= np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-30)
            pa = np.einsum("nkj,nj->nk", A, ax)
            pb = np.einsum("nkj,nj->nk", B, ax)
            ov = np.minimum(pa.max(1), pb.max(1)) - np.maximum(pa.min(1), pb.min(1))
            sep |= ov <= eps
    return ~sep


def overlap_test(T, G=256):
    """Exact triangle-pair overlap test (separating axis), grid broad phase over the 0-1 square."""
    area = 0.5 * np.abs((T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1]) - (T[:, 2, 0] - T[:, 0, 0]) * (T[:, 1, 1] - T[:, 0, 1]))
    ok = np.where(area > 1e-14)[0]
    lo = np.clip(np.floor(T.min(1) * G).astype(int), 0, G - 1)
    hi = np.clip(np.floor(T.max(1) * G).astype(int), 0, G - 1)
    cells = {}
    for t in ok:
        for cx in range(lo[t, 0], hi[t, 0] + 1):
            for cy in range(lo[t, 1], hi[t, 1] + 1):
                cells.setdefault(cx * G + cy, []).append(t)
    pairs = set()
    for lst in cells.values():
        if len(lst) > 1:
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    pairs.add((lst[i], lst[j]))
    pairs = np.array(sorted(pairs), np.int64).reshape(-1, 2)
    hit = np.zeros(len(pairs), bool)
    for s in range(0, len(pairs), 200000):
        hit[s:s + 200000] = sat_overlap(T, pairs[s:s + 200000])
    return pairs[hit], len(pairs), int(len(T) - len(ok))


def raster_islands(T, iid, res=RES):
    """Island id per texel (texel centre inside the triangle), -1 empty; count of claims per texel."""
    ids = np.full((res, res), -1, np.int32)
    cnt = np.zeros((res, res), np.uint8)
    for t in range(len(T)):
        p = T[t] * res
        x0, y0 = np.maximum(np.floor(p.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(p.max(0)).astype(int), res)
        if x1 <= x0 or y1 <= y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        (ax, ay), (bx, by), (cx, cy) = p
        dd = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(dd) < 1e-12:
            continue
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / dd
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / dd
        ins = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
        sub_i = ids[y0:y1, x0:x1]
        sub_c = cnt[y0:y1, x0:x1]
        new = ins & (sub_i != iid[t])
        sub_c[new] += 1
        sub_i[ins] = iid[t]
    return ids, cnt


def island_gaps(ids, rmax=4):
    """Contacts between different islands within a Chebyshev distance r (texels), r = 1..rmax."""
    out = {}
    for r in range(1, rmax + 1):
        c = 0
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                s = np.roll(np.roll(ids, dy, 0), dx, 1)
                c += int(((ids >= 0) & (s >= 0) & (s != ids)).sum())
        out[r] = c // 2
    return out


def stage_atlas():
    open_props()
    obs = mesh_objects()
    pre = {}
    tables = {}
    # 1) per-island scale -> equal texel density (x weight); hidden islands keep their share
    work = []
    for ob in obs:
        d = mesh_arrays(ob.data)
        isl = face_islands(d)
        t = island_table(ob, d, isl)
        nd = np.median(t["dens"][t["dens"] > 0.5 * t["dens"].max()])  # the object's normal density
        w, group = weight_rules(ob.name, t)
        work.append((ob, d, isl, t, nd, w, group))
    # scaled UV area = a3 * (dens * s)^2; one global factor brings the total near the final size
    tot = sum(float((t["a3"] * (t["dens"] * w / nd) ** 2).sum()) for _, _, _, t, nd, w, _ in work)
    g = math.sqrt(0.6 / tot)
    for ob, d, isl, t, nd, w, group in work:
        me = ob.data
        hidden = t["dens"] < 0.5 * nd
        s = g * w / nd
        uv = d["uv"].copy()
        nsplit = 0
        for i in range(len(t["a3"])):
            li = np.where(isl[d["fol"]] == i)[0]
            c = 0.5 * (uv[li].min(0) + uv[li].max(0))
            uv[li] = c + (uv[li] - c) * s[i]
            nsplit += split_hollow(d, isl, i, uv)
        me.uv_layers["UVMap"].data.foreach_set("uv", uv.astype(np.float32).ravel())
        me.update()
        group[hidden] = "hidden"
        tables[ob.name] = dict(isl=isl, t=t, w=w, group=group, hidden=hidden)
        pre[ob.name] = dict(islands=int(len(t["a3"])), hidden_islands=int(hidden.sum()), src_density=float(nd),
                            hollow_islands_split=nsplit,
                            area_m2=round(float(t["a3"].sum()), 4), hidden_area_m2=round(float(t["a3"][hidden].sum()), 4))
        log(ob.name, pre[ob.name])
    # 2) pack all together
    best_cfg, tries = pack_all(obs)
    # 3) checks + density report
    T, oid, iid = all_uv_tris(obs)
    bad, npairs, degen = overlap_test(T)
    flipped = {}
    rep_obj = {}
    groups = {}
    for k, ob in enumerate(obs):
        d = mesh_arrays(ob.data)
        sa = uv_face_areas(d, signed=True)
        flipped[ob.name] = int((sa < 0).sum())
        tb = tables[ob.name]
        a2 = np.bincount(tb["isl"], np.abs(sa), len(tb["t"]["a3"]))
        dens = np.sqrt(a2 / np.maximum(tb["t"]["a3"], 1e-12)) * RES
        vis = ~tb["hidden"]
        rep_obj[ob.name] = dict(px_per_m=round(float(np.average(dens[vis], weights=tb["t"]["a3"][vis])), 1),
                                px_per_m_min=round(float(dens[vis].min()), 1), px_per_m_max=round(float(dens[vis].max()), 1),
                                hidden_px_per_m=round(float(dens[~vis].mean()), 1) if (~vis).any() else None,
                                uv_coverage=round(float(np.abs(sa).sum()), 4), flipped_faces=flipped[ob.name],
                                **pre[ob.name])
        for g in set(tb["group"]):
            m = tb["group"] == g
            gg = groups.setdefault(g, [0.0, 0.0])
            gg[0] += float((dens[m] * tb["t"]["a3"][m]).sum()); gg[1] += float(tb["t"]["a3"][m].sum())
    groups = {g: round(v[0] / max(v[1], 1e-9), 1) for g, v in groups.items()}
    ids, cnt = raster_islands(T, iid)
    shared = int((cnt > 1).sum())
    gaps = island_gaps(ids)
    lo, hi = float(T.min()), float(T.max())
    rep = dict(res=RES, margin_fraction=MARGIN, margin_px=MARGIN * RES, pack=best_cfg, pack_tries=tries,
               triangles=int(len(T)), islands=int(iid.max() + 1), uv_bounds=[lo, hi],
               overlap_pairs_tested=npairs, overlapping_triangle_pairs=int(len(bad)),
               overlapping_pairs_sample=[[int(a), int(b)] for a, b in bad[:20]], degenerate_uv_tris=degen,
               raster_shared_texels=shared, raster_coverage=round(float((ids >= 0).mean()), 4),
               island_contacts_within_px=gaps, px_per_m_by_group=groups, objects=rep_obj,
               weights=dict(high=W_HI, rules="barrel (not bore), carriage cheek islands (wood, |y| 0.30..0.46), "
                                              "Helm_Wheel islands > %.3f m from the axle (rim, spokes, handles, bands), "
                                              "Turret_Gun (not bore)" % HELM_RIM_SPOKES_R))
    json.dump(rep, open(CHECKS + "atlas.json", "w"), indent=1)
    log("ATLAS", json.dumps({k: rep[k] for k in ("islands", "triangles", "uv_bounds", "overlap_pairs_tested",
                                                   "overlapping_triangle_pairs", "raster_shared_texels",
                                                   "raster_coverage", "island_contacts_within_px", "px_per_m_by_group")}))
    for n, r in rep_obj.items():
        log("  ", n, r["px_per_m"], "px/m, coverage", r["uv_coverage"], "flipped", r["flipped_faces"])
    assert len(bad) == 0 and shared == 0 and lo >= 0 and hi <= 1, "atlas has overlaps or leaves 0-1"
    # layout picture: islands coloured per object, darker per island
    rng = np.random.default_rng(3)
    pal = np.array([[.85, .45, .35], [.35, .6, .85], [.55, .8, .4], [.9, .75, .3], [.7, .5, .85],
                    [.4, .8, .8], [.85, .55, .7], [.6, .6, .6], [.95, .6, .2]], np.float32)
    isl_obj = np.zeros(iid.max() + 1, np.int64); isl_obj[iid] = oid
    shade = rng.uniform(0.6, 1.0, iid.max() + 1).astype(np.float32)
    img = np.full((RES, RES, 3), 0.1, np.float32)
    m = ids >= 0
    img[m] = pal[isl_obj[ids[m]] % len(pal)] * shade[ids[m]][:, None]
    img[cnt > 1] = (1, 0, 0)
    write_png(RENDERS + "uv/props_atlas_uv.png", img[::2, ::2], srgb_data=True)
    legend = {ob.name: pal[k % len(pal)].round(2).tolist() for k, ob in enumerate(obs)}
    json.dump(legend, open(CHECKS + "atlas_uv_legend.json", "w"), indent=1)
    save_props()


def write_png(path, rgb, srgb_data=True, bw=False):
    """rgb: (h, w, 3) floats 0..1, row 0 = bottom (Blender order), values stored as given."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    h, w = rgb.shape[:2]
    name = os.path.basename(path)
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.colorspace_settings.name = "sRGB" if srgb_data else "Non-Color"
    px = np.ones((h, w, 4), np.float32)
    px[:, :, :3] = rgb
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


# ================================================================ 3 bake
def build_bake_material():
    """comic_lines.py build() with prop lengths (P) + part_kind (bore = ink, tones) + spin objects."""
    m = bpy.data.materials.get("M_PropsComicBake") or bpy.data.materials.new("M_PropsComicBake")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    k = [0]

    def node(kind, **props):
        n = N(kind)
        k[0] += 1
        n.location = (-3000 + k[0] * 120, (k[0] % 8) * -160)
        for a, v in props.items():
            setattr(n, a, v)
        return n

    def plug(sock, v):
        if isinstance(v, (int, float, tuple)):
            sock.default_value = v
        else:
            L(v, sock)

    def math_(op, a, b=None):
        n = node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b)):
            if v is not None:
                plug(n.inputs[i], v)
        return n.outputs[0]

    def vmath(op, a, b=None, scale=None):
        n = node("ShaderNodeVectorMath", operation=op)
        if a is not None:
            plug(n.inputs[0], a)
        if b is not None:
            plug(n.inputs[1], b)
        if scale is not None:
            plug(n.inputs["Scale"], scale)
        return n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs["Vector"]

    def mr(src, a, b, c, d):
        n = node("ShaderNodeMapRange", clamp=True)
        for i, v in zip((1, 2, 3, 4), (a, b, c, d)):
            plug(n.inputs[i], v)
        plug(n.inputs[0], src)
        return n.outputs[0]

    def noise(vec, scale, detail=1.0):
        n = node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        L(vec, n.inputs["Vector"])
        return n.outputs["Fac"]

    geo = node("ShaderNodeNewGeometry")
    pos, nrm = geo.outputs["Position"], geo.outputs["Normal"]
    sp = node("ShaderNodeSeparateXYZ"); L(pos, sp.inputs[0])
    ka = node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="part_kind")
    kind_attr = ka.outputs["Fac"]
    spin_a = node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="comic_spin")
    spin = spin_a.outputs["Fac"]
    la = node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="comic_light")
    light = vmath("NORMALIZE", la.outputs["Vector"])  # per-object key light (see LIGHT_OF)
    ba = node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="comic_bias")
    ax_a = node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="comic_axial")
    sc_a = node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="comic_scale")
    ink_s = sc_a.outputs["Fac"]          # per-object ink length scale (INK_SCALE_OF)

    def cmp_kind(kv):
        n = node("ShaderNodeMath", operation="COMPARE")
        L(kind_attr, n.inputs[0]); n.inputs[1].default_value = float(kv); n.inputs[2].default_value = 0.1
        return n.outputs[0]

    wob = math_("MULTIPLY", math_("SUBTRACT", noise(pos, P["wobble_scale"]), 0.5), 0.2)
    ndl_true = vmath("DOT_PRODUCT", nrm, light)
    # spinning parts: constant N.L, so the light-bound ink does not turn with the part
    ndl_b = math_("ADD", ndl_true, ba.outputs["Fac"])
    ndl = math_("ADD", math_("MULTIPLY", ndl_b, math_("SUBTRACT", 1.0, spin)), math_("MULTIPLY", spin, P["spin_ndl"]))
    shadow = mr(ndl, 0.15, -0.35, 0.0, 1.0)

    bev = node("ShaderNodeBevel", samples=P["bevel_samples"])
    L(math_("MULTIPLY", ink_s, P["bevel"]), bev.inputs["Radius"])
    vd = vmath("DOT_PRODUCT", bev.outputs[0], nrm)
    e = math_("ADD", mr(vd, P["edge_vd_lo"], P["edge_vd_hi"], 1.0, 0.0), math_("MULTIPLY", wob, 0.6))
    thr = math_("SUBTRACT", P["edge_thr"], math_("MULTIPLY", shadow, P["edge_shadow"]))
    edge = mr(math_("SUBTRACT", e, thr), 0.0, 0.025, 0.0, 1.0)

    ao_s = node("ShaderNodeAmbientOcclusion", samples=16, only_local=True)
    L(math_("MULTIPLY", ink_s, P["crease_dist"]), ao_s.inputs["Distance"])
    c_thr = math_("ADD", P["crease_thr"], math_("MULTIPLY", shadow, 0.06))
    crease = mr(math_("SUBTRACT", math_("ADD", ao_s.outputs["AO"], math_("MULTIPLY", wob, 0.3)), c_thr), -0.01, 0.0, 1.0, 0.0)

    ao_b = node("ShaderNodeAmbientOcclusion", samples=16, only_local=True)
    ao_b.name = "AO_Main"
    L(math_("MULTIPLY", ink_s, P["spot_dist"]), ao_b.inputs["Distance"])
    aob = math_("ADD", ao_b.outputs["AO"], math_("MULTIPLY", wob, 0.2))
    spot = mr(aob, P["spot_lo"], P["spot_hi"], 1.0, 0.0)

    d = vmath("NORMALIZE", vmath("SUBTRACT", light, vmath("SCALE", nrm, scale=ndl_true)))
    s_dir = vmath("NORMALIZE", vmath("CROSS_PRODUCT", nrm, d))
    phase = math_("ADD", math_("MULTIPLY", math_("DIVIDE", vmath("DOT_PRODUCT", pos, d), ink_s), P["hatch_freq"]),
                  math_("MULTIPLY", wob, 0.5))
    f = math_("FRACT", phase)
    dist = math_("ABSOLUTE", math_("SUBTRACT", f, 0.5))
    stroke_id = math_("FLOOR", phase)
    cv = node("ShaderNodeCombineXYZ")
    L(math_("MULTIPLY", vmath("DOT_PRODUCT", pos, s_dir), P["dash_scale"]), cv.inputs[0])
    L(math_("MULTIPLY", stroke_id, 1.731), cv.inputs[1])
    dash = noise(cv.outputs[0], 1.0, 0.0)
    band = math_("MULTIPLY", mr(ndl, 0.12, 0.0, 0.0, 1.0), mr(ndl, -0.5, -0.3, 0.0, 1.0))
    occl = mr(ao_b.outputs["AO"], 0.62, 0.45, 0.0, 1.0)
    deep = math_("MULTIPLY", mr(ndl, -0.3, -0.5, 0.0, 1.0), 0.25)
    amount = math_("MAXIMUM", math_("MAXIMUM", band, occl), deep)
    taper = mr(math_("SUBTRACT", dash, math_("SUBTRACT", 0.78, math_("MULTIPLY", amount, 0.33))), 0.0, 0.16, 0.0, 1.0)
    halfw = math_("MULTIPLY", taper, P["hatch_halfw"])
    hatch = mr(math_("SUBTRACT", dist, halfw), -0.015, 0.0, 1.0, 0.0)
    hatch = math_("MULTIPLY", hatch, mr(amount, 0.05, 0.12, 0.0, 1.0))

    lines = math_("MAXIMUM", edge, crease)
    lines = math_("MAXIMUM", lines, spot)
    lines = math_("MAXIMUM", lines, hatch)
    if P["panel_spacing"] > 0:  # broken plank / panel lines on wood only
        pband = math_("FRACT", math_("MULTIPLY", math_("ADD", sp.outputs["Z"], math_("MULTIPLY", wob, 0.4 * P["panel_spacing"] / 2.2)),
                                     1.0 / P["panel_spacing"]))
        panel = mr(pband, 0.0, 0.016, 1.0, 0.0)
        panel = math_("MULTIPLY", panel, mr(noise(pos, 0.45 * 2.2 / P["panel_spacing"]), 0.44, 0.47, 0.0, 1.0))
        panel = math_("MULTIPLY", panel, math_("MULTIPLY", cmp_kind(KIND["wood"]), math_("SUBTRACT", 1.0, spin)))
        lines = math_("MAXIMUM", lines, math_("MULTIPLY", panel, 0.9))
    # axle-view outline for radial round parts (helm spokes + handles): seen along the axle (pilot, game
    # camera) their silhouettes are where the normal turns away from the axle; ink |N.X| < ~0.66 where the
    # normal is not radial (rim faces, hub drums stay clean). Rotation about the axle does not change it.
    tco = node("ShaderNodeTexCoord")
    rv = vmath("NORMALIZE", vmath("MULTIPLY", tco.outputs["Object"], (0.0, 1.0, 1.0)))
    ndr = math_("ABSOLUTE", vmath("DOT_PRODUCT", nrm, rv))
    ndx = math_("ABSOLUTE", vmath("DOT_PRODUCT", nrm, (1.0, 0.0, 0.0)))
    tube = math_("MULTIPLY", mr(ndx, P["axial_hi"], P["axial_lo"], 0.0, 1.0), mr(ndr, 0.55, 0.45, 0.0, 1.0))
    lines = math_("MAXIMUM", lines, math_("MULTIPLY", tube, ax_a.outputs["Fac"]))
    lines = math_("MAXIMUM", lines, cmp_kind(KIND["bore"]))  # the bore is solid ink
    mask_node = node("ShaderNodeMath", operation="MINIMUM")
    L(lines, mask_node.inputs[0]); mask_node.inputs[1].default_value = 1.0
    mask_node.name = "ComicMask"
    em_mask = N("ShaderNodeEmission"); em_mask.name = "BakeMask"; em_mask.location = (1200, -400)
    L(mask_node.outputs[0], em_mask.inputs["Color"])

    # flat wash per part kind (no lighting)
    col = node("ShaderNodeRGB"); col.outputs[0].default_value = lin(TONE_HEX[0])
    cur = col.outputs[0]
    for kv in (1, 2, 3, 4):
        mx = node("ShaderNodeMixRGB", blend_type="MIX")
        L(cmp_kind(kv), mx.inputs["Fac"])
        L(cur, mx.inputs["Color1"])
        mx.inputs["Color2"].default_value = lin(TONE_HEX[kv])
        cur = mx.outputs[0]
    em_tone = N("ShaderNodeEmission"); em_tone.name = "BakeTone"; em_tone.location = (1200, -200)
    L(cur, em_tone.inputs["Color"])
    out = N("ShaderNodeOutputMaterial"); out.name = "Out"; out.location = (1500, 0)
    L(em_mask.outputs[0], out.inputs["Surface"])
    tex = N("ShaderNodeTexImage"); tex.name = "BakeTarget"; tex.location = (1000, -700)
    return m


def setup_cycles(cpu):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    dev = "CPU"
    if not cpu:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                if any(d.type == dev_type for d in prefs.devices):
                    break
            except TypeError:
                continue
        for d in prefs.devices:
            d.use = d.type != "CPU"
        dev = "GPU" if any(d.use for d in prefs.devices) else "CPU"
    sc.cycles.device = dev
    log("cycles device", dev)
    return dev


def ridge_widths(mask, thr=0.5, kmax=30):
    """Stroke width per ridge texel: 2 * (erosion steps to reach paper) - 1."""
    m = mask > thr
    depth = np.zeros(m.shape, np.int16)
    cur = m.copy()
    k = 0
    while cur.any() and k < kmax:
        k += 1
        depth[cur] = k
        cur = cur & np.roll(cur, 1, 0) & np.roll(cur, -1, 0) & np.roll(cur, 1, 1) & np.roll(cur, -1, 1)
    mx = depth.copy()
    for ax in (0, 1):
        for s in (1, -1):
            mx = np.maximum(mx, np.roll(depth, s, ax))
    ridge = (depth > 0) & (depth >= mx)
    return 2 * depth[ridge].astype(np.int32) - 1


def fill_ids(ids, steps=12):
    """Give the empty texels between islands the id of the nearest island (grows ids into the gaps)."""
    f = ids.copy()
    for _ in range(steps):
        empty = f < 0
        if not empty.any():
            break
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.roll(f, dy, 0), dx, 1)
            take = empty & (sh >= 0) & (f < 0)
            f[take] = sh[take]
    return f


def dilate(a, r, ids=None):
    """Grey max filter over a disc of radius r texels (thickens every stroke by ~r on each side).
    With ids (island id per texel, gaps filled), a texel only takes ink from its own island, so ink never
    jumps the gap from a neighbouring island."""
    if r <= 0:
        return a.copy()
    out = a.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if (dx or dy) and dx * dx + dy * dy <= r * r + r:
                sh = np.roll(np.roll(a, dy, 0), dx, 1)
                if ids is not None:
                    sh = np.where(np.roll(np.roll(ids, dy, 0), dx, 1) == ids, sh, 0.0)
                np.maximum(out, sh, out=out)
    return out


def stage_bake(cpu):
    open_props()
    sc = bpy.context.scene
    obs = mesh_objects()
    final = bpy.data.materials["M_AirshipProps"]
    bm_ = build_bake_material()
    nt = bm_.node_tree
    dev = setup_cycles(cpu)
    sc.render.bake.margin = P["margin_px"]
    sc.render.bake.margin_type = "EXTEND"
    sc.render.bake.use_clear = True
    for ob in obs:
        ob["comic_spin"] = 1.0 if ob.name in SPIN else 0.0
        ob["comic_light"] = LIGHT_OF(ob.name)
        ob["comic_bias"] = BIAS_OF(ob.name)
        ob["comic_axial"] = 1.0 if ob.name in AXIAL else 0.0
        ob["comic_scale"] = INK_SCALE_OF(ob.name)
        ob.data.materials[0] = bm_
        ob.hide_render = False
        ob.hide_set(False)
    for o in sc.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = obs[0]
    imgs = {}
    for nm in ("mask", "tone"):
        im = bpy.data.images.new(f"_bake_{nm}", RES, RES, alpha=False, float_buffer=True)
        im.colorspace_settings.name = "Non-Color" if nm == "mask" else "Linear Rec.709"
        imgs[nm] = im
    tex = nt.nodes["BakeTarget"]
    out = nt.nodes["Out"]
    times = {}
    try:
        for nm, emit, spp in (("mask", "BakeMask", P["samples"]), ("tone", "BakeTone", 16)):
            tex.image = imgs[nm]
            nt.nodes.active = tex
            nt.links.new(nt.nodes[emit].outputs[0], out.inputs["Surface"])
            sc.cycles.samples = spp
            if nm == "tone":  # texels outside the islands stay paper (mips, filtering)
                pp = np.tile(np.array(lin(PAPER_HEX), np.float32), RES * RES)
                imgs[nm].pixels.foreach_set(pp)
            t = time.time()
            bpy.ops.object.bake(type="EMIT", margin=P["margin_px"], margin_type="EXTEND", use_clear=(nm == "mask"))
            times[nm] = round(time.time() - t, 1)
            log(f"baked {nm} ({spp} spp, {dev}) in {times[nm]}s")
    finally:
        for ob in obs:
            ob.data.materials[0] = final
            for kk in ("comic_spin", "comic_light", "comic_bias", "comic_axial", "comic_scale"):
                if kk in ob:
                    del ob[kk]
    # post-process, as comic_lines.py
    px = np.empty(RES * RES * 4, np.float32)
    imgs["mask"].pixels.foreach_get(px)
    raw = px.reshape(RES, RES, 4)[:, :, 0].copy()
    T, oid, iid = all_uv_tris(obs)
    ids, _ = raster_islands(T, iid)
    # stroke growth per object: dilate_px x the object's ink scale (the small round-2 helm gets 2 texels, the rest 3)
    filled = fill_ids(ids)
    obj_of_isl = np.zeros(iid.max() + 1, np.int64); obj_of_isl[iid] = oid
    obj_tex = np.where(filled >= 0, obj_of_isl[np.maximum(filled, 0)], -1)
    rad = np.array([max(1, int(round(P["dilate_px"] * INK_SCALE_OF(ob.name)))) for ob in obs])
    m = dilate(raw, P["dilate_px"], filled)
    for r in sorted(set(rad.tolist()) - {P["dilate_px"]}):
        sel = np.isin(obj_tex, np.nonzero(rad == r)[0])
        m[sel] = dilate(raw, r, filled)[sel]
    for _ in range(P["smooth"]):
        for ax in (0, 1):
            m = (np.roll(m, 1, ax) + 2 * m + np.roll(m, -1, ax)) * 0.25
    t = np.clip((m - P["ink_lo"]) / (P["ink_hi"] - P["ink_lo"]), 0.0, 1.0)
    m = t * t * (3 - 2 * t)
    imgs["tone"].pixels.foreach_get(px)
    tone = lin_to_srgb(px.reshape(RES, RES, 4)[:, :, :3])
    ink = srgb(INK_HEX)
    col = tone + (ink - tone) * m[:, :, None]
    os.makedirs(TEXDIR, exist_ok=True)
    lines_img = write_png(TEXDIR + "T_AirshipProps_ComicLines.png", col, srgb_data=True)
    mask_img = write_png(TEXDIR + "T_AirshipProps_ComicMask.png", np.repeat(m[:, :, None], 3, 2), srgb_data=False)
    for im in imgs.values():
        bpy.data.images.remove(im)
    # ink statistics over the texels the atlas uses
    used = ids >= 0
    widths = ridge_widths(np.where(used, m, 0.0))
    atlas = json.load(open(CHECKS + "atlas.json"))
    ppm = np.mean([v["px_per_m"] for v in atlas["objects"].values()])
    per_obj = {}
    obj_of_isl = np.zeros(iid.max() + 1, np.int64); obj_of_isl[iid] = oid
    for k, ob in enumerate(obs):
        mm = used & (obj_of_isl[np.maximum(ids, 0)] == k)
        per_obj[ob.name] = round(float((m[mm] > 0.5).mean()), 3)
    hist = np.bincount(np.minimum(widths, 41))
    stats = dict(params=P, tones=TONE_HEX, device=dev, bake_seconds=times,
                 ink_fraction_used_texels=round(float((m[used] > 0.5).mean()), 4), ink_fraction_by_object=per_obj,
                 stroke_width_px_pct25_50_75=[int(np.percentile(widths, q)) for q in (25, 50, 75)] if widths.size else None,
                 stroke_width_cm_pct25_50_75=[round(float(np.percentile(widths, q)) / ppm * 100, 1) for q in (25, 50, 75)] if widths.size else None,
                 stroke_width_hist_px={int(i): int(hist[i]) for i in range(1, len(hist)) if hist[i]},
                 mean_px_per_m=round(float(ppm), 1),
                 raw_mask_mean=round(float(raw[used].mean()), 4))
    json.dump(stats, open(CHECKS + "bake.json", "w"), indent=1)
    log("BAKE", json.dumps({k: stats[k] for k in ("ink_fraction_used_texels", "ink_fraction_by_object",
                                                   "stroke_width_px_pct25_50_75", "stroke_width_cm_pct25_50_75")}))
    # final material: baked colour into Base Color, mask next to it unplugged
    for im in list(bpy.data.images):
        if im.name in ("T_AirshipProps_ComicLines", "T_AirshipProps_ComicMask") or im.name.startswith("T_AirshipProps_Comic") and im not in (lines_img, mask_img):
            bpy.data.images.remove(im)
    lines_img.filepath = "//textures/T_AirshipProps_ComicLines.png"
    mask_img.filepath = "//textures/T_AirshipProps_ComicMask.png"
    lines_img.name = "T_AirshipProps_ComicLines"
    mask_img.name = "T_AirshipProps_ComicMask"
    fn = final.node_tree
    bs = next(n for n in fn.nodes if n.type == "BSDF_PRINCIPLED")
    bs.inputs["Roughness"].default_value = 0.9
    tc = fn.nodes.get("ComicLines") or fn.nodes.new("ShaderNodeTexImage")
    tc.name = "ComicLines"; tc.label = "T_AirshipProps_ComicLines"; tc.image = lines_img; tc.location = (-600, 300)
    tm = fn.nodes.get("ComicMask") or fn.nodes.new("ShaderNodeTexImage")
    tm.name = "ComicMask"; tm.label = "T_AirshipProps_ComicMask (white = ink, unplugged)"; tm.image = mask_img
    tm.location = (-600, 0)
    fn.links.new(tc.outputs["Color"], bs.inputs["Base Color"])
    fn.nodes.active = tc
    bpy.data.materials.remove(bm_)
    sc.render.engine = "BLENDER_WORKBENCH"
    # geometry and transforms are still the modellers' (md5 of vertex positions from the assemble step)
    ref = json.load(open(CHECKS + "assemble.json"))
    for ob in obs:
        co = np.zeros(len(ob.data.vertices) * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        assert hashlib.md5(co.tobytes()).hexdigest() == ref[ob.name]["co_md5"], ob.name
        assert [round(x, 4) for x in ob.location] == ref[ob.name]["loc"], ob.name
        assert tuple(ob.rotation_euler) == (0, 0, 0) and tuple(ob.scale) == (1, 1, 1), ob.name
        assert [u.name for u in ob.data.uv_layers] == ["UVMap"] and [m.name for m in ob.data.materials] == ["M_AirshipProps"]
        assert not any(k.startswith("comic_") for k in ob.keys()), ob.name
    log("geometry, transforms, UV channel and material slot verified for", len(obs), "meshes")
    save_props()


# ================================================================ 4 render (never saves)
def ensure_ship_copy():
    if not os.path.exists(SHIP_COPY):
        before = md5(TALAL_SHIP)
        shutil.copy2(TALAL_SHIP, SHIP_COPY)
        assert md5(SHIP_COPY) == before
    return SHIP_COPY


def stage_render(tag, cpu):
    from bpy_extras.object_utils import world_to_camera_view
    open_props()
    sc = bpy.context.scene
    for im in bpy.data.images:
        if im.filepath:
            im.reload()
    helm = bpy.data.collections["Helm"]
    cannon = bpy.data.collections["Cannon"]
    turret = bpy.data.collections["Turret"]
    HW = bpy.data.objects["Helm_Wheel"].location.copy()      # wheel centre on the pedestal (v3: (-0.35, 0, 1.00))
    # world, camera, look as render_preview.py PREVIEW_FLAT (renders/comic5_*.png)
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.color = (0.62, 0.66, 0.74)
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"; sh.color_type = "TEXTURE"
    sh.show_object_outline = False; sh.show_cavity = False; sh.show_shadows = False
    sc.display.render_aa = "16"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    cd = bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.new("PreviewCam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.clip_start, cd.clip_end = 0.02, 2000

    def look(pos, tgt, lens=None, fov_h=None):
        cam.location = V(pos)
        cam.rotation_euler = (V(tgt) - V(pos)).to_track_quat("-Z", "Y").to_euler()
        cd.sensor_fit = "HORIZONTAL"
        if fov_h:
            cd.angle = math.radians(fov_h)
        else:
            cd.lens = lens

    written = []

    def render(name, res=(1600, 1000), crop=None):
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.resolution_percentage = 100
        path = RENDERS + f"baked{tag}_{name}.png"
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        written.append(path)
        log("wrote", path, f"{time.time() - T0:.0f}s")
        if crop:  # (world point, half size px): x4 nearest crop to see single pixels
            pt, hs = crop
            p = world_to_camera_view(sc, cam, V(pt))
            cx, cy = int(p.x * res[0]), int(p.y * res[1])
            img = bpy.data.images.load(path)
            ww, hh = img.size
            a = np.empty(ww * hh * 4, np.float32); img.pixels.foreach_get(a)
            a = a.reshape(hh, ww, 4)
            y0, y1 = max(0, cy - hs), min(hh, cy + hs); x0, x1 = max(0, cx - hs), min(ww, cx + hs)
            c = np.repeat(np.repeat(a[y0:y1, x0:x1], 4, 0), 4, 1)
            out = bpy.data.images.new("crop_" + name, c.shape[1], c.shape[0])
            out.pixels.foreach_set(c.ravel())
            out.filepath_raw = path.replace(".png", "_crop.png"); out.file_format = "PNG"; out.save()
            written.append(out.filepath_raw)
            bpy.data.images.remove(img)

    # --- studio: helm and cannon side by side (collection instances, sources hidden)
    def instance(coll, loc, rot_z=0.0, rot_y=0.0, name=None):
        e = bpy.data.objects.new(name or ("I_" + coll.name), None)
        e.instance_type = "COLLECTION"
        e.instance_collection = coll
        e.location = V(loc)
        e.rotation_euler = (0.0, rot_y, rot_z)
        sc.collection.objects.link(e)
        return e

    lc = bpy.context.view_layer.layer_collection
    for c in (helm, cannon, turret):
        lc.children[c.name].exclude = True
    studio = [instance(helm, (0, 1.25, 0)), instance(cannon, (0, -1.75, 0)), instance(turret, (-0.6, 3.4, 0))]
    floor_me = bpy.data.meshes.new("Floor")
    bmf = bmesh.new(); bmesh.ops.create_grid(bmf, x_segments=1, y_segments=1, size=6.0); bmf.to_mesh(floor_me); bmf.free()
    floor = bpy.data.objects.new("Floor", floor_me)
    fm = bpy.data.materials.new("FloorPaper"); fm.diffuse_color = (0.78, 0.78, 0.78, 1)
    floor_me.materials.append(fm)
    sc.collection.objects.link(floor)
    floor.location.z = -0.051
    look((6.4, -5.6, 3.3), (0.1, -0.3, 0.95), lens=42)
    render("side_by_side")
    look((-6.6, 4.4, 3.0), (-0.1, -0.2, 0.95), lens=42)
    render("side_by_side_back")
    look((2.7, -4.9, 1.25), (0.5, -1.75, 0.65), lens=50)
    render("close_cannon")
    look((-1.9, -3.4, 1.3), (-0.4, -1.75, 0.6), lens=50)
    render("close_cannon_breech")
    hw = HW + V((0, 1.25, 0))
    look(hw + V((-2.4, 1.3, 0.5)), hw + V((0, 0, -0.08)), lens=50)
    render("close_helm")
    look((-1.6, 0.4, 0.55), (-0.05, 1.25, 0.45), lens=40)
    render("close_pedestal")
    look(hw + V((1.0, -3.0, 0.1)), hw + V((0.25, 0, -0.15)), lens=45)
    render("helm_side")
    look((2.6, 5.2, 2.2), (-0.3, 3.4, 1.1), lens=42)
    render("close_turret")
    look((-3.4, 1.9, 2.2), (-0.6, 3.4, 1.2), lens=42)
    render("close_turret_back")
    look((4.6, -1.0, 1.4), (0.8, -1.75, 0.7), lens=50)
    render("cannon_front")
    # lit view (how the Principled material shows it in a lit engine)
    sc.render.engine = "CYCLES"
    setup_cycles(cpu)
    sc.cycles.samples = 64
    sc.cycles.use_denoising = False
    sun_d = bpy.data.lights.new("Sun", "SUN"); sun_d.energy = 2.2; sun_d.angle = math.radians(3)
    sun = bpy.data.objects.new("Sun", sun_d); sc.collection.objects.link(sun)
    sun.rotation_euler = LIGHT.to_track_quat("Z", "Y").to_euler()
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1); bg.inputs["Strength"].default_value = 0.6
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    look((6.4, -5.6, 3.3), (0.1, -0.3, 0.95), lens=42)
    render("lit_34")
    sun.hide_render = True
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    for o in studio + [floor]:
        bpy.data.objects.remove(o)

    # --- on the ship (copy of StylizedAirship.blend; never saved)
    with bpy.data.libraries.load(ensure_ship_copy(), link=False) as (src, dst):
        dst.objects = ["SM_Airship"]
    ship = dst.objects[0]
    sc.collection.objects.link(ship)
    for im in bpy.data.images:
        if im.name.startswith("T_Airship_Comic") and not im.has_data:
            im.filepath = "/mnt/new_partition/BlenderProjects/StylizedAirship/textures/" + im.name + ".png"
            im.reload()
    log("ship images", [(im.name, im.filepath, im.has_data) for im in bpy.data.images if im.name.startswith("T_Airship")])
    HELM_AT = V((-6.5, 0.0, 2.605))
    instance(helm, HELM_AT, rot_y=0.034)
    # cannons at the rig's stations (checks/rig/placement.json when it exists, else RIG_CONTRACT 4 approximations)
    spots = {"L1": (-0.46, 5.96, 2.56, 1), "L2": (-11.3, 4.15, 2.83, 1), "R1": (-0.46, -5.96, 2.56, -1), "R2": (-11.3, -4.15, 2.83, -1)}
    pj = RIG + "checks/rig/placement.json"
    if os.path.exists(pj):
        pc = json.load(open(pj))["cannons"]
        spots = {k: tuple(pc[k]["origin"]) + (1 if k[0] == "L" else -1,) for k in spots}
    for k, (x, y, z, s) in spots.items():
        instance(cannon, (x, y, z), rot_z=s * math.pi / 2, name="I_Cannon_" + k)
    # front turrets on the narrow forward deck (z 6.55), rig_common.TURRET_MOUNTS
    for k, y in (("L", 2.45), ("R", -2.45)):
        instance(turret, (21.0, y, 6.55), name="I_Turret_" + k)
    AX = HELM_AT + HW
    L1 = V(spots["L1"][:3]) + V((0, 0.5, 0.6))
    TL = V((21.0, 2.45, 6.55 + 1.2))

    # game camera (65 m spring arm, 12 deg down, FOV 85, 1920x1080): view direction, 30 m from the wheel
    p = math.radians(12)
    pos65 = V((0, 0, 8.5)) - V((math.cos(p), 0, -math.sin(p))) * 65
    dgame = (AX - pos65).normalized()
    look(AX - dgame * 30, AX + V((0, 0, -0.4)), fov_h=85)
    render("far30", (1920, 1080), crop=(AX + V((0, 0, -0.5)), 110))
    # 30 m from the port side, slightly from above: cannons L1/L2 + helm
    tgt = V((-7.5, 3.0, 3.4))
    look(tgt + V((6.0, 28.5, 8.5)).normalized() * 30, tgt, fov_h=85)
    render("far30_port", (1920, 1080), crop=(L1, 110))
    # 30 m off the port bow, slightly from above: the two turrets on the forward deck
    look(TL + V((12.0, 25.0, 9.0)).normalized() * 30, TL + V((0, -2.45, -0.5)), fov_h=85)
    render("far30_turrets", (1920, 1080), crop=(TL, 110))
    # 10 m on deck behind the helm: hull ink and prop ink side by side
    look(AX + V((-8.0, -5.0, 2.5)), AX + V((1.5, 1.0, -1.0)), fov_h=70)
    render("deck10", (1920, 1080))
    # game camera itself (65 m) with crop
    look(pos65, V((0, 0, 8.5)), fov_h=85)
    render("game65", (1920, 1080), crop=(AX + V((0, 0, -0.5)), 60))
    json.dump(written, open(CHECKS + f"renders{tag}.json", "w"), indent=1)


# ================================================================ main
def main():
    a = parse_args()
    log("stages", a["stages"], "params", P)
    for st in a["stages"]:
        t = time.time()
        if st == "assemble":
            stage_assemble()
        elif st == "atlas":
            stage_atlas()
        elif st == "bake":
            stage_bake(a["cpu"])
        elif st == "render":
            stage_render(a["tag"], a["cpu"])
        else:
            raise SystemExit(f"unknown stage {st}")
        log(f"stage {st} done in {time.time() - t:.0f}s")


main()
