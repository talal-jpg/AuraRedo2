"""Pivots, axes and clearance ranges of the moving parts of SM_Airship (read-only, never saves).

Usage:
  blender -b --factory-startup <copy.blend> --python rig_analysis.py -- \
      --islands sm_airship_islands.json --vparts sm_airship_vertex_parts.json --out rig_clearance.json

Needs classify_islands.py output. Blender world metres / degrees.

Clearance method (rotate a copy in 1 deg steps until the first failure):
  * PEN  - penetration into the closed hull shell (island 392, manifold, outward normals): points sampled on the
           moving faces (vertices + 0.15 m barycentric grid) that are OUTSIDE the shell at rest must not go deeper
           than PEN_TOL inside it. Points already inside at rest (the pods/rudder are built half sunk into the hull)
           are ignored: moving them deeper is invisible.
  * HIT  - BVH overlap with every other static island (pipes, bands, rails, deck props, fans, ...): any face pair
           that did not intersect at rest is a contact. Static islands that already intersect the group at rest
           ("supports", e.g. the deck block a lamp post stands in) are left out and listed.
"""
import bpy, json, math, sys
import numpy as np
from collections import Counter
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(n, d=None):
    return argv[argv.index(n) + 1] if n in argv else d
ISL = json.load(open(arg("--islands", "sm_airship_islands.json")))
VP = json.load(open(arg("--vparts", "sm_airship_vertex_parts.json")))
OUT = arg("--out", "rig_clearance.json")
PEN_TOL, SOFT_TOL, SPACING, STEP = 0.02, 0.06, 0.15, 1.0

