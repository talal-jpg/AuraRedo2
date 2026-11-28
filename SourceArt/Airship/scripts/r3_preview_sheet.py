"""Round 3 export: side-by-side sheet of the approved toon renders against the baked previews (python3 + Pillow).

  python3 -B r3_preview_sheet.py [--shots q34_fp,side,...] [--tag TEXT] [--out NAME.jpg] [--crops]

Reads Docs/Airship/round3/media/full/<shot>_toon_after.jpg (approved, Freestyle ink, three cel bands) and
media/export/<shot>_baked[_<tag>].jpg (r3_preview.py: palette + baked ink, lit like Unreal) and writes
media/export/baked_sheet.jpg: one row per shot, approved left, baked right, the shot name and what it is on top.
--crops: a second sheet baked_crops.jpg with 1:1 crops of the two (same pixels), for the line work.
--cols KEY:LABEL;KEY:LABEL;... (review fixes, EXPORT_R3.md 15): any number of columns; KEY toon = the approved render
(media/full/<shot>_toon_after.jpg, else media/export/review/<shot>_toon_after.jpg), any other KEY = media/export/<shot>_KEY.jpg
(e.g. baked, baked_game, baked_sil). --title TEXT goes on top. --crop-scale N: the crops sheet magnifies N times
(nearest), --crop-box shot=x0,y0,x1,y1;... replaces the default crop boxes; --crops-out NAME.jpg.
"""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont

DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
FULL = DOCS + '/media/full'
EXP = DOCS + '/media/export'
A = sys.argv[1:]


def arg(k, d):
    return A[A.index(k) + 1] if k in A else d


SHOTS = arg('--shots', 'q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L,keel_low,deck_eye').split(',')
TAG = arg('--tag', '')
OUT = arg('--out', 'baked_sheet.jpg')
COLS = [tuple(c.split(':', 1)) for c in arg('--cols', '').split(';') if c] or \
    [('toon', 'approved toon (Freestyle ink)'), ('baked' + (('_' + TAG) if TAG else ''), 'baked: palette + ink texture, lit')]
TITLE = arg('--title', '')
CROP_SCALE = int(arg('--crop-scale', '1'))
CROPS_OUT = arg('--crops-out', 'baked_crops.jpg')
REVIEW = EXP + '/review'
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
SMALL = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 17)
BG = (36, 38, 44)
W = 1920 // max(len(COLS), 2)
ABOUT = {}
for f in (os.path.join(FULL, 'full_shots.json'), os.path.join(FULL, 'fix_shots.json'), os.path.join(REVIEW, 'review_shots.json'),
          os.path.join(EXP, 'review_fix_shots.json')):
    if os.path.isfile(f):
        for k, v in json.load(open(f)).items():
            if isinstance(v, dict):
                ABOUT[k] = v.get('about', '')
ABOUT.setdefault('side', 'orthographic side view, port')


def src(sh, key):
    if key == 'toon':
        for d in (FULL, REVIEW):
            p = os.path.join(d, sh + '_toon_after.jpg')
            if os.path.isfile(p):
                return p
        return None
    p = os.path.join(EXP, '%s_%s.jpg' % (sh, key))
    return p if os.path.isfile(p) else None


def label(im, text):
    d = ImageDraw.Draw(im)
    tw = d.textlength(text, font=FONT)
    d.rectangle((0, 0, tw + 16, 30), fill=(20, 22, 28))
    d.text((8, 4), text, fill=(240, 240, 240), font=FONT)
    return im


def fit(p, w):
    im = Image.open(p).convert('RGB')
    h = round(im.size[1] * w / im.size[0])
    return im.resize((w, h), Image.LANCZOS)


def blank(w, h, text):
    im = Image.new('RGB', (w, h), (60, 60, 66))
    ImageDraw.Draw(im).text((20, h // 2 - 10), text, fill=(200, 200, 200), font=SMALL)
    return im


rows = []
for sh in SHOTS:
    ps = [src(sh, k) for k, _ in COLS]
    if not any(ps[1:]):
        print('[sheet] missing', sh, [k for k, _ in COLS])
        continue
    ims = []
    for (k, lab), p in zip(COLS, ps):
        ims.append(label(fit(p, W), lab) if p else blank(W, round(W * 9 / 16), '%s: none for this shot' % k))
    hmax = max(i.size[1] for i in ims)
    rows.append((sh, ims, hmax))
GAP, HEAD = 6, 30
TOP = 40 if TITLE else 0
height = TOP + sum(HEAD + r[2] + GAP for r in rows) + GAP
sheet = Image.new('RGB', (len(COLS) * W + (len(COLS) + 1) * GAP, height), BG)
d = ImageDraw.Draw(sheet)
if TITLE:
    d.text((GAP + 4, 8), TITLE, fill=(250, 250, 250), font=FONT)
y = GAP + TOP
for sh, ims, hmax in rows:
    d.text((GAP + 4, y + 5), '%s  -  %s' % (sh, ABOUT.get(sh, '')), fill=(225, 225, 225), font=SMALL)
    y += HEAD
    for c, im in enumerate(ims):
        sheet.paste(im, (GAP + c * (W + GAP), y))
    y += hmax + GAP
sheet.save(os.path.join(EXP, OUT), quality=90)
print('[sheet]', os.path.join(EXP, OUT), sheet.size)

if '--crops' in A:
    CROPS = {'stairs_close': (900, 420, 1860, 1000), 'fan_close_L': (150, 200, 1110, 780), 'deck_eye': (480, 380, 1440, 900),
             'keel_low': (1150, 350, 1910, 1010), 'q34_fp': (1100, 520, 1900, 840), 'talal_back': (330, 300, 1290, 1000)}
    if '--crop-box' in A:
        CROPS = {}
        for it in arg('--crop-box', '').split(';'):
            k, v = it.split('=')
            CROPS[k] = tuple(int(x) for x in v.split(','))
    tiles = []
    for sh, box in CROPS.items():
        ps = [src(sh, k) for k, _ in COLS]
        if all(ps):
            ims = []
            for (k, lab), p in zip(COLS, ps):
                im = Image.open(p).convert('RGB').crop(box)
                if CROP_SCALE > 1:
                    im = im.resize((im.size[0] * CROP_SCALE, im.size[1] * CROP_SCALE), Image.NEAREST)
                ims.append(label(im, '%s %s (%s)' % (sh, lab.split(':')[0], '1:1' if CROP_SCALE == 1 else '%dx' % CROP_SCALE)))
            tiles.append(ims)
    cw = max(t[0].size[0] for t in tiles)
    hh = sum(t[0].size[1] + GAP for t in tiles) + GAP
    cs = Image.new('RGB', (len(COLS) * cw + (len(COLS) + 1) * GAP, hh), BG)
    y = GAP
    for ims in tiles:
        for c, im in enumerate(ims):
            cs.paste(im, (GAP + c * (cw + GAP), y))
        y += ims[0].size[1] + GAP
    cs.save(os.path.join(EXP, CROPS_OUT), quality=90)
    print('[sheet]', os.path.join(EXP, CROPS_OUT), cs.size)
