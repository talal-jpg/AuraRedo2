"""Zone 3 (round 3): the rear thruster pods RL / RR and their hull pockets.

The pods use zone 1's shared builder (detail_pod.build_pod, which='RL' / 'RR') for the drum plates, rib rivets, ring
band, the big plates' lips / straps / patches, the side-box lids, the pipe bundle, the junction housing, the nozzle
hoops and fins and the petal hinges / actuators. Its two "hug pipes" and two actuators in the gap under the big
plates are switched off there (K['pod']['hug_th'] empty, 'act_th' empty) and built here instead, because the rear pods
sit deeper in the hull: at zone 1's angles the hull-clearance test drops them (ZONES.md section 10). Here every pipe
and actuator picks the free angles of its own pod (same tests: outside the hull with the 3-degree tilt margin, clear
of the pod's plates and boxes), preferring the sides you see from aft and from below.

The pocket: zone 1's cavity stiffeners (copied from detail_pod.cavity), but the ring rib at a fixed height is replaced
by a riveted rust LIP that follows the real opening edge on the pocket wall (the rim band outside the opening belongs
to zone 1 / zone 2 above the bilge line: their plates come to 9 cm of it).
"""
import bpy, sys, os, math, random, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S
from detail_pod import HullClear, pod_basis_mirrored, pod_islands

RD = 1.85


def _rot_about(pivot, axis, deg):
    from mathutils import Matrix
    p = V(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, V(axis).normalized()) @ Matrix.Translation(-p)


def _xform(co, M):
    M = np.array(M)
    return np.asarray(co, float) @ M[:3, :3].T + M[:3, 3]




class PodTests:
    """the free-space tests of detail_pod.build_pod for one pod (hull clearance with the tilt margin, radial clearance
    of the pod's own plates / boxes)"""

    def __init__(self, ship, which, skin, K):
        self.O, self.T0, self.A, self.NP = ship.pod_frame(which)
        self.e0, self.e90, self.e90r = pod_basis_mirrored(self.A, which)
        self.hc0 = HullClear(skin)
        self.CLR = K['pod']['hull_clear']
        blk_mask = np.isin(ship.p_island, [i for i, r in ship.islands.items()
                                           if r['part'] == 'Pod_' + which and r['piece'] != 'drum'])
        self.blk = ship.bvh(blk_mask)
        pod_mask = np.char.startswith(ship.p_bone.astype(str), 'Thruster_' + which)
        self.pod_bvh = ship.bvh(pod_mask & ~np.char.startswith(ship.p_bone.astype(str), 'Thruster_%s_' % which))
        # every hull-bone face near the pod (skin, steam pipes, tabs ...) and the pod's 9 extreme / rest tilts
        hb = np.nonzero(ship.p_bone == 'Hull')[0]
        cen = np.array([ship.co[ship.polys[i]].mean(0) for i in hb])
        near = hb[np.linalg.norm(cen - self.O, axis=1) < 5.0]
        self.hull_near = BVHTree.FromPolygons(ship.co.tolist(), [ship.polys[i] for i in near])
        hp = np.array(ship.arm.data.bones['Thruster_' + which].head_local)
        self.tilts = [np.array(_rot_about(hp, (0, 1, 0), a) @ _rot_about(hp, (-1, 0, 0), b))
                      for a in (-3.0, 0.0, 3.0) for b in (-3.0, 0.0, 3.0)]

    def motion_ok(self, p, r):
        """a detail point (radius r around it) stays r + 2 cm off every hull-bone face in all 9 pod tilts"""
        p = np.asarray(p, float)
        for M in self.tilts:
            q = M[:3, :3] @ p + M[:3, 3]
            if self.hull_near.find_nearest(V(q), r + 0.02)[0] is not None:
                return False
        return True

    def cyl(self, h, th, r):
        return S.cyl_point(self.T0, self.A, self.e0, self.e90, h, th, r)

    def hc_ok(self, p, m=None):
        m = self.CLR if m is None else m
        L = np.linalg.norm(np.asarray(p) - self.O)
        return self.hc0(p, m + L * math.sin(math.radians(3.0)))

    def radial_free(self, h, th, r_in=RD + 0.07, r_out=3.2):
        p, d = self.cyl(h, th, r_out)
        return self.blk.ray_cast(V(p), V(-d), r_out - r_in)[0] is None


