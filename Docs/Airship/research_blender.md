# Airship: Blender model analysis for rigging

Read-only analysis of `SM_Airship` in `/mnt/new_partition/BlenderProjects/StylizedAirship/StylizedAirship.blend`
(md5 `4cb832deaa0fa005bf6a9359e34692bb`, 2026-10-31 14:30). Work ran on a copy:
`/mnt/new_partition/UnrealProjects/_AirshipWork_logs/scratch/blender_parts/Airship_copy.blend`. Talal's file was not opened.

Coordinates: Blender world metres, +X bow, +Y port (left), +Z up. Unreal: `X = 100x`, `Y = -100y`, `Z = 100z` (cm).
Directions below are physical (fore/aft, port/starboard, inboard/outboard), so they do not depend on the sign flip.

## 0. Files and how to rerun

| File (under `Docs/Airship/research/`) | What it holds |
|---|---|
| `classify_islands.py` | island -> rig part classifier (+ optional Workbench check renders) |
| `sm_airship_islands.json` | 1150 islands: id, first vertex, counts, source part, match distance, rig part, piece, index, centroid, bbox; per-part counts; frames (pivots) |
| `sm_airship_vertex_parts.json` | per-vertex rig part index and island id (36,908 entries), ready for 100 % rigid skin weights |
| `rig_analysis.py` / `rig_clearance.json` | pivots, axes, clearance sweeps (pods, nozzles, petals, fans, rudder, lamps, strips, chains) |
| `deck_placement.py` / `deck_placement.json` | deck survey, rail data, helm and cannon proposals (+ placeholder renders) |
| `img/*.jpg` | check images (colour per part, deck placeholders) |

```
B=/mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/blender; R=Docs/Airship/research
$B -b --factory-startup <copy.blend> --python $R/classify_islands.py -- --out $R/sm_airship_islands.json \
   --vertex-out $R/sm_airship_vertex_parts.json --render <scratch>/renders          # ~10 s
$B -b --factory-startup <copy.blend> --python $R/rig_analysis.py -- --islands $R/sm_airship_islands.json \
   --vparts $R/sm_airship_vertex_parts.json --out $R/rig_clearance.json             # ~3 min
$B -b --factory-startup <copy.blend> --python $R/deck_placement.py -- --islands $R/sm_airship_islands.json \
   --vparts $R/sm_airship_vertex_parts.json --out $R/deck_placement.json --render <scratch>/renders
```
`--factory-startup` keeps the BlenderMCP add-on (socket :9876) from loading in the headless run. Nothing saves the .blend.

## 1. Island classification

`SM_Airship`: 36,908 verts, 38,517 faces, 69,210 tris, **1150 loose islands**, identity transform, one material.

* Every SM vertex was matched to the nearest surface of each evaluated `Airship_Parts` object (BVH). An island takes the
  part with the smallest mean distance. 1146 islands match with max distance < 1 mm.
* Check: finalize.py merged the parts in sorted-name order with no merge-by-distance, so source labels must be monotonic
  in vertex index. **0 order violations**, 0 unassigned islands.
* Edited after the merge (expected): island 1147 `Underside_Front` (4500 verts) max 0.93 m = Talal's raised bow
  underside; island 392 hull skin max 1.3 cm. Two degenerate 3-vertex islands (1148, 1149, under the bow) stay in Hull.

### Rig parts (what the skin weights should use)

