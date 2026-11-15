# Mech Sentinel head: near mesh (SM_MechSentinel_Head, with SOCKET_Tentacle_XX children) and far LOD
# (SM_MechSentinel_Far, simplified head + 8 baked trailing tentacles).
# Faceted hard-surface low poly, built procedurally with bmesh (deterministic, no randomness).
# Axes / units follow mech_art_contract.md: meters, nose = +X, up = +Z, origin = center of the head body.

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import mech_sentinel_common as C

HEAD_NAME = "SM_MechSentinel_Head"
FAR_NAME = "SM_MechSentinel_Far"

MAT_BODY = 0
MAT_EYES = 1

# Rear collar socket ring (shared by the near head sockets, the far LOD tentacles and the hero preview).
SOCKET_X = -1.0                 # m, on the rear collar
SOCKET_RING_Y = 0.31            # ring half-width (Y)
SOCKET_RING_Z = 0.27            # ring half-height (Z): slightly squashed
SOCKET_RING_Z_OFFSET = -0.05    # ring centre biased downwards
SOCKET_FAN_DEG = 20.0           # outward fan of the rest direction away from -X
SOCKET_DROOP = 0.08             # extra downward component of the rest direction (before normalising)

# Far LOD tentacles.
FAR_TENTACLE_LENGTH = 1.9
FAR_TENTACLE_POINTS = 8         # 7 segments
FAR_TENTACLE_SIDES = 5
FAR_TENTACLE_ROOT_RADIUS = C.TENTACLE_ROOT_DIAMETER * 0.5
FAR_TENTACLE_TIP_RADIUS = 0.022


# ---------------------------------------------------------------------------------------------------------------------
# Sockets

def get_socket_frames():
    """8 (location, direction) pairs in head space (== world space of the built head): one per tentacle socket.

    Location is on the rear collar; direction is the tentacle rest direction (mostly -X, fanned outward ~20 deg,
    with a slight droop). Index i matches SOCKET_Tentacle_{i:02d}.
    """
    frames = []
    fan = math.radians(SOCKET_FAN_DEG)
    for i in range(C.NUM_TENTACLES):
        a = math.radians(22.5 + 45.0 * i)  # no socket exactly at top / bottom
        ca, sa = math.cos(a), math.sin(a)
        loc = Vector((SOCKET_X, SOCKET_RING_Y * ca, SOCKET_RING_Z_OFFSET + SOCKET_RING_Z * sa))
        direction = Vector((-math.cos(fan), math.sin(fan) * ca, math.sin(fan) * sa - SOCKET_DROOP)).normalized()
        frames.append((loc, direction))
    return frames


# ---------------------------------------------------------------------------------------------------------------------
# Low level bmesh helpers

def _basis(axis):
    """Right handed (u, v, w) with w = axis (u x v = w)."""
    w = Vector(axis).normalized()
    hint = Vector((0.0, 0.0, 1.0)) if abs(w.z) < 0.9 else Vector((0.0, 1.0, 0.0))
    u = hint.cross(w).normalized()
    v = w.cross(u).normalized()
    return u, v, w


def _ring(bm, x, r, n, keel=0.0, belly=1.0, width=1.0, slant=0.0, z0=0.0, phase=0.0):
    """Cross-section ring around the X axis. Vertex 0 at +Y, counter-clockwise seen from +X (n/4 is the top).
    keel pushes the dorsal vertex out (ridge), belly < 1 flattens the underside, slant shifts the top along X."""
    verts = []
    for i in range(n):
        a = 2.0 * math.pi * i / n + phase
        c, s = math.cos(a), math.sin(a)
        rr = r * (1.0 + keel * max(0.0, s) ** 6)
        y = rr * c * width
        z = rr * s * (belly if s < 0.0 else 1.0)
        verts.append(bm.verts.new((x + slant * s, y, z + z0)))
    return verts


def _bridge(bm, a, b, mat=MAT_BODY):
    """Quads between two rings of equal size (a = earlier in the profile)."""
    faces = []
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((a[i], b[i], b[j], a[j]))
        f.material_index = mat
        faces.append(f)
    return faces


