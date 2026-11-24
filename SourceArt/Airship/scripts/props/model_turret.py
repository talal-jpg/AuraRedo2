"""Front machine-gun turret for the airship's narrow forward deck (round 2, 2026-11-24). Stylized, chunky, game ready,
built like model_cannon.py (bmesh in code, metres, +Z up).

Run headless (re-runnable, rebuilds everything from scratch and overwrites the output):
    blender -b --factory-startup --python model_turret.py
Output: rig/props/Turret.blend, collection "Turret", report rig/props/Turret_report.json:
    Turret_Base   the yaw part. Origin = yaw axis on the deck (z 0 = deck top). Round iron pedestal on a bolted foot
                  ring, a turning ring, a cradle with two cheeks holding the trunnions at z PIVOT_H, a curved armour
                  shield in front (slot for the barrels), a wooden ammo crate on the left cheek. Nothing farther than
                  0.44 m from the axis (0.88 m across; the gantry rail is 0.465 m away), turns clear of a gunner
                  standing 1.0 m behind the axis.
    Turret_Gun    the pitch part. Origin = trunnion axis centre (pitch axis = local Y), fires +X. Twin water-jacketed
                  barrels, receiver block behind the trunnions, spade grips hanging behind it (chest height for the
                  141.6 cm mech), a brass ring sight; nothing more than 0.45 m behind the axis. Located at
                  (0, 0, PIVOT_H) on the base.
    Turret_Muzzle EMPTY at the muzzle point between the barrel ends (MUZZLE_X, 0, 0), parented to Turret_Gun.
Unreal (AAirshipTurret): BaseMesh yaws about the Root (the mount on the deck), GunMesh sits at (0, 0, PivotHeight) on
BaseMesh and pitches (+ = muzzle up), Muzzle at (MuzzleForward, 0, 0) on GunMesh. Clearance of the pitch range
-20..+40 against the base is checked here (PITCH_CHECK).
Materials (placeholder colours for previews): M_Turret_Iron / _Wood / _Brass / _Bore; bake_props_comic.py turns them
into the part_kind face attribute, puts both objects on the shared prop atlas and bakes the comic ink like the cannon.
Every mesh: smooth shading with sharp edges marked by angle, seams = sharp edges + one meridian per turned part, one
non-overlapping UV map.
"""
import bpy, bmesh, math, json, os
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree

ROOT = "/mnt/new_partition/BlenderProjects/StylizedAirship/rig/"
OUT = ROOT + "props/Turret.blend"
REPORT = ROOT + "props/Turret_report.json"

# ---------------------------------------------------------------- layout
PIVOT_H = 1.50          # trunnion (pitch) axis above the deck: clears the gantry rail top (1.135 m) at -20 deg
MUZZLE_X = 1.80         # muzzle point ahead of the trunnion axis (gun space)
BARREL_Y = 0.10         # twin barrels at y +-BARREL_Y
JACKET_R, BARREL_R = 0.07, 0.03
FOOT_R = 0.42           # foot ring radius (0.84 m across)
RING_Z = (0.80, 0.88)   # turning ring
CRADLE_Z = (0.88, 0.96)
CHEEK_IN, CHEEK_OUT = 0.20, 0.26     # cheek inner / outer face |y|
# shield = a slab of a vertical cylinder round the yaw axis. Everything on the yaw part stays within 0.44 m of the axis:
# the gantry rail's inner face is 0.465 m from the axis at the mounts (|y| 2.45 vs 2.915), and the base turns 110 deg
SHIELD_R, SHIELD_T = 0.425, 0.03    # outer radius, thickness
SHIELD_HALF_DEG = 52.0  # the shield spans +-52 deg round the bow side (|y| 0.335)
SLOT_HALF_W = 0.20      # barrel slot |y| at the shield's inner face (jackets reach |y| 0.17, their bands 0.18)
SHIELD_Z = (0.96, 1.92, 1.22)   # bottom, top at the centre, slot bottom
BASE_MAX_R = 0.44       # nothing on the yaw part farther from the axis (rail clearance, see the shield)
REAR_MAX = 0.45         # nothing on the gun farther behind the trunnion axis (receiver, rear plate, spade grips)
PITCH_RANGE = (-20.0, 40.0)
PITCH_CHECK = [-20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0]
SEG_LATHE, SEG_SMALL, SEG_BOLT = 32, 16, 10

