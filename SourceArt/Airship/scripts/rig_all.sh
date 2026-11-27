#!/bin/bash
# Rebuild the whole SK_Airship rig, export and checks (headless Blender, ~3 min). Never touches Talal's .blend files.
#   bash rig/scripts/rig_all.sh            (from anywhere; BLENDER=/path/to/blender to use another build)
# The props (helm, cannons, turret) and their atlas come from rig/props/AirshipProps.blend: rebuild them first with
# props_all.sh when a prop script changed.
set -e
RIG=/mnt/new_partition/BlenderProjects/StylizedAirship/rig
B=${BLENDER:-/home/talal/.local/bin/blender}
export TMPDIR=$RIG/tmp          # keep Blender temp files off the nearly full root filesystem
S=$RIG/scripts
cd $RIG
# pristine input: a byte copy of Talal's file (only refreshed when missing)
[ -f AirshipRig_src.blend ] || cp /mnt/new_partition/BlenderProjects/StylizedAirship/StylizedAirship.blend AirshipRig_src.blend
run() { echo "== $*"; "$B" -b --factory-startup "$@" 2>&1 | grep -E '^\[|Error|Traceback|line [0-9]+,' ; }
run AirshipRig_src.blend --python $S/rig_place.py                                   # 1 placement + cannon/helm/turret clearance
run --python $S/rig_build.py                                                        # 2-4 deck removals, armature, skin, props, test action
run --python $S/rig_export.py                                                       # 5 SK_Airship.fbx
run --python $S/rig_export.py -- --anim                                             #   SK_Airship_testanim.fbx
run --python $S/export_turret.py                                                    #   SM_AirshipTurret_Base/Gun.fbx + turret_dims.json
run --python $S/rig_fbx_inspect.py -- export/SK_Airship.fbx --json checks/rig/fbx_SK_Airship.json --csv checks/rig/bones_ue.csv
run --python $S/rig_fbx_inspect.py -- export/SK_Airship_testanim.fbx --json checks/rig/fbx_SK_Airship_testanim.json
run --python $S/rig_roundtrip.py                                                    # 6 re-import + compare
run --python $S/rig_check_motion.py                                                 #   hull-part motion ranges
run --python $S/rig_render.py                                                       #   renders/rig/*.png
run --python $S/round2_render.py -- --mode after                                    #   renders/round2/after_*.png
python3 $S/rig_readme.py                                                           # 7 export/README_rig.md
