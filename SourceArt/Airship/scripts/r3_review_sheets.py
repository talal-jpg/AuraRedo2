"""Round 3 review fixes: the sheets and numbers of EXPORT_R3.md section 15 from r3_review_renders.sh's renders
(python3 + Pillow, no numpy).

  python3 -B SourceArt/Airship/scripts/r3_review_sheets.py

Writes into Docs/Airship/round3/media/export/:
  baked_sheet.jpg        approved toon | baked, preview light (v2 defaults) | baked, StartupMap light (v2), the 8 shots
                         (the pass-1 sheet is baked_sheet_pass1.jpg)
  baked_crops.jpg        1:1 crops approved | baked v2 (pass 1: baked_crops_pass1.jpg)
  game_light_fix.jpg     StartupMap light: approved | v1 plain lit (pass 1's material) | v2 look (review findings 1, 2)
  shade_fix.jpg          preview light, the review's cameras: approved | v1 | v2 (finding 2: the shaded stern)
  silhouette_option.jpg  approved | v2 (HasSilhouette off, default) | v2 + silhouette (on), with 1:1 crops (finding 3)
  props_option.jpg       approved | props in Talal's paper look (M_AirshipProps) | props recoloured (finding 5)
  far_ink_fix.jpg        other ships at 120 / 200 / 300 m: pass-1 ink line | v2, with 4x crops (finding 7)
and Docs/Airship/round3/export_review_renders.json: the median colours of fixed patches (the stern wall, the hull side)
per variant, and the far-ship darkening of the pass-1 ink line against v2 on ship pixels.
"""
import os, json
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageStat

DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
FULL = DOCS + '/media/full'
EXP = DOCS + '/media/export'
REV = EXP + '/review'
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
SMALL = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 17)
BG = (36, 38, 44)
GAP, HEAD = 6, 30
ABOUT = {}
for f in (FULL + '/full_shots.json', FULL + '/fix_shots.json', REV + '/review_shots.json', EXP + '/review_fix_shots.json'):
    if os.path.isfile(f):
        for k, v in json.load(open(f)).items():
            if isinstance(v, dict):
                ABOUT[k] = v.get('about', '')
ABOUT.setdefault('side', 'orthographic side view, port')
REPORT = {}


def toon(sh):
    for d in (FULL, REV):
        p = os.path.join(d, sh + '_toon_after.jpg')
        if os.path.isfile(p):
            return p
    return None


def exp(sh, key):
    p = os.path.join(EXP, '%s_%s.jpg' % (sh, key))
    return p if os.path.isfile(p) else None


def label(im, text):
    d = ImageDraw.Draw(im)
    tw = d.textlength(text, font=FONT)
    d.rectangle((0, 0, tw + 16, 30), fill=(20, 22, 28))
    d.text((8, 4), text, fill=(240, 240, 240), font=FONT)
    return im


