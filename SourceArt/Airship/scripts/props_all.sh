#!/bin/bash
# Rebuild the prop models and their shared comic-ink atlas (headless Blender, ~3-8 min): Helm.blend, Cannon.blend,
# Turret.blend -> AirshipProps.blend + textures/T_AirshipProps_Comic{Lines,Mask}.png. Never touches Talal's files.
#   bash rig/scripts/props_all.sh          (BLENDER=... another build; BAKE_ARGS=--cpu to bake on the CPU)
# Then run rig_all.sh (the rig places the helm and cannons from AirshipProps.blend, export_turret.py exports the turret).
set -e
RIG=/mnt/new_partition/BlenderProjects/StylizedAirship/rig
B=${BLENDER:-/home/talal/.local/bin/blender}
export TMPDIR=$RIG/tmp
S=$RIG/scripts
cd $RIG
run() { echo "== $*"; "$B" -b --factory-startup "$@" 2>&1 | grep -E '^\[|_REPORT|^saved|Error|Traceback|line [0-9]+,' | cut -c1-600 ; }
run --python $S/model_helm.py                                                       # rig/props/Helm.blend
run --python $S/model_cannon.py                                                     # rig/props/Cannon.blend
run --python $S/model_turret.py                                                     # rig/props/Turret.blend (round 2)
run --python $S/bake_props_comic.py -- --stages assemble,atlas,bake $BAKE_ARGS      # AirshipProps.blend + atlas textures
run --python $S/bake_props_comic.py -- --stages render $BAKE_ARGS                   # renders/props/baked_*.png