| Rig part | Islands | Verts | Tris | Pieces | Motion |
|---|---:|---:|---:|---|---|
| Hull | 669 | 26,378 | 50,078 | hull skin, bow wedge, fin, deck rails, deck props, gantry, bands, pipes, underside | static root |
| Pod_FL / FR / RL / RR | 60 each | 1,276 | 2,336 | drum 1, rib 5, mount collar 1, plate 3, bolt 15, side box 2, pipe 27, clamp 6 | gimbal (tiny range, see 3.1) |
| Nozzle_FL / FR / RL / RR | 18 each | 504 | 900 | nozzle shell 2, band 1, throat recess 1, throat glow 1, lip ring 1, **petal 12** | child of pod: vectoring, petals |
| FanHousing_L / R | 29 each | 1,022 | 1,936 | shell, intake lip, duct back wall, tail cone, gimbal ring, ring beam 2, ring knob 4, top platform, top winch, top rail 15, hanging rod | yaw (steering) |
| FanRotor_L / R | 29 each | 336 | 570 | hub+spinner 1, blade 28 | spin about X, child of housing |
| FanMount_L / R | 3 each | 24 | 36 | pylon 1, strut 2 | static (weight to Hull) |
| Rudder | 2 | 54 | 100 | blade, tiller bar | yaw about hinge |
| SearchLight_AftL / MidL / MidR / FwdC | 3 each | 52 | 92 | post, head, lens | spring wobble + head pan |
| HangStrip_1..4 | 4 / 3 / 5 / 3 | 32 / 24 / 40 / 24 | | zigzag segments (`index` 0 = top) | not recommended (buried, 3.6) |
| ChainFwd / ChainAft | 6 each | 48 | 72 | sagging links | pendulum (Fwd only) |
| Winch_Fwd / Winch_Aft | 3 each | 84 | 156 | drum, 2 flanges | optional spin |

Sum = 1150 islands / 36,908 verts / 69,210 tris. Turbine split per side: 29 housing + 29 rotor + 3 mount = 61 = the
Turbines part's 122 islands / 2. Thruster split: 60 pod + 18 nozzle = 78 per pod.

### Source part -> rig part

| Source object (Airship_Parts) | Islands | Goes to |
|---|---:|---|
| Thruster_Front_L / Front_R / Rear_L / Rear_R | 78 each | Pod_FL/FR/RL/RR + Nozzle_* (nozzle = islands with all points at h >= 2.38 m along the nozzle axis from T0) |
| Turbines | 122 | FanHousing_*, FanRotor_* (inside the duct, r <= 2.78 m, -0.65 < dx < 1.3), FanMount_* (reaches x > centre + 2.2 m) |
| Rudder | 2 | Rudder |
| Gantry | 160 | SearchLight_* (12), HangStrip_* (15), Chain* (12), Winch_* (6), rest Hull (115) |
| Hull, BowWedge, BowFin, DeckRails, DeckProps, SteamBands, SteamPipes, Underside_Front | 20, 8, 3, 200, 21, 7, 292, 3 | Hull |

Rule details are in `classify_islands.py` (section 3). Petals are numbered 0-11 by angle around the nozzle axis, blades
0-27 by angle around X (`index` field).

### Check images (looked at)

`img/parts_chase.jpg`, `parts_fan_close.jpg`, `parts_pod_close.jpg`, `parts_gantry_close.jpg`, `parts_below.jpg`
(full-size PNGs + `parts_side_port.png`, `parts_fan_rear.png` in `_AirshipWork_logs/scratch/blender_parts/renders/`).
Colours: Hull grey, pods orange (shade per pod), nozzles red, fan housings blue, rotors yellow, fan mounts green,
rudder purple, searchlights cyan, strips magenta, chains light green, winches brown. All splits read correctly; the fan
close-up shows the **green pylon slab entering the intake and ending right in front of the yellow blades**.

## 2. Pivots and axes

