# Airship round 2, PR B addendum: the lobby (implementation spec, revision 2)

Status: revision 2, 2026-11-28. Addendum to `SPEC_B.md` (revision 2). It changes SPEC_B only where section 7 says so;
everything else in SPEC_B stands. Nothing here is built or run. Revision 1 (2026-11-25) was critiqued in
`_AirshipWork_logs/scratch/r2b/lobby_critique.json` (1 blocker, 3 major and 12 minor entries; its summary says 11). Every
entry is answered in the changelog below.

Base: the sparse worktree `/mnt/new_partition/UnrealProjects/_AirshipWorkB`, branch `airship-r2-prb` at e9636cc (PR A
merged in), clean working tree. **Every project `file:line` below was re-read in that tree on 2026-11-28** (PR A moved
many lines; the function names are the anchors). Engine lines are in `/mnt/new_partition/5.8/Engine/...`. Map facts were
decoded read-only from Talal's `AuraRedo3/Content/Maps/StartupMap.umap` (dated 2026-11-26 15:18, decoded again on
2026-11-28 with the scratchpad parser `uparse.py`: the actors of section 1 are unchanged since revision 1).

Marks: **verified** = read in the code or engine source; **decoded** = read from asset bytes; **inferred** = worked out.

Terms: **session** = the online session (a Steam lobby on this project, 5.6); **lobby** = the in-game lobby this addendum
adds; **match map** = StartupMap; **hard travel** = a ServerTravel where every client disconnects and connects again;
**seamless travel** = a ServerTravel where the clients stay connected and the engine moves everyone through a transition
world.

Talal, verbatim: "1. Lobby level", then: "have the same startup level as lobby level for now, and when the real match
start the floor and the seperate hex platform which is placed right above the floor right now, I will remove later on ,
the real level consists of only the hex path spawner that spawns hex platforms , bridges for the level and enemy
spawners and every thing else remains".

**Reading used (unchanged).** For now the lobby **is** StartupMap: no lobby map and no travel at Start. Players walk
around on the start floor and on the hex platform above it while the lobby UI shows the teams, who is ready and the
host's rules. The host presses Start and the match starts in the same level. Talal will delete the floor and that
platform later. So nothing in the match may depend on them, the lobby must keep working without them (3.1), and our code
never removes or edits his map's actors. The other reading ("they disappear at Start") is Q-L1; the optional `LobbyOnly`
tag covers it (3.4).

---

## Changelog vs revision 1

| # | Critique entry | Revision 2 | Where |
|---|---|---|---|
| B1 | Blocker: the hard ServerTravel back to the lobby drops every client on the Steam net driver | The return to the lobby, and PR B's own `RestartMatch`, travel **seamlessly** (`?SeamlessTravel` on the URL, no TransitionMap: the engine's empty transition world). The Steam reject chain is verified line by line. Seamless travel, an in-place reset and "hard travel plus a rejoin window" are compared; seamless wins. PIE falls back to hard travel by itself, so both arrival paths are specified and tested. | 5.1-5.3, D11 |
| M1 | Major: seamless arrivals skip Login / InitNewPlayer / PostLogin; old game mode timers keep firing | One arrival routine `OnPlayerArrived` runs from `PostLogin` (hard) and from a new `InitSeamlessTravelPlayer` override (seamless). `StartToLeaveMap` clears every game mode timer. `CopyProperties` carries TeamId; no `Reset` override may clear it; `OverrideWith` is never called on AGameModeBase. Players still loading are recognised (a replicated arriving flag set in `PostSeamlessTravel`; the engine's `bActorSeamlessTraveled` is cleared before any game code runs, review row 1) and not counted. Two more gaps found: the airship pilot component is only added on PostLogin, and a client's old pilot component can remove the new one's input mapping. Both fixed. | 5.4, D12 |
| M2 | Major: players start the match with the lobby panel open in UI-only input | Every machine closes the panel when the lobby countdown starts and gives input back (game only, cursor hidden). Players move during the 5 s. LB1.5 and LM1.6 check the input mode; LM1.6 also a real move input. | 6.1, LB1.5, LM1.6 |
| M3 | Major: late joins called impossible in PIE | Wrong in revision 1. The as_80 client rejoins with `open 127.0.0.1:<ServerPort>` (the PIE server port). Four cases are tested: lobby, lobby countdown, InProgress, Ended. Only the host crash and the Steam checks stay manual. | 8.4 |
| m1 | Ships spawn one tick before the players are put aboard | The lobby countdown **is** PR B's Countdown phase, started by the host: ships are claimed or spawned at its start, as in PR B. The untagged placed ship is removed only at its end. Cancel releases or removes the team ships. | 4.7, D9 |
| m2 | Button names; Start doesn't say what starts | PLAY becomes CLOSE; READY is hidden for the host; START shows the mode that will start ("START 2v1", "START CO-OP (ONE SHIP)"); the Practice entry reads "Practice (co-op, one ship)". | 6.2, 6.4 |
| m3 | Rows rebuilt 4 times a second eat clicks | Rows are rebuilt only when the player/team signature changes; otherwise their texts are updated in place. | 6.4 |
| m4 | Host can't move anyone when teams are full | The host's MOVE into a full team swaps with a player of that team (one with a pending request first, else the last to join). | 4.4 |
| m5 | `LobbyOnly` hide missed late joiners | Applied as a state on every machine from the replicated phase (OnRep and BeginPlay), not at a phase change. Pickups use the same state. | 3.4 |
| m6 | ExpectedPlayers isn't Max Players at load | With the lobby, InitGameState and StartPlay write the URL's Players, clamped to the mode's maximum. | 4.2 |
| m7 | Session: return skips EndSession; Steam Ending; lobby vs match not visible | EndSession also at the return when InProgress; StartSession waits while Ending; an advertised `InMatch` key shows IN LOBBY / IN MATCH in the browser. | 5.6 |
| m8 | Every rules change un-readies everyone | Only a team mode or Max Players change clears ready. Edits are sent once, 0.75 s after the last one, with one session update. | 4.5, 4.6, 6.4 |
| m9 | Slow and inconsistent loop after a match | A match that ends while the host has a session goes to the lobby too (Play Solo + Open Lobby included). The end panel says how to skip. A rematch with the same players on the same teams starts with one click. Seamless travel has no 4 s pause. | 2.5, 4.5, 5.3 |
| m10 | Ground detection accepts anything; no-zone fallback teleports everyone | A capsule sweep on the pawn channel, walkable normal only. Without a zone only a fall catch runs. New test with the floor deleted in the lobby (`Aura.Lobby.Resolve`). | 3.1, 3.2, LB1.9 |
| m11 | Lobby cooldowns, effects and pickups carry into round 1 | At Start every timed effect (cooldowns, buffs) is removed; pickups are off in the lobby. LB1.6 checks it. | 3.3, 4.7 |
| m12 | 3 and 4 PIE instances may not fit in memory | Talal's lean rule: one standalone run and one 2-player listen run. The 3 and 4 player rules use bot player states (`Aura.Lobby.Bots`). | 8.3, 8.4 |
| - | Not in the critique | The separate lobby map code (LobbyMap, TravelToMatch, arrival wait) is deferred; its design is kept (2.7, 5.8). The lobby's own countdown event is dropped (PR B's Countdown event is sent). All file:line refs re-verified after PR A (for example `CanBoard` is now `AirshipPawn.cpp:1673`, `CanMount` `:2533`). | 8.7 |

---

## 0. Final decisions

