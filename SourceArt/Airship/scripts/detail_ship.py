"""Ship-side helpers for the detail pass: which SM_Airship faces are what, target surfaces, the hull flank chart and
the thruster pod frames. Shared by detail_zone1.py and the later zones.

The rig mesh SM_Airship is Talal's mesh minus the 21 deck islands (deck_removals.json); rig vertex i = source vertex
kept_vertex_index()[i], so the research island ids still name every piece (sm_airship_islands.json).
"""
import math
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D

SKIN = C.SHELL_ISLAND          # 392: the closed hull skin (deck surface and the pocket walls are part of it)


class Ship:
    def __init__(self, bpy):
        self.ob = bpy.data.objects[C.HULL_OBJ]
        self.arm = bpy.data.objects['Armature']
        me = self.ob.data
        assert np.allclose(np.array(self.ob.matrix_world), np.eye(4))
        co, polys = C.mesh_arrays(me)
        self.co = co
        self.polys = polys
        VP = C.load_json(C.RESEARCH + '/sm_airship_vertex_parts.json')
        ISL = C.load_json(C.RESEARCH + '/sm_airship_islands.json')
        self.islands = {r['id']: r for r in ISL['islands']}
        self.frames = ISL['frames']
        visl = np.array(VP['vertex_island'])
        keep = C.kept_vertex_index(visl)
        assert len(keep) == len(co), (len(keep), len(co))
        self.v_island = visl[keep]
        vb, _, _ = C.hull_vertex_bones()
        self.v_bone = np.array(vb)[keep]
        self.p_island = np.array([self.v_island[p[0]] for p in polys])
        self.p_bone = np.array([self.v_bone[p[0]] for p in polys])
        self.p_src = np.array([self.islands[i]['src'] for i in self.p_island])
        self.p_piece = np.array([self.islands[i].get('piece', '') for i in self.p_island])
        # check against the armature's own vertex groups (rigid skin): bone of the first vertex of each polygon
        gname = {g.index: g.name for g in self.ob.vertex_groups}
        for k in range(0, len(polys), 97):
            v = me.vertices[polys[k][0]]
            assert gname[v.groups[0].group] == self.p_bone[k], (k, gname[v.groups[0].group], self.p_bone[k])

    def surface(self, mask):
        return D.Surface.from_mesh(self.ob.data, poly_mask=mask)

    def bvh(self, mask):
        idx = [self.polys[i] for i in np.nonzero(mask)[0]]
        return BVHTree.FromPolygons(self.co.tolist(), idx)

    def island_verts(self, ids):
        return self.co[np.isin(self.v_island, list(ids))]

    def pod_frame(self, pod):
        f = self.frames['Pod_' + pod]
        return D.vec(f['origin']), D.vec(f['T0']), D.unit(f['axis_nozzle']), D.vec(f['nozzle_pivot'])


def pod_basis(A):
    """(e0, e90): radial unit vectors at angle 0 (forward-ish) and 90 (port-ish) around the pod axis A, matching the
    angles in research (atan2 of the radial vector's y and x)"""
    x = np.array([1.0, 0.0, 0.0])
    e0 = D.unit(x - A * x.dot(A))
    e90 = np.cross(A, e0)
    if e90[1] < 0:
        e90 = -e90
    return e0, e90


def cyl_point(T0, A, e0, e90, h, ang_deg, r):
    a = math.radians(ang_deg)
    d = e0 * math.cos(a) + e90 * math.sin(a)
    return T0 + A * h + d * r, d


