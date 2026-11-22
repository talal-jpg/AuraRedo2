# as_20b_deck_slabs.py - plain python3 (offline, no editor): turns Saved/Airship/deck_survey.json (as_20a, Blender) into
# the box slabs that CR_Airship's kinematic Wreck Hull body gets under the deck and the gantries (review finding 5:
# the kicked searchlights and other break-off parts had nothing to land on and fell through deck and gantry).
# Writes Saved/Airship/deck_slabs.json (boxes in UE component cm: min/max) + deck_slabs.png (top view, for a look).
#   python3 -B Docs/Airship/scripts/ue/as_20b_deck_slabs.py
# Rules: per strip along X (deck 200 cm, gantries 100 cm), the top-most near-horizontal Hull surface of each 25 cm cell, in the deck band
# (190..300 cm; a hatch top 300..360 counts as deck, the slab runs under it) or a gantry band (630..680, 720..760).
# Cells of one strip with tops within 12 cm form a cluster; its contiguous Y runs become boxes, top = 2 cm below the
# lowest surface of the run, 80 cm (deck) / 40 cm (gantry) thick. Neighbouring strips with the same Y run (+-13 cm) and
# tops within 4 cm merge. Then every box is cut in Y around the rest AABB (+5 cm) of every Wreck body it would touch
# (part_bounds.json; cannons, pods, nacelles, rudder, posts), so nothing starts inside a slab.
import json, os, sys

SAVED = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship'
d = json.load(open(os.path.join(SAVED, 'deck_survey.json')))
pb = json.load(open(os.path.join(SAVED, 'part_bounds.json')))['bones']
STEP = d['step_cm']
X_MIN = -1530.0          # aft of this: rudder + fan nacelles (break-off bodies), no slabs
BANDS = [('deck', 190.0, 300.0, 80.0), ('gantry_low', 630.0, 680.0, 40.0), ('gantry_high', 720.0, 760.0, 40.0)]
HATCH = (300.0, 360.0)

def band_of(zs):
    """(band name, surface z, thickness) of a cell from its hits (top down), or None."""
    top = [z for z in zs if z > 150.0]
    if not top:
        return None
    z0 = top[0]
    for name, lo, hi, th in BANDS:
        if lo <= z0 <= hi:
            return name, z0, th
    if HATCH[0] < z0 <= HATCH[1]:
        below = [z for z in top[1:] if BANDS[0][1] <= z <= BANDS[0][2]]
        if below:
            return 'deck', max(below), BANDS[0][3]
    return None