MATS = {
    "M_Turret_Iron": (0.085, 0.095, 0.115),
    "M_Turret_Wood": (0.32, 0.17, 0.085),
    "M_Turret_Brass": (0.55, 0.40, 0.12),
    "M_Turret_Bore": (0.012, 0.012, 0.016),
}
IRON, WOOD, BRASS, BORE = 0, 1, 2, 3   # global material ids, remapped per object


# ================================================================ bmesh helpers (as model_cannon.py)
def finish(bm, mat, sharp_deg=40.0, chamfer=0.0, tri_ngons=True, seam_sharp=True, chamfer_min_deg=30.0, recalc=True):
    """Normals out, optional chamfer on convex hard edges, ngons -> tris/quads, sharp + seam over sharp_deg, smooth
    faces, material id (None = keep the per-face ids)."""
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
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


def lathe(prof, axis, origin=(0, 0, 0), e1=None, segs=SEG_LATHE, mats=None, mat=IRON, sharp_deg=40.0, meridians=1):
    """Surface of revolution, prof = [(a, r)] along axis, r == 0 -> pole; mats[i] = material of band i -> i + 1.
    The meridian at angle 0 (direction e1) is a UV seam; every sharp ring is a seam (finish)."""
    bm = bmesh.new()
    A = V(axis).normalized()
    E1 = V(e1).normalized() if e1 else A.orthogonal().normalized()
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
    return finish(bm, None, sharp_deg)


def prism(poly, plane, w0, w1, mat, chamfer=0.0, sharp_deg=35.0):
    """Closed prism from a simple 2D polygon. plane 'XZ': (a,b)->(a, w, b); 'XY': (a, b, w); 'YZ': (w, a, b)."""
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
    return finish(bm, mat, sharp_deg, chamfer)


def box(x0, x1, y0, y1, z0, z1, mat, chamfer=0.0):
    return prism([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], "XZ", y0, y1, mat, chamfer)


def torus(center, normal, R, r, seg_major=20, seg_minor=8, mat=BRASS, e1=None):
    bm = bmesh.new()
    N = V(normal).normalized()
    E1 = V(e1).normalized() if e1 else N.orthogonal().normalized()
    E2 = N.cross(E1)
    C = V(center)
    grid = []
    for i in range(seg_major):
        t = 2 * math.pi * i / seg_major
        d = E1 * math.cos(t) + E2 * math.sin(t)
        grid.append([bm.verts.new(C + d * (R + r * math.cos(2 * math.pi * j / seg_minor)) +
                                  N * (r * math.sin(2 * math.pi * j / seg_minor))) for j in range(seg_minor)])
    for i in range(seg_major):
        inn = (i + 1) % seg_major
        for j in range(seg_minor):
            jn = (j + 1) % seg_minor
            bm.faces.new((grid[i][j], grid[inn][j], grid[inn][jn], grid[i][jn]))
    bm.edges.ensure_lookup_table()
    for j in range(seg_minor):  # one cut around the tube, one along it
        e = bm.edges.get((grid[0][j], grid[0][(j + 1) % seg_minor]))
        if e:
            e.seam = True
    for i in range(seg_major):
        e = bm.edges.get((grid[i][0], grid[(i + 1) % seg_major][0]))
        if e:
            e.seam = True
    return finish(bm, mat, 50.0)


def bolt(pos, axis, r=0.03, h=0.022, mat=IRON):
    """Round iron bolt head (low frustum) sitting on a face; its base hides in the face."""
    ax = V(axis)
    return lathe([(-0.004, r), (h, r * 0.64), (h, 0.0)], ax, pos, segs=SEG_BOLT, mat=mat, sharp_deg=50.0,
                 e1=(0, 0, -1) if abs(ax.z) < 0.9 else (1, 0, 0))


