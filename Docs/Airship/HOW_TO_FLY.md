# How to fly the airship

Version 2 (2026-11-23, with the follow-up fixes to the gun lock and the parked free look). The ship has four control
schemes in one build. **Point & Fly is the default.** Classic (the v1 controls of 2026-11-22), Galleon and Sky Racer
are one console command away ("Switch schemes" below). How the schemes were built, tested and judged:
`controls/RESULTS.md`. Round 2 (2026-11-28, tested in PIE: `round2/RESULTS_A.md`) adds gunners at the cannons, two
front machine guns, bigger cannonballs, damage to the crew, and a ship that drifts or holds after you leave the helm.
You take the helm only at the wheel, you stay there when you leave it, and you walk on the planks: "Round 2" below.

## Try it

* Map: `/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest` (start platform, walls and a ground plane for cannon and
  crash tests). In any other map, `Aura.Airship.Spawn` (server console) puts a ship 60 m in front of and 15 m above
  player 0.
* Get onto the deck, walk up to the steering wheel and press **F** (gamepad **Y**) to take the helm. **F** again leaves
  it: you stay standing at the wheel. F anywhere else, on the deck, beside or under the hull, does nothing ("Getting
  aboard, the helm, the deck" below). Leave the helm while moving and the ship keeps drifting slowly ahead; leave it at
  rest and it stays where it is ("Round 2" below). Other players can stand and walk on the deck, and man the cannons and
  the two front machine guns.
* For a test without the climb: `Aura.Airship.Board` (server console) puts player 0 at the helm from anywhere.

## Point & Fly (the default)

Look where you want to go and the ship goes there. The camera's direction is the ship's heading: move the mouse and
the 52 m ship banks, swings round and settles on the new heading without overshooting. W and S drive, A and D
sidestep, so the ship moves like your character on foot. Hold the right mouse button to look around without steering
and to aim a broadside.

### Keys

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Steer: the camera's direction is the heading. The ship turns to it at up to 30-45 deg/s (35 at cruise) and stops on it. Camera pitch only aims: looking down never changes height | mouse | right stick |
| Drive. S slows firmly (about 1 g) while you move forward, then backs up slowly | W / S | left stick up / down |
| Sidestep (14 m/s, leaning 7 deg into it) | A / D | left stick left / right |
| Turn with keys: the heading turns at the ship's full turn rate and the camera follows | Q / E | D-pad left / right |
| Climb / sink (12 / 15 m/s). Let go and the ship stops within about 6 m and holds that height | Space / Left Ctrl or C | right / left trigger |
| Boost (uses boost fuel; each start costs 10, forward kick every 1.5 s at most) | Left Shift | A |
| Air brake (stops from 48 m/s in about 2.5 s). With a big turn still to come at speed: brake-drift (below) | X | B |
| Look around and aim (broadside mode, below); the ship holds its heading | hold right mouse | hold LB |
| Fire the cannons on the side the camera faces (each cannon reloads in 1.5 s; a cannon a gunner mans is theirs). One press, one broadside; held, it also arms the gun lock (below). With the camera within 50 deg of the bow, holding it fires the two front machine guns instead | left mouse | RB |
| Zoom the camera between 40 and 120 m | mouse wheel | D-pad up / down |
| Leave the helm | F | Y |

The keyboard alone works too: Q/E turn, A/D sidestep. The cannons turn up to 20 deg either way from the beam and aim
from -10 to +8.5 deg of elevation. They lob their balls on an arc and lift the barrels for the range by themselves:
put the crosshair on the target. Past about 240 m the arc is out of reach and the ball falls short.

### Camera modes

* **Steering** (right mouse button up). The camera is the heading, and it only moves when you move it. The heading can
  run up to 150 deg ahead of the nose: spin the mouse all the way round and the ship follows at its full turn rate
  instead of flipping at 180 deg.
* **Broadside** (right mouse button held). The camera is free and the ship keeps its heading. The view tightens (FOV
  -15 deg), the deck flattens (bank x 0.4), and Q/E turn the ship while the camera stays where it looks. Let go and
  the camera eases back onto the heading in about 0.7 s; moving the mouse during that steers at once.
* **Parked**. Below 3 m/s, with none of W/S, A/D, Q/E or Shift held (gamepad: left stick, D-pad left / right, A), the
  mouse only looks around and the heading holds, as on foot. Only those keys end it: the first of them turns the ship
  to where the camera looks. Space, Ctrl and X do not, so you can climb at a hover while looking around. A hit or a
  collision does not end it either, even when it pushes the ship past 3 m/s: the heading holds, the ship turns back to
  it, and the camera stays where you looked. Holding the right mouse button gives broadside mode, as in flight. Let go
  below 3 m/s and you are parked again; if a hit still has the ship moving faster, you are in steering mode, as after a
  broadside in flight, and it parks again once it is slower than 3 m/s.

### The gun lock (broadside mode)

While you hold Fire (left mouse / RB), and for 6 s after each broadside you fire, holding the right mouse button with
your aim 55-150 deg off the bow keeps your broadside on it. When the aim has been out of the guns' arc for 0.25 s and is
not coming back in, the ship swings (at most 45 deg/s) to keep its beam within 3 deg of your aim. The lock follows your
aim, not a target, so it swings the ship even with nothing under the crosshair. The HUD shows **LOCK** with an arrow
toward the swing, and a gamepad ticks. W then circles the target, and A/D close or open the range. Q/E override the
lock, and letting go of the right mouse button ends it. Without Fire held or a recent broadside, the right mouse button
is a plain look around and never swings the ship.

A press of Fire fires one broadside, or nothing while that side reloads. Holding it never fires again (press again
when the side shows READY), but it keeps the lock armed for as long as you hold it.

### What the HUD shows

Bottom left, the ship panel (as in v1): the HULL bar, BOOST fuel in %, speed (m/s), ALT (m above the ground) and the
PORT / STBD reload (READY, or a bar and seconds; the side the cannons face is the dark tag).

Over the view:

| Mark | Meaning |
|---|---|
| "+" at the centre | Steering mode: your heading. Faded while parked |
| Chevron | Where the bow points now, at the height of the "+" |
| Amber line from the chevron to the "+" | The turn still to come (shown above 3 deg, hidden while parked). The chevron flashes once when the ship arrives |
| Ring with two brackets (right mouse button held) | The guns. Solid ring: the aim is in the facing side's arc; dashed: out of the arc. In the arc, the ring fills in amber as that side reloads. Amber brackets: in the arc and loaded |
| LOCK tag under the ring | The gun lock is swinging the ship; the arrow shows which way |
| Strip at the top (right mouse button held) | The whole circle around the ship: the bow (triangle) at the centre, ticks every 30 deg, both guns' arcs as thick bars at the beams (the facing side amber when in arc and loaded), your aim as a ring, the heading as a diamond |
| Boarding hint | "LOOK = STEER · W/S DRIVE · A/D SIDESTEP · Q/E TURN" and "HOLD RMB / LB TO LOOK AROUND OR AIM · X / B IN A TURN: DRIFT": at least 8 s after boarding and until you have held the right mouse button once (at most 45 s), once per session |
| "HOLD RMB / LB TO LOOK" under the "+" | Shown when you steer with the camera more than 50 deg off the nose, until you have held the right mouse button once |

### Moves worth learning

1. **Look with the right mouse button.** A glance without it turns the ship. In a hairpin that costs a gate.
2. **Brake-turn.** For a reversal, look back and hold S down to about 30 m/s, then W: 180 deg in 5.1 s inside 112 m,
   against 5.6 s and 178 m flat out (bench).
3. **Brake-drift.** Above 8 m/s, flick the camera 40 deg or more off the nose and hold X. The hull slides round faster
   than it can turn (a 180 deg reversal: nose round in 4.1 s instead of 5.4, bench), and the slide ends by itself
   15 deg before the heading. A slide of 1.2 s or more gives a forward kick of up to 6 m/s when it ends, but only up
   to cruise speed (48 m/s), so drifting on a straight gains nothing. Let go of X as the slide ends: X still brakes.
4. **Drift broadside.** With a target ahead, flick the camera to put it on your beam and hold X, then hold the right
   mouse button and fire as the guns come round.
5. **Circle and fire.** Right mouse button on the target and fire: the lock keeps the broadside on it while W carries
   you round. Press Fire again each time the side is loaded (every 1.5 s); each broadside renews the lock's 6 s, and
   holding Fire keeps the lock on in between.
6. **Line up with Q/E.** In broadside mode Q/E turn the ship under a still camera, so you never lose the target.

## Round 2: gunners, machine guns, damage

These apply in every scheme.

### At a glance

* **Take the helm at the wheel.** Stand behind or beside the steering wheel and press F. Anywhere else F does nothing.
* **Leave in place.** F again: you stay standing behind the wheel and walk with the ship.
* **Man a gun.** Walk up to a cannon or a front machine gun and press F. Aim with the mouse, fire with the left button,
  F to leave.
* **What the driver fires.** Left mouse looking to a side: a broadside from the cannons nobody mans. Left mouse looking
  ahead (within 50 deg of the bow): the two front machine guns, if nobody mans them.
* **Crew damage.** When the ship is hit, the pilot and every gunner lose a quarter of that damage.
* **Drift.** Leave the helm while moving and the ship drifts on slowly (2.5 m/s); leave it at rest and it stays put.
* **Getting aboard.** Fly up with hover and boost (Space, Space, Space, then Shift + W), or jump or hover across from a
  platform at deck height.

### Manning a gun

Walk up to a cannon or one of the two machine guns on the narrow forward deck and press **F** within about 3.5 m of its
seat (beside the cannon's breech, behind the machine gun). You stay yourself: you stand at the gun, aim with your own
camera, and enemies can still target you. When you leave the gun you are put on the planks next to it.

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Aim: the gun follows your camera (a cannon within its 20 deg / -10..+8.5 deg arc; a machine gun from far out to the side to 30 deg across the bow, -20..+40 deg) | mouse | right stick |
| Fire. Cannon: one ball per press, 1.5 s reload. Machine gun: hold, 10 rounds a second, overheats after about 3 s and cools while you let go | left mouse | RB |
| Narrower view | hold right mouse | hold LB |
| Camera closer / farther | mouse wheel | D-pad up / down |
| Leave the gun | F | Y |

The gunner HUD shows the gun's name, its mark (where the gun really points; for a cannon, where its ball comes down
at your aim's distance), the reload or the heat (OVERHEAT), OUT OF ARC, the machine gun's health and the hull. Any
player can man any free gun, with or without a pilot aboard. The pilot's broadside fires only the cannons nobody mans;
the pilot's panel shows who mans what (GUNS row) and MANNED on a side with both cannons manned.

### The front machine guns

Two machine guns sit on the edges of the narrow forward deck. Each bullet does 4 hits of the character gun. They shoot
characters, ships, other machine guns, enemy cannonballs and sentinels, never your own ship or crew. Nobody on one: the
pilot fires both by holding the left mouse button with the camera within 50 deg of the bow. Each has 400 health; a
destroyed one burns, stops firing and throws its gunner off.

The sentinel swarm only goes for a ship that somebody drives, or for a player at one of its guns. On a driven ship one
bullet in four is aimed at a machine gun that still works (Project Settings > Game > Airship > Crew, "Swarm Turret Aim
Chance"; 0 = never), the rest at the middle of the hull. Every hit on the hull also costs the pilot and each gunner a
quarter of it. A gunner on a ship nobody drives is the swarm's target himself: most bullets hit him or his gun.

### Damage

* Cannonballs are 1 m across and have health: about 8 machine-gun bullets (or 30 character-gun hits) shoot one down in
  the air, and then it does no damage. A ball's splash reaches 6 m.
* Sentinel bullets now hurt ships and machine guns too.
* When the ship takes damage, its pilot and every gunner take a quarter of it. If that would kill someone, they are
  put on foot first and die there. Damage the pilot took while flying stays after leaving the helm.

### Getting aboard, the helm, the deck

* **The deck.** You walk on the planks now. Before, you stood on an invisible lid 1.2 to 2.9 m above them. The wheel,
  its pedestal, the cannons, the winches, the searchlight posts and the crates and barrels on the main deck are solid;
  the rails are not (you can walk off the edge). A walking player no longer pushes the hovering ship.
* **Taking the helm.** Stand behind or beside the wheel and press **F**. You must be within 1.5 m of the spot the pilot
  stands on (55 cm behind the wheel) and at deck height (within 1 m). In front of the wheel does not count. Both numbers
  are in Project Settings > Game > Airship (`HelmReach`, `HelmReachHeight`).
* **Leaving the helm.** **F** leaves you where you stood while driving, behind the wheel, facing the bow, and you walk
  with the ship. You are no longer moved 2.5 m to port, and you are not thrown. Only when the ship dies or is removed
  under you, or its damage would kill you, are you thrown clear as before.
* **Under or beside the hull, F does nothing.** There is no climb aboard. A hovering ship keeps its nozzles at least
  4 m above the ground, so its main deck is never lower than about 12.5 m over flat ground: 18.7 m in `L_AirshipTest`
  (the ship is placed 16 m up), 13.6 m for the ship placed in StartupMap. A jump reaches 1.76 m and the air jump
  3.5 m, so you cannot jump aboard from the ground.
* **How you get aboard: fly.** Space, Space at the top, Space again: you hover 3.5 m up. Now hold **Shift + W**: the
  boost flies you where you look, up as well. Fly up beside the ship, come in over the planks, let go, and press Space
  once more to drop out of the hover onto the deck. Then walk to the wheel and press F. Measured in PIE with these keys
  and nothing else: from the ground 15 m beside the parked ship to the helm, 5.4 s in the air, no mana used.
  * Shift on the ground does not fly: there the boost is a run at twice the walking speed. It flies only while you
    hover.
  * The flight is fast (up to 26 m/s) and you keep your speed when you let go. Steer against your motion to stop.
  * Hover alone moves level at 6 m/s for as long as you like (66 m in the test, no mana used), so from a platform at
    deck height or above you can also cross to the deck with Space, Space, Space and W.
  * The grapple does **not** take you aboard. Its rope refuses the ship (it hooks only world geometry, never a pawn).
  * In StartupMap the hex platform beside the ship (`BP_MyHexPlatform1`) has its top 3.5 m above the main deck and
    7.9 m from it. A running jump from its edge should land on the deck (about 9.8 m of reach for that drop, worked
    out from the measured jump and walking speed; not yet played there). Back up to the platform needs the hover and
    the boost.
* **The forward deck** (the machine guns) is 4.2 m above the main deck and has no stairs. The air jump does not reach
  it from the main deck, and F does not reach a machine gun from the main deck either. **Known limit:** on foot you
  get there only by hover and boost (as above). Stairs or a ladder come with the model detail pass after this PR. One
  way works today by accident: jump under the forward deck near a machine gun and press F at the top of the jump. The
  gun is then in range, you are put on it, and leaving it puts you on the forward deck.
* **Jumping on deck in flight.** A jump or air jump on the deck stays with the ship: you come down where you took off,
  at any speed, and a direction key turns only your own movement. Jump past the rail and you leave the ship with its
  speed. Hovering does not hold you to the ship: it flies on without you (read from the code, not flown yet).
* **You can be shot on deck.** Guns, machine guns and sentinel bullets now hit a player standing on the planks. Before,
  the invisible lid above the planks stopped them. Shots at the ship land on its hull, forward deck, pods, fans,
  rudder, cannons, wheel, winches and searchlights. Open structure, such as the truss under the forward deck, has no
  hit box: shots pass through it.

### After you leave the helm

* Moving faster than 1 m/s: the ship slows to 2.5 m/s and keeps drifting ahead on the same heading, engines idle,
  until a pilot boards or something is in its way, then it stops and holds there.
* At rest: it holds its spot and heading, without the slow creep it had before.
* Gunners on board don't change this.

## The other schemes

Classic, Galleon and Sky Racer share one key layout: A/D turn, Q/E strafe, and the mouse only looks. Only what
differs is listed.

### Classic (v1)

The controls as first built, kept exactly (`Aura.Airship.Scheme check` lists 0 differences). Against Point & Fly:

| Key | Classic |
|---|---|
| Mouse / right stick | Free look. The camera recentres behind the ship after 1.5 s without look input above 8 m/s |
| A / D (left stick left / right) | Turn; the ship banks into the turn |
| Q / E (D-pad left / right) | Strafe at 12 m/s |
| S | Backs up slowly (no firm slow-down) |
| X + A/D above 8 m/s | Drift. A drift of 1.2 s or more gives a 6 m/s kick when it ends (no speed cap) |
| Right mouse button / LB | Tighter view (FOV -15), and the camera does not recentre while it is held; nothing else |
| HUD | The panel only, no marks over the view |
| Feel | v1: the nose dips 16.5 deg at full throttle (20 on boost), a climb floats on 12 m past where you let go, the brake peaks at 4.3 g; no camera shake, FOV punches or rumble |

### Galleon

You are the captain: give speed orders and the ship holds them hands-off, which leaves you free to fight. Keys as
Classic, except:

| Key | Galleon |
|---|---|
| W / S (left stick up / down) | Engine telegraph. Each press rings one notch: ASTERN (12 m/s back), STOP, SLOW (14 m/s), HALF (28 m/s), FULL (full power, 48 m/s). The ship holds the ordered speed. Hold to step on (first repeat after 0.25 s, then every 0.15 s); holding never passes STOP, a fresh press does. Stick: past half way is a press |
| A / D | Helm: 26 deg/s at rest, 44 at 15 m/s, 34 at cruise, heeling up to 26 deg. Let go and the turn is taken off firmly ("meet her") |
| X | Air brake (2.3 g peak, 3.1 s from cruise), then the ordered speed comes back |
| X + A/D above 6 m/s | Stern swing: the stern slides round, with a small surge on the way out |
| Left Shift | FULL STEAM: full power plus boost while held (4.1 s from a full tank), then back to the order |
| Q / E | Sidle at 10 m/s |
| Space / Ctrl | Climb 10 / sink 13 m/s; stops about 4 m past where you let go |
| Mouse | Ship-relative camera: it turns with the ship. More than 55 deg off the bow is beam watch: the view stays on the beam until you look back within 40 deg. Otherwise it recentres slowly, 2 s after your last look input (above 8 m/s) |
| Right mouse button / LB | Broadside stations: the gun deck levels (bank x 0.2), the helm gives fine orders (x 0.5), FOV -18. Beam watch also gives stations for 6 s after each broadside you fire |
| Camera | Higher, farther and slower: an 80 m arm, zoom 50-140 m |
| HUD | The panel grows: the telegraph row (the ordered notch dark; STEAM while boosting), a speed rule (the fill is your speed, the hollow triangle the ordered speed), the HELM row (needle, deg/s, SWING and STATIONS tags), and FIRE on the facing side when the aim is in its arc and the guns are loaded |

### Sky Racer

Arcade speed: a hard launch, a fast planted turn, and a drift that charges a three-tier mini-turbo. Keys as Classic,
except:

| Key | Sky Racer |
|---|---|
| W / S | W: full drive (33 m/s after 2 s, 56 m/s top). S: a progressive brake while moving forward faster than 3 m/s (a tap costs about 1 m/s); below 3 m/s it backs up |
| A / D | Up to 50 deg/s at 16 m/s, 38 at top speed; banks 23 deg and levels itself when you let go |
| X | Brake (stops from 56 m/s in 2.9 s) |
| X + A/D (at least half way) above 15 m/s | **Drift.** The tail steps out and the ship slides round a tighter arc. It drives at full power whether W is held or not (hold S as well for a slower, tighter drift). A mini-turbo charges, faster the harder you steer into the turn: tiers I / II / III after 0.5 / 1.1 / 2.0 s at full steer. Let go of X to fire it: a kick of 3 / 5 / 7.5 m/s, a short burn and some boost fuel. Drift again within 2.5 s and the next turbo chains: +15 % per link, up to three links (x2-x4 on the HUD) |
| Left Shift | Boost burst: every press gives at least 0.5 s of boost and a 6 m/s kick; hold to extend |
| Space / Ctrl | Climb 13.5 / dive 16.5 m/s; stops within 1 s of letting go. Diving at speed adds forward speed |
| Q / E | Side slide at 14 m/s |
| Mouse | Free look. The chase camera takes over again 0.6 s after your last look input and looks into the turn |
| Right mouse button / LB | Gun deck: bank x 0.35, throttle x 0.6, brake x 0.3, turn x 0.8, FOV -14 |
| Camera | Lower and closer (54 m arm); the FOV widens with speed and punches on boost and turbo |
| Collisions | Forgiving: no damage below 7 m/s (Classic 4 m/s), less per hit |
| HUD | A DRIFT row (TURBO while it burns): the charge bar with the tier marks, I / II / III and the chain; the panel outline flashes on a release |

## At a glance (PIE pass 1, fixed 30 fps)

| | Point & Fly | Classic | Galleon | Sky Racer |
|---|---|---|---|---|
| Top speed / boost peak (m/s) | 48.0 / 86.9 | 48.0 / 88.0 | 47.8 / 88.2 | 56.4 / 92.5 |
| Time to 80 % of top speed (s) | 3.27 | 3.30 | 3.30 | 2.87 |
| Turn rate at cruise (deg/s) / time to 90 % of it (s) | 35.0 / 0.70 | 35.1 / 0.90 | 34.1 / 0.87 | 38.0 / 0.60 |
| Brake from cruise: stop time (s) / distance (m) | 2.47 / 57 | 2.17 / 39 | 3.07 / 57 | 2.87 / 72 |
| Climb / sink (m/s); overshoot after a 30 m climb (m) | 12.0 / 15.0; 5.7 | 12.0 / 15.0; 12.2 | 10.0 / 13.0; 4.0 | 13.6 / 16.5; 5.35 |
| Sidestep (m/s) | 14.3 | 12.2 | 10.1 | 14.2 |
| Nose dip at full throttle (deg) | -4.0 | -16.5 | -4.0 | -4.9 |
| Gate course, precise bot (s) | 58.9 | 59.8 | 61.0 | 49.0 |

Course times include a harness start offset of up to 0.7 s (Classic; `controls/PIE_RESULTS.md`). The final play test
of the polished Point & Fly (2026-11-23) measured the same values, the course included (58.93 s); what the polish
changed is a 1.7 deg stop after a fast turn (was 8.6) and a gun lock that keeps the target 4.7 deg aft of the beam (was
7.4): `controls/RESULTS.md` "Final play test".

## Switch schemes

| Scheme | Number |
|---|---|
| Classic (v1) | 0 |
| Galleon | 1 |
| Sky Racer | 2 |
| Point & Fly (default) | 3 |

* **Console** (server; not in shipping builds): `Aura.Airship.Scheme <0-3>` switches every ship in the world at once,
  even mid-flight, and replicates to every player. In PIE, open the console with the backtick key in the game window
  (with a listen server: in the host's window). `Aura.Airship.Scheme` alone prints each ship's scheme.
* **Details panel**: open `/Game/Assets/MyShip/Drivable/BP_AirshipPawn`, Class Defaults, Details, **Airship >
  Controls > Control Scheme**, to change the default of every ship of that Blueprint. On a ship placed in a level, the
  same property sets that one ship. It is applied at BeginPlay. Today neither `BP_AirshipPawn` nor `L_AirshipTest` sets
  it, so both use the C++ default, Point & Fly.
* **Blueprint**: **Set Control Scheme** (category Airship | Controls) on the ship, called on the server; a client's call
  only logs a warning. **Get Control Scheme** reads it.

A switch resets every scheme tuning value to the scheme's preset, so `Aura.Airship.Set` changes to those values last
until the next switch.

## Server console commands (not in shipping builds)

| Command | Does |
|---|---|
| `Aura.Airship.Spawn` | A ship 60 m in front of and 15 m above player 0 |
| `Aura.Airship.Board [player]` / `Aura.Airship.Exit [player]` | The player (default 0) takes the helm of the nearest free ship, from any distance (only the F key needs you at the wheel) / leaves it and stays at the wheel |
| `Aura.Airship.Damage <n>` / `Aura.Airship.Kill` | Every living ship takes n damage (the crew takes a quarter) / dies (the crew is ejected unhurt) |
| `Aura.Airship.Set <name> <value>` / `Aura.Airship.Get <name>` | Any ship property by name (the flight component; `Pawn.<name>`, `Anim.<name>`) |
| `Aura.Airship.Input <throttle> <steer> [lift] [strafe] [boost] [brake]` / `Aura.Airship.InputClear` | Flies every ship with fixed controls. Classic-style in every scheme (no heading target); under Galleon the throttle is the order: 1 FULL, 0.67 HALF, 0.33 SLOW, 0 STOP, -1 ASTERN |
| `Aura.Airship.Telemetry` | Logs each ship's flight values, its scheme state and its hull inertia |
| `Aura.Airship.Passengers` | Logs the characters riding a ship |
| `Aura.Airship.Debug 1` | Draws the forces and ground contacts |
| `Aura.Airship.RepMode 0/1` | The ship's network replication mode |
| `Aura.Airship.Scheme [0-3 \| check]` | 0-3: switch every ship's control scheme (server). No argument: print each ship's scheme. `check`: list every scheme tuning value that differs from the class defaults (0 right after `Aura.Airship.Scheme 0`) |
| `Aura.Airship.Mount <player> <station>` / `Aura.Airship.Dismount [player]` | **Round 2.** The player mans a gun of the nearest ship with it free (0-3 cannons L1, L2, R1, R2; 4-5 machine guns L, R) / leaves it |
| `Aura.Airship.TurretFire <0/1> [x y z]` | **Round 2.** The unmanned machine guns fire at the point (default 100 m ahead) / stop |
| `Aura.Airship.TurretDamage <0/1> <n>` / `Aura.Airship.StationFire <player> [x y z] [seconds]` | **Round 2.** Damage a machine gun / fire a player's gun at a point |
| `Aura.Airship.Set Settings.<name> <value>` | **Round 2.** A project setting of the airship on this machine (for example `Settings.DriftSpeed 0`) |

`Docs/Airship/CPP_NOTES.md` section 6 lists the arguments, section 14 the control-scheme code.
