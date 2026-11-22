"""Classify every loose island of SM_Airship into a rig part (read-only on the .blend).

Usage (headless, never saves the file; open a COPY of Talal's .blend):
  blender -b --factory-startup <copy.blend> --python classify_islands.py -- \
      --out <islands.json> [--vertex-out <vertex_parts.json>] [--render <dir>]

How it works
  1. Loose islands of SM_Airship = connected components over mesh edges.
  2. Source part: every SM vertex is matched to the nearest surface of each evaluated object in
     collection Airship_Parts (BVH, world space). An island goes to the part with the smallest mean
     distance. finalize.py merged the parts in sorted-name order with no merge-by-distance, so the
     source labels must be monotonic in vertex index: that is checked ("order_violations").
  3. Sub-split of the moving parts by fixed geometric rules (see RULES below): thruster pod vs nozzle,
     turbine housing (yaw) vs rotor (spin) vs fixed mount, rudder, gantry searchlights, hanging strips,
     sagging chains, winch drums. Everything else is "Hull" (rigid root).
  4. Optional --render: Workbench flat colour check images (one colour per part), 5 views.

Coordinates: Blender world, metres, +X bow, +Y port (left), +Z up. Unreal: X fwd, Y = -Blender Y, cm.
"""
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default
OUT = arg("--out", "sm_airship_islands.json")
VOUT = arg("--vertex-out")
RENDER = arg("--render")

SM_NAME, PARTS_COLL = "SM_Airship", "Airship_Parts"
EDIT_TOL = 0.005          # island max distance above this = geometry edited after the merge
A_LOCAL = (Matrix.Rotation(math.radians(8), 3, "Y") @ V((0, 0, -1))).normalized()  # thrusters_ref.py A
T0_LOCAL = V((0, 0, -0.4))                                                          # thrusters_ref.py T0
NOZZLE_H = 2.38           # thrusters_ref: drum ends at S(2.4), nozzle from S(2.4) to petal tips S(4.35)
POD_TAG = {"Thruster_Front_L": "FL", "Thruster_Front_R": "FR", "Thruster_Rear_L": "RL", "Thruster_Rear_R": "RR"}

