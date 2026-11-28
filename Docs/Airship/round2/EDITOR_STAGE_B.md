# Round 2, PR B: the editor stage (lobby, teams, lives, lanes)

The steps the lead runs, in order, after PR B is committed. The code builds (`REVIEW_lobby.md`). No script has run, and
the editor has never opened this code.

Talal's lean rule: one solo PIE run and one multiplayer PIE run for the PR. Here they are `as_79` (standalone) and
`as_80` (listen, 2 players). Everything else in the stage builds or checks assets, with no PIE.

## 1. Where it runs, and what Content it needs

* **Not in `_AirshipWorkB`.** That worktree is sparse: it has no `Content/` and no `SourceArt/` (`.git/worktrees/.../info/sparse-checkout`:
  `!/Content/`, `!/SourceArt/`). An editor can't open it.
* **In the airship clone `_AirshipWork`**, the editor that every harness script expects. `inbox.sh`, `launch.sh` and
  `set_play_mode.sh` all point at it (`Docs/Airship/scripts/harness/*.sh`, `W=/mnt/new_partition/UnrealProjects/_AirshipWork`).
  Another pass is working there now: wait until it is done and the shared lock is free.
* **The clone needs:** branch `airship-r2-prb` merged in (C++ and `Docs/Airship/scripts`), then a build with
  `_AirshipWork_logs/build_r2.sh` (the clone's build script; exit 0).
* **Content it already has (PR A state) that the stage reads.** None of it is changed except where noted.
  * `/Game/Maps/StartupMap`: `Floor`, `BP_MyHexPlatform_C_1`, `PlayerStart_0` at (0, 0, 205), the hex path spawner, the
    wave spawners, `BP_Potion_C_1`, the placed free ship. It is never saved.
  * `/Game/Level/UI/BP_MyHUD` (as_78 sets `LobbyWidgetClass`), `/Game/Level/BP_MyGameMode` (as_73 reads it).
  * Under `/Game/Level/UI/UserWidgets/MainMenu/Menu3/`: `WBP_MainMenu3` (as_72 adds a row), `WBP_PauseMenu3`,
    `WBP_SessionPlayerRow3`, `WBP_OptionRow`, `Fonts/` (F_Anton, F_Bebas, F_Barlow, F_RubikMono), `Materials/` (the
    graffiti slab MIs). as_77 copies styles from these; it falls back to a flat palette for anything missing and lists it.
  * `/Game/Assets/MyShip/Drivable/BP_AirshipPawn`, the input actions the harnesses inject (IA_Move, IA_LMB, IA_RMB,
    IA_Pause) and `IMC_AirshipBoard`.
* **No new input actions, no map edits, no TEMP setup.** The lobby panel uses the existing IA_Pause (Esc goes through
  `AMyPlayerController2::TogglePauseMenu` to the panel). as_79 / as_80 destroy the floor and platform only in their PIE
  copies. as_71 (team PlayerStarts) is optional and not part of this stage.
* **Content the stage creates or saves** (in the clone; commit these with PR B):
  * new: `Menu3/WBP_Lobby3.uasset`, `Menu3/WBP_LobbyPlayerRow3.uasset` (as_77);
  * changed: `/Game/Level/UI/BP_MyHUD.uasset` (as_78), `Menu3/WBP_MainMenu3.uasset` (as_72).
  * Backups of the changed assets go to `_AirshipWork/Saved/Match/backup/`. Never commit them.
  * In Talal's tree today, `BP_MyHUD` and `WBP_MainMenu3` have no local change. `StartupMap` does, and no step saves it.
    (Checked read-only with `git --no-optional-locks status`.)

## 2. The steps

Shell variables used below:

```
D=/mnt/new_partition/UnrealProjects/_AirshipWork_logs
W=/mnt/new_partition/UnrealProjects/_AirshipWork
H=$W/Docs/Airship/scripts/harness
U=$W/Docs/Airship/scripts/ue
```

Rules for every step (SPEC_B section 3, the memory notes):

* One inbox script at a time.
* Never run an asset script during PIE.
* Run `free -g` before each editor start. You need 7 GB available (`launch.sh` refuses below that when another editor
  runs; `as_80` wants at least 6).
* Restart the editor before each PIE run.
* Quit the editor cleanly at the end. Never use `pkill -f`.
* Run long steps in the background with their output in a log file. Don't pipe them into tail or grep.

### Step 0. Merge, build, lock

```
cd $W && git merge airship-r2-prb          # or check out a branch that has it; resolve as for PR A
$D/build_r2.sh                             # exit 0; the only warnings are the old bIsFocusable ones
free -g
$D/lock.sh take "PR B editor stage (lobby)"
$H/set_play_mode.sh standalone             # editor closed; no-op if it is already standalone
```

### Step 1. Asset scripts (one editor session, no PIE)

```
$H/launch.sh /Game/Maps/StartupMap
$H/inbox.sh 72 $U/as_72_menu_lives.py 300   # RESULT: OK    WBP_MainMenu3 gets Row_ShipLives / ShipLivesComboBox, saved
$H/inbox.sh 77 $U/as_77_lobby_widget.py 300 # RESULT: OK    WBP_Lobby3 + WBP_LobbyPlayerRow3 built, compiled, saved
$H/inbox.sh 78 $U/as_78_lobby_hud.py 180    # RESULT: OK {...}  BP_MyHUD LobbyWidgetClass = WBP_Lobby3_C, saved, verified
$H/inbox.sh 73 $U/as_73_verify_b.py 300     # RESULT: {...} -> Saved/Match/as_73_verify.txt (read-only)
```

What each must show:

* **as_72:** `RESULT: OK`. If ShipLivesComboBox already exists, it reports and stops, which is also fine.
  Report: `Saved/Match/as_72_menu_lives.json`.
* **as_77:** `RESULT: OK`. The JSON (`Saved/Match/as_77_lobby_widget.json`) lists for each WBP the `missing` and
  `wrong_class` names: both must be empty. `not_variable` should be empty too (unknown counts as unknown). It also lists
  the styles copied and the ones that fell back.
  * Names the C++ now relies on: `Item_<key>`, `Wrap_<key>`, and `Wrap_Code`, which holds CODE, the code and COPY.
* **as_78:** `RESULT: OK`. In `Saved/Match/as_78_verify.txt` every line is PASS, or INFO for a value that
  `DefaultGame.ini` sets on purpose. A WARN for `UMainMenu3.<list>` means WBP_MainMenu3 overrides a C++ list (RL9): tell
  Talal, don't change it.
  * `UMyMatchSettings.LobbySpawn = <MyLobbySpawn.AUTO: 0>` is now a PASS (review row 11).
* **as_73:** no FAIL in `Saved/Match/as_73_verify.txt`. Its `menu` WARN must be gone after as_72.

A look at the panel before PIE is optional: `$H/xgrab_loop.sh $W/Saved/Match/xgrab &` during step 2 grabs the window
(the method `run_b_pie.sh` uses). Never take a Slate viewport screenshot.

Then:

```
$H/quit_keep_lock.sh
```

### Step 2. The solo run: as_79 (one PIE session, standalone, 1 player)

```
free -g                                      # >= 7 GB available
$H/launch.sh /Game/Maps/StartupMap
$H/inbox.sh 79 $U/as_79_pie_lobby.py 120     # RESULT: ARMED (poll as_79s_status.py; results in .../Saved/Match/b79)
# every 30 s until the first line says "phase finished" (about 6 game minutes, more in real time):
$H/inbox.sh 79s $U/as_79s_status.py 60
cat $W/Saved/Match/b79/b79_report.txt
$H/quit_keep_lock.sh
```

* Stop it early: `$H/inbox.sh 79x $U/as_79x_stop.py 60`.
* Run only some tests: an inbox wrapper `AS79_ONLY = ('LB1.4', 'LB1.6')` + `exec(open('$U/as_79_pie_lobby.py').read())`.
  LB1.1 always runs.

**Expected:** `checks: {'PASS': 17, 'SKIP': 1}`. Every line below is PASS, plus the one SKIP:

| Check | What it shows |
|---|---|
| `LB1.1_lobby` | phase Lobby at load, the PlayerStarts ground (Floor + the platform), the zone, the pawn near (0, 0, 205), no team ship |
| `LB1.1_expected` | ExpectedPlayers = DefaultExpectedPlayers |
| `LB1.1_panel` | the panel opened by itself, UI-only input, cursor on |
| `LB1.1_swarm` | every wave spawner stopped, 0 sentinels at 15 s |
| `LB1.2_locks` | turret rounds do no damage, `Board` refused with Locked, potions without collision |
| `LB1.3_zone` | back in the zone within 1 s, no ranking |
| `LB1.4_rules` | `Teams=practice ShipLives=5 Swarm=3` applied at once |
| `LB1.4_swarm` | **new** (review row 12): "Swarm difficulty 3" line = the Very Hard preset, spawner wave 1 multipliers / MaxAlive moved by preset 3 / old preset |
| `LB1.5_start`, `LB1.5_cancel` | countdown 5 s with game input; cancel back to Lobby, no team ship |
| `LB1.6_start`, `LB1.6_swarm` | aboard team 0's ship at 0, full vitals, timed effects gone; swarm resumed, sentinels within 12 s |
| `LB1.7_return` | `End -1`, back to the lobby 3 s later with `Lobby=1`, rules kept, round 0 |
| `LB1.8_no_floor` | without the floor: fall death, respawn on a path platform |
| `LB1.9_path_lobby`, `LB1.9_start` | lobby on the first path platform, start from there |
| `LB1.10_play_solo` | the Play Solo URL: practice countdown, no pawn for 5 s, then aboard |
| SKIP `LB1.1_burrower_paused` | not readable from Python; LB1.6 reads the log line instead |

### Step 3. The multiplayer run: as_80 (one PIE session, listen server, 2 players)

```
$H/set_play_mode.sh listen 2                 # editor closed (after quit_keep_lock.sh)
free -g                                      # >= 7 GB available
$H/launch.sh /Game/Maps/StartupMap
$H/inbox.sh 80 $U/as_80_pie_lobby_mp.py 120  # RESULT: ARMED
# every 30 s until "phase finished" (about 13 game minutes, up to an hour in real time):
$H/inbox.sh 80s $U/as_80s_status.py 60
cat $W/Saved/Match/b80/b80_report.txt
$H/quit_and_release.sh                       # quits, releases the lock
$H/set_play_mode.sh standalone               # editor closed
```

* Stop it early: `$H/inbox.sh 80x $U/as_80x_stop.py 60`.
* To skip the PIE seamless test (RL14, it can take the editor down), use a wrapper with `AS80_SEAMLESS = False`
  before the exec.

**Expected:** `checks: {'PASS': 24, 'SKIP': 3}`. Every line below is PASS:

| Check | What it shows |
|---|---|
| `LM1.1_lobby` | both in Lobby, pawns in the zone, teams 0 / 1, the client's view = the server's |
| `LM1.1_panels` | panel open on both; the host sees START with its label and no READY; the client sees READY with its label and no START (**new**: every parent's visibility, review row 8) |
| `LM1.2_zone`, `LM1.3_no_damage` | the zone on the client; damage off in the lobby |
| `LM1.4_switch`, `LM1.4_2v2` | bot moves, swaps, the 2v2 rebalance |
| `LM1.5_rules`, `LM1.5_ready_kept` | the client's rules follow; ready cleared only by a mode change |
| `LM1.6_strict`, `LM1.6_input`, `LM1.6_aboard` | NotReady refuses a strict start; game input on both at the countdown (**changed**: flags only, the IA_Move distance is data, review row 14); both aboard their own ship |
| `LMF_own_ship`, `LMF_players` | friendly fire off: no damage to the own team's ship or teammates; the other team's ship and players take it |
| `LM1.7_rejoin_match` | a rejoin in the match puts the client aboard team 1's ship |
| `LMS_lives`, `LMS_eliminated` | a ship life lost, a new ship 10 s later; the last kill ends the match, team 0 wins on both |
| `LM1.8_return` | the end goes back to the lobby with teams and rules kept, ready flags false |
| `LM1.9_rejoin_lobby`, `LM1.10_rejoin_countdown`, `LM1.11_rejoin_ended` | late joins in the lobby, the lobby countdown, Ended |
| `LM1.12_cancel`, `LM1.12_reopen` | a disconnect cancels a 1v1 countdown; the client joins again |
| `LM1.13_seamless`, `LM1.13_third_start` | the PIE seamless return (**new**: "Match: seamless arrival, N carried" with N >= 1 and 0 arriving after 5 s, review row 1); a third start |
| SKIP `LM.host_crash`, `LM.steam_seamless`, `LM.menu_end_to_end` | manual (SPEC_B_LOBBY 8.5) |

With `AS80_SEAMLESS = False`, the two LM1.13 checks are not run: `{'PASS': 22, 'SKIP': 3}`.

### Step 4. After the runs

* The editor is closed and the play mode is standalone again.
* Commit, from the clone, the four Content files of section 1. Commit no backups and no `Saved/`.
* For the PR text, keep the two report heads, plus these lines:
  * the Q-L1 to Q-L4 defaults (SPEC_B_LOBBY section 9):
    1. Q-L1: the floor and the platform stay after Start.
    2. Q-L2: without the floor, the lobby moves to the path's first platform.
    3. Q-L3: Play Solo goes straight into practice, and practice starts aboard.
    4. Q-L4: ready flags are shown, not required. The host starts with a second click, and a rematch needs none.
  * the manual checks of 8.5: the menu end to end, and two packaged Steam machines for the seamless return.

## 3. Known risks

1. **The arriving fix (review row 1) has one PIE check.** That check is LM1.13, and it runs only with
   `net.AllowPIESeamlessTravel 1`. A hard PIE travel never carries player states. The real test is still two Steam
   machines (SPEC_B_LOBBY 8.5, RL4).
2. **LM1.13 can crash the editor** (RL14, `GameModeBase.cpp:503`). It runs last. If it crashes, report it; don't retry.
   Then run as_80 again with `AS80_SEAMLESS = False` only if the earlier checks did not finish.
3. **The as_77 layout has never been seen.** The sizes are guesses: a 1640 x 960 panel, combos 150 to 400 px. Look at
   the xgrab frames (step 1 note) before you trust LM1.1's visibility checks alone.
4. **APIs that no harness has used before:** `get_world_subsystem`, `get_active_gameplay_effect_remaining_and_total_time`,
   `get_active_effects`, `has_mapping_context`, `UWidget.get_parent` (new in `wshown`). Each sits in a try block, and a
   failure shows as `None` in the check's text. `LB1.4_swarm` treats unreadable spawner numbers as "log line only".
5. **The in-process PIE rejoin** (`open 127.0.0.1:<port>`, LM1.7 and LM1.9 to LM1.12) has not been tried here.
6. **Not covered by the lean runs.** Lane behaviour past the spawn point (pace, assist, recall, bypass; as_74 T2.x) and
   the free-ship fire fix (review row 7: LMF uses team ships). If wanted, run
   `B_STAGES="main" B74_ONLY="T2.1 T2.4 T2.10" $D/run_b_pie.sh` (as_74, non-lobby PR B flow) as an extra.
   * A console check for row 7 in a co-op round: board the untagged ship as team 0, then `Aura.Airship.TurretFire` at
     team 0's ship. Its hull health must not change.
7. **The `Item_` / `Wrap_` naming contract.** If someone renames those containers in the designer, a hidden button's
   label shows again. Nothing breaks, but LM1.1 then fails.
8. **Memory.** Each UMGToolSet or Niagara toolset call leaks a little. The editor runs in a 13 GB scope (`launch.sh`).
   Restart between steps, as above, and watch `free -g`.
9. **The clone is shared.** The other pass in `_AirshipWork` must be finished. The shared lock (`$D/lock.sh status`)
   must be free before step 0.
