#!/bin/bash
# Independent verification of rig/export/SK_Airship.fbx (headless Blender, ~1 min). Writes only to
# rig/checks/verify/, rig/renders/verify/ and rig/tmp/verify/; opens copies of Talal's / the rigger's .blend files.
set -e
RIG=/mnt/new_partition/BlenderProjects/StylizedAirship/rig
B=/mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/blender
PY=/mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/4.5/python/bin/python3.11
S=$RIG/scripts; T=$RIG/tmp/verify; C=$RIG/checks/verify
export TMPDIR=$T; mkdir -p $T $C $RIG/renders/verify
cp /mnt/new_partition/BlenderProjects/StylizedAirship/StylizedAirship.blend $C/Talal_copy.blend
cp $RIG/props/AirshipProps.blend $T/AirshipProps_copy.blend
cp $RIG/AirshipRig.blend $T/AirshipRig_copy.blend
run() { echo "== $*"; "$B" -b --factory-startup "$@" 2>&1 | grep -E '^\[|Error|Traceback|line [0-9]+,' ; }
run $C/Talal_copy.blend --python $S/verify_fbx.py                                              # 1 low-level FBX
run $C/Talal_copy.blend --python $S/verify_fbx.py -- --fbx $RIG/export/SK_Airship_testanim.fbx --out $C/fbx_verify_testanim.json
run --python $S/verify_import.py                                                               # 1+2 import, weights, deform test, atlas overlap
run $T/AirshipProps_copy.blend --python $S/verify_props.py                                     # 4 props vs atlas source
run $T/AirshipRig_copy.blend --python $S/verify_rigblend.py
$PY -I $S/verify_sketch_camera.py                                                              # 3 sketch cameras
run $C/Talal_copy.blend --python $S/verify_sketch_marks.py                                     #   marks on the ship
run --python $S/verify_render.py                                                               # 2+3 renders
run --python $S/verify_render.py -- --only sketchcam_3_cannon_spots_ghost --ghost-fwd -4.881,-0.076,0.1265   # yellow = the old fore station x -5.344 (before 2026-11-22)
run $T/AirshipRig_copy.blend --python $S/verify_station_fit.py                               #   cannon at each rail gap vs the marks
python3 $S/verify_sketch_overlay.py
run --python $S/verify_props_render.py                                                         # 4 textured props
rm -f $T/AirshipRig_copy.blend
