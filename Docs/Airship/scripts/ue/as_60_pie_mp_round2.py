# as_60_pie_mp_round2.py - round 2 PIE harness, LISTEN-SERVER part of the test plan (Docs/Airship/round2/SPEC_A.md
# section 4, the "L" rows, and the review fixes of section 6 that need a client). as_59 is the standalone part.
# Play As Listen Server with 2 players (the host + 1 client, one process: set_play_mode.sh listen 2 with the editor
# closed), L_AirshipTest, ship 1 (placed in the map) + ship 2 (Aura.Airship.Spawn, or the map's second ship if it has
# one), fixed 30 fps game time. Built like as_45: a frame-by-frame state machine (Slate post-tick callback) drives BOTH
# PIE worlds from the editor's Python:
#  server world (UEDPIE_0): the host's PC / character, the server copies of the client's PC / character and the ships
#  client world (UEDPIE_1): the client's PC / character / ship copies, its Enhanced Input subsystem
# The client acts only through its own machine: F / fire / exit / walk are injected into the CLIENT's Enhanced Input
# subsystem (IA_AirshipBoard -> ServerRequestBoard; as a gunner IA_AirshipFire -> ServerGunnerFire / ServerGunnerTrigger,
# IA_AirshipExit -> ServerRequestDismount; IA_Move), its aim is its own control rotation (the gunner's camera trace),
# and a client pilot's flight goes through DebugSetInput on the CLIENT's ship copy (ServerSetPilotInput). Server-only
# console commands (Damage, TurretFire, Set, TestBullet, and Mount / Board / Exit for the HOST) run in the server world.
# Every call from Python into Unreal runs under the editor's script guard (FEditorScriptExecutionGuard in PyUtil
# InvokeFunctionCall): AActor::GetFunctionCallspace then answers Local, so an RPC started inside such a call runs on the
# calling machine and is never sent. A console Mount / Board / Exit for the CLIENT from Python moves only the server's
# copy (ClientMountChanged / ClientRestart stay on the server; the client's input, camera and own copy are never told),
# and a client-side RequestFire / RequestExit called from Python runs its server RPC on the client. So the client changes
# roles only through its own injected input (client_to: F, Exit), the client's guns fire only from injected input, and
# anything whose result must reach the client (a turret wreck's eject, a lethal crew share) comes from a sentinel test
# bullet, whose hit lands in the swarm's tick (first real run 2026-11-25: 11 FAIL, most of them from this).
# Run (L_AirshipTest open, no PIE, the round-2 C++ built, as_51..as_57 run, the ini in listen mode):
#   Docs/Airship/scripts/harness/inbox.sh 60 Docs/Airship/scripts/ue/as_60_pie_mp_round2.py 120
#   status: inbox.sh 60s Docs/Airship/scripts/ue/as_60s_status.py 60     stop: inbox.sh 60x Docs/Airship/scripts/ue/as_60x_stop.py 60
#   or the whole session: _AirshipWork_logs/run_r2_listen.sh (lock, launch, run, poll, quit, release)
# Results: Saved/Airship/round2_mp/r2mp_result.json (checks with the measured values, events, 5 Hz series),
#   r2mp_report.txt, r2mp_log.txt, r2mp_status.txt (rewritten every 2 s), r2mp_restore.json; captures
#   Saved/Airship/captures/round2_mp/.
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, UBurrowerSettings.bEnabled False,
# p.NetShowCorrections 1 (0 after), Net PktLag on both worlds (the g2_ phases only, 0 after), the LogAirshipPilot
# verbosity (Verbose in the g2_ phases for "back on the seat", Log after), the UAirshipSettings values the run changes
# (Settings.DriftSpeed 0 in g6_drift: every snapshot value is written back to the class default). The crew share is
# left at the project value (D4 is under test here). One TEMP_AS60_Capture SceneCapture2D in the editor level (removed
# after PIE; the map is never saved). The user's own Play ("Repeating last play command" in the log) is never stopped.
# Knobs (inbox globals, read at arm; they last for the editor session, so reset what you set):
#   AS60_ONLY = ('g2_',)   phase-name prefixes for a short run: settle and spawn2 always run, and a group's first phase
#                          (its role setup) runs whenever any phase of that group is kept
#   AS60_LAG_MS = 100      one-way lag (game ms, as as_45 emulates it: Net PktLag on both worlds, scaled by the real
#                          fps) for the T5.13 group g2_ only; 0 = no lag. Every other phase runs without lag.
#   AS60_SCHEME = 3        Point & Fly: the scheme of the ships at settle, the drift group and the crew groups
#   AS60_AIM_SCHEME = 0    Classic for the phases where the harness points a pilot's camera (g1_ host pilot, g3_ client
#                          pilot): Point & Fly's gun lock would swing the hull toward a broadside (as as_59)
#   AS60_CRUISE_THROTTLE = 1.0   the host's throttle in T5.13's cruise (Classic top speed 48 m/s)
#
# Phases (game seconds) -> checks (spec test IDs; ship 1 = the map's, ship 2 = the spawned one):
#  settle 4      scheme, wind off, cvars, client index      setup; T6.1 turrets on server AND client at the mounts, 400
#  spawn2 3      Aura.Airship.Spawn, parked at PARK2         setup_ship2
#  g1_  client gunner on a ship the HOST pilots (ship 1 at its spawn point, Classic)
#   g1_board 3   Board 0 (the host flies ship 1)             g1_setup
#   g1_far 3     client on deck >= 4.5 m from every seat, F  T5.2 refused (the helm is the host's)
#   g1_mount 3   client on the lid 2 m from L1's seat, F     T5.1 mounted <= 0.5 s, attached at the seat on both machines,
#                                                            CMC off, IMC_Airship on the client; T5.14; fix 6.1 flags set
#   g1_aim 3     client control rotation at the port wall    T5.3 cannon L1 yaw / elevation on server and client within 1 deg
#   g1_fire 3    client LMB, again 0.5 s later; Board cidx   T5.4 one ball from L1 on the server, its copy and the FX on the
#                                                            client, recoil once; T5.10 Board refused while mounted
#   g1_broadside 3.5 the host's port broadside               T5.5 only L2 fires (L1 is manned)
#   g1_exit 4    client F (IA_AirshipExit), then W 1 s       T5.8 detached, CMC on, falling / walking, IMC off, walks >= 1 m
#   g1_turret 6  client F behind turret L, aim at the wall,  T5.3 (turret) aim replicated (vs the client's view-ray hit);
#                LMB 1 s                                     T5.6 server 9-11 shots, client
#                                                            predicted 9-11, heat ~0.33, muzzle flash on both machines
#   g1_overheat 8 LMB held 3.5 s                             T5.7 overheat ~3 s, no rounds (server, predicted) until 0.35
#   g1_wreck 4   turret L of ship 1 wrecked by a test bullet T6.6 wreck on the client (OnRep, fire FX), gunner ejected,
#                (health + 10) with the client on it, then   no more shots from it, turret R still fires
#                TurretFire
#  g2_  T5.13 (review fix 6.1): Net PktLag on both worlds (AS60_LAG_MS)
#   g2_walk 5    client walks on the deck (IA_Move), F on L1 mounted while its moves are in flight
#   g2_cruise 17 the host flies ship 1 at AS60_CRUISE_THROTTLE: a 10 s window once >= 30 m/s
#   g2_end 5     brake, lag off                              T5.13 the client's own copy within 5 cm of the seat
#                                                            (hull-relative, client), no correction applied to it on the
#                                                            client (log), "back on the seat" rare, the camera with it
#   g2_crew 3    Aura.Airship.Damage 100                     T4.1 host pilot -25, client gunner -25 (server and its own view)
#  g3_  client PILOT of ship 2, host GUNNER on it (Classic)
#   g3_swap 4    client Exit (L1), F on ship 2; host Exit 0  g3_setup; T4.4 the host keeps its health at the exit (75)
#   g3_arc 5     client camera at ship 1 60 m ahead, LMB 1 s T6.2 both turrets 9-11 (server), predicted 9-11, ship 1 hit,
#                                                            no cannonball
#   g3_port 4    client camera 90 deg to port, LMB           T6.3 port broadside, no turret shots
#   g3_r1 5      host Mount 0 2 (R1), host LMB; client's     T5.12 the host's R1 ball, its recoil once and FX on the client,
#                starboard broadside                         aim replicated, the host seen at the seat on the client; the
#                                                            client's broadside fires only R2
#   g3_turret 5  host Mount 0 5 (turret R), LMB 1 s          T5.12 turret: server 9-11, the client draws 9-11, flash there
#   g3_exit 3    host F                                      T5.8 (host gunner) back on foot
#  g4_  crew damage with the CLIENT pilot of ship 2; the host's gun from ship 1's forward deck (bow to bow, 45 m)
#   g4_setup 3.5 ship 1 bow to bow, the host on its deck
#   g4_hull 5    host GA_GunShoot at ship 2's bow (below)    crew share: client pilot -25 % of the hull loss on the server
#                                                            and in its own view
#   g4_turret 5  host GA_GunShoot at ship 2's turret L       fix 6.3: the hull hit goes to the turret behind it; whole hits;
#                                                            the client sees the same turret health
#   g4_bullet 3  Aura.MechSentinel.TestBullet at the hull    ship -3, client pilot -0.75 (server and client)
#   g4_damage 2.5 Aura.Airship.Damage 100                    T4.1 (client pilot) -25 on the server and the client
#  g5_  cannonballs (ship 1 parked 400 m away: its balls are the "enemy" ones)
#   g5_down 5    a hovering ball 5 m ahead of ship 2's bow,  T2.7 bShotDown on the server within 1 s; the client copy
#                TurretFire at it                            bursts, hides and stops within 0.5 s, collision off; no damage
#   g5_spent 4   a 0-damage ball into ship 2's port side     fix 6.2: the client copy's collision is off after the impact,
#                                                            a client trace through it reaches the hull
#  g6_  drift after a CLIENT pilot leaves at speed (Point & Fly)
#   g6_cruise 4  client throttle 1 (its own ship copy)
#   g6_drift 22  client F (IA_AirshipExit) at speed; once    T9.7 Drift on the server, the client copy moves the same;
#                slow, Settings.DriftSpeed 0 (Drift -> Hold)  T8.4 L the client's character stays at the wheel on both
#                                                            machines (hull space), walking, no snap on its own machine
#   g6_hold 8    hold                                        hold on the server and the client (< 0.5 m), DriftSpeed back
#  g8_  a client's jump on a flying deck (the host pilots ship 1, Classic, throttle 1)
#   g8_jump 11   the client on the planks 1.5 m behind the     T8.7 L / T8.8 L both copies leave the deck, land within 4 m of the
#                helm; at >= 30 m/s ACharacter::Jump on its    take-off point (hull space) and stay within 50 cm after it
#                own copy
#  g9_  a remote gunner leaves a gun when its move clock is old (review 2026-11-27, AAirshipPawn::DismountGunner)
#   g9_clock <= 180 the client on ship 1's planks until its   T5.8b the client's F on L1, 3 s mounted, F again, W 1.5 s: the
#                move time stamp (read from the server's log)  server's copy and its own copy walk >= 1 m (hull space), no
#                is past 125 s, then F / F / W                "TimeStamp expired" in the server's log
#  g7_  lethal crew share (D4)
#   g7_k1 5.5    host pilots ship 2, client F on L1, both    T4.3 the client gunner dismounted first, then dead; T4.2 (host)
#                at 10 health, a 100 test bullet in the hull the pilot ejected first, then dead; ship alive
#   g7_resp 9    both players respawn (GameMode, 5 s)        setup_respawn
#   g7_k2 5.5    the client F-boards ship 2 at 10, bullet    T4.2 (client) ejected first (PC pawn = character on both
#                                                            machines), then dead; ship alive
#  end           log scan                                    T5.13 log part (corrections, "back on the seat")
# Not here (SKIP in the report with the reason): late join (not possible in PIE), T5.11 (Kill kills every ship; as_59
# T5.11 S), T5.15 (as_59 S), T4.5, T8.1, T2.8 (3 players), T3.5 / T6.7 (no swarm in L_AirshipTest), T7.x.
# 2026-11-27 (Talal 11-25, helm and deck; SPEC_A.md 6.8; not run in PIE yet). Setups only, no threshold changed:
#  * deck_point traces the deck the characters walk on (the Mesh's physics asset, AAirshipPawn::IsDeckOnPhysicsAsset)
#    instead of the top of the hull's collision (the UCX lid, which characters now pass through);
#  * F takes the helm only at the wheel, so a client that takes a helm by F is put 80 cm behind the standing spot
#    (board_point; it was any deck point 4.5 m from the guns); the points next to a gun seat are on its helm side (open
#    planks; the far side is the cannon itself, which the deck trace would now land on);
#  * the hull's collision ignores Visibility, so the "hull" test bullets keep the Mesh's collision on and aim at the hull's
#    side 1 m above the hull origin (a PA_Airship box; g4_bullet, g7's hull_bullet), and g5_spent's ball goes there too
#    (its trace through the hidden ball runs 4 m on, to the box behind the hull's skin);
#  * new: T8.4_client_exit_in_place_L in g6_drift (the client pilot leaves at speed: both copies stay at the wheel, hull
#    space, the client's own copy never more than 1 m off: round 1 snapped it by 3 m).
# 2026-11-27, first listen run after the helm / deck change (38 PASS, 1 FAIL: T5.12a at 1.04 deg). Changes, no limit moved:
#  * T5.12a compares the client's barrel against the server's own -1..4 frames earlier (it was 0..4): the host shows its
#    own gunner's aim a frame late (the aim reaches the ship after the Mesh's animation update), the client shows the
#    replicated aim in the same frame, so the client is one frame AHEAD while the barrel moves (0.21 deg at -1, 1.03 at 0);
#  * new deck_arrival_no_shove_L (g1_far): the run showed the ship knocked 3-5.5 m away every time a character was put on
#    the planks from the ground (the mech's mesh and jet packs are kinematic WorldDynamic bodies inside the hull's convex
#    until the passenger rule makes them query only; fixed in C++: AAirshipPawn::IsPassengerCandidate,
#    UAirshipSubsystem::CheckNewPassengers);
#  * new T8.2_client_F_away_from_wheel_L (g3_swap): the client's F 2.5 m behind a free wheel does nothing;
#  * new group g8_ (T8.7_client_deck_jump_L): the client jumps on the deck of the ship the host flies.
# 2026-11-27, review of the gunner dismount (must fix 1). New group g9_ (T5.8b_dismount_old_clock_L): a client's move time
# stamp restarts only at a possession (ClientRestart) or every 240 s (MinTimeBetweenTimeStampResets) and stands still
# while it is mounted. DismountGunner deleted the server's prediction state; a new one starts at 0 and takes a stamp more
# than 120 s above its own for "a move from before the reset" (UCharacterMovementComponent::IsClientTimeStampValid), so the
# server refused every move of that client until its clock wrapped: up to 2 minutes. Every earlier run dismounted the
# client with a young clock. The phase reads the clock from the server's log (LogNetPlayerMovement VeryVerbose for 0.4 s:
# "TimeStamp x Accepted!"), waits until it is past 125 s, and only then mounts and dismounts. It ends itself when done.
import json, math, os, re as _re, time, traceback  # unreal = inbox namespace

AS60_AS30 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_30_pie_smoke.py'
_as60_src = open(AS60_AS30).read()
exec(compile(_as60_src[:_as60_src.index('\nclass AsRun')], AS60_AS30, 'exec'), globals())   # OUT, MAP_NAME, v3, q4, r, dist, wrap180, tl_get/tl_set, gp, valid, find_log

AS60_VERSION = 'as_60_pie_mp_round2 2026-11-27 helm+deck, listen run'
MP2 = os.path.join(OUT, 'round2_mp')
CAPS60 = os.path.join(OUT, 'captures', 'round2_mp')
TEMP60 = 'TEMP_AS60_'
IA = '/Game/Assets/MyShip/Drivable/Input/'
IA_LMB_PATH = '/Game/Level/PlayerInput/IA_LMB'
IA_MOVE_PATH = '/Game/Level/PlayerInput/IA_Move'
IMC_AIRSHIP_PATH = '/Game/Assets/MyShip/Drivable/Input/IMC_Airship'
SETTINGS_CLS = '/Script/Aura.AirshipSettings'
PILOT_COMP_CLS = '/Script/Aura.AirshipPilotComponent'
BALL_BP = '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball.BP_AirshipCannonball_C'
GE_GUN = '/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C'
MAX_CAPS = 16
# L_AirshipTest (as_22_test_map.py): ship spawn, the port cannon wall's face (60 x 4 x 30 m, x -3000..3000, z 100..3100)
SPAWN = (0.0, 2500.0, 1600.0)
PORT_FACE_Y = -9300.0
PARK2 = (0.0, 40000.0, 1600.0)       # ship 2, away from every flight path (as as_59)
FAR1 = (0.0, 80000.0, 1600.0)        # ship 1 in g5_: 400 m from ship 2, past the turrets' 250 m range and out of their arcs
CHAR_FOOT = (-2500.0, -2500.0, 150.0)
T6_AHEAD = 10780.0                   # g3_arc: ship 1 this far ahead of ship 2 (centres): its stern ~60 m from the muzzles (as_59 T6.4)
GUN_GAP = 4500.0                     # g4_: the host's deck point -> ship 2's turret L, horizontal
HOST_DECK_X = 2850.0                 # g4_: the host on ship 1's forward deck, ahead of its turrets (hull x 2100)
TURRET_PT_SIDE = 500.0               # g1_turret: aim point on the port wall this far ahead of turret L's pivot
CANNON_PT_AHEAD = 1500.0             # g1_aim: aim point on the port wall this far ahead of L1's muzzle
MUZZLE_FALLBACK = {'L1': (-44.8, -784.5, 323.7), 'L2': (-1143.7, -578.7, 363.5), 'R1': (-44.8, 784.5, 323.7), 'R2': (-1143.7, 578.7, 363.5)}
MOUNT_FALLBACK = [(2100.0, -245.0, 655.0), (2100.0, 245.0, 655.0)]
SCHEME_NAMES = {0: 'CLASSIC', 1: 'GALLEON', 2: 'SKY_RACER', 3: 'POINT_FLY'}
NEUTRAL = (0.0, 0.0, 0.0, 0.0, False, False)
BRAKE = (0.0, 0.0, 0.0, 0.0, False, True)
SETTINGS_SNAP = ('CrewDamageShare', 'DriftSpeed', 'DriftMaxDistance', 'bHoldWhenUnpiloted', 'HoldEngageSpeed', 'MuzzleFXMaxSeconds',
                 'TurretGunDamageMultiplier', 'DriverTurretArcDeg', 'DriftMinExitSpeed')
GROUPS = [
    ('g1_', [('g1_board', 3.0), ('g1_far', 3.0), ('g1_mount', 3.0), ('g1_aim', 3.0), ('g1_fire', 3.0), ('g1_broadside', 3.5),
             ('g1_exit', 4.0), ('g1_turret', 6.0), ('g1_overheat', 8.0), ('g1_wreck', 4.0)]),
    ('g2_', [('g2_walk', 5.0), ('g2_cruise', 17.0), ('g2_end', 5.0), ('g2_crew', 3.0)]),
    ('g3_', [('g3_swap', 4.0), ('g3_arc', 5.0), ('g3_port', 4.0), ('g3_r1', 5.0), ('g3_turret', 5.0), ('g3_exit', 3.0)]),
    ('g4_', [('g4_setup', 3.5), ('g4_hull', 5.0), ('g4_turret', 5.0), ('g4_bullet', 3.0), ('g4_damage', 2.5)]),
    ('g5_', [('g5_down', 5.0), ('g5_spent', 4.0)]),
    ('g6_', [('g6_cruise', 4.0), ('g6_drift', 22.0), ('g6_hold', 8.0)]),
    ('g8_', [('g8_jump', 11.0)]),
    ('g9_', [('g9_clock', 180.0)]),      # ends itself as soon as it is done (about 12 s + the wait for the client's clock)
    ('g7_', [('g7_k1', 5.5), ('g7_resp', 9.0), ('g7_k2', 5.5)]),
]
SKIPPED = {
    'T_late_join': 'late join is not possible in PIE (every PIE client joins at the start). The design relies on replicated '
                   'state and OnReps (OnRep_StationGunners, the turrets\' OnRep_Destroyed, the balls\' OnRep_ShotDown); code '
                   'review covers it (SPEC_A.md section 4, "Not testable in PIE")',
    'T5.11': 'Aura.Airship.Kill kills every ship of the world, which ends the later groups: as_59 T5.11 S covers it',
    'T5.15': 'standalone (as_59 T5.15 S); the ragdoll rule runs on every machine but is not driven here',
    'T4.5': 'not in as_60 (a ship firing at another ship\'s manned station)',
    'T8.1': 'not in as_60 (F under the hull: as_59 T8.1 S; the helm at the wheel and the exit in place: as_59 T8.2-T8.7, here T8.4 L)',
    'T2.8': 'needs 3 players (a rider, a gunner and the pilot)',
    'T3.5': 'L_AirshipTest has no swarm spawner', 'T6.7': 'L_AirshipTest has no swarm spawner',
    'T7.x': 'Blender / captures: as_59 and the Blender checks',
}


def en(x):
    n = getattr(x, 'name', None)
    return n if isinstance(n, str) else str(x).split('.')[-1].split(':')[0].strip('<> ')


def same(a, b):
    try:
        return a is not None and b is not None and bool(a == b)
    except Exception:  # noqa: BLE001
        return False


def parse_export(txt):
    """'(A=1.0,B=(0.1,0.2),C=True)' -> dict; nested parentheses (arrays) become lists of floats (or strings). As as_59."""
    s = txt.strip()
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    parts, depth, cur, q = [], 0, '', False
    for ch in s:
        if ch == '"':
            q = not q
        if not q and ch == '(':
            depth += 1
        elif not q and ch == ')':
            depth -= 1
        if ch == ',' and depth == 0 and not q:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    if cur:
        parts.append(cur)

    def conv(v):
        v = v.strip()
        if v in ('True', 'False'):
            return v == 'True'
        if v.startswith('(') and v.endswith(')'):
            inner = v[1:-1].strip()
            return [conv(x) for x in inner.split(',')] if inner else []
        try:
            return float(v)
        except ValueError:
            return v
    out = {}
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
            out[k.strip()] = conv(v)
    return out


def call(obj, *names, **kw):
    """the first method of obj that exists among names, called with kw['args']."""
    args = kw.get('args', ())
    for n in names:
        f = getattr(obj, n, None)
        if f is not None:
            return f(*args)
    raise AttributeError('none of %s on %s' % (names, obj))


def trace_loc(res):
    """hit location of a K2_LineTraceComponent result (None on a miss), whichever way the bool return is wrapped (as_45)"""
    if not res:
        return None
    if isinstance(res, tuple):
        if isinstance(res[0], bool) and not res[0]:
            return None
        for x in res:
            if isinstance(x, unreal.Vector):
                return v3(x)
    return None


HIT_INFO_ERR = []      # the first failure of each way hit_info reads a HitResult (as as_59: a silent miss hid it before)


def hit_info(res):
    """(blocking, impact point list, actor, component) of a line trace result (HitResult, tuple or None). As as_59: reads
    the HitResult with GameplayStatics.break_hit_result (not in UE 5.8 Python), else HitResult.to_tuple(), else its
    properties; each failure is recorded once in HIT_INFO_ERR (a failure used to read as 'no hit')."""
    if res is None:
        return False, None, None, None
    hit = res
    if isinstance(res, tuple):
        hit = next((x for x in res if isinstance(x, unreal.HitResult)), None)
        if hit is None:
            return False, None, None, None
    t = None
    for how in ('break', 'to_tuple'):
        try:
            t = tuple(unreal.GameplayStatics.break_hit_result(hit)) if how == 'break' else tuple(hit.to_tuple())
            break
        except Exception:  # noqa: BLE001
            if len(HIT_INFO_ERR) < 4:
                HIT_INFO_ERR.append('%s: %s' % (how, traceback.format_exc().strip().splitlines()[-1]))
    if t is not None:
        bools = [x for x in t if isinstance(x, bool)]
        vecs = [x for x in t if isinstance(x, unreal.Vector)]
        act = next((x for x in t if isinstance(x, unreal.Actor)), None)
        comp = next((x for x in t if isinstance(x, unreal.PrimitiveComponent)), None)
        if comp is not None and act is None:
            try:
                act = comp.get_owner()
            except Exception:  # noqa: BLE001
                pass
        imp = v3(vecs[1]) if len(vecs) > 1 else (v3(vecs[0]) if vecs else None)
        return (bools[0] if bools else False), imp, act, comp
    try:
        comp = hit.get_editor_property('component')
        act = comp.get_owner() if comp else None
        return bool(hit.get_editor_property('blocking_hit')), v3(hit.get_editor_property('impact_point')), act, comp
    except Exception:  # noqa: BLE001
        if len(HIT_INFO_ERR) < 4:
            HIT_INFO_ERR.append('props: %s' % traceback.format_exc().strip().splitlines()[-1])
        return False, None, None, None


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def stats(xs):
    if not xs:
        return None
    s = sorted(xs)
    return {'n': len(s), 'mean': r(sum(s) / len(s), 2), 'p95': r(s[min(len(s) - 1, int(0.95 * len(s)))], 2), 'max': r(s[-1], 2)}


def hdist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def fnum(x, default=None):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return default