| # | Decision | Section |
|---|---|---|
| D1 | The lobby is a phase of `AMyGameMode`: `EMyMatchPhase::Lobby`, appended. A replicated `AMyGameState::bInLobby` says "lobby rules apply". It is true in phase Lobby and during the lobby's countdown, and false from the round start. | 4.1, 4.3 |
| D2 | Host Game from the main menu starts in the lobby (`?Lobby=1`). So does every map load that follows a match that ended while the host had a session. Play Solo, console opens and the PR B harnesses keep the PR B flow. CVar `Aura.Lobby.Enable` forces it for tests. | 2.1, 2.5, 4.2 |
| D3 | Lobby ground: Auto = a PlayerStart with walkable, pawn-blocking ground under it (capsule sweep). Else the path's first platform. Else the PlayerStart with a fall catch only. | 3.1 |
| D4 | A lobby zone holds players in (0.5 s grace, then back). The race can't start early: no ranking, no collapse, no path growth, waves stopped, Burrowers paused, ships locked. | 3.2, 3.3 |
| D5 | In the lobby abilities work; damage and pickups are off. At Start, lobby pawns are replaced and every timed effect is removed. | 3.3, 4.7 |
| D6 | Teams: auto-balance on join. A player may switch when the teams stay within one, or swap with a player who asks for the opposite. The host's MOVE swaps when the target team is full. | 4.4 |
| D7 | Ready flags are shown. The host may start without them after a second click (Q-L4 default). A rematch with the same players on the same teams needs no second click. `bLobbyRequireReady` makes them required. Only team mode and Max Players changes clear them. | 4.5 |
| D8 | Only the host changes rules and starts, through Server RPCs on the player controller. Rules edits are batched into one request. | 4.6, 4.8 |
| D9 | Start = PR B's `StartCountdown` with `LobbyCountdownSeconds` (5 s), forced by the host: active teams, sides, handicap and ships at its start; lobby rules stay on until its end. Every machine closes the lobby panel at its start. Cancel goes back to phase Lobby and releases or removes the team ships. At its end PR B's `OnCountdownEnd` and `BeginRound` run: lobby pawns taken back, timed effects removed, everyone aboard his own team's ship, swarm resumed, StartSession. | 4.7 |
| D10 | Practice also starts aboard (team 0's ship). Respawns before anyone has landed go to the path's first platforms. The match never needs the floor. | 3.4 |
| D11 | Match end: end screen, then `ReturnToLobby()` = a ServerTravel to this map with `?Lobby=1` and `?SeamlessTravel`. No TransitionMap: the engine makes an empty transition world. PR B's `RestartMatch` uses the same seamless travel. PIE travels hard unless `net.AllowPIESeamlessTravel=1`. | 5.1-5.3 |
| D12 | Both arrival paths run `OnPlayerArrived`: host flag, pilot component, log; on the seamless path also the team keep and `EvaluateTeams`. `StartToLeaveMap` clears every game mode timer. TeamId travels by `CopyProperties` (seamless) or the match memory (hard). Players still loading are not counted and block Start for up to 45 s. | 5.4 |
| D13 | Lobby widget `UMyLobbyWidget` (C++, BindWidgetOptional) and `WBP_Lobby3` built by as_77. Esc opens it during the lobby. | 6 |
| D14 | Host leaves: every client is kicked to the main menu (exists today). | 4.9 |
| D15 | Session: StartSession at every round start, EndSession at the match end and at a return while InProgress; StartSession waits while Ending; advertised `InMatch`. | 5.6 |
| D16 | Tests: one standalone PIE run (as_79) and one 2-player listen PIE run (as_80). The seamless PIE smoke test runs last in as_80. The real test of D11 is two Steam machines (manual). | 8 |
| D17 | Deferred: the separate lobby map and its two travels, a loading screen, team pads, the editor's "Add Client". | 8.7 |

---

## 1. What exists (the facts the design stands on)

* **StartupMap actors** (decoded, Talal's tree, 2026-11-28): `Floor` (StaticMeshActor, scale 8 at (-3, 10, -4), the 80 m
  start floor); `BP_MyHexPlatform_C_1` (a placed `BP_MyHexPlatform`, root at (16, -199, 1678): 112 pillar instances over
  x -2063..2094, y -1999..1901, all at z 1678, about 17 m above the floor); `PlayerStart_0` at (0, 0, 205), the only
  PlayerStart, under that platform; `BP_AirshipPawn_C_6` at (3700, 555, 1097), a free ship next to the floor;
  `BP_Potion_C_1` at (1369, 104, 63); decor `StaticMeshActor_1..4` (one is a static `SM_Airship` at (13340, 8972, 893));
  `MechSentinelWaveSpawner_0`; `BP_MyHexPathSpawner_C_1` at (5441.6, -10000, 0). The clone's StartupMap has the same
  actors without the airship pawn (decoded, revision 1).
* **The placed platform has no SplineDistance** (`MyHexPlatform.h:290`, `:334` default -1; only the path's PCG sets it).
  A landing on it keeps the rank (`MyPlayerState.cpp:54-58`). It is never a respawn candidate (`MyGameMode.cpp:3245`) and
  is never activated for collapse (`MyGameState.cpp:140`). Verified.
* **The path's platforms can be reached from the floor** (boost, grapple; inferred). A landing on a path platform ranks
  the player (`MyCharPlayer.cpp:359` -> `MyPlayerState.cpp:45-67` -> `AMyGameState::UpdatePlayerRanking`, which activates
  the collapse behind the leader, `MyGameState.cpp:63-123`). Verified. So the lobby keeps players off the path (3.2).
* **The race world runs from load.** The path spawner builds its first segments in BeginPlay (`MyHexPathSpawner.cpp:45`,
  `:71-74`). The wave spawner arms itself in BeginPlay (`bStopped = !bAutoStart`, `MechSentinelWaveSpawner.cpp:186`) and
  queues waves from new segments (`:1082`). `StopWaves` / `StartWaves` pause and resume (`MechSentinelWaveSpawner.h:225`,
  `:229`; `.cpp:359`, `:389`). Burrowers: `SetSpawningPaused` (`BurrowerSpawnSubsystem.cpp:418-425`, gate at `:196`).
  Path growth: an on-foot pawn within ExtendDistance x S of the path end (`MyHexPathSpawner.cpp:257-291`, test at `:285`).
  Verified.
* **PR B's flow as built.** Host Game: `UMainMenu3::OnCreateSession` -> `ServerTravel(PathToLobby + Options)`
  (`MainMenu3.cpp:1298-1321`, travel at `:1314`; PathToLobby = MenuSetup's LobbyPath + `?listen`, `:30-33`). Play Solo:
  `OpenLevelLeavingSession(PathToLobby + Options)` (`:450-461`), a listen server without a session.
  `AMyGameMode::StartPlay` (`MyGameMode.cpp:741-805`): practice counts down at once (`:776-781`); versus goes to
  WaitingToStart with no pawns (`:783`, `IsHoldingPawns` `:657-673`). Countdown, start aboard, end, restart:
  `StartCountdown` `:1059-1142`, `OnCountdownEnd` `:1144-1250`, `BeginRound` `:1252-1274`, `SpawnWaitingPlayers`
  `:1360-1427`, `EndMatch` `:1460-1500`, `RestartMatch` `:1502-1567` (a hard `ServerTravel(URL, true)` at `:1562`).
  Team memory: `UMyMatchMemorySubsystem` (`MyMatchMemorySubsystem.h:22-55`), reset when a map loads without `Round`
  (`MyGameMode.cpp:373-394`). Verified.
* **Travel and net config.** `GameDefaultMap=/Game/Maps/MM_MainMenu`, `ServerDefaultMap=/Game/Maps/StartupMap`
  (`Config/DefaultEngine.ini:2`, `:5`). No `TransitionMap` anywhere (grep of `Config/*.ini`, `BaseEngine.ini`,
  `BaseGame.ini`). `GameNetDriver` = `SteamSocketsNetDriver`, fallback `IpNetDriver` (`DefaultEngine.ini:106`).
  `DefaultPlatformService=Steam` (`:113`). Sessions use `bUseLobbiesIfAvailable` (`MultiplayerSessionsSubsystem.cpp:142`,
  `:188`). BP_MyGameMode has no `bUseSeamlessTravel` (decoded, SPEC_B B4.6). Verified.
* **`LoadScreen.umap` is not a loading screen** (an ObjectRedirector to the course's save-slot menu map; decoded,
  revision 1). No MoviePlayer code (grep).

---

## 2. L1 Flow

```
Main menu --Host Game--> session --ServerTravel StartupMap?listen?<rules>?Players=n?Lobby=1--> LOBBY (StartupMap)
   ^                                                                                     | host START
   |                                                                          lobby countdown 5 s (PR B Countdown)
   |  Leave (pause menu / lobby LEAVE)                                                    v
   +----------------------------- LOBBY <--seamless ServerTravel ?Lobby=1-- END SCREEN <-- MATCH (same world)
Join (code, browse, invite) --ClientTravel to the host--> whatever the host runs (lobby, countdown, match, end screen)
Play Solo --OpenLevel StartupMap?listen?<rules>?Players=1--> practice countdown --> MATCH (no lobby; lobby after the
                                                             match if the host opened a session meanwhile)
```

### 2.1 Host Game

1. Unchanged up to the session: `StartLobbyButtonClicked` -> `CreateSessionWithSettings` (`MainMenu3.cpp:436-448`).
2. `OnCreateSession` (`:1298-1321`) travels to `PathToLobby + BuildMatchOptions(false) + "?Lobby=1"` when
   `UMyMatchSettings::bLobbyWhenHosting` (default true). This travel has no clients and stays hard.
3. `AMyGameMode::InitGame` reads `Lobby=1` (4.2). StartPlay goes to phase **Lobby** (4.7).

### 2.2 Join

Unchanged on the client: the subsystem joins the session and travels to the host (`MainMenu3.cpp:1401`,
`MultiplayerSessionsSubsystem.cpp:938-956`). On the server: `PreLogin` (ban, session full, team cap,
`MyGameMode.cpp:189-219`) -> `InitNewPlayer` -> `AssignTeam` (`:704-739`, `:807-851`) -> `PostLogin` (`:221-241`).

| Host's state | The joiner |
|---|---|
| Lobby | a team (balance, or last round's team from the memory), ready false, a pawn at a lobby spot (3.1). |
| Lobby countdown (phase Countdown, `bInLobby`) | a team, no pawn (`IsHoldingPawns`, 4.7); put aboard with everyone at 0. A team that had nobody becomes active at 0 and gets its ship (`OnCountdownEnd`, `MyGameMode.cpp:1210-1214`). |
| InProgress | late joiner per SPEC_B B1.3 / B9.7: aboard his ship (practice too, 3.4). |
| Ended | a pawn as in InProgress; the return to the lobby takes him along. |
| During the seamless return | the engine sends him to the destination map (`World.cpp:7161-7167`, `:7612-7618`). |

The session is joinable in the lobby and during the match (join in progress is always on, 5.6).

### 2.3 Play Solo: straight into practice, no lobby (Q-L3)

Play Solo keeps its URL without `Lobby`, so StartPlay starts practice at once. Change from PR B: practice starts
**aboard** team 0's ship (D10, 3.4). The pause menu's Open Lobby still lets friends in (`PauseMenu3.cpp:566-606`); they
join the running practice, which turns into versus as in SPEC_B B1.3. When that match ends the host has a session, so the
game returns to the lobby (2.5).

### 2.4 Start

The host presses START in the lobby panel (or the pause menu's START MATCH, or `Aura.Lobby.Start`). PR B's countdown runs
for `LobbyCountdownSeconds` (5 s) while everyone is still in the lobby zone with lobby rules on. At 0 PR B's start runs
in place: lobby pawns taken back, everyone aboard his own team's deck, waves resumed, Burrowers unpaused, StartSession.
No travel (4.7).

### 2.5 Match end -> back to the lobby

`EndMatch` (`MyGameMode.cpp:1460-1500`) shows the end screen as built. Its timer (`:1493`) calls **`ReturnToLobby()`**
when `WillReturnToLobby()`, else `RestartMatch()` as built. `WillReturnToLobby()` = this map load had a lobby, or the host
has a session now (`UMultiplayerSessionsSubsystem::IsHostingSession`, `MultiplayerSessionsSubsystem.cpp:916`). EndMatch
copies that into the game state's `bLobbyRound`, so every end panel reads "Back to the lobby in n s". The host's panel
adds "Esc > Back to lobby to go now" (the pause menu row, 7.3). `ReturnToLobby()` remembers the teams and travels
seamlessly to this map with `?Lobby=1` (5.3). The race world is rebuilt; everyone comes back into the lobby with the same
teams and rules. `RestartMatch` stays for games without a session (Play Solo, console) and `Aura.Match.Restart`.

### 2.6 Leaving

* A client: pause menu Leave Session (`PauseMenu3.cpp:369-376`, `:887-906`) or the lobby panel's LEAVE (the same
  confirm) -> `LeaveSessionAndOpenLevel(main menu)` (`MultiplayerSessionsSubsystem.cpp:958-974`). The host's `Logout`
  recounts the teams (4.9).
* The host: the same button kicks every client with "The host closed the lobby." first (`SendClientsHostLeft`,
  `PauseMenu3.cpp:862-885`), then leaves.

### 2.7 A separate lobby map (deferred, design kept)

Later a `LobbyMap` setting could name a small map (`L_Lobby`, 3.5) that runs the same `AMyGameMode` in phase Lobby. Its
Start would travel to the match map (`TravelToMatch`, seamless, with `FromLobby=1`); the match map would hold pawns in
WaitingToStart until the arrivals are in (the arrival count of 5.4 is the base for it); the match end would travel back.
Nothing of this is built in this PR (8.7).

---

## 3. L2 The lobby area

### 3.1 Where players stand

Decided once per map load in `AMyGameMode::InitGame`, and again by `Aura.Lobby.Resolve`. Components are registered before
InitGame (`World.cpp:5988` UpdateWorldComponents, `:6034` InitGame), so sweeps work there (verified). New
`ResolveLobbySpawn()`, setting `LobbySpawn` = Auto (default), PlayerStarts or PathStart:

1. **PlayerStarts** (Auto, when ground is found). Candidates: PlayerStarts with `PlayerStartTag == Lobby` (none today),
   else all, skipping `APlayerStartPIE` as `ChoosePlayerStart` does (`MyGameMode.cpp:2816`). From each, a capsule sweep
   straight down `LobbyGroundTraceDepth` (5000 cm) on `ECC_Pawn` with the default pawn's capsule, ignoring pawns.
   A hit counts only when `ImpactNormal.Z >= LobbyGroundMinNormalZ` (0.7) and `UWorld::FindTeleportSpot` accepts the
   pawn there. That is what a pawn could stand on; fog cards and steep pillar sides don't count. Each accepted hit gives a
   **zone box**: the hit actor's `GetComponentsBoundingBox(true)` grown in X and Y by `LobbyZoneMargin` (1500 cm), from
   the box top minus `LobbyZoneDepth` (2000 cm) to the box top plus `LobbyZoneHeight` (6000 cm). Every `AMyHexPlatform`
   **without** SplineDistance whose XY bounds overlap a zone box is merged into it. That picks up the platform above the
   floor without naming it (inferred: its pillars at z 1678 are inside the box). Today: one box of about 110 x 110 m.
   Players spawn through `ChoosePlayerStart` (Lobby-tagged first in the lobby) and PR B's ring search around an occupied
   start (250 / 500 / 750 cm, 8 directions, `MyGameMode.cpp:2906-2938`). Talal's free ship lies inside the box; it is
   locked in the lobby (3.3).
2. **PathStart** (Auto, when no PlayerStart has ground; the case once the floor is deleted). The lobby spot is the path
   platform with the smallest SplineDistance (>= 0) that has tiles. The PCG may build it over several frames: pawns are
   held until it exists (`bLobbyGroundReady`, 4.7), `LobbyTick` polls every 0.25 s, and after 10 s step 3 applies.
   Players are placed with `FindRespawnTile` (`MyGameMode.cpp:3324`), facing along the path. The zone box is that
   platform's bounds grown as above. No ranking happens in the lobby (3.3), so standing there starts nothing.
3. **Nothing found:** the PlayerStart, with a Warning `Lobby: no ground under any PlayerStart and no path platform`.
   There is no zone box, so the zone teleport is off. Only a fall catch runs: a pawn below the PlayerStart's Z minus
   `LobbyZoneDepth` goes back to the PlayerStart (3.2).

Logged: `LogMatch Lobby: spawn PlayerStarts, ground Floor (+ BP_MyHexPlatform_C_1), zone <box>`.

Considered and not taken (unchanged): a lobby on the two team ships' decks (both ships for the whole lobby, a 450 m
teleport per team switch, ships to keep locked in their lanes).

### 3.2 The lobby zone

Server, `LobbyTick` every 0.25 s while `bInLobby`. For each arrived player state's living character (the
`UpdateFallDeaths` loop shape, `MyGameMode.cpp:2591-2667`):

* inside any zone box: clear its timer;
* outside: after `LobbyZoneGraceSeconds` (0.5 s) send it back: `CancelActiveAbilities` (`MyGameMode.cpp:249-275`, ends a
  grapple's root motion), `StopMovementImmediately`, `TeleportTo` a lobby spot (PlayerStarts: the chosen start plus
  `UWorld::FindTeleportSpot`; PathStart: `FindRespawnTile`), `ClientSetRotation`, `ClientLobbyMessage` "Stay in the
  lobby: the match starts when the host presses Start". Log `Lobby: <name> back to the lobby (left the zone)`;
* no zone box (3.1 step 3): only the fall catch.

`MatchTick` skips `UpdateFallDeaths` while `bInLobby` (`MyGameMode.cpp:2465-2468` skips None and WaitingToStart today).
This matters in the lobby countdown, which is phase Countdown. Riders on the locked free ship inside the box are inside.

### 3.3 What runs in the lobby (phase Lobby and the lobby countdown)

| System | Lobby | Where |
|---|---|---|
| Abilities | on | unchanged |
| Damage | **off**: the IncomingDamage branch drops it while `UMyTeamLibrary::IsDamageOff` (`bInLobby` and not `bLobbyDamage`) | `MyAttributeSet.cpp:74-82`, next to the spawn protection test at `:81-82` |
| Pickups | **off**: `AMyEffectActor` collision off on every machine while `bInLobby` (3.4's state); restored at Start | `MyEffectActor.cpp:19` (OnOverlap runs on clients too, no authority test) |
| Knockback | still pushes; the zone brings players back | none |
| Ranking / collapse | **off**: `AMyPlayerState::SetCurrentPlatform` returns while `bInLobby` | `MyPlayerState.cpp:45-67` |
| Path growth | can't happen: the zone is more than 300 m from the path end (u 400 m, SPEC_B Appendix C) | none |
| Sentinel waves | **stopped**: `StopSwarm()` after `Super::StartPlay` (`MyGameMode.cpp:756`); resumed at the round start | `StartPlay`, `BeginRound` |
| Burrowers | **paused**, unpaused at the round start | same (`StopSwarm`, `MyGameMode.cpp:1784-1798`) |
| Swarm difficulty | as built: before Super in StartPlay (`:753`), on player count changes (`:936`) and rules changes (`:1636`) | unchanged |
| Ships | **locked**: `CanBoard` / `CanMount` refuse while `UMyTeamLibrary::AreShipsLocked`. The client's prompt (`FindBoardableAirship`) shows nothing; `TryUseNearest` answers `EAirshipUseRefusal::Locked`, toast "Ships unlock when the match starts". `CanUseShip` stays a pure team test (the grapple's ship hook uses it, `GA_GrappleSwing2.cpp:1777`, `:2148`). | `AirshipPawn.cpp:1673`, `:2533`; `AirshipPilotComponent.cpp:258-294`, `:368-470`; `AirshipTypes.h:124-131`; `MyMatchHUDWidget.cpp:270-284` |
| Team ships | none in phase Lobby; claimed or spawned when the lobby countdown starts (4.7) | `StartCountdown` |
| Fall death | off (the zone replaces it) | `MatchTick` |
| Respawn | a lobby pawn destroyed anyway respawns at a lobby spot (`FindRespawnSpot` checks the lobby first); none during the lobby countdown (held, aboard at 0) | `MyGameMode.cpp:3185` |
| Match HUD | toasts and name tags; the lobby widget shows the rest (6) | `MyMatchHUDWidget.cpp:348` (phase switch) |
| XP | nothing to earn | none |

At Start (4.7) every lobby pawn is replaced and every **timed** active effect (cooldowns, timed buffs) is removed from
the player state's ability system. Infinite effects stay: the secondary attributes and passives belong to the player, not
to the lobby (`MyCharPlayer.cpp:420-437` explains which effects stay on the ASC). So round 1 starts like every later
round.

### 3.4 The match without the floor (audit of PR B)

| PR B dependency on the floor / PlayerStart | Fix |
|---|---|
| Practice spawns at the PlayerStart: `SpawnWaitingPlayers` puts practice into `Others` -> `RestartPlayer` (`MyGameMode.cpp:1380`, `:1423-1426`). Without the floor the pawn falls. | `bStartAboard` covers practice: the test is `Settings->bStartAboard` (was `bVersusRound && bStartAboard`) at `:1380` and in `RestartPlayer` at `:2867`. Practice countdowns hold pawns too (4.7). |
| A respawn before anyone has landed goes to the PlayerStart: the platform search needs `GetLeadSplineDistance() >= 0` (`:3212`), else `:3310-3320` | Match on: with nobody landed, the search runs with PastDistance = -1, so the path's first platforms are candidates (nearest the path start first, own side first in versus). The PlayerStart stays the last resort. |
| A late joiner's "past the lead" spot needs a landing (`:2872`) | The same: no landing needed. |
| The tie-break's team progress uses `CurrentPlatform` even without SplineDistance (`GetTeamProgress` `:2729-2737`) | Skip platforms without SplineDistance. |
| `SpawnTeamShip`'s last fallback is in front of a PlayerStart (`:1909-1961`) | Kept: it runs only with no lane and no `ShipStart<id>` actor, which means no path (L_AirshipTest), not "no floor". |
| SPEC_B flag 5 (the floor's side) and `bAlternateSides` | Still valid while the floor exists; harmless after. |

**Lobby actor state (Q-L1, and pickups).** A state, not a phase edge: `AMyGameState::ApplyLobbyActorState()` runs on
every machine from `NotifyMatchWritten` (server, `MyGameState.cpp:311-315`), `OnRep_Match` (clients, `:317-320`) and
`BeginPlay`. It computes `bShowLobbyActors = MatchPhase == None || bInLobby` and acts only when that differs from what it
applied last:

* actors tagged `UMyMatchSettings::LobbyOnlyActorTag` (default `LobbyOnly`): shown with collision when true, hidden
  without collision when false (`SetActorHiddenInGame`, `SetActorEnableCollision`, runtime only);
* `AMyEffectActor` pickups: collision off when `bInLobby`, on otherwise.

A late joiner's first replicated state is InProgress, so his machine hides the tagged actors at once (the critique's
case). No actor carries the tag today; nothing happens unless Talal adds it. StartupMap is not world-partitioned
(critique, checked), so no tagged actor streams in later.

### 3.5 The separate lobby map (deferred)

The revision 1 plan for `L_Lobby` (40 m floor, lights, 8 `Lobby` PlayerStarts, two team pads, two static `SM_Airship`
meshes, `as_81_lobby_map.py`) is kept as a design only. Not in this PR (8.7).

---

## 4. L3 Game mode, game state, player state

### 4.1 A phase of AMyGameMode (not AMyLobbyGameMode)

Unchanged reasons: one world has one game mode, and the lobby needs what `AMyGameMode` already has (teams, rules,
PreLogin caps, memory, swarm difficulty, the travel URL). The lobby methods go in a new
`Source/Aura/Private/MyGameModeLobby.cpp` (same class, declared in `MyGameMode.h`; `MyGameMode.cpp` is 3431 lines).

`EMyMatchPhase` gains **`Lobby`, appended** (`MyMatchTypes.h:30-40`). Nothing compares phases by order (grep).
`UMyTeamLibrary::IsMatchActive` (`MyTeamLibrary.cpp:35-39`, phase != None) is true in the lobby, which is wanted.

### 4.2 Deciding the lobby (InitGame)

Only when the match is on. The decision reads only the CVar and the URL, so it goes **before** `ParseMatchOptions`
(`MyGameMode.cpp:439`), which needs it (AutoCoopPlayers below); the spawn is resolved after it:

```cpp
// SPEC_B_LOBBY 4.2. Later wins: the CVar Aura.Lobby.Enable (-1 = by URL), then the URL's Lobby=0|1
bLobbyRound = false;
if (CVar Aura.Lobby.Enable >= 0)                            bLobbyRound = CVar > 0;
if (UGameplayStatics::HasOption(Options, TEXT("Lobby")))    ParseBool(ParseOption(Options, "Lobby"), bLobbyRound);  // bad value: Warning, unchanged
ParseMatchOptions(Options);                                  // as built (:439)
if (bLobbyRound) ResolveLobbySpawn();                        // 3.1
```

* `ParseMatchOptions` skips the `AutoCoopPlayers` switch (`MyGameMode.cpp:503-507`) when `bLobbyRound`: Players means
  Max Players there, not the player count. In the lobby the host picks Practice for co-op.
* **ExpectedPlayers = Max Players** with the lobby. `InitGameState` (`:691-702`, write at `:700`) and `StartPlay`
  (`:749`) write `bLobbyRound ? GetLobbyMaxPlayers() : GetNeededPlayers()`. `GetLobbyMaxPlayers()` = the mode's
  maximum (2 for 1v1, 4 for 2v2) when it has one, else the URL's `Players` (`:482-499`). So the header shows "n / Max"
  from the first frame.
* `InitGameState` also writes `bLobbyRound` into the game state.
* Logged: `Match on on StartupMap (...): ..., lobby on (URL Lobby=1), spawn PlayerStarts`.

### 4.3 Replicated state

Game state (`MyGameState.h`; every field `ReplicatedUsing = OnRep_Match`, written by new server setters that call
`NotifyMatchWritten`, `MyGameState.cpp:311-315`):

```cpp
UPROPERTY(ReplicatedUsing = OnRep_Match) bool bLobbyRound = false;     // this match ends in the lobby (end panel, pause label)
UPROPERTY(ReplicatedUsing = OnRep_Match) bool bInLobby = false;        // lobby rules: phase Lobby and the lobby countdown
UPROPERTY(ReplicatedUsing = OnRep_Match) EMyLobbyStartBlock LobbyStartBlock = EMyLobbyStartBlock::None;
UPROPERTY(ReplicatedUsing = OnRep_Match) EMyLobbyStartBlock LobbyConfirmBlock = EMyLobbyStartBlock::None;  // 4.7: the soft
                                       // block the host's Start must confirm, over every block (NotReady not in a rematch)
UPROPERTY(ReplicatedUsing = OnRep_Match) uint8 LobbyNotReady = 0;      // players (not the host) not ready
UPROPERTY(ReplicatedUsing = OnRep_Match) bool bLobbyRematch = false;   // same players on the same teams as last match
// Reused: MatchPhase, MatchRules, Teams[].NumPlayers, ExpectedPlayers (= Max Players), PhaseEndServerTime, RoundIndex
bool IsInLobby() const { return bInLobby; }
bool IsLobbyCountingDown() const { return bInLobby && MatchPhase == EMyMatchPhase::Countdown; }
int32 CountArrivingPlayers() const;   // player states with AMyPlayerState::IsArriving() (5.4), any machine
void ApplyLobbyActorState();          // 3.4
```

Player state (`MyPlayerState.h`; TeamId already replicates, `MyPlayerState.cpp:16-26`, `MyPlayerState.h:91-92`):

```cpp
UPROPERTY(ReplicatedUsing = OnRep_Lobby) bool bLobbyReady = false;
UPROPERTY(ReplicatedUsing = OnRep_Lobby) uint8 RequestedTeam = MyMatch::NoTeam;   // a pending switch (4.4)
UPROPERTY(ReplicatedUsing = OnRep_Lobby) bool bIsHost = false;                     // OnPlayerArrived (5.4)
UPROPERTY(ReplicatedUsing = OnRep_Lobby) bool bArriving = false;                   // 5.4 row 4: set in PostSeamlessTravel
double RequestServerTime = 0.0;                                                   // server only: oldest request first
FSimpleMulticastDelegate OnLobbyChanged;                                          // every machine
void SetLobbyReady(bool); void SetRequestedTeam(uint8); void SetIsHost(bool);     // server, ForceNetUpdate
bool IsArriving() const { return bArriving; }                                     // 5.4: carried here, owner not arrived yet
virtual void CopyProperties(APlayerState* PlayerState) override;                  // Super, then TeamId (5.4)
```

`EMyLobbyStartBlock` (`MyMatchTypes.h`): `None, Arriving, Counting, Traveling, NeedOpponent, NotReady, NeedTwoPerTeam,
Uneven, OneShip`. `EMyLobbySpawn`: `Auto, PlayerStarts, PathStart`. `EMyMatchEvent` gains, appended: `LobbyCancelled,
LobbyTeamChanged, LobbyRulesChanged, LobbyReturn` (the lobby countdown sends PR B's `Countdown` event).

### 4.4 Teams in the lobby

* **On join:** `AssignTeam` as built (`MyGameMode.cpp:807-851`): the remembered team if it fits, else the smaller team,
  a tie to team 0. Practice: team 0. New optional parameter `PreferredTeam` (default 255), tried before the memory with
  the same cap test; the seamless arrival passes the copied TeamId (5.4).
* **Switching** (`RequestLobbyTeam(Player, Target)`, `bLobbyTeamSwitch` default true):

```cpp
if (!IsInLobby() || IsLobbyCountingDown())       refuse: "Teams are locked while the match starts"
if (MatchRules.TeamMode == EMyTeamMode::Practice) refuse: "Practice: everyone is on one ship"
const uint8 From = Player->GetTeamId();
if (Target == From || Target >= MyMatch::NumTeams) { Player->SetRequestedTeam(MyMatch::NoTeam); return; }   // cancel
RecountTeams(); const int32 A = Count[From], B = Count[Target], Cap = GetTeamCap();   // Cap 0 = none
if ((Cap == 0 || B < Cap) && B < A) { MoveLobbyTeam(Player, Target); return; }       // teams stay within one
for (Other on Target with Other->GetRequestedTeam() == From, oldest RequestServerTime first)
    { MoveLobbyTeam(Other, From); MoveLobbyTeam(Player, Target); return; }            // a swap
Player->SetRequestedTeam(Target);   // pending: "You swap when an ORANGE player asks for BLUE"
```

  `MoveLobbyTeam` sets TeamId, clears RequestedTeam, recounts, keeps the ready flag, sends `LobbyTeamChanged`.
* **Host move** (`MoveLobbyPlayer`, host only). Target team under its cap: move, no balance rule (the host may build a
  3v1; Start then warns, Uneven). Target team at its cap (full 1v1 or 2v2): **swap** with one player of the target team:
  the one whose RequestedTeam is the mover's team first, else the one who joined last (`PlayerArray` order; AGameStateBase
  appends there). So the host can always arrange a full 1v1 or 2v2.
* **Team mode change** in the lobby: `RebalanceLobbyTeams()` clears every request, sets every TeamId to 255 and runs
  `AssignTeam` for each player in `PlayerArray` order, so the memory and join order apply again.
* **Leave:** the counts drop (4.9). Requests aimed at the leaver are never answered.

### 4.5 Ready

A ready button per client (`SetLobbyReady`). The host has no flag: he is ready when he starts. `LobbyNotReady` is the
count shown on the Start button. Shown, not required, by default (Q-L4): the host may start anyway after a second click;
`bLobbyRequireReady` makes NotReady a hard block.

* **Clearing.** With `bLobbyRulesClearReady` (default true), only a change of the team mode or of Max Players clears
  every flag ("Teams changed: press READY again"). Lives, swarm, time limit and the flags never do. A team move keeps
  them.
* **Rematch.** `bLobbyRematch` is true when this load came from a return (`RoundIndex > 0`), every team player is found in
  the match memory with his current team, and the memory holds no one else (`UMyMatchMemorySubsystem::FindTeam`,
  `GetNumRemembered`, `MyMatchMemorySubsystem.h:32`, `:44`). Then NotReady needs no second click. The host already
  accepted these teams last match. Without valid net ids (PIE with the NULL subsystem) it stays false.

### 4.6 Rules in the lobby (host only)

`ApplyLobbyRules(const FMyMatchRules& NewRules, int32 MaxPlayers, FText& OutWhy)`:

1. Refused outside the lobby or while counting down.
2. N = arrived players. `ModeMax` = `UMyTeamLibrary::GetTeamModeMaxPlayers` (2 for 1v1, 4 for 2v2, 0 otherwise; the
   numbers of `UMainMenu3::GetTeamModeMaxPlayers`, `MainMenu3.cpp:567-578`, which forwards to it). Refused when
   `ModeMax > 0 && N > ModeMax` ("1v1 has room for 2: 3 players are in") or `MaxPlayers < N`. With `ModeMax > 0`,
   MaxPlayers = ModeMax.
3. The team mode applies **at once in the lobby**: `ApplyRules` defers it whenever the phase isn't None
   (`MyGameMode.cpp:1616-1620`); add `&& !IsInLobby()`. When it changed, `ApplyRules` itself runs `RebalanceLobbyTeams()`
   and clears the ready flags, so every caller gets the same result.
4. `ExpectedPlayers = MaxPlayers` on the game mode and the game state.
5. Ready flags cleared when MaxPlayers changed (the team mode case is step 3; 4.5). Event `LobbyRulesChanged`.
6. When hosting a session: one `UMultiplayerSessionsSubsystem::AdvertiseMatch(TeamMode, Difficulty, MaxPlayers,
   /*bInMatch*/false)` per accepted request. It reads `GetCurrentHostSettings` (`MultiplayerSessionsSubsystem.cpp:892`),
   sets `Rules = UMainMenu3::GetRuleSetForTeamMode`, `Difficulty`, `NumPublicConnections`, `bInMatch`, and calls
   `UpdateHostSettings` (`:823-855`). The pause menu's Open Lobby advertises a running match the same way
   (`PauseMenu3.cpp:576-587`).

The widget sends one request 0.75 s after the last edit (6.4), so a host changing three settings sends one request and
one session update. In the lobby the console's `Aura.Match.Rules` calls `ApplyLobbyRules` with the current Max Players,
so its refusals are the widget's. Everything else in `FMyMatchRules` goes through the existing `ApplyRules` (`MyGameMode.cpp:1609-1669`).

### 4.7 Start

**StartPlay with the lobby** (`MyGameMode.cpp:741-805`, after the tick timers at `:773-774`, before the practice /
versus split at `:776`):

```cpp
if (bLobbyRound)
{
    StopSwarm();                                  // after Super (:756): the spawners armed themselves in BeginPlay
    MyGameState->SetInLobby(true);
    MyGameState->SetMatchPhase(EMyMatchPhase::Lobby, 0.0);
    LobbyStartServerTime = GetServerTime();       // the Arriving block's timeout (5.4)
    GetWorldTimerManager().SetTimer(LobbyTickTimer, this, &ThisClass::LobbyTick, 0.25f, true);
    AdvertiseIfHosting(/*bInMatch*/false);        // 5.6
    SpawnLobbyPlayers();                          // every controller without a pawn that PlayerCanRestart allows
    EvaluateTeams();
    return;
}
```

`IsHoldingPawns` (`MyGameMode.cpp:657-673`) becomes:

```cpp
case EMyMatchPhase::None:           return bLobbyRound || !IsPracticeStart() || Settings->bStartAboard;   // StartPlay places them
case EMyMatchPhase::Lobby:          return !bLobbyGroundReady;          // PathStart before its platform exists; true at once otherwise
case EMyMatchPhase::WaitingToStart: return true;
case EMyMatchPhase::Countdown:      return bCountdownVersus || bPracticeToVersus || Settings->bStartAboard;   // lobby countdown too
default:                            return false;
```

The host logs in before StartPlay (`MyGameMode.cpp:785-788`), so in phase None he is held and `SpawnLobbyPlayers` gives
him his lobby pawn. With `bLobbyRound` decided in InitGame, the listen-PIE quirk of `:785-802` (the host looked like a
standalone practice player) can't give him a pawn early. With practice and `bStartAboard`, nobody gets a pawn during a
practice countdown: the camera waits 5 s, as in a versus countdown.

`RestartPlayer` (`:2846`) while `bInLobby` in phase Lobby: PathStart places the pawn at a lobby spot; PlayerStarts uses
`Super` plus the ring search. `ChoosePlayerStart` (`:2793-2844`) prefers `Lobby`-tagged starts in the lobby and skips
them in the match.

**Start blocks** (`GetLobbyStartBlock(int32& OutNotReady)`, written to the game state by `LobbyTick` when they change):

| Block | When | Kind |
|---|---|---|
| Arriving | a player is still loading after a seamless return (`CountArrivingPlayers() > 0`), until `LobbyArrivalTimeout` (45 s) after StartPlay | hard |
| Counting | the lobby countdown runs (the button shows CANCEL) | hard |
| Traveling | a return is pending (`bRestarting`) | hard |
| NeedOpponent | 1v1 or 2v2 with a team at 0 players | hard |
| NotReady | a client isn't ready | soft (hard with `bLobbyRequireReady`; no second click with `bLobbyRematch`) |
| NeedTwoPerTeam | 2v2 with a team at 1 (plays 2v1 or 1v1) | soft |
| Uneven | the teams differ by more than one (host moves) | soft |
| OneShip | Auto with 2 or more players all on one team (plays co-op, one ship) | soft |

Practice has no hard block except Arriving / Counting / Traveling. Auto with one player starts practice.

**`StartFromLobby(bool bForce, FText& OutWhy)`** (host). A hard block refuses. A soft block refuses without `bForce`
("Click again to start anyway"), except NotReady with `bLobbyRematch`. The soft block that needs the second click is
`GetLobbyConfirmBlock(Mask, bRematch)` over every block (`MyGameModeLobby.cpp:878`); `UpdateLobbyState` replicates it as
`LobbyConfirmBlock`, so the widget asks for the same block the server refuses (a rematch with NotReady and
NeedTwoPerTeam confirms NeedTwoPerTeam). Otherwise:

```cpp
StartCountdown(/*bForced*/true, /*DelayOverride*/Settings->LobbyCountdownSeconds, /*bFromLobby*/true);
```

`StartCountdown` (`MyGameMode.cpp:1059-1142`) gains `float DelayOverride = -1.f` (-1 = `MatchStartDelay`, `:1120`) and
`bool bFromLobby = false`. With `bFromLobby` its ship step is `ClaimOrSpawnShips(bCountdownVersus,
/*bRemoveUntaggedPlaced*/false)` (`:1125`; new parameter on `ClaimOrSpawnShips`, `:1842-1898`, guarding `:1875`).
Everything else is PR B's: active teams, lane sides, handicap, lives, phase Countdown with `PhaseEndServerTime`, the
`Countdown` event, the timer for `OnCountdownEnd`. The ships are spawned 5 s before anyone boards, as in every PR B start,
and wait in their lanes (the lane treats Countdown as not started, `AirshipLaneComponent.cpp:871`). `ProtectShip` adds
the countdown to their protection (`MyGameMode.cpp:2122-2126`). `bInLobby` stays true, so the zone, damage off, locks
and the ranking gate hold during the 5 s. Talal's untagged free ship is removed only at the end, when `OnCountdownEnd`
calls `ClaimOrSpawnShips(bVersusRound)` (`:1236`) as built, because that removal can't be undone on a cancel.

**`CancelLobbyStart(Reason)`** (host CANCEL, or automatic): only while `IsLobbyCountingDown()`. Clears `CountdownTimer`;
for both teams `RemoveTeamShip(Team, "lobby start cancelled")` and `bActive = false` (`RemoveTeamShip` releases a
claimed placed ship and destroys a spawned one, `MyGameMode.cpp:2060-2108`); `bCountdownVersus = bHostForcedStart =
false`; `SetMatchPhase(Lobby, 0.0)`; event `LobbyCancelled`. Then it gives lobby pawns back (review rows 3 and 5): the
countdown held new pawns and dropped respawns, so a dead pawn gets `ScheduleRespawn` and a controller without one gets
`SpawnLobbyPlayers` (`PollLobbyGround` does it later while PathStart still waits). Log `Lobby: after the cancel n lobby
pawn(s) spawned, m respawn(s) scheduled`.

**During the lobby countdown.** `EvaluateTeams`' Countdown branch (`MyGameMode.cpp:947-976`) first checks: if
`IsLobbyCountingDown()` and the start block turned hard (a 1v1 / 2v2 team emptied), `CancelLobbyStart("ORANGE left")`
and stop. Otherwise PR B's code runs: an emptied team in Auto goes inactive and loses its ship, and the forced start goes
on (`bHostForcedStart` skips `BackToWaiting`, `:972-974`, `:1226-1229`). `BackToWaiting` (`:1276-1296`) must never run
in a lobby round: it calls `CancelLobbyStart` instead when `IsInLobby()`. Rules are locked. `OnCountdownEnd` re-checks
the hard block first.

**`BeginRound`** (`:1252-1274`) gains, before `SpawnWaitingPlayers` (`:1273`):

```cpp
if (MyGameState->IsInLobby())
{
    TakeBackLobbyPawns();            // every player controller's pawn: CancelActiveAbilities, RemoveTimedEffects,
                                     // UnwatchPlayerPawn, UnPossess, Destroy (StartPlay's take-back, :789-802, as a helper)
    // every player state: SetLobbyReady(false), SetRequestedTeam(255) (they mean something in the lobby only)
    MyGameState->SetInLobby(false);  // ships unlock, damage and pickups on, ranking on, LobbyOnly actors hidden
    GetWorldTimerManager().ClearTimer(LobbyTickTimer);
    ResumeSwarm();                   // StartWaves(false) on every wave spawner, Burrowers unpaused
}
StartSessionIfHost();                // every round (5.6)
```

`RemoveTimedEffects(ASC)` removes every active effect with a duration above 0 (a `FGameplayEffectQuery` with a custom
match on `FActiveGameplayEffect::GetDuration() > 0`): cooldowns and timed buffs. Then `SpawnWaitingPlayers` puts
everyone aboard. The new pawn refills Health and Mana (`InitAbilitySystemAfterRespawn` applies `VitalAttributesEffect`,
`MyCharPlayer.cpp:420-437`). Practice turning into versus (B1.3) never has `bInLobby`, so it keeps its pawns, as built.

### 4.8 RPCs and authority

On `AMyPlayerController2` (all Server, Reliable, validated on the server):

```cpp
UFUNCTION(Server, Reliable) void ServerLobbySetReady(bool bReady);
UFUNCTION(Server, Reliable) void ServerLobbyRequestTeam(uint8 TeamId);                       // 255 = cancel a request
UFUNCTION(Server, Reliable) void ServerLobbySetRules(const FMyMatchRules& Rules, int32 MaxPlayers);   // host
UFUNCTION(Server, Reliable) void ServerLobbyStart(bool bForce);                              // host
UFUNCTION(Server, Reliable) void ServerLobbyCancelStart();                                   // host
UFUNCTION(Server, Reliable) void ServerLobbyMovePlayer(APlayerState* Player, uint8 TeamId);  // host
UFUNCTION(Client, Reliable) void ClientLobbyMessage(const FText& Text);                       // refusals, zone, swaps (rare)
```

The host check is `AMyGameMode::IsLobbyHost(const APlayerController* PC)`: `PC->IsLocalController() && GetNetMode() !=
NM_Client`, the condition PostLogin uses (`MyGameMode.cpp:226`). On a listen server the host's Server RPCs run locally, so
the host's widget takes the same route as everyone else's. A refusal answers with `ClientLobbyMessage(OutWhy)`. The pause
menu's direct calls on the game mode (`PauseMenu3.cpp:431-443`, `:495-503`) stay: they run on the host only.

### 4.9 Leaving, and the host leaving

* **A client leaves:** `Logout` -> `EvaluateTeams(Leaving)` (`MyGameMode.cpp:293-320`, `:913-1005`). The lobby branch
  recounts, refreshes the start block, and cancels a running lobby countdown when the block turns hard.
* **The host leaves on purpose:** clients are kicked with the host-left reason, then the host goes to the main menu
  (2.6). `ClientWasKicked` keeps the reason for the menu (`MyPlayerController2.h:224`, `.cpp:443-456`).
* **The host crashes or loses connection:** the subsystem destroys the session and keeps "Lost connection to the host."
  (`MultiplayerSessionsSubsystem.cpp:1219-1282`); the engine sends the client to the default map with `?closed`
  (`UnrealEngine.cpp:15512`, `:15527`), MM_MainMenu (`DefaultEngine.ini:2`). No host migration (SPEC_B 0.2).
* The team memory is host-only; it goes with the host.

---

## 5. L4 Travel and the session

### 5.1 The blocker: a hard travel drops Steam clients (verified chain, not run)

1. The game net driver is `SteamSocketsNetDriver` with `IpNetDriver` as the fallback (`DefaultEngine.ini:106`). PIE
   runs without Steam, so PIE uses the IP driver (inferred; the PR B PIE runs had no valid net ids, SPEC_B B1.6).
2. A hard ServerTravel: `ProcessServerTravel` calls `StartToLeaveMap` (`GameModeBase.cpp:480`), sends every remote player
   `ClientTravel(URL, TRAVEL_Relative, bSeamless=false)` (`:423`) and sets `World->NextURL` (`:517`). A listen server
   switches only when `NextSwitchCountdown` runs out (`UnrealEngine.cpp:15943-15955`): `ServerTravelPause`, 4 s for the
   Steam driver (`BaseEngine.ini:2535`), set when the world started listening (`World.cpp:7992`).
3. The client travels at once: `ClientTravelInternal` -> `SetClientTravel` (`PlayerController.cpp:5753`) -> Browse to the
   same host -> a new connection, while the host is still in the old world.
4. While `NextURL` is set, the host answers `Ignore` (`World.cpp:7089-7093`).
5. The IP driver drops only that packet; the client's handshake retries until the new map listens
   (`IpNetDriver.cpp:1263-1279`). That is why PIE and PR B's M7.1 restart pass.
6. SteamSockets closes every connection that isn't `Accept`ed: "Connection rejected" (`SteamSocketsNetDriver.cpp:470`,
   `:540`).
7. The client's pending game sees `USOCK_Closed` (`PendingNetGame.cpp:536-539`) -> `PendingConnectionFailure`, no retry
   (`UnrealEngine.cpp:16017`) -> the project's handler destroys the client's session and keeps an error for the menu
   (`MultiplayerSessionsSubsystem.cpp:1219-1282`).

So on Steam every hard travel with clients drops them: revision 1's return to the lobby, and PR B's own `RestartMatch`
(`MyGameMode.cpp:1562`). Revision 1's evidence (`MainMenu3.cpp:1314`) was a travel without clients.

### 5.2 The options compared

| | A. Seamless travel (chosen) | B. In-place reset, no travel | C. Hard travel + client rejoin window |
|---|---|---|---|
| Steam connection | stays: the net driver moves to the new world (`World.cpp:8526-8565`) | stays | rejected (5.1); the client must join again |
| The race world | loads fresh, as today's reload: path, PCG, platforms, bridges, swarm, Burrowers, ships, pickups | every system needs a new Reset: the path spawner builds only in BeginPlay (`MyHexPathSpawner.cpp:45-87`) and destroys passed segments; collapse only goes up (`MyGameState.cpp:125-147`); pillar breaks, bridge collapses, minimap bake, atmosphere per platform; Mass sentinels and wave progress; Burrower pawns; wrecks; Talal's free ship is `Destroy`ed at a versus start (`MyGameMode.cpp:1837`) and can't come back; XP and level | loads fresh |
| New code | 5.4: one arrival routine, `StartToLeaveMap`, `CopyProperties`, one pilot-input fix, an arrival count | about 10 Reset paths in systems built without one, each untested | a retry loop in the sessions subsystem that keeps the session through `PendingConnectionFailure`; each retry is a fresh PreLogin |
| PIE | hard by default (the IP driver works); seamless with `net.AllowPIESeamlessTravel=1` (`GameModeBase.cpp:503-511`) | same everywhere | PIE can't show the Steam failure |
| Time to the lobby | the load only: seamless has no `ServerTravelPause` (`GameModeBase.cpp:520-524`) | none | 4 s + reconnect + load |
| Engine support | the standard multiplayer travel; joins during it are redirected (`World.cpp:7161-7167`, `:7612-7618`) | none | none |

Decision: **A**. B rebuilds by hand what a map load gives for free, in systems that were never meant to reset. C keeps
the failure and patches around it.

### 5.3 ReturnToLobby and RestartMatch

`RestartMatch` (`MyGameMode.cpp:1502-1567`) becomes `TravelToRound(bool bLobby)`; `RestartMatch()` =
`TravelToRound(false)`, `ReturnToLobby()` = `TravelToRound(true)`:

```cpp
// Guards as RestartMatch (:1507-1510); timers cleared (:1512-1514)
// Round  = +1 after a versus round, unchanged after practice; RememberTeams first (:1516-1529)
if (bLobby) EndSessionIfHost();                                   // 5.6, when InProgress
Options = BuildRulesOptions(MatchRules, NextTeamMode)             // :615-620
        + "?Players=" + (bLobby ? GetReturnLobbyMaxPlayers(n) : <players that played>, as :1533-1544)
        // GetReturnLobbyMaxPlayers: GetLobbyMaxPlayers, at least the players in, and after a round that was not a lobby
        // round (Play Solo + Open Lobby) at least the hosted session's slots (review rows 2 and 6)
        + "?Match=1?Round=<n>" + (bLobby ? "?Lobby=1" : "")
        + (Settings->bSeamlessTravel ? "?SeamlessTravel" : "");   // engine option, GameModeBase.cpp:494-497
if (bLobby) MulticastMatchEvent(LobbyReturn);                     // end panel: "Back to the lobby..."
Standalone: OpenLevel as :1554-1558.  Else: ServerTravel(Map + "?listen" + Options, /*bAbsolute*/true) as :1560-1566
```

* The option goes on the URL, not on `bUseSeamlessTravel`, so only these two travels change. `GlobalDefaultGameMode` is
  BP_MyGameMode (`DefaultEngine.ini:4`) and `MatchMaps` is empty by default (`MyMatchSettings.h:85-87`), so the class
  flag could also reach other maps' travels.
* `bAbsolute = true` stays. Remote clients always get `TRAVEL_Relative` with the seamless flag (`GameModeBase.cpp:423`),
  which is what client-side seamless travel needs (`PlayerController.cpp:5742-5745`). The server strips `?listen` from
  the clients' URL (`GameModeBase.cpp:404-419`).
* PIE turns the option off and travels hard unless `net.AllowPIESeamlessTravel=1` (`GameModeBase.cpp:503-511`). Both
  arrival paths therefore must work (5.4).
* Log: `Match: back to the lobby, round <n>, <seamless | hard>: <url>`.
* The comments that say "non-seamless" are updated: `MyMatchMemorySubsystem.h:13-21` and `MyGameMode.cpp:1534-1535`.

### 5.4 What a seamless arrival skips, and what this project adds

The engine path (verified) and the project's gaps:

| # | Engine | Project gap | Fix |
|---|---|---|---|
| 1 | `StartToLeaveMap` runs first (`GameModeBase.cpp:480`). The old game mode, game state and game session are kept into the transition world (`:548-556`). Timers live on the game instance's timer manager (`World.cpp:8056-8059`), so they keep firing there. | `MatchTick`, `HealthTick`, `RestartTimer`, `CountdownTimer`, `LobbyTickTimer`, respawn timers would run in a world without a path or lanes. | `AMyGameMode::StartToLeaveMap()` override: `GetWorldTimerManager().ClearAllTimersForObject(this)`, `PendingRespawns.Reset()`, `StopSwarm()`, `bRestarting = true`, remove test bots (Appendix L-B). Runs for hard travel too. |
| 2 | No TransitionMap: an empty world of the same type (`World.cpp:8367-8370`). The old world is collected before the destination loads (`:8943`), so the same map can be the destination. `CreateWorld` initialises world subsystems for it (`World.cpp:2817`, `:2447`); it never begins play. | The swarm, lane, airship and Burrower world subsystems exist for a few frames in an empty world. | Nothing expected (inferred); the PIE smoke test (LM1.13) is the check. |
| 3 | The destination's game mode is new: `SetGameMode(PendingTravelURL)` -> `InitGame` with the URL's options (`World.cpp:8992`, `:6034`). | none: `Lobby`, `Round` and the rules are read as on a hard load (4.2). | - |
| 4 | The new game state adds every player state in the world, the carried old ones too (`GameStateBase.cpp:71-74`). Carried actors have `bActorSeamlessTraveled` (`World.cpp:8833`, `Actor.h:566`, public). An old player state stays until its owner arrives. | They would be counted as players before they have loaded. | `AMyPlayerState::IsArriving()` = a replicated `bArriving`, on every machine. Not `bActorSeamlessTraveled`: `InitializeActorsForPlay` (`World.cpp:9021`) -> `ULevel::InitializeNetworkActors` clears it on every actor (`Level.cpp:3709`) before `InitGame`, `PostSeamlessTravel` and `StartPlay`. `AMyGameMode::PostSeamlessTravel` marks every carried player state arriving before `Super` replaces those whose owners have loaded; the replacement never has the flag (not copied), the carried one is destroyed when its owner arrives. `RecountTeams` (`MyGameMode.cpp:853-890`) skips arriving player states. The lobby rows show them as LOADING (6.4). Start block Arriving (4.7). PR B's WaitingToStart auto-start uses the same counts, so it waits for the arrivals too. |
| 5 | Players already loaded (the host) are handled in `PostSeamlessTravel` before `BeginPlay` (`World.cpp:9094`, `:9098`; `GameModeBase.cpp:644-672`). Clients come later through `ServerNotifyLoadedWorld` (`PlayerController.cpp:697-726`). | none: the host is held in phase None and gets his pawn in StartPlay, as on a hard load (4.7). | - |
| 6 | `HandleSeamlessTravelPlayer` (`GameModeBase.cpp:607-641`): a new controller of `PlayerControllerClass` with a new player state; `SeamlessTravelFrom` resets the old player state, copies it with `CopyProperties`, destroys it (`PlayerController.cpp:3652-3667`); then `InitSeamlessTravelPlayer` (`GameModeBase.cpp:811-836`), `GenericPlayerInitialization` (`:973-998`, the HUD) and `HandleStartingNewPlayer`. It never calls PreLogin, Login, InitNewPlayer, PostLogin or OnPostLogin (`:1001-1048`). | `AssignTeam` and `EvaluateTeams` live in `InitNewPlayer` (`MyGameMode.cpp:704-739`); the host flag goes in PostLogin; the airship pilot component is added only on `GameModePostLoginEvent` (`AirshipSubsystem.cpp:49`, `:91-97`; plus PCs present at BeginPlay, `:68-79`). | Override `InitSeamlessTravelPlayer` (protected virtual, `GameModeBase.h:567`): keep the team (row 7), call `Super` (it picks the start spot, so the team must be set first), then `OnPlayerArrived(PC, /*bSeamless*/true)`. |
| 7 | `APlayerState::CopyProperties` copies score, ping, player id, unique id, name, start time (`PlayerState.cpp:116-125`). `Reset` on the old player state only zeroes the score (`:230-235`). `OverrideWith` is called only for AGameMode's inactive players (`GameMode.cpp:687-759`); AMyGameMode is an AGameModeBase (`MyGameMode.h:27`). | TeamId would be lost. | `AMyPlayerState::CopyProperties`: `Super`, then `SetTeamId(TeamId)` on the new one. Not the ready flag, the host flag or the platform. No `Reset` override may clear TeamId. `OverrideWith`: not needed. The seamless team keep: `Kept = PS->GetTeamId(); PS->SetTeamId(255); AssignTeam(PS, PS->GetUniqueId(), /*PreferredTeam*/Kept)`, so the mode and caps of the new round still apply (a team mode changed to Practice puts everyone on team 0). |
| 8 | ASC | The new player state has a new ASC (`MyPlayerState.cpp:113-117`), `bAbilitiesGiven` false, so the first pawn gives attributes, startup and passive abilities (`MyCharPlayer.cpp:364-392` server, `:302-334` client). | none: the same as a hard load. XP, level and points start over in both (not copied). |
| 9 | HUD: the old world's viewport widgets are removed at its teardown (`World.cpp:8679` -> `OnWorldBeginTearDown`, `GameViewportSubsystem.cpp:39`, `:301-322`); `ClientSetHUD` from `GenericPlayerInitialization` gives the new controller a new HUD; the old HUD goes with the old controller (`PlayerController.cpp:1633-1654`). | none: `AMyHUD::BeginPlay` adds the match and lobby widgets (`MyHUD.cpp:25-30`); the pawn's `PossessedBy` / `OnRep_PlayerState` calls `InitOverlay` (`MyCharPlayer.cpp:395-400`, `:336-342`). | - |
| 10 | Input: the new controller's `BeginPlay` sets game-only input (`MyPlayerController2.cpp:186`); `SetupInputComponent` adds `IMC_PlayerInputMappingContext` (`:143`). Enhanced Input mappings live on the local player, which both controllers share. | On a client the old controller (and its pilot component) can end play after the new pilot component added `IMC_AirshipBoard`; `TeardownLocalInput` then removes the shared context (`AirshipPilotComponent.cpp:57-69`, `:152-176`) and F stops working. A hard load destroys the old world first, so it never happened. | In `TeardownLocalInput`, remove the mapping only when `MappingSubsystem->GetLocalPlayer()->PlayerController == GetPlayerController()`. Pop and destroy its own input component as before. |
| 11 | Clients keep every replicated non-startup actor through the transition until the server closes its channel (`World.cpp:8745`). | Stale pawns, ships or platforms on a client would show in the lobby (inferred: the closes arrive as for any destroyed actor). | LM1.13 compares the client's platform and ship counts with the server's. |
| 12 | Old controllers are swapped, not logged out: their player state is cleared first (`PlayerController.cpp:3661-3662`), and `AController::Destroyed` logs out only with a player state (`Controller.cpp:597-607`). A client that drops while loading is logged out with its old player state. | none: `Logout` -> `EvaluateTeams(Leaving)` as today. | - |
| 13 | Spawning: `PlayerCanRestart` -> `CanRestartPlayer` needs `HasClientLoadedCurrentWorld` and no `PendingSwapConnection` (`GameModeBase.cpp:1203-1212`, `PlayerController.cpp:3343-3346`). | none: `SpawnLobbyPlayers` and `SpawnWaitingPlayers` (`MyGameMode.cpp:1366-1371`) ask `PlayerCanRestart`, so a controller still loading gets no pawn. | `SpawnLobbyPlayers` uses the same test. |

**`OnPlayerArrived(APlayerController* PC, bool bSeamless)`**, called from `PostLogin` (`MyGameMode.cpp:221-241`, after
`Super`) and from the `InitSeamlessTravelPlayer` override:

* `SetIsHost(IsLobbyHost(PC))`;
* `UAirshipSubsystem::EnsurePilotComponent(PC)` (public, idempotent, `AirshipSubsystem.h:78-79`, `.cpp:99-109`);
* seamless only: `EvaluateTeams()` (the hard path keeps it in `InitNewPlayer`, `MyGameMode.cpp:733-736`, because PR B
  needs it before `PlayerCanRestart`; `HandleStartingNewPlayer` runs after `InitSeamlessTravelPlayer`, so the order holds);
* log `Team: <name> arrives (<hard | seamless>), team <id>, phase <phase>`.

`PostLogin` keeps its StartSession call only when `!bLobbyRound` (`:226-238`; 5.6).

### 5.5 PIE versus a packaged Steam game

| | Travel | Arrival path | Shows the Steam blocker |
|---|---|---|---|
| PIE listen (default) | hard (`GameModeBase.cpp:503-511`) | Login / InitNewPlayer / PostLogin; team from the memory, else join order | no (IP driver) |
| PIE listen, `net.AllowPIESeamlessTravel 1` | seamless | `InitSeamlessTravelPlayer`; team from `CopyProperties` | no (IP driver) |
| Packaged, Steam, two machines | seamless | `InitSeamlessTravelPlayer` | yes: the real test (8.5) |

### 5.6 The session (Steam lobby or EOS session)

* **StartSession.** PostLogin calls it today (`MyGameMode.cpp:226-238`). With the lobby it skips it; `BeginRound` calls
  `StartSessionIfHost()` every round. Steam starts only from Pending or Ended (`OnlineSessionInterfaceSteam.cpp:399-433`,
  test at `:406-408`); EOS the same (`OnlineSessionEOS.cpp:1734`, test at `:1742-1743`).
* **EndSession.** New `UMultiplayerSessionsSubsystem::EndSession()` (`SessionInterface->EndSession(NAME_GameSession)`
  when InProgress, with a delegate and a log). Called by `EndMatch` and by `ReturnToLobby` (a BACK TO LOBBY during a match
  skips EndMatch). Both engines end only from InProgress (`OnlineSessionInterfaceSteam.cpp:498-510`, test at `:507`;
  `OnlineSessionEOS.cpp:1955`, `:1964`).
* **Ending.** Steam's EndSession is asynchronous: the state is Ending until its task completes
  (`OnlineSessionInterfaceSteam.cpp:555-574`, state at `:567`). The existing guard handles InProgress and Starting only
  (`MultiplayerSessionsSubsystem.cpp:402-411`). Add: while Ending, remember the request and start in the EndSession
  completion delegate.
* **What browsers see.** Steam's Start and End only change the local state (`OnlineSessionInterfaceSteam.cpp:406-414`).
  New advertised key `AuraSessionKeys::InMatch` (int 0 / 1) next to the others (`MultiplayerSessionTypes.h:13-23`):
  `FAuraHostSettings::bInMatch` -> `ApplyHostSettings` (`MultiplayerSessionsSubsystem.cpp:1166-1182`) ->
  `MakeSessionInfo` (`:1184-1217`) -> `FAuraSessionInfo::bInMatch`. The session row adds "IN LOBBY" / "IN MATCH" to its
  `RulesText` (`SessionEntry3.h:57-58`). Written by `AdvertiseMatch(..., bInMatch)`: false in the lobby's StartPlay,
  true in `StartSessionIfHost`.
* **Joinability.** Join in progress is always on (`MultiplayerSessionTypes.h:72`; `MultiplayerSessionsSubsystem.cpp:136`).
  Steam lobbies are joinable while it is on and there is room (`OnlineSessionAsyncLobbySteam.cpp:447`, `:657`). On EOS the
  flag blocks joins once the session has started (`OnlineSessionEOS.cpp:1378-1387`). A future "no join in progress"
  option must toggle the flag with UpdateSession at Start.
* **The pause menu's Open Lobby** on a running Play Solo game calls StartSession at once (`PauseMenu3.cpp:944-947`). Kept:
  that game is a running match. Its end then returns to the lobby (2.5).

### 5.7 Loading screen (deferred)

During a seamless return the clients see the empty transition world (black) for the load. No loading screen in this
PR. Later: a game-instance subsystem adds a "LOADING" widget with `bAutoRemoveOnWorldRemoved = false` on
`FWorldDelegates::OnSeamlessTravelStart` and removes it on `PostLoadMapWithWorld` (`World.cpp:9100`).

### 5.8 The separate lobby map's travel (deferred)

With `L_Lobby` later: Start = a seamless travel to the match map with `FromLobby=1`; the match map holds pawns in
WaitingToStart until `CountArrivingPlayers() == 0` or `LobbyArrivalTimeout`; the match end travels back. Nothing of this
is built now.

---

## 6. L5 Lobby UI

### 6.1 Where and when, and the input mode

* `AMyHUD` gets `LobbyWidgetClass` (`TSubclassOf<UMyLobbyWidget>`, EditAnywhere), set on BP_MyHUD by as_78. It is added
  in `BeginPlay` next to `AddMatchWidget` (`MyHUD.cpp:25-30`), the same way (`UGameViewportSubsystem::AddWidgetForPlayer`,
  `:43-73`), ZOrder 5, local controllers only, while the match is on. It collapses itself while `!IsInLobby()`.
* **Panel open:** remember whether the cursor was shown, `FlushPressedKeys`, `FInputModeUIOnly` focused on the panel,
  cursor on (as `UPauseMenu3::OpenMenu`, `PauseMenu3.cpp:175-212`).
* **Panel closed (`ClosePanel`):** `FInputModeGameOnly` with `SetConsumeCaptureMouseDown(false)`, cursor back as it was
  (as `UPauseMenu3::CloseMenu`, `:214-241`, the mode `AMyPlayerController2::BeginPlay` sets, `MyPlayerController2.cpp:179-186`).
  Only the compact strip shows, except during the lobby countdown: the match HUD's bar is drawn there then, and the
  large countdown and its hint show instead (review row 15).
* **Opens by itself** once per map load, when the local player's lobby pawn first exists and the phase is Lobby (not
  during the countdown).