strips = {}
for x, y, zs in d['cells']:
    if x < X_MIN:
        continue
    b = band_of(zs)
    if b is None:
        continue
    k = (b[0] == 'deck', int((x - X_MIN) // (200.0 if b[0] == 'deck' else 100.0)))
    strips.setdefault(k, []).append((x, y, b[0], b[1], b[2]))

boxes = []
for k in sorted(strips):
    cells = sorted(strips[k], key=lambda c: (c[2], c[3]))
    # clusters per band by z (span <= 12 cm)
    clusters = []
    for c in cells:
        if clusters and clusters[-1][0][2] == c[2] and c[3] - clusters[-1][0][3] <= 12.0:
            clusters[-1].append(c)
        else:
            clusters.append([c])
    for cl in clusters:
        if len(cl) < 4:
            continue
        ys = sorted(set(c[1] for c in cl))
        runs, cur = [], [ys[0]]
        for yy in ys[1:]:
            if yy - cur[-1] > 1.5 * STEP:
                runs.append(cur)
                cur = [yy]
            else:
                cur.append(yy)
        runs.append(cur)
        for r in runs:
            if len(r) < 2:
                continue
            rc = [c for c in cl if r[0] <= c[1] <= r[-1]]
            top = min(c[3] for c in rc) - 2.0
            boxes.append({'band': cl[0][2], 'min': [min(c[0] for c in rc) - STEP / 2, r[0] - STEP / 2, top - cl[0][4]],
                          'max': [max(c[0] for c in rc) + STEP / 2, r[-1] + STEP / 2, top], 'cells': len(rc)})

# merge neighbouring strips (same band, same y run, tops within 4 cm, touching in x)
boxes.sort(key=lambda b: (b['band'], round(b['min'][1] / 13.0), b['min'][0]))
merged = []
for b in boxes:
    for m in merged:
        if (m['band'] == b['band'] and abs(m['min'][1] - b['min'][1]) <= 13.0 and abs(m['max'][1] - b['max'][1]) <= 13.0
                and abs(m['max'][2] - b['max'][2]) <= 4.0 and abs(m['max'][0] - b['min'][0]) <= 1.0):
            top = min(m['max'][2], b['max'][2])
            th = m['max'][2] - m['min'][2]
            m['max'] = [b['max'][0], max(m['max'][1], b['max'][1]), top]
            m['min'] = [m['min'][0], min(m['min'][1], b['min'][1]), top - th]
            m['cells'] += b['cells']
            break
    else:
        merged.append(dict(b))

# keep clear of every Wreck body's rest AABB (+5 cm): cut the box in Y around it
# Wreck bodies as as_12 _part_plan builds them (body -> bones whose vertex bounds make its box)
WRECK = {}
for p_ in ('FL', 'FR', 'RL', 'RR'):
    WRECK['Thruster_' + p_] = ['Thruster_' + p_]
for s_ in 'LR':
    WRECK['Turbine_' + s_] = ['Turbine_' + s_, 'Turbine_%s_Rotor' % s_]
    WRECK['Turbine_%s_Rod' % s_] = ['Turbine_%s_Rod' % s_]
WRECK['Rudder'] = ['Rudder']
for c_ in ('L1', 'L2', 'R1', 'R2'):
    cb_ = 'Cannon_' + c_
    WRECK[cb_] = [cb_, cb_ + '_Quoin'] + [cb_ + '_Wheel_' + w_ for w_ in ('FL', 'FR', 'BL', 'BR')]
    WRECK[cb_ + '_Barrel'] = [cb_ + '_Barrel']
for L_ in ('AftL', 'MidL', 'MidR', 'FwdC'):
    WRECK['SearchLight_' + L_] = ['SearchLight_' + L_, 'SearchLight_%s_Head' % L_]
BODY_BB = dict((k, {'min': [min(pb[b]['min'][i] for b in v) for i in range(3)],
                    'max': [max(pb[b]['max'][i] for b in v) for i in range(3)]}) for k, v in WRECK.items())
MIN_SIDE = 60.0          # pieces narrower than this (deck lip strips, cut leftovers) are dropped
PAD = 5.0                # cm in X / Y around a body's rest box
PAD_Z = 1.0              # cm in Z: a slab 2 cm under a part that stands on the surface is not cut

def overlap(a, b):
    return all(a['min'][i] < b['max'][i] and b['min'][i] < a['max'][i] for i in range(3))

cuts = []
final = merged
for bn in sorted(BODY_BB):
    pads_ = (PAD, PAD, PAD_Z)
    bb = {'min': [v - pads_[i] for i, v in enumerate(BODY_BB[bn]['min'])], 'max': [v + pads_[i] for i, v in enumerate(BODY_BB[bn]['max'])]}
    nxt = []
    for s in final:
        if not overlap(s, bb):
            nxt.append(s)
            continue
        cuts.append((bn, s['band'], [round(v) for v in s['min']], [round(v) for v in s['max']]))
        for lo, hi in ((s['min'][1], bb['min'][1]), (bb['max'][1], s['max'][1])):
            if hi - lo >= MIN_SIDE:
                p = {'band': s['band'], 'min': list(s['min']), 'max': list(s['max']), 'cells': s['cells']}
                p['min'][1], p['max'][1] = lo, hi
                nxt.append(p)
    final = nxt

final = [b for b in final if min(b['max'][0] - b['min'][0], b['max'][1] - b['min'][1]) >= MIN_SIDE]
final.sort(key=lambda b: (b['band'], b['min'][0], b['min'][1]))
for i, b in enumerate(final):
    b['name'] = '%s_%02d' % (b['band'], i)
    b['min'] = [round(v, 1) for v in b['min']]
    b['max'] = [round(v, 1) for v in b['max']]
left = [(bn, s['name']) for bn in sorted(BODY_BB) for s in final
        if overlap(s, {'min': [v - 0.5 for v in BODY_BB[bn]['min']], 'max': [v + 0.5 for v in BODY_BB[bn]['max']]})]
out = {'boxes': final, 'count': len(final), 'cuts_around_wreck_bodies': cuts, 'overlaps_left': left,
       'rules': 'see as_20b_deck_slabs.py header'}
json.dump(out, open(os.path.join(SAVED, 'deck_slabs.json'), 'w'), indent=1)
print('slabs %d (deck %d, gantry %d), cuts %d, overlaps left %d' % (
    len(final), len([b for b in final if b['band'] == 'deck']), len([b for b in final if b['band'] != 'deck']),
    len(cuts), len(left)))
for b in final:
    print('  %-15s x %7.1f..%7.1f  y %7.1f..%7.1f  z %6.1f..%6.1f' % (b['name'], b['min'][0], b['max'][0], b['min'][1],
                                                                    b['max'][1], b['min'][2], b['max'][2]))
try:
    from PIL import Image, ImageDraw
    S = 0.25
    W, Hh = int(5200 * S), int(2000 * S)
    im = Image.new('RGB', (W, Hh), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    px = lambda x, y: ((x + 2050) * S, (y + 1000) * S)
    for x, y, zs in d['cells']:
        top = [z for z in zs if z > 150]
        if top:
            g = int(max(0, min(255, (top[0] - 150) / 900 * 255)))
            a, b2 = px(x - STEP / 2, y - STEP / 2)
            dr.rectangle([a, b2, a + STEP * S, b2 + STEP * S], fill=(g, g, g))
    col = {'deck': (0, 160, 0), 'gantry_low': (220, 120, 0), 'gantry_high': (200, 0, 200)}
    for b in final:
        dr.rectangle([px(b['min'][0], b['min'][1]), px(b['max'][0], b['max'][1])], outline=col[b['band']], width=2)
    for bn in BODY_BB:
        bb = BODY_BB[bn]
        dr.rectangle([px(bb['min'][0], bb['min'][1]), px(bb['max'][0], bb['max'][1])], outline=(255, 0, 0), width=1)
    im.save(os.path.join(SAVED, 'deck_slabs.png'))
    print('top view', os.path.join(SAVED, 'deck_slabs.png'))
except Exception as e:  # noqa: BLE001
    print('no PNG: %r' % e)
