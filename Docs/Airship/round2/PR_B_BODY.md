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

- **Multiplayer, as_80 (listen server, 2 players), the final full run: PASS 22, FAIL 2, SKIP 3.** It ran every scenario
  in one PIE session, with the seamless return last, and the editor did not crash.
  - Every check except the two LM1.13 ones passed, including:
    - **friendly fire, in one run:** each player's gun hurts the other team's hull (5.0) and not his own ship; the host's
      gun hurts the enemy player (1.0, 6 server hits) and not a teammate (no drop; the positive control is the enemy
      window just before it, same shooter and aim);
    - the rejoins, ship lives and elimination, the **return to the lobby with teams and rules kept**, and the
      disconnect cancel.
  - The two FAILs were LM1.13, the PIE seamless return, and both were the harness: it read the players before the seamless
    travel had given them their new controllers. After that fix:
    - **LM1.13_third_start passed** in both re-runs;
    - **LM1.13_seamless met every condition** in both re-runs: new controller, pilot component, teams, counts, arrivals,
      no crash. Its one FAIL was the harness misreading IMC_AirshipBoard as unmapped. UE Python returns the priority, 0
      here, for a mapped context, and `bool(0)` is False. That read is fixed but has not run yet (one short listen run).
  - So 23 of the 24 checks have a PIE PASS, and the 24th passes in its data.
- **Lanes, as_74:**
  - **T2.1 PASS:** peak 28.05 m/s, settled 40.1 m ahead, with the player staged at u 350 m (the spec's u 200 m was too
    short for the 2.5 m/s^2 ramp to reach 28 m/s).
  - **T2.7 PASS:** your "parked in lane again and unmounted" case, Cruising 0.0 s after leaving the helm and 6 m/s after
    2.2 s.
  - T2.4 (assist) and T2.10 (recall after 20 s) PASS.
- **Solo, as_79 (standalone):** all **17 PASS + 1 SKIP** (the runbook's expected count), reached over the first run and
  four re-runs.
- **Asset scripts:**
  - as_72: OK.
  - as_77: OK, with 0 missing, 0 wrong class and 0 style fallbacks.
  - as_78: 36 PASS.
  - as_73: 30 PASS, 0 FAIL.
- **Fixes made in the editor stage (C++):**
  - The lobby panel is drawn above the HUD overlay (`MyHUD.cpp`).
  - Relative ServerTravel (`MyGameModeLobby.cpp`). Without it, the client froze on the end screen, because the next
    map listened on port 7777 instead of the session's port.
  - A crash guard on a seamless return in the Mech Sentinel client bubble (`MechSentinelClientBubble.*`). Without it,
    the client crashed on the PIE seamless return; a packaged client takes the same path (untested).
  - StationAims start at zero (`AirshipPawn.cpp`). This removes a log error, present since part A, on every ship spawn.
  - Countdown and DEFEAT text (`MyMatchHUDWidget.cpp`).
- **Fixes made in the editor stage (widget):** the panel scales down to fit narrow viewports, and long names are
  clipped.
- **Harness fixes:** the earlier "host's gun makes no hit after the start" was the harness sending both machines' input
  to one of them. Details: `NOTES_lobby_core.md` sections 9 to 11.

## Defaults chosen (Q-L1 to Q-L4)

1. **Q-L1:** the floor and the platform above it stay during the match. The match never uses them. To make them
   disappear at Start, tag them `LobbyOnly`.
2. **Q-L2:** without the floor, the lobby moves by itself to the path's first platform (tested).
3. **Q-L3:** Play Solo skips the lobby, and practice starts aboard team 0's ship.
4. **Q-L4:** ready flags are shown, not required. The host can start anyway with a second click. A rematch needs none.

## Not tested / manual

- **Needs you:**
  - Two packaged Steam machines, for the seamless return to the lobby (PIE uses the IP driver and, by default, a hard travel).
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
  - One short listen run of LM1.13 with the fixed IMC read, to report its PASS.
  - Seen in PIE: a PCG ensure in the existing bridge/PCG teardown when a client's hex bridge is destroyed (the trigger
    was not traced; PR B's match bridge culling may be involved), and client "GiveAbility ... not allowed" errors at
    every spawn (already there in part A).
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
  - MainMenu3, PauseMenu3, SessionEntry3, MultiplayerSessionsSubsystem and MultiplayerSessionTypes (the lobby);
  - BurrowerCharacter and MechSentinelSwarmSubsystem (small hooks);
  - MyHexPathSpawner and MyHexBridgeSubsystem.
- **Your local files are not touched:** StartupMap, BurrowerSettings.h, MyHexPlatform.h, BP_MyCharMech,
  GE_GunShootDamage, GA_GunShootBP and GA_BeamBP.
- **Base:** redo3 5d178bf (PR #19, part A).
- **Full results, the per-check tables and the media:** `Docs/Airship/round2/RESULTS_B.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
