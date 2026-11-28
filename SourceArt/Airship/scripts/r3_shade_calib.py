"""Round 3 review fixes (EXPORT_R3.md section 15.2): choose the defaults of M_AirshipR3 v2's look knobs (LitMix, ShadeLift,
LiftSat, LiftLock) so the ship keeps the approved yellow and rust in StartupMap, the level matches are played in.

  B=/mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/4.5/python/bin/python3.11     (Blender's python: numpy)
  $B -I -B SourceArt/Airship/scripts/r3_shade_calib.py [-- --out Docs/Airship/round3/export_shade_calib.json]

Model (r3_look.py): per palette colour c and face kind, the displayed sRGB in StartupMap =
  display( exposure * LitMix * c * light(face, R) + max(Sat(c, LiftSat), 0) * ShadeLift )
with light = the sky light's two hemispheres (R = DaylightAmbientCubemap's unknown mean radiance, r3_look.SKY_R) plus the
moon on the faces that face it. Targets: the approved toon renders' cel bands (media/full/*_toon_after.jpg: lit band =
the palette, mid band = 0.70 x the palette, r3_preview's colour check). Faces: a vertical wall in shade (mid band), a
vertical wall facing the moon (lit band), a deck top (lit band). Score: mean CIE76 colour difference over the main
colours, weighted by how much of the ship they cover; worst case over R. Grid search, then the chosen point's numbers per
colour, plus the current material (v1: LitMix 1, no lift) for comparison.
"""
import os, sys, json, itertools
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import r3_common as RC
import r3_look as LK

A = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = RC.arg(A, '--out', RC.DOCS + '/export_shade_calib.json')
# main colours by weight (what covers the ship: export_colour_check.json pixel counts, rounded)
WEIGHTS = dict(hull_paint=3.0, paint_yellow=2.0, paint_ochre=1.0, paint_orange=1.0, rust_red=2.0, rust_dark=1.0,
               keel_block=0.5, deck=1.0, copper=0.5, wood=0.5, steel=0.5, dark_metal=0.5, machinery=0.5, brass=0.3)
SLOTS = list(WEIGHTS)
C = np.array([RC.PAL[RC.SLOT[k]] for k in SLOTS])
W = np.array([WEIGHTS[k] for k in SLOTS]); W = W / W.sum()
pp = LK.startup_pp()
EV = 2.0 ** -LK.STARTUP['ev100']
cos_moon_wall = float(np.cos(np.radians(-LK.STARTUP['moon_rot_pyr'][0])))   # a wall facing the moon's azimuth
cos_moon_top = float(np.sin(np.radians(-LK.STARTUP['moon_rot_pyr'][0])))
FACES = {   # face: (target band, light factor function of the light dict)
    'wall_shade': (0.70, lambda L: 0.5 * L['upper'] + 0.5 * L['lower']),
    'wall_lit': (1.00, lambda L: 0.5 * L['upper'] + 0.5 * L['lower'] + L['moon'] * cos_moon_wall / np.pi),
    'deck_top': (1.00, lambda L: L['upper'] + L['moon'] * cos_moon_top / np.pi),
}
TGT = {f: LK.l2s(C * band) * 255.0 for f, (band, _) in FACES.items()}
TGT_LAB = {f: LK.lab(t) for f, t in TGT.items()}


def shown(look, sky_r):
    L = LK.startup_lights(sky_r)
    out = {}
    for f, (_, fn) in FACES.items():
        v = EV * look['lit_mix'] * C * fn(L) + LK.emissive_display(C, look)
        out[f] = LK.display_startup(v, pp)
    return out


def score(look):
    worst, per_r = 0.0, {}
    for r in LK.SKY_R:
        s = shown(look, r)
        de = {f: float((np.linalg.norm(LK.lab(s[f]) - TGT_LAB[f], axis=1) * W).sum()) for f in FACES}
        m = float(np.mean(list(de.values())))
        per_r[r] = dict(mean=round(m, 2), **{f: round(v, 2) for f, v in de.items()})
        worst = max(worst, m)
    return worst, per_r


