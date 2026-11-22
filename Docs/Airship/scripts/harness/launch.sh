#!/bin/bash
# usage: launch.sh [map] [--with-other-editor] -> starts the editor on the airship clone with the Python inbox
# (no MCP server: Talal's own editor may hold port 8000), waits for the inbox and for shader compiles to go idle.
# Refuses when another UnrealEditor runs unless --with-other-editor is given AND >= 7 GB are available.
# Output: Saved/Airship/editor_stdout.log
W=/mnt/new_partition/UnrealProjects/_AirshipWork
H=$W/Docs/Airship/scripts/harness
MAP=/Engine/Maps/Templates/Template_Default; OTHER=0
for a in "$@"; do case "$a" in --with-other-editor) OTHER=1;; *) MAP="$a";; esac; done
for p in $(ps -C UnrealEditor -o pid=); do
  if tr '\0' ' ' < /proc/$p/cmdline | grep -q '_AirshipWork'; then echo "airship editor already running: $p"; exit 2; fi
  if [ $OTHER = 0 ]; then echo "another UnrealEditor is running (pid $p): pass --with-other-editor"; exit 2; fi
done
AV=$(free -g | awk '/^Mem:/{print $7}')
if [ "$AV" -lt 7 ] && [ -n "$(ps -C UnrealEditor -o pid=)" ]; then echo "only ${AV} GB available with another editor open: not starting"; exit 4; fi
mkdir -p $W/Saved/ClaudeInbox $W/Saved/Airship; rm -f $W/Saved/ClaudeInbox/*.py
# After a crash the editor opens a modal "Restore Packages" dialog that blocks the inbox: move the restore data aside.
R=$W/Saved/Autosaves/PackageRestoreData.json; [ -f $R ] && mv $R $W/Saved/Airship/PackageRestoreData.$(date -u +%H%M%S).json && echo "moved aside $R"
cd /mnt/new_partition/5.8/Engine/Binaries/Linux
DISPLAY=:0 XAUTHORITY=/home/talal/.Xauthority setsid nohup ./UnrealEditor $W/Aura.uproject $MAP -norelativemousemode "-ExecCmds=py $H/pt_boot.py" > $W/Saved/Airship/editor_stdout.log 2>&1 < /dev/null & disown
sleep 5
for p in $(ps -C UnrealEditor -o pid=); do tr '\0' ' ' < /proc/$p/cmdline | grep -q '_AirshipWork' && EP=$p; done
echo "editor pid $EP"
echo 'print("alive")' > $W/Saved/Airship/alive_probe.py
$H/inbox.sh alive $W/Saved/Airship/alive_probe.py 900 || exit 3
c=0; s=0
while [ $c -lt 10 ] && [ $s -lt 1200 ]; do if [ "$(ps -C ShaderCompileWorker -o pid= | wc -l)" = 0 ]; then c=$((c+1)); else c=0; fi; s=$((s+1)); sleep 1; done
echo "shaders idle after ${s}s"; date -u +%H:%M:%S
