"""Pirate ship's wheel (helm) for the stylized airship: builds rig/props/Helm.blend from code.

Run (headless, re-runnable; it rebuilds the whole file from scratch and overwrites Helm.blend,
so hand edits in Helm.blend are lost on a re-run):
  blender -b --factory-startup --python rig/scripts/model_helm.py

Objects (metres, +Z up, +X = bow):
  Helm_Pedestal  origin = centre of the base plate on the deck (z 0 = deck surface), static.
                 Two wooden stanchions (fore/aft) on iron shoes, iron pillow-block bearings,
                 a rope drum (barrel) with the tiller rope coiled on it and running down
                 through two deck fairleads, the axle with a brass end cap, lateral knees,
                 a stretcher and an iron base plate with bolts.
  Helm_Wheel     origin = on the axle at the wheel centre; axle along local +X (helmsman at -X
                 looking toward +X), so spinning about local X turns the wheel. Rim (iron bands
                 over the 8 felloe joints), 8 turned spokes through the rim ending in turned
                 handle pegs, hub with iron flanges, a brass dome cap and a ring of 8 bolts.

v2 (2026-11-22 review fixes): chunkier rim (0.18 radial x 0.15 deep) and spokes/handles (radii x1.45),
hub flange r 0.33, wider iron bands (0.11 m of arc), an iron ferrule on the king spoke's handle neck
(shape marker that survives the monochrome bake; the brass knob stays), base plate skirt down to
z -0.05 (deck slopes 1.9 deg at x -6.5), thicker rope (r 0.03, 2.5 turns, 8 sides), drum end discs
split into a visible full-density rim annulus + a hidden centre. v1 backup: rig/props/_backup_helm_v1/.

v3 (round 2, 2026-11-24, "ship wheel smaller to the size of the character"): wheel 1.40 m across the handle
tips (was 3.1 m), axle 1.00 m above the deck (was 1.65), wheel centre 0.35 m aft of the pedestal origin
(was 0.63), rim 0.44-0.54 x 0.10 deep, pedestal scaled by 1.00 / 1.65. v2 files:
rig/_backup_round1_20261124/props/.

Shading: every face smooth; sharp edges only on hard breaks (flanges, box corners, cap rims).
UVs: one map "UVMap" per object; seams = cap rims + one hidden meridian / longitudinal cut per
tube (+ cross cuts on the rim under the iron bands); angle-based unwrap, average island scale,
pack. Face attribute "part_kind" (0 wood, 1 iron, 2 brass, 3 rope) and the preview colour
attribute "PartColor" come from it. One plain material M_Helm (no nodes) on both objects.
"""
import bpy, bmesh, math, json, sys
import numpy as np
from mathutils import Vector as V

OUT_BLEND = "/mnt/new_partition/BlenderProjects/StylizedAirship/rig/props/Helm.blend"

# ---------------------------------------------------------------- knobs
# v3 (round 2, 2026-11-24): the wheel is scaled to the player mech (capsule 141.6 cm tall, radius 34 cm): 140 cm across
# the handle tips (v2: 310 cm), hub at chest height (axle 1.00 m above the deck, v2 1.65). The spoke and hub profiles
# below are the v2 ones, scaled by WHEEL_S along the spoke; the rim and the spoke radii are set on their own so the
# small wheel stays a little chunkier than a pure scale (it must still read from the 65 m game camera). The pedestal is
# the v2 pedestal scaled uniformly by PED_S (it is modelled in v2 units below).
AXLE_H = 1.00          # axle height above the deck; the handle tips clear the deck by AXLE_H - TIP_R
TIP_R = 0.70           # radius of the handle-peg tips (wheel 1.40 m across)
WHEEL_DESIGN_TIP_R = 1.55              # tip radius the spoke / hub profiles were drawn for (v2)
WHEEL_S = TIP_R / WHEEL_DESIGN_TIP_R   # 0.452: spoke lengths, hub, bolts, ferrule
PED_DESIGN_AXLE_H = 1.65               # axle height the pedestal was drawn for (v2)
PED_S = AXLE_H / PED_DESIGN_AXLE_H     # 0.606: the whole pedestal
RIM_RO, RIM_RI = 0.54, 0.44   # rim outer / inner radius (0.10 radial; a pure scale of v2 would be 0.53 / 0.45)
RIM_HB = 0.05          # rim half thickness along the axle (0.10)
RIM_CH = 0.015         # rim edge chamfer
SPOKE_SCALE = 0.70     # radius scale of the v1 spoke + handle profile (v1 = 1.0, v2 1.45 for the 3.1 m wheel)
HUB_FLANGE_R = 0.15    # front hub flange radius (v2 0.33)
BOLT_RING_R = 0.11     # hub bolt circle radius (v2 0.25)
BOLT_S = 0.6           # hub bolt heads: v2 size x this (a pure WHEEL_S scale would make them 2 cm specks)
BAND_ARC = 0.06        # iron band length along the rim (v2 0.11)
BAND_GAP = 0.006       # iron band thickness over the rim
FERRULE = (1.36 * WHEEL_S, 1.41 * WHEEL_S, 0.012 * WHEEL_S)  # king-spoke iron ferrule: t from, t to, radius over the neck
PLATE_BOTTOM = -0.05   # base plate skirt bottom (z 0 = deck): hides the 1.9 deg deck slope (+-1.1 cm under the v3 plate)
RIM_STEPS = 7          # rim rings per felloe (8 felloes): 56 round, no visible kinks at ~2 m
SPOKE_SEGS = 10
HUB_SEGS = 24
WHEEL_X = -0.35        # wheel centre (x) relative to the pedestal origin (v2 -0.63)
POST_X = 0.30          # fore/aft stanchions at x = +-POST_X (pedestal design units, x PED_S in the model: 0.18)
ROPE = True            # tiller rope coiled on the drum
ROPE_TURNS = 2.5       # n + 0.5 so the two ends leave on opposite sides
ROPE_R = 0.03          # rope radius (pedestal design units)
ROPE_STEPS = 20        # rings per turn
ROPE_SEGS = 8
UNWRAP = "MINIMUM_STRETCH"   # SLIM: less area stretch on the bulging turned parts than ANGLE_BASED

