# Mech Sentinel source art - tentacle, claw tip and "sweep a tentacle along a curve" builders.
# Runs with Blender 5.x, either the `bpy` Python module or `blender -b -P` (imported by build_mech_sentinel.py).
#
# Public API
#   build_tentacle(collection=None)       -> 'SM_MechSentinel_Tentacle'    (straight, +X, 11 armored sleeves + claw)
#   build_tentacle_tip(collection=None)   -> 'SM_MechSentinel_TentacleTip' (3-prong claw alone, base at origin, +X)
#   sweep_tentacle(points, root_radius, tip_radius, sides, name, collection=None, with_claw=False, ...)
#                                          -> tube mesh along a polyline (parallel-transport frames, tapered)
#   make_trailing_curve(root, direction, length, num_points, droop, sway, seed)
#                                          -> list[Vector], a deterministic trailing / drooping S-curve
#
# Everything is built with bmesh from explicit rings, so the output is fully deterministic.

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mech_sentinel_common as C  # noqa: E402

TENTACLE_NAME = "SM_MechSentinel_Tentacle"
TENTACLE_TIP_NAME = "SM_MechSentinel_TentacleTip"

TENTACLE_SIDES = 8
SHAFT_LENGTH = C.TENTACLE_SEGMENTS * C.TENTACLE_SEGMENT_LENGTH          # 1.98 m
ROOT_RADIUS = C.TENTACLE_ROOT_DIAMETER * 0.5                          # 0.09 m
SHAFT_END_RADIUS = C.TENTACLE_SHAFT_END_DIAMETER * 0.5                # 0.0175 m

# Claw tip, authored for a base radius of SHAFT_END_RADIUS (scaled for other tip radii).
CLAW_BASE_RADIUS = SHAFT_END_RADIUS
CLAW_LENGTH = 0.13                                                    # tentacle total = 1.98 + 0.13 = 2.11 m

# One armored sleeve, as (u, radius factor) rings; u runs 0..1 from the root side of the sleeve to its tip side.
# u=0 is the V-groove between two sleeves, then a short chamfer out to the sleeve body, which widens slightly
# into a flared trailing rim; the next sleeve's groove closes the rim with a steep step back in.
SLEEVE_PROFILE = (
    (0.00, 0.74),   # groove floor
    (0.11, 0.95),   # sleeve start (chamfer out of the groove)
    (0.84, 1.10),   # flared trailing rim
)
ROOT_RING_FACTOR = 1.0  # the very first ring (root collar) keeps the nominal 0.18 m diameter
END_RING_FACTOR = 1.0   # the last shaft ring keeps the nominal 0.035 m diameter (claw base)


# ---------------------------------------------------------------------------------------------------------------------
# Small geometry helpers

def _ring_angles(sides):
    # Half-step offset: flats (not corners) face up / down / sideways.
    off = math.pi / sides
    return [2.0 * math.pi * j / sides + off for j in range(sides)]


def _add_ring(bm, center, n_axis, b_axis, radius, sides, stretch_dir=None, stretch=1.0):
    """Ring of `sides` verts around `center` in the plane (n_axis, b_axis); counter-clockwise about n x b."""
    verts = []
    for a in _ring_angles(sides):
        off = (n_axis * math.cos(a) + b_axis * math.sin(a)) * radius
        if stretch_dir is not None and abs(stretch - 1.0) > 1e-6:
            off = off + stretch_dir * (off.dot(stretch_dir) * (stretch - 1.0))
        verts.append(bm.verts.new(center + off))
    return verts


def _bridge(bm, ring_a, ring_b, mat=0):
    """Quads between two rings with the same vertex count; outward normals when ring_b is ahead of ring_a."""
    n = len(ring_a)
    for j in range(n):
        k = (j + 1) % n
        f = bm.faces.new((ring_a[j], ring_a[k], ring_b[k], ring_b[j]))
        f.material_index = mat


def _cap(bm, ring, facing_forward, mat=0):
    f = bm.faces.new(ring if facing_forward else list(reversed(ring)))
    f.material_index = mat
    return f


def _fan(bm, ring, tip, mat=0):
    n = len(ring)
    for j in range(n):
        f = bm.faces.new((ring[j], ring[(j + 1) % n], tip))
        f.material_index = mat


def _frame_from_tangent(t, up=Vector((0.0, 0.0, 1.0))):
    """Initial frame (n, b) for tangent t: b is world up projected onto the ring plane, n = b x t."""
    t = t.normalized()
    b = up - t * up.dot(t)
    if b.length < 1e-4:
        alt = Vector((0.0, 1.0, 0.0))
        b = alt - t * alt.dot(t)
    b.normalize()
    n = b.cross(t).normalized()
    return n, b


