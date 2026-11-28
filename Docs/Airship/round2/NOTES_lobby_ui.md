# Round 2, PR B: lobby UI notes

The UI of `SPEC_B_LOBBY.md` (revision 2) section 6, on top of the lobby core (`NOTES_lobby_core.md`), in the worktree
`_AirshipWorkB` (branch `airship-r2-prb`, base e9636cc). It covers the lobby widget, the HUD hook-up, the match HUD's
lobby parts, the pause menu, the main menu lists, and the session rows. It also adds the editor script that builds the
widgets and the two lean PIE harnesses.

**Status.** It builds with `_AirshipWork_logs/build_r2b.sh`: Result Succeeded, `build_r2b_052927.log`. There are no new
warnings. The only warnings are the old `bIsFocusable` ones in `MainMenu.cpp` and `MainMenu2.cpp`.

**Review fix pass (2026-11-28, `REVIEW_lobby.md`).** Built again: `build_r2b_061106.log` and `build_r2b_061456.log`,
Result Succeeded, no new warnings. Section 7 lists what changed in the widget, the rows and the scripts. Line numbers in
sections 2 and 4 are from before that pass; section 7 has the new ones.

**Nothing has run.** No editor, no PIE and no scripts ran. Nothing is committed. The scripts passed a syntax check and a
local name check only: every global they use is defined, and every `self.x()` they call exists. That check is
`scratchpad/flake/check.py`.

All line numbers are in the worktree as it is at the end of this pass.

## 1. Files

| File | What |
|---|---|
| `Source/Aura/Public/Match/MyLobbyWidget.h`, `Private/Match/MyLobbyWidget.cpp` (new) | `UMyLobbyWidget`: the panel, the compact strip, the countdown, messages; implements `IMyLobbyPanel` |
| `Source/Aura/Public/Match/MyLobbyPlayerRow.h`, `Private/Match/MyLobbyPlayerRow.cpp` (new) | `UMyLobbyPlayerRow`: one player in a team list |
| `Source/Aura/Public/UI/MyHUD.h`, `Private/UI/MyHUD.cpp` | `LobbyWidgetClass`, `AddLobbyWidget`, `GetLobbyWidget` |
| `Source/Aura/Public/Match/MyMatchHUDWidget.h`, `Private/Match/MyMatchHUDWidget.cpp` | phase Lobby, the 6.6 strip, "Back to the lobby in n s", lobby toasts, the Locked toast |
| `Source/Aura/Public/EOS/PauseMenu3.h`, `Private/EOS/PauseMenu3.cpp` | START MATCH in the lobby, Restart hidden in the lobby, BACK TO LOBBY, `RequestLeaveSession`, Open Lobby's `bInMatch` |
| `Source/Aura/Public/EOS/MainMenu3.h`, `Private/EOS/MainMenu3.cpp` | the option-list statics; `GetTeamModeMaxPlayers` forwards to the team library |
| `Source/Aura/Private/EOS/SessionEntry3.cpp` | IN LOBBY / IN MATCH |
| `Source/Aura/Public/PlayerInput/MyPlayerController2.h`, `.cpp` | one new function: `OpenLeaveSessionConfirm` |
| `Docs/Airship/scripts/ue/as_77_lobby_widget.py` (new) | builds `WBP_Lobby3` and `WBP_LobbyPlayerRow3` |
| `Docs/Airship/scripts/ue/as_78_lobby_hud.py` (new) | sets BP_MyHUD's `LobbyWidgetClass`, then verifies |
| `Docs/Airship/scripts/ue/as_79_lobbylib.py` (new) | lobby readers shared by as_79 and as_80 |
| `Docs/Airship/scripts/ue/as_79_pie_lobby.py`, `as_79s_status.py`, `as_79x_stop.py` (new) | the standalone run (LB1.1 to LB1.10) |
| `Docs/Airship/scripts/ue/as_80_pie_lobby_mp.py`, `as_80s_status.py`, `as_80x_stop.py` (new) | the 2-player listen run (LM1.1 to LM1.13, plus LMF and LMS) |
| `Docs/Airship/scripts/ue/as_70_matchlib.py` | `MB_PHASE` and `MB_EVENTS` get Lobby and the 4 lobby events, appended (`:52`, `:57-58`) |
| `Docs/Airship/scripts/ue/as_74_pie_match.py`, `as_75_pie_match_mp.py` | the practice change of 7.7: practice starts aboard |

