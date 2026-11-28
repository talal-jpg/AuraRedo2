# Round 2, PR B: lobby core notes

The C++ core of `SPEC_B_LOBBY.md` (revision 2) in the worktree `_AirshipWorkB` (branch `airship-r2-prb`, base e9636cc).
The lobby widget, the HUD, the pause menu and the editor scripts are not in this pass (section 6).

**Status.** It builds with `_AirshipWork_logs/build_r2b.sh`: Result Succeeded, `build_r2b_045015.log` (the earlier
`build_r2b_044734.log` compiled the rest of the changed files). The only warnings are the old `bIsFocusable` ones in
`MainMenu.cpp` / `MainMenu2.cpp`. **Nothing has run in the editor or PIE.** Nothing is committed.

**Review fix pass (2026-11-28, `REVIEW_lobby.md`).** 16 findings checked against the code: 15 real, 1 not real as
described (hardened anyway). Built with `build_r2b.sh`: `build_r2b_061106.log` (31 actions) and `build_r2b_061456.log`
(the last edit), both Result Succeeded, no new warnings. Section 8 lists what changed. Line numbers below are updated
where the fixes moved them.

All line numbers are in the worktree as it is at the end of this pass. Q-L1 to Q-L4 use the spec's defaults (section 7).

## 1. Files

| File | What |
|---|---|
| `Source/Aura/Private/MyGameModeLobby.cpp` (new) | every lobby method of `AMyGameMode` |
| `Source/Aura/Public/MyGameMode.h`, `Private/MyGameMode.cpp` | lobby API and members; the PR B flow changes (2.2) |
| `Source/Aura/Public/MyGameState.h`, `Private/MyGameState.cpp` | replicated lobby state, `ApplyLobbyActorState` |
| `Source/Aura/Public/MyPlayerState.h`, `Private/MyPlayerState.cpp` | ready, request, host, `IsArriving`, `CopyProperties`, the ranking gate |
| `Source/Aura/Public/PlayerInput/MyPlayerController2.h`, `.cpp` | the lobby RPCs, `OnLobbyMessage`, the Esc route, `OpenPauseMenu` |
| `Source/Aura/Public/Match/MyLobbyPanel.h` (new) | `IMyLobbyPanel`, the interface the lobby widget implements |
| `Source/Aura/Public/Match/MyMatchTypes.h` | `EMyMatchPhase::Lobby`, `EMyLobbyStartBlock`, `EMyLobbySpawn`, 4 events |
| `Source/Aura/Public/Match/MyMatchSettings.h` | Appendix L-A settings, category Lobby |
| `Source/Aura/Public/Match/MyTeamLibrary.h`, `Private/Match/MyTeamLibrary.cpp` | lobby helpers for every machine |
| `Source/Aura/Private/Match/MyLobbyConsole.cpp` (new) | CVar `Aura.Lobby.Enable`, `Aura.Lobby.*` commands |
| `Source/Aura/Private/Match/MyMatchConsole.cpp` | phase name Lobby; `Aura.Match.Rules`, `Aura.Match.Start`, `Aura.Match.Status` in the lobby |
| `Source/Aura/Public/EOS/MultiplayerSessionsSubsystem.h`, `.cpp`, `MultiplayerSessionTypes.h` | `EndSession`, the Ending wait, `AdvertiseMatch`, the `InMatch` key |
| `Source/Aura/Private/EOS/MainMenu3.cpp` | Host Game adds `?Lobby=1` |
| `Source/Aura/Private/Airship/AirshipPawn.cpp`, `AirshipPilotComponent.cpp`, `AirshipLaneComponent.cpp`, `Public/Airship/AirshipTypes.h` | ship locks, the `Locked` refusal, the input teardown fix |
| `Source/Aura/Private/AbilitySystem/MyAttributeSet.cpp` | damage off in the lobby |
| `Source/Aura/Public/MechSwarm/Spawning/MechSentinelWaveSpawner.h` | one public getter, `IsStopped()` |
| `Source/Aura/Public/Match/MyMatchMemorySubsystem.h` | comment: the restart is seamless outside PIE |

