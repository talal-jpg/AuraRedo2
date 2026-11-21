# bw_07_settings.py -- Burrower editor session, EDITOR_SESSION.md step 7 (in-editor half).
#
# Run inside the running UE 5.8 editor of the clone, through the inbox harness, AFTER bw_06_blueprint.py:
#   D=/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts; $D/harness/inbox.sh 07set $D/bw_07_settings.py 60
#
# What it does:
#   * Sets UBurrowerSettings' CDO BurrowerClass = BP_Burrower_C FOR THE RUNNING EDITOR SESSION ONLY, so the next PIE
#     session spawns Burrowers (UBurrowerSpawnSubsystem reads GetDefault<UBurrowerSettings>() at world begin play).
#     Nothing is written to any .ini here: set_editor_property with notify mode NEVER does not call PostEditChangeProperty,
#     and even with notifications UDeveloperSettings::PostEditChangeProperty only broadcasts (DeveloperSettings.cpp:89-92);
#     only the Project Settings details panel writes DefaultGame.ini (SSettingsEditor.cpp:366-455).
#   * Prints every Burrower setting, and whether Config/DefaultGame.ini on disk already has BurrowerClass and the
#     DirectoriesToAlwaysCook entry. To make both permanent run, WITH THE EDITOR CLOSED:
#       python3 /mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/bw_07_settings_ini.py
#   * Reads (does not change) ProjectPackagingSettings.DirectoriesToAlwaysCook of the session.
#
# UBurrowerSettings is not exported to Python (it is wrapped as DeveloperSettings), so its properties are addressed by
# their C++ names ('BurrowerClass', 'bEnabled', ...): snake_case names fail there (Saved/ClaudeInbox/bw_probe1.out).
# Re-runnable: setting the same class again is a no-op.

import unreal
import os
import json
import traceback

BW07_SETTINGS_CLASS = '/Script/Aura.BurrowerSettings'             # Source/Aura/Public/Burrower/BurrowerSettings.h
BW07_BP_CLASS = '/Game/Assets/Enemies/Burrower/BP_Burrower.BP_Burrower_C'
BW07_BURROWER_NATIVE = '/Script/Aura.BurrowerCharacter'
BW07_COOK_DIR = '/Game/Assets/Enemies/Burrower'
BW07_PACKAGING_CLASSES = ('/Script/DeveloperToolSettings.ProjectPackagingSettings', '/Script/UnrealEd.ProjectPackagingSettings')
BW07_MAP_NAME = 'StartupMap'
BW07_SETTINGS_PROPS = ('bEnabled', 'BurrowerClass', 'AllowedMaps', 'FirstSpawnDelay', 'SpawnInterval', 'PlayerRespawnGrace',
                       'SpawnDistanceBehind', 'SpawnHeightOffset', 'MinSpeedForVelocityDirection', 'MaxAlivePerPlayer',
                       'bRespawnAfterDeath', 'DespawnDistance', 'bOnlyCombatPawns', 'PollInterval')

BW07_PROJECT_DIR = os.path.abspath(unreal.Paths.project_dir())
BW07_INI = os.path.join(BW07_PROJECT_DIR, 'Config', 'DefaultGame.ini')
BW07_RESULT_JSON = os.path.join(BW07_PROJECT_DIR, 'Saved', 'Burrower', 'bw_07_settings.json')
BW07_R = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0, 'lines': []}


def bw07_out(tag, msg):
    line = '%s: %s' % (tag, msg)
    print(line)
    BW07_R[tag] = BW07_R.get(tag, 0) + 1
    BW07_R['lines'].append(line)


def bw07_path(v):
    if v is None:
        return 'None'
    try:
        return v.get_path_name()
    except Exception:
        return str(v)


def bw07_load_class(path):
    try:
        return unreal.load_class(None, path)
    except Exception:
        return None