## 2. What is built

### 2.1 `UMyLobbyWidget` (spec 6.1, 6.3, 6.4)

* **Class.** `UMyLobbyWidget : UMyUserWidget, IMyLobbyPanel` (`MyLobbyWidget.h:41`). Every name of 6.3 is
  `BindWidgetOptional` (`:85-187`). The settings of Appendix L-A are there too: `PlayerRowClass`, `TimeLimitChoices`,
  `RefreshInterval`, `StartConfirmSeconds` and `RulesSendDelay` (`:193-209`). Three extras: `MessageSeconds`, `bAutoOpen`
  and `PracticeRuleLabel` (`:213-221`).
* **Registration.** `NativeConstruct` registers the widget with `PC->SetLobbyPanel(this)` and binds `OnLobbyMessage`
  (`MyLobbyWidget.cpp:155`). `NativeDestruct` unregisters it and gives the input back if the panel was open (`:131`, `:170`).
* **Shows nothing outside the lobby.** The root stays `SelfHitTestInvisible`. The panel, strip, countdown and message
  collapse unless `IsInLobby()` (`RefreshViews`, `:520`). The root is never collapsed, so the widget keeps ticking. That
  way a game state that replicates late still brings the lobby UI up.
* **Panel open** (`OpenPanel`, `:278`).
  * It remembers whether the cursor showed, then calls `FlushPressedKeys`.
  * It sets `FInputModeUIOnly` focused on the widget and turns the cursor on, as `UPauseMenu3::OpenMenu` does.
  * It focuses the first control, so a gamepad can use the panel.
  * It logs `Lobby panel open (<PC>)`.
* **Panel closed** (`ClosePanel`, `:311`).
  * A host rules edit that is still waiting is sent first.
  * Then it sets `FInputModeGameOnly` with `SetConsumeCaptureMouseDown(false)` and puts the cursor back as it was.
  * It logs `Lobby panel closed (<PC>)`.
* **Esc and gamepad B.** `NativeOnKeyDown` closes the panel (`:345`). The panel has UI-only input, so `IA_Pause` doesn't
  fire.
* **Opens by itself** once per map load. This happens when the local pawn first exists and the phase is Lobby, unless the
  pause menu is open (`NativeTick`, `:429`).
* **Closes by itself on every machine** in three cases (`Refresh`, `:472`):
  * when the lobby countdown starts;
  * when the lobby ends;
  * in `NativeDestruct`.
* **Refresh.** It runs every `RefreshInterval`, and on the next tick after `OnMatchChanged`, which sets a flag (`:214`).
  The panel's own contents update only while the panel is open.
* **Rows.** A signature is built from the player list: (PlayerId, TeamId, arriving, object name) per player, deduplicated
  by PlayerId. When a carried player state and its replacement share an id, the one not arriving wins. Rows are rebuilt
  only when that signature changes (`RefreshRows`, `:555`). Otherwise `RefreshRowTexts` updates the texts in place
  (`:609`). This fixes critique entry m3.
  * Players still without a team are left out until `AssignTeam` runs.
  * Without `PlayerRowClass`, each player gets one plain text line, updated in place (`RebuildRows`, `:636`).
* **Headers.** For example "BLUE  2 / 2" in the team colour (`RefreshTeams`, `:759`). The cap comes from
  `GetDisplayTeamCap` (`:734`):
  * 1 for 1v1 and 2 for 2v2;
  * in Auto, `AutoMaxPlayersPerTeam`, or else half of Max Players;
  * in Practice, everyone on BLUE, and ORANGE reads "practice: one ship".