sm = bpy.data.objects[SM_NAME]
me = sm.data
assert sm.matrix_world == Matrix.Identity(4), "SM_Airship must have an identity transform"
nv, nf = len(me.vertices), len(me.polygons)
co = np.zeros(nv * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
ed = np.zeros(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
lt = np.zeros(nf, dtype=np.int64); me.polygons.foreach_get("loop_total", lt)
ls = np.zeros(nf, dtype=np.int64); me.polygons.foreach_get("loop_start", ls)
lv = np.zeros(len(me.loops), dtype=np.int64); me.loops.foreach_get("vertex_index", lv)
face_v0 = lv[ls]

# ------------------------------------------------------------------ 1. islands
par = np.arange(nv)
def find(a):
    r = a
    while par[r] != r:
        r = par[r]
    while par[a] != r:
        par[a], a = r, par[a]
    return r
for a, b in ed:
    ra, rb = find(a), find(b)
    if ra != rb:
        par[max(ra, rb)] = min(ra, rb)
roots = np.array([find(i) for i in range(nv)])
uniq, v_isl = np.unique(roots, return_inverse=True)   # islands numbered by their lowest vertex index
n_isl = len(uniq)
f_isl = v_isl[face_v0]
isl_verts = [[] for _ in range(n_isl)]
for i, k in enumerate(v_isl):
    isl_verts[k].append(i)
isl_verts = [np.array(v) for v in isl_verts]
isl_nf = np.bincount(f_isl, minlength=n_isl)
isl_tris = np.bincount(f_isl, weights=lt - 2, minlength=n_isl).astype(int)

# ------------------------------------------------------------------ 2. source part
dg = bpy.context.evaluated_depsgraph_get()
parts = sorted([o for o in bpy.data.collections[PARTS_COLL].objects if o.type == "MESH"], key=lambda o: o.name)
names = [o.name for o in parts]
D = np.zeros((nv, len(parts)))
for j, o in enumerate(parts):
    ev = o.evaluated_get(dg); m = ev.to_mesh()
    t = BVHTree.FromPolygons([o.matrix_world @ v.co for v in m.vertices], [tuple(p.vertices) for p in m.polygons])
    ev.to_mesh_clear()
    for i in range(nv):
        r = t.find_nearest(V(co[i]), 3.0)
        D[i, j] = r[3] if r[0] is not None else 3.0
src = np.zeros(n_isl, dtype=int); dmean = np.zeros(n_isl); dmax = np.zeros(n_isl); margin = np.zeros(n_isl)
for k in range(n_isl):
    m = D[isl_verts[k]].mean(0)
    s = np.argsort(m)
    src[k] = s[0]; dmean[k] = m[s[0]]; dmax[k] = D[isl_verts[k], s[0]].max(); margin[k] = m[s[1]] - m[s[0]]
seq = src[np.argsort([v.min() for v in isl_verts])]
order_violations = int(np.sum(seq[1:] < seq[:-1]))

# ------------------------------------------------------------------ 3. sub-split
part = ["Hull"] * n_isl
piece = [""] * n_isl
group = [None] * n_isl     # e.g. segment index of a hanging strip, petal index
frames = {}

def stats(k):
    p = co[isl_verts[k]]
    return p, p.mean(0), p.min(0), p.max(0)

# thruster pods ---------------------------------------------------------
for oname, tag in POD_TAG.items():
    ob = bpy.data.objects[oname]
    R = ob.matrix_world.to_3x3().normalized()
    O = ob.matrix_world.translation.copy()
    A = (R @ A_LOCAL).normalized()
    T0 = O + R @ T0_LOCAL
    frames["Pod_" + tag] = dict(object=oname, origin=list(O), axis_nozzle=list(A), T0=list(T0),
                                nozzle_pivot=list(T0 + A * 2.4))
    a, t0 = np.array(A), np.array(T0)
    petals = []
    for k in np.where(src == names.index(oname))[0]:
        p, c, mn, mx = stats(k)
        d = p - t0; h = d @ a; r = np.linalg.norm(d - np.outer(h, a), axis=1)
        nvk, ext = len(p), mx - mn
        if h.min() >= NOZZLE_H:
            part[k] = "Nozzle_" + tag
            if nvk == 8:
                piece[k] = "petal"; petals.append(k)
            elif nvk == 96:
                piece[k] = "lip_ring" if h.min() > 3.5 else "nozzle_band"
            elif np.ptp(r) < 0.01:
                piece[k] = "throat_glow"
            elif r.min() < 1.15 and nvk == 48 and h.min() > 3.3:
                piece[k] = "throat_recess"
            else:
                piece[k] = "nozzle_shell"
        else:
            part[k] = "Pod_" + tag
            big = ext.max()
            if nvk == 48 and np.ptp(h) > 3.5:
                piece[k] = "drum"
            elif nvk == 96:
                piece[k] = "rib"
            elif nvk == 120:
                piece[k] = "mount_collar"
            elif nvk == 12:
                piece[k] = "plate" if big > 0.8 else "pipe" if big > 0.3 else "clamp" if big > 0.2 else "bolt"
            elif nvk == 8:
                piece[k] = "side_box"
            else:
                piece[k] = "pod_misc"
    # petals ordered by angle around the axis
    ref = np.cross(a, [0, 1, 0]); ref /= np.linalg.norm(ref)
    ref2 = np.cross(a, ref)
    def ang(k):
        d = co[isl_verts[k]].mean(0) - t0
        return math.atan2(d @ ref2, d @ ref) % (2 * math.pi)
    for i, k in enumerate(sorted(petals, key=ang)):
        group[k] = i

# turbines -------------------------------------------------------------
tj = names.index("Turbines")
tur = np.where(src == tj)[0]
for side, tag in ((1, "L"), (-1, "R")):
    ks = [k for k in tur if np.sign(co[isl_verts[k]].mean(0)[1]) == side]
    shell = max(ks, key=lambda k: len(isl_verts[k]))
    p = co[isl_verts[shell]]
    # centre on the axis: mid of the shell bbox in y/z, and the shell's x mid as reference
    TC = np.array([0.0, (p[:, 1].min() + p[:, 1].max()) / 2, (p[:, 2].min() + p[:, 2].max()) / 2])
    TC[0] = (p[:, 0].min() + p[:, 0].max()) / 2
    hub = None
    for k in ks:
        q = co[isl_verts[k]]; d = q - TC
        r = np.linalg.norm(d[:, 1:], axis=1); dx = d[:, 0]
        nvk = len(q)
        if q[:, 0].max() > TC[0] + 2.2:               # reaches forward/inboard to the hull
            part[k] = "FanMount_" + tag
            sv = np.linalg.svd(q - q.mean(0), compute_uv=False)
            piece[k] = "pylon" if sv[1] > 1.0 else "strut"     # pylon: 2.4 x 1.6 slab, struts: 0.4 square
        elif r.max() <= 2.78 and dx.min() > -0.65 and dx.max() < 1.3:   # inside the duct: spins
            part[k] = "FanRotor_" + tag
            piece[k] = "hub_spinner" if r.min() < 0.1 else "blade"
            if r.min() < 0.1:
                hub = k
        else:
            part[k] = "FanHousing_" + tag
            if k == shell: piece[k] = "shell"
            elif nvk == 160: piece[k] = "intake_lip"
            elif np.ptp(r) < 0.01 and nvk == 64: piece[k] = "duct_back_wall"
            elif nvk == 48 and dx.max() < -1.5: piece[k] = "tail_cone"
            elif nvk == 222: piece[k] = "gimbal_ring"
            elif nvk == 20: piece[k] = "ring_knob"
            elif nvk == 8 and q[:, 2].max() < TC[2] - 3.0: piece[k] = "hanging_rod"
            elif nvk == 8 and r.min() > 3.4 and r.max() < 4.2 and np.ptp(dx) < 0.35: piece[k] = "ring_beam"
            elif nvk == 8 and np.ptp(q[:, 0]) > 2.9 and np.ptp(q[:, 1]) > 1.9: piece[k] = "top_platform"
            elif nvk == 8 and min(q.max(0) - q.min(0)) > 0.7: piece[k] = "top_winch"
            elif nvk == 8: piece[k] = "top_rail"
            else: piece[k] = "housing_misc"
    # blades: index by angle about the X axis
    blades = [k for k in ks if piece[k] == "blade"]
    for i, k in enumerate(sorted(blades, key=lambda k: math.atan2(*(co[isl_verts[k]].mean(0) - TC)[[2, 1]]) % (2 * math.pi))):
        group[k] = i
    ring_x = float(np.mean([co[isl_verts[k]][:, 0].mean() for k in ks if piece[k] == "gimbal_ring"]))
    bl = np.concatenate([co[isl_verts[k]] for k in blades])
    frames["Fan_" + tag] = dict(axis_yz=[float(TC[1]), float(TC[2])], spin_axis=[1, 0, 0], yaw_axis=[0, 0, 1],
                                yaw_pivot=[ring_x, float(TC[1]), float(TC[2])],
                                spin_pivot=[float(bl[:, 0].mean()), float(TC[1]), float(TC[2])],
                                blade_tip_radius=float(np.linalg.norm((bl - TC)[:, 1:], axis=1).max()),
                                shell_radius_max=float(np.linalg.norm((p - TC)[:, 1:], axis=1).max()),
                                shell_x=[float(p[:, 0].min()), float(p[:, 0].max())],
                                housing_x=[float(min(co[isl_verts[k]][:, 0].min() for k in ks if part[k].startswith("FanHousing"))),
                                           float(max(co[isl_verts[k]][:, 0].max() for k in ks if part[k].startswith("FanHousing")))])

# rudder ----------------------------------------------------------------
for k in np.where(src == names.index("Rudder"))[0]:
    part[k] = "Rudder"
    piece[k] = "blade" if len(isl_verts[k]) == 30 else "tiller_bar"

# gantry: searchlights, hanging strips, sag chains, winch drums ---------
gj = names.index("Gantry")
gk = list(np.where(src == gj)[0])
posts = []
for k in gk:
    p, c, mn, mx = stats(k); e = mx - mn
    if len(p) == 12 and e[2] > 2.9 and e[0] < 0.2 and e[1] < 0.2:
        posts.append(k)
lamp_names = {}
for k in posts:
    c = co[isl_verts[k]].mean(0)
    base = co[isl_verts[k]][:, 2].min()
    nm = "SearchLight_%s%s" % ("Fwd" if c[0] > 27 else "Mid" if c[0] > 20 else "Aft", "L" if c[1] > 1.5 else "R" if c[1] < -1.5 else "C")
    lamp_names[k] = nm
    part[k] = nm; piece[k] = "post"
    top = co[isl_verts[k]][:, 2].max()
    frames[nm] = dict(post_base=[float(c[0]), float(c[1]), float(base)], post_top=[float(c[0]), float(c[1]), float(top)])
    for j in gk:
        if j == k: continue
        q = co[isl_verts[j]]; cj = q.mean(0)
        if len(q) == 20 and abs(cj[1] - c[1]) < 0.1 and abs(cj[0] - c[0]) < 0.5 and abs(cj[2] - top) < 0.4:
            part[j] = nm
            piece[j] = "lens" if np.ptp(q[:, 0]) < 0.1 else "head"
            if piece[j] == "head":
                frames[nm]["head_pivot"] = [float(c[0]), float(c[1]), float(cj[2])]
BOT = 4.35   # build_airship gantry truss bottom chord
strips, chains = {}, {}
for k in gk:
    if part[k] != "Hull": continue
    p, c, mn, mx = stats(k); e = mx - mn
    if len(p) != 8: continue
    if 12.5 < c[0] < 16.6 and mx[2] < BOT + 0.05 and abs(e[1] - 0.40) < 0.01 and 0.45 < e[0] < 0.7:
        strips.setdefault(round(float(c[1]), 1), []).append(k)
    elif 0.14 < e[1] < 0.2 and mx[2] < BOT + 0.05 and (12.0 < c[0] < 16.4 or 21.4 < c[0] < 26.6) and abs(c[1]) > 2.8:
        chains.setdefault("ChainAft" if c[0] < 20 else "ChainFwd", []).append(k)
for i, (y, ks) in enumerate(sorted(strips.items())):
    nm = "HangStrip_%d" % (i + 1)
    ks.sort(key=lambda k: -co[isl_verts[k]][:, 2].max())
    for s, k in enumerate(ks):
        part[k] = nm; piece[k] = "segment"; group[k] = s
    top = co[isl_verts[ks[0]]]
    frames[nm] = dict(anchor=[float(top[:, 0].mean()), float(y), float(top[:, 2].max())], segments=len(ks),
                      bottom_z=float(co[isl_verts[ks[-1]]][:, 2].min()))
for nm, ks in chains.items():
    ks.sort(key=lambda k: co[isl_verts[k]].mean(0)[0])
    for s, k in enumerate(ks):
        part[k] = nm; piece[k] = "link"; group[k] = s
    a, b = co[isl_verts[ks[0]]], co[isl_verts[ks[-1]]]
    ea = a[np.argmin(a[:, 0])]; eb = b[np.argmax(b[:, 0])]
    frames[nm] = dict(end_a=[float(v) for v in ea], end_b=[float(v) for v in eb], links=len(ks),
                      lowest_z=float(min(co[isl_verts[k]][:, 2].min() for k in ks)))
for k in gk:
    if part[k] != "Hull": continue
    p, c, mn, mx = stats(k); e = mx - mn
    if len(p) == 28 and abs(c[2] - 5.0) < 0.05 and c[0] > 27:
        nm = "Winch_%s" % ("Fwd" if c[0] > 29.5 else "Aft")
        part[k] = nm; piece[k] = "drum" if e[1] > 2 else "flange"
        frames[nm] = dict(centre=[float(c[0]), 0.0, 5.0], spin_axis=[0, 1, 0])

# ------------------------------------------------------------------ 4. report
moving = {"Hull": "static root"}
def kind(nm):
    if nm == "Hull": return "static"
    if nm.startswith("FanMount"): return "static (fixed mount, weight to root)"
    if nm.startswith("Pod_"): return "gimbal pitch/roll"
    if nm.startswith("Nozzle_"): return "child of pod: vectoring / petals"
    if nm.startswith("FanHousing_"): return "yaw (steering)"
    if nm.startswith("FanRotor_"): return "spin about X, child of housing"
    if nm == "Rudder": return "yaw about hinge"
    if nm.startswith("SearchLight"): return "spring wobble at post base, head pan"
    if nm.startswith("HangStrip"): return "spring chain"
    if nm.startswith("Chain"): return "pendulum swing about end-to-end line"
    if nm.startswith("Winch"): return "optional spin"
    return "?"
counts = {}
for k in range(n_isl):
    c = counts.setdefault(part[k], dict(islands=0, verts=0, faces=0, tris=0, kind=kind(part[k]), pieces={}))
    c["islands"] += 1; c["verts"] += len(isl_verts[k]); c["faces"] += int(isl_nf[k]); c["tris"] += int(isl_tris[k])
    if piece[k]:
        c["pieces"][piece[k]] = c["pieces"].get(piece[k], 0) + 1
src_counts = {}
for k in range(n_isl):
    s = src_counts.setdefault(names[src[k]], dict(islands=0, verts=0, faces=0))
    s["islands"] += 1; s["verts"] += len(isl_verts[k]); s["faces"] += int(isl_nf[k])

unassigned, edited, degenerate = [], [], []
islands = []
for k in range(n_isl):
    p, c, mn, mx = stats(k)
    rec = dict(id=k, v0=int(isl_verts[k].min()), nv=len(p), nf=int(isl_nf[k]), tris=int(isl_tris[k]),
               src=names[src[k]], d_mean=round(float(dmean[k]), 5), d_max=round(float(dmax[k]), 5),
               part=part[k], piece=piece[k], c=[round(float(v), 4) for v in c],
               bbmin=[round(float(v), 4) for v in mn], bbmax=[round(float(v), 4) for v in mx])
    if group[k] is not None: rec["index"] = group[k]
    islands.append(rec)
    if dmax[k] > 3.0 - 1e-6: unassigned.append(k)
    elif dmax[k] > EDIT_TOL: edited.append(dict(id=k, src=names[src[k]], nv=len(p), d_max=round(float(dmax[k]), 4)))
    if np.ptp(p, axis=0).max() < 0.02: degenerate.append(dict(id=k, nv=len(p), c=[round(float(v), 3) for v in c]))

out = dict(source_blend=bpy.data.filepath, mesh=SM_NAME, n_verts=nv, n_faces=nf, n_tris=int((lt - 2).sum()),
           n_islands=n_isl, coords="Blender world metres: +X bow, +Y port/left, +Z up. Unreal: X=x*100, Y=-y*100, Z=z*100 cm",
           order_violations=order_violations, edit_tolerance_m=EDIT_TOL,
           source_parts=src_counts, parts=counts, frames=frames, unassigned=unassigned,
           edited_after_merge=edited, degenerate=degenerate, islands=islands)
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(out, f, indent=1)
part_names = sorted(counts)
if VOUT:
    with open(VOUT, "w") as f:
        json.dump(dict(mesh=SM_NAME, n_verts=nv, parts=part_names,
                       vertex_part=[part_names.index(part[k]) for k in v_isl],
                       vertex_island=[int(k) for k in v_isl]), f, separators=(",", ":"))
print("CLASSIFY islands=%d order_violations=%d unassigned=%d edited=%s" % (n_isl, order_violations, len(unassigned), edited))
for nm in part_names:
    print("CLASSIFY %-20s %s" % (nm, {k: v for k, v in counts[nm].items() if k != "pieces"}))

# ------------------------------------------------------------------ 5. check renders
if RENDER:
    os.makedirs(RENDER, exist_ok=True)
    PAL = {"Hull": (0.62, 0.62, 0.64), "Pod_": (0.95, 0.55, 0.15), "Nozzle_": (0.85, 0.1, 0.1),
           "FanHousing_": (0.15, 0.45, 0.95), "FanRotor_": (1.0, 0.9, 0.1), "FanMount_": (0.1, 0.55, 0.2),
           "Rudder": (0.6, 0.2, 0.8), "SearchLight": (0.0, 0.85, 0.85), "HangStrip": (1.0, 0.2, 0.75),
           "Chain": (0.55, 1.0, 0.4), "Winch": (0.45, 0.25, 0.1)}
    POD_SHADE = {"FL": 1.0, "FR": 0.8, "RL": 0.65, "RR": 0.5}
    def colour(nm):
        for key, c in PAL.items():
            if nm.startswith(key):
                if key in ("Pod_", "Nozzle_"):
                    s = POD_SHADE[nm.split("_")[1]]
                    return (c[0] * s, c[1] * s, c[2] * s, 1)
                if nm.endswith("_R") and key.startswith("Fan"):
                    return (c[0] * 0.7, c[1] * 0.7, c[2] * 0.7, 1)
                return (*c, 1)
        return (1, 0, 1, 1)
    scene = bpy.context.scene
    for o in list(scene.objects):
        o.hide_render = True
    coll = bpy.data.collections.new("PartCheck"); scene.collection.children.link(coll)
    polys = [tuple(lv[ls[i]:ls[i] + lt[i]]) for i in range(nf)]
    for nm in part_names:
        fsel = [i for i in range(nf) if part[f_isl[i]] == nm]
        vs = sorted({v for i in fsel for v in polys[i]})
        remap = {v: j for j, v in enumerate(vs)}
        m = bpy.data.meshes.new("chk_" + nm)
        m.from_pydata([tuple(co[v]) for v in vs], [], [tuple(remap[v] for v in polys[i]) for i in fsel])
        o = bpy.data.objects.new("chk_" + nm, m); o.color = colour(nm); coll.objects.link(o)
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light, sh.color_type = "STUDIO", "OBJECT"     # flat per-part colours, studio light for shape
    scene.view_settings.view_transform = "Standard"
    sh.show_object_outline, sh.object_outline_color = True, (0, 0, 0)
    sh.show_cavity = False
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    scene.render.film_transparent = False
    scene.world = scene.world or bpy.data.worlds.new("W")
    scene.world.color = (1, 1, 1)
    cam_d = bpy.data.cameras.new("ChkCam"); cam = bpy.data.objects.new("ChkCam", cam_d); scene.collection.objects.link(cam)
    scene.camera = cam
    VIEWS = {  # name: (location, target, ortho scale or None + lens)
        "chase": ((-52, 24, 24), (1, 0, 1), None, 36),
        "side_port": ((2, 80, 2), (5.5, 0, 2), 58, None),
        "below": ((-2, 18, -70), (2, 0, -2), 56, None),
        "fan_close": ((-2, 24, 7), (-17.2, 7.6, 1.4), None, 38),
        "fan_rear": ((-36, 16, 8), (-17.2, 0, 1.4), None, 34),
        "pod_close": ((14, 16, -10), (3.6, 4.7, -3.0), None, 45),
        "gantry_close": ((30, 22, 12), (19, 0, 4.5), None, 32),
    }
    for vname, (loc, tgt, ortho, lens) in VIEWS.items():
        cam.location = V(loc)
        cam.rotation_euler = (V(tgt) - V(loc)).to_track_quat("-Z", "Y").to_euler()
        if ortho:
            cam_d.type, cam_d.ortho_scale = "ORTHO", ortho
        else:
            cam_d.type, cam_d.lens = "PERSP", lens
        scene.render.filepath = os.path.join(RENDER, "parts_%s.png" % vname)
        bpy.ops.render.render(write_still=True)
    print("CLASSIFY renders ->", RENDER)