class R60(object):
    def __init__(self):
        self.R = {'version': AS60_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'checks': {},
                  'events': [], 'series': [], 'errors': {}, 'lines': [], 'shots': [], 'done': False, 'setup': {}, 'mp': {}}
        self.orig = {}
        self.cfg = {}
        self.handle = None
        self.phase = 'arming'
        self.phases = []
        self.pi = -1
        self.p_t0 = 0.0
        self.now = 0.0
        self.t_world0 = None
        self.wall0 = time.time()
        self.end_wall = 0.0
        self.last_sample = -1.0
        self.last_status = 0.0
        self.D = {}
        self.carry = {}
        self.sw = self.cw = None
        self.hpc = self.rpc = self.cpc = None
        self.hchar = self.cchar_s = self.cchar_c = self.hchar_c = None
        self.ship1_s = self.ship1_c = self.ship2_s = self.ship2_c = None
        self.ship2_from_map = False
        self.sub_s = self.sub_c = None
        self.cidx = None
        self.capres = {}
        self.cap_dead = {}
        self.ncap = 0
        self.balls = {'server': {}, 'client': {}}
        self.ball_obj = {'server': {}, 'client': {}}
        self.log_file = find_log()
        self.log_off = os.path.getsize(self.log_file) if self.log_file else 0
        self.log_marks = []
        self.user_play = False
        self.frames = 0
        self.phase_clock = (0, time.time())
        self.fps_prev = None
        self.act = {}
        self.imc = None
        self.lag_on = False
        self.croles = None
        self.turret_fire_on = False
        self.verbose_pilot = False
        self.mz_local = dict(MUZZLE_FALLBACK)
        self.gun_base = 1.0
        self.share = 0.25
        self.attrs = {}
        for n in ('Health', 'MaxHealth'):
            a = unreal.GameplayAttribute()
            a.import_text('(AttributeName="%s",Attribute=/Script/Aura.MyAttributeSet:%s,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")' % (n, n))
            self.attrs[n] = a

    # ---------------------------------------------------------------- output
    def line(self, tag, msg):
        s = '%s: [%7.2f %s] %s' % (tag, self.now, self.phase, msg)
        self.R['lines'].append(s)
        try:
            with open(os.path.join(MP2, 'r2mp_log.txt'), 'a') as f:
                f.write(s + '\n')
        except Exception:  # noqa: BLE001
            pass

    def check(self, key, status, msg, data=None):
        self.R['checks'][key] = {'status': status, 'summary': msg, 'data': data, 't': r(self.now), 'phase': self.phase}
        self.line(status, '%s: %s' % (key, msg))

    def event(self, name, **kw):
        kw.update({'event': name, 't': r(self.now), 'phase': self.phase})
        self.R['events'].append(kw)

    def err(self, where):
        e = self.R['errors'].setdefault(where, {'n': 0, 'last': ''})
        e['n'] += 1
        e['last'] = traceback.format_exc()[-1500:]
        if e['n'] == 1:
            self.line('WARN', 'script error in %s: %s' % (where, e['last'].strip().splitlines()[-1]))

    def status_text(self):
        c = {}
        for v in self.R['checks'].values():
            c[v['status']] = c.get(v['status'], 0) + 1
        left = sum(d for _, d in self.phases[self.pi + 1:]) if self.phases and self.pi >= 0 else None
        return 'as_60 phase %s (%d/%d) game_t %.1f wall %.0f s frames %d checks %s, about %s game s left, done %s, reason %s' % (
            self.phase, self.pi + 1, len(self.phases), self.now, time.time() - self.wall0, self.frames, c,
            None if left is None else int(left), self.R['done'], self.R.get('reason'))

    def write(self, force=False):
        # The status file is small and goes every 2 s; the result dump only when forced (arm, every phase end, the end):
        # a big dump stalls the frame, and with Net PktLag (real time) a stall bunches up the lagged packets (as_45)
        if time.time() - self.last_status >= 2.0 or force:
            self.last_status = time.time()
            try:
                with open(os.path.join(MP2, 'r2mp_status.txt'), 'w') as f:
                    f.write(self.status_text() + '\n')
            except Exception:  # noqa: BLE001
                pass
        if not force:
            return
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        self.R['balls'] = self.balls
        self.R['hit_info_err'] = list(HIT_INFO_ERR)
        try:
            with open(os.path.join(MP2, 'r2mp_result.json'), 'w') as f:
                json.dump(self.R, f, default=str)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- arm / restore
    def settings(self):
        return unreal.get_default_object(unreal.load_class(None, SETTINGS_CLS))

    def build_phases(self):
        only = self.cfg.get('only')
        ph = [('settle', 4.0), ('spawn2', 3.0)]
        for prefix, items in GROUPS:
            keep = [p for p in items if not only or any(p[0].startswith(o) for o in only)]
            if not keep:
                continue
            if keep[0][0] != items[0][0]:
                keep = [items[0]] + keep      # the group's first phase sets up its roles
            ph += keep
        return ph

    def arm(self):
        os.makedirs(MP2, exist_ok=True)
        os.makedirs(CAPS60, exist_ok=True)
        g = globals()
        lag = g.get('AS60_LAG_MS', 100.0)
        self.cfg = {'only': tuple(g.get('AS60_ONLY') or ()), 'lag_ms': float(100.0 if lag is None else lag),
                    'scheme': int(g.get('AS60_SCHEME', 3) if g.get('AS60_SCHEME', 3) is not None else 3),
                    'aim_scheme': int(g.get('AS60_AIM_SCHEME', 0) or 0),
                    'cruise_throttle': float(g.get('AS60_CRUISE_THROTTLE', 1.0) or 1.0)}
        self.phases = self.build_phases()
        self.R['cfg'] = self.cfg
        self.R['phases'] = self.phases
        with open(os.path.join(MP2, 'r2mp_log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (AS60_VERSION, self.R['armed_utc'], self.cfg))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if MAP_NAME not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open the map first' % (ew.get_path_name(), MAP_NAME))
            return False
        for cls in ('/Script/Aura.AirshipTurret', '/Script/Aura.AirshipCannonball', PILOT_COMP_CLS):
            if unreal.load_class(None, cls) is None:
                self.line('FAIL', '%s not found: the round-2 C++ is not built into this editor' % cls)
                return False
        ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
        self.R['play_settings'] = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
        pls = self.R['play_settings']
        if 'ListenServer' not in str(pls.get('PlayNetMode')) or int(pls.get('PlayNumberOfClients', 0)) != 2 or \
                str(pls.get('RunUnderOneProcess', True)).lower() in ('false', '0'):
            self.line('FAIL', 'play settings %s: want PIE_ListenServer, 2 players, one process (set_play_mode.sh listen 2 with '
                              'the editor closed)' % pls)
            return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 5 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            self.orig['engine'] = tl_get(eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS})
        except Exception:  # noqa: BLE001
            self.err('fixed_fps')
        try:
            bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
            self.orig['burrower_enabled'] = bool(bcdo.get_editor_property('bEnabled'))
            bcdo.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('burrower_settings')
        try:
            st = self.settings()
            snap = {}
            for n in SETTINGS_SNAP:
                try:
                    snap[n] = st.get_editor_property(n)
                except Exception:  # noqa: BLE001
                    self.err('settings_snapshot_' + n)
            self.orig['settings'] = snap
            self.R['setup']['settings'] = dict((k, str(v)) for k, v in snap.items())
            self.share = fnum(snap.get('CrewDamageShare'), 0.25)
        except Exception:  # noqa: BLE001
            self.err('settings_snapshot')
        for n in ('IA_AirshipBoard', 'IA_AirshipFire', 'IA_AirshipExit'):
            self.act[n] = unreal.load_asset(IA + n)
        self.act['IA_LMB'] = unreal.load_asset(IA_LMB_PATH)
        self.act['IA_Move'] = unreal.load_asset(IA_MOVE_PATH)
        self.imc = unreal.load_asset(IMC_AIRSHIP_PATH)
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP60):
                    eas.destroy_actor(a)
            cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, -6000, 3000))
            cap.set_actor_label(TEMP60 + 'Capture')
            cc = cap.capture_component2d
            cc.set_editor_property('capture_every_frame', False)
            cc.set_editor_property('capture_on_movement', False)
            self.line('INFO', 'placed %sCapture in the editor level (removed after PIE, the map is not saved)' % TEMP60)
        except Exception:  # noqa: BLE001
            self.err('temp_capture')
        with open(os.path.join(MP2, 'r2mp_restore.json'), 'w') as f:
            json.dump(self.orig, f, indent=1, default=str)
        self.log_mark('arm')
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed; listen-server PIE requested (%s); %d phases, about %d game s' % (
            self.R['play_settings'], len(self.phases), sum(d for _, d in self.phases)))
        return True

    def restore(self):
        try:
            if 'engine' in self.orig:
                eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
                tl_set(eng, {'bUseFixedFrameRate': bool(self.orig['engine'].get('bUseFixedFrameRate', False)),
                             'FixedFrameRate': float(self.orig['engine'].get('FixedFrameRate', 30.0))})
        except Exception:  # noqa: BLE001
            self.err('restore_engine')
        try:
            if 'burrower_enabled' in self.orig:
                bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
                bcdo.set_editor_property('bEnabled', self.orig['burrower_enabled'], unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_burrower')
        try:
            # Aura.Airship.Set Settings.<Name> writes the mutable class default (one object for both PIE worlds): put every
            # value the run may have changed back
            st = self.settings()
            for n, v in (self.orig.get('settings') or {}).items():
                st.set_editor_property(n, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_settings')
        try:
            ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            unreal.SystemLibrary.execute_console_command(ew, 'p.NetShowCorrections 0')
            unreal.SystemLibrary.execute_console_command(ew, 'log LogAirshipPilot Log')
            unreal.SystemLibrary.execute_console_command(ew, 'log LogNetPlayerMovement Log')
        except Exception:  # noqa: BLE001
            self.err('restore_cvar')

    def remove_temp(self):
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            n = 0
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP60):
                    eas.destroy_actor(a)
                    n += 1
            self.line('INFO', 'removed %d %s* actors from the editor level' % (n, TEMP60))
        except Exception:  # noqa: BLE001
            self.err('remove_temp')

    def finish(self, reason):
        if self.phase in ('ending', 'finished'):
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        for s in (self.ship1_c, self.ship2_c, self.ship1_s, self.ship2_s):
            try:
                if valid(s):
                    s.debug_clear_input()
            except Exception:  # noqa: BLE001
                pass
        for w in (self.sw, self.cw):
            try:
                if w is not None:
                    unreal.SystemLibrary.execute_console_command(w, 'Net PktLag=0')
            except Exception:  # noqa: BLE001
                pass
        try:
            if self.sw is not None and self.turret_fire_on:
                unreal.SystemLibrary.execute_console_command(self.sw, 'Aura.Airship.TurretFire 0')
        except Exception:  # noqa: BLE001
            pass
        self.log_mark('end')
        self.scan_log()
        self.finalize_t513()
        self.write_skips()
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and not self.user_play:
            les.editor_request_end_play()
        self.phase = 'ending'
        self.end_wall = time.time()

    def end_tick(self):
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and time.time() - self.end_wall < 20.0 and not self.user_play:
            return
        self.restore()
        if not les.is_in_play_in_editor():
            self.remove_temp()
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        self.phase = 'finished'
        self.R['done'] = True
        self.write(True)
        write_r2mp_report(self.R)
        self.line('INFO', 'done; results in round2_mp/r2mp_result.json / r2mp_report.txt')

    def write_skips(self):
        for k, why in SKIPPED.items():
            if k not in self.R['checks']:
                self.R['checks'][k] = {'status': 'SKIP', 'summary': why, 'data': None, 't': r(self.now), 'phase': '-'}
        ran = set(p for p, _ in self.phases)
        for prefix, items in GROUPS:
            if not any(p in ran for p, _ in items):
                self.R['checks']['group_' + prefix.strip('_')] = {'status': 'SKIP', 'summary': 'group %s not run (AS60_ONLY %s)' % (
                    prefix, self.cfg.get('only')), 'data': None, 't': r(self.now), 'phase': '-'}

    # ---------------------------------------------------------------- log
    def log_mark(self, name):
        try:
            self.log_marks.append((name, os.path.getsize(self.log_file) if self.log_file else 0, r(self.now)))
        except Exception:  # noqa: BLE001
            pass

    def log_text(self):
        if not self.log_file:
            return ''
        with open(self.log_file, 'rb') as f:
            f.seek(self.log_off)
            return f.read().decode('utf-8', 'replace')

    def log_between(self, a, b):
        """the log text between the first mark named a and the first mark named b after it (b None: to the end)"""
        try:
            ma = next((m for m in self.log_marks if m[0] == a), None)
            if ma is None or not self.log_file:
                return None
            mb = next((m for m in self.log_marks if b is not None and m[0] == b and m[1] >= ma[1]), None)
            with open(self.log_file, 'rb') as f:
                f.seek(ma[1])
                data = f.read((mb[1] - ma[1]) if mb else -1)
            return data.decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            self.err('log_between')
            return None

    def scan_log(self):
        if not self.log_file:
            return
        try:
            txt = self.log_text()
            lines = txt.splitlines()
            pats = {'airship': 'LogAirship', 'airship_warn': 'LogAirship: Warning', 'error': 'Error:', 'ensure': 'Ensure condition failed',
                    'accessed_none': 'Accessed None', 'user_play': 'Repeating last play command', 'not_recognized': 'Command not recognized',
                    'corr_client': '*** Client: Error for', 'corr_server': '*** Server: Error for',
                    'ignore_checks': 'is set to ignore error checks', 'back_on_seat': 'back on the seat of station',
                    'mounted': ' mounted ', 'crew': 'crew damage', 'manning': 'manning', 'left_station': 'left station',
                    'turret': 'LogAirshipTurret', 'cannonball': 'LogAirshipCannonball', 'pilot': 'LogAirshipPilot',
                    'hard_snap_lin': 'Hard snap due to linear difference error', 'netdriver': 'LogNet: Warning',
                    'ts_expired': 'ServerMove: TimeStamp expired', 'giveability_client': 'GiveAbility called on the client'}
            sc = {}
            for k, p in pats.items():
                hit = [l for l in lines if p in l]
                if k == 'error':
                    hit = [l for l in hit if 'not allowed' not in l and 'LoadErrors' not in l]
                sc[k] = {'count': len(hit), 'sample': hit[:10] + (hit[-5:] if len(hit) > 15 else [])}
            self.R['log_scan'] = sc
            seg = {}
            raw = txt.encode('utf-8', 'replace')
            marks = self.log_marks + [('eof', self.log_off + len(raw), r(self.now))]
            for i in range(len(marks) - 1):
                a = max(0, marks[i][1] - self.log_off)
                b = max(a, marks[i + 1][1] - self.log_off)
                chunk = raw[a:b].decode('utf-8', 'replace')
                seg[marks[i][0]] = {'corr_client': chunk.count('*** Client: Error for'), 'corr_server': chunk.count('*** Server: Error for'),
                                    'ignore_checks': chunk.count('is set to ignore error checks'), 'back_on_seat': chunk.count('back on the seat of station'),
                                    'airship_warn': chunk.count('LogAirship: Warning'), 'ts_expired': chunk.count('ServerMove: TimeStamp expired'),
                                    'error': len([l for l in chunk.splitlines() if 'Error:' in l and 'not allowed' not in l and 'LoadErrors' not in l])}
            self.R['log_segments'] = seg
            if sc['user_play']['count']:
                self.user_play = True
        except Exception:  # noqa: BLE001
            self.err('scan_log')

    def scan_user_play(self):
        if not self.log_file or int(self.now * 2) == self.carry.get('_ulast'):
            return
        self.carry['_ulast'] = int(self.now * 2)
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                if 'Repeating last play command' in f.read():
                    self.user_play = True
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- PIE helpers
    def wname(self, w):
        return 'server' if same(w, self.sw) else 'client'

    def cmd(self, w, c):
        unreal.SystemLibrary.execute_console_command(w, c)
        self.event('cmd', cmd=c, world=self.wname(w))
        self.line('INFO', 'console (%s): %s' % (self.wname(w), c))

    def scmd(self, c):
        self.cmd(self.sw, c)

    def subsystem(self, w):
        for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                lp = s.get_outer()
                if lp.get_class().get_name() == 'LocalPlayer' and same(lp.get_world(), w):
                    return s
            except Exception:  # noqa: BLE001
                pass
        return None

    def inject(self, which, action, vec=(1.0, 0.0, 0.0)):
        """one frame of input on that machine's Enhanced Input (held: call every frame; a gap is the release)"""
        try:
            if which == 'client':
                if self.sub_c is None:
                    self.sub_c = self.subsystem(self.cw)
                sub = self.sub_c
            else:
                if self.sub_s is None:
                    self.sub_s = self.subsystem(self.sw)
                sub = self.sub_s
            sub.inject_input_vector_for_action(self.act[action], unreal.Vector(*vec), [], [])
        except Exception:  # noqa: BLE001
            self.err('inject_%s_%s' % (which, action))

    def imc_on(self, sub):
        try:
            res = sub.has_mapping_context(self.imc)
            return bool(res[0] if isinstance(res, tuple) else res)
        except Exception:  # noqa: BLE001
            self.err('has_mapping_context')
            return None

    def pilot_comp(self, pc):
        return pc.get_component_by_class(unreal.load_class(None, PILOT_COMP_CLS))

    def tele(self, ship):
        try:
            return parse_export(ship.get_flight_telemetry().export_text())
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def mode(self, ship):
        v = fnum(self.tele(ship).get('UnpilotedMode'))
        return int(v) if v is not None else -1

    def ship_hp(self, ship):
        return fnum(self.tele(ship).get('Health')) if valid(ship) else None

    def health(self, a):
        try:
            if not valid(a):
                return None
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            if asc is None:
                return None
            x = asc.get_gameplay_attribute_value(self.attrs['Health'])
            return round(float(x[0] if isinstance(x, tuple) else x), 3)
        except Exception:  # noqa: BLE001
            self.err('health')
            return None

    def hurt(self, a, amount):
        """Damage through the airship damage effect on a's own ASC (SetByCaller), on the server (as as_45 / as_59)."""
        try:
            ge = unreal.load_class(None, DMG_GE)
            tag = unreal.GameplayTag()
            tag.import_text('(TagName="SetDamageByCaller")')
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            spec = asc.make_outgoing_spec(ge, 1.0, asc.make_effect_context())
            spec = unreal.AbilitySystemLibrary.assign_tag_set_by_caller_magnitude(spec, tag, float(amount))
            asc.apply_gameplay_effect_spec_to_self(spec)
            self.event('hurt', who=a.get_name(), amount=r(amount, 2))
        except Exception:  # noqa: BLE001
            self.err('hurt')

    def set_health(self, a, target):
        h = self.health(a)
        if h is not None and h > target:
            self.hurt(a, h - target)
        return h

    def hull(self, ship):
        return ship.get_editor_property('HullCollision')

    def tship(self, ship, loc, yaw=0.0, vel=(0.0, 0.0, 0.0)):
        """teleport a server ship (and what is attached to it), velocities zeroed (as as_59)"""
        ship.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
        h = self.hull(ship)
        h.set_physics_linear_velocity(unreal.Vector(*vel), False, 'None')
        h.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
        self.event('teleport', ship=ship.get_name(), loc=r(list(loc), 0), yaw=r(yaw, 1))

    def wind_off(self, ship):
        try:
            fc = ship.get_editor_property('Flight')
            for n in ('WindLateralAccel', 'WindRollAccel', 'WindPitchAccel'):
                # NEVER: no Pre/PostEditChange on a PIE component (that re-registers it, as_43)
                fc.set_editor_property(n, 0.0, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('wind_off')

    def set_scheme(self, ship, s):
        try:
            ship.set_control_scheme(getattr(unreal.AirshipControlScheme, SCHEME_NAMES[int(s)]))
            self.event('scheme', ship=ship.get_name(), scheme=SCHEME_NAMES.get(int(s)))
        except Exception:  # noqa: BLE001
            self.err('set_scheme')

    def yaw(self, ship):
        return float(ship.get_actor_rotation().yaw)

    def fwd(self, ship):
        return v3(ship.get_actor_forward_vector())

    def rgt(self, ship):
        return v3(ship.get_actor_right_vector())

    def loc(self, a):
        return v3(a.get_actor_location())

    def rel(self, ship, p):
        """hull-space (= HullCollision = the ship's root) location of the world point p"""
        return v3(unreal.MathLibrary.inverse_transform_location(ship.get_actor_transform(), unreal.Vector(*p)))

    def world_of(self, ship, local):
        return v3(unreal.MathLibrary.transform_location(ship.get_actor_transform(), unreal.Vector(*local)))

    def hh(self, c):
        caps = gp(c, 'capsule_component', 'CapsuleComponent')
        try:
            return float(caps.get_scaled_capsule_half_height()) if caps else 90.0
        except Exception:  # noqa: BLE001
            return 90.0

    def seat_local(self, ship, st):
        return self.rel(ship, v3(ship.get_station_seat_location(st)))

    def helm_local(self, ship):
        return self.rel(ship, v3(ship.get_pilot_seat_location()))

    def seat_rel_expected(self, ship, st, c):
        """the gunner's capsule centre at the seat, hull space (AAirshipPawn::GetStationSeatRelativeTransform)"""
        s = self.seat_local(ship, st)
        clr = fnum(gp(ship, 'PilotSeatClearance', 'pilot_seat_clearance', default=5.0), 5.0)
        return [s[0], s[1], s[2] + self.hh(c) + clr]

    def cm_flags(self, c):
        cm = gp(c, 'character_movement', 'CharacterMovement')
        if cm is None:
            return {}
        return {'server_ignores_errors': gp(cm, 'ignore_client_movement_error_checks_and_correction', 'bIgnoreClientMovementErrorChecksAndCorrection'),
                'client_ignores_corrections': gp(cm, 'client_ignore_movement_corrections', 'bClientIgnoreMovementCorrections')}

    def char_info(self, c, ship=None):
        if not valid(c):
            return None
        cm = gp(c, 'character_movement', 'CharacterMovement')
        caps = gp(c, 'capsule_component', 'CapsuleComponent')
        par = c.get_attach_parent_actor()
        p = self.loc(c)
        d = {'loc': r(p, 1), 'mode': en(cm.get_editor_property('movement_mode')) if cm else None,
             'cmc_tick': bool(cm.is_component_tick_enabled()) if cm else None, 'coll': en(caps.get_collision_enabled()) if caps else None,
             'actor_coll': bool(c.get_actor_enable_collision()), 'att': par.get_name() if par else None, 'health': self.health(c),
             'role': en(c.get_local_role()), 'name': c.get_name()}
        if valid(ship):
            d['rel'] = r(self.rel(ship, p), 1)
        return d

    def prim_info(self, c):
        """every primitive component of the character c: collision enabled, object type, its response to PhysicsBody (the
        hull's object type) and to Pawn, simulating or not (what could push the hull's physics body)"""
        out = []
        try:
            for pc in c.get_components_by_class(unreal.PrimitiveComponent):
                try:
                    par = pc.get_attach_parent()
                    out.append({'name': pc.get_name(), 'cls': pc.get_class().get_name(), 'coll': en(pc.get_collision_enabled()),
                                'obj': en(pc.get_collision_object_type()), 'profile': str(pc.get_collision_profile_name()),
                                'to_physicsbody': en(pc.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PHYSICS_BODY)),
                                'to_pawn': en(pc.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),
                                'sim': bool(pc.is_simulating_physics()), 'parent': par.get_name() if par else None})
                except Exception:  # noqa: BLE001
                    self.err('prim_info_one')
        except Exception:  # noqa: BLE001
            self.err('prim_info')
        return out

    def deck_comp(self, ship):
        """what characters stand on and Visibility traces hit: the Mesh (PA_Airship's boxes, tops at the planks) when the
        ship says so (AAirshipPawn::IsDeckOnPhysicsAsset, Talal 11-25), else the hull's collision (v1: the UCX lid)"""
        try:
            if bool(call(ship, 'is_deck_on_physics_asset')):
                return ship.get_editor_property('Mesh')
        except Exception:  # noqa: BLE001
            self.err('deck_comp')
        return self.hull(ship)

    def deck_point(self, ship, hx, hy, c):
        """world point on the deck (deck_comp: a line trace on that component alone; the planks' boxes, or whatever part box
        stands over that spot) at hull-space (hx, hy), plus the character's half height + 30 cm (as as_59)"""
        tr = ship.get_actor_transform()
        top = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, 1600.0))
        bot = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, -200.0))
        hit = trace_loc(self.deck_comp(ship).line_trace_component(top, bot, False, False, False))
        p = hit if hit is not None else self.world_of(ship, (hx, hy, 700.0))
        return [p[0], p[1], p[2] + self.hh(c) + 30.0], hit is not None

    def tp(self, chars, loc, yaw):
        for c in chars:
            if not valid(c):
                continue
            try:
                c.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
                cm = gp(c, 'character_movement', 'CharacterMovement')
                if cm:
                    cm.stop_movement_immediately()
            except Exception:  # noqa: BLE001
                self.err('tp')

    def tp_client(self, loc, yaw):
        """both copies of the client's character (as as_45: the client's own copy is the autonomous one)"""
        self.tp([self.cchar_s, self.cchar_c], loc, yaw)
        self.event('tp_client', loc=r(list(loc), 0))

    def tp_host(self, loc, yaw):
        self.tp([self.hchar], loc, yaw)
        self.event('tp_host', loc=r(list(loc), 0))

    def local_socket(self, ship, name):
        m = ship.get_editor_property('Mesh')
        return v3(m.get_socket_transform(name, unreal.RelativeTransformSpace.RTS_COMPONENT).translation)

    def muzzle_w(self, ship, c):
        return self.world_of(ship, self.mz_local[c])

    def muzzle_comps(self, ship):
        out = []
        try:
            fx = ship.get_editor_property('MuzzleFX')
            for c in ship.get_editor_property('Mesh').get_children_components(True):
                if isinstance(c, unreal.NiagaraComponent) and fx is not None and same(c.get_asset(), fx):
                    out.append(c.get_name())
        except Exception:  # noqa: BLE001
            self.err('muzzle')
        return out

    def turret(self, ship, i):
        try:
            t = ship.get_turret(i)
            if valid(t):
                return t
        except Exception:  # noqa: BLE001
            self.err('get_turret')
        try:
            for t in (ship.get_editor_property('Turrets') or []):
                if valid(t) and call(t, 'get_turret_index') == i:
                    return t
        except Exception:  # noqa: BLE001
            self.err('turrets')
        return None

    def tstate(self, t):
        d = {}
        if not valid(t):
            return d
        for k, names in (('destroyed', ('is_turret_destroyed',)), ('heat', ('get_heat01', 'get_heat_01')), ('overheated', ('is_overheated',)),
                         ('health', ('get_health',)), ('shots', ('get_shot_count',)), ('yaw', ('get_aim_yaw_deg',)), ('pitch', ('get_aim_pitch_deg',))):
            try:
                v = call(t, *names)
                d[k] = round(float(v), 4) if isinstance(v, float) else v
            except Exception:  # noqa: BLE001
                d[k] = None
        return d

    def shots(self, t):
        v = self.tstate(t).get('shots')
        return int(v) if isinstance(v, (int, float)) else 0

    def comp_active(self, a, prop):
        try:
            return bool(a.get_editor_property(prop).is_active())
        except Exception:  # noqa: BLE001
            self.err('active_' + prop)
            return None

    def turret_pivot_local(self, t, i):
        try:
            m = v3(t.get_editor_property('Mount').get_editor_property('location'))
        except Exception:  # noqa: BLE001
            m = list(MOUNT_FALLBACK[i])
        piv = fnum(gp(t, 'PivotHeight', 'pivot_height', default=150.0), 150.0)
        return [m[0], m[1], m[2] + piv]

    def turret_expected_aim(self, ship, t, i, point):
        """mount-relative yaw / pitch (deg) from the gun pivot to a world point (the turret's ComputeAimRaw)"""
        p = self.rel(ship, point)
        pv = self.turret_pivot_local(t, i)
        d = [p[k] - pv[k] for k in range(3)]
        return math.degrees(math.atan2(d[1], d[0])), math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))

    def gunner(self, ship, st):
        try:
            return call(ship, 'get_station_gunner', args=(st,))
        except Exception:  # noqa: BLE001
            try:
                return (ship.get_editor_property('StationGunners') or [None] * 6)[st]
            except Exception:  # noqa: BLE001
                return None

    def station_of(self, ship, c):
        for st in range(6):
            if same(self.gunner(ship, st), c):
                return st
        return None

    def anim(self, ship, names):
        out = {}
        try:
            ai = ship.get_editor_property('Mesh').get_anim_instance()
        except Exception:  # noqa: BLE001
            return out
        if ai is None:
            return out
        for n in names:
            try:
                out[n] = round(float(ai.get_editor_property(n)), 3)
            except Exception:  # noqa: BLE001
                out[n] = None
        return out

    def cam(self, w):
        cm = unreal.GameplayStatics.get_player_camera_manager(w, 0)
        return v3(cm.get_camera_location()), cm.get_camera_rotation()

    def aim_pc(self, which, point):
        """that machine's control rotation from its camera toward a world point (the aim traces start at the camera)"""
        try:
            pc, w = (self.hpc, self.sw) if which == 'host' else (self.cpc, self.cw)
            loc, _ = self.cam(w)
            pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*loc), unreal.Vector(*point)))
        except Exception:  # noqa: BLE001
            self.err('aim_' + which)

    def look(self, which, yaw, pitch=-4.0):
        try:
            pc = self.hpc if which == 'host' else self.cpc
            pc.set_control_rotation(unreal.Rotator(0.0, float(pitch), float(yaw)))
        except Exception:  # noqa: BLE001
            self.err('look_' + which)

    def cam_yaw_off(self, w, ship):
        try:
            _, rot = self.cam(w)
            return abs(wrap180(float(rot.yaw) - self.yaw(ship)))
        except Exception:  # noqa: BLE001
            return None

    def trace(self, w, a, b, ignore=None):
        try:
            res = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(*a), unreal.Vector(*b), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         False, ignore or [], unreal.DrawDebugTrace.NONE, True)
            ok, imp, act, comp = hit_info(res)
            return {'hit': ok, 'at': r(imp, 1) if imp else None, 'actor': act.get_name() if act else None,
                    'comp': comp.get_name() if comp else None, 'cls': act.get_class().get_name() if act else None}
        except Exception:  # noqa: BLE001
            self.err('trace')
            return None

    def own_ignores(self, ship):
        out = [ship] if valid(ship) else []
        for i in (0, 1):
            t = self.turret(ship, i) if valid(ship) else None
            if t is not None:
                out.append(t)
        return out

    def aim_point_est(self, w, which_ship, target):
        """where a camera trace toward target lands (first Visibility hit past which_ship and its turrets), else target"""
        try:
            c, _ = self.cam(w)
            d = [target[k] - c[k] for k in range(3)]
            n = math.sqrt(sum(x * x for x in d)) or 1.0
            end = [c[k] + d[k] / n * (n + 3000.0) for k in range(3)]
            t = self.trace(w, c, end, self.own_ignores(which_ship) + [x for x in (self.hchar, self.cchar_s) if valid(x)])
            return t['at'] if t and t.get('at') else list(target)
        except Exception:  # noqa: BLE001
            self.err('aim_point_est')
            return list(target)

    def spawn_ball(self, loc, vel, source, damage=60.0, gravity=-1.0):
        try:
            cls = unreal.load_class(None, BALL_BP) or unreal.load_class(None, BALL_CLS)
            b = unreal.AirshipCannonball.spawn_test_cannonball(self.sw, cls, unreal.Vector(*loc), unreal.Vector(*vel), source, float(damage), float(gravity))
            self.event('test_ball', loc=r(list(loc), 0), vel=r(list(vel), 0), source=source.get_name() if source else None,
                       ball=b.get_name() if b else None)
            return b
        except Exception:  # noqa: BLE001
            self.err('spawn_ball')
            return None

    def ball_state(self, b):
        d = {}
        if not valid(b):
            return d
        for k, names in (('health', ('get_ball_health',)), ('shot_down', ('is_shot_down',))):
            try:
                d[k] = call(b, *names)
            except Exception:  # noqa: BLE001
                d[k] = None
        try:
            d['hidden'] = bool(gp(b, 'hidden', 'bHidden', default=False))
            d['coll'] = bool(b.get_actor_enable_collision())
            d['loc'] = r(self.loc(b), 1)
        except Exception:  # noqa: BLE001
            self.err('ball_state')
        return d

    def client_ball_near(self, p, radius=800.0):
        best = None
        for k, b in list(self.ball_obj['client'].items()):
            try:
                if not valid(b):
                    continue
                d = dist(self.loc(b), p)
                if d <= radius and (best is None or d < best[0]):
                    best = (d, b)
            except Exception:  # noqa: BLE001
                continue
        return best[1] if best else None

    # ---------------------------------------------------------------- balls (both worlds, every frame)
    def track_balls(self):
        cls = unreal.load_class(None, BALL_CLS)
        for key, w in (('server', self.sw), ('client', self.cw)):
            try:
                seen = set()
                for b in unreal.GameplayStatics.get_all_actors_of_class(w, cls):
                    k = b.get_name()
                    seen.add(k)
                    p = v3(b.get_actor_location())
                    rec = self.balls[key].get(k)
                    if rec is None:
                        rec = {'first': r(p, 1), 't0': r(self.now, 3), 'phase': self.phase}
                        try:
                            src = b.get_editor_property('SourceShip')
                            rec['source'] = src.get_name() if src else None
                        except Exception:  # noqa: BLE001
                            rec['source'] = None
                        self.balls[key][k] = rec
                        self.ball_obj[key][k] = b
                    hidden = bool(gp(b, 'hidden', 'bHidden', default=False))
                    if hidden and 'hidden_at' not in rec:
                        rec['hidden_at'], rec['t_hidden'] = r(p, 1), r(self.now, 3)
                    if rec.get('stopped'):
                        continue
                    if rec.get('last') is not None and dist(p, rec['last']) < 2.0 and self.now > rec['t_last'] + 1e-6:
                        if dist(p, rec['first']) > 50.0 or hidden:
                            rec['stopped'], rec['t_hit'], rec['impact'] = True, rec['t_last'], r(p, 1)
                    else:
                        rec['last'], rec['t_last'] = r(p, 1), r(self.now, 3)
                for k, rec in self.balls[key].items():
                    if k not in seen and not rec.get('gone'):
                        rec['gone'] = r(self.now, 3)
                        self.ball_obj[key].pop(k, None)
            except Exception:  # noqa: BLE001
                self.err('balls_' + key)

    def new_balls(self, key, t0, near=None, radius=600.0, source=None):
        out = []
        for k, b in self.balls[key].items():
            if b['t0'] < t0 - 0.05:
                continue
            if near is not None and dist(b['first'], near) > radius:
                continue
            if source is not None and b.get('source') not in (None, source):
                continue
            out.append(b)
        return out

    # ---------------------------------------------------------------- recoil peaks (as as_45) and muzzle FX
    def rec_start(self, name, ships, cannons):
        self.D.setdefault('rec', {})[name] = {'ships': ships, 'cannons': list(cannons), 'server': {}, 'client': {}}

    def rec_update(self):
        for name, T in (self.D.get('rec') or {}).items():
            for key, ship in (('server', T['ships'][0]), ('client', T['ships'][1])):
                if not valid(ship):
                    continue
                av = self.anim(ship, ['CannonRecoilCm_' + c for c in T['cannons']])
                for c in T['cannons']:
                    rec = T[key].setdefault(c, {'max': 0.0, 'peaks': 0, 'prev': None, 'rising': False})
                    v = av.get('CannonRecoilCm_' + c) or 0.0
                    if rec['prev'] is None:
                        rec['prev'] = v
                        continue
                    rec['max'] = max(rec['max'], round(v, 2))
                    if v > rec['prev'] + 0.05 and not rec['rising']:
                        rec['rising'] = True
                        rec['peaks'] += 1
                    elif v < rec['prev'] - 0.05:
                        rec['rising'] = False
                    rec['prev'] = v

    def peaks(self, name, key, c):
        T = (self.D.get('rec') or {}).get(name) or {}
        return ((T.get(key) or {}).get(c) or {}).get('peaks')

    def mz_start(self, name, ships, until):
        self.D.setdefault('mz', {})[name] = {'ships': ships, 'until': self.now + until,
                                            'old': {'server': set(self.muzzle_comps(ships[0])), 'client': set(self.muzzle_comps(ships[1]))},
                                            'new': {'server': set(), 'client': set()}}

    def mz_update(self):
        for name, T in (self.D.get('mz') or {}).items():
            if self.now > T['until']:
                continue
            for key, ship in (('server', T['ships'][0]), ('client', T['ships'][1])):
                if valid(ship):
                    for c in self.muzzle_comps(ship):
                        if c not in T['old'][key]:
                            T['new'][key].add(c)

    def mz_new(self, name):
        T = (self.D.get('mz') or {}).get(name)
        return {'server': len(T['new']['server']), 'client': len(T['new']['client'])} if T else {'server': None, 'client': None}

    # ---------------------------------------------------------------- captures (TEMP_AS60_Capture, both worlds, as as_45)
    def capture(self, w, label, kind, ship=None):
        key = self.wname(w)
        if self.cap_dead.get(key) or self.ncap >= MAX_CAPS:
            return None
        try:
            if key not in self.capres:
                caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.SceneCapture2D) if (TEMP60 + 'Capture') in a.get_actor_label()]
                if not caps:
                    self.cap_dead[key] = True
                    self.line('WARN', 'no %sCapture in the %s world: no captures there' % (TEMP60, key))
                    return None
                rt = unreal.RenderingLibrary.create_render_target2d(w, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8)
                cc = caps[0].capture_component2d
                cc.set_editor_property('texture_target', rt)
                cc.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                cc.set_editor_property('capture_every_frame', False)
                cc.set_editor_property('capture_on_movement', False)
                cc.set_editor_property('always_persist_rendering_state', True)
                self.capres[key] = (caps[0], cc, rt)
            a, cc, rt = self.capres[key]
            fov = 60.0
            if kind == 'player':
                cm = unreal.GameplayStatics.get_player_camera_manager(w, 0)
                frm, rot, fov = cm.get_camera_location(), cm.get_camera_rotation(), cm.get_fov_angle()
            else:
                views = {'side': ((2500.0, -5200.0, 1400.0), (-300.0, 0.0, 0.0)), 'deck': ((-2200.0, -2600.0, 1500.0), (-650.0, 0.0, 400.0)),
                         'bow': ((1200.0, -1400.0, 1300.0), (2300.0, 0.0, 700.0)), 'port': ((-3200.0, -2600.0, 900.0), (-600.0, -650.0, 300.0))}
                if kind not in views or not valid(ship):
                    return None
                frm = unreal.Vector(*self.world_of(ship, views[kind][0]))
                rot = unreal.MathLibrary.find_look_at_rotation(frm, unreal.Vector(*self.world_of(ship, views[kind][1])))
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(frm, rot, False, True)
            cc.capture_scene()
            name = '%s_%s_%s' % (label, kind, key)
            unreal.RenderingLibrary.export_render_target(w, rt, CAPS60, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 'kind': kind, 'world': key, 't': r(self.now), 'file': os.path.join(CAPS60, name + '.png')})
            return name
        except Exception:  # noqa: BLE001
            self.err('capture_' + key)
            self.cap_dead[key] = True
            return None

    # ---------------------------------------------------------------- sampling (5 Hz, light)
    def sample(self):
        if self.now - self.last_sample < 0.2:
            return
        self.last_sample = self.now
        try:
            s = {'t': r(self.now, 2), 'ph': self.phase}
            for key, a in (('S1s', self.ship1_s), ('S1c', self.ship1_c), ('S2s', self.ship2_s), ('S2c', self.ship2_c)):
                if valid(a):
                    t = self.tele(a)
                    s[key] = {'loc': r(self.loc(a), 0), 'v': r(t.get('ForwardSpeedMS'), 2), 'hp': r(t.get('Health'), 1),
                              'mode': t.get('UnpilotedMode'), 'st': t.get('StationMask'), 'pil': t.get('bHasPilot')}
            for key, c in (('Hs', self.hchar), ('Cs', self.cchar_s), ('Cc', self.cchar_c)):
                if valid(c):
                    par = c.get_attach_parent_actor()
                    s[key] = {'loc': r(self.loc(c), 0), 'hp': self.health(c), 'att': par.get_name() if par else None}
                    if key != 'Hs':
                        cm = gp(c, 'character_movement', 'CharacterMovement')
                        s[key]['mode'] = en(cm.get_editor_property('movement_mode')) if cm else None
            self.R['series'].append(s)
        except Exception:  # noqa: BLE001
            self.err('sample')

    # ---------------------------------------------------------------- state machine
    def role(self, w):
        try:
            if unreal.SystemLibrary.is_standalone(w):
                return 'standalone'
            return 'server' if unreal.SystemLibrary.is_server(w) else 'client'
        except Exception:  # noqa: BLE001
            return '?'

    def tick(self, dt):
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            self.err('tick')
            if sum(e['n'] for e in self.R['errors'].values()) > 400:
                self.finish('too many script errors')
        self.write()

    def _tick(self):
        if self.phase == 'finished':
            return
        if self.phase == 'ending':
            self.end_tick()
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.phase == 'wait_pie':
            ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
            sv = [w for w in ws if self.role(w) == 'server' and MAP_NAME in w.get_path_name()]
            cl = [w for w in ws if self.role(w) == 'client' and MAP_NAME in w.get_path_name()]
            if sv and cl:
                self.sw, self.cw = sv[0], cl[0]
                self.phase = 'wait_actors'
                self.line('INFO', 'PIE worlds: server %s, client %s' % (self.sw.get_path_name(), self.cw.get_path_name()))
            elif time.time() - self.wall0 > 240:
                self.finish('listen PIE did not start in 240 s (worlds %s)' % [(w.get_path_name(), self.role(w)) for w in ws])
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        tw = unreal.GameplayStatics.get_time_seconds(self.sw)
        if self.t_world0 is None:
            self.t_world0 = tw
        self.now = tw - self.t_world0
        self.frames += 1
        if self.phase == 'wait_actors':
            if self.find_actors():
                self.next_phase()
            elif self.now > 30:
                self.finish('actors not found after 30 s: %s' % self.R.get('setup_try'))
            return
        self.scan_user_play()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        self.track_balls()
        self.rec_update()
        self.mz_update()
        self.sample()
        self.client_roles_tick()
        el = self.now - self.p_t0
        ph = self.phase
        try:
            getattr(self, 'ph_' + ph, lambda e: None)(el)
        except Exception:  # noqa: BLE001
            self.err('ph_' + ph)
        if self.phase != ph:
            return
        if el >= self.phases[self.pi][1]:
            try:
                getattr(self, 'end_' + ph, lambda: None)()
            except Exception:  # noqa: BLE001
                self.err('end_' + ph)
                self.check(ph, 'FAIL', 'evaluation crashed: %s' % traceback.format_exc().strip().splitlines()[-1])
            self.write(True)
            if self.phase in ('ending', 'finished'):
                return
            self.next_phase()

    def next_phase(self):
        f0, w0 = self.phase_clock
        self.fps_prev = (self.frames - f0) / max(0.01, time.time() - w0)
        self.phase_clock = (self.frames, time.time())
        self.pi += 1
        if self.pi >= len(self.phases):
            self.finish('all phases done')
            return
        self.phase = self.phases[self.pi][0]
        self.p_t0 = self.now
        self.D = {}
        self.croles = None
        self.log_mark(self.phase)
        self.line('INFO', 'phase %s (%.1f s), real fps of the last phase %.1f' % (self.phase, self.phases[self.pi][1], self.fps_prev or 0.0))
        try:
            getattr(self, 'start_' + self.phase, lambda: None)()
        except Exception:  # noqa: BLE001
            self.err('start_' + self.phase)

    def client_ship(self, ship_s):
        """the client world's copy of a server ship: same name, else the nearest"""
        try:
            cls = unreal.load_class(None, SHIP_CLS)
            cs = list(unreal.GameplayStatics.get_all_actors_of_class(self.cw, cls))
            m = next((s for s in cs if s.get_name() == ship_s.get_name()), None)
            if m is not None:
                return m
            p = self.loc(ship_s)
            cs = [s for s in cs if not same(s, self.ship1_c)]
            return min(cs, key=lambda s: dist(self.loc(s), p)) if cs else None
        except Exception:  # noqa: BLE001
            self.err('client_ship')
            return None

    def host_on_client(self):
        """the client world's copy of the host's character (the Character nearest to the host's server location)"""
        try:
            p = self.loc(self.hchar)
            oth = [c for c in unreal.GameplayStatics.get_all_actors_of_class(self.cw, unreal.Character) if not same(c, self.cchar_c)]
            return min(oth, key=lambda c: dist(self.loc(c), p)) if oth else None
        except Exception:  # noqa: BLE001
            self.err('host_on_client')
            return None

    def find_actors(self):
        try:
            ship_cls = unreal.load_class(None, SHIP_CLS)
            self.hpc = unreal.GameplayStatics.get_player_controller(self.sw, 0)
            rem = [pc for pc in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.PlayerController) if not pc.is_local_controller()]
            self.rpc = rem[0] if rem else None
            self.cpc = unreal.GameplayStatics.get_player_controller(self.cw, 0)
            self.hchar = self.hpc.get_controlled_pawn() if self.hpc else None
            self.cchar_s = self.rpc.get_controlled_pawn() if self.rpc else None
            self.cchar_c = self.cpc.get_controlled_pawn() if self.cpc else None
            ss = sorted(unreal.GameplayStatics.get_all_actors_of_class(self.sw, ship_cls), key=lambda s: s.get_name())
            self.ship1_s = ss[0] if ss else None
            if len(ss) >= 2:
                self.ship2_s = ss[1]
                self.ship2_from_map = True
            self.ship1_c = self.client_ship(self.ship1_s) if self.ship1_s else None
            if self.cchar_c:
                self.hchar_c = self.host_on_client()
            self.sub_s = self.subsystem(self.sw)
            self.sub_c = self.subsystem(self.cw)
            self.cidx = None
            if self.rpc:
                for i in range(1, 8):
                    if same(unreal.GameplayStatics.get_player_controller(self.sw, i), self.rpc):
                        self.cidx = i
                        break
            self.R['setup_try'] = {'hpc': bool(self.hpc), 'rpc': bool(self.rpc), 'cpc': bool(self.cpc), 'hchar': bool(self.hchar),
                                   'cchar_s': bool(self.cchar_s), 'cchar_c': bool(self.cchar_c), 'hchar_c': bool(self.hchar_c),
                                   'ship1_s': bool(self.ship1_s), 'ship1_c': bool(self.ship1_c), 'sub_s': bool(self.sub_s), 'sub_c': bool(self.sub_c),
                                   'cidx': self.cidx is not None}
            if self.now > 3.0 and self.rpc and not self.cchar_s and 'restarted' not in self.R:
                gm = unreal.GameplayStatics.get_game_mode(self.sw)
                lp = self.hchar.get_actor_location() + unreal.Vector(0, 400, 300)
                gm.restart_player_at_transform(self.rpc, unreal.Transform(location=lp, rotation=unreal.Rotator(0, 0, 0)))
                self.R['restarted'] = str(lp)
                self.line('INFO', 'the client had no pawn: restart_player_at_transform next to the host')
            if all(self.R['setup_try'].values()) and isinstance(self.hchar, unreal.Character) and isinstance(self.cchar_c, unreal.Character):
                self.R['setup'].update({'server_world': self.sw.get_path_name(), 'client_world': self.cw.get_path_name(),
                                        'host_char': self.hchar.get_name(), 'client_char_server': self.cchar_s.get_name(),
                                        'client_char_client': self.cchar_c.get_name(), 'host_char_client': self.hchar_c.get_name(),
                                        'ship1': self.ship1_s.get_name(), 'ship1_client': self.ship1_c.get_name(), 'client_index': self.cidx,
                                        'ship_roles': (en(self.ship1_s.get_local_role()), en(self.ship1_c.get_local_role())),
                                        'ship2_from_map': self.ship2_s.get_name() if self.ship2_from_map else None})
                self.line('INFO', 'setup %s' % self.R['setup'])
                return True
        except Exception:  # noqa: BLE001
            self.err('find_actors')
        return False

    # ---------------------------------------------------------------- roles (every group's first phase)
    def where(self, c):
        for ship in (self.ship1_s, self.ship2_s):
            if not valid(ship):
                continue
            try:
                if same(ship.get_pilot(), c):
                    return ('pilot', ship, None)
            except Exception:  # noqa: BLE001
                pass
            st = self.station_of(ship, c)
            if st is not None:
                return ('station', ship, st)
        return ('foot', None, None)

    def ensure_roles(self, host, client):
        """host 'pilot1' (the host flies ship 1) or 'foot'; client 'pilot2' (the client flies ship 2) or 'foot'. The host's
        changes are server console commands in this frame (its machine is the server: every RPC is local anyway). The
        client's go through its own input, as a player's do (client_to: F / Exit injected into its Enhanced Input, one
        step every 0.8 s): a console command run from Python runs under the editor's script guard
        (FEditorScriptExecutionGuard: AActor::GetFunctionCallspace answers Local), so the RPCs it starts for a remote
        player (ClientMountChanged, ClientRestart) run on the server's copy and never reach the client. A no-op when the
        roles are already so (the full run)."""
        hw, cw = self.where(self.hchar), self.where(self.cchar_s)
        done = []
        if hw[0] == 'station':
            self.scmd('Aura.Airship.Dismount 0')
            done.append('host dismount')
        if hw[0] == 'pilot' and not (host == 'pilot1' and same(hw[1], self.ship1_s)):
            self.scmd('Aura.Airship.Exit 0')
            done.append('host exit')
        if host == 'pilot1' and not (hw[0] == 'pilot' and same(hw[1], self.ship1_s)):
            p, _ = self.deck_point(self.ship1_s, -300.0, 300.0, self.hchar)
            self.tp_host(p, self.yaw(self.ship1_s))
            self.scmd('Aura.Airship.Board 0')
            done.append('host boards ship 1')
        want_c = client == 'pilot2' and valid(self.ship2_s)
        if (want_c and not (cw[0] == 'pilot' and same(cw[1], self.ship2_s))) or (not want_c and cw[0] != 'foot'):
            self.client_to(client)
            done.append('client %s -> %s by its own input' % (cw[0], client))
        self.line('INFO', 'roles host %s client %s: were host %s client %s; %s' % (
            host, client, hw[0], cw[0], ', '.join(done) if done else 'nothing to change'))

    def board_point(self, ship, c):
        """where F takes ship's helm (Talal 11-25: only at the wheel, AAirshipPawn::IsWithinHelmReach): on the planks 80 cm
        behind the pilot's standing spot (HelmReach 150 cm; clear of somebody who stands at the spot itself), every gun
        seat more than 3.5 m away"""
        helm = self.helm_local(ship)
        return self.deck_point(ship, helm[0] - 80.0, helm[1], c)[0]

    def client_to(self, role, far_first=False):
        """the client's role changes through its own machine: 'pilot2' (F on ship 2's deck away from the guns), 'foot'.
        client_roles_tick does one step at a time (Exit / Dismount, teleport, F), 0.8 s apart (BoardCooldown 0.5 s).
        far_first (g3_swap, T8.2 L): before the step to the wheel the client is put on the planks 2.5 m behind the wheel
        of the free ship 2 and presses F there; self.far_res gets what happened in the 0.8 s after it."""
        self.croles = {'want': role, 'next': self.now, 'steps': [], 'tries': 0, 'tp': False, 'far': 'todo' if (far_first and role == 'pilot2') else None}
        self.client_roles_tick()

    def far_point(self, ship, c):
        """T8.2: on the planks 250 cm behind the wheel hub on the centre line (as as_59 T8.2 S): 195 cm behind the pilot's
        standing spot, outside HelmReach (150 cm). Returns (world point, info)"""
        helm = self.helm_local(ship)
        try:
            wheel = self.local_socket(ship, 'Helm_Wheel')
        except Exception:  # noqa: BLE001
            self.err('helm_wheel_socket')
            wheel = [helm[0] + 55.0, helm[1], helm[2] + 96.0]
        hx, hy = wheel[0] - 250.0, helm[1]
        p, traced = self.deck_point(ship, hx, hy, c)
        seats = [self.seat_local(ship, st) for st in range(6)]
        return p, {'hull_xy': [r(hx, 1), r(hy, 1)], 'traced': traced, 'wheel_h_cm': 250.0, 'seat_h_cm': r(hdist((hx, hy), helm), 1),
                   'min_gun_seat_cm': r(min(dist((hx, hy, helm[2]), x) for x in seats), 0), 'helm_reach': fnum(gp(self.settings(), 'HelmReach', 'helm_reach')),
                   'station_mount_distance': fnum(gp(self.settings(), 'StationMountDistance', 'station_mount_distance'))}

    def client_roles_tick(self):
        cr = getattr(self, 'croles', None)
        if not cr or cr.get('done') or self.now < cr['next']:
            return
        try:
            w = self.where(self.cchar_s)
            want = cr['want']
            if (want == 'pilot2' and w[0] == 'pilot' and same(w[1], self.ship2_s)) or (want == 'foot' and w[0] == 'foot'):
                cr['done'] = True
                self.line('INFO', 'client role %s reached at %.2f s: %s' % (want, self.now, cr['steps']))
                return
            cr['tries'] += 1
            if cr['tries'] > 6:
                cr['done'] = True
                self.line('WARN', 'client role %s not reached after 6 steps (%s): console fallback (the client is not told: Python '
                                  'script guard)' % (want, cr['steps']))
                if w[0] == 'station':
                    self.scmd('Aura.Airship.Dismount %d' % self.cidx)
                elif w[0] == 'pilot':
                    self.scmd('Aura.Airship.Exit %d' % self.cidx)
                if want == 'pilot2':
                    self.scmd('Aura.Airship.Board %d' % self.cidx)
                return
            if w[0] in ('station', 'pilot'):
                self.inject('client', 'IA_AirshipExit')
                cr['steps'].append('%s exit %.2f' % (w[0], self.now))
                cr['next'] = self.now + 0.8
            elif want == 'pilot2' and cr.get('far') == 'todo':
                cr['tries'] -= 1
                p, info = self.far_point(self.ship2_s, self.cchar_s)
                self.far_res = {'point': info, 'free_helm': not self.ship2_s.has_pilot()}
                self.tp_client(p, self.yaw(self.ship2_s))
                cr['far'] = 'tp'
                cr['steps'].append('far tp %.2f' % self.now)
                cr['next'] = self.now + 0.3
            elif want == 'pilot2' and cr.get('far') == 'tp':
                cr['tries'] -= 1
                self.far_res['at_F'] = {'server': self.char_info(self.cchar_s, self.ship2_s), 'client': self.char_info(self.cchar_c, self.ship2_c)}
                self.log_mark('g3_far_F')
                self.inject('client', 'IA_AirshipBoard')
                cr['far'] = 'pressed'
                cr['steps'].append('far F %.2f' % self.now)
                cr['next'] = self.now + 0.8
            elif want == 'pilot2' and cr.get('far') == 'pressed':
                cr['tries'] -= 1
                self.far_res['after'] = {'pilot': self.ship2_s.get_pilot().get_name() if self.ship2_s.get_pilot() else None,
                                         'client_sees_pilot': bool(self.ship2_c.has_pilot()),
                                         'client_pawn_is_char': same(self.cpc.get_controlled_pawn(), self.cchar_c),
                                         'stations': [self.station_of(self.ship2_s, self.cchar_s), self.station_of(self.ship1_s, self.cchar_s)],
                                         'server': self.char_info(self.cchar_s, self.ship2_s), 'client': self.char_info(self.cchar_c, self.ship2_c)}
                cr['far'] = 'done'
                cr['steps'].append('far result %.2f' % self.now)
                cr['next'] = self.now
            elif want == 'pilot2' and not cr['tp']:
                self.tp_client(self.board_point(self.ship2_s, self.cchar_s), self.yaw(self.ship2_s))
                cr['tp'] = True
                cr['steps'].append('tp %.2f' % self.now)
                cr['next'] = self.now + 0.1
            elif want == 'pilot2':
                self.inject('client', 'IA_AirshipBoard')
                cr['tp'] = False
                cr['steps'].append('F %.2f' % self.now)
                cr['next'] = self.now + 0.8
        except Exception:  # noqa: BLE001
            self.err('client_roles')

    def view_hit(self, w, ignore):
        """where that machine's view ray (the camera manager's location and rotation: what UAirshipPilotComponent::
        ComputeGunnerAim traces) first hits Visibility, past ignore; None on a miss"""
        try:
            loc, rot = self.cam(w)
            cp, sp_, cy, sy = (math.cos(math.radians(float(rot.pitch))), math.sin(math.radians(float(rot.pitch))),
                               math.cos(math.radians(float(rot.yaw))), math.sin(math.radians(float(rot.yaw))))
            f = [cp * cy, cp * sy, sp_]
            end = [loc[k] + f[k] * 30000.0 for k in range(3)]
            t = self.trace(w, loc, end, ignore)
            return (t or {}).get('at')
        except Exception:  # noqa: BLE001
            self.err('view_hit')
            return None

    def bullet(self, frm, to, damage):
        self.scmd('Aura.MechSentinel.TestBullet %.0f %.0f %.0f %.0f %.0f %.0f %s' % (tuple(frm) + tuple(to) + (damage,)))

    # ================================================================ settle / spawn2
    def start_settle(self):
        self.scmd('p.NetShowCorrections 1')
        for ship in (self.ship1_s, self.ship1_c):
            self.wind_off(ship)
        self.set_scheme(self.ship1_s, self.cfg['scheme'])
        geo = {}
        for c in ('L1', 'L2', 'R1', 'R2'):
            try:
                geo[c] = r(self.local_socket(self.ship1_s, 'Cannon_%s_Muzzle' % c), 1)
            except Exception:  # noqa: BLE001
                self.err('muzzle_socket')
        self.mz_local.update(geo)
        self.R['setup']['muzzles_hull'] = self.mz_local
        try:
            ge = unreal.load_class(None, GE_GUN)
            cdo = unreal.get_default_object(ge)
            tot = 0.0
            for m in cdo.get_editor_property('modifiers'):
                mm = m.get_editor_property('modifier_magnitude').get_editor_property('scalable_float_magnitude')
                tot += float(mm.get_editor_property('value'))
            self.gun_base = tot
        except Exception:  # noqa: BLE001
            self.err('ge_gun')
            self.gun_base = 1.0
        if not self.gun_base or self.gun_base <= 0.0:
            self.line('WARN', 'GE_GunShootDamage magnitude not readable as a plain number (%s): expecting the fallback 1' % self.gun_base)
            self.gun_base = 1.0
        self.R['setup']['gun_base_damage'] = self.gun_base
        self.R['setup']['crew_share'] = self.share
        self.line('INFO', 'muzzles (hull space) %s; GE_GunShootDamage magnitude %.3f; crew share %.2f' % (self.mz_local, self.gun_base, self.share))
        self.D['f0'], self.D['w0'] = self.frames, time.time()

    def ph_settle(self, el):
        if el >= 1.0 and 'tl' not in self.D:
            self.D['tl'] = True
            self.scmd('Aura.Airship.Telemetry')
            self.cmd(self.cw, 'Aura.Airship.Telemetry')

    def end_settle(self):
        fps = (self.frames - self.D['f0']) / max(0.01, time.time() - self.D['w0'])
        self.R['mp']['real_fps_settle'] = r(fps, 2)
        mounts = []
        try:
            for m in self.settings().get_editor_property('TurretMounts'):
                mounts.append(v3(m.get_editor_property('location')))
        except Exception:  # noqa: BLE001
            self.err('mounts')
            mounts = [list(m) for m in MOUNT_FALLBACK]
        out, ok = {}, True
        for key, ship in (('server', self.ship1_s), ('client', self.ship1_c)):
            rows = []
            for i in (0, 1):
                t = self.turret(ship, i)
                if t is None:
                    rows.append({'index': i, 'turret': None})
                    ok = False
                    continue
                lp = self.rel(ship, self.loc(t))
                want = mounts[i] if i < len(mounts) else None
                d = dist(lp, want) if want else None
                par = t.get_attach_parent_actor()
                hp = self.tstate(t).get('health')
                rows.append({'index': i, 'turret': t.get_name(), 'hull_loc': r(lp, 2), 'mount': want, 'off_cm': r(d, 2) if d is not None else None,
                             'parent': par.get_name() if par else None, 'health': hp, 'class': t.get_class().get_name()})
                ok = ok and d is not None and d <= 1.0 and same(par, ship) and hp is not None and abs(hp - 400.0) < 0.5
            out[key] = rows
        self.check('T6.1_turrets_L', 'PASS' if ok else 'FAIL', 'ship 1\'s two turrets on the server and the client: at the mounts +-1 cm '
                   '(hull space), attached to that machine\'s ship, 400 health: %s; real fps %.1f' % (out, fps), out)

    def start_spawn2(self):
        self.D['before'] = set(a.get_name() for a in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.load_class(None, SHIP_CLS)))
        if not self.ship2_from_map:
            self.scmd('Aura.Airship.Spawn')

    def ph_spawn2(self, el):
        if self.ship2_s is None:
            for a in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.load_class(None, SHIP_CLS)):
                if a.get_name() not in self.D['before'] and not a.is_airship_dead():
                    self.ship2_s = a
                    self.line('INFO', 'ship 2: %s' % a.get_name())
        if self.ship2_s is not None and el >= 1.0 and 'parked' not in self.D:
            self.D['parked'] = True
            self.wind_off(self.ship2_s)
            self.set_scheme(self.ship2_s, self.cfg['scheme'])
            self.tship(self.ship2_s, PARK2, 0.0)
        if self.ship2_s is not None and el >= 2.0 and self.ship2_c is None:
            self.ship2_c = self.client_ship(self.ship2_s)
            if self.ship2_c is not None:
                self.wind_off(self.ship2_c)

    def end_spawn2(self):
        ok = valid(self.ship2_s) and valid(self.ship2_c)
        self.check('setup_ship2', 'PASS' if ok else 'FAIL', 'ship 2 (%s) parked at %s: server %s, client copy %s, turrets server %s client %s' % (
            'the map\'s second ship' if self.ship2_from_map else 'Aura.Airship.Spawn', PARK2, self.ship2_s.get_name() if valid(self.ship2_s) else None,
            self.ship2_c.get_name() if valid(self.ship2_c) else None, [bool(self.turret(self.ship2_s, i)) for i in (0, 1)] if valid(self.ship2_s) else None,
            [bool(self.turret(self.ship2_c, i)) for i in (0, 1)] if valid(self.ship2_c) else None))
        if not ok:
            self.finish('no second ship on both machines')

    # ================================================================ g1_: client gunner on a host-piloted ship
    def start_g1_board(self):
        self.ensure_roles('pilot1', 'foot')
        p = self.loc(self.ship1_s)
        if hdist(p, SPAWN) > 5000.0 or abs(wrap180(self.yaw(self.ship1_s))) > 5.0:
            self.tship(self.ship1_s, SPAWN, 0.0)
        self.set_scheme(self.ship1_s, self.cfg['aim_scheme'])
        self.look('host', self.yaw(self.ship1_s), -8.0)

    def end_g1_board(self):
        ok = same(self.ship1_s.get_pilot(), self.hchar) and same(self.hpc.get_controlled_pawn(), self.ship1_s) and bool(self.ship1_c.has_pilot()) \
            and same(self.cpc.get_controlled_pawn(), self.cchar_c) and same(self.rpc.get_controlled_pawn(), self.cchar_s)
        self.check('g1_setup_host_pilot', 'PASS' if ok else 'FAIL', 'the host flies ship 1 (server pilot %s, host pawn is the ship %s, the client '
                   'sees a pilot %s), the client on foot %s; ship 1 at %s, scheme %s' % (
                       self.ship1_s.get_pilot().get_name() if self.ship1_s.get_pilot() else None, same(self.hpc.get_controlled_pawn(), self.ship1_s),
                       bool(self.ship1_c.has_pilot()), same(self.cpc.get_controlled_pawn(), self.cchar_c), r(self.loc(self.ship1_s), 0),
                       SCHEME_NAMES.get(self.cfg['aim_scheme'])))

    # ---- T5.2: F on the deck far from every station, the helm taken: refused
    def start_g1_far(self):
        s = self.ship1_s
        seats = [self.seat_local(s, st) for st in range(6)]
        helm = self.helm_local(s)
        pick = None
        for hx, hy in ((600.0, 0.0), (-300.0, 0.0), (1200.0, 0.0), (-1800.0, 0.0), (200.0, 0.0)):
            dmin = min(hdist((hx, hy), x) for x in seats)
            if dmin < 450.0:
                continue
            p, traced = self.deck_point(s, hx, hy, self.cchar_s)
            if traced:
                pick = (hx, hy, p, dmin)
                break
        if pick is None:
            pick = (600.0, 0.0, self.deck_point(s, 600.0, 0.0, self.cchar_s)[0], min(hdist((600.0, 0.0), x) for x in seats))
        self.D['pt'] = {'hull_xy': [pick[0], pick[1]], 'world': r(pick[2], 0), 'min_seat_cm': r(pick[3], 0), 'helm_cm': r(hdist((pick[0], pick[1]), helm), 0)}
        # deck_arrival (2026-11-27): the client comes from the ground (not a deck passenger: every primitive as the
        # blueprint has it) straight onto the planks, which lie inside the hull's collision convex (the lid is 2.6 m above
        # them). What the hovering ship does in the next second is recorded, and the character's primitives before / after.
        self.D['arr'] = {'ship0': self.loc(s), 'from': r(self.loc(self.cchar_s), 0), 'prims_before': self.prim_info(self.cchar_s), 'trk': []}
        self.tp_client(pick[2], self.yaw(s))

    def ph_g1_far(self, el):
        arr = self.D.get('arr')
        if arr is not None and el <= 2.0:
            p = self.loc(self.ship1_s)
            ci = self.char_info(self.cchar_s, self.ship1_s) or {}
            arr['trk'].append((r(el, 3), r(dist(p, arr['ship0']), 1), r(p[2] - arr['ship0'][2], 1), ci.get('coll'), ci.get('mode'),
                               r(dist(self.loc(self.ship1_c), arr['ship0']), 1)))
            if el >= 0.5 and 'prims_after' not in arr:
                arr['prims_after'] = self.prim_info(self.cchar_s)
        if el >= 1.0 and 'f' not in self.D:
            self.D['f'] = True
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client, far from the stations)')

    def end_g1_far(self):
        s = self.ship1_s
        gs = [self.station_of(s, self.cchar_s), self.station_of(self.ship2_s, self.cchar_s) if valid(self.ship2_s) else None]
        ok = all(g is None for g in gs) and same(s.get_pilot(), self.hchar) and same(self.cpc.get_controlled_pawn(), self.cchar_c) and \
            self.cchar_c.get_attach_parent_actor() is None
        self.check('T5.2_F_far_from_stations_L', 'PASS' if ok else 'FAIL', 'client F on ship 1\'s deck %s (>= 4.5 m from every seat), the '
                   'helm is the host\'s: station %s (want none), pilot still the host %s, client still on foot %s' % (
                       self.D.get('pt'), gs, same(s.get_pilot(), self.hchar), same(self.cpc.get_controlled_pawn(), self.cchar_c)), self.D.get('pt'))
        # deck_arrival_no_shove_L: a character that appears on the planks must not move the ship. The hull ignores Pawn, so
        # the capsule cannot; any other primitive of the character that blocks PhysicsBody with physics on is a kinematic
        # body inside the hull's convex until the passenger rule (UAirshipSubsystem::UpdatePassengers) makes it query only.
        # Limit 15 cm in the 2 s after the teleport (the hovering ship alone wanders about 1 cm).
        arr = self.D.get('arr') or {}
        trk = arr.get('trk') or []
        dmax = max([x[1] for x in trk] or [None]) if trk else None
        dzmin = min([x[2] for x in trk] or [None]) if trk else None
        dcmax = max([x[5] for x in trk] or [None]) if trk else None
        pb, pa = arr.get('prims_before') or [], arr.get('prims_after') or []
        phys = lambda L: [(x['name'], x['cls'], x['coll'], x['obj'], x['to_physicsbody']) for x in L if 'PHYSICS' in str(x['coll']).upper() and not x['sim']]  # noqa: E731
        changed = [(a['name'], a['coll'], b['coll']) for a in pb for b in pa if a['name'] == b['name'] and a['coll'] != b['coll']]
        q_at = next((x[0] for x in trk if x[3] == 'QUERY_ONLY'), None)
        okm = dmax is not None and dmax <= 15.0
        self.check('deck_arrival_no_shove_L', 'PASS' if okm else 'FAIL', 'the client from the ground %s onto ship 1\'s planks at hull xy %s (the host holds '
                   'the ship, no input): in the next 2 s the server\'s ship moved at most %s cm from where it was (want <= 15), lowest %s cm; the '
                   'client\'s copy of the ship at most %s cm; the capsule query only from %s s; the character\'s kinematic primitives with physics '
                   'collision before the teleport %s, after 0.5 s on deck %s; switched by the passenger rule %s' % (
                       arr.get('from'), (self.D.get('pt') or {}).get('hull_xy'), dmax, dzmin, dcmax, q_at, phys(pb), phys(pa), changed),
                   {'track': trk[::2], 'prims_before': pb, 'prims_after': pa})

    # ---- T5.1 / T5.14: F on the planks 2 m from L1's seat, on its helm side (the far side is the cannon itself: the deck
    # trace would put the player on its boxes; until the helm / deck change the player stood on the lid above it)
    def start_g1_mount(self):
        s = self.ship1_s
        seat, helm = self.seat_local(s, 0), self.helm_local(s)
        d = [seat[0] - helm[0], seat[1] - helm[1]]
        n = math.hypot(*d) or 1.0
        hx, hy = seat[0] - d[0] / n * 200.0, seat[1] - d[1] / n * 200.0
        p, traced = self.deck_point(s, hx, hy, self.cchar_s)
        lp = self.rel(s, p)
        self.D['pt'] = {'hull': r(lp, 0), 'traced': traced, 'seat_h_cm': r(hdist(lp, seat), 0), 'seat_dz_cm': r(lp[2] - self.hh(self.cchar_s) - 30.0 - seat[2], 0),
                        'helm_cm': r(dist(lp, helm), 0)}
        self.tp_client(p, self.yaw(s) - 90.0)
        self.line('INFO', 'client onto the planks near L1: %s' % self.D['pt'])

    def ph_g1_mount(self, el):
        s = self.ship1_s
        if el >= 0.8 and 'f' not in self.D:
            self.D['f'] = el
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client, near L1)')
        if 'f' in self.D:
            if 'srv_t' not in self.D and same(self.gunner(s, 0), self.cchar_s):
                self.D['srv_t'] = el
            if 'cli_t' not in self.D and same(self.cchar_c.get_attach_parent_actor(), self.ship1_c):
                self.D['cli_t'] = el
        if el >= 2.0 and 'fb' not in self.D and 'srv_t' not in self.D:
            self.D['fb'] = True
            self.scmd('Aura.Airship.Mount %d 0' % self.cidx)
            self.line('WARN', 'F did not man L1 in 1.2 s: fallback Aura.Airship.Mount')
        if el >= 2.4 and 'snap' not in self.D:
            self.D['snap'] = {'server': self.char_info(self.cchar_s, s), 'client': self.char_info(self.cchar_c, self.ship1_c),
                              'imc': self.imc_on(self.sub_c), 'seat_expected': r(self.seat_rel_expected(s, 0, self.cchar_s), 1),
                              'flags_server': self.cm_flags(self.cchar_s), 'flags_client': self.cm_flags(self.cchar_c),
                              'client_gunner_seen': self.gunner(self.ship1_c, 0) is not None}
            self.capture(self.cw, 'g1_mount', 'player')
            self.capture(self.sw, 'g1_mount', 'deck', s)

    def end_g1_mount(self):
        sn = self.D.get('snap') or {}
        sv, cl = sn.get('server') or {}, sn.get('client') or {}
        dev = dist(cl['rel'], sv['rel']) if cl.get('rel') and sv.get('rel') else None
        dexp = dist(sv['rel'], sn['seat_expected']) if sv.get('rel') and sn.get('seat_expected') else None
        t_srv = (self.D['srv_t'] - self.D['f']) if 'srv_t' in self.D and 'f' in self.D else None
        ok = (t_srv is not None and t_srv <= 0.5 + 1e-3 and not self.D.get('fb') and sv.get('att') == self.ship1_s.get_name()
              and cl.get('att') == self.ship1_c.get_name() and cl.get('cmc_tick') is False and sn.get('imc') is True and dev is not None and dev <= 5.0)
        self.check('T5.1_client_F_mounts_L1', 'PASS' if ok else 'FAIL', 'client F at %s: server StationGunners[0] = client %.2f s after F%s (want <= 0.5); '
                   'client copy attached to %s, CMC ticking %s (want off), IMC_Airship on the client %s; client copy vs server copy, hull '
                   'space: %s cm apart (want <= 5); server copy vs the seat (seat + half height + clearance) %s cm; client sees the gunner %s' % (
                       self.D.get('pt'), t_srv if t_srv is not None else -1, ' FALLBACK console Mount' if self.D.get('fb') else '', cl.get('att'),
                       cl.get('cmc_tick'), sn.get('imc'), r(dev, 2) if dev is not None else None, r(dexp, 2) if dexp is not None else None,
                       sn.get('client_gunner_seen')), sn)
        ok2 = all(x.get('actor_coll') is True and x.get('coll') == 'QUERY_ONLY' for x in (sv, cl))
        self.check('T5.14_gunner_collision_L', 'PASS' if ok2 else 'FAIL', 'mounted gunner: server copy actor collision %s capsule %s; client copy '
                   'actor collision %s capsule %s (want on, QUERY_ONLY on both)' % (sv.get('actor_coll'), sv.get('coll'), cl.get('actor_coll'), cl.get('coll')))
        fs, fc = sn.get('flags_server') or {}, sn.get('flags_client') or {}
        ok3 = bool(fs.get('server_ignores_errors')) and bool(fc.get('client_ignores_corrections'))
        self.check('fix6.1_flags_at_mount', 'PASS' if ok3 else 'FAIL', 'review fix 6.1 while mounted: server copy '
                   'bIgnoreClientMovementErrorChecksAndCorrection %s (MountGunner), client copy bClientIgnoreMovementCorrections %s '
                   '(BeginLocalGunner); want both true' % (fs.get('server_ignores_errors'), fc.get('client_ignores_corrections')))

    # ---- T5.3: the client aims L1 at the port wall
    def l1_target(self):
        m = self.muzzle_w(self.ship1_s, 'L1')
        return [m[0] + CANNON_PT_AHEAD, PORT_FACE_Y, m[2]]

    def start_g1_aim(self):
        self.D['P'] = self.l1_target()
        self.D['trk'] = []

    def ph_g1_aim(self, el):
        self.aim_pc('client', self.D['P'])
        a = self.anim(self.ship1_s, ['CannonYawDeg_L1', 'CannonElevDeg_L1'])
        b = self.anim(self.ship1_c, ['CannonYawDeg_L1', 'CannonElevDeg_L1'])
        self.D['trk'].append((r(el, 3), a.get('CannonYawDeg_L1'), a.get('CannonElevDeg_L1'), b.get('CannonYawDeg_L1'), b.get('CannonElevDeg_L1')))

    def end_g1_aim(self):
        trk = [x for x in self.D['trk'] if None not in x]
        win = [x for x in trk if x[0] >= 2.0]
        P = self.D['P']
        m = self.muzzle_w(self.ship1_s, 'L1')
        exp = math.degrees(math.atan2(abs(P[0] - m[0]), abs(P[1] - m[1])))
        res = {'target': r(P, 0), 'expected_abs_yaw': r(exp, 2)}
        ok = bool(win) and bool(trk)
        if ok:
            sy, se, cy, ce = [mean([x[k] for x in win]) for k in (1, 2, 3, 4)]
            y0 = trk[0][1]
            half = [x[0] for x in trk if abs(x[1] - y0) >= 0.5 * abs(sy - y0)] if abs(sy - y0) > 0.1 else []
            res.update({'server_yaw': r(sy, 2), 'server_elev': r(se, 2), 'client_yaw': r(cy, 2), 'client_elev': r(ce, 2), 'yaw_at_start': r(y0, 2),
                        'server_half_way_s': half[0] if half else None, 'yaw_diff': r(abs(sy - cy), 3), 'elev_diff': r(abs(se - ce), 3)})
            ok = abs(sy - cy) <= 1.0 and abs(se - ce) <= 1.0 and abs(abs(sy) - exp) <= 2.5
        self.check('T5.3_client_aim_L1_replicated', 'PASS' if ok else 'FAIL', 'client control rotation at the port wall %s: cannon L1 (anim) over the '
                   'last second: %s; want server and client within 1 deg (yaw and elevation) and |yaw| within 2.5 deg of the bearing from the '
                   'muzzle. StationAims itself is not readable from Python; yaw_at_start and server_half_way_s are reported, not judged' % (r(P, 0), res), res)

    # ---- T5.4 / T5.10: the client fires L1, again 0.5 s later; Board while mounted
    def start_g1_fire(self):
        self.D['P'] = self.l1_target()
        self.rec_start('L', (self.ship1_s, self.ship1_c), ['L1', 'L2'])

    def ph_g1_fire(self, el):
        self.aim_pc('client', self.D['P'])
        if el >= 0.5 and 'p1' not in self.D:
            self.D['p1'] = self.now
            self.mz_start('L1', (self.ship1_s, self.ship1_c), 0.8)
            self.inject('client', 'IA_AirshipFire')
            self.event('inject', what='IA_AirshipFire (client gunner L1)')
        if el >= 1.0 and 'p2' not in self.D:
            self.D['p2'] = self.now
            self.inject('client', 'IA_AirshipFire')
        if el >= 2.0 and 'board' not in self.D:
            self.D['board'] = True
            self.scmd('Aura.Airship.Board %d' % self.cidx)
        if el >= 2.6 and 'board_res' not in self.D:
            self.D['board_res'] = {'still_gunner_L1': same(self.gunner(self.ship1_s, 0), self.cchar_s), 'client_pawn_is_char': same(self.rpc.get_controlled_pawn(), self.cchar_s),
                                   'ship2_pilot': self.ship2_s.get_pilot().get_name() if valid(self.ship2_s) and self.ship2_s.get_pilot() else None}

    def end_g1_fire(self):
        p1, p2 = self.D.get('p1', 1e9), self.D.get('p2', 1e9)
        mL1, mL2 = self.muzzle_w(self.ship1_s, 'L1'), self.muzzle_w(self.ship1_s, 'L2')
        sb = self.new_balls('server', p1)
        s_l1 = [b for b in sb if dist(b['first'], mL1) <= 600.0]
        s_after = [b for b in sb if b['t0'] >= p2 - 0.05]
        cb = self.new_balls('client', p1)
        pk = {'L1': (self.peaks('L', 'server', 'L1'), self.peaks('L', 'client', 'L1')), 'L2': (self.peaks('L', 'server', 'L2'), self.peaks('L', 'client', 'L2'))}
        mz = self.mz_new('L1')
        ok = len(sb) == 1 and len(s_l1) == 1 and not s_after and len(cb) == 1 and pk['L1'][1] == 1 and pk['L1'][0] == 1 and not pk['L2'][1] \
            and (mz['server'] or 0) >= 1 and (mz['client'] or 0) >= 1
        self.check('T5.4_client_cannon_fire', 'PASS' if ok else 'FAIL', 'client LMB (IA_AirshipFire) at the wall, again 0.5 s later: server balls %d '
                   '(%d from L1, %d after the second press: want 1 / 1 / 0), client copies %d (want 1); recoil peaks L1 server / client %s (want 1 / 1: '
                   'the client\'s prediction and the multicast shown once), L2 %s (want 0); new muzzle FX server %s client %s (want >= 1 each)' % (
                       len(sb), len(s_l1), len(s_after), len(cb), pk['L1'], pk['L2'], mz['server'], mz['client']),
                   {'server_balls': sb, 'client_balls': cb, 'peaks': pk, 'muzzle_fx': mz})
        br = self.D.get('board_res') or {}
        ok2 = br.get('still_gunner_L1') and br.get('client_pawn_is_char') and not br.get('ship2_pilot')
        self.check('T5.10_board_refused_while_mounted_L', 'PASS' if ok2 else 'FAIL', 'Aura.Airship.Board %s while the client mans L1 (ship 2 is free): '
                   '%s (want still the gunner, its character, ship 2 without a pilot)' % (self.cidx, br))

    # ---- T5.5: the host's port broadside skips the manned L1
    def start_g1_broadside(self):
        self.D['P'] = self.l1_target()
        self.rec_start('B', (self.ship1_s, self.ship1_c), ['L1', 'L2'])

    def ph_g1_broadside(self, el):
        self.aim_pc('client', self.D['P'])
        if 'ft' not in self.D:
            self.look('host', self.yaw(self.ship1_s) - 90.0, -4.0)
        if el >= 1.5 and 'ft' not in self.D:
            self.D['ft'] = self.now
            self.D['nb0'] = len(self.balls['server'])
            self.inject('server', 'IA_AirshipFire')
            self.event('inject', what='IA_AirshipFire (host pilot, port)')
        ft = self.D.get('ft')
        if ft is not None and self.now - ft >= 0.6 and 'fb' not in self.D and len(self.balls['server']) == self.D['nb0']:
            self.D['fb'] = True
            self.ship1_s.request_fire()
            self.line('WARN', 'the host\'s fire injection made no ball in 0.6 s: fallback RequestFire')

    def end_g1_broadside(self):
        ft = self.D.get('ft', 1e9)
        sb = self.new_balls('server', ft)
        near1 = [b for b in sb if dist(b['first'], self.muzzle_w(self.ship1_s, 'L1')) <= 600.0]
        near2 = [b for b in sb if dist(b['first'], self.muzzle_w(self.ship1_s, 'L2')) <= 600.0]
        pk = {'L1': (self.peaks('B', 'server', 'L1'), self.peaks('B', 'client', 'L1')), 'L2': (self.peaks('B', 'server', 'L2'), self.peaks('B', 'client', 'L2'))}
        ok = len(sb) == 1 and len(near2) == 1 and not near1 and not pk['L1'][0] and not pk['L1'][1] and pk['L2'][0] == 1 and pk['L2'][1] == 1 and not self.D.get('fb')
        self.check('T5.5_broadside_skips_manned_L1', 'PASS' if ok else 'FAIL', 'host pilot fires the port broadside with L1 manned by the client: '
                   'server balls %d (from L2 %d, from L1 %d: want 1 / 1 / 0); recoil peaks server / client L1 %s (want 0 / 0) L2 %s (want 1 / 1)%s' % (
                       len(sb), len(near2), len(near1), pk['L1'], pk['L2'], ' FALLBACK RequestFire' if self.D.get('fb') else ''), {'balls': sb, 'peaks': pk})

    # ---- T5.8: the client's F leaves L1, then it walks
    def start_g1_exit(self):
        self.D['modes'] = {'server': [], 'client': []}

    def ph_g1_exit(self, el):
        s = self.ship1_s
        if el >= 0.3 and 'f' not in self.D:
            self.D['f'] = el
            self.inject('client', 'IA_AirshipExit')
            self.event('inject', what='IA_AirshipExit (client gunner)')
        if 'f' in self.D and 'srv_t' not in self.D and self.gunner(s, 0) is None:
            self.D['srv_t'] = el
        if el >= 1.5 and 'fb' not in self.D and same(self.gunner(s, 0), self.cchar_s):
            self.D['fb'] = True
            self.scmd('Aura.Airship.Dismount %d' % self.cidx)
            self.line('WARN', 'the client\'s F did not leave L1 in 1.2 s: fallback Aura.Airship.Dismount (the client is not told)')
        if 'f' in self.D:
            for key, c in (('server', self.cchar_s), ('client', self.cchar_c)):
                cm = gp(c, 'character_movement', 'CharacterMovement')
                if cm:
                    md = en(cm.get_editor_property('movement_mode'))
                    if not self.D['modes'][key] or self.D['modes'][key][-1] != md:
                        self.D['modes'][key].append(md)
        if el >= 2.0 and 'snap' not in self.D:
            self.D['snap'] = {'server': self.char_info(self.cchar_s, s), 'client': self.char_info(self.cchar_c, self.ship1_c), 'imc': self.imc_on(self.sub_c)}
        if el >= 2.1 and 'p0' not in self.D:
            self.D['p0'] = (self.loc(self.cchar_s), self.loc(self.cchar_c))
        if 2.2 <= el < 3.2:
            self.look('client', self.yaw(s), -8.0)
            self.inject('client', 'IA_Move', (1.0, 0.0, 0.0))
        if el >= 3.6 and 'p1' not in self.D:
            self.D['p1'] = (self.loc(self.cchar_s), self.loc(self.cchar_c), self.char_info(self.cchar_s, s), self.char_info(self.cchar_c, self.ship1_c))

    def end_g1_exit(self):
        sn = self.D.get('snap') or {}
        sv, cl = sn.get('server') or {}, sn.get('client') or {}
        p0, p1 = self.D.get('p0'), self.D.get('p1')
        mv = (r(hdist(p0[0], p1[0]), 1), r(hdist(p0[1], p1[1]), 1)) if p0 and p1 else (None, None)
        fin = (p1[2] or {}, p1[3] or {}) if p1 else ({}, {})
        mods = self.D['modes']
        ok = (self.gunner(self.ship1_s, 0) is None and not self.D.get('fb') and sv.get('att') is None and cl.get('att') is None and cl.get('cmc_tick') is True
              and sn.get('imc') is False and all(set(mods[k]) <= set(['MOVE_FALLING', 'MOVE_WALKING', 'MOVE_NONE']) and mods[k] and mods[k][-1] == 'MOVE_WALKING' for k in mods)
              and mv[0] is not None and mv[0] >= 100.0 and mv[1] >= 100.0 and fin[1].get('mode') == 'MOVE_WALKING')
        self.check('T5.8_client_F_dismount_L', 'PASS' if ok else 'FAIL', 'client F (IA_AirshipExit) on L1%s: station free on the server %.2f s after F; '
                   'at +1.7 s server copy %s, client copy %s, IMC_Airship on the client %s (want off); movement modes seen server %s client %s (want '
                   'falling / walking, last walking); W for 1 s moved server %s cm client %s cm (want >= 100)' % (
                       ' FALLBACK RequestDismount' if self.D.get('fb') else '', (self.D.get('srv_t') or -1) - (self.D.get('f') or 0), sv, cl, sn.get('imc'),
                       mods['server'], mods['client'], mv[0], mv[1]), {'snap': sn, 'final': fin, 'modes': mods})

    # ---- T5.6 + turret aim: the client on turret L
    def turret_target(self):
        t = self.turret(self.ship1_s, 0)
        pv = self.world_of(self.ship1_s, self.turret_pivot_local(t, 0))
        return [pv[0] + TURRET_PT_SIDE, PORT_FACE_Y, pv[2]]

    def start_g1_turret(self):
        # F 1.5 m behind turret L's seat (nearest: the seat, 3.5 m mount range; the other seats and the helm are farther).
        # Aura.Airship.Mount from Python would mount the server's copy only (the script guard keeps ClientMountChanged local)
        s = self.ship1_s
        seat = self.seat_local(s, 4)
        p, traced = self.deck_point(s, seat[0] - 150.0, seat[1], self.cchar_s)
        self.D['mpt'] = {'hull': r(self.rel(s, p), 0), 'traced': traced, 'seat': r(seat, 0)}
        self.tp_client(p, self.yaw(s))
        self.D['Q'] = self.turret_target()
        self.D['aims'], self.D['heat'], self.D['fx'] = [], [], {'server': False, 'client': False}

    def ph_g1_turret(self, el):
        ts, tc = self.turret(self.ship1_s, 0), self.turret(self.ship1_c, 0)
        if el >= 0.3 and 'f' not in self.D:
            self.D['f'] = el
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client, behind turret L)')
        if el >= 0.4:
            self.aim_pc('client', self.D['Q'])
        if el >= 0.9 and 'm' not in self.D:
            self.D['m'] = {'gunner': same(self.gunner(self.ship1_s, 4), self.cchar_s), 'att_client': (self.char_info(self.cchar_c, self.ship1_c) or {}).get('att'),
                           'client_cmc_tick': (self.char_info(self.cchar_c) or {}).get('cmc_tick'), 'imc': self.imc_on(self.sub_c), 'pt': self.D.get('mpt')}
            if not self.D['m']['gunner']:
                self.D['fb'] = True
                self.scmd('Aura.Airship.Mount %d 4' % self.cidx)
                self.line('WARN', 'the client\'s F did not man turret L in 0.6 s: fallback Aura.Airship.Mount (the client is not told)')
        if 1.4 <= el < 1.9:
            a, b = self.tstate(ts), self.tstate(tc)
            vh = self.view_hit(self.cw, self.own_ignores(self.ship1_c) + [x for x in (self.cchar_c, self.hchar_c) if valid(x)])
            self.D['aims'].append((a.get('yaw'), a.get('pitch'), b.get('yaw'), b.get('pitch'), vh))
        if el >= 1.95 and 's0' not in self.D:
            self.D['s0'] = (self.shots(ts), self.shots(tc))
        if 2.0 <= el < 3.0:
            self.inject('client', 'IA_AirshipFire')
        if 2.0 <= el < 3.4:
            self.D['heat'].append(self.tstate(ts).get('heat'))
        if 2.1 <= el < 3.2:
            self.D['fx']['server'] = self.D['fx']['server'] or bool(self.comp_active(ts, 'MuzzleFXComponent'))
            self.D['fx']['client'] = self.D['fx']['client'] or bool(self.comp_active(tc, 'MuzzleFXComponent'))
        if el >= 2.5 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture(self.cw, 'g1_turret', 'player')
        if el >= 4.5 and 's1' not in self.D:
            self.D['s1'] = (self.shots(ts), self.shots(tc))

    def end_g1_turret(self):
        ts = self.turret(self.ship1_s, 0)
        m = self.D.get('m') or {}
        s0, s1 = self.D.get('s0') or (0, 0), self.D.get('s1') or (0, 0)
        ds, dc = s1[0] - s0[0], s1[1] - s0[1]
        hv = [h for h in self.D['heat'] if isinstance(h, (int, float))]
        hmax = max(hv) if hv else None
        ok = m.get('gunner') and not self.D.get('fb') and m.get('att_client') == self.ship1_c.get_name() and m.get('client_cmc_tick') is False \
            and 9 <= ds <= 11 and 9 <= dc <= 11 and hmax is not None and 0.25 <= hmax <= 0.42 and self.D['fx']['server'] and self.D['fx']['client']
        self.check('T5.6_client_turret_burst', 'PASS' if ok else 'FAIL', 'client F behind turret L %s%s (client gunner %s, attached on the client to %s, '
                   'its CMC ticking %s (want off: BeginLocalGunner ran there), IMC_Airship %s); client LMB held 1.0 s at the port wall: server shots %d '
                   '(want 9-11), client tracers %d (want 9-11: its predicted rounds, the multicast skipped while it predicts), server heat max %s (want '
                   '~0.33), muzzle flash server %s client %s' % (
                       self.D.get('mpt'), ' FALLBACK console Mount' if self.D.get('fb') else '', m.get('gunner'), m.get('att_client'), m.get('client_cmc_tick'),
                       m.get('imc'), ds, dc, r(hmax, 3) if hmax is not None else None, self.D['fx']['server'], self.D['fx']['client']))
        res = self.turret_aim_eval(self.ship1_s, ts, 0, self.D['aims'], self.D['Q'])
        self.check('T5.3_client_aim_turret_replicated', 'PASS' if res.get('ok') else 'FAIL', 'client gunner on turret L aims at the port wall: turret '
                   'GetAimYawDeg / GetAimPitchDeg %s; want the server within 3 deg of the bearing from the pivot to where the client\'s view ray '
                   'meets the wall (what ComputeGunnerAim traces; the bearing to the harness\'s target point is reported) and the client copy within '
                   '2 deg of the server' % res, res)

    def turret_aim_eval(self, ship, t, i, aims, target):
        """the turret's yaw / pitch (server, client) over the window vs the bearing from its pivot to the aiming machine's
        view-ray hit (mean over the window), and to the harness's target point (reported only)"""
        rows = [x for x in aims if None not in x[:4]]
        vh = [x[4] for x in rows if x[4] is not None]
        res = {'target': r(target, 0) if target else None, 'frames': len(rows), 'view_hits': len(vh)}
        if not rows or not t or not vh:
            res['ok'] = False
            return res
        vm = [mean([v[k] for v in vh]) for k in range(3)]
        ey, ep = self.turret_expected_aim(ship, t, i, vm)
        ty, tp = self.turret_expected_aim(ship, t, i, target) if target else (None, None)
        sy, sp, cy, cp = [mean([x[k] for x in rows]) for k in range(4)]
        res.update({'view_hit': r(vm, 0), 'expected_view_ray': (r(ey, 2), r(ep, 2)), 'expected_target': (r(ty, 2), r(tp, 2)),
                    'view_hit_from_target_cm': r(dist(vm, target), 0) if target else None, 'server': (r(sy, 2), r(sp, 2)), 'client': (r(cy, 2), r(cp, 2))})
        res['ok'] = abs(sy - ey) <= 3.0 and abs(sp - ep) <= 3.0 and abs(sy - cy) <= 2.0 and abs(sp - cp) <= 2.0
        return res

    # ---- T5.7: overheat with a client gunner (server and predicted rounds)
    def start_g1_overheat(self):
        self.D['Q'] = self.turret_target()
        self.D['trk'] = []

    def ph_g1_overheat(self, el):
        ts, tc = self.turret(self.ship1_s, 0), self.turret(self.ship1_c, 0)
        self.aim_pc('client', self.D['Q'])
        if 0.5 <= el < 4.0:
            self.inject('client', 'IA_AirshipFire')
        a, b = self.tstate(ts), self.tstate(tc)
        self.D['trk'].append((r(el, 3), a.get('shots'), a.get('heat'), a.get('overheated'), b.get('shots'), b.get('heat'), b.get('overheated')))

    def end_g1_overheat(self):
        trk = [x for x in self.D['trk'] if x[0] >= 0.5]
        t_oh = next((x[0] for x in trk if x[3]), None)
        t_rec = next((x[0] for x in trk if t_oh is not None and x[0] > t_oh and not x[3]), None)
        win = [x for x in trk if t_oh is not None and t_oh <= x[0] <= (t_rec if t_rec is not None else 1e9)]
        s_oh = (win[-1][1] - win[0][1]) if len(win) > 1 and win[0][1] is not None and win[-1][1] is not None else None
        heat_rec = next((x[2] for x in trk if t_rec is not None and x[0] >= t_rec), None)
        c_oh_t = next((x[0] for x in trk if x[6]), None)
        cwin = [x for x in trk if c_oh_t is not None and x[6] and x[0] >= c_oh_t]
        c_oh = (cwin[-1][4] - cwin[0][4]) if len(cwin) > 1 and cwin[0][4] is not None and cwin[-1][4] is not None else None
        ok = (t_oh is not None and 2.6 <= t_oh - 0.5 <= 3.4 and s_oh == 0 and t_rec is not None and heat_rec is not None and heat_rec <= 0.36
              and c_oh_t is not None and c_oh == 0)
        self.check('T5.7_overheat_client_gunner', 'PASS' if ok else 'FAIL', 'client LMB held 3.5 s: server overheat %s s into the hold (want ~3), '
                   'server shots while overheated %s (want 0), recovered at %s s (heat %s, want <= 0.35); the client copy reads overheated from %s s '
                   '(%s s after the server), its predicted rounds while it reads it %s (want 0)' % (
                       r(t_oh - 0.5, 2) if t_oh is not None else None, s_oh, t_rec, heat_rec, c_oh_t,
                       r(c_oh_t - t_oh, 2) if c_oh_t is not None and t_oh is not None else None, c_oh), {'track': trk[::4]})

    # ---- T6.6: turret L wrecked with the client on it
    def start_g1_wreck(self):
        ts = self.turret(self.ship1_s, 0)
        self.D['t'] = ts
        h = self.tstate(ts).get('health')
        self.D['h'] = h if isinstance(h, (int, float)) else 400.0
        # Only this turret: a sentinel test bullet (its health + 10) from 25 m outboard at its HitBox, the Mesh collision off
        # (as as_59 T3.2: the hull hit goes to the turret behind it). The hit lands in the swarm's tick, so the wreck's
        # eject sends ClientMountChanged to the client gunner; a GE applied from Python (or Aura.Airship.TurretDamage, which
        # also wrecks that turret of EVERY ship) would run under the editor script guard and the client would only let go
        # through its own safety net a second later.
        m = self.ship1_s.get_editor_property('Mesh')
        self.D['mesh_coll'] = m.get_collision_enabled()
        m.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        to = v3(ts.get_editor_property('HitBox').get_world_location())
        rg = self.rgt(self.ship1_s)
        frm = [to[k] - rg[k] * 2500.0 for k in range(3)]
        self.D['line'] = self.trace(self.sw, frm, to)
        self.bullet(frm, to, '%.0f' % (self.D['h'] + 10.0))
        self.D['t_hurt'] = self.now
        self.D['trk'] = []

    def ph_g1_wreck(self, el):
        s, c = self.ship1_s, self.ship1_c
        ts, tc = self.turret(s, 0), self.turret(c, 0)
        a, b = self.tstate(ts), self.tstate(tc)
        if 'ds' not in self.D and a.get('destroyed'):
            self.D['ds'] = el
        if 'dc' not in self.D and b.get('destroyed'):
            self.D['dc'] = el
        if el >= 0.8 and 'mesh_back' not in self.D:
            self.D['mesh_back'] = True
            s.get_editor_property('Mesh').set_collision_enabled(self.D['mesh_coll'])
            if 'ds' not in self.D:
                self.D['fb'] = True
                self.hurt(ts, self.D['h'] + 10.0)
                self.line('WARN', 'the test bullet did not wreck turret L in 0.8 s (first hit on its line %s): fallback GE from Python '
                                  '(the eject\'s ClientMountChanged stays local: the client lets go by its safety net)' % self.D.get('line'))
        if el >= 1.3 and 'snap' not in self.D:
            self.D['snap'] = {'server': a, 'client': b, 'fire_fx_client': self.comp_active(tc, 'DestroyedFXComponent'),
                              'fire_fx_server': self.comp_active(ts, 'DestroyedFXComponent'), 'station4': self.gunner(s, 4),
                              'client_char_server': self.char_info(self.cchar_s, s), 'client_char_client': self.char_info(self.cchar_c, c),
                              'imc': self.imc_on(self.sub_c)}
            self.D['s0'] = (self.shots(ts), self.shots(self.turret(s, 1)), self.shots(self.turret(c, 1)))
            self.capture(self.cw, 'g1_wreck', 'bow', c)
        if el >= 1.5 and 'on' not in self.D:
            self.D['on'] = True
            q = self.world_of(s, (2100.0 + 10000.0, 0.0, 805.0))
            self.turret_fire_on = True
            self.scmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(q))
        if el >= 2.5 and 'off' not in self.D:
            self.D['off'] = True
            self.scmd('Aura.Airship.TurretFire 0')
            self.turret_fire_on = False
        if el >= 3.8 and 's1' not in self.D:
            self.D['s1'] = (self.shots(ts), self.shots(self.turret(s, 1)), self.shots(self.turret(c, 1)))

    def end_g1_wreck(self):
        if 'mesh_back' not in self.D and 'mesh_coll' in self.D:
            self.ship1_s.get_editor_property('Mesh').set_collision_enabled(self.D['mesh_coll'])
        sn = self.D.get('snap') or {}
        s0, s1 = self.D.get('s0') or (0, 0, 0), self.D.get('s1') or (0, 0, 0)
        d = [s1[i] - s0[i] for i in range(3)]
        cs, cc = sn.get('client_char_server') or {}, sn.get('client_char_client') or {}
        ok = (not self.D.get('fb') and (sn.get('server') or {}).get('destroyed') and (sn.get('client') or {}).get('destroyed') and sn.get('fire_fx_client') and sn.get('station4') is None
              and cs.get('att') is None and cc.get('att') is None and sn.get('imc') is False and d[0] == 0 and d[1] > 0 and d[2] > 0)
        self.check('T6.6_turret_wreck_client_gunner', 'PASS' if ok else 'FAIL', 'turret L of ship 1 to 0 health (a %.0f test bullet at its HitBox%s, '
                   'first hit on the line %s) with the client on it: destroyed on the server %s (at %s s), on the client %s (at %s s, OnRep), fire FX client %s server %s; station 4 %s (want free); '
                   'client character server att %s / client att %s (want detached: ejected), IMC_Airship on the client %s (want off); TurretFire 1 '
                   'for 1 s after: shots turret L %d (want 0), turret R server %d / client tracers %d (want > 0)' % (
                       self.D.get('h', 400.0) + 10.0, ' FALLBACK GE from Python' if self.D.get('fb') else '', (self.D.get('line') or {}).get('actor'),
                       (sn.get('server') or {}).get('destroyed'), self.D.get('ds'), (sn.get('client') or {}).get('destroyed'), self.D.get('dc'),
                       sn.get('fire_fx_client'), sn.get('fire_fx_server'), sn.get('station4'), cs.get('att'), cc.get('att'), sn.get('imc'), d[0], d[1], d[2]),
                   {'snap': dict((k, v) for k, v in sn.items() if k != 'station4')})

    # ================================================================ g2_: T5.13, a mount while walking, then a lagged cruise
    def lag(self, on):
        for w in (self.cw, self.sw):
            if w is None:
                continue
            if on:
                lag = self.cfg['lag_ms']
                fps = self.fps_prev or self.R['mp'].get('real_fps_settle') or 30.0
                n = int(round(max(lag, min(10.0 * lag, lag * FIXED_FPS / max(1.0, fps)))))
                self.R['mp']['pktlag'] = {'game_ms': lag, 'pktlag_real_ms': n, 'real_fps': r(fps, 1)}
                self.cmd(w, 'Net PktLag=%d' % n)
            else:
                self.cmd(w, 'Net PktLag=0')
        self.lag_on = on

    def start_g2_walk(self):
        self.ensure_roles('pilot1', 'foot')
        if hdist(self.loc(self.ship1_s), SPAWN) > 5000.0:
            self.tship(self.ship1_s, SPAWN, 0.0)
        self.set_scheme(self.ship1_s, self.cfg['aim_scheme'])
        self.look('host', self.yaw(self.ship1_s), -8.0)
        # the walker goes onto the planks before the lag starts (no lagged moves from before the teleport)
        s = self.ship1_s
        seat = self.seat_local(s, 0)
        inb = 60.0 if seat[1] < 0 else -60.0
        p, traced = self.deck_point(s, seat[0] - 250.0, seat[1] + inb, self.cchar_s)
        self.D['ap'] = {'hull': r(self.rel(s, p), 0), 'traced': traced}
        self.tp_client(p, self.yaw(s))
        self.cmd(self.sw, 'log LogAirshipPilot Verbose')
        self.verbose_pilot = True

    def ph_g2_walk(self, el):
        s = self.ship1_s
        if el >= 0.3 and 'lag' not in self.D:
            self.D['lag'] = True
            if self.cfg['lag_ms'] > 0:
                self.lag(True)
        if el >= 1.5 and ('m_t' not in self.D or el < self.D['m_t'] + 0.7):
            self.look('client', self.yaw(s), -8.0)
            self.inject('client', 'IA_Move', (1.0, 0.0, 0.0))
        if el >= 2.0 and 'f' not in self.D:
            self.D['f'] = el
            v = v3(self.cchar_c.get_velocity())
            self.D['v_at_f'] = r(math.hypot(v[0], v[1]), 1)
            self.D['info_at_f'] = self.char_info(self.cchar_c, self.ship1_c)
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client, walking)')
        if 'f' in self.D and 'm_t' not in self.D and same(self.gunner(s, 0), self.cchar_s):
            self.D['m_t'] = el
            self.log_mark('g2_mounted')
            self.line('INFO', 'the walking client manned L1 %.2f s after F' % (el - self.D['f']))
        if el >= 3.5 and 'm_t' not in self.D and 'fb' not in self.D:
            self.D['fb'] = True
            self.scmd('Aura.Airship.Mount %d 0' % self.cidx)
            self.line('WARN', 'F did not man L1 in 1.5 s: fallback Aura.Airship.Mount (T5.13 then tests a console mount, not a walking F)')

    def end_g2_walk(self):
        if 'm_t' not in self.D and same(self.gunner(self.ship1_s, 0), self.cchar_s):
            self.D['m_t'] = self.now - self.p_t0
            self.log_mark('g2_mounted')
        self.carry['t513'] = {'walk': dict((k, v) for k, v in self.D.items() if k in ('ap', 'f', 'm_t', 'fb', 'v_at_f', 'info_at_f')),
                              'pktlag': self.R['mp'].get('pktlag'), 'client_name': self.cchar_c.get_name(), 'server_name': self.cchar_s.get_name()}

    def start_g2_cruise(self):
        self.D['trk'] = []

    def ph_g2_cruise(self, el):
        s, c = self.ship1_s, self.ship1_c
        self.look('host', self.yaw(s), -8.0)
        if el >= 0.3 and 'thr' not in self.D:
            self.D['thr'] = True
            s.debug_set_input(self.cfg['cruise_throttle'], 0.0, 0.0, 0.0, False, False)
            self.event('host_input', input='throttle %.2f' % self.cfg['cruise_throttle'])
        v = fnum(self.tele(s).get('ForwardSpeedMS'), 0.0)
        if 'w0' not in self.D and el >= 1.0 and (v >= 30.0 or el >= 7.0):
            self.D['w0'] = el
            self.line('INFO', 'T5.13 window starts at %.1f m/s' % v)
        w0 = self.D.get('w0')
        if w0 is not None and el <= w0 + 10.0:
            try:
                pc_, ps_ = self.loc(self.cchar_c), self.loc(self.cchar_s)
                cam, _ = self.cam(self.cw)
                par = self.cchar_c.get_attach_parent_actor()
                self.D['trk'].append({'el': r(el, 3), 'v': r(v, 2), 'vc': r(fnum(self.tele(c).get('ForwardSpeedMS')), 2),
                                      'rel_c': r(self.rel(c, pc_), 2), 'rel_s': r(self.rel(s, ps_), 2),
                                      'exp_c': r(self.seat_rel_expected(c, 0, self.cchar_c), 2), 'att_c': par.get_name() if par else None,
                                      'cam_rel': r(self.rel(c, cam), 1), 'cam_d': r(dist(cam, pc_), 1),
                                      'gunner': same(self.gunner(s, 0), self.cchar_s)})
            except Exception:  # noqa: BLE001
                self.err('t513_sample')
        if w0 is not None and el >= w0 + 10.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture(self.cw, 'g2_cruise', 'player')

    def end_g2_cruise(self):
        t = self.carry.setdefault('t513', {})
        t['trk'] = self.D['trk']
        t['w0'] = self.D.get('w0')
        t['flags'] = {'server': self.cm_flags(self.cchar_s), 'client': self.cm_flags(self.cchar_c)}
        self.eval_t513(final=False)

    def start_g2_end(self):
        self.ship1_s.debug_set_input(*BRAKE)
        if self.lag_on:
            self.lag(False)
        self.cmd(self.sw, 'log LogAirshipPilot Log')
        self.verbose_pilot = False

    def ph_g2_end(self, el):
        if el >= 3.5 and 'clr' not in self.D:
            self.D['clr'] = True
            self.ship1_s.debug_clear_input()

    def eval_t513(self, final):
        t = self.carry.get('t513') or {}
        trk = t.get('trk') or []
        wk = t.get('walk') or {}
        dev = [dist(x['rel_c'], x['rel_s']) for x in trk]
        dexp = [dist(x['rel_c'], x['exp_c']) for x in trk]
        att_ok = bool(trk) and all(x['att_c'] == (self.ship1_c.get_name() if valid(self.ship1_c) else None) for x in trk)
        gun_ok = bool(trk) and all(x['gunner'] for x in trk)
        vv = [x['v'] for x in trk if x['v'] is not None]
        jumps = [dist(trk[i]['cam_rel'], trk[i - 1]['cam_rel']) for i in range(1, len(trk))]
        cd = [x['cam_d'] for x in trk]
        span = (max(cd) - min(cd)) if cd else None
        res = {'frames': len(trk), 'window_s': r((trk[-1]['el'] - trk[0]['el']) if trk else 0, 2), 'speed_ms': stats(vv),
               'client_vs_server_seat_cm': stats(dev), 'client_vs_expected_seat_cm': stats(dexp), 'attached_all': att_ok, 'gunner_all': gun_ok,
               'camera_jump_cm': stats(jumps), 'camera_dist_cm': stats(cd), 'camera_dist_span_cm': r(span, 1) if span is not None else None,
               'walk': wk, 'pktlag': t.get('pktlag'), 'flags_end_of_window': t.get('flags')}
        moving = wk.get('v_at_f') is not None and wk['v_at_f'] >= 50.0 and not wk.get('fb')
        ok_pos = bool(trk) and len(trk) >= 250 and mean(vv) is not None and mean(vv) >= 28.0 and att_ok and gun_ok and max(dev) <= 5.0
        ok_cam = bool(jumps) and max(jumps) <= 50.0 and span is not None and span <= 500.0
        if final:
            seg = self.log_between('g2_mounted', 'g2_end') if any(m[0] == 'g2_mounted' for m in self.log_marks) else None
            cname, sname = t.get('client_name'), t.get('server_name')
            if seg is not None:
                lines = seg.splitlines()
                corr = [l for l in lines if '*** Client: Error for %s ' % cname in l]
                ign = [l for l in lines if '*** Server: %s is set to ignore error checks' % sname in l]
                back = [l for l in lines if 'back on the seat of station' in l and cname in l]
                res['log'] = {'client_corrections': len(corr), 'server_ignored_moves': len(ign), 'back_on_seat': len(back),
                              'samples': (corr[:3] + back[:3])}
                rare = max(3, int(0.02 * max(1, len(trk))))
                ok_log = len(corr) == 0 and len(back) <= rare
                res['log']['back_on_seat_limit'] = rare
            else:
                ok_log = False
                res['log'] = 'no log segment from the mount to g2_end (no mount, or the log was not found)'
        else:
            ok_log = True
            res['log'] = 'pending (read at the end of the run)'
        ok = moving and ok_pos and ok_cam and ok_log
        self.check('T5.13_gunner_seat_lag', ('PASS' if ok else 'FAIL') if final else ('INFO' if ok else 'FAIL'),
                   'client walking %s cm/s when F %s manned L1 (%s), then the host flew ship 1 at %s m/s with Net PktLag %s on both worlds: the '
                   'client\'s own copy vs the seat, hull space on the client: %s cm vs the server copy, %s cm vs seat + half height + clearance '
                   '(want max <= 5), attached to its ship copy every frame %s; the client camera frame-to-frame (hull space) %s cm (want max <= 50: '
                   'no snap) and its distance to the gunner span %s cm (want <= 500); log after the mount %s (want 0 client corrections, "back on '
                   'the seat" rare: at most 2 %% of the frames, 3 minimum; the server\'s "set to ignore error checks" lines show the fix acked moves '
                   'in flight)%s' % (
                       wk.get('v_at_f'), 'FALLBACK console Mount' if wk.get('fb') else 'injected',
                       r(wk.get('m_t') - wk.get('f'), 2) if wk.get('m_t') is not None and wk.get('f') is not None else None,
                       res['speed_ms'], t.get('pktlag'), res['client_vs_server_seat_cm'], res['client_vs_expected_seat_cm'], att_ok, res['camera_jump_cm'],
                       res['camera_dist_span_cm'], res['log'], '' if final else ' [provisional: the log part is read at the end]'),
                   dict(res, track=trk[::10]))

    def finalize_t513(self):
        if (self.carry.get('t513') or {}).get('trk') is not None:
            try:
                self.eval_t513(final=True)
            except Exception:  # noqa: BLE001
                self.err('finalize_t513')

    # ---- T4.1: host pilot + client gunner take the crew share
    def start_g2_crew(self):
        if not same(self.ship1_s.get_pilot(), self.hchar):
            self.ensure_roles('pilot1', 'foot')
        if not same(self.gunner(self.ship1_s, 0), self.cchar_s):
            self.scmd('Aura.Airship.Mount %d 0' % self.cidx)

    def crew_h(self, ship_s, ship_c):
        return {'host': self.health(self.hchar), 'client_s': self.health(self.cchar_s), 'client_c': self.health(self.cchar_c),
                'ship_s': self.ship_hp(ship_s), 'ship_c': self.ship_hp(ship_c)}

    def ph_g2_crew(self, el):
        if el >= 0.5 and 'h0' not in self.D:
            self.D['roles'] = {'pilot': same(self.ship1_s.get_pilot(), self.hchar), 'gunner_L1': same(self.gunner(self.ship1_s, 0), self.cchar_s)}
            self.D['h0'] = self.crew_h(self.ship1_s, self.ship1_c)
            self.scmd('Aura.Airship.Damage 100')
        if el >= 1.5 and 'h1' not in self.D:
            self.D['h1'] = self.crew_h(self.ship1_s, self.ship1_c)

    def drops(self, h0, h1):
        return dict((k, r(h0[k] - h1[k], 3) if h0.get(k) is not None and h1.get(k) is not None else None) for k in h0)

    def end_g2_crew(self):
        h0, h1 = self.D.get('h0') or {}, self.D.get('h1') or {}
        dr = self.drops(h0, h1)
        want = 100.0 * self.share
        ok = (self.D.get('roles') or {}).get('pilot') and (self.D.get('roles') or {}).get('gunner_L1') and \
            all(dr.get(k) is not None and abs(dr[k] - want) <= 0.5 for k in ('host', 'client_s', 'client_c')) and dr.get('ship_s') is not None and abs(dr['ship_s'] - 100.0) < 0.5
        self.check('T4.1_crew_share_host_pilot_client_gunner', 'PASS' if ok else 'FAIL', 'Aura.Airship.Damage 100 with the host at the helm and the '
                   'client on L1 (%s): drops %s (want host pilot, the client gunner on the server and in its own view each %.1f +-0.5 = %.2f x 100; '
                   'ship 100); before %s' % (self.D.get('roles'), dr, want, self.share, h0), {'before': h0, 'after': h1})

    # ================================================================ g3_: client pilot of ship 2, host gunner
    def start_g3_swap(self):
        self.D['h_pre'] = self.health(self.hchar)
        self.D['host_was_pilot'] = valid(self.ship1_s) and same(self.ship1_s.get_pilot(), self.hchar)
        cw = self.where(self.cchar_s)
        self.far_res = None
        if not (cw[0] == 'pilot' and same(cw[1], self.ship2_s)):
            self.client_to('pilot2', far_first=True)

    def ph_g3_swap(self, el):
        if el >= 1.0 and 'x' not in self.D:
            self.D['x'] = True
            hw = self.where(self.hchar)
            if hw[0] == 'pilot':
                self.scmd('Aura.Airship.Exit 0')
            elif hw[0] == 'station':
                self.scmd('Aura.Airship.Dismount 0')
        if el >= 2.0 and 'h_post' not in self.D:
            self.D['h_post'] = self.health(self.hchar)
            self.D['host_on_foot'] = same(self.hpc.get_controlled_pawn(), self.hchar)
            self.tp_host(CHAR_FOOT, 0.0)
        if el >= 2.4 and 'placed' not in self.D:
            self.D['placed'] = True
            p2, f2 = self.loc(self.ship2_s), self.fwd(self.ship2_s)
            self.tship(self.ship1_s, [p2[k] + f2[k] * T6_AHEAD for k in range(3)], self.yaw(self.ship2_s))
            self.set_scheme(self.ship2_s, self.cfg['aim_scheme'])
            self.look('client', self.yaw(self.ship2_s), -8.0)

    def end_g3_swap(self):
        self.line('INFO', 'g3_swap client steps %s' % ((self.croles or {}).get('steps')))
        ok = same(self.ship2_s.get_pilot(), self.cchar_s) and same(self.cpc.get_controlled_pawn(), self.ship2_c) and same(self.hpc.get_controlled_pawn(), self.hchar)
        self.check('g3_setup_client_pilot', 'PASS' if ok else 'FAIL', 'the client flies ship 2 (server pilot %s, client pawn is its ship copy %s), the '
                   'host on foot %s; ship 1 parked %.0f m ahead; ship 2 scheme %s' % (
                       self.ship2_s.get_pilot().get_name() if self.ship2_s.get_pilot() else None, same(self.cpc.get_controlled_pawn(), self.ship2_c),
                       same(self.hpc.get_controlled_pawn(), self.hchar), T6_AHEAD / 100.0, SCHEME_NAMES.get(self.cfg['aim_scheme'])))
        # T8.2 L (Talal 11-25: "only be able to drive once close enough to grab the steering wheel"): the client's F on the
        # planks 2.5 m behind the wheel of the free ship 2 goes to the server (ServerRequestBoard -> TryUseNearest ->
        # AAirshipPawn::IsWithinHelmReach on the server's copy) and does nothing; the F at the wheel right after it is
        # g3_setup_client_pilot above.
        fr = getattr(self, 'far_res', None)
        if fr is None:
            self.check('T8.2_client_F_away_from_wheel_L', 'SKIP', 'the client was ship 2\'s pilot already at the start of g3_swap (AS60_ONLY run)')
        else:
            pt, af, at = fr.get('point') or {}, fr.get('after') or {}, (fr.get('at_F') or {})
            refused = (self.log_between('g3_far_F', None) or '').count('F refused')
            ok_far = (fr.get('free_helm') and pt.get('traced') and (pt.get('seat_h_cm') or 0) > (pt.get('helm_reach') or 1e9)
                      and (pt.get('min_gun_seat_cm') or 0) > (pt.get('station_mount_distance') or 1e9)
                      and (at.get('server') or {}).get('mode') == 'MOVE_WALKING' and bool(af) and af.get('pilot') is None and not af.get('client_sees_pilot')
                      and af.get('client_pawn_is_char') and all(x is None for x in af.get('stations') or [0])
                      and (af.get('server') or {}).get('att') is None and (af.get('client') or {}).get('att') is None and ok)
            self.check('T8.2_client_F_away_from_wheel_L', 'PASS' if ok_far else 'FAIL', 'the client on ship 2\'s planks %s cm behind the wheel hub (hull xy %s, '
                       'deck traced %s, %s cm from the pilot\'s standing spot: HelmReach %s; nearest gun seat %s cm: StationMountDistance %s; ship 2 '
                       'without a pilot %s; server copy at F %s), F (IA_AirshipBoard on the client): 0.8 s later ship 2\'s pilot %s (want none), the '
                       'client sees a pilot %s, its pawn still its character %s, stations %s (want none), attached server / client %s / %s (want '
                       'none); "F refused" in the server log since that F: %s; then F at the wheel takes the helm: %s (g3_setup_client_pilot)' % (
                           pt.get('wheel_h_cm'), pt.get('hull_xy'), pt.get('traced'), pt.get('seat_h_cm'), pt.get('helm_reach'), pt.get('min_gun_seat_cm'),
                           pt.get('station_mount_distance'), fr.get('free_helm'), dict((k, (at.get('server') or {}).get(k)) for k in ('rel', 'mode')),
                           af.get('pilot'), af.get('client_sees_pilot'), af.get('client_pawn_is_char'), af.get('stations'),
                           (af.get('server') or {}).get('att'), (af.get('client') or {}).get('att'), refused, ok), fr)
        if self.D.get('host_was_pilot'):
            a, b = self.D.get('h_pre'), self.D.get('h_post')
            ok2 = a is not None and b is not None and abs(a - b) <= 0.5 and self.D.get('host_on_foot')
            self.check('T4.4_exit_keeps_health_host_L', 'PASS' if ok2 else 'FAIL', 'the host pilot\'s health %s before Exit, %s after (want the same: '
                       'not refilled by the possession), on foot %s' % (a, b, self.D.get('host_on_foot')))
        else:
            self.check('T4.4_exit_keeps_health_host_L', 'SKIP', 'the host did not fly a ship at the start of g3_swap (AS60_ONLY run)')

    # ---- T6.2: the client pilot's LMB in the bow arc drives both turrets
    def turret_counts(self, ship):
        return [self.shots(self.turret(ship, i)) for i in (0, 1)]

    def start_g3_arc(self):
        self.D['s0'] = (self.turret_counts(self.ship2_s), self.turret_counts(self.ship2_c))
        self.D['h0'] = self.ship_hp(self.ship1_s)

    def ph_g3_arc(self, el):
        tgt = self.loc(self.ship1_s)
        tgt[2] += 200.0
        self.aim_pc('client', tgt)
        if el >= 1.4 and 'yaw_off' not in self.D:
            self.D['yaw_off'] = self.cam_yaw_off(self.cw, self.ship2_c)
            self.D['t_on'] = self.now
        if 1.5 <= el < 2.5:
            self.inject('client', 'IA_AirshipFire')
        if el >= 4.5 and 's1' not in self.D:
            self.D['s1'] = (self.turret_counts(self.ship2_s), self.turret_counts(self.ship2_c))
            self.D['h1'] = self.ship_hp(self.ship1_s)

    def end_g3_arc(self):
        s0, s1 = self.D.get('s0'), self.D.get('s1') or self.D.get('s0')
        ds = [s1[0][i] - s0[0][i] for i in (0, 1)]
        dc = [s1[1][i] - s0[1][i] for i in (0, 1)]
        balls = self.new_balls('server', self.D.get('t_on', 1e9), source=self.ship2_s.get_name())
        h0, h1 = self.D.get('h0'), self.D.get('h1')
        drop = (h0 - h1) if h0 is not None and h1 is not None else None
        exp = sum(ds) * fnum(self.orig.get('settings', {}).get('TurretGunDamageMultiplier'), 4.0) * self.gun_base
        yo = self.D.get('yaw_off')
        ok = all(9 <= x <= 11 for x in ds) and all(9 <= x <= 11 for x in dc) and not balls and drop is not None and exp > 0 and abs(drop - exp) <= 0.25 * exp \
            and yo is not None and yo <= 30.0
        self.check('T6.2_client_pilot_turrets', 'PASS' if ok else 'FAIL', 'client pilot of ship 2, camera %s deg off the bow (want <= 30) at ship 1 '
                   '%.0f m ahead, LMB held 1 s: server shots per turret %s (want 9-11 each), client tracers %s (want 9-11 each, predicted); '
                   'ship 1 %s -> %s (drop %s, want %.0f +-25 %% = shots x %.0f x gun %.2f: the server\'s hits); ship 2 cannonballs %d (want 0)' % (
                       r(yo, 1) if yo is not None else None, T6_AHEAD / 100.0, ds, dc, h0, h1, drop, exp,
                       fnum(self.orig.get('settings', {}).get('TurretGunDamageMultiplier'), 4.0), self.gun_base, len(balls)))

    # ---- T6.3: camera 90 deg to port: a broadside, no turret rounds
    def start_g3_port(self):
        self.D['s0'] = self.turret_counts(self.ship2_s)

    def ph_g3_port(self, el):
        if 'ft' not in self.D:
            self.look('client', self.yaw(self.ship2_c) - 90.0, -4.0)
        if el >= 1.5 and 'ft' not in self.D:
            self.D['ft'] = self.now
            self.D['nb0'] = len(self.balls['server'])
            self.D['yaw_off'] = self.cam_yaw_off(self.cw, self.ship2_c)
            self.inject('client', 'IA_AirshipFire')
            self.event('inject', what='IA_AirshipFire (client pilot, port)')
        ft = self.D.get('ft')
        if ft is not None and self.now - ft >= 0.6 and 'fb' not in self.D and len(self.balls['server']) == self.D['nb0']:
            self.D['fb'] = True
            self.line('WARN', 'the client\'s fire injection made no ball in 0.6 s (no fallback: a call from Python runs its RPC locally)')

    def end_g3_port(self):
        ft = self.D.get('ft', 1e9)
        sb = self.new_balls('server', ft, source=self.ship2_s.get_name())
        n1 = [b for b in sb if dist(b['first'], self.muzzle_w(self.ship2_s, 'L1')) <= 600.0]
        n2 = [b for b in sb if dist(b['first'], self.muzzle_w(self.ship2_s, 'L2')) <= 600.0]
        ds = [self.turret_counts(self.ship2_s)[i] - self.D['s0'][i] for i in (0, 1)]
        ok = len(sb) == 2 and len(n1) == 1 and len(n2) == 1 and ds == [0, 0] and not self.D.get('fb')
        self.check('T6.3_client_pilot_broadside', 'PASS' if ok else 'FAIL', 'client pilot camera %s deg off the bow (to port), LMB: server balls %d '
                   '(L1 %d, L2 %d: want 2 / 1 / 1), turret shots %s (want [0, 0])%s' % (
                       r(self.D.get('yaw_off'), 1) if self.D.get('yaw_off') is not None else None, len(sb), len(n1), len(n2), ds,
                       ' FALLBACK RequestFire' if self.D.get('fb') else ''), {'balls': sb})

    # ---- T5.12: the host mans R1 of the client's ship and fires; the client's starboard broadside fires only R2
    def r1_target(self):
        return self.world_of(self.ship2_s, (self.mz_local['R1'][0] + 1500.0, self.mz_local['R1'][1] + 10000.0, self.mz_local['R1'][2]))

    def start_g3_r1(self):
        p, _ = self.deck_point(self.ship2_s, -300.0, 300.0, self.hchar)
        self.tp_host(p, self.yaw(self.ship2_s))
        self.D['aims'] = []

    def ph_g3_r1(self, el):
        s, c = self.ship2_s, self.ship2_c
        if el >= 0.4 and 'm' not in self.D:
            self.D['m'] = True
            self.scmd('Aura.Airship.Mount 0 2')
        if el >= 0.5 and el < 3.0:
            self.aim_pc('host', self.r1_target())
        if el >= 1.0 and 'att' not in self.D:
            hc = self.host_on_client()
            self.hchar_c = hc
            self.D['att'] = {'server': self.char_info(self.hchar, s), 'client': self.char_info(hc, c) if hc else None,
                             'gunner_server': same(self.gunner(s, 2), self.hchar), 'gunner_client_seen': self.gunner(c, 2) is not None}
        if 0.5 <= el < 1.6:
            a = self.anim(s, ['CannonYawDeg_R1', 'CannonElevDeg_R1'])
            b = self.anim(c, ['CannonYawDeg_R1', 'CannonElevDeg_R1'])
            self.D['aims'].append((a.get('CannonYawDeg_R1'), a.get('CannonElevDeg_R1'), b.get('CannonYawDeg_R1'), b.get('CannonElevDeg_R1'), r(el, 3)))
        if el >= 1.0 and 'rec1' not in self.D:
            # the baseline comes before the press: the host's own shot happens in the very next tick, so a tracker started
            # with the press would take the rising recoil as its baseline and miss the peak on the server
            self.D['rec1'] = True
            self.rec_start('R1', (s, c), ['R1', 'R2'])
        if el >= 1.6 and 'f1' not in self.D:
            self.D['f1'] = self.now
            self.mz_start('R1', (s, c), 0.8)
            self.inject('server', 'IA_AirshipFire')
            self.event('inject', what='IA_AirshipFire (host gunner R1)')
        if el >= 2.2 and 'f2' not in self.D:
            self.look('client', self.yaw(c) + 90.0, -4.0)
        if el >= 3.0 and 'pk1' not in self.D:
            # the host's R1 shot alone: freeze its tracker, a fresh one (baseline now, R1 decaying) watches the broadside
            self.D['pk1'] = (self.peaks('R1', 'server', 'R1'), self.peaks('R1', 'client', 'R1'))
            self.D['rec'].pop('R1', None)
            self.rec_start('R2', (s, c), ['R1', 'R2'])
        if el >= 3.4 and 'f2' not in self.D:
            self.D['f2'] = self.now
            self.D['nb0'] = len(self.balls['server'])
            self.inject('client', 'IA_AirshipFire')
            self.event('inject', what='IA_AirshipFire (client pilot, starboard)')
        f2 = self.D.get('f2')
        if f2 is not None and self.now - f2 >= 0.6 and 'fb' not in self.D and len(self.balls['server']) == self.D['nb0']:
            self.D['fb'] = True
            self.line('WARN', 'the client\'s starboard fire injection made no ball in 0.6 s (no fallback: a call from Python runs its RPC locally)')

    def end_g3_r1(self):
        s = self.ship2_s
        f1, f2 = self.D.get('f1', 1e9), self.D.get('f2', 1e9)
        mR1, mR2 = self.muzzle_w(s, 'R1'), self.muzzle_w(s, 'R2')
        b1 = [b for b in self.new_balls('server', f1) if b['t0'] < f2 - 0.05]
        b1r1 = [b for b in b1 if dist(b['first'], mR1) <= 600.0]
        at = self.D.get('att') or {}
        sv, cl = at.get('server') or {}, at.get('client') or {}
        dev = dist(sv['rel'], cl['rel']) if sv.get('rel') and cl.get('rel') else None
        # The client's barrel follows the replicated aim a frame or more later: while the server's cannon still slews (45
        # deg/s) that is a lag, not a disagreement. Judged on the frames from 1.0 s where the server's barrel moved < 0.1 deg
        # in the last 0.1 s (settled); the max over every frame is reported.
        # The host's camera is still swinging after the mount (spring-arm lag), so the server's R1 slews for the whole
        # window and the client's barrel, which follows the replicated aim, trails it by its replication delay: compared
        # frame for frame that delay x the slew rate (up to 45 deg/s, 1.5 deg a frame) reads as a disagreement. Compared
        # as the client against the server k frames earlier, k = 0..4 (the best k is reported), from 1.0 s.
        # 2026-11-27 (first run after the helm / deck change: 1.04 deg at k = 0, 0.99 on 11-25): k = -1 is compared too. On
        # the host the gunner's aim reaches StationAims in the pilot component's tick and the ship's own barrel shows it
        # from the Mesh's next animation update, a frame later; the client gets the replicated aim before its frame's ticks
        # and shows it in the same frame. So in one harness frame the client's barrel is up to ONE frame ahead of the
        # server's own (the samples: at every frame of the swing back the client is ahead by the server's change of the
        # next frame). That is the host's display order, not a disagreement; the 1 deg limit is unchanged.
        rows = [x for x in self.D['aims'] if None not in x[:4]]
        settled = [rows[i] for i in range(3, len(rows)) if rows[i][4] >= 1.0 and abs(rows[i][0] - rows[i - 3][0]) < 0.1 and abs(rows[i][1] - rows[i - 3][1]) < 0.1]
        best = None
        per_k = {}
        for k in range(-1, 5):
            pr = [(rows[i - k], rows[i]) for i in range(max(k, 0), len(rows) + min(k, 0)) if rows[i][4] >= 1.0]
            if len(pr) < 5:
                continue
            my = max(abs(a[0] - c[2]) for a, c in pr)
            me = max(abs(a[1] - c[3]) for a, c in pr)
            per_k[k] = r(max(my, me), 2)
            if best is None or max(my, me) < max(best[1], best[2]):
                best = (k, my, me, len(pr))
        aims = rows if best else []
        dy = best[1] if best else None
        de = best[2] if best else None
        self.D['aim_all'] = {'frames': len(rows), 'best_lag_frames': best[0] if best else None, 'pairs': best[3] if best else None, 'max_diff_per_lag': per_k,
                             'same_frame_max_yaw_diff': r(max(abs(x[0] - x[2]) for x in rows if x[4] >= 1.0), 2) if rows else None,
                             'settled_frames': len(settled), 'settled_max_yaw_diff': r(max(abs(x[0] - x[2]) for x in settled), 2) if settled else None,
                             'server_yaw_first_last': (r(rows[0][0], 2), r(rows[-1][0], 2)) if rows else None}
        pk1 = self.D.get('pk1') or (self.peaks('R1', 'server', 'R1'), self.peaks('R1', 'client', 'R1'))
        mz = self.mz_new('R1')
        ok = (at.get('gunner_server') and at.get('gunner_client_seen') and sv.get('att') == s.get_name() and cl.get('att') == self.ship2_c.get_name()
              and dev is not None and dev <= 10.0 and len(aims) >= 5 and dy is not None and dy <= 1.0 and de <= 1.0 and len(b1) == 1 and len(b1r1) == 1 and pk1 == (1, 1)
              and (mz['client'] or 0) >= 1)
        self.check('T5.12a_host_gunner_R1', 'PASS' if ok else 'FAIL', 'Aura.Airship.Mount 0 2 on the client\'s ship: host at R1 on the server %s, '
                   'the client sees it there %s (host copy on the client attached to %s, %s cm from the server\'s seat point, hull space: want <= 10); '
                   'R1 aim server vs client max diff yaw %s elev %s deg, the client against the server best_lag_frames earlier (want <= 1 with a lag '
                   'of -1 to 4 frames; -1 = the client one frame ahead of the host\'s own barrel, which shows the aim a frame late; %s); host LMB: '
                   'server balls %d (from R1 %d: want 1 / 1), R1 recoil '
                   'peaks server / client %s (want 1 / 1), new muzzle FX server %s client %s (want >= 1 on the client)' % (
                       at.get('gunner_server'), at.get('gunner_client_seen'), cl.get('att'), r(dev, 1) if dev is not None else None,
                       r(dy, 2) if dy is not None else None, r(de, 2) if de is not None else None, self.D.get('aim_all'), len(b1), len(b1r1), pk1,
                       mz['server'], mz['client']),
                   {'att': at, 'balls': b1, 'aims': self.D['aims']})
        b2 = self.new_balls('server', f2, source=s.get_name())
        b2r1 = [b for b in b2 if dist(b['first'], mR1) <= 600.0]
        b2r2 = [b for b in b2 if dist(b['first'], mR2) <= 600.0]
        pk2 = (self.peaks('R2', 'server', 'R1'), self.peaks('R2', 'client', 'R1'))
        ok2 = len(b2) == 1 and len(b2r2) == 1 and not b2r1 and not pk2[0] and not pk2[1] and not self.D.get('fb')
        self.check('T5.12b_client_broadside_skips_R1', 'PASS' if ok2 else 'FAIL', 'client pilot\'s starboard broadside with the host on R1 (R1 loaded '
                   'again by then): server balls %d (R2 %d, R1 %d: want 1 / 1 / 0), R1 recoil peaks server / client %s (want 0 / 0)%s' % (
                       len(b2), len(b2r2), len(b2r1), pk2, ' FALLBACK RequestFire' if self.D.get('fb') else ''), {'balls': b2})

    # ---- T5.12 (turret): the host on turret R of the client's ship
    def start_g3_turret(self):
        self.scmd('Aura.Airship.Dismount 0')
        self.D['aims'], self.D['fx'] = [], {'server': False, 'client': False}

    def ph_g3_turret(self, el):
        s, c = self.ship2_s, self.ship2_c
        ts, tc = self.turret(s, 1), self.turret(c, 1)
        if el >= 0.5 and 'm' not in self.D:
            self.D['m'] = True
            self.scmd('Aura.Airship.Mount 0 5')
        tgt = self.loc(self.ship1_s)
        tgt[2] += 200.0
        if el >= 0.6:
            self.aim_pc('host', tgt)
        if el >= 1.3 and 'est' not in self.D:
            self.D['est'] = self.aim_point_est(self.sw, s, tgt)
            self.D['mounted'] = same(self.gunner(s, 5), self.hchar)
        if 1.4 <= el < 1.9:
            a, b = self.tstate(ts), self.tstate(tc)
            vh = self.view_hit(self.sw, self.own_ignores(s) + [x for x in (self.hchar, self.cchar_s) if valid(x)])
            self.D['aims'].append((a.get('yaw'), a.get('pitch'), b.get('yaw'), b.get('pitch'), vh))
        if el >= 1.95 and 's0' not in self.D:
            self.D['s0'] = (self.shots(ts), self.shots(tc))
            self.D['h0'] = self.ship_hp(self.ship1_s)
        if 2.0 <= el < 3.0:
            self.inject('server', 'IA_AirshipFire')
        if 2.1 <= el < 3.2:
            self.D['fx']['server'] = self.D['fx']['server'] or bool(self.comp_active(ts, 'MuzzleFXComponent'))
            self.D['fx']['client'] = self.D['fx']['client'] or bool(self.comp_active(tc, 'MuzzleFXComponent'))
        if el >= 4.5 and 's1' not in self.D:
            self.D['s1'] = (self.shots(ts), self.shots(tc))
            self.D['h1'] = self.ship_hp(self.ship1_s)

    def end_g3_turret(self):
        s0, s1 = self.D.get('s0') or (0, 0), self.D.get('s1') or (0, 0)
        ds, dc = s1[0] - s0[0], s1[1] - s0[1]
        ts = self.turret(self.ship2_s, 1)
        res = self.turret_aim_eval(self.ship2_s, ts, 1, self.D['aims'], self.D.get('est'))
        ok_aim = res.get('ok')
        h0, h1 = self.D.get('h0'), self.D.get('h1')
        drop = (h0 - h1) if h0 is not None and h1 is not None else None
        ok = self.D.get('mounted') and 9 <= ds <= 11 and 9 <= dc <= 11 and self.D['fx']['client'] and ok_aim and drop is not None and drop > 0
        self.check('T5.12c_host_gunner_turret', 'PASS' if ok else 'FAIL', 'Aura.Airship.Mount 0 5 (host on turret R of the client\'s ship, mounted %s), '
                   'host LMB held 1 s at ship 1: server shots %d (want 9-11), the client draws %d (want 9-11, from the multicast), muzzle flash on '
                   'the client %s; aim %s (server within 3 deg of the bearing to the host\'s view-ray hit, the harness\'s camera-to-ship-1 trace is '
                   'the reported target; client within 2 deg of the server); ship 1 %s -> %s (want a drop)' % (
                       self.D.get('mounted'), ds, dc, self.D['fx']['client'], res, h0, h1), res)

    # ---- T5.8 (host gunner): F leaves turret R
    def ph_g3_exit(self, el):
        s = self.ship2_s
        if el >= 0.3 and 'f' not in self.D:
            self.D['f'] = el
            self.inject('server', 'IA_AirshipExit')
            self.event('inject', what='IA_AirshipExit (host gunner)')
        if 'f' in self.D and 'srv_t' not in self.D and self.gunner(s, 5) is None:
            self.D['srv_t'] = el
        if el >= 1.5 and 'fb' not in self.D and same(self.gunner(s, 5), self.hchar):
            self.D['fb'] = True
            self.pilot_comp(self.hpc).request_dismount()
            self.line('WARN', 'the host\'s F did not leave turret R in 1.2 s: fallback RequestDismount')
        if el >= 2.6 and 'snap' not in self.D:
            self.D['snap'] = self.char_info(self.hchar, s)

    def end_g3_exit(self):
        sn = self.D.get('snap') or {}
        ok = self.gunner(self.ship2_s, 5) is None and not self.D.get('fb') and sn.get('att') is None and sn.get('cmc_tick') is True and \
            sn.get('mode') in ('MOVE_WALKING', 'MOVE_FALLING') and same(self.hpc.get_controlled_pawn(), self.hchar)
        self.check('T5.8_host_gunner_F_dismount', 'PASS' if ok else 'FAIL', 'host F (IA_AirshipExit) on turret R%s: station free %.2f s after F; host '
                   'at +2.3 s %s (want detached, CMC on, walking or falling)' % (
                       ' FALLBACK RequestDismount' if self.D.get('fb') else '', (self.D.get('srv_t') or -1) - (self.D.get('f') or 0), sn))

    # ================================================================ g4_: crew damage with the client pilot, the host's gun
    def start_g4_setup(self):
        self.ensure_roles('foot', 'pilot2')
        s2 = self.ship2_s
        p2, f2, y2 = self.loc(s2), self.fwd(s2), self.yaw(s2)
        d = 2100.0 + GUN_GAP + HOST_DECK_X
        self.tship(self.ship1_s, [p2[0] + f2[0] * d, p2[1] + f2[1] * d, p2[2]], y2 + 180.0)
        p, traced = self.deck_point(self.ship1_s, HOST_DECK_X, 0.0, self.hchar)
        self.tp_host(p, y2 + 180.0)
        self.D['geo'] = {'ship1': r(self.loc(self.ship1_s), 0), 'host': r(p, 0), 'deck_traced': traced}

    def ph_g4_setup(self, el):
        if el >= 2.5 and 'line' not in self.D:
            t = self.turret(self.ship2_s, 0)
            hb = v3(t.get_editor_property('HitBox').get_world_location()) if t else None
            if hb:
                self.aim_pc('host', hb)
                c, _ = self.cam(self.sw)
                self.D['line'] = self.trace(self.sw, c, hb, self.own_ignores(self.ship1_s) + [self.hchar])
                self.D['cam'] = r(c, 0)
                self.D['hitbox'] = r(hb, 0)

    def end_g4_setup(self):
        self.check('g4_setup_bow_to_bow', 'INFO', 'ship 1 bow to bow with the client\'s ship 2, the host on its forward deck: %s; host camera %s, '
                   'first Visibility hit toward ship 2\'s turret L HitBox %s: %s' % (self.D.get('geo'), self.D.get('cam'), self.D.get('hitbox'), self.D.get('line')))

    def gun_frames(self):
        # GE_GunShootDamage is 1 in the repo and 1000 in the user's local tree: with a big value one hit is plenty
        return 1 if self.gun_base > 20.0 else 60

    def gun_track(self, el, extra=None):
        h = {'ship_s': self.ship_hp(self.ship2_s), 'ship_c': self.ship_hp(self.ship2_c), 'pilot_s': self.health(self.cchar_s), 'pilot_c': self.health(self.cchar_c)}
        if extra:
            h.update(extra())
        tr = self.D.setdefault('trk', [])
        if not tr or any(tr[-1][1].get(k) != v for k, v in h.items()):
            tr.append((r(el, 3), h))
        return h

    def start_g4_hull(self):
        self.D['T'] = self.world_of(self.ship2_s, (2600.0, 0.0, 450.0))
        self.D['n'] = 0

    def ph_g4_hull(self, el):
        self.aim_pc('host', self.D['T'])
        h = self.gun_track(el)
        if el >= 0.9 and 'h0' not in self.D:
            self.D['h0'] = h
        if el >= 1.0 and self.D['n'] < self.gun_frames() and el < 3.0:
            self.inject('server', 'IA_LMB')
            self.D['n'] += 1
        if el >= 4.5 and 'h1' not in self.D:
            self.D['h1'] = h

    def end_g4_hull(self):
        h0, h1 = self.D.get('h0') or {}, self.D.get('h1') or {}
        dr = self.drops(h0, h1)
        ds = dr.get('ship_s')
        want = ds * self.share if ds is not None else None
        ok = ds is not None and ds > 0 and all(dr.get(k) is not None and abs(dr[k] - want) <= max(0.5, 0.05 * want) for k in ('pilot_s', 'pilot_c')) and \
            dr.get('ship_c') is not None and abs(dr['ship_c'] - ds) <= 0.5
        self.check('crew_share_host_gun_client_pilot', 'PASS' if ok else 'FAIL', 'the host (on ship 1\'s deck) fires GA_GunShoot at ship 2\'s bow below '
                   'its deck (%d frames of IA_LMB): drops %s (want ship > 0 on both machines, the client pilot %s = %.2f x the ship\'s loss, on the server '
                   'and in its own view, +-max(0.5, 5 %%)); track %s' % (self.D['n'], dr, r(want, 2) if want is not None else None, self.share,
                                                                         self.D.get('trk', [])[:12]), {'before': h0, 'after': h1})

    def start_g4_turret(self):
        t = self.turret(self.ship2_s, 0)
        self.D['hb'] = v3(t.get_editor_property('HitBox').get_world_location()) if t else None
        self.D['n'] = 0

    def ph_g4_turret(self, el):
        if self.D.get('hb') is None:
            return
        self.aim_pc('host', self.D['hb'])

        def tur():
            return {'turret_s': self.tstate(self.turret(self.ship2_s, 0)).get('health'), 'turret_c': self.tstate(self.turret(self.ship2_c, 0)).get('health')}
        h = self.gun_track(el, tur)
        if el >= 0.8 and 'line' not in self.D:
            c, _ = self.cam(self.sw)
            self.D['line'] = self.trace(self.sw, c, self.D['hb'], self.own_ignores(self.ship1_s) + [self.hchar])
        if el >= 0.9 and 'h0' not in self.D:
            self.D['h0'] = h
        if el >= 1.0 and self.D['n'] < self.gun_frames() and el < 3.0:
            self.inject('server', 'IA_LMB')
            self.D['n'] += 1
        if el >= 4.5 and 'h1' not in self.D:
            self.D['h1'] = h
            self.capture(self.sw, 'g4_turret', 'player')

    def end_g4_turret(self):
        h0, h1 = self.D.get('h0') or {}, self.D.get('h1') or {}
        dr = self.drops(h0, h1)
        dt = dr.get('turret_s')
        hits = dt / self.gun_base if dt is not None and self.gun_base > 0 else None
        first = (self.D.get('line') or {}).get('actor')
        ok = dt is not None and dt > 0 and abs(hits - round(hits)) < 0.01 and h1.get('turret_c') is not None and abs(h1['turret_c'] - h1['turret_s']) < 0.01
        self.check('fix6.3_host_gun_turret_through_hull', 'PASS' if ok else 'FAIL', 'the host fires GA_GunShoot at ship 2\'s turret L HitBox %s: '
                   'first Visibility hit from the host camera %s (the turret itself since the hull\'s collision ignores Visibility, or ship 2\'s '
                   'Mesh: a PA_Airship box in front of it, which FindTurretBehindHullHit hands on); turret %s -> %s on the server (drop %s = %s hits of %.2f, want > 0 whole hits), the client '
                   'sees %s; ship 2 %s -> %s, client pilot %s -> %s (the crew share of any hull hit)' % (
                       r(self.D.get('hb'), 0), self.D.get('line'), h0.get('turret_s'), h1.get('turret_s'), dt, r(hits, 2) if hits is not None else None,
                       self.gun_base, h1.get('turret_c'), h0.get('ship_s'), h1.get('ship_s'), h0.get('pilot_s'), h1.get('pilot_s')),
                   {'first_hit': first, 'track': self.D.get('trk', [])[:20]})

    def start_g4_bullet(self):
        # Since the helm / deck change (Talal 11-25) the hull's collision ignores Visibility: the Mesh's physics asset
        # bodies are what the bullet meets, so the Mesh's collision stays on (as_59 T3.1)
        pass

    def hull_side_line(self, ship):
        """(from, to) of a test bullet into ship's port side: 37 m to port -> 1 m above the hull origin (below the planks,
        inside the hull tub's PA boxes, clear of the pods), as as_59 T3.1"""
        to = self.loc(ship)
        up, rg = v3(ship.get_actor_up_vector()), self.rgt(ship)
        to = [to[k] + up[k] * 100.0 for k in range(3)]
        return [to[k] - rg[k] * 3700.0 for k in range(3)], to

    def ph_g4_bullet(self, el):
        s = self.ship2_s
        if el >= 0.5 and 'b' not in self.D:
            self.D['b'] = True
            self.D['h0'] = self.crew2_h()
            frm, to = self.hull_side_line(s)
            self.D['line'] = self.trace(self.sw, frm, to)
            self.scmd('Aura.MechSentinel.TestBullet %.0f %.0f %.0f %.0f %.0f %.0f 3' % (tuple(frm) + tuple(to)))
        if el >= 2.0 and 'h1' not in self.D:
            self.D['h1'] = self.crew2_h()

    def end_g4_bullet(self):
        dr = self.drops(self.D.get('h0') or {}, self.D.get('h1') or {})
        want = 3.0 * self.share
        ok = dr.get('ship_s') is not None and abs(dr['ship_s'] - 3.0) < 0.05 and all(dr.get(k) is not None and abs(dr[k] - want) <= 0.05 for k in ('pilot_s', 'pilot_c'))
        self.check('crew_share_sentinel_bullet_client_pilot', 'PASS' if ok else 'FAIL', 'Aura.MechSentinel.TestBullet (3) from 37 m to port at ship 2\'s '
                   'hull side (a PA_Airship box, as T3.1): drops %s (want ship 3, the client pilot %.2f on the server and in its own view); first '
                   'Visibility hit %s' % (dr, want, self.D.get('line')))

    def crew2_h(self):
        return {'ship_s': self.ship_hp(self.ship2_s), 'ship_c': self.ship_hp(self.ship2_c), 'pilot_s': self.health(self.cchar_s), 'pilot_c': self.health(self.cchar_c)}

    def ph_g4_damage(self, el):
        if el >= 0.3 and 'h0' not in self.D:
            self.D['roles'] = same(self.ship2_s.get_pilot(), self.cchar_s)
            self.D['h0'] = self.crew2_h()
            self.scmd('Aura.Airship.Damage 100')
        if el >= 1.3 and 'h1' not in self.D:
            self.D['h1'] = self.crew2_h()

    def end_g4_damage(self):
        dr = self.drops(self.D.get('h0') or {}, self.D.get('h1') or {})
        want = 100.0 * self.share
        ok = self.D.get('roles') and dr.get('ship_s') is not None and abs(dr['ship_s'] - 100.0) < 0.5 and \
            all(dr.get(k) is not None and abs(dr[k] - want) <= 0.5 for k in ('pilot_s', 'pilot_c'))
        self.check('T4.1b_crew_share_client_pilot', 'PASS' if ok else 'FAIL', 'Aura.Airship.Damage 100 with the client at ship 2\'s helm (%s): drops %s '
                   '(want ship 100, the client pilot %.1f +-0.5 on the server and in its own view)' % (self.D.get('roles'), dr, want))

    # ================================================================ g5_: cannonballs seen by the client
    def start_g5_down(self):
        self.ensure_roles('foot', 'pilot2')
        self.tp_host(CHAR_FOOT, 0.0)
        self.tship(self.ship1_s, FAR1, 0.0)
        self.D['trk'] = []

    def ph_g5_down(self, el):
        s = self.ship2_s
        if el >= 0.5 and 'ball' not in self.D:
            B = self.world_of(s, (3120.0 + 500.0, 0.0, 805.0))
            rg = self.rgt(s)
            self.D['B'] = r(B, 0)
            self.D['h0'] = self.crew2_h()
            self.D['ball'] = self.spawn_ball(B, [rg[k] * 200.0 for k in range(3)], self.ship1_s, 60.0, 0.0)
        b = self.D.get('ball')
        if b is None:
            return
        if el >= 0.8 and self.D.get('cball') is None:
            self.D['cball'] = self.client_ball_near(self.loc(b) if valid(b) else self.D['B'])
        if el >= 1.0 and 'tf' not in self.D and valid(b):
            self.D['tf'] = el
            self.D['sh0'] = self.turret_counts(s)
            self.turret_fire_on = True
            self.D['tf_k'] = int(el * 5)
            self.scmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.loc(b)))
        elif 'tf' in self.D and 'down' not in self.D and self.turret_fire_on and valid(b) and int(el * 5) != self.D.get('tf_k'):
            # The ball moves 2 m/s across the bow: TurretFire at a fixed point is left behind within half a second if the
            # turrets have to slew first (they follow the client pilot's camera until the command). Re-aimed at the ball
            # every 0.2 s: "TurretFire at it".
            self.D['tf_k'] = int(el * 5)
            unreal.SystemLibrary.execute_console_command(self.sw, 'Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.loc(b)))
        if 'tf' in self.D and int(el * 10) != self.D.get('_tk'):
            self.D['_tk'] = int(el * 10)
            self.D.setdefault('tst', []).append((r(el, 2), [self.tstate(self.turret(s, i)) for i in (0, 1)], r(self.loc(b), 0) if valid(b) else None))
        st = self.ball_state(b) if valid(b) else {}
        if 'tf' in self.D and 'down' not in self.D and st.get('shot_down'):
            self.D['down'] = el
            self.D['down_at'] = st.get('loc')
            self.D['sh1'] = self.turret_counts(s)
            self.scmd('Aura.Airship.TurretFire 0')
            self.turret_fire_on = False
        if 'tf' in self.D and 'down' not in self.D and el >= 3.0 and self.turret_fire_on:
            self.D['sh_end'] = self.turret_counts(s)
            self.scmd('Aura.Airship.TurretFire 0')
            self.turret_fire_on = False
        cb = self.D.get('cball')
        cs = self.ball_state(cb) if cb is not None and valid(cb) else {}
        if cs:
            self.D['trk'].append((r(el, 3), cs.get('shot_down'), cs.get('hidden'), cs.get('coll'), cs.get('loc')))
            if 'c_down' not in self.D and (cs.get('shot_down') or cs.get('hidden')):
                self.D['c_down'] = el
        if 'c_down' in self.D and el >= self.D['c_down'] + 0.3 and 'ctr' not in self.D and cs.get('loc'):
            fw = self.fwd(self.ship2_c)
            p = cs['loc']
            self.D['ctr'] = self.trace(self.cw, [p[k] - fw[k] * 500.0 for k in range(3)], [p[k] + fw[k] * 500.0 for k in range(3)], [self.ship2_c])
            self.capture(self.cw, 'g5_down', 'player')
        if el >= 4.6 and 'h1' not in self.D:
            self.D['h1'] = self.crew2_h()

    def end_g5_down(self):
        if self.turret_fire_on:
            self.scmd('Aura.Airship.TurretFire 0')
            self.turret_fire_on = False
        tf, dn, cd = self.D.get('tf'), self.D.get('down'), self.D.get('c_down')
        trk = self.D.get('trk') or []
        after = [x for x in trk if cd is not None and x[0] >= cd + 0.1 and x[4]]
        still = max((dist(x[4], after[0][4]) for x in after), default=None) if after else None
        last = trk[-1] if trk else None
        off = dist(last[4], self.D['down_at']) if last and last[4] and self.D.get('down_at') else None
        sh = [self.D['sh1'][i] - self.D['sh0'][i] for i in (0, 1)] if 'sh1' in self.D and 'sh0' in self.D else None
        if sh is None and 'sh_end' in self.D and 'sh0' in self.D:
            sh = ['not down after', [self.D['sh_end'][i] - self.D['sh0'][i] for i in (0, 1)]]
        dr = self.drops(self.D.get('h0') or {}, self.D.get('h1') or {})
        ctr = self.D.get('ctr') or {}
        ok = (tf is not None and dn is not None and dn - tf <= 1.0 and cd is not None and cd - dn <= 0.5 and last is not None and last[2] is True and last[3] is False
              and still is not None and still < 5.0 and all(dr.get(k) is not None and abs(dr[k]) < 0.01 for k in ('ship_s', 'pilot_s', 'pilot_c'))
              and 'annonball' not in str(ctr.get('cls')))
        self.check('T2.7_ball_shot_down_client', 'PASS' if ok else 'FAIL', 'a hovering ball (ship 1\'s, 60 damage) 5 m ahead of ship 2\'s bow, '
                   'TurretFire at it: shot down on the server %s s after TurretFire 1 (want <= 1, about 8 rounds: shots %s); the client copy burst / '
                   'hid %s s after the server (want <= 0.5), at the end hidden %s, collision %s (want off), moved %s cm after its burst (want < 5: '
                   'stopped), %s cm from the server\'s shoot-down point; health drops ship 2 / client pilot %s (want 0: defused, no splash although '
                   'the hull is in its 6 m radius); a client trace through it hits %s (want not the ball)' % (
                       r(dn - tf, 2) if dn is not None and tf is not None else None, sh, r(cd - dn, 2) if cd is not None and dn is not None else None,
                       last[2] if last else None, last[3] if last else None, r(still, 1) if still is not None else None, r(off, 1) if off is not None else None,
                       dr, ctr), {'client_track': trk[::3], 'drops': dr, 'turrets': (self.D.get('tst') or [])[:30]})

    def start_g5_spent(self):
        self.D['trk'] = []

    def ph_g5_spent(self, el):
        s = self.ship2_s
        if el >= 0.3 and 'ball' not in self.D:
            o, e = s.get_actor_bounds(False)
            rg = self.rgt(s)
            half = abs(float(e.x) * rg[0]) + abs(float(e.y) * rg[1])
            p = self.loc(s)
            start = [p[k] - rg[k] * (half + 1000.0) for k in range(3)]
            # 1 m above the hull origin: the hull's side below the planks, where a PA_Airship box lies behind the skin (3 m
            # up, as before the helm / deck change, there is only the lid, which Visibility traces now pass)
            start[2] += 100.0
            self.D['start'] = r(start, 0)
            self.D['ball'] = self.spawn_ball(start, [rg[k] * 3000.0 for k in range(3)], self.ship1_s, 0.0, 0.0)
            self.D['t_ball'] = self.now
        b = self.D.get('ball')
        if b is None:
            return
        if el >= 0.45 and self.D.get('cball') is None:
            self.D['cball'] = self.client_ball_near(self.loc(b) if valid(b) else self.D['start'], 1500.0)
        recs = [x for x in self.balls['server'].values() if x['t0'] >= self.D['t_ball'] - 0.05]
        if recs and 'imp' not in self.D and (recs[0].get('hidden_at') or recs[0].get('impact')):
            self.D['imp'] = recs[0].get('hidden_at') or recs[0].get('impact')
            self.D['imp_t'] = el
        cb = self.D.get('cball')
        cs = self.ball_state(cb) if cb is not None and valid(cb) else {}
        if cs:
            self.D['trk'].append((r(el, 3), cs.get('hidden'), cs.get('coll'), cs.get('loc')))
            if 'c_hid' not in self.D and cs.get('hidden'):
                self.D['c_hid'] = el
        if 'c_hid' in self.D and el >= self.D['c_hid'] + 0.15 and 'ctr' not in self.D and cs.get('loc'):
            rg = self.rgt(self.ship2_c)
            p = cs['loc']
            self.D['ctr'] = self.trace(self.cw, [p[k] - rg[k] * 500.0 for k in range(3)], [p[k] + rg[k] * 400.0 for k in range(3)])
            self.D['c_coll'] = cs.get('coll')
            sb = self.D.get('ball')
            if valid(sb):
                sp = self.loc(sb)
                self.D['str'] = self.trace(self.sw, [sp[k] - rg[k] * 500.0 for k in range(3)], [sp[k] + rg[k] * 400.0 for k in range(3)])

    def end_g5_spent(self):
        ctr, stt = self.D.get('ctr') or {}, self.D.get('str') or {}
        ok = self.D.get('imp') is not None and self.D.get('c_hid') is not None and self.D.get('c_coll') is False and ctr.get('actor') == self.ship2_c.get_name() \
            and 'annonball' not in str(ctr.get('cls'))
        self.check('fix6.2_spent_ball_client', 'PASS' if ok else 'FAIL', 'a 0-damage ball (ship 1\'s) into ship 2\'s port side: server impact %s at %s s; '
                   'the client copy hidden at %s s with collision %s (want off: MulticastImpact / OnProjectileStop); a client Visibility trace through '
                   'the hidden ball toward the hull hits %s (want ship 2 %s, not the ball); the same on the server %s' % (
                       self.D.get('imp'), self.D.get('imp_t'), self.D.get('c_hid'), self.D.get('c_coll'), ctr, self.ship2_c.get_name(), stt),
                   {'client_track': (self.D.get('trk') or [])[::2]})

    # ================================================================ g6_: drift after a client pilot leaves at speed
    def start_g6_cruise(self):
        self.ensure_roles('foot', 'pilot2')
        self.set_scheme(self.ship2_s, self.cfg['scheme'])

    def ph_g6_cruise(self, el):
        self.look('client', self.yaw(self.ship2_c), -10.0)
        if el >= 0.5 and 'thr' not in self.D:
            self.D['thr'] = True
            self.ship2_c.debug_set_input(1.0, 0.0, 0.0, 0.0, False, False)
            self.event('client_input', input='throttle 1 (DebugSetInput on the client ship copy)')

    def start_g6_drift(self):
        self.ship2_c.debug_clear_input()
        t = self.tele(self.ship2_s)
        self.D['v_exit'] = t.get('ForwardSpeedMS')
        # T8.4 L: the driving pose of both copies (attached at the seat), each in its own machine's hull space
        self.D['drive'] = {'server': self.rel(self.ship2_s, self.loc(self.cchar_s)), 'client': self.rel(self.ship2_c, self.loc(self.cchar_c)),
                           'seat_expected': self.helm_local(self.ship2_s)}
        self.D['xt'] = []
        self.inject('client', 'IA_AirshipExit')
        self.event('inject', what='IA_AirshipExit (client pilot at speed)')
        self.D['trk'] = []

    def ph_g6_drift(self, el):
        s, c = self.ship2_s, self.ship2_c
        if el >= 1.2 and 'fb' not in self.D and s.has_pilot():
            self.D['fb'] = True
            self.scmd('Aura.Airship.Exit %d' % self.cidx)
            self.line('WARN', 'the client\'s exit injection did nothing in 1.2 s: fallback Aura.Airship.Exit (the client gets no ClientRestart)')
        if 'foot_t' not in self.D and same(self.cpc.get_controlled_pawn(), self.cchar_c):
            self.D['foot_t'] = el
        if 'srv_foot_t' not in self.D and not s.has_pilot():
            self.D['srv_foot_t'] = el
        if 'srv_foot_t' in self.D and el <= self.D['srv_foot_t'] + 3.0:
            # every frame for 3 s from the server's exit: both copies in their own hull's space, their modes and parents
            cs, cc = self.char_info(self.cchar_s, s) or {}, self.char_info(self.cchar_c, c) or {}
            self.D['xt'].append((r(el - self.D['srv_foot_t'], 3), cs.get('rel'), cc.get('rel'), cs.get('mode'), cc.get('mode'), cs.get('att'), cc.get('att'),
                                 cc.get('actor_coll'), cc.get('role')))
        t = self.tele(s)
        m = int(fnum(t.get('UnpilotedMode'), -1))
        vf = fnum(t.get('ForwardSpeedMS'))
        vc = fnum(self.tele(c).get('ForwardSpeedMS'))
        self.D['trk'].append((r(el, 3), m, r(vf, 3), r(vc, 3), r(dist(self.loc(s), self.loc(c)), 1), fnum(t.get('DriftTargetSpeedMS')), r(self.now, 3),
                              r(self.loc(s), 1), r(self.loc(c), 1)))
        if 'ds0' not in self.D and el >= 3.0 and ((m == 2 and vf is not None and vf <= 3.0) or el >= 19.0):
            self.D['ds0'] = el
            self.D['ds0_slow'] = m == 2 and vf is not None and vf <= 3.0
            self.scmd('Aura.Airship.Set Settings.DriftSpeed 0')
            self.carry['g6_ds0'] = self.now

    def end_g6_drift(self):
        self.carry['g6'] = dict((k, v) for k, v in self.D.items())
        # T8.4 L (Talal 11-25): "when player exits, the character should keep its position in front of the steering wheel".
        # Server: UnboardPilot leaves it at the seat, walking, the ship its base. The client's own copy: ClientLeftHelm ->
        # PlaceLeftPilotLocal puts it at the same hull-relative place at once (left to replication it fell with no base and
        # no speed: 1.2 m behind per frame at 35 m/s until the server's correction, round 1's 3 m snap).
        xt, dr = self.D.get('xt') or [], self.D.get('drive') or {}
        ds, dc = dr.get('server'), dr.get('client')
        dev_s = [hdist(x[1], ds) for x in xt if x[1] and ds]
        dev_c = [hdist(x[2], dc) for x in xt if x[2] and dc]
        step_c = [dist(xt[i][2], xt[i - 1][2]) for i in range(1, len(xt)) if xt[i][2] and xt[i - 1][2]]
        late = [x for x in xt if x[0] >= 2.0]
        end = late[-1] if late else (xt[-1] if xt else None)
        modes_s, modes_c = sorted(set(x[3] for x in xt if x[3])), sorted(set(x[4] for x in xt if x[4]))
        both = [dist(x[1], x[2]) for x in late if x[1] and x[2]]
        dz = (end[1][2] - ds[2], end[2][2] - dc[2]) if end and end[1] and end[2] and ds and dc else (None, None)
        ok = (bool(xt) and end is not None and not self.D.get('fb') and self.D.get('foot_t') is not None
              and bool(dev_s) and max(dev_s) <= 10.0 and bool(dev_c) and max(dev_c) <= 100.0
              and end[1] is not None and end[2] is not None and hdist(end[1], ds) <= 10.0 and hdist(end[2], dc) <= 10.0
              and end[3] == 'MOVE_WALKING' and end[4] == 'MOVE_WALKING' and end[5] is None and end[6] is None)
        self.check('T8.4_client_exit_in_place_L', 'PASS' if ok else 'FAIL', 'client pilot F (IA_AirshipExit) at %s m/s%s, 3 s from the server\'s exit, each '
                   'copy in its own hull\'s space against its driving pose (server %s, client %s; the seat %s): server copy at most %s cm off in xy '
                   '(want <= 10), the client\'s own copy at most %s cm off (want <= 100: no snap; round 1: 300), its largest step in one frame %s cm; '
                   'from 2 s on: server %s, client %s (want within 10 cm in xy, walking, detached), z %s / %s cm from the driving pose (the seat\'s '
                   'clearance down onto the deck box), the two copies %s cm apart; modes seen server %s client %s; client copy first frame %s' % (
                       self.D.get('v_exit'), ' FALLBACK console Exit (no ClientRestart, no ClientLeftHelm: not the tested path)' if self.D.get('fb') else '',
                       r(ds, 1) if ds else None, r(dc, 1) if dc else None, r(dr.get('seat_expected'), 1) if dr.get('seat_expected') else None,
                       r(max(dev_s), 1) if dev_s else None, r(max(dev_c), 1) if dev_c else None, r(max(step_c), 1) if step_c else None,
                       end[1::2][:3] if end else None, end[2::2][:3] if end else None, r(dz[0], 1) if dz[0] is not None else None,
                       r(dz[1], 1) if dz[1] is not None else None, stats(both), modes_s, modes_c, xt[0] if xt else None),
                   {'drive': dr, 'track': xt[::3], 'dev_server_cm': stats(dev_s), 'dev_client_cm': stats(dev_c)})

    def start_g6_hold(self):
        self.D['trk'] = []

    # ================================================================ g8_: the client jumps on the deck of a flying ship
    # T8.7 L / T8.8 L (added 2026-11-27). as_59 T8.7 / T8.8 are the standalone checks of UMyCharacterMovementComponent's
    # "stay based on a vehicle in the air" (CPP_NOTES 15.10); here the jumper is the client's own (autonomous) character,
    # so the jump is predicted on its machine and replayed by the server from its moves. ACharacter::Jump on the client's
    # copy only sets its jump flag (no RPC): the move goes out with the client's next movement tick, as a key press does.
    def start_g8_jump(self):
        self.ensure_roles('pilot1', 'foot')
        s = self.ship1_s
        self.tship(s, SPAWN, 0.0)
        self.set_scheme(s, self.cfg['aim_scheme'])
        helm = self.helm_local(s)
        # 1.5 m behind the standing spot: open planks (as as_59 t8_walk)
        p, traced = self.deck_point(s, helm[0] - 150.0, helm[1], self.cchar_s)
        self.D['pt'] = {'hull': r(self.rel(s, p), 0), 'traced': traced}
        self.tp_client(p, self.yaw(s))
        self.D['trk'] = []

    def ph_g8_jump(self, el):
        s, c = self.ship1_s, self.ship1_c
        self.look('host', self.yaw(s), -8.0)
        if el >= 1.0 and 'thr' not in self.D:
            self.D['thr'] = True
            s.debug_set_input(1.0, 0.0, 0.0, 0.0, False, False)
            self.event('host_input', input='throttle 1.00')
        v = fnum(self.tele(s).get('ForwardSpeedMS'), 0.0)
        if 'j' not in self.D and el >= 3.0 and (v >= 30.0 or el >= 6.5):
            self.D['j'] = el
            self.D['j_v'] = r(v, 2)
            self.D['j_rel'] = {'server': self.rel(s, self.loc(self.cchar_s)), 'client': self.rel(c, self.loc(self.cchar_c))}
            self.D['j_info'] = {'server': self.char_info(self.cchar_s, s), 'client': self.char_info(self.cchar_c, c)}
            try:
                self.cchar_c.jump()
            except Exception:  # noqa: BLE001
                self.err('g8_jump')
            self.event('client_jump', v=r(v, 1))
        j = self.D.get('j')
        if j is not None and el >= j + 0.15 and 'j_stop' not in self.D:
            self.D['j_stop'] = True
            try:
                self.cchar_c.stop_jumping()
            except Exception:  # noqa: BLE001
                self.err('g8_stop_jumping')
        if el >= 1.0:
            cs, cc = self.char_info(self.cchar_s, s) or {}, self.char_info(self.cchar_c, c) or {}
            self.D['trk'].append((r(el, 3), cs.get('rel'), cc.get('rel'), cs.get('mode'), cc.get('mode'), r(v, 2)))
        if j is not None and el >= j + 3.2 and 'brk' not in self.D:
            self.D['brk'] = True
            s.debug_set_input(*BRAKE)

    def end_g8_jump(self):
        try:
            self.ship1_s.debug_set_input(*BRAKE)
        except Exception:  # noqa: BLE001
            self.err('g8_brake')
        trk, j, jr = self.D.get('trk') or [], self.D.get('j'), self.D.get('j_rel') or {}
        res = {}
        for name, ri, mi in (('server', 1, 3), ('client', 2, 4)):
            rows = [x for x in trk if j is not None and x[0] >= j and x[0] <= j + 3.2 and x[ri]]
            walk0 = [x for x in trk if j is not None and x[0] < j and x[ri]]
            air = [x for x in rows if x[mi] == 'MOVE_FALLING']
            land = next((x for x in rows if air and x[0] > air[-1][0] and x[mi] == 'MOVE_WALKING'), None)
            j0 = jr.get(name)
            miss = hdist(land[ri], j0) if land and j0 else None
            post = [x for x in rows if land is not None and land[0] <= x[0] <= land[0] + 1.5]
            slide = max([hdist(x[ri], land[ri]) for x in post] or [None]) if post else None
            steps = [dist(rows[i][ri], rows[i - 1][ri]) for i in range(1, len(rows))]
            before = max([hdist(x[ri], j0) for x in walk0] or [None]) if (walk0 and j0) else None
            res[name] = {'air_frames': len(air), 'top_dz_cm': r(max([x[ri][2] for x in air] or [0.0]) - j0[2], 1) if (air and j0) else None,
                         'air_s': r(land[0] - j, 3) if land else None, 'land_miss_cm': r(miss, 1) if miss is not None else None,
                         'slide_cm': r(slide, 1) if slide is not None else None, 'post_frames': len(post),
                         'post_walking': bool(post) and all(x[mi] == 'MOVE_WALKING' for x in post),
                         'max_step_cm': r(max(steps), 1) if steps else None, 'walk_drift_before_cm': r(before, 1) if before is not None else None,
                         'end': (rows[-1][ri], rows[-1][mi]) if rows else None}
        both = [dist(x[1], x[2]) for x in trk if j is not None and j <= x[0] <= j + 3.2 and x[1] and x[2]]
        seg = self.log_between('g8_jump', None) or ''
        corr = {'client': seg.count('*** Client: Error for'), 'server': seg.count('*** Server: Error for')}
        ok = (self.D.get('j_v') or 0.0) >= 15.0 and bool(self.D.get('pt', {}).get('traced'))
        for name in ('server', 'client'):
            q = res.get(name) or {}
            ok = ok and q.get('air_frames', 0) >= 5 and q.get('land_miss_cm') is not None and q['land_miss_cm'] <= 400.0 \
                and q.get('slide_cm') is not None and q['slide_cm'] <= 50.0 and q.get('post_frames', 0) >= 10 and q.get('post_walking')
        self.check('T8.7_client_deck_jump_L', 'PASS' if ok else 'FAIL', 'the client on ship 1\'s planks 1.5 m behind the helm (hull %s, traced %s), the host '
                   'flies it (Classic, throttle 1); at %s m/s the client jumps (ACharacter::Jump on its own copy). Each copy in its own hull\'s '
                   'space: server copy %s; the client\'s own copy %s (want on both: in the air, back on the deck walking within 400 cm of the '
                   'take-off point in xy (as T8.7 S), at most 50 cm from the landing point in the next 1.5 s (as T8.8 S)); the two copies %s cm '
                   'apart during the jump; movement corrections logged in this phase (the teleport at its start included): %s' % (
                       self.D.get('pt', {}).get('hull'), self.D.get('pt', {}).get('traced'), self.D.get('j_v'), res.get('server'), res.get('client'),
                       stats(both), corr), {'res': res, 'jump': self.D.get('j_info'), 'track': [x for x in trk if j is not None and x[0] >= j - 0.1][:100]})

    def ph_g6_hold(self, el):
        s, c = self.ship2_s, self.ship2_c
        t = self.tele(s)
        self.D['trk'].append((r(el, 3), int(fnum(t.get('UnpilotedMode'), -1)), r(self.loc(s), 1), r(self.loc(c), 1), r(fnum(t.get('ForwardSpeedMS')), 3), r(self.now, 3)))

    def end_g6_hold(self):
        orig = (self.orig.get('settings') or {}).get('DriftSpeed', 250.0)
        self.scmd('Aura.Airship.Set Settings.DriftSpeed %s' % orig)
        g = self.carry.get('g6') or {}
        trk = g.get('trk') or []
        ex = next((x[0] for x in trk if x[1] == 2), None)
        drift = [x for x in trk if x[1] == 2 and x[2] is not None and x[3] is not None]
        dv = [abs(x[2] - x[3]) for x in drift]
        err_raw = [x[4] for x in drift]
        # The client copy (a simulated proxy once the client is on foot) shows the server's path shifted in time: at 40 m/s
        # a frame is 133 cm. Its error is measured against the server's position k frames earlier, k = -4..4 (negative: the
        # server k frames LATER), the best k reported: a copy that drifts off its own way still shows, a time offset doesn't.
        # Both signs: in one PIE process the client reads the server's end-of-frame state and then steps its own physics
        # once in the same frame, so it reads ONE FRAME AHEAD of the server (fix2 run 2026-11-25: 140 cm ahead at 41 m/s,
        # 46 cm at 12 m/s, i.e. 34-37 ms at every speed, sideways 0.1 cm; k = 0..4 only looked behind and read 145 cm).
        # The cross-track error (the client's offset from the server's position, minus its part along the server's own
        # direction of travel) is reported as well: it does not depend on the time offset.
        idx = dict((id(x), i) for i, x in enumerate(trk))
        lagged = {}
        for k in range(-4, 5):
            e = []
            for x in drift:
                i = idx[id(x)]
                if 0 <= i - k < len(trk) and len(trk[i - k]) > 7 and trk[i - k][7] is not None and x[8] is not None:
                    e.append(dist(trk[i - k][7], x[8]))
            if len(e) >= max(10, len(drift) // 2):
                lagged[k] = e
        kbest = min(lagged, key=lambda k: (max(lagged[k]), abs(k))) if lagged else None
        err_d = lagged[kbest] if kbest is not None else err_raw
        xtrack = []
        for x in drift:
            i = idx[id(x)]
            if 0 < i < len(trk) - 1 and trk[i - 1][7] is not None and trk[i + 1][7] is not None and x[7] is not None and x[8] is not None:
                dv3 = [trk[i + 1][7][k] - trk[i - 1][7][k] for k in range(3)]
                n = math.sqrt(sum(v * v for v in dv3))
                if n > 1.0:
                    u = [v / n for v in dv3]
                    o = [x[8][k] - x[7][k] for k in range(3)]
                    a = sum(o[k] * u[k] for k in range(3))
                    xtrack.append(math.sqrt(max(0.0, sum(v * v for v in o) - a * a)))
        tg = sorted(set(round(x[5], 2) for x in drift if x[5] is not None))
        ok1 = (ex is not None and ex <= 1.0 and g.get('foot_t') is not None and not g.get('fb') and bool(drift) and mean(dv) <= 0.3 and bool(err_d) and max(err_d) <= 100.0
               and (g.get('v_exit') or 0) > 1.0 and tg and abs(tg[0] - 2.5) <= 0.01)
        self.check('T9.7_drift_after_client_exit', 'PASS' if ok1 else 'FAIL', 'client pilot F (IA_AirshipExit) at %s m/s%s: back on foot at %s s; server '
                   'mode Drift at %s s (want <= 1), drift target %s m/s (want 2.5); the client copy\'s forward speed vs the server\'s |diff| %s m/s (want '
                   'mean <= 0.3), position error %s cm against the server %s frames earlier (negative: later; want max <= 100: the same path; '
                   'same frame %s; per k max %s), cross-track %s cm. The drift bit itself (RepInput) is not readable from Python' % (
                       g.get('v_exit'), ' FALLBACK console Exit' if g.get('fb') else '', g.get('foot_t'), ex, tg, stats(dv), stats(err_d), kbest, stats(err_raw),
                       dict((k, r(max(v), 1)) for k, v in sorted(lagged.items())), stats(xtrack)),
                   {'track': trk[::10], 'best_k': kbest, 'cross_track': stats(xtrack)})
        h = self.D['trk']
        ds_abs = self.carry.get('g6_ds0')
        # the time from the DriftSpeed 0 command to the first Hold frame (mode 3), across the end of g6_drift and g6_hold
        modes = [(x[6], x[1]) for x in trk] + [(x[5], x[1]) for x in h]
        t_hold = next((t for t, m in modes if ds_abs is not None and t >= ds_abs - 1e-6 and m == 3), None)
        dt_hold = (t_hold - ds_abs) if t_hold is not None else None
        win = [x for x in h if x[0] >= 2.0]
        mv_s = max((hdist(x[2], win[0][2]) for x in win), default=None) if win else None
        mv_c = max((hdist(x[3], win[0][3]) for x in win), default=None) if win else None
        err = [dist(x[2], x[3]) for x in win]
        ok2 = (dt_hold is not None and dt_hold <= 1.5 and mv_s is not None and mv_s < 50.0 and mv_c < 50.0 and max(err) <= 100.0
               and win[-1][1] == 3)
        self.check('g6_hold_after_drift', 'PASS' if ok2 else 'FAIL', 'Settings.DriftSpeed 0 at %s s of g6_drift (the ship slow already %s): Hold %s s '
                   'after the command (want <= 1.5); from 2 s into g6_hold the server ship moved %s cm, the client copy %s cm (want < 50 both), '
                   'server vs client %s cm, final mode %s (want 3); DriftSpeed restored to %s' % (
                       g.get('ds0'), g.get('ds0_slow'), r(dt_hold, 2) if dt_hold is not None else None, r(mv_s, 1) if mv_s is not None else None,
                       r(mv_c, 1) if mv_c is not None else None, stats(err), win[-1][1] if win else None, orig), {'track': h[::6]})

    # ================================================================ g9_: a gunner's dismount with an old move clock
    def stamp_probe(self, tag, el, t0):
        """the client's move time stamp as the server accepts it: LogNetPlayerMovement VeryVerbose in the server world from
        t0 for 0.4 s, then the last "TimeStamp x Accepted! ... Pawn: <the client's character>" line. None while it runs,
        then (stamp or None, the phase time of that line, lines found)"""
        P = self.D.setdefault('probe_' + tag, {})
        if el >= t0 and 'a' not in P:
            P['a'] = el
            self.log_mark(tag + '_a')
            self.scmd('Log LogNetPlayerMovement VeryVerbose')
        if 'a' in P and el >= P['a'] + 0.4 and 'b' not in P:
            P['b'] = el
            self.scmd('Log LogNetPlayerMovement Log')
        if 'b' in P and el >= P['b'] + 0.6 and 'res' not in P:
            self.log_mark(tag + '_b')
            txt = self.log_between(tag + '_a', tag + '_b') or ''
            name = self.cchar_s.get_name()
            got = [float(m.group(1)) for m in _re.finditer(r'TimeStamp ([0-9.]+) Accepted! CurrentTimeStamp: [0-9.]+ Pawn: (\S+)', txt)
                   if m.group(2) == name]
            P['res'] = (got[-1] if got else None, P['b'], len(got))
        return P.get('res')

    def start_g9_clock(self):
        self.ensure_roles('foot', 'foot')
        self.D['st'] = 'roles'
        self.D['modes'] = {'server': [], 'client': []}

    def g9_rel(self):
        return (self.rel(self.ship1_s, self.loc(self.cchar_s)), self.rel(self.ship1_c, self.loc(self.cchar_c)))

    def ph_g9_clock(self, el):
        s, D = self.ship1_s, self.D
        st = D['st']
        if st == 'roles':
            if el >= 1.0 and (not self.croles or self.croles.get('done')):
                self.tship(s, SPAWN, 0.0)
                p, traced = self.near_seat_point(s, 0, self.cchar_s)
                D['pt'] = {'hull': r(self.rel(s, p), 0), 'traced': traced}
                self.tp_client(p, self.yaw(s) - 90.0)
                D['st'], D['t'] = 'probe1', el + 0.5
        elif st == 'probe1':
            res = self.stamp_probe('g9_p1', el, D['t'])
            if res is not None:
                D['p1res'] = res
                if res[0] is None:
                    wait = 126.0
                    self.line('WARN', 'g9: no "TimeStamp ... Accepted!" line for %s in 0.4 s of VeryVerbose: waiting 126 s blind' % self.cchar_s.get_name())
                else:
                    now_stamp = res[0] + (el - res[1])
                    # past 125 s and at least 35 s before the wrap at 240 (the mount, 3 s on the gun, the walk)
                    wait = (126.0 - now_stamp) if now_stamp < 126.0 else (0.0 if now_stamp <= 205.0 else (240.0 - now_stamp) + 126.0)
                    self.line('INFO', 'g9: the client\'s move time stamp is %.1f s now (%d lines): mounting in %.1f s' % (now_stamp, res[2], wait + 2.5))
                D['wait'] = r(wait, 1)
                D['st'], D['t'] = 'wait', el + wait
        elif st == 'wait':
            if el >= D['t']:
                D['st'], D['t'] = 'probe2', el
        elif st == 'probe2':
            res = self.stamp_probe('g9_p2', el, D['t'])
            if res is not None:
                D['stamp'] = r(res[0] + (el - res[1]), 1) if res[0] is not None else None
                D['st'] = 'mount'
        elif st == 'mount':
            if 'f' not in D:
                D['f'] = el
                self.inject('client', 'IA_AirshipBoard')
                self.event('inject', what='IA_AirshipBoard (client, near L1, move time stamp %s s)' % D.get('stamp'))
            if same(self.gunner(s, 0), self.cchar_s):
                D['mounted'] = el
                D['st'] = 'mounted'
            elif el >= D['f'] + 1.5:
                D['fail'] = 'the client\'s F did not man L1 in 1.5 s'
                D['st'] = 'done'
        elif st == 'mounted':
            if el >= D['mounted'] + 3.0:
                self.log_mark('g9_exit')
                self.inject('client', 'IA_AirshipExit')
                self.event('inject', what='IA_AirshipExit (client gunner, old clock)')
                D['x'] = el
                D['st'] = 'exit'
        elif st == 'exit':
            if 'x_srv' not in D:
                if self.gunner(s, 0) is None:
                    D['x_srv'] = el
                elif el >= D['x'] + 1.5:
                    D['fail'] = 'the client\'s F did not leave L1 in 1.5 s'
                    D['st'] = 'done'
            else:
                for key, c in (('server', self.cchar_s), ('client', self.cchar_c)):
                    cm = gp(c, 'character_movement', 'CharacterMovement')
                    if cm:
                        md = en(cm.get_editor_property('movement_mode'))
                        if not D['modes'][key] or D['modes'][key][-1] != md:
                            D['modes'][key].append(md)
                t = el - D['x_srv']
                if t >= 1.0 and 'p0' not in D:
                    D['p0'] = self.g9_rel()
                if 'p0' in D and t < 2.5:
                    self.look('client', self.yaw(s), -8.0)
                    self.inject('client', 'IA_Move', (1.0, 0.0, 0.0))
                if t >= 3.2:
                    D['p1'] = self.g9_rel()
                    D['fin'] = (self.char_info(self.cchar_s, s), self.char_info(self.cchar_c, self.ship1_c))
                    D['st'] = 'done'
        if D['st'] == 'done' and 'ended' not in D:
            D['ended'] = el
            self.phases[self.pi] = (self.phase, el)      # ends the phase in this tick

    def end_g9_clock(self):
        D = self.D
        self.scmd('Log LogNetPlayerMovement Log')
        p0, p1 = D.get('p0'), D.get('p1')
        mv = (r(hdist(p0[0], p1[0]), 1), r(hdist(p0[1], p1[1]), 1)) if p0 and p1 else (None, None)
        seg = self.log_between('g9_exit', None) or ''
        # A move refused because of the clock: the reset branch ("Before TimeStamp Reset"), or a stamp more than 1 s from the
        # server's copy of the clock. Not counted (first run on the fixed build, 2 lines, at the W press and its release): a
        # stamp one frame (0.033 s) behind the server's copy. That is the engine's own resend of an important move it has
        # already processed (the "old move" of a packed move goes through ServerMove_PerformMovement and is logged the same
        # way, at Log level); nothing is lost with it, the two copies walked the same distance.
        exp, near = [], []
        for l in seg.splitlines():
            if 'TimeStamp expired' not in l:
                continue
            m = _re.search(r'ServerMove: TimeStamp expired: ([0-9.]+), CurrentTimeStamp: ([0-9.]+)', l)
            if 'Before TimeStamp Reset' in l or m is None or abs(float(m.group(1)) - float(m.group(2))) > 1.0:
                exp.append(l.strip()[-150:])
            else:
                near.append(r(float(m.group(1)) - float(m.group(2)), 3))
        stamp = D.get('stamp')
        ok = (not D.get('fail') and stamp is not None and stamp >= 121.0 and mv[0] is not None and mv[0] >= 100.0 and mv[1] >= 100.0 and not exp)
        self.check('T5.8b_dismount_old_clock_L', 'PASS' if ok else 'FAIL', 'the client on ship 1\'s planks near L1 (%s); its move time stamp %s s at the '
                   'mount (read from the server\'s log; want >= 121: more than half of the 240 s between two resets; the phase waited %s s for '
                   'it); F mans L1, 3 s on the gun, F again%s: station free on the server %s s after it; from 1 s later W for 1.5 s moved the '
                   'server\'s copy %s cm and the client\'s own copy %s cm in hull space (want >= 100 both); movement modes after the dismount server '
                   '%s client %s; moves the server refused because of the clock after the dismount ("TimeStamp expired" with the reset branch '
                   'or a stamp more than 1 s off): %d (want 0)%s; resends of a move already processed (a stamp within 1 s behind, the engine\'s '
                   'old-move path, not counted): %d %s' % (
                       D.get('pt'), stamp, D.get('wait'), (' [%s]' % D['fail']) if D.get('fail') else '',
                       r(D['x_srv'] - D['x'], 2) if 'x_srv' in D and 'x' in D else None, mv[0], mv[1], D['modes']['server'], D['modes']['client'],
                       len(exp), (': ' + ' | '.join(exp[:2])) if exp else '', len(near), near[:6]),
                   {'near_expired_s': near, 'stamp': stamp, 'probe1': D.get('p1res'), 'moved': mv, 'final': D.get('fin'), 'expired': exp[:6], 'expired_n': len(exp), 'modes': D['modes']})

    # ================================================================ g7_: lethal crew share
    def near_seat_point(self, ship, st, c, d_cm=200.0):
        """a deck point d_cm from station st's seat on its helm side (open planks, as g1_mount): F there mans that station"""
        seat, helm = self.seat_local(ship, st), self.helm_local(ship)
        d = [seat[0] - helm[0], seat[1] - helm[1]]
        n = math.hypot(*d) or 1.0
        return self.deck_point(ship, seat[0] - d[0] / n * d_cm, seat[1] - d[1] / n * d_cm, c)

    def hull_bullet(self, ship, damage):
        """a sentinel test bullet from 37 m to port into ship's hull side (a PA_Airship box; the Mesh's collision stays on
        since the hull's own ignores Visibility, as T3.1): the ship's damage lands in the swarm's tick, so the crew share's
        eject / dismount send their RPCs to the client (a console Aura.Airship.Damage from Python runs them under the editor
        script guard: local only)"""
        frm, to = self.hull_side_line(ship)
        self.D['line'] = self.trace(self.sw, frm, to)
        self.bullet(frm, to, '%.0f' % damage)

    def restore_mesh(self, ship):
        if 'mesh_coll' in self.D and not self.D.get('mesh_back'):
            self.D['mesh_back'] = True
            ship.get_editor_property('Mesh').set_collision_enabled(self.D['mesh_coll'])

    def start_g7_k1(self):
        self.ensure_roles('foot', 'foot')
        s = self.ship2_s
        ph, _ = self.deck_point(s, -300.0, 300.0, self.hchar)
        self.tp_host(ph, self.yaw(s))
        pc_, _ = self.near_seat_point(s, 0, self.cchar_s)
        self.tp_client(pc_, self.yaw(s) - 90.0)
        self.D['trk'] = []

    def ph_g7_k1(self, el):
        s = self.ship2_s
        if el >= 0.4 and 'b' not in self.D:
            self.D['b'] = True
            self.scmd('Aura.Airship.Board 0')
        if el >= 0.6 and 'm' not in self.D:
            self.D['m'] = True
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client, at L1 of ship 2)')
        if el >= 1.4 and 'mchk' not in self.D:
            self.D['mchk'] = True
            if not same(self.gunner(s, 0), self.cchar_s):
                self.D['mfb'] = True
                self.scmd('Aura.Airship.Mount %d 0' % self.cidx)
                self.line('WARN', 'the client\'s F did not man L1 of ship 2 in 0.8 s: fallback Aura.Airship.Mount (the client is not told)')
        if el >= 1.6 and 'low' not in self.D:
            self.D['low'] = True
            self.set_health(self.hchar, 10.0)
            self.set_health(self.cchar_s, 10.0)
        if el >= 2.2 and 'pre' not in self.D:
            self.D['pre'] = {'host_pilot': same(s.get_pilot(), self.hchar), 'client_gunner': same(self.gunner(s, 0), self.cchar_s),
                             'h_host': self.health(self.hchar), 'h_client_s': self.health(self.cchar_s), 'h_client_c': self.health(self.cchar_c),
                             'client_cmc_tick': (self.char_info(self.cchar_c) or {}).get('cmc_tick'), 'client_by_F': not self.D.get('mfb'),
                             'ship_hp': self.ship_hp(s)}
        if el >= 2.4 and 'dmg' not in self.D:
            self.D['dmg'] = el
            self.hull_bullet(s, 100.0)
        if el >= 4.0:
            self.restore_mesh(s)
        if 'dmg' in self.D:
            par_s = self.cchar_s.get_attach_parent_actor() if valid(self.cchar_s) else None
            par_c = self.cchar_c.get_attach_parent_actor() if valid(self.cchar_c) else None
            self.D['trk'].append({'el': r(el, 3), 'host_pawn_char': same(self.hpc.get_controlled_pawn(), self.hchar), 'pilot': bool(s.get_pilot()),
                                  'h_host': self.health(self.hchar), 'gunner0': same(self.gunner(s, 0), self.cchar_s), 'att_s': par_s.get_name() if par_s else None,
                                  'h_cs': self.health(self.cchar_s), 'att_c': par_c.get_name() if par_c else None, 'h_cc': self.health(self.cchar_c),
                                  'dead': bool(s.is_airship_dead())})

    def first_dead(self, trk, key):
        return next((x for x in trk if x.get(key) is not None and x[key] <= 0.0), None)

    def end_g7_k1(self):
        self.restore_mesh(self.ship2_s)
        pre, trk = self.D.get('pre') or {}, self.D.get('trk') or []
        fs = self.first_dead(trk, 'h_cs')
        fc = self.first_dead(trk, 'h_cc')
        fh = self.first_dead(trk, 'h_host')
        last = trk[-1] if trk else {}
        ok = (pre.get('client_gunner') and pre.get('client_by_F') and fs is not None and not fs['gunner0'] and fs['att_s'] is None and fc is not None
              and fc['att_c'] is None and fc['el'] - fs['el'] <= 1.0 and not last.get('dead'))
        self.check('T4.3_gunner_lethal_share_client', 'PASS' if ok else 'FAIL', 'client gunner on L1 of ship 2 (manned by its F %s, its CMC ticking %s) at %s '
                   'health, a 100 test bullet into ship 2\'s hull (share %.1f; first hit on the line %s): first server frame dead %s (want station free '
                   'and detached there: dismounted first); first client frame dead %s (want detached, within 1 s); ship 2 alive %s' % (
                       pre.get('client_by_F'), pre.get('client_cmc_tick'), pre.get('h_client_s'), 100.0 * self.share, (self.D.get('line') or {}).get('actor'),
                       fs, fc, not last.get('dead')), {'pre': pre, 'track': trk[::3]})
        ok2 = (pre.get('host_pilot') and fh is not None and fh['host_pawn_char'] and not fh['pilot'] and not last.get('dead'))
        self.check('T4.2_pilot_lethal_share_host', 'PASS' if ok2 else 'FAIL', 'host pilot of ship 2 at %s health, the same 100 bullet: first frame dead %s '
                   '(want the host\'s PC on its character and no pilot there: ejected first); ship alive %s' % (pre.get('h_host'), fh, not last.get('dead')))

    def start_g7_resp(self):
        self.D['old'] = (self.cchar_s, self.cchar_c, self.hchar)

    def ph_g7_resp(self, el):
        old_s, old_c, old_h = self.D['old']
        for key, pc, old in (('cs', self.rpc, old_s), ('cc', self.cpc, old_c), ('h', self.hpc, old_h)):
            if key in self.D:
                continue
            try:
                p = pc.get_controlled_pawn()
                if valid(p) and isinstance(p, unreal.Character) and not same(p, old) and (self.health(p) or 0.0) > 0.0:
                    self.D[key] = (el, p)
            except Exception:  # noqa: BLE001
                self.err('respawn_' + key)

    def end_g7_resp(self):
        got = dict((k, self.D[k][0]) for k in ('cs', 'cc', 'h') if k in self.D)
        if 'cs' in self.D:
            self.cchar_s = self.D['cs'][1]
        if 'cc' in self.D:
            self.cchar_c = self.D['cc'][1]
        if 'h' in self.D:
            self.hchar = self.D['h'][1]
        self.hchar_c = self.host_on_client() if valid(self.cchar_c) else None
        ok = 'cs' in self.D and 'cc' in self.D
        self.check('setup_respawn', 'PASS' if ok else 'FAIL', 'respawned characters (GameMode, RespawnDelay 5 s), phase seconds: %s (want the client on '
                   'both machines; the host as well for later use)' % got)

    def start_g7_k2(self):
        self.D['trk'] = []
        if not (valid(self.cchar_s) and valid(self.cchar_c)):
            self.D['skip'] = True
            return
        self.tp_client(self.board_point(self.ship2_s, self.cchar_s), self.yaw(self.ship2_s))

    def ph_g7_k2(self, el):
        if self.D.get('skip'):
            return
        s = self.ship2_s
        if el >= 0.3 and 'x' not in self.D:
            self.D['x'] = True
            if s.has_pilot():
                self.scmd('Aura.Airship.Exit 0')
        if el >= 0.6 and 'b' not in self.D:
            self.D['b'] = True
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (respawned client, ship 2 deck)')
        if el >= 1.3 and 'bchk' not in self.D:
            self.D['bchk'] = True
            if not same(s.get_pilot(), self.cchar_s):
                self.D['bfb'] = True
                self.scmd('Aura.Airship.Board %d' % self.cidx)
                self.line('WARN', 'the respawned client\'s F did not take ship 2\'s helm in 0.7 s: fallback Aura.Airship.Board (no ClientRestart)')
        if el >= 1.6 and 'low' not in self.D:
            self.D['low'] = True
            self.set_health(self.cchar_s, 10.0)
        if el >= 2.2 and 'pre' not in self.D:
            self.D['pre'] = {'client_pilot': same(s.get_pilot(), self.cchar_s), 'client_pawn_ship': same(self.cpc.get_controlled_pawn(), self.ship2_c),
                             'h_s': self.health(self.cchar_s), 'h_c': self.health(self.cchar_c), 'by_F': not self.D.get('bfb'),
                             'imc_client': self.imc_on(self.sub_c)}
        if el >= 2.4 and 'dmg' not in self.D:
            self.D['dmg'] = el
            self.hull_bullet(s, 100.0)
        if el >= 4.0:
            self.restore_mesh(s)
        if 'dmg' in self.D:
            self.D['trk'].append({'el': r(el, 3), 'srv_pawn_char': same(self.rpc.get_controlled_pawn(), self.cchar_s),
                                  'cli_pawn_char': same(self.cpc.get_controlled_pawn(), self.cchar_c), 'pilot': bool(s.get_pilot()),
                                  'h_cs': self.health(self.cchar_s), 'h_cc': self.health(self.cchar_c), 'dead': bool(s.is_airship_dead())})

    def end_g7_k2(self):
        self.restore_mesh(self.ship2_s)
        if self.D.get('skip'):
            self.check('T4.2_pilot_lethal_share_client', 'FAIL', 'no respawned client character: not run')
            return
        pre, trk = self.D.get('pre') or {}, self.D.get('trk') or []
        fs = self.first_dead(trk, 'h_cs')
        fc = self.first_dead(trk, 'h_cc')
        last = trk[-1] if trk else {}
        cli_on_char = next((x['el'] for x in trk if x['cli_pawn_char']), None)
        ok = (pre.get('client_pilot') and pre.get('by_F') and pre.get('client_pawn_ship') and fs is not None and fs['srv_pawn_char'] and not fs['pilot'] and fc is not None
              and cli_on_char is not None and cli_on_char - fs['el'] <= 1.0 and not last.get('dead'))
        self.check('T4.2_pilot_lethal_share_client', 'PASS' if ok else 'FAIL', 'the respawned client flies ship 2 (%s) at %s health, a 100 test bullet into its hull: '
                   'first server frame dead %s (want its PC on its character, no pilot: ejected first); the client\'s own PC on its character at %s s, '
                   'first client frame dead %s (want within 1 s of the server); ship alive %s' % (
                       pre, pre.get('h_s'), fs, cli_on_char, fc, not last.get('dead')), {'track': trk[::3]})


def write_r2mp_report(R):
    try:
        L = ['%s  armed %s  reason: %s  game %.1f s  wall %s s' % (R['version'], R['armed_utc'], R.get('reason'), R.get('game_t', 0), R.get('wall_s')),
             'cfg %s' % R.get('cfg'), 'play settings %s' % R.get('play_settings'), 'setup %s' % json.dumps(R.get('setup'), default=str),
             'mp %s' % json.dumps(R.get('mp'), default=str), '']
        cnt = {}
        for k, c in R['checks'].items():
            cnt[c['status']] = cnt.get(c['status'], 0) + 1
        L.append('checks: %s' % cnt)
        for k, c in R['checks'].items():
            L.append('%-5s %-42s %s' % (c['status'], k, c['summary']))
        L.append('')
        L.append('script errors: %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        L.append('hit_info read failures (break_hit_result is expected to fail in UE 5.8: to_tuple is the fallback): %s' % R.get('hit_info_err'))
        for k, v in R['errors'].items():
            L.append('--- %s\n%s' % (k, v['last'][-900:]))
        ls = R.get('log_scan') or {}
        L.append('log: %s' % dict((k, v['count']) for k, v in ls.items()))
        for k in ('corr_client', 'back_on_seat', 'ignore_checks', 'ts_expired', 'airship_warn', 'error', 'ensure', 'accessed_none'):
            for s in (ls.get(k) or {}).get('sample', [])[:4]:
                L.append('    %s: %s' % (k, s[:300]))
        L.append('log per phase: %s' % json.dumps(R.get('log_segments')))
        L.append('captures: %s' % [s['file'] for s in R.get('shots', [])])
        with open(os.path.join(MP2, 'r2mp_report.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        with open(os.path.join(MP2, 'r2mp_report.txt'), 'w') as f:
            f.write('report failed: %s' % traceback.format_exc())


_old60 = globals().get('AS60_RUN')
if _old60 is not None and _old60.phase not in ('finished',):
    print('an as_60 run is active (phase %s): stop it first (as_60x_stop.py)' % _old60.phase)
else:
    AS60_RUN = R60()
    _ok60 = AS60_RUN.arm()
    if not _ok60:
        AS60_RUN.restore()
        AS60_RUN.remove_temp()
        AS60_RUN.phase = 'finished'
    for _l in AS60_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_60s_status.py; results in Saved/Airship/round2_mp/)' if _ok60 else 'FAIL: not armed'))