* **Switch team.** The button reads SWITCH TO ORANGE, or CANCEL SWITCH while a request is pending. It is hidden in
  practice or with `bLobbyTeamSwitch` off, and disabled during the countdown.
* **Rules.**
  * **Option lists.** They come from `UMainMenu3`'s C++ class defaults (`FillRuleOptions`, `:847`). The Practice entry
    reads "Practice (co-op, one ship)".
  * **Refresh.** A refresh writes the replicated rules into the controls with `ESelectInfo::Direct`
    (`ApplyRulesToControls`, `:951`). It skips a box that is open, and skips everything while a host edit waits.
  * **Unknown values.** A value the box doesn't offer, such as `ShipLives 4` set from the console, is added to the box
    (`SetComboToInt`, `:919`).
  * **Change handlers.** They ignore `Direct` (`:1083-1106`). A user edit restarts the 0.75 s timer. When it fires, the
    widget sends one `ServerLobbySetRules` (`SendRules`, `:1119`) and logs
    `Lobby panel: rules request Teams=.. ShipLives=.. ...`.
  * **1v1 and 2v2.** They set Max Players and lock it at once (`RefreshMaxPlayersLock`, `:1039`).
  * **Clients.** Every control is disabled and the hint reads "Set by the host" (`RefreshRules`, `:1057`).
  * **Refusals.** A message that arrives within 2 s of the host's request also shows in `RulesHintText` (`:220`).
* **Start** (host only).
  * **Label.** `GetStartLabel` (`:1147`) names what will start:
    * START PRACTICE (ONE SHIP);
    * START 2v1, with the team counts;
    * START 1v1 or START 2v2, which a hard block keeps disabled;
    * START CO-OP (ONE SHIP);
    * CANCEL while counting down.
  * **Hard block.** It disables the button and shows its reason (`RefreshActions`, `:1174`).
  * **Soft block.** The first click shows "<reason> - click again to start anyway" for `StartConfirmSeconds`. The second
    click sends `ServerLobbyStart(true)` (`StartButtonClicked`, `:1256`). A changed block asks again.
  * **Rematch.** NotReady with `IsLobbyRematch()` starts on the first click.
* **READY** (clients only). It toggles the player's ready flag. The label reads READY while he is not ready and NOT READY
  while he is (`:1297`). Clients see "Waiting for the host to start", plus the block's reason if there is one.
* **Code.** It comes from the session info, or for the host from `GetCurrentJoinCode`. It is hidden without a session
  (`GetJoinCode`, `:702`). COPY puts it on the clipboard (`:1339`).
* **CLOSE, MENU, LEAVE** (`:1350-1365`).
  * CLOSE closes the panel.
  * MENU closes the panel, then calls `OpenPauseMenu`.
  * LEAVE closes the panel, then calls `OpenLeaveSessionConfirm`, the pause menu's Leave Session confirm.
* **Countdown.** "MATCH STARTS IN n" is computed from `PhaseEndServerTime - GetServerWorldTimeSeconds()`, and the text
  is set only when the second changes. The hint reads "Esc: lobby", or "Esc: lobby (CANCEL)" for the host
  (`RefreshCountdown`, `:535`).
* **Compact strip.** "LOBBY   BLUE 2 - ORANGE 1   1 NOT READY   Esc: lobby" in the lobby, and
  "MATCH STARTING   ...   Esc: lobby" during the countdown (`RefreshCompact`, `:807`).
* **Focus.** While the panel is open, a click on the world gives the keyboard focus to this world's viewport. The widget
  then takes the focus back so Esc keeps working (`:440`). It does this only when its own viewport holds the focus. In
  single-process PIE, the other windows share the Slate user, so taking the focus back unconditionally would steal it
  every frame.