| Part | Pivot (Blender m) | Pivot (UE cm) | Axis | Notes |
|---|---|---|---|---|
| Pod_FL gimbal | (3.833, 4.656, -0.934) | (383.3, -465.6, -93.4) | free (pitch about Y, roll about X) | object origin = mount top |
| Pod_FR gimbal | (3.833, -4.918, -1.130) | (383.3, 491.8, -113.0) | " | Talal's hand placement: not mirror-exact |
| Pod_RL gimbal | (-7.167, 5.130, -1.204) | (-716.7, -513.0, -120.4) | " | |
| Pod_RR gimbal | (-7.167, -5.768, -1.239) | (-716.7, 576.8, -123.9) | " | |
| Nozzle axis (all pods) | | | A = (-0.139, 0, -0.990) | down, tipped 8.0 deg aft; pods have no rotation |
| Nozzle_FL / FR / RL / RR joint | FL (3.499, 4.656, -3.711), FR (3.499, -4.918, -3.907), RL (-7.501, 5.130, -3.980), RR (-7.501, -5.768, -4.016) | FL (349.9, -465.6, -371.1), FR (349.9, 491.8, -390.7), RL (-750.1, -513.0, -398.0), RR (-750.1, 576.8, -401.6) | A | = T0 + 2.4 A, drum/nozzle joint (drum R 1.85, nozzle top R 1.60); T0 = origin + (0,0,-0.4) |
| Petal hinge (12 per nozzle) | T0 + 3.9 A + 1.45 d | | t = A x d (tangent); +angle flares out | d = radial unit of the petal; petal length 0.48 m |
| Fan rotor spin (L / R) | (-17.2, +-7.6, 1.4) | (-1720, -+760, 140) | +X | blades x -17.415..-16.900, tip radius 2.751 m, hub r 0.82 |
| Fan housing yaw, recommended (L / R) | (-17.2, +-5.35, 1.4) | (-1720, -+535, 140) | vertical | 2.25 m inboard of the duct axis (see 3.3) |
| Fan duct axis / gimbal ring | ring plane x = -17.446, axis y = +-7.6, z = 1.4 | | | shell radius max 3.649, shell x -18.758..-15.519, housing x -19.906..-15.411 |
| FanMount pylon end (L) | x -16.89..-17.57, y 5.76..3.44, z 0.50..2.10 | | | slab 2.4 x 1.6 m from hull side (x -14.2) into the intake; mirror for R |
| Rudder hinge, recommended | line x = -16.364, y = 0, z -4.4..5.8 | (-1636.4, 0, ...) | vertical | hull stern face on the centreline (x -16.18..-16.36 for z -2.9..2.6) |
| Rudder hinge, alt. | (-15.6, 0, 2.9) -> (-16.0, 0, -4.4) | | (0.055, 0, 0.998) | leading edge from build_airship.py |
| SearchLight_AftL | foot (11.2, 2.8, 6.55) | (1120, -280, 655) | wobble about foot | head pivot z 9.70, post 3.0 m |
| SearchLight_MidL / MidR | (24.6, +-2.4, 7.35) | (2460, -+240, 735) | wobble at the upper-tier top | foot z 6.55 is inside the 0.8 m tier block; free post 2.2 m; head z 9.70 |
| SearchLight_FwdC | foot (30.4, 0.9, 7.35) | (3040, -90, 735) | | head z 10.50 |
| Fan hanging rods (L / R) | top (-17.2, +-7.6, -2.126) | (-1720, -+760, -212.6) | spring | 0.35 sq x 1.07 m, child of FanHousing |
| ChainFwd | (21.464, -3.353, 2.961) -> (26.545, -2.946, 4.320) | | end-to-end line | 6 links, lowest z 1.98 |
| ChainAft | (12.152, 3.147, 4.327) -> (16.247, 3.353, 3.975) | | end-to-end line | 6 links, lowest z 1.93 |
| HangStrip_1..4 anchors | (13.425,-2.9), (15.425,-2.0), (14.225,2.2), (16.225,2.9), all z 4.36 | | | truss bottom chord z 4.35 |
| Winch_Aft / Winch_Fwd | (28.3, 0, 5.0) / (30.4, 0, 5.0) | | +Y | drum r 0.72, flanges r 0.90 |

No flags, antennas or other poles exist (scan of all islands taller than 1 m and thinner than 0.4 m: only the 4 searchlight
posts, the gantry truss/rail verticals, the winch supports and the 2 fan hanging rods).

## 3. Clearance (rotated copies vs the static mesh)

Method (`rig_analysis.py`): 1 deg steps. **hard** = last angle with no new contact; **soft** = last angle where nothing
goes more than 6 cm deeper. Contacts: (a) BVH overlap with any static island that did not already touch the part at rest;
(b) penetration of the closed hull skin (island 392, 2-ray parity) by sample points (vertices + 0.15 m grid) that were
outside at rest. Pieces that already pierce the skin at rest (drum, ribs, pipe ends: the pods are built half sunk) may
cross it; they fail only if they lift more than 2 cm off it.

### 3.1 Thruster pods (gimbal about the object origin)

| Pod | nozzle fore | aft | outboard | inboard | limiter |
|---|---|---|---|---|---|
| FL | 3 / 5 | 1 / 3 | 2 / 4 | 1 / 2 | aft wrap pipes 747/765-768 and the hull skin |
| FR | 3 / 5 | 3 / 4 | 3 / 4 | 7 / 8 | pipe 843, rib 795, hull skin |
| RL | 3 / 5 | 2 / 5 | 4 / 5 | 2 / 3 | pipe 921, hull tab 395 (belly box at -9.97, 4.19, -3.79), skin |
| RR | 3 / 5 | 4 / 5 | 3 / 4 | 3 / 4 | pipes 999/1000, rib 952, skin |

