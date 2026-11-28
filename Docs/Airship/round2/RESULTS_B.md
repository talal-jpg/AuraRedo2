# Airship round 2, PR B: results

PR B adds ship lanes, teams, ship lives, match rules and an in-level lobby. This page covers what PR B does for
players, how to play it, what the editor stage tested, and what is left for Talal.

**Branch:** `claude/project-thread-0emzt1`. It holds PR B (53d7a06, merged at e5ba6a5) and the editor-stage fixes,
on top of redo3 5d178bf (PR #19, part A).

**Related docs:**

* Design: `SPEC_B.md` (match and lanes) and `SPEC_B_LOBBY.md` rev 2 (lobby).
* Code notes: `NOTES_lobby_core.md` (sections 9 to 11 cover this stage's fixes) and `NOTES_lobby_ui.md`.
* The stage runbook: `EDITOR_STAGE_B.md`.
* Player's guide: `../HOW_TO_FLY.md` ("Team match").

Contents

1. What PR B does, ask by ask
2. How to play it
3. Test results
4. Fixes made in the editor stage
5. Defaults chosen (Q-L1 to Q-L4)
6. Not tested: needs Talal
7. Open items
8. Media

---

## 1. What PR B does, ask by ask

| Talal's words | What players get |
|---|---|
| "ship moves at a certain speed on the line besides platforms on either side for both teams" | Each team has one ship on its own lane, just outside the platforms, one lane on each side of the path. With nobody at the helm it cruises at 6 m/s. It goes up to 28 m/s to catch up with its team and never flies past the built path. |
| "until driven and taken out of its lane" | When you take the helm, the lane keeps flying the ship (**LANE AUTO**) until you press a drive key. After that the ship is yours, in or out of the lane. |
| "if parked in lane again and unmounted from drive starts moving auto in lane again" | Leave the helm inside the lane below 8 m/s and the ship cruises on at once. Leave it anywhere else and it drifts and holds as in part A, then after 20 s it flies itself back to its lane. |
| "number of lives for ships" | Each team has 3 ship lives by default (1 to 9). A lost ship comes back in its lane 10 s later. It takes no damage until your team boards it, or for 15 s. A team with no ships left loses. Solo practice never runs out. |
| "1v1 or 2 v2 ( will also depend on the number of players" | Teams follow the player count: 1 player is practice (one ship), 2 is 1v1, 3 is 2v1 (the smaller team gets one more ship life), 4 is 2v2, and more are balanced. The host can also pick Practice, 1v1 or 2v2. |
| "rules might include difficulty of swarms" | SWARM is Easy, Normal (today's game), Hard, Very Hard or Nightmare. It scales the sentinel waves (count, health, damage, speed and cap) and the Burrowers. More players also means more sentinels. |
| "no swarms only attack ship when driving" | Sentinels target and damage a ship, and its guns, only while someone drives it. |
| "1. Lobby level" (like Far Far West) | Host Game opens a walkable lobby in StartupMap, with a panel that shows both teams, who is ready, the host's rules and START. A 5 s countdown follows, then everyone is aboard their own team's ship in the same level. After the match everyone goes back to the lobby with the same teams and rules. |
| Friendly fire off, including your own team's ship | Your gun, beam, splash, cannons, machine guns and fireballs don't hurt your teammates, your team's ship or its guns. Nobody can drive or man the other team's ship. The pilot still takes his quarter of the hull's damage. The host can turn friendly fire on. |

The rest of PR B (`SPEC_B.md`):

* **Match flow:** countdown, play, then a 15 min time limit with a tie-break: ships left, then hull health, then how
  far along the path the team got. The match ends in VICTORY, DEFEAT, DRAW or PRACTICE OVER, with an end screen.
* **Ship hook:** the grapple reels you onto your own team's ship from up to 120 m. It is a rule, on by default.
* **HUD:**
  * a match bar with lives, both hulls, the clock and the phase;
  * ship markers and name tags in team colour;
  * "your ship is under attack" and other toasts;
  * a lane row on the pilot's panel;
  * the end panel.
* **Fixed ship damage in a match:** a gun hit does 5 to a team ship and a machine-gun round does 4, whatever
  GE_GunShootDamage says. Talal's local 1000 no longer sinks a ship in one shot.
* **The race keeps working:**
  * a player aboard a ship never becomes the lead and never grows the path;
  * Burrowers don't hunt players on ships;
  * crew thrown off a ship over the void die by the fall instead of falling for minutes.

## 2. How to play it

### From the main menu (the real flow)

1. **Host Game.** The host form has a new SHIP LIVES row.
2. **You are in the lobby.** It is StartupMap: walk around on the floor and the platform above it. The lobby zone keeps
   you in: if you leave it, you are put back after 0.5 s. Damage, pickups and the ships are off, and the swarm waits.
3. **The lobby panel opens by itself.** Esc closes it and opens it again.
   * BLUE and ORANGE list each player, the HOST tag and whether he is ready. SWITCH TO ORANGE asks to switch teams. The
     host's TO ORANGE button on a row moves that player.
   * A player who isn't the host presses READY.
   * The host sets the RULES: Teams, Ship lives, Swarm, Max players, Time limit, Friendly fire, Ship hook and Lane
     assist. Changes apply to everyone. The other players see them read-only.
4. **The host presses START.** The button names the match, for example START 1v1 or START PRACTICE (ONE SHIP). If
   someone isn't ready, it asks for a second click and then starts anyway.
5. **MATCH STARTS IN 5.** Esc cancels back to the lobby. At 0, everyone stands on their own team's deck with full
   health.
6. **Play.** Sink the other team's ship until it has none left.
7. **The end panel.** It shows "Back to the lobby in n s" (20 s). The host can go sooner with Esc > BACK TO LOBBY.
   Everyone comes back with the same teams and rules, and the ready flags are cleared.

**Joining.** Friends can join at any time with the code, the server browser or an invite:

* in the lobby they get a team and a spot;
* during the countdown they come aboard at 0;
* during the match they join their team's ship.

**Play Solo** skips the lobby: practice starts at once, aboard team 0's ship. Friends can still come in through the
pause menu's Open Lobby. When that match ends, everyone goes to the lobby.

### In the editor

* **Lobby:** open StartupMap and type `Aura.Lobby.Enable 1` in the console. Then press Play (standalone with 1 player,
  or Listen Server with 2 players). Without the CVar, Play starts practice at once, like Play Solo.
* **Travel between rounds:** PIE uses a hard travel unless `net.AllowPIESeamlessTravel 1` is set. A packaged game
  travels seamlessly.

### Console commands that matter (server side, not in Shipping)

| Command | What it does |
|---|---|
| `Aura.Lobby.Enable 1` | A CVar, set before Play: start in the lobby. -1 (the default) leaves it to the URL. |
| `Aura.Lobby.Start [strict]` | The host's START. `strict` respects the ready flags. |
| `Aura.Lobby.Cancel` / `Aura.Lobby.Return` | Cancel the countdown / go back to the lobby now |
| `Aura.Lobby.Status` | Phase, teams, ready flags, and the panel and input state |
| `Aura.Lobby.Bots <n>` | Test bots in the lobby. Start refuses while bots exist. |
| `Aura.Lobby.Panel 0/1` | Close or open the panel (local) |
| `Aura.Match.Rules Teams=1v1 ShipLives=5 Swarm=3 ...` | Set the rules. In the lobby this does the same as the host's panel. |
| `Aura.Match.Status` / `Aura.Match.Dump` | The match state. Dump writes `Saved/Match/match_state.json`. |
| `Aura.Match.End <team or -1>` | End the match (-1 = no winner) |
| `Aura.Match.KillShip <team>` / `Aura.Match.DamageShip <team> <n>` | Sink or damage a team's ship |
| `Aura.Match.Swarm <0-4>` | Change the swarm difficulty during play |
| `Aura.Match.Recall <team>` | Send a ship back to its lane |
| `Aura.Lane.Status` / `Aura.Lane.Debug 1` | Show the lane state / draw the lanes |

The full lists are in `SPEC_B.md` Appendix B and `SPEC_B_LOBBY.md` Appendix L-B.

## 3. Test results

Talal's lean rule allows one solo PIE run (as_79) and one multiplayer PIE run (as_80) per PR. On top of those, the lane
behaviour he asked about got its own check (an as_74 subset). Each failing check was fixed, then re-run on its own with
`AS79_ONLY` / `AS80_ONLY` wrappers. No threshold was changed.

**The final evidence (2026-11-28, after every fix in section 4):**

| Run | Checks run | Report head |
|---|---|---|
| **as_80 final run (11:18)**, listen, 2 players | all, seamless on, LM1.13 last | **PASS 22, FAIL 2, SKIP 3.** Every LM and LMF check passed in this one run, except the two LM1.13 checks. Those two failed on the harness (3.3). |
| as_80, LM1.13 fix 1 (11:26) | LM1.13 (LM1.1 always runs) | PASS 3, FAIL 1, SKIP 3. LM1.13_third_start passed. LM1.13_seamless failed on one read only. |
| as_80, LM1.13 fix 2 (11:33) | LM1.13 | PASS 3, FAIL 1, SKIP 3. The same read failed again, and the probe in this run showed that the read itself was wrong. Read correctly, the recorded value means the context is mapped (3.3). The fixed read has not run. |
| **as_74, T2.1 restaged (11:36)**, standalone | settle + T2.1 | **PASS 3, SKIP 1.** Peak 28.05 m/s. |
| as_79 (solo) | see 3.2 | Every check passed (17 PASS + 1 SKIP over the runs). Not re-run in this pass. |

So **23 of the 24 as_80 checks have a PIE PASS**: 22 in the final run, plus LM1.13_third_start in both fix runs. The
24th, LM1.13_seamless, passes in its recorded data but not yet as a reported PASS (section 7, item 1). The editor did not
crash in any of these runs. Evidence: `Saved/Match/b80_final_run1/`, `b80_final_fix1_lm113/`, `b80_final_fix2_lm113/`,
`b74_main_t21_final/`.

### 3.1 Asset scripts (one editor session, no PIE)

| Script | Result |
|---|---|
| as_72 (menu lives row) | OK: WBP_MainMenu3 has Row_ShipLives and ShipLivesComboBox |
| as_77 (lobby widget) | OK: WBP_Lobby3 and WBP_LobbyPlayerRow3 are built and compile. 0 missing, 0 wrong class, 0 not variable, 0 style fallbacks. |
| as_78 (lobby HUD) | 36 PASS: BP_MyHUD's LobbyWidgetClass is WBP_Lobby3_C |
| as_73 (verify) | 30 PASS, 0 FAIL, 0 WARN, 2 INFO |

### 3.2 Solo run: as_79 (standalone, 1 player)

The runbook expects `{'PASS': 17, 'SKIP': 1}`. Across the first run and the re-runs, every check reached PASS.

| Run | Checks run | Report head |
|---|---|---|
| Run 1 (08:41) | all | PASS 13, FAIL 4, SKIP 1 |
| Fix 1 (09:05) | LB1.3 to LB1.9 (LB1.1 always runs) | PASS 14, FAIL 1, SKIP 1 |
| Fix 2 (09:09) | LB1.8 | PASS 4, FAIL 1, SKIP 1 |
| Fix 3 (09:12) | LB1.8 | PASS. A later run overwrote the report, so the line is in `b79/b79_log.txt` |
| Step 4 (10:21) | LB1.2 (now with a positive control) | PASS 5, SKIP 1 |

| Check | Result |
|---|---|
| LB1.1 lobby, expected players, panel, swarm | PASS in every run. The lobby is there at load, the panel opens by itself, and there are 0 sentinels at 15 s. |
| LB1.2_locks | PASS. 12 machine-gun rounds hit the player with no damage; the ships are locked; potions have no collision. |
| LB1.3_zone | PASS. The player was back in the zone after 0.53 s, with no ranking. |
| LB1.4_rules, LB1.4_swarm | PASS. `Teams=practice ShipLives=5 Swarm=3` applied at once, and Very Hard reached the spawner: count, health and damage x1.6, max alive x1.4. |
| LB1.5_start, LB1.5_cancel | PASS. The countdown was 5.00 s, and Cancel went back to the lobby with no team ship left. |
| LB1.6_start, LB1.6_swarm | PASS. The player was aboard team 0's ship 0.0 s after the start, 12 cm from the lane spawn point, at full health, with timed effects removed. The swarm resumed. |
| LB1.7_return | PASS. Back in the lobby 3.0 s after the end, rules kept, round 0. |
| LB1.8_no_floor | PASS (fix 3). Without the floor there was a fall death after 6.4 s and a respawn on a path platform. |
| LB1.9_path_lobby, LB1.9_start | PASS. The lobby moved to the first path platform, and the match started from there. |
| LB1.10_play_solo | PASS. A practice countdown with no pawn for 5 s, then the player was on team 0's deck. |
| SKIP LB1.1_burrower_paused | Not readable from Python. LB1.6 reads the log line instead. |

### 3.3 Multiplayer run: as_80 (listen server, 2 players)

The runbook expects `{'PASS': 24, 'SKIP': 3}`. The final run (`b80_final_run1/`, 121 game s, 189 s of wall time) ran
every scenario in one PIE session, with the seamless test last. Its head was **PASS 22, FAIL 2, SKIP 3**. The LM1.13 rows
come from the two fix runs after it.

| Check | Final result |
|---|---|
| LM1.1_lobby, LM1.1_panels | PASS. Both players are in the lobby on teams 0 / 1. The host sees START and no READY; the client sees READY and no START. |
| LM1.2_zone | PASS. The client was back in the zone after 0.63 s, and his machine showed the zone message. |
| LM1.3_no_damage | PASS. The host's gun hit the client 6 times in the lobby (6 server "HitActor" lines), with no health drop. |
| LM1.4_switch, LM1.4_2v2 | PASS. Switch requests, swaps and the 2v2 rebalance work (with console bots). |
| LM1.5_rules, LM1.5_ready_kept | PASS. The client saw the host's rules 0.13 s later. A 1v1 with 3 players in was refused. |
| LM1.6_strict, LM1.6_input, LM1.6_aboard | PASS. Both players were on their own ship's deck 0.0 s after the start. The client's injected IA_Move moved him 522 cm. |
| **LMF_own_ship** | **PASS, every half in one run:** the host's and the client's guns each did 5.0 to the other team's hull, and nothing to their own ship. |
| **LMF_players** | **PASS:** the enemy took 1.0 with 6 server hits. The teammate took nothing (crosshair on him in 7 samples, 0 server hits). The friendly-fire return comes before the HitActor print, so "0 hits" alone can't tell a blocked shot from no shot: the positive control is the enemy window just before it (same shooter and aim, 6 hits). |
| LM1.7_rejoin_match | PASS. The client rejoined during the match and was aboard team 1's ship 0.2 s later. |
| LMS_lives, LMS_eliminated | PASS. A lost ship cost one life, and a new ship came 10.37 s later. The last kill ended the match with team 0 winning, on both machines. |
| LM1.8_return | PASS. Back in the lobby with the same teams and rules, and the ready flags cleared. |
| LM1.9, LM1.10, LM1.11 (rejoins) | PASS. A player who leaves and rejoins (in the lobby, during the countdown, or on the end screen) ends up in the right place. |
| LM1.12_cancel, LM1.12_reopen | PASS. A disconnect cancelled a 1v1 countdown 0.1 s later, and the client joined again after 0.2 s. |
| **LM1.13_third_start** | **PASS in both fix runs:** a third start after the seamless return put both players aboard. |
| LM1.13_seamless | **Passes in its data, not yet as a PASS line.** In both fix runs every part held: the seamless travel lines, new worlds, both players in the lobby, a new controller for the client, the pilot component on both machines, the teams kept, equal platform and ship counts, no GC error, no fall death, "seamless arrival, 2 carried", and 0 still arriving after 5 s. The one FAIL was "IMC_AirshipBoard mapped False", and that was the harness misreading the answer. The engine's HasMappingContext returns a bool plus the priority. UE Python gives `None` for false and the priority for true (`PyGenUtil.cpp:2669-2674`). The board context's priority is 0, so `bool(0)` read it as unmapped. The fix 2 probe recorded `0` (mapped, priority 0) for IMC_AirshipBoard and for the controller's own context, on both machines, before and after the travel. The read is fixed (`is not None`) but has not run (the two-round limit). |
| SKIP LM.host_crash, LM.steam_seamless, LM.menu_end_to_end | Manual (section 6). |

What else the final run's log shows:

* 4 harness read errors (`schar` 2, `phase_of` 2): the first `schar` came during the LM1.10 rejoin, the rest while a world was swapped. The run's LM1.13 FAILs came from the same stale-controller reads (fixed afterwards).
* One fall death: the client, when LMS killed his ship.
* 8 ensures, all from one engine PCG ensure (`!Container->bAreResourcesInaccessible`, `PCGManagedResourceContainer.cpp:353`). It fired on the client when the server closed the channel of an `AMyHexBridge` (`AMyHexBridge::EndPlay` -> `UPCGComponent::EndPlay`) during LMS. That is the hex bridge code, not PR B (section 7).

Two grabs from the final run, about 6 s apart (host and client): each player aboard his own team's ship in the 1v1 match (section 8).

**History: the earlier as_80 runs**

| Run | Checks run | Report head |
|---|---|---|
| Step 3, run 1 (09:27) | all | PASS 14, FAIL 6, SKIP 4. Stopped: the client never came back after the lobby return. |
| Step 3, fix 1 (09:43) | LM1.6, LMF, LMS, LM1.8 to LM1.13 | PASS 7, FAIL 2, SKIP 8. The worlds did not come back within 150 s. |
| Step 4, run 1 (10:23) | LM1.3, LM1.6, LMF, LMS, LM1.8 to LM1.13 | PASS 15, FAIL 3. The editor crashed in LM1.13, so there is no report; the lines are in `b80_s4run1/b80_log.txt`. |
| Step 4, run 2 (10:42) | LM1.6, LMF, LMS, LM1.8, LM1.12, LM1.13 | PASS 10, FAIL 3, SKIP 3 |
| Item 1 probe (11:10) | LM1.6, LMF, a gun probe (no LM1.3) | PASS 8, FAIL 1, SKIP 3. Both LMF checks passed. The FAIL was the probe's own strict line. `Saved/Match/b80_item1_probe/` |

* The travel fix (section 4, C++ row 2) landed between step 3 and step 4. The step 3 failures from LM1.8 on came from the
  bug it fixes.
* The earlier LMF failures, including the host's gun making no server hit after the start, were the harness's input
  injection (section 4, harness).
* The earlier LM1.13 failures:
  * step 4 run 1: the editor crash, fixed in C++;
  * step 4 run 2: the harness lost track of the client after the travel.

### 3.4 Lanes: as_74 main pass, the lane checks only

**Final: T2.1 restaged (11:36, `Saved/Match/b74_main_t21_final/`): PASS 3, SKIP 1.**

| Check | Result |
|---|---|
| T1.1_practice_start | PASS. Countdown, play at 5.03 s, the player aboard team 0's ship. |
| T1.2_team_ship | PASS. The ship spawned exactly on the lane spawn point, Cruising and protected. |
| **T2.1_pace** | **PASS (final run).** The player stood at u 350 m: peak 28.05 m/s (band 27 to 29, unchanged). The ship settled 40.13 m ahead in TeamPace, with 0.38 m overshoot and a 2.50 m/s² ramp. The lead's call: the staging moved from u 200 m to u >= 330 m. At 200 m the ship had 250 m, and 28 m/s and back needs about 310 m. |
| **T2.7_park_in_lane** | **PASS. This is Talal's case.** The ship was flown out of its lane and back in, and the pilot left the helm at 1.5 m/s. The ship was Cruising 0.0 s later and at 6 m/s after 2.2 s. |
| T2.4_assist | PASS. Boarding a cruising ship gave Assist at once, with 5.98 to 6.06 m/s for 10 s with no input. The broadside fired. |
| T2.10_recall | PASS. The ship was left 200 m out of its lane. It was Returning at 20.0 s and Cruising at 46 s, with no hull damage. |
| SKIP T7.1_hud_text | Not readable from Python. |

**History**

| Run | Checks run | Report head |
|---|---|---|
| Lanes, run 1 (09:14) | settle + T2.1, T2.4, T2.7, T2.10 | PASS 3, FAIL 3, SKIP 1. T2.1 peaked at 25.2 m/s with the player at u 213 m. |
| Fix 1 (09:19) | T2.4, T2.10 | PASS 3, FAIL 1, SKIP 1 |
| Fix 2 (09:22) | T2.4 | PASS 3, SKIP 1 |
| T2.1 restaged (11:36) | T2.1 | PASS 3, SKIP 1 |

## 4. Fixes made in the editor stage

Each fix is in `NOTES_lobby_core.md` sections 9 to 11 (file:line, why, which check). Both builds exited 0, with only
the two old bIsFocusable warnings.

**C++**

| Where | Change | Why | Check |
|---|---|---|---|
| `MyHUD.cpp:109-122` | The lobby panel goes in the viewport layer (ZOrder 5) | The HUD's globes, ability icons and crosshair were drawn over the panel and its START button | LB1.1_panel, LB1.4_rules, window grabs |
| `MyGameModeLobby.cpp:1673-1680`, `TravelToRound` | A relative ServerTravel, plus `?Lobby=0` when needed | An absolute travel made the next map listen on port 7777, while clients came back to the old port (17777 in PIE). The client froze on the end screen. | LM1.8 to LM1.12 |
| `MechSentinelClientBubble.h:88` / `.cpp:245` | A Tick guard: skip the tick when the bubble's world is gone | "Assertion failed: World" crashed the client on the PIE seamless return to the lobby. A packaged client takes the same path (untested). | LM1.13, run 2 |
| `AirshipPawn.cpp:416-418` | StationAims start at zero | Every team-ship spawn logged "WriteQuantizedVector: Value isn't finite" (since part A) | 0 such errors in the as_80 logs |
| `MyMatchHUDWidget.cpp:448-449`, `:489-492` | A lobby round's bar says MATCH STARTS IN n, and DEFEAT is drawn in ink | The bar and the big text showed two different countdown texts, and the losing team saw DEFEAT in the winner's colour | window grabs |

**Lobby widget** (as_77, rebuilt twice)

* The player row's name column is 270 px, clipped with an ellipsis. Long PIE names ran into the HOST tag.
* The panel now sits in a ScaleBox that only scales down, and the team lists are 236 px high. The panel now fits the
  editor's narrow PIE viewport, and START stays inside the card.

**Harness** (no threshold changed)

* `ground_at` uses `HitResult.to_tuple()`, because UE 5.8 Python has no `break_hit_result`.
* `placed()` matches exact names. The prefix match also destroyed ten path platforms.
* `log_wait` / `event_wait`: a log line reaches the log file a frame or more late.
* LB1.8 finds the respawn platform through the pawn's movement base.
* T2.4 turns the camera abeam first, because part A's driver turret arc fires the machine guns instead of the broadside
  when the camera looks forward.
* T2.10 reads its event after the wait.
* LB1.2 and LM1.3 now need at least one real hit, so "no damage" can no longer pass on missed shots.
* as_80:
  * `core.EnsureAlwaysEnabled 0` for the run;
  * a new world is detected by the server clock going back;
  * LMF restaged;
  * LM1.12's reopen reads the world name before the `open`;
  * LM1.6_input warns when the client moved 0 cm.
* `as_70_matchlib.py`, `subsystem`: the injected input goes to the right machine. The cache key was the world's
  name, and both PIE worlds are named "StartupMap", so in a listen run every machine got the input subsystem looked up
  first (`NOTES_lobby_core.md` 10, row 14).
* **Final pass** (`NOTES_lobby_core.md` section 11):
  * **LM1.13 maps the players only once the seamless travel is done.** It waits for every player's "arrives
    (seamless)" line, then for one controller per player on the server and one on the client. Only then does it map
    the players again. Before, it read old objects that were being replaced: the engine gives every player a new
    controller in a seamless travel, and the client gets his only when he has loaded.
  * **The teams are compared by player name.** The join order changes in a seamless travel.
  * **The IMC_AirshipBoard read.** UE Python returns `None` or the priority (0 here), and `bool(0)` read a mapped
    context as missing. The read is now `is not None`, and LM1.13 also reads the controller's own context as a
    positive control.
  * **T2.1 stages the player at u 350 m.** This was the lead's call; the 27 to 29 m/s band is unchanged.

## 5. Defaults chosen (Q-L1 to Q-L4)

Talal's lobby questions were never answered, so the code uses these defaults (`SPEC_B_LOBBY.md` section 9):

1. **Q-L1:** the floor and the platform above it stay during the match. The match never uses them. To make them
   disappear at Start, tag them `LobbyOnly` in the map.
2. **Q-L2:** after the floor is deleted, the lobby moves by itself to the path's first platform (tested: LB1.8, LB1.9).
3. **Q-L3:** Play Solo skips the lobby, and practice starts aboard team 0's ship.
4. **Q-L4:** ready flags are shown, not required. The host can start without everyone ready by clicking START a second
   time. A rematch with the same teams needs no second click. `bLobbyRequireReady` makes the flags required.

## 6. Not tested: needs Talal

**Manual checks** (`SPEC_B_LOBBY.md` 8.5):

1. **Two packaged Steam machines, for the seamless return to the lobby.** This is the real test: PIE uses the IP driver
   and a hard travel. Check that:
   * the client stays connected and lands in the lobby, with no main menu and no "Couldn't connect";
   * the teams are kept;
   * the session starts and ends with each match;
   * the server browser shows IN LOBBY / IN MATCH.
2. **The menu end to end:**
   * MM_MainMenu -> Host -> the lobby panel;
   * the host edits the rules, and the client's boxes follow and stay disabled;
   * the START texts;
   * LEAVE goes back to the menu.
3. **The host leaving or crashing:** the client should see "The host closed the lobby." or "Lost connection to the
   host.".
4. **Play Solo -> Open Lobby:** a friend joins, the match ends, and everyone goes to the lobby.

**Built but not run in PIE** (outside the lean runs):

* **Match sizes:** a 2v1 (3 players) and a real 2v2 match. 2v2 was tested only in the lobby, with bots.
* **Lanes:**
  * team 1's lane beyond its spawn;
  * path-end pacing, going round the other ship, curved lanes, and the recall fallback.
* **Ship lives:** a ship sunk by real fire (LMS used `Aura.Match.KillShip`), spawn protection, crew thrown off the
  ship, practice over, and solo unlimited ships.
* **Rules:** the ship hook, the time limit and its tie-break, and the Easy swarm preset.
* **Friendly fire on a free ship:** machine guns and cannonballs from the untagged placed ship (review row 7).
* **The beam's knockback on a teammate** (`LaunchCharacter` in GA_BeamBP): nobody has read that graph yet.
* **The swarm against a ship in the new lane states** (Cruising, Assist).
* **Regressions:** the part A regression on L_AirshipTest (as_76) and the multiplayer match without the lobby (as_75).
  as_75 injects input through the same as_70 `subsystem` as as_80. Any earlier as_75 result where both machines had input
  injected may have had the input mixup of section 4. It is fixed now, but those results are worth a second look.

## 7. Open items

1. **LM1.13_seamless needs one short listen run to report its PASS.** Run `AS80_ONLY = ('LM1.13',)` with the PIE
   seamless travel on; it takes about 1.5 minutes of wall time.
   * Both fix runs met every condition of the check except the IMC_AirshipBoard read, and that read was the harness's
     misreading of a mapped context (3.3).
   * The fixed read (`is not None`) has not run. The two fix rounds this pass allowed were used up.
   * LM1.13_third_start already passed in both fix runs.
2. **Done: the listen host's gun after the start was the harness, not the game.** The harness picked the machine to
   inject input into by the world's name, and both PIE worlds are named "StartupMap". In the final run, LMF_own_ship
   and LMF_players passed with every half, after LM1.3 and with LM1.6 injecting the client's input first. Details:
   `NOTES_lobby_core.md` section 10, row 14.
3. **Done: T2.1.** The player was restaged at u 350 m (the lead's call). It passed with a peak of 28.05 m/s, and the
   band is unchanged.
4. **The crash guard is in Mech Sentinel code (the PR #3 area).** Talal should know: without it the client crashed on the
   PIE seamless return, and a packaged client takes the same path (untested). With it, the PIE seamless return ran three times in this pass with no crash.
5. **Seen in the final run, not PR B:**
   * An engine PCG ensure on the client when the server closed a hex bridge's channel during LMS (`AMyHexBridge::EndPlay`
     -> `UPCGComponent::EndPlay`, `PCGManagedResourceContainer.cpp:353`, 8 log lines). Talal's hex bridge code; worth a
     look if it shows outside PIE.
   * "GiveAbility called ... on the client, not allowed!" for the startup abilities, at every pawn spawn on a client. It
     shows from the first spawn of the run, not only after travel.
   * The ensure site is existing bridge/PCG teardown code, but what closed the bridge's channel was not traced, and PR B
     changes bridge culling in a match (MyHexBridgeSubsystem), so PR B may be involved. The GiveAbility errors were
     already there in part A.
6. **Cosmetic, not fixed:**
   * On a client, the host's rules show in grey text on near black.
   * Console bots can push a team past Max Players ("ORANGE 2 / 1").
   * In practice, the match bar's SHIPS LOST bar touches its title (see the countdown image).
   * The on-screen "HitActor / IncomingDamage" prints come from Talal's own debug code in `GA_GunShoot.cpp`. They draw
     over the panel's left edge.

## 8. Media

All the images are window grabs from the PIE runs.

**The lobby panel (host, alone), final layout**

![Lobby panel](media/r2b_lobby_panel_scalebox.jpg)

**The same panel in the editor's narrow PIE viewport.** It scales down to fit.

![Lobby panel, narrow viewport](media/r2b_lobby_panel_pie_narrow.jpg)

**The host changed the rules: practice, 5 ship lives, Very Hard swarm**

![Rules changed](media/r2b_lobby_rules.jpg)

**The countdown.** Esc cancels it, and the ship waits, protected.

![Countdown](media/r2b_lobby_countdown.jpg)

**The 1v1 match on both machines (final as_80 run).** The host is on the left, aboard BLUE's ship; the client is on the
right, aboard ORANGE's. Each one's match bar marks his own team (YOU), and the marker at the edge points to the other ship.

![1v1 match, both aboard](media/r2b_match_1v1_both_aboard.jpg)

**At the helm of a cruising ship: LANE AUTO at 6 m/s**

![Lane assist](media/r2b_lane_assist.jpg)

**The client's end screen in a 1v1.** DEFEAT is in ink, then the screen counts down to the lobby.

![Defeat](media/r2b_defeat_ink.jpg)

**Back in the lobby after the match, with the rules kept**

![Back in the lobby](media/r2b_lobby_back_in_lobby.jpg)

**Before the HUD layer fix.** The crosshair and the ability icons are drawn over LANE ASSIST and START.

![Before the layer fix](media/r2b_lobby_before_layer_fix.jpg)

**After the layer fix, before the ScaleBox.** START sits on the card's bottom edge.

![After the layer fix](media/r2b_lobby_panel.jpg)
