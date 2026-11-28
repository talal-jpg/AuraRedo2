#!/bin/bash
# Round 3 export + offline checks, in order (Docs/Airship/round3/EXPORT_R3.md section 14). Headless Blender only, through
# blender_capped.sh; writes only under rig/detail/r3export/ (+ Docs/Airship/round3/ reports and media, SourceArt/Airship/r3
# and textures/r3 at the staging step). Talal's files are only read. About 2 minutes.
#   SourceArt/Airship/scripts/r3_export_all.sh [--no-stage] [--no-render]
# Needs rig/detail/r3export/AirshipR3_export.blend and textures/ (r3_prep.py + r3_bake.py, the UV + bake run).
set -e
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
X=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/r3export
T=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/checks/verify/Talal_copy.blend   # byte copy of Talal's file (read)
L=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/r3fbx
SH=q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L,keel_low,deck_eye
mkdir -p $L $X/checks/r2_repro
run() { local log=$1; shift; echo "== $*"; BL_MEM_MAX=6G $B "$@" > $L/$log.log 2>&1 || { echo "FAILED, see $L/$log.log"; exit 1; }
        grep -E '^\[(export|r3_|verify|DEFECT)|Traceback' $L/$log.log | tail -4 || true; }
# 1. FBX files (rig_export.py --round3: SK + LOD1/2; r3_export_static.py: HullDetail + LOD1/2, turrets)
run export_sk_lod0 --python $S/rig_export.py -- --round3
run export_sk_lod1 --python $S/rig_export.py -- --round3 --lod 1
run export_sk_lod2 --python $S/rig_export.py -- --round3 --lod 2
run export_static --python $S/r3_export_static.py
# 2. round 2 still reproducible: a fresh round-2 export (no flags) compared with rig/export/SK_Airship.fbx
run r2_repro --python $S/rig_export.py -- --out $X/checks/r2_repro/SK_Airship_round2_fresh.fbx
# 3. offline checks: low-level reader against the sources and round 2; verify_fbx / verify_import with --r3 per LOD
run fbx_check --python $S/r3_fbx_check.py -- --r2-repro $X/checks/r2_repro/SK_Airship_round2_fresh.fbx
for L_ in 0 1 2; do
  F=$X/fbx/SK_Airship.fbx; O=fbx_verify; I=import_verify
  [ $L_ != 0 ] && F=$X/fbx/SK_Airship_LOD$L_.fbx && O=fbx_verify_lod$L_ && I=import_verify_lod$L_
  run verify_fbx_lod$L_ $T --python $S/verify_fbx.py -- --r3 --fbx $F --out $X/checks/$O.json
  run verify_import_lod$L_ --python $S/verify_import.py -- --r3 --fbx $F --out $X/checks/$I.json --low $X/checks/$O.json
done
# 4. round trip renders: the same cameras from the export blend and from a fresh import of the FBX files
if [ "$1" != "--no-render" ] && [ "$2" != "--no-render" ]; then
  run preview_blendref --python $S/r3_preview.py -- --shots $SH --variants lit,flat --tag blendref
  run preview_fbx --python $S/r3_preview.py -- --shots $SH --variants lit,flat --tag fbx --from-fbx $X/fbx
  run preview_lod1_blendref --python $S/r3_preview.py -- --shots fan_close_L,pilot_45 --variants lit --lod 1 --tag blendref
  run preview_lod1_fbx --python $S/r3_preview.py -- --shots fan_close_L,pilot_45 --variants lit --lod 1 --tag fbx --from-fbx $X/fbx
  python3 -B $S/r3_roundtrip_sheet.py
fi
# 5. stage the Unreal inputs (SourceArt/Airship/r3, textures/r3, r3_unreal_inputs.json)
if [ "$1" != "--no-stage" ] && [ "$2" != "--no-stage" ]; then
  python3 -B $S/r3_unreal_inputs.py
fi
find $S -name __pycache__ -type d -prune -exec rm -rf {} +
echo "r3_export_all: done"