## 2. What is built

### 2.1 The lobby in `MyGameModeLobby.cpp`

* **Decision (4.2).** `InitGame` calls `DecideLobby` before `ParseMatchOptions` (`MyGameMode.cpp:471`). The CVar
  `Aura.Lobby.Enable` first, then the URL's `Lobby=0|1` (`MyGameModeLobby.cpp:158`). `ParseMatchOptions` skips the
  AutoCoopPlayers switch with the lobby (`MyGameMode.cpp:543`). The log line ends with `lobby on (URL Lobby=1), spawn
  PlayerStarts`.
* **Ground (3.1).** `ResolveLobbySpawn` (`MyGameModeLobby.cpp:197`) runs from `InitGame` (`MyGameMode.cpp:476`) and from
  `Aura.Lobby.Resolve`.
  * PlayerStarts: Lobby-tagged starts first, else all, `APlayerStartPIE` skipped. A capsule sweep on `ECC_Pawn` with the
    default pawn's capsule, every pawn ignored. A hit counts with `ImpactNormal.Z >= LobbyGroundMinNormalZ` and
    `FindTeleportSpot` accepting the pawn.
  * Each ground actor gives a zone box (`SetLobbyZoneAround`, `:364`). Platforms without SplineDistance that overlap a
    zone in XY are merged into it.
  * Else PathStart: the path platform with the smallest SplineDistance (`FindFirstPathPlatform`, `:410`). When it does not
    exist yet, `EMyLobbyGround::Waiting`: pawns are held and `PollLobbyGround` (`:642`) waits up to `LobbyPathStartWait`.
  * Else none: the PlayerStart and a fall catch only (`SetLobbyGroundNone`, `:385`).
* **Lobby begins (4.7).** `StartPlay` calls `BeginLobby` (`MyGameMode.cpp:826`, `MyGameModeLobby.cpp:590`). It records the
  running wave spawners, stops the swarm, sets `bInLobby` and phase Lobby, starts the 0.25 s `LobbyTick`, advertises the
  session (IN LOBBY), spawns the lobby pawns and evaluates the teams.
* **Pawns.** `IsHoldingPawns` (`MyGameMode.cpp:697`): phase None holds with the lobby; phase Lobby holds only while the
  PathStart platform is missing (`:713`). `SpawnLobbyPlayers` (`MyGameModeLobby.cpp:570`) asks `PlayerCanRestart`, so a
  client still loading gets no pawn. `RestartPlayer` puts a PathStart pawn on a tile (`MyGameMode.cpp:2988`). PlayerStarts
  uses `Super` plus the ring search; `ChoosePlayerStart` prefers the lobby's starts in the lobby and in phase None of a
  lobby round, and puts Lobby-tagged starts last in the match (`MyGameMode.cpp:2920`).
* **Zone (3.2).** `UpdateLobbyZone` (`MyGameModeLobby.cpp:676`): outside every zone box for `LobbyZoneGraceSeconds` ->
  `SendToLobbySpot` (`:503`): cancel abilities, stop the movement, teleport, `ClientSetRotation`, the message "Stay in the
  lobby: ...". Without a zone only the fall catch runs. `MatchTick` skips the fall death while in the lobby
  (`MyGameMode.cpp:2568`).