### 2.2 `UMyLobbyPlayerRow` (6.3)

* `Setup` shows `LocalHighlight` on the local player's own row (`MyLobbyPlayerRow.cpp:29`).
* `Refresh` updates the texts only (`:45`):
  * the status, in this order: LOADING, HOST, WANTS <team>, READY, NOT READY;
  * the ping, left empty for the host and for a player who is loading;
  * MOVE, shown in the host's view except in practice, and enabled in phase Lobby only.
* `MoveText` is an optional extra name. It reads "TO ORANGE", or "SWAP TO ORANGE" when that team is full.
* MOVE calls `UMyLobbyWidget::RequestMovePlayer`, which sends `ServerLobbyMovePlayer` (`MyLobbyWidget.cpp:1326`).

### 2.3 HUD (6.1)

* `AMyHUD::LobbyWidgetClass` is `EditAnywhere` and empty by default (`MyHUD.h:52`). as_78 sets it on BP_MyHUD.
* `AddLobbyWidget` runs from `BeginPlay` and from `InitOverlay` (`MyHUD.cpp:32`, `:84`). It is added the same way as the
  match widget: the whole viewport, ZOrder 5, local controllers only.
* `EndPlay` removes it, and `GetLobbyWidget()` returns it (`MyHUD.h:28`).
* There is no C++ default class. A bare `UMyLobbyWidget` has no tree, so it would register as an invisible panel with
  UI-only input.

### 2.4 Match HUD (6.6, 7.1)

* **Phase Lobby.** The match bar is not drawn (`MyMatchHUDWidget.cpp:1045`).
* **Without a registered panel** (no `LobbyWidgetClass`), it draws the one-line strip "LOBBY   BLUE n - ORANGE n   host:
  Esc > Start match", or "waiting for the host" for clients (`:510`). After 2 s it logs one Warning (`:518`).
* **Name tags and toasts** work in phase Lobby, because the phase is not None.
* **Ended.**
  * With `IsLobbyRound()`, the end panel reads "Back to the lobby in n s", else "Restarting in n s" (`:560`).
  * The host also gets the line "Esc > Back to lobby to go now" (`:561`).
* **Lobby toasts** (`:288-344`):
  * `LobbyCancelled`: "The host cancelled the start", or "Start cancelled: <block text>";
  * `LobbyTeamChanged`: "You are on ORANGE now", "<name> joined ORANGE", or "Teams rebalanced ..." for value -1;
  * `LobbyRulesChanged`: clients only;
  * `LobbyReturn`.
* **Locked refusal.** It shows the toast "Ships unlock when the match starts" (`HandleUseRefused`, `:358`).

### 2.5 Pause menu (7.3)

* **START MATCH** shows in phase Lobby as well as WaitingToStart (`PauseMenu3.cpp:466`). Its click calls
  `RequestStartMatch`, which the core makes force a start in phase Lobby.
* **The Restart row** is hidden while `IsInLobby()`, which includes the lobby countdown (`:467`).
* **BACK TO LOBBY.** With `WillReturnToLobby()`, the Restart row reads BACK TO LOBBY (`:470-476`).
  * `SetMatchRowLabel` gives a one-letter stamp the first letter, the same way `CloneButtonRow` does (`:479`).
  * Its confirm reads "End the match and take everyone back to the lobby?" (`:551`).
  * Yes runs `CloseMenu`, then `ReturnToLobby` (`:886-893`).
* **`RequestLeaveSession()`** opens the menu if it is closed, then shows the Leave Session confirm (`:378`).
* **Open Lobby.**
  * It advertises `bInMatch = !IsInLobby()` (`:634`).
  * After the session is created, it skips StartSession while the game is in the lobby (`:1011`). `BeginRound` starts
    the session there.

### 2.6 Menus and sessions (7.2, 7.4)

