#!/usr/bin/env python3
# bw_07_settings_ini.py -- Burrower editor session, EDITOR_SESSION.md step 7 (ini half) and cpp_notes.md items 6 and 7.
#
# Run with the plain system python3 while the Unreal Editor of the clone is CLOSED:
#   python3 /mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/bw_07_settings_ini.py [--dry-run]
#
# Idempotently edits /mnt/new_partition/UnrealProjects/_BurrowerWork/Config/DefaultGame.ini:
#   [/Script/Aura.BurrowerSettings]                 (UCLASS(Config = Game, DefaultConfig) UBurrowerSettings, BurrowerSettings.h)
#   BurrowerClass=/Game/Assets/Enemies/Burrower/BP_Burrower.BP_Burrower_C
#                                                   (TSoftClassPtr written like [/Script/Aura.MyHexBridgeSettings] BridgeClass=)
#   [/Script/UnrealEd.ProjectPackagingSettings]     (UProjectPackagingSettings::OverrideConfigSection keeps the UnrealEd name,
#   +DirectoriesToAlwaysCook=(Path="/Game/Assets/Enemies/Burrower")   ProjectPackagingSettings.h:190-193)
#                                                   (inserted after the existing +DirectoriesToAlwaysCook lines)
# Everything else is kept byte for byte (encoding, BOM, line endings, order, blank lines). Nothing is duplicated:
# a second run prints "nothing to change". Before a write the original is copied to
# Saved/Burrower/DefaultGame.ini.bak_bw07_<time>. A unified diff of the change is printed.
#
# Options: --dry-run (print the diff only), --force (skip the "editor running" check), --ini PATH (another file, for tests),
#          --backup-dir DIR (default Saved/Burrower).
# Exit code: 0 ok, 1 FAIL, 2 refused because the editor is running.

import argparse
import difflib
import os
import re
import shutil
import sys
import time

WORK = '/mnt/new_partition/UnrealProjects/_BurrowerWork'
INI_DEFAULT = os.path.join(WORK, 'Config', 'DefaultGame.ini')
BACKUP_DIR = os.path.join(WORK, 'Saved', 'Burrower')

BURROWER_SECTION = '/Script/Aura.BurrowerSettings'
BURROWER_KEY = 'BurrowerClass'
BURROWER_VALUE = '/Game/Assets/Enemies/Burrower/BP_Burrower.BP_Burrower_C'
PACK_SECTION = '/Script/UnrealEd.ProjectPackagingSettings'
COOK_KEY = 'DirectoriesToAlwaysCook'
COOK_DIR = '/Game/Assets/Enemies/Burrower'
COOK_LINE = '+%s=(Path="%s")' % (COOK_KEY, COOK_DIR)
BP_FILE = os.path.join(WORK, 'Content', 'Assets', 'Enemies', 'Burrower', 'BP_Burrower.uasset')

COUNT = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}
COOK_RE = re.compile(r'^\s*([+\-!.]?)' + COOK_KEY + r'\s*=\s*\(\s*Path\s*=\s*"?([^")]*)"?\s*\)\s*$')


def out(tag, msg):
    COUNT[tag] += 1
    print('%s: %s' % (tag, msg))


def norm_dir(p):
    return p.strip().strip('"').rstrip('/').lower()


def editor_running_on_clone():
    """PIDs of UnrealEditor processes whose command line names the clone (read from /proc, nothing is touched)."""
    pids = []
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            with open('/proc/%s/cmdline' % d, 'rb') as f:
                argv = [a.decode('utf-8', 'replace') for a in f.read().split(b'\0') if a]
        except Exception:
            continue
        if not argv:
            continue
        exe = os.path.basename(argv[0])
        if exe.startswith('UnrealEditor') and any('_BurrowerWork' in a for a in argv):
            pids.append((int(d), exe))
    return pids


