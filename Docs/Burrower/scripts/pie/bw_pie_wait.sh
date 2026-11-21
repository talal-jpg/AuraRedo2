#!/bin/bash
# usage: bw_pie_wait.sh [timeout_s=1800]   (start it within 15 min after arming; an older finished result is ignored)
# Waits until Saved/Burrower/pie_result.json says "done" (the test restores and stops PIE itself), the editor crashed
# (new entry in Saved/Crashes) or the editor process is gone; prints a progress line every 30 s and the report at the end.
# Exit: 0 done, 1 timeout, 2 crash, 3 editor gone.
W=/mnt/new_partition/UnrealProjects/_BurrowerWork
D=$W/Docs/Burrower/scripts/pie
R=$W/Saved/Burrower/pie_result.json
CR=$W/Saved/Crashes
T=${1:-1800}
n0=$(ls "$CR" 2>/dev/null | wc -l)
clone_pid() { for p in $(ps -C UnrealEditor -o pid=); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q "_BurrowerWork" && { echo $p; return; }; done; }
t0=$(date +%s)
for i in $(seq 1 "$T"); do
  if [ "$(ls "$CR" 2>/dev/null | wc -l)" != "$n0" ]; then echo "FAIL: editor crash: $CR/$(ls -t "$CR" | head -1)"; python3 -B "$D/bw_pie_report.py" "$R"; exit 2; fi
  if [ -z "$(clone_pid)" ]; then echo "FAIL: the clone's editor process is gone"; python3 -B "$D/bw_pie_report.py" "$R"; exit 3; fi
  if python3 -c "import json,sys; d=json.load(open('$R')); sys.exit(0 if d.get('done') and d.get('armed_wall',0) >= $t0 - 900 else 1)" 2>/dev/null; then
    python3 -B "$D/bw_pie_report.py" "$R"; exit 0
  fi
  if [ $((i % 30)) = 0 ]; then
    python3 -c "import json; d=json.load(open('$R')); print('INFO: %ds phase %s game t %s fps %s checks %s' % ($i, d.get('phase'), d.get('game_t'), d.get('fps_est'), {k: v['status'] for k, v in d.get('checks', {}).items()}))" 2>/dev/null
    echo "INFO: MemAvailable $(awk '/MemAvailable/{printf "%.1f GB", $2/1048576}' /proc/meminfo), clone editor RSS $(ps -o rss= -p "$(clone_pid)" 2>/dev/null | awk '{s+=$1} END {printf "%.1f GB", s/1048576}')"
  fi
  sleep 1
done
echo "FAIL: timeout after ${T}s"; python3 -B "$D/bw_pie_report.py" "$R"; exit 1
