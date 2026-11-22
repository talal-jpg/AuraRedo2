"""Deck survey of SM_Airship and placement proposals for the helm (pirate wheel) and 4 broadside cannons.
Read-only (never saves the .blend).

Usage:
  blender -b --factory-startup <copy.blend> --python deck_placement.py -- \
      --islands sm_airship_islands.json --vparts sm_airship_vertex_parts.json --out deck_placement.json [--render <dir>]

Method: 0.2 m grid of rays straight down onto SM_Airship. A cell is open deck when the first hit is the hull
skin (island 392) with normal.z > 0.9. Everything that is not the hull skin is an obstacle (rails, deck props,
pipes, bands, gantry legs, fin, fans). Clearance of a point = smallest 3D distance to an obstacle face, sampled
at 0.15/0.6/1.2/1.9/2.6 m above the deck, also capped by the distance to the deck edge.
Blender world metres: +X bow, +Y port, +Z up.
"""
import bpy, json, math, os, sys
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None):
    return argv[argv.index(n) + 1] if n in argv else d
ISL = json.load(open(arg("--islands", "sm_airship_islands.json")))
VP = json.load(open(arg("--vparts", "sm_airship_vertex_parts.json")))
OUT = arg("--out", "deck_placement.json"); RENDER = arg("--render")

me = bpy.data.objects["SM_Airship"].data
nf = len(me.polygons)
co = np.array([v.co[:] for v in me.vertices]); polys = [tuple(p.vertices) for p in me.polygons]
visl = np.array(VP["vertex_island"]); fisl = np.array([visl[p[0]] for p in polys])
IS = {r["id"]: r for r in ISL["islands"]}
SHELL = max((r for r in ISL["islands"] if r["src"] == "Hull"), key=lambda r: r["nv"])["id"]
allb = BVHTree.FromPolygons(co.tolist(), polys)
obs_f = [i for i in range(nf) if fisl[i] != SHELL]
obs = BVHTree.FromPolygons(co.tolist(), [polys[i] for i in obs_f])
obs_nr_f = [i for i in obs_f if IS[int(fisl[i])]["src"] != "DeckRails"]          # obstacles except the rails
obs_nr = BVHTree.FromPolygons(co.tolist(), [polys[i] for i in obs_nr_f])
R = {"method": __doc__.split("Method:")[1].strip()}

# ---------------------------------------------------------------- grid survey
STEP = 0.2
xs = np.round(np.arange(-16.4, 21.6, STEP), 3); ys = np.round(np.arange(-9.0, 9.01, STEP), 3)
deckz = np.full((len(xs), len(ys)), np.nan); nz = np.zeros_like(deckz); kind = np.zeros(deckz.shape, int)  # 0 none 1 deck 2 obstacle 3 skin-not-flat
for i, x in enumerate(xs):
    for j, y in enumerate(ys):
        h = allb.ray_cast(V((x, y, 30)), V((0, 0, -1)), 60)
        if h[0] is None: continue
        isl = int(fisl[h[2]])
        deckz[i, j] = h[0].z; nz[i, j] = h[1].z
        kind[i, j] = 1 if (isl == SHELL and h[1].z > 0.9) else 3 if isl == SHELL else 2
deck = kind == 1
# distance to the deck edge (nearest non-deck cell that is not an obstacle sitting on the deck)
edge_cells = np.argwhere(~deck & (kind != 2) | (kind == 0))
ec = np.c_[xs[edge_cells[:, 0]], ys[edge_cells[:, 1]]]
def edge_dist(x, y):
    return float(np.min(np.hypot(ec[:, 0] - x, ec[:, 1] - y)))
def clearance(x, y, z0, heights=(0.15, 0.6, 1.2, 1.9, 2.6), cap=4.0, tree=None):
    d = cap; tree = tree or obs
    for hh in heights:
        r = tree.find_nearest(V((x, y, z0 + hh)), cap)
        if r[0] is not None: d = min(d, r[3])
    return d
def deck_at(x, y):
    h = allb.ray_cast(V((x, y, 30)), V((0, 0, -1)), 60)
    if h[0] is None: return None
    return dict(z=round(h[0].z, 3), normal=[round(v, 3) for v in h[1]], island=int(fisl[h[2]]),
                src=IS[int(fisl[h[2]])]["src"], deck=bool(int(fisl[h[2]]) == SHELL and h[1].z > 0.9))

