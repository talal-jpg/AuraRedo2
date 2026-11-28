"""Round 3 export: stage the files the Unreal scripts read (Docs/Airship/scripts/ue/as_90 .. as_93) into the repo.

  python3 -B SourceArt/Airship/scripts/r3_unreal_inputs.py

Copies (byte copies, md5 checked after the copy):
  rig/detail/r3export/fbx/*.fbx                        -> SourceArt/Airship/r3/  (SK_Airship[_LOD1/_LOD2],
                                                          SM_AirshipR3_HullDetail[_LOD1/_LOD2], SM_AirshipTurret_Base/_Gun)
  rig/detail/r3export/textures/T_AirshipR3_*.png       -> SourceArt/Airship/textures/r3/
  rig/checks/hull_ink/T_AirshipDrivable_ComicMask.png  -> SourceArt/Airship/textures/r3/T_AirshipR3_HullComicMask.png
and writes SourceArt/Airship/r3/r3_unreal_inputs.json: per file its md5 and bytes, and what the Unreal scripts check
against (from rig/detail/r3export/checks/fbx_check.json, manifest.json and r3_bake_report.json): triangles per LOD,
material slot order, UV layers, bounds in UE cm, the palette (24 linear colours), the ink decode (InkDistMax / InkDistNeg
in cm), the LOD screen-size inputs. Refuses to stage when fbx_check.json has defects or is older than an FBX.
Talal's files are only read.
"""
import os, sys, json, shutil, hashlib, time

BL = '/mnt/new_partition/BlenderProjects/StylizedAirship'
X = BL + '/rig/detail/r3export'
SA = '/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship'
OUT_FBX = SA + '/r3'
OUT_TEX = SA + '/textures/r3'
FBX = ['SK_Airship.fbx', 'SK_Airship_LOD1.fbx', 'SK_Airship_LOD2.fbx', 'SM_AirshipR3_HullDetail.fbx',
       'SM_AirshipR3_HullDetail_LOD1.fbx', 'SM_AirshipR3_HullDetail_LOD2.fbx', 'SM_AirshipTurret_Base.fbx',
       'SM_AirshipTurret_Gun.fbx']
TEX = ['T_AirshipR3_HullInk.png', 'T_AirshipR3_DetailInk_H.png', 'T_AirshipR3_DetailInk_M.png', 'T_AirshipR3_PropsInk.png']
COMIC_SRC = BL + '/rig/checks/hull_ink/T_AirshipDrivable_ComicMask.png'


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def load(p):
    with open(p) as f:
        return json.load(f)


chk = load(X + '/checks/fbx_check.json')
if chk['defects']:
    sys.exit('fbx_check.json has %d defects: not staged' % len(chk['defects']))
newest = max(os.path.getmtime(os.path.join(X, 'fbx', f)) for f in FBX)
if os.path.getmtime(X + '/checks/fbx_check.json') < newest:
    sys.exit('fbx_check.json is older than an FBX: run r3_fbx_check.py first')
for f in FBX:
    if chk['files'][f]['md5'] != md5(os.path.join(X, 'fbx', f)):
        sys.exit('%s changed after fbx_check.json: run r3_fbx_check.py again' % f)
man = load(X + '/manifest.json')
bake = load(X + '/checks/r3_bake_report.json')
os.makedirs(OUT_FBX, exist_ok=True)
os.makedirs(OUT_TEX, exist_ok=True)
files = {}
for f in FBX:
    src, dst = os.path.join(X, 'fbx', f), os.path.join(OUT_FBX, f)
    shutil.copyfile(src, dst)
    files['r3/' + f] = dict(source=src, md5=md5(dst), bytes=os.path.getsize(dst))
    assert files['r3/' + f]['md5'] == md5(src)
for f in TEX + ['T_AirshipR3_HullComicMask.png']:
    src = COMIC_SRC if 'ComicMask' in f else os.path.join(X, 'textures', f)
    dst = os.path.join(OUT_TEX, f)
    shutil.copyfile(src, dst)
    files['textures/r3/' + f] = dict(source=src, md5=md5(dst), bytes=os.path.getsize(dst))
    assert files['textures/r3/' + f]['md5'] == md5(src)
