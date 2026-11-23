#!/bin/bash
# usage: set_play_mode.sh standalone|listen [players=2] -> sets PlayNetMode / PlayNumberOfClients of the airship clone's
# LevelEditorPlaySettings in Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini. Only with the clone editor CLOSED:
# a running editor keeps its own copy and writes it back when it quits (and a value set from Python is never saved).
# listen = Play As Listen Server with <players> players (the host + players-1 clients) in one process.
# A copy of the ini before the change goes to _AirshipWork_logs/scratch/mp/ (once per mode switch).
W=/mnt/new_partition/UnrealProjects/_AirshipWork
INI=$W/Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini
for p in $(ps -C UnrealEditor -o pid=); do
  if tr '\0' ' ' < /proc/$p/cmdline | grep -q '_AirshipWork'; then echo "the airship clone editor runs (pid $p): close it first"; exit 2; fi
done
case "$1" in
  standalone) MODE=PIE_Standalone; N=1;;
  listen) MODE=PIE_ListenServer; N=${2:-2};;
  *) echo "usage: $0 standalone|listen [players]"; exit 1;;
esac
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/scratch/mp; mkdir -p $B
cp "$INI" "$B/EditorPerProjectUserSettings.ini.$(date -u +%H%M%S).before_$1"
python3 - "$INI" "$MODE" "$N" <<'EOF'
import sys
path, mode, n = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path).read().split('\n')
sec, seen = None, set()
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith('[') and s.endswith(']'):
        sec = s
        continue
    if sec == '[/Script/UnrealEd.LevelEditorPlaySettings]':
        if s.startswith('PlayNetMode='):
            lines[i] = 'PlayNetMode=' + mode; seen.add('mode')
        elif s.startswith('PlayNumberOfClients='):
            lines[i] = 'PlayNumberOfClients=' + n; seen.add('n')
        elif s.startswith('RunUnderOneProcess='):
            lines[i] = 'RunUnderOneProcess=True'; seen.add('one')
if seen != {'mode', 'n', 'one'}:
    sys.exit('keys not all found in [/Script/UnrealEd.LevelEditorPlaySettings]: %s' % sorted(seen))
open(path, 'w').write('\n'.join(lines))
EOF
grep -nE '^(PlayNetMode|PlayNumberOfClients|RunUnderOneProcess)=' "$INI"
