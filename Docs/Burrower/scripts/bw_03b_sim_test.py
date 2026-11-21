# bw_03b_sim_test.py - "the PA_Burrower ragdoll does not explode" check in Simulate-In-Editor (or PIE).
# Run after bw_03_physics_asset.py, in the clone editor through the inbox harness, map Template_Default:
#   Docs/Burrower/scripts/harness/inbox.sh 03b Docs/Burrower/scripts/bw_03b_sim_test.py 120
# This script only sets up and starts a Slate post-tick state machine and returns at once (the world does not tick
# while an inbox script runs). Read the result ~20-60 s later (longer when the editor window is hidden/throttled):
#   Docs/Burrower/scripts/harness/inbox.sh 03c Docs/Burrower/scripts/bw_03c_sim_result.py
# Result file: <project>/Saved/Burrower/pa_sim.json (status running/done/error).
#
# What it does (editor world, never saved):
#  1. checks no PIE runs, removes leftover TEMP_BurrowerSimTest actors, makes sure Template_Default is open
#     (loads it only if no map package is dirty),
#  2. places TEMP_BurrowerSimTest (SkeletalMeshActor: SK_Burrower, physics asset override PA_Burrower,
#     PhysicsActor collision, Simulate Physics on, AlwaysTickPoseAndRefreshBones) SPAWN_HEIGHT above the floor,
#     slightly tilted so the body lands unevenly and the joints work,
#  3. starts SIE (LevelEditorSubsystem.editor_play_simulate; PIE with PLAY_MODE='PIE'),
#  4. every frame: finds the PIE duplicate by tag in UnrealEditorSubsystem.get_game_world() (no PIE references are
#     kept between frames, so the PIE world can be garbage-collected), samples per body: centre of mass
#     (physics body), linear velocity, bone world transform; joint gap (child bone origin vs where the parent body
#     says the joint is), neighbour bone distance vs rest, capsule bottoms vs the floor,
#  5. at start of play also reads the runtime constraints (limits / disable collision) after
#     SetConstraintProfileForAll(None): this is the template's DefaultProfile = what is saved in the asset,
#  6. after SIM_SECONDS of (estimated) physics time: ends play, destroys the TEMP actor, writes pa_sim.json.
import unreal, json, math, os, time, traceback, gc


