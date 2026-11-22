#!/bin/bash
# Shared Unreal lock for the sessions on this PC (Burrower, swarm, double jump, airship, ...).
#   lock.sh take "<what>"   -> waits (2-min checks) until no Unreal process runs and the lock is free, then takes it
#                              (mkdir), writes "burrower <UTC> <what>" to .ue_lock/owner and logs "<UTC> burrower took <what>".
#                              Exit 0 = taken. Optional env WAIT_MAX_MIN (default 120).
#   lock.sh release [owner] -> releases ONLY a lock whose owner line starts with "burrower" and only when no
#                              Unreal process of the _BurrowerWork clone is left; logs "<UTC> burrower released".
#   lock.sh owner           -> prints the owner line (or "no lock")
D=/mnt/new_partition/UnrealProjects
L=$D/.ue_lock
LOG=$D/.ue_lock_log
utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }
unreal_running() { [ -n "$(ps -C UnrealEditor,UnrealBuildTool,ShaderCompileWorker,CrashReportClientEditor -o pid=)" ]; }
ours_running() { for p in $(ps -C UnrealEditor,CrashReportClientEditor,CrashReportClient,UnrealBuildTool,ShaderCompileWorker -o pid=); do c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null); { [ -z "$c" ] || echo "$c" | grep -q '_BurrowerWork'; } && echo $p; done; }
case "$1" in
  take)
    what="${2:-unreal work}"
    max=$(( ${WAIT_MAX_MIN:-120} * 60 )); waited=0
    while true; do
      if [ ! -d $L ] && ! unreal_running; then
        if mkdir $L 2>/dev/null; then
          echo "burrower $(utc) $what" > $L/owner
          echo "$(utc) burrower took $what" >> $LOG
          echo "TAKEN: $(cat $L/owner)"
          exit 0
        fi
      fi
      if [ $waited -ge $max ]; then echo "NOT TAKEN after $((waited/60)) min; owner: $(cat $L/owner 2>/dev/null || echo none); running: $(ps -C UnrealEditor,UnrealBuildTool -o pid=,args= | cut -c1-120 | tr '\n' ' ')"; exit 1; fi
      sleep 120; waited=$((waited+120))
    done ;;
  release)
    if [ ! -d $L ]; then echo "no lock to release"; exit 0; fi
    o=$(cat $L/owner 2>/dev/null)
    case "$o" in
      burrower*) ;;
      *) echo "NOT releasing: the lock is not ours (owner: ${o:-unknown})"; exit 1 ;;
    esac
    # Optional exact owner line (the one this run's "take" wrote): never release another burrower run's lock
    if [ -n "$2" ] && [ "$o" != "$2" ]; then echo "NOT releasing: owner '$o' is not the lock this run took ('$2')"; exit 1; fi
    if [ -n "$(ours_running)" ]; then echo "NOT releasing: our Unreal processes still run: $(ours_running | tr '\n' ' ')"; exit 1; fi
    rm -rf $L && echo "$(utc) burrower released" >> $LOG && echo "RELEASED $(utc)" ;;
  owner)
    cat $L/owner 2>/dev/null || echo "no lock" ;;
  *) echo "usage: lock.sh take \"<what>\" | release | owner"; exit 2 ;;
esac