def _fan(bm, apex, ring, mat=MAT_BODY, flip=False):
    faces = []
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((apex, ring[i], ring[j]) if not flip else (apex, ring[j], ring[i]))
        f.material_index = mat
        faces.append(f)
    return faces


def _ngon(bm, ring, mat=MAT_BODY, flip=False):
    f = bm.faces.new(ring if not flip else list(reversed(ring)))
    f.material_index = mat
    return f


def _pod_ring(bm, center, u, v, w, depth, radius, sides, phase=0.0, squash=1.0):
    verts = []
    for i in range(sides):
        a = 2.0 * math.pi * i / sides + phase
        p = center + w * depth + u * (radius * math.cos(a)) + v * (radius * math.sin(a) * squash)
        verts.append(bm.verts.new(p))
    return verts


def _build_profile(bm, profile, n, front_apex, rear_apex, body_mat=MAT_BODY):
    """Surface of revolution from a front->back profile [(x, r, keel, belly, slant)], closed by two fans."""
    rings = [_ring(bm, x, r, n, keel=k, belly=b, slant=s) for (x, r, k, b, s) in profile]
    for ra, rb in zip(rings[:-1], rings[1:]):
        _bridge(bm, ra, rb, body_mat)
    front = bm.verts.new(front_apex)
    rear = bm.verts.new(rear_apex)
    _fan(bm, front, rings[0], body_mat)
    _fan(bm, rear, rings[-1], body_mat, flip=True)
    return rings


def _eye_pod(bm, center, axis, radius, sides=6, embed=0.05, rim_h=0.022, lens_h=0.03, phase=0.0, simple=False):
    """Closed eye pod: armoured hex housing (slot 0) with a faceted lens dome (slot 1)."""
    u, v, w = _basis(axis)
    center = Vector(center)
    base = _pod_ring(bm, center, u, v, w, -embed, radius * 1.05, sides, phase)
    rim = _pod_ring(bm, center, u, v, w, rim_h, radius, sides, phase)
    _bridge(bm, rim, base, MAT_BODY)
    _ngon(bm, base, MAT_BODY, flip=True)
    if simple:
        apex = bm.verts.new(center + w * (rim_h + lens_h))
        _fan(bm, apex, rim, MAT_EYES)
        return
    lens = _pod_ring(bm, center, u, v, w, rim_h - 0.006, radius * 0.72, sides, phase)
    _bridge(bm, rim, lens, MAT_BODY)  # inner bevel of the housing
    apex = bm.verts.new(center + w * (rim_h + lens_h))
    _fan(bm, apex, lens, MAT_EYES)


def _tube(bm, points, radii, sides, mat=MAT_BODY, phase=0.0, squash=1.0, up_hint=None):
    """Closed tapered tube along a polyline (parallel transported frame). radius 0 at the end -> pointed tip."""
    pts = [Vector(p) for p in points]
    tangents = []
    for i in range(len(pts)):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
        tangents.append(t.normalized())
    w = tangents[0]
    hint = Vector(up_hint) if up_hint is not None else Vector((0.0, 0.0, 1.0))
    if abs(hint.normalized().dot(w)) > 0.95:
        hint = Vector((0.0, 1.0, 0.0))
    u = hint.cross(w).normalized()
    rings = []
    tip = None
    for i, (p, t, r) in enumerate(zip(pts, tangents, radii)):
        if i > 0:
            u = (u - t * u.dot(t)).normalized()
        v = t.cross(u).normalized()
        if r <= 1e-6:
            tip = bm.verts.new(p)
            break
        rings.append(_pod_ring(bm, p, u, v, t, 0.0, r, sides, phase, squash))
    # rings run start -> end along +t: bridge(back, front) gives outward normals
    for ra, rb in zip(rings[:-1], rings[1:]):
        _bridge(bm, rb, ra, mat)
    _ngon(bm, rings[0], mat, flip=True)
    if tip is not None:
        _fan(bm, tip, rings[-1], mat)
    else:
        _ngon(bm, rings[-1], mat)
    return rings


def _finish_bmesh(bm):
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = False


def _clear_selection():
    for o in bpy.context.view_layer.objects:
        o.select_set(False)


# ---------------------------------------------------------------------------------------------------------------------
# Near head

