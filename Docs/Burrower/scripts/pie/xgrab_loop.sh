#!/bin/bash
# usage: setsid nohup xgrab_loop.sh [request_dir] > /dev/null 2>&1 &
# For every <request_dir>/<label>.req that bw_pie_test.py writes (first line = output dir), grabs every viewable editor /
# PIE window ("Unreal Editor", "Preview", "PIE" in the title) into <output dir>/x_<label>_<n>_<title>.png with ImageMagick
# import, but only windows of the clone's editor process (_NET_WM_PID = the editor whose command line has _BurrowerWork).
# Read-only on the desktop (xdotool search / getwindowname / getwindowpid, xwininfo; no input). Waits up to 10 min for
# that editor, then runs while it lives. A window on a hidden i3 workspace is not viewable and is skipped (logged).
REQ=${1:-/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower/xgrab}
export DISPLAY=${DISPLAY:-:0} XAUTHORITY=${XAUTHORITY:-/home/talal/.Xauthority}
mkdir -p "$REQ"
LOG=$REQ/log.txt
# only the clone's editor (cmdline has _BurrowerWork): the user's own editor windows are never grabbed
clone_pid() { for p in $(ps -C UnrealEditor -o pid=); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q "_BurrowerWork" && { echo $p; return; }; done; }
for i in $(seq 1 600); do [ -n "$(clone_pid)" ] && break; sleep 1; done
EP=$(clone_pid)
echo "$(date -u +%T) xgrab loop start, clone editor pid $EP" >> "$LOG"
while [ -n "$EP" ] && [ -d /proc/$EP ]; do
  for r in "$REQ"/*.req; do
    [ -f "$r" ] || continue
    d=$(head -1 "$r"); l=$(basename "$r" .req); rm -f "$r"
    mkdir -p "$d"
    n=0
    for id in $(xdotool search --name "Unreal Editor|Preview|PIE" 2>/dev/null); do
      wp=$(xdotool getwindowpid "$id" 2>/dev/null)
      # no _NET_WM_PID on the window: accept it only when the clone's editor is the only editor running
      [ -z "$wp" ] && [ "$(ps -C UnrealEditor -o pid= | wc -l)" = 1 ] && wp=$EP
      [ "$wp" = "$EP" ] || continue
      ms=$(xwininfo -id "$id" 2>/dev/null | grep -c IsViewable)
      nm=$(xdotool getwindowname "$id" 2>/dev/null)
      geo=$(xwininfo -id "$id" 2>/dev/null | awk '/Width:/{w=$2}/Height:/{h=$2}END{print w"x"h}')
      echo "$(date -u +%T) $l $id viewable=$ms $geo '$nm'" >> "$LOG"
      [ "$ms" = 1 ] || continue
      case "$geo" in 1x*|*x1|0x*|x) continue;; esac
      n=$((n+1)); tag=$(echo "$nm" | tr -c 'A-Za-z0-9' '_' | cut -c1-40)
      import -window "$id" "$d/x_${l}_${n}_${tag}.png" 2>>"$LOG"
    done
    [ $n = 0 ] && echo "$(date -u +%T) $l: no viewable window (editor on a hidden workspace?)" >> "$LOG"
  done
  sleep 0.2
done
echo "$(date -u +%T) xgrab loop end (clone editor $EP gone)" >> "$LOG"