def bw07_ini_sections(path):
    """{section: [stripped lines]} of an .ini (all occurrences of a section merged)."""
    out = {}
    cur = None
    with open(path, encoding='latin-1') as f:
        for line in f:
            s = line.strip()
            if s.startswith('[') and s.endswith(']'):
                cur = s[1:-1]
                out.setdefault(cur, [])
            elif cur is not None and s:
                out[cur].append(s)
    return out


def bw07_norm_dir(p):
    return p.strip().strip('"').rstrip('/').lower()


def bw07_main():
    try:
        if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
            bw07_out('WARN', 'PIE is running: the change applies to the NEXT PIE session (the spawner reads the settings at '
                     'world begin play)')
    except Exception as e:
        bw07_out('WARN', 'could not check PIE: %s' % e)

    scls = bw07_load_class(BW07_SETTINGS_CLASS)
    if scls is None:
        bw07_out('FAIL', '%s not found: build AuraEditor with the Burrower code and restart the editor' % BW07_SETTINGS_CLASS)
        return
    cdo = unreal.get_default_object(scls)
    bp_cls = bw07_load_class(BW07_BP_CLASS)
    if bp_cls is None:
        bw07_out('FAIL', '%s not found: run bw_06_blueprint.py first' % BW07_BP_CLASS)
    else:
        native = bw07_load_class(BW07_BURROWER_NATIVE)
        try:
            is_child = bool(unreal.MathLibrary.class_is_child_of(bp_cls, native))
        except Exception:
            is_child = True
        if not is_child:
            bw07_out('FAIL', 'BP_Burrower_C is not a child of BurrowerCharacter: not set (the soft class pointer is typed '
                     'TSoftClassPtr<ABurrowerCharacter>)')
            bp_cls = None
    if bp_cls is not None:
        try:
            cur = cdo.get_editor_property('BurrowerClass')
        except Exception as e:
            cur = 'ERR %s' % e
        if cur == bp_cls:
            bw07_out('INFO', 'BurrowerClass already %s in this session' % bw07_path(bp_cls))
        else:
            try:
                mode = unreal.PropertyAccessChangeNotifyMode.NEVER
            except Exception:
                mode = None
            try:
                if mode is not None:
                    cdo.set_editor_property('BurrowerClass', bp_cls, mode)
                else:
                    cdo.set_editor_property('BurrowerClass', bp_cls)
                bw07_out('INFO', 'BurrowerClass: %s -> %s (session only, not saved)' % (bw07_path(cur), bw07_path(bp_cls)))
            except Exception as e:
                bw07_out('FAIL', "set_editor_property('BurrowerClass') failed: %s. By hand: Project Settings > Game > "
                         'Burrower > Burrower Class = BP_Burrower (that also writes DefaultGame.ini)' % e)
        try:
            back = cdo.get_editor_property('BurrowerClass')
        except Exception as e:
            back = 'ERR %s' % e
        if back == bp_cls:
            bw07_out('PASS', 'Burrower settings CDO BurrowerClass = %s (running session)' % bw07_path(back))
        else:
            bw07_out('FAIL', 'Burrower settings CDO BurrowerClass reads back %s' % bw07_path(back))

    # every setting of the session
    vals = {}
    for p in BW07_SETTINGS_PROPS:
        try:
            v = cdo.get_editor_property(p)
            vals[p] = [str(x) for x in v] if p == 'AllowedMaps' else (bw07_path(v) if p == 'BurrowerClass' else v)
        except Exception as e:
            vals[p] = 'ERR %s' % e
    bw07_out('INFO', 'Burrower settings (session): %s' % ', '.join('%s=%s' % (k, vals[k]) for k in BW07_SETTINGS_PROPS))
    try:
        bw07_out('INFO', 'ToolsetLibrary view: %s' % unreal.ToolsetLibrary.get_object_properties(cdo, ['BurrowerClass', 'bEnabled']))
    except Exception as e:
        bw07_out('INFO', 'ToolsetLibrary view not available: %s' % e)
    if vals.get('bEnabled') is False:
        bw07_out('WARN', 'bEnabled is False: no automatic spawns (Aura.Burrower.SpawnNow still works)')
    maps = vals.get('AllowedMaps')
    if isinstance(maps, list) and maps and BW07_MAP_NAME not in maps:
        bw07_out('WARN', 'AllowedMaps %s does not contain %s: no Burrowers there' % (maps, BW07_MAP_NAME))

    # DefaultGame.ini on disk (read only)
    want_cls = BW07_BP_CLASS
    try:
        secs = bw07_ini_sections(BW07_INI)
        bc = [l.split('=', 1)[1].strip() for l in secs.get('/Script/Aura.BurrowerSettings', []) if l.split('=', 1)[0].strip() == 'BurrowerClass']
        if bc and bc[-1] == want_cls:
            bw07_out('PASS', 'DefaultGame.ini [/Script/Aura.BurrowerSettings] BurrowerClass=%s' % bc[-1])
        else:
            bw07_out('WARN', 'DefaultGame.ini has no BurrowerClass=%s yet (found %s): close the editor and run '
                     'python3 Docs/Burrower/scripts/bw_07_settings_ini.py, or set it in Project Settings > Game > Burrower'
                     % (want_cls, bc or 'none'))
        cook = [l for l in secs.get('/Script/UnrealEd.ProjectPackagingSettings', []) if l.lstrip('+').startswith('DirectoriesToAlwaysCook=')]
        has = any(bw07_norm_dir(BW07_COOK_DIR) in bw07_norm_dir(l) for l in cook if not l.startswith('-'))
        if has:
            bw07_out('PASS', 'DefaultGame.ini DirectoriesToAlwaysCook contains %s' % BW07_COOK_DIR)
        else:
            bw07_out('WARN', 'DefaultGame.ini DirectoriesToAlwaysCook lacks %s (has %s): run bw_07_settings_ini.py with the '
                     'editor closed' % (BW07_COOK_DIR, cook))
    except Exception as e:
        bw07_out('WARN', 'could not read %s: %s' % (BW07_INI, e))

    # ProjectPackagingSettings of the session (read only)
    pcls = None
    for p in BW07_PACKAGING_CLASSES:
        pcls = bw07_load_class(p)
        if pcls:
            break
    if pcls is None:
        bw07_out('WARN', 'ProjectPackagingSettings class not found (%s)' % (BW07_PACKAGING_CLASSES,))
    else:
        try:
            dirs = []
            for d in unreal.get_default_object(pcls).get_editor_property('DirectoriesToAlwaysCook'):
                try:
                    dirs.append(str(d.get_editor_property('Path')))
                except Exception:
                    dirs.append(d.export_text())
            inside = any(bw07_norm_dir(BW07_COOK_DIR) == bw07_norm_dir(x) or bw07_norm_dir(BW07_COOK_DIR) in bw07_norm_dir(x)
                         for x in dirs)
            bw07_out('INFO', 'session ProjectPackagingSettings.DirectoriesToAlwaysCook = %s (%s %s; only matters for a '
                     'cook/package, which reads DefaultGame.ini)' % (dirs, 'contains' if inside else 'lacks', BW07_COOK_DIR))
        except Exception as e:
            bw07_out('WARN', 'reading DirectoriesToAlwaysCook failed: %s' % e)


try:
    bw07_main()
except Exception as _bw07_e:
    bw07_out('FAIL', 'bw_07_settings raised %s\n%s' % (_bw07_e, traceback.format_exc()))
finally:
    print('SUMMARY: %d PASS, %d WARN, %d FAIL' % (BW07_R['PASS'], BW07_R['WARN'], BW07_R['FAIL']))
    try:
        os.makedirs(os.path.dirname(BW07_RESULT_JSON), exist_ok=True)
        with open(BW07_RESULT_JSON, 'w') as _f:
            json.dump(BW07_R, _f, indent=1)
    except Exception as _e:
        print('WARN: could not write %s: %s' % (BW07_RESULT_JSON, _e))