# Front -> back profile of the armoured mantle: (x, radius, keel, belly, slant).
# Each carapace plate is a widening cone whose rear rim overhangs the next plate (undercut lip = dark shadow line).
_HEAD_N = 12
_HEAD_PROFILE = [
    # face dome edge / brow
    (1.080, 0.200, 0.00, 0.90, 0.00),
    (1.030, 0.330, 0.00, 0.88, 0.00),
    # plate 1 (crown): the widest part, a bulbous front like a squid mantle seen from the front
    (0.980, 0.400, 0.03, 0.86, 0.00),
    (0.600, 0.510, 0.08, 0.86, 0.00),
    (0.640, 0.470, 0.06, 0.86, 0.00),
    # plate 2
    (0.630, 0.455, 0.05, 0.86, 0.00),
    (0.220, 0.515, 0.08, 0.86, 0.00),
    (0.260, 0.475, 0.06, 0.86, 0.00),
    # plate 3
    (0.250, 0.460, 0.05, 0.87, 0.00),
    (-0.170, 0.495, 0.08, 0.87, 0.00),
    (-0.130, 0.455, 0.06, 0.87, 0.00),
    # plate 4: the mantle tapers towards the tentacle collar
    (-0.140, 0.435, 0.05, 0.88, 0.00),
    (-0.480, 0.425, 0.07, 0.88, 0.00),
    (-0.440, 0.390, 0.05, 0.88, 0.00),
    # plate 5
    (-0.450, 0.375, 0.04, 0.90, 0.00),
    (-0.700, 0.370, 0.05, 0.90, 0.00),
    (-0.665, 0.335, 0.04, 0.90, 0.00),
    # ribbed collar
    (-0.675, 0.310, 0.00, 0.94, 0.00),
    (-0.715, 0.345, 0.00, 0.94, 0.00),
    (-0.765, 0.345, 0.00, 0.94, 0.00),
    (-0.785, 0.310, 0.00, 0.94, 0.00),
    (-0.825, 0.340, 0.00, 0.94, 0.00),
    (-0.875, 0.340, 0.00, 0.94, 0.00),
    (-0.895, 0.305, 0.00, 0.94, 0.00),
    # rear port cone carrying the tentacle sockets
    (-0.915, 0.340, 0.00, 0.94, 0.00),
    (-1.070, 0.180, 0.00, 0.94, 0.00),
]
_HEAD_FRONT_APEX = (1.115, 0.0, 0.0)
_HEAD_REAR_APEX = (-1.120, 0.0, -0.02)

# Eye cluster on the face dome: (y, z, radius). 8 lenses, spider-like arrangement.
_EYES = [
    (0.095, 0.030, 0.068), (-0.095, 0.030, 0.068),
    (0.190, 0.150, 0.045), (-0.190, 0.150, 0.045),
    (0.210, -0.080, 0.050), (-0.210, -0.080, 0.050),
    (0.000, 0.180, 0.045),
    (0.000, -0.130, 0.050),
]


def _face_x(rho, profile, apex_x):
    """x of the face dome at radial distance rho (piecewise linear through the apex and the first profile rings)."""
    pts = [(0.0, apex_x)] + [(r, x) for (x, r, _k, _b, _s) in profile[:2]]
    for (r0, x0), (r1, x1) in zip(pts[:-1], pts[1:]):
        if rho <= r1:
            t = (rho - r0) / (r1 - r0)
            return x0 + (x1 - x0) * t
    return pts[-1][1]