def tile(p, w, lab, box=None, scale=1):
    if p is None:
        im = Image.new('RGB', (w, round(w * 9 / 16)), (60, 60, 66))
        ImageDraw.Draw(im).text((20, im.size[1] // 2 - 10), lab + ': none for this shot', fill=(200, 200, 200), font=SMALL)
        return im
    im = Image.open(p).convert('RGB')
    if box:
        im = im.crop(box)
        if scale > 1:
            im = im.resize((im.size[0] * scale, im.size[1] * scale), Image.NEAREST)
    if w and im.size[0] != w:
        im = im.resize((w, round(im.size[1] * w / im.size[0])), Image.LANCZOS)
    return label(im, lab)


def sheet(out, title, rows, labels, width=1920, box=None, scale=1, note=None):
    """rows: [(shot, [path or None per column], optional box)]"""
    n = len(labels)
    w = (width - (n + 1) * GAP) // n
    built = []
    for r in rows:
        sh, paths = r[0], r[1]
        bx = r[2] if len(r) > 2 else box
        ims = [tile(p, w, lab, bx, scale) for p, lab in zip(paths, labels)]
        built.append((sh, ims, max(i.size[1] for i in ims)))
    top = 40 + (26 if note else 0)
    h = top + sum(HEAD + b[2] + GAP for b in built) + GAP
    S = Image.new('RGB', (n * w + (n + 1) * GAP, h), BG)
    d = ImageDraw.Draw(S)
    d.text((GAP + 4, 8), title, fill=(250, 250, 250), font=FONT)
    if note:
        d.text((GAP + 4, 38), note, fill=(205, 205, 205), font=SMALL)
    y = top
    for sh, ims, hm in built:
        d.text((GAP + 4, y + 5), '%s  -  %s' % (sh, ABOUT.get(sh, '')), fill=(225, 225, 225), font=SMALL)
        y += HEAD
        for c, im in enumerate(ims):
            S.paste(im, (GAP + c * (w + GAP), y))
        y += hm + GAP
    S.save(os.path.join(EXP, out), quality=90)
    print('[sheets]', out, S.size)


def median_rgb(p, box):
    if p is None:
        return None
    im = Image.open(p).convert('RGB').crop(box)
    return [int(round(x)) for x in ImageStat.Stat(im).median]


SH8 = ['q34_fp', 'side', 'pilot_45', 'talal_back', 'stairs_close', 'fan_close_L', 'keel_low', 'deck_eye']
# 1. the main sheet and crops
sheet('baked_sheet.jpg', 'Round 3 review fixes: approved toon | baked, preview light | baked, StartupMap light (M_AirshipR3 v2 defaults)',
      [(s, [toon(s), exp(s, 'baked'), exp(s, 'baked_game')]) for s in SH8],
      ['approved toon (Freestyle ink)', 'baked v2, preview light', 'baked v2, StartupMap light + grade'], width=2400,
      note='v2 = LitMix 0.5, ShadeLift 0.55, LiftSat 1.3 (export_shade_calib.json), ink line capped at InkDistMax, hull rivet dots 1.2 cm. '
           'Pass 1: baked_sheet_pass1.jpg.')
CROPS = {'stairs_close': (900, 420, 1860, 1000), 'fan_close_L': (150, 200, 1110, 780), 'deck_eye': (480, 380, 1440, 900),
         'keel_low': (1150, 350, 1910, 1010), 'q34_fp': (1100, 520, 1900, 840), 'talal_back': (330, 300, 1290, 1000)}
sheet('baked_crops.jpg', 'Round 3 review fixes: 1:1 crops, approved | baked v2 (preview light) | baked v2 (StartupMap)',
      [(s, [toon(s), exp(s, 'baked'), exp(s, 'baked_game')], b) for s, b in CROPS.items()],
      ['approved (1:1)', 'baked v2 preview light (1:1)', 'baked v2 StartupMap (1:1)'], width=2900)
# 2. StartupMap light: v1 against v2
GAME = ['q34_fp', 'pilot_45', 'talal_back', 'deck_eye', 'chase65_back', 'enemy70_low', 'enemy120_q', 'deck_cannon']
sheet('game_light_fix.jpg', 'StartupMap light (moon 2.24 lux, cyan sky light, V2.1 grading, Filmic; display model): approved | v1 plain lit | v2 look',
      [(s, [toon(s), exp(s, 'baked_game_v1'), exp(s, 'baked_game')]) for s in GAME],
      ['approved toon', 'v1: Default Lit only (pass 1)', 'v2: LitMix 0.5 + ShadeLift 0.55, LiftSat 1.3'], width=2400,
      note='Sky light strength is a model (DaylightAmbientCubemap mean radiance 0.6, unknown offline); fog, bloom and Lumen are not modelled. '
           'The editor stage checks it in StartupMap.')
# 3. preview light, the review's cameras: v1 against v2
SHADE = ['chase40_back', 'chase65_back', 'enemy70_low', 'enemy120_q', 'deck_aft_helm']
sheet('shade_fix.jpg', 'Preview light (neutral), the review cameras: approved | v1 plain lit | v2 look (the shaded stern)',
      [(s, [toon(s), exp(s, 'baked_r_v1'), exp(s, 'baked_r_v2')]) for s in SHADE],
      ['approved toon', 'v1 (pass 1)', 'v2 defaults'], width=2400)
# 4. silhouettes
SIL = [('stairs_close', 'baked', 'baked_sil'), ('q34_fp', 'baked', 'baked_sil'), ('deck_eye', 'baked', 'baked_sil'),
       ('deck_cannon', 'baked_r_v2', 'baked_r_sil'), ('chase65_back', 'baked_r_v2', 'baked_r_sil'), ('chase120_back', 'baked_r_v2', 'baked_r_sil')]
sheet('silhouette_option.jpg', 'Silhouette option (HasSilhouette, default OFF): approved | v2 off | v2 on (2.4 px, faded out 60-120 m)',
      [(s, [toon(s), exp(s, a), exp(s, b)]) for s, a, b in SIL],
      ['approved toon (Freestyle)', 'v2, silhouette off (default)', 'v2, silhouette on'], width=2400)
SILC = {'stairs_close': (980, 150, 1900, 1060), 'q34_fp': (1100, 520, 1900, 840), 'deck_cannon': (500, 300, 1400, 900)}
sheet('silhouette_option_crops.jpg', 'Silhouette option, 1:1 crops: approved | off | on',
      [(s, [toon(s), exp(s, a), exp(s, b)], SILC[s]) for s, a, b in SIL if s in SILC],
      ['approved (1:1)', 'off (1:1)', 'on (1:1)'], width=2800)
# 5. props
PROPS = [('deck_cannon', 'baked_r_paper', 'baked_r_v2'), ('deck_aft_helm', 'baked_r_paper', 'baked_r_v2'),
         ('turret_deck', 'baked_r_paper', 'baked_r_v2'), ('q34_fp', 'baked_paper', 'baked'), ('chase65_back', 'baked_r_paper', 'baked_r_v2')]
sheet('props_option.jpg', 'Props and turrets (question for Talal): approved | paper look in game today (M_AirshipProps) | recoloured (MI_AirshipR3_Props)',
      [(s, [toon(s), exp(s, a), exp(s, b)]) for s, a, b in PROPS],
      ['approved toon (recoloured)', 'paper (today, M_AirshipProps)', 'recoloured (palette 17-19)'], width=2400)
# 6. far ships: pass-1 line against v2, plus 4x crops round the ship
FAR = ['enemy120_q', 'enemy200_q', 'enemy300_q']


def ship_box(p, bgtol=10, pad=8):
    im = Image.open(p).convert('RGB')
    bgc = im.getpixel((2, 2))
    diff = ImageChops.difference(im, Image.new('RGB', im.size, bgc)).convert('L').point(lambda v: 255 if v > bgtol else 0)
    b = diff.getbbox()
    return (max(b[0] - pad, 0), max(b[1] - pad, 0), min(b[2] + pad, im.size[0]), min(b[3] + pad, im.size[1])), diff


rows, far = [], {}
for s in FAR:
    a, b = exp(s, 'baked_r_inkv1'), exp(s, 'baked_r_v2')
    if not (a and b):
        continue
    box, mask = ship_box(b)
    ia, ib = Image.open(a).convert('L'), Image.open(b).convert('L')
    darker = ImageChops.subtract(ib, ia)            # how much darker the pass-1 line made each pixel
    m = mask.crop(box); dk = darker.crop(box)
    n_ship = sum(1 for v in m.getdata() if v)
    vals = [d for d, mm in zip(dk.getdata(), m.getdata()) if mm]
    far[s] = dict(ship_pixels=n_ship, mean_darkening_8bit=round(sum(vals) / max(n_ship, 1), 2),
                  share_darker_by_20=round(sum(1 for v in vals if v > 20) / max(n_ship, 1), 4),
                  share_darker_by_40=round(sum(1 for v in vals if v > 40) / max(n_ship, 1), 4), box=box)
    sc = max(1, min(4, 900 // max(box[2] - box[0], 1)))
    rows.append((s, [a, b], box))
    rows[-1] = (s, [a, b], box)
    far[s]['crop_scale'] = sc
REPORT['far_ink'] = far
if rows:
    sc = min(far[r[0]]['crop_scale'] for r in rows)
    sheet('far_ink_fix.jpg', 'Other ships at 120 / 200 / 300 m (FOV 85, 1920 px, SK LOD2): pass-1 ink line | v2 (crops %dx)' % sc,
          rows, ['pass 1: band passes InkDistMax', 'v2: band ends at InkDistMax'], width=1920, scale=sc,
          note='mean darkening of ship pixels by the pass-1 line: ' + ', '.join('%s %.1f/255 (%.0f %% of pixels > 20)' % (
              k, v['mean_darkening_8bit'], 100 * v['share_darker_by_20']) for k, v in far.items()))
# 7. the stern wall in the chase view (review finding 2): the pixels where the approved render shows the review's
#    transom colour (209,173,99) +- 10, median per variant
def stern(sh, ref=(209, 173, 99), tol=10, box=(800, 600, 1120, 900)):
    t = toon(sh)
    if t is None:
        return None
    px = Image.open(t).convert('RGB').load()
    pts = [(x, y) for y in range(box[1], box[3], 2) for x in range(box[0], box[2], 2)
           if all(abs(a - b) <= tol for a, b in zip(px[x, y], ref))]
    out = dict(pixels=len(pts), ref=list(ref))
    for k, key in (('approved', None), ('v1_preview', 'baked_r_v1'), ('v2_preview', 'baked_r_v2'),
                   ('v1_startupmap', 'baked_game_v1'), ('v2_startupmap', 'baked_game')):
        p = t if key is None else exp(sh, key)
        if p is None or not pts:
            out[k] = None
            continue
        q = Image.open(p).convert('RGB').load()
        out[k] = [sorted(q[x, y][c] for x, y in pts)[len(pts) // 2] for c in range(3)]
    return out


pat = {'chase65_back_stern': stern('chase65_back')}
REPORT['patches'] = pat
json.dump(REPORT, open(os.path.join(DOCS, 'export_review_renders.json'), 'w'), indent=1)
print('[sheets] export_review_renders.json', json.dumps(REPORT)[:1500])