def best_run(oks, ths, prefer, min_n):
    """longest run of consecutive True angles (wrapping round 360) that overlaps the preferred windows, else the
    longest; returns the list of angles or []"""
    n = len(oks)
    if all(oks):
        return list(ths)
    start = next(i for i in range(n) if not oks[i])
    runs, cur = [], []
    for k in range(1, n + 1):
        i = (start + k) % n
        if oks[i]:
            cur.append(ths[i] if not cur or ths[i] > cur[-1] else ths[i] + 360.0)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    runs = [r for r in runs if len(r) >= min_n]
    if not runs:
        return []

    def pref(r):
        for (a, b) in prefer:
            for t in r:
                tt = (t + 180.0) % 360.0 - 180.0
                if a <= tt <= b:
                    return 1
        return 0
    return max(runs, key=lambda r: (pref(r), len(r)))


def hug_pipes_and_actuators(pod, ship, which, K, log, skin):
    """the two thick pipes hugging the drum in its lowest band (h 1.74 .. 2.16, between the last two ribs), clamped,
    ends bent into the drum; two actuators across the gap from the lower rib up to the rib above the big plates. Each
    at the free angles of this pod."""
    PZ = K['pod_z3'][which]
    T = PodTests(ship, which, skin, K)
    ths = np.arange(-180.0, 180.0, 4.0)
    out = dict(hugs=[], acts=[])
    for k_, (hh, rpp, mat) in enumerate(PZ['hugs']):
        rr = RD + 0.012 + rpp
        oks = []
        for th in ths:
            p = T.cyl(hh, th, rr + rpp)[0]
            oks.append(T.radial_free(hh, th, r_in=rr + rpp + 0.01) and T.hc_ok(p) and
                       T.hc_ok(T.cyl(hh, th, RD + 0.02)[0]) and T.motion_ok(T.cyl(hh, th, rr)[0], rpp * 1.3))
        run = best_run(oks, ths, PZ['prefer'], PZ.get('hug_min_n', 7))
        if not run:
            log.setdefault('pod_z3_skipped', []).append('hug pipe %d (%s)' % (k_, which))
            continue
        ta, tb = run[0], run[-1]
        if tb - ta > PZ.get('hug_max_deg', 150.0):          # very long free run: centre a shorter pipe on the preferred side
            mid = (ta + tb) / 2
            ta, tb = mid - PZ['hug_max_deg'] / 2, mid + PZ['hug_max_deg'] / 2
        pts = [T.cyl(hh, ta - 3.0, RD - 0.02)[0]]
        pts += [T.cyl(hh, th, rr)[0] for th in np.arange(ta + 2.0, tb - 1.9, 4.0)]
        pts += [T.cyl(hh, tb + 3.0, RD - 0.02)[0]]
        ncl = max(2, int((tb - ta) / 30.0))

        def pod_surf_fn(pt):
            rel = np.asarray(pt) - T.T0
            hq = rel @ T.A
            dq = D.unit(rel - T.A * hq)
            return T.T0 + T.A * hq + dq * RD, dq
        D.pipe_run(pod, pts, rpp, 0.1, sides=10, mat=mat, flange_at=(0.3, 0.7),
                   clamp_at=[(i + 0.5) / ncl for i in range(ncl)], surf_fn=pod_surf_fn, kind='pod_pipe')
        out['hugs'].append([round(float(ta), 1), round(float(tb), 1), hh])
    # actuators: two, 14 degrees apart, at the free angle nearest to the preferred one
    AR = K['pod']['act_r']
    cand = []
    for th in np.arange(-180.0, 180.0, 2.0):
        a = T.cyl(1.12, th, AR)[0]
        b = T.cyl(2.15, th, AR)[0]
        ok = T.hc_ok(a) and T.hc_ok(b) and T.radial_free(1.6, th, r_in=AR + 0.06) and \
            T.radial_free(1.3, th, r_in=AR + 0.06) and T.motion_ok(a, 0.06) and T.motion_ok(b, 0.06) and \
            T.motion_ok((a + b) / 2, 0.06)
        cand.append((th, ok))
    okset = {round(t): o for t, o in cand}
    if K.get('debug_dir'):
        dbg = []
        for th, _ in cand:
            a = T.cyl(1.12, th, AR)[0]; b = T.cyl(2.15, th, AR)[0]
            dbg.append('%d:%d%d%d%d' % (th, T.hc_ok(a), T.hc_ok(b), T.radial_free(1.6, th, r_in=AR + 0.06),
                                         T.radial_free(1.3, th, r_in=AR + 0.06)))
        log['debug_act_' + which] = ' '.join(dbg)
    pref = PZ['act_pref']
    best = None
    for gap in PZ.get('act_gaps', (14,)):                # zone 1's 14 degrees apart, closer where the free arc is short
        for dth in sorted(set(round(t) for t, _ in cand), key=lambda t: min(abs(((t - pref + 180) % 360) - 180), 999)):
            if abs(((dth - pref + 180) % 360) - 180) > PZ.get('act_window', 60):
                continue
            t2 = dth + gap
            t2w = round(((t2 + 180) % 360) - 180)
            between = [round(((dth + k + 180) % 360) - 180) for k in range(2, gap, 2)]
            if okset.get(dth) and okset.get(t2w) and all(okset.get(t) for t in between):
                best = (dth, t2)
                break
        if best is not None:
            break
    if best is None:
        log.setdefault('pod_z3_skipped', []).append('actuators (%s)' % which)
    else:
        for th in best:
            a = T.cyl(1.12, th, AR)[0]
            b = T.cyl(2.15, th, AR)[0]
            d = T.cyl(0, th, 1)[1]
            D.piston(pod, a, b, r=0.04, eye_axis=np.cross(T.A, d))
            for (hh, pp) in ((1.12, a), (2.15, b)):
                q, dd = T.cyl(hh, th, RD + 0.02)
                D.chamfer_box(pod, D.frame_matrix(q + dd * (AR - RD) * 0.5, np.cross(T.A, dd), T.A, dd), 0.012, 0.05,
                              (AR - RD) * 0.5 + 0.01, 0.004, 'dark_metal', 'piston')
            out['acts'].append(round(float(th), 1))
    log['pod_z3_' + which] = out
    return out