* **Gating (3.3).**
  * Damage: `MyAttributeSet.cpp:84` drops IncomingDamage while `UMyTeamLibrary::IsDamageOff`.
  * Ranking and collapse: `SetCurrentPlatform` returns while in the lobby (`MyPlayerState.cpp:116`).
  * Ships: `CanBoard` / `CanMount` refuse while `AreShipsLocked` (`AirshipPawn.cpp:1688`, `:2547`). The F prompt shows
    nothing (`AirshipPilotComponent.cpp:281`). `TryUseNearest`, `TryBoard` and `TryMount` answer
    `ClientUseRefused(EAirshipUseRefusal::Locked)` (`AirshipPilotComponent.cpp:413`, `:348`, `:522`).
  * Waves and Burrowers: stopped in `BeginLobby`, resumed in `BeginRound` (`ResumeSwarm`, `MyGameModeLobby.cpp:1446`).
  * Pickups and LobbyOnly actors: `AMyGameState::ApplyLobbyActorState` (`MyGameState.cpp:395`), on every machine from
    `NotifyMatchWritten`, `OnRep_Match` and `BeginPlay`. It acts only on a change and gives back only what it changed.
* **Teams (4.4).**
  * `AssignTeam` takes `PreferredTeam` before the match memory (`MyGameMode.cpp:873`).
  * `RequestLobbyTeam` (`MyGameModeLobby.cpp:1064`): a move when the target team is smaller, a swap with the oldest
    request for his team, else pending.
  * `MoveLobbyPlayer` (`:1155`): the host's move, a swap when the team is full.
  * `RebalanceLobbyTeams` (`:1231`): on a team mode change, all teams again in join order.
  * `RecountTeams` skips arriving player states (`MyGameMode.cpp:920`).
* **Ready (4.5).** `SetLobbyReady` (`MyGameModeLobby.cpp:1299`); the host has no flag. `ClearLobbyReady` (`:1270`) runs
  only on a team mode or Max Players change. `ComputeLobbyRematch` (`:878`).
* **Rules (4.6).** `ApplyLobbyRules` (`:1332`) refuses "1v1 has room for 2: 3 players are in" and Max Players below the
  player count. It calls `ApplyRules`, writes Max Players, sends `LobbyRulesChanged` and makes one session update.
  `ApplyRules` applies the team mode at once in phase Lobby, sets Max Players for 1v1 / 2v2, rebalances and clears ready
  (`MyGameMode.cpp:1699`, `:1721`).
* **Start blocks.** `GetLobbyStartBlocks` (`MyGameModeLobby.cpp:777`) returns every block as bits.
  `UpdateLobbyState` (`:915`) writes the first one, the not-ready count and the rematch flag into the game state.
* **Start (4.7).** `StartFromLobby` (`MyGameModeLobby.cpp:967`) refuses hard blocks, and soft blocks without `bForce`
  (NotReady not for a rematch) and with bots. The soft block to confirm is `GetLobbyConfirmBlock(Mask, bRematch)`
  (`:878`), which `UpdateLobbyState` also replicates (`:953`). Then `StartCountdown(true, LobbyCountdownSeconds, true)`. `StartCountdown` keeps untagged
  placed ships when started from the lobby (`MyGameMode.cpp:1197`). `RequestStartMatch` (the pause menu's START MATCH,
  `Aura.Match.Start`) starts with force in phase Lobby (`MyGameMode.cpp:1541`).
* **Cancel.** `CancelLobbyStart` (`MyGameModeLobby.cpp:1027`): ships released or removed, teams inactive, phase Lobby,
  event `LobbyCancelled` (value = the cause). Then the lobby pawns come back: `ScheduleRespawn` for a dead pawn,
  `SpawnLobbyPlayers` for a controller without one (`:1056-1080`). A 1v1 / 2v2 team that empties during the countdown cancels it
  (`EvaluateTeams`, `MyGameMode.cpp:1006`; `OnCountdownEnd`, `:1229`). `BackToWaiting` cancels instead in the lobby
  (`:1378`).
* **Round start.** `BeginRound` (`MyGameMode.cpp:1360`): `TakeBackLobbyPawns` (`MyGameModeLobby.cpp:1407`, also every
  timed effect and every pending respawn), `SetInLobby(false)`, the lobby tick stops, `ResumeSwarm`, then
  `StartSessionIfHost` every round (`:1368`). `SpawnWaitingPlayers` puts practice aboard too (`:1485`).

