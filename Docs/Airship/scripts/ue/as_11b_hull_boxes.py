# as_11b_hull_boxes.py - plain python3 (offline, no editor): fits PA_Airship's Hull boxes and the ChainFwd boxes to the
# round-2 hull (Saved/Airship/hull_survey.json from as_11a_hull_survey_blender.py) and writes Saved/Airship/pa_hull_boxes.json,
# which as_11_physics_asset.py reads. Why: the round-1 PA had 4 hand-made hull boxes from a 2.5 m hull profile; they stood
# up to 5.2 m above the hull's top surface (HullBow over the open bow, HullAft at the stern corners) and 2-10 m below/outside
# it. The SK mesh is QueryOnly Pawn + Visibility block, so sentinel bullets (Pawn sweeps) and Visibility traces hit those
# invisible boxes. Talal 11-24: "make a proper PA for ship".
#   python3 -B Docs/Airship/scripts/ue/as_11b_hull_boxes.py
# Model: per 25 cm survey column, the hull is solid between the lowest and the highest hit inside a region's z band (the
# hull tub is closed by deck and bottom; the forward platform 620..735 is a closed slab / block). Bands keep stacked
# structures apart: the main hull below 410 (aft of x 1000) / below 300 (x 1000..2130, under the open truss), the bow
# well and wedge below 450 (from x 2130), the forward platform 560..760. The open truss between the hull and the platform
# gets no box (over the main deck: from x 2130 on the well / wedge block reaches up to it).
# Per region and 200 cm x-slab: candidates are boxes across the centre line (|y| < Y) and mirrored side pairs
# (Y0 <= |y| < Y1, the stern quarters beside the rudder notch), limits in 25 cm steps; a box covers only columns that all
# have hull in the band, its top = the lowest column top - 2 cm, its bottom = the highest column bottom (so it never stands
# above the deck or below the hull in any column it covers); 3 are picked greedily by the column volume they add. Neighbouring slabs with near-equal boxes merge. Boxes are shrunk 5 cm in x/y (a cell is 25 cm wide).
# Checks (the same rule over every box): no column of a box above its top hit + 2 cm, below its bottom hit - 2 cm, or
# without hull; coverage of the hull's column volume per region is printed.
# ChainFwd: one box per link (vertices grouped by distance), + 2 cm.
# Talal 11-25 (helm and deck, SPEC_A.md section 6.8): characters now WALK on these boxes (the hull's UCX lid ignores Pawn),
# so the deck must have no hole a player falls through. The first fit had two: the main deck's forward end and the open
# bow well behind the bow wedge (x 1995..2255: the 200 cm slab 2005..2205 held columns without a deck, so it got no box,
# and nothing below either: a walker stepped off at x 1995 and fell through the ship), and the stern (x < -1570: one
# 200 cm slab over the rudder notch kept only two thin side boxes). Fix: MainFwd ends at x 2130 where the planks end (its
# last slab 2000..2130 is all deck), the well x 2130..2250 is its own region with the bow wedge's band (a block up to the
# open truss level, z 428, like the bow wedge it joins: a 1.9 m step up from the planks), and the stern is its own region
# with 50 cm slabs (SLAB_OF). Every other slab keeps its old x limits (Main starts at -1575, Bow at 2250: the same
# boundaries as before, so their boxes are unchanged).
#   AS11B_OUT=<path> python3 -B ... writes there instead of Saved/Airship/pa_hull_boxes.json (a dry run to compare).
import json, os, sys

SAVED = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship'
STEP = 25.0
SLAB = 200.0
SHRINK = 5.0
TOP_GAP = 2.0
MIN_H = 10.0
PAD_CHAIN = 2.0
MAX_PICK = 3          # boxes (a side pair counts once) per slab
MIN_GAIN = 0.03       # a pick must add 3 % of the slab's column volume
# (name, x_min, x_max, z_lo, z_hi): columns use only their hits inside [z_lo, z_hi). as_58_verify_round2.py reads this
# list (5-tuples): a box's region is the second part of its name.
REGIONS = [('Stern', -1775.0, -1575.0, -1e9, 410.0),
           ('Main', -1575.0, 1000.0, -1e9, 410.0),
           ('MainFwd', 1000.0, 2130.0, -1e9, 300.0),
           ('Well', 2130.0, 2250.0, -1e9, 450.0),
           ('Bow', 2250.0, 3175.0, -1e9, 450.0),
           ('Platform', 1000.0, 3175.0, 560.0, 760.0)]
# slab width per region (cm), SLAB when not listed: the stern's quarter galleries and transom slope around the rudder notch
SLAB_OF = {'Stern': 50.0}


def load():
    s = json.load(open(os.path.join(SAVED, 'hull_survey.json')))
    cols = {}
    for x, y, hits in s['cells']:
        cols[(round(x, 1), round(y, 1))] = [z for z, _ in hits]
    return s, cols


def band_interval(hits, lo, hi):
    zs = [z for z in hits if lo <= z < hi]
    return (min(zs), max(zs)) if zs else None