* **Closes by itself on every machine** (major M2): (1) when the lobby countdown starts (`IsLobbyCountingDown()` turns
  true); (2) when `IsInLobby()` turns false, if still open; (3) in `NativeDestruct`. During the 5 s players have game
  input and can move; the large "MATCH STARTS IN n" and a hint stay ("Esc: lobby"; the host's: "Esc: lobby (CANCEL)").
* **Esc in the lobby** opens or closes the panel instead of the pause menu: `AMyPlayerController2::TogglePauseMenu`
  (`MyPlayerController2.cpp:404-417`) asks the HUD's lobby widget first while `IsInLobby()` and the pause menu is closed.
  While the panel has UI-only input, IA_Pause doesn't fire, so `NativeOnKeyDown` closes it on Esc or Gamepad B, as the
  pause menu does (`PauseMenu3.cpp:323`). The panel's MENU button closes it and opens the pause menu (new
  `AMyPlayerController2::OpenPauseMenu()`). No new input asset.
* If the pause menu is open when the countdown starts, it stays open: the player opened it.

### 6.2 Layout (Menu3 yellow-and-black: F_Anton titles, F_Bebas / F_Barlow text, WBP_OptionRow rows)

```
+------------------------------------------------------------------------------------------+
| LOBBY  Talal's lobby                                          CODE  K7Q2PX   [COPY]       |
|------------------------------------------------------------------------------------------|
|  BLUE  2 / 2                                  |  ORANGE  1 / 2                            |
|  * Talal            HOST            32 ms     |    Friend2          NOT READY      58 ms   |
|    Friend1          READY           41 ms     |    Friend3          LOADING               |
|  [ SWITCH TO ORANGE ]                         |                                           |
|------------------------------------------------------------------------------------------|
|  RULES                                                    (clients: greyed, "set by host") |
|  TEAMS [Auto teams v]   SHIP LIVES [3 v]   SWARM [Normal v]                              |
|  MAX PLAYERS [4 v]      TIME LIMIT [15 min v]   [x] FRIENDLY FIRE  [x] SHIP HOOK  [x] LANE ASSIST |
|------------------------------------------------------------------------------------------|
|  [ READY ] (clients)  [ CLOSE ]   [ MENU ]   [ LEAVE ]                 [ START 2v1 ]      |
|                                            1 not ready - click again to start anyway      |
+------------------------------------------------------------------------------------------+
Compact strip (panel closed), top centre:  LOBBY   BLUE 2 - ORANGE 1   1 NOT READY   Esc: lobby
Countdown (both views, large, centre):      MATCH STARTS IN 4
```

