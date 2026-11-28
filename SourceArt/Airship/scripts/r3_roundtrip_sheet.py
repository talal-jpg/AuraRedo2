"""Round 3 export: the FBX round trip against the export blend, as numbers and as a sheet (python3 + Pillow).

  python3 -B r3_roundtrip_sheet.py [--shots q34_fp,side,...] [--lod1-shots fan_close_L,pilot_45]

Reads the renders r3_preview.py made of the same cameras twice: from the export blend (--tag blendref) and from a
fresh Blender import of the FBX files (--from-fbx rig/detail/r3export/fbx --tag fbx):
  rig/detail/r3export/checks/preview/<shot>_flat_{blendref,fbx}.png   base colour as emission, no light (lossless)
  Docs/Airship/round3/media/export/<shot>_baked_{blendref,fbx}.jpg     the lit Unreal mimic
  (also <shot>_flat.png of the bake step, and the LOD1 pair <shot>_baked_lod1_{blendref,fbx}.jpg when present)
Writes Docs/Airship/round3/export_roundtrip.json (per shot: mean / max difference, share of pixels over 8 and 32 of 255)
and media/export/roundtrip_sheet.jpg: per shot the blend render, the FBX render and their difference x8.
"""
import os, sys, json
from PIL import Image, ImageChops, ImageDraw, ImageFont

DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
EXP = DOCS + '/media/export'
PREV = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/r3export/checks/preview'
A = sys.argv[1:]


def arg(k, d):
    return A[A.index(k) + 1] if k in A else d


SHOTS = arg('--shots', 'q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L,keel_low,deck_eye').split(',')
LOD1 = [s for s in arg('--lod1-shots', 'fan_close_L,pilot_45').split(',') if s]
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
W = 640


def stats(a, b):
    A_ = Image.open(a).convert('RGB')
    B_ = Image.open(b).convert('RGB')
    if A_.size != B_.size:
        return dict(error='sizes %s vs %s' % (A_.size, B_.size)), None
    d = ImageChops.difference(A_, B_)
    g = d.convert('L')
    h = g.histogram()
    n = float(sum(h))
    return dict(mean=round(sum(i * v for i, v in enumerate(h)) / n, 4), max=max(i for i, v in enumerate(h) if v),
                share_over_8=round(sum(h[9:]) / n, 6), share_over_32=round(sum(h[33:]) / n, 6),
                pixels_over_32=int(sum(h[33:]))), d


def label(im, text):
    dr = ImageDraw.Draw(im)
    tw = dr.textlength(text, font=FONT)
    dr.rectangle((0, 0, tw + 12, 26), fill=(20, 22, 28))
    dr.text((6, 3), text, font=FONT, fill=(235, 235, 235))
    return im


res = {}
rows = []
for sh in SHOTS:
    r = {}
    r['flat_blend_vs_fbx'], _ = stats('%s/%s_flat_blendref.png' % (PREV, sh), '%s/%s_flat_fbx.png' % (PREV, sh))
    if os.path.isfile('%s/%s_flat.png' % (PREV, sh)):
        r['flat_bakestep_vs_fbx'], _ = stats('%s/%s_flat.png' % (PREV, sh), '%s/%s_flat_fbx.png' % (PREV, sh))
    a, b = '%s/%s_baked_blendref.jpg' % (EXP, sh), '%s/%s_baked_fbx.jpg' % (EXP, sh)
    r['lit_blend_vs_fbx'], d = stats(a, b)
    res[sh] = r
    ims = [Image.open(a).convert('RGB'), Image.open(b).convert('RGB'),
           Image.eval(d, lambda x: min(255, 8 * x)) if d is not None else Image.new('RGB', (W, W))]
    rows.append((sh, ims))
for sh in LOD1:
    a, b = '%s/%s_baked_lod1_blendref.jpg' % (EXP, sh), '%s/%s_baked_lod1_fbx.jpg' % (EXP, sh)
    if os.path.isfile(a) and os.path.isfile(b):
        st, d = stats(a, b)
        res[sh + '_lod1'] = dict(lit_blend_vs_fbx=st)
        rows.append((sh + ' LOD1', [Image.open(a).convert('RGB'), Image.open(b).convert('RGB'), Image.eval(d, lambda x: min(255, 8 * x))]))

tiles = []
for sh, ims in rows:
    h = int(ims[0].size[1] * W / ims[0].size[0])
    t = [im.resize((W, h), Image.LANCZOS) for im in ims]
    label(t[0], '%s: export blend' % sh)
    label(t[1], '%s: FBX round trip' % sh)
    label(t[2], 'difference x8')
    tiles.append(t)
H = sum(t[0].size[1] for t in tiles)
sheet = Image.new('RGB', (3 * W, H), (36, 38, 44))
y = 0
for t in tiles:
    for k, im in enumerate(t):
        sheet.paste(im, (k * W, y))
    y += t[0].size[1]
sheet.save(EXP + '/roundtrip_sheet.jpg', quality=88)
worst = max((v['share_over_32'] for r in res.values() for v in r.values() if 'share_over_32' in v), default=None)
out = dict(about='FBX round trip: the same cameras rendered from the export blend and from a fresh Blender import of '
                 'rig/detail/r3export/fbx (r3_preview.py --from-fbx). flat = base colour as emission (lossless PNG); lit = '
                 'the Unreal mimic (JPEG, so a few levels of noise). share_over_N = share of pixels whose grey difference '
                 'is over N of 255.', shots=res, worst_share_over_32=worst)
json.dump(out, open(DOCS + '/export_roundtrip.json', 'w'), indent=1)
print('roundtrip: worst share over 32/255 = %s; sheet %s' % (worst, EXP + '/roundtrip_sheet.jpg'))
for k, v in res.items():
    print(k, {a: (b.get('mean'), b.get('max'), b.get('share_over_8'), b.get('share_over_32')) for a, b in v.items()})
