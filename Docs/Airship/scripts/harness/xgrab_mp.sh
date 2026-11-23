#!/bin/bash
# usage: xgrab_mp.sh [req_dir] -> X window grabs for the listen-server PIE test (as_45_pie_mp.py): for every
# <req_dir>/<label>.req (content: main | client | both) grabs the editor's main window (the host's PIE viewport) and/or the
# PIE client window ("Aura Preview [NetMode: Client 1] ..."). Read-only X calls only (xwininfo, ImageMagick import): no
# xdotool, no input. Only viewable windows are grabbed. Output: <req_dir>/x_<label>_<main|client>.png, log in <req_dir>/log.txt.
# Ends when the clone editor is gone.
D=${1:-/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/mp/xgrab}
mkdir -p "$D"
export DISPLAY=:0 XAUTHORITY=/home/talal/.Xauthority
ours() { for p in $(ps -C UnrealEditor -o pid=); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q '_AirshipWork' && echo $p; done; }
while [ -n "$(ours)" ]; do
  for r in "$D"/*.req; do
    [ -f "$r" ] || continue
    l=$(basename "$r" .req); which=$(head -1 "$r" 2>/dev/null); rm -f "$r"
    for kind in client main; do
      [ "$which" = both ] || [ "$which" = "$kind" ] || continue
      if [ $kind = main ]; then pat='"Aura - Unreal Editor"'; else pat='NetMode: Client'; fi
      for id in $(xwininfo -root -tree 2>/dev/null | grep -F "$pat" | awk '{print $1}'); do
        info=$(xwininfo -id "$id" 2>/dev/null)
        vis=$(echo "$info" | grep -c IsViewable)
        w=$(echo "$info" | awk '/Width:/{print $2}'); h=$(echo "$info" | awk '/Height:/{print $2}')
        echo "$(date -u +%T) $l $kind $id viewable=$vis ${w}x${h}" >> "$D/log.txt"
        [ "$vis" = 1 ] || continue
        [ "${w:-0}" -gt 300 ] && [ "${h:-0}" -gt 200 ] || continue
        import -window "$id" "$D/x_${l}_${kind}.png" 2>>"$D/log.txt" && echo "$(date -u +%T) $l -> x_${l}_${kind}.png" >> "$D/log.txt"
        break
      done
    done
  done
  sleep 0.2
done
echo "$(date -u +%T) editor gone, loop ends" >> "$D/log.txt"
