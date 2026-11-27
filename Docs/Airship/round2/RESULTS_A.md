# Airship round 2, PR A: results

What was built for Talal's round-2 asks, how it was tested in PIE, the numbers it measured, and what is left open.
Branch `claude/project-thread-0emzt1` at 3a8c89e, on top of redo3 930c54f. Design and every decision: `SPEC_A.md`. Code
notes: `../CPP_NOTES.md` section 15. Editor scripts and run log: `NOTES_assets.md`. Player's guide: `../HOW_TO_FLY.md`
("Round 2").

Contents

1. What was built, ask by ask
2. Editor stage (assets)
3. PIE results (as_59 standalone, as_60 listen, as_62 real swarm, regression)
4. Measured numbers
5. Known limits and open items
6. How to test it yourself
7. Media

---

## 1. What was built, ask by ask

| # | Talal's ask | What PR A does |
|---|---|---|
| 1 | Two machine-gun turrets in front, 4x or 10x the character gun | Two turrets (`BP_AirshipTurret`, C++ `AAirshipTurret`) on the side edges of the narrow forward deck. Each bullet does 4x the character gun's hit (`TurretGunDamageMultiplier` 4, a project setting: 10 is one number away). 10 rounds a second, overheat after about 3 s, 400 health; a destroyed turret burns, stops and throws its gunner off. |
| 1, 7 | Bigger cannonballs with projectile motion, health, can be destroyed, AOE damage | Balls 1 m across (was 56 cm), launched at 70 m/s on a real arc (gravity x 0.6), aimed ballistically with lead for the ship's own speed. Each ball has 30 health in character-gun hits (8 turret bullets); a shot-down ball bursts in the air with no damage. Splash 6 m, falling to 30 % at the edge. |
| 2 | Cannons mountable; if one is manned, the driver controls only the other; driver, gunner and ship take damage, also from the swarm (find why it couldn't) | Any player can man any free cannon or turret with F. The pilot's broadside fires only the cannons nobody mans; Fire with the camera within 50 deg of the bow drives the unmanned turrets. Every hit on the ship also costs the pilot and each gunner a quarter of it (`CrewDamageShare` 0.25). Why the swarm could not hurt the ship: its bullets only swept the Pawn channel, and the hull is a PhysicsBody. Sentinel bullets now also trace Visibility against tagged ship parts (`BulletTargetTag`). |
| 3 | Cannons and guns mountable by the player | As above: gunner stations, own camera aim, HUD, F to leave. |
| 4 | Ship keeps drifting slowly after dismount | Leave the helm above 1 m/s: the ship slows to 2.5 m/s and drifts on its heading until something is in its way, then holds. Leave at rest: it holds its spot. Every scheme. |
| 5 | Wheel the size of the character | Wheel 140 cm across the handle tips (the mech is 141.6 cm tall), hub at chest height, pilot 55 cm behind it. |
| 6 | Remove marked geometry, make props like the cannons and the front lamp pipes movable | The five marked deck pieces are deleted from the mesh (hull ink repainted where they were). The cannons already aim and recoil; the new turrets turn and pitch. The lamp posts and searchlights stay as they are (lead decision, SPEC_A D7). |
| 8 | Cannon smoke keeps emitting; stop it within 1 s | The muzzle effect no longer loops and the C++ cuts its components after 1 s (`MuzzleFXMaxSeconds`). Measured: gone 0.87 s after the shot, with or without the C++ cap. |
| - | "Make a proper PA for ship" | `PA_Airship` rebuilt: 35 bodies, 143 boxes (103 for the hull, deck boxes meeting their neighbours, 7 for the crates and barrels on deck). Players walk on the planks; shots hit the deck parts. |
| - | "Swarms only attack the ship when driving" | The swarm targets a ship only while somebody drives it, or a player at one of its guns. A parked, empty ship takes nothing (measured 0 in 20-30 s). One driven-ship bullet in four aims at a working turret (`SwarmTurretAimChance` 0.25), else no swarm bullet could ever reach one. |
| - | 11-25: drive only when close enough to hold the wheel; on exit keep the position at the wheel; no climbing | F takes the helm only within 1.5 m of the pilot's standing spot and 1 m of deck height. F under or beside the hull does nothing. Leaving the helm leaves you exactly where you stood while driving (0.0 cm in the hull's plane), walking with the ship. |