### 6.3 C++ classes and BindWidget names

New `Source/Aura/Public/Match/MyLobbyWidget.h` (+ `.cpp`), derived from `UMyUserWidget` like UMainMenu3. Every widget is
`BindWidgetOptional`:

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
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* CountdownHintText;   // "Esc: lobby" / host "Esc: lobby (CANCEL)"
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* MessageText;         // ClientLobbyMessage, 3 s
    // Header
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* TitleText;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* JoinCodeText;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* CopyCodeButton;
    // Teams
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* BlueHeaderText;      // "BLUE  2 / 2"
    UPROPERTY(meta = (BindWidgetOptional)) UPanelWidget* BlueList;          // rows of PlayerRowClass
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* OrangeHeaderText;
    UPROPERTY(meta = (BindWidgetOptional)) UPanelWidget* OrangeList;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* SwitchTeamButton;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* SwitchTeamText;      // SWITCH TO ORANGE / CANCEL SWITCH
    // Rules (host edits; clients see them disabled)
    UPROPERTY(meta = (BindWidgetOptional)) UWidget* RulesPanel;
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* TeamModeComboBox;     // RuleSets (Practice entry relabelled)
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* ShipLivesComboBox;    // ShipLivesChoices
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* SwarmComboBox;        // DifficultyNames
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* MaxPlayersComboBox;   // MaxPlayerChoices
    UPROPERTY(meta = (BindWidgetOptional)) UComboBoxString* TimeLimitComboBox;    // TimeLimitChoices
    UPROPERTY(meta = (BindWidgetOptional)) UCheckBox* FriendlyFireCheckBox;
    UPROPERTY(meta = (BindWidgetOptional)) UCheckBox* GrappleShipsCheckBox;
    UPROPERTY(meta = (BindWidgetOptional)) UCheckBox* LaneAssistCheckBox;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* RulesHintText;       // "Set by the host" / a refusal
    // Actions
    UPROPERTY(meta = (BindWidgetOptional)) UButton* ReadyButton;            // clients only (hidden for the host)
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* ReadyText;           // READY / NOT READY
    UPROPERTY(meta = (BindWidgetOptional)) UButton* StartButton;            // host only
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* StartText;           // START 1v1 / START CO-OP (ONE SHIP) / CANCEL
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* StartReasonText;     // the block's reason, or the confirm hint
    UPROPERTY(meta = (BindWidgetOptional)) UButton* CloseButton;            // was PLAY in revision 1
    UPROPERTY(meta = (BindWidgetOptional)) UButton* MenuButton;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* LeaveButton;
    UPROPERTY(EditAnywhere, Category = "Lobby") TSubclassOf<UMyLobbyPlayerRow> PlayerRowClass;
    UPROPERTY(EditAnywhere, Category = "Lobby") TArray<int32> TimeLimitChoices = { 0, 5, 10, 15, 20, 30 };   // 0 = none
    UPROPERTY(EditAnywhere, Category = "Lobby") float RefreshInterval = 0.25f;
    UPROPERTY(EditAnywhere, Category = "Lobby") float StartConfirmSeconds = 3.f;
    UPROPERTY(EditAnywhere, Category = "Lobby") float RulesSendDelay = 0.75f;
};