### 2.2 Changes to the PR B flow (3.4)

* Practice starts aboard team 0's ship: `IsHoldingPawns` holds pawns in phase None and in every countdown with
  `bStartAboard` (`MyGameMode.cpp:712`), `SpawnWaitingPlayers` (`:1485`) and the late joiner in `RestartPlayer`
  (`:3014`) no longer need a versus round.
* A respawn with nobody landed goes to the path's first platforms when the match is on (`FindRespawnSpot`,
  `MyGameMode.cpp:3375`); the late joiner needs no landing either. A lobby pawn respawns at a lobby spot (`:3346`).
* `GetTeamProgress` skips platforms without SplineDistance (`MyGameMode.cpp:2838`).
* Respawns are not scheduled during the lobby countdown (`MyGameMode.cpp:3180`, `:3239`); everyone starts aboard at 0.

### 2.3 Match end, travel, arrivals (5.3, 5.4)

* `EndMatch` (`MyGameMode.cpp:1616`) decides `WillReturnToLobby` (`MyGameModeLobby.cpp:1475`), writes it into the game
  state's `bLobbyRound` and ends the session. Its timer calls `OnEndScreenDone` -> `ReturnToLobby` or `RestartMatch`.
  `EndMatch` does nothing in the lobby or its countdown.
* `RestartMatch` is `TravelToRound(false)` (`MyGameMode.cpp:1647`); `ReturnToLobby` is `TravelToRound(true)`.
  `TravelToRound` (`MyGameModeLobby.cpp:1497`) adds `?SeamlessTravel` to a ServerTravel when `bSeamlessTravel`, and
  `?Lobby=1` and Max Players for the lobby. The class flag `bUseSeamlessTravel` is not set. It logs
  `Match: back to the lobby, round n, seamless|hard (PIE, net.AllowPIESeamlessTravel 0)|OpenLevel: <url>`.
* `StartToLeaveMap` (`MyGameModeLobby.cpp:1671`): `ClearAllTimersForObject(this)`, pending respawns dropped, swarm stopped,
  `bRestarting`, bots removed. `ScheduleRespawn` does nothing once `bRestarting` is set.
* `InitSeamlessTravelPlayer` (`MyGameModeLobby.cpp:1646`): copy the team, set 255, `AssignTeam(..., Kept)`, then `Super`,
  then `OnPlayerArrived(PC, true)`.
* `OnPlayerArrived` (`:1608`), also from `PostLogin` (`MyGameMode.cpp:244`): host flag, `EnsurePilotComponent`,
  `EvaluateTeams` on the seamless path, log `Team: <name> arrives (hard|seamless), team X, phase Y`.
* `AMyPlayerState::CopyProperties` copies TeamId (`MyPlayerState.cpp:31`). No `Reset` override exists.
* `IsArriving()` = the replicated `bArriving` (`MyPlayerState.h:113`, `:145`). `AMyGameMode::PostSeamlessTravel`
  (`MyGameModeLobby.cpp:1749`) sets it on every carried player state before `Super` replaces the loaded ones. Not
  `bActorSeamlessTraveled`: the engine clears that before any game code runs (`World.cpp:9021`, `Level.cpp:3709`).
* `BeginRound` clears every ready flag and switch request (`MyGameMode.cpp:1362-1372`).
* The lobby's Players on the return URL is `GetReturnLobbyMaxPlayers` (`MyGameModeLobby.cpp:1553`, used at `:1631`).
* `TeardownLocalInput` and `TeardownGunnerInput` remove a mapping only when the local player's controller is this
  component's controller (`AirshipPilotComponent.cpp:159`, `:172`, `:922`).

### 2.4 Session (5.6)

* `PostLogin` keeps its StartSession only without the lobby (`MyGameMode.cpp:228`). `BeginRound` starts the session
  every round and advertises IN MATCH (`StartSessionIfHost`, `MyGameModeLobby.cpp:1706`).