def slab_rows(bm, pts_fn, n):
    """Closed curved slab from n + 1 cross-sections, each 4 points (inner-bottom, outer-bottom, outer-top, inner-top)."""
    rows = [[bm.verts.new(p) for p in pts_fn(i / n)] for i in range(n + 1)]
    for k in range(n):
        a, b = rows[k], rows[k + 1]
        for s in range(4):
            sn = (s + 1) % 4
            bm.faces.new((a[s], a[sn], b[sn], b[s]))
    bm.faces.new(rows[0][::-1])
    bm.faces.new(rows[-1])
    return rows


# ================================================================ base (yaw part)
SLOT_DEG = math.degrees(math.asin(SLOT_HALF_W / (SHIELD_R - SHIELD_T)))   # 30.4 deg


def shield_top(t):
    """shield top edge height at angle t (deg, 0 = bow): highest at the centre, a little lower toward the edges"""
    return SHIELD_Z[1] - 0.12 * (t / SHIELD_HALF_DEG) ** 2


def shield_piece(t0, t1, z_top_fn, z0, n):
    """one curved armour slab of the shield between angles t0..t1 (deg, + = toward +Y), z0 .. z_top_fn(t)"""
    bm = bmesh.new()
    ri, ro = SHIELD_R - SHIELD_T, SHIELD_R

    def section(u):
        t = t0 + (t1 - t0) * u
        zt = z_top_fn(t)
        c, s_ = math.cos(math.radians(t)), math.sin(math.radians(t))
        return [(ri * c, ri * s_, z0), (ro * c, ro * s_, z0), (ro * c, ro * s_, zt), (ri * c, ri * s_, zt)]
    slab_rows(bm, section, n)
    return finish(bm, IRON, 35.0, chamfer=0.006)


def shield_front(t, z):
    """point and normal on the shield's outer face at angle t (deg)"""
    n = V((math.cos(math.radians(t)), math.sin(math.radians(t)), 0.0))
    return n * SHIELD_R + V((0, 0, z)), n