* `UMainMenu3::GetDefaultRuleSets`, `GetDefaultDifficultyNames`, `GetDefaultMaxPlayerChoices` and
  `GetDefaultShipLivesChoices` return the C++ class default's arrays (`MainMenu3.h:98-101`, `MainMenu3.cpp:574-592`).
* `UMainMenu3::GetTeamModeMaxPlayers` forwards to `UMyTeamLibrary` (`MainMenu3.cpp:571`).
* `USessionEntry3`'s RulesText reads "<rules>  IN LOBBY" or "<rules>  IN MATCH", from `FAuraSessionInfo::bInMatch`
  (`SessionEntry3.cpp:60-62`).

## 3. Deviations from the spec, and why

1. **`AMyPlayerController2::OpenLeaveSessionConfirm()` is new** (`MyPlayerController2.h:119`, `.cpp:455`). The pause menu
   is private to the controller. LEAVE needs to reach `UPauseMenu3::RequestLeaveSession` through it.
2. **`MoveText` is an extra optional name on the row**, the MOVE label. Without it the button has no text that says where
   the player goes.
3. **as_77 does not use `WBP_OptionRow` rows.** That row has a 600 px label column (MainMenu3 builder `b_settings.py`), so
   two of them don't fit side by side. The rules are compact cells instead, a label above each combo, in one row of five
   plus a row of three check boxes. The combo and check styles are still copied from WBP_MainMenu3.
4. **The READY label is an action.** It reads READY while not ready and NOT READY while ready, which takes the flag back.
5. **Rows skip players with team 255** until `AssignTeam` runs, except players who are arriving. This avoids a row for the
   first frame of a join.
6. **Esc goes through `IMyLobbyPanel`**, as the core already does (`NOTES_lobby_core.md` section 3, item 3). The HUD has
   `GetLobbyWidget()` for anything else.
7. **The match HUD hides its bar in phase Lobby.** The lobby widget's compact strip shows instead. During the lobby
   countdown, PR B's bar shows as built, with "MATCH STARTS IN n" and the teams' lives.

## 4. Editor scripts and harnesses (not run): the exact commands

The scripts load their libraries from `<editor project>/Docs/Airship/scripts/ue`: as_70, as_74, as_75 and as_79_lobbylib.
The editor's project therefore needs this branch's `Docs/Airship/scripts/ue` and its built C++. `inbox.sh` defaults to
`_AirshipWork/Saved/ClaudeInbox`. Every command runs from the editor project's root. Follow the rules of SPEC_B
section 3: one inbox script at a time, never an asset script during PIE, `free -g` first, and quit the editor cleanly
when done.

```
# 1. Widgets and HUD (editor open, StartupMap open, no PIE)
Docs/Airship/scripts/harness/inbox.sh 77 Docs/Airship/scripts/ue/as_77_lobby_widget.py 180   # report Saved/Match/as_77_lobby_widget.json
Docs/Airship/scripts/harness/inbox.sh 78 Docs/Airship/scripts/ue/as_78_lobby_hud.py 120      # report Saved/Match/as_78_verify.txt
#    (AS77_REBUILD = True / AS77_DRY = True / AS78_VERIFY_ONLY = True are inbox globals for a rebuild, a dry run, a re-check)

# 2. Standalone run, one PIE session (as_79 sets Standalone / 1 player in memory itself)
free -g
Docs/Airship/scripts/harness/inbox.sh 79 Docs/Airship/scripts/ue/as_79_pie_lobby.py 60
Docs/Airship/scripts/harness/inbox.sh 79s Docs/Airship/scripts/ue/as_79s_status.py 30         # poll until "phase finished"
#    results: Saved/Match/b79/b79_report.txt (+ b79_result.json, b79_log.txt); stop: as_79x_stop.py

# 3. Listen run, 2 players, one PIE session: quit the editor first
Docs/Airship/scripts/harness/set_play_mode.sh listen 2
#    start the editor, StartupMap open, free -g >= 6 GB available
Docs/Airship/scripts/harness/inbox.sh 80 Docs/Airship/scripts/ue/as_80_pie_lobby_mp.py 60
Docs/Airship/scripts/harness/inbox.sh 80s Docs/Airship/scripts/ue/as_80s_status.py 60         # poll until "phase finished"
#    results: Saved/Match/b80/b80_report.txt; stop: as_80x_stop.py; AS80_SEAMLESS = False skips LM1.13 (RL14)
#    afterwards: quit the editor, Docs/Airship/scripts/harness/set_play_mode.sh standalone
```