* `UMultiplayerSessionsSubsystem::EndSession` (`MultiplayerSessionsSubsystem.cpp:436`) ends only from InProgress, with a
  completion delegate (`:463`). `StartSession` waits while the session is Ending (`:417`).
* `AdvertiseMatch(TeamMode, Difficulty, MaxPlayers, bInMatch)` (`:480`): one `UpdateHostSettings`. MaxPlayers 0 keeps
  the slots. Key `AuraSessionKeys::InMatch` (`MultiplayerSessionTypes.h:24`); `FAuraHostSettings::bInMatch` (`:78`) and
  `FAuraSessionInfo::bInMatch` (`:155`); written in `ApplyHostSettings` (`.cpp:1263`), read in `MakeSessionInfo`
  (`:1284`).
* Without a hosted session the game mode logs `Lobby: no session to advertise (in lobby|in match)`.
* Host Game travels with `?Lobby=1` when `bLobbyWhenHosting` (`MainMenu3.cpp:1313`).

### 2.5 Host leaving (4.9)

Nothing new: the pause menu's Leave kicks the clients first (exists). A client's leave reaches `Logout` ->
`EvaluateTeams(Leaving)`, which refreshes the start block and cancels a 1v1 / 2v2 lobby countdown.

### 2.6 Console (Appendix L-B, `MyLobbyConsole.cpp`)

`Aura.Lobby.Enable` (CVar, also in Shipping), `Aura.Lobby.Status`, `.Start [strict]`, `.Cancel`, `.Ready <i> <0|1>`,
`.Team <i> <0|1|255>`, `.Move <i> <0|1>`, `.Bots <n>`, `.Resolve [Auto|PlayerStarts|PathStart]`, `.Return`,
`.Zone [s]`, `.Panel <0|1>`. PlayerIndex = the index in `GameState->PlayerArray`. In phase Lobby, `Aura.Match.Rules`
goes through `ApplyLobbyRules` with the current Max Players (`MyMatchConsole.cpp:555`) and `Aura.Match.Start` starts
the lobby (`:653`). `Aura.Match.Status` has one `lobby:` line (`:483`).

`Aura.Lobby.Status` prints, for the harness:

```
LogMatch: Lobby status (<client|server|standalone> <world>): phase Lobby, in lobby 1, counting 0, countdown -1.0 s, lobby round 1, start block None, not ready 0, rematch 0, arriving 0, expected 2, teams 1 / 1, rules Teams=auto
LogMatch:   server: spawn PlayerStarts (request Auto), ground Floor (+ BP_MyHexPlatform_C_1), ground ready 1, zones 1, bots 0, will return to the lobby 1
LogMatch:   zone 0: min (x, y, z) max (x, y, z)
LogMatch:   player 0 <name>: id <PlayerId>, team 0, ready 0, request 255, host 1, arriving 0, bot 0, pawn <class> at X=.. Y=.. Z=..
LogMatch:   local 0 <PC>: panel 1 (widget 1), IgnoreInput 1, capture <EMouseCaptureMode int>, cursor 1, pause menu 0
```

Other log lines a harness can match: `Lobby: spawn PlayerStarts, ground ...`, `Match: phase Lobby (...)`,
`Lobby: start block <Block> (...)`, `Lobby: the host starts (...)`, `Match: phase Countdown 5.0 s (..., from the lobby,
...)`, `Lobby: start cancelled (<reason>: <Block>), back to phase Lobby`, `Lobby: N lobby pawn(s) taken back, M timed
effect(s) removed`, `Lobby: swarm resumed (...)`, `Lobby: <name> back to the lobby (left the zone) at ...`,
`Lobby message (<role> <world>): <text>`, `Lobby: rules applied, max players a -> b`, `Lobby: rules refused (...)`,
`Lobby: teams rebalanced for 2v2: ...`, `Lobby: <name> BLUE -> ORANGE (switch|swap|moved by the host|swapped by the
host), teams a / b`, `Lobby: bot Bot 1 joins BLUE`, `Match: leaving the map (game mode timers cleared)`, and the
airship's `refused (Locked: ...)`.

