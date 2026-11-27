# Airship round 2, PR B: teams, ship lanes, ship lives, match rules (implementation spec)

Status: contract for the parallel implementers (2026-11-25), **revision 2** after the critique (what changed and what was
rejected: section 6, Critique log). **Built on 2026-11-25 / 27: section 7 (Implementation notes) says where the code
differs from the text below; nothing has run in the editor yet.** Base: the clone
`/mnt/new_partition/UnrealProjects/_AirshipWork`, the thread's PR branch at **8c7e599** (PR A code + docs,
merged with redo3 930c54f). Every `file:line` below is at 8c7e599 unless it says otherwise. PR A is still in its editor
stage: if its fixes move lines, the function names stay the anchors. PR B is written on top of PR A's final commit.

Maps this spec was written from: `scratchpad/map/lanes_map.json` (path, lanes, rules and teams),
`scratchpad/map/round2_map.json`, `scratchpad/map/prA_result.json`; PR A docs `round2/SPEC_A.md` (D9, D10, sections 5.3
and 6) and `CPP_NOTES.md` section 15.

How claims were checked: **verified** = read in the code at 8c7e599 (or in the 5.8 engine source at
`/mnt/new_partition/5.8/Engine/Source`); **decoded** = read from the .uasset/.umap bytes with the scratchpad parser;
**inferred** = worked out, not run. Nothing here was built or run in the editor.

