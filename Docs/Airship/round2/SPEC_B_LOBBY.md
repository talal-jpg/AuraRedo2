# Airship round 2, PR B addendum: the lobby (implementation spec)

Status: addendum to `SPEC_B.md` (revision 2), 2026-11-25. It changes SPEC_B only where section 7 below says so;
everything else in SPEC_B stands. Nothing here was built or run.

Base: the sparse worktree `/mnt/new_partition/UnrealProjects/_AirshipWorkB` (branch `airship-r2-prb`, PR B code
uncommitted on top of 8c7e599). **Every project `file:line` is in that worktree's working tree as of 2026-11-25 05:15 UTC**
(PR B code moves as it is fixed; the function names are the anchors). Engine lines are in
`/mnt/new_partition/5.8/Engine/...`. Map facts were decoded read-only from the `.umap` bytes with the scratchpad parser
(`scratchpad/map/uparse.py`) from Talal's tree (`AuraRedo3/Content/Maps/StartupMap.umap`) and the clone's
(`_AirshipWork/Content/Maps/StartupMap.umap`).

Marks: **verified** = read in the code or engine source; **decoded** = read from asset bytes; **inferred** = worked out.

Terms: **session** = the online session (on this project a Steam lobby, see 5.5); **lobby** = the in-game lobby phase
this addendum adds; **match map** = StartupMap.

Talal, verbatim: "1. Lobby level", then: "have the same startup level as lobby level for now, and when the real match
start the floor and the seperate hex platform which is placed right above the floor right now, I will remove later on ,
the real level consists of only the hex path spawner that spawns hex platforms , bridges for the level and enemy
spawners and every thing else remains".

**Reading used.** For now the lobby **is** StartupMap: no lobby map and no travel at Start. Players spawn and walk
around on the start floor and on the hex platform placed above it while the lobby UI shows the teams, who is ready and
the host's rules. The host presses Start and the match starts in the same level: players go to their team ships, the
swarm and the race begin. Talal will later delete the floor and that platform himself. The real level is then the hex
path spawner (platforms and bridges), the enemy spawners and the rest of the map. So:

* nothing in the match may depend on the floor or that platform (players start aboard the team ships; lanes come from
  the path);