WOOD, IRON, BRASS, ROPEK = 0, 1, 2, 3
KIND_COL = {WOOD: (0.60, 0.42, 0.27), IRON: (0.33, 0.35, 0.38), BRASS: (0.80, 0.62, 0.26),
            ROPEK: (0.78, 0.70, 0.50)}
TAU = 2 * math.pi


# ---------------------------------------------------------------- mesh builder
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.kind = self.bm.faces.layers.int.new("part_kind")
        self.hid = self.bm.faces.layers.int.new("uv_hidden")  # faces nobody sees: tiny UV islands

    def face(self, vs, kind, hidden=False):
        f = self.bm.faces.new(vs)
        f[self.kind] = kind
        f[self.hid] = int(hidden)
        f.smooth = True
        return f

    def edge(self, a, b, sharp=False, seam=False):
        e = self.bm.edges.get((a, b))
        if e is None:
            return
        if sharp:
            e.smooth = False
        if seam:
            e.seam = True

    # surface of revolution. prof: (t, r, hard[, kind]) from the start end to the finish end
    # along the outside; r == 0 is a pole. hard: True = sharp ring + seam, "seam" = UV cut only.
    # kind of point i applies to the band i -> i+1; hidden = band indices nobody sees.
    def lathe(self, prof, segs, origin, axis, ref, kind, phase=0.0, facet=False, hidden=()):
        a = V(axis).normalized()
        u = (V(ref) - a * a.dot(V(ref))).normalized()
        w = a.cross(u)
        o = V(origin)
        rows = []
        for p in prof:
            t, r = p[0], p[1]
            c = o + a * t
            if r <= 1e-9:
                rows.append(self.bm.verts.new(c))
            else:
                rows.append([self.bm.verts.new(c + (u * math.cos(phase + TAU * j / segs) +
                                                     w * math.sin(phase + TAU * j / segs)) * r)
                             for j in range(segs)])
        ring = lambda R: isinstance(R, list)
        for i in range(len(prof) - 1):
            A, B = rows[i], rows[i + 1]
            k = prof[i][3] if len(prof[i]) > 3 else kind
            h = i in hidden
            for j in range(segs):
                j1 = (j + 1) % segs
                if ring(A) and ring(B):
                    self.face((A[j], A[j1], B[j1], B[j]), k, h)
                elif ring(A):
                    self.face((A[j], A[j1], B), k, h)
                else:
                    self.face((A, B[j1], B[j]), k, h)
        for i, p in enumerate(prof):
            if p[2] and ring(rows[i]):
                R = rows[i]
                for j in range(segs):
                    self.edge(R[j], R[(j + 1) % segs], sharp=p[2] is True, seam=True)
        if facet:
            for i in range(len(prof) - 1):
                A, B = rows[i], rows[i + 1]
                if ring(A) and ring(B):
                    for j in range(segs):
                        self.edge(A[j], B[j], sharp=True)
        # meridian seam (j = 0) through every region between breaks that is not a disc
        brk = [i for i, p in enumerate(prof) if p[2] or p[1] <= 1e-9 or i in (0, len(prof) - 1)]
        for b0, b1 in zip(brk, brk[1:]):
            pole0, pole1 = not ring(rows[b0]), not ring(rows[b1])
            if pole0 != pole1:
                continue  # disc: no cut needed
            for i in range(b0, b1):
                A, B = rows[i], rows[i + 1]
                a0 = A[0] if ring(A) else A
                b0v = B[0] if ring(B) else B
                self.edge(a0, b0v, seam=True)
        return rows

    # tube through rows of verts (each row one section, same count, sections CCW so that the
    # quads (k,i)(k,i+1)(k+1,i+1)(k+1,i) face out). hard[i]: longitudinal edge at section
    # point i is sharp. ring_hard[k]: ring k edges sharp. caps close open ends.
    def tube(self, rows, kind, hard=None, closed=False, caps=True, seam_idx=0,
             ring_hard=None, cross_seams=(), hide_caps=(False, False)):
        ns = len(rows[0])
        nk = len(rows)
        kk = nk if closed else nk - 1
        for k in range(kk):
            A, B = rows[k], rows[(k + 1) % nk]
            for i in range(ns):
                i1 = (i + 1) % ns
                self.face((A[i], A[i1], B[i1], B[i]), kind)
        for k in range(kk):
            A, B = rows[k], rows[(k + 1) % nk]
            for i in range(ns):
                if hard and hard[i]:
                    self.edge(A[i], B[i], sharp=True)
                if i == seam_idx:
                    self.edge(A[i], B[i], seam=True)
        for k in range(nk):
            hk = ring_hard[k] if ring_hard else False
            sk = k in cross_seams
            if hk or sk:
                for i in range(ns):
                    self.edge(rows[k][i], rows[k][(i + 1) % ns], sharp=hk, seam=sk)
        if caps and not closed:
            for R, rev, hc in ((rows[0], True, hide_caps[0]), (rows[-1], False, hide_caps[1])):
                vs = list(reversed(R)) if rev else list(R)
                f = self.face(vs, kind, hc)
                for i in range(ns):
                    self.edge(R[i], R[(i + 1) % ns], sharp=True, seam=True)
                if len(vs) > 4:
                    bmesh.ops.triangulate(self.bm, faces=[f], quad_method="BEAUTY", ngon_method="BEAUTY")

    def row(self, section, P, N, B, sa=1.0, sb=1.0):
        return [self.bm.verts.new(P + N * (s[0] * sa) + B * (s[1] * sb)) for s in section]

    def finish(self, name, mat):
        bm = self.bm
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        # preview colour attribute from part_kind
        kinds = np.zeros(len(me.polygons), dtype=np.int32)
        me.attributes["part_kind"].data.foreach_get("value", kinds)
        ca = me.color_attributes.new("PartColor", "BYTE_COLOR", "CORNER")
        loop_tot = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("loop_total", loop_tot)
        per_loop = np.repeat(kinds, loop_tot)
        lut = np.array([KIND_COL[k] + (1.0,) for k in sorted(KIND_COL)], dtype=np.float32)
        ca.data.foreach_set("color", lut[per_loop].ravel())
        me.color_attributes.active_color = ca
        me.color_attributes.render_color_index = me.color_attributes.active_color_index
        return me


