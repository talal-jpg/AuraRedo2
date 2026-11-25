# as_71_match_map.py - round 2 PR B map edits for the team match (SPEC_B section 3). DRY RUN by default: it prints what it
# would do and changes nothing. Knobs (inbox globals; a wrapper sets every one):
#   AS71_APPLY = False     True: make the changes in the editor level (not saved)
#   AS71_SAVE = False      True (with AS71_APPLY): save the level. Refused in Talal's own tree (the project dir is AuraRedo3)
#                          unless AS71_USER_OK = True (his explicit OK for this change)
#   AS71_STARTS = True     4 PlayerStarts on the start floor: Team0 at (-1500, 1500, 205), (1500, 1500, 205), Team1 at
#                          (-1500, -1500, 205), (1500, -1500, 205). They spread the players over the floor in practice and with
#                          bStartAboard off; they don't fix the floor's asymmetry (both pairs are on the floor, v +85 / +115 m)
#   AS71_FOG = False       PathEndFogCount 5 on the path spawner instance (banks at 0, +-110, +-220 m: the lanes covered, Q12)
#   AS71_TAG_SHIP = False  tag the first placed airship without a ShipTeam<id> tag 'ShipTeam0' (Q9; untagged ones are removed
#                          at a versus countdown)
#   AS71_ANY_MAP = False   the coordinates are StartupMap's floor: other maps are refused unless this is True
# Never run during PIE. Report: Saved/Match/as_71_map.json.
# Run: Docs/Airship/scripts/harness/inbox.sh 71 Docs/Airship/scripts/ue/as_71_match_map.py 120
import json, os, traceback  # unreal = inbox namespace

AS71_ITEMS = [('PlayerStart_Team0_A', 'Team0', (-1500.0, 1500.0, 205.0)), ('PlayerStart_Team0_B', 'Team0', (1500.0, 1500.0, 205.0)),
              ('PlayerStart_Team1_A', 'Team1', (-1500.0, -1500.0, 205.0)), ('PlayerStart_Team1_B', 'Team1', (1500.0, -1500.0, 205.0))]
AS71_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Match')
R71 = {'lines': [], 'done': [], 'would': [], 'saved': False}


def o71(tag, msg):
    R71['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def as71_main():
    g = globals()
    apply_, save = bool(g.get('AS71_APPLY')), bool(g.get('AS71_SAVE'))
    starts = g.get('AS71_STARTS', True) is not False
    fog, tag_ship, any_map, user_ok = bool(g.get('AS71_FOG')), bool(g.get('AS71_TAG_SHIP')), bool(g.get('AS71_ANY_MAP')), bool(g.get('AS71_USER_OK'))
    R71['cfg'] = {'apply': apply_, 'save': save, 'starts': starts, 'fog': fog, 'tag_ship': tag_ship, 'any_map': any_map, 'user_ok': user_ok}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if les.is_in_play_in_editor():
        o71('FAIL', 'PIE is running: not touching the level')
        return
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    R71['map'] = w.get_path_name()
    if 'StartupMap' not in w.get_path_name() and not any_map:
        o71('FAIL', 'the open map is %s, not StartupMap (the PlayerStart spots are its floor): set AS71_ANY_MAP to go on' % w.get_path_name())
        return
    proj = os.path.abspath(unreal.Paths.project_dir()).rstrip('/')
    if save and os.path.basename(proj) == 'AuraRedo3' and not user_ok:
        o71('FAIL', 'AS71_SAVE in Talal\'s own tree (%s) needs his explicit OK (AS71_USER_OK = True): nothing changed' % proj)
        return
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    acts = eas.get_all_level_actors()
    labels = dict((a.get_actor_label(), a) for a in acts)
    if starts:
        for label, tag, loc in AS71_ITEMS:
            if label in labels:
                o71('INFO', '%s already there (tag %s)' % (label, labels[label].get_editor_property('player_start_tag')))
                continue
            R71['would'].append('add %s tagged %s at %s' % (label, tag, loc))
            if apply_:
                a = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, 0.0))
                a.set_actor_label(label)
                a.set_editor_property('player_start_tag', unreal.Name(tag))
                R71['done'].append('added %s (%s) at %s' % (label, tag, loc))
    sps = [a for a in acts if a.get_class().get_name().startswith('BP_MyHexPathSpawner') or a.get_class().get_name() == 'MyHexPathSpawner']
    if fog:
        if not sps:
            o71('WARN', 'AS71_FOG: no path spawner in the level')
        for sp in sps[:1]:
            old = sp.get_editor_property('PathEndFogCount')
            if old == 5:
                o71('INFO', '%s PathEndFogCount already 5' % sp.get_actor_label())
                continue
            R71['would'].append('%s PathEndFogCount %s -> 5' % (sp.get_actor_label(), old))
            if apply_:
                sp.set_editor_property('PathEndFogCount', 5)
                R71['done'].append('%s PathEndFogCount %s -> 5' % (sp.get_actor_label(), old))
    if tag_ship:
        ship_cls = unreal.load_class(None, '/Script/Aura.AirshipPawn')
        ships = [a for a in acts if unreal.MathLibrary.class_is_child_of(a.get_class(), ship_cls)]
        free = [a for a in ships if not any(str(t).startswith('ShipTeam') for t in a.tags)]
        if not free:
            o71('INFO', 'AS71_TAG_SHIP: no untagged placed airship (%d placed)' % len(ships))
        for s in free[:1]:
            R71['would'].append('tag %s ShipTeam0' % s.get_actor_label())
            if apply_:
                s.tags = list(s.tags) + [unreal.Name('ShipTeam0')]
                R71['done'].append('tagged %s ShipTeam0' % s.get_actor_label())
    o71('INFO', '%s: %s' % ('applied' if apply_ else 'DRY RUN, would', R71['done'] if apply_ else (R71['would'] or 'nothing')))
    if apply_ and save:
        if R71['done']:
            R71['saved'] = bool(unreal.EditorLevelLibrary.save_current_level())
            o71('INFO' if R71['saved'] else 'FAIL', 'save_current_level: %s' % R71['saved'])
        else:
            o71('INFO', 'nothing changed: not saved')
    elif apply_:
        o71('INFO', 'changed in the editor level only (not saved; the map shows as modified)')


try:
    os.makedirs(AS71_OUT, exist_ok=True)
    as71_main()
    with open(os.path.join(AS71_OUT, 'as_71_map.json'), 'w') as _f:
        json.dump(R71, _f, indent=1, default=str)
    print('RESULT: %s' % ('saved' if R71['saved'] else ('applied' if R71['done'] else 'no change')))
except Exception:  # noqa: BLE001
    print('RESULT: FAIL %s' % traceback.format_exc())