Talal's asks, verbatim: "ship moves at a certain speed on the line besides platforms on either side for both teams, until
driven and taken out of its lane and after if parked in lane again and unmounted from drive starts moving auto in lane
again / game rules include number of lives for ships, 1v1 or 2 v2 ( will also depend on the number of players.rules might
include difficulty of swarms". Later: "no swarms only attack ship when driving".

Contents

* 0. Goals, non-goals, conventions, flags (things in the plan that can't work as stated)
* 1. Decisions B1-B12 (B12: how a match plays, role by role)
* 2. File ownership and the API contract between owners
* 3. Editor steps (scripts, BP defaults, map changes)
* 4. PIE test plan
* 5. Risks, open questions for Talal, and the posted decisions that change
* 6. Critique log (revision 2), after the appendices
* 7. Implementation notes (2026-11-27): review fixes, what the parts built differently, new settings and questions
* Appendix A: settings. Appendix B: console commands. Appendix C: StartupMap numbers. Appendix D: hook point index.

---

## 0. Goals, non-goals, conventions, flags

### 0.1 Goals (what PR B delivers)

1. **Teams.** 2 teams. 1 player = practice (one ship, no opponent), 2 = 1v1, 3 = 2v1 (the smaller team gets one more
   ship life), 4 = 2v2, 5+ = balanced (B1). Teams are kept across a restart and the lane sides swap every round (B1.6).
2. **Lanes.** One ship per team on a lane just outside the platform field, one lane on each side of the path. With nobody
   driving it the ship cruises along its lane (6 m/s, faster when it has to catch up with its team, never past the built
   path), until a pilot drives it out of the lane. Parked back in the lane and left, it cruises again. Left outside, it
   drifts then holds (PR A D9), and after `ShipRecallDelay` (20 s) it flies itself back to its lane (B2.11).
3. **Ship lives.** 3 per team by default. A destroyed ship respawns in its lane, protected for a short time (B3.4); a
   team with no lives left loses. Solo practice has unlimited ships (B3.2).
4. **Match flow.** Waiting for players (the host can start early), countdown, play, a time limit with a tie-break, win /
   lose / draw / practice over, end screen, restart (B4).
5. **Rules.** Team mode, ship lives, swarm difficulty (the host menu's Difficulty box), time limit, friendly fire, ship
   grapple; from the host menu, URL options, the command line and the console.
6. **No friendly fire** between teammates (gun, beam, splash, cannons, turrets, fireballs; the crew share stays). Nobody
   drives or mans the other team's ship.
7. **Swarm rule.** Sentinels only attack a ship while it is driven (targeting already works that way; PR B makes the
   bullet damage follow it, B6.4).
8. **Ship hook.** The grapple can reel a player onto their own team's ship (setting, default on, B7).
9. **HUD.** Team, ship lives, both ships' hull health, match state and clock, the objective, ship markers, team name
   tags over players, "your ship is under attack", the lane state and what an exit does on the pilot's panel, toasts,
   end screen (B8).
10. **The existing race keeps working**: a piloted or ridden ship never becomes the lead that culls platforms or grows
    the path; Burrowers ignore players on ships; ejected crew die by a fall instead of falling for minutes, and nobody
    aboard a ship dies of the fall rule (B9).
11. **Damage to ships doesn't depend on the gun's GE value** (Talal's local GE_GunShootDamage is 1000 per hit): in a
    match, the gun and the turrets do a fixed amount to team ships and their turrets (B6.5).

### 0.2 Non-goals

* No lobby map, no team picker UI, no team chat, no host migration, no dedicated server work (the Burrower does not run
  on a dedicated server today, `BurrowerSpawnSubsystem.cpp:49-53`).
* No team colours on the ship mesh or the mech mesh (it would need a material change; not looked into); team colour
  only in the HUD (markers, name tags, B8).
* No lane markers in the world (debug draw only). No minimap change (its view radius is 120 m at S = 2,
  `MyHexMinimapWidget.h` ViewRadius 6000 x S: the lanes are off it).
* No kill credit / XP for ship kills.
* No turret self-defence: unmanned turrets fire only for the pilot, as in PR A (it would need target selection; spawn
  protection, the under-attack alert and the time limit cover the camping case instead, B3.4, B8.3, B4.4).
* No sudden death after the time limit: the tie-break decides (B4.4).
* No change to Talal's locally modified files: `Content/Maps/StartupMap.umap`,
  `Source/Aura/Public/Burrower/BurrowerSettings.h`, `Source/Aura/Public/Actors/MyHexPlatform.h` (staged), `BP_MyCharMech` (verified with
  `git status` in `/mnt/new_partition/UnrealProjects/AuraRedo3`). PR B works around each (B5.6, B9).
* No new input assets (B7 uses the grapple's own input; the HUD needs none).

### 0.3 Conventions

* **S** = the path spawner's `GetLayoutScale()` = HexRadius / 100 (`MyHexPathSpawner.h:144-145`). StartupMap: HexRadius
  200 (decoded), so S = 2. "x S" in a table means the value scales with S.
* **Start-heading frame** (B2.1): origin O = the path's first point = the spawner's location at BeginPlay
  (`MyHexPathSpawner.cpp:59-60`), forward F = the spawner's yaw psi0 (`:54`, StartYaw), right R = (-F.Y, F.X, 0), the same
  "across" the spawner uses (`:426`, `:535`). For a world point P: **u** = (P - O).F (progress), **v** = (P - O).R
  (sideways, + = right). Lane **side** +1 = right of the start heading (+Y in StartupMap), -1 = left.
* **Team ids**: 0 and 1. `MyMatch::NoTeam` = 255 (free ships, players outside a match). Team names in the HUD: BLUE (0),
  ORANGE (1).
* **Ship-borne** (B9.1): a pawn that is a ship (its player is at the helm), a character attached to a ship (pilot,
  gunner), or a character the new team-blind `AAirshipPawn::IsRiding` says rides a ship (today's rider test in
  `IsRiderForDamage`, `AirshipPawn.cpp:1539-1571`, moved out unchanged; B6.3). An enemy standing on your deck is
  ship-borne too. **On foot** = a living player character that is not ship-borne.
* **Team ship**: an `AAirshipPawn` with TeamId 0 or 1. Free ships (TeamId 255: `Aura.Airship.Spawn`, ships placed in a
  map without a team tag, any ship while no match runs) behave exactly as in PR A.
* **Match on**: the map is in `UMyMatchSettings::MatchMaps` (default `StartupMap`), or the CVar `Aura.Match.Enable` is 1
  (B5.5). With the match off, every PR B path returns the PR A behaviour (all TeamIds 255), so PR A's harnesses on
  L_AirshipTest are untouched unless a harness turns the match on.
* Server = authority (listen host). Every decision in PR B is made on the server; clients only display (B10).

### 0.4 Flags: parts of the plan that can't work as stated (each fixed below)

1. **The grapple can't simply be allowed on ships.** GrappleSwing2 refuses the hull twice: its anchor object types are
   WorldStatic and WorldDynamic only (`GA_GrappleSwing2.h:372`, checked at `.cpp:1240`) and it rejects any pawn
   (`.cpp:1241`). Even allowed, the swing needs the anchor at least 250 cm above the attach point (`MinAnchorHeight`,
   `.cpp:1251`), within 40 m (`MaxGrappleDistance` 4000, `.h:573`), and a fixed world anchor (the root motion source
   swings about `Anchor`, `.cpp:363`, `:670`, `:743`). A lane ship sits about path height, 14-84 m from the nearest
   platform edge (inferred, B2.1), and moves. Fix: a separate **reel** mode for ships with its own range and a moving,
   deterministic anchor (B7). Verified.
2. **"25 m beyond the outer platforms" is 25 m beyond the field's limit, not beyond the real platforms.** The lane offset
   comes from `SegmentBoundsHalfWidth` x S (`MyHexPathSpawner.h:264-265`: 200 m at S = 2). The real outermost platforms
   vary along the path (side streams reach about 130 m, the rings up to 200 m, from the layout numbers in lanes_map):
   the hull's inner side is 14 to 84 m from the nearest platform edge (inferred). The ship hook (120 m) covers it; a test
   measures it (T2.9).
3. **Ships in their lanes can't hit each other.** The lanes are 450 m apart at S = 2; the cannons reach 244 m on level
   ground (CPP_NOTES 15.4) and the turrets 250 m (15.2). Ship-to-ship fights need a pilot to take the ship out of its
   lane. Kept as the design (it matches "until driven and taken out of its lane"); open question Q11.
4. **A pilot who logs out destroys his team's ship today.** `APlayerController::Destroyed` calls `PawnLeavingGame`, which
   destroys the possessed pawn (engine `PlayerController.cpp:1633-1646`, `:1572-1579`) before `GameMode::Logout`
   (`Controller.cpp:595-604`); the ship's EndPlay then destroys the pilot's character (`AirshipPawn.cpp:500-510`). With
   ship lives that would cost a ship for a disconnect. Fix in B1.4. Verified (engine source).
5. **The start floor sits on team 0's side, and the host is always team 0.** StartupMap's floor is 60-140 m to +Y of the
   path (lanes_map). Team 0's ship is about 75 m from the floor's corner, team 1's about 274 m (Appendix C): team 1 can
   only reach its ship from the left-side platforms, and join order puts the host on team 0 every round. Team-tagged
   PlayerStarts can't fix it (the floor is the only place for them: v +60..+140 m). Fix without a map change: a versus
   match starts with each team on its own ship's deck (B4.2), and the lane sides swap every round (B1.6). Open question
   Q3.
6. **No fall death exists.** No KillZ override in StartupMap (decoded: no `KillZ` name in the map) and no fall code in
   Source (grep). A player thrown off a dying ship 225 m out falls until the world's default KillZ (inferred: minutes at
   the 40 m/s default terminal velocity). Fix: a match fall-death plane (B9.6). Open question Q4.
7. **The second player gets no pawn in listen-server PIE** on StartupMap (memory note mech-sentinel-demo-setup: "NO
   PLAYERSTART with positive rating"); nothing in C++ handles it (`MyGameMode.cpp` has no ChoosePlayerStart). The 2-4
   player tests need it fixed: B4.2.
8. **The Rules box has one entry and there is no lives box** (`MainMenu3.h:106`, `:219-223`). Team mode goes into the Rules
   box; ship lives need a new optional box added to WBP_MainMenu3 by script (B5.2, section 3).
9. **A ship left outside its lane is stranded.** "Left outside the lane, it drifts slowly ahead then holds" holds it
   for ever: a pilot who exits, is ejected or is put on foot by a lethal crew share (CPP_NOTES 15.3) leaves a ship
   that no life loss replaces and that the race leaves behind, out of hook range. With both ships stranded no ship can
   lose a life. Fix: the recall (B2.11). Open question Q16 (it adds to the posted decision).
10. **Nothing ends a match in which nobody attacks.** Lanes are out of cannon and turret range of each other (flag 3),
    an undriven ship is safe from the swarm, players respawn without limit. Fix: a time limit with a tie-break (B4.4).
    Open question Q17.
11. **Ship lives mean nothing with Talal's local gun value.** His GE_GunShootDamage is 1000 per hit (round2_map): the
    on-foot gun sinks a 2000-health ship in about 0.2 s and one turret round (4 x the GE value) sinks it. With the
    committed value (1 per hit) the gun needs about 7 minutes per ship. Fix: fixed damage to ships in a match (B6.5).
    Open question Q18.
12. **The plan's pace can't keep the ship in hook range of grapple runners.** 15 m/s catch-up only when 80 m behind, and
    300 m short of the path end, leave the hull up to about 130 m from the front runner; GrappleSwing2 players move at
    24-40 m/s (`GA_GrappleSwing2.h:129`, `:258`, `:325`). Fix: a proportional pace law up to 28 m/s and a 100 m end
    margin (B2.4, B2.6). Open question Q5.

---

## 1. Decisions

### B1. Teams, assignment, late join and leave

#### B1.1 Data

* `AMyPlayerState::TeamId` (uint8, Replicated with `OnRep_TeamId`, default 255) plus `OnTeamChanged` (native multicast,
  every machine). Server setter `SetTeamId(uint8)`. Today the class has no team field (`MyPlayerState.h:19-112`,
  verified). It survives respawns (the player state outlives pawns, `MyGameMode.h:48-50`).
* `AAirshipPawn::TeamId` (uint8, Replicated with `OnRep_TeamId`, default 255), server setter `SetTeamId`. Set before
  `FinishSpawning` for ships the match spawns (B3.1), so turrets and the lane component see it in BeginPlay.
* `AMyGameState::Teams` (fixed 2 entries, `FMyTeamState`, ReplicatedUsing `OnRep_Teams`): TeamId, bActive, NumPlayers,
  LivesLeft, BonusLives, ShipsLost, LaneSide, ShipHealthPct, Ship, ShipRespawnServerTime, EmptySinceServerTime,
  bEliminated (section 2.1). The game state is always
  relevant; today its only replicated property is the ranking (`MyGameState.cpp:16-20`, verified).
* No `IGenericTeamAgentInterface`: nothing in the project uses AI perception or team attitudes (grep: no team code at all,
  rules_teams in lanes_map). One static helper resolves the team of any actor: `UMyTeamLibrary::GetTeamId` (section 2.3).

#### B1.2 Who goes where

`AMyGameMode::InitNewPlayer` (engine `GameModeBase.h:530`, runs in Login before PostLogin and before the pawn spawns)
calls `AssignTeam(PlayerState)`:

```
if !MatchOn:                              TeamId = 255; return
if Rules.TeamMode == Practice:            TeamId = 0;   return      // co-op: everyone on one ship
Cap = { Auto: unlimited, OneVsOne: 1, TwoVsTwo: 2 }[Rules.TeamMode]
Remembered = MatchMemory->FindTeam(UniqueNetId)                        // last round's team (B1.6), or none
if Remembered valid && Count[Remembered] < Cap:  Pick = Remembered   // last round was balanced, so this stays balanced
else: Pick = (Count[0] <= Count[1]) ? 0 : 1   // the smaller team; a tie goes to team 0
if Count[Pick] >= Cap: Pick = 1 - Pick     // the other one (PreLogin refused the join if both are full)
PlayerState->SetTeamId(Pick); Teams[Pick].NumPlayers++
```

`bActive` is not set at join any more: the active teams are decided when the countdown starts, from NumPlayers > 0
(B4.2), and again when it ends. A team that empties before the start goes back to inactive.

Join order therefore gives (first round, nobody remembered): host team 0; 2nd player team 1; 3rd team 0; 4th team 1
(2v2); 5th team 0 (3v2) and so on. Team 0 is not always the floor side: the sides swap every round (B1.6).
More than 4 players is only possible without an EOS session cap (the menu offers 1-4, `MainMenu3.h:110`, enforced in
`MultiplayerSessionsSubsystem.cpp:1101-1103`): Auto keeps balancing, one ship per team. In 1v1 / 2v2 the cap is hard:
`AMyGameMode::PreLogin` (`MyGameMode.cpp:33-49`) refuses a join when both teams are full ("That match is full (2v2)."),
the same way the session check does.

1 player = **practice**: only team 0 is active, one ship, no win condition. Solo practice (one player) has unlimited
ships; co-op practice (TeamMode Practice with 2+ players) counts lives (B3.2, B4.4). A versus mode waits for its players
before the countdown (B4.2); the host can start early, and then 2v2 with 3 players plays 2v1.

**Smaller team handicap** (`bSmallTeamHandicap`, default on): when the active teams differ in size at the start, the
smaller team gets `BonusLives` = bigger size - smaller size extra ship lives (2v1: 4 against 3; capped at 9). Reason: the
bigger team can have a pilot plus a gunner, about double the firepower (the pilot's mouse fires the turrets or the
broadside, each gunner adds a cannon or a turret, CPP_NOTES 15.1-15.2), while the solo player must choose between flying
and everything else. Extra lives are simple and show in the lives boxes; a hull multiplier was the other option
(Critique log, Q19).

#### B1.3 Late join

A player joining during WaitingToStart or the countdown gets a team by the same rule and waits for the start with the
others (B4.2). A player joining while the match runs gets a team by the same rule and spawns as a match-start player
would (B9.7). If that makes a team active for the first time (practice becoming 1v1): phase Countdown again
(`MatchStartDelay`, event `PracticeToVersus`), and at its end both teams are reset: LivesLeft = ShipLives (+ handicap),
ShipsLost 0, team 0's ship healed to full and protected (B3.4), team 1's ship spawned at the match front (B3.1), the
time limit restarted. The players already in keep playing through that countdown (their race isn't reset). Joining
during `Ended` assigns a team for the restart.

#### B1.4 Leave

* `AMyGameMode::Logout` (`:114-133`): NumPlayers--. During WaitingToStart nothing else happens. During the countdown a
  team that empties goes back to inactive, and a versus match whose start condition no longer holds goes back to
  WaitingToStart (B4.2). While the match runs, at 0 the team keeps its ship (it cruises or holds with nobody aboard) and
  its lives, and `EmptySinceServerTime` is set. If it stays empty for `TeamEmptyForfeitSeconds` (30 s) while the other
  team is active, it **forfeits** (B4.4). A new join goes to the empty team (the smaller one) and clears the timer. In
  practice (one team) nothing happens: the host is always a player on a listen server.
* **A pilot leaving must not destroy the ship** (flag 4). `AMyPlayerController2` overrides `PawnLeavingGame` (engine
  `PlayerController.h:2054`, virtual):

```cpp
void AMyPlayerController2::PawnLeavingGame()
{
	// A pilot's pawn is his team's ship: give it back unpiloted instead of destroying it, and destroy the character
	if (AAirshipPawn* Ship = Cast<AAirshipPawn>(GetPawn()))
	{
		ACharacter* Pilot = Ship->GetPilot();
		Ship->UnboardPilot(false);   // detaches; it can't re-possess (this PC is being destroyed, LevelActor.cpp:912)
		UnPossess();                 // the ship stays: lane cruise, or PR A drift / hold
		if (IsValid(Pilot)) { Pilot->Destroy(); }
		return;
	}
	Super::PawnLeavingGame();
}
```

  `UnboardPilot` refuses to re-possess a PC that is being destroyed (`AirshipPawn.cpp:1388`), and the PC is marked
  as being destroyed before `Destroyed()` runs (engine `LevelActor.cpp:912` marks it, `:926` calls Destroyed). Gunners need
  nothing: their pawn is the character, which `PawnLeavingGame` destroys, and PR A's `UpdateStations` drops destroyed
  gunners (`AirshipPawn.cpp:2007`).

#### B1.5 Team change

Only by console (`Aura.Match.Team <Player> <Team>`, B11) in PR B. The server ejects the player first if he pilots, mans
or rides the other team's ship (UnboardPilot / DismountGunner), then sets the team and updates the counts.

#### B1.6 Teams across a restart, lane sides per round

* New `UMyMatchMemorySubsystem` (UGameInstanceSubsystem, host side; it survives the non-seamless ServerTravel the
  restart uses, B4.6): `TMap<FString, uint8>` from each player's unique net id (`FUniqueNetIdRepl::ToString`, from
  the player state) to his TeamId, written when the match ends, and `RoundIndex` (0 on a fresh map load from the menu,
  +1 on every `RestartMatch`; as built: +1 only after a versus round, 7.1 N6). `AssignTeam` reads it (B1.2), so friends stay together in 2v2. It is cleared when the
  host leaves to the menu. A player without a valid id (possible in PIE with the NULL online subsystem, not checked)
  falls back to join order.
* `bAlternateSides` (default on): the side table used by `UMyLaneSubsystem::GetSideForTeam` is `TeamLaneSide` on even
  rounds and swapped on odd rounds (team 0 left, team 1 right). The game state replicates each team's side (FMyTeamState
  `LaneSide`) for the HUD. The floor's side therefore alternates between the teams. As built (7.1 F5): only odd
  **versus** rounds swap, decided when the round's countdown starts (`AMyGameState::bLaneSidesSwapped`); a practice
  round always uses round 0's sides, so its lone ship is on the floor's side.

---

### B2. Lanes

#### B2.1 Geometry (start-heading frame)

The path never doubles back: its heading is `StartYaw + SampleNoise(...) * MaxYawDeviation` with the noise clamped to
+-1 (`MyHexPathSpawner.cpp:315`, `:615-620`, verified), so for MaxYawDeviation < 90 deg the progress u grows
monotonically along it and the path is a function v_path(u), z_path(u). StartupMap has MaxYawDeviation 0 (decoded): a
straight line.

The platform field is everything within H = `SegmentBoundsHalfWidth` x S of the path (`MyHexPathSpawner.h:254-265`; the
comment says it mirrors the PCG graph's 9975 layout cm). The lane is the curve that keeps a distance of
R = H + LaneClearance from every path point, i.e. the outer envelope of circles of radius **R** (not the field's
envelope of radius H shifted sideways in v: on a bend at angle theta to the start heading that shift leaves only
LaneClearance x cos(theta) between the curves, 12.5 m at the BP default MaxYawDeviation 60 deg, `MyHexPathSpawner.h:224`,
which is 1.2 m from the hull's side):

```
R          = H + LaneClearance
v_right(u) = max over samples i with |u_i - u| <= R of ( v_i + sqrt(R^2 - (u_i - u)^2) )
v_left(u)  = min over samples i with |u_i - u| <= R of ( v_i - sqrt(R^2 - (u_i - u)^2) )
z_lane(u)  = z_path(u) + LaneHeight
```

Every lane point is then at least R from every path sample, so at least LaneClearance from any point of the field, in
every direction. On a straight path it is the same line as before (v = +-(H + LaneClearance)).

* Samples: the path spline every `LaneSampleStep` (500 cm x S) along its length, converted to (u, v, z). The lane is
  stored as values at a fixed u step (the same 500 cm x S) from `LaneStartU` to the path end; queries interpolate
  linearly; the tangent comes from neighbouring samples. Between two samples 10 m apart the circles' envelope dips by
  d^2 / (8R) = 6 cm (inferred): negligible.
* Then a moving average over +-`LaneSmoothHalfWindow` (2500 cm x S), followed by the per-sample **max with the
  unsmoothed envelope** (min on the left side). The average lifts the lane outward at the kinks where two circles meet
  and would pull it inward at an arc's peak by about w^2 / (6R) = 5000^2 / 135000 = 1.9 m at S = 2 (inferred; revision 1
  said 0.5 m, which used w at S = 1). Taking the max keeps the smooth arc there, so smoothing only ever moves the lane
  away from the field.
* `LaneClearance` 2500 cm (not scaled): the hull's half width 11.3 m (lanes_map, research_blender) plus 13.7 m. The
  hull is about 29 m long (half length 14.5 m, lanes_map); aligned with the lane tangent, its corners keep the 13.7 m
  sideways gap where the field edge is straight, and more on the outside of a bend. `Aura.Lane.Check` (B11) measures the
  smallest gap between the hull's footprint (a 29 x 22.6 m rectangle on the lane tangent) and the field along the whole
  lane; T2.12 runs it on a curved path.
  `LaneHeight` 200 cm (not scaled): the hull origin 2 m above path height; the deck then sits about 4.5 m above it and
  the nozzles 3.9 m below (lanes_map ship facts).
* Before the path start the lane continues straight back along F for `LaneBackReach` (6000 cm x S): u from -120 m at
  S = 2, so a ship can spawn level with the start floor.
* MaxYawDeviation >= `MaxYawForEnvelope` (80 deg): the subsystem logs an error and uses straight lanes at
  +-(H + LaneClearance) along F (the envelope is still computed for the debug draw).
* StartupMap result (Appendix C): v = +-22500 cm, i.e. **y = +12500 (right) and y = -32500 (left)**, z 200, the lead's
  numbers. Round 0: team 0 right, team 1 left; the sides swap every round (B1.6).

**Fallback lane source** (no path spawner in the level, e.g. L_AirshipTest): an actor with the tag `MatchLaneOrigin`
(any actor; tests place a TEMP target point) gives O and psi0; the virtual path is straight, H =
`FallbackLaneHalfWidth` (10000 cm, not scaled), path end u = `FallbackLaneLength` (150000 cm). Neither: no lanes; team
ships then behave as PR A ships (lane state NoLane) and the log says why once.

#### B2.2 Who owns the geometry and when it is rebuilt

`UMyLaneSubsystem` (new UWorldSubsystem, server only, Game and PIE worlds). The path spline exists only on the server: the
spawner does not replicate and returns from BeginPlay on clients (`MyHexPathSpawner.cpp:32`, `:49-52`, verified; lanes_map
traced the role swap in the engine).

* `OnWorldBeginPlay` (which runs before any actor's BeginPlay, engine `World.cpp:6167` vs `:6174`, verified): find the
  first `AMyHexPathSpawner` (a level has one, the spawner's own lookup `MyHexPathSpawner.cpp:101-114`), bind its
  `OnSegmentSpawned` (`h:152-153`). The spawner resets its spline and builds the initial segments in its own BeginPlay
  (`cpp:59-72`), and each of them broadcasts (`cpp:397-400`), so the subsystem sees all of them; it also catches up with
  `GetSegments()` (`h:129-130`) if bound late.
* Each `OnSegmentSpawned`: re-sample from `LaneRebuildFromU = old path end u - 2R` to the new end. Reason: appending a
  point reshapes the last spline span (auto tangents, lanes_map), and a circle reaches R, so lane values up to 2R behind
  the old end can change; earlier ones can't. A straight path changes nothing.
* The spawner's StartYaw, StartZ and the bounds width are protected or private (`h:396-398`, `h:264`). PR B adds public
  getters (section 2.4): `GetStartYaw()`, `GetPathHalfWidth()` (= SegmentBoundsHalfWidth x S), `GetMaxYawDeviation()`.
* The lane geometry stays on the server. Clients get what they need for the HUD through the ship's replicated lane hint
  (B10).

#### B2.3 Lane states (per team ship, server, replicated enum `EMyLaneState`)

| State | Meaning | Flight |
|---|---|---|
| NoLane | free ship, match off, no lane source, or the ship is dead | PR A |
| Cruising | unpiloted, follows the lane, target moving | lane law (B2.5) |
| Waiting | unpiloted, follows the lane, target stopped (team behind, path end, blocked, match not started / over) | lane law, speed 0 |
| Assist | a pilot at the helm with his drive keys untouched, in the lane zone: the lane flies (B2.9) | lane law, pilot aims and fires |
| PilotedInLane | a pilot flies, inside the lane zone | the pilot |
| OutOfLane | a pilot flies, outside the lane zone | the pilot |
| Parked | unpiloted, not following the lane (left outside it, or still too fast) | PR A drift / hold / coast |
| Returning | unpiloted, flying itself back to its own lane (recall, B2.11) | lane law toward the lane |

The lane zone is always the ship's **own** team's lane. A team ship parked in the other team's lane is simply Parked
(no capture there), and the other team's cruising ship goes round it (B2.7).

**Lane zone** (hysteresis, measured at the hull origin against the lane point at the ship's own u): enter when
|lateral| <= `LaneZoneEnterLateral` (2000 cm) and |vertical| <= `LaneZoneEnterVertical` (1500 cm) and u in
[LaneStartU, PathEndU]; leave when |lateral| > `LaneZoneExitLateral` (4000 cm) or |vertical| > `LaneZoneExitVertical`
(2500 cm) or u is more than 20 m outside that range. The enter numbers are the lanes_map's park tolerances; the exit
numbers its "out of lane" ones.

**Parked in lane** = in the lane zone and horizontal speed <= `LaneParkSpeed` (800 cm/s: a little above the lane speed, so
a pilot who exits while riding along at lane speed counts; a 48 m/s fly-through does not).

Transitions:

```
spawn on the lane                                   -> Cruising (or Waiting before the match starts)
Cruising / Waiting / Returning, a pilot boards      -> Assist at once if in the zone (the pilot inherits the cruise;
                                                       without Rules.bLaneAssist: PilotedInLane), else OutOfLane
Assist, any drive input (the drive-intent bit)      -> PilotedInLane (immediately)
PilotedInLane, no drive intent for LaneAssistDelay (1 s), in zone, speed <= LaneAssistMaxSpeed (1500), and Point &
  Fly's camera in its parked free look              -> Assist          (only with Rules.bLaneAssist)
PilotedInLane / Assist, leaves the zone             -> OutOfLane
OutOfLane, enters the zone                          -> PilotedInLane
pilot exits: parked in lane                         -> Cruising
pilot exits: otherwise                              -> Parked (PR A: drift after a moving exit, else hold)
Parked, parked in lane for LaneParkSettleTime (0.5 s) -> Cruising   ("parked back in the lane": also a drift that
                                                                    slows inside the zone)
Parked for ShipRecallDelay (20 s), match InProgress -> Returning    (B2.11)
Returning, in the zone                              -> Cruising
ship dies                                           -> NoLane
match Ended                                         -> Waiting (Cruising and Assist ships stop on the lane)
```

"Pilot" = `HasPilot() || GetController()`, the same rule PR A uses (`AirshipFlightComponent.cpp:1142`). Gunners never
count as a pilot (PR A D9.1): a ship with gunners and no pilot cruises.

#### B2.4 The lane target (server, every frame, `UAirshipLaneComponent::UpdateLane`)

Called by the pawn's Tick on the server right before `Flight->UpdateFlight` (`AirshipPawn.cpp:566-569`), so the flight
model uses this frame's target.

```
u_s    = ProjectU(COM)                         // the ship's own progress
cap    = CruiseEndU = PathEndU - LaneEndMargin                     (B2.6)
if team front known:  cap = min(cap, TeamFrontU + LaneMaxLead)     (B2.6; LaneMaxLead 0 = no pace limit)
if team front known:  desired = clamp(LaneSpeed + LanePaceGain * (TeamFrontU + LanePaceOffset - u_s),
                                      LaneSpeed, LaneCatchUpSpeed)            // proportional pace, 6 m/s floor
else:                 desired = LaneSpeed
if Waiting reasons (blocked, match not started / over):  desired = 0
desired = min(desired, sqrt(2 * LaneAccel * max(0, cap - u_t)))   // eases into the cap: no overshoot, no spring back
if Ship->HasIncomingReel():  desired = TargetSpeed                 // speed frozen while someone reels in (B7.4)
TargetSpeed = ApproachConstant(TargetSpeed, desired, LaneAccel * dt)       // ramps, never jumps
TargetAccel = (TargetSpeed - TargetSpeedLastFrame) / dt
u_t = min(u_t + TargetSpeed * dt, u_s + LaneMaxTargetLead)                 // never far ahead of the ship
if !Ship->HasIncomingReel(): u_t = min(u_t, cap)
if u_t >= cap - 10 cm: Clamp = TeamPace / PathEnd
P = LanePoint(side, u_t) + Outward(side) * BypassOffset           // BypassOffset 0 unless going round a blocker (B2.7)
lateral join: P is moved toward the ship's own lateral position so |P - ship| across the lane <= LaneJoinStep (1000 cm)
Target.Mode         = Lane
Target.HoldPoint    = P.XY
Target.HoldVelocity = LaneTangent(u_t).XY * TargetSpeed
Target.HoldAccel    = LaneTangent(u_t).XY * TargetAccel           // fed forward (B2.5 item 6)
Target.HeadingYaw   = LaneTangentYaw(u_s)
Target.bHasHoldZ    = true;  Target.HoldZ = P.Z
Flight->SetLaneTarget(Target, State == Assist)
```

On entering Cruising, u_t = clamp(u_s, LaneStartU, cap) and TargetSpeed = the ship's speed along the lane (no jerk when a
pilot exits at lane speed). `TeamFrontU` = the largest u of the team's on-foot living players (B9.1), from
`GameState->PlayerArray`; unknown when the team has nobody on foot (all dead or all aboard): then only the path end
limits the ship. While a reel is frozen the ship may pass the cap by at most TargetSpeed x ShipReelMaxTime (30 m at
6 m/s); the cap applies again when the reel ends.

Numbers and why:

* `LaneSpeed` 600 cm/s: the lead's 6 m/s, which is also the mech's walking speed (MaxWalkSpeed is not overridden in
  BP_MyCharMech, decoded; no C++ override, grep: the engine default 600, inferred). It is the floor while the team is
  near, so a cruising ship never crawls. With Point & Fly's station keeping off in the lane law (B2.5) the 6 m/s
  minimum the lanes_map warned about does not apply.
* Proportional pace: `LanePaceGain` 0.3 /s toward an aim point `LanePaceOffset` 1500 cm ahead of the team front, up to
  `LaneCatchUpSpeed` 2800 cm/s, and `LaneMaxLead` 4000 cm ahead of the front at most. Reason: the ship is only useful
  if its team can reach it with the ship hook (120 m, B7), and grapple players move at 24-40 m/s (GA_GrappleSwing2
  SoftMaxSpeed 3000, GroundReelSpeed 2400, ReleaseMaxSpeed 4000). Revision 1's step law (15 m/s only when 80 m behind)
  left a fast team 80 m ahead of the ship, up to about 116 m from it with the sideways gap. Steady state (inferred): a
  runner at 20 m/s keeps the ship (20 - 6) / 0.3 = 47 m behind the aim point, 32 m behind him: at most
  sqrt(32^2 + 84^2) = 90 m away with the widest sideways gap (flag 2); at 28 m/s, 58 m behind, at most 102 m away.
  Only a runner holding more than 28 m/s for long outruns it. A team standing still: the ship settles at the cap,
  40 m ahead, at most sqrt(40^2 + 84^2) = 93 m away. The ship's top speed is 50 m/s (`VTop` 5000), so 28 m/s leaves the
  pilot a big margin.
* `LaneAccel` 250 cm/s^2: 0 to 6 m/s in 2.4 s, 6 to 28 in 8.8 s; braking into the cap from 6 m/s takes 7.2 m.
* `LaneMaxTargetLead` 1500 cm: a ship held back (a ram, a blocker) never gets a target running away from it.

#### B2.5 Forces (UAirshipFlightComponent, server): PR A's module with a Lane mode

PR A built the unpiloted module so a lane could plug in: the target struct already carries a moving hold point and its
velocity (`AirshipFlightComponent.h:14-30`; SPEC_A 5.3). Changes:

1. `EAirshipUnpilotedMode::Lane = 4` (`AirshipTypes.h:88-98`).
2. `FAirshipUnpilotedTarget` gains `bool bHasHoldZ = false; float HoldZ = 0.f; FVector2D HoldAccel = FVector2D::ZeroVector;`.
3. New `void SetLaneTarget(const FAirshipUnpilotedTarget& Target, bool bAssist)`: stores the target and the frame
   number. `UpdateUnpilotedMode` (`cpp:1125-1275`) checks it first: a lane target set this frame wins when flight is on,
   the ship is alive, no debug input is active, and either there is no pilot or bAssist. Then `UnpilotedTarget =` the
   lane target, `bDriftRequest = false`, `bDriftBlocked = false`. Otherwise PR A's switch runs unchanged; leaving Lane
   with no pilot goes through `None` (hold if slow, else coast, `cpp:1161-1187`).
4. Yaw: the drift / hold heading override (`cpp:1596-1605`) also runs in Lane.
5. Station keeping gate (`cpp:1968`): `&& !bUnpilotedLane` (it would brake the cruise: 6 m/s is inside its band).
6. Force (`cpp:2012-2032`): Lane uses the hold law with the target velocity, plus the drag at that velocity and the
   target's own acceleration fed forward, capped at `LaneAccelMax` (600 cm/s^2; revision 1 had 200, which can't hold
   28 m/s: the drag there is 0.05 x 2800 + 3e-6 x 2800^2 = 164 cm/s^2, plus the 250 cm/s^2 ramp; the fans give
   `AFan` 1323 cm/s^2, `AirshipFlightComponent.h:513`):

```cpp
else if (bUnpilotedLane)
{
	// The hold law on a moving point (Kp, Kd as the hold), with the hull drag at the lane speed fed forward so the
	// ship doesn't trail its target (ADragFwd above takes the real drag off), capped
	const FVector LaneCOM = Body->GetCenterOfMass();
	const FVector2D Err = UnpilotedTarget.HoldPoint - FVector2D(LaneCOM.X, LaneCOM.Y);
	const FVector2D VErr = UnpilotedTarget.HoldVelocity - FVector2D(V.X, V.Y);
	const float T = static_cast<float>(FVector2D::DotProduct(UnpilotedTarget.HoldVelocity, FVector2D(Fwd.X, Fwd.Y)));
	const FVector2D DragFF = FVector2D(Fwd.X, Fwd.Y) * (DragC1 * T + DragC2 * T * FMath::Abs(T));
	const FVector2D ALane = (Err * M->LaneKp + VErr * M->LaneKd + DragFF + UnpilotedTarget.HoldAccel).GetClampedToMaxSize(M->LaneAccelMax);
	ACom += FVector(ALane.X, ALane.Y, 0.0);
}
```

   (M = `UMyMatchSettings::Get()`; defaults Kp 0.4, Kd 0.8 as PR A's hold. At 6 m/s the feed-forward is
   0.05 x 600 + 3e-6 x 600^2 = 31 cm/s^2; the drag constants are the class defaults DragC1 0.05, DragC2 3e-6 per
   round2_map's drift section. Without it the ship would trail by 31 / 0.4 = 78 cm.)
7. Altitude: in the vertical block (`cpp:1462-1487`), in Lane mode with bHasHoldZ: `HoldZ = FInterpConstantTo(HoldZ,
   Target.HoldZ, Dt, LaneClimbRate)` (200 cm/s) and `bHoldValid = true` before `HoldError` is taken. The MinClearance
   floor (`:1489-1497`) still lifts the ship over anything under its pods.
8. `SelectControls` neutral branch (`cpp:474-479`): set `Button_Drift` in Lane mode too (no Galleon STOP reverse in the
   cosmetics; the bit's comment becomes "unpiloted cruise: drift or lane").
9. Assist (B2.9): on the authority, right after `SelectControls` in `UpdateFlight` (`cpp:857`): if Mode is Lane and the
   target came with bAssist, keep the controls' aim (AimPoint, HasAimPoint, Aim, FireHeld, Stations) and clear the drive
   (Throttle = neutral or Galleon STOP, Steer, Lift, Strafe, Boost, Brake, HeadingTarget), and set Button_Drift.
   Before clearing, store `bPilotDriveInput` = the new **drive-intent bit** `Airship::Button_DriveIntent = 1 << 7` (the
   one free bit of the button byte, `AirshipTypes.h:42-57`) or any of those axes non-neutral this frame (|axis| > 0.05,
   Boost, Brake, Galleon notch != STOP), exposed as `HasPilotDriveInput()` for the lane component. The pilot's machine
   sets the bit in `GatherLocalInput` whenever its own drive test is true: in Point & Fly that is `bMoveKeys`
   (`AirshipPawn.cpp:905-912`, which includes Q/E on IA_AirshipStrafe, the camera's turn keys) or the camera leaving its
   parked free look into steering; in the other schemes any drive axis or button. Reason: in Point & Fly the heading
   target is the steering and Q/E turn it (`:948`), but the server can't tell that from HeadingTarget alone, so
   revision 1's server-side test missed Q/E (they would have turned only the pilot's cosmetics). The bit is ignored on
   free ships.
10. `SetDriftMaxDistanceOverride(float)`: used instead of `UAirshipSettings::DriftMaxDistance` (`cpp:1216`) when > 0.
    Team ships get `LaneOutDriftMaxDistance` (30000 cm, B2.8).
11. A public `bool SweepHullAhead(float HeadingYaw, float Distance, FHitResult* OutHit) const` that wraps PR A's look-ahead
    box sweep (`SweepDriftAhead`, `cpp:1036-1114`) with an explicit heading and length, for the lane component.
12. `FillTelemetry` (`cpp:2187`): Lane counts as its own mode; `bUnpilotedLane`.

#### B2.6 Pacing and the end of the built path

`CruiseEndU = PathEndU - LaneEndMargin`, `LaneEndMargin` = 5000 cm x S (100 m at S = 2). Reasons:

* A player within ExtendDistance x S (200 m, 2D) of the path end grows the path, one segment (200 m) per 0.25 s check
  (`MyHexPathSpawner.cpp:255-280`, decoded overrides), so runners are normally 200-400 m behind the end and never more
  than one check closer than 200 m. 100 m therefore never holds the ship behind the front runner (revision 1's 300 m
  held it up to 100 m behind a runner 200 m from the end: about 130 m from him with the sideways gap, out of hook range).
  The platforms of the newest segment that are still generating are inside the field, 25 m or more from the lane
  (B2.1), so being level with them is harmless; the team pace (front + 40 m) is the usual limit anyway.
* An unpiloted ship is never a player controller's pawn, so it can't grow the path itself (`:268-279` iterates player
  controllers). Riders standing on a cruising ship are at least sqrt(100^2 + 225^2) = 246 m from the end, beyond 200 m,
  and from PR B on riders don't grow the path anyway (B9.2).
* Path-end fog: the banks stand at +-55 and +-165 m (BP default count 4, spacing 5500 x S, `cpp:429-432`; lanes_map). The
  lanes at 225 m are outside them. Recommend `PathEndFogCount` 5 on the spawner (banks at 0, +-110, +-220 m): a map
  change, so it is left to Talal (Q12).

Piloted ships are not clamped: once out of the lane a ship is fully the driver's (the lead's decision). A pilot can fly past
the end into the empty sky; the path doesn't grow for him (B9.2).

#### B2.7 Collision avoidance

* **Platforms and bridges**: none in a lane by construction (the envelope plus 13.7 m of clearance from the hull's side;
  bridges only join platforms inside the field, lanes_map). This depends on the PCG graph staying inside
  SegmentBoundsHalfWidth (`MyHexPathSpawner.h:254-262` says the bounds must follow the graph): risk R5.
* **Look-ahead** (safety net): every 0.25 s in Cruising / Assist, `Flight->SweepHullAhead(lane heading, max(1500, speed
  x 3 s + speed^2 / (2 x LaneAccelMax)))`. PR A's sweep already ignores characters, cannonballs, pawns that aren't ships,
  the ship's own attachments, and only counts bodies that block the hull's channel (`cpp:981-996`, `:1093-1110`). A hit
  -> Waiting (Clamp Blocked), logged with the blocker's name; 3 clear sweeps in a row (0.75 s) -> Cruising again.
* **Going round a blocker**: blocked for `LaneBlockedTimeout` (5 s) -> the lane component sweeps a second line
  `LaneBypassOffset` (3500 cm: both hulls' half widths, 22.6 m, plus 12 m) further **outward** (away from the field:
  there is only sky there) over the same length. Clear: `BypassOffset` ramps to 3500 cm through the lateral join step
  (Clamp Bypass, state unchanged), and the ship passes. It ramps back to 0 once a sweep along the real lane is clear and
  the blocker is more than 3000 cm behind the stern (hull length 29 m). Outward line blocked too: keep waiting, re-try
  every 5 s. 35 m stays inside the 40 m exit width, so an Assist ship stays in its zone. Reason: a ship parked in front
  of a cruising one (an enemy parking in the other lane, or a teammate) must not be able to hold it behind its team for
  ever.
* **Hull contacts**: the pawn forwards `OnHullHit` (`AirshipPawn.cpp:3664`, where it already calls
  `Flight->NotifyHullContact` at `:3691`) to `Lane->NotifyHullContact`: a bow contact (PR A's rule, `cpp:1009-1018`)
  while cruising -> Waiting for 2 s, then the look-ahead decides.
* **The other ship**: the lanes are 2 x (H + LaneClearance) = 450 m apart at S = 2, so two cruising ships never meet. A
  ship parked in front of a cruising one is found by the look-ahead (other ships are not ignored, `cpp:995`): the
  cruising ship waits behind it, then goes round it after 5 s (above). An enemy ship parked in your lane is not
  captured by your lane (the zone is per team, B2.3); if it is left there unpiloted, its own recall (B2.11) flies it
  home after 20 s.
* **Start floor**: lane 0 at v +225 m, the floor at v +60..+140 m (Appendix C): clear by 74 m.
* Sentinels and Burrowers don't collide with the hull (no MechSentinelObstacleComponent on BP_AirshipPawn, round2_map; the
  Burrower's capsule collides with nothing, `BurrowerCharacter.h:33-34`).

#### B2.8 Interaction with PR A's drift and hold

* Lane mode replaces drift and hold while the lane component sets a target. When it stops setting one (pilot takes the
  helm, the ship is Parked), PR A's module runs as built.
* A pilot exiting out of the lane: `UnboardPilot` calls `Flight->NotifyPilotLeft` (`AirshipPawn.cpp:1418-1421`) as today
  and the lane state becomes Parked: drift after a moving exit, hold after one at rest.
* "Drifts slowly ahead then holds": PR A ends a drift only on a blocker or after `DriftMaxDistance`, which defaults to 0 =
  never (`AirshipSettings.h` Unpiloted, SPEC_A D9.4). Over the void nothing blocks, so a team ship would drift at 2.5 m/s
  for ever. PR B gives team ships `LaneOutDriftMaxDistance` 30000 cm through `SetDriftMaxDistanceOverride`. It is
  measured from the exit point, and the slow-down from 48 m/s takes about 260 m (round2_map drift section), so 300 m
  ends it about 16 s after the ship reaches 2.5 m/s. Free ships keep PR A's setting (as_59 T9.1 expects a long drift).
* PR A's distance end calls `BeginHold` at any speed (`cpp:1216-1232`). PR B changes that one branch: still faster than
  `HoldEngageSpeed` -> Coast (which becomes Hold once slow, `cpp:1189-1196`); a blocked drift still holds at once. Reason:
  a hold spring started at speed overshoots by v^2 / (2 x 200 cm/s^2).
* A drifting or holding ship that ends up parked in its lane zone is captured (Parked -> Cruising, B2.3).
* A team ship still Parked after `ShipRecallDelay` is recalled (B2.11): the drift / hold is only the first 20 s.
* `Aura.Airship.Set Settings.DriftSpeed 0` / `bHoldWhenUnpiloted 0` still give the old behaviour outside the lane.

#### B2.9 Lane assist while a pilot is at the helm

Talal's sentence has the ship cruise "until driven and taken out of its lane". Without an assist, a pilot who boards a
cruising ship to fire the broadside would stop it: Point & Fly's station keeping brakes a ship with no throttle below
6 m/s (lanes_map, `cpp:1968-1971`). So, with `Rules.bLaneAssist` (default on, Q2):

* Boarding a Cruising / Waiting ship goes straight to Assist. The lane keeps flying; the pilot aims and fires the cannons
  and the turrets as usual (his AimPoint and fire bits pass through, B2.5 item 9).
* Any drive key (W/S, A/D, Space/Ctrl, Q/E, Shift, X; Galleon: any order other than STOP) hands the helm to him at once
  (PilotedInLane), through the drive-intent bit (B2.5 item 9). Point & Fly's mouse look in its parked free look is
  look, not drive: in Assist the ship keeps the lane's heading while the camera moves. Assist is not entered again
  while Point & Fly's camera is steering (out of its parked free look), so a pilot steering with the mouse alone is
  never taken over after 1 s.
* The pilot's own machine: while the replicated lane state is Assist and no drive key is down, `GatherLocalInput` sends
  no heading target and Steer 0, and Point & Fly stays in its parked free look (`AirshipPawn.cpp:900-951`,
  `UpdatePointFlyCamera` at `:4948`: its parked condition gains "or lane assist"). Without this the pilot's wheel and fans
  would turn on his screen while the server holds the lane (cosmetic mismatch).
* HUD: "LANE AUTO  -  W/S/A/D take the helm" (B8).

#### B2.10 Edge cases

* Respawned or spawned ship: spawned on the lane (B3.1), so no join flight is needed.
* A ship spawned or parked behind `LaneStartU` (never by PR B): the zone test fails, it stays Parked.
* Ship turned backwards in the lane: the heading loop turns it at `HoldYawRateMax` 10 deg/s (18 s for 180 deg) while the
  position law holds it; no special case.
* Debug input (`Aura.Airship.Input`) on a team ship: PR A rule, None while active (`cpp:1142`); the lane re-captures it
  afterwards if it is parked in the zone.
* Match off mid-session (CVar) has no effect until the next map load.

#### B2.11 Recall: a ship left outside its lane flies itself back

Talal's words cover a ship "parked in lane again". A ship left anywhere else would otherwise drift and hold for ever
(flag 9). With `bShipRecall` (default on, Q16):

* **When**: a team ship, match InProgress, nobody piloting (`HasPilot() || GetController()` false), lane state Parked
  continuously for `ShipRecallDelay` (20 s). Boarding resets the timer. Gunners and deck riders don't stop it:
  a ship nobody flies goes home, and they ride along. The timer replicates (`RecallServerTime` on the lane component,
  0 = none) for the HUD: "SHIP RETURNS TO LANE IN 12 s" on the match bar and the gunners' panel.
* **How** (state Returning, Lane mode): the target is the own lane's point at the ship's own u (clamped to
  [LaneStartU, cap]), with no LaneJoinStep limit; the target moves toward it at up to `ShipRecallSpeed` (2500 cm/s);
  heading = toward the target point until within 50 m, then the lane tangent; LaneAccelMax as cruising. If the straight
  line to the lane point passes within H + 2500 cm of the path (a ship parked on the other side of the field), the
  target first climbs to path height + `ShipRecallCrossHeight` (8000 cm: above every platform, prop and the sentinel
  wave corners at +46 m, Appendix C), crosses, and descends once outside the field. The look-ahead (B2.7) sweeps along
  the travel direction. Once in the zone: Cruising, which then catches up with the team at up to 28 m/s (B2.4).
* **Fallback**: blocked for more than 10 s, still not in the zone after `ShipRecallMaxTime` (60 s), or more than
  `ShipRecallMaxDistance` (100000 cm) from the lane point: the ship is replaced with no life lost. Gunners are
  dismounted and deck riders noted; the ship is destroyed (`OnTeamShipDestroyed` sees the recall flag: no life lost, no
  respawn delay) and a new one spawns at once on the lane at the team front (B3.1); gunners and riders are put on its
  deck (the match-start deck spots, B4.2). Logged.
* Free ships, the match not in progress, and `bShipRecall` off: PR A's drift / hold as before.
* Cost: one extra state in the lane component; the sweeps are the existing ones.

---

### B3. Ship spawn per team, lives, respawn, death, crew

#### B3.1 Spawning

`AMyGameMode::SpawnTeamShip(TeamId, U)` (server):

1. Transform: the lane point at (side of TeamId, U), yaw = lane tangent; no lane: an actor tagged `ShipStart<TeamId>`;
   neither: the team's PlayerStart moved by `UAirshipSettings::SpawnDistance` / `SpawnHeight` (the Aura.Airship.Spawn rule,
   `AirshipSubsystem.cpp:482-506`).
2. `SpawnActorDeferred<AAirshipPawn>(UAirshipSettings::AirshipClass)` (falls back to `AAirshipPawn` with a warning as
   `SpawnAirshipInFront` does, `:491-498`), `SetTeamId(TeamId)`, `FinishSpawning`, collision handling
   AdjustIfPossibleButAlwaysSpawn (`:503-505`).
3. Bind the ship's `GetOnDeathDelegate()` (`AirshipPawn.h:109`, broadcast on every machine at `AirshipPawn.cpp:3924`) to
   `OnTeamShipDied` and `OnDestroyed` to `OnTeamShipDestroyed`, the same pattern as `WatchPlayerPawn`
   (`MyGameMode.cpp:140-165`). `Teams[TeamId].Ship = Ship`.

When: at the countdown's start for every active team at U = `LaneSpawnU` (0: level with the path start, the floor's front
edge is at u -14 m), so the ships are there to spawn the players on (B4.2); when a team becomes active later (B1.3) and
at a respawn at U = clamp(front, LaneStartU, CruiseEndU), where front = TeamFrontU, else the match front (the largest u
of any on-foot player), else the dead ship's u. Away from the enemy: if the enemy ship is alive and within
`ShipSpawnMinEnemyDistance` (25000 cm, just over cannon and turret range, flag 3) of that lane point, U moves back
along the lane in 50 m steps (down to LaneStartU) until it isn't; if no such point exists, U stays (the protection
covers it, B3.4). A respawned or match-start ship is spawn-protected (B3.4).

**Ships placed in the map**: one tagged `ShipTeam0` / `ShipTeam1` is claimed by that team at the countdown's start instead
of a new one (SetTeamId, bind; it is not teleported: it gets lane-captured when parked in its zone, else recalled after
20 s, B2.11; with `bStartAboard` the players spawn on its deck where it is). Untagged placed ships: destroyed at the
countdown's start in a 2-team match (`bDestroyUntaggedPlacedShipsInVersus`, default true, logged), left free in
practice. Talal's local
StartupMap has `BP_AirshipPawn_C_6` at (3700, 555, 1097) (lanes_map, decoded): Q9.

#### B3.2 Lives

* `Rules.ShipLives` (default 3, 1..9) = how many ships a team may lose. LivesLeft starts at ShipLives + BonusLives (the
  smaller team's handicap, B1.2). Each death: LivesLeft -1, ShipsLost +1. LivesLeft > 0: a new ship after
  `ShipRespawnDelay`. LivesLeft = 0: the team is eliminated (B4.4). So 3 lives = 3 ships in all (the first one
  included).
* **Solo practice** (one active team with one player, `bSoloPracticeUnlimitedShips`, default on, Q20): lives aren't
  counted; every lost ship comes back after ShipRespawnDelay; the HUD shows "SHIPS LOST n" instead of boxes. In solo
  practice only crashes and the swarm (while driven) can sink a ship, and a learner shouldn't be sent back to a reload
  after three crashes. Co-op practice (2+ players on the one team) counts lives and ends in PracticeOver.
* `ShipRespawnDelay` 10 s. Reason: the wreck lives 25 s (`WreckLifeSpan`, `AirshipPawn.h:853`) and falls with gravity
  once its forces are off (`HandleDeath`, `cpp:3846-3866`); after 10 s it is well below the lane (about 490 m in free
  fall, inferred), so the new ship doesn't spawn into it.
* Destroyed without a death (console Destroy, `PawnLeavingGame` before B1.4 lands, level teardown): no life lost; a
  replacement after ShipRespawnDelay (at once for a recall replacement, B2.11). `OnTeamShipDestroyed` ignores the world
  tearing down.
* Changing ShipLives during a match (console): LivesLeft = max(NewLives - ShipsLost, alive ? 1 : 0); a team at 0 with a
  dead ship is eliminated at once.

#### B3.3 Death, wreck and crew

PR A does the death: `Die` (`cpp:3792-3808`) sets bIsDead, multicasts, sets the wreck's life span and ejects the crew next
tick (`EjectCrewAfterDeath`, `cpp:3927-3945`: the killing blow's crew share first, then the pilot `UnboardPilot(true)`
and every gunner `DismountGunner(s, true)`, thrown clear with EjectUpSpeed 1200 / EjectSideSpeed 600, `h:759-762`). Deck
riders fall with the tumbling wreck. PR B adds:

* The lane state becomes NoLane (the flight is off: PR A clears the unpiloted state, `cpp:932-940`).
* The crew lands nowhere: 225 m out there is only sky. Once ejected (they are on foot then; while attached or riding
  the falling wreck they are ship-borne and skipped), the match fall death (B9.6) kills them about 5.5-7 s after the
  ejection (inferred: 1.2 s up at EjectUpSpeed 1200, about 4.3 s down 89 m, the 1 s falling check and the 0.5 s poll);
  deck riders who stay on the tumbling wreck are checked once they leave it. The normal respawn then puts them ahead of
  the lead after RespawnDelay 5 s (`MyGameMode.h:66-67`, B9.7). Their crew-share injuries carry over as today.
* `MulticastMatchEvent(ShipDestroyed, Team, LivesLeft)` -> HUD toast; the wreck keeps its marker greyed until it goes.
* The team's respawn timer shows on the HUD (`ShipRespawnServerTime`, replicated).

#### B3.4 Spawn protection

A ship spawned at the countdown, at a respawn or by a recall replacement takes **no damage** until its own team first
boards the helm or mans a station, or for `ShipSpawnProtection` (15 s), whichever comes first. Reason: revision 1
respawned the ship 10 s after a death, in the same lane at the team front where the attacker was already waiting, with
no protection: a lone attacker could sink a cruising ship in 25-50 s (B3.5) and take three lives in two to three minutes
while the defenders were still on foot.

* One choke point: `UMyAttributeSet::PostGameplayEffectExecute`'s IncomingDamage branch (`MyAttributeSet.cpp:64-68`)
  drops the damage when the owning ASC has the loose tag `Airship.State.SpawnProtected` (server). Every damage path to
  a ship or a turret ends there (gun, beam, splash, cannonballs, turret rounds, sentinel bullets, hull impacts: all are
  GEs on the ship's or the turret's ASC), so no caller changes. The ship adds the tag to its own ASC and its turrets'
  (server) and removes it on the first board / mount by its team or when the time runs out. A protected ship has no
  crew share (no Health loss).
* Replicated `ProtectionEndServerTime` on the ship (0 = none) for the HUD's shield on the marker.
* The enemy can't board it anyway (B6.3); sentinels only target a driven ship, so protection ends before they can.

#### B3.5 Expected time to kill (inferred, committed values, every shot landing, an undriven 2000-health ship)

| Attacker | Damage per second | Time for one ship |
|---|---|---|
| Pilot's broadside (2 balls x 60 every 1.5 s, `AirshipPawn.h:611`, `:802`, `:806`) | 80 | 25 s |
| Pilot's two turrets in the bow arc (2 x 10 rounds/s x 4, B6.5) | 80 peak, about 44 with heat (fire about 2 s, locked about 1.6 s, CPP_NOTES 15.2) | 25-45 s |
| Pilot plus one gunner on a turret | about 100-120 | 17-20 s |
| On-foot gun, `ShipDamageGunHit` 5 (B6.5), committed fire rate 0.216 s | 23 | 87 s (40 s at Talal's local 0.1 s) |
| On-foot gun before B6.5, committed GE value 1 | 4.6 | 7 min |
| On-foot gun before B6.5, Talal's local GE value 1000 | about 10000 | 0.2 s |
| Beam hit | 150 per hit; its rate is GE_BeamCooldown's, not decoded | - |

With 3 lives, 10 s respawn and 15 s protection, a lone attacker at his best needs about 3 x 25 + 2 x 25 = 125 s to
eliminate a team that never fights back; real hit rates are lower. Tune `ShipLives`, `MaxHealth` (on BP_AirshipPawn)
and the B6.5 values together from this table (Q6, Q18).

---

### B4. Match flow

#### B4.1 Phases (`EMyMatchPhase`, replicated on the game state)

`None` (match off: nothing of PR B shows) -> `WaitingToStart` (versus only: waiting for players) -> `Countdown` ->
`InProgress` -> `Ended`; practice turning into versus goes InProgress -> Countdown -> InProgress (B1.3). No `AGameMode` /
`AGameState` switch: the project derives from the Base classes (`MyGameMode.h:19`, `MyGameState.h:35`), and switching
would force both; PR B keeps its own small phase enum (the lanes_map recommendation).

#### B4.2 Start

Real hosting: MainMenu3 creates the session, then the host travels into StartupMap (`ServerTravel(PathToLobby)`,
`MainMenu3.cpp:1144`), and clients find and join it afterwards, often 10-60 s later. Revision 1's fixed 5 s countdown
would have started nearly every versus match as practice. So:

* `AMyGameMode::StartPlay` (engine `GameModeBase.h:159`), match on: first the swarm difficulty is applied (B5.4: the
  rules are known from InitGame, and the wave spawners' and the path spawner's BeginPlay haven't run yet), then Super.
  Then:
  * **Practice** (TeamMode Practice, or Auto with ExpectedPlayers 1, or a standalone game): phase Countdown at once,
    `MatchStartDelay` (5 s). Players spawn on the floor as today and may move (the race isn't gated for 5 s). As
    built: ExpectedPlayers 1 is practice in every team mode (Play Solo with the Rules box on 1v1 / 2v2, 7.1 F3), and
    a player who joins the empty team during this countdown waits for its end and starts aboard (7.1 F6).
  * **Versus** (Auto with ExpectedPlayers >= 2, OneVsOne, TwoVsTwo): phase **WaitingToStart** until the start condition
    holds: OneVsOne both teams have a player; TwoVsTwo both teams have two; Auto NumPlayers >= ExpectedPlayers. Then
    Countdown (5 s). `ExpectedPlayers` = the URL option `Players` (the host menu's Max Players, B5.2), else
    `DefaultExpectedPlayers` (2: listen PIE, a console-opened listen game).
  * The host can start at once with whoever is in: the pause menu's **Start match** button (host only, WaitingToStart
    only, B5.2) or `Aura.Match.Start`. With one player that is practice; with 3 players in 2v2 it is 2v1 (B1.2).
* **No pawns while waiting** in versus: `PlayerCanRestart_Implementation` (`MyGameMode.cpp:135`, already overridden)
  returns false during WaitingToStart and Countdown, so `HandleStartingNewPlayer` gives nobody a pawn. The camera stays
  at the controller's start spot (InitNewPlayer places it there), the match bar says "WAITING FOR PLAYERS 1/2 - host:
  Esc > Start match", and the pause menu works (IA_Pause is bound on the controller, `MyPlayerController2.cpp:152`).
  Reason: nobody races ahead, grows the path or starts the collapse while the others are still joining, so nothing in
  the race needs gating or resetting.
* **Countdown start**: the active teams are decided from NumPlayers > 0, the lane sides set (B1.6), the handicap worked
  out (B1.2), and each active team's ship spawned on its lane at LaneSpawnU, Waiting (Clamp NotStarted), protected (its
  15 s of protection start counting at InProgress).
* **Countdown end** (InProgress): the active teams are checked again (a team that emptied: inactive, its ship removed
  with no life counted; versus with one team left goes back to WaitingToStart); every active team gets LivesLeft = ShipLives + BonusLives; the time limit
  starts (B4.4); event Started; the objective line shows (B8.1). Then every player without a pawn is spawned:
  * Versus with `bStartAboard` (default on, Q3): on his own team's ship's deck, at the ship's deck spots
    (`AAirshipPawn::GetDeckSpawnTransforms`, found like UnboardPilot finds the deck, `AirshipPawn.cpp:1352-1358`;
    `RestartPlayerAtTransform`). The ships stand still (Waiting) until then. Reason: the only start that is fair per
    round without a map change (flag 5); each team starts with its ship and decides who flies and who runs. A runner
    gets to the platforms when the pilot flies him in; the ship left outside its lane comes home by itself (B2.11).
  * Practice, or `bStartAboard` off: at a PlayerStart (`Team<id>` tags first, then the spawn fix below).
* **Spawn fix** (flag 7): `ChoosePlayerStart_Implementation` prefers PlayerStarts whose `PlayerStartTag` is `Team<id>`
  and that are unoccupied, then any unoccupied one, then any (always returning one, so the engine's "NO PLAYERSTART with
  positive rating" path at engine `GameModeBase.cpp:1184` never runs); and `RestartPlayer` (engine `GameModeBase.h:435`):
  if Super leaves the controller without a pawn, try the chosen start's location ringed by 8 directions at 250, 500 and
  750 cm with `UWorld::FindTeleportSpot` (the call `FitPawnOnTile` already uses, `MyGameMode.cpp:522`) and
  `RestartPlayerAtTransform`. Reason: the engine's own fallback keeps an occupied start only if `FindTeleportSpot` finds
  room next to it (engine `GameModeBase.cpp:1116-1123`); the PIE log line means it found none, so it is our "then any"
  plus the ring search that gets the second player a pawn (revision 1 said the engine always picks an occupied start:
  wrong).

#### B4.3 During play

Nothing is frozen. Players respawn without limit as today (`bRespawnEnabled`, `MyGameMode.h:62-63`); only ships have
lives. The server checks every 0.5 s: forfeit timers (B1.4), ship respawn timers, spawn protection, the time limit,
fall death (B9.6).

#### B4.4 Win, lose, draw, practice over, time limit

* Two active teams: a team whose LivesLeft is 0 and whose ship is dead is **eliminated**; the other team wins. Both in the
  same frame: Draw. A forfeit (B1.4): the other team wins.
* **Time limit** (`Rules.TimeLimitMinutes`, default 15, 0 = none; versus only, Q17): when it runs out, the tie-break
  decides at once: more ship lives left (as built: without the handicap's extra lives, so fewer ships lost wins,
  7.1 F4, Q23), then the higher hull health fraction of the living ships (a dead ship
  counts 0), then the team front further along the path (largest u of the team's on-foot players; a team with nobody on
  foot counts its ranking leader's last platform; this gives the race a stake), else Draw. Reason: lanes are out of
  each other's range (flag 3), an undriven ship is safe from the swarm, and players respawn freely, so a match where
  nobody attacks would otherwise never end. 15 min: three lives at the B3.5 rates take a few minutes when fights
  happen. Event TimeWarning at 1 min left; the match bar shows the clock.
* Practice (one active team): no winner; co-op practice ends in PracticeOver when its last ship dies; solo practice
  never ends by itself (B3.2). No time limit in practice.
* On the result: phase Ended, `Result` (TeamWon / Draw / PracticeOver), `EndReason` (Eliminated / Forfeit / TimeLimit /
  Host), `WinningTeam` (or 255), `PhaseEndServerTime` (for the restart countdown); event Ended. Cruising ships stop
  (Waiting); the sentinel wave spawners `StopWaves()` (`MechSentinelWaveSpawner.cpp:376-379`) and the Burrower spawns
  pause (B5.4); everything else keeps running.

#### B4.5 End screen

The match HUD's end panel (B8.5) shows VICTORY / DEFEAT / DRAW / PRACTICE OVER, ships left per team and the restart
countdown, on every machine from the replicated phase.

#### B4.6 Restart

After `EndScreenSeconds` (20 s; 0 = never by itself), on the pause menu's **Restart match** button (host only, B5.2) or on
`Aura.Match.Restart` (host): `AMyGameMode::RestartMatch` writes the teams into `UMyMatchMemorySubsystem` (B1.6),
RoundIndex + 1, and reloads the map with the current rules as URL options (B5.3): listen server
`GetWorld()->ServerTravel(MapPath + "?listen" + Options, true)` (engine `World.h:4231`); standalone
`UGameplayStatics::OpenLevel(this, MapPath, true, OptionsWithoutLeadingQuestionMark)` (OpenLevel adds its own `?`,
engine `GameplayStatics.cpp:992-995`, so `?Teams=..` would become `Map??Teams=..`). MapPath = the world's package name
without the PIE prefix. The project doesn't use seamless travel (no `bUseSeamlessTravel` in BP_MyGameMode, decoded), so
clients reconnect; teams come back from the memory subsystem (B1.6). The EOS session survives a ServerTravel (the menu's
own hosting path is a ServerTravel, `MainMenu3.cpp:1144`).

* The button matters: the console commands are compiled out of Shipping (`#if !UE_BUILD_SHIPPING`,
  `AirshipSubsystem.cpp:513`; the match console follows the same pattern), so a packaged host with EndScreenSeconds 0
  could otherwise never restart. On a listen server the host's pause menu runs on the server: it calls
  `AMyGameMode::RestartMatch` / `RequestStartMatch` directly (no RPC needed; a client's menu doesn't show the buttons).
* After the reload the host's `PostLogin` calls `StartSession` again (`MyGameMode.cpp:56-66`). PR B makes
  `UMultiplayerSessionsSubsystem::StartSession` (`MultiplayerSessionsSubsystem.cpp:387-402`) return early when the
  session's state is already InProgress (`SessionInterface->GetSessionState(NAME_GameSession)`); what EOS does with a
  second StartSession isn't known, so R6 adds a packaged two-machine check.

---

### B5. Rules and options

#### B5.1 The rules

`FMyMatchRules` (replicated on the game state, so clients' HUDs and the grapple can read them):

| Field | Default | Values |
|---|---|---|
| TeamMode | Auto | Auto, Practice, OneVsOne, TwoVsTwo |
| ShipLives | 3 | 1..9 |
| SwarmDifficulty | 1 (Normal) | 0..4 = the menu's DifficultyNames (`MainMenu3.h:98`) |
| TimeLimitMinutes | 15 | 0..60, 0 = none (versus only, B4.4) |
| bFriendlyFire | false | |
| bGrappleShips | true | |
| bLaneAssist | true | |

Defaults live in `UMyMatchSettings::DefaultRules` (new UDeveloperSettings, Config=Game, "Project Settings > Game > Match",
the UAirshipSettings / UBurrowerSettings pattern, `AirshipSettings.h:24`). No ini change is needed (C++ defaults).

#### B5.2 The host menu (MainMenu3)

* Difficulty: the existing `HostDifficultyComboBox` (`MainMenu3.h:221`, filled from DifficultyNames at `cpp:1042-1050`,
  read at `cpp:395-398`) becomes `Swarm`.
* Team mode: the existing `HostRulesComboBox` (`h:223`). `RuleSets` (`h:106`, the C++ default; WBP_MainMenu3 doesn't
  override it, checked by string scan) becomes `{ "Auto teams", "1v1", "2v2", "Practice" }`. The chosen string is already
  advertised as the session's Rules and used by the browse filter (`MultiplayerSessionsSubsystem.cpp:1128-1132`).
* The Rules box limits the Max Players box (`MaxPlayersComboBox`, `h:219`, choices `MaxPlayerChoices` `h:110`): 1v1 ->
  2, 2v2 -> 4 (the box is set and disabled), Auto and Practice -> free. Reason: revision 1 let "1v1" advertise 4 slots,
  and PreLogin then refused the third join with "That match is full".
* Ship lives: a new optional `UComboBoxString* ShipLivesComboBox` (BindWidgetOptional, choices `ShipLivesChoices = {1, 2,
  3, 5, 9}`, preselect 3). WBP_MainMenu3 gets the row by script (section 3, as_72). Without it: the default.
* Time limit, friendly fire, grapple, assist: no menu box (console, URL, settings).
* `UMainMenu3::BuildMatchOptions()` returns `?Teams=<auto|1v1|2v2|practice>?ShipLives=<n>?Swarm=<0-4>?Players=<max
  players>` (Play Solo: `Players=1`). It is appended to PathToLobby (`cpp:32`) at both exits:
  `ServerTravel(PathToLobby + Options)` after the session is created (`cpp:1144`) and
  `OpenLevelLeavingSession(PathToLobby + Options)` for Play Solo (`cpp:436`; Play Solo also calls
  `ReadHostSettingsFromWidgets` first, which it doesn't today, `cpp:431-437`). Our own `Players` name, not the engine's
  `MaxPlayers` (which AGameSession reads too).
* Pause menu (`PauseMenu3`): two host-only buttons, **Start match** (shown during WaitingToStart: calls
  `AMyGameMode::RequestStartMatch`) and **Restart match** (shown while the match is on: `AMyGameMode::RestartMatch`).
  Shown only when the owning player controller is local on the server (`HasAuthority()` and the game mode exists). The
  pause menu's in-game host settings (`PauseMenu3.cpp:272`, `UpdateHostSettings`) don't change match rules in PR B.

#### B5.3 How the choice reaches the game mode

`AMyGameMode::InitGame(MapName, Options, Error)` (engine `GameModeBase.h:62`) parses, in this order (later wins):
`UMyMatchSettings::DefaultRules`, the command line (`-MatchTeams= -MatchShipLives= -MatchSwarm= -MatchTimeLimit=
-MatchFF= -MatchGrappleShips= -MatchLaneAssist=`, FParse), the URL options (`UGameplayStatics::ParseOption`: `Teams`,
`ShipLives`, `Swarm`, `TimeLimit`, `FF`, `GrappleShips`, `LaneAssist`, `Players`, and `Match=0|1` to force the match off /
on). Bad values are clamped and logged. The result is kept on the game mode and copied into `AMyGameState::MatchRules`
in StartPlay before Super (the game state exists by then). Client join options are never read for rules (only
InitGame's, which are the host's). The restart (B4.6) writes all of them back into the URL.

#### B5.4 Swarm difficulty

What exists (verified):

* Wave spawner: `CountMultiplier` with `SetCountMultiplier` that re-plans running waves
  (`MechSentinelWaveSpawner.h:320-321`, `.cpp:403-421`); per-wave Health / Armor / Damage / AttackSpeed / MoveSpeed / SelfBuffChance multipliers
  (`h:81-100`) resolved by `ResolveWave` from curves or the hand-made list (`cpp:263-301`), clamped by `ClampWave`
  (`cpp:303-317`), folded by `ResolveWaveFolded` (`cpp:319-329`); counts by `ResolveCount` (`cpp:336-339`); `MaxAlive`
  (`h:377`, 500 in StartupMap, decoded).
* Global rules asset (`UMechSentinelSwarmRules`, `MechSentinelSwarmRules.h:61-190`): MaxAttackersPerPlayer (10 in
  DA_MechSentinelSwarmRules, decoded), SelfBuffChance, buffs, KillXP. `SetRulesOverride`
  (`MechSentinelSwarmSubsystem.h:178`); the lookup order is override > GameMode asset > class default (`cpp:289-300`). The header comment at `h:173`
  says the opposite: fix the comment.
* Burrower: `UBurrowerSettings` read with GetDefault on every poll (`BurrowerSpawnSubsystem.cpp:195-298`): SpawnInterval
  30 s, MaxAlivePerPlayer 1 (committed values; Talal has local edits to that header, so PR B never touches it);
  `CharacterLevel` 1 (`BurrowerCharacter.cpp:64`) sets the attribute effects' level (`:259`).

What PR B adds (combat owner):

* `FMechSentinelDifficultyScale` {Count, Health, Armor, Damage, AttackSpeed, MoveSpeed, SelfBuffChance, MaxAlive}, all 1
  = today. `AMechSentinelWaveSpawner::SetDifficultyScale(const FMechSentinelDifficultyScale&)` (server): the stat scales
  are applied in `ResolveWave` before `ClampWave` (so `GetWaveDefinition` previews stay right), Count in `ResolveCount`
  next to CountMultiplier (the designer's CountMultiplier is kept), MaxAlive scales the spawner's own MaxAlive read at
  BeginPlay; then `ReplanRuns()` like SetCountMultiplier. It must work **before BeginPlay** (it stores the scale; BeginPlay
  applies MaxAlive; ReplanRuns only runs once runs are planned), because the game mode calls it in StartPlay before
  Super: the path spawner builds the initial segments in its own BeginPlay (`MyHexPathSpawner.cpp:69-72`) and the
  External-mode spawner queues wave 1 from them (`MechSentinelWaveSpawner.cpp:1021-1062`, DelayBefore 4 s, SpawnDuration
  6 s), so revision 1's "applied at match start" (5 s later) gave most of wave 1 Normal stats. Live changes later
  (console, players joining) call it again; sentinels already alive keep their stats.
* SelfBuffChance is scaled in one place only: the wave's `SelfBuffChanceMultiplier` (`MechSentinelWaveSpawner.h:98-100`,
  which already multiplies the rules' chance). Revision 1 also scaled the rules copy's SelfBuffChance, which squared
  the preset (Nightmare 4x, Easy 0.25x).
* A transient copy of the GameMode's rules asset (`DuplicateObject`) with the preset's MaxAttackersPerPlayer only, passed
  to `SetRulesOverride`. No new assets.
* **Player count**: waves are per path segment with no player factor (`HandlePathSegmentSpawned`: wave number from the
  segment index; no player count anywhere in the spawner, grep), so 2v2 spreads one wave over four players. The game
  mode multiplies the preset's Count by `SwarmPlayerCountBase + SwarmPlayerCountPerPlayer x NumPlayers` (0.6 + 0.4 x N:
  1.0 for one player, 1.4 for two, 2.2 for four), capped at `SwarmPlayerCountMax` (2.2), and calls SetDifficultyScale
  again when NumPlayers changes. MaxAlive (500 x the preset) still caps the total.
* What difficulty does to a match: it mostly sets how risky the race is and how costly an attack sortie is (only a
  driven ship is a swarm target, players respawn freely). It doesn't decide who wins.
* `UBurrowerSpawnSubsystem::SetDifficultyOverride(float SpawnIntervalScale, int32 MaxAlivePerPlayer /*0 = config*/,
  int32 CharacterLevel /*0 = 1*/)` and `SetSpawningPaused(bool)`, read at the settings uses above; the level is set on
  the Burrower before its attributes are applied (`BurrowerCharacter.cpp:259`).

Presets (`UMyMatchSettings::SwarmDifficulties`, index = SwarmDifficulty; Normal = exactly today's game):

| | Easy | Normal | Hard | Very Hard | Nightmare |
|---|---|---|---|---|---|
| Count | 0.6 | 1.0 | 1.3 | 1.6 | 2.0 |
| Health | 0.7 | 1.0 | 1.3 | 1.6 | 2.0 |
| Armor | 0.75 | 1.0 | 1.15 | 1.3 | 1.5 |
| Damage | 0.6 | 1.0 | 1.3 | 1.6 | 2.0 |
| AttackSpeed | 0.85 | 1.0 | 1.1 | 1.2 | 1.3 |
| MoveSpeed | 0.9 | 1.0 | 1.05 | 1.1 | 1.15 |
| SelfBuffChance | 0.5 | 1.0 | 1.25 | 1.5 | 2.0 |
| MaxAlive (spawner cap) | 0.6 | 1.0 | 1.2 | 1.4 | 1.6 |
| MaxAttackersPerPlayer | 6 | asset (10) | 12 | 14 | 16 |
| Burrower SpawnInterval | x1.5 | x1 | x0.8 | x0.65 | x0.5 |
| Burrower MaxAlivePerPlayer | config | config | config | at least 2 | at least 2 |
| Burrower level | 1 | 1 | 2 | 3 | 4 |

Burrower MaxAlivePerPlayer is a floor on `UBurrowerSettings`' value, never a cut (7.1 F10): with Talal's local 10
every preset keeps 10.

These stack on the wave curves (which already grow with the wave number: Count x1 to x5.5 over 40 waves, lanes_map) and
on the player-count factor (Count only). The numbers are first guesses: Q13. Applied in StartPlay before Super, on every
rules change and when the player count changes; `Aura.Match.Swarm <n>` changes it live.

#### B5.5 Match on / off

`UMyMatchSettings::MatchMaps` (default `{ "StartupMap" }`, short map names without the PIE prefix, the UBurrowerSettings
AllowedMaps pattern, `BurrowerSpawnSubsystem.cpp:90-104`). CVar `Aura.Match.Enable`: -1 = by MatchMaps (default), 0 = off,
1 = on; read in InitGame. URL `?Match=0|1` wins over both. Only AMyGameMode runs a match.

With the match off the game plays as PR A (7.1 F8, F9; 7.3 for B9.1 / B9.2): no ship hook, the Burrower hunts a
piloted free ship, the lead pawn and path growth count ship-borne pawns, no lanes are built. One difference on
purpose: a kicked pilot of a free ship no longer leaves his character behind (7.1 F1). What the default on StartupMap
means for everyday Play and for older harnesses: 7.4.

#### B5.6 Talal's local files

The difficulty goes through runtime overrides, so `BurrowerSettings.h` (his uncommitted MaxAlivePerPlayer 10 and
SpawnHeightOffset -1500) stays untouched and keeps working as his base values. His local GE_GunShootDamage (1000 per hit,
round2_map) no longer decides ship balance (B6.5), but it still makes players one-shot each other with the gun once PvP
matters, and turret rounds (4 x the GE value) one-shot characters: Q18, asked before the first versus play test.

---

### B6. Friendly fire and enemy ship access

#### B6.1 One rule

`UMyTeamLibrary::IsFriendlyFireBlocked(const AActor* Instigator, const AActor* Target)`: true when the match is on,
`Rules.bFriendlyFire` is off, both resolve to the same valid team (`GetTeamId`, section 2.3) and Target isn't the
instigator itself. Free ships and team-less actors (sentinels, the Burrower, 255) are never protected. Damage is decided
on the server only, so the rules there are the authority.

#### B6.2 Where it goes (every player-made damage path, verified)

| Source | Where today | Change |
|---|---|---|
| Character gun on GAS actors | `GA_GunShoot::MyFunc`, ASC branch `GA_GunShoot.cpp:243-279` | return before applying when blocked (Avatar vs the target, after the hull-to-turret hand-on at `:222-231`) |
| Character gun on cannonballs | `:204-218` (own ship's balls skipped via IsRiderForDamage) | also skip balls whose source ship is a teammate's |
| Beam hit and every splash | `UMySplashDamageLibrary::IsDamageableEnemy` `MySplashDamageLibrary.cpp:92-105` | false when blocked (covers GA_Beam's hit `GA_Beam.cpp:163`, `:228` and the splash gather `MySplashDamageLibrary.cpp:166`) |
| Cannonball hit and splash | `AAirshipCannonball::ShouldIgnore` `AirshipCannonball.cpp:186-222` (used at `:241`, `:266`, `:298`) | true when blocked; the team comes from the new `SourceTeamId` stored on the ball at spawn (server), not from SourceShip at impact: the code already expects the ship to be gone by then (`:346-352`), and a gone ship would resolve to 255 and drop the protection |
| Turret rounds | `AAirshipTurret::ApplyBulletDamage` `AirshipTurret.cpp:703`, the comment "Team checks (a later PR) go here" at `:732` | return when blocked (OwnShip vs Target); enemy-ball tests at `:586` and `:679` treat teammates' balls like own balls |
| Fireballs (AMyProjectile) | overlap `MyProjectile.cpp:40-49`, no check at all | ignore the overlap (no damage, not destroyed) when blocked, instigator = `GetInstigator()`, else the spec context's instigator |
| Crew share | `AAirshipPawn::FlushCrewDamage` | unchanged: not friendly fire (the lead's decision) |
| Hull impacts | `AAirshipPawn::OnHullHit` | unchanged (physics) |
| Beam knockback in GA_BeamBP | Blueprint (mentioned at `GA_Beam.h:90`, `:119`); the asset calls `LaunchCharacter` (decoded: a string scan of GA_BeamBP.uasset finds `LaunchCharacter` / `LaunchVelocity`; whom it launches isn't decoded) | with PR B's fall death a teammate pushed off a platform is a real friendly kill. as_70 dumps the graph around LaunchCharacter (read only) before the first versus test; if it can reach teammates, a Branch on `UMyTeamLibrary::IsFriendlyFireBlocked` (BlueprintPure) goes before the call (by hand in the editor stage, Talal's OK, or a script); M3.1 checks it (teammate moved < 0.5 m) |

Shooting your own team's ship hull is blocked too (team 0 player vs team 0 ship); PR A left the shooter's own hull open
(SPEC_A 6.4).

#### B6.3 Enemy ship access

* `AAirshipPawn::CanBoard` (`AirshipPawn.cpp:1194-1219`) and `CanMount` (`:1708-1757`): false unless
  `UMyTeamLibrary::CanUseShip(Candidate, this)` (ship team 255, or match off, or the same team). Every path goes through
  them: F (`UAirshipPilotComponent::TryUseNearest`, `AirshipPilotComponent.cpp:367-450`, checks both at `:403` and the
  station loop), the mount RPC (`TryMount` `:452`), the console.
* Finding a ship to use is filtered with `UMyTeamLibrary::CanUseShip`, which works on every machine (it reads only
  replicated team ids), not with CanBoard (authority only, `AirshipPawn.cpp:1198`):
  * `UAirshipPilotComponent::FindBoardableAirship` (`:255-289`, BlueprintPure "any machine", `AirshipPilotComponent.h:59-61`),
    so the client's "Press F" prompt doesn't offer the enemy ship.
  * `UAirshipSubsystem::FindNearestAirship` (`AirshipSubsystem.cpp:150-172`) gains an optional `const APawn* ForUser`;
    `TryBoard(nullptr, true)` (`AirshipPilotComponent.cpp:309-313`), which `Aura.Airship.Board` uses
    (`AirshipSubsystem.cpp:762`), passes the player's character. Revision 1 filtered only FindBoardableAirship, which the
    console path doesn't call: in versus `Aura.Airship.Board` could have picked the nearer enemy ship and failed.
  * `Aura.Airship.Mount` needs nothing: `TryMount` already picks the nearest ship with `CanMount`
    (`AirshipPilotComponent.cpp:465-482`), which gets the team rule.
* Feedback: `TryUseNearest` remembers whether an enemy helm or station was in range and, when it refuses, calls the new
  client RPC `ClientUseRefused(EAirshipUseRefusal Reason)` (unreliable) -> static `OnLocalUseRefused` -> HUD toast "ORANGE
  ship: you can't use it" (B8.3).
* Enemies may still stand on a ship's deck (physics passengers stay team-blind, `IsPassengerCandidate`). The rider test
  is split in two:
  * `AAirshipPawn::IsRiding(const ACharacter*)`: today's body of `IsRiderForDamage` (`:1539-1571`), team-blind. It is
    what "ship-borne" means (0.3), so an enemy on your deck never becomes the lead pawn, grows the path, gets hunted by a
    Burrower or falls under the fall-death rule (B9.1, B9.2, B9.4, B9.6).
  * `IsRiderForDamage` = `IsRiding` plus a team test for characters that aren't attached: only the ship's own team (or
    anyone on a free ship) is spared by its cannonballs, turrets and aim traces. An enemy boarder on the deck can be shot
    by the turrets, and the pilot's aim trace no longer looks through him. Attached characters are the pilot and
    gunners, who are on the ship's team by construction.

#### B6.4 Sentinels and ships ("no swarms only attack ship when driving")

* Targeting is unchanged: sentinels take every player state's pawn (`MechSentinelSwarmSubsystem.cpp:447-470`, verified),
  so a ship is a target only while someone pilots it.
* Bullet damage follows the same rule for team ships. The tag `UMechSentinelSwarmSubsystem::BulletTargetTag` sits on
  three actors today: the hull (constructor, `AirshipPawn.cpp:397`) and both turrets (`SpawnTurrets`, `:2304`, and the
  turret's own BeginPlay, `AirshipTurret.cpp:176`). The turrets' HitBox is WorldDynamic and blocks Visibility
  (`AirshipTurret.cpp:97`), and the bullet's block trace damages any tagged actor it stops on
  (`MechSentinelSwarmSubsystem.cpp:687-691`), so revision 1's "hull tag only" would still have let a bullet aimed at a
  gunner damage a turret of an undriven ship. PR B adds one server function, `AAirshipPawn::RefreshSentinelBulletTags()`:
  the tag goes on the hull **and every turret** when `bDriven = HasPilot() || GetController() != nullptr` (the same rule
  the targeting uses: a player whose character was destroyed aboard keeps flying through the controller,
  `AirshipPawn.cpp:606-612`), or the ship is free (255), or `bSentinelBulletsHitUndrivenShips`; otherwise it is removed
  from all three. Called from `OnRep_PilotCharacter` (`:1424-1451`, which also runs on the server at board and exit),
  `PossessedBy` / `UnPossessed`, the end of `SpawnTurrets`, `SetTeamId`, and the pilot-character-destroyed branch at
  `:606-612`. The turret's own add in BeginPlay is kept only for a turret without a ship (`GetShip()` null); a turret
  with a ship leaves the tag to it. With the tags off, a bullet that stops on an undriven ship does nothing (untagged
  blockers do nothing, `:678-708`), and the turret hand-on (`:693-704`) isn't asked either.
* Consequence: gunners on an undriven ship are still targets (they are players), but the hull stops most bullets aimed at
  them (PR A risk 1: the lid hides them). Setting `bSentinelBulletsHitUndrivenShips` (default false) restores PR A's
  behaviour. Q10.

#### B6.5 Damage to ships in a match (fixed, not the gun's GE value)

The gun's damage is GE_GunShootDamage's value (committed 1 per hit, Talal's local 1000, round2_map), and the turret
round is `TurretGunDamageMultiplier` (4) x that value read at runtime (CPP_NOTES 15.2). Ship lives can't be balanced
on a number that differs by 1000x between the committed tree and Talal's (flag 11, B3.5). So, while the match is on,
damage to a **team ship or a team ship's turret** is a fixed amount:

| Source | Setting (`UMyMatchSettings`) | Default | Where |
|---|---|---|---|
| Character gun, per hit | `ShipDamageGunHit` | 5 | `GA_GunShoot::MyFunc`, after the turret hand-on (`GA_GunShoot.cpp:222-231`): a hull target calls `AAirshipPawn::ApplyShipDamage(ShipDamageGunHit, Shooter)` (the ship's own damage path with its own effect, `AirshipPawn.h:383-389`, unrelated to GE_GunShootDamage; it gains an optional `AActor* DamageInstigator` that goes into the effect context, so the under-attack event can tell a shot from a crash, B8.3), a turret target the new `AAirshipTurret::ApplyTurretDamage(float, AActor*)` (same pattern on the turret's ASC); the GE spec isn't applied to them |
| Turret round | `ShipDamageTurretRound` | 4 | `AAirshipTurret::ApplyBulletDamage` (`AirshipTurret.cpp:703`): for a ship or turret target the magnitude is this value instead of `GetBulletDamage()` |
| Cannonball, beam, splash, impacts | unchanged | 60, 150 / 75, physics | not GE_GunShootDamage based already |

0 = the PR A behaviour (the GE value). Free ships and the match off: PR A behaviour. Characters still take the gun's GE
value and 4 x it from turrets (that part of Talal's local value is Q18). Defaults: 4 per turret round is today's
committed number (4 x 1); 5 per gun hit makes the on-foot gun a slow but real threat (87 s per ship alone at the
committed fire rate, B3.5) instead of 7 minutes or 0.2 s.

---

### B7. Grapple on ships (ship hook)

Behind `Rules.bGrappleShips` (default true). With the match off the ship hook is off and the grapple is PR A's,
unless `UMyMatchSettings::bShipHookOutsideMatch` (default false; then `DefaultRules.bGrappleShips` decides): 7.1 F9.

#### B7.1 What the player does

Aim the crosshair at a ship's hull (within `MaxShipHookDistance` 12000 cm) and press the grapple: the hook flies there,
then the rope **reels** the player in onto the deck. No pendulum swing on ships. Default: own team's ship or free ships
only (`bShipHookOwnTeamOnly` true, Q1). Reason for 120 m: the hull's inner side is 14-84 m from the nearest platform edge
(flag 2), 75 m from the start floor's corner for the floor side (Appendix C), and the pace law keeps the ship within
about 90-100 m of the team front (B2.4). The HUD tells the player when his ship is in reach ("AIM + GRAPPLE" on its
marker, B8.2).

#### B7.2 Search (owning client, `UGA_GrappleSwing2`)

* The crosshair ray is traced to max(MaxGrappleDistance, MaxShipHookDistance). Fan rays never pick ships (a ship hook is
  a deliberate aim).
* `EvaluateHit` (`GA_GrappleSwing2.cpp:1227-1296`): before the object-type and pawn rejections at `:1240-1241`, a hit on
  an `AAirshipPawn` (or an actor attached to one: the turrets) goes to a new `EvaluateShipHit`: ship alive, rule on, team
  rule, distance <= MaxShipHookDistance, ship speed <= `ShipHookMaxShipSpeed` (3000 cm/s: above the lane's top speed of
  2800, B2.4, so a lane ship is never refused). No height, floor or arc rules.
* Target point: from the hit, the hull-local point (X_hit, Y_hit clamped to the deck, 1500) traced straight down onto the
  hull (`UPrimitiveComponent::LineTraceComponent` on `GetHull()`, the way UnboardPilot finds the deck,
  `AirshipPawn.cpp:1352-1358`), plus 150 cm: `TargetHullLocal`. The deck is the walkable lid (CPP_NOTES 3).
* Target data (`FGameplayAbilityTargetData_GrappleSwing2`, `h:380-425`) gains: `uint8 bShipReel`, `TWeakObjectPtr<AActor>
  AnchorActor` (serialized through the package map), `FVector TargetHullLocal`, `FVector AnchorVelocity` (the ship's
  velocity at the target point on the client: linear plus angular x r). `Anchor` = the world target point at
  ClientStartTime.

#### B7.3 The reel (both machines, predicted like the swing)

A new root motion source `FRootMotionSource_GrappleReel2` in the same files (Override, predicted, saved and replayed by
the CMC like the swing's, `GA_GrappleSwing2.cpp:151-860`). Its anchor moves at a constant velocity, so the owning client
and the server compute exactly the same point at every move without knowing each other's view of the ship:

```
A(t)   = AnchorStart + AnchorVelocity * t            // t = the source's own time since the reel began
Aim(t) = A(t) + Up * min(ShipReelLiftMax, ShipReelLiftFraction * |A(t) - X|)   // over the gunwale, not into the side
V      = AnchorVelocity + ShipReelSpeed * normalize(Aim(t) - X)
finish when |A(t) - X| <= ShipReelArriveDistance, or the capsule is inside the deck box (hull-local, + 200 cm) on this
         machine's view of the ship, or t >= ShipReelMaxTime:
         leave with AnchorVelocity + Up * 200, movement mode Falling (it lands on the lid and becomes a rider)
```

`ShipReelSpeed` 3000 cm/s (120 m in 4 s), `ShipReelArriveDistance` 250, `ShipReelMaxTime` 5 s, `ShipReelLiftFraction`
0.25, `ShipReelLiftMax` 800. The deck-box finish lets a reel that drifted a little still land; if the two machines
finish a frame apart, the CMC corrects the last metres. A lane ship keeps a constant velocity during a reel because the
server freezes its lane speed while the reel runs (B7.4); a piloted ship that turns or brakes drifts off the line.

#### B7.4 Server validation and the moving ship

`ServerValidate` (`cpp:1499-1539`) for a reel: the ship (AnchorActor) alive and allowed; the server's own hull point
(HullTM_server x TargetHullLocal) within `ShipHookMaxDrift` (600 cm) + |V_ship| x 0.3 s of A at the server's time;
|AnchorVelocity - V_ship_server| <= 500 cm/s; distance <= MaxShipHookDistance + the existing range slack; the rope line of
sight with TraceStatic (WorldStatic / WorldDynamic, `GA_GrappleSwing2.h:372`) **ignoring the ship and every actor
attached to it**: the turrets' HitBox is WorldDynamic (`AirshipTurret.cpp:97`), so revision 1's trace would have been
blocked by the ship's own turrets. While the reel runs, the server's Poll compares A(t) with its hull point; a drift
beyond the same allowance as the validation, `ShipHookMaxDrift` (600 cm) + |V_ship| x `ShipHookLatencyAllowance`
(0.3 s), ends the reel through the existing reject path (`OnServerRejected`, `cpp:1551`): the player falls. Revision 1
used 600 cm alone in the poll, so a 25 m/s ship seen 0.3 s late was 7.5 m off at the first poll. Reason: client and
server see the ship at different times (physics replication lag), so neither can use its own view of the hull.

**The lane holds still for a reel**: on a valid reel the server calls `AAirshipPawn::NotifyIncomingReel(Reeler, true)`,
and `(Reeler, false)` when it ends (finish, reject, ability end; at most ShipReelMaxTime + 1 s as a safety). While any
reel toward the ship is registered, `HasIncomingReel()` is true and the lane keeps its TargetSpeed and heading as they are
(no ramp, no cap stop, no pace change, B2.4). Reason: the lane ramps its speed at 2.5 m/s^2 and eases into its cap;
inferred, a 4 s reel during a 1 m/s^2 ramp drifted 8 m and a stop at the cap about 9 m, so revision 1 cancelled reels
exactly when players needed them. A piloted ship is the pilot's: no freeze, the drift allowance applies.

#### B7.5 Cosmetics and risk

The rope cue's end is a world point today (`cpp:1451`). For a reel the owner and server update it from A(t) through
`GetGrappleSwing2State` (`cpp:902-923`); on other machines the rope end may lag the ship (cosmetic, checked by eye in T6.1 / M7.2). If B7
proves riskier than this, it ships as a separate commit in PR B and the rest doesn't depend on it.

---

### B8. HUD and feedback

All drawn in C++ (NativePaint, no assets), the UAirshipHUDWidget approach (`AirshipHUDWidget.h:13-30`).

#### B8.1 Match bar (new `UMyMatchHUDWidget`, top centre, every player)

Added by `AMyHUD::InitOverlay` next to the minimap (`MyHUD.cpp:23-76`, `MatchWidgetClass` defaulting to the C++ class
like `MinimapWidgetClass` at `:17-20`), ZOrder 2, draws nothing while the phase is None.

```
 BLUE (YOU)  [##][##][##]  [=========  ]      12:41      [######     ]  [##][##][  ]  ORANGE
             SHIP: LANE  6 m/s  (or WAITING FOR TEAM / PILOTED BY <name> / OUT OF LANE / RETURNS TO LANE IN 12 s /
                   BACK IN 7 s / NO SHIPS LEFT)
```

* Lives are boxes, filled = left (solo practice: "SHIPS LOST n"). Next to them each ship's hull bar (from FMyTeamState
  `ShipHealthPct`, written by the server at most 4 Hz; empty while dead), so everyone sees both hulls.
* Centre: the phase text (WAITING FOR PLAYERS 1/2 - host: Esc > Start match, MATCH STARTS IN n, PRACTICE, FIGHT for 2 s
  after the start, VICTORY / DEFEAT / DRAW / PRACTICE OVER), else the match clock (time left; hidden with no limit).
* **Objective line**, 6 s at the start and on the PracticeToVersus start: "Sink ORANGE's ship 3 times. Keep yours
  afloat." (the enemy's LivesLeft), and with a time limit "Most ships left after 15:00 wins." Practice: "Practice: learn
  to fly. Nobody is against you."
* Practice shows only the own team.

#### B8.2 Ship markers

For each team ship alive: a diamond 15 m above the ship (`ProjectWorldLocationToScreen`), team colour, distance in m, a
small hull bar under it, "YOU" on the own team's, a shield while spawn-protected (`ProtectionEndServerTime`, B3.4). The
own ship's marker sticks to the screen edge with an arrow when off screen; the enemy's only when on screen or within
600 m. On foot within `MaxShipHookDistance` of the own ship (and the rule on): "AIM + GRAPPLE" under its marker. The own
marker flashes for 2 s on a ShipUnderAttack event. Hidden for the player at that ship's helm.

#### B8.3 Toasts (centre, 3 s, at most 3)

From `AMyGameState::MulticastMatchEvent(EMyMatchEvent, uint8 Team, int32 Value)` (reliable, the respawn FX multicast's
pattern, `MyGameState.h:81-82`): "Your ship was destroyed: 2 left", "ORANGE ship destroyed", "Your ship is back",
"**YOUR SHIP IS UNDER ATTACK**" (event ShipUnderAttack: the game mode binds the Health change delegate of each team
ship's ASC at SpawnTeamShip, server; a loss whose effect instigator isn't the ship itself sends it, at most once per
`ShipUnderAttackInterval` 5 s per team, Value = the health percent; hull impacts call `ApplyShipDamage` on the ship's
own ASC, `AirshipPawn.cpp:3718`, `:3735`, so crashes don't count, while B6.5's gun hits pass the shooter as the
instigator; the same delegate writes ShipHealthPct), "Your ship is returning to its lane", "1 minute
left", "ORANGE has no players: they forfeit in 30 s", "A second player joined: 1v1 starts in 5 s". From the pilot
component: "That's ORANGE's ship".

#### B8.4 Name tags and teammates

* Over every other player's character (not ship-borne pilots: their ship's marker shows them): the name in team colour,
  13 px, 2.2 m above the capsule. Teammates always (up to the relevancy range, B10); enemies within 100 m, or further
  when in line of sight (one Visibility trace per enemy every 0.25 s). Every player is the same mech, so this is the only
  way to tell friend from foe on foot.
* Crosshair: the match HUD traces from the camera every frame (Pawn channel, 200 m); on a teammate it draws "TEAMMATE"
  under the screen centre in team colour (the on-foot crosshair isn't drawn in C++, grep, so it is a Blueprint widget;
  PR B doesn't touch it). A shot at a teammate does
  nothing (B6.1), and this says why.

#### B8.5 End panel

Centre, 520 x 260: the result and its reason ("ORANGE ran out of ships", "Time up: BLUE has more ships left", "ORANGE
forfeited"), "BLUE 2 ships left - ORANGE 0", "Restarting in 15 s" (or "Host: Esc > Restart match"). The panel is drawn
in NativePaint and takes no input; the button is in the pause menu (B5.2).

#### B8.6 Pilot panel (UAirshipHUDWidget)

A LANE row under the GUNS row (PR A added PILOT and GUNS rows, `AirshipHUDWidget.h:24-29`) that says what an exit does
now, from the replicated lane state, hint and the ship's speed:

| Situation | LANE row |
|---|---|
| Assist | "LANE AUTO - W/S/A/D take the helm" |
| PilotedInLane, speed <= LaneParkSpeed | "IN LANE - EXIT = CRUISE" |
| PilotedInLane, faster | "IN LANE - SLOW DOWN TO PARK (8 m/s)" |
| OutOfLane | "LANE 35 m <- - EXIT = DRIFT + HOLD, BACK IN 20 s" (side relative to the hull, from the hint's lateral error and lane yaw; the recall part only with bShipRecall) |

Then "LIVES 2". Gunners see the same row (read only) plus "RETURNS TO LANE IN n s" while the recall timer runs. Hidden on
free ships. The panel grows by one row in every scheme for team ships only (Classic scheme checks run on free ships).

---

### B9. The existing race

#### B9.1 The lead pawn (culling hazard)

`SelectLeadPawn` returns the ranked leader's `GetPawn()` (`MyHexBridgeSubsystem.cpp:4777-4803`), which is the ship while
he pilots. `GetLeadPathDistance` projects that pawn onto the path (`:4816-4836`) and drives platform culling
(`MyHexPlatform.cpp:644-678`, CullBehindDistance 20000, `MyHexPlatform.h:700-701`) and segment destruction
(`MyHexPathSpawner.cpp:471-500`). A leader flying 600 m ahead would cull platforms in front of his runners. Riders have
the same problem: their position is the ship's.

Fix (lanes owner): `SelectLeadPawn` skips leaders whose pawn is ship-borne (`UAirshipSubsystem::IsShipBorne`) and returns
the first on-foot leader, else null. `GetLeadPathDistance`, when there is no lead pawn but the ranking has a leader, returns
`AMyGameState::GetLeadSplineDistance()` (the leader's last platform's path distance, `MyGameState.h:60-62`; SplineDistance
is a world path distance, `MyHexPathSegment.h:51-56`). Effect: segment destruction follows the leader's last platform; the
platforms' own culling pauses (`UpdateLeadState` returns with no lead pawn, `MyHexPlatform.cpp:559-562`) until someone on
foot leads again, which happens as soon as a runner lands further (the ranking only changes on landings,
`MyPlayerState.cpp:27-49`). Platform collapse is unaffected (driven by the ranking, `MyGameState.cpp:83`). Changing
`MyHexPlatform.cpp` to cull around the leader's last platform instead was considered and left out (more code in the
platform; Talal has its header staged).

#### B9.2 Path growth

`CheckPlayers` (`MyHexPathSpawner.cpp:268-279`) skips ship-borne pawns: the path grows only for players on foot. A pilot
racing ahead no longer adds segments (each segment also starts a sentinel wave, `MechSentinelWaveSpawner.cpp:1021`).
When everyone is aboard ships, the path waits and the lane ships wait at CruiseEndU.

#### B9.3 Ranking

Unchanged: ship-borne players keep the rank of the platform they last landed on (only on-foot landings update it,
`MyCharPlayer.cpp:359`). The leaders' HUD TODO (`MyGameState.cpp:94`) is not PR B's.

#### B9.4 Burrower

It hunts each player's pawn with the combat interface (`BurrowerSpawnSubsystem.cpp:231-232`, `:403-405`;
`BurrowerCharacter.cpp:513-528`, `:550-580`), which includes a piloted ship (`AAirshipPawn` implements it,
`AirshipPawn.h:80`). A Burrower chasing a ship 225 m out would carve through every platform in between (its rotor collapses
the tiles it touches, `BurrowerCharacter.h:14-18`). Fix: `ABurrowerCharacter::IsLivingTarget` returns false for ship-borne
pawns while a match runs (with the match off it is PR A's, 7.1 F8); the subsystem then treats the player like one without a pawn: no spawns, and his spawn countdown is paused while
he is aboard (`BurrowerSpawnSubsystem.cpp:252`). There is **no** respawn grace when he is back on foot (revision 1 said
there was): the grace branch runs only for a new pawn (`:234-244`), and after unboarding `Entry.Pawn` is still the same
character. Accepted: the countdown picks up where it paused.

#### B9.5 Sentinel waves

Waves start at the segment box's top corners, +-200 m from the path at S = 2 (lanes_map), 25 m inside the lanes. Only
piloted ships are targets (B6.4). No change.

#### B9.6 Match fall death

Server, every 0.5 s while the match is on, for each player state's **own pawn** that is a character (not every
character in the world): it dies through `IMyCombatInterface::Die` (the normal death and respawn,
`MyGameMode.cpp:184-193`) when all of these hold:

* it is alive and **not ship-borne** (`UAirshipSubsystem::IsShipBorne` false: not attached as pilot or gunner, not
  riding, 0.3);
* its Z is more than `FallDeathDepth` (8000 cm) below the lane / path height at its own u;
* its movement mode has been MOVE_Falling with no movement base for more than `FallDeathMinFallTime` (1 s).

Reasons: the flight model has no altitude floor over the void (MinClearance acts only with ground below,
`AirshipFlightComponent.cpp:1489`), so a ship diving under the platforms would otherwise kill its pilot, gunners and
deck riders; and a seated pilot is unpossessed (`BoardPilot` possesses the ship, `AirshipPawn.cpp:1320`), so his death
would reach `OnPlayerPawnDied` with a null controller (`MyGameMode.cpp:188-191`) and `ScheduleRespawn` would return on
it (`:225`): stuck with a dead character attached to the ship. Checking only the player states' pawns and skipping
ship-borne ones avoids both. A dying ship's crew is checked once it is ejected (B3.3).

80 m is below every platform: tile tops reach 16.2 m below path height and the bottom pillars hang about 10 m under them
(lanes_map, memory bottom-pillar-gc), so a fall from the upper chain onto the lower one never triggers it. From a ship
at lane height, ejected upward, it triggers about 5.5-7 s after the ejection (B3.3, inferred). 0 = off. Q4.

#### B9.7 Respawn of players

Still past the global lead, because everything behind it collapses (`FindRespawnSpot`, `MyGameMode.cpp:372-455`: only
platforms with SplineDistance beyond the lead's are candidates), but **on the player's own side of the path** in a
versus match: of the candidates sorted along the path, the first 6 within 6000 cm x S of spline distance of the nearest
are re-sorted by `side x UMyLaneSubsystem::GetLateralFromPath(platform)` (largest first: furthest toward his own lane),
then the existing order. Reason: revision 1 could respawn a player on the enemy's side of the field, up to about 425 m
from his own lane, far past the hook. A late joiner during InProgress spawns like a match-start player (B4.2: aboard
his ship when `bStartAboard` and it is alive, else by this rule). Option `bRespawnAboard` (default off, Q15): respawn on
the own ship's deck when it is alive, in its lane zone and hasn't been damaged for 5 s. Off by default because a
respawn aboard leaves a runner 225 m out until a pilot flies him in.

---

### B10. Replication and authority

| State | Lives on | Replication | Written by |
|---|---|---|---|
| TeamId | AMyPlayerState | Replicated, OnRep_TeamId | server (GameMode) |
| TeamId | AAirshipPawn | Replicated, OnRep_TeamId (set before FinishSpawning; claimed ships later) | server (GameMode) |
| MatchPhase, MatchRules, Teams[2] (incl. ShipHealthPct, LaneSide, ShipsLost, BonusLives), Result, EndReason, WinningTeam, PhaseEndServerTime, MatchEndServerTime, ExpectedPlayers, RoundIndex | AMyGameState (always relevant) | Replicated; OnRep -> OnMatchChanged (native multicast); ShipHealthPct written at most 4 Hz | server (GameMode) |
| Match events | AMyGameState | NetMulticast Reliable (ShipUnderAttack at most once per 5 s per team) | server |
| LaneState, LaneHint, RecallServerTime | UAirshipLaneComponent on the ship (ship is always relevant, `AirshipPawn.cpp:284`) | Replicated; hint written at most every `LaneHintInterval` 0.25 s | server |
| ProtectionEndServerTime | AAirshipPawn | Replicated | server |
| Team memory across a restart | UMyMatchMemorySubsystem (game instance) | not replicated (host only) | server |
| **Relevancy of player characters** | every player character while the match is on | `SetNetCullDistanceSquared(MatchNetCullDistance^2)`, 60000 cm, set on the server in `AMyGameMode::SetPlayerDefaults` (`MyGameMode.cpp:107-112`) | server |
| Lane geometry, lane targets, forces | UMyLaneSubsystem, UAirshipLaneComponent, UAirshipFlightComponent | server only | server |
| Use refusal | UAirshipPilotComponent | Client RPC, unreliable | server |
| Ship hook data | GA_GrappleSwing2 target data | the ability's existing server RPC | owning client, validated by the server |

`FMyLaneHint` {int16 LateralDm, int16 VerticalDm, int32 ProgressDm, int16 LaneYawDeg10, uint8 Clamp}: about 11 bytes at
4 Hz per ship. The ship already replicates every frame while awake (`bReplicateEveryFrame`, `AirshipPawn.h:1249`).

**Relevancy.** Characters use the engine's default net cull distance, 150 m (engine `Actor.cpp:312`,
`SetNetCullDistanceSquared(225000000)`); nothing in Source overrides it (grep) and BP_MyCharMech has no `NetCull` string
(decoded: it keeps the default). Only pilots and gunners are made always relevant (`AirshipPawn.cpp:1310`, `:1804`).
With lanes 450 m apart, deck riders, players reeling to a ship and enemies across the field would not replicate to
most viewers, and a client can't aim at what it doesn't have (the beam's hit check needs the client to name the hit
character, `GA_Beam.h` ApplyBeamDamage). 600 m covers the lane separation plus the length of a fight; with at most 4
players the extra traffic is small. Mass sentinels replicate by their own LOD distances (engine default: off beyond
50 m, `MassReplicationFragments.cpp:59-62`; the project's `DA_MechSentinelConfig` sets its own, not decoded): M8.2
checks that a client at the path centre sees the sentinels attacking a driven lane ship, R13.
Countdowns use `GetServerWorldTimeSeconds()`. Clients never decide team, lane, lives, damage or phase; the console
commands that change state are server-only (`CheckServer`, the `AirshipSubsystem.cpp:517-525` pattern).

---

### B11. Console and telemetry for tests

Full list in Appendix B. Summary:

* `Aura.Match.Status` (any machine), `Aura.Match.Rules k=v ...`, `Aura.Match.Set <Name> <Value>` (UMyMatchSettings on this
  machine), `Aura.Match.Start`, `Aura.Match.End <Team|-1>`, `Aura.Match.Restart`, `Aura.Match.Team <Player> <Team>`,
  `Aura.Match.ShipLives <Team> <N>`, `Aura.Match.KillShip <Team>` (DebugKill: no crew share, `AirshipPawn.h:392`),
  `Aura.Match.DamageShip <Team> <Amount>` (`ApplyShipDamage`, `AirshipPawn.h:388-389`, with the crew share; `Aura.Airship.Damage`
  hits every ship, `AirshipSubsystem.cpp:785`),
  `Aura.Match.Swarm <0-4>`, `Aura.Match.Recall <Team>`, `Aura.Match.Dump [path]`; CVar `Aura.Match.Enable`.
* `Aura.Lane.Status`, `Aura.Lane.Teleport <Team> <U m> [dZ m]`, `Aura.Lane.Rebuild`, `Aura.Lane.Check` (B2.1: the
  smallest gap between the hull footprint on the lane and the field, both sides, logged with its u); CVar
  `Aura.Lane.Debug 0|1|2`.
* `Aura.Airship.Telemetry` (`AirshipSubsystem.cpp:900-902`) gets a fourth line: team, lane state, u, lateral / vertical
  error, target speed, clamp. `FAirshipFlightTelemetry` (`AirshipTypes.h:330-331`) gains TeamId, LaneState, LaneUM,
  LaneLateralErrorM, LaneVerticalErrorM, LaneTargetSpeedMS, LaneClamp, bUnpilotedLane.
* `Aura.Match.Dump` writes `Saved/Match/match_state.json`: phase, rules, result, teams (players, lives, ship, respawn
  time), ships (telemetry above, position, velocity), players (team, pawn class, ship-borne, u, health), path end u,
  cruise end u. The harnesses read this and the BlueprintPure getters.
* Every state change logs one line in a `LogMatch` / `LogLane` category (the harness scans them).

---

### B12. How a match plays (roles and counter-play)

Revision 1 never said what players who don't drive are for. This is the loop PR B is built for, so the numbers above
can be judged against it.

| Role | Does | Risk / counter |
|---|---|---|
| **Pilot** | Takes the ship out of the lane to attack: broadside (80/s) or the turrets in the bow arc, B3.5; drops runners on the platforms | His ship is a swarm target while driven (B6.4); he takes 25 % of the hull's damage (crew share); the enemy's pilot and gunners shoot back |
| **Gunner** | Mans a cannon or a turret on his own ship: about doubles its firepower | Safe from the swarm on an undriven ship (the hull stops the bullets), but an undriven ship goes home after 20 s outside its lane (B2.11) |
| **Runner** | Races on the platforms: sets his ship's pace (team front, B2.4), grows the path, wins the time-limit tie-break by the team front (B4.4); hooks back to his ship (B7) | Swarm and Burrower; the fall |
| **Sniper** | From the platform edge on the enemy's side: beams the enemy ship (150 per hit, 200 m range) or shoots it (5 per hit, B6.5) | The enemy's turrets (only while its pilot fires them), its gunners, the swarm on foot; crossing the field takes time |

Defending: the "under attack" alert and the hull bars (B8) say when to go home; spawn protection (B3.4) gives a
respawned ship time to be crewed; the hook and the pace law keep the ship within reach of its runners; respawns land
on the own side of the field (B9.7).

---

## 2. File ownership and the API contract

No two owners touch the same file. The lead owns this spec, commits, editor runs and `Config/*` (no ini change needed).

| Owner | Files (only these) |
|---|---|
| **match** | new `Source/Aura/Public/Match/MyMatchTypes.h`, `MyMatchSettings.h`, `MyTeamLibrary.h`, `MyMatchHUDWidget.h`, `MyMatchMemorySubsystem.h`; new `Source/Aura/Private/Match/MyTeamLibrary.cpp`, `MyMatchHUDWidget.cpp`, `MyMatchConsole.cpp`, `MyMatchMemorySubsystem.cpp`; `Public|Private/MyGameMode.*`, `MyGameState.*`, `MyPlayerState.*`; `Public|Private/PlayerInput/MyPlayerController2.*`; `Public|Private/UI/MyHUD.*` |
| **lanes** | new `Public|Private/Match/MyLaneSubsystem.*`; new `Public|Private/Airship/AirshipLaneComponent.*`; `Public|Private/Actors/MyHexPathSpawner.*`; `Public|Private/Actors/MyHexBridgeSubsystem.*` |
| **airship** | `Public|Private/Airship/AirshipPawn.*`, `AirshipFlightComponent.*`, `AirshipPilotComponent.*`, `AirshipSubsystem.*`, `AirshipHUDWidget.*`, `AirshipCannonball.*`, `AirshipTurret.*`, `AirshipTypes.h`; `Docs/Airship/CPP_NOTES.md` (new section 16), `Docs/Airship/HOW_TO_FLY.md` |
| **combat** | `Private/AbilitySystem/Abilities/GA_GunShoot.cpp`, `Public|Private/AbilitySystem/MySplashDamageLibrary.*`, `Private/AbilitySystem/MyAttributeSet.cpp` (the spawn-protection gate only, B3.4), `Private/Actors/MyProjectile.cpp`, `Public|Private/MechSwarm/Spawning/MechSentinelWaveSpawner.*`, `Public/MechSwarm/Core/MechSentinelSwarmSubsystem.h` (comment fix only), `Public|Private/Burrower/BurrowerSpawnSubsystem.*`, `Private/Burrower/BurrowerCharacter.cpp` |
| **grapple** | `Public|Private/AbilitySystem/Abilities/GA_GrappleSwing2.*`, `Docs/GA_GrappleSwing2.md` |
| **menu** | `Public|Private/EOS/MainMenu3.*`, `Public|Private/EOS/PauseMenu3.*` (Start / Restart match buttons), `Private/EOS/MultiplayerSessionsSubsystem.cpp` (StartSession skip, B4.6) |
| **assets** | new `Docs/Airship/scripts/ue/as_70_match_plan.py` .. `as_76*.py` (section 3; numbers 70+ because PR A's editor stage already uses as_60*) |

`Aura.Build.cs`: no change (UMG, GameplayAbilities, Niagara, EnhancedInput, DeveloperSettings, Slate are already
dependencies, `Aura.Build.cs:11-22`, verified). `MyHexPlatform.h` and `BurrowerSettings.h` are not touched (0.2).

Order: match writes `MyMatchTypes.h`, `MyMatchSettings.h` and `MyTeamLibrary.h` first (header-only API, below); then all
owners in parallel against sections 2.1-2.8; the first build after the airship owner is done.

### 2.1 match: `Match/MyMatchTypes.h` (exact)

```cpp
#pragma once
#include "CoreMinimal.h"
#include "MyMatchTypes.generated.h"

class AAirshipPawn;

namespace MyMatch
{
	constexpr uint8 NoTeam = 255;
	constexpr int32 NumTeams = 2;
	constexpr int32 NumDifficulties = 5;
}

UENUM(BlueprintType) enum class EMyMatchPhase : uint8 { None, WaitingToStart, Countdown, InProgress, Ended };
UENUM(BlueprintType) enum class EMyTeamMode : uint8 { Auto, Practice, OneVsOne, TwoVsTwo };
UENUM(BlueprintType) enum class EMyMatchResult : uint8 { None, TeamWon, Draw, PracticeOver };
UENUM(BlueprintType) enum class EMyMatchEndReason : uint8 { None, Eliminated, Forfeit, TimeLimit, Host };
UENUM(BlueprintType) enum class EMyMatchEvent : uint8
{
	Countdown, Started, ShipDestroyed, ShipRespawned, TeamEliminated, ForfeitWarning, Forfeited, PracticeToVersus, Ended,
	ShipUnderAttack, ShipReturning, TimeWarning
};
UENUM(BlueprintType) enum class EMyLaneState : uint8 { NoLane, Cruising, Waiting, Assist, PilotedInLane, OutOfLane, Parked, Returning };
UENUM(BlueprintType) enum class EMyLaneClamp : uint8 { None, TeamPace, PathEnd, Blocked, NotStarted, Ended, Bypass, Reel };

USTRUCT(BlueprintType) struct FMyMatchRules
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EMyTeamMode TeamMode = EMyTeamMode::Auto;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, meta = (ClampMin = "1", ClampMax = "9")) int32 ShipLives = 3;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, meta = (ClampMin = "0", ClampMax = "4")) int32 SwarmDifficulty = 1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, meta = (ClampMin = "0", ClampMax = "60")) int32 TimeLimitMinutes = 15;  // 0 = none
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bFriendlyFire = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bGrappleShips = true;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bLaneAssist = true;
};

USTRUCT(BlueprintType) struct FMyTeamState
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly) uint8 TeamId = MyMatch::NoTeam;
	UPROPERTY(BlueprintReadOnly) bool bActive = false;
	UPROPERTY(BlueprintReadOnly) int32 NumPlayers = 0;
	UPROPERTY(BlueprintReadOnly) int32 LivesLeft = 0;
	UPROPERTY(BlueprintReadOnly) int32 BonusLives = 0;               // smaller team handicap (B1.2)
	UPROPERTY(BlueprintReadOnly) int32 ShipsLost = 0;
	UPROPERTY(BlueprintReadOnly) int8 LaneSide = 0;                  // +1 right, -1 left, 0 none (B1.6)
	UPROPERTY(BlueprintReadOnly) uint8 ShipHealthPct = 0;            // 0..100, at most 4 Hz (B8.1)
	UPROPERTY(BlueprintReadOnly) TObjectPtr<AAirshipPawn> Ship;     // null while dead / respawning
	UPROPERTY(BlueprintReadOnly) double ShipRespawnServerTime = 0.0; // 0 = no respawn pending
	UPROPERTY(BlueprintReadOnly) double EmptySinceServerTime = 0.0;  // 0 = has players
	UPROPERTY(BlueprintReadOnly) double LastUnderAttackServerTime = 0.0;   // server rate limit (not needed on clients)
	UPROPERTY(BlueprintReadOnly) bool bEliminated = false;
};

USTRUCT(BlueprintType) struct FMySwarmDifficultyPreset
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere) FName Name;
	UPROPERTY(EditAnywhere) float Count = 1.f;           UPROPERTY(EditAnywhere) float Health = 1.f;
	UPROPERTY(EditAnywhere) float Armor = 1.f;           UPROPERTY(EditAnywhere) float Damage = 1.f;
	UPROPERTY(EditAnywhere) float AttackSpeed = 1.f;     UPROPERTY(EditAnywhere) float MoveSpeed = 1.f;
	UPROPERTY(EditAnywhere) float SelfBuffChance = 1.f;  UPROPERTY(EditAnywhere) float MaxAlive = 1.f;
	UPROPERTY(EditAnywhere) int32 MaxAttackersPerPlayer = 0;      // 0 = the rules asset's
	UPROPERTY(EditAnywhere) float BurrowerSpawnIntervalScale = 1.f;
	UPROPERTY(EditAnywhere) int32 BurrowerMaxAlivePerPlayer = 0;  // 0 = UBurrowerSettings
	UPROPERTY(EditAnywhere) int32 BurrowerLevel = 1;
};

USTRUCT(BlueprintType) struct FMyLaneHint
{
	GENERATED_BODY()
	UPROPERTY() int16 LateralDm = 0;     // ship minus lane, decimetres, + = toward the start heading's right
	UPROPERTY() int16 VerticalDm = 0;
	UPROPERTY() int32 ProgressDm = 0;    // u
	UPROPERTY() int16 LaneYawDeg10 = 0;  // lane tangent yaw at the ship, 0.1 deg
	UPROPERTY() uint8 Clamp = 0;         // EMyLaneClamp
};
```

### 2.2 match: game state, player state, game mode

```cpp
// AMyGameState (MyGameState.h): additions
EMyMatchPhase GetMatchPhase() const;                 // BlueprintPure
const FMyMatchRules& GetMatchRules() const;
const FMyTeamState& GetTeamState(uint8 TeamId) const; // a default entry for an invalid id
EMyMatchResult GetMatchResult() const; uint8 GetWinningTeam() const; double GetPhaseEndServerTime() const;
EMyMatchEndReason GetEndReason() const; double GetMatchEndServerTime() const;   // time limit end, 0 = none
int32 GetExpectedPlayers() const; int32 GetRoundIndex() const;
UFUNCTION(NetMulticast, Reliable) void MulticastMatchEvent(EMyMatchEvent Event, uint8 TeamId, int32 Value);
FSimpleMulticastDelegate OnMatchChanged;              // every machine, after any OnRep and on the server after writes
FOnMatchEvent OnMatchEvent;                           // every machine, from the multicast
// (file scope in MyGameState.h: DECLARE_MULTICAST_DELEGATE_ThreeParams(FOnMatchEvent, EMyMatchEvent, uint8, int32);)
// server-only writers, used by AMyGameMode only
void SetMatchPhase(EMyMatchPhase, double PhaseEndServerTime); void SetMatchRules(const FMyMatchRules&);
FMyTeamState& EditTeam(uint8 TeamId); void SetResult(EMyMatchResult, uint8 WinningTeam); void MarkTeamsDirty();

// AMyPlayerState (MyPlayerState.h)
UFUNCTION(BlueprintPure) uint8 GetTeamId() const;
void SetTeamId(uint8 NewTeam);                         // server
FSimpleMulticastDelegate OnTeamChanged;

// AMyGameMode (MyGameMode.h): overrides InitGame, InitNewPlayer, StartPlay, ChoosePlayerStart_Implementation,
// RestartPlayer; extends PreLogin, Logout, PlayerCanRestart_Implementation (no pawn while waiting, B4.2),
// SetPlayerDefaults (net cull distance, B10), FindRespawnSpot (own side, B9.7). Public, server:
bool IsMatchOn() const;
void ApplyRules(const FMyMatchRules& NewRules);        // live: swarm, lives, FF, grapple, assist, time limit (team mode: next restart)
AAirshipPawn* SpawnTeamShip(uint8 TeamId, float U);
void RequestStartMatch();                              // host: pause menu / Aura.Match.Start: WaitingToStart -> Countdown
void StartMatchNow();                                  // console: skip the countdown too
void EndMatch(EMyMatchResult Result, uint8 WinningTeam, EMyMatchEndReason Reason); void RestartMatch();
void SetPlayerTeam(AMyPlayerState* Player, uint8 TeamId);   // console; ejects from the other team's ship first

// UMyMatchMemorySubsystem (Match/MyMatchMemorySubsystem.h, UGameInstanceSubsystem, host)
bool FindTeam(const FUniqueNetIdRepl& Id, uint8& OutTeam) const; void RememberTeams(const AGameStateBase* GameState);
int32 GetRoundIndex() const; void NextRound(); void Reset();   // Reset when the host leaves to the menu
```

### 2.3 match: `UMyTeamLibrary` (BlueprintFunctionLibrary, every machine unless noted)

```cpp
static bool IsMatchActive(const UObject* WorldContext);           // phase != None (game state)
static const FMyMatchRules& GetRules(const UObject* WorldContext); // the game state's, else UMyMatchSettings defaults
static uint8 GetTeamId(const AActor* Actor);
static bool AreTeammates(const AActor* A, const AActor* B);       // both valid (!= 255) and equal
static bool IsFriendlyFireBlocked(const AActor* Instigator, const AActor* Target);   // B6.1 (server use); BlueprintPure for GA_BeamBP
static bool CanUseShip(const AActor* User, const AAirshipPawn* Ship);              // B6.3, any machine (replicated team ids only)
static bool IsTeamShipTarget(const AActor* Target);                                // B6.5: a team ship or a team ship's turret, match on
static FLinearColor GetTeamColor(uint8 TeamId); static FText GetTeamName(uint8 TeamId);
```

`GetTeamId` resolves, in this order: AMyPlayerState -> its TeamId; AController -> its player state; AAirshipPawn -> its
TeamId; AAirshipTurret -> its ship's; AAirshipCannonball -> its `SourceTeamId` (stored at spawn, B6.2); APawn with a player state
-> that; an actor attached (up to 4 parents) to an AAirshipPawn -> the ship's (the seated pilot is unpossessed, so he has no
player state then, `AirshipPawn.cpp:1320`); an actor attached to a character -> the character's; an actor whose ASC's owner
is a player state -> that; else 255.

### 2.4 lanes: spawner getters, lane subsystem, lane component

```cpp
// AMyHexPathSpawner (MyHexPathSpawner.h), public, server values
float GetStartYaw() const { return StartYaw; }
double GetStartZ() const { return StartZ; }
float GetPathHalfWidth() const { return SegmentBoundsHalfWidth * GetLayoutScale(); }
float GetMaxYawDeviation() const { return MaxYawDeviation; }
float GetExtendDistanceWorld() const { return ExtendDistance * GetLayoutScale(); }

// UMyLaneSubsystem : UWorldSubsystem (Match/MyLaneSubsystem.h), server; Game and PIE worlds
static UMyLaneSubsystem* Get(const UObject* WorldContext);
bool HasLanes() const;
int8 GetSideForTeam(uint8 TeamId) const;                 // TeamLaneSide, swapped on odd rounds (B1.6); 0 = none
float ProjectU(const FVector& World) const;
float GetLateralFromPath(const FVector& World) const;     // v minus the path's v at that u (B9.7)
bool CheckHullClearance(float& OutMinGapCm, float& OutAtU) const;   // Aura.Lane.Check (B2.1)
bool GetLanePoint(int8 Side, float U, FVector& OutLocation, FVector& OutTangent) const;   // U clamped to the lane
float GetLaneStartU() const; float GetPathEndU() const; float GetCruiseEndU() const;
bool GetTeamFrontU(uint8 TeamId, float& OutU) const;      // B2.4
bool GetSpawnTransform(uint8 TeamId, float U, FTransform& Out) const;
FSimpleMulticastDelegate OnLanesChanged;
void DrawDebug(float Duration) const;

// UAirshipLaneComponent : UActorComponent (Airship/AirshipLaneComponent.h); replicated; no tick of its own
void UpdateLane(float DeltaSeconds);                      // server, AAirshipPawn::Tick before Flight->UpdateFlight
void NotifyPilotChanged(bool bHasPilot);                  // server, end of BoardPilot / UnboardPilot
void NotifyHullContact(const AActor* Other, const FHitResult& Hit);   // server, from OnHullHit
void NotifyTeamChanged();                                 // server, from AAirshipPawn::SetTeamId
UFUNCTION(BlueprintPure) EMyLaneState GetLaneState() const;
const FMyLaneHint& GetLaneHint() const;
bool IsAssistActive() const;                              // every machine: LaneState == Assist
double GetRecallServerTime() const;                       // every machine: when the recall starts, 0 = none (B2.11)
bool IsRecallReplacing() const;                           // server: the ship is being replaced by a recall (no life lost)
void DebugTeleportToLane(float U, float DeltaZ = 0.f);    // server, console
// Replicated: EMyLaneState LaneState; FMyLaneHint LaneHint; double RecallServerTime
```

The lane component reads `Flight->GetUnpilotedMode()`, `Flight->HasPilotDriveInput()`, `Flight->SweepHullAhead()`,
`GetShip()->HasIncomingReel()` and writes `Flight->SetLaneTarget()` / `SetDriftMaxDistanceOverride()`. It reads the team
from `GetShip()->GetTeamId()` and the match phase from the game state. For a recall replacement it calls
`AMyGameMode::SpawnTeamShip` through the game mode (match owner's API) after marking itself `IsRecallReplacing`.

`UMyHexBridgeSubsystem` (`MyHexBridgeSubsystem.cpp:4777-4836`): B9.1. `AMyHexPathSpawner::CheckPlayers` (`cpp:268-279`):
B9.2. Both call `UAirshipSubsystem::IsShipBorne`.

### 2.5 airship

```cpp
// AAirshipPawn (AirshipPawn.h)
UFUNCTION(BlueprintPure) uint8 GetTeamId() const { return TeamId; }
void SetTeamId(uint8 NewTeam);                 // server: OnRep path, BulletTargetTag refresh, Lane->NotifyTeamChanged
UAirshipLaneComponent* GetLane() const { return Lane; }   // CreateDefaultSubobject "Lane" in the constructor
UPROPERTY(ReplicatedUsing = OnRep_TeamId) uint8 TeamId = 255;
bool IsRiding(const ACharacter* Character) const;     // team-blind rider test (0.3, B6.3); IsRiderForDamage adds the team
void RefreshSentinelBulletTags();                      // server: hull + turrets (B6.4)
void SetSpawnProtected(float Seconds);                 // server: loose tag on the ship's and turrets' ASCs (B3.4)
bool IsSpawnProtected() const;                         // every machine, from ProtectionEndServerTime
void NotifyIncomingReel(const AActor* Reeler, bool bActive);   // server, from GA_GrappleSwing2 (B7.4)
bool HasIncomingReel() const;                          // server
void GetDeckSpawnTransforms(int32 Count, TArray<FTransform>& Out) const;   // server: start aboard (B4.2)
// CanBoard, CanMount, IsRiderForDamage: team rules (B6.3). OnRep_PilotCharacter, PossessedBy, UnPossessed,
// SpawnTurrets, SetTeamId, the pilot-destroyed branch (:606-612): RefreshSentinelBulletTags (B6.4).
// Tick: Lane->UpdateLane before Flight->UpdateFlight (server). BoardPilot / UnboardPilot: Lane->NotifyPilotChanged,
// first board / mount by its team ends the protection. OnHullHit: Lane->NotifyHullContact. GatherLocalInput: assist
// look and the drive-intent bit (B2.5 item 9, B2.9). GetFlightTelemetry: lane fields.

void ApplyShipDamage(float Damage, AActor* DamageInstigator = nullptr);   // existing; the instigator goes into the context (B6.5)

// AAirshipTurret
void ApplyTurretDamage(float Damage, AActor* DamageInstigator);   // server: fixed damage on the turret's ASC (B6.5)
// BeginPlay: adds BulletTargetTag only when GetShip() is null (B6.4). ApplyBulletDamage: ShipDamageTurretRound (B6.5).

// AAirshipCannonball
uint8 SourceTeamId = 255;                              // set by the ship at spawn (server), B6.2

// UAirshipFlightComponent: B2.5 items 1-12
void SetLaneTarget(const FAirshipUnpilotedTarget& Target, bool bAssist);
void SetDriftMaxDistanceOverride(float Distance);
bool HasPilotDriveInput() const;
bool SweepHullAhead(float HeadingYaw, float Distance, FHitResult* OutHit) const;

// AirshipTypes.h: Airship::Button_DriveIntent = 1 << 7 (B2.5 item 9)

// UAirshipSubsystem
static bool IsShipBorne(const APawn* Pawn);            // every machine (0.3)
static AAirshipPawn* FindShipCarrying(const APawn* Pawn);
AAirshipPawn* FindNearestAirship(const FVector& Location, bool bOnlyBoardable, const APawn* ForUser = nullptr) const;   // B6.3

// UAirshipPilotComponent
UENUM() enum class EAirshipUseRefusal : uint8 { None, NothingInRange, EnemyShip };   // AirshipTypes.h
UFUNCTION(Client, Unreliable) void ClientUseRefused(EAirshipUseRefusal Reason);
static TMulticastDelegate<void(EAirshipUseRefusal)> OnLocalUseRefused;   // the match HUD binds it

// AAirshipCannonball::ShouldIgnore, AAirshipTurret::ApplyBulletDamage / ball tests: B6.2 (UMyTeamLibrary)
// AirshipTypes.h: EAirshipUnpilotedMode::Lane, FAirshipFlightTelemetry lane fields, EAirshipUseRefusal
```

### 2.6 combat

```cpp
// MechSentinelWaveSpawner.h
USTRUCT(BlueprintType) struct FMechSentinelDifficultyScale
{ GENERATED_BODY() /* float Count, Health, Armor, Damage, AttackSpeed, MoveSpeed, SelfBuffChance, MaxAlive = 1 */ };
UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly) void SetDifficultyScale(const FMechSentinelDifficultyScale& Scale);
const FMechSentinelDifficultyScale& GetDifficultyScale() const;
// BurrowerSpawnSubsystem.h
void SetDifficultyOverride(float SpawnIntervalScale, int32 MaxAlivePerPlayer, int32 CharacterLevel);
void SetSpawningPaused(bool bPaused);
// BurrowerCharacter.cpp: IsLivingTarget false for ship-borne pawns (B9.4)
// GA_GunShoot.cpp, MySplashDamageLibrary.cpp, MyProjectile.cpp: B6.2; GA_GunShoot.cpp also B6.5
// MyAttributeSet.cpp: IncomingDamage dropped while the target ASC has Airship.State.SpawnProtected (B3.4)
```

The game mode builds the scale from the preset (Count times the player-count factor, B5.4) and calls these on every
`AMechSentinelWaveSpawner` in the world and on the Burrower subsystem, plus `UMechSentinelSwarmSubsystem::SetRulesOverride`
with its transient rules copy, first in StartPlay before Super. `SetDifficultyScale` must be safe before the spawner's
BeginPlay (B5.4).

### 2.7 grapple

B7, inside `GA_GrappleSwing2.h/.cpp` only. Reads `UMyTeamLibrary::GetRules` / `CanUseShip` and `AAirshipPawn::GetHull()`;
calls `AAirshipPawn::NotifyIncomingReel` on the server. New EditDefaultsOnly properties on the ability:
MaxShipHookDistance 12000, ShipReelSpeed 3000, ShipReelArriveDistance 250, ShipReelMaxTime 5, ShipReelLiftFraction 0.25,
ShipReelLiftMax 800, ShipHookMaxDrift 600, ShipHookLatencyAllowance 0.3, ShipHookMaxShipSpeed 3000,
ShipReelDeckBoxMargin 200, bShipHookOwnTeamOnly true.

### 2.8 menu

`UMainMenu3`: `RuleSets` default (B5.2), the Rules box limiting Max Players, `ShipLivesComboBox` (BindWidgetOptional) +
`ShipLivesChoices`, `BuildMatchOptions()`, the two travel calls, Play Solo reading the widgets. `UPauseMenu3`: Start match
and Restart match buttons (host only), calling `AMyGameMode::RequestStartMatch` / `RestartMatch`.
`UMultiplayerSessionsSubsystem::StartSession`: return early when the session is already InProgress. The option names are
the contract with AMyGameMode: `Teams` (`auto`, `1v1`, `2v2`, `practice`, case-insensitive; the RuleSets strings map to
them), `ShipLives`, `Swarm`, `TimeLimit`, `FF`, `GrappleShips`, `LaneAssist`, `Players`, `Match`.

---

## 3. Editor steps

Rules: scripts run through the inbox in the lead's editor stage, after PR A's stage is finished and the editor lock is
free; never during PIE (memory: asset scripts during PIE freeze the game thread); `free -g` first and the editor restarted
before PIE runs (memory pc-memory-limits). No script saves `StartupMap` unless Talal asks; tests place TEMP actors in the
editor level before PIE and remove them after, never saving (the as_59 method).

| Script | Does | Saves |
|---|---|---|
| `as_70_match_plan.py` | Read-only report for the open map: path spawner values (S, H, MaxYawDeviation, fog count), the computed lanes (both sides, 50 samples), PlayerStarts and their tags, placed ships, the floor's bounds, the lane distances in Appendix C; prints what as_71 would change. Also dumps GA_BeamBP's graph nodes around `LaunchCharacter` (its target pin's source) for the knockback check (B6.2). Writes `Saved/Match/as_70_plan.json`. | nothing |
| `as_71_match_map.py` | Map edits for the match (dry run by default): 4 PlayerStarts tagged `Team0` at (-1500, 1500, 205), (1500, 1500, 205) and `Team1` at (-1500, -1500, 205), (1500, -1500, 205) on the start floor (StartupMap). They only spread the players over the floor for practice and `bStartAboard` off; they don't fix the floor's asymmetry (both pairs are on the floor, v +85 and +115 m; flag 5). Optional `PathEndFogCount` 5 on the spawner instance; optional `ShipTeam0` tag on a placed ship. `AS71_APPLY=True` applies in the editor level; `AS71_SAVE=True` saves, and refuses when `unreal.Paths.project_dir()` is Talal's `AuraRedo3` unless `AS71_USER_OK=True` (his explicit OK). | only with both flags |
| `as_72_menu_lives.py` | WBP_MainMenu3 (`/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_MainMenu3`): a `Row_ShipLives` WBP_OptionRow (label SHIP LIVES, a ComboBoxString named `ShipLivesComboBox` in its Control slot) after `Row_HostRules`, with the style of `Ctl_HostRules`; compile, save. Uses the UMGToolSet path from memory main-menu3 (`unreal.ToolsetRegistry.execute_tool('UMGToolSet.UMGToolSet', ...)`). Talal's tree has no local change to this asset (git status). | WBP_MainMenu3 |
| `as_73_verify_b.py` | After the build: the new classes load; BP_AirshipPawn's CDO has the `Lane` component; UMyMatchSettings defaults equal Appendix A; BP_MyGameMode is an AMyGameMode child with GameStateClass AMyGameState (`MyGameMode.cpp:24`); WBP_MainMenu3 has ShipLivesComboBox (warn only); BP_MyHUD's MatchWidgetClass resolves. Report `Saved/Match/as_73_verify.txt`. | nothing |
| `as_74_pie_match.py` (+ `as_74s_status.py`, `as_74x_stop.py`) | Standalone harness, section 4.1. Map: the clone's StartupMap (`AS74_MAP`), or L_AirshipTest with a TEMP `TEMP_AS74_LaneOrigin` target point tagged `MatchLaneOrigin` at (0, 0, 1400), yaw 0 and `Aura.Match.Set FallbackLaneHalfWidth 5000` (lanes at y +-75 m, z 1600: the cannon walls at y -95 m stay 6.7 m clear of the hull, the start platform's edge at 50 m clear by 13.7 m, as_22 layout). Sets `Aura.Match.Enable 1`, fixed 30 fps, Burrower off unless a phase needs it; restores all at the end. For T2.12 it sets the editor-level spawner's MaxYawDeviation to 60 before PIE and back after (never saved, the TEMP method). | nothing |
| `as_75_pie_match_mp.py` (+ `as_75s`, `as_75x`) | Listen-server harness, section 4.2, 2 / 3 / 4 players (`AS75_PLAYERS`): writes PlayNetMode / PlayNumberOfClients into `Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini` with the editor closed (memory: ToolsetLibrary doesn't persist them), forces Standalone back at the end. Sets `Aura.Match.Set DefaultExpectedPlayers <n>` before PIE so the match starts once all clients are in (B4.2). | ini only |
| `as_76_regress.py` | PR A regression with the match off and on: as_59 (standalone), as_43 / as_45 phases with free ships; then as_59 with `Aura.Match.Enable 1` on L_AirshipTest to show team ships don't break PR A's checks apart from the listed expected differences (team ship lanes, tag rule). | nothing |

BP defaults: none needed. The lane component and the match HUD widget come from C++ defaults; BP_AirshipPawn picks up the
new default subobject on load. `UMyMatchSettings` has C++ defaults (no ini). Config: nothing.

Map changes needed in StartupMap (Talal's call, as_71): team PlayerStarts (optional: the spawn fix works without them),
`PathEndFogCount` 5 (Q12), a `ShipTeam0` tag or removal of his placed ship (Q9). In the clone the PIE harness gets the
same through TEMP actors and runtime settings, so nothing in the clone's StartupMap has to be saved either (it would
clash with his local StartupMap on merge, the PA_Airship lesson of PR A).

---

## 4. PIE test plan

Results to `Saved/Match/` (`b_result.json` with measured values, `b_report.txt`, captures in `Saved/Match/captures/`),
fixed 30 fps game time, Point & Fly unless noted, the user's own Play never stopped (log check). Each row: ID, setup,
pass condition.

### 4.1 Standalone (as_74)

Map StartupMap (clone) unless noted; 1 player = practice.

| ID | Setup | Pass |
|---|---|---|
| T1.1 | load, wait 6 s | standalone = practice: phase Countdown from the load until 5.0 +-0.2 s, then InProgress; Teams[0] active, Teams[1] inactive; player TeamId 0, spawned on the floor |
| T1.2 | after the start | one team ship, TeamId 0, at (5442, 12500, 200) +-100 cm, yaw 0 +-2 deg; LaneState Waiting (player behind) or Cruising; spawn-protected (ProtectionEndServerTime set) |
| T2.1 | teleport the player onto a platform at u 200 m | ship speeds up (proportional pace) to at most 28 +-1 m/s, slows toward 6 m/s near the front, settles 40 +-3 m ahead of the player (TeamPace) after it stops moving; overshoot past the cap <= 1 m; lateral error <= 1.5 m, vertical <= 1.0 m, heading <= 3 deg while moving; target speed ramps at <= 2.6 m/s^2 |
| T2.1b | the harness moves the player along a platform row at 20 m/s for 60 s (teleport steps every frame, on foot) | after the first 15 s, the 3D distance from the player to the hull's nearest point stays < 100 m |
| T2.2 | `Aura.Match.Set LaneMaxLead 0`, player stays | ship settles at CruiseEndU +-3 m (100 m behind the path end), overshoot <= 1 m, speed <= 0.3 m/s, Clamp PathEnd; path end u unchanged for 20 s |
| T2.3 | `Aura.Lane.Debug 1` | lane polylines drawn at y +12500 / -32500 (StartupMap) within 50 cm; capture |
| T2.4 | Board (`Aura.Airship.Board 0`) while Cruising | LaneState Assist at once; speed stays 6 +-0.5 m/s for 10 s with no input; the pilot's broadside still fires in Assist (`RequestFire`: a ball spawns within 0.2 s) |
| T2.5 | `Aura.Airship.Input 1 0` (throttle) for 2 s | PilotedInLane within 1 frame; InputClear: Assist again after 1.0 +-0.2 s |
| T2.5b | Point & Fly, Assist; the harness presses Q (IA_AirshipStrafe) for 1 s | PilotedInLane within 2 frames (drive-intent bit, B2.5 item 9); the ship turns on the server too |
| T2.6 | strafe out (`Aura.Airship.Input 0 0 0 1`) 8 s | OutOfLane once lateral > 40 m; exit (`Aura.Airship.Exit 0`) at > 8 m/s: Parked, UnpilotedMode Drift; drift ends by 300 m from the exit point, then Hold (not Hold at speed), unless the recall starts first (20 s) |
| T2.7 | board, fly back into the zone, stop (< 5 m/s), exit | Cruising within 0.5 s of the exit; 6 m/s reached within 3 s |
| T2.8 | a TEMP cube 40 x 40 x 20 m on the lane 150 m ahead (placed in the editor level before PIE) | ship waits >= 5 m short of it (hull bounds), Clamp Blocked, no hull damage; at 3 s the harness turns the cube's PIE copy's collision off (`set_actor_enable_collision(False)`): Cruising again within 1 s |
| T2.9 | walk the platform edge on the team's side 1 km (teleports every 50 m), log the 2D gap to the lane hull's inner side | report min / median / max gap (expected 14-84 m, flag 2); no gap > 115 m (hook range) |
| T2.10 | board, fly 200 m out of the lane, exit, player teleported 300 m away on a platform (no teammate within 120 m) | Parked; Returning at 20 +-0.5 s after the exit (event ShipReturning); Cruising within 20 + 30 s; no hull damage |
| T2.11 | the T2.8 cube, collision left on | Bypass (Clamp) after 5 +-0.5 s, the ship passes the cube >= 5 m clear, BypassOffset back to 0 and lateral error <= 1.5 m within 30 s of passing |
| T2.12 | the editor-level spawner's MaxYawDeviation set to 60 before PIE (TEMP, not saved), NoiseSeed as in the map; 1 km of path | `Aura.Lane.Check`: smallest hull-to-field gap >= 13 m on both sides (B2.1) |
| T3.1 | `Aura.Match.KillShip 0` | ShipsLost 1, event ShipDestroyed; new ship at +10.0 +-0.3 s, TeamId 0, on the lane at the team front u +-5 m, Cruising / Waiting, protected |
| T3.2 | pilot aboard the respawned ship, `Aura.Match.KillShip 0` (no crew share, so he is ejected alive) | pilot ejected (PR A), falls, dies by fall death within 8 s of the ejection (log `LogMatch fall death`; 5.5-7 s expected, B3.3), respawns 5 s later on a platform on the team's side |
| T3.3 | `Aura.Match.Set bSoloPracticeUnlimitedShips 0`, kill three ships | LivesLeft 0, phase Ended, Result PracticeOver, end panel shown; restart after 20 +-0.5 s; the reloaded map has the same rules (`Aura.Match.Status`) |
| T3.4 | right after a respawn, `Aura.Match.DamageShip 0 100`, a turret round (`Aura.Airship.TurretFire`, a TEMP free ship's), a cannonball splash and the player's gun on the hull | hull health unchanged for each; board it, repeat `DamageShip 0 100`: -100; after 15 s without boarding also -100 |
| T3.5 | solo practice (setting on), kill 4 ships | still InProgress, ShipsLost 4, HUD "SHIPS LOST 4", a new ship each time |
| T3.6 | pilot aboard, `Aura.Lane.Teleport 0 <u> -150` (ship 150 m below path height) for 10 s | the pilot is alive (ship-borne); exit there: he dies by fall death within 8 s |
| T4.1 | before PIE `Aura.Match.Set DefaultRules.SwarmDifficulty 0`; load | **wave 1's** spawner DifficultyScale = Easy preset; its planned total = round(base x 0.6) +-1; its sentinels have Easy health; GetRules()->MaxAttackersPerPlayer 6; Burrower SpawnInterval 45 s (log); SelfBuffChance of a wave = rules' x 0.5 (not 0.25) |
| T4.2 | `Aura.Match.Swarm 4` | Health / Damage multipliers of `GetWaveDefinition(next)` = base x 2.0 +-1 %; MaxAlive 800 (500 x 1.6) |
| T5.1 | ship-borne leader: board, fly 600 m ahead along the path for 30 s | no platform with SplineDistance greater than the player's last platform minus 200 m is destroyed (count 0); the lead pawn is null while aboard (`Aura.Match.Dump`); path end u unchanged while only the ship is near the end |
| T5.2 | Burrower on (`UBurrowerSettings.bEnabled`), board | no Burrower spawns for the player while aboard; the existing one stops targeting him (target null) |
| T6.1 | ship hook from a platform edge 60 m from the cruising ship (L_AirshipTest variant: from the start platform to the lane ship) | the player lands on the deck (movement base = the hull) within 4 s in >= 4 of 5 tries; no server rejection on a cruising ship |
| T6.2 | ship hook on a piloted ship at 25 m/s turning | the server ends the reel when the drift exceeds 6 m + 0.3 s x speed (log) and the player falls, no crash, no client stuck in root motion |
| T6.3 | ship hook on a lane ship (a) during a catch-up ramp, (b) while it eases into the TeamPace cap | lands in >= 4 of 5 each; no server rejection; Clamp Reel logged while the reel runs |
| T6.4 | ship hook with the crosshair on a turret of the own ship | accepted (the rope trace ignores the ship's turrets); lands on the deck |
| T7.1 | HUD captures | match bar (lives, hull bars, clock, objective line), ship marker (on and off screen, shield, "AIM + GRAPPLE", hull bar), pilot LANE row in Assist / PilotedInLane slow and fast / OutOfLane, recall timer, end panel with its reason |
| T8.1 | match off (`Aura.Match.Enable 0`), L_AirshipTest | as_59's checks give the same result as before PR B (as_76) |
| T8.2 | `Aura.Airship.Spawn` in a match | the spawned ship is free (TeamId 255), anyone can board it, no lane |

### 4.2 Listen server (as_75), StartupMap, 2, 3 and 4 players

| ID | Players | Pass |
|---|---|---|
| M1.0 | 2, `DefaultExpectedPlayers 3` | no pawns, phase WaitingToStart, match bar "WAITING FOR PLAYERS 2/3" on both; `Aura.Match.Start`: Countdown 5 s, then InProgress 1v1 |
| M1.1 | 2 (`DefaultExpectedPlayers 2`) | Countdown starts when the client is in; at its end every player has a pawn on his own ship's deck (start aboard) within 1 s; teams 0 / 1; two ships (y +12500 and -32500); client's `GetTeamState` equals the server's within 0.5 s. Practice variant (`Teams=practice`): pawns on the floor within 3 s (spawn fix), >= 2 m apart |
| M1.2 | 3 | teams sized {2, 1}, the solo team's LivesLeft 4 (handicap); 4: {2, 2}; join order host 0, c1 1, c2 0, c3 1 |
| M1.3 | 2, TeamMode OneVsOne, a 3rd client tries to join | refused with "That match is full (1v1)." (PreLogin) |
| M1.4 | 2, the client leaves during the countdown | back to WaitingToStart, team 1 inactive, no team 1 ship |
| M2.1 | 2 | client presses F next to team 0's ship: refused, toast on the client within 0.5 s; `Aura.Airship.Mount 1 0` with the client next to team 0's ship mans station 0 of the client's own ship (the nearest one it may use), never team 0's; F next to its own ship boards it |
| M2.3 | 2 | the client stands nearer team 0's ship: `Aura.Airship.Board 1` boards team 1's ship (console filter, B6.3); the client's "Press F" prompt never names team 0's ship |
| M2.2 | 2 | client stands on team 0's forward deck: `Aura.Airship.TurretFire 1 X Y Z` at his position (every ship's unmanned turrets fire; team 1's are out of range) damages him (rider rule); the host standing on his own deck at the same spot: not damaged |
| M3.1 | 2, enemies | host gun hits the client: -1 per hit (GE value); host gun on team 1's hull: -5 per hit (B6.5), on its turret -5; `Aura.Match.Team 1 0` (teammates): 0 damage from gun, beam hit, beam splash, a cannonball splash 3 m away (also with the firing ship destroyed in flight: SourceTeamId), turret rounds, a fireball; the beam's knockback moves the teammate < 0.5 m; crew share still 25 % (`Aura.Match.DamageShip 0 100` -> pilot -25) |
| M3.2 | 2 | `Aura.Match.Rules FF=1`: teammates take damage again |
| M4.1 | 2 | undriven team 1 ship with a sentinel test bullet (`Aura.MechSentinel.TestBullet`) at its hull: hull health unchanged; at its forward turret: turret health unchanged; the same with a pilot aboard: hull -3, turret damaged; pilot aboard and the harness destroys his character (server world): tags stay on (controller still flying) |
| M5.1 | 2 | kill team 1's ship 3 times: Ended, Result TeamWon, WinningTeam 0 on both machines within 1 s; client shows DEFEAT, host VICTORY |
| M5.2 | 2 | client pilots team 1's ship, then the client window closes (as_45x method): the ship stays (not destroyed), LaneState Parked or Cruising, LivesLeft unchanged; after 30 s team 1 forfeits: Ended, WinningTeam 0 |
| M6.1 | 2 | client's lane state and hint follow the server's (state equal, lateral within 0.5 m) |
| M6.2 | 4 | all four HUDs show the right team and lives; frame time with 2 cruising ships: lane update <= 0.05 ms per ship on the server (stat or Insights scope `LaneUpdate`) |
| M5.3 | 2 | `Aura.Match.Rules TimeLimit=1` after the start, then `Aura.Match.DamageShip 1 500`: Ended 60 +-1 s after the rule change, EndReason TimeLimit, WinningTeam 0 (equal lives, higher hull fraction); event TimeWarning sent once (at once, as less than a minute is left) |
| M7.1 | 2 | restart after Ended: both reconnect, each player's TeamId as before (memory subsystem; if PIE gives no valid net ids, log it and accept join order), the lane sides swapped (team 0 at y -32500), RoundIndex 1, rules kept (manual check if PIE ServerTravel fails: R6) |
| M7.2 | 2 | client ship hook onto its own ship (cruising): lands on the deck in >= 4 of 5, no correction storm (CMC corrections logged <= 3 per reel) |
| M8.1 | 2 | the client on its own deck, the host standing on team 0's deck 300-450 m away: the host's character exists in the client's world, and the client's gun hits on him apply (relevancy 600 m, B10) |
| M8.2 | 2 | host pilots team 0's ship in its lane; sentinels attack it; the client at the path centre (225 m away) has replicated sentinels within 50 m of team 0's ship (count > 0); report the count against the server's (R13) |
| M9.1 | 2 | teammates (`Aura.Match.Team 1 0`): the client mans a station of team 0's ship and the host stands on its deck; `Aura.Lane.Teleport 0 <u> -150` for 10 s: both alive (fall rule skips the ship-borne); then the host takes the helm and the client walks onto the deck: both alive again |

Manual (not automatable in PIE): late join turning practice into 1v1 (a second PIE client can't be added mid-session:
fresh countdown, both teams reset), host menu options end to end (MM_MainMenu -> Host -> Start, then
`Aura.Match.Status`; Rules 1v1 sets Max Players to 2), the pause menu's Start match / Restart match buttons on the host
and their absence on a client.

---

## 5. Risks, open questions, and posted decisions that change

### 5.1 Risks

1. **R1 Reachability.** Lanes 225 m out, real platforms often 130 m out (flag 2, inferred): without the ship hook the
   ships are hard to reach mid-run. If B7 slips, a fallback is a lane that hugs the real outermost platforms (more
   lateral wiggle, needs platform footprints from PCG).
2. **R2 Moving anchors in prediction.** The reel is deterministic only while the ship flies straight at constant speed
   (the lane, frozen during the reel, B7.4). On a piloted ship it ends early by design when the drift passes the
   latency allowance.
3. **R3 PR A not yet play-tested.** PR B builds on the unpiloted module, stations, turrets and crew share, which haven't
   run in PIE yet; their fixes may move hooks.
4. **R4 Assist and Point & Fly's camera** (B2.9) touch the pilot's input code; a mistake there shows as the ship turning to
   the camera in Assist. Tested by T2.4 / T2.5.
5. **R5 The envelope trusts SegmentBoundsHalfWidth.** If the PCG graph places platforms further out, lanes cut through
   them; the look-ahead stops the ship but the lane is blocked. T2.9 measures it.
6. **R6 ServerTravel restart in listen PIE** may behave differently from a packaged game; M7.1 falls back to a manual
   standalone check. A packaged two-machine EOS check is needed too: the restart's second StartSession (skipped when the
   session is InProgress, B4.6), the team memory with real EOS net ids, and the pause-menu Restart button in Shipping
   (no console there).
7. **R7 Asymmetric start** (flag 5): solved for versus by starting aboard; practice still starts on the floor (no
   opponent, so it doesn't matter).
8. **R8 Fall death** changes how long a fall takes for every player on foot in a match (B9.6).
9. **R9 Culling pause** while every leader is ship-borne keeps more platforms alive (performance), until a runner lands
   further (B9.1). Starting aboard makes this the state of every versus match until the first runner lands.
10. **R10 Lane separation 450 m > cannon / turret range** (flag 3); the time limit ends a match nobody fights (B4.4).
11. **R11 Talal's local values**: GE_GunShootDamage 1000 per hit, empty PA_Airship, BurrowerSettings MaxAlivePerPlayer
    10. Ship damage no longer depends on the GE value (B6.5), but player-vs-player gun and turret damage to characters
    still does: one-shot kills with his value (Q18).
12. **R12 Listen PIE frame rate** (~6 fps with a client window focused, memory) makes timing checks noisy: fixed 30 fps
    game time in the harness.
13. **R13 Sentinel replication range.** Mass replicates sentinels by its own LOD distances (engine default off beyond
    50 m; the project's DA_MechSentinelConfig values weren't decoded). Clients far from a driven lane ship may not see
    the sentinels attacking it (M8.2). Raising the distance costs bandwidth with hundreds of sentinels.
14. **R14 Recall crossing the field** (B2.11): the climb to path height + 80 m is a guess at the tallest thing in the
    field; the look-ahead and the replace fallback catch a wrong guess.
15. **R15 Waiting with no pawn** (B4.2): a host who waits for joins sees a still camera for up to a minute. The
    alternative (pawns on the floor with the path growth and the collapse frozen, then everyone moved back at the
    start) touches the ranking, the spawner and the respawn code, so it was not chosen.

### 5.2 Open questions for Talal (defaults in brackets; none blocks the implementation)

1. **Q1** Ship hook: grapple onto ships at all, and only your own team's [yes, own team and free ships]? Should players
   also be able to hook onto the enemy ship to board its deck and fight there?
2. **Q2** While someone drives the ship but stays in the lane, should it keep cruising by itself until he uses the drive
   keys (lane assist) [yes], or is the driver always fully in control?
3. **Q3** The start floor is on one side, so one team's ship is 75 m from it and the other's 274 m, and the host was
   always on the near side. In a versus match, should each team start on its own ship's deck (fair every round; the
   pilot then flies his runners to the platforms) [yes, and the sides swap every round], or everyone on the floor as
   today (sides still swap every round, so it evens out over two rounds)? A longer-term fix is a start pad on each
   side or the floor on the path's middle (a map change).
4. **Q4** Players die after falling 80 m below the platforms in a match [yes]; nobody aboard a ship dies of it. Today
   nothing stops a fall: is that on purpose?
5. **Q5** Lane speed 6 m/s; catching up proportionally up to 28 m/s so the ship stays within hook range of its
   runners (15 m ahead of the team front as its aim); never more than 40 m ahead of its team; 100 m behind the end of
   the path [yes]? (Revision 1 had 15 m/s only when 80 m behind and 300 m behind the end: too slow for grapple
   runners.)
6. **Q6** Ship lives = ships a team may lose: 3 lives = 3 ships in all [yes]? Hull 2000 and the B3.5 kill times are the
   numbers to tune with it.
7. **Q7** More than 4 players (no session cap): keep balancing teams (3v2, 3v3) [yes] or refuse?
8. **Q8** A team with nobody left forfeits after 30 s [yes]?
9. **Q9** Your StartupMap ship (`BP_AirshipPawn_C_6`): in a 2-team match untagged placed ships are removed at the start
   [yes]; tag it `ShipTeam0` instead?
10. **Q10** Sentinel bullets don't damage a ship nobody drives, even when they were aimed at a gunner on it [right]?
11. **Q11** Ships in their lanes are 450 m apart, out of cannon (244 m) and turret (250 m) range: to fight, a pilot leaves
    the lane [fine]? Or should lanes be closer?
12. **Q12** Five path-end fog banks so the lanes are covered too (a StartupMap change) [yes, by as_71 with your OK]?
13. **Q13** Difficulty presets (B5.4), with more sentinels per wave for more players (x1.4 for two, x2.2 for four):
    right? And your local Burrower values: make MaxAlivePerPlayer 10 the Nightmare value?
14. **Q14** Restart: automatic 20 s after the result [yes], or only when the host says so (the pause menu's Restart
    match button works either way)?
15. **Q15** A dead player respawns ahead of the race leader as today, on his own team's side of the path [yes], or on
    his team's ship when it is alive and in its lane?
16. **Q16** (changes a posted decision, 5.3) A team ship left outside its lane with nobody flying it: after 20 s it flies
    itself back to its lane and cruises again [yes], or it stays where it was left for ever (then it can be stranded
    behind the race, and a match can stall)?
17. **Q17** (adds to a posted decision) A versus match has a 15-minute limit; at the end the team with more ship lives
    wins, then the one with more hull left, then the one further along the race [yes]? Or no limit?
18. **Q18** Damage to ships: fixed 5 per gun hit and 4 per turret round in a match, whatever GE_GunShootDamage says
    [yes]. Separately, before the first versus play test: which gun value should player-vs-player use? Your local 1000
    per hit kills a player in one shot, and a turret round does 4 x that to characters.
19. **Q19** (adds to a posted decision) 3 players = 2v1, and the solo player's team gets one extra ship life [yes]? Or
    should 3 players default to co-op practice, everyone on one ship?
20. **Q20** Solo practice: unlimited ships, so learning to fly never ends in a reload [yes]? (Co-op practice keeps the
    lives.)
21. **Q21** A versus match waits until the expected players are in (the host's Max Players); the host can start early
    from the pause menu [yes]?
22. **Q22** A respawned ship can't be damaged until its team boards it, or for 15 s [yes]?

Q23-Q25 came out of the implementation and its reviews: section 7.5. Q7 and Q19 each have a setting behind their
answer now (`AutoMaxPlayersPerTeam`, `AutoCoopPlayers`, 7.2).

### 5.3 Decisions posted to Talal that can't work as posted (each is a question above, with the recommendation)

| Posted decision | Why it can't work alone | Recommendation | Q |
|---|---|---|---|
| "Left outside the lane, it drifts slowly ahead then holds (PR A behaviour)" | the ship is stranded for ever when its pilot exits, is ejected or is put on foot by the crew share; nothing replaces it, the race leaves it behind out of hook range, and with both ships stranded no ship can lose a life (flag 9) | keep the drift and hold for 20 s, then the recall flies it home (B2.11); setting `bShipRecall` | Q16 |
| "A team with no ship lives left loses" as the only end | lanes are out of each other's range, an undriven ship is safe from the swarm, players respawn freely: if nobody attacks, nobody ever loses (flag 10) | a 15-minute limit with a tie-break (B4.4); `TimeLimit=0` gives the posted rule back | Q17 |
| "3 = 2v1" | works, but the two-player team has about double the firepower with the same lives and hull | +1 ship life for the smaller team (B1.2); or 3 players as co-op practice | Q19 |
| "1 player = practice (one ship, no opponent)" with "3 lives" | a learner's practice ends in a reload after three crashes | unlimited ships in solo practice (B3.2) | Q20 |
| "cruises at about 6 m/s" | kept as the cruise and the floor; the catch-up had to become faster and proportional to keep the ship in reach (flag 12) | B2.4 | Q5 |

Everything else the lead posted stands as posted: 2 teams and the team sizes, the lanes 25 m beyond the field at
y = +12500 / -32500 in StartupMap, "once driven out of the lane it is fully the driver's", "parked back in the lane and
left, it cruises again", 3 lives with a respawn in the lane, the settings (menu Difficulty box, lives and team mode,
console), no friendly fire, no use of the other team's ship, and the grapple on ships (default yes).

---

## Appendix A. Settings (`UMyMatchSettings`, Config=Game, "Project Settings > Game > Match")

| Category | Name | Default | Unit / meaning |
|---|---|---|---|
| Match | MatchMaps | { StartupMap } | short names; empty = every map with AMyGameMode |
| Match | DefaultRules | Auto, 3, 1, 15, false, true, true | B5.1 |
| Match | MatchStartDelay | 5 | s (the countdown) |
| Match | DefaultExpectedPlayers | 2 | Auto without a `Players` URL option on a listen server (B4.2); 1 = practice at once, a joiner turns it versus (Q25) |
| Match | AutoMaxPlayersPerTeam | 0 | Auto: cap per team, 0 = none (Q7; added by the fixes, 7.2) |
| Match | AutoCoopPlayers | 0 | Auto with exactly this many expected players plays co-op practice; 0 = never (Q19; 7.2) |
| Match | bStartAboard | true | versus: spawn each team on its own deck at the start (B4.2) |
| Match | bRespawnAboard | false | B9.7, Q15 |
| Match | bAlternateSides | true | B1.6 |
| Match | bSmallTeamHandicap | true | B1.2 |
| Match | bTimeLimitCountsHandicap | false | the time limit's lives step counts the handicap's lives (B4.4, Q23; 7.2) |
| Match | bShipHookOutsideMatch | false | ship hook with the match off (B7, Q24; 7.2) |
| Match | bSoloPracticeUnlimitedShips | true | B3.2 |
| Match | ShipRespawnDelay | 10 | s |
| Match | ShipSpawnProtection | 15 | s; 0 = off (B3.4) |
| Match | ShipSpawnMinEnemyDistance | 25000 | cm (B3.1) |
| Match | TeamEmptyForfeitSeconds | 30 | s; 0 = never |
| Match | EndScreenSeconds | 20 | s; 0 = no automatic restart |
| Match | bDestroyUntaggedPlacedShipsInVersus | true | |
| Match | FallDeathDepth / FallDeathMinFallTime | 8000 / 1.0 | cm below lane / path height, 0 = off; s falling with no base |
| Match | bSentinelBulletsHitUndrivenShips | false | B6.4 |
| Match | ShipDamageGunHit / ShipDamageTurretRound | 5 / 4 | per hit on a team ship or its turret; 0 = the GE value (B6.5) |
| Match | ShipUnderAttackInterval | 5 | s between ShipUnderAttack events per team |
| Match | MatchNetCullDistance | 60000 | cm, player characters while the match is on (B10) |
| Match | TeamLaneSide | (+1, -1) | per team, round 0 |
| Match | TeamColors | (0.25, 0.66, 0.96), (0.96, 0.54, 0.25) | linear |
| Match | TeamNames | BLUE, ORANGE | |
| Match | ShipLivesChoices (menu) | 1, 2, 3, 5, 9 | (on UMainMenu3) |
| Difficulty | SwarmDifficulties | B5.4 table | 5 entries |
| Difficulty | SwarmPlayerCountBase / PerPlayer / Max | 0.6 / 0.4 / 2.2 | Count factor = min(Base + PerPlayer x N, Max) |
| Lanes | LaneClearance | 2500 | cm, not scaled |
| Lanes | LaneHeight | 200 | cm, not scaled |
| Lanes | LaneSampleStep | 500 | cm x S |
| Lanes | LaneSmoothHalfWindow | 2500 | cm x S |
| Lanes | LaneBackReach | 6000 | cm x S |
| Lanes | LaneEndMargin | 5000 | cm x S (revision 1: 15000) |
| Lanes | LaneSpawnU | 0 | cm (u of the match-start spawn) |
| Lanes | MaxYawForEnvelope | 80 | deg |
| Lanes | FallbackLaneHalfWidth / FallbackLaneLength | 10000 / 150000 | cm (MatchLaneOrigin) |
| Cruise | LaneSpeed | 600 | cm/s (cruise, and the floor while the team front is known) |
| Cruise | LaneCatchUpSpeed | 2800 | cm/s, the lane's top speed (revision 1: 1500 with LaneCatchUpBehind 8000, removed) |
| Cruise | LanePaceGain / LanePaceOffset | 0.3 / 1500 | 1/s, cm ahead of the team front |
| Cruise | LaneMaxLead | 4000 | cm; 0 = no pace limit |
| Cruise | LaneAccel | 250 | cm/s^2 (target speed ramp; revision 1: 100) |
| Cruise | LaneMaxTargetLead / LaneJoinStep | 1500 / 1000 | cm |
| Cruise | LaneKp / LaneKd / LaneAccelMax | 0.4 / 0.8 / 600 | 1/s^2, 1/s, cm/s^2 (revision 1: 200) |
| Cruise | LaneClimbRate | 200 | cm/s |
| Zone | LaneZoneEnterLateral / Vertical | 2000 / 1500 | cm |
| Zone | LaneZoneExitLateral / Vertical | 4000 / 2500 | cm |
| Zone | LaneParkSpeed / LaneParkSettleTime | 800 / 0.5 | cm/s, s |
| Assist | LaneAssistDelay / LaneAssistMaxSpeed | 1.0 / 1500 | s, cm/s |
| Safety | LaneLookAheadMin / LaneLookAheadTime / LaneSweepInterval / LaneBlockedClearChecks | 1500 / 3 / 0.25 / 3 | cm, s, s, count |
| Safety | LaneOutDriftMaxDistance | 30000 | cm; team ships outside the lane |
| Safety | LaneBlockedTimeout / LaneBypassOffset | 5 / 3500 | s, cm outward (B2.7) |
| Recall | bShipRecall / ShipRecallDelay | true / 20 | s Parked before the recall (B2.11) |
| Recall | ShipRecallSpeed / ShipRecallCrossHeight | 2500 / 8000 | cm/s, cm above path height to cross the field |
| Recall | ShipRecallMaxTime / ShipRecallMaxDistance / ShipRecallBlockedTime | 60 / 100000 / 10 | s, cm, s before the replace fallback |
| Net | LaneHintInterval | 0.25 | s |

Ship hook properties: section 2.7 (on GA_GrappleSwing2).

## Appendix B. Console commands and CVars

| Command | Where | What |
|---|---|---|
| `Aura.Match.Status` | any | phase, rules, result, teams (players, lives, ship, lane state, respawn in), players (team, ship-borne) |
| `Aura.Match.Rules Teams=.. ShipLives=.. Swarm=.. TimeLimit=.. FF=.. GrappleShips=.. LaneAssist=..` | server | ApplyRules; team mode at the next restart; TimeLimit restarts the clock from now |
| `Aura.Match.Set <Name> <Value>` / `Aura.Match.Get <Name>` | any | a UMyMatchSettings value on this machine (the `Aura.Airship.Set Settings.` pattern, `AirshipSubsystem.cpp:613-668`); lane geometry knobs need `Aura.Lane.Rebuild` |
| `Aura.Match.Start` | server | WaitingToStart: start the countdown with whoever is in (the pause menu's Start match); Countdown: end it now |
| `Aura.Match.End <Team or -1>` | server | TeamWon for Team, -1 = Draw (EndReason Host) |
| `Aura.Match.Recall <Team>` | server | start that team ship's recall now (B2.11) |
| `Aura.Match.Restart` | server | B4.6 |
| `Aura.Match.Team <PlayerIndex> <0/1>` | server | B1.5 |
| `Aura.Match.ShipLives <Team> <N>` | server | B3.2 |
| `Aura.Match.KillShip <Team>` | server | that team's ship: DebugKill (sets Health directly, so it ignores spawn protection) |
| `Aura.Match.DamageShip <Team> <Amount>` | server | that team's ship: ApplyShipDamage (crew share applies) |
| `Aura.Match.Swarm <0-4>` | server | difficulty now |
| `Aura.Match.Dump [path]` | server | JSON (B11) |
| `Aura.Lane.Status` | server | per team ship: state, u, errors, target u and speed, clamp, front u, cruise end u |
| `Aura.Lane.Teleport <Team> <U m> [dZ m]` | server | puts the ship on its lane at U (dZ above or below the lane), velocity zero, Cruising |
| `Aura.Lane.Rebuild` | server | re-sample the whole lane |
| `Aura.Lane.Check` | server | smallest hull-footprint-to-field gap on both lanes and its u (B2.1) |
| CVar `Aura.Match.Enable` | read at InitGame | -1 MatchMaps, 0 off, 1 on |
| CVar `Aura.Lane.Debug` | server | 0 off, 1 lanes and targets, 2 plus look-ahead boxes |
| `Aura.Airship.Telemetry` | any | fourth line: lane (B11) |

PlayerIndex = the server's player controller order (0 = host), as `Aura.Airship.*` uses (`AirshipSubsystem.cpp:527-540`).

## Appendix C. StartupMap numbers (decoded and worked out)

* Spawner at (5441.6, -10000, 0), no rotation; HexRadius 200 (S = 2), SegmentLength 10000, PointsPerSegment 2,
  ExtendDistance 10000, MaxYawDeviation 0; PathEndFogCount not overridden (BP default 4). Decoded from both trees' maps
  (lanes_map) and re-checked in the clone's map for MaxYawDeviation, HexRadius, SegmentLength, ExtendDistance,
  PointsPerSegment.
* u = x - 5441.6, v = y + 10000. H = 10000 x 2 = 20000 cm. Lane offset R = 20000 + 2500 = 22500: round 0 team 0 at
  y = +12500, team 1 at y = -32500 (swapped on odd versus rounds, 7.1 F5); z = 0 + 200.
* Path: 2 initial segments of 200 m (u 0..40000); a new one whenever a player is within 200 m (2D) of the end.
  CruiseEndU at the start = 40000 - 10000 = 30000 (x 35442). LaneStartU = -12000 (x -6558).
* Match-start ships at (5442, 12500, 200) and (5442, -32500, 200), yaw 0.
* Start floor 80 m square at the origin (lanes_map): u -94..-14 m, v +60..+140 m. Its corner (4000, 4000) to the right
  lane's hull inner side (y 11370): about 75 m; corner (4000, -4000) to the left lane's (y -31370): about 274 m.
* Field limit 200 m; hull inner side 213.7 m: 13.7 m minimum gap to any platform the graph may place.
* Sentinel corners at v +-200 m, z +46.2 m: 25 m inside the lanes, 44 m above them.
* Fog banks at v +-55 and +-165 m (count 4); count 5 would put them at 0, +-110, +-220 m.

## Appendix D. Hook point index (8c7e599)

| Where | Change | Owner |
|---|---|---|
| `MyGameMode.h:19-164`, `MyGameMode.cpp:33-49` (PreLogin), `:114-133` (Logout), `:107-112` (SetPlayerDefaults: net cull), `:135-138` (PlayerCanRestart: wait), `:140-165`, `:270-342`, `:372-455` (FindRespawnSpot: own side) | InitGame, InitNewPlayer, StartPlay, ChoosePlayerStart, RestartPlayer, team ships, rules, swarm | match |
| `MyGameState.h:35-113`, `MyGameState.cpp:16-20` | match state, teams, events | match |
| `MyPlayerState.h:19-112`, `MyPlayerState.cpp:16-25` | TeamId | match |
| `MyPlayerController2.h:60-69` | PawnLeavingGame | match |
| `MyHUD.h:16-48`, `MyHUD.cpp:17-76` | MatchWidgetClass | match |
| `MyHexPathSpawner.h:126-160` (public getters), `MyHexPathSpawner.cpp:268-279` | getters, CheckPlayers | lanes |
| `MyHexBridgeSubsystem.cpp:4777-4836` | SelectLeadPawn, GetLeadPathDistance | lanes |
| `AirshipPawn.cpp:271-398` (constructor: Lane component; `:397` tag), `:400-415` (TeamId rep), `:553-613` (Tick: `:568`; `:606-612` pilot destroyed: tags), `:868-998` (assist look, drive-intent bit), `:1194-1219` (CanBoard), `:1284-1330` / `:1332-1422` (notify lane, end protection), `:1424-1451` (tags), `:1539-1571` (IsRiding / rider team), `:1708-1757` (CanMount), `:2295-2310` (SpawnTurrets: tags), `:3664-3691` (hull contact), `:4232` (telemetry) | B2, B3.4, B6 | airship |
| `AirshipFlightComponent.h:14-30`, `.cpp:424-484`, `:831-941`, `:1125-1275` (`:1213-1225`), `:1462-1487`, `:1596-1605`, `:1968`, `:2012-2032`, `:2187` | Lane mode | airship |
| `AirshipTypes.h:88-98`, `:330` | Lane enum, telemetry, refusal enum | airship |
| `AirshipPilotComponent.cpp:255-289`, `:367-450` | console filter, refusal | airship |
| `AirshipSubsystem.cpp:900-902` (+ new static IsShipBorne) | telemetry line 4 | airship |
| `AirshipCannonball.cpp:186-222` (SourceTeamId); `AirshipTurret.cpp:176` (tag only without a ship), `:586`, `:679`, `:703-732` (team check, ShipDamageTurretRound) | friendly fire, B6.4, B6.5 | airship |
| `AirshipSubsystem.cpp:150-172` (FindNearestAirship ForUser), `AirshipPilotComponent.cpp:255-289`, `:309-313` | console / prompt team filter | airship |
| `AirshipHUDWidget.cpp` (pilot panel rows) | LANE row | airship |
| `GA_GunShoot.cpp:204-218`, `:222-279`; `MySplashDamageLibrary.cpp:92-105`; `MyProjectile.cpp:40-49`; `MyAttributeSet.cpp:64-68` | friendly fire, fixed ship damage, spawn protection | combat |
| `MechSentinelWaveSpawner.h:320-377`, `.cpp:263-339`, `:403-421`; `MechSentinelSwarmSubsystem.h:173` | difficulty, comment | combat |
| `BurrowerSpawnSubsystem.cpp:195-298`; `BurrowerCharacter.cpp:64`, `:259`, `:513-528` | difficulty, ship-borne targets | combat |
| `GA_GrappleSwing2.h:372-425`, `:573`; `.cpp:129-150`, `:1227-1296`, `:1383-1466`, `:1499-1539`, `:1551` | ship hook | grapple |
| `MainMenu3.h:98-110`, `:219-223`; `MainMenu3.cpp:29-50`, `:385-411`, `:431-437`, `:1144`; `PauseMenu3.*`; `MultiplayerSessionsSubsystem.cpp:387-402` | options, Start / Restart buttons, StartSession skip | menu |

---

## 6. Critique log (revision 2, 2026-11-25)

Each critic issue was checked against the code at 8c7e599 (and the 5.8 engine source) before it was folded in. Verdicts:
**folded** (taken as suggested or with the changes named), **partly** (the valid part taken, the rest rejected with the
reason), **rejected**. The decisions the lead posted to Talal stay, except the ones listed in 5.3, which are questions now (Q5, Q16, Q17,
Q19, Q20).

| # | Issue (critic's section) | Checked | Verdict and what changed |
|---|---|---|---|
| 1 | Stranded ships, no way to end the match (B2.3, B2.8, B3.2, B4.4) | spec text; CPP_NOTES 15.3 (lethal crew share puts the pilot on foot) | **Partly.** Recall added (B2.11, flag 9, Q16, T2.10): Parked for 20 s -> Returning (climbs over the field when it must cross it) -> Cruising; replace with no life lost when blocked, too slow or too far. Rejected the second trigger "no teammate within hook range for 15 s": the 20 s timer alone covers it and gunners riding along don't need a special case. |
| 2 | No time limit, stalemate (B4.4, flag 3, B6.4) | CPP_NOTES 15.2 (unmanned turrets are the pilot's) | **Partly.** `TimeLimitMinutes` 15 (rules, URL `TimeLimit`), tie-break lives > hull fraction > team front u, clock on the bar (B4.4, flag 10, Q17, M5.3). Rejected sudden death (undriven ships as swarm targets, or lanes moving in): the tie-break already ends the match, and moving the lanes in would change the posted lane decision. |
| 3 | Short time to kill, spawn camping (B3.1, B3.2, 0.2) | `AirshipPawn.h:611`, `:802`, `:806`; CPP_NOTES 15.2 heat | **Partly.** Spawn protection until first boarded / manned or 15 s, one gate in `UMyAttributeSet` (B3.4, Q22, T3.4); respawn at least 250 m from the enemy ship (B3.1); under-attack alert (B8.3); time-to-kill table (B3.5); the non-goal removed. Rejected turret self-defence: it needs target selection code; protection, the alert and the time limit cover the case (0.2). |
| 4 | Talal's local gun value breaks ship lives (R11, B5.6) | round2_map guns; CPP_NOTES 15.2; `GA_GunShoot.cpp:243-279`; `AirshipPawn.h:383-389` | **Folded** with a change: fixed `ShipDamageGunHit` 5 and `ShipDamageTurretRound` 4 on team ships and their turrets (B6.5, flag 11). The critic's 20 per turret round rejected: 4 is today's committed number (4 x 1), and 20 would sink a ship in about 10 s. The gun-value question split from Q13 into Q18, to ask before the first versus play test. |
| 5 | Host advantage at the start (B1.2, flag 5, as_61, now as_71) | Appendix C geometry; the as_71 coordinates (v +85 / +115 m, both on the floor) | **Partly.** Versus starts with each team on its own deck (`bStartAboard`, B4.2), lane sides swap every round (B1.6), the claim that Team1 PlayerStarts help removed (section 3), Q3. Rejected "spawn both ships level with the floor at equal distance": the floor lies inside the right half of the field, so the far lane can't be brought level with it without a lane inside the field. |
| 6 | Countdown vs real joins (B4.2, B1.3) | `MainMenu3.cpp:1144` (ServerTravel after the session is created) | **Partly.** Versus waits in WaitingToStart until the expected players are in (new `Players` URL option from Max Players), the host can start early (pause menu, `Aura.Match.Start`); practice turning into versus runs a fresh countdown and resets both teams (B1.3, B4.2, Q21, M1.0, M1.4). Changed: no pawns while waiting instead of "free play", because free play lets the host race ahead, grow the path and start the collapse before the others arrive (R15). |
| 7 | Pace vs hook range (B2.4, B2.6, B7.1) | `GA_GrappleSwing2.h:129`, `:258`, `:325`; `AirshipFlightComponent.h:513` (AFan) | **Folded.** Proportional pace (gain 0.3 /s, aim 15 m ahead of the front, 6 m/s floor, up to 28 m/s, ramp 2.5 m/s^2), LaneEndMargin 100 m x S, acceleration fed forward (flag 12, B2.4, B2.6, Q5, T2.1b). Found while checking: revision 1's LaneAccelMax 200 couldn't hold 28 m/s (raised to 600), and ShipHookMaxShipSpeed 2500 would have refused hooks on a catching-up lane ship (raised to 3000). |
| 8 | 2v1 fairness (B1.2) | CPP_NOTES 15.1-15.2 | **Folded** as +1 ship life per missing player for the smaller team (`bSmallTeamHandicap`, B1.2, M1.2); the hull multiplier is the named alternative and co-op practice for 3 players is asked (Q19). Rejected auto-firing turrets as the handicap (target selection again). |
| 9 | Roles of players not driving; respawn position (B9.3, B9.7, Q15) | `MyGameMode.cpp:372-455` (respawn only past the global lead: everything behind it collapses) | **Partly.** Role table (B12); respawn past the lead **on the own side** of the path (B9.7); `bRespawnAboard` as an option, default off (Q15); the tie-break gives the race a stake (B4.4). Rejected "respawn past the own team's front": a team front behind the global lead is on collapsing platforms. Rejected a faster ship respawn for the race leader: the tie-break is enough. |
| 10 | Fall death kills ship-borne characters (B9.6) | B9.6 text; `AirshipFlightComponent.h` (no altitude limit) | **Folded** together with 19 (B9.6, T3.6, M9.1). |
| 11 | HUD can't explain the match (B8) | B8 text; 0.2 | **Folded:** team name tags, "TEAMMATE" under the crosshair, hull bars on the bar and the markers, "YOUR SHIP IS UNDER ATTACK" toast and a flashing marker (at most every 5 s), objective line, "AIM + GRAPPLE", clock, end reason (B8.1-B8.5, T7.1). Changed: the TEAMMATE label is drawn by the match HUD instead of tinting the crosshair, which isn't in C++ (grep: a Blueprint widget, not touched). |
| 12 | Ship parked in the other team's lane (B2.3, B2.7) | B2.3 zone text | **Folded** with a change: per-team zone stated, no capture in the other lane (B2.3); after 5 s blocked the lane ship goes round **outward** by 35 m (B2.7, T2.11). Rejected climbing over the blocker: deck riders on both ships, and outward there is only sky. 35 m rather than 40 so an Assist ship stays in its zone. |
| 13 | Solo practice ends after three ships (B4.4, B1.2) | B3.2 / B4.4 text | **Folded:** unlimited ships in solo practice, lives in co-op practice (B3.2, Q20, T3.3, T3.5). |
| 14 | Swarm difficulty: player count, wave 1 at Normal (B5.4) | `MechSentinelWaveSpawner.cpp:1018-1062` (no player count, grep); `MyHexPathSpawner.cpp:69-72` | **Folded:** Count x (0.6 + 0.4 x players, max 2.2); the preset applied in StartPlay before Super; a sentence on what difficulty does to a match (B5.4, Q13, T4.1). |
| 15 | Teams reshuffle on restart; 1v1 advertises 4 slots (B4.6, B5.2) | `MainMenu3.h:110`, `:219-223` | **Folded:** `UMyMatchMemorySubsystem` (a game instance subsystem, like the project's UMultiplayerSessionsSubsystem and UMySettingsSubsystem) keeps teams by unique net id, sides swap per round (B1.6, M7.1); the Rules box sets Max Players (B5.2); the non-goal removed. |
| 16 | Parking feedback for the pilot (B8.5, B2.3) | B8.5 text | **Folded:** the LANE row says what an exit does now (B8.6). |
| 17 | Beam knockback with the new fall death (B6.2) | string scan of `GA_BeamBP.uasset`: `LaunchCharacter`, `LaunchVelocity` present | **Folded:** as_70 reads the graph before the first versus test; a Branch on `IsFriendlyFireBlocked` (BlueprintPure) if needed; M3.1 pass condition (teammate moved < 0.5 m). |
| 18 | Turrets keep the sentinel bullet tag (B6.4) | `AirshipPawn.cpp:397`, `:2304`, `:606-612`; `AirshipTurret.cpp:97`, `:176`; `MechSentinelSwarmSubsystem.cpp:687-691` | **Folded:** `RefreshSentinelBulletTags()` on the hull and every turret, keyed on `HasPilot() || GetController()`, with its call sites; the turret's own add only without a ship (B6.4, M4.1). |
| 19 | Fall death: null controller for a seated pilot; T3.2 timing (B9.6) | `MyGameMode.cpp:188-191`, `:225`; `AirshipPawn.cpp:1320`; `AirshipFlightComponent.cpp:1489` | **Folded:** only player states' own pawns, never ship-borne, falling with no base for > 1 s; the crew checked once ejected; T3.2 loosened to 8 s with the expected 5.5-7 s (B9.6, B3.3). |
| 20 | Lane offset in v shrinks on bends (B2.1) | `MyHexPathSpawner.h:224` (MaxYawDeviation 60), `:239` (NoiseSeed 17.31) | **Folded:** envelope of circles of radius H + LaneClearance; smoothing then max with the unsmoothed envelope; the smoothing number corrected (1.9 m, revision 1 said 0.5 m); hull footprint gap check `Aura.Lane.Check` and T2.12. Changed: the check runs in PIE (the lane code is C++), not as an offline script. |
| 21 | Reel anchor drifts off a ramping lane ship; LOS sees turrets (B7.3, B7.4) | spec numbers; `AirshipTurret.cpp:97`; `GA_GrappleSwing2.h:372` | **Folded:** lane speed frozen during a reel (`NotifyIncomingReel` / `HasIncomingReel`), eased cap, the in-reel drift allowance equal to the validation's, a deck-box finish, LOS ignoring the ship and its attached actors (B7.3, B7.4, T6.3, T6.4). |
| 22 | Relevancy across 450 m (B10) | engine `Actor.cpp:312`; `AirshipPawn.cpp:1310`, `:1804`; no NetCull in Source (grep); engine Mass replication default off beyond 50 m | **Folded:** player characters get a 600 m cull distance while the match is on (B10, M8.1); a sentinel visibility check (M8.2, R13). Chose the cull distance over "riders and reelers always relevant" because it also covers enemies across the field. |
| 23 | IsRiderForDamage with a team test changes "ship-borne" (0.3, B6.3) | spec text | **Folded:** team-blind `IsRiding` for ship-borne; `IsRiderForDamage` = IsRiding + team (0.3, B6.3). |
| 24 | Console board ignores the team filter (B6.3) | `AirshipSubsystem.cpp:150-172`, `:762`; `AirshipPilotComponent.cpp:309-313`; `AirshipPawn.cpp:1198` | **Folded:** `FindNearestAirship(..., ForUser)` and `FindBoardableAirship` filtered with `CanUseShip` (any machine) (B6.3, M2.3). Found while checking: `Aura.Airship.Mount` already filters through `CanMount` (`AirshipPilotComponent.cpp:465-482`), so it needs nothing. |
| 25 | Script numbers collide with PR A's as_60* (section 3) | `ls Docs/Airship/scripts/ue` (untracked as_60_pie_mp_round2.py, as_60s_status.py, as_60x_stop.py) | **Folded:** PR B's scripts are as_70-as_76 (sections 2-4). |
| 26 | SelfBuffChance scaled twice (B5.4) | `MechSentinelWaveSpawner.h:98-100` | **Folded:** the wave multiplier only; the rules copy sets MaxAttackersPerPlayer only (B5.4, T4.1). |
| 27 | Difficulty applied after wave 1 is queued (B5.4, B4.2) | `MyHexPathSpawner.cpp:69-72`; `MechSentinelWaveSpawner.cpp:1021-1062`; `.h:75` | **Folded** (same fix as 14): StartPlay before Super; `SetDifficultyScale` must work before the spawner's BeginPlay (B5.4, 2.6). The other option, spawners reading the match rules in their BeginPlay, not taken: it would put match code in the spawner. |
| 28 | Point & Fly Q/E in Assist (B2.9) | `AirshipPawn.cpp:905-912`, `:948`; `AirshipTypes.h:42-57` (bit 7 free) | **Folded:** drive-intent bit `1 << 7`; no Assist re-entry while the camera steers (B2.5 item 9, B2.9, T2.5b). |
| 29 | Target stops dead at the cap, overshoot (B2.4, T2.1, T2.2) | spec numbers | **Folded:** the target speed eases into the cap (`sqrt(2 a d)`); T2.1 / T2.2 measure after settling with an overshoot bound. |
| 30 | bActive never cleared (B1.2-B1.4) | spec text | **Folded:** active teams decided at the countdown's start and end (B1.2, B1.4, B4.2, M1.4). |
| 31 | Restart in packaged builds; second StartSession; OpenLevel `?` (B4.6) | `AirshipSubsystem.cpp:513`; `MyGameMode.cpp:56-66`; `MultiplayerSessionsSubsystem.cpp:387-402`; engine `GameplayStatics.cpp:992-995` | **Partly.** Pause-menu Restart match / Start match (host), StartSession skipped when InProgress, the leading `?` stripped for OpenLevel, R6 packaged check (B4.6, B5.2). Rejected a button on the end panel (the match HUD is NativePaint and takes no input; the hint points at the pause menu) and a server RPC (the listen host's menu runs on the server; clients don't get the buttons). |
| 32 | Cannonball team from SourceShip at impact (B6.2) | `AirshipCannonball.cpp:193`, `:346-352` | **Folded:** `SourceTeamId` stored at spawn (B6.2, 2.3, 2.5, M3.1). |
| 33 | Two wrong claims: Burrower grace, PlayerStart fallback (B9.4, B4.2) | `BurrowerSpawnSubsystem.cpp:234-244`, `:252`; engine `GameModeBase.cpp:1116-1123`, `:1184` | **Folded:** both sentences corrected (B9.4, B4.2); the ChoosePlayerStart "then any" fallback and the ring search stay. |

Also changed while checking (not raised by the critics):

* `AAirshipPawn::ApplyShipDamage` gains an optional instigator: hull impacts already call it with the ship's own ASC
  (`AirshipPawn.cpp:3718`, `:3735`), so the under-attack event needs the shooter in the context to tell a shot from a
  crash (B6.5, B8.3).
* `Aura.Match.KillShip` ignores spawn protection: `DebugKill` sets Health directly (`AirshipPawn.cpp`, DebugKill), not
  through the attribute set, so the life tests still work (Appendix B).
* The Countdown phase is new in `EMyMatchPhase`; `EMyMatchEndReason`, three match events, the Returning lane state and
  the Bypass / Reel clamps are new in `MyMatchTypes.h` (2.1).
* New files: `Match/MyMatchMemorySubsystem.h/.cpp` (match owner); owners widened: menu takes `PauseMenu3.*` and
  `MultiplayerSessionsSubsystem.cpp`, combat takes the one gate in `MyAttributeSet.cpp` (section 2).
* Size: revision 2 adds roughly 2,000 lines of C++ to revision 1's plan (recall and bypass in the lane component about
  450, waiting / countdown / start aboard / time limit / handicap / memory in the match code about 600, HUD additions
  about 400, the rest spread thin) and about 400 lines of harness Python (inferred).

---

## 7. Implementation notes (2026-11-27)

What was built from this spec, and where the code differs from sections 0-5 and the appendices, with the reason.
Where this section and the sections above disagree, this section is what the code does (the affected places above
carry a pointer to here).

`file:line` in this section is in the PR B worktree `/mnt/new_partition/UnrealProjects/_AirshipWorkB` (branch
`airship-r2-prb`: the WIP commit 1853bc6 plus this pass's two comment edits and docs). Paths are under `Source/Aura/`
unless they start with `Docs/`. Function names are the anchors if lines move.

State: the parts, three reviews and the fix pass are done. `build_r2b.sh` ends with EXIT 0 (2026-11-27) three ways:
the whole module in unity files, the 16 .cpp files the findings and their fixes touch compiled on their own
(outside the unity files), and with adaptive unity off. **Nothing has been run in the editor or in PIE yet**: section 4 is still the plan,
and every "fixed" below means "the code now does this and compiles", not "seen working".

### 7.1 Review fixes

The three reviews gave 12 findings and 8 nits. All 12 findings were checked against the code and were valid; each is
fixed. The swarm-count finding was reported twice (F2).

| # | What was wrong | What the code does now | Where | Spec text it changes |
|---|---|---|---|---|
| F1 | A host kick or ban of a team ship's pilot destroyed the ship and left his character in the world with no controller. The engine's `AGameSession::KickPlayer` destroys the possessed pawn before the controller (engine `GameSession.cpp:369-378`), and the controller still has its connection, so `PawnLeavingGame` (B1.4) never runs (engine `PlayerController.cpp:1635-1645`). | `UMultiplayerSessionsSubsystem::KickPlayer` puts a team ship's pilot on foot first (`UnboardPilot(false)`), so the kick takes his character and the ship stays (cruise or hold, as in B1.4). A free ship still goes with its pilot, as in PR A, and the pilot's leftover character is destroyed after the kick. | `Private/EOS/MultiplayerSessionsSubsystem.cpp:1099-1124` | B1.4: a second path next to `PawnLeavingGame` (`Private/PlayerInput/MyPlayerController2.cpp:419-441`) |
| F2 | When a player left, the swarm's player-count factor stayed one player too high until the next join: `ApplySwarmDifficulty` counted the player array, which still holds the leaver during `Logout`. | It adds up the two teams' `NumPlayers`, which `RecountTeams(Leaving)` has just written without him. | `Private/MyGameMode.cpp:1727-1730` (compared at `:930-937`) | B5.4: none (the rule was right) |
| F3 | Play Solo with the Rules box on 1v1 or 2v2 waited for players who can't come (Play Solo creates no session). | `IsPracticeStart` is true for `ExpectedPlayers <= 1` in every team mode (Play Solo sends `Players=1`, and so does a restart with only the host left). A player who joins later turns it into versus (B1.3). | `Private/MyGameMode.cpp:622-628` | B4.2 "Practice (... Auto with ExpectedPlayers 1 ...)": any team mode |
| F4 | The smaller team's handicap lives decided the time-limit tie-break by themselves: a 2v1 nobody fought ended 4 lives against 3 for the one-player team. | The first tie-break step compares `LivesLeft - BonusLives` (= ShipLives - ShipsLost: fewer ships lost wins). `bTimeLimitCountsHandicap` (default off) gives the old rule back. The HUD says "Fewest ships lost after 15:00 wins." and "Time up: X lost fewer ships". | `UMyTeamLibrary::GetTimeLimitLives`, `Private/Match/MyTeamLibrary.cpp:177-182`; `ResolveTimeLimit`, `Private/MyGameMode.cpp:2743-2760`; `Private/Match/MyMatchHUDWidget.cpp:415-420`, `:567-572` | B4.4 first tie-break step; new question Q23 (7.5) |
| F5 | A practice round played on an odd round put the lone ship on the left lane, about 274 m from the start floor and out of hook range (a versus round followed by practice). | The sides swap on odd **versus** rounds only. It is decided once, when the round's countdown starts, and replicated as `AMyGameState::bLaneSidesSwapped`; `UMyLaneSubsystem::GetSideForTeam` and the game mode's fallback read it. A ship left over from a countdown that went back to waiting is removed when the sides change. | `StartCountdown`, `Private/MyGameMode.cpp:1094-1110`; `Private/Match/MyLaneSubsystem.cpp:707-724`; `Private/MyGameMode.cpp:1007-1018`; `Public/MyGameState.h:129-131`, `:218` | B1.6, Appendix C ("swapped on odd rounds") |
| F6 | A player who joined the empty team during a practice countdown (a host's early start with one player) got a pawn on the floor at once; the round then turned versus with the others on their decks and him 274 m from his lane. | `IsWaitingForTeamStart`: during a Countdown, a player whose team isn't active yet gets no pawn. When the countdown ends his team becomes active, the round is versus, and `SpawnWaitingPlayers` starts him aboard his own ship. Players who already had a pawn (the practice start of 7.3) keep it. | `Private/MyGameMode.cpp:675-689`, `:322-325`, `:1211-1215`, `:1376-1383` | B1.3 first sentence now holds for a practice countdown too |
| F7 | Two open-question defaults couldn't be changed by a value: Q7 (more than 4 players) and Q19's alternative (3 players as co-op). | `AutoMaxPlayersPerTeam` (0 = no cap; with a cap, PreLogin refuses a join when both teams are full) and `AutoCoopPlayers` (0 = never; Auto with exactly that many expected players plays the round as TeamMode Practice, the next round decides again). | `Public/Match/MyMatchSettings.h:101-107`; `GetTeamCap`, `Private/MyGameMode.cpp:645-655`; `:206-218`; `ParseMatchOptions`, `:501-507` | Appendix A (7.2); Q7, Q19 |
| F8 | With the match off, Burrowers ignored pilots, gunners and deck riders of free ships. In PR A the Burrower hunted the piloted ship. | `IsLivingTarget` skips ship-borne pawns only while `UMyTeamLibrary::IsMatchActive`. | `Private/Burrower/BurrowerCharacter.cpp:522-529` | B9.4: "while a match runs"; B5.5 |
| F9 | With the match off, the ship hook was on (the rule's default is true): a crosshair on a free ship reeled the player onto its deck, and every grapple search fired an extra 120 m trace. | `IsShipHookOn`: the rule while a match runs; with no match it is off, unless `bShipHookOutsideMatch` (default off; then `DefaultRules.bGrappleShips` decides). | `Private/AbilitySystem/Abilities/GA_GrappleSwing2.cpp:1704-1713`; `Public/Match/MyMatchSettings.h:129-131` | B7 first line; B5.5 |
| F10 | The difficulty's Burrower MaxAlivePerPlayer replaced UBurrowerSettings' value: with Talal's local 10, Very Hard and Nightmare cut it to 2. | The preset is a floor on the setting, never a cut: `max(preset, setting)`. With his 10, every preset keeps 10; with the committed 1, Very Hard and Nightmare give 2. | `Private/Burrower/BurrowerSpawnSubsystem.cpp:398-404` | B5.4 table row; B5.6 holds again |
| F11 | `MatchMaps` = { StartupMap } puts every existing StartupMap harness inside a team match. The Burrower PIE harness (listen, 2 players) would wait for a countdown, start both players on ship decks, and find no Burrower target. | The Burrower harness turns the match off for its run: config key `match_enable` (default 0) sets `Aura.Match.Enable 0` at arm time and restores it at the end; the cleanup script restores it too. | `Docs/Burrower/scripts/pie/bw_pie_test.py:60`, `:1182-1192`, `:1255-1260`; `bw_pie_cleanup.py:49-50`; `README.md:158` | section 4: see 7.4 for harnesses outside this repo's Docs |

Nits:

| # | Nit | Outcome | Where |
|---|---|---|---|
| N1 | AssignTeam's spectator check never fired (it ran before the engine marks a `?SpectatorOnly=1` joiner). | Fixed: `InitNewPlayer` reads the option itself and skips AssignTeam; a player Super made a spectator after all is set back to team 255. | `Private/MyGameMode.cpp:708-724` |
| N2 | `SetTeamId`'s pilot check could never fire (a seated pilot is unpossessed and attached, so his team read as the ship's new team). | Fixed: the pilot is judged by the controller that flies the ship. | `Private/Airship/AirshipPawn.cpp:808-820` |
| N3 | `OnLocalUseRefused` is a process-wide static: in single-process PIE one player's refusal showed a toast in every window. (Reported twice.) | Fixed: the delegate carries the refused player's controller and the HUD ignores other players'. Signature: `(const APlayerController*, EAirshipUseRefusal)`. | `Public/Airship/AirshipPilotComponent.h:108`; `Private/Airship/AirshipPilotComponent.cpp:31`, `:477-483`; `Private/Match/MyMatchHUDWidget.cpp:270-276` |
| N4 | The Burrower's ship-borne check wasn't gated on the match. | Same as F8. | |
| N5 | During the practice-to-versus countdown the practice team's ship stopped and a recall in progress was cancelled; B1.3 says those players keep playing. | Fixed: `AMyGameState::bPlayGoesOn` (replicated, set by `SetMatchPhase(Countdown, End, true)` from `StartPracticeToVersus`); the lane component treats that countdown as InProgress. | `Private/MyGameMode.cpp:1319-1322`; `Public/MyGameState.h:133-135`, `:149-150`, `:221`; `Private/MyGameState.cpp:211-222`; `Private/Airship/AirshipLaneComponent.cpp:573-575` |
| N6 | RoundIndex goes up only after a versus round, not on every RestartMatch as B1.6 says. | Kept and written down here: a practice restart keeps the round, so the next versus round still alternates. Together with F5 a practice ship is always on the floor's side. | `RestartMatch`, `Private/MyGameMode.cpp:1516-1532` |
| N7 | One-player listen-server PIE on StartupMap leaves the host with no pawn, waiting for a second player (Esc > Start match gets him out). | **Not changed** (Appendix A designs it so, and the as_75 stages set `DefaultExpectedPlayers` themselves). It is a value change: `DefaultExpectedPlayers` 1 starts such a game as practice at once and a joiner turns it into versus. The setting's tooltip says so now. New question Q25 (7.5). | `Public/Match/MyMatchSettings.h:97-99` |

Left as it is, noticed while checking F5: a practice countdown on an odd round that a joiner turns into versus (F6)
keeps the unswapped sides for that one round, because the sides are decided when the countdown starts.

### 7.2 Added by the fixes: settings, replicated state, API

Settings (`UMyMatchSettings`, category Match; additions to Appendix A, all defaults keep the behaviour sections 0-5
describe unless 7.1 says otherwise):

| Name | Default | Meaning |
|---|---|---|
| AutoMaxPlayersPerTeam | 0 | Auto teams: at most this many per team, a join is refused when both are full. 0 = no cap (Q7) |
| AutoCoopPlayers | 0 | Auto with exactly this many expected players plays co-op practice instead of versus. 3 = Q19's alternative. 0 = never |
| bTimeLimitCountsHandicap | false | the time limit's first tie-break step counts the handicap's extra lives too (F4, Q23) |
| bShipHookOutsideMatch | false | the ship hook also works with the match off (F9, Q24) |

Replicated on `AMyGameState` (additions to B10): `bLaneSidesSwapped` (F5) and `bPlayGoesOn` (N5), both in
`Aura.Match.Dump` as `sides_swapped` and `play_goes_on` (`Private/Match/MyMatchConsole.cpp:361-362`).

API (additions to section 2): `UMyTeamLibrary::GetTimeLimitLives(const FMyTeamState&)`;
`AMyGameState::AreLaneSidesSwapped()`, `IsPlayGoingOn()`, `SetLaneSidesSwapped(bool)`, a third parameter on
`SetMatchPhase(Phase, EndTime, bInPlayGoesOn = false)`; `AMyGameMode::IsWaitingForTeamStart(Controller)`;
`UAirshipPilotComponent::OnLocalUseRefused` gains the controller (N3);
`UBurrowerSpawnSubsystem::GetMaxAlivePerPlayer()` returns the larger of the preset and the setting (F10).

### 7.3 Deviations made by the parts

Match (game mode, game state, memory, console):

* **Listen PIE logs the host in before the listen port opens** (engine `GameInstance.cpp:538` against `:562`), so at
  his login the net mode is Standalone and he gets a practice pawn. In a versus start `StartPlay` takes back any pawn
  spawned before the wait (unpossess, destroy, one log line). A packaged `LoadMap` listens first and never needs it.
  `Private/MyGameMode.cpp:786-802`.
* **The countdown start and practice-to-versus are evaluated in `InitNewPlayer`**, after the team is assigned, not in
  PostLogin (B1.2 only names AssignTeam there). Reason: the engine asks `PlayerCanRestart` for the new player's pawn
  inside `Super::PostLogin`, so the phase has to be right before that. `Private/MyGameMode.cpp:733-735`.
* **Restart URL**: `Players=<players in the match now>` (at least 1) instead of the host's Max Players, plus `Match=1`
  and `Round=N` (B4.6 lists only the rules). Reason: clients reconnect after the non-seamless travel, so the next
  round starts as soon as they are all back; the host's Start match covers anyone who doesn't return.
  `Private/MyGameMode.cpp:1534-1547`.
* **RoundIndex** +1 only after a versus round (N6). The URL's `Round` wins over the memory's count.
  `Private/MyGameMode.cpp:1516-1532`, `:378-390`.
* **Match memory**: `Reset` is called by `AMyGameMode::InitGame` whenever the URL has no `Round` option (a fresh
  match from the menu or an open command); nothing else calls it (B1.6 said "cleared when the host leaves to the
  menu": the same effect, from the other end). Added `SetRoundIndex` and `GetNumRemembered`.
  `Private/MyGameMode.cpp:373-394`; `Public/Match/MyMatchMemorySubsystem.h:42-47`.
* **Practice countdown** (the practice start, or a host start with one team): players aren't held, as B4.2 says.
  A player who joins the empty team during it now waits for its end and starts aboard (F6); a join while practice is
  InProgress uses the PracticeToVersus countdown (B1.3).
* **Placed ships**: one claimed through its `ShipTeam<id>` tag is spawn-protected too (the spec didn't say).
  `RemoveTeamShip` gives a claimed placed ship back as a free ship (team 255) instead of destroying it; a spawned team
  ship has its pilot and gunners put on foot before it is destroyed, because the ship's EndPlay would otherwise take
  the pilot's character with it. `Private/MyGameMode.cpp:1862-1866`, `:2060-2108`.
* **`ApplyRules`** keeps the running round's TeamMode in `MatchRules` (so the HUD and the logic stay consistent) and
  stores the new one as `NextTeamMode` for the restart. A changed TimeLimit restarts the clock; `Aura.Match.Rules`
  with `TimeLimit=` given but unchanged calls `RestartTimeLimit()` itself. ShipLives changed while InProgress goes
  through `SetTeamShipLives(ShipLives + BonusLives)`. `Private/MyGameMode.cpp:1609-1669`;
  `Private/Match/MyMatchConsole.cpp:549`.
* **Extra public `AMyGameMode` API** beyond 2.2: `GetMatchRules`, `GetNextTeamMode`, `IsVersusRound`,
  `RestartTimeLimit`, `SetTeamShipLives` (for `Aura.Match.ShipLives`), `BuildRulesOptions`, static
  `ParseRulesOptions` (shared by InitGame and `Aura.Match.Rules`). `Public/MyGameMode.h:126-165`.
* **`GetNeededPlayers`** (the game state's ExpectedPlayers, for the HUD's "WAITING FOR PLAYERS n/m"): practice 1,
  1v1 2, 2v2 4, Auto max(2, Players or DefaultExpectedPlayers). `Private/MyGameMode.cpp:630-643`.
* **Fall death** compares the player's height with the lane point at his u (path height + LaneHeight) from
  `UMyLaneSubsystem::GetLanePoint`; without lanes there is no fall death. `Private/MyGameMode.cpp:2591-2667`.
* **Tie-break tolerances**: the hull fractions must differ by more than 0.1 %, race progress by more than 1 m. Race
  progress is `UMyLaneSubsystem::GetTeamFrontU`, else the largest u of the team's players' last platforms.
  `Private/MyGameMode.cpp:2709-2741`, `:2767`, `:2777`.
* **ShipUnderAttack** fires only when the effect context's instigator is set and isn't the ship. Hull impacts,
  `Aura.Match.DamageShip` (no instigator: the context is the ship) and DebugKill (no effect) don't send it. Sentinel
  bullets do: their source is the swarm's GAS proxy ASC. `OnTeamShipHealthChanged`, `Private/MyGameMode.cpp:2383-2417`.
* **Net cull distance**: `SetPlayerDefaults` sets the 600 m only on `ACharacter` pawns; ships are always relevant
  already. `Private/MyGameMode.cpp:283-290`.
* **`Aura.Match.Dump`** writes its JSON by hand (no Json module), so `Aura.Build.cs` is unchanged.
  `Private/Match/MyMatchConsole.cpp:260`.
* **`Aura.Match.Recall`** calls `UAirshipLaneComponent::StartRecall()`, which the lanes owner added for it (not in
  2.4). `Private/Match/MyMatchConsole.cpp:803`; `Public/Airship/AirshipLaneComponent.h:69`.

HUD (`UMyMatchHUDWidget`):

* TEAMMATE under the crosshair shows only while the local pawn is a character (not for a pilot).
  `Private/Match/MyMatchHUDWidget.cpp:913-916`.
* Name tags sit 220 cm above the character's origin (property `NameTagHeight`, `Public/Match/MyMatchHUDWidget.h:73`).
* The countdown reads "FIGHT STARTS IN n" for versus and "MATCH STARTS IN n" for practice (`.cpp:357`); assist reads
  "SHIP: LANE AUTO, <name> AT THE HELM" (`.cpp:500`).
* AIM + GRAPPLE uses a HUD property `ShipHookDistance` (12000) that mirrors GA_GrappleSwing2's MaxShipHookDistance
  instead of reading the ability (`.h:67-69`, `.cpp:628`). Change both together.

Lanes (`UMyLaneSubsystem`, `UAirshipLaneComponent`, the race hooks):

* **B9.1 and B9.2 apply only while `UMyTeamLibrary::IsMatchActive`** (lead pawn selection, the GetLeadPathDistance
  fallback, path growth). With the match off they are exactly PR A, as 0.3 and B5.5 require; the spec didn't say.
  `Private/Actors/MyHexBridgeSubsystem.cpp:4795`, `:4839`; `Private/Actors/MyHexPathSpawner.cpp:273`.
* **Lanes are built only when `AMyGameMode::IsMatchOn()`** at OnWorldBeginPlay (server). With the match off
  `HasLanes()` is false and the `Aura.Lane.*` commands say so. `Private/Match/MyLaneSubsystem.cpp:74-81`.
* **u_s is measured at the hull origin** (the zone's point, and what the altitude hold holds), not at the centre of
  mass. To match, HoldPoint = lane point + (COM - origin).XY, so the hull origin follows the lane while the flight's
  position law moves the COM. `Private/Airship/AirshipLaneComponent.cpp:246`, `:990`.
* **The cap never pulls the target back.** On entry TargetU = clamp(u_s, LaneStartU, max(cap, u_s)), and each frame
  u_t = min(u_t, max(cap, u_t_old)); B2.4 has clamp(u_s, LaneStartU, cap) and min(u_t, cap). The spec's form would fly
  a ship parked ahead of its team (or one whose front drops back) backwards along the lane at the hold law's speed.
  Now it waits where it is until the cap passes it. The lead clamp (u_s + LaneMaxTargetLead) still pulls the target
  back toward a held-back ship, as specified. `Private/Airship/AirshipLaneComponent.cpp:403`, `:918`.
* **Braking**: a target stopping for a blocker, the countdown or the match end brakes at max(LaneAccel, LaneAccelMax)
  = 600 cm/s^2; every other change of the target speed ramps at LaneAccel (250). The look-ahead length uses the same
  600. `Private/Airship/AirshipLaneComponent.cpp:790-791`, `:907-908`, recall `:1186`.
* **The ShipReturning event** is sent by `UAirshipLaneComponent::EnterReturning`, not by the game mode; the HUD's
  toast uses it. `Private/Airship/AirshipLaneComponent.cpp:479`, `:529`.

Airship classes: `Docs/Airship/CPP_NOTES.md` 16.9 (the lateral grip's speed target in Lane mode, Point & Fly starting
parked on a team ship's helm, the drive-intent bit on team ships only, the drift distance end, five more telemetry
fields, the additions the contract didn't list) and 16.11 (the review fixes on the airship side). Ship hook:
`Docs/GA_GrappleSwing2.md` section 10.

### 7.4 What a match on StartupMap changes outside PR B

`MatchMaps` defaults to { StartupMap } (B5.5), so with PR B merged:

* **Play on StartupMap starts a match.** Standalone: practice (a 5 s countdown the player can move through, one ship
  in the right lane, the match HUD). Listen server with 2 or more players: versus (no pawns until the countdown ends,
  then each team on its own deck). Listen server with one player: it waits for a second (N7).
  `Aura.Match.Enable 0` before the map loads, or `?Match=0`, gives the old race; so does removing StartupMap from
  MatchMaps.
* **Every PIE harness on StartupMap written before PR B runs inside that match** unless it turns it off. Only the
  Burrower harness in this repo's Docs was changed (F11). Any other one lives outside this worktree (not checked
  here; for example the hex collapse, Mech Sentinel demo and JumpHover PIE harnesses, where they load StartupMap):
  each needs `Aura.Match.Enable 0` at arm time and the old value back at the end, the way `as_70_matchlib` and
  `bw_pie_test.py` do it. as_76 proves "match off = PR A" on L_AirshipTest only.
* With the match off, two things that an earlier build of PR B changed are PR A's again (F8, F9): the Burrower hunts
  a piloted free ship, and the grapple never anchors on a ship.

### 7.5 Questions these notes add (defaults in brackets, as in 5.2)

23. **Q23** (touches Q17 and Q19) When the time runs out in a 2v1, should the smaller team's extra life count?
    [No: the team that lost fewer ships wins, then hull, then the race; `bTimeLimitCountsHandicap`.]
24. **Q24** Outside a match (other maps, or the match turned off), should the grapple reel onto free ships
    [no, exactly as before PR B; `bShipHookOutsideMatch`]? And should Burrowers leave players on free ships alone
    there [no, as before; no setting yet]?
25. **Q25** Play in the editor as a listen server with one player on StartupMap waits for a second player (Esc >
    Start match). Should it start as practice at once, and turn versus when someone joins
    [not by default; `DefaultExpectedPlayers` 1 does it]?

Q7 and Q19 now each have a setting behind their answer (F7).
