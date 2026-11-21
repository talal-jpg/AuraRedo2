#!/bin/bash
# usage: bw_ini_playmode.sh set|restore|show
# Sets the clone's PIE mode to "listen server + 1 client" in
#   Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini, section [/Script/UnrealEd.LevelEditorPlaySettings]:
#     PlayNetMode=PIE_ListenServer   PlayNumberOfClients=2 (instance 0 = listen server, 1 = client; PlayLevel.cpp:2887-2918)
#     RunUnderOneProcess=True
# ONLY WITH THE EDITOR CLOSED (the editor reads the file at start and may write it at exit).
# set:     backs the file up once (<ini>.bw_pie_backup, plus the 3 original lines in <ini>.bw_pie_keys), then edits the 3 keys.
# restore: puts the 3 keys back to their backed-up values (other changes the editor made to the file are kept),
#          keeps the full backup as <ini>.bw_pie_backup.<UTC stamp>.
# show:    prints the 3 keys.
W=/mnt/new_partition/UnrealProjects/_BurrowerWork
INI=$W/Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini
BK=$INI.bw_pie_backup
KEYS=$INI.bw_pie_keys
MODE=${1:-show}
# editors of this clone (an editor of another project, e.g. the user's AuraRedo3, does not use this ini)
clone_pids() { for p in $(ps -C UnrealEditor -o pid=); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q "_BurrowerWork" && echo $p; done; }
if [ "$MODE" != show ] && [ -n "$(clone_pids)" ]; then
  echo "FAIL: the clone's UnrealEditor is running (pid $(clone_pids | tr '\n' ' ')): close it first (bw_quit_clean.py), the ini is read at start and written at exit"
  exit 2
fi
[ -f "$INI" ] || { echo "FAIL: $INI not found"; exit 2; }
python3 - "$MODE" "$INI" "$BK" "$KEYS" <<'EOF'
import sys, os, json, shutil, time
mode, ini, bk, keys = sys.argv[1:5]
SEC = '[/Script/UnrealEd.LevelEditorPlaySettings]'
WANT = {'PlayNetMode': 'PIE_ListenServer', 'PlayNumberOfClients': '2', 'RunUnderOneProcess': 'True'}

def read(path):
    with open(path) as f:
        return f.read().split('\n')

def section_range(lines):
    s = None
    for i, l in enumerate(lines):
        if l.strip() == SEC:
            s = i
            continue
        if s is not None and l.startswith('[') and l.strip().endswith(']'):
            return s, i
    return (s, len(lines)) if s is not None else (None, None)

def get_keys(lines):
    s, e = section_range(lines)
    out = {}
    if s is None:
        return out
    for l in lines[s + 1:e]:
        k = l.split('=', 1)[0]
        if k in WANT:
            out[k] = l.split('=', 1)[1] if '=' in l else ''
    return out

def put_keys(lines, values):
    """values: key -> value, or None to remove the key."""
    s, e = section_range(lines)
    if s is None:
        lines = lines + ['', SEC]
        s, e = len(lines) - 1, len(lines)
    body = lines[s + 1:e]
    done = set()
    new = []
    for l in body:
        k = l.split('=', 1)[0]
        if k in values:
            if k in done or values[k] is None:
                continue
            new.append('%s=%s' % (k, values[k]))
            done.add(k)
        else:
            new.append(l)
    # missing keys go right after the section's last non-blank line
    ins = len(new)
    while ins > 0 and new[ins - 1].strip() == '':
        ins -= 1
    for k, v in values.items():
        if k not in done and v is not None:
            new.insert(ins, '%s=%s' % (k, v))
            ins += 1
    return lines[:s + 1] + new + lines[e:]

lines = read(ini)
if mode == 'show':
    print('INFO: %s %s' % (SEC, get_keys(lines)))
elif mode == 'set':
    if not os.path.exists(bk):
        shutil.copy2(ini, bk)
        with open(keys, 'w') as f:
            json.dump({k: get_keys(lines).get(k) for k in WANT}, f)
        print('INFO: backup %s, original keys %s' % (bk, get_keys(lines)))
    else:
        print('WARN: backup %s already exists (an earlier set was not restored): kept, original keys from %s' % (bk, keys))
    with open(ini, 'w') as f:
        f.write('\n'.join(put_keys(lines, dict(WANT))))
    print('PASS: set %s' % get_keys(read(ini)))
elif mode == 'restore':
    if not os.path.exists(keys):
        print('WARN: no %s (nothing was set): unchanged %s' % (keys, get_keys(lines)))
        sys.exit(0)
    with open(keys) as f:
        orig = json.load(f)
    with open(ini, 'w') as f:
        f.write('\n'.join(put_keys(lines, orig)))
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    if os.path.exists(bk):
        os.replace(bk, bk + '.' + stamp)
    os.replace(keys, keys + '.' + stamp)
    print('PASS: restored %s (full backup kept as %s.%s)' % (get_keys(read(ini)), bk, stamp))
else:
    print('usage: bw_ini_playmode.sh set|restore|show')
    sys.exit(2)
EOF
