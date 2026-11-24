"""Pirate naval cannon for the airship deck (stylized, chunky, game ready).  v2 (2026-11-22 review fixes), v3 wide bore

Run headless (re-runnable, rebuilds everything from scratch and overwrites the output):
    blender -b --factory-startup --python model_cannon.py
Output: rig/props/Cannon.blend, collection "Cannon":
    Cannon_Carriage   origin = carriage centre on the deck (z=0 = bottom of the wheels)
    Cannon_Barrel     origin = trunnion axis centre (elevation pivot, axis local Y), fires +X
    Cannon_Wheel_FL/FR/BL/BR  origin = axle centre (spin axis local Y); F = +X, L = +Y
    Cannon_Muzzle     EMPTY at the muzzle mouth centre, +X out, parented to Cannon_Barrel
    Cannon_Quoin      wedge + handle peg under the breech, origin = its rear-bottom edge centre on the stool
                      bed top (-0.80, 0, 0.33); the rig slides it back along -X as the barrel elevates
v2 changes (cannon_review.md): quoin split out + stool bed lowered to a 0.31-0.33 plank (elevation up to ~+8.7 deg),
rimbase 24 seg (barrel fillet ring dropped to pay for it), trunnion notch 16 steps, rope rings 16x8 smooth,
bolts 12 seg, wheels 40 seg disc + 16 seg hub, chunkier bolts (5 per cheek side) / ring bolts / linchpins / cap-squares.
Units metres, +Z up. Every mesh: applied rotation/scale, smooth shading with sharp edges marked
by angle, seams = sharp edges + one meridian per turned part, one non-overlapping UV map.
All parts are built in code (bmesh), so a fix is an edit of the numbers below + a re-run.
"""
import bpy, bmesh, math, json, os, sys
import numpy as np
from mathutils import Vector as V

ROOT = "/mnt/new_partition/BlenderProjects/StylizedAirship/rig/"
OUT = ROOT + "props/Cannon.blend"

# ---------------------------------------------------------------- layout (carriage space)
TRUN = V((0.30, 0.0, 0.80))     # trunnion axis centre = barrel pivot, in carriage space
WHEEL_R = 0.22                  # truck radius -> axle height
AXLE_X = (0.50, -0.53)          # front, rear axletree centres
WHEEL_Y = 0.525                 # wheel centre |y|
CHEEK_IN, CHEEK_OUT = 0.325, 0.435   # cheek inner / outer face |y|
CHEEK_Z0 = 0.25                 # cheek bottom
SEG_BARREL, SEG_TRUN, SEG_RIMBASE, SEG_WHEEL, SEG_ARM, SEG_BOLT = 32, 24, 24, 40, 16, 12
SEG_HUB, SEG_RING_MAJOR, SEG_RING_MINOR, NOTCH_K = 16, 16, 8, 16
WHEEL_HW, WHEEL_TYRE_C = 0.05, 0.025   # wheel half width, 45 deg iron tyre chamfer (radial = axial)
HUB_R, HUB_HW = 0.07, 0.075            # wheel hub cylinder radius, half length
BOLT_R, BOLT_H = 0.035, 0.025          # chunky comic bolt heads (v1: 0.022 / 0.016)
CAP_T = 0.03                           # cap-square strap thickness (v1: 0.024)
# stool bed plank (under the breech) and the separate quoin that slides on it
STOOL_X, STOOL_HW, STOOL_Z = (-0.88, -0.30), 0.30, (0.31, 0.33)
QUOIN_ORIGIN = V((-0.80, 0.0, STOOL_Z[1]))   # rear-bottom edge centre of the quoin at rest
QUOIN_HW, QUOIN_SLOPE, QUOIN_NOSE_H = 0.15, 0.60, 0.035   # half width, top slope (rise/run), nose height