grid = dict(lit_mix=[0.0, 0.25, 0.5, 0.75, 1.0], shade_lift=list(np.round(np.arange(0.2, 1.31, 0.05), 3)),
            lift_sat=list(np.round(np.arange(1.0, 2.01, 0.1), 3)))
res = []
for lm, sl, ls in itertools.product(grid['lit_mix'], grid['shade_lift'], grid['lift_sat']):
    look = dict(lit_mix=lm, shade_lift=float(sl), lift_sat=float(ls), lift_lock=1.0)
    w, _ = score(look)
    res.append((w, look))
res.sort(key=lambda x: x[0])
best_by_lm = {}
for w, lk in res:
    best_by_lm.setdefault(lk['lit_mix'], (w, lk))
print('best per LitMix (worst-case mean dE over sky R %s):' % (LK.SKY_R,))
for lm, (w, lk) in sorted(best_by_lm.items()):
    print('  LitMix %.2f: dE %.2f  ShadeLift %.2f LiftSat %.2f' % (lm, w, lk['shade_lift'], lk['lift_sat']))
# the choice: the best point whose LitMix keeps some of the level's light (moon shading, shadows): the smallest dE among
# LitMix >= 0.5 unless a lower LitMix is clearly (> 1.5 dE) better
best = res[0]
keep = min((x for x in res if x[1]['lit_mix'] >= 0.5), key=lambda x: x[0])
chosen = keep if keep[0] - best[0] <= 1.5 else best
look = chosen[1]
print('chosen', look, 'worst dE %.2f (overall best %.2f at %s)' % (chosen[0], best[0], best[1]))


def table(lk, r=LK.SKY_R_PREVIEW):
    s = shown(lk, r)
    return {k: {f: dict(shown=[int(round(x)) for x in s[f][i]], approved=[int(round(x)) for x in TGT[f][i]],
                        dE=round(float(np.linalg.norm(LK.lab(s[f][i]) - TGT_LAB[f][i])), 1),
                        hue_shown=round(float(LK.hue_deg(s[f][i])), 0), hue_approved=round(float(LK.hue_deg(TGT[f][i])), 0))
                for f in FACES} for i, k in enumerate(SLOTS)}


v1 = dict(LK.LOOK_OFF)
rep = dict(
    about=__doc__.strip().splitlines()[0], model='r3_look.py; display = ' + LK.DM_DIR + '/display_model.py (forward, Filmic + '
    'V2.1 grading + 32^3 10-bit LUT)', startup=LK.STARTUP, sky_r_range=LK.SKY_R, weights=WEIGHTS,
    faces={f: dict(target_band=b) for f, (b, _) in FACES.items()}, grid={k: [float(x) for x in v] for k, v in grid.items()},
    chosen=look, chosen_worst_dE=round(chosen[0], 2), chosen_per_sky_r=score(look)[1],
    overall_best=dict(look=best[1], worst_dE=round(best[0], 2)),
    best_per_lit_mix={str(k): dict(look=v[1], worst_dE=round(v[0], 2)) for k, v in sorted(best_by_lm.items())},
    v1_plain_lit=dict(look=v1, worst_dE=round(score(v1)[0], 2), per_sky_r=score(v1)[1]),
    per_colour_chosen_sky_r_mid=table(look), per_colour_v1_sky_r_mid=table(v1),
    reviewer_candidate_emissive_0p8=dict(look=dict(lit_mix=1.0, shade_lift=0.8 * EV, lift_sat=1.0, lift_lock=1.0),
                                         note='the review\'s candidate: palette x 0.8 as plain emissive (scene units; x exposure here)',
                                         worst_dE=round(score(dict(lit_mix=1.0, shade_lift=0.8 * EV, lift_sat=1.0, lift_lock=1.0))[0], 2)),
)
for name, lk in (('chosen', look), ('v1', v1)):
    t = table(lk)
    print(name, {k: (t[k]['wall_shade']['shown'], t[k]['wall_shade']['approved'], t[k]['wall_lit']['shown']) for k in
                 ('hull_paint', 'paint_yellow', 'rust_red', 'deck')})
RC.dump_json(rep, OUT)
print('wrote', OUT)