def _parallel_transport(tangents):
    """Rotation-minimizing frames (n_i, b_i) along a list of unit tangents (no twist, no flips)."""
    n, b = _frame_from_tangent(tangents[0])
    frames = [(n, b)]
    for i in range(1, len(tangents)):
        t0, t1 = tangents[i - 1], tangents[i]
        q = t0.rotation_difference(t1)
        n = q @ n
        n = (n - t1 * n.dot(t1))
        if n.length < 1e-6:
            n, _ = _frame_from_tangent(t1)
        n.normalize()
        b = t1.cross(n).normalized()
        frames.append((n, b))
    return frames


class _Spine:
    """Arc-length parametrised Catmull-Rom curve through a polyline (straight line for 2 points)."""

    def __init__(self, points, samples_per_span=16):
        pts = []
        for p in points:
            p = Vector(p)
            if not pts or (p - pts[-1]).length > 1e-6:
                pts.append(p)
        if len(pts) < 2:
            raise ValueError("sweep needs at least two distinct points")
        dense = [pts[0].copy()]
        if len(pts) == 2:
            for k in range(1, samples_per_span + 1):
                dense.append(pts[0].lerp(pts[1], k / samples_per_span))
        else:
            ext = [2.0 * pts[0] - pts[1]] + pts + [2.0 * pts[-1] - pts[-2]]
            for i in range(1, len(ext) - 2):
                p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
                for k in range(1, samples_per_span + 1):
                    t = k / samples_per_span
                    t2, t3 = t * t, t * t * t
                    dense.append(0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                                        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3))
        self.dense = dense
        self.cum = [0.0]
        for i in range(1, len(dense)):
            self.cum.append(self.cum[-1] + (dense[i] - dense[i - 1]).length)
        self.length = self.cum[-1]

    def _locate(self, s):
        s = min(max(s, 0.0), self.length)
        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        seg = max(self.cum[hi] - self.cum[lo], 1e-9)
        return lo, hi, (s - self.cum[lo]) / seg

    def point(self, s):
        lo, hi, f = self._locate(s)
        return self.dense[lo].lerp(self.dense[hi], f)

    def tangent(self, s, eps=0.004):
        a = self.point(max(s - eps, 0.0))
        b = self.point(min(s + eps, self.length))
        d = b - a
        if d.length < 1e-9:
            lo, hi, _ = self._locate(s)
            d = self.dense[hi] - self.dense[lo]
        return d.normalized()


# ---------------------------------------------------------------------------------------------------------------------
# Claw

# Hub rings (x, radius) in claw space for a base radius of CLAW_BASE_RADIUS. Ring 0 is the base (shared with the shaft).
_CLAW_HUB = (
    (0.000, CLAW_BASE_RADIUS),
    (0.007, 0.0255),   # collar flare
    (0.021, 0.0255),   # collar band (glow ring on the full tentacle)
    (0.033, 0.0150),   # front chamfer, closed by a cap
)
# Prong spine as (x, radial distance) - leaves the hub, bows outward, hooks back in to a point.
_CLAW_PRONG_SPINE = ((0.014, 0.0095), (0.050, 0.0305), (0.094, 0.0330), (CLAW_LENGTH, 0.0085))
_CLAW_PRONG_HALF_WIDTH = (0.0068, 0.0062, 0.0040)    # tangential half width per ring
_CLAW_PRONG_HALF_THICK = (0.0050, 0.0058, 0.0040)    # radial half thickness per ring
_CLAW_PRONG_ANGLES = (90.0, 210.0, 330.0)             # one prong on top, two below-sideways


def _build_claw(bm, xform, scale, sides, base_ring=None, glow=False):
    """Adds a 3-prong claw to `bm`. Claw space: base at origin, pointing +X, up +Z; `xform` maps it to mesh space.
    When `base_ring` (sides verts, same angle convention as _add_ring) is given, the hub grows out of it."""
    xf = xform

    def P(x, y, z):
        return xf @ (Vector((x, y, z)) * scale)

    ex, ey, ez = Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0))
    rings = []
    for i, (x, r) in enumerate(_CLAW_HUB):
        if i == 0 and base_ring is not None:
            rings.append(base_ring)
            continue
        ring = []
        for a in _ring_angles(sides):
            ring.append(bm.verts.new(P(x, r * math.cos(a), r * math.sin(a))))
        rings.append(ring)
    if base_ring is None:
        _cap(bm, rings[0], facing_forward=False)
    for i in range(len(rings) - 1):
        _bridge(bm, rings[i], rings[i + 1], mat=1 if (glow and i == 1) else 0)
    _cap(bm, rings[-1], facing_forward=True)

    spine = [Vector((x, r)) for x, r in _CLAW_PRONG_SPINE]
    for phi_deg in _CLAW_PRONG_ANGLES:
        phi = math.radians(phi_deg)
        radial = ey * math.cos(phi) + ez * math.sin(phi)

        def to3(v2):
            return ex * v2.x + radial * v2.y

        prong_rings = []
        for k in range(len(spine) - 1):
            prev_p = spine[max(k - 1, 0)]
            next_p = spine[k + 1]
            t2 = (next_p - prev_p).normalized()
            n2 = Vector((-t2.y, t2.x))                  # outward normal inside the prong plane
            t3, n3 = to3(t2).normalized(), to3(n2).normalized()
            g3 = t3.cross(n3).normalized()              # tangential (n x g = t: counter-clockwise ring)
            c3 = to3(spine[k])
            w, h = _CLAW_PRONG_HALF_WIDTH[k], _CLAW_PRONG_HALF_THICK[k]
            local = (c3 + n3 * h, c3 + g3 * w, c3 - n3 * (h * 0.7), c3 - g3 * w)
            prong_rings.append([bm.verts.new(xf @ (v * scale)) for v in local])
        _cap(bm, prong_rings[0], facing_forward=False)
        for k in range(len(prong_rings) - 1):
            _bridge(bm, prong_rings[k], prong_rings[k + 1])
        tip = bm.verts.new(xf @ (to3(spine[-1]) * scale))
        _fan(bm, prong_rings[-1], tip)


