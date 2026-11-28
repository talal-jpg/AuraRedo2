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

## 9. Editor stage fixes (2026-11-28, step 2: the solo run as_79)

First run: `{'PASS': 13, 'FAIL': 4, 'SKIP': 1}`. After the fixes below, every check passed in a re-run of only the
failing or affected checks (`AS79_ONLY` wrappers, three re-runs): `{'PASS': 17, 'SKIP': 1}` in all. Reports:
`Saved/Match/b79_run1/`, `b79_run2_fix1/`, `b79_run3_fix2/`, `b79/` (the last run, LB1.8).

**C++ (one change, rebuilt with `build_r2.sh`, exit 0, no new warnings)**

1. `MyHUD.cpp:109-122`, `AMyHUD::AddLobbyWidget`: the panel now goes into the viewport layer
   (`UGameViewportSubsystem::AddWidget`, ZOrder 5), not the player layer (`AddWidgetForPlayer`). The engine draws the
   whole player layer under every `AddToViewport` widget (`SGameLayerManager.cpp:131-143`: `EGameLayerOrder::Player` <
   `Viewport`), so the HUD overlay (`OverlayWidget->AddToViewport()`, ZOrder 0) drew its globes, ability icons and
   crosshair over the panel, its LANE ASSIST box and its START button, and could take their clicks. Seen in the window
   grabs of the first run (`media/r2b_lobby_before_layer_fix.jpg`); fixed in `media/r2b_lobby_panel.jpg`. The pause
   menu (viewport layer, 50) stays above the panel. The match HUD (2) and the minimap (1) stay in the player layer.
   Checks: LB1.1_panel and LB1.4_rules, re-run, PASS.

**Widget (as_77, `AS77_REBUILD = True`, 0 missing / wrong class / not variable, 0 style fallbacks)**

2. `as_77_lobby_widget.py:555-570`, the player row: the name column is 270 px (was 250), clipped, with an ellipsis, and
   the status keeps a 12 px gap. The PIE name "talal-01A2215176EF71" ran past the 250 px column into HOST.

**Harness (no threshold changed)**

3. `as_70_matchlib.py:1026`, `ground_at`: `HitResult.to_tuple()`. UE 5.8 Python has no
   `GameplayStatics.break_hit_result` (as_62 found this), so every ground trace failed with a script error.
   as_74 uses this too.
4. `as_79_pie_lobby.py:130`, `placed()`: exact names. The prefix `BP_MyHexPlatform_C_1` also matched the path spawner's
   `BP_MyHexPlatform_C_10` .. `_19`, and LB1.8 destroyed ten path platforms with the floor.
5. `as_79_lobbylib.py:33-44`, `log_wait` / `event_wait`. The log tail reads the editor log file, and a C++ line reaches
   it a frame or more after it is logged. LB1.3 (`:247`), LB1.5_cancel (`:360`) and LB1.9 (`:506`) read their line in
   the same frame as the state change, so they found none, although the lines are in the log. They now wait up to
   1-2 s for it. The timed parts of these checks read the state, not the log.
6. `as_79_pie_lobby.py:466-485`, LB1.8: the respawn's platform comes from the pawn's movement base, then from a trace
   that ignores the pawn, then from the path platform whose bounds hold him. The trace used to hit the pawn's own
   capsule. One respawn stood on `BP_MyHexBridge2_C_26`, a bridge end on a path tile (`FindRespawnTile` picks path
   tiles first). The passing run stood on `BP_MyHexPlatformBottom_C_1` (SplineDistance 4000) through its base.
7. `as_79_pie_lobby.py:329`, the new knob `AS79_HOLD` (default 0): after LB1.4's and LB1.7's checks it holds the open
   panel for window grabs. `xgrab_loop.sh` takes about 3 s per grab of the 5094 x 1366 editor window, and the panel is
   open for under a second between those tests.

### 9.1 Lane check (as_74 main pass, only T2.1, T2.4, T2.7, T2.10; settle always runs)

