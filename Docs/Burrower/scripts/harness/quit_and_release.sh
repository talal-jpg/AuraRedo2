#!/bin/bash
# usage: quit_and_release.sh -> quits the clone's editor cleanly and releases the shared Unreal lock.
# 1. closes every asset editor first (closing an open ABP editor during shutdown crashed UE 5.8 here on
#    2026-11-21: SIGSEGV in FAnimationBlueprintEditor::~FAnimationBlueprintEditor), then quit_editor().
# 2. waits up to 180 s for the editor to exit; if it hangs in CrashReportClientEditor, ends both by PID
#    (only processes whose command line names the _BurrowerWork clone).
# 3. releases /mnt/new_partition/UnrealProjects/.ue_lock ONLY when no Unreal process of ours is left.
W=/mnt/new_partition/UnrealProjects/_BurrowerWork
H=$W/Docs/Burrower/scripts/harness
L=/mnt/new_partition/UnrealProjects/.ue_lock
T=$(mktemp /tmp/bw_quit_XXXX.py)
cat > $T <<'EOF'
import unreal
try:
    unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_asset_editors()
except Exception as e:
    print('close_all_asset_editors failed: %r' % e)
d = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
m = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
print('dirty (discarded)', d, m)
unreal.SystemLibrary.quit_editor()
EOF
ours() { ps -eo pid=,args= | grep -E '[U]nrealEditor|[C]rashReportClient' | grep '_BurrowerWork' | awk '{print $1}'; }
if [ -n "$(ours)" ]; then
  $H/inbox.sh quit $T 30
  for i in $(seq 1 180); do [ -z "$(ours)" ] && break; sleep 1; done
  if [ -n "$(ours)" ]; then
    echo "editor still running after 180 s: $(ours | tr '\n' ' ') -> TERM"
    ours | xargs -r kill -TERM; sleep 20
    ours | xargs -r kill -KILL; sleep 2
  fi
fi
rm -f $T
if [ -n "$(ours)" ]; then echo "NOT releasing the lock: still running $(ours | tr '\n' ' ')"; exit 1; fi
if [ -d $L ] && grep -q '^burrower' $L/owner 2>/dev/null; then
  rm -rf $L && echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) burrower released" >> /mnt/new_partition/UnrealProjects/.ue_lock_log
  echo "lock released $(date -u +%T)"
else
  echo "lock not held by burrower; nothing released"
fi