def read_ini(path):
    raw = open(path, 'rb').read()
    if raw.startswith(b'\xff\xfe'):
        enc, bom = 'utf-16-le', b'\xff\xfe'
    elif raw.startswith(b'\xfe\xff'):
        enc, bom = 'utf-16-be', b'\xfe\xff'
    elif raw.startswith(b'\xef\xbb\xbf'):
        enc, bom = 'utf-8', b'\xef\xbb\xbf'
    else:
        enc, bom = 'latin-1', b''           # latin-1 round-trips every byte unchanged
    text = raw[len(bom):].decode(enc)
    crlf = text.count('\r\n')
    nl = '\r\n' if crlf and crlf >= (text.count('\n') - crlf) else '\n'
    lines = re.findall(r'[^\n]*\n|[^\n]+$', text)   # every piece keeps its own line ending; ''.join(lines) == text
    assert ''.join(lines) == text
    return raw, enc, bom, text, nl, lines


def body(line):
    return line.rstrip('\r\n')


def sections(lines):
    """[(name, header_index, end_index_exclusive)] in file order."""
    secs = []
    for i, l in enumerate(lines):
        s = body(l).strip()
        if len(s) > 2 and s.startswith('[') and s.endswith(']'):
            if secs:
                secs[-1][2] = i
            secs.append([s[1:-1], i, len(lines)])
    return [tuple(s) for s in secs]


def last_content_index(lines, sec):
    """Index of the last non-blank line of a section (the header if it has no keys)."""
    name, h, e = sec
    last = h
    for i in range(h + 1, e):
        if body(lines[i]).strip():
            last = i
    return last


def ensure_newline(lines, i, nl):
    if not lines[i].endswith('\n'):
        lines[i] = lines[i] + nl


def append_section(lines, nl, name, key_lines):
    """New section at the end of the file, separated like the file's other sections (blank line before and after)."""
    if lines:
        ensure_newline(lines, len(lines) - 1, nl)
        if body(lines[-1]).strip():
            lines.append(nl)
    lines.append('[%s]%s' % (name, nl))
    for k in key_lines:
        lines.append(k + nl)
    lines.append(nl)


def set_burrower_class(lines, nl):
    secs = [s for s in sections(lines) if s[0] == BURROWER_SECTION]
    want = '%s=%s' % (BURROWER_KEY, BURROWER_VALUE)
    if not secs:
        append_section(lines, nl, BURROWER_SECTION, [want])
        return 'added section [%s] with %s' % (BURROWER_SECTION, want)
    if len(secs) > 1:
        out('WARN', '[%s] appears %d times in the file' % (BURROWER_SECTION, len(secs)))
    hits = []
    for name, h, e in secs:
        for i in range(h + 1, e):
            k = body(lines[i]).split('=', 1)[0].strip()
            if k.lstrip('+-!.') == BURROWER_KEY:
                hits.append(i)
    if hits:
        if all(body(lines[i]).strip() == want for i in hits):
            return None
        if len(hits) > 1:
            out('WARN', '%d %s lines found; all are set to the BP_Burrower class' % (len(hits), BURROWER_KEY))
        changed = []
        for i in hits:
            if body(lines[i]).strip() != want:
                ending = lines[i][len(body(lines[i])):] or nl
                changed.append(body(lines[i]).strip())
                lines[i] = want + ending
        return 'replaced %s with %s' % (changed, want)
    i = last_content_index(lines, secs[0])
    ensure_newline(lines, i, nl)
    lines.insert(i + 1, want + nl)
    return 'inserted %s into [%s]' % (want, BURROWER_SECTION)