def _build_head_bmesh():
    bm = bmesh.new()
    _build_profile(bm, _HEAD_PROFILE, _HEAD_N, _HEAD_FRONT_APEX, _HEAD_REAR_APEX)

    # eye cluster
    for (y, z, r) in _EYES:
        rho = math.hypot(y, z)
        x = _face_x(rho, _HEAD_PROFILE, _HEAD_FRONT_APEX[0])
        outward = Vector((0.0, y, z)).normalized() if rho > 1e-6 else Vector((0.0, 0.0, 0.0))
        axis = Vector((1.0, 0.0, 0.0)) + outward * (0.35 * rho / 0.3)
        _eye_pod(bm, (x - 0.004, y, z), axis, r, sides=6, embed=0.05, phase=math.pi / 6.0)

    # mandibles: hooked claws under the face, curling inwards
    for side in (1.0, -1.0):
        pts = [(0.86, 0.17 * side, -0.22), (1.00, 0.20 * side, -0.33), (1.12, 0.17 * side, -0.40),
               (1.20, 0.10 * side, -0.40), (1.235, 0.04 * side, -0.35)]
        radii = [0.06, 0.05, 0.036, 0.02, 0.0]
        _tube(bm, pts, radii, 4, MAT_BODY, phase=math.pi / 4.0)

    # tentacle ports: armoured hex bosses on the rear port cone, one per socket
    for loc, d in get_socket_frames():
        u, v, w = _basis(d)
        base = _pod_ring(bm, loc, u, v, w, -0.13, 0.12, 6, math.pi / 6.0)
        top = _pod_ring(bm, loc, u, v, w, 0.0, 0.115, 6, math.pi / 6.0)
        inner = _pod_ring(bm, loc, u, v, w, -0.012, 0.085, 6, math.pi / 6.0)
        _bridge(bm, top, base)
        _bridge(bm, top, inner)
        _ngon(bm, inner)
        _ngon(bm, base, flip=True)

    _finish_bmesh(bm)
    return bm


def build_head(collection=None):
    """Near head mesh 'SM_MechSentinel_Head' (no tentacles) with SOCKET_Tentacle_00..07 children, UV0, slots
    [Body, Eyes]. Object sits at the origin with identity transform."""
    bm = _build_head_bmesh()
    obj = C.mesh_object_from_bmesh(HEAD_NAME, bm, collection)
    C.assign_slots(obj, with_eyes=True)
    C.apply_transforms(obj)
    C.smart_uv(obj, angle_deg=55.0, margin=0.008)
    for i, (loc, d) in enumerate(get_socket_frames()):
        C.add_socket(obj, i, loc, d, collection)
    return obj


# ---------------------------------------------------------------------------------------------------------------------
# Far LOD

_FAR_N = 8
_FAR_PROFILE = [
    (1.050, 0.300, 0.00, 0.88, 0.00),
    (0.960, 0.410, 0.03, 0.86, 0.00),
    (0.560, 0.515, 0.08, 0.86, 0.00),
    (0.600, 0.470, 0.06, 0.86, 0.00),
    (0.180, 0.520, 0.08, 0.86, 0.00),
    (0.220, 0.475, 0.06, 0.86, 0.00),
    (-0.480, 0.425, 0.07, 0.88, 0.00),
    (-0.440, 0.390, 0.05, 0.88, 0.00),
    (-0.880, 0.340, 0.00, 0.92, 0.00),
    (-1.060, 0.190, 0.00, 0.94, 0.00),
]
_FAR_FRONT_APEX = (1.110, 0.0, 0.0)
_FAR_REAR_APEX = (-1.120, 0.0, -0.02)