This is Talal's first ask, and the lean runs never exercise it. First run: settle T1.1 / T1.2 PASS, **T2.7 PASS**
("parked in the lane again and unmounted": Cruising 0.0 s after the exit, 6 m/s after 2.2 s), T2.1, T2.4 and T2.10
FAIL. Reports: `Saved/Match/b74_main_lanes_run1/`, `b74_main_lanes_fix1/`, `b74_main/` (the last run, T2.4).

8. `as_74_pie_match.py:763-783`, T2.4: before `RequestFire`, the harness aims the view 200 m abeam until the camera is
   at least 75 deg off the bow. Round 2 part A added the driver turret arc (`DriverTurretArcDeg` 50): in that arc
   `RequestFire` drives the turrets and fires no broadside (`AirshipPawn.cpp:3711-3715`, `:3214`). as_74 was written
   before that. Setting the control rotation for 3 frames was not enough, because the camera lags. After the fix the
   ball spawned at once with the camera 77.7 deg off the bow: PASS. Assist and 6 +-0.5 m/s held in every run.
9. `as_74_pie_match.py:1024`, T2.10: the `ShipReturning` event is read after the wait for Cruising. It is logged in the
   same frame as Parked -> Returning, and the same-frame read found no line (the log lag of fix 5). PASS: Returning at
   20.0 s, Cruising at 46.0 s, no hull damage.
10. **T2.1 is still FAIL, and it is not fixed here (the threshold rule).** Everything in T2.1 passes except the peak:
    the ship settled 40.11 m ahead in TeamPace, overshoot 0.33 m, ramp 2.50 m/s^2. The peak was 25.2 m/s, and the
    harness wants 27-29 m/s (`as_74_pie_match.py:630`). SPEC_B T2.1 says "speeds up ... to **at most** 28 +-1 m/s". At
    the 2.5 m/s^2 ramp that the same check requires, 28 m/s and back needs about 310 m: 4 -> 28 m/s takes about 154 m,
    and 28 -> 0 takes about 157 m. The player at u 200 m gave the ship 250 m (210 m behind him plus the 40 m lead), so
    25.2 m/s is the most it could reach. Two choices for the lead: read "at most" as written (`peak <= 29.0`), or put
    the T2.1 player at u >= 320 m. **Resolved in the final pass (section 11, row 18): the player at u 350 m, PASS.**

## 10. Editor stage fixes (2026-11-28, step 3: the multiplayer run as_80, and the review of steps 1-3)

