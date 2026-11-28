# as_70_match_plan.py - round 2 PR B, READ-ONLY report for the map open in the editor (SPEC_B section 3; nothing is changed
# or saved): the path spawner's values (S, H, MaxYawDeviation, the path-end fog), the lanes they give (both sides, 50
# samples of the straight-path lane; a curved path is built only at BeginPlay, so its envelope is a PIE check: T2.12),
# the PlayerStarts and their tags, placed airships and their tags, the start floor's bounds, the Appendix C distances,
# what as_71_match_map.py would change, and GA_BeamBP's graph around LaunchCharacter (whom the beam knockback launches:
# B6.2, a teammate pushed off a platform is a friendly kill with the fall death).
# Run (no PIE): Docs/Airship/scripts/harness/inbox.sh 70 Docs/Airship/scripts/ue/as_70_match_plan.py 120
# Report: Saved/Match/as_70_plan.json (+ as_70_beam_<graph>.t3d for the graphs that call LaunchCharacter).
import json, math, os, re, traceback  # unreal = inbox namespace

_AS70_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(compile(open(os.path.join(_AS70_UE, 'as_70_matchlib.py')).read(), os.path.join(_AS70_UE, 'as_70_matchlib.py'), 'exec'), globals())

AS70_BEAM = '/Game/Level/GAS/GameplayAbilities/GA_Beam/GA_BeamBP'
AS71_STARTS = [('PlayerStart_Team0_A', 'Team0', (-1500.0, 1500.0, 205.0)), ('PlayerStart_Team0_B', 'Team0', (1500.0, 1500.0, 205.0)),
               ('PlayerStart_Team1_A', 'Team1', (-1500.0, -1500.0, 205.0)), ('PlayerStart_Team1_B', 'Team1', (1500.0, -1500.0, 205.0))]
P70 = {'lines': [], 'counts': {}}


def o70(tag, msg):
    P70['counts'][tag] = P70['counts'].get(tag, 0) + 1
    P70['lines'].append('%s: %s' % (tag, msg))
    print('%s: %s' % (tag, msg))


def as70_prop(a, *names):
    for n in names:
        try:
            return a.get_editor_property(n)
        except Exception:  # noqa: BLE001
            continue
    return None


def as70_bounds(a):
    o, e = a.get_actor_bounds(True)
    return [o.x - e.x, o.x + e.x, o.y - e.y, o.y + e.y, o.z - e.z, o.z + e.z]