## 3. Deviations from the spec, and why

1. `ServerLobbyMovePlayer(APlayerState* TargetPlayer, uint8 TeamId)`: UHT refuses the parameter name `Player`
   (`APlayerController::Player` exists).
2. `AMyPlayerState::CopyProperties` is protected, as in `APlayerState`.
3. **Esc and the panel go through an interface.** `TogglePauseMenu` asks `AMyPlayerController2::GetLobbyPanel()`, an
   `IMyLobbyPanel` the widget registers with `SetLobbyPanel` (`MyPlayerController2.cpp:419`, `:455`). The spec says "the
   HUD's lobby widget". The HUD and widget do not exist yet, and this keeps the controller and the console
   (`Aura.Lobby.Panel`, `Aura.Lobby.Status`) free of the widget class. Without a registered panel Esc opens the pause
   menu (6.6).
4. **`ResumeSwarm` resumes only the spawners that ran when the lobby began** (`BeginLobby` records them). The spec says
   "StartWaves(false) on every wave spawner": that would start a never-armed internal-mode spawner from wave 1
   (`MechSentinelWaveSpawner.cpp` StartWaves). It needs `AMechSentinelWaveSpawner::IsStopped()`, a new one-line public
   getter (`MechSentinelWaveSpawner.h:233`).
5. **Rematch** needs "the URL had Round" (`MyGameMode.cpp:406`), not `RoundIndex > 0`: a return after practice keeps round 0.
6. **A lobby countdown cancels itself only for NeedOpponent.** Other hard blocks can't start during it, and NotReady with
   `bLobbyRequireReady` would cancel at every late join.
7. `ApplyRules` applies a team mode at once only in **phase Lobby**, not during the lobby countdown. The pause menu calls
   `ApplyRules` directly, and a rebalance during the countdown would move players after the ships were picked.
