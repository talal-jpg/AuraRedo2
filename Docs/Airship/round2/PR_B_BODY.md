<!-- claude-projects-attribution: {"github_login":"talal-jpg"} -->
_Requested by **Talal** · [project thread](https://claude.ai/code/project/chan_01Spzu5fNbYB2wfTMSDFqGLc?thread=cmsg_01Spzu5fNbYB2wfTMSDFqGLcFQHnUwAEGsVSV9nm9CRX8s)_

## Summary

Airship round 2, part B: ship lanes, teams, ship lives, match rules and an in-level lobby. What changes for players:

- **Lanes.** Each team has one ship on its own lane, just outside the platforms, one lane on each side of the path.
  With nobody at the helm it cruises at 6 m/s, up to 28 m/s to catch up with its team, and never past the built path.
  - Take the helm and the lane keeps flying (LANE AUTO) until you press a drive key. After that the ship is yours.
  - Leave the helm inside the lane below 8 m/s and it cruises on at once.
  - Leave it anywhere else and it drifts and holds, then after 20 s it flies itself back to its lane.
- **Ship lives.** 3 per team by default (1 to 9). A lost ship comes back in its lane 10 s later, protected until your
  team boards it or for 15 s. A team with no ships left loses. Solo practice never runs out.
- **Teams by player count.** 1 player is practice, 2 is 1v1, 3 is 2v1 (the smaller team gets one more ship life), 4 is
  2v2. The host can also pick Practice, 1v1 or 2v2.
- **Rules.** The host sets teams, ship lives, swarm difficulty (Easy to Nightmare: it scales the sentinel waves and the
  Burrowers), time limit (15 min, with a tie-break), friendly fire, ship hook and lane assist.
- **Friendly fire off.** Your gun, beam, splash, cannons, machine guns and fireballs don't hurt your teammates, your
  team's ship or its guns. Nobody can drive or man the other team's ship.
- **Swarms attack a ship only while it is driven.**
- **Lobby** (your "1. Lobby level"): Host Game opens a walkable lobby in StartupMap. A panel shows both teams, who is
  ready, the host's rules and START. A 5 s countdown follows, then everyone is aboard their own ship in the same level.
  After the match everyone goes back to the lobby with the same teams and rules.
- **Also:**
  - The grapple reels you onto your own ship from up to 120 m.
  - The match HUD shows lives, both hulls, the clock, ship markers, team name tags, an "under attack" alert and the end
    screen.
  - Ship damage in a match is fixed (gun 5, machine-gun round 4), so your local GE_GunShootDamage of 1000 can't sink a
    ship in one shot.

## How to test

- **From the menu:** Host Game, then the lobby. Esc opens and closes the panel. Friends join with the code. The host
  sets the rules and presses START. After the match everyone is back in the lobby. Play Solo skips the lobby.
- **In the editor:** open StartupMap, type `Aura.Lobby.Enable 1` in the console, then press Play (standalone, or Listen
  Server with 2 players). Without the CVar, Play starts practice at once.
- **Useful console commands:** `Aura.Lobby.Start`, `Aura.Lobby.Cancel`, `Aura.Lobby.Return`, `Aura.Match.Rules
  Teams=1v1 ShipLives=5 Swarm=3`, `Aura.Match.KillShip <team>`, `Aura.Match.End <team>`, `Aura.Lane.Debug 1`. The full
  steps and console commands are in `Docs/Airship/round2/RESULTS_B.md` section 2.

## Test results

All runs were PIE in the airship clone, following the lean rule: one solo run, one multiplayer run, and the lane check.
Failing checks were fixed and re-run on their own. No threshold was changed.

- **Asset scripts:**
  - as_72: OK.
  - as_77: OK, with 0 missing, 0 wrong class and 0 style fallbacks.
  - as_78: 36 PASS.
  - as_73: 30 PASS, 0 FAIL.
- **Solo, as_79 (standalone):** all **17 PASS + 1 SKIP** (the runbook's expected count), reached over the first run and
  four re-runs. The first run's head was PASS 13, FAIL 4, SKIP 1; the last re-run's (LB1.2) was PASS 5, SKIP 1.
- **Multiplayer, as_80 (listen server, 2 players): 21 of 24 checks passed in at least one run.**
  - Report heads, in order: PASS 14 FAIL 6 SKIP 4; PASS 7 FAIL 2 SKIP 8; PASS 15 FAIL 3 (crash, no report); PASS 10
    FAIL 3 SKIP 3.
  - Passed: the lobby and panels, zone, damage off in the lobby, team switches and 2v2, rules, start, rejoins, ship
    lives and elimination, the **return to the lobby with teams and rules kept**, and the disconnect cancel.
  - Not passed:
    - `LMF_own_ship`: each half passed in some run, never all in one run.
    - `LM1.13_seamless`: the seamless return worked in run 2, but the harness lost track of the client. Its fix has not
      run.
    - `LM1.13_third_start`: never ran.
- **Lanes, as_74 lane checks:**
  - **T2.7 PASS.** This is your "parked in lane again and unmounted" case: Cruising 0.0 s after leaving the helm, and 6
    m/s after 2.2 s.
  - T2.4 (assist) and T2.10 (recall after 20 s) PASS.
  - T2.1 FAIL on one number: a peak of 25.2 m/s against the harness's 27 to 29. The staging gives the ship 250 m, but 28
    m/s and back needs about 310 m. That is the lead's call.
- **Fixes made in the editor stage (C++):**
  - The lobby panel is drawn above the HUD overlay (`MyHUD.cpp`).
  - Relative ServerTravel (`MyGameModeLobby.cpp`). Without it, the client froze on the end screen, because the next
    map listened on port 7777 instead of the session's port.
  - A crash guard on a seamless return in the Mech Sentinel client bubble (`MechSentinelClientBubble.*`). Without it,
    packaged clients crash on every seamless lobby return.
  - StationAims start at zero (`AirshipPawn.cpp`). This removes a log error, present since part A, on every ship spawn.
  - Countdown and DEFEAT text (`MyMatchHUDWidget.cpp`).
- **Fixes made in the editor stage (widget):** the panel scales down to fit narrow viewports, and long names are
  clipped. Details: `NOTES_lobby_core.md` sections 9 and 10.

## Defaults chosen (Q-L1 to Q-L4)

1. **Q-L1:** the floor and the platform above it stay during the match. The match never uses them. To make them
   disappear at Start, tag them `LobbyOnly`.
2. **Q-L2:** without the floor, the lobby moves by itself to the path's first platform (tested).
3. **Q-L3:** Play Solo skips the lobby, and practice starts aboard team 0's ship.
4. **Q-L4:** ready flags are shown, not required. The host can start anyway with a second click. A rematch needs none.

## Not tested / manual

- **Needs you:**
  - Two packaged Steam machines, for the seamless return to the lobby (PIE uses the IP driver and a hard travel).
  - The main menu end to end: Host, rules in the panel, LEAVE.
  - Host leave and host crash.
  - Play Solo -> Open Lobby -> back to the lobby.
- **Built but not run in PIE:**
  - a 2v1 and a real 2v2 match;
  - team 1's lane beyond its spawn;
  - the ship hook;
  - the time limit and its tie-break;
  - spawn protection and crew thrown off the ship;
  - friendly fire on a free ship;
  - the beam knockback on a teammate;
  - the part A regression (as_76) and the multiplayer match without the lobby (as_75).
- **Open:**
  - In one as_80 run the listen host's gun made no server hit after the start. The cause was not found.
  - LM1.13 needs one more listen run.
  - Cosmetic: grey read-only rules on the client, and the SHIPS LOST bar touching its title in practice.

## Content files changed

The four assets the editor scripts created or saved. There is no map change.

- `Content/Level/UI/UserWidgets/MainMenu/Menu3/WBP_Lobby3.uasset` (new: the lobby panel)
- `Content/Level/UI/UserWidgets/MainMenu/Menu3/WBP_LobbyPlayerRow3.uasset` (new: a player row)
- `Content/Level/UI/BP_MyHUD.uasset` (LobbyWidgetClass = WBP_Lobby3_C)
- `Content/Level/UI/UserWidgets/MainMenu/Menu3/WBP_MainMenu3.uasset` (a SHIP LIVES row in the host form)

Your local tree has no change to these four (checked read-only).

## Notes

- **Commit 8b4fa29 (round 3, zone 1) rides along.** It holds docs and Blender scripts only (`Docs/Airship/round3/`,
  `SourceArt/Airship/scripts/`), with no game impact.
- **Shared code touched outside `Airship/` and `Match/`:**
  - the game mode, game state, player state, controller and HUD;
  - GA_GunShoot, MySplashDamageLibrary, MyAttributeSet (spawn protection) and MyProjectile (friendly fire);
  - GA_GrappleSwing2 (the ship hook);
  - MechSentinelWaveSpawner and BurrowerSpawnSubsystem (difficulty);
  - MechSentinelClientBubble (the crash guard);
  - MainMenu3, PauseMenu3 and MultiplayerSessionsSubsystem (the lobby);
  - MyHexPathSpawner and MyHexBridgeSubsystem.
- **Your local files are not touched:** StartupMap, BurrowerSettings.h, MyHexPlatform.h, BP_MyCharMech,
  GE_GunShootDamage, GA_GunShootBP and GA_BeamBP.
- **Base:** redo3 5d178bf (PR #19, part A).
- **Full results, the per-check tables and the media:** `Docs/Airship/round2/RESULTS_B.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