# outline + centreline height
outline = []
for i, x in enumerate(xs):
    js = np.where(deck[i])[0]
    if len(js) == 0: continue
    if abs(x - round(x)) > 1e-6: continue                                         # report every 1 m
    jc = np.argmin(np.abs(ys))
    outline.append(dict(x=float(x), y_min=float(ys[js.min()]), y_max=float(ys[js.max()]),
                        z_centre=None if np.isnan(deckz[i, jc]) or kind[i, jc] != 1 else round(float(deckz[i, jc]), 3),
                        z_edge=round(float(deckz[i, js.max()]), 3)))
R["deck_outline_every_1m"] = outline

# rails: DeckRails posts per side (vertical islands about 1.1 m tall)
rails = [r for r in ISL["islands"] if r["src"] == "DeckRails"]
posts = sorted([r for r in rails if r["bbmax"][2] - r["bbmin"][2] > 0.9], key=lambda r: r["c"][0])
R["rails"] = dict(height_m=1.1, mid_bar_m=0.55, post_section_m=0.09, bar_section_m=0.07, posts_per_side=len(posts) // 2,
                  x_range=[min(r["c"][0] for r in posts), max(r["c"][0] for r in posts)])
def side_posts(s):
    return sorted([r for r in posts if np.sign(r["c"][1]) == s], key=lambda r: r["c"][0])
def rail_at(x, s):
    P = side_posts(s)
    px = np.array([r["c"][0] for r in P])
    k = int(np.clip(np.searchsorted(px, x), 1, len(P) - 1))
    a, b = P[k - 1], P[k]
    t = (x - a["c"][0]) / (b["c"][0] - a["c"][0])
    y = a["c"][1] + t * (b["c"][1] - a["c"][1]); zb = a["bbmin"][2] + t * (b["bbmin"][2] - a["bbmin"][2])
    return dict(y=round(y, 3), base_z=round(zb, 3), top_bar_z=round(zb + 1.1, 3), mid_bar_z=round(zb + 0.55, 3),
                post_before=[round(a["c"][0], 3), round(a["c"][1], 3)], post_after=[round(b["c"][0], 3), round(b["c"][1], 3)],
                post_gap=round(math.hypot(b["c"][0] - a["c"][0], b["c"][1] - a["c"][1]), 3))

# deck props for reference
R["deck_props"] = [dict(id=r["id"], c=r["c"], bbmin=r["bbmin"], bbmax=r["bbmax"]) for r in ISL["islands"]
                   if r["src"] == "DeckProps" and r["nv"] >= 24]

# ---------------------------------------------------------------- helm
helm_rows = []
for x in np.arange(-14.0, 8.01, 0.25):
    d = deck_at(x, 0.0)
    if not d or not d["deck"]: continue
    c_wheel = clearance(x, 0.0, d["z"])
    hx = x - 0.9; dh = deck_at(hx, 0.0)
    c_helm = clearance(hx, 0.0, dh["z"]) if dh and dh["deck"] else 0.0
    ed = edge_dist(x, 0.0)
    helm_rows.append(dict(x=round(float(x), 2), deck_z=d["z"], clear_wheel=round(min(c_wheel, ed), 2), clear_helmsman=round(c_helm, 2)))
R["helm_profile_centreline"] = helm_rows
WHEEL_R = 1.2
good = [r for r in helm_rows if r["clear_wheel"] >= WHEEL_R + 0.3 and r["clear_helmsman"] >= 0.7 and -11.0 <= r["x"] <= -1.0]
best = max(good, key=lambda r: (min(r["clear_wheel"], 3.0) - 0.15 * abs(r["x"] + 6.0))) if good else None
if best:
    d = deck_at(best["x"], 0.0)
    R["helm"] = dict(pedestal_base=[best["x"], 0.0, d["z"]], deck_normal=d["normal"], free_radius_m=best["clear_wheel"],
                     helmsman_stand=[round(best["x"] - 0.9, 2), 0.0, deck_at(best["x"] - 0.9, 0.0)["z"]],
                     wheel_axle_dir="+X (wheel plane = YZ), helmsman aft of the wheel facing +X (bow)",
                     suggested_wheel_radius_m=WHEEL_R, suggested_axle_height_above_deck_m=round(WHEEL_R + 0.35, 2),
                     candidates=[r for r in good][::4])
print("HELM", R.get("helm"))

