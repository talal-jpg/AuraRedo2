#!/bin/bash
# usage: xgrab_loop.sh [req_dir] -> while the airship clone editor runs, grabs its main X window (the PIE viewport with
# the HUD) once for every <req_dir>/<label>.req that a PIE harness writes (as_43_pie_validate.py xgrab()).
# Read-only X calls only (xwininfo, ImageMagick import): no xdotool, no input. Grabs only viewable windows (an editor
# on a hidden i3 workspace is skipped and logged). Output: <req_dir>/x_<label>.png, log in <req_dir>/log.txt.
D=${1:-/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/val/xgrab}
mkdir -p "$D"
export DISPLAY=:0 XAUTHORITY=/home/talal/.Xauthority
ours() { for p in $(ps -C UnrealEditor -o pid=); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q '_AirshipWork' && echo $p; done; }
while [ -n "$(ours)" ]; do
  for r in "$D"/*.req; do
    [ -f "$r" ] || continue
    l=$(basename "$r" .req); rm -f "$r"
    n=0
    for id in $(xwininfo -root -tree 2>/dev/null | grep -E '"[^"]*Unreal Editor[^"]*"' | awk '{print $1}'); do
      info=$(xwininfo -id "$id" 2>/dev/null)
      vis=$(echo "$info" | grep -c IsViewable)
      w=$(echo "$info" | awk '/Width:/{print $2}'); h=$(echo "$info" | awk '/Height:/{print $2}')
      echo "$(date -u +%T) $l $id viewable=$vis ${w}x${h}" >> "$D/log.txt"
      [ "$vis" = 1 ] || continue
      [ "${w:-0}" -gt 400 ] && [ "${h:-0}" -gt 300 ] || continue
      n=$((n+1))
      import -window "$id" "$D/x_${l}_${n}.png" 2>>"$D/log.txt" && echo "$(date -u +%T) $l -> x_${l}_${n}.png" >> "$D/log.txt"
    done
  done
  sleep 0.2
done
echo "$(date -u +%T) editor gone, loop ends" >> "$D/log.txt"
