#!/bin/bash
# usage: launch.sh [map] -> starts the editor on the Burrower clone with the MCP server and the Python inbox,
# waits for the inbox and for shader compiles to go idle. Output: Saved/Burrower/editor_stdout.log
W=/mnt/new_partition/UnrealProjects/_BurrowerWork
H=$W/Docs/Burrower/scripts/harness
MAP=${1:-/Engine/Maps/Templates/Template_Default}
if [ -n "$(ps -C UnrealEditor -o pid=)" ]; then echo "an UnrealEditor is already running:"; ps -C UnrealEditor -o pid,args; exit 2; fi
cd /mnt/new_partition/5.8/Engine/Binaries/Linux
DISPLAY=:0 XAUTHORITY=/home/talal/.Xauthority setsid nohup ./UnrealEditor $W/Aura.uproject $MAP -norelativemousemode "-ExecCmds=ModelContextProtocol.StartServer,py $H/pt_boot.py" > $W/Saved/Burrower/editor_stdout.log 2>&1 < /dev/null & disown
sleep 5
EP=$(ps -C UnrealEditor -o pid= | head -1 | tr -d ' ')
[ -n "$EP" ] && setsid nohup /mnt/new_partition/UnrealProjects/AuraRedo3/Saved/ClaudeTools/opt1024/keepawake.sh $EP > /dev/null 2>&1 < /dev/null &
echo "editor pid $EP"
echo 'print("alive")' > /tmp/bw_alive_$$.py
$H/inbox.sh alive /tmp/bw_alive_$$.py 900 || exit 3
rm -f /tmp/bw_alive_$$.py
c=0; s=0
while [ $c -lt 10 ] && [ $s -lt 1200 ]; do if [ "$(ps -C ShaderCompileWorker -o pid= | wc -l)" = 0 ]; then c=$((c+1)); else c=0; fi; s=$((s+1)); sleep 1; done
echo "shaders idle after ${s}s"; date -u +%H:%M:%S