# ---------------------------------------------------------------- cannons
CAR_L, CAR_W, BARREL, BARREL_R = 1.6, 1.2, 2.6, 0.22
def cannon_eval(x, s):
    rl = rail_at(x, s)
    yr = rl["y"]
    yc = yr - s * (0.3 + CAR_L / 2)                        # carriage centre: front edge 0.3 m inside the rail line
    d = deck_at(x, yc)
    if not d or not d["deck"]: return None
    # footprint all on deck and clear up to 1.2 m
    worst, ok = 4.0, True
    for dx in np.linspace(-CAR_W / 2, CAR_W / 2, 5):
        for dy in np.linspace(-CAR_L / 2, CAR_L / 2, 5):
            dd = deck_at(x + dx, yc + dy)
            if not dd or not dd["deck"]: ok = False
            else: worst = min(worst, clearance(x + dx, yc + dy, dd["z"], heights=(0.1, 0.5, 1.0), tree=obs_nr))
    if not ok: return None
    # barrel through the rail: axis between mid and top bar, muzzle 0.9 m past the rail
    zthr = rl["base_z"] + 0.83
    zover = rl["top_bar_z"] + 0.035 + BARREL_R + 0.05
    def barrel_clear(zax):
        m = 4.0
        for t in np.linspace(0, 1, 12):
            y = (yc + s * 0.2) + t * ((yr + s * 0.9) - (yc + s * 0.2))
            r = obs.find_nearest(V((x, y, zax)), 4.0)
            if r[0] is not None and IS[int(fisl[obs_f[r[2]]])]["src"] != "DeckRails": m = min(m, r[3])
            elif r[0] is not None: m = min(m, r[3] + 0.0)
        return m
    return dict(x=round(float(x), 2), side="port(+Y)" if s > 0 else "starboard(-Y)", base=[round(float(x), 3), round(yc, 3), d["z"]],
                facing=[0, s, 0], deck_normal=d["normal"], deck_z=d["z"], rail=rl,
                footprint_clearance_m=round(worst, 2), footprint_note="clearance to anything but the deck rail (rail line is 0.3 m ahead)", barrel_axis_z_through_rail=round(zthr, 3),
                barrel_through_rail_clearance_m=round(barrel_clear(zthr), 3),
                barrel_axis_z_over_rail=round(zover, 3), barrel_over_rail_clearance_m=round(barrel_clear(zover), 3),
                muzzle_y=round(yr + s * 0.9, 3))
cands = {}
for s in (1, -1):
    for x in np.arange(-13.0, 7.01, 0.25):
        c = cannon_eval(float(x), s)
        if c and c["footprint_clearance_m"] >= 0.3: cands.setdefault(s, []).append(c)
        if c: R.setdefault("cannon_scan", []).append({k: c[k] for k in ("x", "side", "footprint_clearance_m", "deck_z")} | {"rail_y": c["rail"]["y"], "post_gap": c["rail"]["post_gap"], "barrel_thru_clear": c["barrel_through_rail_clearance_m"]})
R["cannon_candidates_count"] = {k: len(v) for k, v in cands.items()}
# pick two x stations usable on both sides, >= 4 m apart, mid/aft deck, at a rail post gap >= 0.85 (barrel through)
def score(cp, cs):
    return min(cp["footprint_clearance_m"], cs["footprint_clearance_m"], 1.0) + 0.5 * min(cp["rail"]["post_gap"], cs["rail"]["post_gap"]) \
        - 0.05 * abs(cp["x"] + 6.0)
pairs = []
port = {c["x"]: c for c in cands.get(1, [])}; stbd = {c["x"]: c for c in cands.get(-1, [])}
for x in sorted(set(port) & set(stbd)):
    pairs.append((score(port[x], stbd[x]), x))
pairs.sort(reverse=True)
# composition rule: one pair ~2.5 m ahead of the helm and one ~2.5 m behind it (they frame the helmsman in a
# chase camera), each snapped to the middle of a rail post gap so the barrel passes between posts.
hx = R["helm"]["pedestal_base"][0] if R.get("helm") else -5.5
gaps = sorted(set(round((a["c"][0] + b["c"][0]) / 2, 2) for a, b in zip(side_posts(1)[:-1], side_posts(1)[1:])))
chosen = []
for target in (hx + 2.5, hx - 2.5):
    ok = [g for g in gaps if cannon_eval(g, 1) and cannon_eval(g, -1) and cannon_eval(g, 1)["footprint_clearance_m"] >= 0.3
          and cannon_eval(g, -1)["footprint_clearance_m"] >= 0.3]
    chosen.append(min(ok, key=lambda g: abs(g - target)))
for x in chosen:
    for s_ in (1, -1):
        (port if s_ > 0 else stbd)[x] = cannon_eval(x, s_)