def chamfer_rect(ha, hb, c, hard=True):
    """8-point chamfered rectangle, CCW in (a, b)."""
    pts = [(ha, -hb + c), (ha, hb - c), (ha - c, hb), (-ha + c, hb),
           (-ha, hb - c), (-ha, -hb + c), (-ha + c, -hb), (ha - c, -hb)]
    return [(x, y, hard) for x, y in pts]


def circle(r, n, phase=0.0):
    return [(r * math.cos(phase + TAU * i / n), r * math.sin(phase + TAU * i / n), False) for i in range(n)]


def plane_cut_rows(b, section, p0, p1, N, plane0, plane1):
    """Two rows of a straight prism from p0 toward p1, ends cut by planes (point, normal)."""
    d = (V(p1) - V(p0))
    T = d.normalized()
    N = (V(N) - T * T.dot(V(N))).normalized()
    B = T.cross(N)
    rows = []
    for (pp, pn) in (plane0, plane1):
        pp, pn = V(pp), V(pn)
        r = []
        for s in section:
            q0 = V(p0) + N * s[0] + B * s[1]
            tt = (pp - q0).dot(pn) / T.dot(pn)
            r.append(b.bm.verts.new(q0 + T * tt))
        rows.append(r)
    return rows


def rmf_frames(pts):
    """Rotation-minimising frames (double reflection) along a polyline: [(P, N, B)]."""
    P = [V(p) for p in pts]
    n = len(P)
    T = []
    for i in range(n):
        d = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)])
        T.append(d.normalized())
    t0 = T[0]
    ref = V((1, 0, 0)) if abs(t0.x) < 0.9 else V((0, 1, 0))
    r = (ref - t0 * t0.dot(ref)).normalized()
    out = [(P[0], r, t0.cross(r))]
    for i in range(n - 1):
        v1 = P[i + 1] - P[i]
        c1 = v1.dot(v1)
        rL = r - v1 * (2 / c1 * v1.dot(r))
        tL = T[i] - v1 * (2 / c1 * v1.dot(T[i]))
        v2 = T[i + 1] - tL
        c2 = v2.dot(v2)
        r = rL - v2 * (2 / c2 * v2.dot(rL)) if c2 > 1e-12 else rL
        r = (r - T[i + 1] * T[i + 1].dot(r)).normalized()
        out.append((P[i + 1], r, T[i + 1].cross(r)))
    # N x B must equal T for outward winding with CCW sections: B = T x N gives N x B = T
    return out