def region_cols(cols, r):
    _, x0, x1, lo, hi = r
    out = {}
    for (x, y), hits in cols.items():
        if x0 <= x < x1:
            iv = band_interval(hits, lo, hi)
            if iv:
                out[(x, y)] = iv
    return out


def box_for(rc, xs, Y0, Y1):
    """box over the columns of x centres xs and Y0 <= |y| < Y1 (both sides; Y0 = 0: one box across the centre line):
    (bot, top) or None if a column has no hull in the band."""
    bot, top = -1e9, 1e9
    n = 0
    y = Y0 + STEP / 2
    while y < Y1:
        for x in xs:
            for yy in (y, -y):
                iv = rc.get((x, round(yy, 1)))
                if iv is None:
                    return None
                bot = max(bot, iv[0])
                top = min(top, iv[1])
                n += 1
        y += STEP
    if n == 0 or top - TOP_GAP - bot < MIN_H:
        return None
    return bot, top - TOP_GAP


def slab_columns(rc, xs):
    xs = set(xs)
    return [(abs(cy), b0, t0) for (cx, cy), (b0, t0) in rc.items() if cx in xs]


def covered(sc, boxes):
    """column volume (cm * cells) of a slab's columns sc [(|y|, bottom, top)] inside the union of boxes (Y0, Y1, b, t)."""
    tot = 0.0
    for ay, b0, t0 in sc:
        ivs = sorted((max(b, b0), min(t, t0)) for Y0, Y1, b, t in boxes if Y0 <= ay < Y1 and min(t, t0) > max(b, b0))
        last = -1e9
        for a, c in ivs:
            a = max(a, last)
            if c > a:
                tot += c - a
                last = c
    return tot


def fit_region(rc, r):
    """per x-slab: candidate boxes = every centred box (|y| < Y) and every mirrored side pair (Y0 <= |y| < Y1) whose
    columns all have hull, the widest per (bottom, top); then MAX_PICK picked greedily by added coverage."""
    name, x0, x1, _, _ = r
    slab_w = SLAB_OF.get(name, SLAB)
    xs_all = sorted(set(x for x, _ in rc))
    if not xs_all:
        return []
    ymax = max(abs(y) for _, y in rc) + STEP
    nY = int(ymax / STEP) + 1
    slabs = []
    s0 = x0
    while s0 < x1:
        s1 = min(x1, s0 + slab_w)
        xs = [x for x in xs_all if s0 <= x < s1]
        if xs:
            widest = {}
            for i0 in range(nY):
                for i1 in range(i0 + 1, nY + 1):
                    Y0, Y1 = i0 * STEP, i1 * STEP
                    bt = box_for(rc, xs, Y0, Y1)
                    if bt is None:
                        continue
                    k = (Y0, bt)
                    if k not in widest or widest[k] < Y1:
                        widest[k] = Y1
            cands = sorted((Y0, Y1, bt[0], bt[1]) for (Y0, bt), Y1 in widest.items())
            sc = slab_columns(rc, xs)
            tot = sum(t - b for _, b, t in sc)
            best, bestv = [], 0.0
            for _ in range(MAX_PICK):
                add, addv = None, bestv + MIN_GAIN * tot
                for c in cands:
                    if c in best:
                        continue
                    v = covered(sc, best + [c])
                    if v > addv:
                        add, addv = c, v
                if add is None:
                    break
                best.append(add)
                bestv = addv
            slabs.append({'x0': min(xs) - STEP / 2, 'x1': max(xs) + STEP / 2, 'xs': xs, 'boxes': sorted(best), 'cov': bestv, 'tot': tot})
        s0 = s1
    return slabs


def merge(rc, slabs):
    """neighbouring slabs whose boxes match (same count, side limits +-25, bottom/top +-12) become one, re-evaluated;
    kept only if it loses under 3 % of the two slabs' coverage."""
    out = []
    for s in slabs:
        if out:
            p = out[-1]
            if abs(p['x1'] - s['x0']) < 1e-6 and len(p['boxes']) == len(s['boxes']) and all(
                    abs(a[0] - b[0]) <= STEP and abs(a[1] - b[1]) <= STEP and abs(a[2] - b[2]) <= 12 and abs(a[3] - b[3]) <= 12
                    for a, b in zip(p['boxes'], s['boxes'])):
                xs = p['xs'] + s['xs']
                nb = []
                for a, b in zip(p['boxes'], s['boxes']):
                    Y0, Y1 = max(a[0], b[0]), min(a[1], b[1])
                    bt = box_for(rc, xs, Y0, Y1) if Y1 > Y0 else None
                    if not bt:
                        nb = None
                        break
                    nb.append((Y0, Y1, bt[0], bt[1]))
                if nb:
                    v = covered(slab_columns(rc, xs), nb)
                    if v >= 0.97 * (p['cov'] + s['cov']):
                        out[-1] = {'x0': p['x0'], 'x1': s['x1'], 'xs': xs, 'boxes': nb, 'cov': v, 'tot': p['tot'] + s['tot']}
                        continue
        out.append(s)
    return out