def trailing_tentacle_points(index, length=FAR_TENTACLE_LENGTH, count=FAR_TENTACLE_POINTS, frames=None):
    """Points of a trailing, drooping S-curve tentacle starting at socket `index` (head space).

    The curve leaves along the socket direction, bends back/down under a little gravity and swings sideways
    in a gentle S. Returned points are equally spaced along the curve; total length == `length`.
    """
    frames = frames or get_socket_frames()
    loc, d = frames[index]
    radial = Vector((0.0, d.y, d.z))
    radial = radial.normalized() if radial.length > 1e-6 else Vector((0.0, 0.0, -1.0))
    rest = (Vector((-1.0, 0.0, 0.0)) + radial * 0.22 + Vector((0.0, 0.0, -0.42))).normalized()
    side = rest.cross(Vector((0.0, 0.0, 1.0)))
    side = side.normalized() if side.length > 1e-6 else Vector((0.0, 1.0, 0.0))
    up = side.cross(rest).normalized()
    phase = 0.9 * index
    amp = 0.55 if index % 2 == 0 else -0.55
    steps = 96
    ds = length / steps
    dense = [loc.copy()]
    p = loc.copy()
    for k in range(steps):
        t = (k + 0.5) / steps
        blend = min(1.0, t * 2.2)
        blend = blend * blend * (3.0 - 2.0 * blend)
        heading = d.lerp(rest, blend)
        wiggle = math.sin(2.0 * math.pi * (t * 1.15) + phase) * amp * min(1.0, t * 3.0)
        heading = (heading + side * wiggle + up * (0.25 * wiggle * math.cos(phase))).normalized()
        p = p + heading * ds
        dense.append(p.copy())
    # resample to `count` points equally spaced along the polyline
    cum = [0.0]
    for a, b in zip(dense[:-1], dense[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    out = []
    j = 0
    for k in range(count):
        s = total * k / (count - 1)
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg <= 0.0 else (s - cum[j]) / seg
        out.append(dense[j].lerp(dense[j + 1], min(1.0, max(0.0, t))))
    # rescale so the polyline length is exactly `length`
    poly = sum((b - a).length for a, b in zip(out[:-1], out[1:]))
    scale = length / poly if poly > 0 else 1.0
    return [out[0] + (q - out[0]) * scale for q in out]


def _build_far_head_bmesh():
    bm = bmesh.new()
    _build_profile(bm, _FAR_PROFILE, _FAR_N, _FAR_FRONT_APEX, _FAR_REAR_APEX)
    for (y, z, r) in _EYES:
        rho = math.hypot(y, z)
        x = _FAR_FRONT_APEX[0] + (_FAR_PROFILE[0][0] - _FAR_FRONT_APEX[0]) * (rho / _FAR_PROFILE[0][1])
        outward = Vector((0.0, y, z)).normalized() if rho > 1e-6 else Vector((0.0, 0.0, 0.0))
        axis = Vector((1.0, 0.0, 0.0)) + outward * (0.35 * rho / 0.3)
        _eye_pod(bm, (x, y, z), axis, r * 1.1, sides=3, embed=0.04, rim_h=0.0, lens_h=0.035,
                 phase=math.pi / 2.0, simple=True)
    for side in (1.0, -1.0):
        pts = [(0.86, 0.17 * side, -0.22), (1.06, 0.19 * side, -0.37), (1.21, 0.08 * side, -0.40)]
        _tube(bm, pts, [0.06, 0.04, 0.0], 3, MAT_BODY, phase=math.pi / 2.0)
    _finish_bmesh(bm)
    return bm


def _append_object_mesh(bm, obj, material_index):
    """Append an object's evaluated, world-space mesh to `bm`; new faces get `material_index`."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    me = bpy.data.meshes.new_from_object(eval_obj)
    me.transform(obj.matrix_world)
    before = set(bm.faces)
    bm.from_mesh(me)
    for f in bm.faces:
        if f not in before:
            f.material_index = material_index
    bpy.data.meshes.remove(me)


def build_far_lod(tentacle_sweep_fn, collection=None):
    """Far LOD 'SM_MechSentinel_Far': simplified head + 8 trailing tentacles swept with
    tentacle_sweep_fn(points, root_radius, tip_radius, sides, name) -> mesh object. Slots [Body, Eyes]."""
    bm = _build_far_head_bmesh()
    frames = get_socket_frames()
    temp_objects = []
    for i, (loc, d) in enumerate(frames):
        pts = trailing_tentacle_points(i, frames=frames)
        pts[0] = pts[0] - d * 0.06  # root sinks into the port cone: no visible gap
        obj = tentacle_sweep_fn(pts, FAR_TENTACLE_ROOT_RADIUS, FAR_TENTACLE_TIP_RADIUS, FAR_TENTACLE_SIDES,
                                f"TMP_FarTentacle_{i:02d}")
        temp_objects.append(obj)
    bpy.context.view_layer.update()
    for obj in temp_objects:
        _append_object_mesh(bm, obj, MAT_BODY)
    for obj in temp_objects:
        me = obj.data if obj.type == 'MESH' else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    for f in bm.faces:
        f.smooth = False
    far = C.mesh_object_from_bmesh(FAR_NAME, bm, collection)
    C.assign_slots(far, with_eyes=True)
    C.apply_transforms(far)
    C.smart_uv(far, angle_deg=55.0, margin=0.006)
    return far