* the in-level lobby must keep working when they are gone (it moves to the path's first platform by itself, 3.1);
* a separate lobby map later is a setting (`LobbyMap`, empty = in-level lobby), not a rewrite (2.7, 5.7);
* our code never removes or edits his map's actors. Everything the lobby needs is spawned at runtime or comes from C++
  and settings.

Other reading: "when the real match starts, the floor and the platform go" could mean they should disappear at Start.
Q-L1 asks. The default leaves them in place. An optional `LobbyOnly` actor tag, which only Talal would add, hides
tagged actors at Start (3.4).

---

## 0. Decisions at a glance

| # | Decision | Section |
|---|---|---|
| D1 | The lobby is a new phase `EMyMatchPhase::Lobby` of `AMyGameMode`, not a separate game mode: one world can only have one game mode, and the lobby needs the match code that already exists (teams, rules, memory). | 4.1 |
| D2 | Only Host Game from the main menu starts in the lobby (`?Lobby=1` on the travel URL). Play Solo, console opens and the PR B harnesses keep the PR B flow. CVar `Aura.Lobby.Enable` forces it for tests. | 2, 4.2 |
| D3 | Where players stand in the lobby: Auto = PlayerStarts that have ground under them (today: the floor, plus the placed platform above it), else the path's first platform (after the floor is deleted). | 3.1 |
| D4 | A lobby zone (the ground's bounds plus margins) holds players in. Anyone outside it for 0.5 s is teleported back. The race can't start early: no ranking, no collapse, no path growth, waves stopped, Burrowers paused, ships locked. | 3.2, 3.3 |
| D5 | In the lobby abilities work but nothing does damage. | 3.3 |
| D6 | Teams: auto-balance on join as built. A player may switch when that keeps the teams within one of each other, or swap with a player who asks for the opposite switch. The host can move anyone. | 4.4 |
| D7 | Ready flags are shown. The host may start without them after a second click ("start anyway"). The setting `bLobbyRequireReady` makes them required. | 4.5, 4.7 |
| D8 | Only the host changes rules (team mode at once in the lobby, lives, swarm, time limit, max players, flags) and starts. Every request goes through RPCs on the player controller. | 4.6, 4.8 |
| D9 | Start = a 5 s lobby countdown, then PR B's start in place: ships claimed or spawned, every player put aboard his own team's ship, swarm resumed, StartSession. | 4.7 |
| D10 | Practice also starts aboard (team 0's ship). Respawns before anyone has landed go to the path's first platforms, never the PlayerStart. The match no longer depends on the floor. | 3.4 |
| D11 | Match end: end screen, then after `EndScreenSeconds` back to the lobby by reloading the map (hard ServerTravel with `?Lobby=1`). Teams come back through `UMyMatchMemorySubsystem` and the rules through the URL. | 2.5, 5.2 |
| D12 | No seamless travel now. `AMyPlayerState::CopyProperties` (TeamId) is added so it can be turned on later. | 5.3 |
| D13 | The lobby widget `UMyLobbyWidget` (C++, BindWidgetOptional) and the WBP `WBP_Lobby3` are built by `as_77` in the Menu3 style. Esc opens the lobby panel while in the lobby. | 6 |
| D14 | Host leaves: the session ends, every client goes back to the main menu (exists today; tested). | 4.9 |

---

## 1. What exists (the facts the design stands on)

* **StartupMap actors** (decoded, Talal's tree): `Floor` (StaticMeshActor, `SM_Template_Map_Floor` scale 8 at (-3, 10, -4),
  the 80 m start floor); `BP_MyHexPlatform_C_1` (a placed `BP_MyHexPlatform`, GridSize 7, HexRadius 200, root
  `HexPillarsISM` at (16, -199, 1678): the "separate hex platform right above the floor"); `PlayerStart_0` at (0, 0, 205)
  (the only PlayerStart); `BP_AirshipPawn_C_6` at (3700, 555, 1097), a free ship next to the floor; `BP_Potion_C_1`;
  decor `StaticMeshActor_1..4` (one is a static `SM_Airship` at (13340, 8972, 893)); `MechSentinelWaveSpawner_0`
  (AdvanceMode External); `BP_MyHexPathSpawner_C_1` (HexRadius 200, ExtendDistance 10000, path start x 5441.6, y -10000).
  The clone's StartupMap has the same actors without the airship pawn (decoded).
* **The placed platform has no SplineDistance** (`MyHexPlatform.h:290`, `:334` default -1; only the path's PCG sets it).
  Landing on it sets `CurrentPlatform` but keeps the rank (`MyPlayerState.cpp:52-59`). It is never a respawn candidate
  (`MyGameMode.cpp:3184`) and is never activated for collapse (`MyGameState.cpp:138`). Verified.
* **The path's platforms can be reached from the floor.** The floor's front edge is at u -14 m, the path starts at u 0
  (SPEC_B Appendix C); boost and grapple cover that easily (inferred). A landing on a path platform ranks the player
  (`MyCharPlayer.cpp:345-361` -> `MyPlayerState.cpp:61-66` -> `AMyGameState::UpdatePlayerRanking`, which activates the
  collapse behind the leader, `MyGameState.cpp:61-102`). Verified. So the lobby has to keep players off the path (3.2).
* **The race world runs from load.** The path spawner builds its initial segments in BeginPlay
  (`MyHexPathSpawner.cpp:71`). The External-mode wave spawner arms itself in BeginPlay (`bStopped = !bAutoStart`,
  `MechSentinelWaveSpawner.cpp:186`) and queues wave 1 from those segments (`:1066-1092`, DelayBefore 4 s). `StopWaves`
  pauses every queued wave's countdown and spawning; `StartWaves` resumes them (`MechSentinelWaveSpawner.h:219-229`,
  `.cpp:359-392`). Burrowers: `UBurrowerSpawnSubsystem::SetSpawningPaused` (`BurrowerSpawnSubsystem.cpp:196`,
  `:415-422`). Path growth: a pawn within ExtendDistance x S = 200 m of the path end (`MyHexPathSpawner.cpp:257-290`).
  Verified.
* **PR B's flow as built.** Host Game: `UMainMenu3::OnCreateSession` -> `ServerTravel(PathToLobby + Options)`
  (`MainMenu3.cpp:1298-1321`; PathToLobby = MenuSetup's LobbyPath + `?listen`, `:30-33`; BP_MM_MainMenu passes
  `/Game/Maps/StartupMap`, memory main-menu3). Play Solo: `OpenLevelLeavingSession(PathToLobby + Options)`
  (`:450-461`), a listen server without a session. `AMyGameMode::StartPlay` (`MyGameMode.cpp:704-768`): practice counts
  down at once; versus goes to WaitingToStart with no pawns (`IsHoldingPawns`, `:646-662`). Countdown, start aboard,
  end, restart: `StartCountdown` `:1021-1081`, `OnCountdownEnd` `:1083-1189`, `BeginRound` `:1191-1213`,
  `SpawnWaitingPlayers` `:1297-1364`, `EndMatch` `:1397-1437`, `RestartMatch` `:1439-1503` (a hard ServerTravel with the
  rules, `Players`, `Match=1`, `Round`). Team memory: `UMyMatchMemorySubsystem` (`MyMatchMemorySubsystem.h`), reset when a
  map loads without `Round` (`MyGameMode.cpp:373-394`). Verified.
* **Travel config.** `GameDefaultMap=/Game/Maps/MM_MainMenu`, `ServerDefaultMap=/Game/Maps/StartupMap`, no
  `TransitionMap` (`Config/DefaultEngine.ini:1-6`; none in BaseEngine.ini either). BP_MyGameMode has no
  `bUseSeamlessTravel` (decoded, SPEC_B B4.6). Online: `DefaultPlatformService=Steam` (`DefaultEngine.ini:112-113`);
  sessions are created with `bUseLobbiesIfAvailable` (`MultiplayerSessionsSubsystem.cpp:184`). The folder is called EOS,
  but the configured service is Steam. The code uses the generic session interface, so both are covered below.
* **`LoadScreen.umap` is not a loading screen.** `Content/Maps/LoadScreen.umap` is an ObjectRedirector to
  `/Game/Maps/Aura/LoadScreen` (decoded strings), the course's save-slot menu map (BP_MainMenuGameMode, WBP_LoadSlot*,
  `AMyLoadScreenHUD`, `MVVM_LoadScreenViewModel`). Nothing uses it as a transition map; no MoviePlayer code (grep).

---

## 2. L1 Flow

```
Main menu --Host Game--> session created --ServerTravel StartupMap?listen?<rules>?Players=n?Lobby=1-->  LOBBY (StartupMap)
   ^                                                                                                    |  host Start
   |                                                                                         lobby countdown 5 s
   |  Leave (pause menu / lobby LEAVE)                                                                   v
   +-------------------------------------------- LOBBY <--hard reload, ?Lobby=1-- END SCREEN <-- MATCH (same world)
Join (code, browse, invite) --ClientTravel to the host--> whatever the host runs: LOBBY, or the MATCH as a late joiner
Play Solo --OpenLevel StartupMap?listen?<rules>?Players=1--> practice countdown --> MATCH (no lobby)
```

### 2.1 Host Game

1. Unchanged up to the session: Create Session panel -> `StartLobbyButtonClicked` -> `CreateSessionWithSettings`
   (`MainMenu3.cpp:436-448`).
2. `OnCreateSession` (`:1298-1321`) travels to `GetHostTravelPath() + BuildMatchOptions(false) + "?Lobby=1"`
   (new: `?Lobby=1` when `UMyMatchSettings::bLobbyWhenHosting`, default true). `GetHostTravelPath()` returns `LobbyMap +
   "?listen"` when `UMyMatchSettings::LobbyMap` is set (later, 2.7), else `PathToLobby` (StartupMap, as today).
3. `AMyGameMode::InitGame` reads `Lobby=1` (4.2). StartPlay goes to phase **Lobby** (4.7) instead of WaitingToStart.

### 2.2 Join

Unchanged on the client: the subsystem joins the session and `ClientTravel`s to the host's address
(`MainMenu3.cpp:1401-1414` -> `MultiplayerSessionsSubsystem.cpp:934-952`). The client loads whatever the host runs.
On the server, `PreLogin` (ban, session full, team cap: `MyGameMode.cpp:189-219`) -> `InitNewPlayer` -> `AssignTeam`
(`:677-702`, `:770-814`), then by phase:

| Host's phase | The joiner |
|---|---|
| Lobby (also while the lobby countdown runs) | gets a team (balance, or last round's team from the memory) and a pawn in the lobby (3.1). Ready = false. During the countdown he is put aboard with everyone at its end. |
| InProgress | late joiner per SPEC_B B1.3 / B9.7: aboard his ship (or past the lead on his side). Practice turning into 1v1 still runs its fresh countdown. |
| Ended | gets a team and a pawn as in InProgress; the reload to the lobby follows within EndScreenSeconds. |

The session stays joinable in the lobby and during the match (join in progress is always on today, 5.5).

### 2.3 Play Solo (recommendation: straight into the match, no lobby)

There is nobody to wait for, and the main menu's host panel already set the rules (`PlaySoloButtonClicked` reads the
widgets, `MainMenu3.cpp:450-461`). Play Solo keeps its URL without `Lobby`, so it starts practice at once (StartPlay ->
StartCountdown). The pause menu's Open Lobby still lets friends in (`PauseMenu3.cpp:566-610`); they join the running
practice, and practice turns into 1v1 as in SPEC_B B1.3. Change from PR B: practice starts **aboard** team 0's ship, not
on the floor (D10, 3.4).

### 2.4 Start

The host presses START in the lobby panel (or the pause menu's START MATCH, or `Aura.Lobby.Start`). A 5 s lobby
countdown runs while everyone is still in the lobby. At 0, the PR B start runs in place: active teams decided, ships
claimed or spawned, every player put aboard his own team's deck, waves resumed, Burrowers unpaused, StartSession. No
travel (4.7).

### 2.5 Match end -> back to the lobby

`EndMatch` (`MyGameMode.cpp:1397-1437`) shows the end screen as built. After `EndScreenSeconds` (20 s) its timer calls
**`ReturnToLobby()`** instead of `RestartMatch()` when this map load had a lobby. `ReturnToLobby()` remembers the teams
and reloads the map with `?Lobby=1` (5.2). The race world is rebuilt (path, platforms, collapse, swarm), and everyone
comes back into the lobby phase with the same teams and rules. It is **not** a restart in place. The host can do it at
once from the pause menu (BACK TO LOBBY, 7.3). `RestartMatch` (no lobby) stays for lobby-off games and
`Aura.Match.Restart`.

### 2.6 Leaving

* A client: pause menu Leave Session (`PauseMenu3.cpp:369-376`, `:887-903`) or the lobby panel's LEAVE (the same confirm)
  -> `LeaveSessionAndOpenLevel(main menu)` (`MultiplayerSessionsSubsystem.cpp:954-970`). On the host, `Logout` recounts
  the teams (4.9).
* The host: the same button kicks every client with "The host closed the lobby." first (`SendClientsHostLeft`,
  `PauseMenu3.cpp:862-885`, `PauseMenu3.h:112`), then leaves. 4.9 covers a host that crashes.

### 2.7 What a separate LobbyMap changes (later, no rework)

With `UMyMatchSettings::LobbyMap` set (for example `/Game/Maps/L_Lobby`):

* Host Game travels to `LobbyMap?listen?<rules>?Players=n?Lobby=1` (2.1 step 2 already does this).
* That map runs the same `AMyGameMode` in phase Lobby (`IsLobbyOnlyLevel()`, 4.2). Its Start runs `TravelToMatch()`
  instead of the in-place start: RememberTeams, then `ServerTravel(MatchMap?listen?<rules>?Players=<players in the
  lobby>?Round=n?FromLobby=1)`.
* On the match map, `FromLobby=1` holds pawns in WaitingToStart until that many players are in, or until
  `LobbyArrivalTimeout` (45 s). Then the countdown and start aboard run as built. WaitingToStart is reused as the
  arrival wait (5.7).
* Match end: `ReturnToLobby()` travels to `LobbyMap` instead of reloading the current map.
* Play Solo and Join are unchanged. Play Solo goes to the match map (PathToLobby).

---

## 3. L2 The lobby area

### 3.1 Where players stand (in-level, the default)

Decided once per map load, in `AMyGameMode::InitGame`. Components are registered before InitGame
(`World.cpp:5988` UpdateWorldComponents, `:6034` InitGame), so traces work there (verified). New
`ResolveLobbySpawn()`, with setting `LobbySpawn` = Auto (default), PlayerStarts or PathStart:

1. **PlayerStarts mode** (Auto when it finds ground). Candidates are the PlayerStarts with `PlayerStartTag == Lobby`
   (none today), else all PlayerStarts. From each one, `LineTraceSingleByChannel` straight down
   `LobbyGroundTraceDepth` (5000 cm) on `ECC_WorldStatic`, ignoring pawns. Each hit gives a **zone box**: the hit
   actor's `GetComponentsBoundingBox(true)` grown in X and Y by `LobbyZoneMargin` (1500 cm), from the box top minus
   `LobbyZoneDepth` (2000 cm) to the box top plus `LobbyZoneHeight` (6000 cm). Every `AMyHexPlatform` **without**
   SplineDistance whose XY bounds overlap a zone box is merged into it. That picks up the platform above the floor
   without naming it (its root at z 1678 is about 17 m above the floor and inside the box, decoded). Today this gives one
   box of about 110 x 110 m around the floor (inferred). Players spawn through the engine path: `ChoosePlayerStart`
   prefers Lobby-tagged, unoccupied starts in the lobby, and PR B's ring search around an occupied start spreads them
   (250 / 500 / 750 cm in 8 directions, `MyGameMode.cpp:2843-2877`). Talal's free ship `BP_AirshipPawn_C_6` lies inside
   the box (decoded position). It is locked in the lobby (3.3).
2. **PathStart mode** (Auto when no PlayerStart has ground under it, which is the case once the floor is deleted). The
   lobby spot is the path platform with the smallest SplineDistance (>= 0) that has tiles, the platform the race starts
   from. The PCG may build it over several frames, so the lobby waits for it: `bLobbyGroundReady` is false, pawns are
   held (4.7), and `LobbyTick` polls every 0.25 s. After 10 s without one, it falls back to the PlayerStart with a
   Warning. Players are placed with `FindRespawnTile` (`MyGameMode.cpp:3263`), facing along the path. The zone box is
   that platform's bounds grown as above. No ranking happens there (3.3), so standing on it starts nothing.
3. Nothing found: the PlayerStart, with a Warning `Lobby: no ground under any PlayerStart and no path platform`.

Logged: `LogMatch Lobby: spawn PlayerStarts, ground Floor (+ BP_MyHexPlatform_C_1), zone <box>`.

Considered and not taken: a lobby on the two team ships' decks (each team on its own deck). It needs both ships
spawned for the whole lobby, a team switch would teleport 450 m, and the ships would have to be locked and kept in their
lanes. The path's first platform is simpler and is already ground in "the real level".

### 3.2 The lobby zone

Server, `LobbyTick` every 0.25 s while the phase is Lobby. For each player state's own pawn that is a living character
(the `UpdateFallDeaths` loop shape, `MyGameMode.cpp:2559-2610`):

* inside any zone box: clear its timer;
* outside: start a timer; after `LobbyZoneGraceSeconds` (0.5 s), send it back. That means `CancelActiveAbilities` (the
  existing helper, `MyGameMode.cpp:249-274`, which ends a grapple's root motion), `StopMovementImmediately`, `TeleportTo`
  a lobby spot (PlayerStarts mode: the chosen start plus `UWorld::FindTeleportSpot`; PathStart: `FindRespawnTile`), then
  `ClientSetRotation` and `ClientLobbyMessage(LobbyZone)`. The toast reads "Stay in the lobby: the match starts when the
  host presses Start". It logs `LogMatch Lobby: <name> back to the lobby (left the zone)`.

This replaces the fall death in the lobby: `MatchTick` skips `UpdateFallDeaths` in phase Lobby (`MyGameMode.cpp:2409`
already skips None and WaitingToStart; add Lobby). Riders standing on the locked free ship inside the box are inside.

Reason: 14 m separate the floor from the first platform, and a landing there starts the collapse (section 1). A
confinement leaves the race code alone, except for the one ranking gate below, which guards against landings inside
the 0.5 s grace.

### 3.3 What runs in the lobby

| System | Lobby | Where |
|---|---|---|
| Abilities (gun, beam, grapple, boost, jump-hover) | on: they are what players play with while waiting | unchanged |
| Damage | **off**: the IncomingDamage branch drops it while the phase is Lobby (`bLobbyDamage` false) | `MyAttributeSet.cpp:74-84`, next to the spawn-protection check at `:81` |
| Knockback (beam LaunchCharacter) | still pushes; the zone brings players back | none |
| Ranking / collapse | **off**: `AMyPlayerState::SetCurrentPlatform` returns at once while the phase is Lobby | `MyPlayerState.cpp:45-67` |
| Path growth | can't happen: the zone is more than 300 m from the path end (u 400 m, Appendix C of SPEC_B) | none |
| Sentinel waves | **stopped**: `StopWaves()` on every spawner after `Super::StartPlay` (the spawner re-arms itself in BeginPlay, `MechSentinelWaveSpawner.cpp:186`); `StartWaves(false)` at the round start | `AMyGameMode::StartPlay`, `BeginRound` |
| Burrowers | **paused**: `SetSpawningPaused(true)`; unpaused at the round start | same |
| Swarm difficulty | applied before Super in StartPlay and on every rules or player-count change, as built | `MyGameMode.cpp:714-716`, `:893-899` |
| Ships | **locked**: `CanBoard` / `CanMount` refuse while `UMyTeamLibrary::AreShipsLocked` (phase Lobby); the prompt says "Ships unlock when the match starts" (new refusal `EAirshipUseRefusal::Locked`). `CanUseShip` stays a pure team test, because the grapple's ship hook uses it (`GA_GrappleSwing2.cpp:1774`, `:2145`) | `AirshipPawn.cpp:1654`, `:2208`; `AirshipPilotComponent.cpp:277`, `:409`; `MyMatchHUDWidget.cpp:270` |
| Team ships | none in the lobby: claimed or spawned at Start (B3.1) | unchanged |
| Fall death | off (the zone replaces it) | `MatchTick` |
| Respawn | a lobby pawn that is destroyed anyway respawns at a lobby spot (`FindRespawnSpot` checks the lobby first) | `MyGameMode.cpp:3124` |
| Match HUD | toasts and name tags only; the lobby widget shows the rest (6) | `MyMatchHUDWidget.cpp:293` (phase switch at `:347`) |
| XP | nothing to earn (no enemies, no damage) | none |

### 3.4 The match without the floor (audit of PR B)

| PR B dependency on the floor / PlayerStart | Fix |
|---|---|
| Practice spawns at the PlayerStart (B4.2; `SpawnWaitingPlayers` puts practice into `Others` -> `RestartPlayer`, `MyGameMode.cpp:1316-1324`). After the floor's removal the pawn would fall. | `bStartAboard` covers practice too: aboard team 0's ship. The test is `Settings->bStartAboard` (was `bVersusRound && bStartAboard`). Practice countdowns hold pawns too (4.7), so nobody stands on the floor for the 5 s. |
| A respawn before anyone has landed goes to the PlayerStart (`FindRespawnSpot` `:3249-3260`: the platform search needs `GetLeadSplineDistance() >= 0`, `:3151`) | Match on: when nobody has landed, the platform search runs with PastDistance = -1, so the path's first platforms are candidates (nearest the path start first, own side first in versus). The PlayerStart stays the last resort. |
| A late joiner's "past the lead" spot needs a landing (`RestartPlayer` `:2811`) | The same: no landing needed in a match. |
| The tie-break's team progress uses `CurrentPlatform` even without SplineDistance (`GetTeamProgress` `:2676-2681`) | Skip platforms without SplineDistance. |
| `SpawnTeamShip`'s last fallback is in front of a PlayerStart (`:1879-1901`) | Kept: it only runs with no lane and no `ShipStart<id>` actor, which means no path (L_AirshipTest), not "no floor". |
| SPEC_B flag 5 (the floor's side) and `bAlternateSides` | Still valid while the floor exists; harmless after. |

**`LobbyOnly` tag (optional, Q-L1):** at the first phase change away from Lobby, every machine hides the actors tagged
`UMyMatchSettings::LobbyOnlyActorTag` (default `LobbyOnly`). It runs in `AMyGameState::OnRep_Match` on clients and after
`SetMatchPhase` on the server, because StaticMeshActors don't replicate. Hiding is `SetActorHiddenInGame(true)` plus
`SetActorEnableCollision(false)`, at runtime only. No actor carries the tag today, so nothing happens unless Talal adds
it in his map. The next lobby reload shows them again.

### 3.5 The separate lobby map (later): contents and cost

Built later by an editor script (`as_81_lobby_map.py`, not in this PR) as `/Game/Maps/L_Lobby`:

| Item | L_Lobby | In-level today |
|---|---|---|
| Floor | `SM_Template_Map_Floor` at scale 4 (40 m), collision on | Talal's Floor (+ the placed platform) |
| Light and sky | DirectionalLight, SkyLight, SkyAtmosphere (or a BP_Sky_Sphere copy), ExponentialHeightFog, an unbound PostProcessVolume with the game's look | StartupMap's own |
| PlayerStarts | 8, tag `Lobby`, a ring of radius 6 m | PlayerStart_0 + ring search |
| Team pads | two `AMyLobbyTeamPad` actors (a 6 x 6 m box trigger, a team-coloured plane, a TextRender) at y +-15 m; entering one calls `RequestLobbyTeam` | the SWITCH TEAM button |
| Ships on display | two static `SM_Airship` meshes (no pawns, no Niagara, no physics) at x +-40 m | none |
| Rules / start terminal | none: the lobby panel (Esc) | the same |
| World settings | GameMode override `BP_MyGameMode`; no PCG world actor, no path spawner, no wave spawner | n/a |
| Burrower | paused by the lobby phase (if `UBurrowerSettings::AllowedMaps` is empty it would run anywhere, `BurrowerSpawnSubsystem.cpp:90-104`) | paused |
| Cost | one floor, a few lights, two static meshes: well under the match map (inferred) | the full StartupMap at load, minus the swarm |

---

## 4. L3 Game mode, game state, player state

### 4.1 A phase of AMyGameMode (not AMyLobbyGameMode)

Reasons:

1. The in-level lobby shares the match's world, and a world has one game mode (`UWorld::SetGameMode`). A separate class
   would need a map change.
2. Everything the lobby needs is already in AMyGameMode: team assignment and counts (`AssignTeam`, `RecountTeams`),
   rules parsing (`ParseRulesOptions`), PreLogin caps, team memory, swarm difficulty, the travel URL (`BuildRulesOptions`).
3. The separate lobby map later uses the same class with `IsLobbyOnlyLevel()`. Its race code idles because the map has no
   path, lanes or spawners. A thin BP child (`BP_MyLobbyGameMode`) can still give that map another pawn or HUD without
   C++.

To keep `MyGameMode.cpp` (3370 lines) readable, the lobby methods go in a new file `Source/Aura/Private/MyGameModeLobby.cpp`
(the same class, declared in `MyGameMode.h`).

`EMyMatchPhase` gains **`Lobby`, appended at the end** (`MyMatchTypes.h:30-40`), so existing values don't change.
Nothing compares phases by order (grep: no `<` / `>` on EMyMatchPhase in Source). `UMyTeamLibrary::IsMatchActive`
(`MyTeamLibrary.cpp:35-39`: phase != None) is true in the lobby, which is wanted: teams, rules, the on-foot path rule and
name tags all apply.

### 4.2 Deciding the lobby (InitGame)

After `ParseMatchOptions` (`MyGameMode.cpp:439`), only when the match is on:

```cpp
// SPEC_B_LOBBY 4.2. Later wins: a separate lobby level is always a lobby, else the URL's Lobby=0|1, else the CVar
bLobbyOn = false;
if (IsLobbyOnlyLevel())                                   // UMyMatchSettings::LobbyMap names this map (later)
    bLobbyOn = true;
else if (UGameplayStatics::HasOption(Options, TEXT("Lobby")))
    ParseBool(UGameplayStatics::ParseOption(Options, TEXT("Lobby")), bLobbyOn);   // bad value: Warning, off
else if (CVar Aura.Lobby.Enable >= 0)                     // -1 (default) = by URL only
    bLobbyOn = CVar > 0;
bArrivalWait = !bLobbyOn && UGameplayStatics::HasOption(Options, TEXT("FromLobby"));   // later: 5.7
if (bLobbyOn) ResolveLobbySpawn();                        // 3.1
```

`IsLobbyOnlyLevel()` compares the short map name (no PIE prefix) with `LobbyMap`'s; an empty `LobbyMap` is false. Being
the lobby level also turns the match on (the `MatchMaps` check, `MyGameMode.cpp:396-431`, treats `LobbyMap` as listed).
`InitGameState` writes `bLobbyRound = bLobbyOn || bArrivalWait` into the game state (it decides the end-screen text and
the pause menu label). `ExpectedPlayers` keeps the URL's `Players`, and in the lobby it means **Max Players** ("3/4").
Logged: `Match on on StartupMap (...): ..., lobby on (URL Lobby=1), spawn PlayerStarts`.

### 4.3 Replicated state

Game state (`MyGameState.h`, every field `ReplicatedUsing = OnRep_Match`, written by the server through new
setters that call `NotifyMatchWritten`):

```cpp
UPROPERTY(ReplicatedUsing = OnRep_Match) bool bLobbyRound = false;          // this map load returns to a lobby
UPROPERTY(ReplicatedUsing = OnRep_Match) EMyLobbyStartBlock LobbyStartBlock = EMyLobbyStartBlock::None;
UPROPERTY(ReplicatedUsing = OnRep_Match) uint8 LobbyNotReady = 0;            // players (not the host) not ready
// Reused: MatchPhase (Lobby), MatchRules, Teams[].NumPlayers, ExpectedPlayers (= Max Players in the lobby),
// PhaseEndServerTime (> 0 in phase Lobby = the lobby countdown's end), RoundIndex
bool IsLobbyCountingDown() const { return MatchPhase == EMyMatchPhase::Lobby && PhaseEndServerTime > 0.0; }
```

Player state (`MyPlayerState.h`; the class already replicates TeamId, `MyPlayerState.cpp:19-26`):

```cpp
UPROPERTY(ReplicatedUsing = OnRep_Lobby) bool bLobbyReady = false;
UPROPERTY(ReplicatedUsing = OnRep_Lobby) uint8 RequestedTeam = MyMatch::NoTeam;   // a pending switch (4.4)
UPROPERTY(ReplicatedUsing = OnRep_Lobby) bool bIsHost = false;                     // set in PostLogin for the server's local player
FSimpleMulticastDelegate OnLobbyChanged;                                            // every machine
void SetLobbyReady(bool); void SetRequestedTeam(uint8); void SetIsHost(bool);       // server, ForceNetUpdate
virtual void CopyProperties(APlayerState* PlayerState) override;                    // TeamId only (5.3)
```

`EMyLobbyStartBlock` (`MyMatchTypes.h`): `None, NeedOpponent, NotReady, Uneven, NeedTwoPerTeam, Counting, Traveling`.
`EMyMatchEvent` gains, appended: `LobbyCountdown, LobbyCancelled, LobbyTeamChanged, LobbyRulesChanged, LobbyReturn`.

### 4.4 Teams in the lobby

* **On join:** `AssignTeam` as built: the remembered team if it fits, else the smaller team, a tie goes to team 0
  (`MyGameMode.cpp:770-814`). Practice: everyone on team 0.
* **Switching** (`RequestLobbyTeam(Player, Target)`, a request from the player, `bLobbyTeamSwitch` default true):

```cpp
if (!IsInLobby() || IsLobbyCountingDown())      refuse: "Teams are locked while the match starts"
if (MatchRules.TeamMode == EMyTeamMode::Practice) refuse: "Practice: everyone is on one ship"
const uint8 From = Player->GetTeamId();
if (Target == From || Target >= MyMatch::NumTeams) { Player->SetRequestedTeam(MyMatch::NoTeam); return; }   // cancel
RecountTeams(); const int32 A = Count[From], B = Count[Target], Cap = GetTeamCap();   // Cap 0 = none
if ((Cap == 0 || B < Cap) && B < A)  { MoveLobbyTeam(Player, Target); return; }      // teams stay within one
for (AMyPlayerState* Other : players on Target with Other->GetRequestedTeam() == From)    // oldest request first
    { MoveLobbyTeam(Other, From); MoveLobbyTeam(Player, Target); return; }               // a swap
Player->SetRequestedTeam(Target);   // pending: "You swap when an ORANGE player asks for BLUE"
```

  `MoveLobbyTeam` sets TeamId, clears RequestedTeam, recounts, keeps the ready flag and sends `LobbyTeamChanged`.
  Examples: 3 players {2, 1}: one of the two moves to the other team at once ({1, 2}). 4 players {2, 2} or a 1v1 {1, 1}:
  a switch waits for a partner, then both swap.
* **Host move** (`MoveLobbyPlayer`, host only): allowed while the target team is under its cap, with no balance rule. The
  host may build a 3v1 on purpose; Start then warns (Uneven, soft).
* **Rules change of the team mode** in the lobby: `RebalanceLobbyTeams()` resets every TeamId to 255 and runs `AssignTeam`
  for each player in `PlayerArray` order (join order; AGameStateBase appends there), so the memory and join order apply
  again.
* **Leave:** the counts drop (4.9). Requests aimed at the leaver are simply never answered.

### 4.5 Ready

A ready button per player (`SetLobbyReady`). The host has no flag: he is ready when he starts. Every rules change
clears all flags (`bLobbyRulesClearReady`, default true): "Rules changed: press READY again". A team move keeps them.
`LobbyNotReady` on the game state is the count shown on the Start button. Reason for showing but not requiring them:
friends in a voice call don't need a checkbox, but the host should see who isn't ready (Far Far West's host starts when
he wants). `bLobbyRequireReady` makes NotReady a hard block.

### 4.6 Rules in the lobby (host only)

`ApplyLobbyRules(const FMyMatchRules& NewRules, int32 MaxPlayers, FText& OutWhy)`:

1. Refused outside phase Lobby or while counting down.
2. N = players in. `ModeMax` = 2 for 1v1, 4 for 2v2, 0 otherwise (the same numbers as `UMainMenu3::GetTeamModeMaxPlayers`,
   used through a shared static in `MyTeamLibrary`). Refused if `ModeMax > 0 && N > ModeMax` ("1v1 has room for 2: 3
   players are in") or `MaxPlayers < N`. With `ModeMax > 0`, MaxPlayers = ModeMax.
3. The team mode applies **at once in the lobby**: `ApplyRules` defers it to the next restart whenever the phase isn't
   None (`MyGameMode.cpp:1551-1556`); add `&& Phase != Lobby` there. Then `RebalanceLobbyTeams()` if the mode changed.
4. `ExpectedPlayers = MaxPlayers` on the game mode and the game state.
5. Ready flags cleared (4.5). Event `LobbyRulesChanged`.
6. The session's advertised values follow (when hosting a session): new
   `UMultiplayerSessionsSubsystem::AdvertiseMatchRules(EMyTeamMode, int32 Difficulty, int32 MaxPlayers)` reads
   `GetCurrentHostSettings` (`MultiplayerSessionsSubsystem.cpp:888`), sets `Rules = UMainMenu3::GetRuleSetForTeamMode`,
   `Difficulty`, `NumPublicConnections`, and calls `UpdateHostSettings` (`:819-851`). This is what the pause menu's Open
   Lobby does when advertising a running match (`PauseMenu3.cpp:574-587`), and what Browse Sessions filters on.

Everything else in `FMyMatchRules` (lives, swarm, time limit, friendly fire, grapple, assist) goes through the existing
`ApplyRules` unchanged.

### 4.7 Start

**StartPlay with the lobby** (in `AMyGameMode::StartPlay`, `MyGameMode.cpp:704-768`, before its practice / versus split):

```cpp
if (bLobbyOn)
{
    // ApplySwarmDifficulty before Super ran above, as built
    StopSwarm();                                            // after Super: the spawners armed themselves in BeginPlay
    MyGameState->SetMatchPhase(EMyMatchPhase::Lobby, 0.0);
    GetWorldTimerManager().SetTimer(LobbyTickTimer, this, &ThisClass::LobbyTick, 0.25f, true);
    SpawnLobbyPlayers();                                    // every controller without a pawn (the host logged in held)
    EvaluateTeams();
    return;
}
```

`IsHoldingPawns` (`MyGameMode.cpp:646-662`) becomes:

```cpp
case EMyMatchPhase::None:      return bLobbyOn || !IsPracticeStart() || Settings->bStartAboard;   // StartPlay places them
case EMyMatchPhase::Lobby:     return !bLobbyGroundReady;                                          // PathStart, before the platform
case EMyMatchPhase::WaitingToStart: return true;
case EMyMatchPhase::Countdown: return bCountdownVersus || bPracticeToVersus || Settings->bStartAboard;
default: return false;
```

(The host logs in before StartPlay, as the comment at `:656` says, so in phase None he is held and `SpawnLobbyPlayers`
gives him his lobby pawn. With practice and `bStartAboard`, nobody gets a pawn during the practice countdown: the camera
waits at the start spot for 5 s, as in a versus countdown.)

`RestartPlayer` (`:2785`) in phase Lobby: PathStart mode places the pawn at the lobby spot; PlayerStarts mode uses
`Super` plus the ring search. `ChoosePlayerStart` (`:2732-2783`) prefers `Lobby`-tagged starts in the lobby and skips
them in the match.

**Start blocks** (`GetLobbyStartBlock(int32& OutNotReady)`, written to the game state in `LobbyTick` when they change):

| Block | When | Kind |
|---|---|---|
| Counting / Traveling | the lobby countdown runs / a travel is pending | hard |
| NeedOpponent | 1v1 or 2v2 with a team at 0 players | hard |
| NotReady | some player (not the host) isn't ready | soft (hard with `bLobbyRequireReady`) |
| NeedTwoPerTeam | 2v2 with a team at 1 (plays 2v1 or 1v1) | soft |
| Uneven | the teams differ by more than one (host moves) | soft |

Auto and Practice have no hard block. Auto with one player starts practice; with 2 or more, versus by the teams shown.

**`StartFromLobby(bool bForce, FText& OutWhy)`** (host): a hard block refuses, and so does a soft one without bForce.
Otherwise it sets `SetMatchPhase(Lobby, Now + LobbyCountdownSeconds)` (5 s), sends event
`LobbyCountdown(Value = seconds)` and sets a timer for `OnLobbyCountdownEnd`. `CancelLobbyStart(Reason)` (host, or
automatic) clears the timer, sets the phase back to Lobby with 0 and sends `LobbyCancelled`.

**`OnLobbyCountdownEnd()`:**

```cpp
RecountTeams();
if (IsHardBlock(GetLobbyStartBlock(NotReady)))  { CancelLobbyStart(TEXT("a team emptied")); return; }
if (IsLobbyOnlyLevel())                         { TravelToMatch(); return; }      // later, 2.7
bFreshStart = true;
StartCountdown(/*bForced*/true, /*DelayOverride*/0.f);   // active teams, lane sides, handicap, ships (B3.1); no Countdown event at 0 s
// StartCountdown with 0 s schedules OnCountdownEnd for the next tick (MyGameMode.cpp:1077-1080)
```

`StartCountdown` gains the `DelayOverride` parameter (default -1 = `MatchStartDelay`), and sends no `Countdown` event
when the delay is 0. **`BeginRound`** (`:1191-1213`) gains, before `SpawnWaitingPlayers`:

```cpp
if (!bPracticeToVersusRound)  TakeBackPawnsForStart();   // every pawn that isn't a character riding its own team's ship
ResumeSwarm();                                           // StartWaves(false) on every wave spawner, Burrower unpaused
StartSessionIfHost();                                    // 5.5
```

`TakeBackPawnsForStart` is the StartPlay take-back code (`:752-765`: CancelActiveAbilities, UnwatchPlayerPawn,
UnPossess, Destroy) moved into a helper `TakeBackPawn(APlayerController*)`. It keeps a pawn for which
`UAirshipSubsystem::FindShipCarrying(Pawn)` is the player's own team ship. Then `SpawnWaitingPlayers` puts everyone
aboard (versus, and now practice). The new pawn refills Health and Mana (`InitAbilitySystemAfterRespawn` applies
`VitalAttributesEffect`, `MyCharPlayer.cpp:420-437`), so nothing spent in the lobby carries into the match. Practice
turning into versus (B1.3) doesn't take pawns back, as built.

### 4.8 RPCs and authority

On `AMyPlayerController2` (match owner; all Server, Reliable, validated on the server):

```cpp
UFUNCTION(Server, Reliable) void ServerLobbySetReady(bool bReady);
UFUNCTION(Server, Reliable) void ServerLobbyRequestTeam(uint8 TeamId);                 // 255 = cancel a request
UFUNCTION(Server, Reliable) void ServerLobbySetRules(const FMyMatchRules& Rules, int32 MaxPlayers);   // host
UFUNCTION(Server, Reliable) void ServerLobbyStart(bool bForce);                        // host
UFUNCTION(Server, Reliable) void ServerLobbyCancelStart();                             // host
UFUNCTION(Server, Reliable) void ServerLobbyMovePlayer(APlayerState* Player, uint8 TeamId);   // host
UFUNCTION(Client, Unreliable) void ClientLobbyMessage(const FText& Text);               // refusals, zone, swaps
```

The host check is `AMyGameMode::IsLobbyHost(const APlayerController* PC)`: `PC->IsLocalController() && GetNetMode() !=
NM_Client`, the condition PostLogin uses for the host (`MyGameMode.cpp:225-226`). On a listen server the host's Server
RPCs run locally, so the host's widget takes the same path as everyone else's. That keeps one route, and validation
can't be skipped. A refused request answers with `ClientLobbyMessage(OutWhy)`. The pause menu's direct calls on the game
mode (`PauseMenu3.cpp:431-443`, `:495-503`) stay as they are: they run on the host only.

### 4.9 Leaving, and the host leaving

* **A client leaves the lobby:** `Logout` -> `EvaluateTeams(Leaving)` (`MyGameMode.cpp:293-320`, `:876-967`). The phase
  Lobby branch recounts, refreshes the start block and, if the countdown runs and the block turns hard, cancels it at
  once ("ORANGE left: start cancelled").
* **The host leaves on purpose:** clients are kicked with the host-left reason, then the host goes to the main menu
  (2.6). Each client's `ClientWasKicked` keeps the reason for the menu (`MyPlayerController2.h:224`).
* **The host crashes or loses connection:** each client's net driver fails. The subsystem destroys the session and keeps
  "Lost connection to the host." for the menu (`MultiplayerSessionsSubsystem.cpp:1189-1252`). The engine sends the client
  to the default map with `?closed` (`UnrealEngine.cpp:15512`, `:15527`), which is MM_MainMenu (`DefaultEngine.ini:2`).
  Verified. No host migration (SPEC_B 0.2).
* The team memory is host-only (`UMyMatchMemorySubsystem`), so it disappears with the host. Nothing to clean up.

---

## 5. L4 Travel and the session

### 5.1 Travel in this project (verified)

* `RestartMatch` uses a hard ServerTravel on a listen server and `OpenLevel` in standalone (`MyGameMode.cpp:1489-1502`).
* Hard, because BP_MyGameMode has no `bUseSeamlessTravel` (decoded). `ProcessServerTravel` uses seamless only when that
  flag or `?SeamlessTravel` is set (`GameModeBase.cpp:476-498`), and never in PIE unless `net.AllowPIESeamlessTravel=1`
  (`:504-511`).
* No TransitionMap is set (`DefaultEngine.ini:1-6`). Seamless travel would then build an empty transition world
  (`World.cpp:8330`, `:8367-8370`), so a TransitionMap is optional.
* Seamless travel would keep the PlayerStates through the transition (`GameModeBase.cpp:539-559`) and copy them through
  `SeamlessTravelFrom` -> `APlayerState::SeamlessTravelTo` -> `DispatchCopyProperties` -> `CopyProperties`
  (`PlayerController.cpp:3652-3658`, `PlayerState.cpp:101-104`, `:116`, `:413-418`; swap in `GameModeBase.cpp:618-619`).
* The session survives a ServerTravel; the menu's own hosting path is one (`MainMenu3.cpp:1314`).

### 5.2 In-level: one travel per round

With the in-level lobby there is **no travel at Start**. The only travel is the return after the match. New
**`ReturnToLobby()`** is `RestartMatch`'s code with these changes:

```cpp
// Options = BuildRulesOptions(MatchRules, NextTeamMode)            (MyGameMode.cpp:607-612)
//         + "?Players=<ExpectedPlayers = Max Players>?Match=1?Round=<n>?Lobby=1"
// Map     = UMyMatchSettings::LobbyMap if set (2.7), else this map (UWorld::RemovePIEPrefix of the package name)
// Round   = +1 after a versus round (the lane sides swap), unchanged after practice, as RestartMatch decides (:1453-1468)
// Teams   = Memory->RememberTeams(GameState) first, as RestartMatch does (:1458-1468)
// Event LobbyReturn to everyone before the travel (end panel: "Back to the lobby...")
```

`EndMatch`'s timer (`:1428-1431`) calls `bLobbyRound ? ReturnToLobby : RestartMatch`. On the reload, InitGame sees
`Round` (keeps the memory, `:378-390`) and `Lobby=1` (4.2). Clients reconnect, `AssignTeam` gives each his remembered
team (by net id; PIE with the NULL subsystem may have no valid ids: join order, SPEC_B B1.6), and everyone is back in the
lobby. Ready flags start false: the player states are new.

### 5.3 Seamless travel: not now (prepared)

The in-level design has one travel per round, after the match, and that travel rebuilds the race world anyway. Hard
travel is enough. The memory subsystem already carries the teams and the URL carries the rules. Prepared for a later
switch: `AMyPlayerState::CopyProperties` copies `TeamId` (not the ready flag), so turning on `bUseSeamlessTravel` on
BP_MyGameMode for the separate lobby map works without other changes. AGameModeBase has no inactive player states, so
CopyProperties has no other caller in this project (grep: no `AddInactivePlayer`; that is AGameMode only).

### 5.4 How the rules and teams reach the match

* In-level: the lobby edits the live game mode (4.6), so nothing has to travel. The return URL writes every rule back
  (5.2).
* Separate lobby map (later): `TravelToMatch` writes the same options plus `FromLobby=1`, and the match map's InitGame
  parses them exactly as today (`MyGameMode.cpp:445-500`). Teams go through `RememberTeams` before the travel.

### 5.5 The session (Steam lobby or EOS session)

* **When StartSession runs.** Today the host's PostLogin calls `StartSession` (`MyGameMode.cpp:221-239`), so the session
  is InProgress the moment the host arrives. With the lobby: PostLogin skips it when `bLobbyOn`, `BeginRound` calls it
  for the host (`StartSessionIfHost`), and `EndMatch` calls a new `UMultiplayerSessionsSubsystem::EndSession()`
  (`SessionInterface->EndSession(NAME_GameSession)` when InProgress, with a delegate and a log). So the session is
  Pending or Ended in the lobby and InProgress only during a match. Steam starts only from Pending or Ended and ends only
  from InProgress (`OnlineSessionInterfaceSteam.cpp:398-433`, `:497-510`), so the next round's StartSession works. PR B's
  "already InProgress" guard (`MultiplayerSessionsSubsystem.cpp:398-404`) stays as a safety.
* **Joinability.** Join in progress is always on today (`FAuraHostSettings::bAllowJoinInProgress` true,
  `MultiplayerSessionTypes.h:70-72`; no UI sets it, grep). So the lobby and the match are both joinable on Steam lobbies,
  which are joinable when join in progress is on and there is room (`OnlineSessionAsyncLobbySteam.cpp:447`, `:657`).
  Recorded for any future "no join in progress" option: on Steam lobbies the flag blocks joins at all times, and on EOS
  it blocks joins once the session has started (`OnlineSessionEOS.cpp:1380-1387`). So such an option must keep the flag
  on in the lobby and change it with UpdateSession at Start, not rely on StartSession.
* **Advertised rules** follow the lobby's rules (4.6 step 6).
* **The pause menu's Open Lobby** (a session opened from a running Play Solo game) calls StartSession at once
  (`PauseMenu3.cpp:934-948`). Kept: that game is already a running match.

### 5.6 Loading screen

`LoadScreen.umap` is not one (section 1), and the project has no travel loading screen. The return to the lobby is a hard
travel: clients see the last frame, then the lobby. Recommendation: none for the in-level lobby, since the end panel
already says "Back to the lobby in n s". With the separate lobby map (two travels per round), add a small game-instance
subsystem that shows a full-screen "LOADING" widget on `FCoreUObjectDelegates::PreLoadMap` and removes it on
`PostLoadMapWithWorld`. Not in this PR.

### 5.7 Separate LobbyMap: two travels, arrival wait (later)

Start in L_Lobby -> `TravelToMatch()` -> the match map with `FromLobby=1?Players=<n>`. There `bArrivalWait` keeps PR B's
WaitingToStart (no pawns) until `NumPlayers >= Players` or `LobbyArrivalTimeout` (45 s, a timer started in StartPlay).
Then `StartCountdown(true)`. The PR B start-aboard flow follows. The match end returns to L_Lobby (5.2). Each travel is
hard; seamless travel would save the reconnects then (5.3).

---

## 6. L5 Lobby UI

### 6.1 Where and when

* `AMyHUD` gets `LobbyWidgetClass` (`TSubclassOf<UMyLobbyWidget>`, EditAnywhere). It is set on BP_MyHUD by as_78, the way
  `PauseMenuClass` was set on BP_MyPlayerController2 (memory main-menu3). It is added in `BeginPlay` and `InitOverlay`
  like the match widget (`MyHUD.cpp:25-29`, `:43-73`), ZOrder 5, for every local player while the match is on. The widget
  collapses itself outside phase Lobby.
* **Esc in the lobby** opens the lobby panel instead of the pause menu: `AMyPlayerController2::TogglePauseMenu`
  (`MyPlayerController2.cpp:404-417`) asks the HUD's lobby widget first when the phase is Lobby and the pause menu isn't
  open. No new input asset (IA_Pause is Escape and Gamepad Special Right, memory main-menu3). The panel's MENU button
  closes it and opens the pause menu (new `AMyPlayerController2::OpenPauseMenu()`).
* The panel opens by itself the first time the local player's lobby pawn exists (each map load). PLAY closes it.
* Panel open: `FInputModeUIOnly` with the cursor, as `UPauseMenu3::OpenMenu` does (`PauseMenu3.cpp:175-212`). Closed:
  game only, cursor hidden, and only the compact strip shows.

### 6.2 Layout (Menu3 yellow-and-black: F_Anton titles, F_Bebas / F_Barlow text, WBP_OptionRow rows)

```
+------------------------------------------------------------------------------------------+
| LOBBY  Talal's lobby                                          CODE  K7Q2PX   [COPY]       |
|------------------------------------------------------------------------------------------|
|  BLUE  2 / 2                                  |  ORANGE  1 / 2                            |
|  * Talal            HOST            32 ms     |    Friend2          NOT READY      58 ms   |
|    Friend1          READY           41 ms     |                                           |
|  [ SWITCH TO ORANGE ]                         |                                           |
|------------------------------------------------------------------------------------------|
|  RULES                                                    (clients: greyed, "set by host") |
|  TEAMS [Auto teams v]   SHIP LIVES [3 v]   SWARM [Normal v]                              |
|  MAX PLAYERS [4 v]      TIME LIMIT [15 min v]   [x] FRIENDLY FIRE  [x] SHIP HOOK  [x] LANE ASSIST |
|------------------------------------------------------------------------------------------|
|  [ READY ]   [ PLAY ]   [ MENU ]   [ LEAVE ]                  [ START (1 NOT READY) ]      |
|                                                     Click again to start anyway          |
+------------------------------------------------------------------------------------------+
Compact strip (panel closed), top centre:  LOBBY   BLUE 2 - ORANGE 1   1 NOT READY   Esc: lobby
Countdown (both views, large, centre):      MATCH STARTS IN 4
```

### 6.3 C++ classes and BindWidget names

New `Source/Aura/Public/Match/MyLobbyWidget.h` (+ `.cpp`), derived from `UMyUserWidget` like UMainMenu3. Every widget
is `BindWidgetOptional`, so a missing one is simply not used:

```cpp
UCLASS() class AURA_API UMyLobbyWidget : public UMyUserWidget
{
    GENERATED_BODY()
public:
    void OpenPanel(); void ClosePanel(); bool IsPanelOpen() const;
protected:
    virtual void NativeConstruct() override; virtual void NativeDestruct() override;
    virtual void NativeTick(const FGeometry& Geometry, float DeltaTime) override;
    virtual FReply NativeOnKeyDown(const FGeometry& Geometry, const FKeyEvent& KeyEvent) override;   // Esc / B close
    // Views
    UPROPERTY(meta = (BindWidgetOptional)) UWidget* LobbyPanel;
    UPROPERTY(meta = (BindWidgetOptional)) UWidget* CompactPanel;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* CompactText;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* CountdownText;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* MessageText;          // ClientLobbyMessage, 3 s
    // Header
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* TitleText;            // lobby name (session) or "LOBBY"
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* JoinCodeText;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* CopyCodeButton;
    // Teams
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* BlueHeaderText;       // "BLUE  2 / 2"
    UPROPERTY(meta = (BindWidgetOptional)) UPanelWidget* BlueList;           // rows of PlayerRowClass
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* OrangeHeaderText;
    UPROPERTY(meta = (BindWidgetOptional)) UPanelWidget* OrangeList;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* SwitchTeamButton;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* SwitchTeamText;       // SWITCH TO ORANGE / CANCEL SWITCH
    // Rules (host edits; clients see them disabled)
    UPROPERTY(meta = (BindWidgetOptional)) UWidget* RulesPanel;
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* TeamModeComboBox;     // RuleSets
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* ShipLivesComboBox;    // ShipLivesChoices
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* SwarmComboBox;        // DifficultyNames
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* MaxPlayersComboBox;   // MaxPlayerChoices
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* TimeLimitComboBox;    // TimeLimitChoices
    UPROPERTY(meta = (BindWidgetOptional)) UCheckBox* FriendlyFireCheckBox;
    UPROPERTY(meta = (BindWidgetOptional)) UCheckBox* GrappleShipsCheckBox;
    UPROPERTY(meta = (BindWidgetOptional)) UCheckBox* LaneAssistCheckBox;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* RulesHintText;        // "Set by the host" / a refusal
    // Actions
    UPROPERTY(meta = (BindWidgetOptional)) UButton* ReadyButton;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* ReadyText;            // READY / NOT READY
    UPROPERTY(meta = (BindWidgetOptional)) UButton* StartButton;             // host only (hidden on clients)
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* StartText;            // START / START (n NOT READY) / CANCEL
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* StartReasonText;      // why it is disabled, or the confirm hint
    UPROPERTY(meta = (BindWidgetOptional)) UButton* PlayButton;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* MenuButton;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* LeaveButton;
    UPROPERTY(EditAnywhere, Category = "Lobby") TSubclassOf<UMyLobbyPlayerRow> PlayerRowClass;
    UPROPERTY(EditAnywhere, Category = "Lobby") TArray<int32> TimeLimitChoices = { 0, 5, 10, 15, 20, 30 };   // 0 = none
    UPROPERTY(EditAnywhere, Category = "Lobby") float RefreshInterval = 0.25f;
    UPROPERTY(EditAnywhere, Category = "Lobby") float StartConfirmSeconds = 3.f;
};

UCLASS() class AURA_API UMyLobbyPlayerRow : public UMyUserWidget     // Match/MyLobbyPlayerRow.h
{
    GENERATED_BODY()
public:
    void Setup(UMyLobbyWidget* Owner, AMyPlayerState* Player, bool bIsLocal, bool bHostView);
protected:
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* PlayerNameText;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* StatusText;    // HOST / READY / NOT READY / WANTS ORANGE
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* PingText;      // APlayerState::GetPingInMilliseconds
    UPROPERTY(meta = (BindWidgetOptional)) UWidget* LocalHighlight;   // the "*" / outline on the own row
    UPROPERTY(meta = (BindWidgetOptional)) UButton* MoveButton;       // host view only: move to the other team
};
```

**The option lists come from MainMenu3,** so the host menu and the lobby can't drift apart. They are protected
UPROPERTYs on UMainMenu3 (`MainMenu3.h:115-136`). New public statics: `UMainMenu3::GetDefaultRuleSets()`,
`GetDefaultDifficultyNames()`, `GetDefaultMaxPlayerChoices()`, `GetDefaultShipLivesChoices()` return the C++ CDO's arrays,
as `GetRuleSetForTeamMode` already reads `GetDefault<UMainMenu3>()->RuleSets` (`MainMenu3.cpp:544-554`). The team-mode
mapping uses `GetTeamModeForRuleSet` / `GetRuleSetForTeamMode`. The combos are filled the way `FillStaticOptions` does
(`MainMenu3.cpp:1168-1227`). as_78 warns if WBP_MainMenu3's CDO overrides one of those lists (it doesn't for RuleSets,
SPEC_B B5.2).

### 6.4 Behaviour

* **Refresh:** every `RefreshInterval`, and at once on `AMyGameState::OnMatchChanged`, the widget rebuilds the two lists
  from `PlayerArray` (8 rows at most; no per-player-state delegates to track joins and leaves). It sets every control from
  the replicated `MatchRules`, `ExpectedPlayers`, `LobbyStartBlock`, `LobbyNotReady` and `PhaseEndServerTime` with
  `ESelectInfo::Direct`, and ignores `Direct` in its own change handlers, so a refresh never sends a request.
* **Host edits:** any rules control changes -> read all controls into an `FMyMatchRules` plus MaxPlayers ->
  `ServerLobbySetRules`. A refusal comes back as `ClientLobbyMessage`, and the next refresh resets the controls to the
  real rules. Picking 1v1 or 2v2 sets and disables Max Players, as in the host menu (`MainMenu3.cpp:468-500`).
* **Clients:** RulesPanel visible, every control disabled, `RulesHintText` "Set by the host".
* **Start button** (host): None -> START. Soft block -> "START (2 NOT READY)", "START 2v1" or "START (TEAMS UNEVEN)". The
  first click sets `StartReasonText` to "Click again to start anyway" for `StartConfirmSeconds`, and a second click in that
  time sends `ServerLobbyStart(true)`. Hard block -> disabled, with the reason ("1v1 needs a player on ORANGE"). While
  counting down -> CANCEL (`ServerLobbyCancelStart`). Clients don't see the button; `StartReasonText` shows "Waiting for
  the host to start" or the block's reason.
* **Countdown:** `CountdownText` "MATCH STARTS IN n" from `PhaseEndServerTime - GameState->GetServerWorldTimeSeconds()`.
  SWITCH TEAM and the rules are disabled while it runs.
* **Code:** host `GetCurrentJoinCode` (`MultiplayerSessionsSubsystem.cpp:445`), client `GetCurrentSessionInfo` (as the
  pause menu's Copy Code does, `PauseMenu3.cpp:515`). Hidden without a session.
* **LEAVE:** opens the pause menu's Leave Session confirm (new public `UPauseMenu3::RequestLeaveSession()`, which calls
  the existing `LeaveSessionButtonClicked`, `PauseMenu3.cpp:369-376`), so the host-left kick stays in one place.

### 6.5 Built by script (as_77)

`as_77_lobby_widget.py` creates `/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_Lobby3` (parent `UMyLobbyWidget`) and
`WBP_LobbyPlayerRow3` (parent `UMyLobbyPlayerRow`) with UMGToolSet (`unreal.ToolsetRegistry.execute_tool(
'UMGToolSet.UMGToolSet', ...)` from the inbox, synchronous, the MainMenu3 builder's method and as_72's helpers). Style is
copied, not invented:

* the rules rows are `WBP_OptionRow` (named slots Label / Control) with the label and combo styles of WBP_MainMenu3's
  `Txt_HostRules` / `Ctl_HostRules` / `Box_HostRulesComboBox` (as as_72 does);
* the buttons copy WBP_PauseMenu3's Resume row (as `UPauseMenu3`'s runtime `CloneButtonRow` does);
* the player row copies `WBP_SessionPlayerRow3`'s text styles;
* fonts F_Anton / F_Bebas / F_Barlow from `Menu3/Fonts`.

The script is idempotent (it reports and stops when the widgets exist; `AS77_REBUILD` rebuilds them), never runs during
PIE, saves only these two new assets by path, and writes `Saved/Match/as_77_lobby_widget.json`. Talal's tree has no local
change in `Menu3/` or to BP_MyHUD (git status), so nothing clashes on merge.

### 6.6 Without the WBP

If `LobbyWidgetClass` is unset or fails to load: a Warning, Esc opens the pause menu as today, the match HUD draws a
one-line lobby strip ("LOBBY  BLUE 2 - ORANGE 1 - host: Esc > Start match"; NativePaint, `MyMatchHUDWidget.cpp:347`
switch), and the pause menu's START MATCH row shows in phase Lobby (7.3). Tests and a packaged host can still start.

---

## 7. L6 Changes to what PR B built

### 7.1 Game mode, state, player state, controller, HUD (match owner)

| Where | Change |
|---|---|
| `MyGameMode.cpp` InitGame `:366-443` | lobby decision, `ResolveLobbySpawn` (4.2, 3.1) |
| `InitGameState` `:664-675` | `bLobbyRound` |
| `PostLogin` `:221-241` | skip StartSession with the lobby; `SetIsHost(true)` for the server's local player |
| `StartPlay` `:704-768` | the lobby branch (4.7); the PIE take-back `:752-765` becomes `TakeBackPawn` |
| `IsHoldingPawns` `:646-662` | 4.7 (also holds practice countdowns with `bStartAboard`) |
| `EvaluateTeams` `:876-967` | phase Lobby branch: start block, cancel the countdown on a hard block |
| `ApplyRules` `:1545-1605` | team mode at once in phase Lobby (`:1551-1556`) |
| `StartCountdown` `:1021-1081` | `DelayOverride`; no Countdown event at 0 s |
| `BeginRound` `:1191-1213` | `TakeBackPawnsForStart`, `ResumeSwarm`, `StartSessionIfHost` |
| `SpawnWaitingPlayers` `:1316-1324` | aboard for practice too (`bStartAboard`) |
| `EndMatch` `:1397-1437` | timer -> `ReturnToLobby` when `bLobbyRound`; `EndSession` |
| `MatchTick` `:2368-2413` | no fall death in phase Lobby |
| `ChoosePlayerStart` `:2732-2783`, `RestartPlayer` `:2785-2878` | Lobby-tagged starts; lobby spot; late joiners without a landing (3.4) |
| `FindRespawnSpot` `:3124-3261` | lobby spot first; path start before the PlayerStart (3.4) |
| `GetTeamProgress` `:2653-2685` | ignore platforms without SplineDistance |
| new `MyGameModeLobby.cpp` | `ResolveLobbySpawn`, `SpawnLobbyPlayers`, `LobbyTick` (zone, ground poll, start block), `GetLobbySpot`, `RequestLobbyTeam`, `MoveLobbyPlayer`, `RebalanceLobbyTeams`, `SetLobbyReady`, `ApplyLobbyRules`, `GetLobbyStartBlock`, `StartFromLobby`, `CancelLobbyStart`, `OnLobbyCountdownEnd`, `ReturnToLobby`, `TravelToMatch` (later), `IsLobbyHost`, `TakeBackPawn(sForStart)`, `ResumeSwarm`, `StartSessionIfHost` |
| `MyGameState.h/.cpp` | 4.3 fields and setters; `LobbyOnly` hide on leaving Lobby (3.4) |
| `MyPlayerState.h/.cpp` | 4.3 fields; `SetCurrentPlatform` returns in phase Lobby (`:45-67`); `CopyProperties` |
| `MyPlayerController2.h/.cpp` | 4.8 RPCs; Esc to the lobby panel (`TogglePauseMenu` `:404-417`); `OpenPauseMenu()` |
| `UI/MyHUD.h/.cpp` | `LobbyWidgetClass`, `AddLobbyWidget`, `GetLobbyWidget()` |
| `Match/MyMatchTypes.h` | `EMyMatchPhase::Lobby` (appended), `EMyLobbyStartBlock`, `EMyLobbySpawn`, new events (appended) |
| `Match/MyMatchSettings.h` | Appendix L-A |
| `Match/MyTeamLibrary.h/.cpp` | `IsInLobby`, `AreShipsLocked`, `IsDamageOff` (phase Lobby and not `bLobbyDamage`), `TeamModeMaxPlayers` |
| `Match/MyMatchHUDWidget.cpp` | phase Lobby: toasts and name tags (+ the 6.6 strip without the WBP); Ended: "Back to the lobby in n s" when `bLobbyRound` (`:385-434`); toasts for the lobby events |
| `Match/MyMatchConsole.cpp` or new `Match/MyLobbyConsole.cpp` | Appendix L-B |

### 7.2 Main menu (menu owner)

* `OnCreateSession` (`MainMenu3.cpp:1298-1321`): `GetHostTravelPath() + BuildMatchOptions(false) + "?Lobby=1"` (2.1).
  Play Solo is unchanged.
* New public statics for the option lists (6.3).

### 7.3 Pause menu (menu owner)

* `RefreshMatchButtons` (`PauseMenu3.cpp:445-455`): START MATCH shows in WaitingToStart **and** in Lobby when not counting
  down. In Lobby, `StartMatchButtonClicked` calls `RequestStartMatch`, which forwards to `StartFromLobby(/*bForce*/true)`
  (the host's explicit start, like B5.2's start with whoever is in).
* The Restart row: when the game state's `bLobbyRound` is true, its label is BACK TO LOBBY, its confirm text is "End the
  match and take everyone back to the lobby?", and it calls `ReturnToLobby` (`:505-510`, `:821-826`). Otherwise as built.
* New public `RequestLeaveSession()` (6.4).

### 7.4 Sessions (menu owner)

`UMultiplayerSessionsSubsystem::EndSession()` and `AdvertiseMatchRules(...)` (5.5, 4.6). `StartSession`'s InProgress guard
stays.

### 7.5 Airship (airship owner) and combat (combat owner)

* `AAirshipPawn::CanBoard` / `CanMount` (`AirshipPawn.cpp:1654`, `:2208`): `if (UMyTeamLibrary::AreShipsLocked(this))
  return false;`.
* `EAirshipUseRefusal::Locked` (AirshipTypes.h), sent by the pilot component (`AirshipPilotComponent.cpp:277`, `:409`),
  with the toast "Ships unlock when the match starts".
* `UMyAttributeSet` (`MyAttributeSet.cpp:81-82`): the damage is dropped also when `UMyTeamLibrary::IsDamageOff(...)`.

### 7.6 The WaitingToStart phase: kept

It is still used when the lobby is off: console `open StartupMap?listen`, `RestartMatch` without the lobby, the PR B
listen harness as_75 (no `Lobby` option, CVar -1). Later it is also the separate lobby map's arrival wait (5.7). No code
is removed.

### 7.7 Defaults and what PR B tests change

* Host Game -> lobby. Play Solo, console, as_74 / as_75 / as_76 -> PR B flow, so those harnesses keep working.
* Practice now starts aboard. **SPEC_B T1.1** ("spawned on the floor") becomes: no pawn during the 5 s countdown, then
  the pawn on team 0's deck within 1 s of InProgress. **M1.1's practice variant** becomes "pawns aboard team 0's ship".
  as_74 / as_75 need that one-line pass change.
* SPEC_B B4.2's bullet "Practice, or `bStartAboard` off: at a PlayerStart" becomes "`bStartAboard` off: the path's first
  platform, else a PlayerStart".

---

## 8. L7 Files, scripts, tests, risks

### 8.1 File ownership

The lobby is one work package after PR B's code. If it is split, these are the owners (no two touch the same file):

| Owner | New | Changed (PR B files) |
|---|---|---|
| match | `Private/MyGameModeLobby.cpp`; `Public/Private/Match/MyLobbyWidget.*`, `MyLobbyPlayerRow.*`; `Private/Match/MyLobbyConsole.cpp` | `MyGameMode.*`, `MyGameState.*`, `MyPlayerState.*`, `PlayerInput/MyPlayerController2.*`, `UI/MyHUD.*`, `Match/MyMatchTypes.h`, `Match/MyMatchSettings.h`, `Match/MyTeamLibrary.*`, `Match/MyMatchHUDWidget.cpp` |
| menu | none | `EOS/MainMenu3.*`, `EOS/PauseMenu3.*`, `EOS/MultiplayerSessionsSubsystem.h/.cpp` |
| airship | none | `Airship/AirshipPawn.cpp` (two lines), `Airship/AirshipTypes.h` (refusal), `Airship/AirshipPilotComponent.cpp` |
| combat | none | `AbilitySystem/MyAttributeSet.cpp` (one condition) |
| assets | `Docs/Airship/scripts/ue/as_77`..`as_80*` (8.2) | none |

Order: match writes the `MyMatchTypes.h` / `MyMatchSettings.h` / `MyTeamLibrary.h` additions first (header API), then the
owners work in parallel. No `Aura.Build.cs` change: UMG and OnlineSubsystem are already dependencies
(`Aura.Build.cs:11-13`, verified). No `Config/*` change (C++ defaults).

### 8.2 Editor scripts (rules of SPEC_B section 3: inbox, never during PIE, `free -g` first, explicit paths)

| Script | Does | Saves |
|---|---|---|
| `as_77_lobby_widget.py` | WBP_Lobby3 + WBP_LobbyPlayerRow3 (6.5); backup none needed (new assets) | the two new WBPs |
| `as_78_lobby_hud.py` | BP_MyHUD `LobbyWidgetClass` = WBP_Lobby3_C, compile, save; then verify: the new classes load, WBP_Lobby3 has the 6.3 names (missing ones listed, not an error), UMainMenu3's option lists vs WBP_MainMenu3's CDO, `UMyMatchSettings` lobby defaults = Appendix L-A. Backup of BP_MyHUD to `Saved/Match/backup/`. Report `Saved/Match/as_78_verify.txt` | BP_MyHUD |
| `as_79_pie_lobby.py` (+ `as_79s_status.py`, `as_79x_stop.py`) | standalone harness 8.3 on the clone's StartupMap: sets `Aura.Lobby.Enable 1`, fixed 30 fps, restores the CVars at the end | nothing |
| `as_80_pie_lobby_mp.py` (+ `as_80s`, `as_80x`) | listen harness 8.4, 2 / 3 / 4 players (`AS80_PLAYERS`), the as_75 ini method for PlayNetMode / clients, `Aura.Lobby.Enable 1` | ini only |
| `as_81_lobby_map.py` | later, not in this PR: L_Lobby (3.5) | L_Lobby |

No script saves StartupMap. TEMP actors (as_59 method) are not needed: the floor and the placed platform are in both
maps already.

### 8.3 Standalone PIE tests (as_79, StartupMap clone, 1 player)

| ID | Setup | Pass |
|---|---|---|
| LB1.1 | load with the lobby | phase Lobby within 1 s; log `Lobby: spawn PlayerStarts, ground Floor (+ BP_MyHexPlatform_C_1)`; the zone contains (0, 0, 205) and the placed platform's location; the pawn within 8 m of (0, 0, 205); no team ship; every wave spawner stopped and 0 sentinels alive at 15 s; Burrower `IsSpawningPaused` true |
| LB1.2 | a free ship by `Aura.Airship.Spawn`; `Aura.Airship.TurretFire` at the player's position | Health unchanged (lobby, no damage); `Aura.Airship.Board 0` refused with Locked (log); after LB1.6's start the same turret fire lowers Health |
| LB1.3 | the harness teleports the pawn onto a path platform at u 50 m | back inside the zone within 1.0 s (0.5 s grace + 0.25 s tick + a frame); `CurrentPlatform` null, `PlatformSplineDistance` -1; `GetActivatedSplineDistance` -1 (nothing collapses) |
| LB1.4 | `Aura.Match.Rules Teams=practice ShipLives=5 Swarm=3` in the lobby | applied at once, team mode included (`Aura.Match.Status`); spawner DifficultyScale = Very Hard preset |
| LB1.5 | `Aura.Lobby.Start`, then `Aura.Lobby.Cancel` at 2 s | PhaseEndServerTime set 5 +-0.1 s ahead, then 0; phase Lobby; events LobbyCountdown, LobbyCancelled |
| LB1.6 | `Aura.Lobby.Start`, wait 7 s | at 5 +-0.1 s phase InProgress within 2 frames; one team ship, TeamId 0, at (5442, 12500, 200) +-100 cm; the player rides its deck within 1 s and has full Health and Mana; spawners running and wave 1 sentinels alive within 4 + 6 + 2 s; Burrower not paused |
| LB1.7 | `Aura.Match.Set EndScreenSeconds 3`, `Aura.Match.End -1` | Ended; after 3 +-0.5 s the map reloads (OpenLevel) with `Lobby=1` (log); phase Lobby; rules as set in LB1.4; RoundIndex 0 (practice keeps the round) |
| LB1.8 | after the start (nobody has landed yet), the harness destroys the PIE copies of Floor and BP_MyHexPlatform_C_1 (PIE world only), then teleports the player 150 m below the lane, on foot | fall death within 8 s; the respawn is on a path platform (SplineDistance >= 0), never within 30 m of (0, 0, 205) |
| LB1.9 | before PIE `Aura.Match.Set LobbySpawn PathStart` | the pawn on the platform with the smallest SplineDistance within 10 s; after 30 s there `CurrentPlatform` null, nothing activated; LB1.6's start works from there |
| LB1.10 | no Lobby (CVar -1, URL `?Teams=auto?Players=1`, the Play Solo URL) | practice countdown at once; no pawn for 5 s; then the pawn on team 0's deck (7.7) |

### 8.4 Listen PIE tests (as_80)

| ID | Players | Pass |
|---|---|---|
| LM1.1 | 2 | both in phase Lobby with pawns on the floor within 3 s of the client's join, at least 2 m apart (ring search); teams 0 / 1; the client's Teams, ready flags and `bIsHost` equal the server's within 0.5 s; `WBP_Lobby3` instance exists on both (find_object); host's StartButton visible, client's hidden |
| LM1.2 | 2 | `Aura.Lobby.Start strict` refused NotReady; `Aura.Lobby.Ready 1 1`, then `Aura.Lobby.Start strict`: countdown 5 s; at 0 both ride their own ship's deck within 1 s (team 0 y +12500, team 1 y -32500); TeamIds as in the lobby |
| LM1.3 | 3, then 4 | 3: teams {2, 1}; `Aura.Lobby.Team 2 1` moves c2 at once ({1, 2}). 4: {2, 2}; `Aura.Lobby.Team 1 0` leaves c1 pending (RequestedTeam 0 on the client within 0.5 s); `Aura.Lobby.Team 2 1` (c2, team 0) swaps both, requests cleared, counts {2, 2} |
| LM1.4 | 3, then 2 | 3 players: `Aura.Match.Rules Teams=1v1` refused ("1v1 has room for 2"). 2 players: `Teams=2v2 ShipLives=5 Swarm=3` -> the client's rules equal within 0.5 s, ready flags false, Max Players 4; a session update logged when hosting (in PIE without a session: "no session to advertise", accepted) |
| LM1.5 | 2, 1v1 | the client leaves during the lobby countdown: cancelled within 0.5 s (event LobbyCancelled, NeedOpponent), phase Lobby, no ship spawned |
| LM1.6 | 2 | after the start `Aura.Match.Set EndScreenSeconds 3`, `Aura.Match.End 0`: ServerTravel with `Lobby=1`, `Round=1`; both reconnect; phase Lobby; TeamIds as before (or join order with no valid net ids, logged, as SPEC_B M7.1); rules kept; ready flags false. A second start puts team 0 at y -32500 (sides swapped) |
| LM1.7 | 2 | in the lobby the host's gun hits on the client: Health unchanged; after the start: -1 per hit (SPEC_B M3.1's GE value) |
| LM1.8 | 2 | in the lobby the client teleported 100 m out of the zone (harness, server world) is back within 1.0 s and gets the zone message (client log) |

### 8.5 Manual and packaged checks

* The full menu path: MM_MainMenu -> Host -> the lobby panel opens; the host edits the rules, the client's combos follow
  and are disabled; START's reasons; LEAVE -> menu.
* Late join during a match, and the host leaving or crashing (PIE can't add a client mid-session or end the host alone):
  the client lands in the match aboard / past the lead; on the host's Leave the client shows "The host closed the
  lobby."; on a host crash, "Lost connection to the host.". Two machines, packaged (Steam).
* Packaged, two machines: the session is joinable in the lobby, StartSession logged at the match start and EndSession at
  its end, joinable again in the next lobby, a rejoin goes into the new lobby with the remembered team.

### 8.6 Risks

1. **RL1 The zone teleport feels like a rubber band** mid-grapple. 15 m margin, 60 m headroom and 0.5 s grace; tune with
   LB1.3 / LM1.8.
2. **RL2 The in-level lobby costs the full match map** (PCG platforms, fog, clouds). Waves and Burrowers are off; nothing
   else can be made cheap without a separate map (3.5).
3. **RL3 PCG platform timing in PathStart mode** (the first platform may take frames): held pawns plus a 10 s timeout
   with the PlayerStart fallback.
4. **RL4 Hard travel back to the lobby in listen PIE** may differ from a packaged game (SPEC_B R6); LM1.6 falls back to a
   manual check.
5. **RL5 Practice now starts aboard** (7.7): a behaviour change for learners (they fly to the platforms first) and a 5 s
   still camera at Play Solo's start.
6. **RL6 Talal's free ship inside the lobby zone** (`BP_AirshipPawn_C_6`): locked in the lobby; removed at a versus start
   (B3.1, SPEC_B Q9), free in practice.
7. **RL7 A landing on a path platform during the 0.5 s grace** would rank the player without the `SetCurrentPlatform`
   gate; the gate is required, not optional.
8. **RL8 Steam lobby joinability depends on the join-in-progress flag at all times** (5.5): any future "no join in
   progress" option has to toggle it at Start.
9. **RL9 Option lists read from the C++ CDO of UMainMenu3**: a value changed only on WBP_MainMenu3 would not reach the
   lobby (as_78 warns).
10. **RL10 The ring search around one PlayerStart** gives 25 spots (centre + 24); enough for 4-8 players on the floor
    (inferred). More would need Lobby-tagged PlayerStarts (Talal's map) or L_Lobby.

---

## 9. Questions for Talal (defaults in brackets; none blocks the work)

1. **Q-L1** When the match starts, should the floor and the platform above it stay where they are until you delete them
   [yes, the match never uses them], or disappear at Start? For the second, tag them `LobbyOnly` in your map and the game
   hides them at Start (3.4).
2. **Q-L2** After you delete the floor, the in-level lobby moves by itself to the path's first platform [yes]. Or do you
   want the separate lobby map (L_Lobby, 3.5) by then?
3. **Q-L3** Play Solo goes straight into practice, no lobby [yes]. Practice now starts aboard team 0's ship, so nothing
   needs the floor [yes].
4. **Q-L4** Ready flags: shown, and the host may start anyway after a second click [yes], or everyone must be ready?

---

## Appendix L-A. Settings added to `UMyMatchSettings` (category "Lobby", Config=Game, C++ defaults)

| Name | Default | Meaning |
|---|---|---|
| bLobbyWhenHosting | true | the main menu's Host Game travels with `?Lobby=1` (7.2) |
| LobbyMap | "" | empty = in-level lobby (the match map is the lobby); a map path = a separate lobby map (2.7) |
| MatchMap | /Game/Maps/StartupMap | where a separate lobby's Start travels (unused in-level) |
| LobbySpawn | Auto | Auto, PlayerStarts, PathStart (3.1) |
| LobbyGroundTraceDepth | 5000 | cm, the trace under each PlayerStart |
| LobbyZoneMargin / LobbyZoneHeight / LobbyZoneDepth | 1500 / 6000 / 2000 | cm around, above and below the ground's top (3.1) |
| LobbyZoneGraceSeconds | 0.5 | s outside the zone before the teleport back |
| LobbyCountdownSeconds | 5 | s from Start to the match |
| bLobbyRequireReady | false | true = NotReady blocks Start |
| bLobbyTeamSwitch | true | players may ask to switch (4.4) |
| bLobbyRulesClearReady | true | a rules change clears the ready flags |
| bLobbyDamage | false | true = damage in the lobby |
| LobbyOnlyActorTag | LobbyOnly | actors with it are hidden at Start (3.4); none tagged today |
| LobbyArrivalTimeout | 45 | s, separate lobby map only (5.7) |
| bStartAboard (existing) | true | now also practice (3.4) |
| EndScreenSeconds (existing) | 20 | then back to the lobby when the round had one |

On `UMyLobbyWidget`: `TimeLimitChoices` {0, 5, 10, 15, 20, 30}, `RefreshInterval` 0.25, `StartConfirmSeconds` 3.

## Appendix L-B. Console additions (compiled out of Shipping like `Aura.Match.*`)

| Command | Where | What |
|---|---|---|
| CVar `Aura.Lobby.Enable` | read at InitGame | -1 = by the URL's Lobby option (default), 0 off, 1 on |
| `Aura.Lobby.Status` | any | phase, countdown, spawn mode, zone boxes, start block, per player: team, ready, request, host |
| `Aura.Lobby.Start [strict]` | server | the lobby countdown; soft blocks ignored unless `strict` |
| `Aura.Lobby.Cancel` | server | cancels the lobby countdown |
| `Aura.Lobby.Ready <PlayerIndex> <0/1>` | server | sets a player's ready flag |
| `Aura.Lobby.Team <PlayerIndex> <0/1>` | server | that player's switch request (the 4.4 rule) |
| `Aura.Lobby.Move <PlayerIndex> <0/1>` | server | the host's move (no balance rule) |
| `Aura.Lobby.Return` | server | `ReturnToLobby` now (the pause menu's BACK TO LOBBY) |
| `Aura.Lobby.Zone [seconds]` | server | draws the zone boxes (DrawDebugBox, 10 s default) |
| `Aura.Lobby.Panel <0/1>` | local | opens / closes the lobby panel (captures) |

PlayerIndex = the server's player controller order, 0 = the host (as `Aura.Match.Team`, SPEC_B Appendix B).
`Aura.Match.Start` in phase Lobby = `Aura.Lobby.Start`; `Aura.Match.Status` gains one lobby line.

## Appendix L-C. Engine and session facts used (verified)

| Fact | Where |
|---|---|
| InitGame runs after the components are registered (traces work) | `World.cpp:5988`, `:6034` |
| The game mode's Options are the URL's `?` options | `World.cpp:5974-5975` |
| A new player gets a pawn only when PlayerCanRestart says so | `GameModeBase.cpp:1068-1076`, `:1203-1212` |
| Seamless only with `bUseSeamlessTravel` / `?SeamlessTravel`, never in PIE by default | `GameModeBase.cpp:488`, `:494-501`, `:504-511`; `GameModeBase.h:579` |
| No TransitionMap -> an empty transition world | `World.cpp:8330`, `:8367-8370` |
| PlayerStates kept and copied in seamless travel | `GameModeBase.cpp:539-559`, `:607-619`; `PlayerController.cpp:3652-3658`; `PlayerState.cpp:101-104`, `:116`, `:413-418` |
| A client that loses its host goes to the default map | `UnrealEngine.cpp:15512`, `:15527`; `DefaultEngine.ini:2` |
| Steam StartSession from Pending / Ended only; EndSession from InProgress only | `OnlineSessionInterfaceSteam.cpp:398-433`, `:497-510` |
| Steam lobby joinable = join in progress and room | `OnlineSessionAsyncLobbySteam.cpp:447`, `:657` |
| EOS join in progress is a session flag set on the session | `OnlineSessionEOS.cpp:1380-1387` |
| OpenLevel adds its own `?` | `GameplayStatics.cpp:981` (SPEC_B B4.6) |
