"""Zone 6 helpers (round 3): pose matrices, posed BVHs of the moving ship parts, per-piece clearance tests, a small 2D
free-cell grid with a largest-free-rectangle search, and polygon helpers for flat faces (rudder). Zone 6 only: the
shared modules are not changed.
"""
import math
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D


def xform(P, M):
    M = np.asarray(M)
    P = np.asarray(P, float)
    return P @ M[:3, :3].T + M[:3, 3]


# ------------------------------------------------------------------ pose matrices (rest-world, like rig_common.apply_pose)
def yaw_M(spec, s, deg):
    return np.array(C.rot_about(spec['bones']['Turbine_' + s]['head'], (0, 0, -1), deg))


def spin_M(spec, s, deg):
    return np.array(C.rot_about(spec['bones']['Turbine_%s_Rotor' % s]['head'], (1, 0, 0), deg))


def rod_M(spec, s, a, b):
    h = spec['bones']['Turbine_%s_Rod' % s]['head']
    return np.array(C.rot_about(h, (0, 1, 0), a) @ C.rot_about(h, (1, 0, 0), b))


def rudder_M(spec, deg):
    return np.array(C.rot_about(spec['bones']['Rudder']['head'], (0, 0, 1), deg))


# ------------------------------------------------------------------ ship geometry by bone / island, optionally posed
class ShipGeo:
    def __init__(self, ship, keep):
        self.ship = ship
        self.keep = np.asarray(keep, bool)
        self.pb = ship.p_bone.astype(str)

    def mask(self, bones=None, islands=None, islands_ex=()):
        m = self.keep.copy()
        if bones is not None:
            m &= np.isin(self.pb, list(bones))
        if islands is not None:
            m &= np.isin(self.ship.p_island, list(islands))
        if len(islands_ex):
            m &= ~np.isin(self.ship.p_island, list(islands_ex))
        return m

    def bvh(self, mask, M=None, extra=()):
        """BVH of the masked SM_Airship faces (+ detail Mesh builders in `extra`), all moved by M (4x4) if given"""
        co = self.ship.co if M is None else xform(self.ship.co, M)
        polys = [self.ship.polys[i] for i in np.nonzero(mask)[0]]
        cos = [co]
        off = len(co)
        for m in extra:
            if not m.f:
                continue
            v = np.asarray(m.v, float)
            if M is not None:
                v = xform(v, M)
            cos.append(v)
            polys = polys + [[i + off for i in f] for f in m.f]
            off += len(v)
        return BVHTree.FromPolygons(np.concatenate(cos).tolist(), polys)


def piece_tree(tmp, M=None):
    v = np.asarray(tmp.v, float)
    if M is not None:
        v = xform(v, M)
    return BVHTree.FromPolygons(v.tolist(), [list(f) for f in tmp.f])


def pa_bad(P, boxes):
    """vertices standing above a PA_Airship hull box top inside its footprint (Blender metres)"""
    P = np.asarray(P, float)
    bad = np.zeros(len(P), bool)
    for mn, mx in boxes:
        bad |= (P[:, 0] >= mn[0]) & (P[:, 0] <= mx[0]) & (P[:, 1] >= mn[1]) & (P[:, 1] <= mx[1]) & (P[:, 2] > mx[2])
    return bad


def check_piece(tmp, checks):
    """checks: list of tuples
         ('static', bvh, name)            piece at rest must not intersect bvh
         ('targets', [bvh, ..], name)     piece at rest vs posed targets (the moving ship parts in their poses)
         ('moved', [(M, bvh), ..], name)  the piece moves with its bone: moved by M vs a fixed target
         ('fn', f(P) -> bool array, name) a vertex predicate (True = bad)
       returns the name of the first failing check, or None"""
    if not tmp.f:
        return None
    t0 = None
    for c in checks:
        kind, arg, name = c
        if kind == 'static':
            t0 = t0 or piece_tree(tmp)
            if t0.overlap(arg):
                return name
        elif kind == 'targets':
            t0 = t0 or piece_tree(tmp)
            for b in arg:
                if t0.overlap(b):
                    return name
        elif kind == 'moved':
            for M, b in arg:
                if piece_tree(tmp, M).overlap(b):
                    return name
        elif kind == 'fn':
            if np.asarray(arg(np.asarray(tmp.v, float))).any():
                return name
    return None


