#!/bin/bash
# usage: bw_05b_use_pin_ui.sh -> ticks "Use Pin" on the 19 rig variable rows of ABP_Burrower's Control Rig node through the editor UI
# (see bw_05b_use_pin_ui.py), one inbox call per UI action. The clone editor must be running (harness/launch.sh) on a
# visible workspace, with no other window covering the ABP editor. Then re-run bw_05_anim_bp.py.
D=/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts
T=$(mktemp -d /tmp/bw05b_XXXX)
step() { printf "BW05B_PHASE = '%s'\nexec(open('%s/bw_05b_use_pin_ui.py').read())\n" "$1" "$D" > $T/$1.py; $D/harness/inbox.sh 05b_$1 $T/$1.py 60; sleep 2; }
step open; sleep 3
step select
for i in $(seq 1 25); do
  out=$(step tick); echo "$out"
  echo "$out" | grep -q -E 'ALL_TICKED|FAIL' && break
done
step save
rm -rf $T