def as70_main():
    out = {'map': None, 'spawner': None, 'lanes': None, 'player_starts': [], 'ships': [], 'floor': None, 'appendix_c': {}, 'as71_would': [],
           'beam': {}}
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        o70('FAIL', 'PIE is running: run this with the editor idle')
        return out
    w = mb_editor_world()
    out['map'] = w.get_path_name()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    acts = eas.get_all_level_actors()
    st = mb_cdo('settings')
    clr, lh = float(st.get_editor_property('LaneClearance')), float(st.get_editor_property('LaneHeight'))
    sps = [a for a in acts if mb_isa(a, 'spawner')]
    origins = [a for a in acts if unreal.Name('MatchLaneOrigin') in list(a.tags)]
    O = yaw = H = None
    if sps:
        sp = sps[0]
        S = float(sp.get_layout_scale())
        d = {'name': sp.get_name(), 'label': sp.get_actor_label(), 'location': r(v3(sp.get_actor_location()), 1), 'yaw': r(sp.get_actor_rotation().yaw, 2),
             'S': S}
        for n in ('HexRadius', 'SegmentBoundsHalfWidth', 'MaxYawDeviation', 'NoiseSeed', 'SegmentLength', 'PointsPerSegment', 'ExtendDistance',
                  'InitialSegments', 'PathEndFogCount', 'PathEndFogSpacing'):
            v = as70_prop(sp, n)
            d[n] = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        H = float(d['SegmentBoundsHalfWidth'] or 10000.0) * S
        d['H_cm'] = H
        out['spawner'] = d
        O, yaw = d['location'], d['yaw']
        o70('INFO', 'path spawner %s: S %.2f, H %.0f cm, MaxYawDeviation %s, fog count %s, at %s yaw %s' % (
            d['label'], S, H, d['MaxYawDeviation'], d['PathEndFogCount'], d['location'], d['yaw']))
        if (d['MaxYawDeviation'] or 0.0) > 0.0:
            o70('WARN', 'MaxYawDeviation %s: the lanes follow the envelope of the path built at BeginPlay; the straight lanes below are '
                        'the start only (T2.12 checks the real envelope in PIE)' % d['MaxYawDeviation'])
        if (d['MaxYawDeviation'] or 0.0) >= float(st.get_editor_property('MaxYawForEnvelope')):
            o70('WARN', 'MaxYawDeviation >= MaxYawForEnvelope: the lane subsystem falls back to straight lanes (B2.1)')
        if d['PathEndFogCount'] is not None:
            sp_cm = float(d.get('PathEndFogSpacing') or 5500.0) * S
            n = int(d['PathEndFogCount'])
            out['fog_banks_v_m'] = [r((i - (n - 1) / 2.0) * sp_cm / 100.0, 1) for i in range(n)]
            o70('INFO', 'path-end fog banks at v %s m (count %d); count 5 would give %s m' % (
                out['fog_banks_v_m'], n, [r((i - 2.0) * sp_cm / 100.0, 1) for i in range(5)]))
    elif origins:
        a = origins[0]
        O, yaw, H = r(v3(a.get_actor_location()), 1), r(a.get_actor_rotation().yaw, 2), float(st.get_editor_property('FallbackLaneHalfWidth'))
        o70('INFO', 'no path spawner; MatchLaneOrigin %s at %s yaw %s: fallback H %.0f cm' % (a.get_actor_label(), O, yaw, H))
    else:
        o70('WARN', 'no path spawner and no MatchLaneOrigin actor: no lanes on this map (team ships fly as PR A ships)')
    if O is not None:
        R = H + clr
        a = math.radians(yaw)
        F, Rt = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        S = (out['spawner'] or {}).get('S') or 1.0
        u0 = -float(st.get_editor_property('LaneBackReach')) * S
        init_len = float((out['spawner'] or {}).get('InitialSegments') or 2) * float((out['spawner'] or {}).get('SegmentLength') or 10000.0) * S \
            if out['spawner'] else float(st.get_editor_property('FallbackLaneLength'))
        lanes = {}
        for side in (1, -1):
            pts = []
            for i in range(50):
                u = u0 + (init_len - u0) * i / 49.0
                pts.append(r([O[0] + F[0] * u + Rt[0] * side * R, O[1] + F[1] * u + Rt[1] * side * R, O[2] + lh], 0))
            lanes[str(side)] = pts
        out['lanes'] = {'R_cm': R, 'v_cm': [R, -R], 'lane_start_u_cm': u0, 'path_end_u_cm': init_len,
                        'cruise_end_u_cm': init_len - float(st.get_editor_property('LaneEndMargin')) * S, 'points': lanes,
                        'spawn_points': [r([O[0] + F[0] * float(st.get_editor_property('LaneSpawnU')) + Rt[0] * sd * R,
                                            O[1] + F[1] * float(st.get_editor_property('LaneSpawnU')) + Rt[1] * sd * R, O[2] + lh], 0) for sd in (1, -1)]}
        o70('INFO', 'lanes at v +-%.0f cm: right lane through %s, left lane through %s; spawn points %s; LaneStartU %.0f, initial path end %.0f, '
                    'CruiseEndU %.0f cm' % (R, lanes['1'][0], lanes['-1'][0], out['lanes']['spawn_points'], u0, init_len, out['lanes']['cruise_end_u_cm']))
    for a in acts:
        try:
            if isinstance(a, unreal.PlayerStart):
                out['player_starts'].append({'label': a.get_actor_label(), 'loc': r(v3(a.get_actor_location()), 0),
                                             'tag': str(as70_prop(a, 'player_start_tag', 'PlayerStartTag'))})
            elif mb_isa(a, 'ship'):
                out['ships'].append({'label': a.get_actor_label(), 'loc': r(v3(a.get_actor_location()), 0), 'yaw': r(a.get_actor_rotation().yaw, 1),
                                     'tags': [str(t) for t in a.tags]})
            elif 'floor' in a.get_actor_label().lower() and out['floor'] is None:
                out['floor'] = {'label': a.get_actor_label(), 'bounds': r(as70_bounds(a), 0)}
        except Exception:  # noqa: BLE001
            continue
    o70('INFO', 'PlayerStarts %s' % out['player_starts'])
    o70('INFO' if not out['ships'] else 'WARN', 'placed airships %s (untagged ones are removed at a versus countdown; a ShipTeam<id> tag '
                                               'makes it that team\'s, B3.1, Q9)' % out['ships'])
    o70('INFO', 'floor %s' % out['floor'])
    if out['floor'] and out['lanes'] and O is not None:
        b = out['floor']['bounds']
        R = out['lanes']['R_cm']
        corners = [(b[0], b[2]), (b[0], b[3]), (b[1], b[2]), (b[1], b[3])]
        a = math.radians(yaw)
        for side in (1, -1):
            inner = R - MB_HULL_HALF_WIDTH
            best = min(abs(side * inner - ((cx - O[0]) * -math.sin(a) + (cy - O[1]) * math.cos(a))) for cx, cy in corners)
            out['appendix_c']['floor_corner_to_lane_%+d_hull_inner_m' % side] = r(best / 100.0, 1)
        out['appendix_c']['field_limit_to_hull_inner_m'] = r((R - MB_HULL_HALF_WIDTH - (out['lanes']['R_cm'] - clr)) / 100.0, 1)
        o70('INFO', 'Appendix C: %s (SPEC: floor corner 75 m / 274 m, field limit 13.7 m at StartupMap)' % out['appendix_c'])
    have = set(p['label'] for p in out['player_starts'])
    for label, tag, loc in AS71_STARTS:
        if label not in have:
            out['as71_would'].append('add %s tagged %s at %s' % (label, tag, loc))
    if out['spawner'] and out['spawner'].get('PathEndFogCount') != 5:
        out['as71_would'].append('AS71_FOG: PathEndFogCount %s -> 5 on %s' % (out['spawner'].get('PathEndFogCount'), out['spawner']['label']))
    untagged = [s for s in out['ships'] if not any(t.startswith('ShipTeam') for t in s['tags'])]
    if untagged:
        out['as71_would'].append('AS71_TAG_SHIP: tag %s ShipTeam0' % untagged[0]['label'])
    o70('INFO', 'as_71 would: %s' % (out['as71_would'] or 'nothing'))
    out['beam'] = as70_beam()
    return out