def _bw03b_module():
    """All code lives in this function scope: the inbox harness execs every script in one shared namespace. The tick callback is a closure, so later scripts cannot replace its helpers."""
    import unreal, json, math, os, time, traceback, gc  # local: closures below never see names rebound by other inbox scripts

    SK_PATH = '/Game/Assets/Enemies/Burrower/SK_Burrower'
    PA_PATH = '/Game/Assets/Enemies/Burrower/PA_Burrower'
    TEMPLATE_MAP = '/Engine/Maps/Templates/Template_Default'
    LOAD_TEMPLATE_IF_NEEDED = True   # only when no map package is dirty (load_level does not save)
    PLAY_MODE = 'SIE'                # 'SIE' (no player pawn, preferred) or 'PIE'
    TAG = 'TEMP_BurrowerSimTest'
    SPAWN_HEIGHT = 500.0             # component origin (= ground under the body) above the floor top, cm
    SPAWN_ROT = (8.0, 0.0, 15.0)     # pitch, yaw, roll (deg)
    SIM_SECONDS = 6.0                # physics seconds to simulate (estimated: sum of min(dt, physics step cap))
    MIN_FRAMES = 60
    START_TIMEOUT_S = 90.0
    RUN_TIMEOUT_S = 300.0            # wall clock for the sampling phase (hidden editor windows run at a few fps)
    STOP_TIMEOUT_S = 60.0
    REST_WINDOW_S = 0.5
    STORE_EVERY_S = 0.1
    APPLY_DEFAULT_PROFILE_CHECK = True

    BONES = ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail']
    JOINTS = [('J1_Forequarters', 'J0_Head'), ('J2_Midbody', 'J1_Forequarters'),
              ('J3_Hindbody', 'J2_Midbody'), ('J4_Tail', 'J3_Hindbody')]
    TOOLSET = 'PhysicsToolsets.PhysicsAssetToolset'
    TOOLSET_CLASS = '/Script/PhysicsToolsets.PhysicsAssetToolset'
    LIMIT_DEG = 20.0


    def _p(tag, msg): print('%s: %s' % (tag, msg))


    # ---------------------------------------------------------------------------------- math (same as bw_03)
    def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
    def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
    def _cmul(a, b): return (a[0] * b[0], a[1] * b[1], a[2] * b[2])
    def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    def _len(a): return math.sqrt(_dot(a, a))


    def _qnorm(q):
        n = math.sqrt(sum(c * c for c in q))
        return tuple(c / n for c in q) if n > 1e-12 else (0.0, 0.0, 0.0, 1.0)


    def _qconj(q): return (-q[0], -q[1], -q[2], q[3])


    def _qrot(q, v):
        q = _qnorm(q); u = (q[0], q[1], q[2]); w = q[3]
        t = _mul(_cross(u, v), 2.0)
        return _add(_add(v, _mul(t, w)), _cross(u, t))


    def _qirot(q, v): return _qrot(_qconj(_qnorm(q)), v)


    def _rot_z(p, y, r):
        sp, cp = math.sin(math.radians(p)), math.cos(math.radians(p))
        sy, cy = math.sin(math.radians(y)), math.cos(math.radians(y))
        sr, cr = math.sin(math.radians(r)), math.cos(math.radians(r))
        return (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)


    def _vt(v): return (float(v.x), float(v.y), float(v.z))
    def _xf(t): return (_vt(t.translation), (float(t.rotation.x), float(t.rotation.y), float(t.rotation.z), float(t.rotation.w)), _vt(t.scale3d))
    def _fin(*vals): return all(math.isfinite(float(x)) for v in vals for x in (v if isinstance(v, (tuple, list)) else (v,)))
    def _r(v, n=2): return [round(float(x), n) for x in v] if isinstance(v, (tuple, list)) else round(float(v), n)


    def _lower(o):
        if isinstance(o, dict):
            return {str(k).lower(): _lower(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_lower(v) for v in o]
        return o


    def _enum_name(v):
        return str(getattr(v, 'name', v))


    def _out_path():
        base = os.path.abspath(unreal.Paths.project_saved_dir())
        return os.path.join(base, 'Burrower', 'pa_sim.json')


    def _write(S, status):
        path = S['out']
        S['status'] = status
        data = {k: v for k, v in S.items() if not k.startswith('_')}
        data['written_utc'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=1, default=str)
        os.replace(tmp, path)


    # ---------------------------------------------------------------------------------- setup helpers
    def _shapes_from_pa(pa):
        """bone -> {c (local), a (local axis), r, l} through the PhysicsAssetToolset (read-only GetBodyShapes)."""
        out = {}
        use_reg = False
        try:
            use_reg = unreal.ToolsetRegistry.is_toolset_registered(TOOLSET)
        except Exception:
            pass
        cdo = None
        if not use_reg:
            cdo = unreal.get_default_object(unreal.load_class(None, TOOLSET_CLASS))
        for b in BONES:
            if use_reg:
                res = unreal.ToolsetRegistry.execute_tool(TOOLSET, 'GetBodyShapes', json.dumps(
                    {'PhysicsAsset': pa.get_path_name(), 'BoneName': b}))
                err = str(res.get_editor_property('error') or '')
                if err:
                    raise RuntimeError('GetBodyShapes(%s): %s' % (b, err))
                shapes = _lower(json.loads(str(res.get_editor_property('value')))).get('returnvalue') or []
                caps = [s for s in shapes if 'CAPSULE' in str(s.get('shapetype', '')).upper()]
                if not caps:
                    continue
                s = caps[0]
                c = s.get('center', {}); ro = s.get('rotation', {})
                out[b] = {'c': (float(c.get('x', 0)), float(c.get('y', 0)), float(c.get('z', 0))),
                          'a': _rot_z(float(ro.get('pitch', 0)), float(ro.get('yaw', 0)), float(ro.get('roll', 0))),
                          'r': float(s.get('radius', 0)), 'l': float(s.get('length', 0))}
            else:
                shapes = cdo.call_method('GetBodyShapes', (pa, b)) or []
                for s in shapes:
                    if 'CAPSULE' in _enum_name(s.get_editor_property('shape_type')).upper():
                        c = s.get_editor_property('center'); ro = s.get_editor_property('rotation')
                        out[b] = {'c': _vt(c), 'a': _rot_z(ro.pitch, ro.yaw, ro.roll),
                                  'r': float(s.get_editor_property('radius')), 'l': float(s.get_editor_property('length'))}
                        break
        return out


    def _ref_rel(skm):
        """Reference pose: rel[(child,parent)] = child origin in the parent bone frame; rest bone distances."""
        skel = skm.get_editor_property('skeleton')
        pose = unreal.AnimPoseExtensions.get_reference_pose(skel)
        G = {b: _xf(unreal.AnimPoseExtensions.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD)) for b in BONES}
        rel, rest = {}, {}
        for c, p in JOINTS:
            rel[c + '-' + p] = _qirot(G[p][1], _sub(G[c][0], G[p][0]))
            rest[c + '-' + p] = _len(_sub(G[c][0], G[p][0]))
        return G, rel, rest


    def _find_floor(eas):
        best, best_score = None, -1.0
        for a in eas.get_all_level_actors():
            try:
                if not isinstance(a, unreal.StaticMeshActor):
                    continue
                o, e = a.get_actor_bounds(False)
                o, e = _vt(o), _vt(e)
                top = o[2] + e[2]
                if e[2] > 200.0 or abs(top) > 500.0:
                    continue
                score = e[0] * e[1] * (10.0 if 'floor' in a.get_actor_label().lower() else 1.0)
                if score > best_score:
                    best, best_score = (a.get_actor_label(), o, e, top), score
            except Exception:
                continue
        return best


    def _cleanup_temp(eas, S=None):
        n = 0
        for a in eas.get_all_level_actors():
            try:
                tags = [str(t) for t in a.get_editor_property('tags')]
                if TAG in tags or a.get_actor_label().startswith(TAG):
                    if eas.destroy_actor(a):
                        n += 1
            except Exception as e:
                if S is not None:
                    S['warnings'].append('cleanup: %r' % (e,))
        return n


    def _ev(enum_cls, *names):
        for n in names:
            v = getattr(enum_cls, n, None)
            if v is not None:
                return v
        return None


    def _phys_step_cap():
        try:
            cdo = unreal.get_default_object(unreal.load_class(None, '/Script/Engine.PhysicsSettings'))
            d = _lower(json.loads(unreal.ToolsetLibrary.get_object_properties(
                cdo, ['MaxPhysicsDeltaTime', 'bSubstepping', 'MaxSubstepDeltaTime', 'MaxSubsteps'])))
            if d.get('bsubstepping'):
                return float(d.get('maxsubstepdeltatime', 0.0167)) * int(d.get('maxsubsteps', 6)), d
            return float(d.get('maxphysicsdeltatime', 1.0 / 30.0)), d
        except Exception as e:
            return 1.0 / 30.0, {'error': repr(e)}


    # ---------------------------------------------------------------------------------- PIE-time helpers
    def _pie_comp():
        """Fresh lookup every frame (no PIE references survive a frame)."""
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
        if world is None:
            return None, None
        actors = unreal.GameplayStatics.get_all_actors_with_tag(world, TAG)
        if not actors:
            return world, None
        return world, actors[0].get_editor_property('skeletal_mesh_component')


    def _strip_acc(res):
        if not isinstance(res, tuple):
            res = (res,)
        return [x for x in res if not isinstance(x, unreal.ConstraintInstanceAccessor)]


    def _read_runtime_constraints(comp):
        lib = unreal.ConstraintInstanceBlueprintLibrary
        out = {}
        accs = comp.get_constraints(False)
        try:
            for acc in accs:
                nm = _strip_acc(lib.get_attached_body_names(acc))
                ang = _strip_acc(lib.get_angular_limits(acc))
                lin = _strip_acc(lib.get_linear_limits(acc))
                # bool return + ref param: Python returns the accessor for True and None for False (PyGenUtil.cpp 1161)
                dis_raw = lib.get_disable_collsion(acc)
                dis = [False] if dis_raw is None else ([dis_raw] if isinstance(dis_raw, bool) else [True])
                key = '%s-%s' % (nm[1] if len(nm) > 1 else '?', nm[0] if nm else '?')
                out[key] = {'angular': [_enum_name(x) if i % 2 == 0 else round(float(x), 3) for i, x in enumerate(ang)],
                            'linear': [_enum_name(x) for x in lin[:3]] + [round(float(lin[3]), 3)] if len(lin) == 4 else [],
                            'disable_collision': bool(dis[0]) if dis else None}
        finally:
            del accs
        return out


    def _constraints_ok(d):
        if sorted(d.keys()) != sorted('%s-%s' % j for j in JOINTS):
            return False
        for v in d.values():
            a, l = v['angular'], v['linear']
            if len(a) != 6 or len(l) != 4 or v['disable_collision'] is not True:
                return False
            if not all('LIMITED' in str(a[i]).upper() and abs(a[i + 1] - LIMIT_DEG) < 0.01 for i in (0, 2, 4)):
                return False
            if not all('LOCKED' in str(x).upper() for x in l[:3]):
                return False
        return True


    def _sample(S, comp, t_game):
        m = S['_m']
        com, vel, bone, bottoms = {}, {}, {}, {}
        for b in BONES:
            c = _vt(comp.get_center_of_mass(b))
            v = _vt(comp.get_physics_linear_velocity(b))
            tf = _xf(comp.get_socket_transform(b))
            com[b], vel[b], bone[b] = c, v, tf
            if not _fin(c, v, tf[0], tf[1]):
                if S['nan_first'] is None:
                    S['nan_first'] = {'t': S['physics_time_est'], 'body': b, 'com': str(c), 'vel': str(v)}
                S['nan_found'] = True
                return False
        pt = S['physics_time_est']
        frame_max_speed = 0.0
        for b in BONES:
            sp = _len(vel[b])
            frame_max_speed = max(frame_max_speed, sp)
            if sp > S['max_speed']['value']:
                S['max_speed'] = {'value': round(sp, 2), 'body': b, 't': round(pt, 3)}
            t, q, s = bone[b]
            cap = S['_shapes'].get(b)
            if cap:
                centre = _add(t, _qrot(q, _cmul(s, cap['c'])))
                axis = _qrot(q, cap['a'])
                bottoms[b] = centre[2] - abs(axis[2]) * cap['l'] * 0.5 - cap['r']
                m['bone_com_err'] = max(m['bone_com_err'], _len(_sub(centre, com[b])))
            else:
                bottoms[b] = com[b][2] - S['_radius_guess'].get(b, 100.0)
        min_bottom = min(bottoms.values())
        S['min_bottom_ever'] = min(S['min_bottom_ever'], min_bottom) if S['min_bottom_ever'] is not None else min_bottom
        gaps = {}
        for c, p in JOINTS:
            k = c + '-' + p
            tp, qp, sp_ = bone[p]
            expect = _add(tp, _qrot(qp, _cmul(sp_, S['_rel'][k])))
            gaps[k] = _len(_sub(bone[c][0], expect))
            g = m['gap'].setdefault(k, 0.0)
            m['gap'][k] = max(g, gaps[k])
            d = _len(_sub(bone[c][0], bone[p][0]))
            lo, hi = m['nd'].setdefault(k, [d, d])
            m['nd'][k] = [min(lo, d), max(hi, d)]
            dc = _len(_sub(com[c], com[p]))
            lo, hi = m['cd'].setdefault(k, [dc, dc])
            m['cd'][k] = [min(lo, dc), max(hi, dc)]
        m['speed_hist'].append((pt, frame_max_speed))
        if S['first'] is None:
            S['first'] = {'t': round(pt, 3), 'com': {b: _r(com[b]) for b in BONES}, 'min_bottom': round(min_bottom, 2)}
        S['last'] = {'t': round(pt, 3), 'com': {b: _r(com[b]) for b in BONES}, 'min_bottom': round(min_bottom, 2),
                     'bottoms': {b: round(v, 2) for b, v in bottoms.items()}, 'speed': {b: round(_len(vel[b]), 2) for b in BONES}}
        if pt - m['last_store'] >= STORE_EVERY_S or not S['samples']:
            m['last_store'] = pt
            S['samples'].append({'t': round(pt, 3), 'game_t': round(t_game, 3), 'com_z': {b: round(com[b][2], 1) for b in BONES},
                                 'min_bottom': round(min_bottom, 1), 'max_gap': round(max(gaps.values()), 2),
                                 'max_speed': round(frame_max_speed, 1)})
        return True


    # ---------------------------------------------------------------------------------- state machine
    def _request_end(S):
        try:
            unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
            S['_last_end_req'] = time.time()
        except Exception as e:
            S['errors'].append('editor_request_end_play: %r' % (e,))


    def _finalize(S):
        m = S['_m']
        floor = S['floor_top_z']
        S['joint_gap_cm'] = {k: round(v, 3) for k, v in m['gap'].items()}
        S['max_joint_gap_cm'] = round(max(m['gap'].values()), 3) if m['gap'] else None
        nd = {}
        for k, (lo, hi) in m['nd'].items():
            rest = S['rest_bone_dist_cm'][k]
            nd[k] = {'rest': round(rest, 2), 'min': round(lo, 2), 'max': round(hi, 2), 'max_abs_dev': round(max(abs(lo - rest), abs(hi - rest)), 3)}
        S['neighbour_bone_dist'] = nd
        S['max_neighbour_dev_cm'] = round(max(v['max_abs_dev'] for v in nd.values()), 3) if nd else None
        S['com_dist_range_cm'] = {k: [round(lo, 2), round(hi, 2)] for k, (lo, hi) in m['cd'].items()}
        S['bone_vs_com_max_err_cm'] = round(m['bone_com_err'], 3)
        if S['first'] and S['last']:
            S['start_min_bottom_above_floor_cm'] = round(S['first']['min_bottom'] - floor, 2)
            S['final_min_bottom_above_floor_cm'] = round(S['last']['min_bottom'] - floor, 2)
            S['min_bottom_ever_above_floor_cm'] = round(S['min_bottom_ever'] - floor, 2)
            S['fell_cm'] = round(S['first']['min_bottom'] - S['last']['min_bottom'], 2)
            S['drift_xy_max_cm'] = round(max(math.hypot(S['last']['com'][b][0] - S['first']['com'][b][0],
                                                        S['last']['com'][b][1] - S['first']['com'][b][1]) for b in BONES), 2)
            S['final_com_above_floor_cm'] = {b: round(S['last']['com'][b][2] - floor, 2) for b in BONES}
            fl = S.get('floor')
            if fl:
                (cx, cy), (hx, hy) = fl['centre_xy'], fl['half_extent_xy']
                S['off_floor_bodies'] = [b for b in BONES if abs(S['last']['com'][b][0] - cx) > hx or abs(S['last']['com'][b][1] - cy) > hy]
        hist = m['speed_hist']
        if hist:
            t_end = hist[-1][0]
            win = [sp for (t, sp) in hist if t >= t_end - REST_WINDOW_S]
            S['rest'] = {'window_s': REST_WINDOW_S, 'max_speed_in_window': round(max(win), 2), 'came_to_rest': max(win) < 50.0}
        S['frames'] = m['frames']
        wall = max(1e-3, S.get('_t_sample_end', time.time()) - S.get('_t_sample_start', time.time()))
        S['avg_fps'] = round(m['frames'] / wall, 2)


    def _bw03b_step(S):
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        now = time.time()
        ph = S['phase']
        if ph == 'wait_start':
            if les.is_in_play_in_editor():
                world, comp = _pie_comp()
                if comp is not None:
                    S['phase'] = 'sampling'
                    S['_t_sample_start'] = now
                    S['_last_game_t'] = float(unreal.GameplayStatics.get_time_seconds(world))
                    S['simulating_at_start'] = {b: bool(comp.is_simulating_physics(b)) for b in BONES}
                    if not all(S['simulating_at_start'].values()):
                        S['warnings'].append('bodies not simulating at start: %s; calling set_simulate_physics(True)' % S['simulating_at_start'])
                        comp.set_simulate_physics(True)
                    try:
                        S['profile_check'] = {'before_apply': _read_runtime_constraints(comp)}
                        if APPLY_DEFAULT_PROFILE_CHECK:
                            comp.set_constraint_profile_for_all('None', True)
                            S['profile_check']['after_apply'] = _read_runtime_constraints(comp)
                        pc = S['profile_check']
                        pc['ok'] = _constraints_ok(pc['before_apply']) and _constraints_ok(pc.get('after_apply', pc['before_apply']))
                    except Exception as e:
                        S['profile_check'] = {'ok': None, 'error': repr(e)}
                        S['warnings'].append('runtime constraint read failed: %r' % (e,))
                    _write(S, 'running')
                return
            if now - S['_t_requested'] > START_TIMEOUT_S:
                S['errors'].append('play session did not start (or the TEMP actor was not found in the PIE world) '
                                   'within %.0f s' % START_TIMEOUT_S)
                S['phase'] = 'stopping' if les.is_in_play_in_editor() else 'cleanup'
                if S['phase'] == 'stopping':
                    _request_end(S); S['_t_stop'] = now
            return
        if ph == 'sampling':
            if not les.is_in_play_in_editor():
                S['errors'].append('play session ended before the test finished')
                S['_t_sample_end'] = now
                S['phase'] = 'cleanup'
                return
            world, comp = _pie_comp()
            if comp is None:
                S['errors'].append('TEMP actor vanished from the PIE world')
                S['_t_sample_end'] = now
                S['phase'] = 'stopping'; _request_end(S); S['_t_stop'] = now
                return
            t = float(unreal.GameplayStatics.get_time_seconds(world))
            if t > S['_last_game_t']:
                dt = t - S['_last_game_t']
                S['_last_game_t'] = t
                S['game_time'] = round(t, 3)
                S['physics_time_est'] = S['physics_time_est'] + min(dt, S['physics_step_cap'])
                S['_m']['frames'] += 1
                if not _sample(S, comp, t):
                    S['errors'].append('NaN/inf in body state: %s' % S['nan_first'])
            comp = None; world = None
            done = S['physics_time_est'] >= SIM_SECONDS and S['_m']['frames'] >= MIN_FRAMES
            if done or S['nan_found'] or now - S['_t_sample_start'] > RUN_TIMEOUT_S:
                if not done and not S['nan_found']:
                    S['warnings'].append('run timeout: only %.2f s physics time in %d frames' % (S['physics_time_est'], S['_m']['frames']))
                S['_t_sample_end'] = now
                S['phase'] = 'stopping'
                gc.collect()
                _request_end(S); S['_t_stop'] = now
            elif now - S['_last_write'] > 2.0:
                S['_last_write'] = now
                _write(S, 'running')
            return
        if ph == 'stopping':
            if not les.is_in_play_in_editor():
                S['phase'] = 'cleanup'
            elif now - S['_t_stop'] > STOP_TIMEOUT_S:
                S['errors'].append('play session did not end within %.0f s; stop it by hand (Esc / Stop)' % STOP_TIMEOUT_S)
                S['phase'] = 'cleanup'
            elif now - S.get('_last_end_req', 0) > 3.0:
                _request_end(S)
            return
        if ph == 'cleanup':
            gc.collect()
            try:
                eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                S['temp_actors_removed'] = _cleanup_temp(eas, S)
            except Exception as e:
                S['errors'].append('cleanup failed: %r' % (e,))
            _finalize(S)
            S['phase'] = 'done'
            S['finished_utc'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
            _write(S, 'error' if S['errors'] and not S['samples'] else 'done')
            _bw03b_unregister(S)


    def _bw03b_unregister(S):
        h = S.get('_handle')
        S['_handle'] = None
        if h is not None:
            try:
                unreal.unregister_slate_post_tick_callback(h)
            except Exception as e:
                unreal.log_warning('[bw_03b] unregister failed: %r' % (e,))


    def _bw03b_tick(S, delta):
        if not S or S.get('phase') == 'done':
            return
        try:
            _bw03b_step(S)
        except Exception:
            S['errors'].append('tick exception: ' + traceback.format_exc()[-2000:])
            try:
                les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
                if S['phase'] in ('wait_start', 'sampling') and les.is_in_play_in_editor():
                    S['_t_sample_end'] = time.time()
                    S['phase'] = 'stopping'; _request_end(S); S['_t_stop'] = time.time()
                elif S['phase'] != 'cleanup':
                    S['phase'] = 'cleanup'
                else:  # exception in cleanup itself: write what we have and stop ticking
                    S['phase'] = 'done'
                    try:
                        _write(S, 'error')
                    except Exception:
                        pass
                    _bw03b_unregister(S)
            except Exception:
                S['phase'] = 'done'
                _bw03b_unregister(S)


    # ---------------------------------------------------------------------------------- start
    def _bw03b_start():
        old = globals().get('_BW03B')
        if old and old.get('phase') not in (None, 'done'):
            age = time.time() - old.get('_t_created', 0)
            if age < 600:
                _p('FAIL', 'a bw_03b run is still active (phase %s, %.0f s old). Wait and run bw_03c_sim_result.py.' % (old.get('phase'), age))
                return
            _p('WARN', 'stale bw_03b run (%.0f s old) is unregistered' % age)
            _bw03b_unregister(old)
            old['phase'] = 'done'
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            _p('FAIL', 'PIE/SIE already running: stop it first. Nothing done.')
            return
        out = _out_path()
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out):
            os.remove(out)
        S = {'out': out, 'phase': 'setup', 'status': 'running', 'mode': PLAY_MODE, 'errors': [], 'warnings': [],
             'started_utc': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()), '_t_created': time.time(),
             'params': {'spawn_height': SPAWN_HEIGHT, 'spawn_rot_pyr': SPAWN_ROT, 'sim_seconds': SIM_SECONDS,
                        'min_frames': MIN_FRAMES, 'rest_window_s': REST_WINDOW_S},
             'nan_found': False, 'nan_first': None, 'max_speed': {'value': 0.0, 'body': None, 't': None},
             'physics_time_est': 0.0, 'game_time': 0.0, 'first': None, 'last': None, 'min_bottom_ever': None,
             'samples': [], 'profile_check': None,
             '_m': {'gap': {}, 'nd': {}, 'cd': {}, 'bone_com_err': 0.0, 'speed_hist': [], 'frames': 0, 'last_store': -1e9},
             '_last_write': 0.0, '_handle': None}
        globals()['_BW03B'] = S   # phase 'setup'; the outer except marks it done/error if setup fails
        _write(S, 'running')

        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = ues.get_editor_world()
        wpath = world.get_outermost().get_name() if world else ''
        if wpath != TEMPLATE_MAP:
            dirty = []
            try:
                dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
            except Exception as e:
                dirty = ['<unknown: %r>' % (e,)]
            if not LOAD_TEMPLATE_IF_NEEDED or dirty:
                S['errors'].append('editor map is %s, not %s (dirty maps: %s)' % (wpath, TEMPLATE_MAP, dirty))
                _p('FAIL', 'open %s first (launch.sh default map). Current %s, dirty map packages %s. Not loading.' % (TEMPLATE_MAP, wpath, dirty))
                S['phase'] = 'done'; _write(S, 'error')
                return
            _p('INFO', 'loading %s (current map %s is not dirty)' % (TEMPLATE_MAP, wpath))
            if not les.load_level(TEMPLATE_MAP):
                _p('FAIL', 'load_level(%s) failed' % TEMPLATE_MAP)
                S['errors'].append('load_level failed'); S['phase'] = 'done'; _write(S, 'error')
                return
            world = ues.get_editor_world()
        _p('INFO', 'editor map %s' % world.get_outermost().get_name())

        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        n = _cleanup_temp(eas)
        if n:
            _p('INFO', 'removed %d leftover %s actor(s)' % (n, TAG))

        skm = unreal.load_asset(SK_PATH)
        pa = unreal.load_asset(PA_PATH)
        if not isinstance(skm, unreal.SkeletalMesh) or not isinstance(pa, unreal.PhysicsAsset):
            _p('FAIL', 'SK_Burrower or PA_Burrower missing: run bw_03_physics_asset.py first')
            S['errors'].append('assets missing'); S['phase'] = 'done'; _write(S, 'error')
            return
        cur = skm.get_editor_property('physics_asset')
        if cur is None or cur.get_path_name() != pa.get_path_name():
            _p('WARN', 'SK_Burrower.physics_asset is %s, not PA_Burrower (the test uses a component override anyway)' % (cur.get_path_name() if cur else None))
            S['warnings'].append('mesh physics asset is not PA_Burrower')

        try:
            S['_shapes'] = _shapes_from_pa(pa)
            _p('INFO', 'capsules read from PA_Burrower: %s' % sorted(S['_shapes'].keys()))
        except Exception as e:
            S['_shapes'] = {}
            S['warnings'].append('could not read PA shapes (%r): capsule bottoms approximated from COM' % (e,))
            _p('WARN', 'could not read PA shapes (%r); bottoms approximated' % (e,))
        S['_radius_guess'] = {'J0_Head': 160.0, 'J1_Forequarters': 185.0, 'J2_Midbody': 175.0, 'J3_Hindbody': 125.0, 'J4_Tail': 85.0}
        G, rel, rest = _ref_rel(skm)
        S['_rel'] = rel
        S['rest_bone_dist_cm'] = {k: round(v, 3) for k, v in rest.items()}
        _p('INFO', 'rest bone distances %s' % S['rest_bone_dist_cm'])

        fl = _find_floor(eas)
        if fl:
            label, o, e, top = fl
            S['floor'] = {'label': label, 'top_z': round(top, 2), 'centre_xy': [round(o[0], 1), round(o[1], 1)], 'half_extent_xy': [round(e[0], 1), round(e[1], 1)]}
            S['floor_top_z'] = top
            if min(e[0], e[1]) < 1200.0:
                S['warnings'].append('floor half extent %s cm is small for a 20 m body (it may tip over the edge)' % [round(e[0]), round(e[1])])
            sx, sy = o[0], o[1]
            _p('INFO', 'floor %s top z %.1f, half extent %.0f x %.0f cm' % (label, top, e[0], e[1]))
        else:
            S['floor'] = None; S['floor_top_z'] = 0.0; sx, sy = 0.0, 0.0
            S['warnings'].append('no floor actor found; assuming floor z = 0')
            _p('WARN', 'no floor StaticMeshActor found; assuming z = 0')

        loc = unreal.Vector(sx, sy, S['floor_top_z'] + SPAWN_HEIGHT)
        rot = unreal.Rotator(roll=SPAWN_ROT[2], pitch=SPAWN_ROT[0], yaw=SPAWN_ROT[1])
        actor = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, loc, rot, False)  # EditorActorSubsystem.h 228
        if actor is None:
            _p('FAIL', 'spawn_actor_from_class(SkeletalMeshActor) returned None')
            S['errors'].append('spawn failed'); S['phase'] = 'done'; _write(S, 'error')
            return
        actor.set_actor_label(TAG)
        actor.set_editor_property('tags', [TAG])
        comp = actor.get_editor_property('skeletal_mesh_component')
        comp.set_skeletal_mesh_asset(skm)
        comp.set_physics_asset(pa, True)
        try:  # bones must refresh from the bodies even when the viewport does not render them (SkinnedMeshComponent.h 96)
            comp.set_editor_property('visibility_based_anim_tick_option',
                                     _ev(unreal.VisibilityBasedAnimTickOption, 'ALWAYS_TICK_POSE_AND_REFRESH_BONES'))
        except Exception as e:
            S['warnings'].append('visibility_based_anim_tick_option not set: %r' % (e,))
        comp.set_collision_profile_name('PhysicsActor')
        try:
            comp.set_collision_enabled(_ev(unreal.CollisionEnabled, 'QUERY_AND_PHYSICS'))
        except Exception as e:
            S['warnings'].append('set_collision_enabled failed: %r (PhysicsActor profile is QueryAndPhysics anyway)' % (e,))
        comp.set_simulate_physics(True)  # Default bodies simulate when the component's BodyInstance simulates (BodyInstance.cpp 1195)
        try:
            bi = comp.get_editor_property('body_instance')
            if not bi.get_editor_property('simulate_physics'):
                S['warnings'].append('BodyInstance.bSimulatePhysics still false after set_simulate_physics(True)')
        except Exception:
            pass
        S['spawn'] = {'location': _r(_vt(loc), 1), 'rotation_pyr': list(SPAWN_ROT), 'actor': actor.get_name()}
        actor = comp = None
        cap, settings = _phys_step_cap()
        S['physics_step_cap'] = cap
        S['physics_settings'] = settings
        _p('INFO', 'placed %s at %s; physics step cap %.4f s (%s)' % (TAG, S['spawn']['location'], cap, settings))

        S['_handle'] = unreal.register_slate_post_tick_callback(lambda delta, _S=S: _bw03b_tick(_S, delta))
        S['phase'] = 'wait_start'
        S['_t_requested'] = time.time()
        if PLAY_MODE == 'PIE':
            les.editor_request_begin_play()
        else:
            les.editor_play_simulate()
        _write(S, 'running')
        _p('INFO', 'requested %s; state machine running. Results in %s; read them with bw_03c_sim_result.py in '
                   '~20-60 s (hidden/throttled editor: longer, up to %.0f s).' % (PLAY_MODE, out, RUN_TIMEOUT_S + START_TIMEOUT_S))


    def _bw03b_run():
        try:
            _bw03b_start()
        except Exception as e:
            print('FAIL: bw_03b setup crashed: %r\n%s' % (e, traceback.format_exc()))
            try:
                S = globals().get('_BW03B')
                if S and S.get('phase') in ('setup', 'wait_start'):
                    if S.get('_handle') is not None:
                        _bw03b_unregister(S)
                    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
                        _request_end(S)
                        print('WARN: a play session was requested; it is being stopped. Run bw_03b again once it ended.')
                    S['errors'].append('setup crashed: %r' % (e,))
                    S['phase'] = 'done'
                    _write(S, 'error')
                _cleanup_temp(unreal.get_editor_subsystem(unreal.EditorActorSubsystem))
                print('INFO: TEMP actor removed after the setup error')
            except Exception as e2:
                print('WARN: cleanup after setup error failed: %r (remove %s by hand)' % (e2, TAG))
    return _bw03b_run


try:
    _bw03b_module()()
except Exception as _e:
    print('FAIL: bw_03b could not start: %r' % (_e,))
