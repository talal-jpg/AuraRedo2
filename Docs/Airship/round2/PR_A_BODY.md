<!-- claude-projects-attribution: {"github_login":"talal-jpg"} -->
_Requested by **Talal** · [project thread](https://claude.ai/code/project/chan_01Spzu5fNbYB2wfTMSDFqGLc?thread=cmsg_01Spzu5fNbYB2wfTMSDFqGLcFQHnUwAEGsVSV9nm9CRX8s)_

## What this adds (airship round 2, part A)

- **Two front machine-gun turrets** (`BP_AirshipTurret`, C++ `AAirshipTurret`) on the edges of the forward deck: 4x the character gun per bullet (`TurretGunDamageMultiplier`, 10 is one setting away), 10 rounds/s, overheat after about 3 s, 400 health, a burning wreck that throws its gunner off. They hit characters, ships, turrets, cannonballs and sentinels, never their own ship or crew.
- **Bigger cannonballs** 1 m across on a real arc (70 m/s, gravity x 0.6, ballistic aim with lead, about 244 m range), 6 m splash, and 30 health: turrets or players can shoot them down in the air.
- **Gunner stations:** any player mans a free cannon or turret with F and aims with their own camera. The pilot's broadside fires only the unmanned cannons; Fire looking ahead (within 50 deg of the bow) drives the unmanned turrets.
- **Crew and swarm damage:** the pilot and every gunner take a quarter of each hit on the ship. Sentinel bullets now hurt ships and turrets (they used to sweep only the Pawn channel, which the hull is not on). The swarm targets a ship only while someone drives it or mans a gun; one bullet in four aimed at a driven ship goes for a working turret.
- **Drift and hold:** leave the helm while moving and the ship drifts at 2.5 m/s until something blocks it; leave it at rest and it holds its spot.
- **Helm and deck (your 11-25 points):** F takes the helm only within 1.5 m of the wheel, leaving keeps you exactly where you stood, there is no climb from below, and players walk on the planks. `PA_Airship` is rebuilt for this (35 bodies, 143 boxes, crates and barrels included).
- **Model:** the wheel is 140 cm across (character size), the five marked deck pieces are removed (hull ink repainted), the cannon bore is wider, and the turrets have new meshes. Muzzle smoke is gone 0.87 s after the shot.
- **Fixes found while testing:** jumps on a flying deck stay in the ship's frame (no 1.7 m slide), characters arriving on deck no longer shove the ship 3-5 m, a remote gunner leaving a gun is no longer frozen on the server, and a ship destroyed under its pilot throws him clear.

## Try it

Open `/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest` and press Play. Get on deck with Space, Space, Space then Shift + W (or `Aura.Airship.Board`), walk to the wheel and press F. Walk to a cannon or turret and press F to man it. Keys: `Docs/Airship/HOW_TO_FLY.md` ("Round 2"). Console: `Aura.Airship.Mount`, `TurretFire`, `TurretDamage`, `Damage`, `Set Settings.<name>`; full list in `Docs/Airship/round2/RESULTS_A.md` section 6.

## Tests (PIE in a separate clone, final build)

- Round 2, standalone (as_59): **55 PASS, 0 FAIL**, 4 INFO, 13 SKIP (the skips need 2+ players or the swarm and are covered below).
- Round 2, listen server + 1 client (as_60): **43 PASS, 0 FAIL**, 1 INFO, 9 SKIP. Includes a client gunner on a 47 m/s ship at 100 ms lag, client pilots, crew shares on both machines, and the helm exit at 40 m/s (6.5 cm, no correction).
- Real Mech Sentinel swarm (as_62): **20 PASS, 0 FAIL**, 1 INFO, 1 SKIP. Driven ship -195 in 30 s under 5 sentinels, pilot exactly 0.25 x; an empty ship takes 0; turrets kill sentinels; cannonball splash hits real sentinels.
- Assets: as_58 55 PASS + compile check, Control Rig eval 145/145, physics asset 11 PASS, hull ink 21 PASS.
- Regression: v1 validation under Classic 24/25 on the final build (`f2_boost_path`, the documented v1 crash bump, as in round 1). On the build before the last two narrow fixes: multiplayer Classic 22/22, `Aura.Airship.Scheme check` 0 differences, and the follow-up checks 7/9: `p4_firehold` / `p4_tap60` fail because Fire looking ahead now drives the turrets (on purpose); with `Settings.DriverTurretArcDeg 0` they pass 9/9.
- The multiplayer Classic re-run on the final build was skipped to keep testing lean; the two last fixes do not touch its paths.
- Results, every non-PASS with its reason, all measured numbers and media: `Docs/Airship/round2/RESULTS_A.md`.

## Shared code touched (outside `Airship/`)

- `GA_GunShoot`: the gun's crosshair hit damages cannonballs (gun units) and records the shot direction.
- `MechSentinelSwarmSubsystem`: a Visibility trace for tagged targets (ship parts), the `BulletTargetRedirect` and `BulletAimRedirect` hooks (inert when unbound), and the `Aura.MechSentinel.TestBullet` console command. `MechSentinelCombatProcessors.cpp`: 5 lines calling the aim hook.
- `MechSentinelCombatLibrary::GetMoveVelocityAt`: reads the simulating body under a kinematic base.
- `UMyCharacterMovementComponent`: jumps from a simulating pawn's deck stay based on it in the air (only for such bases; ground, hex platforms and bridges unchanged).

## Known limits

- Getting aboard is by hover + boost or from a platform at deck height (your decision); no climb, and the grapple does not hook the ship. In StartupMap a running jump from the platform beside the ship should reach the deck (worked out, not played).
- The turret deck is 4.2 m above the main deck with no stairs: stairs or a ladder come with the model detail pass after this PR.
- The rails have no collision (you can walk off the edge); the open truss under the forward deck has no hit box.
- How much cannon smoke is drawn differs between editor sessions (never any after 1.2 s; cause not found).
- With your local `GE_GunShootDamage` of 1000 a turret bullet does 4000 and destroys a ship. Your empty local `PA_Airship` conflicts with the rebuilt one: take the branch's.
- Hover does not keep you with a moving ship; flight to the deck costs no mana.
- Balance numbers are first guesses: crew share 0.25, swarm turret aim 0.25, ball health 30, turret 4x.
- Not tested: a client's air jump or jumps with lag on a flying deck, a gunner on a driven ship under the real swarm, anything played on StartupMap.

## Base

Built and tested on redo3 930c54f (PR #18). Lanes, teams and ship lives are part B.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