# ---------------------------------------------------------------- barrel profile
# (u, r): u = distance from the base-ring rear face along the bore axis, r = radius.
# Traversed so the outer surface runs toward +u, then back into the bore (keeps normals outward).
BARREL_LEN = 2.60               # base-ring rear face -> muzzle face
TRUN_U = 0.40 * BARREL_LEN      # trunnions at 40 % of the length from the breech
# round 2 (2026-11-24): the bore was widened from 0.13 to 0.22 for the 1 m cannonball (Radius 50 cm in Unreal); the lip
# keeps its 0.28 outer radius (6 cm wall at the face, 2-5 mm behind the muzzle swell: never visible, the bore is ink)
BORE_R, BORE_DEPTH = 0.22, 0.40
BARREL_PROFILE = [
    (-0.310, 0.000),  # cascabel knob tip (pole): ball R 0.10, 22.5 deg profile steps
    (-0.302, 0.038),
    (-0.281, 0.071),
    (-0.248, 0.092),
    (-0.210, 0.100),
    (-0.172, 0.092),
    (-0.139, 0.071),
    (-0.120, 0.054),  # cascabel neck
    (-0.104, 0.054),
    (-0.082, 0.130),  # breech dome (v2: the fillet ring at (-0.094, 0.078) was dropped to pay for the rimbases)
    (-0.062, 0.185),
    (-0.038, 0.230),
    (-0.014, 0.262),
    (0.000, 0.272),
    (0.000, 0.315),   # base ring rear face
    (0.075, 0.315),
    (0.075, 0.300),   # first reinforce
    (0.780, 0.290),
    (0.780, 0.312),   # first reinforce ring
    (0.845, 0.312),
    (0.845, 0.283),   # second reinforce (carries the trunnions)
    (1.300, 0.272),
    (1.300, 0.292),   # second reinforce ring
    (1.350, 0.292),
    (1.350, 0.255),   # chase
    (1.600, 0.249),
    (1.600, 0.268),   # chase girdle
    (1.650, 0.268),
    (1.650, 0.247),
    (2.270, 0.222),   # muzzle neck
    (2.270, 0.236),   # neck astragal
    (2.310, 0.236),
    (2.310, 0.224),
    (2.370, 0.228),   # muzzle swell (tulip)
    (2.430, 0.243),
    (2.480, 0.260),
    (2.500, 0.268),
    (2.500, 0.280),   # muzzle lip
    (2.600, 0.280),
    (2.600, BORE_R + 0.03),   # muzzle face (0.16 before round 2)
    (2.585, BORE_R),  # countersink
    (BARREL_LEN - BORE_DEPTH, BORE_R),  # dark bore tube
    (BARREL_LEN - BORE_DEPTH, 0.000),   # bore bottom (pole)
]
BORE_FROM = len(BARREL_PROFILE) - 3   # bands from here on use the bore material

# materials: placeholder colours for previews; the real look is the baked comic ink later
MATS = {
    "M_Cannon_Iron": (0.085, 0.095, 0.115),
    "M_Cannon_Wood": (0.32, 0.17, 0.085),
    "M_Cannon_Bore": (0.012, 0.012, 0.016),
}
IRON, WOOD, BORE = 0, 1, 2   # global material ids, remapped per object