Fixes found on the way (all in C++, all tested):

* **Jumping on a flying deck.** A jump from the deck now stays in the ship's frame: at 48 m/s the player lands 1 cm
  from the take-off point and does not slide (was 1.7 m forward). In `UMyCharacterMovementComponent`, only for bases
  that are simulating pawns (the airship); the ground, hex platforms and bridge parts behave as before.
* **Characters shoved the ship.** A character arriving on the planks knocked the hovering ship 3 to 5.5 m away (the
  mech's mesh and jet packs are kinematic bodies the hull blocked). Now 0.1 cm.
* **A remote gunner leaving a gun** with a move clock past 120 s stood frozen on the server for up to 2 minutes. Fixed
  (the server's prediction clock is reset at the dismount).
* **A ship destroyed under its pilot** now throws him clear.
* **A ship without physics-asset bodies** can still be boarded (helm reach measured from the deck stood on).

## 2. Editor stage (assets)

Run in a separate clone with the scripts of `../scripts/ue` (order and what each does: `NOTES_assets.md`). All PASS on
the final assets:

| Script | What it does | Result |
|---|---|---|
| as_51 | `NS_AirshipMuzzle` plays once | PASS |
| as_52-as_57 | Turret meshes, `BP_AirshipTurret`, muzzle / tracer / fire effects, `BP_AirshipCannonball` at 1 m, wheel and bore re-import | PASS (NOTES_assets.md) |
| as_11 + as_11b | `PA_Airship` rebuilt: 35 bodies, 143 boxes, 103 hull boxes | 11 PASS |
| as_13 | Control Rig eval after the bone moves | 145 / 145 |
| as_61 | Hull ink repainted where the 5 pieces were (`M_AirshipDrivable`, `T_AirshipDrivable_ComicLines`) | 21 PASS |
| as_58 | Verifies the whole round-2 asset state, compile check | 55 PASS, compile all_ok |

## 3. PIE results

All on the final build (`build_r2_160644.log`), map `L_AirshipTest`, Point & Fly unless stated, fixed 30 fps. Every
check prints its measured values; reports are kept in the clone's `Saved/Airship/round2_final_sa`, `round2_final_mp`
and `round2_final_swarm`.

| Suite | Mode | PASS | FAIL | INFO | SKIP | Log |
|---|---|---|---|---|---|---|
| as_59 round 2 | standalone | **55** | 0 | 4 | 13 | no error, no ensure |
| as_60 round 2 | listen server + 1 client | **43** | 0 | 1 | 9 | no error, no ensure (pre-existing "GiveAbility on the client" errors only) |
| as_62 real swarm | standalone, real sentinels | **20** | 0 | 1 | 1 | SW.log PASS |

### Every non-PASS line

| Suite | Check | Status | Why |
|---|---|---|---|
| as_59 | T1.3 muzzle captures | INFO | Pictures to look at, not a measurement (T1.1 measures the smoke's life) |
| as_59 | T5.16a / T5.16b gunner pose | INFO | Gunner's feet 8 cm (R1) and 7 cm (port turret) over the deck: reported only |
| as_59 | T7.3 deck capture | INFO | Pictures to look at |
| as_59 | T2.7, T4.3, T5.1-T5.5, T5.12, T5.13, T6.2, T6.3, T9.7 | SKIP | Need a second player: covered by as_60 |
| as_59 | T3.5, T6.7 | SKIP | No swarm in the standalone suite: covered by as_62 |
| as_59 | T3.4 | SKIP | `L_AirshipTest` has no untagged GAS enemy |
| as_59 | T4.5 | SKIP | Needs a second pilot firing at a manned station (2 players at once) |
| as_59 | T7.1 | SKIP | Blender checks, not PIE (they passed: 118 bones, 31 meshes) |
| as_60 | g4 bow-to-bow setup | INFO | Setup positions, reported only |
| as_60 | T_late_join | SKIP | Late join is not possible in PIE |
| as_60 | T5.11, T5.15, T8.1 | SKIP | Covered by the standalone suite |
| as_60 | T4.5, T2.8 | SKIP | Need 3 players at once; T2.8 is covered per role in as_59 and as_62 |
| as_60 | T3.5, T6.7, T7.x | SKIP | Swarm / Blender, covered elsewhere |
| as_62 | SW.d1 turret losses without a hold | INFO | Reported only (the held-sentinel check SW.d2 passes) |
| as_62 | SW.b_driven | SKIP | A gunner on a driven ship under the swarm needs a second player |

### Regression (older suites)

as_43 was re-run on the final build (2026-11-28). The other rows are from the build before the last two narrow fixes
(the turret station reach back to one value, the eject of a destroyed ship's pilot).

The final-build re-run of as_45 under Classic was stopped before it started, at Talal's request to keep testing lean;
its row is the result from the build before the last two narrow fixes, which do not touch the paths it checks.

| Suite | Build | Result | Non-PASS and why |
|---|---|---|---|
| as_43 v1 validation, Classic | final | 24 / 25 | `f2_boost_path`: +5.35 m/s upward bump after clipping an obstacle at 91.6 m/s against a 5.0 limit. The documented v1 crash bump, same as round 1 |
| as_45 multiplayer, Classic | before the last fixes | 22 / 22 | - |
| as_45 multiplayer, Point & Fly | before the last fixes | 18 / 22 | `b1_hud_board`, `e3_hud_host_flying`, `a3_keys_rpc`, `c_cannons`: the four v1-key checks that fail by design under Point & Fly (`../controls/RESULTS.md`) |
| Follow-up checks (as_50f) | before the last fixes | 7 / 9 | `p4_firehold`, `p4_tap60` fire no broadside: they press Fire in the frame the camera leaves the bow, where round 2 makes Fire drive the machine guns (on purpose). With `Settings.DriverTurretArcDeg 0`: 9 / 9 |
| `Aura.Airship.Scheme 0` + `check` | before the last fixes | 0 differences | Classic is still exactly v1 |

## 4. Measured numbers

From the final runs unless noted. "Gun" = one hit of the character's gun (`GE_GunShootDamage`).

**Machine-gun turrets**

| | Value |
|---|---|
| Damage per bullet | 4 x the gun. In this branch the gun does 1, so 4 (T6.8: 84 damage from 21 bullets). With Talal's local `GE_GunShootDamage` of 1000: 4000 per bullet |
| Fire rate | 10 rounds/s (11 shots in a 1.0 s hold, 21 in a 1 s `TurretFire` with both guns) |
| Heat | Overheat 2.9 s into a held trigger; no shots while overheated; firing again 1.2 s after letting go (heat 0.35) |
| Health | 400 each; a destroyed turret burns, stops firing and ejects its gunner (T6.6) |
| Aim | Spread 1 deg, range 250 m, pitch -20 to +40 deg; from far out to the side to 30 deg across the bow |
| Driver control | Fire with the camera within 50 deg of the bow (`DriverTurretArcDeg`); a client pilot's turrets fired 11 and 10 rounds in 1 s |
| Against sentinels (as_62) | 82 rounds: 68 damage events, 2 kills; in the earlier swarm run 106 rounds, 86 events, 3 kills |

**Cannonballs**

| | Value |
|---|---|
| Size | 1 m across (radius 50 cm), mesh scale 1 |
| Launch speed | 70 m/s from the muzzle (measured 69.98) |
| Gravity | x 0.6 |
| Range | About 244 m level at the 8.5 deg elevation cap. Past it the ball falls short (aim at 300 m: 8 to 12 m low) |
| Accuracy | Aim 150 m off the beam: impact 0.9 to 1.4 m from the aim, apex 3.2 to 3.3 m, 2.1 s flight. Ship at 30 m/s: 1.1 to 2.2 m |
| Damage | 60 per ball at the centre; splash 6 m, 30 % at the edge (measured 21.4 at 5.51 m, design 21.43) |
| Health | 30 gun hits, or about 8 turret bullets (a turret shot one down in 0.67 s, 7 rounds per gun). Shot down: bursts, no damage |
| Own crew | A ship's own splash hurts none of its rider, gunner, pilot or itself (T2.8, as_59 and as_62); a broadside into another ship 4.5 m away cost that ship 120 and ours 0 |
| On the real swarm | 3 balls at sentinels: 3 damage events; 7 bursting beside sentinels: 10 events, 2 kills |

**Smoke**: the muzzle effect is gone 0.87 s after the shot (T1.1: 2 components at +0.3 s, 0 at +1.5 s; 0 at +1.2 s
without the C++ cap, T1.2).

**Drift and hold after leaving the helm**

| | Value |
|---|---|
| Drift | Point & Fly, Galleon, Classic: exit at 46-47 m/s, 2.48 to 2.49 m/s from 30 s on, heading change 0.0 deg, no reverse thrust |
| Hold at rest | Moved 0.9 cm in 30 s |
| Toward a wall | Stops 7.3 m short and holds, no damage |
| Taking the helm again | Drift ends at once; 1.5 to 14 m/s in 1.2 s |
| Listen | A client pilot leaving at 40 m/s: the server's ship drifts at 2.5 m/s within 0.07 s; the client sees the same |

**Wheel vs character**: wheel 140 cm across the tips (vertex bounds), the mech 141.6 cm tall; hub at chest height,
the pilot's standing spot 55 cm behind it.

**Crew damage share**

| | Value |
|---|---|
| `Aura.Airship.Damage 100` | ship -100, pilot -25, gunner -25 (both machines) |
| Host's gun on a client-piloted ship | ship -9, pilot -2.25 |
| Sentinel bullet (3) | ship -3, pilot -0.75 |
| Real swarm, 5 sentinels, 30 s, driven | ship -195, pilot -48.75 (exactly 0.25 x) |
| Real swarm, 8 sentinels, 45 s, driven | ship -345, pilot -86.25 |
| Gunner on an undriven ship, 22 s | gunner -115.5 (108 direct from 36 hits, 7.5 share): he lasts about 21 s |
| Lethal share | at 10 health the pilot or gunner is put on foot first, then dies; the ship lives on |
| Balance | a 110-health pilot dies when the ship has lost 440 of its 2000 |

**Helm reach and exit**

| | Value |
|---|---|
| Helm reach | 150 cm horizontal from the pilot's standing spot, 100 cm in height (`HelmReach`, `HelmReachHeight`) |
| F at 195 cm | refused (standalone and from a listen client) |
| F at the spot | at the helm |
| F under the hull | nothing, 7.1 m and 12 m below the belly |
| Exit at rest | 0.0 cm from the driving pose in the hull's plane; settles 10.9 cm down onto the deck |
| Exit at 40 m/s (listen client) | 6.5 cm on both machines, no correction |
| Destroyed ship | the pilot is thrown clear (falling, 10.7 m/s up), health unchanged |

**Deck**

| | Value |
|---|---|
| Walker's feet over the deck boxes | 0.4 to 2.2 cm in flight; 2.1 cm at the wheel |
| Gunners' feet | 8 cm at cannon R1, 7 cm at the port turret |
| Walker carried at 53 m/s with a turn | moved at most 20 cm on deck, walking all the time |
| Jump at 49.7 m/s | lands 1 cm from take-off, then moves 5 cm (was 1.7 m slide) |
| Air jump with a side key at 48 m/s | 5 cm along the hull, 3 m to the side |
| Characters arriving on the planks | ship moves 0.1 cm (was 554 cm) |
| Shots at a player on deck | hit him (from above and from the side) |

**Getting aboard** (as_59 opt-in `t8_boost`, INFO, the game's keys only)

| | Value |
|---|---|
| Main deck over the ground in `L_AirshipTest` | 18.3 to 18.8 m |
| Forward deck over the main deck | 4.2 m |
| Jump / jump + air jump | 1.76 m / 3.53 m |
| Hover (Space x 3) | 3.5 m up, level at 6 m/s, no mana used |
| Hover + Shift + W | up to 26 m/s along the view; 20.8 m up after 1.4 s |
| Ground beside the ship to the helm | 5.4 s in the air, then W and F |

## 5. Known limits and open items

Talal's decisions:

* **Getting aboard** is by hover + boost (measured above) or from a platform at deck height. There is no climb, ladder
  or boarding from below, and the grapple does not take you aboard (it hooks only world geometry, never a pawn).
  In his StartupMap (read from disk, not played) the hex platform next to the ship is 7.9 m from the main deck and
  3.5 m above it: a running jump makes it (9.8 m of reach for that drop). Back up needs hover and boost.
* **The turret deck has no stairs or ladder.** The forward deck is 4.2 m above the main deck and F does not reach a
  turret from the main deck. Stairs or a ladder come with the model detail pass that follows this PR. Until then: hover
  and boost, or by accident a jump under the forward deck with F at its top.

Other limits:

* **The rails have no collision.** You can walk off the edge of the deck. Open structure (the truss under the forward
  deck) has no hit box either: shots pass through it.
* **Cannon smoke differs between editor sessions.** "Gone within 1 s" is measured (0.87 s). What the camera shows on
  the same build differs: orange-brown puffs at 0.1 s in the final run, a large grey cloud at 0.3 s in one earlier
  session, only sparks in two short runs; never anything at 1.2 s. Cause not found (a guess: the first shot after an
  editor start, before the effect's shaders are ready). Fire two broadsides in one session and look at the second.
* **Talal's local `GE_GunShootDamage` of 1000** makes one turret bullet (4000) destroy a ship and one gun hit a turret.
  Do not run the PIE suites with that value. PR B sets ship damage for matches.
* **Talal's empty local `PA_Airship`** conflicts with the rebuilt one when he pulls: take the branch's.
* **Hover does not keep you with the ship.** A hovering player is left behind by a moving ship (read from the code).
  The flight to the deck uses no mana (`GE_HoverCost`, `GE_BoostCost` exist but cost nothing in the test), and the
  character barely brakes in the air after a boost (13.9 m/s a second after letting go): steer against the motion.
* **Not covered by a test:** a client's air jump on a flying deck and deck jumps with lag; the hover or grapple started
  from a moving deck; a gunner on a driven ship under a real swarm; a real swarm against a flying (not hovering) ship;
  all three own-crew roles at once (each role alone passes); anything on StartupMap.
* **Balance first guesses:** `SwarmTurretAimChance` 0.25 (5 sentinels need about 11 minutes to destroy a turret, 30
  about 2; 0 switches it off), `CrewDamageShare` 0.25, ball health 30, turret 4x.
* **Side effect of the passenger fix:** a character standing on a platform inside the hull's box + 3 m has query-only
  collision while there, so simulated debris passes through it.
* **Follow-up checks `p4_firehold` / `p4_tap60`** keep failing on this build because of the bow arc (above). Left as
  written so the v1 check stays.
* **Cosmetic:** the host's own cannon barrel shows its gunner's aim one frame later than clients do.
* **Pre-existing:** "GiveAbility called on the client" errors when a client re-possesses its character.
* **No video in this PR's media:** every capture is a still from the test harnesses (the editor was in use for the
  regression re-run when the media was made).

## 6. How to test it yourself

Open `/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest` and press Play. Get on deck with Space, Space, Space and then
Shift + W (or use `Aura.Airship.Board`), walk to the wheel and press F. Keys: `../HOW_TO_FLY.md`.

Server console (backtick in the game window; with a listen server, in the host's window):

| Command | Does |
|---|---|
| `Aura.Airship.Spawn` | A ship 60 m ahead of and 15 m above player 0 |
| `Aura.Airship.Board [player]` / `Aura.Airship.Exit [player]` | Take the helm of the nearest free ship from anywhere / leave it in place |
| `Aura.Airship.Mount <player> <station>` / `Aura.Airship.Dismount [player]` | Man a gun: 0-3 cannons L1, L2, R1, R2; 4-5 turrets L, R / leave it |
| `Aura.Airship.TurretFire <0/1> [x y z]` | The unmanned turrets fire at a point (default 100 m ahead) / stop |
| `Aura.Airship.TurretDamage <0/1> <n>` | Damage a turret (400 destroys it) |
| `Aura.Airship.StationFire <player> [x y z] [seconds]` | Fire a player's gun at a point |
| `Aura.Airship.Damage <n>` / `Aura.Airship.Kill` | Damage every ship (the crew takes a quarter) / kill them |
| `Aura.Airship.Set Settings.<name> <value>` | Any airship project setting on this machine, e.g. `Settings.DriftSpeed 0`, `Settings.DriverTurretArcDeg 0`, `Settings.TurretGunDamageMultiplier 10`, `Settings.SwarmTurretAimChance 0` |
| `Aura.Airship.Telemetry` / `Aura.Airship.Passengers` | Log each ship's state (drift mode, crew health, stations) / the characters riding |
| `Aura.Airship.Scheme 0` then `Aura.Airship.Scheme check` | Classic, and the list of differences from v1 (0) |
| `Aura.MechSentinel.TestBullet` | A deterministic sentinel bullet (damage 3) |

The settings are also in Project Settings > Game > Airship (Crew, Stations, Turrets, Unpiloted, Boarding).

The automated suites (a clone with the editor closed first; read each runner's header):
`_AirshipWork_logs/run_r2_pie.sh` (as_59 standalone; `AS59_ONLY="t8_boost"` for the boarding measurement),
`run_r2_listen.sh` (as_60, listen with 2 players), `run_r2_swarm.sh` (as_62).

## 7. Media

All in `media/`, made from the final runs' captures and the editor-stage stills.

| File | Shows |
|---|---|
| `r2a_turrets_firing.jpg` | A client gunner firing the port turret; the turrets and sentinels trading fire over the forward deck |
| `r2a_cannonball_arc_splash.png` | The measured ball paths at 150 m and 300 m, and the splash falloff with the measured point |
| `r2a_gunners.jpg` | Gunners at cannon R1 and at the port turret, standing on the deck |
| `r2a_helm_on_planks.jpg` | The pilot at the wheel on the planks; the wheel next to the mech |
| `r2a_deck_top.jpg` | The whole deck from above (pieces gone, no ink patches); the turrets on the forward deck |
| `r2a_muzzle_smoke.jpg` | The port muzzles 0.1, 0.3 and 1.2 s after a broadside |
| `r2a_swarm_driven_ship.jpg` | The real swarm on the driven ship; a gunner on an undriven ship drawing it |

![Turrets](media/r2a_turrets_firing.jpg)
![Ball arc and splash](media/r2a_cannonball_arc_splash.png)
![Gunners](media/r2a_gunners.jpg)
![Helm](media/r2a_helm_on_planks.jpg)
![Deck](media/r2a_deck_top.jpg)
![Smoke](media/r2a_muzzle_smoke.jpg)
![Swarm](media/r2a_swarm_driven_ship.jpg)