# ---------------------------------------------------------------------------------------------------------------------
# Public builders

def make_trailing_curve(root, direction, length=1.9, num_points=12, droop=0.30, sway=0.10, seed=0):
    """Deterministic trailing tentacle curve (list of Vector, len == num_points, consecutive points exactly
    length / (num_points - 1) apart, like the in-game chain).

    root      start point (socket location).
    direction initial heading (socket +X: mostly backward, fanned outward); the curve leaves the root tangent to it.
    droop     gravity sag in meters: the tip hangs about this far below the straight line (world -Z, quadratic).
    sway      lateral S-wave amplitude in meters (grows from 0 at the root, ~1 period over the length),
              plus a smaller vertical wave; phases / frequencies come from `seed`.
    """
    root = Vector(root)
    d = Vector(direction).normalized()
    up = Vector((0.0, 0.0, 1.0))
    side = d.cross(up)
    if side.length < 1e-4:
        side = Vector((0.0, 1.0, 0.0))
    side.normalize()
    vert = side.cross(d).normalized()

    rng = random.Random(int(seed) * 7919 + 17)
    f1 = rng.uniform(0.75, 1.15)
    ph1 = rng.uniform(0.0, 2.0 * math.pi)
    f2 = rng.uniform(0.45, 0.85)
    ph2 = rng.uniform(0.0, 2.0 * math.pi)

    def ramp(t):
        t = min(max(t, 0.0), 1.0)
        return t * t * (3.0 - 2.0 * t)

    def curve(t):
        e = ramp(t)
        p = root + d * (length * t)
        p = p + side * (sway * e * math.sin(2.0 * math.pi * f1 * t + ph1))
        p = p + vert * (0.4 * sway * e * math.sin(2.0 * math.pi * f2 * t + ph2))
        p.z -= droop * t * t
        return p

    steps = 600
    dense = [curve(1.6 * k / steps) for k in range(steps + 1)]
    num_points = max(2, int(num_points))
    seg = length / (num_points - 1)
    out = [dense[0].copy()]
    acc = 0.0
    target = seg
    for k in range(1, len(dense)):
        a, b = dense[k - 1], dense[k]
        dl = (b - a).length
        while acc + dl >= target - 1e-12 and len(out) < num_points:
            f = (target - acc) / max(dl, 1e-12)
            out.append(a.lerp(b, f))
            target += seg
        acc += dl
        if len(out) >= num_points:
            break
    # Re-chain so every segment is exactly `seg` long (chord vs. arc correction).
    chained = [out[0]]
    for i in range(1, len(out)):
        chained.append(chained[-1] + (out[i] - out[i - 1]).normalized() * seg)
    return chained