def build_base():
    P = []
    # pedestal: foot flange (skirt 1 cm below the deck line: the gantry deck is flat at the mounts), column, collar,
    # turning ring, cradle seat
    prof = [(-0.01, 0.0), (-0.01, FOOT_R), (0.05, FOOT_R), (0.065, FOOT_R - 0.015), (0.065, 0.30),
            (0.10, 0.26), (0.14, 0.245), (0.70, 0.215), (0.70, 0.24), (0.76, 0.24), (0.76, 0.215),
            (RING_Z[0], 0.215), (RING_Z[0], 0.33), (RING_Z[1] - 0.015, 0.33), (RING_Z[1], 0.315),
            (RING_Z[1], 0.0)]
    P.append(lathe(prof, (0, 0, 1), e1=(-1, 0, 0), segs=SEG_LATHE + 8))
    for k in range(10):                   # foot ring bolts
        a = 2 * math.pi * (k + 0.5) / 10
        P.append(bolt((0.365 * math.cos(a), 0.365 * math.sin(a), 0.065), (0, 0, 1)))
    for k in range(12):                   # turning ring bolt heads round its rim
        a = 2 * math.pi * k / 12
        P.append(bolt((0.33 * math.cos(a), 0.33 * math.sin(a), (RING_Z[0] + RING_Z[1]) / 2), (math.cos(a), math.sin(a), 0),
                      r=0.018, h=0.014))
    # cradle plate on the turning ring, cheeks with round tops over the trunnions
    P.append(box(-0.22, 0.22, -CHEEK_OUT, CHEEK_OUT, CRADLE_Z[0] - 0.01, CRADLE_Z[1], IRON, chamfer=0.01))
    rc = 0.13
    cheek = [(-0.20, CRADLE_Z[1] - 0.01), (0.20, CRADLE_Z[1] - 0.01), (0.17, 1.30)]
    for i in range(1, 12):                # round top: arc from -40 deg (front) over the top to 220 deg (back)
        a = math.radians(-40 + 260 * i / 12)
        cheek.append((rc * math.cos(a), PIVOT_H + rc * math.sin(a)))
    cheek.append((-0.17, 1.30))
    for s in (1, -1):
        y0, y1 = sorted((s * CHEEK_IN, s * CHEEK_OUT))
        P.append(prism(cheek, "XZ", y0, y1, IRON, chamfer=0.008))
        # trunnion boss + cap on the outer face, two bolts lower down
        P.append(lathe([(0.0, 0.075), (0.035, 0.075), (0.045, 0.06), (0.045, 0.0)], (0, s, 0),
                       (0, s * CHEEK_OUT, PIVOT_H), e1=(0, 0, -1), segs=SEG_SMALL + 4))
        for x in (-0.11, 0.11):
            P.append(bolt((x, s * CHEEK_OUT, 1.10), (0, s, 0), r=0.024, h=0.016))
    # shield: two wings either side of the barrel slot + an apron under it, rivets, two brackets to the cradle
    P.append(shield_piece(SLOT_DEG, SHIELD_HALF_DEG, shield_top, SHIELD_Z[0], 8))
    P.append(shield_piece(-SHIELD_HALF_DEG, -SLOT_DEG, shield_top, SHIELD_Z[0], 8))
    P.append(shield_piece(-SLOT_DEG - 0.3, SLOT_DEG + 0.3, lambda t: SHIELD_Z[2], SHIELD_Z[0], 12))
    for t in (-46.0, -36.5, 36.5, 46.0):
        for z in (1.04, 1.50, shield_top(t) - 0.07):
            p, n = shield_front(t, z)
            P.append(bolt(p, n, r=0.018, h=0.011))
    for t in (-18.0, 0.0, 18.0):
        p, n = shield_front(t, SHIELD_Z[0] + 0.08)
        P.append(bolt(p, n, r=0.018, h=0.011))
    ri = SHIELD_R - SHIELD_T
    for s in (1, -1):                     # brackets from the cradle plate out to the shield's inner face
        xs = math.sqrt(ri * ri - 0.24 ** 2) + 0.004
        P.append(box(0.16, xs, min(s * 0.20, s * 0.28), max(s * 0.20, s * 0.28), CRADLE_Z[0], 1.10, IRON, chamfer=0.006))
    # wooden ammo crate on the left (+Y) cheek, iron straps and a rope-less iron handle
    ax0, ax1, ay0, ay1, az0, az1 = -0.15, 0.12, CHEEK_OUT, 0.385, 1.10, 1.36
    P.append(box(ax0, ax1, ay0 - 0.005, ay1, az0, az1, WOOD, chamfer=0.01))
    P.append(box(ax0 - 0.008, ax1 + 0.008, ay0 - 0.005, ay1 + 0.008, az1 - 0.035, az1 + 0.01, IRON, chamfer=0.006))
    for x in (ax0 + 0.05, ax1 - 0.05):
        P.append(box(x - 0.015, x + 0.015, ay0 - 0.005, ay1 + 0.006, az0 - 0.004, az1 - 0.03, IRON))
    P.append(torus(((ax0 + ax1) / 2, ay1 + 0.004, az1 - 0.10), (0, 1, 0), 0.04, 0.008, 16, 6, IRON, e1=(0, 0, -1)))
    return P