# ================================================================== pocket: wall stiffeners + a lip on the opening edge
def pocket_wall_map(ship, skin, which, K):
    """per angle (every 3 deg): the h range of the pocket wall seen from the axis (rays from the axis outward hit the
    skin at the pocket radius), contiguous from the roof down; None where there is no wall"""
    O, T0, A, NP = ship.pod_frame(which)
    e0, e90, _ = pod_basis_mirrored(A, which)
    R = K['pocket']['r']
    hr = K['pocket']['roof_h']
    out = {}
    for th in np.arange(-180.0, 180.0, 3.0):
        hs = []
        for h in np.arange(hr + 0.06, 2.6, 0.02):
            c = T0 + A * h
            d = S.cyl_point(T0, A, e0, e90, h, th, 1.0)[1]
            r = skin.ray(c, d, 3.5)
            ok = r is not None and abs(r[3] - R) < 0.05 and float(np.dot(r[1], -d)) > 0.5
            if ok:
                hs.append(h)
            elif hs:
                break
        out[float(th)] = (hs[0], hs[-1]) if len(hs) >= 5 else None
    return out


def pocket(hull, ship, skin, which, K, rng, log, zi):
    """wall stiffeners (zone 1's cavity code) and a riveted rust lip along the opening edge, on the wall"""
    O, T0, A, NP = ship.pod_frame(which)
    e0, e90, _ = pod_basis_mirrored(A, which)
    R = K['pocket']['r']
    hr = K['pocket']['roof_h']
    PK = K['pocket_z3']
    wm = pocket_wall_map(ship, skin, which, K)
    T = PodTests(ship, which, skin, K)

    def wall_pt(h, th, inset=0.0):
        p, d = S.cyl_point(T0, A, e0, e90, h, th, R - inset)
        return p, -d

    def pod_r(h, th):
        """outermost pod surface (pod bone only) at (h, th), from outside toward the axis"""
        p, d = S.cyl_point(T0, A, e0, e90, h, th, 3.3)
        hit = T.pod_bvh.ray_cast(V(p), V(-d), 3.3)
        return 0.0 if hit[0] is None else 3.3 - hit[3]

    def clear(h, th, depth):
        """the lip's inner face (R - depth) keeps its distance from the pod at this angle, tilt included"""
        rp = max(pod_r(h + dh, th + dt) for dh in (-0.15, 0.0, 0.15) for dt in (-4.0, 0.0, 4.0))
        if rp == 0.0:
            return True
        L = math.hypot(h + 0.4, rp)
        return R - depth - rp > L * math.sin(math.radians(3.0)) + PK['pod_clear']
    # ---- the lip: a band on the wall just inside the opening edge
    ths = sorted(wm)
    edge = {th: wm[th][1] for th in ths if wm[th] is not None}
    log['pocket_%s_wall' % which] = dict(angles_with_wall=len(edge), of=len(ths),
                                         edge_h=[round(min(edge.values()), 2), round(max(edge.values()), 2)] if edge else None)
    lw, lt = PK['lip_w'], PK['lip_t']
    good = []
    for th in ths:
        if th not in edge:
            good.append(False)
            continue
        he = edge[th]
        ok = clear(he - lw / 2, th, 0.01 + lt) and zi.zone_at(wall_pt(he - lw / 2, th)[0], 0.2) in (PK['zone'],)
        good.append(ok)
    # runs of good angles -> lip pieces (the edge height is smoothed along the run)
    nlip = nr = 0
    i = 0
    runs = []
    while i < len(ths):
        if not good[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(ths) and good[j + 1] and abs(edge[ths[j + 1]] - edge[ths[j]]) < 0.12:
            j += 1
        if j - i >= 4:
            runs.append((i, j))
        i = j + 1
    for (i, j) in runs:
        tt = np.array(ths[i:j + 1])
        hh = np.array([edge[t] for t in tt])
        k = max(1, min(5, len(tt) // 4))
        hs = np.array([hh[max(0, q - k):q + k + 1].min() for q in range(len(hh))])     # stay inside the wall
        th0 = tt[0] + 1.0
        Lu = math.radians(tt[-1] - 1.0 - th0) * R
        if Lu < 0.4:
            continue

        def f(u, v, th0=th0, tt=tt, hs=hs):
            th = th0 + math.degrees(u / R)
            he = float(np.interp(th, tt, hs))
            return wall_pt(he - 0.015 - v, th)
        top_fn, ok = D.solid_plate(hull, f, D.grid_coords(0.0, Lu, 0.16), np.array([0.0, lw / 2, lw]), 0.01, lt, 0.012,
                                   'rust_red', kind='rim')
        if ok:
            nlip += 1
            kb = max(1, int(Lu / K['rivet']['spacing']))
            nr += D.rivet_row(hull, top_fn, [(Lu * (q + 0.5) / kb, lw / 2) for q in range(kb)], r=0.02, h=0.011)
    # ---- wall stiffeners (zone 1's cavity code): vertical dark straps from the roof down to the lip
    nst = 0
    for th in np.arange(-180.0 + 6.0, 180.0 - 5.0, PK['stiff_step']):
        tk = float(3.0 * round(th / 3.0))
        if tk not in wm or wm.get(tk) is None:
            continue
        h0, h1 = wm[tk]
        h1 = min(h1 - lw - 0.04, K['pocket']['cavity_bottom_h'])
        if h1 - (h0 + 0.05) < 0.3:
            continue
        if not (clear(h1, th, 0.055) and clear((h0 + h1) / 2, th, 0.055)):
            continue
        if zi.zone_at(wall_pt((h0 + h1) / 2, th)[0], 0.2) != PK['zone']:
            continue
        w = 0.09

        def fw(u, v, th=th):
            return wall_pt(v, th + math.degrees((u - w / 2) / R))
        top_fn, ok_ = D.solid_plate(hull, fw, np.array([0.0, w]), D.grid_coords(h0 + 0.05, h1, 0.3), 0.01, 0.045, 0.01,
                                    'dark_metal', kind='cavity')
        if ok_:
            nst += 1
            nr += D.rivet_row(hull, top_fn, [(w / 2, h) for h in np.arange(h1 - 0.1, h0 + 0.1, -0.3)], r=0.018, h=0.01)
    log['pocket_' + which] = dict(lip_pieces=nlip, lip_runs=len(runs), stiffeners=nst, rivets=nr)


# ================================================================== the pod's motion range against the hull (build-time)
def _pieces_hit(mesh, co, other):
    """component ids of `mesh` (vertices `co`) whose faces overlap BVH `other`"""
    if not mesh.f:
        return set()
    bvh = BVHTree.FromPolygons(co.tolist(), [list(f) for f in mesh.f])
    pairs = bvh.overlap(other)
    if not pairs:
        return set()
    fc, _ = mesh.components()
    return {int(fc[a]) for a, _ in pairs}


def motion_filter(ship, deleted, which, pod, noz, hull, log):
    """the rig check's pod set, done at build time: pod pitch / roll {-3, 0, 3} x nozzle pitch / roll {-5, 0, 5}
    (RIG_CONTRACT). Pod / nozzle detail pieces that overlap the ship's hull-bone faces or our own hull details in any
    pose, and our hull details (pocket lip / stiffeners) that overlap the posed pod / nozzle (ship parts or details),
    are removed. Zone 1 needed no such filter (FL sits higher in its pocket); the rear pods sit deeper in the hull."""
    arm = ship.arm
    hp = np.array(arm.data.bones['Thruster_' + which].head_local)
    hn = np.array(arm.data.bones['Thruster_%s_Nozzle' % which].head_local)
    hb = (ship.p_bone == 'Hull') & ~deleted
    hull_ship = BVHTree.FromPolygons(ship.co.tolist(), [ship.polys[i] for i in np.nonzero(hb)[0]])
    pod_m = (ship.p_bone == 'Thruster_' + which) & ~deleted
    noz_m = (ship.p_bone == 'Thruster_%s_Nozzle' % which) & ~deleted
    pod_vi = sorted({v for i in np.nonzero(pod_m)[0] for v in ship.polys[i]})
    noz_vi = sorted({v for i in np.nonzero(noz_m)[0] for v in ship.polys[i]})
    remap_p = {v: k for k, v in enumerate(pod_vi)}
    remap_n = {v: k for k, v in enumerate(noz_vi)}
    pod_faces = [[remap_p[v] for v in ship.polys[i]] for i in np.nonzero(pod_m)[0]]
    noz_faces = [[remap_n[v] for v in ship.polys[i]] for i in np.nonzero(noz_m)[0]]
    removed = {'pod': 0, 'nozzle': 0, 'hull': 0}
    P, N = (-3.0, 0.0, 3.0), (-5.0, 0.0, 5.0)
    for _round in range(2):
        hull_det = BVHTree.FromPolygons(hull.v, [list(f) for f in hull.f]) if hull.f else None
        bad = {'pod': set(), 'nozzle': set(), 'hull': set()}
        hco = np.asarray(hull.v, float)
        for a in P:
            for b in P:
                Mp = _rot_about(hp, (0, 1, 0), a) @ _rot_about(hp, (-1, 0, 0), b)
                pco = _xform(pod.v, Mp) if pod.v else None
                sp = BVHTree.FromPolygons(_xform(ship.co[pod_vi], Mp).tolist(), pod_faces)
                for c in N:
                    for d in N:
                        Mn = Mp @ _rot_about(hn, (0, 1, 0), c) @ _rot_about(hn, (-1, 0, 0), d)
                        nco = _xform(noz.v, Mn) if noz.v else None
                        sn = BVHTree.FromPolygons(_xform(ship.co[noz_vi], Mn).tolist(), noz_faces)
                        for oname, other in (('ship_hull', hull_ship), ('z3_hull_details', hull_det)):
                            if other is None:
                                continue
                            if c == N[0] and d == N[0] and pco is not None:     # the pod does not depend on the nozzle
                                hit = _pieces_hit(pod, pco, other)
                                if hit and 'debug_dir' in log:
                                    fc_, _ = pod.components()
                                    for h_ in hit:
                                        fi = [i for i in range(len(pod.f)) if fc_[i] == h_]
                                        cen = np.mean([pod.v[j] for i in fi[:20] for j in pod.f[i]], axis=0)
                                        log.setdefault('motion_debug', []).append((which, 'pod', pod.k[fi[0]], len(fi), oname, a, b,
                                                                                   [round(float(x), 2) for x in cen]))
                                bad['pod'] |= hit
                            if nco is not None:
                                bad['nozzle'] |= _pieces_hit(noz, nco, other)
                        if hull.f:
                            mov = [sn]
                            if noz.f:
                                mov.append(BVHTree.FromPolygons(nco.tolist(), [list(f) for f in noz.f]))
                            if c == N[0] and d == N[0]:
                                mov.append(sp)
                                if pod.f:
                                    mov.append(BVHTree.FromPolygons(pco.tolist(), [list(f) for f in pod.f]))
                            for o in mov:
                                bad['hull'] |= _pieces_hit(hull, hco, o)
        if not any(bad.values()):
            break
        for key, m in (('pod', pod), ('nozzle', noz), ('hull', hull)):
            if not bad[key]:
                continue
            fc, vc = m.components()
            # hardware sitting on a removed piece (a pipe's flanges and clamps, a plate's rivets) goes with it
            gone = BVHTree.FromPolygons(m.v, [list(m.f[i]) for i in range(len(m.f)) if int(fc[i]) in bad[key]])
            by = {}
            for vi, c_ in enumerate(vc):
                by.setdefault(int(c_), []).append(vi)
            for c_, vs_ in by.items():
                if c_ in bad[key] or len(vs_) > 400:
                    continue
                if all(gone.find_nearest(V(m.v[vi]), 0.04)[0] is not None for vi in vs_[::max(1, len(vs_) // 24)]):
                    bad[key].add(c_)
            drop = [i for i in range(len(m.f)) if int(fc[i]) in bad[key]]
            kinds = {}
            for i in drop:
                kinds[m.k[i]] = kinds.get(m.k[i], 0) + 1
            log.setdefault('motion_filter_%s' % which, {}).setdefault(key, {})
            for k_, v_ in kinds.items():
                log['motion_filter_%s' % which][key][k_] = log['motion_filter_%s' % which][key].get(k_, 0) + v_
            removed[key] += len(bad[key])
            m.drop_faces(drop)
    log.setdefault('motion_filter_%s' % which, {})['pieces_removed'] = removed