# ================================================================ bmesh helpers
def finish(bm, mat, sharp_deg=40.0, chamfer=0.0, tri_ngons=True, seam_sharp=True, chamfer_min_deg=30.0):
    """Normals out, optional chamfer on convex hard edges (> chamfer_min_deg), ngons -> tris/quads,
    sharp + seam on edges over sharp_deg, smooth faces, material id."""
    if chamfer > 0:
        es = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle_signed(0) > math.radians(chamfer_min_deg)]
        vs = list({v for e in es for v in e.verts})
        bmesh.ops.bevel(bm, geom=vs + es, offset=chamfer, offset_type="OFFSET", segments=1,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
    if tri_ngons:
        ng = [f for f in bm.faces if len(f.verts) > 4]
        if ng:
            res = bmesh.ops.triangulate(bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
            bmesh.ops.join_triangles(bm, faces=res["faces"], angle_face_threshold=math.radians(1.0),
                                     angle_shape_threshold=math.radians(50.0))
    bm.normal_update()
    lim = math.radians(sharp_deg)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > lim:
            e.smooth = False
            e.seam = e.seam or seam_sharp
    for f in bm.faces:
        f.smooth = True
        if mat is not None:
            f.material_index = mat
    return bm


def lathe(prof, axis, origin=(0, 0, 0), e1=(0, 0, -1), segs=32, mats=None, mat=0, sharp_deg=40.0,
          seam_rings=None, meridians=1):
    """Surface of revolution. prof = [(a, r)] along axis; r == 0 -> pole. Right-handed sweep about
    the axis, so a profile whose outer surface runs toward +a gets outward normals.
    The meridian at angle 0 (direction e1) is a UV seam (meridians=2 adds the opposite one).
    seam_rings: profile indices whose rings are seams (default: every sharp edge is a seam)."""
    bm = bmesh.new()
    A = V(axis).normalized()
    E1 = V(e1).normalized()
    E2 = A.cross(E1)
    O = V(origin)
    rings = []
    for a, r in prof:
        if r < 1e-9:
            rings.append([bm.verts.new(O + A * a)])
        else:
            rings.append([bm.verts.new(O + A * a + (E1 * math.cos(2 * math.pi * j / segs)
                                                    + E2 * math.sin(2 * math.pi * j / segs)) * r)
                          for j in range(segs)])
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        m = mats[i] if mats else mat
        for j in range(segs):
            jn = (j + 1) % segs
            if len(r0) == 1:
                f = bm.faces.new((r0[0], r1[jn], r1[j]))
            elif len(r1) == 1:
                f = bm.faces.new((r0[j], r0[jn], r1[0]))
            else:
                f = bm.faces.new((r0[j], r0[jn], r1[jn], r1[j]))
            f.material_index = m
    bm.edges.ensure_lookup_table()
    for jm in range(meridians):
        j = jm * segs // meridians
        for i in range(len(rings) - 1):
            e = bm.edges.get((rings[i][min(j, len(rings[i]) - 1)], rings[i + 1][min(j, len(rings[i + 1]) - 1)]))
            if e:
                e.seam = True
    for i in (seam_rings or []):
        rg = rings[i]
        for j in range(len(rg)):
            e = bm.edges.get((rg[j], rg[(j + 1) % len(rg)]))
            if e:
                e.seam = True
    return finish(bm, None, sharp_deg, seam_sharp=seam_rings is None)


def prism(poly, plane, w0, w1, mat, chamfer=0.0, sharp_deg=35.0, chamfer_min_deg=30.0):
    """Closed prism from a simple 2D polygon. plane 'XZ': (a,b)->(a, w, b); 'XY': (a, b, w);
    'YZ': (w, a, b)."""
    def P(a, b, w):
        return {"XZ": (a, w, b), "XY": (a, b, w), "YZ": (w, a, b)}[plane]
    bm = bmesh.new()
    lo = [bm.verts.new(P(a, b, w0)) for a, b in poly]
    hi = [bm.verts.new(P(a, b, w1)) for a, b in poly]
    bm.faces.new(lo)
    bm.faces.new(hi)
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(bm, mat, sharp_deg, chamfer, chamfer_min_deg=chamfer_min_deg)


def box(x0, x1, y0, y1, z0, z1, mat, chamfer=0.0):
    return prism([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], "XZ", y0, y1, mat, chamfer)


def torus(center, normal, R, r, seg_major=12, seg_minor=6, mat=IRON, e1=None, sharp_deg=50.0):
    bm = bmesh.new()
    N = V(normal).normalized()
    E1 = V(e1).normalized() if e1 else N.orthogonal().normalized()
    E2 = N.cross(E1)
    C = V(center)
    grid = []
    for i in range(seg_major):
        t = 2 * math.pi * i / seg_major
        d = E1 * math.cos(t) + E2 * math.sin(t)
        row = []
        for j in range(seg_minor):
            p = 2 * math.pi * j / seg_minor
            row.append(bm.verts.new(C + d * (R + r * math.cos(p)) + N * (r * math.sin(p))))
        grid.append(row)
    for i in range(seg_major):
        inn = (i + 1) % seg_major
        for j in range(seg_minor):
            jn = (j + 1) % seg_minor
            bm.faces.new((grid[i][j], grid[inn][j], grid[inn][jn], grid[i][jn]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.edges.ensure_lookup_table()
    for j in range(seg_minor):  # one cut around the tube, one along it
        e = bm.edges.get((grid[0][j], grid[0][(j + 1) % seg_minor]))
        if e: e.seam = True
    for i in range(seg_major):
        e = bm.edges.get((grid[i][0], grid[(i + 1) % seg_major][0]))
        if e: e.seam = True
    return finish(bm, mat, sharp_deg)


def bolt(pos, axis, r=BOLT_R, h=BOLT_H, mat=IRON):
    """Round iron bolt head (low frustum) sitting on a face; its base hides in the face."""
    return lathe([(-0.004, r), (h, r * 0.64), (h, 0.0)], axis, pos, segs=SEG_BOLT, mat=mat, sharp_deg=50.0,
                 e1=(0, 0, -1) if abs(V(axis).z) < 0.9 else (1, 0, 0))


def sweep_strap(path_in, path_out, y0, y1, mat, sharp_deg=40.0):
    """Strap from paired inner/outer XZ polylines, extruded across y0..y1 (closed)."""
    bm = bmesh.new()
    rows = []
    for (xi, zi), (xo, zo) in zip(path_in, path_out):
        rows.append([bm.verts.new((xi, y0, zi)), bm.verts.new((xo, y0, zo)),
                     bm.verts.new((xo, y1, zo)), bm.verts.new((xi, y1, zi))])
    for k in range(len(rows) - 1):
        a, b = rows[k], rows[k + 1]
        for s in range(4):
            sn = (s + 1) % 4
            bm.faces.new((a[s], a[sn], b[sn], b[s]))
    bm.faces.new(rows[0])
    bm.faces.new(rows[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(bm, mat, sharp_deg)


# ================================================================ assembly
def make_object(name, parts, mat_names, location, coll):
    """parts: list of finished bmeshes (global material ids). Appends them into one mesh."""
    me = bpy.data.meshes.new(name)
    remap = {g: i for i, g in enumerate(mat_names)}
    big = bmesh.new()
    tmp = bpy.data.meshes.new("_tmp")
    for bm in parts:
        for f in bm.faces:
            f.material_index = remap[f.material_index]
        bm.to_mesh(tmp)
        big.from_mesh(tmp)
        bm.free()
    bpy.data.meshes.remove(tmp)
    big.to_mesh(me)
    big.free()
    names = list(MATS)
    for g in mat_names:
        me.materials.append(bpy.data.materials[names[g]])
    me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    coll.objects.link(ob)
    return ob


def build_barrel():
    prof = [(u - TRUN_U, r) for u, r in BARREL_PROFILE]
    mats = [BORE if i >= BORE_FROM else IRON for i in range(len(prof) - 1)]
    parts = [lathe(prof, (1, 0, 0), segs=SEG_BARREL, mats=mats)]
    # trunnions + rimbases (inner ends open, hidden inside the barrel)
    t_r, t_end = 0.085, CHEEK_OUT + 0.025
    for s in (1, -1):
        ax = (0, s, 0)
        parts.append(lathe([(0.20, t_r), (t_end, t_r), (t_end, 0.0)], ax, segs=SEG_TRUN))
        parts.append(lathe([(0.20, 0.12), (0.30, 0.12), (0.30, 0.08)], ax, segs=SEG_RIMBASE))
    return parts


def cheek_poly():
    xc, zc, rn = TRUN.x, TRUN.z, 0.088   # trunnion notch (bottom half of the trunnion seat)
    pts = [(-0.76, CHEEK_Z0)]
    a0, a1, ah = AXLE_X[1] + 0.11, AXLE_X[0] - 0.11, 0.055   # shallow arch cut between the axletrees
    pts += [(a0 + (a1 - a0) * i / 8, CHEEK_Z0 + ah * math.sin(math.pi * i / 8)) for i in range(9)]
    pts += [(0.83, CHEEK_Z0), (0.83, 0.67), (0.70, zc)]
    # notch, front to back (v2: 16 steps of 11.25 deg, smooth shaded)
    k = NOTCH_K
    for i in range(k + 1):
        a = math.pi * i / k                # 0 -> pi : (xc+rn, zc) down round to (xc-rn, zc)
        pts.append((xc + rn * math.cos(a), zc - rn * math.sin(a)))
    pts += [(0.06, zc), (0.06, 0.68), (-0.24, 0.68), (-0.24, 0.56), (-0.54, 0.56), (-0.54, 0.44),
            (-0.83, 0.44), (-0.83, CHEEK_Z0 + 0.07)]
    return pts


# 5 chunky bolt heads per cheek side (x, z), all clear of the wheel discs in side view
CHEEK_BOLTS = [(-0.765, 0.375), (-0.40, 0.47), (-0.10, 0.60), (0.50, 0.63), (0.765, 0.52)]
RING_EYE = (-0.02, 0.48)        # breeching-rope eye boss centre (x, z) on the cheek outer face
RING_R, RING_r = 0.065, 0.02    # rope ring major / tube radius (v1: 0.052 / 0.012)


def build_carriage():
    P = []
    poly = cheek_poly()
    for s in (1, -1):
        y0, y1 = sorted((s * CHEEK_IN, s * CHEEK_OUT))
        P.append(prism(poly, "XZ", y0, y1, WOOD, chamfer=0.012))
    # axletrees (beam through both cheeks) + iron axle arms + chunky linchpins (30 x 24 mm)
    for ax in AXLE_X:
        P.append(box(ax - 0.10, ax + 0.10, -0.45, 0.45, 0.13, 0.31, WOOD, chamfer=0.012))
        for s in (1, -1):
            P.append(lathe([(0.44, 0.045), (WHEEL_Y + 0.088, 0.045), (WHEEL_Y + 0.10, 0.033),
                            (WHEEL_Y + 0.10, 0.0)], (0, s, 0), (ax, 0, WHEEL_R), segs=SEG_ARM, mat=IRON))
            yp = s * (WHEEL_Y + 0.088)
            P.append(box(ax - 0.015, ax + 0.015, yp - 0.012, yp + 0.012, WHEEL_R - 0.075, WHEEL_R + 0.075, IRON))
    # transom (front cross beam) and the stool bed: a plank on the rear axletree (v2: z 0.31-0.33, was 0.31-0.37)
    P.append(box(0.44, 0.62, -CHEEK_IN - 0.005, CHEEK_IN + 0.005, 0.31, 0.44, WOOD, chamfer=0.012))
    P.append(box(STOOL_X[0], STOOL_X[1], -STOOL_HW, STOOL_HW, STOOL_Z[0], STOOL_Z[1], WOOD, chamfer=0.008))
    # (the quoin is its own object now: build_quoin)
    # cap-squares: iron straps over the trunnions, bolted to the cheek tops
    xc, zc = TRUN.x, TRUN.z
    ri, t = 0.088, CAP_T
    ro = ri + t
    al = math.asin(t / ro)
    k = 12
    pin = [(xc - ro - 0.10, zc)] + [(xc + ri * math.cos(math.pi - math.pi * i / k),
                                     zc + ri * math.sin(math.pi - math.pi * i / k)) for i in range(k + 1)] + [(xc + ro + 0.10, zc)]
    pout = [(xc - ro - 0.10, zc + t)] + [(xc + ro * math.cos(math.pi - al - (math.pi - 2 * al) * i / k),
                                          zc + ro * math.sin(math.pi - al - (math.pi - 2 * al) * i / k)) for i in range(k + 1)] + [(xc + ro + 0.10, zc + t)]
    for s in (1, -1):
        y0, y1 = sorted((s * (CHEEK_IN + 0.008), s * (CHEEK_OUT - 0.008)))
        P.append(sweep_strap(pin, pout, y0, y1, IRON))
        yc = s * (CHEEK_IN + CHEEK_OUT) / 2
        for dx in (-1, 1):
            P.append(bolt((xc + dx * (ro + 0.052), yc, zc + t), (0, 0, 1), r=0.03, h=0.022))
    # bolt heads on the cheek outer faces
    for s in (1, -1):
        for x, z in CHEEK_BOLTS:
            P.append(bolt((x, s * CHEEK_OUT, z), (0, s, 0)))
    for s in (1, -1):   # transom through-bolts, seen from the front
        P.append(bolt((0.62, s * 0.20, 0.375), (1, 0, 0)))
    # breeching-rope ring bolts: eye boss + iron ring hanging flat on the cheek, between the wheels
    ex, ez = RING_EYE
    for s in (1, -1):
        P.append(lathe([(-0.004, 0.032), (0.03, 0.032), (0.04, 0.022), (0.04, 0.0)], (0, s, 0),
                       (ex, s * CHEEK_OUT, ez), segs=SEG_BOLT, mat=IRON, sharp_deg=50.0))
        P.append(torus((ex, s * (CHEEK_OUT + RING_r + 0.002), ez - RING_R), (0, 1, 0), RING_R, RING_r,
                       SEG_RING_MAJOR, SEG_RING_MINOR, IRON, e1=(0, 0, 1), sharp_deg=90.0))
    return P


def quoin_geometry():
    """Quoin wedge outline (XZ, carriage space, rest pose): flat land under the base ring, then a 31 deg
    slope down to a short nose (thin end forward). Its land top meets the base ring bottom at elevation 0."""
    ring_r = max(r for u, r in BARREL_PROFILE if 0.0 <= u <= 0.08)
    ztop = TRUN.z - ring_r - 0.002                      # base ring bottom (minus a hair)
    xr = TRUN.x - TRUN_U                                # base ring rear face x = land front edge
    xb, zb = QUOIN_ORIGIN.x, QUOIN_ORIGIN.z
    xn = xr + (ztop - zb - QUOIN_NOSE_H) / QUOIN_SLOPE  # nose x
    return [(xb, zb), (xn, zb), (xn, zb + QUOIN_NOSE_H), (xr, ztop), (xb, ztop)]


def build_quoin():
    """Built in carriage space, then moved so QUOIN_ORIGIN is the object origin."""
    poly = quoin_geometry()
    xb, zb = QUOIN_ORIGIN.x, QUOIN_ORIGIN.z
    # sharp at 25 deg: the 31 deg land/slope ridge stays a crisp hard edge (not chamfered, not smoothed)
    parts = [prism(poly, "XZ", -QUOIN_HW, QUOIN_HW, WOOD, chamfer=0.012, sharp_deg=25.0, chamfer_min_deg=40.0)]
    # handle peg sticking out of the back face (inner end buried in the wedge)
    a0 = -xb - 0.01
    parts.append(lathe([(a0, 0.035), (a0 + 0.075, 0.035), (a0 + 0.09, 0.024), (a0 + 0.09, 0.0)], (-1, 0, 0),
                       (0, 0, zb + 0.085), segs=16, mat=WOOD))
    for bm in parts:
        bmesh.ops.translate(bm, vec=-QUOIN_ORIGIN, verts=bm.verts)
    return parts


def build_wheel():
    """v2: 40 segment disc (wood face fans + iron 45 deg tyre chamfers and tread) + 16 segment hub cylinder."""
    w, c, R = WHEEL_HW, WHEEL_TYRE_C, WHEEL_R
    prof = [(-w, 0.0), (-w, R - c), (-w + c, R), (w - c, R), (w, R - c), (w, 0.0)]
    mats = [WOOD, IRON, IRON, IRON, WOOD]
    # islands: each face disc (split in halves by the 2 meridians), the iron band (2 halves)
    disc = lathe(prof, (0, 1, 0), segs=SEG_WHEEL, mats=mats, seam_rings=[1, 4], meridians=2)
    hub = lathe([(-HUB_HW, 0.0), (-HUB_HW, HUB_R), (HUB_HW, HUB_R), (HUB_HW, 0.0)], (0, 1, 0), segs=SEG_HUB, mat=WOOD)
    return [disc, hub]


# ================================================================ UVs + checks
def unwrap(ob, margin=0.006):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, correct_aspect=True, margin=0.001)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=margin, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def uv_overlap(me, res=2048):
    """Rasterise every UV triangle; pixels hit by two triangles = overlap."""
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    cnt = np.zeros((res, res), np.uint8)
    oob = 0
    for lt in me.loop_triangles:
        p = np.array([uv[l].uv[:] for l in lt.loops]) * res
        if p.min() < -1e-3 or p.max() > res + 1e-3:
            oob += 1
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, res), min(y1, res)
        if x1 <= x0 or y1 <= y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = p
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / d
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / d
        l3 = 1 - l1 - l2
        inside = (l1 > 1e-6) & (l2 > 1e-6) & (l3 > 1e-6)
        cnt[y0:y1, x0:x1] += inside.astype(np.uint8)
    return int((cnt > 1).sum()), float((cnt > 0).mean()), oob


def report(ob):
    me = ob.data
    me.calc_loop_triangles()
    bm = bmesh.new()
    bm.from_mesh(me)
    areas = [f.calc_area() for f in bm.faces]
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    sharp = sum(1 for e in bm.edges if not e.smooth)
    bm.free()
    ov, cov, oob = uv_overlap(me)
    mw = ob.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return {"tris": len(me.loop_triangles), "faces": len(me.polygons), "ngons": ngons,
            "min_face_area": round(min(areas), 7), "open_edges": nonman, "sharp_edges": sharp,
            "uv_overlap_px@2k": ov, "uv_coverage": round(cov, 3), "uv_out_of_0_1": oob,
            "origin": [round(c, 4) for c in ob.matrix_world.translation],
            "rot": [round(c, 4) for c in ob.rotation_euler], "scale": [round(c, 4) for c in ob.scale],
            "bbox_min": [round(c, 3) for c in lo], "bbox_max": [round(c, 3) for c in hi],
            "materials": [m.name for m in me.materials]}


# ================================================================ main
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    for n, c in MATS.items():
        m = bpy.data.materials.new(n)
        m.diffuse_color = c + (1.0,)
        m.use_nodes = True
        bsdf = next(nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = c + (1.0,)
        bsdf.inputs["Roughness"].default_value = 0.8 if n != "M_Cannon_Iron" else 0.55
        if n == "M_Cannon_Iron":
            bsdf.inputs["Metallic"].default_value = 0.6
    coll = bpy.data.collections.new("Cannon")
    sc.collection.children.link(coll)

    carriage = make_object("Cannon_Carriage", build_carriage(), [WOOD, IRON], (0, 0, 0), coll)
    barrel = make_object("Cannon_Barrel", build_barrel(), [IRON, BORE], TRUN, coll)
    wheels = []
    for tag, x, s in (("FL", AXLE_X[0], 1), ("FR", AXLE_X[0], -1), ("BL", AXLE_X[1], 1), ("BR", AXLE_X[1], -1)):
        wheels.append(make_object("Cannon_Wheel_" + tag, build_wheel(), [WOOD, IRON], (x, s * WHEEL_Y, WHEEL_R), coll))
    quoin = make_object("Cannon_Quoin", build_quoin(), [WOOD], QUOIN_ORIGIN, coll)

    muzzle = bpy.data.objects.new("Cannon_Muzzle", None)
    muzzle.empty_display_type = "ARROWS"
    muzzle.empty_display_size = 0.35
    coll.objects.link(muzzle)
    muzzle.parent = barrel
    muzzle.location = (BARREL_LEN - TRUN_U, 0, 0)   # muzzle mouth centre in barrel space

    obs = [carriage, barrel] + wheels + [quoin]
    for ob in obs:
        unwrap(ob)
    bpy.context.view_layer.update()

    rep = {ob.name: report(ob) for ob in obs}
    mz = muzzle.matrix_world.translation
    rep["Cannon_Muzzle"] = {"type": muzzle.type, "parent": muzzle.parent.name,
                            "world": [round(c, 4) for c in mz], "local": [round(c, 4) for c in muzzle.location]}
    rep["dims"] = {
        "barrel_len_base_ring_to_muzzle": BARREL_LEN,
        "barrel_len_overall_incl_cascabel": round(BARREL_LEN - BARREL_PROFILE[0][0], 3),
        "trunnion_from_breech_face": round(TRUN_U, 3),
        "trunnion_height_above_deck": TRUN.z,
        "muzzle_centre_height": round(mz.z, 3),
        "muzzle_x_from_carriage_origin": round(mz.x, 3),
        "stool_bed_z": list(STOOL_Z),
        "quoin_outline_xz_rest": [[round(a, 4), round(b, 4)] for a, b in quoin_geometry()],
        "quoin_slope": QUOIN_SLOPE,
    }
    allpts = [ob.matrix_world @ v.co for ob in [carriage] + wheels for v in ob.data.vertices]
    rep["dims"]["carriage_footprint_xy"] = [round(max(p.x for p in allpts) - min(p.x for p in allpts), 3),
                                            round(max(p.y for p in allpts) - min(p.y for p in allpts), 3)]
    allpts += [ob.matrix_world @ v.co for ob in (barrel, quoin) for v in ob.data.vertices]
    rep["dims"]["whole_cannon_bbox"] = [[round(min(p[i] for p in allpts), 3) for i in range(3)],
                                        [round(max(p[i] for p in allpts), 3) for i in range(3)]]
    print("CANNON_REPORT " + json.dumps(rep))
    with open(ROOT + "props/Cannon_report.json", "w") as fh:
        json.dump(rep, fh, indent=1)

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