R["cannons"] = []
for x in sorted(chosen, reverse=True):
    for s, tbl in ((1, port), (-1, stbd)):
        c = tbl[x]
        c2 = c
        c2["name"] = "Cannon_%s%s" % ("Fwd" if x == max(chosen) else "Aft", "L" if s > 0 else "R")
        R["cannons"].append(c2)
        print("CANNON", c2["name"], {k: c2[k] for k in ("base", "deck_z", "footprint_clearance_m", "barrel_axis_z_through_rail", "barrel_through_rail_clearance_m", "barrel_axis_z_over_rail")}, c2["rail"])
R["cannon_station_scores_top"] = [(round(a, 3), b) for a, b in pairs[:12]]

json.dump(R, open(OUT, "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
print("DECK written", OUT)

# ---------------------------------------------------------------- check renders with placeholders
if RENDER:
    os.makedirs(RENDER, exist_ok=True)
    scene = bpy.context.scene
    for o in list(scene.objects): o.hide_render = True
    col = bpy.data.collections.new("DeckCheck"); scene.collection.children.link(col)
    ship = bpy.data.objects["SM_Airship"].copy(); ship.hide_render = False; col.objects.link(ship); ship.color = (0.7, 0.7, 0.72, 1)
    def add(name, verts, faces, colr):
        m = bpy.data.meshes.new(name); m.from_pydata(verts, [], faces)
        o = bpy.data.objects.new(name, m); o.color = colr; col.objects.link(o); return o
    def box(name, c, size, colr, rot=None):
        import bmesh
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts: v.co = V((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
        if rot: bmesh.ops.rotate(bm, verts=bm.verts, matrix=rot)
        for v in bm.verts: v.co += V(c)
        m = bpy.data.meshes.new(name); bm.to_mesh(m); bm.free()
        o = bpy.data.objects.new(name, m); o.color = colr; col.objects.link(o); return o
    def cyl(name, a, b, r, colr):
        import bmesh
        a, b = V(a), V(b); bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=r, radius2=r, depth=(b - a).length,
                              matrix=Matrix.Translation((a + b) / 2) @ V((0, 0, 1)).rotation_difference(b - a).to_matrix().to_4x4())
        m = bpy.data.meshes.new(name); bm.to_mesh(m); bm.free()
        o = bpy.data.objects.new(name, m); o.color = colr; col.objects.link(o); return o
    if R.get("helm"):
        b = R["helm"]["pedestal_base"]; ah = R["helm"]["suggested_axle_height_above_deck_m"]
        box("Pedestal", (b[0], 0, b[2] + ah / 2), (0.5, 0.5, ah), (0.9, 0.6, 0.1, 1))
        cyl("Wheel", (b[0] + 0.25, 0, b[2] + ah), (b[0] + 0.4, 0, b[2] + ah), WHEEL_R, (1.0, 0.8, 0.1, 1))
        hs = R["helm"]["helmsman_stand"]; cyl("Helmsman", (hs[0], 0, hs[2]), (hs[0], 0, hs[2] + 1.8), 0.3, (0.2, 0.5, 1.0, 1))
    for c in R["cannons"]:
        s = c["facing"][1]; x, yc, z = c["base"]
        box(c["name"] + "_carriage", (x, yc, z + 0.35), (CAR_W, CAR_L, 0.7), (0.85, 0.15, 0.1, 1))
        za = c["barrel_axis_z_through_rail"]
        cyl(c["name"] + "_barrel", (x, yc - s * 0.6, za), (x, c["muzzle_y"], za), BARREL_R, (0.15, 0.15, 0.15, 1))
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading; sh.light, sh.color_type = "STUDIO", "OBJECT"; sh.show_object_outline = True
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    cam_d = bpy.data.cameras.new("DeckCam"); cam = bpy.data.objects.new("DeckCam", cam_d); scene.collection.objects.link(cam); scene.camera = cam
    for vname, (loc, tgt, ortho, lens) in {"deck_top": ((-3, 0, 60), (-3, 0, 0), 30, None),
                                          "deck_chase": ((-40, 10, 18), (-4, 0, 3), None, 35),
                                          "deck_side": ((-4, 40, 6), (-4, 0, 3), 30, None)}.items():
        cam.location = V(loc)
        up = "Y" if vname != "deck_top" else "X"
        cam.rotation_euler = (V(tgt) - V(loc)).to_track_quat("-Z", up).to_euler()
        if vname == "deck_top":
            cam.rotation_euler = (0, 0, 0)                            # looking down: +X (bow) right, +Y (port) up
        if ortho: cam_d.type, cam_d.ortho_scale = "ORTHO", ortho
        else: cam_d.type, cam_d.lens = "PERSP", lens
        scene.render.filepath = os.path.join(RENDER, vname + ".png")
        bpy.ops.render.render(write_still=True)
    print("DECK renders ->", RENDER)