# ---------------------------------------------------------------- wheel (local space)
def build_wheel(mat):
    b = Builder()
    X = V((1, 0, 0))

    def radial(phi):
        return V((0, math.sin(phi), math.cos(phi)))

    # spokes: chunky turned shaft from inside the hub (hidden pole), collar at the hub, long taper,
    # bead, through the rim (thinner than the rim), then the handle peg: bulb, neck, round knob.
    # "seam" rings cut the hidden inner cap and the knob tip off as discs (no pole pinching).
    # bead sits 0.125 inside the rim's inner face as in v1 (it moves in with the deeper rim)
    # (v2 profile in design units: t for tips at WHEEL_DESIGN_TIP_R, scaled by WHEEL_S along the spoke below)
    bd = RIM_RI / WHEEL_S - 0.125
    sp = [(0.17, 0.0, False), (0.18, 0.046, "seam"), (0.325, 0.066, False),
          (0.37, 0.048, False), (bd - 0.045, 0.040, False), (bd, 0.060, False), (bd + 0.045, 0.040, False),
          (1.16, 0.042, False), (1.24, 0.064, False), (1.32, 0.066, False), (1.385, 0.042, False),
          (1.44, 0.060, False), (1.505, 0.057, "seam"), (WHEEL_DESIGN_TIP_R - 0.012, 0.034, False),
          (WHEEL_DESIGN_TIP_R, 0.0, False)]
    sp = [(p[0] * WHEEL_S, p[1] * SPOKE_SCALE) + tuple(p[2:]) for p in sp]

    def r_at(t):
        for p, q in zip(sp, sp[1:]):
            if p[0] <= t <= q[0]:
                return p[1] + (q[1] - p[1]) * (t - p[0]) / (q[0] - p[0])

    # king spoke (k 0, top at rest): an iron ferrule on the handle neck marks "rudder amidships" by
    # shape (bakes as a black band; colour does not survive the monochrome ink bake), brass knob kept
    f0, f1, fo = FERRULE
    rf = max(r_at(f0), r_at(f1)) + fo
    king = ([p for p in sp if p[0] < f0] +
            [(f0, r_at(f0), True, IRON), (f0, rf, True, IRON), (f1, rf, True, IRON), (f1, r_at(f1), True, BRASS)] +
            [(p[0], p[1], p[2], BRASS) for p in sp if p[0] > f1])
    for k in range(8):
        phi = k * TAU / 8
        prof = king if k == 0 else sp
        b.lathe(prof, SPOKE_SEGS, (0, 0, 0), radial(phi), X, WOOD, hidden={0})  # seam faces +X (back)

    # rim: one closed loop, chamfered section, 8 felloes; cross seams at the joints (under bands)
    rc = (RIM_RO + RIM_RI) / 2
    ha = (RIM_RO - RIM_RI) / 2
    sec = chamfer_rect(ha, RIM_HB, RIM_CH)
    rows = []
    n = 8 * RIM_STEPS
    for i in range(n):
        phi = math.radians(22.5) + TAU * i / n
        rows.append(b.row(sec, radial(phi) * rc, radial(phi), X))
    b.tube(rows, WOOD, hard=[s[2] for s in sec], closed=True, seam_idx=3,
           cross_seams=set(range(0, n, RIM_STEPS)))

    # iron bands over the 8 felloe joints
    g = BAND_GAP
    secb = chamfer_rect(ha + g, RIM_HB + g, RIM_CH + 0.004)
    dphi = BAND_ARC / 2 / rc
    for k in range(8):
        pj = math.radians(22.5) + k * TAU / 8
        rows = [b.row(secb, radial(p) * rc, radial(p), X) for p in (pj - dphi, pj + dphi)]
        b.tube(rows, IRON, hard=[True] * 8, seam_idx=3)

    # hub: brass dome cap, iron front flange, wooden drum, iron back flange (t along +X)
    hub = [(-0.24, 0.0, False, BRASS), (-0.232, 0.062, False, BRASS), (-0.21, 0.115, "seam", BRASS),
           (-0.172, 0.150, False, BRASS), (-0.125, 0.165, True, IRON), (-0.125, HUB_FLANGE_R / WHEEL_S, True, IRON),
           (-0.06, HUB_FLANGE_R / WHEEL_S, True, IRON), (-0.06, 0.225, True, WOOD), (0.085, 0.225, True, IRON),
           (0.085, 0.26, True, IRON), (0.13, 0.26, True, IRON), (0.13, 0.0, False, IRON)]
    hub = [(p[0] * WHEEL_S, p[1] * WHEEL_S) + tuple(p[2:]) for p in hub]   # v2 design units -> metres
    b.lathe(hub, HUB_SEGS, (0, 0, 0), X, (0, 0, 1), IRON)  # meridian seam at +Z, behind spoke 0

    # bolt ring on the front flange (hex heads, between the spokes)
    for k in range(8):
        phi = math.radians(22.5) + k * TAU / 8
        c = V(((-0.125 + 0.004) * WHEEL_S, 0, 0)) + radial(phi) * BOLT_RING_R
        br, bh = 0.024 * BOLT_S, 0.026 * BOLT_S
        b.lathe([(0, 0, False), (0, br, True), (bh, br, True), (bh, 0, False)],
                6, c, -X, radial(phi), IRON, facet=True, hidden={0})
    return b.finish("Helm_Wheel", mat)