# ================================================================ gun (pitch part, origin = trunnion axis)
def barrel_profile():
    """(a, r) along +X for one barrel: neck out of the receiver, water jacket with cooling bands, front collar, nose,
    bare barrel, flash hider, muzzle face, dark bore"""
    J = JACKET_R
    prof = [(0.12, 0.0), (0.12, 0.05), (0.17, 0.05), (0.17, 0.08), (0.24, 0.08), (0.24, J),
            (0.52, J), (0.52, J + 0.01), (0.58, J + 0.01), (0.58, J),
            (0.86, J), (0.86, J + 0.01), (0.92, J + 0.01), (0.92, J),
            (1.20, J), (1.20, J + 0.012), (1.30, J + 0.012), (1.36, 0.042), (1.36, BARREL_R),
            (1.64, BARREL_R), (1.64, 0.044), (1.66, 0.048), (MUZZLE_X, 0.052), (MUZZLE_X, 0.024),
            (MUZZLE_X - 0.03, 0.024), (MUZZLE_X - 0.14, 0.024), (MUZZLE_X - 0.14, 0.0)]
    mats = [IRON] * (len(prof) - 1)
    mats[-1] = mats[-2] = BORE          # bore tube and bottom
    return prof, mats


def build_gun():
    P = []
    # receiver + top cover + rear plate: everything stays within REAR_MAX behind the trunnion axis
    P.append(box(-0.30, 0.17, -0.15, 0.15, -0.11, 0.12, IRON, chamfer=0.015))
    P.append(box(-0.27, 0.10, -0.11, 0.11, 0.12, 0.15, IRON, chamfer=0.01))
    P.append(box(-0.36, -0.29, -0.13, 0.13, -0.12, 0.08, IRON, chamfer=0.01))
    for y in (-0.08, 0.08):              # rivets on the receiver sides
        P.append(bolt((-0.15, 0.15, y * 0.6), (0, 1, 0), r=0.018, h=0.012))
        P.append(bolt((-0.15, -0.15, y * 0.6), (0, -1, 0), r=0.018, h=0.012))
    # trunnion pins into the cheeks (inner face at |y| CHEEK_IN), hidden ends inside
    for s in (1, -1):
        P.append(lathe([(0.12, 0.0), (0.12, 0.05), (CHEEK_IN + 0.015, 0.05), (CHEEK_IN + 0.015, 0.0)], (0, s, 0),
                       (0, 0, 0), e1=(0, 0, -1), segs=SEG_SMALL))
    # twin barrels
    prof, mats = barrel_profile()
    for y in (BARREL_Y, -BARREL_Y):
        P.append(lathe(prof, (1, 0, 0), (0, y, 0), e1=(0, 0, -1), segs=SEG_LATHE - 8, mats=mats))
    # barrel clamp between the jackets, front strap
    P.append(box(0.70, 0.78, -BARREL_Y, BARREL_Y, -0.045, 0.045, IRON, chamfer=0.008))
    P.append(box(1.24, 1.30, -BARREL_Y, BARREL_Y, -0.04, 0.04, IRON, chamfer=0.006))
    # ring sight on a post between the barrels + rear leaf sight on the receiver
    P.append(box(0.995, 1.025, -0.012, 0.012, 0.035, 0.205, IRON))
    P.append(torus((1.01, 0.0, 0.28), (1, 0, 0), 0.075, 0.01, 24, 8, BRASS, e1=(0, 0, 1)))
    for a in (0, 90, 180, 270):          # cross wires of the ring sight
        d = V((0, math.sin(math.radians(a)), math.cos(math.radians(a))))
        c = V((1.01, 0.0, 0.28)) + d * 0.0375
        P.append(lathe([(-0.0375, 0.0), (-0.0375, 0.004), (0.0375, 0.004), (0.0375, 0.0)], d, c, segs=6, mat=BRASS))
    P.append(box(-0.25, -0.22, -0.025, 0.025, 0.15, 0.25, BRASS, chamfer=0.004))
    # cocking lever standing on the top cover (right), the belt feed port on the left side (clear of the cheeks)
    P.append(box(-0.13, -0.05, -0.10, -0.075, 0.15, 0.21, IRON, chamfer=0.005))
    P.append(lathe([(0.0, 0.0), (0.0, 0.022), (0.045, 0.022), (0.055, 0.0)], (0, 0, 1), (-0.09, -0.0875, 0.205),
                   e1=(1, 0, 0), segs=SEG_SMALL, mat=BRASS))
    P.append(box(-0.20, -0.06, 0.15, 0.185, -0.02, 0.10, IRON, chamfer=0.008))
    # spade grips: two arms down-back from the rear plate, wooden grips, an iron trigger bar between them
    gx, gz0, gz1 = -0.41, -0.22, -0.05
    for s in (1, -1):
        y0, y1 = sorted((s * 0.09, s * 0.125))
        P.append(prism([(-0.36, 0.02), (-0.36, -0.08), (gx + 0.03, gz1 - 0.01), (gx - 0.03, gz1 - 0.01),
                        (gx - 0.03, gz1 + 0.05)], "XZ", y0, y1, IRON, chamfer=0.006))
        yc = s * 0.107
        P.append(lathe([(gz0 - 0.02, 0.0), (gz0 - 0.02, 0.03), (gz0, 0.034), (gz0 + 0.01, 0.028),
                        (gz1 - 0.01, 0.028), (gz1, 0.032), (gz1 + 0.01, 0.0)], (0, 0, 1), (gx, yc, 0),
                       e1=(1, 0, 0), segs=SEG_SMALL, mats=[IRON, IRON, WOOD, WOOD, WOOD, IRON]))
    P.append(lathe([(-0.09, 0.0), (-0.09, 0.012), (0.09, 0.012), (0.09, 0.0)], (0, 1, 0), (gx + 0.035, 0, gz0 + 0.06),
                   e1=(0, 0, -1), segs=8))
    return P


