# Mass properties of the airship hull body the way UE 5.8 / Chaos computes them, from the 8 UCX convexes of SM_Airship
# (Docs/Airship/sims/fix2/ucx.json, Blender metres: +X bow, +Y port, +Z up; UE hull space = (100x, -100y, 100z) cm).
#
# Engine path ported (source read in /mnt/new_partition/5.8):
#   Chaos MassProperties.cpp  CalculateVolumeAndCenterOfMassImpl, CalculateInertiaAndRotationOfMassImpl (fan-triangulated
#                             surface integrals, uniform density), CombineWorldSpace (parallel axis), TransformToLocalSpace
#                             (trigonometric 3x3 eigen solve: returns diag(LARGEST, SMALLEST, MIDDLE) + RotationOfMass)
#   Engine BodyUtils.cpp      ApplyMassPropertiesModifiers: mass override (inertia x MassRatio), COM nudge, and with
#                             p.ComNudgeAffectsInertia (default true) Ixx += m dx^2, Iyy += m dy^2, Izz += m dz^2 (diagonal
#                             only, as the engine does), then TransformToLocalSpace again.
#   UAirshipFlightComponent::ApplyBodySettings: MassKg 40000, COM moved to DesiredCenterOfMass (-170, 0, 0).
#
# Result used by airship_sim.py (hull_mass.json):
#   tensor_actor   the true 3x3 inertia in hull axes (kg cm^2): what Chaos integrates with
#   chaos_I        what UPrimitiveComponent::GetInertiaTensor() returns: the principal values in Chaos order
#                  (largest, smallest, middle), NOT (roll, pitch, yaw). The flight component multiplies its hull-axis
#                  angular accelerations by these components (TauX = I.X * alpha_roll, ...), see airship_sim.py.
#
# Run: python3 mass_props.py   (writes hull_mass.json next to this file, < 1 s)
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
UCX_JSON = os.path.join(HERE, '..', '..', 'sims', 'fix2', 'ucx.json')
OUT_JSON = os.path.join(HERE, 'hull_mass.json')

MASS_KG = 40000.0
DESIRED_COM = (-170.0, 0.0, 0.0)
SMALL = 1e-8          # UE_SMALL_NUMBER
KINDA_SMALL = 1e-4    # UE_KINDA_SMALL_NUMBER


# ------------------------------------------------------------------------------------------------ small 3x3 helpers
def mat_zero():
    return [[0.0] * 3 for _ in range(3)]


def mat_add(a, b):
    return [[a[i][j] + b[i][j] for j in range(3)] for i in range(3)]