me = bpy.data.objects["SM_Airship"].data
nv, nf = len(me.vertices), len(me.polygons)
co = np.zeros(nv * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
polys = [tuple(p.vertices) for p in me.polygons]
PN = VP["parts"]
vpart = np.array(VP["vertex_part"]); visl = np.array(VP["vertex_island"])
fpart = np.array([vpart[p[0]] for p in polys]); fisl = np.array([visl[p[0]] for p in polys])
islands = ISL["islands"]; IS = {r["id"]: r for r in islands}; FR = ISL["frames"]
co_list = co.tolist()
faces_by_isl = {}
for i, k in enumerate(fisl):
    faces_by_isl.setdefault(int(k), []).append(i)
SHELL = max((r for r in islands if r["src"] == "Hull"), key=lambda r: r["nv"])["id"]   # the hull skin (392)
shell_f = faces_by_isl[SHELL]
shell_bvh = BVHTree.FromPolygons(co_list, [polys[i] for i in shell_f])
R = {"method": __doc__.split("Clearance method")[1].strip(), "hull_shell_island": SHELL, "pen_tol_m": PEN_TOL}

def isl_ids(part=None, pieces=None, prefix=None):
    return [r["id"] for r in islands if (part is None or r["part"] == part) and (prefix is None or r["part"].startswith(prefix))
            and (pieces is None or r["piece"] in pieces)]
def faces_of_isl(ids):
    return np.array(sorted(i for k in ids for i in faces_by_isl[k]), dtype=int)
def faces_of(*parts):
    return faces_of_isl([r["id"] for r in islands if r["part"] in parts])

def rot(p, axis, deg):
    a = np.asarray(axis, float); a = a / np.linalg.norm(a)
    t = math.radians(deg); c, s = math.cos(t), math.sin(t)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    Rm = np.eye(3) + s * K + (1 - c) * K @ K
    M = np.eye(4); M[:3, :3] = Rm; M[:3, 3] = np.asarray(p) - Rm @ np.asarray(p)
    return M
def xf(P, M):
    return P if M is None else P @ M[:3, :3].T + M[:3, 3]

class Group:
    def __init__(self, fids):
        self.f = np.asarray(fids, dtype=int)
        vs = sorted({v for i in self.f for v in polys[i]})
        self.v = np.array(vs); rm = {v: j for j, v in enumerate(vs)}
        self.p = [tuple(rm[v] for v in polys[i]) for i in self.f]
        pts = [co[self.v]]; ids = [visl[self.v]]
        for i in self.f:                                   # barycentric samples on each fan triangle
            q = co[list(polys[i])]
            for t in range(1, len(q) - 1):
                a, b, c = q[0], q[t], q[t + 1]
                n = int(math.ceil(max(np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(c - b)) / SPACING))
                if n < 2: continue
                for u in range(n + 1):
                    for w in range(n + 1 - u):
                        pts.append([(a * (n - u - w) + b * u + c * w) / n]); ids.append([fisl[i]])
        self.S = np.concatenate([np.atleast_2d(p) for p in pts])
        self.Si = np.concatenate([np.atleast_1d(np.asarray(x)) for x in ids])
    def bvh(self, M=None):
        return BVHTree.FromPolygons(xf(co[self.v], M).tolist(), self.p)

_ib = {}
def island_depth(k, P):
    """max depth of points P inside closed island k (nearest-face normal test), 0 if none inside."""
    r = IS[k]; lo = np.array(r["bbmin"]) - 0.01; hi = np.array(r["bbmax"]) + 0.01
    sel = np.all((P >= lo) & (P <= hi), axis=1)
    if not sel.any(): return 0.0
    if k not in _ib: _ib[k] = BVHTree.FromPolygons(co_list, [polys[i] for i in faces_by_isl[k]])
    best = 0.0
    for p in P[sel]:
        q, n, _, d = _ib[k].find_nearest(V(p))
        if (V(p) - q).dot(n) < 0: best = max(best, d)
    return best

RAYS = [V((0.5373, 0.2341, 0.8102)).normalized(), V((-0.3127, 0.8846, -0.3459)).normalized()]
def parity_inside(p):
    """ray parity against the closed hull shell, two directions must agree (guards against grazing hits)."""
    votes = 0
    for d in RAYS:
        n, o = 0, V(p)
        for _ in range(40):
            h = shell_bvh.ray_cast(o + d * 1e-4, d, 500)
            if h[0] is None: break
            n += 1; o = h[0]
        votes += n % 2
    return votes == 2

def depth(P):
    """signed: >0 inside the hull shell (distance to surface), <=0 outside (minus distance).
    Nearest-face sign, confirmed by ray parity for every point within 0.3 m of the skin."""
    out = np.empty(len(P))
    for i, p in enumerate(P):
        q, n, _, d = shell_bvh.find_nearest(V(p))
        inside = (V(p) - q).dot(n) < 0
        if d < 0.3 or inside:
            inside = parity_inside(p)
        out[i] = d if inside else -d
    return out

class Test:
    """One moving group: penetration test vs the hull shell + strict overlap vs the other static islands."""
    def __init__(self, g, exclude_faces=(), pen=True):
        self.g = g
        ex = set(int(i) for i in g.f) | set(int(i) for i in exclude_faces) | set(shell_f)
        cand = [i for i in range(nf) if i not in ex]
        st = BVHTree.FromPolygons(co_list, [polys[i] for i in cand])
        rest = {int(cand[j]) for _, j in g.bvh().overlap(st)}
        self.supports = sorted({int(fisl[f]) for f in rest})
        drop = set(f for k in self.supports for f in faces_by_isl[k])
        self.cand = np.array([i for i in cand if i not in drop], dtype=int)
        self.st = BVHTree.FromPolygons(co_list, [polys[i] for i in self.cand])
        self.pen = pen
        if pen:
            d0 = depth(g.S)
            self.rest_inside = float((d0 > 0).mean())
            # islands that already pierce the hull skin at rest are "anchored": crossing the skin is fine for them
            # (a pierced cylinder just changes its piercing angle), they only must not pull out of it.
            cnt = Counter(int(k) for k in g.Si[d0 > 0])
            self.anchored = sorted(k for k, c in cnt.items() if c >= 3)
            free = ~np.isin(g.Si, self.anchored)
            self.out = g.S[free & (d0 <= 0)]; self.out_d = -d0[free & (d0 <= 0)]
            self.anc = {k: g.S[(g.Si == k)] for k in self.anchored}
    def ok(self, M, pivot, deg):
        """returns (hard_ok, soft_ok, reason): hard = no new contact at all, soft = nothing deeper than SOFT_TOL."""
        h = {int(self.cand[j]) for _, j in self.g.bvh(M).overlap(self.st)}
        reason, deep = "", 0.0
        if h:
            ks = sorted({int(fisl[f]) for f in h})
            P = xf(self.g.S, M)
            for k in ks:
                deep = max(deep, island_depth(k, P))
            reason = "isl " + ",".join("%d:%s%s" % (k, IS[k]["src"], ("/" + IS[k]["piece"]) if IS[k]["piece"] else "") for k in ks[:4]) + \
                     " depth %.2f" % deep
        if self.pen:
            reach = np.linalg.norm(self.out - pivot, axis=1) * math.radians(deg) + SOFT_TOL
            sel = self.out_d <= reach
            if sel.any():
                d = depth(xf(self.out[sel], M)).max()
                if d > PEN_TOL:
                    reason = (reason + "; " if reason else "") + "hull shell %.2f" % d
                    h = h or {-1}
                    deep = max(deep, d)
            for k, P in self.anc.items():          # anchored pieces must not open a visible gap to the skin
                if deg <= 0: continue
                d = depth(xf(P[::max(1, len(P) // 400)], M))
                if not (d > 0).any():
                    gap = float((-d).min())
                    if gap > PEN_TOL:
                        reason = (reason + "; " if reason else "") + "isl %d %s lifts %.2f off the skin" % (k, IS[k]["piece"], gap)
                        h = h or {-2}; deep = max(deep, gap)
        return not h, deep <= SOFT_TOL, reason
    def sweep(self, pivot, axis, max_deg=45):
        """[hard_limit, soft_limit, reason at the hard limit, reason at the soft limit] in degrees."""
        a, hard, hr = 0.0, None, ""
        while a < max_deg - 1e-9:
            h_ok, s_ok, why = self.ok(rot(pivot, axis, a + STEP), np.asarray(pivot), a + STEP)
            if not h_ok and hard is None:
                hard, hr = a, why
            if not s_ok:
                return [hard if hard is not None else a, a, hr, why]
            a += STEP
        return [hard if hard is not None else max_deg, max_deg, hr, "free to %d" % max_deg]
    def info(self):
        d = dict(supports=[(k, IS[k]["src"], IS[k]["piece"] or "-") for k in self.supports])
        if self.pen:
            d["rest_fraction_inside_hull_shell"] = round(self.rest_inside, 3)
            d["anchored_in_hull_skin"] = [(k, IS[k]["piece"] or IS[k]["src"]) for k in self.anchored]
        return d

# ---------------------------------------------------------------- thruster pods
R["pods"] = {}
for tag in ("FL", "FR", "RL", "RR"):
    f = FR["Pod_" + tag]
    O, A = np.array(f["origin"]), np.array(f["axis_nozzle"])
    side = 1 if O[1] > 0 else -1
    T = Test(Group(faces_of("Pod_" + tag, "Nozzle_" + tag)))
    lim = {}
    for phi in range(0, 360, 15):
        u = np.array([math.cos(math.radians(phi)), math.sin(math.radians(phi)), 0.0])
        lim[phi] = T.sweep(O, np.cross([0, 0, -1.0], u), 40)      # +angle swings the nozzle toward u
    out_phi, in_phi = (90, 270) if side > 0 else (270, 90)
    R["pods"][tag] = dict(
        pivot=[round(v, 4) for v in O], nozzle_axis=[round(v, 5) for v in A], nozzle_pivot=[round(v, 4) for v in f["nozzle_pivot"]],
        rest_tilt_aft_deg=round(math.degrees(math.atan2(-A[0], -A[2])), 2), **T.info(),
        nozzle_fore=lim[0], nozzle_aft=lim[180], nozzle_outboard=lim[out_phi], nozzle_inboard=lim[in_phi],
        cone_min_hard=min(v[0] for v in lim.values()), cone_min_soft=min(v[1] for v in lim.values()),
        cone=[[k] + v for k, v in lim.items()])
    print("POD", tag, {k: v for k, v in R["pods"][tag].items() if k != "cone"})
    for c in R["pods"][tag]["cone"]: print("   cone", tag, c)

# nozzle vectoring relative to its pod: pivot S(2.4) on the axis (drum/nozzle joint), drum excluded (it is the socket)
R["nozzle_vectoring"] = {}
for tag in ("FL", "FR", "RL", "RR"):
    f = FR["Pod_" + tag]; side = 1 if f["origin"][1] > 0 else -1
    drum = isl_ids("Pod_" + tag, ("drum",))
    T = Test(Group(faces_of("Nozzle_" + tag)), exclude_faces=faces_of_isl(drum), pen=True)
    np_ = np.array(f["nozzle_pivot"]); row = {}
    for lab, phi in (("fore", 0), ("aft", 180), ("out", 90 if side > 0 else 270), ("in", 270 if side > 0 else 90)):
        u = np.array([math.cos(math.radians(phi)), math.sin(math.radians(phi)), 0.0])
        row[lab] = T.sweep(np_, np.cross([0, 0, -1.0], u), 30)
    R["nozzle_vectoring"][tag] = dict(pivot=np_.round(4).tolist(), joint_radius_m=1.6,
                                      rim_gap_m_at_deg={d: round(1.6 * math.sin(math.radians(d)), 3) for d in (2, 4, 6, 8, 10)}, **row)
    print("NOZZLE", tag, R["nozzle_vectoring"][tag])

# pivot height scan (main 4 directions) - where along the pod axis a gimbal pivot fits best
R["pod_pivot_scan"] = {}
for tag in ("FL", "FR", "RL", "RR"):
    f = FR["Pod_" + tag]; T0p, A = np.array(f["T0"]), np.array(f["axis_nozzle"]); side = 1 if T0p[1] > 0 else -1
    T = Test(Group(faces_of("Pod_" + tag, "Nozzle_" + tag)))
    rows = []
    for hh in (-1.6, -0.4, 0.4, 1.2, 2.0):
        p = T0p + A * hh
        row = dict(h=hh, pivot=p.round(3).tolist())
        for lab, phi in (("fore", 0), ("aft", 180), ("out", 90 if side > 0 else 270), ("in", 270 if side > 0 else 90)):
            u = np.array([math.cos(math.radians(phi)), math.sin(math.radians(phi)), 0.0])
            r = T.sweep(p, np.cross([0, 0, -1.0], u), 30)
            row[lab] = r[:2]
        rows.append(row)
        print("PODSCAN", tag, row)
    R["pod_pivot_scan"][tag] = rows

# petals of one nozzle (all pods are copies of one mesh)
f = FR["Pod_FL"]; A = np.array(f["axis_nozzle"]); T0 = np.array(f["T0"])
pet = sorted([r for r in islands if r["part"] == "Nozzle_FL" and r["piece"] == "petal"], key=lambda r: r["index"])
po, pc, sup = [], [], set()
for r in pet:
    T = Test(Group(faces_of_isl([r["id"]])), pen=False)
    sup |= {IS[k]["piece"] or IS[k]["src"] for k in T.supports}
    d = np.array(r["c"]) - T0; d -= A * (d @ A); d /= np.linalg.norm(d)
    hinge = T0 + A * 3.9 + d * 1.45
    po.append(T.sweep(hinge, np.cross(A, d), 45)); pc.append(T.sweep(hinge, -np.cross(A, d), 45))
R["petals"] = dict(hinge="T0 + A*3.9 + d*1.45 (petal top edge centre), axis A x d (tangent), +angle = flare outward",
                   supports_at_rest=sorted(sup), open=po[0], close=pc[0],
                   open_min_hard=min(p[0] for p in po), close_min_hard=min(p[0] for p in pc), length_m=0.48)
print("PETALS", R["petals"])

# ---------------------------------------------------------------- rear fans
def prof_inside(dx, r):
    sc = 0.82
    prof = [(h * sc, rr * sc) for rr, h in ((3.5, -1.9), (4.3, -1.6), (4.45, 0.5), (4.35, 1.45), (4.1, 1.95),
                                             (3.75, 2.05), (3.5, 1.85), (3.4, 1.2), (3.4, -1.7))]
    inside = False
    for (x0, y0), (x1, y1) in zip(prof, prof[1:] + prof[:1]):
        if (y0 > r) != (y1 > r) and dx < x0 + (r - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside

R["fans"] = {}
for tag in ("L", "R"):
    f = FR["Fan_" + tag]; side = 1 if tag == "L" else -1
    piv = np.array(f["yaw_pivot"]); TC = np.array([-17.2, f["axis_yz"][0], f["axis_yz"][1]])
    sp = np.array(f["spin_pivot"])
    H = "FanHousing_" + tag
    rotor = faces_of("FanRotor_" + tag); mount = faces_of("FanMount_" + tag)
    inner_ids = isl_ids(H, ("shell", "intake_lip", "duct_back_wall", "tail_cone", "hanging_rod"))
    frame_ids = [k for k in isl_ids(H) if k not in inner_ids]
    pylon = isl_ids("FanMount_" + tag, ("pylon",)); struts = isl_ids("FanMount_" + tag, ("strut",))
    beams = isl_ids(H, ("ring_beam",))
    def yaw_lims(T):
        a = T.sweep(piv, [0, 0, 1], 45); b = T.sweep(piv, [0, 0, -1], 45)    # +Z: intake turns toward +Y
        return (a, b) if side > 0 else (b, a)                                 # (intake outboard, intake inboard)
    # option A: the whole nacelle (shell, ring, top deck, rotor) yaws; only pylon + struts stay on the hull
    gA = Group(np.concatenate([faces_of(H), rotor]))
    TA = Test(gA, exclude_faces=mount)
    A_out, A_in = yaw_lims(TA)
    # option B: gimbal frame (ring, knobs, ring beams, top platform, rails, winch) stays with the hull mount,
    # the inner duct (shell, lip, back wall, tail cone, hanging rod) + rotor yaw inside it
    gB = Group(np.concatenate([faces_of_isl(inner_ids), rotor]))
    TB = Test(gB, exclude_faces=np.concatenate([mount, faces_of_isl(beams)]))
    B_out, B_in = yaw_lims(TB)
    # option C: whole nacelle yaws about a vertical axis through the pylon end (the pylon is the hinge)
    pe = None
    pend = co[visl == pylon[0]]; pend = pend[np.argsort(pend[:, 0])[:4]]       # 4 aft-most pylon verts = its end
    pivC = np.array([pend[:, 0].mean(), pend[:, 1].mean(), TC[2]])
    def yaw_lims_at(T, p):
        a = T.sweep(p, [0, 0, 1], 45); b = T.sweep(p, [0, 0, -1], 45)
        return (a, b) if side > 0 else (b, a)
    C_out, C_in = yaw_lims_at(TA, pivC)
    # pipe ends that plug into the nacelle: let them clip and see what limits next
    nac = Group(np.concatenate([faces_of(H), rotor]))
    lo, hi = nac.S.min(0) - 0.8, nac.S.max(0) + 0.8
    near = []
    for r in islands:
        if r["src"] != "SteamPipes": continue
        if np.any(np.array(r["bbmax"]) < lo) or np.any(np.array(r["bbmin"]) > hi): continue
        P = co[visl == r["id"]]
        nb = BVHTree.FromPolygons(xf(co[nac.v], None).tolist(), nac.p)
        if min(nb.find_nearest(V(q))[3] for q in P) < 0.6: near.append(r["id"])
    TAp = Test(nac, exclude_faces=np.concatenate([mount, faces_of_isl(near)]))
    scan = []
    for px in (-17.446, -17.2, -17.0):
        for off in (0.0, 1.0, 1.5, 2.0, 2.25, 2.5, 3.0):
            p = np.array([px, TC[1] - side * off, TC[2]])
            o_, i_ = yaw_lims_at(TAp, p)
            scan.append(dict(pivot=p.round(3).tolist(), inboard_offset=off, hull_out=o_[:2], hull_in=i_[:2], why_out=o_[3], why_in=i_[3]))
    # rotor vs pylon: yaw x one blade period of spin
    gr = Group(rotor)
    pyb = BVHTree.FromPolygons(co_list, [polys[i] for i in faces_of_isl(pylon)])
    def rotor_hits_pylon(deg, p=None):
        p = piv if p is None else p
        for s in np.arange(0, 360 / 28, 1.0):
            M = rot(p, [0, 0, 1], deg) @ rot(sp, [1, 0, 0], s)
            if gr.bvh(M).overlap(pyb):
                return True
        return False
    def walk(pred, sign):
        a = 0
        while a < 45 and pred(sign * (a + 1)): a += 1
        return a
    rest_contact = rotor_hits_pylon(0)
    pos = walk(lambda d: not rotor_hits_pylon(d), 1) if not rest_contact else 0
    neg = walk(lambda d: not rotor_hits_pylon(d), -1) if not rest_contact else 0
    bl_out, bl_in = (pos, neg) if side > 0 else (neg, pos)
    posC = walk(lambda d: not rotor_hits_pylon(d, pivC), 1); negC = walk(lambda d: not rotor_hits_pylon(d, pivC), -1)
    blC_out, blC_in = (posC, negC) if side > 0 else (negC, posC)
    rmin = 9.0
    for s in np.arange(0, 360 / 28, 1.0):
        P = xf(co[gr.v], rot(sp, [1, 0, 0], s))
        for p in P:
            q = pyb.find_nearest(V(p))
            if q[0] is not None: rmin = min(rmin, q[3])
    # embedded ends (struts into the shell wall; ring beams into the shell wall for option B)
    def ends(k, n=4):
        p = co[visl == k]; return p[np.argsort(np.linalg.norm(p - TC, axis=1))[:n]]
    def embedded(ids, deg, p=None):
        M = rot(piv if p is None else p, [0, 0, 1], -deg)
        for k in ids:
            for x, y, z in xf(ends(k), M) - TC:
                if not prof_inside(x, math.hypot(y, z)): return False
        return True
    def emb_range(ids, pv=None):
        if not embedded(ids, 0): return None
        p = walk(lambda d: embedded(ids, d, pv), 1); n = walk(lambda d: embedded(ids, d, pv), -1)
        return (p, n) if side > 0 else (n, p)
    for row in scan:
        p = np.array(row["pivot"])
        a_ = walk(lambda d: not rotor_hits_pylon(d, p), 1); b_ = walk(lambda d: not rotor_hits_pylon(d, p), -1)
        row["rotor_vs_pylon_out_in"] = (a_, b_) if side > 0 else (b_, a_)
        row["struts_embedded_out_in"] = emb_range(struts, p)
        print("FANSCAN", tag, row)
    # how deep the plugged-in pipe ends sink into the nacelle shell at the recommended pivot / angles
    shell_isl = isl_ids(H, ("shell",))[0]; lip_isl = isl_ids(H, ("intake_lip",))[0]
    rec = np.array([-17.2, TC[1] - side * 2.25, TC[2]])
    PE = np.concatenate([co[visl == k] for k in near]) if near else np.zeros((0, 3))
    clip = {}
    for deg in (-20, -12, -6, 0, 6, 12, 20):
        Pl = xf(PE, rot(rec, [0, 0, 1], -deg))           # pipe ends in the yawed nacelle frame
        clip[(deg if side > 0 else -deg)] = round(max(island_depth(shell_isl, Pl), island_depth(lip_isl, Pl)), 3)
    R["fans"][tag] = dict(recommended_pivot=rec.round(4).tolist(), pipe_end_depth_in_nacelle_by_outboard_deg=clip,
        yaw_pivot=[round(v, 4) for v in piv], yaw_axis=[0, 0, 1], spin_pivot=[round(v, 4) for v in sp], spin_axis=[1, 0, 0],
        design_centre=TC.round(4).tolist(),
        optionA_whole_nacelle=dict(intake_outboard=A_out, intake_inboard=A_in, **TA.info()),
        optionB_inner_duct=dict(intake_outboard=B_out, intake_inboard=B_in, **TB.info()),
        optionC_pylon_hinge=dict(yaw_pivot=pivC.round(4).tolist(), intake_outboard=C_out, intake_inboard=C_in,
                                 rotor_clear_of_pylon_outboard_inboard=(blC_out, blC_in),
                                 struts_embedded_outboard_inboard=emb_range(struts, pivC)),
        rotor_pylon_contact_at_rest=rest_contact, rotor_pylon_min_gap_at_rest_m=round(rmin, 3),
        rotor_clear_of_pylon_intake_outboard=bl_out, rotor_clear_of_pylon_intake_inboard=bl_in,
        struts_embedded_outboard_inboard=emb_range(struts), ring_beams_embedded_outboard_inboard=emb_range(beams),
        pipe_ends_plugged_into_nacelle=near, pivot_scan_with_pipe_ends_clipping=scan,
        pylon_end=ends(pylon[0]).round(3).tolist())
    print("FAN", tag, R["fans"][tag])

# ---------------------------------------------------------------- rudder
T = Test(Group(faces_of("Rudder")))
aft = []
for z in np.arange(-4.4, 3.01, 0.5):
    h = shell_bvh.ray_cast(V((-30, 0.02, z)), V((1, 0, 0)), 40)
    aft.append((round(float(z), 2), None if h[0] is None else round(h[0].x, 3)))
xa = min(x for z, x in aft if x is not None and z > -2.5)
le_top, le_bot = np.array([-15.6, 0, 2.9]), np.array([-16.0, 0, -4.4])      # build_airship rudder outline
R["rudder"] = dict(hull_aft_x_on_centreline_by_z=aft, **T.info(), hinges={})
for nm, (p, ax) in {"leading_edge": (le_top, le_top - le_bot), "vertical_at_hull_aft_face": (np.array([xa, 0, 1.4]), np.array([0, 0, 1.0]))}.items():
    a1 = T.sweep(p, ax, 60); a2 = T.sweep(p, -ax, 60)        # about +Z-ish: +angle swings the trailing edge to -Y
    R["rudder"]["hinges"][nm] = dict(point=p.round(3).tolist(), axis=(ax / np.linalg.norm(ax)).round(4).tolist(),
                                     trailing_edge_to_starboard=a1, trailing_edge_to_port=a2)
print("RUDDER", R["rudder"])

# ---------------------------------------------------------------- searchlights
R["searchlights"] = {}
for nm in sorted(k for k in FR if k.startswith("SearchLight")):
    g = Group(faces_of(nm))
    base = np.array(FR[nm]["post_base"]); post = isl_ids(nm, ("post",))[0]
    under = [r["id"] for r in islands if r["part"] == "Hull" and r["bbmin"][0] <= base[0] <= r["bbmax"][0]
             and r["bbmin"][1] <= base[1] <= r["bbmax"][1] and abs(r["bbmax"][2] - base[2]) < 0.02]
    T = Test(g, exclude_faces=faces_of_isl(under), pen=False)
    # pivot where the post leaves its support (deck block it stands in), else the post foot
    top = base[2]
    for k in T.supports:
        r = IS[k]
        if r["bbmin"][0] <= base[0] <= r["bbmax"][0] and r["bbmin"][1] <= base[1] <= r["bbmax"][1]:
            top = max(top, r["bbmax"][2])
    piv = np.array([base[0], base[1], top])
    lims = []
    for phi in range(0, 360, 45):
        u = np.array([math.cos(math.radians(phi)), math.sin(math.radians(phi)), 0.0])
        lims.append(T.sweep(piv, np.cross([0, 0, 1.0], u), 20)[0])                       # +angle tips the head toward u
    hg = Group(faces_of_isl(isl_ids(nm, ("head", "lens"))))
    hp = np.array(FR[nm]["head_pivot"])
    st = BVHTree.FromPolygons(co_list, [polys[i] for i in range(nf) if fpart[i] != PN.index(nm)])
    gap = min(st.find_nearest(V(p))[3] for p in hg.S)
    R["searchlights"][nm] = dict(post_foot=base.round(3).tolist(), wobble_pivot=piv.round(3).tolist(), stands_on=under,
                                 free_post_length=round(base[2] + 3.0 - top, 3), head_pivot=hp.round(3).tolist(),
                                 **T.info(), tilt_limit_by_dir_0_45_90_135_180_225_270_315=lims, tilt_limit_min=min(lims),
                                 head_gap_to_static_m=round(gap, 3))
    print("LAMP", nm, R["searchlights"][nm])

# ---------------------------------------------------------------- hanging strips and sagging chains
R["strips"] = {}
for nm in sorted(k for k in FR if k.startswith("HangStrip")):
    T = Test(Group(faces_of(nm)))
    a = np.array(FR[nm]["anchor"])
    segs = sorted([r for r in islands if r["part"] == nm], key=lambda r: r["index"])
    seg_in = []
    for r in segs:
        gs = Group(faces_of_isl([r["id"]]))
        seg_in.append(round(float((depth(gs.S) > 0).mean()), 2))
    sw = {lab: T.sweep(a, np.cross([0, 0, -1.0], u), 45)[0] for lab, u in
          (("fore", [1, 0, 0]), ("aft", [-1, 0, 0]), ("port", [0, 1, 0]), ("stbd", [0, -1, 0]))}
    R["strips"][nm] = dict(anchor=[round(v, 3) for v in a], bottom_z=round(FR[nm]["bottom_z"], 3), segments=len(segs),
                           segment_fraction_inside_hull_shell=seg_in, **T.info(), swing_limits=sw)
    print("STRIP", nm, R["strips"][nm])
R["chains"] = {}
for nm in sorted(k for k in FR if k.startswith("Chain")):
    T = Test(Group(faces_of(nm)))
    a, b = np.array(FR[nm]["end_a"]), np.array(FR[nm]["end_b"])
    R["chains"][nm] = dict(end_a=a.round(3).tolist(), end_b=b.round(3).tolist(), lowest_z=round(FR[nm]["lowest_z"], 3), **T.info(),
                           swing_pos=T.sweep(a, b - a, 45), swing_neg=T.sweep(a, a - b, 45))
    print("CHAIN", nm, R["chains"][nm])

json.dump(R, open(OUT, "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
print("RIG written", OUT)