# ================================================================ assembly
def make_object(name, parts, location, coll):
    """parts: finished bmeshes (global material ids). Appends them into one mesh with only the materials it uses."""
    me = bpy.data.meshes.new(name)
    used = sorted({f.material_index for bm in parts for f in bm.faces})
    remap = {g: i for i, g in enumerate(used)}
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
    for g in used:
        me.materials.append(bpy.data.materials[names[g]])
    me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    coll.objects.link(ob)
    return ob


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
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    ov, cov, oob = uv_overlap(me)
    co = np.array([tuple(v.co) for v in me.vertices])
    return {"tris": len(me.loop_triangles), "verts": len(me.vertices), "faces": len(me.polygons),
            "min_face_area": round(min(areas), 7), "open_edges": nonman,
            "uv_overlap_px@2k": ov, "uv_coverage": round(cov, 3), "uv_out_of_0_1": oob,
            "origin": [round(c, 4) for c in ob.matrix_world.translation],
            "local_bbox_min": co.min(0).round(4).tolist(), "local_bbox_max": co.max(0).round(4).tolist(),
            "max_radius_xy": round(float(np.hypot(co[:, 0], co[:, 1]).max()), 4),
            "materials": [m.name for m in me.materials]}


def bvh_of(ob, M):
    me = ob.data
    co = [tuple(M @ v.co) for v in me.vertices]
    return BVHTree.FromPolygons(co, [tuple(p.vertices) for p in me.polygons])


def pitch_clearance(base, gun):
    """gun pitched through PITCH_CHECK (rotation about the trunnion axis, + = muzzle up) against the base. The
    trunnion pins sit in the cheeks on purpose, so gun faces reaching |y| >= CHEEK_IN are left out."""
    tb = bvh_of(base, Matrix.Identity(4))
    me = gun.data
    keep = [tuple(p.vertices) for p in me.polygons if max(abs(me.vertices[i].co.y) for i in p.vertices) < CHEEK_IN - 1e-4]
    out = {}
    for p in PITCH_CHECK:
        M = Matrix.Translation(V((0, 0, PIVOT_H))) @ Matrix.Rotation(math.radians(-p), 4, "Y")
        tg = BVHTree.FromPolygons([tuple(M @ v.co) for v in me.vertices], keep)
        out["%+d" % p] = len(tg.overlap(tb))
    return out


