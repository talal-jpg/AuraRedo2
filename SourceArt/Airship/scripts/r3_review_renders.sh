#!/bin/bash
# Round 3 review fixes: every preview render and sheet of Docs/Airship/round3/EXPORT_R3.md section 15, in order.
# Headless Blender only (blender_capped.sh), read only on the export blend; writes Docs/Airship/round3/media/export/ and
# r3export/checks/preview/. About 6 minutes. The pass-1 sheets are kept as baked_sheet_pass1.jpg / baked_crops_pass1.jpg
# and the pass-1 renders in media/export/pass1/.
#   SourceArt/Airship/scripts/r3_review_renders.sh [--no-sheets]
set -e
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
L=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/r3review
mkdir -p $L
SH8=q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L,keel_low,deck_eye
EXTRA=below,transom_rear,chain_aft,q34_rs,pilot_45q
run() { local log=$1; shift; echo "== $log: $*"; BL_MEM_MAX=6G $B --python $S/r3_preview.py -- "$@" > $L/$log.log 2>&1 || { echo "FAILED, see $L/$log.log"; exit 1; }
        grep -cE '\] render ' $L/$log.log | sed 's/^/   renders: /'; }
# 1. the shipping defaults (M_AirshipR3 v2: look LitMix 0.5 / ShadeLift 0.55 / LiftSat 1.3, capped ink line, hull dots
#    1.2 cm), the toon previews' neutral light: the approved-shot set (+ colour check passes) and LOD1
run main --shots $SH8,$EXTRA --variants lit,flat,idx
run lod1 --shots fan_close_L,pilot_45,close_flank --lod 1
# 2. the same shots in StartupMap's light and display (moon, cyan sky light, V2.1 grading, Filmic): v2 and v1 (plain lit)
run game --shots $SH8 --light game --tag game
run game_v1 --shots $SH8 --light game --look off --tag game_v1
# 3. the review's cameras (chase from behind with the stern in shadow, other ships, deck views), SK LOD by distance and
#    HullDetail LOD0 (Nanite): neutral v2, neutral v1, StartupMap v2, StartupMap v1
for look in default off; do
  T=; [ $look = off ] && T=_v1
  run rev0$T --shots deck_cannon,deck_aft_helm,turret_deck --look $look --tag r${T:-_v2}
  run rev1$T --shots chase40_back,chase65_back,enemy70_low --lod-m 1 --lod-h 0 --lodtag off --look $look --tag r${T:-_v2}
  run rev2$T --shots chase120_back,enemy120_q,enemy200_q,enemy300_q --lod-m 2 --lod-h 0 --lodtag off --look $look --tag r${T:-_v2}
  run grev1$T --shots chase65_back,enemy70_low --lod-m 1 --lod-h 0 --lodtag off --light game --look $look --tag game${T}
  run grev2$T --shots enemy120_q --lod-m 2 --lod-h 0 --lodtag off --light game --look $look --tag game${T}
  run grev0$T --shots deck_cannon --light game --look $look --tag game${T}
done
# 4. far ships: the pass-1 ink line (its anti-alias band passes InkDistMax) against v2
run far_v1 --shots enemy120_q,enemy200_q,enemy300_q --lod-m 2 --lod-h 0 --lodtag off --ink-aa v1 --tag r_inkv1
# 5. the silhouette option (HasSilhouette on) against the default (off)
run sil --shots stairs_close,q34_fp,deck_eye --sil on --tag sil
run sil_r0 --shots deck_cannon --sil on --tag r_sil
run sil_r1 --shots chase65_back --lod-m 1 --lod-h 0 --lodtag off --sil on --tag r_sil
run sil_r2 --shots chase120_back --lod-m 2 --lod-h 0 --lodtag off --sil on --tag r_sil
# 6. the props and turrets in Talal's paper look (M_AirshipProps, unchanged) against the recolour
run paper0 --shots deck_cannon,deck_aft_helm,turret_deck --props-palette off --tag r_paper
run paper1 --shots q34_fp --props-palette off --tag paper
run paper2 --shots chase65_back --lod-m 1 --lod-h 0 --lodtag off --props-palette off --tag r_paper
[ "$1" = "--no-sheets" ] || python3 -B $S/r3_review_sheets.py
find $S -name __pycache__ -type d -prune -exec rm -rf {} +
echo "r3_review_renders: done"