F = chk['files']
sk = {str(l): F['SK_Airship.fbx' if l == 0 else 'SK_Airship_LOD%d.fbx' % l] for l in (0, 1, 2)}
hd = {str(l): F['SM_AirshipR3_HullDetail.fbx' if l == 0 else 'SM_AirshipR3_HullDetail_LOD%d.fbx' % l] for l in (0, 1, 2)}
summary = dict(
    about='Round 3 inputs for the Unreal scripts (as_90 .. as_93), staged by SourceArt/Airship/scripts/r3_unreal_inputs.py '
          'from rig/detail/r3export (checked by r3_fbx_check.py, verify_fbx.py --r3, verify_import.py --r3).',
    staged=time.strftime('%Y-%m-%d %H:%M:%S'), files=files,
    sk=dict(tris={l: v['tris'] for l, v in sk.items()}, material_slots=sk['0']['material_slot_order'],
            uv_channels=3, bones=118, bounds_ue_cm=sk['0']['bounds_ue'],
            render_vertices_est_lod0=sum(m['ue']['render_vertices_est'] for m in sk['0']['meshes'].values())),
    hull_detail=dict(tris={l: v['tris'] for l, v in hd.items()}, material_slots=hd['0']['materials'], uv_channels=2,
                     bounds_ue_cm=hd['0']['bounds_ue'], render_vertices_est_lod0=hd['0']['ue']['render_vertices_est']),
    turrets={n: dict(tris=F[n + '.fbx']['tris'], bounds_ue_cm=F[n + '.fbx']['bounds_ue'], uv_channels=2)
             for n in ('SM_AirshipTurret_Base', 'SM_AirshipTurret_Gun')},
    palette=man['palette'],
    ink=dict(InkDistMax_cm=round(100 * bake['knobs']['dmax'], 4), InkDistNeg_cm=round(100 * bake['knobs']['dneg'], 4),
             encoding='R = (d + InkDistNeg) / (InkDistMax + InkDistNeg), d in cm; G = rivet dot; B = 0',
             ink_hex='1C2230', side_d_cm=round(100 * bake['knobs']['side_d'], 4)),
    textures={f: dict(size=bake['pages'][p]['size'] if p in bake['pages'] else None, uv=uv)
              for f, p, uv in (('T_AirshipR3_HullInk', 'hull', 'UV2 R3Ink'), ('T_AirshipR3_DetailInk_H', 'H', 'UV0'),
                               ('T_AirshipR3_DetailInk_M', 'M', 'UV0'), ('T_AirshipR3_PropsInk', 'P', 'UV0'),
                               ('T_AirshipR3_HullComicMask', None, 'UV0 (Talal\'s UVs)'))},
    ue_build=dict(full_precision_uvs='required: half-float UVs put lines up to 1 texel off on the 4096 pages',
                  sk_threshold_uv=1.0 / 65536,
                  sk_weld_pairs_at_default=chk['files']['SK_Airship.fbx']['meshes']['SM_Airship']['ue']['weld'],
                  hull_detail_weld_pairs=hd['0']['ue']['weld']),
    lod=dict(sk_screen_size_inputs=dict(fov_deg=85, distances_m=[30, 80], formula='1.94 * R / D (16:9, FOV 85)'),
             manifest=man['lods']))
# review fixes (EXPORT_R3.md section 15): M_AirshipR3 v2's look defaults, chosen by r3_shade_calib.py for StartupMap
_calib = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/export_shade_calib.json'
if os.path.isfile(_calib):
    _c = load(_calib)
    summary['look'] = dict(LitMix=_c['chosen']['lit_mix'], ShadeLift=_c['chosen']['shade_lift'],
                           LiftSat=_c['chosen']['lift_sat'], LiftLock=_c['chosen']['lift_lock'],
                           source='Docs/Airship/round3/export_shade_calib.json (r3_shade_calib.py)',
                           worst_dE_startupmap=_c['chosen_worst_dE'], v1_plain_lit_dE=_c['v1_plain_lit']['worst_dE'])
summary['bake_knobs'] = dict(dot_r_cm=round(100 * bake['knobs']['dot_r'], 3),
                             dot_r_hull_cm=round(100 * bake['knobs'].get('dot_r_hull', bake['knobs']['dot_r']), 3))
with open(OUT_FBX + '/r3_unreal_inputs.json', 'w') as f:
    json.dump(summary, f, indent=1)
print('staged %d FBX + %d PNG into %s and %s; summary %s' % (len(FBX), len(TEX) + 1, OUT_FBX, OUT_TEX,
                                                             OUT_FBX + '/r3_unreal_inputs.json'))