8. New setting `LobbyPathStartWait` (10 s, the spec's number in 3.1).
9. `TakeBackLobbyPawns` also drops pending respawns, so a dead lobby player starts aboard. Respawns are not scheduled
   during the lobby countdown ("none during the lobby countdown", 3.3).
10. `TeardownGunnerInput` has the same owner rule as `TeardownLocalInput`.
11. `AirshipLaneComponent.cpp:871` treats phase Lobby as "not started". No team ship exists in phase Lobby today; it is a
    guard.
12. `TravelToRound` adds `?SeamlessTravel` only to a ServerTravel (standalone uses OpenLevel). The player count leaves out bots.
13. `EndMatch` refuses in the lobby and its countdown (`Aura.Match.End` there has no match to end).
14. `ChoosePlayerStart` also uses the lobby starts in phase None of a lobby round: the host's StartSpot is picked at his
    login, before StartPlay, and the engine reuses it.
15. `TryBoard` and `TryMount` refuse with `Locked` too, so the console's `Aura.Airship.Board 0` logs the reason (LB1.2).
16. The `?Lobby=1` of Host Game (`MainMenu3.cpp:1313`) is done here although MainMenu3 is a menu file: without it the
    lobby is never reached from the menu.
17. Event values: `LobbyCancelled` = the cause block (0 = the host), `LobbyTeamChanged` = the PlayerId (-1 for a
    rebalance), `LobbyRulesChanged` = Max Players, `LobbyReturn` = the next round.
18. New helper `UMyTeamLibrary::GetLobbyStartBlockText` (`MyTeamLibrary.cpp:246`): the widget and the server's refusals
    show the same text.

## 4. For the UI agent: the C++ interface

Everything below is built and compiles. Bind to it; do not change it without telling the lead.

**Game state** (`MyGameState.h:148-185`, any machine, replicated, `OnMatchChanged` on every change):
`IsLobbyRound()`, `IsInLobby()`, `IsLobbyCountingDown()`, `GetLobbyStartBlock()`, `GetLobbyConfirmBlock()`, `GetLobbyNotReady()`,
`IsLobbyRematch()`, `CountArrivingPlayers()`. Reused: `GetMatchPhase()`, `GetMatchRules()`,
`GetTeamState(t).NumPlayers`, `GetExpectedPlayers()` (= Max Players in the lobby), `GetPhaseEndServerTime()` (the
countdown's end), `GetServerWorldTimeSeconds()`. `OnMatchEvent` sends `Countdown` at the lobby start and
`LobbyCancelled`, `LobbyTeamChanged`, `LobbyRulesChanged`, `LobbyReturn`.

**Player state** (`MyPlayerState.h:95-120`): `IsLobbyReady()`, `GetRequestedTeam()` (255 = none), `IsHost()`,
`IsArriving()`, `GetTeamId()`, `OnLobbyChanged`, `OnTeamChanged`. Ping: `GetPingInMilliseconds()`. A carried player
state and its replacement share `GetPlayerId()`: dedupe rows by PlayerId, the one not arriving wins (6.4).

**Controller** (`MyPlayerController2.h:107-159`):

* Requests: `ServerLobbySetReady(bool)`, `ServerLobbyRequestTeam(uint8)` (255 cancels),
  `ServerLobbySetRules(const FMyMatchRules&, int32 MaxPlayers)`, `ServerLobbyStart(bool bForce)`,
  `ServerLobbyCancelStart()`, `ServerLobbyMovePlayer(APlayerState* TargetPlayer, uint8)`.
* Answers: `ClientLobbyMessage` -> `OnLobbyMessage` (native multicast, `const FText&`).
* Panel: `SetLobbyPanel(UObject*)`, `GetLobbyPanel()`.
* Pause menu: `OpenPauseMenu()` (the MENU button), `IsPauseMenuOpen()`.

**`IMyLobbyPanel`** (`Match/MyLobbyPanel.h`): `OpenPanel()`, `ClosePanel()`, `IsPanelOpen() const`.
`UMyLobbyWidget` must inherit it (`class UMyLobbyWidget : public UMyUserWidget, public IMyLobbyPanel`), call
`PC->SetLobbyPanel(this)` in NativeConstruct and `SetLobbyPanel(nullptr)` in NativeDestruct. Esc then reaches it from
`TogglePauseMenu`; with UI-only input the panel itself must close on Esc / Gamepad B (`NativeOnKeyDown`).

**Team library** (`MyTeamLibrary.h:83-117`): `IsInLobby`, `IsLobbyCountingDown`, `AreShipsLocked`, `IsDamageOff`,
`GetTeamModeMaxPlayers`, `IsHardLobbyStartBlock`, `GetLobbyStartBlockText(World, Block, NotReady)`,
`GetMatchPhaseName`, `GetTeamModeOption`, and the old `GetTeamName` / `GetTeamColor`.

**Host-only game mode calls** (the pause menu runs on the host): `WillReturnToLobby()`, `ReturnToLobby()`,
`RequestStartMatch()` (starts the lobby with force in phase Lobby), `IsLobbyRound()`, `IsInLobby()`.

**Other owners' files the UI pass still has to change** (spec section 7):

1. `UMyLobbyWidget`, `UMyLobbyPlayerRow` (6.3) and `AMyHUD::LobbyWidgetClass` / `AddLobbyWidget` / `GetLobbyWidget` (6.1).
2. `MyMatchHUDWidget.cpp`:
   * the phase Lobby strip (6.6);
   * Ended: "Back to the lobby in n s" when `IsLobbyRound()`;
   * the lobby event toasts;
   * the `EAirshipUseRefusal::Locked` toast: `HandleUseRefused` returns for anything but EnemyShip today.
3. `PauseMenu3.cpp`:
   * START MATCH in phase Lobby (it calls `RequestStartMatch`, already lobby-aware);
   * **hide the Restart row while `IsInLobby()`**: today it shows in the lobby countdown (phase Countdown), and
     `RestartMatch` reloads without the lobby;
   * BACK TO LOBBY when `WillReturnToLobby()`;
   * public `RequestLeaveSession()`;
   * Open Lobby on a running match: set `Settings.bInMatch`, and skip its StartSession while `IsInLobby()`.
4. `MainMenu3`: `GetDefaultRuleSets()` etc. (6.3); `GetTeamModeMaxPlayers` may forward to the team library.
5. `SessionEntry3`: IN LOBBY / IN MATCH from `FAuraSessionInfo::bInMatch`.
6. Scripts as_77 / as_78 (widgets, BP_MyHUD) and the harnesses as_79 / as_80. as_74 / as_75 need the one-line practice
   change (7.7): no pawn during the 5 s countdown, then aboard team 0's ship.

## 5. Not checked

* Nothing ran. PIE uses the IP driver, so a PIE pass proves nothing about Steam travel (RL4). The two-machine Steam test
  of the seamless return is still to do (8.5).
* The adaptive build compiled the changed files outside the unity blobs. My new files use named namespaces, so a clean
  unity build should not clash; it was not built that way.
* PIE travels hard by default: `ProcessServerTravel` logs a Warning ("Seamless travel is disabled in PIE") on every
  restart and return. That is expected.

## 6. Not in this pass

The widget and HUD code, the pause menu, the main menu statics, `SessionEntry3`, and the editor scripts as_77 to as_80
(section 4). The deferred items of spec 8.7: a separate lobby map, a loading screen, the editor's Add Client.

## 7. Q-L1 to Q-L4 (never answered: these defaults are in the code)

1. Q-L1: the floor and the platform stay after Start; the `LobbyOnly` tag hides tagged actors outside the lobby (none
   tagged).
2. Q-L2: without the floor the lobby moves to the path's first platform by itself (`LobbySpawn` Auto).
3. Q-L3: Play Solo goes straight into practice; practice starts aboard team 0's ship.
4. Q-L4: ready flags are shown. The host starts anyway with a second click; a rematch needs none. `bLobbyRequireReady`
   makes them required.

## 8. Review fixes (2026-11-28, `REVIEW_lobby.md`)

1. **Arrivals.** `IsArriving()` reads a replicated `bArriving` (`MyPlayerState.h:113`), set by the new
   `AMyGameMode::PostSeamlessTravel` (`MyGameModeLobby.cpp:1749`). Log: `Match: seamless arrival, N carried player
   state(s) arriving until their owners load`. `BeginRound` clears ready flags and requests (`MyGameMode.cpp:1362`).
2. **Return URL Players.** `GetReturnLobbyMaxPlayers(NumPlayers)` (`MyGameModeLobby.cpp:1553`): `GetLobbyMaxPlayers`, at
   least the players in, and outside a lobby round at least the hosted session's slots.
3. **Cancel gives pawns back** (`MyGameModeLobby.cpp:1056-1080`).
4. **Confirm block.** `AMyGameMode::GetLobbyConfirmBlock` (`:878`) decides over every block; the game state replicates
   it (`MyGameState.h:167`, `:289`); `SetLobbyStartBlock` takes it (`MyGameState.cpp:362`).
5. **Free-ship fire.** `UMyTeamLibrary::GetFiringTeamId` / `IsTeamFireBlocked` (`MyTeamLibrary.cpp:138`, `:161`), used by
   `AAirshipCannonball::InitCannonball` (`AirshipCannonball.cpp:93-95`) and the turret (`AirshipTurret.cpp:742`, `:792`).
6. **`ClientLobbyMessage` is Reliable** (`MyPlayerController2.h:153`).
7. **`UPauseMenu3::NativeDestruct`** gives the input back when it is removed while open (`PauseMenu3.cpp:315`).

The UI side (widget, rows, scripts) is in `NOTES_lobby_ui.md` section 7.