def gunner_clearance(base, gun):
    """gap between a gunner capsule (r 0.34, 1.416 tall) standing 1.0 m behind the yaw axis and the turret: the base at
    any yaw (its largest radius below the capsule top), the gun at yaw 0 over the pitch range (its rearmost point below
    the capsule top: the spade grips, where the gunner's hands go)"""
    co = np.array([tuple(v.co) for v in base.data.vertices])
    r = np.hypot(co[:, 0], co[:, 1])
    gb = 1.0 - 0.34 - float(r[co[:, 2] < 1.416].max())
    cg = np.array([tuple(v.co) for v in gun.data.vertices])
    rear = 0.0
    for p in PITCH_CHECK:
        R = np.array(Matrix.Rotation(math.radians(-p), 3, "Y"))
        w = cg @ R.T + np.array((0, 0, PIVOT_H))
        low = w[:, 2] < 1.416
        if low.any():
            rear = max(rear, float(-w[low, 0].min()))
    return dict(base_m=round(gb, 4), gun_grips_m=round(1.0 - 0.34 - rear, 4), gun_rear_extent_m=round(rear, 4))


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
        bsdf.inputs["Roughness"].default_value = 0.8 if "Iron" not in n else 0.55
        if "Iron" in n or "Brass" in n:
            bsdf.inputs["Metallic"].default_value = 0.6
    coll = bpy.data.collections.new("Turret")
    sc.collection.children.link(coll)

    base = make_object("Turret_Base", build_base(), (0, 0, 0), coll)
    gun = make_object("Turret_Gun", build_gun(), (0, 0, PIVOT_H), coll)
    muzzle = bpy.data.objects.new("Turret_Muzzle", None)
    muzzle.empty_display_type = "ARROWS"
    muzzle.empty_display_size = 0.25
    coll.objects.link(muzzle)
    muzzle.parent = gun
    muzzle.location = (MUZZLE_X, 0, 0)
    for ob in (base, gun):
        unwrap(ob)
    bpy.context.view_layer.update()

    rep = {ob.name: report(ob) for ob in (base, gun)}
    rep["Turret_Muzzle"] = {"parent": muzzle.parent.name, "local": [round(c, 4) for c in muzzle.location],
                            "world": [round(c, 4) for c in muzzle.matrix_world.translation]}
    rep["dims"] = {"pivot_height": PIVOT_H, "muzzle_x": MUZZLE_X, "barrel_y": BARREL_Y, "jacket_r": JACKET_R,
                   "foot_r": FOOT_R, "shield_top_centre": SHIELD_Z[1], "shield_r": SHIELD_R, "slot_half_width": SLOT_HALF_W,
                   "pitch_range_deg": list(PITCH_RANGE)}
    rep["pitch_clearance_overlapping_pairs"] = pitch_clearance(base, gun)
    rep["gunner_capsule_clearance_m"] = gunner_clearance(base, gun)
    assert all(v == 0 for v in rep["pitch_clearance_overlapping_pairs"].values()), rep["pitch_clearance_overlapping_pairs"]
    assert rep["Turret_Base"]["max_radius_xy"] <= BASE_MAX_R, ("the yaw part reaches past", BASE_MAX_R, rep["Turret_Base"])
    assert rep["gunner_capsule_clearance_m"]["base_m"] > 0.15, rep["gunner_capsule_clearance_m"]
    assert rep["gunner_capsule_clearance_m"]["gun_grips_m"] > 0.0, rep["gunner_capsule_clearance_m"]
    assert -rep["Turret_Gun"]["local_bbox_min"][0] <= REAR_MAX + 1e-6, ("gun reaches too far back", rep["Turret_Gun"])
    for k in ("Turret_Base", "Turret_Gun"):
        assert rep[k]["uv_overlap_px@2k"] == 0 and rep[k]["uv_out_of_0_1"] == 0, (k, rep[k])
    print("TURRET_REPORT " + json.dumps(rep))
    with open(REPORT, "w") as fh:
        json.dump(rep, fh, indent=1)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