Step 3's runs: `Saved/Match/b80_run1/` (`{'PASS': 14, 'FAIL': 6, 'SKIP': 4}`, stopped) and `b80_fix1/` (`{'PASS': 7,
'FAIL': 2, 'SKIP': 8}`, the worlds did not come back after the lobby return). Backups of the files changed here:
`Saved/Match/backup/step3/` (step 3) and `Saved/Match/backup/step4/` (the review fixes).

**C++ (rebuilt with `build_r2.sh`, exit 0, only the two old bIsFocusable warnings: `build_r2_095101.log`, then
`build_r2_101738.log`)**

1. `MyGameModeLobby.cpp:1673-1680`, `AMyGameMode::TravelToRound`: `ServerTravel(TravelURL, /*bAbsolute=*/false)` (was
   `true`), plus `?Lobby=0` when this map's URL had a Lobby option and the next round has no lobby. Why: an absolute URL
   takes FURL's default port (7777) for the next map (`GameModeBase.cpp:490`, `UnrealEngine.cpp:15955` browse
   `FURL(&LastURL, NextURL, NextTravelType)`), while every remote client is sent `ClientTravel(URL, TRAVEL_Relative)`
   (`ProcessClientTravel`) and comes back to its old host and port: 17777 in PIE (`UGameInstance::EnableListenServer` sets
   `LastURL.Port` to the PIE ServerPort), `-port=` elsewhere. The host listened on 7777, and the client was left frozen on
   the end screen ("Back to the lobby in 0 s", `xgrab_b80/x_LM1.8_return_092839_client.png`). A relative URL keeps
   `LastURL`'s port and options (`URL.cpp:159-175`); a new option replaces an old one with the same key (`FURL::AddOption`).
   Every option InitGame reads is written again here (Teams, ShipLives, Swarm, TimeLimit, FF, GrappleShips, LaneAssist,
   Players, Match, Round, Lobby when returning to the lobby; SeamlessTravel whenever the setting is on), and the `?Lobby=0`
   covers a restart without the lobby after a lobby round. Check: LM1.8_return (and LM1.9 to LM1.13 after it).
2. `AirshipPawn.cpp:416-418`, the constructor: `StationAims.Init(FVector_NetQuantize(ForceInitToZero), NumStations)` (was
   `SetNum`). `FVector_NetQuantize()` leaves the vector uninitialized, and every team ship's first replication logged
   "LogCore: Error: WriteQuantizedVector: Value isn't finite" plus a NetSerialize warning (pre-existing from PR A,
   `Aura-backup-2026.11.28-09.42.30.log:5349`). Not serialized in BP_AirshipPawn or StartupMap (no `StationAims` name in
   either file), so the constructor value is what every ship starts with. Check: the as_80 log's error list.
3. `MyMatchHUDWidget.cpp:448-449`: in a lobby round the match bar's countdown reads "MATCH STARTS IN n" like the lobby
   widget's large text (it said "FIGHT STARTS IN n" under "MATCH STARTS IN n" in versus); outside the lobby, versus keeps
   "FIGHT STARTS". `:489-492`: DEFEAT is drawn in ink, not in the winner's colour (the orange loser saw a blue DEFEAT).
   Cosmetic; seen in the as_80 window grabs.

**Widget (as_77, `AS77_REBUILD = True`: 0 missing / wrong class / not variable, 0 style fallbacks, 106 widgets)**

4. `as_77_lobby_widget.py:605-621`: LobbyPanel (1640 x 960) now sits in a SizeBox in a ScaleBox (`PanelScale`, ScaleToFit,
   DownOnly, the full viewport less 24 px; both SelfHitTestInvisible). The DPI scale follows the short side, so a viewport
   narrower than about 16:10 cut the LOBBY tag, the names and START off at both sides (the editor's PIE viewport:
   `xgrab_b80/x_None_092725_main.png`). The C++ only shows and hides LobbyPanel, so nothing else changes.
5. `as_77_lobby_widget.py`, the team lists: 236 px high (was 272). With the SWITCH TO row shown, the column ran past 960
   and the START label sat on the card's bottom edge (`media/r2b_lobby_panel.jpg`).

**Harness (no threshold loosened; two checks got a positive control)**

6. `as_80_pie_lobby_mp.py` (step 3): `core.EnsureAlwaysEnabled 0` for the run (the engine's PIE-only ensure in
   `PackageMapClient.cpp:3145` dumped a callstack on every client move while the old client world waited for the hard
   travel, taking PIE to 3 fps); a world swap is detected by the server clock going back (the new world came back behind
   the old Python wrapper); LMF restaged (players aboard their own ships where LM1.6 put them, the ships held by debug
   input, a settled aim before each window, hull shots at z 150 below the deck plane so `FindTurretBehindHullHit` cannot
   move them to a turret; turret health and crosshair data); LMF_players on one platform with a settled aim; the
   TeamEliminated / LobbyCancelled reads wait for the log line.
7. `as_80_pie_lobby_mp.py`, LM1.3_no_damage: also needs >= 1 server hit on the client in its window (the "HitActor:
   <pawn>" line GA_GunShoot prints to the log once a target passed the friendly-fire and ship filters, before the
   damage-off attribute set), after a settled aim. Before, "no drop" passed whenever every shot missed. LMF_players logs
   the same hit counts as data.
8. `as_79_pie_lobby.py`, LB1.2_locks: the free ship from `Aura.Airship.Spawn` had the player behind its stern, outside
   both turret arcs (yaw -110 .. 30 / -30 .. 110 deg from the bow, pitch -20 .. 40): its turrets never fired at him, and
   the log shows "TurretFire: fire at" then "stop" with no hit. Now the ship is turned to face him 100 m out (about 16 deg
   down from the forward-deck turrets), and the check needs >= 1 "hit <pawn>" line (`log LogAirshipTurret VeryVerbose` for
   the window, `AAirshipTurret::ApplyBulletDamage`) besides no health drop.
9. `as_80_pie_lobby_mp.py`, LM1.6_input: a WARN line when the injected IA_Move moved the client 0 cm (the flags decide;
   run 1 had 0.0 cm, fix 1 had 522 cm).

**Found by the step 4 runs (C++ rebuilt: `build_r2_104022.log`, exit 0, no new warnings)**

10. `MechSentinelClientBubble.h:88` / `.cpp:245`, new `AMechSentinelClientBubbleInfo::Tick`: returns without ticking when
    the serializer's World is null or not the actor's world. A client keeps its copy of this replicated actor through a
    seamless travel (`FSeamlessTravelHandler` keeps every non-startup actor the client does not own, `World.cpp:8743`), and
    GC nulls the serializer's World (a Transient UPROPERTY, `MassClientBubbleSerializerBase.h:48`) with the old world. The
    engine handler's `check(World)` (`MassClientBubbleHandler.h:736`) then killed the process on the seamless return to the
    lobby: as_80 run 1 of step 4, LM1.13, "Assertion failed: World" in `TClientBubbleHandlerBase<FMechSentinelFastArrayItem>
    ::Tick` (`Saved/Match/b80_s4run1/Aura_crash_LM1.13.log`). In a packaged game this is every client on every seamless
    lobby return (the Steam path), whenever the sentinel bubbles exist. With the guard, run 2's seamless return completed:
    "Match: seamless arrival, 2 carried player state(s)", both players "arrives (seamless)", phase Lobby, no assert or
    ensure after it. Check: LM1.13 (its checks did not complete, see 13).
11. `as_80_pie_lobby_mp.py:650-668`, LMF stage: the client is put back on his spot aboard team 1's ship (hull space) after
    the ship is moved beside team 0's. A teleported ship does not carry its deck riders: run 1 left him 91 m beside it,
    falling, and his shots at team 0's hull went into the platforms.
12. `as_80_pie_lobby_mp.py:893-901`, LM1.12_reopen: the menu world's name is read before the `open` (the open replaces
    that world, and the check text's `mw.get_path_name()` raised "World: Internal Error" in run 1, so the reopen never
    reported). Run 2: PASS, back after 0.2 s.
13. `as_80_pie_lobby_mp.py:921-934`, LM1.13: after the seamless travel the client is mapped again once his new world is
    there. B75 found the server's new world first and mapped the client to his OLD world (still listed until his own
    travel ends); every read of it then failed (run 2: 601 `phase_of` errors, then the test stopped). Ran in the final
    pass, where it proved still too early (section 11, row 15).

**Results (step 4)**

* as_79 (standalone, `AS79_ONLY = ('LB1.2',)`, `Saved/Match/b79/`): `{'PASS': 5, 'SKIP': 1}`. LB1.2_locks: 12 rounds hit
  the player, no health drop. LB1.1_panel PASS with the ScaleBox panel (`media/r2b_lobby_panel_scalebox.jpg`).
* as_80 run 1 (listen 2, LM1.3, LM1.6, LMF, LMS, LM1.8 to LM1.13; `Saved/Match/b80_s4run1/`, no report: the editor
  crashed in LM1.13): PASS LM1.1 x2, LM1.3 (6 server hits, no drop), LM1.6 x3, LMF_players (enemy [1.0] with 6 hits,
  teammate none with the crosshair on him 8 of 8 samples and 0 hits), LMS x2, **LM1.8_return** (teams, rules kept, ready
  false), **LM1.9, LM1.10, LM1.11**, LM1.12_cancel. FAIL LMF_own_ship (the client's stage, fix 11), LM1.12 (harness, fix
  12), LM1.13 (editor crash, fix 10).
* as_80 run 2 (LM1.6, LMF, LMS, LM1.8, LM1.12, LM1.13; `Saved/Match/b80_s4run2/`): `{'PASS': 10, 'FAIL': 3, 'SKIP': 3}`.
  PASS LM1.1 x2, LM1.6 x3, LMS x2, LM1.8_return, LM1.12_cancel, LM1.12_reopen. FAIL LMF_own_ship, LMF_players (see
  below), LM1.13 (harness, fix 13; the product's seamless return worked, fix 10).
* The panel fits the editor's narrow PIE viewport (`media/r2b_lobby_panel_pie_narrow.jpg`); DEFEAT in ink
  (`media/r2b_defeat_ink.jpg`); the bar and the lobby both read "MATCH STARTS IN n" in a lobby countdown.

**Was open: the listen host's gun in LMF.** In run 2 (and step 3's fix 1) the host's gun made no server hit after the
match start (crosshair on the enemy hull 7 of 8 samples, on the enemy player 6 of 8, no "HitActor" line in the session);
in run 1, which fired in the lobby first (LM1.3), it worked. **Resolved below (14): the harness, not the product.**

**Open item 1 (2026-11-28, after step 4): the host's gun was the harness's input injection. No C++ change.**

14. `as_70_matchlib.py:1081-1105`, `MBRun.subsystem` (+ the new `sub_in`, and `mb_wkey` at `:226`): the Enhanced Input
    subsystem a test injects into is now cached by the world's PATH and re-checked against the world on every use. The
    old cache key was `mb_name(w)`, and both PIE copies of the map have the object name "StartupMap"
    (`/Game/Maps/UEDPIE_0_StartupMap.StartupMap` and `UEDPIE_1_...`), so every machine got the subsystem of the world that
    was looked up FIRST in the run. In run 2 and fix 1 that was the client (LM1.6_input injects his IA_Move): every
    IA_LMB that `fire_at` meant for the host went into the client's local player (`fire_at` still aimed the host's view,
    through his own controller, so his crosshair data looked right). In run 1, LM1.3 looked the host up first, and it was
    the other way round: the client's IA_Move moved the host (LM1.6_input's "moved 0.0 cm" WARN of run 1 and of step 3's
    run 1), and the client's LMF shots went to the host. The same name key was in `dump()` (`:824`) and `capture()`
    (`:1152`); both are only called with one world today, and they now use `mb_wkey` too. Backups:
    `Saved/Match/backup/item1/`.

    **The probe** (one listen run, `Saved/Match/b80_item1_probe/`: wrapper `as80_gunprobe.py` = `AS80_ONLY = ('LM1.6',
    'LMF', 'PROBE')`, no LM1.3, `log LogAbilitySystem Verbose` in the probe windows; report, result, harness log and the
    editor log `Aura_item1_probe.log`). After the start, with the two players on one platform 15 m apart, the host's view
    on the client for 1.5 s in each window:
    * The old lookup (the pre-fix code, verbatim, primed client first as in run 2) returns `LocalPlayer_1` (world
      `UEDPIE_1`, the client) for BOTH worlds; the fixed lookup returns `LocalPlayer_0` (`UEDPIE_0`) for the host's world
      and `LocalPlayer_1` for the client's.
    * Window A (old lookup): 0 "HitActor" lines on the client, no drop. The only gun activation was the CLIENT's: his
      own machine `Activated [12] GA_GunShootBP_C_0 ... PredictionKey: [17/0]`, then the server's
      `InternalServerTryActivateAbility: Accepted ClientActivation of Default__GA_GunShootBP_C with PredictionKey [17/0]`
      (`Aura_item1_probe.log:5265-5267`); his crosshair was on a platform pillar, so it hit nothing. The host's
      `AbilitySystem.Ability.ListGranted`: `GA_GunShootBP_C (Local Predicted - Client Or Server)`, not active.
    * Window B (fixed lookup): `BP_MyPlayerState_C_0: Activated [5] GA_GunShootBP_C_0 ... PredictionKey: [Srv: 8]` (a
      server key: the host's own activation, `:5322`), 0 "Accepted ClientActivation", ListGranted `**ACTIVE**`, 6
      server "HitActor: BP_MyCharMech_C_4" lines, each one exactly 1 Health (GA_GunShoot's own PrevHealth / NewHealth
      prints: 104 -> 103 ... 100 -> 99, 96 -> 95).
    * The product side, read on both server ASCs mid-window: user ability activation not inhibited, GA_GunShootBP_C_0
      granted, its asset tags not blocked (`AreAbilityTagsBlocked` false; the tag lists themselves did not read from
      Python); the lobby's damage-off gate is the attribute set's IncomingDamage
      (`MyAttributeSet.cpp:83`), after the HitActor line, so it can't stop a hit from being logged.
    * Checks: `PROBE_cause` PASS. `PROBE_host_gun_after_start` FAIL by its own text only: the drops were [1.0, 3.0]
      against a wanted [1.0]. The 3.0 is not the gun (every gun hit is 1, see above; 99 -> 96 came between two gun hits):
      something else hit both players for 3 per hit, most likely the swarm (it resumes at the start): the host, whom
      nobody shot, lost 3.0 in window A and 21 = 7 x 3.0 in window B. The probe's want was not changed.
    * **The real checks in the same run, after the start, without LM1.3:** `LMF_own_ship` PASS (host on the enemy hull
      [5.0], client on the enemy hull [5.0], neither on his own ship: every half in ONE run) and `LMF_players` PASS
      (enemy [1.0] with 6 server hits, teammate none with 0 hits). LM1.6_input: the client's IA_Move moved him 522 cm.
      Report head `{'PASS': 8, 'FAIL': 1, 'SKIP': 3}` (the FAIL is the probe line above).

## 11. Final evidence pass (2026-11-28): harness fixes only, no C++ change

The runs:

* as_80, all scenarios with the seamless test last (`Saved/Match/b80_final_run1/`): `{'PASS': 22, 'FAIL': 2, 'SKIP': 3}`.
  Every LM and LMF check passed except LM1.13_seamless and LM1.13_third_start. That includes LMF_own_ship and LMF_players,
  with every half, in a run where LM1.3 and LM1.6 ran first.
* LM1.13, fix 1 (`b80_final_fix1_lm113/`): `{'PASS': 3, 'FAIL': 1, 'SKIP': 3}`. Third start PASS. Seamless FAIL on the IMC
  read only.
* LM1.13, fix 2 (`b80_final_fix2_lm113/`): the same head. The probe showed that the IMC read was the harness's (row 17).
* as_74 T2.1 (`b74_main_t21_final/`): `{'PASS': 3, 'SKIP': 1}`.

No crash in any of these runs. Backups of the files changed here: `Saved/Match/backup/final/`.

15. `as_80_pie_lobby_mp.py:986-1000`, LM1.13: after the travel, the harness waits for every player's "Team: <name> arrives
    (seamless)" line (30 s). Then it waits for one player controller per player on the server and one on the client
    (`pc_count`, `:235`, 20 s). Only then, after 1 s, does it map everyone again, with the host first.
    * Why: the final run mapped the players as soon as the new worlds were there. In 5.8,
      `AGameModeBase::HandleSeamlessTravelPlayer` (`GameModeBase.cpp:607-641`) spawns a NEW controller for every player:
      for the host in PostSeamlessTravel, and for the client only when his `ServerNotifyLoadedWorld` comes in.
    * Until then the server's list holds the client's carried old controller. Until the client acknowledges the swap
      (`UNetConnection::HandleClientPlayer`, NMT_PCSwap), his world holds the old one too.
    * The first map therefore read the carried old objects. The result: "a new object False", no pilot component,
      teams `{1: 0, 0: 0}`, and in the third start "both aboard False", plus 2 `schar` errors (`ObjectInstance is null`).
    * In both fix runs: every arrival line, server 2 / client 1 controllers, mapped again. Then: the client's controller
      `BP_MyPlayerController2_C_0 -> _C_1` (a new object), the pilot component on both machines, and the teams kept.
      Also: equal platform and ship counts after 5 s (65 / 65, 0 / 0), no GC error, no fall death, "seamless arrival,
      2 carried", 0 arriving after 5 s, and the third start with both aboard.
    * The product's seamless path did what SPEC_B_LOBBY 5.4 rows 4-7 and 13 describe.
16. `as_80_pie_lobby_mp.py`, LM1.13: the teams before and after the travel are keyed by player NAME (the join order, the
    PlayerArray order, changes in a seamless travel; `APlayerState::CopyProperties` keeps the name).
17. `as_79_lobbylib.py:238`, `has_board_mapping`, and `as_80_pie_lobby_mp.py:253`, `imc_probe` (new): the IMC read is now
    `has_mapping_context(imc) is not None`.
    * Why: `HasMappingContext(Context, int32& OutFoundPriority)` returns a bool with an out parameter. UE Python then
      returns `None` when the C++ returns false, and the out value when it returns true (`PyGenUtil.cpp:2669-2674`).
    * IMC_AirshipBoard's priority is 0 (`UAirshipSettings::BoardMappingPriority`), so `bool(0)` read a mapped context as
      missing.
    * Fix 2's probe recorded `0` for IMC_AirshipBoard and for the controller's own IMC_PlayerInputMappingContext. That
      was on both machines, before the travel, at once after it, and 5 s later.
    * So the context was mapped on the client after the seamless return, and SPEC_B_LOBBY 5.4 row 10's guard holds. One
      correction to that row: in 5.8 the applied contexts live on the controller's `UEnhancedPlayerInput`
      (`EnhancedInputSubsystemInterface.cpp:265-270`, `EnhancedInputSubsystems.cpp:73-81`), not on the local player.
      The new controller's pilot component adds its own context, so the guard only stops the old controller's teardown
      from removing it through the shared subsystem.
    * LM1.13 now takes the IMC read 5 s after the map (like the counts) and logs the positive control and the earlier
      reads as data.
    * **This read has not run since the fix** (the pass allowed two fix rounds). `as_60_pie_mp_round2.py:790-796` (part
      A) has the same `bool()` read; its airship context is not at priority 0 there, so it was not touched.
18. `as_74_pie_match.py:587-594`, T2.1: the player stands at u 350 m (was 200 m; the lead's call: u >= 330 m, the band
    unchanged).
    * Result: peak 28.05 m/s (27-29), settled 40.13 m ahead in TeamPace, overshoot 0.38 m, ramp 2.50 m/s^2, lateral,
      vertical and heading 0.
    * A 1D model of the pace law (0.3 /s gain, 15 m aim, 6 to 28 m/s, 2.5 m/s^2 ramp, sqrt brake into the cap) gives
      25.3 m/s for the old staging (25.2 measured) and 28.0 from u 300 m on.
    * At u 350 m the path extends first (within ExtendDistance of the 400 m end), so the cruise end is never the clamp.

**Seen in the final run, not PR B:** an engine PCG ensure (`!Container->bAreResourcesInaccessible`,
`PCGManagedResourceContainer.cpp:353`). It fired on the client when the server closed an `AMyHexBridge`'s channel during LMS
(`AMyHexBridge::EndPlay` -> `UPCGComponent::EndPlay`), and it is 8 of the run's log lines. The client also logs "GiveAbility
called ... on the client, not allowed!" for the startup abilities at every pawn spawn, from the first spawn of the run on.