def check(cols, boxes, tol=2.0):
    """every box against every survey column it covers (all hits, every band): above the top hit, below the bottom hit,
    or a column without hull. Box min/max in cm."""
    res = []
    for b in boxes:
        mn, mx = b['min'], b['max']
        above = below = empty = n = 0
        worst = 0.0
        x = (int(mn[0] // STEP)) * STEP + STEP / 2
        while x < mx[0]:
            y = (int(mn[1] // STEP) - 1) * STEP + STEP / 2
            while y < mx[1]:
                if mn[0] <= x <= mx[0] and mn[1] <= y <= mx[1]:
                    n += 1
                    hits = cols.get((round(x, 1), round(y, 1)))
                    if not hits:
                        empty += 1
                    else:
                        if mx[2] > hits[0] + tol:
                            above += 1
                            worst = max(worst, mx[2] - hits[0])
                        if mn[2] < hits[-1] - tol:
                            below += 1
                y += STEP
            x += STEP
        res.append({'name': b['name'], 'columns': n, 'above_top': above, 'above_worst_cm': round(worst, 1), 'below_bottom': below,
                    'no_hull': empty})
    return res


def chain_boxes(verts, gap=20.0):
    groups = []
    for v in sorted(verts):
        for g in groups:
            if any(sum((v[i] - w[i]) ** 2 for i in range(3)) <= gap * gap for w in g):
                g.append(v)
                break
        else:
            groups.append([v])
    # merge groups that touch
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if any(sum((a[k] - b[k]) ** 2 for k in range(3)) <= gap * gap for a in groups[i] for b in groups[j]):
                    groups[i] += groups.pop(j)
                    merged = True
                    break
            if merged:
                break
    out = []
    for i, g in enumerate(sorted(groups, key=lambda g: min(p[0] for p in g))):
        mn = [round(min(p[k] for p in g) - PAD_CHAIN, 1) for k in range(3)]
        mx = [round(max(p[k] for p in g) + PAD_CHAIN, 1) for k in range(3)]
        out.append({'name': 'ChainFwd_Link%d' % i, 'min': mn, 'max': mx, 'verts': len(g)})
    return out


def main():
    s, cols = load()
    boxes, report = [], {}
    for r in REGIONS:
        rc = region_cols(cols, r)
        slabs = merge(rc, fit_region(rc, r))
        cov = sum(sl['cov'] for sl in slabs)
        tot = sum(t - b for (b, t) in rc.values())
        report[r[0]] = {'columns': len(rc), 'column_volume_cm': round(tot), 'covered_cm': round(cov),
                        'coverage': round(cov / tot, 3) if tot else None, 'slabs': len(slabs)}
        for si, sl in enumerate(slabs):
            for bi, (Y0, Y1, b, t) in enumerate(sl['boxes']):
                xa, xb = round(sl['x0'] + SHRINK, 1), round(sl['x1'] - SHRINK, 1)
                if Y0 <= 0:
                    boxes.append({'name': 'Hull_%s_%02d_%d' % (r[0], si, bi), 'region': r[0],
                                  'min': [xa, round(-Y1 + SHRINK, 1), round(b, 1)], 'max': [xb, round(Y1 - SHRINK, 1), round(t, 1)]})
                else:
                    for side, sg in (('L', -1), ('R', 1)):
                        ya, yb = sg * (Y0 + SHRINK), sg * (Y1 - SHRINK)
                        boxes.append({'name': 'Hull_%s_%02d_%d%s' % (r[0], si, bi, side), 'region': r[0],
                                      'min': [xa, round(min(ya, yb), 1), round(b, 1)], 'max': [xb, round(max(ya, yb), 1), round(t, 1)]})
    chk = check(cols, boxes)
    bad = [c for c in chk if c['above_top'] or c['below_bottom'] or c['no_hull']]
    chain = chain_boxes(s.get('chain_verts') or [])
    out = {'source': os.path.join(SAVED, 'hull_survey.json'), 'rules': 'see as_11b_hull_boxes.py header', 'hull_boxes': boxes,
           'chain_boxes': chain, 'regions': report, 'check': chk, 'check_failures': bad}
    with open(os.environ.get('AS11B_OUT') or os.path.join(SAVED, 'pa_hull_boxes.json'), 'w') as f:
        json.dump(out, f, indent=1)
    for k, v in report.items():
        print('REGION %-9s %s' % (k, v))
    for b in boxes:
        print('  %-20s x %7.1f..%7.1f  y %6.1f..%6.1f  z %6.1f..%6.1f' % (b['name'], b['min'][0], b['max'][0], b['min'][1],
                                                                       b['max'][1], b['min'][2], b['max'][2]))
    for c in chain:
        print('  %-20s %s..%s (%d verts)' % (c['name'], c['min'], c['max'], c['verts']))
    print('%d hull boxes, %d chain boxes; check failures (above top / below bottom / no hull): %s' % (len(boxes), len(chain), bad))
    print('RESULT: %s' % ('PASS' if not bad and boxes else 'FAIL'))
    return 0 if not bad and boxes else 1


if __name__ == '__main__':
    sys.exit(main())