# ---------------------------------------------------------------- pedestal (world = local)
def build_pedestal(mat):
    """Modelled in v2 design units (axle at PED_DESIGN_AXLE_H), then scaled by PED_S about the origin."""
    b = Builder()
    X, Y, Z = V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1))
    AXLE_H = PED_DESIGN_AXLE_H                  # design units in here (shadows the knob on purpose)
    PLATE_BOTTOM_D = PLATE_BOTTOM / PED_S
    PT = 0.06  # base plate thickness
    HB = 0.10  # half length (x) of the pillow-block bearings

    # base plate: top at PT, the sides run down to PLATE_BOTTOM (a skirt below the deck line z 0),
    # so the plate sits flush on the sloped deck (1.9 deg at x -6.5: +-2.2 cm at the plate corners)
    sec = chamfer_rect(0.56, 0.52, 0.12)
    b.tube([b.row(sec, V((0, 0, PLATE_BOTTOM_D)), X, Y), b.row(sec, V((0, 0, PT)), X, Y)], IRON,
           hard=[True] * 8, seam_idx=0, hide_caps=(True, False))
    # plate bolts
    for (x, y) in ((0.47, 0.43), (-0.47, 0.43), (0.47, -0.43), (-0.47, -0.43),
                   (0, 0.43), (0, -0.43), (0.50, 0), (-0.50, 0)):
        b.lathe([(0, 0, False), (0, 0.026, True), (0.024, 0.026, True), (0.024, 0, False)],
                6, (x, y, PT - 0.004), Z, X, IRON, facet=True, hidden={0})

    hx0, hy0, hx1, hy1 = 0.12, 0.15, 0.095, 0.12  # stanchion half sizes, bottom / top
    z0, z1 = 0.16, 1.50
    hxz = lambda z: hx0 + (hx1 - hx0) * (z - z0) / (z1 - z0)
    hyz = lambda z: hy0 + (hy1 - hy0) * (z - z0) / (z1 - z0)
    for xc in (-POST_X, POST_X):
        C = V((xc, 0, 0))
        # iron shoe (frustum)
        b.tube([b.row(chamfer_rect(0.18, 0.21, 0.045), C + Z * (PT - 0.005), X, Y),
                b.row(chamfer_rect(0.15, 0.18, 0.04), C + Z * 0.19, X, Y)], IRON, hard=[True] * 8,
               hide_caps=(True, False))
        # wooden stanchion, tapered
        b.tube([b.row(chamfer_rect(hx0, hy0, 0.03), C + Z * z0, X, Y),
                b.row(chamfer_rect(hx1, hy1, 0.025), C + Z * z1, X, Y)], WOOD, hard=[True] * 8,
               hide_caps=(True, True))
        # iron hoops round the stanchion
        for zb in (0.98, 1.30):
            za, zc = zb - 0.032, zb + 0.032
            b.tube([b.row(chamfer_rect(hxz(za) + 0.013, hyz(za) + 0.013, 0.033), C + Z * za, X, Y),
                    b.row(chamfer_rect(hxz(zc) + 0.013, hyz(zc) + 0.013, 0.033), C + Z * zc, X, Y)],
                   IRON, hard=[True] * 8)
        # pillow-block bearing: flat sides, round top, the axle through it
        R = 0.165
        tomb = [(R, -0.18, True)] + [(R * math.cos(math.pi * i / 8), R * math.sin(math.pi * i / 8), False)
                                     for i in range(9)] + [(-R, -0.18, True)]
        rows = [b.row(tomb, V((x, 0, AXLE_H)), Y, Z) for x in (xc - HB, xc + HB)]
        b.tube(rows, IRON, hard=[s[2] for s in tomb], seam_idx=10)
        # two cap bolts on the outer face of each block
        sgn = 1 if xc > 0 else -1
        for yb in (-0.105, 0.105):
            b.lathe([(0, 0, False), (0, 0.022, True), (0.02, 0.022, True), (0.02, 0, False)],
                    6, (xc + sgn * (HB - 0.004), yb, AXLE_H - 0.095), X * sgn, Z, IRON, facet=True,
                    hidden={0})
        # lateral knees from the stanchion sides down to the plate
        ks = chamfer_rect(0.05, 0.045, 0.014)
        for s in (-1, 1):
            top = V((xc, s * 0.10, 0.80))
            foot = V((xc, s * 0.44, PT))
            rows = plane_cut_rows(b, ks, top, foot, X, (V((xc, s * 0.06, 0)), V((0, s, 0))),
                                  (V((0, 0, PT - 0.02)), V((0, 0, 1))))
            b.tube(rows, WOOD, hard=[True] * 8, hide_caps=(True, True))
            # iron foot plate under the knee
            fc = V((xc, s * 0.43, 0))
            b.tube([b.row(chamfer_rect(0.075, 0.075, 0.02), fc + Z * (PT - 0.005), X, Y),
                    b.row(chamfer_rect(0.065, 0.065, 0.018), fc + Z * (PT + 0.03), X, Y)], IRON,
                   hard=[True] * 8, hide_caps=(True, False))

    # stretcher between the stanchions
    sec = chamfer_rect(0.055, 0.065, 0.016)
    b.tube([b.row(sec, V((x, 0, 0.55)), Y, Z) for x in (-POST_X, POST_X)], WOOD, hard=[True] * 8,
           hide_caps=(True, True))

    # rope drum (barrel) between the bearings: iron end hoops, wooden body
    xb = POST_X - HB - 0.01
    # end discs: the centre (r < 0.15) is hidden behind the bearing block (half width 0.165), the
    # outer annulus (r 0.15..0.19) shows around it and gets full texel density
    br = [(-xb, 0.0, False, IRON), (-xb, 0.15, "seam", IRON), (-xb, 0.19, True, IRON),
          (-xb + 0.04, 0.19, True, IRON), (-xb + 0.04, 0.17, True, WOOD), (xb - 0.04, 0.17, True, IRON),
          (xb - 0.04, 0.19, True, IRON), (xb, 0.19, True, IRON), (xb, 0.15, "seam", IRON), (xb, 0.0, False, IRON)]
    b.lathe(br, 20, (0, 0, AXLE_H), X, Z, WOOD, phase=math.pi, hidden={0, 8})  # seam underneath

    # axle: inside the wheel hub (starts 0.045 m aft of the wheel centre, the hub's back face is at +0.059), collar at
    # the aft bearing, through both blocks, brass end cap
    xa = (WHEEL_X + 0.10 * WHEEL_S) / PED_S
    bf = POST_X + HB
    ax = [(xa, 0.0, False), (xa, 0.055, True), (-bf - 0.025, 0.055, True), (-bf - 0.025, 0.085, True),
          (-bf, 0.085, True), (-bf, 0.055, True), (bf, 0.055, True), (bf, 0.085, True),
          (bf + 0.035, 0.085, True, BRASS), (bf + 0.035, 0.065, True, BRASS), (bf + 0.06, 0.055, False, BRASS),
          (bf + 0.075, 0.03, False, BRASS), (bf + 0.08, 0.0, False, BRASS)]
    b.lathe(ax, 12, (0, 0, AXLE_H), X, Z, IRON, phase=math.pi, hidden={0, 5})

    if ROPE:
        rope_r = ROPE_R
        rr = 0.17 + rope_r - 0.001   # coil centre-line radius on the drum
        span = 0.16         # fairleads stay clear of the stanchion shoes
        n = int(round(ROPE_TURNS * ROPE_STEPS))
        th0 = -math.pi / 2
        th1 = th0 + TAU * ROPE_TURNS
        x0 = -span / 2
        # end 1 comes up from the deck fairlead on the -Y side, coils, end 2 goes down on +Y
        hel = []
        for i in range(n + 1):
            th = th0 + (th1 - th0) * i / n
            hel.append((x0 + span * i / n, rr * math.sin(th), AXLE_H + rr * math.cos(th)))
        zm = (PT + AXLE_H) / 2
        pts = [(hel[0][0], hel[0][1], PT - 0.01), (hel[0][0], hel[0][1], zm)] + hel + \
              [(hel[-1][0], hel[-1][1], zm), (hel[-1][0], hel[-1][1], PT - 0.01)]
        frames = rmf_frames(pts)
        sec = circle(rope_r, ROPE_SEGS)
        rows = [b.row(sec, P, N, B) for (P, N, B) in frames]
        cuts = {1, 2, n + 2, n + 3} | set(range(2, n + 2, max(1, ROPE_STEPS // 2)))
        b.tube(rows, ROPEK, hard=None, seam_idx=0, cross_seams=cuts, hide_caps=(True, True))
        # fairleads where the rope goes into the deck
        for (x, y) in ((hel[0][0], hel[0][1]), (hel[-1][0], hel[-1][1])):
            C = V((x, y, 0))
            b.tube([b.row(chamfer_rect(0.05, 0.058, 0.015), C + Z * (PT - 0.005), X, Y),
                    b.row(chamfer_rect(0.042, 0.047, 0.012), C + Z * (PT + 0.07), X, Y)], IRON,
                   hard=[True] * 8, hide_caps=(True, False))
    bmesh.ops.scale(b.bm, vec=V((PED_S, PED_S, PED_S)), verts=b.bm.verts)
    return b.finish("Helm_Pedestal", mat)


# ---------------------------------------------------------------- UVs + checks
HIDDEN_UV_SCALE = 0.15  # faces nobody sees (undersides, ends buried in other parts) get tiny islands


def shrink_hidden_islands(ob):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv["UVMap"]
    hl = bm.faces.layers.int.get("uv_hidden")
    seen = set()
    for f in bm.faces:
        if not f[hl] or f.index in seen:
            continue
        isl, st = [], [f]
        seen.add(f.index)
        while st:
            g = st.pop()
            isl.append(g)
            for e in g.edges:
                if e.seam:
                    continue
                for lf in e.link_faces:
                    if lf[hl] and lf.index not in seen:
                        seen.add(lf.index)
                        st.append(lf)
        loops = [l for g in isl for l in g.loops]
        c = sum((l[uvl].uv for l in loops), V((0, 0))) / len(loops)
        for l in loops:
            l[uvl].uv = c + (l[uvl].uv - c) * HIDDEN_UV_SCALE
    bm.to_mesh(me)
    bm.free()


# packer settings tried in turn; the one that leaves the islands biggest (most UV area) wins
PACK_TRIES = [dict(rotate=True, rotate_method="ANY", shape_method="CONCAVE"),
              dict(rotate=True, rotate_method="CARDINAL", shape_method="CONCAVE"),
              dict(rotate=True, rotate_method="ANY", shape_method="CONVEX"),
              dict(rotate=True, rotate_method="AXIS_ALIGNED", shape_method="AABB")]


def best_pack(ob):
    """Pack with each PACK_TRIES setting from the same unpacked UVs and keep the biggest result.
    UV data is re-fetched after every mode switch (holding it across a toggle can crash Blender)."""
    me = ob.data
    me.calc_loop_triangles()
    tl = np.zeros(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("loops", tl)
    base = np.zeros(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers["UVMap"].data.foreach_get("uv", base)
    best = None
    for cfg in PACK_TRIES:
        ob.data.uv_layers["UVMap"].data.foreach_set("uv", base)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.uv.pack_islands(margin=0.004, **cfg)
        except TypeError as e:
            print("pack setting skipped", cfg, e)
            bpy.ops.object.mode_set(mode="OBJECT")
            continue
        bpy.ops.object.mode_set(mode="OBJECT")
        uv = np.zeros(len(ob.data.loops) * 2, dtype=np.float32)
        ob.data.uv_layers["UVMap"].data.foreach_get("uv", uv)
        t = uv.reshape(-1, 2)[tl].reshape(-1, 3, 2).astype(np.float64)
        area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1]) -
                            (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1])).sum()
        print(f"PACK {ob.name} {cfg} uv_area {area:.4f}")
        if best is None or area > best[0]:
            best = (area, uv, cfg)
    ob.data.uv_layers["UVMap"].data.foreach_set("uv", best[1])
    print(f"PACK {ob.name} best {best[2]} uv_area {best[0]:.4f}")


def unwrap(ob):
    vl = bpy.context.view_layer
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    vl.objects.active = ob
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    ob.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if UNWRAP == "MINIMUM_STRETCH":
        bpy.ops.uv.unwrap(method="MINIMUM_STRETCH", fill_holes=True, correct_aspect=True, margin=0.001,
                          iterations=20)
    else:
        bpy.ops.uv.unwrap(method=UNWRAP, fill_holes=True, correct_aspect=True, margin=0.001)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    shrink_hidden_islands(ob)
    best_pack(ob)
    hid = np.zeros(len(ob.data.polygons), dtype=np.int32)
    ob.data.attributes["uv_hidden"].data.foreach_get("value", hid)
    ob.data.attributes.remove(ob.data.attributes["uv_hidden"])
    ob.select_set(False)
    return hid.astype(bool)


def uv_report(me, hidden, res=1024):
    """Overlap over all faces; stretch only over the faces people see."""
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tp = np.zeros(nt, dtype=np.int32)
    me.loop_triangles.foreach_get("polygon_index", tp)
    vis = ~hidden[tp]
    tl = np.zeros(nt * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("loops", tl)
    tv = np.zeros(nt * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tv)
    uv = np.zeros(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers["UVMap"].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[tl].reshape(nt, 3, 2).astype(np.float64)
    co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    P = co.reshape(-1, 3)[tv].reshape(nt, 3, 3).astype(np.float64)
    # overlap: rasterise every triangle (strict interior) and count pixels hit twice
    cnt = np.zeros((res, res), dtype=np.int16)
    for t in range(nt):
        a, b_, c = uv[t] * res
        lo = np.floor(np.minimum(np.minimum(a, b_), c)).astype(int)
        hi = np.ceil(np.maximum(np.maximum(a, b_), c)).astype(int)
        lo = np.clip(lo, 0, res - 1); hi = np.clip(hi, 0, res)
        if hi[0] <= lo[0] or hi[1] <= lo[1]:
            continue
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
        d = (b_[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b_[1] - a[1])
        if abs(d) < 1e-12:
            continue
        w1 = ((b_[0] - xs) * (c[1] - ys) - (c[0] - xs) * (b_[1] - ys)) / d
        w2 = ((c[0] - xs) * (a[1] - ys) - (a[0] - xs) * (c[1] - ys)) / d
        w3 = 1 - w1 - w2
        e = 1e-3
        inside = (w1 > e) & (w2 > e) & (w3 > e)
        cnt[lo[1]:hi[1], lo[0]:hi[0]] += inside.astype(np.int16)
    overlap_px = int((cnt > 1).sum())
    coverage = float((cnt > 0).mean())
    # stretch: area ratio spread and conformal distortion (sigma1/sigma2) per triangle
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    a3 = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    f1, f2 = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
    a2 = 0.5 * np.abs(f1[:, 0] * f2[:, 1] - f1[:, 1] * f2[:, 0])
    ok = (a3 > 1e-10) & vis
    ratio = a2[ok] / a3[ok]
    med = np.median(ratio)
    # Jacobian singular values in a local 2D frame of the 3D triangle
    ex = e1[ok] / np.linalg.norm(e1[ok], axis=1)[:, None]
    nrm = np.cross(e1[ok], e2[ok]); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    ey = np.cross(nrm, ex)
    q1 = np.stack([np.einsum("ij,ij->i", e1[ok], ex), np.zeros(ok.sum())], 1)
    q2 = np.stack([np.einsum("ij,ij->i", e2[ok], ex), np.einsum("ij,ij->i", e2[ok], ey)], 1)
    Q = np.stack([q1, q2], 2)           # 2x2, columns = 3D edges in local frame
    F = np.stack([f1[ok], f2[ok]], 2)   # 2x2, columns = UV edges
    J = F @ np.linalg.inv(Q)
    s = np.linalg.svd(J, compute_uv=False)
    conf = s[:, 0] / np.maximum(s[:, 1], 1e-12)
    w = a3[ok] / a3[ok].sum()
    tex2k = 2048 * math.sqrt(a2[ok].sum() / a3[ok].sum())
    return dict(px_per_m_at_2k=round(tex2k, 1), uv_overlap_px_1k=overlap_px, uv_coverage=round(coverage, 3),
                area_ratio_p5_p95=[round(float(np.percentile(ratio / med, 5)), 3),
                                   round(float(np.percentile(ratio / med, 95)), 3)],
                conformal_mean=round(float((conf * w).sum()), 3),
                conformal_p99=round(float(np.percentile(conf, 99)), 3))


def islands(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    seen, n = set(), 0
    # islands = face groups connected across non-seam edges with matching UVs
    for f in bm.faces:
        if f.index in seen:
            continue
        n += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            for l in g.loops:
                e = l.edge
                if e.seam:
                    continue
                for lf in e.link_faces:
                    if lf.index not in seen:
                        seen.add(lf.index)
                        stack.append(lf)
    bm.free()
    return n


def mesh_checks(ob):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    shells = 0
    seen = set()
    for v in bm.verts:
        if v.index in seen:
            continue
        shells += 1
        st = [v]; seen.add(v.index)
        while st:
            x = st.pop()
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    seen.add(o.index); st.append(o)
    bm.free()
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    mw = ob.matrix_world
    cs = [mw @ V(c) for c in ob.bound_box]
    lo = [min(c[i] for c in cs) for i in range(3)]
    hi = [max(c[i] for c in cs) for i in range(3)]
    return dict(tris=tris, verts=len(me.vertices), faces=len(me.polygons), shells=shells,
                non_manifold_edges=nonman, zero_area_faces=zero, ngons=ngons,
                sharp_edges=int(sum(1 for e in me.edges if e.use_edge_sharp)),
                origin=[round(x, 4) for x in ob.location],
                world_min=[round(x, 3) for x in lo], world_max=[round(x, 3) for x in hi],
                dims=[round(h - l, 3) for l, h in zip(lo, hi)])


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    mat = bpy.data.materials.new("M_Helm")
    mat.diffuse_color = (0.90, 0.86, 0.79, 1.0)   # paper, like the comic texture
    col = bpy.data.collections.new("Helm")
    scene.collection.children.link(col)

    ped = bpy.data.objects.new("Helm_Pedestal", build_pedestal(mat))
    ped.location = (0, 0, 0)
    col.objects.link(ped)
    whl = bpy.data.objects.new("Helm_Wheel", build_wheel(mat))
    whl.location = (WHEEL_X, 0, AXLE_H)
    col.objects.link(whl)
    hidden = {ob.name: unwrap(ob) for ob in (ped, whl)}

    report = {}
    for ob in (whl, ped):
        r = mesh_checks(ob)
        r["uv_islands"] = islands(ob.data)
        r["uv_hidden_faces"] = int(hidden[ob.name].sum())
        r.update(uv_report(ob.data, hidden[ob.name]))
        report[ob.name] = r
    report["axle_height"] = AXLE_H
    report["wheel_centre_world"] = list(whl.location)
    report["deck_clearance_of_tips"] = round(AXLE_H - TIP_R, 3)
    report["wheel_origin_offset_from_pedestal_origin"] = [round(x, 4) for x in (whl.location - ped.location)]
    report["plate_bottom_z"] = PLATE_BOTTOM
    bpy.context.preferences.filepaths.save_version = 0  # no Helm.blend1
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=False)
    print("HELM_REPORT " + json.dumps(report))


main()