(hard / soft deg.) Moving the pivot along the axis (h = -1.6, -0.4, 0.4, 1.2, 2.0 m from T0) does not help: best is
h = 0.4 (0.8 m below the origin along the axis): RL/RR 3-4 deg, FR 3-9, FL still 1-3. **The pods sit in tight pockets (pocket R 2.85 vs pipes/plates up to r 2.9, the
drum pierces the pocket floor): whole-pod tilt is only good for a +-2..3 deg spring jiggle.** Thrust vectoring must come
from the nozzle and the exhaust FX.

### 3.2 Nozzle vectoring (nozzle group about its joint) and petals

| Nozzle | fore | aft | outboard | inboard |
|---|---|---|---|---|
| FL | 30+ | 30+ | 30+ | 26 / 29 |
| FR | 30+ | 30+ | 30+ | 30+ |
| RL | 30+ | 18 / 21 | 12 / 13 | 6 / 7 |
| RR | 30+ | 25 / 29 | 30+ | 9 / 11 |

The real limit is the flat joint: the nozzle top (R 1.60) drops below the drum bottom by 1.6 sin(a):
**2 deg 5.6 cm, 4 deg 11 cm, 6 deg 17 cm, 10 deg 28 cm**. Suggest +-5 deg nozzle vectoring (gap <= 14 cm, on one side).
Petals (all 12 identical): open (flare out) free to 45 deg, close 17 deg (hits the throat recess, island 776).

### 3.3 Rear fans (yaw about a vertical axis)

Inside the steering range the binding limits are: steam-pipe ends plugged into the intake lip, the pylon slab inside the
intake (rotor blades pass **9.8 cm** in front of its tip at rest, no contact over a full blade period), and the hull skin.

| Pivot | intake outboard | intake inboard | notes |
|---|---|---|---|
| A: duct centre (-17.446, +-7.6, 1.4), whole nacelle | 1 / 2 | 45 | pipe ends 466/512/558/560 hit at once; rotor hits pylon after 2 deg |
| B: same pivot, inner duct only (ring, deck, rails stay) | 1 / 2 | 20 / 28 | ring knob 1063 inboard |
| C: pylon end (-17.2, +-4.6, 1.4) | 4 / 11 | 2 / 4 | pipe ends; rotor vs pylon 45 out / 10 in; struts embedded 30 / 10 |

Letting the 10 pipe-end islands per side clip (L: 466, 467, 512, 513, 558, 559, 560, 565, 566, 567; R: 612, 613, 658,
659, 704, 705, 706, 710, 711, 712; they stay 18-34 cm inside the nacelle shell over +-20 deg, so they never pull out),
pivot x = -17.2, offset inboard from the duct axis:

| offset (m) | hull out | hull in | rotor clear of pylon out / in | struts stay embedded out / in |
|---|---|---|---|---|
| 0 | 12-14 | 45 | 2 / 45 | 42 / 44 |
| 1.0 | 17-19 | 45 | 3 / 45 | 45 / 45 |
| 2.0 | 28-30 | 45 | 8 / 41 | 45 / 45 |
| **2.25** | **35-37** | **12** (soft 25) | **12 / 24** | 45 / 20 |
| 2.5 | 41-45 | 9 | 25 / 16 | 43 / 14 |
| 3.0 | 45 | 6 | 45 / 10 | 30 / 10 |

**Recommendation: whole nacelle (FanHousing + FanRotor) yaws about the vertical line through (-17.2, +-5.35, 1.4),
clamp +-12 deg** (clean on both sides, both fans). Up to +-20 deg costs small hull-skin contact inboard (<= 6 cm) and
blade tips crossing the pylon tip outboard. FanMount (pylon + 2 struts) and the pipe ends stay on Hull.

### 3.4 Rudder, lamps, strips, chains