UCLASS() class AURA_API UMyLobbyPlayerRow : public UMyUserWidget     // Match/MyLobbyPlayerRow.h
{
    GENERATED_BODY()
public:
    void Setup(UMyLobbyWidget* Owner, AMyPlayerState* Player, bool bIsLocal, bool bHostView);
    void Refresh();                                                   // texts only, no rebuild (6.4)
protected:
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* PlayerNameText;
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* StatusText;    // HOST / READY / NOT READY / WANTS ORANGE / LOADING
    UPROPERTY(meta = (BindWidgetOptional)) UTextBlock* PingText;      // APlayerState::GetPingInMilliseconds
    UPROPERTY(meta = (BindWidgetOptional)) UWidget* LocalHighlight;
    UPROPERTY(meta = (BindWidgetOptional)) UButton* MoveButton;       // host view only: move (or swap) to the other team
};
```

**The option lists come from MainMenu3** so the host menu and the lobby can't drift apart: they are protected UPROPERTYs
on UMainMenu3 (`MainMenu3.h:115-136`). New public statics `GetDefaultRuleSets()`, `GetDefaultDifficultyNames()`,
`GetDefaultMaxPlayerChoices()`, `GetDefaultShipLivesChoices()` return the C++ CDO's arrays, as `GetRuleSetForTeamMode`
reads `GetDefault<UMainMenu3>()->RuleSets` (`MainMenu3.cpp:544-554`). The combos are filled like `FillStaticOptions`
(`:1168`). The Practice entry is shown as "Practice (co-op, one ship)"; it maps back through `GetTeamModeForRuleSet`,
which matches "practice" anywhere in the text (`:525-542`). as_78 warns if WBP_MainMenu3's CDO overrides a list.

### 6.4 Behaviour

* **Refresh:** every `RefreshInterval` and on `AMyGameState::OnMatchChanged`. The widget builds a signature of
  `PlayerArray`: (PlayerId, TeamId, IsArriving) per player state, deduplicated by PlayerId (a carried old player state and
  its replacement share the id, 5.4 row 7; the one not arriving wins). Rows are destroyed and rebuilt **only when the
  signature changes**; otherwise each row's `Refresh()` updates its status and ping texts in place, so a press and release
  on a row's MOVE button land on the same widget. Controls are set from the replicated `MatchRules`, `ExpectedPlayers`,
  `LobbyStartBlock`, `LobbyNotReady`, `bLobbyRematch` and `PhaseEndServerTime` with `ESelectInfo::Direct`; the change
  handlers ignore `Direct`, so a refresh never sends a request.
* **Host edits:** any rules control change restarts a `RulesSendDelay` (0.75 s) timer; when it fires, the widget reads
  every control into an `FMyMatchRules` plus MaxPlayers and sends one `ServerLobbySetRules`. A refusal comes back as
  `ClientLobbyMessage`; the next refresh resets the controls. Picking 1v1 or 2v2 sets and disables Max Players, as in the
  host menu (`MainMenu3.cpp:468-500`): the value it showed is kept and comes back when the host picks a mode without a
  fixed size (`FreeMaxPlayers`, only for his own edit; a mode that arrives replicated brings its Max Players).
* **Hidden controls:** a host-only or client-only button is hidden with its label and slab: `SetButtonShown` collapses
  the button's outermost `Item_` / `Wrap_` parent that holds no other button (as_77's archetypes; `Wrap_Code` holds CODE,
  the code and COPY).
* **Clients:** the rules are visible and disabled, `RulesHintText` "Set by the host". READY shows for clients only.
* **Start button** (host). Its text names what will start: Practice -> "START PRACTICE (ONE SHIP)"; one team with players
  -> "START CO-OP (ONE SHIP)"; both -> "START {BLUE}v{ORANGE}" with the counts ("START 2v1"). A soft block adds its reason
  in `StartReasonText` ("1 not ready", "teams uneven", "everyone on one team: one ship"); the first click shows "click
  again to start anyway" for `StartConfirmSeconds`, and a second click sends `ServerLobbyStart(true)`. Which block it
  confirms is the replicated `LobbyConfirmBlock` (4.7). NotReady alone with `bLobbyRematch` starts on the first click.
  A rules edit still waiting for its 0.75 s timer is sent first; if the server refuses it, the click does not start. A hard block disables the button with its reason ("1v1 needs a player on
  ORANGE", "waiting for 1 player to load"). While counting down the button reads CANCEL (`ServerLobbyCancelStart`).
  Clients don't see it; `StartReasonText` shows "Waiting for the host to start" or the block's reason.
* **Countdown:** `CountdownText` "MATCH STARTS IN n" from `PhaseEndServerTime - GetServerWorldTimeSeconds()` while
  `IsLobbyCountingDown()`. SWITCH TEAM and the rules are disabled. The panel closes by itself at its start (6.1).
* **Code:** host `GetCurrentJoinCode` (`MultiplayerSessionsSubsystem.cpp:449`), client `GetCurrentSessionInfo` (`:871`),
  as the pause menu's Copy Code (`PauseMenu3.cpp:515`). Hidden without a session.
* **LEAVE:** the pause menu's Leave Session confirm (new public `UPauseMenu3::RequestLeaveSession()`, which calls
  `LeaveSessionButtonClicked`, `PauseMenu3.cpp:369-376`), so the host-left kick stays in one place.

### 6.5 Built by script (as_77)

`as_77_lobby_widget.py` creates `/Game/Level/UI/UserWidgets/MainMenu/Menu3/WBP_Lobby3` (parent `UMyLobbyWidget`) and
`WBP_LobbyPlayerRow3` (parent `UMyLobbyPlayerRow`) with UMGToolSet (`unreal.ToolsetRegistry.execute_tool(
'UMGToolSet.UMGToolSet', ...)` from the inbox, the MainMenu3 builder's method and as_72's helpers). Style is copied:
rules rows from WBP_MainMenu3's `Txt_HostRules` / `Ctl_HostRules` / `Box_HostRulesComboBox` (as as_72 does); buttons from
WBP_PauseMenu3's Resume row (as `UPauseMenu3`'s `CloneButtonRow`, `PauseMenu3.cpp:404-407`); the player row from
`WBP_SessionPlayerRow3`; fonts F_Anton / F_Bebas / F_Barlow from `Menu3/Fonts`. Idempotent (reports and stops when the
widgets exist; `AS77_REBUILD` rebuilds), never during PIE, saves only the two new assets by path, writes
`Saved/Match/as_77_lobby_widget.json`. The names of 6.3 are the contract (CloseButton, not PlayButton; CountdownHintText).

### 6.6 Without the WBP

If `LobbyWidgetClass` is unset or fails to load: a Warning, Esc opens the pause menu, the match HUD draws a one-line
lobby strip ("LOBBY  BLUE 2 - ORANGE 1 - host: Esc > Start match"; NativePaint, the phase switch at
`MyMatchHUDWidget.cpp:348`), and the pause menu's START MATCH row shows in phase Lobby (7.3). Tests and a packaged host can
still start.

---

## 7. L6 Changes to what PR B built (lines as of e9636cc)

### 7.1 Game mode, state, player state, controller, HUD (match owner)

| Where | Change |
|---|---|
| `MyGameMode.h` | new overrides `InitSeamlessTravelPlayer` (protected), `StartToLeaveMap`; lobby members and methods; `StartCountdown(bool, float, bool)`; `ClaimOrSpawnShips(bool, bool)`; `AssignTeam(..., uint8 PreferredTeam)` |
| `MyGameMode.cpp` InitGame `:366-443`, ParseMatchOptions `:445-508` | lobby decision, `ResolveLobbySpawn`; AutoCoopPlayers skipped with the lobby (4.2) |
| `PostLogin` `:221-241` | StartSession only without the lobby; `OnPlayerArrived(PC, false)` (5.4) |
| `InitGameState` `:691-702`, `StartPlay` `:741-805` | ExpectedPlayers = Max Players with the lobby; `bLobbyRound`; the lobby branch (4.7); the take-back `:789-802` becomes a helper |
| `IsHoldingPawns` `:657-673` | 4.7 |
| `AssignTeam` `:807-851`, `RecountTeams` `:853-890` | PreferredTeam; arriving player states not counted (5.4) |
| `EvaluateTeams` `:913-1005` | lobby branch (start block); hard block cancels a lobby countdown |
| `StartCountdown` `:1059-1142`, `ClaimOrSpawnShips` `:1842-1898` | DelayOverride, bFromLobby; untagged placed ships kept from a lobby start |
| `OnCountdownEnd` `:1144-1250`, `BackToWaiting` `:1276-1296` | hard block re-check; `BackToWaiting` -> `CancelLobbyStart` in a lobby round |
| `BeginRound` `:1252-1274` | `TakeBackLobbyPawns`, `SetInLobby(false)`, `ResumeSwarm`, `StartSessionIfHost` |
| `SpawnWaitingPlayers` `:1380`, `RestartPlayer` `:2867` | aboard for practice too |
| `EndMatch` `:1460-1500` | `WillReturnToLobby` -> `bLobbyRound` on the game state; timer -> `ReturnToLobby` or `RestartMatch`; `EndSessionIfHost` |
| `RestartMatch` `:1502-1567` | -> `TravelToRound(bool bLobby)` with `?SeamlessTravel` (5.3) |
| `ApplyRules` `:1609-1669` | team mode at once in the lobby (`:1616-1620`) |
| `MatchTick` `:2424-2469` | no fall death while `bInLobby` (`:2465-2468`) |
| `GetTeamProgress` `:2709-2741` | skip platforms without SplineDistance |
| `ChoosePlayerStart` `:2793-2844`, `RestartPlayer` `:2846-2939` | Lobby-tagged starts; lobby spot; late joiners without a landing (3.4) |
| `FindRespawnSpot` `:3185-3322` | lobby spot first; the path's first platforms before the PlayerStart (3.4) |
| new `MyGameModeLobby.cpp` | `ResolveLobbySpawn`, `SpawnLobbyPlayers`, `LobbyTick` (zone, fall catch, ground poll, start block, rematch, arrivals), `GetLobbySpot`, `RequestLobbyTeam`, `MoveLobbyTeam`, `MoveLobbyPlayer`, `RebalanceLobbyTeams`, `SetLobbyReady`, `ApplyLobbyRules`, `GetLobbyStartBlock`, `GetLobbyMaxPlayers`, `StartFromLobby`, `CancelLobbyStart`, `TakeBackLobbyPawns`, `RemoveTimedEffects`, `ResumeSwarm`, `StartSessionIfHost`, `EndSessionIfHost`, `AdvertiseIfHosting`, `WillReturnToLobby`, `ReturnToLobby`, `TravelToRound`, `OnPlayerArrived`, `InitSeamlessTravelPlayer`, `StartToLeaveMap`, `IsLobbyHost` |
| `MyGameState.h/.cpp` | 4.3 fields and setters; `ApplyLobbyActorState` from `NotifyMatchWritten` (`:311-315`), `OnRep_Match` (`:317-320`), `BeginPlay` |
| `MyPlayerState.h/.cpp` | 4.3 fields; `SetCurrentPlatform` returns while `bInLobby` (`:45-67`); `CopyProperties`; `IsArriving` |
| `PlayerInput/MyPlayerController2.h/.cpp` | 4.8 RPCs; Esc to the lobby panel (`TogglePauseMenu` `:404-417`); `OpenPauseMenu()` |
| `UI/MyHUD.h/.cpp` | `LobbyWidgetClass`, `AddLobbyWidget` (next to `AddMatchWidget`, `:25-73`), `GetLobbyWidget()` |
| `Match/MyMatchTypes.h` | `EMyMatchPhase::Lobby` (appended, `:30-40`), `EMyLobbyStartBlock`, `EMyLobbySpawn`, new events (appended, `:77-92`) |
| `Match/MyMatchSettings.h` | Appendix L-A |
| `Match/MyTeamLibrary.h/.cpp` | `IsInLobby`, `AreShipsLocked`, `IsDamageOff`, `GetTeamModeMaxPlayers` |
| `Match/MyMatchHUDWidget.cpp` | phase Lobby: toasts and name tags (+ the 6.6 strip); Ended: "Back to the lobby in n s" when `bLobbyRound` (`:436-438`), host hint; lobby event toasts; the Locked refusal toast (`HandleUseRefused` `:270-284`) |
| `Match/MyMatchConsole.cpp` or new `Match/MyLobbyConsole.cpp` | Appendix L-B; phase name Lobby (`:114-117`) |
| `Match/MyMatchMemorySubsystem.h` | comment: the restart is seamless outside PIE (`:13-21`) |
| `Actors/MyEffectActor.cpp` | none (the game state toggles its collision, 3.4) |

### 7.2 Main menu (menu owner)

* `OnCreateSession` (`MainMenu3.cpp:1298-1321`): `+ "?Lobby=1"` when `bLobbyWhenHosting` (2.1). Play Solo is unchanged.
* New public statics for the option lists (6.3); `GetTeamModeMaxPlayers` (`:567-578`) forwards to `UMyTeamLibrary`.
* `SessionEntry3`: "IN LOBBY" / "IN MATCH" after the rules text (5.6).

### 7.3 Pause menu (menu owner)

* `RefreshMatchButtons` (`PauseMenu3.cpp:445-455`): START MATCH shows in WaitingToStart **and** in phase Lobby; in Lobby
  `StartMatchButtonClicked` (`:495-503`) -> `RequestStartMatch` -> `StartFromLobby(/*bForce*/true)`. The Restart row is
  hidden while `IsInLobby()`.
* The Restart row when `GameMode->WillReturnToLobby()`: label BACK TO LOBBY, confirm "End the match and take everyone back
  to the lobby?", calls `ReturnToLobby` (`:505-510`, `:821-827`, keeping its `CloseMenu` first). Otherwise as built.
* New public `RequestLeaveSession()` (6.4).

### 7.4 Sessions (menu owner)

`UMultiplayerSessionsSubsystem::EndSession()`, `AdvertiseMatch(...)`, the Ending wait in `StartSession`
(`MultiplayerSessionsSubsystem.cpp:391-423`), the `InMatch` key (5.6).

### 7.5 Airship (airship owner) and combat (combat owner)

* `AAirshipPawn::CanBoard` / `CanMount` (`AirshipPawn.cpp:1673`, `:2533`): `if (UMyTeamLibrary::AreShipsLocked(this))
  return false;`.
* `UAirshipPilotComponent`: `FindBoardableAirship` (`AirshipPilotComponent.cpp:258-294`) returns nothing while locked;
  `TryUseNearest` (`:368-470`) answers `ClientUseRefused(EAirshipUseRefusal::Locked)`; `EAirshipUseRefusal::Locked`
  appended (`AirshipTypes.h:124-131`).
* `UAirshipPilotComponent::TeardownLocalInput` (`:152-176`): the mapping is removed only by the controller that owns the
  local player now (5.4 row 10).
* `UMyAttributeSet` (`MyAttributeSet.cpp:81-82`): the damage is dropped also when `UMyTeamLibrary::IsDamageOff(...)`.

### 7.6 The WaitingToStart phase: kept

Used when the lobby is off: console `open StartupMap?listen`, `RestartMatch` without a session, the PR B listen harness
as_75 (no `Lobby` option, CVar -1). No code is removed.

### 7.7 Defaults and what PR B tests change

* Host Game -> lobby. Play Solo, console, as_74 / as_75 / as_76 -> PR B flow.
* Practice starts aboard. **SPEC_B T1.1** ("spawned on the floor") becomes: no pawn during the 5 s countdown, then the
  pawn on team 0's deck within 1 s of InProgress. **M1.1's practice variant** becomes "pawns aboard team 0's ship".
  as_74 / as_75 need that one-line pass change.
* SPEC_B B4.2's "Practice, or `bStartAboard` off: at a PlayerStart" becomes "`bStartAboard` off: the path's first
  platform, else a PlayerStart".
* **SPEC_B M7.1 (restart)** in PIE stays a hard travel and keeps passing; outside PIE the restart is seamless. Its Steam
  check joins the manual list (8.5).

---

## 8. L7 Files, scripts, tests, risks

### 8.1 File ownership

The lobby is one C++ pass after PR B's code. If it is split (no two owners touch the same file):

| Owner | New | Changed (PR B files) |
|---|---|---|
| match | `Private/MyGameModeLobby.cpp`; `Public/Private/Match/MyLobbyWidget.*`, `MyLobbyPlayerRow.*`; `Private/Match/MyLobbyConsole.cpp` | `MyGameMode.*`, `MyGameState.*`, `MyPlayerState.*`, `PlayerInput/MyPlayerController2.*`, `UI/MyHUD.*`, `Match/MyMatchTypes.h`, `Match/MyMatchSettings.h`, `Match/MyTeamLibrary.*`, `Match/MyMatchHUDWidget.cpp`, `Match/MyMatchMemorySubsystem.h` (comment) |
| menu | none | `EOS/MainMenu3.*`, `EOS/PauseMenu3.*`, `EOS/MultiplayerSessionsSubsystem.h/.cpp`, `EOS/MultiplayerSessionTypes.h`, `EOS/SessionEntry3.*` |
| airship | none | `Airship/AirshipPawn.cpp` (two lines), `Airship/AirshipTypes.h` (refusal), `Airship/AirshipPilotComponent.cpp` (lock, input teardown) |
| combat | none | `AbilitySystem/MyAttributeSet.cpp` (one condition) |
| assets | `Docs/Airship/scripts/ue/as_77`..`as_80*` (8.2) | none |

Order: match writes the header API first (`MyMatchTypes.h`, `MyMatchSettings.h`, `MyTeamLibrary.h`,
`MyGameState.h`, `MyPlayerState.h`), then the owners work in parallel. No `Aura.Build.cs` change (UMG, OnlineSubsystem,
EnhancedInput, GameplayAbilities are dependencies, `Aura.Build.cs:11`). No `Config/*` change (C++ defaults). Build only
with `_AirshipWork_logs/build_r2b.sh`.

### 8.2 Editor scripts (rules of SPEC_B section 3: inbox, never during PIE, `free -g` first, explicit paths)

| Script | Does | Saves |
|---|---|---|
| `as_77_lobby_widget.py` | WBP_Lobby3 + WBP_LobbyPlayerRow3 (6.5) | the two new WBPs |
| `as_78_lobby_hud.py` | BP_MyHUD `LobbyWidgetClass` = WBP_Lobby3_C, compile, save (backup to `Saved/Match/backup/`); verify: classes load, WBP_Lobby3 has the 6.3 names (missing ones listed), the option lists vs WBP_MainMenu3's CDO, `UMyMatchSettings` lobby defaults = Appendix L-A. Report `Saved/Match/as_78_verify.txt` | BP_MyHUD |
| `as_79_pie_lobby.py` (+ `as_79s_status.py`, `as_79x_stop.py`) | the standalone run 8.3, **one PIE session**, on the clone's StartupMap: `Aura.Lobby.Enable 1`, fixed 30 fps, CVars restored at the end | nothing |
| `as_80_pie_lobby_mp.py` (+ `as_80s`, `as_80x`) | the listen run 8.4, **2 players, one PIE session**; the as_75 ini method for PlayNetMode / clients (`set_play_mode.sh listen 2`, editor closed); clients act through their own world (as_75's Enhanced Input injection); `Aura.Lobby.Enable 1`; reads the PIE server port from `LevelEditorPlaySettings` (`server_port`, `LevelEditorPlaySettings.h:402`; default 17777) | ini only |

No script saves StartupMap. TEMP actors are not needed: the floor and the placed platform are in both maps. Before as_80:
`free -g` shows at least 6 GB available, else wait (memory notes: capped editor scope).

### 8.3 Standalone PIE run (as_79, one session, StartupMap clone, 1 player)

The tests run in this order in one PIE session; LB1.7 and LB1.10 load the map again inside it.

| ID | Setup | Pass |
|---|---|---|
| LB1.1 | load with the lobby | phase Lobby within 1 s, `bInLobby`; log `Lobby: spawn PlayerStarts, ground Floor (+ BP_MyHexPlatform_C_1)`; the zone contains (0, 0, 205) and the placed platform's root; the pawn within 8 m of (0, 0, 205); no team ship; every wave spawner stopped and 0 sentinels at 15 s; Burrower `IsSpawningPaused`; `ExpectedPlayers` = the URL's Players (PIE: `DefaultExpectedPlayers`); the panel opened by itself (`Aura.Lobby.Status`: panel 1, IgnoreInput 1) |
| LB1.2 | a free ship by `Aura.Airship.Spawn`; `Aura.Airship.TurretFire` at the player | Health unchanged; `Aura.Airship.Board 0` refused with Locked (log); `BP_Potion_C_1` has no collision |
| LB1.3 | the harness teleports the pawn onto a path platform at u 50 m | back inside the zone within 1.0 s; `CurrentPlatform` null, `PlatformSplineDistance` -1; nothing activated |
| LB1.4 | `Aura.Match.Rules Teams=practice ShipLives=5 Swarm=3` | applied at once, team mode included; spawner DifficultyScale = the Very Hard preset |
| LB1.5 | `Aura.Lobby.Start`, `Aura.Lobby.Cancel` at 2 s | at the start: phase Countdown with `PhaseEndServerTime` 5 +-0.1 s ahead, `bInLobby` true, a team 0 ship spawned, the panel closed with game input (`Aura.Lobby.Status`: panel 0, IgnoreInput 0, cursor 0); after the cancel: phase Lobby, no team ship, events Countdown then LobbyCancelled |
| LB1.6 | use the beam once (cooldown running), `Aura.Lobby.Start`, wait 7 s | InProgress at 5 +-0.1 s; `bInLobby` false; one team ship, TeamId 0, at (5442, 12500, 200) +-100 cm; the player on its deck within 1 s with full Health and Mana; **no active effect with a duration on the ASC** (the lobby cooldown is gone); potion collision back on; spawners running and wave 1 sentinels within 4 + 6 + 2 s; Burrower not paused |
| LB1.7 | `Aura.Match.Set EndScreenSeconds 3`, `Aura.Match.End -1` | Ended; after 3 +-0.5 s the map loads again (OpenLevel) with `Lobby=1`; phase Lobby; rules as in LB1.4; RoundIndex 0 |
| LB1.8 | `Aura.Lobby.Start`; after the start (nobody landed) the harness destroys the PIE copies of Floor and BP_MyHexPlatform_C_1, then teleports the player 150 m below the lane, on foot | fall death within 8 s; the respawn on a path platform (SplineDistance >= 0), never within 30 m of (0, 0, 205); then `Aura.Lobby.Return` |
| LB1.9 | back in the lobby (floor restored by the load): destroy the PIE Floor and platform copies, `Aura.Lobby.Resolve` | log: Auto picked PathStart; the pawn on the platform with the smallest SplineDistance within 10 s; after 30 s there `CurrentPlatform` null, nothing activated; `Aura.Lobby.Start` works from there (pawn aboard at 0) |
| LB1.10 | console `open StartupMap?Teams=auto?Players=1?Lobby=0` (the Play Solo URL) | practice countdown at once; no pawn for 5 s; then the pawn on team 0's deck |

### 8.4 Listen PIE run (as_80, one session, 2 players)

Order matters: the seamless smoke test is last, because PIE seamless travel can break the session.

| ID | Pass |
|---|---|
| LM1.1 | both in phase Lobby with pawns on the floor within 3 s of the client's join, at least 2 m apart; teams 0 / 1; the client's teams, ready flags and `bIsHost` equal the server's within 0.5 s; `WBP_Lobby3` exists on both; the host's StartButton visible and ReadyButton hidden, the client's the other way round; the panel opened by itself on both |
| LM1.2 | the client teleported 100 m out of the zone (server world) is back within 1.0 s; the zone message in the client's log |
| LM1.3 | the host's gun hits on the client: Health unchanged |
| LM1.4 | bots (critique m12): `Aura.Lobby.Bots 1` -> 3 players, teams {2, 1}; `Aura.Lobby.Team 0 1` moves the host at once ({1, 2}). `Aura.Lobby.Bots 2` -> {2, 2}; `Aura.Lobby.Team 1 0` leaves the client pending (RequestedTeam 0 on the client within 0.5 s); the team 0 bot asks for 1: both swap, requests cleared, {2, 2}. `Aura.Match.Rules Teams=2v2` rebalances in join order (team 0: host, bot 1; team 1: client, bot 2); `Aura.Lobby.Move 1 0` (team 0 full) swaps the client with bot 1, the last to join team 0; counts {2, 2}. `Aura.Match.Rules Teams=auto` |
| LM1.5 | `Aura.Lobby.Bots 1` (3 players): `Aura.Match.Rules Teams=1v1` refused ("1v1 has room for 2"). `Aura.Lobby.Bots 0`; `Aura.Lobby.Ready 1 1`. `Teams=2v2 ShipLives=5 Swarm=3`: the client's rules equal within 0.5 s, the client's ready flag false (team mode changed), Max Players 4. `Aura.Lobby.Ready 1 1`, then `ShipLives=3` alone: the flag stays true. One session update per request logged (PIE: "no session to advertise", accepted) |
| LM1.6 | `Teams=auto`. `Aura.Lobby.Start strict` refused NotReady; `Aura.Lobby.Ready 1 1`; `Aura.Lobby.Start strict`: countdown 5 s. At its start both panels closed, IgnoreInput 0 and cursor hidden on both machines; the client's injected IA_Move moves its pawn more than 1 m within 1 s. At 0 both ride their own ship's deck within 1 s (team 0 y +12500, team 1 y -32500); TeamIds as in the lobby |
| LM1.7 | rejoin InProgress (critique M3): the client's world runs `open 127.0.0.1:<ServerPort>`; reconnected within 10 s; back on team 1 (the emptier team; the memory is only written at a return); aboard team 1's ship within 1 s |
| LM1.8 | `Aura.Match.Set EndScreenSeconds 3`, `Aura.Match.End 0`: a hard ServerTravel (PIE) with `Lobby=1`, `Round=1`; both back in phase Lobby; TeamIds as before (or join order without net ids, logged, as SPEC_B M7.1); rules kept; ready flags false; `bLobbyRematch` true only with valid net ids |
| LM1.9 | rejoin in the lobby: `open 127.0.0.1:<ServerPort>`; a balanced team, ready false, a pawn on the floor |
| LM1.10 | rejoin during the lobby countdown: `Aura.Lobby.Start`; the client opens the address at 1 s; no pawn until 0, then aboard with the host (his team active at 0) |
| LM1.11 | rejoin in Ended: `Aura.Match.End 0`; the client opens the address 1 s later; a pawn; then carried back to the lobby by the return |
| LM1.12 | `Aura.Match.Rules Teams=1v1`, `Aura.Lobby.Start`, the client runs `disconnect` at 2 s: cancelled within 0.5 s (LobbyCancelled, NeedOpponent), phase Lobby, no team ship left; then the client opens the address again |
| LM1.13 | seamless smoke test (critique M1), last: `net.AllowPIESeamlessTravel 1` on the server; start, `Aura.Match.End 0`, return. Logs "SeamlessTravel to:" and "SeamlessTravel finished"; both in phase Lobby; the client's controller is a new object; it has an `AirshipPilotComponent` and its local player still maps IMC_AirshipBoard (`HasMappingContext`); TeamIds kept; the overlay widget exists; the ASC has its startup abilities; within 5 s the client's counts of `AMyHexPlatform` and `AAirshipPawn` equal the server's; no "not cleaned up by garbage collection" error (`UnrealEngine.cpp:17380-17420`); no `LogMatch` line from MatchTick or HealthTick between "ProcessServerTravel" and the next "Match on on StartupMap"; a third start puts both aboard |

### 8.5 Manual and packaged checks

* The full menu path: MM_MainMenu -> Host -> the lobby panel opens; the host edits the rules, the client's combos follow
  and are disabled; the Start button's texts; LEAVE -> menu.
* **Two machines, packaged, Steam (the real test of D11):** after a match the client stays connected and lands in the
  lobby (no main menu, no "Couldn't connect"); log `SeamlessTravel to`; teams kept; StartSession at each start,
  EndSession at each end, InProgress again on the next start; the browser shows IN LOBBY / IN MATCH; a lobby-off
  `Aura.Match.Restart` during a hosted match (the lobby-off `RestartMatch`, the same seamless travel) keeps the client
  too. With a session the end of a match always goes to the lobby (2.5), so this console command is the only way to reach
  `RestartMatch` with clients on Steam.
* Host leaves: the client shows "The host closed the lobby."; host crash: "Lost connection to the host.".
* Play Solo, then Open Lobby, a friend joins, the match ends: everyone goes to the lobby.

### 8.6 Risks

1. **RL1 The zone teleport feels like a rubber band** mid-grapple. 15 m margin, 60 m headroom, 0.5 s grace; tune with
   LB1.3 / LM1.2.
2. **RL2 The in-level lobby costs the full match map.** Waves and Burrowers are off; the rest needs a separate map (3.5).
3. **RL3 PCG timing in PathStart mode:** held pawns plus a 10 s timeout.
4. **RL4 PIE proves nothing about Steam travel.** PIE uses the IP driver and, by default, hard travel (5.1, 5.5). The
   seamless return is tested in PIE only as a smoke test (LM1.13). The real test is two Steam machines (8.5). Until then
   D11 is "verified in source, not run".
5. **RL5 Practice starts aboard:** learners fly to the platforms first, and Play Solo starts with a 5 s still camera.
6. **RL6 Talal's free ship inside the lobby zone:** locked in the lobby; removed at a versus start's end (B3.1, SPEC_B Q9),
   free in practice.
7. **RL7 A landing during the 0.5 s grace** would rank the player without the `SetCurrentPlatform` gate: the gate is
   required.
8. **RL8 Steam lobby joinability follows the join-in-progress flag at all times** (5.6).
9. **RL9 Option lists read from UMainMenu3's C++ CDO:** a value changed only on WBP_MainMenu3 wouldn't reach the lobby
   (as_78 warns).
10. **RL10 The ring search around one PlayerStart** gives 25 spots; more players need Lobby-tagged PlayerStarts.
11. **RL11 The transition world** creates the world subsystems for an empty world that never begins play (5.4 row 2).
    LM1.13 is the only check before Steam.
12. **RL12 Client-side actors kept through the travel** (5.4 row 11): LM1.13 counts them.
13. **RL13 Arrivals that never complete** block Start for at most `LobbyArrivalTimeout` (45 s); then the stuck player
    joins as a late joiner if he ever arrives.
14. **RL14 Seamless travel in PIE** ("some issues", `GameModeBase.cpp:503`) can crash the editor: LM1.13 runs last, and
    its failure is reported, not retried.

### 8.7 Deferred (not in this PR)

* The separate lobby map: `LobbyMap` / `MatchMap` settings, `IsLobbyOnlyLevel`, `TravelToMatch`, the `FromLobby` arrival
  wait, `L_Lobby`, `as_81_lobby_map.py`, `AMyLobbyTeamPad`, `BP_MyLobbyGameMode` (2.7, 3.5, 5.8).
* A loading screen for the travel (5.7).
* The editor's late join ("Add Client", `UEditorEngine::RequestLateJoin`, `EditorEngine.h:1885`, `PlayLevel.cpp:1727-1733`;
  setting `bAllowLateJoinInPIE`, `EditorExperimentalSettings.h:94-96`): not callable from Python, and a console command
  would need `UnrealEd` in `Aura.Build.cs`. The rejoin by `open` (`LevelEditorPlaySettings.h:373-377`) covers the same
  server path.
* Keeping XP and level across rounds (both travel types start them over).

---

## 9. Questions for Talal (never answered: the defaults in brackets are used, and are listed in the PR)

1. **Q-L1** When the match starts, should the floor and the platform above it stay until you delete them [yes, the match
   never uses them], or disappear at Start? For the second, tag them `LobbyOnly` in your map (3.4).
2. **Q-L2** After you delete the floor, the in-level lobby moves by itself to the path's first platform [yes]. Or do you
   want the separate lobby map (L_Lobby) by then?
3. **Q-L3** Play Solo goes straight into practice, no lobby [yes]. Practice starts aboard team 0's ship [yes].
4. **Q-L4** Ready flags: shown, and the host may start anyway after a second click [yes; no second click for a rematch
   with the same teams], or must everyone be ready?

---

## Appendix L-A. Settings added to `UMyMatchSettings` (category "Lobby", Config=Game, C++ defaults)

| Name | Default | Meaning |
|---|---|---|
| bLobbyWhenHosting | true | the main menu's Host Game travels with `?Lobby=1` (2.1) |
| bSeamlessTravel | true | `ReturnToLobby` and `RestartMatch` add `?SeamlessTravel` (5.3); false = hard travel (drops Steam clients, 5.1) |
| LobbySpawn | Auto | Auto, PlayerStarts, PathStart (3.1) |
| LobbyGroundTraceDepth | 5000 | cm, the sweep under each PlayerStart |
| LobbyGroundMinNormalZ | 0.7 | a lobby ground hit must be at least this flat (3.1) |
| LobbyZoneMargin / LobbyZoneHeight / LobbyZoneDepth | 1500 / 6000 / 2000 | cm around, above and below the ground's top; Depth is also the fall catch (3.1, 3.2) |
| LobbyZoneGraceSeconds | 0.5 | s outside the zone before the teleport back |
| LobbyCountdownSeconds | 5 | s from Start to the match (PR B's Countdown) |
| LobbyArrivalTimeout | 45 | s after StartPlay during which players still loading block Start (5.4) |
| bLobbyRequireReady | false | true = NotReady blocks Start |
| bLobbyTeamSwitch | true | players may ask to switch (4.4) |
| bLobbyRulesClearReady | true | a team mode or Max Players change clears the ready flags (4.5) |
| bLobbyDamage | false | true = damage in the lobby |
| LobbyOnlyActorTag | LobbyOnly | tagged actors are hidden outside the lobby (3.4); none tagged today |
| bStartAboard (existing) | true | now also practice (3.4) |
| EndScreenSeconds (existing) | 20 | then back to the lobby when `WillReturnToLobby`, else the restart |

On `UMyLobbyWidget`: `TimeLimitChoices` {0, 5, 10, 15, 20, 30}, `RefreshInterval` 0.25, `StartConfirmSeconds` 3,
`RulesSendDelay` 0.75.

## Appendix L-B. Console additions (compiled out of Shipping like `Aura.Match.*`)

| Command | Where | What |
|---|---|---|
| CVar `Aura.Lobby.Enable` | read at InitGame | -1 = by the URL's Lobby option (default), 0 off, 1 on; the URL wins |
| `Aura.Lobby.Status` | any | phase, `bInLobby`, countdown, spawn mode, zone boxes, start block, rematch, arriving count; per player: team, ready, request, host, arriving; per local player: panel open, `GameViewportClient::IgnoreInput`, mouse capture mode, cursor shown |
| `Aura.Lobby.Start [strict]` | server | `StartFromLobby`; soft blocks ignored unless `strict` |
| `Aura.Lobby.Cancel` | server | `CancelLobbyStart` |
| `Aura.Lobby.Ready <PlayerIndex> <0/1>` | server | a player's ready flag |
| `Aura.Lobby.Team <PlayerIndex> <0/1>` | server | that player's switch request (4.4) |
| `Aura.Lobby.Move <PlayerIndex> <0/1>` | server | the host's move (swap when full) |
| `Aura.Lobby.Bots <n>` | server | keeps n bot player states (an `AAIController` with `bWantsPlayerState`, no pawn, a team by `AssignTeam`); 0 removes them. Tests only; Start refuses while bots exist, and `StartToLeaveMap` removes them (an AI controller with a player state is carried by seamless travel, `Controller.cpp:837-840`, keeps its old player state and would count as arriving forever) |
| `Aura.Lobby.Resolve [Auto\|PlayerStarts\|PathStart]` | server | runs `ResolveLobbySpawn` again and sends every lobby pawn to a lobby spot |
| `Aura.Lobby.Return` | server | `ReturnToLobby` now (the pause menu's BACK TO LOBBY) |
| `Aura.Lobby.Zone [seconds]` | server | draws the zone boxes (10 s default) |
| `Aura.Lobby.Panel <0/1>` | local | opens / closes the lobby panel |

PlayerIndex = the index in `GameState->PlayerArray` (join order, 0 = the host, bots included). `Aura.Match.Start` in the
lobby = `Aura.Lobby.Start`; `Aura.Match.Rules` in the lobby = `ApplyLobbyRules` (4.6); `Aura.Match.Status` gains one
lobby line.

## Appendix L-C. Engine and session facts used (verified)

| Fact | Where |
|---|---|
| InitGame runs after the components are registered; its Options are the URL's | `World.cpp:5988`, `:6034`, `:5969-5975` |
| A new player gets a pawn only when PlayerCanRestart says so; that needs a loaded world and no pending swap | `GameModeBase.cpp:1203-1212`; `PlayerController.cpp:3343-3346` |
| Hard travel: clients told at once, the listen host switches after ServerTravelPause (4 s) | `GameModeBase.cpp:423`, `:517`; `UnrealEngine.cpp:15943-15955`; `World.cpp:7992`; `BaseEngine.ini:2535` |
| While switching, the host answers Ignore; IP drops the packet, SteamSockets rejects the connection | `World.cpp:7089-7093`; `IpNetDriver.cpp:1263-1279`; `SteamSocketsNetDriver.cpp:470`, `:540` |
| A rejected pending connection fails without retry | `PendingNetGame.cpp:536-539`; `UnrealEngine.cpp:16017` |
| Seamless: by flag or `?SeamlessTravel`; off in PIE unless `net.AllowPIESeamlessTravel=1`; no pause | `GameModeBase.cpp:488-511`, `:520-524`; `GameModeBase.h:579` |
| Remote clients always travel relative, which client seamless travel needs; `?listen` stripped for them | `GameModeBase.cpp:404-423`; `PlayerController.cpp:5742-5745` |
| No TransitionMap: an empty transition world; the old world is collected before the destination loads | `World.cpp:8367-8370`, `:8943` |
| Kept into the transition: game mode, game state, game session, player states, controllers, the local HUD and camera | `GameModeBase.cpp:539-558`; `World.cpp:8689-8724`; `PlayerController.cpp:3635-3644` |
| Timers live on the game instance | `World.cpp:8056-8059` |
| The net driver moves to the new world | `World.cpp:8526-8565` |
| The destination gets a new game mode with the URL's options; PostSeamlessTravel before BeginPlay | `World.cpp:8992`, `:9094`, `:9098` |
| Carried player states join the new game state's PlayerArray; carried actors are flagged | `GameStateBase.cpp:71-74`; `World.cpp:8833`; `Actor.h:566` |
| Seamless arrival: new controller and player state, Reset + CopyProperties + Destroy of the old one, then InitSeamlessTravelPlayer, GenericPlayerInitialization, HandleStartingNewPlayer; no Login / PostLogin | `GameModeBase.cpp:607-641`, `:811-836`, `:973-998`, `:1001-1048`; `PlayerController.cpp:3652-3667`, `:697-726` |
| CopyProperties / Reset / OverrideWith of APlayerState; OverrideWith only from AGameMode | `PlayerState.cpp:95-125`, `:230-235`, `:413-421`; `GameMode.cpp:687-759` |
| A swapped controller is not logged out | `PlayerController.cpp:3661-3662`; `Controller.cpp:597-607` |
| Viewport widgets go with their world | `World.cpp:6150`, `:8679`; `GameViewportSubsystem.cpp:38-40`, `:301-322` |
| Joins during a seamless travel go to the destination map | `World.cpp:7161-7167`, `:7612-7618` |
| A client that loses its host goes to the default map | `UnrealEngine.cpp:15512`, `:15527`; `DefaultEngine.ini:2` |
| Steam StartSession from Pending / Ended; EndSession from InProgress, asynchronous through Ending | `OnlineSessionInterfaceSteam.cpp:399-433`, `:498-510`, `:555-574` |
| EOS StartSession from Pending / Ended; EndSession from InProgress; join in progress is a session flag | `OnlineSessionEOS.cpp:1734-1743`, `:1955-1964`, `:1378-1387` |
| Steam lobby joinable = join in progress and room | `OnlineSessionAsyncLobbySteam.cpp:447`, `:657` |
| PIE clients can connect with `open 127.0.0.1:<ServerPort>` | `LevelEditorPlaySettings.h:373-377`, `:402` |
| OpenLevel adds its own `?` | `GameplayStatics.cpp:981` (SPEC_B B4.6) |