def add_cook_dir(lines, nl):
    secs = [s for s in sections(lines) if s[0] == PACK_SECTION]
    if not secs:
        out('WARN', 'no [%s] section in the file: adding one' % PACK_SECTION)
        append_section(lines, nl, PACK_SECTION, [COOK_LINE])
        return 'added section [%s] with %s' % (PACK_SECTION, COOK_LINE)
    if len(secs) > 1:
        out('WARN', '[%s] appears %d times in the file' % (PACK_SECTION, len(secs)))
    last_cook = None
    for name, h, e in secs:
        for i in range(h + 1, e):
            m = COOK_RE.match(body(lines[i]))
            if not m:
                continue
            op, path = m.group(1), m.group(2)
            if norm_dir(path) == norm_dir(COOK_DIR):
                if op in ('+', ''):
                    return None
                out('WARN', 'line %d removes the Burrower folder from the cook list: %r (left as is)' % (i + 1, body(lines[i])))
            if secs[0][1] < i < secs[0][2]:
                last_cook = i
    i = last_cook if last_cook is not None else last_content_index(lines, secs[0])
    ensure_newline(lines, i, nl)
    lines.insert(i + 1, COOK_LINE + nl)
    return 'inserted %s into [%s] (after line %d)' % (COOK_LINE, PACK_SECTION, i + 1)


def verify(path):
    _raw, _enc, _bom, _text, _nl, lines = read_ini(path)
    bc = []
    cook = 0
    for name, h, e in sections(lines):
        for i in range(h + 1, e):
            b = body(lines[i]).strip()
            if name == BURROWER_SECTION and b.split('=', 1)[0].strip() == BURROWER_KEY:
                bc.append(b.split('=', 1)[1].strip())
            if name == PACK_SECTION:
                m = COOK_RE.match(b)
                if m and m.group(1) in ('+', '') and norm_dir(m.group(2)) == norm_dir(COOK_DIR):
                    cook += 1
    if bc == [BURROWER_VALUE]:
        out('PASS', '[%s] %s=%s' % (BURROWER_SECTION, BURROWER_KEY, BURROWER_VALUE))
    else:
        out('FAIL', '[%s] %s values: %s' % (BURROWER_SECTION, BURROWER_KEY, bc))
    if cook == 1:
        out('PASS', '[%s] %s once' % (PACK_SECTION, COOK_LINE))
    else:
        out('FAIL', '[%s] Burrower cook entries: %d (want exactly 1)' % (PACK_SECTION, cook))


def check_saved_overrides():
    """Saved/Config/<platform>/Game.ini layers on top of DefaultGame.ini: warn if it overrides our keys."""
    root = os.path.join(WORK, 'Saved', 'Config')
    if not os.path.isdir(root):
        return
    for plat in sorted(os.listdir(root)):
        p = os.path.join(root, plat, 'Game.ini')
        if not os.path.isfile(p):
            continue
        try:
            _r, _e, _b, _t, _n, lines = read_ini(p)
        except Exception as e:
            out('WARN', 'could not read %s: %s' % (p, e))
            continue
        for name, h, e in sections(lines):
            if name not in (BURROWER_SECTION, PACK_SECTION):
                continue
            for i in range(h + 1, e):
                b = body(lines[i]).strip()
                if b.lstrip('+-!.').split('=', 1)[0].strip() in (BURROWER_KEY, COOK_KEY):
                    out('WARN', '%s:%d overrides DefaultGame.ini: %r' % (p, i + 1, b))