def sweep_tentacle(points, root_radius, tip_radius, sides, name, collection=None, with_claw=False,
                   armored=None, glow=False, sleeve_count=None, cap_root=True, uv=True):
    """Low-poly tentacle tube along a polyline (list of Vector).

    Frames are rotation-minimizing (parallel transport from a world-up start frame), so the tube never twists or
    pinches; the radius tapers linearly with arc length from root_radius to tip_radius.

    armored=False: one ring per input point (mitered at the bends) - the far LOD path (5-6 sides, 6-8 segments).
    armored=True : armored sleeves (groove / chamfer / flared rim) laid along a smoothed curve, about one sleeve
                   per 0.18 m of arc length (or `sleeve_count`) - the hero / reference path.
    armored=None : same as with_claw.
    with_claw    : adds the 3-prong claw (scaled to tip_radius) beyond the last point, along the last tangent.
    glow         : the claw collar ring uses slot 1 (MI_MechSentinel_Eyes); slots become [Body, Eyes].
    cap_root     : close the root end (set False when the root is buried inside the head).
    uv           : smart-UV unwrap the result (UV0).
    Returns the mesh object (identity transform, vertices in the space of `points`), slot 0 Body.
    """
    if armored is None:
        armored = with_claw
    sides = max(3, int(sides))
    bm = bmesh.new()

    if armored:
        spine = _Spine(points)
        length = spine.length
        count = sleeve_count or max(1, int(round(length / C.TENTACLE_SEGMENT_LENGTH)))
        pitch = length / count
        stations = []  # (arc length, radius factor)
        for i in range(count):
            for u, k in SLEEVE_PROFILE:
                if i == 0 and u == 0.0:
                    k = ROOT_RING_FACTOR
                stations.append(((i + u) * pitch, k))
        stations.append((length, END_RING_FACTOR))
        centers = [spine.point(s) for s, _ in stations]
        tangents = [spine.tangent(s) for s, _ in stations]
        radii = [(root_radius + (tip_radius - root_radius) * (s / length)) * k for s, k in stations]
        stretch = [(None, 1.0)] * len(stations)
    else:
        pts = []
        for p in points:
            p = Vector(p)
            if not pts or (p - pts[-1]).length > 1e-6:
                pts.append(p)
        if len(pts) < 2:
            raise ValueError("sweep needs at least two distinct points")
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + (pts[i] - pts[i - 1]).length)
        length = cum[-1]
        centers = pts
        tangents, stretch = [], []
        for i in range(len(pts)):
            d_prev = (pts[i] - pts[i - 1]).normalized() if i > 0 else None
            d_next = (pts[i + 1] - pts[i]).normalized() if i < len(pts) - 1 else None
            if d_prev is None:
                tangents.append(d_next)
                stretch.append((None, 1.0))
            elif d_next is None:
                tangents.append(d_prev)
                stretch.append((None, 1.0))
            else:
                t = d_prev + d_next
                t = t.normalized() if t.length > 1e-6 else d_next
                tangents.append(t)
                cos_half = max(t.dot(d_next), 0.6)
                w = d_next - t * d_next.dot(t)
                stretch.append((w.normalized(), 1.0 / cos_half) if w.length > 1e-6 else (None, 1.0))
        radii = [root_radius + (tip_radius - root_radius) * (c / length) for c in cum]

    frames = _parallel_transport(tangents)
    rings = []
    for i, c in enumerate(centers):
        n, b = frames[i]
        sdir, sfac = stretch[i]
        rings.append(_add_ring(bm, c, n, b, radii[i], sides, sdir, sfac))
    if cap_root:
        _cap(bm, rings[0], facing_forward=False)
    for i in range(len(rings) - 1):
        _bridge(bm, rings[i], rings[i + 1])

    if with_claw:
        t = tangents[-1]
        n, b = frames[-1]
        xform = Matrix((t, n, b)).transposed().to_4x4()
        xform.translation = centers[-1]
        _build_claw(bm, xform, radii[-1] / CLAW_BASE_RADIUS, sides, base_ring=rings[-1], glow=glow)
    else:
        _cap(bm, rings[-1], facing_forward=True)

    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    obj = C.mesh_object_from_bmesh(name, bm, collection)
    C.assign_slots(obj, with_eyes=glow)
    if uv:
        C.smart_uv(obj)
    return obj


def build_tentacle(collection=None):
    """SM_MechSentinel_Tentacle: straight along +X from the origin, 11 armored 0.18 m sleeves (shaft ends at
    x = 1.98 m, diameter 0.18 -> 0.035 m), 3-prong claw to x = 2.11 m, 8 sides. Slots [Body, Eyes]
    (Eyes = thin glow ring on the claw collar)."""
    pts = [Vector((0.0, 0.0, 0.0)), Vector((SHAFT_LENGTH, 0.0, 0.0))]
    return sweep_tentacle(pts, ROOT_RADIUS, SHAFT_END_RADIUS, TENTACLE_SIDES, TENTACLE_NAME, collection,
                          with_claw=True, armored=True, glow=True, sleeve_count=C.TENTACLE_SEGMENTS)


def build_tentacle_tip(collection=None):
    """SM_MechSentinel_TentacleTip: the claw alone, base ring (r = 0.0175 m) at the origin, pointing +X. Slot 0 Body."""
    bm = bmesh.new()
    _build_claw(bm, Matrix.Identity(4), 1.0, TENTACLE_SIDES, base_ring=None, glow=False)
    obj = C.mesh_object_from_bmesh(TENTACLE_TIP_NAME, bm, collection)
    C.assign_slots(obj, with_eyes=False)
    C.smart_uv(obj)
    return obj