| Part | Result (hard / soft deg) |
|---|---|
| Rudder, vertical hinge at x -16.364 | free to the 60 deg test limit both ways (blade + tiller bar are sunk 0.4-0.8 m into the stern; hull there is 2.7-3.7 m half-width at x -16.0, so the hidden part stays hidden) |
| Rudder, leading-edge hinge | trailing edge to starboard 53 / 55 (R fan ring knob), to port 57 / 59 (L pylon) |
| SearchLight_AftL tilt | fore/aft/starboard 20+, toward port 6-9 (gantry rail 0.25 m away) |
| SearchLight_FwdC tilt | 20+, toward port 13-14 (tier rail) |
| SearchLight_MidL / MidR tilt | 20+ every way (pivot at tier top z 7.35) |
| Search-light heads | nearest static geometry 0.91 m (Mid) / 1.71 m (Aft, Fwd): pan is free |
| HangStrip_1..4 | 33 / 48 / 41 / 11 % of their surface is **inside the bow hull at rest** (segments 1-3 run through the bow/BowWedge/Underside); swing blocked at 0-4 deg in at least one direction each |
| ChainFwd | free to 45 both ways (rests on BowWedge, 0 % inside hull) |
| ChainAft | +2 / -8 (3 links go through the hull skin) |

## 4. Placement proposals

### 4.1 Deck

| x (m) | -15 | -13 | -11 | -9 | -7 | -5 | -3 | -1 | 1 | 3 | 5 | 7 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deck half-width (m, 0.2 m grid) | 3.8 | 5.0 | 6.4 | 7.2 | 7.4 | 8.2 | 8.4 | 8.2 | 7.8 | 7.2 | 6.4 | 5.6 |
| deck z (m) | 2.91 | 2.90 | 2.82 | 2.72 | 2.62 | 2.55 | 2.49 | 2.45 | 2.42 | 2.39 | 2.39 | 2.37 |
| rail y (m) | 3.89 | 5.24 | 6.29 | 7.06 | 7.60 | 7.94 | 8.09 | 8.04 | 7.67 | 7.07 | 6.31 | 5.49 |
| rail foot z (m) | 2.912 | 2.898 | 2.815 | 2.716 | 2.624 | 2.552 | 2.493 | 2.447 | 2.416 | 2.398 | 2.386 | 2.373 |

* Open deck: hull skin with normal z > 0.9 (normal tilt <= 2 deg). It rises 0.55 m from bow to stern (sheer).
* Rails (DeckRails, 34 posts per side, x -15.76..9.51): posts 0.09 m, bars 0.07 m, **top bar +1.10 m, mid bar
  +0.55 m** above the post foot. Post gap 0.52-0.55 m aft of x -13.5, 0.67 m to x -12, 0.82-1.03 m from x -11.5 to 6.3 (widest 1.02-1.03 at x -6.4..-4.3), 0.76-0.78 m forward of 7.
  The deck lip runs about 0.3 m outside the rail line.
* Props on deck (bbox): forward hatch x -0.5..3.5, y +-1.5, top 3.06; aft hatch x -12.1..-8.9, y +-1.5, top 3.44;
  crates/barrels at x 4.3-7.4 (both sides) and x -14.2..-12.6 (y -2.8..-1.2 and 1.0..1.8). Fan upper struts land on
  the deck at x -13.4..-13.7, y +-3.1..3.5.

### 4.2 Helm (pirate wheel)

| | Value |
|---|---|
| Pedestal base | **(-5.75, 0, 2.578)** m = UE (-575, 0, 257.8) cm, on the centreline between the two hatches |
| Deck normal | (0.034, 0, 0.999) (sheer, 1.9 deg nose-down) |
| Free radius (obstacles 0.15-2.6 m above deck, and deck edge) | **3.15 m** (aft hatch at x -8.9) |
| Wheel | radius 1.2 m (1.0-1.3 fits), axle along +X, axle height ~1.55 m above deck |
| Helmsman stands | (-6.65, 0, 2.61), facing +X; free 2.25 m |
| Alternatives on the centreline | x -5.25: free 3.65 / helmsman 2.75; x -4.25: 3.75 / 3.75 (most room, a bit further forward) |

### 4.3 Cannons (2 per side, broadside)

Stations frame the helm (+-2.5 m fore/aft of it) and sit at the middle of a rail post gap so the barrel can pass
**through** the rail between the mid and the top bar.

