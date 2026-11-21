#!/bin/bash
# usage: inbox.sh <name> <script.py> [timeout_s] -> runs the script in the editor's inbox, prints its .out
IN=${IN:-/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/ClaudeInbox}
N="bw_$1"; T=${3:-60}
rm -f "$IN/$N.out" "$IN/$N.py.taken"
cp "$2" "$IN/$N.py.tmp" && mv "$IN/$N.py.tmp" "$IN/$N.py"
for i in $(seq 1 $((T*5))); do [ -f "$IN/$N.out" ] && { sleep 0.2; cat "$IN/$N.out"; exit 0; }; sleep 0.2; done
echo "TIMEOUT waiting for $N.out"; exit 1