class Part:
    """one detail object (one bone): accepted pieces go into .mesh; rejected ones are counted by label and reason"""

    def __init__(self, name, bone):
        self.name, self.bone = name, bone
        self.mesh = D.Mesh(name)
        self.mesh.cur_group = bone
        self.stats = {}

    def new(self):
        t = D.Mesh('tmp')
        t.cur_group = self.bone
        return t

    def accept(self, tmp, checks, label):
        st = self.stats.setdefault(label, {'built': 0})
        if not tmp.f:
            return False
        why = check_piece(tmp, checks)
        if why:
            st[why] = st.get(why, 0) + 1
            return False
        self.mesh.extend(tmp)
        st['built'] += 1
        return True


# ------------------------------------------------------------------ 2D free-cell grid
def maxrect(free, i0, i1, j0, j1):
    """largest all-True rectangle of free[i0:i1, j0:j1]: (i0, i1, j0, j1) half-open, or None"""
    i0, j0 = max(i0, 0), max(j0, 0)
    i1, j1 = min(i1, free.shape[0]), min(j1, free.shape[1])
    if i1 <= i0 or j1 <= j0:
        return None
    best, br = 0, None
    h = np.zeros(j1 - j0, int)
    for i in range(i0, i1):
        h = np.where(free[i, j0:j1], h + 1, 0)
        stack = []
        for k in range(len(h) + 1):
            cur = int(h[k]) if k < len(h) else 0
            start = k
            while stack and stack[-1][1] >= cur:
                s, hh = stack.pop()
                a = hh * (k - s)
                if a > best:
                    best, br = a, (i - hh + 1, i + 1, j0 + s, j0 + k)
                start = s
            stack.append((start, cur))
    return br


# ------------------------------------------------------------------ flat polygons (x, z) for the rudder faces
def poly_area(P):
    P = np.asarray(P, float)
    return 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))


def inset_poly(P, d):
    """offset a convex polygon inward by d (mitred corners)"""
    P = np.asarray(P, float)
    n = len(P)
    ccw = poly_area(P) > 0
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        t = D.unit(np.array([b[0] - a[0], b[1] - a[1], 0.0]))[:2]
        nn = np.array([-t[1], t[0]]) if ccw else np.array([t[1], -t[0]])      # inward normal
        lines.append((a + nn * d, t))
    out = []
    for i in range(n):
        (p1, t1), (p2, t2) = lines[i - 1], lines[i]
        A = np.array([t1, -t2]).T
        s = np.linalg.solve(A, p2 - p1)
        out.append(p1 + t1 * s[0])
    return np.array(out)


def clip_half(P, keep):
    """Sutherland-Hodgman: clip polygon P (k, 2) to the half plane keep(point) -> signed value >= 0"""
    out = []
    n = len(P)
    for i in range(n):
        a, b = np.asarray(P[i - 1], float), np.asarray(P[i], float)
        fa, fb = keep(a), keep(b)
        if fb >= 0:
            if fa < 0:
                out.append(a + (b - a) * (fa / (fa - fb)))
            out.append(b)
        elif fa >= 0:
            out.append(a + (b - a) * (fa / (fa - fb)))
    return np.array(out) if out else np.zeros((0, 2))


def x_span_at(P, z):
    """(x_min, x_max) of a convex polygon (x, z) at height z, or None"""
    xs = []
    n = len(P)
    for i in range(n):
        a, b = P[i - 1], P[i]
        if (a[1] - z) * (b[1] - z) <= 0 and abs(b[1] - a[1]) > 1e-9:
            xs.append(a[0] + (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]))
    if len(xs) < 2:
        return None
    return min(xs), max(xs)