# ------------------------------------------------------------------ hull flank chart
class FlankChart:
    """Rays in the (y, z) plane of each station x, from outside toward an axis point (x, AY, AZ), angle phi (0 = +Y
    horizontal, + = up). Every cell keeps the skin hit (point, smooth normal), whether other geometry is in front of
    it (covered) and the arc length s measured down the section from the deck edge. side = +1 port, -1 starboard."""

    AY, AZ = 1.5, 0.3

    def __init__(self, skin, obst, xs, phis_deg, side=1, clear=0.30):
        self.skin, self.obst, self.side = skin, obst, side
        self.xs = np.asarray(xs, float)
        self.ph = np.radians(np.asarray(phis_deg, float))
        nx, nphi = len(self.xs), len(self.ph)
        self.P = np.full((nx, nphi, 3), np.nan)
        self.N = np.full((nx, nphi, 3), np.nan)
        self.cov = np.zeros((nx, nphi), bool)      # something other than the skin within `clear` above the skin
        self.hit = np.zeros((nx, nphi), bool)
        for i, x in enumerate(self.xs):
            ax = np.array([x, side * self.AY, self.AZ])
            for j, p in enumerate(self.ph):
                d = np.array([0.0, side * math.cos(p), math.sin(p)])
                o = ax + 20.0 * d
                r = skin.ray(o, -d, 30.0)
                if r is None:
                    continue
                self.hit[i, j] = True
                self.P[i, j], self.N[i, j] = r[0], r[1]
                ro = obst.ray_cast(V(o), V(-d), 30.0)
                if ro[0] is not None and ro[3] < r[3] + 0.002 and r[3] - ro[3] < clear + 1.0:
                    self.cov[i, j] = True
        # jumps / creases between neighbours along phi
        self.brk = np.zeros((nx, nphi), bool)       # break between cell j-1 and j
        dp = np.linalg.norm(self.P[:, 1:] - self.P[:, :-1], axis=2)
        dn = np.einsum('ijk,ijk->ij', self.N[:, 1:], self.N[:, :-1])
        bad = ~(dp < 0.2) | ~(dn > math.cos(math.radians(22)))
        self.brk[:, 1:] = bad
        # arc length from the deck edge: the deck edge = the first cell (from the top) whose normal is not deck-up
        self.s = np.full((nx, nphi), np.nan)
        self.edge_j = np.zeros(nx, int)
        for i in range(nx):
            js = [j for j in range(nphi) if self.hit[i, j]]
            if not js:
                continue
            j0 = next((j for j in js if self.N[i, j][2] < 0.75), js[0])
            self.edge_j[i] = j0
            # s = 0 at the deck edge itself, not at the first cell below it (the cells are 0.5 degree apart, so the
            # first cell's distance below the edge jumps from column to column): extrapolate the flank from the
            # first two flank cells up to the deck plane of the last deck cell
            off = 0.0
            if j0 >= 1 and self.hit[i, j0 - 1] and j0 + 1 < nphi and self.hit[i, j0 + 1]:
                zd = self.P[i, j0 - 1][2]
                a, b = self.P[i, j0], self.P[i, j0 + 1]
                dz = a[2] - b[2]
                if dz > 1e-4 and zd >= a[2]:
                    e = a + (a - b) * min((zd - a[2]) / dz, 3.0)
                    off = float(np.linalg.norm(a - e))
            acc = off
            self.s[i, j0] = off
            for j in range(j0 + 1, nphi):
                if not self.hit[i, j]:
                    break
                acc += np.linalg.norm(self.P[i, j] - self.P[i, j - 1]) if not np.isnan(self.P[i, j - 1][0]) else 0.0
                self.s[i, j] = acc

    def free(self):
        return self.hit & ~self.cov & ~np.isnan(self.s)

    def runs(self, i, min_len=0.25):
        """free runs of column i as (j0, j1, s0, s1) from the deck edge downward (no break inside a run)"""
        f = self.free()[i]
        out = []
        j = 0
        n = len(f)
        while j < n:
            if not f[j]:
                j += 1
                continue
            k = j
            while k + 1 < n and f[k + 1] and not self.brk[i, k + 1]:
                k += 1
            if self.s[i, k] - self.s[i, j] >= min_len:
                out.append((j, k, float(self.s[i, j]), float(self.s[i, k])))
            j = k + 1
        return out

    def col(self, x):
        return int(np.clip(np.round((x - self.xs[0]) / (self.xs[1] - self.xs[0])), 0, len(self.xs) - 1))

    def phi_at(self, x, s):
        """angle (rad) of arc length s in the column nearest x (linear inside the column)"""
        i = self.col(x)
        ss = self.s[i]
        ok = ~np.isnan(ss)
        if ok.sum() < 2:
            return None
        js = np.nonzero(ok)[0]
        sv = ss[js]
        if s < sv[0] - 1e-6 or s > sv[-1] + 1e-6:
            return None
        return float(np.interp(s, sv, self.ph[js]))

    def surf(self, x, s):
        """exact skin point + smooth normal at (x, s): ray at the interpolated angle"""
        ph = self.phi_at(x, s)
        if ph is None:
            return None
        ax = np.array([x, self.side * self.AY, self.AZ])
        d = np.array([0.0, self.side * math.cos(ph), math.sin(ph)])
        r = self.skin.ray(ax + 20.0 * d, -d, 30.0)
        if r is None:
            return None
        return r[0], r[1]

    def free_at(self, x, s, pad_s=0.0):
        """is (x, s) on a free cell (and its neighbours within pad_s along the column)?"""
        i = self.col(x)
        ss = self.s[i]
        f = self.free()[i]
        ok = ~np.isnan(ss)
        if not ok.any():
            return False
        pad_s = max(pad_s, 0.035)
        js = np.nonzero(ok & (ss >= s - pad_s - 1e-6) & (ss <= s + pad_s + 1e-6))[0]
        if len(js) == 0:
            return False
        if not f[js].all():
            return False
        # no break inside the span
        return not self.brk[i, js[0] + 1:js[-1] + 1].any()

    def rect_free(self, x0, x1, s0, s1, pad=0.03, step=0.05):
        for x in np.arange(x0 - pad, x1 + pad + 1e-9, step):
            i = self.col(x)
            ss = self.s[i]
            ok = ~np.isnan(ss)
            js = np.nonzero(ok & (ss >= s0 - pad) & (ss <= s1 + pad))[0]
            if len(js) == 0:
                return False
            if ss[js].min() > s0 - pad + 0.06 or ss[js].max() < s1 + pad - 0.06:
                return False
            if not self.free()[i][js].all():
                return False
            if self.brk[i, js[0] + 1:js[-1] + 1].any():
                return False
        return True