def mat_scale(a, s):
    return [[a[i][j] * s for j in range(3)] for i in range(3)]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_t(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vnorm(a):
    s = math.sqrt(vdot(a, a))
    return (a[0] / s, a[1] / s, a[2] / s) if s > 1e-30 else (0.0, 0.0, 0.0)


# ------------------------------------------------------------------------------------------------ convex surfaces
def ue_point(p):
    """Blender metres -> UE hull space cm."""
    return (100.0 * p[0], -100.0 * p[1], 100.0 * p[2])


def convex_hull_triangles(points):
    """Outward triangles of the 3D convex hull of points (incremental hull). UE builds each UCX element's convex
    from its vertices the same way (FKConvexElem -> Chaos FConvex), so this is the shape Chaos integrates."""
    pts = [tuple(p) for p in points]
    n = len(pts)
    scale = max(max(abs(c) for c in p) for p in pts) or 1.0
    eps = 1e-7 * scale

    def plane(a, b, c):
        nrm = vcross(vsub(pts[b], pts[a]), vsub(pts[c], pts[a]))
        ln = math.sqrt(vdot(nrm, nrm))
        return (nrm[0] / ln, nrm[1] / ln, nrm[2] / ln) if ln > 0 else (0.0, 0.0, 0.0)

    def dist(face, p):
        nrm = plane(*face)
        return vdot(nrm, vsub(pts[p], pts[face[0]]))

    # initial tetrahedron
    i0 = 0
    i1 = max(range(n), key=lambda i: vdot(vsub(pts[i], pts[i0]), vsub(pts[i], pts[i0])))
    def line_d(i):
        d = vcross(vsub(pts[i1], pts[i0]), vsub(pts[i], pts[i0]))
        return vdot(d, d)
    i2 = max(range(n), key=line_d)
    i3 = max(range(n), key=lambda i: abs(vdot(plane(i0, i1, i2), vsub(pts[i], pts[i0]))))
    centroid = tuple(sum(pts[i][k] for i in (i0, i1, i2, i3)) / 4.0 for k in range(3))
    faces = []
    for f in ((i0, i1, i2), (i0, i1, i3), (i0, i2, i3), (i1, i2, i3)):
        if vdot(plane(*f), vsub(centroid, pts[f[0]])) > 0:
            f = (f[0], f[2], f[1])
        faces.append(f)
    for p in range(n):
        if p in (i0, i1, i2, i3):
            continue
        visible = [f for f in faces if dist(f, p) > eps]
        if not visible:
            continue
        edges = {}
        for f in visible:
            for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                edges[e] = edges.get(e, 0) + 1
        horizon = [e for e in edges if (e[1], e[0]) not in edges]
        faces = [f for f in faces if f not in visible]
        for a, b in horizon:
            faces.append((a, b, p))
    return [[pts[a], pts[b], pts[c]] for a, b, c in faces]


def hull_triangles(hull):
    return convex_hull_triangles([ue_point(v) for v in hull['verts']])


def volume_com(polys):
    """Chaos CalculateVolumeAndCenterOfMassImpl (fan triangulation, centre = first vertex of the first face)."""
    center = polys[0][0]
    volume = 0.0
    vts = [0.0, 0.0, 0.0]
    for poly in polys:
        for k in range(len(poly) - 2):
            tri = (poly[0], poly[k + 1], poly[k + 2])
            d = [vsub(p, center) for p in tri]
            dm = [[d[i][r] for i in range(3)] for r in range(3)]   # columns = the three deltas
            per = [dm[r][0] + dm[r][1] + dm[r][2] for r in range(3)]
            det = det3(dm)
            volume += det
            for r in range(3):
                vts[r] += det * per[r]
    com = tuple(center[r] + vts[r] / (4.0 * volume) for r in range(3))
    return volume / 6.0, com


def inertia_about(polys, density, com):
    """Chaos CalculateInertiaAndRotationOfMassImpl before its TransformToLocalSpace: the full tensor about com."""
    std = [[2.0, 1.0, 1.0], [1.0, 2.0, 1.0], [1.0, 1.0, 2.0]]
    cov = mat_zero()
    for poly in polys:
        for k in range(len(poly) - 2):
            tri = (poly[0], poly[k + 1], poly[k + 2])
            d = [vsub(p, com) for p in tri]
            dm = [[d[i][r] for i in range(3)] for r in range(3)]
            det = det3(dm)
            cov = mat_add(cov, mat_mul(mat_mul(dm, mat_scale(std, det)), mat_t(dm)))
    tr = cov[0][0] + cov[1][1] + cov[2][2]
    inertia = [[(tr if i == j else 0.0) - cov[i][j] for j in range(3)] for i in range(3)]
    return mat_scale(inertia, density / 120.0)


# ------------------------------------------------------------------------------------------------ Chaos eigen solve
def eigenvector(m, lam):
    """Unit eigenvector of the symmetric 3x3 m for eigenvalue lam (largest cross product of two rows of m - lam I)."""
    a = [[m[i][j] - (lam if i == j else 0.0) for j in range(3)] for i in range(3)]
    cands = [vcross(a[0], a[1]), vcross(a[0], a[2]), vcross(a[1], a[2])]
    best = max(cands, key=lambda c: vdot(c, c))
    v = vnorm(best)
    # sign: the largest component positive (only for readability)
    k = max(range(3), key=lambda i: abs(v[i]))
    return tuple(-c for c in v) if v[k] < 0 else v


def transform_to_local_space(inertia):
    """Chaos::TransformToLocalSpace eigenvalues: diag (m00, m11, m22) = (largest, smallest, middle) from the
    trigonometric solve, unless the tensor is already (almost) diagonal (then the hull-axis diagonal is kept).
    Returns (diag, principal axes as rows in the input frame, diagonalized?)."""
    off2 = inertia[1][0] ** 2 + inertia[2][0] ** 2 + inertia[2][1] ** 2
    trace = (inertia[0][0] + inertia[1][1] + inertia[2][2]) / 3.0
    if trace <= SMALL or off2 / trace ** 2 < SMALL:
        return (inertia[0][0], inertia[1][1], inertia[2][2]), [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], False
    size_ = math.sqrt(((inertia[0][0] - trace) ** 2 + (inertia[1][1] - trace) ** 2 + (inertia[2][2] - trace) ** 2
                       + 2.0 * off2) / 6.0)
    newm = [[(inertia[i][j] - (trace if i == j else 0.0)) / size_ for j in range(3)] for i in range(3)]
    half_det = det3(newm) / 2.0
    ang = math.pi / 3 if half_det <= -1 else (0.0 if half_det >= 1 else math.acos(half_det) / 3.0)
    m00 = trace + 2 * size_ * math.cos(ang)
    m11 = trace + 2 * size_ * math.cos(ang + 2 * math.pi / 3)
    m22 = 3 * trace - m00 - m11
    rows = [list(eigenvector(inertia, lam)) for lam in (m00, m11, m22)]
    return (m00, m11, m22), rows, True


def main():
    data = json.load(open(UCX_JSON))
    hulls = {k: v for k, v in data.items() if k.startswith('UCX')}
    parts = []
    density = 1.0  # any; the mass override rescales
    for name, hull in sorted(hulls.items()):
        polys = hull_triangles(hull)
        vol, com = volume_com(polys)
        inertia = inertia_about(polys, density, com)
        parts.append({'name': name, 'volume': vol, 'com': com, 'mass': vol * density, 'inertia': inertia,
                      'triangles': len(polys)})

    # CombineWorldSpace: sum of tensors + parallel axis
    mass = sum(p['mass'] for p in parts)
    com = tuple(sum(p['com'][i] * p['mass'] for p in parts) / mass for i in range(3))
    tensor = mat_zero()
    for p in parts:
        tensor = mat_add(tensor, p['inertia'])
        d = vsub(p['com'], com)
        m = p['mass']
        tensor = mat_add(tensor, [[m * (d[1] ** 2 + d[2] ** 2), -m * d[0] * d[1], -m * d[0] * d[2]],
                                  [-m * d[0] * d[1], m * (d[0] ** 2 + d[2] ** 2), -m * d[1] * d[2]],
                                  [-m * d[0] * d[2], -m * d[1] * d[2], m * (d[0] ** 2 + d[1] ** 2)]])

    # ApplyMassPropertiesModifiers: mass override, COM nudge, nudge -> inertia (diagonal only, as the engine does)
    ratio = MASS_KG / mass
    tensor = mat_scale(tensor, ratio)
    nudge = vsub(DESIRED_COM, com)
    for i in range(3):
        tensor[i][i] += MASS_KG * nudge[i] ** 2
    diag, rows, rotated = transform_to_local_space(tensor)

    out = {
        'source': 'Docs/Airship/sims/fix2/ucx.json (8 UCX convexes, uniform density)',
        'mass_kg': MASS_KG,
        'natural_com_cm': [round(c, 2) for c in com],
        'com_nudge_cm': [round(c, 2) for c in nudge],
        'com_cm': list(DESIRED_COM),
        'tensor_actor_kgcm2': [[float('%.6g' % tensor[i][j]) for j in range(3)] for i in range(3)],
        'chaos_I_kgcm2': [float('%.6g' % x) for x in diag],
        'chaos_principal_axes_rows': [[round(c, 5) for c in r] for r in rows],
        'chaos_diagonalized': rotated,
        'hull_axis_I_kgcm2': [float('%.6g' % tensor[i][i]) for i in range(3)],
        'parts': [{'name': p['name'], 'volume_m3': round(p['volume'] / 1e6, 2), 'com_cm': [round(c, 1) for c in p['com']],
                   'hull_triangles': p['triangles']} for p in parts],
        'note': ('GetInertiaTensor() returns chaos_I in the principal frame (largest, smallest, middle). The flight '
                 'component uses its components as if they were (roll, pitch, yaw) about the hull axes.'),
    }
    json.dump(out, open(OUT_JSON, 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