**What the runs cover** (Talal's lean rule: one solo run and one multiplayer run):

* **as_79** runs one PIE session.
  * LB1.1: the lobby loads.
  * LB1.2: the locks (turret rounds do no damage, a Locked refusal, potions without collision).
  * LB1.3: the zone.
  * LB1.4: the rules.
  * LB1.5: the countdown starts and is cancelled.
  * LB1.6: the start (aboard, timed effects gone, the swarm resumed).
  * LB1.7: the match end back to the lobby.
  * LB1.8: without the floor in the match.
  * LB1.9: a lobby on the path's first platform.
  * LB1.10: the Play Solo URL.
* **as_80** runs one PIE session.
  * LM1.1: the lobby on both machines, with START for the host and READY for the client.
  * LM1.2 to LM1.5: the zone, damage off, team moves with bots, the rules and the ready flags.
  * LM1.6: the start, with game input on both machines and both players aboard.
  * **LMF: friendly fire.**
    * Each player's gun on his own team's ship does no damage, after the spawn protection has ended.
    * The same gun on the other team's ship does `ShipDamageGunHit` per hit. This is the positive control.
    * Enemy players take damage; teammates (moved with `Aura.Match.Team`) take none.
  * LM1.7: a late join during the match.
  * **LMS: ship lives.** KillShip takes a life, and the ship comes back after 10 s. The last kill eliminates the team, and
    team 0 wins on both machines.
  * LM1.8: the end goes back to the lobby with the teams and rules kept.
  * LM1.9 to LM1.11: late joins in the lobby, during the lobby countdown, and in Ended.
  * LM1.12: a client's disconnect cancels a 1v1 countdown.
  * LM1.13: the seamless smoke test, last.

**Deviations of the harnesses** are listed in each script's header. The main ones:

* LMF and LMS are new.
* LM1.5 reads the client's rules from his own `Aura.Match.Status` line.
* LM1.11 sets EndScreenSeconds 12, so the rejoin completes before the return.
* LB1.9 waits 10 s on the path platform, not 30 s.
* LB1.1 can't read the Burrower pause from Python. LB1.6 reads the "swarm resumed (..., Burrowers unpaused)" log line
  instead.

**as_74 and as_75** got the one-line practice change of 7.7.

* **as_74's T1.1** wants the player aboard team 0's ship 1 s after InProgress, instead of on the floor. It uses a new
  helper, `aboard` (`as_74_pie_match.py:385`).
* **as_75's M1.1 practice variant** wants every pawn aboard team 0's ship within the countdown + 1 s
  (`as_75_pie_match_mp.py:1281`).

## 5. Not checked

* **Nothing ran.** The widget layout from as_77 has never been seen.
  * Sizes are guesses: a 1640 x 960 panel on a 1920 x 1080 reference, and combo widths of 150 to 400 px.
  * as_77 prints which styles it copied and which fell back to the MainMenu3 builder's flat palette.
  * A screenshot of the open panel (host and client) is the first thing to look at after as_77.
* **The UMGToolSet calls** are the same ones the MainMenu3 builder and as_72 use: CreateWidgetBlueprint, AddWidget,
  ToggleWidgetAsVariable, CompileWidgetBlueprint and GetWidgets.
* **`l77_verify` may not learn the variable flag.** It reads the flag from GetWidgets' info if the tool reports it, and
  counts it as unknown otherwise.
* **The harness readers rely on APIs not used before in this project:**
  * `SubsystemBlueprintLibrary.get_world_subsystem`;
  * `AbilitySystemLibrary.get_active_gameplay_effect_remaining_and_total_time`;
  * `get_active_effects`;
  * `has_mapping_context`.

  Each sits in a try block, and a failure shows up as `None` in the check's text.
* **The `open 127.0.0.1:<port>` rejoins** follow the spec's claim (LevelEditorPlaySettings.h:373-377). A PIE client in
  the same process travelling to the server port has not been tried here.
* **PIE proves nothing about Steam travel** (RL4). The two-machine Steam test of the seamless return is still needed (8.5).

## 6. Q-L1 to Q-L4 (never answered: the defaults are in the code)

As in `NOTES_lobby_core.md` section 7:

1. Q-L1: the floor and the platform stay after Start.
2. Q-L2: without the floor, the lobby moves to the path's first platform.
3. Q-L3: Play Solo goes straight into practice, and practice starts aboard.
4. Q-L4: ready flags are shown, not required. The host starts with a second click, and a rematch needs none.

## 7. Review fixes (2026-11-28, `REVIEW_lobby.md`)

**Widget and rows**

* **Hidden with their item.** `UMyLobbyWidget::SetButtonShown` (`MyLobbyWidget.cpp:278`) collapses the button's outermost
  `Item_` / `Wrap_` parent that holds no other button (`FindButtonItem`, `:248`). The button stays Visible inside it, so
  its label and slab or ring hide with it. Used for START, READY, SWITCH, COPY (`:1279`, `:1266`, `:847`, `:746`) and
  the row's MOVE (`MyLobbyPlayerRow.cpp:105`).
* **Confirm block.** `RefreshActions` and `StartButtonClicked` use the replicated `GetLobbyConfirmBlock()` (`:1254`,
  `:1374`), the server's own decision over every block. A rematch with NotReady plus NeedTwoPerTeam now asks once, and the
  second click sends `bForce`.
* **Start sends a waiting rules edit first** (`:1349-1361`). On the host it applies at once. If a lobby message comes
  back during the send (a refusal, counted in `HandleLobbyMessage`, `:222`), the click does not start.
* **Max Players free value.** `RefreshMaxPlayersLock` (`:1091`) keeps the value a host-picked 1v1 / 2v2 replaced
  (`FreeMaxPlayers`, `MyLobbyWidget.h:338`) and puts it back when he picks a mode without a fixed size. A mode that came in
  replicated brings its own Max Players. `OnTeamModeChanged` marks the rules dirty before it locks (`:1153`).
* **Compact strip** hidden during the lobby countdown (`:576`): the match HUD's bar is drawn there then.

**Scripts**

* `as_77`: a `Wrap_Code` HBox holds CODE, the code and COPY, so they hide together. The header names the `Item_` /
  `Wrap_` contract.
* `as_78`: `a78_same` compares an unreal enum by its `.name` (`<MyLobbySpawn.AUTO: 0>` failed before).
* `as_79_lobbylib`: `wshown` checks every parent's visibility. `panel_view` adds StartText, ReadyText, CopyCodeButton and
  JoinCodeText.
* `as_79`: new `LB1.4_swarm`. It checks the game mode's "Swarm difficulty 3" line against the Very Hard preset
  (`SwarmDifficulties[3]`), and the wave spawner's wave 1 multipliers and MaxAlive against preset 3 / the old preset.
  The dead `swarm` dump key is gone.
* `as_80`: `LM1.1_panels` wants each label shown or hidden with its button. `LM1.6_input` no longer counts the injected
  IA_Move distance (data only: injection bypasses IgnoreInput). `LM1.13_seamless` also wants the "seamless arrival, N
  carried" line with N >= 1, and 0 arriving 5 s later.
* All scripts pass the local name check again (`scratchpad/flake/check.py`). None has run.