def main():
    ap = argparse.ArgumentParser(description='Burrower DefaultGame.ini settings (run with the editor closed)')
    ap.add_argument('--dry-run', action='store_true', help='print the diff, write nothing')
    ap.add_argument('--force', action='store_true', help='skip the "editor running on the clone" check')
    ap.add_argument('--ini', default=INI_DEFAULT, help='ini file to edit (default: the clone DefaultGame.ini)')
    ap.add_argument('--backup-dir', default=BACKUP_DIR, help='where the backup copy goes (default: Saved/Burrower)')
    args = ap.parse_args()
    path = os.path.abspath(args.ini)

    running = editor_running_on_clone()
    if running and not args.force and not args.dry_run:
        out('FAIL', 'an Unreal Editor is running on the clone %s: quit it first (it keeps its own config in memory and '
            'may write DefaultGame.ini itself). Nothing was written.' % running)
        return 2
    if running:
        out('WARN', 'Unreal Editor running on the clone: %s' % running)
    if not os.path.isfile(BP_FILE):
        out('WARN', '%s does not exist yet: BurrowerClass will point to a missing class until bw_06_blueprint.py has saved '
            'BP_Burrower' % BP_FILE)

    raw, enc, bom, text, nl, lines = read_ini(path)
    out('INFO', '%s: %d bytes, %d lines, encoding %s%s, line endings %s'
        % (path, len(raw), len(lines), enc, ' + BOM' if bom else '', 'CRLF' if nl == '\r\n' else 'LF'))
    for name in (BURROWER_SECTION, PACK_SECTION):
        n = len([s for s in sections(lines) if s[0] == name])
        out('INFO', 'section [%s]: %d' % (name, n))
    new_lines = list(lines)
    changes = [c for c in (set_burrower_class(new_lines, nl), add_cook_dir(new_lines, nl)) if c]
    new_text = ''.join(new_lines)

    if not changes or new_text == text:
        out('PASS', 'DefaultGame.ini already has both settings: nothing to change, nothing written')
        verify(path)
        check_saved_overrides()
        return 0 if COUNT['FAIL'] == 0 else 1

    for c in changes:
        out('INFO', c)
    diff = list(difflib.unified_diff([body(l) for l in lines], [body(l) for l in new_lines],
                                     'a/Config/DefaultGame.ini', 'b/Config/DefaultGame.ini', lineterm=''))
    print('--- diff ---')
    for d in diff:
        print(d)
    print('--- end diff ---')

    # Safety: compared line by line, the only differences allowed are inserted lines and a changed BurrowerClass value;
    # every kept line keeps its exact bytes, including its line ending (only a missing final newline may be added).
    old_b = [body(l) for l in lines]
    new_b = [body(l) for l in new_lines]
    ops = difflib.SequenceMatcher(None, old_b, new_b, autojunk=False).get_opcodes()
    bad = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            for k in range(i2 - i1):
                o, n = lines[i1 + k], new_lines[j1 + k]
                if o != n and not (i1 + k == len(lines) - 1 and not o.endswith('\n') and n == o + nl):
                    bad.append(('ending', i1 + k + 1, o, n))
        elif tag == 'replace':
            if not all(b.strip().split('=', 1)[0].strip().lstrip('+-!.') == BURROWER_KEY for b in old_b[i1:i2]):
                bad.append((tag, i1 + 1, old_b[i1:i2], new_b[j1:j2]))
        elif tag == 'delete':
            bad.append((tag, i1 + 1, old_b[i1:i2], []))
    if bad:
        out('FAIL', 'the edit would change more than the two settings %s: nothing written' % bad[:5])
        return 1
    out('PASS', 'every other line is kept byte for byte (only insertions%s)'
        % (' and the BurrowerClass value' if any(o[0] == 'replace' for o in ops) else ''))

    if args.dry_run:
        out('INFO', '--dry-run: nothing written')
        return 0

    os.makedirs(args.backup_dir, exist_ok=True)
    bak = os.path.join(args.backup_dir, 'DefaultGame.ini.bak_bw07_%s' % time.strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(path, bak)
    out('INFO', 'backup: %s' % bak)
    data = bom + new_text.encode(enc)
    with open(path, 'wb') as f:
        f.write(data)
    out('INFO', 'wrote %s (%d -> %d bytes)' % (path, len(raw), len(data)))

    verify(path)
    if open(path, 'rb').read() == data:
        out('PASS', 're-read file matches what was written')
    else:
        out('FAIL', 're-read file differs from what was written (restore %s)' % bak)
    check_saved_overrides()
    return 0 if COUNT['FAIL'] == 0 else 1


if __name__ == '__main__':
    try:
        rc = main()
    except Exception as e:
        import traceback
        out('FAIL', 'bw_07_settings_ini raised %s\n%s' % (e, traceback.format_exc()))
        rc = 1
    print('SUMMARY: %d PASS, %d WARN, %d FAIL' % (COUNT['PASS'], COUNT['WARN'], COUNT['FAIL']))
    sys.exit(rc)