| Cannon | Base point (m) | UE (cm) | Facing | Deck z | Rail y / foot z / mid bar / top bar | Post gap | Footprint free |
|---|---|---|---|---|---|---|---|
| Cannon_FwdL | (-3.33, 6.979, 2.502) | (-333, -697.9, 250.2) | +Y (port) | 2.502 | 8.079 / 2.502 / 3.052 / 3.602 | 0.975 (posts x -3.821, -2.847) | 0.71 |
| Cannon_FwdR | (-3.33, -6.979, 2.502) | (-333, 697.9, 250.2) | -Y (stbd) | 2.502 | -8.079 / same | same | 0.71 |
| Cannon_AftL | (-8.22, 6.186, 2.680) | (-822, -618.6, 268.0) | +Y | 2.680 | 7.286 / 2.680 / 3.230 / 3.780 | 0.937 (posts x -8.668, -7.767) | 0.54 |
| Cannon_AftR | (-8.22, -6.186, 2.680) | (-822, 618.6, 268.0) | -Y | 2.680 | -7.286 / same | same | 0.54 |

* Base point = carriage centre on the deck; carriage 1.6 m (along Y) x 1.2 m, its front edge 0.3 m inside the rail line.
  "Footprint free" = clearance to anything but the rail.
* Barrel 2.6 m, muzzle 0.9 m past the rail (y +-8.98 fwd, +-8.19 aft).
  Through the rail: axis at deck + 0.83 m (z 3.33 fwd, 3.51 aft), 0.24 m clear of both bars, so barrel diameter <= 0.46 m.
  Over the rail: axis at top bar + 0.31 m (z 3.91 fwd, 4.09 aft).
* `img/deck_top.jpg` and `img/deck_chase.jpg` show placeholder carriages (red), barrels (black), wheel (yellow) and
  helmsman (blue); all four guns and the wheel read clearly from a camera behind/above the stern.

## 5. Secondary motion candidates

| Candidate | Islands | Pivot / axis | Range found | Recommendation |
|---|---|---|---|---|
| Thruster pods | Pod_* | origin, free | +-2-3 deg | spring jiggle only (lag on thrust changes) |
| Nozzles | Nozzle_* | joint, A | +-5 deg (gap) | vectoring + spring overshoot |
| Nozzle petals | 12 per nozzle (`index` 0-11) | top edge, tangent | open 45, close 17 | one value driving all 12: flare open with throttle, flutter on death |
| Fan rotors | FanRotor_* | (-17.2, +-7.6, 1.4), X | free spin | speed from throttle/steer; free-wheel spin-down on death |
| Fan nacelles | FanHousing_* | (-17.2, +-5.35, 1.4), Z | +-12 deg | steering yaw + spring overshoot |
| Rudder | Rudder | x -16.364, Z | +-60 deg tested | follow steering (+-30-35 deg reads well), spring lag |
| Search lights | 4 x (post, head, lens) | foot / tier top | 6-20 deg | post spring wobble +-3-5 deg, heads pan/sweep (free) |
| ChainFwd | 6 links | end-to-end line | +-45 | pendulum swing on accel/turn (1 bone, or 2 split at the middle link) |
| Fan hanging rods | 1085, 1146 | top, under each nacelle | not swept [unverified] | small spring pendulum, child of FanHousing |
| Winches | 2 x 3 | (28.3 / 30.4, 0, 5.0), Y | free spin | optional idle spin |
| HangStrips, ChainAft | | | blocked / buried | leave on Hull (most of their length is inside the bow hull) |

## 6. Findings that matter for the rig

1. Every SM_Airship island maps to exactly one rigid part, so skin weights can be 100 % per island
   (`sm_airship_vertex_parts.json`), like the Burrower's "hard" pieces. No geometry or UV edits are needed.
2. The pods cannot visibly tilt (2-4 deg), so thrust vectoring belongs on the nozzle bones (+-5 deg) and the Niagara plume.
3. The fan yaw pivot must be 2.25 m inboard of the duct axis. Otherwise the pylon slab (which ends inside the intake,
   9.8 cm in front of the blades) or the plugged-in steam-pipe ends block the turn at 1-2 deg.
4. The pods are not mirror-exact (Talal placed them by hand): FR is 0.26 m further outboard and 0.2 m lower than FL,
   RR is 0.64 m further outboard than RL. Use the per-pod pivots above.