def as70_beam():
    """GA_BeamBP: export every graph to T3D, keep the LaunchCharacter call nodes and the nodes linked to their pins"""
    res = {'graphs': [], 'launch_nodes': []}
    try:
        bp = unreal.load_asset(AS70_BEAM)
        if bp is None:
            o70('WARN', '%s not found' % AS70_BEAM)
            return res
        graphs = []
        for g in unreal.ObjectIterator(unreal.EdGraph):
            try:
                if g.get_path_name().startswith(bp.get_path_name() + ':') or g.get_path_name().startswith(bp.get_path_name() + '.'):
                    graphs.append(g)
            except Exception:  # noqa: BLE001
                continue
        for g in graphs:
            p = os.path.join(MB_MATCH, 'as_70_beam_%s.t3d' % g.get_name())
            task = unreal.AssetExportTask()
            task.set_editor_property('object', g)
            task.set_editor_property('filename', p)
            task.set_editor_property('automated', True)
            task.set_editor_property('prompt', False)
            task.set_editor_property('replace_identical', True)
            ok = unreal.Exporter.run_asset_export_task(task)
            txt = open(p, errors='replace').read() if ok and os.path.exists(p) else ''
            res['graphs'].append({'graph': g.get_name(), 'exported': bool(ok), 'bytes': len(txt), 'has_launch': 'LaunchCharacter' in txt})
            if 'LaunchCharacter' not in txt:
                try:
                    os.remove(p)
                except Exception:  # noqa: BLE001
                    pass
                continue
            blocks = re.findall(r'Begin Object Class=(\S+) Name="([^"]+)"(.*?)End Object', txt, re.S)
            by_name = dict((n, (c, b)) for c, n, b in blocks)
            for c, n, b in blocks:
                if 'LaunchCharacter' not in b or 'K2Node_CallFunction' not in c:
                    continue
                pins = re.findall(r'CustomProperties Pin \((.*?)\)\s*$', b, re.M)
                pinfo = []
                for pin in pins:
                    pn = re.search(r'PinName="([^"]+)"', pin)
                    links = re.findall(r'LinkedTo=\(([^)]*)\)', pin)
                    linked = [x.split()[0] for x in (links[0].split(',') if links else []) if x.strip()]
                    pinfo.append({'pin': pn.group(1) if pn else None, 'linked': [(l, by_name.get(l, ('?', ''))[0].split('.')[-1],
                                                                                   (re.findall(r'MemberName="([^"]+)"', by_name.get(l, ('', ''))[1]) or [None])[0])
                                                                                  for l in linked]})
                res['launch_nodes'].append({'graph': g.get_name(), 'node': n, 'pins': pinfo})
                o70('INFO', 'GA_BeamBP %s: %s pins %s' % (g.get_name(), n, [(x['pin'], x['linked']) for x in pinfo if x['linked']]))
        if not res['launch_nodes']:
            o70('WARN', 'no LaunchCharacter call found in the exported GA_BeamBP graphs %s' % [x['graph'] for x in res['graphs']])
        else:
            o70('INFO', 'B6.2: if the LaunchCharacter target can be a teammate, a Branch on UMyTeamLibrary::IsFriendlyFireBlocked goes before it '
                        '(by hand, Talal\'s OK); M3.1 measures the knockback on a teammate')
    except Exception:  # noqa: BLE001
        o70('WARN', 'GA_BeamBP graph dump failed: %s' % traceback.format_exc().strip().splitlines()[-1])
    return res


try:
    os.makedirs(MB_MATCH, exist_ok=True)
    _p70 = as70_main()
    _p70['lines'] = P70['lines']
    with open(os.path.join(MB_MATCH, 'as_70_plan.json'), 'w') as _f:
        json.dump(_p70, _f, indent=1, default=str)
    print('RESULT: %s -> Saved/Match/as_70_plan.json' % P70['counts'])
except Exception:  # noqa: BLE001
    print('RESULT: FAIL %s' % traceback.format_exc())
