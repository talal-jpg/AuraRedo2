# SK_Airship rig: 118 bones, rigid skin, FBX for Unreal

Rig of the stylized airship (Talal's `SM_Airship`, geometry and UVs unchanged) plus the new helm and four cannons, made to
`/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/RIG_CONTRACT.md`. Every part is a rigid piece: each vertex
belongs 100 % to one bone. Built headless in Blender 4.5.3 from the scripts in `scripts/` (nothing done by hand).

## Files

Blender side: `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/` (called `rig/` below). Repo copy:
`_AirshipWork/SourceArt/Airship/` (the two FBX files, `textures/`, `scripts/`, this README).

| File | What it is |
|---|---|
| `SK_Airship.fbx` (rig/export, SourceArt/Airship) | Skeleton (118 bones) + 31 skinned meshes in rest pose, no animation. Import this as the skeletal mesh. |
| `SK_Airship_testanim.fbx` | Same skeleton and meshes + a 32 s test sweep (frames 1-961 at 30 fps, take `SK_Airship_TestSweep`): every control swept through its range, one group every 2 s (`checks/rig/testanim_segments.json`). Import as an animation on SKEL_Airship. |
| `rig/AirshipRig.blend` | Blender source: armature `Armature`, the meshes in collection `SK_Airship` (vertex groups + Armature modifier), action `SK_Airship_TestSweep` (not assigned). Made from `rig/AirshipRig_src.blend`, a byte copy of Talal's StylizedAirship.blend (md5 4cb832deaa0fa005bf6a9359e34692bb, never written). |
| `SourceArt/Airship/textures/` (= `rig/props/textures/`) | The prop atlas `T_AirshipProps_ComicLines.png` (sRGB) and `T_AirshipProps_ComicMask.png` (linear), 2048. The hull keeps the existing `T_Airship_ComicLines` / `T_Airship_ComicMask` (4096) already in `/Game/Assets/MyShip`. |
| `rig/checks/rig/` | `placement.json` (helm + cannon spots, cannon/helm clearance sweeps), `motion_ranges.json` (every other control swept), `bones_spec.json` / `bones_blender.json` (bones in Blender metres), `bones_ue.csv` (bones in UE cm), `skin_report.json` (vertex counts per bone and mesh), `fbx_SK_Airship*.json` (raw FBX structure), `roundtrip.json`. |
| `rig/renders/rig/` | `rest_*` colour per bone (side, top, two 3/4 views, close-ups), `A_*` every control at its + limit, `B_*` at its - limit. |

Scripts (`rig/scripts/`, copied to `SourceArt/Airship/scripts/`; run all with `bash rig/scripts/rig_all.sh`, about 2 min):
`rig_common.py` (paths, bone map, pose maths), `rig_place.py` (step 1: placement + clearance), `rig_build.py` (steps 2-4:
armature, skin, props, materials, test action), `rig_export.py` (step 5, `-- --anim` for the test file),
`rig_fbx_inspect.py`, `rig_roundtrip.py`, `rig_check_motion.py`, `rig_render.py` (step 6), `rig_readme.py` (this file),
`rig_inspect.py` (lists what a .blend holds).

## Mesh and materials

* 55,948 vertices, 104,730 triangles, 31 mesh nodes; Unreal merges them into one skeletal mesh.
* Material slot 0 `M_Airship` (SM_Airship, 36,908 vertices, UVs untouched). Slot 1 `M_AirshipProps` (helm + 4 cannons,
  the shared 2048 atlas; the four cannon copies use the same atlas region, everything else is overlap-free). The prop
  meshes are named `SM_AirshipProp_*` so that `SM_Airship` comes first in the FBX (Blender writes objects by name), which
  puts M_Airship first in the file's material list.
* Smoothing by face (as the existing SM_Airship.fbx), normals written per corner, no tangents (Unreal computes them).
* No UCX hulls in this FBX: the pawn uses the existing `/Game/Assets/MyShip/SM_Airship` (8 UCX) as its physics body.

## Skeleton

All positions are Unreal component space in cm (`X = 100x`, `Y = -100y`, `Z = 100z` from Blender metres); port (L) is UE -Y.
Every bone is world-aligned (Blender: head at the pivot, tail = head + (0, 0, 50 cm), roll 0), so in Unreal every bone has
the identity rest rotation, the same as `root`, and its local axes are the component axes. Part roots are direct children
of `Hull`. `v` = vertices skinned to the bone; sockets have no vertices and are not deforming.

```
root                                           (0.0, 0.0, 0.0)                   -  actor origin
└─ Hull                                        (0.0, 0.0, 0.0)             26594 v  hull, deck, rails, gantry, pipes, fan pylons, hang strips, aft chain
   ├─ Thruster_FL                              (383.3, -465.6, -93.4)       1276 v  pod (drum, plates, pipes)
   │  └─ Thruster_FL_Nozzle                    (349.9, -465.6, -371.0)       408 v  nozzle shell, band, throat, lip (petals are children)
   │     ├─ Thruster_FL_Petal00..11            ring, see the CSV          8 v each  12 petals, hinge at the top edge
   │     └─ Thruster_FL_Flame                  (322.8, -465.6, -564.1)           -  socket: nozzle exit, exhaust along A
   ├─ Thruster_FR                              (383.3, 491.8, -113.0)       1276 v  pod
   │  └─ Thruster_FR_Nozzle                    (349.9, 491.8, -390.7)        408 v  nozzle shell, band, throat, lip (petals are children)
   │     ├─ Thruster_FR_Petal00..11            ring, see the CSV          8 v each  12 petals, hinge at the top edge
   │     └─ Thruster_FR_Flame                  (322.8, 491.8, -583.8)            -  socket: nozzle exit, exhaust along A
   ├─ Thruster_RL                              (-716.7, -513.0, -120.4)     1276 v  pod
   │  └─ Thruster_RL_Nozzle                    (-750.1, -513.0, -398.0)      408 v  nozzle shell, band, throat, lip (petals are children)
   │     ├─ Thruster_RL_Petal00..11            ring, see the CSV          8 v each  12 petals, hinge at the top edge
   │     └─ Thruster_RL_Flame                  (-777.2, -513.0, -591.1)          -  socket: nozzle exit, exhaust along A
   ├─ Thruster_RR                              (-716.7, 576.8, -123.9)      1276 v  pod
   │  └─ Thruster_RR_Nozzle                    (-750.1, 576.8, -401.6)       408 v  nozzle shell, band, throat, lip (petals are children)
   │     ├─ Thruster_RR_Petal00..11            ring, see the CSV          8 v each  12 petals, hinge at the top edge
   │     └─ Thruster_RR_Flame                  (-777.2, 576.8, -594.7)           -  socket: nozzle exit, exhaust along A
   ├─ Turbine_L                                (-1720.0, -535.0, 140.0)     1014 v  fan nacelle: shell, ring, top deck + rail (yaw pivot 2.25 m inboard)
   │  ├─ Turbine_L_Rotor                       (-1720.0, -760.0, 140.0)      336 v  rotor hub + 28 blades, spins about +X
   │  ├─ Turbine_L_Rod                         (-1720.0, -760.0, -212.6)       8 v  hanging rod (top)
   │  └─ Turbine_L_Exhaust                     (-1875.8, -760.0, 140.0)          -  socket: duct rear exit, blows toward -X
   ├─ Turbine_R                                (-1720.0, 535.0, 140.0)      1014 v  fan nacelle
   │  ├─ Turbine_R_Rotor                       (-1720.0, 760.0, 140.0)       336 v  rotor hub + 28 blades, spins about +X
   │  ├─ Turbine_R_Rod                         (-1720.0, 760.0, -212.6)        8 v  hanging rod (top)
   │  └─ Turbine_R_Exhaust                     (-1875.8, 760.0, 140.0)           -  socket: duct rear exit, blows toward -X
   ├─ Rudder                                   (-1636.4, 0.0, 70.0)           54 v  blade + tiller bar, vertical hinge
   ├─ SearchLight_AftL                         (1120.0, -280.0, 655.0)        12 v  post
   │  └─ SearchLight_AftL_Head                 (1120.0, -280.0, 970.0)        40 v  head + lens
   ├─ SearchLight_MidL                         (2460.0, -240.0, 735.0)        12 v  post
   │  └─ SearchLight_MidL_Head                 (2460.0, -240.0, 970.0)        40 v  head + lens
   ├─ SearchLight_MidR                         (2460.0, 240.0, 735.0)         12 v  post
   │  └─ SearchLight_MidR_Head                 (2460.0, 240.0, 970.0)         40 v  head + lens
   ├─ SearchLight_FwdC                         (3040.0, -90.0, 735.0)         12 v  post
   │  └─ SearchLight_FwdC_Head                 (3040.0, -90.0, 1050.0)        40 v  head + lens
   ├─ ChainFwd                                 (2654.5, 294.6, 432.0)         48 v  end A, 6 links
   │  └─ ChainFwd_End                          (2146.4, 335.3, 296.1)            -  end B, swing axis marker
   ├─ Winch_Fwd                                (3040.0, 0.0, 500.0)           84 v  drum + 2 flanges
   ├─ Winch_Aft                                (2830.0, 0.0, 500.0)           84 v  drum + 2 flanges
   ├─ Helm                                     (-650.0, 0.0, 260.5)         1268 v  pedestal base on the deck
   │  └─ Helm_Wheel                            (-713.0, 0.0, 425.5)         2016 v  wheel axle centre
   ├─ PilotSeat                                (-843.0, 0.0, 268.9)              -  pilot stands here (marker)
   ├─ Cannon_L1                                (-46.3, -598.5, 243.7)       1522 v  carriage
   │  ├─ Cannon_L1_Barrel                      (-44.8, -628.5, 323.7)       1556 v  barrel (trunnion axis)
   │  │  └─ Cannon_L1_Muzzle                   (-44.8, -784.5, 323.7)            -  socket: muzzle face
   │  ├─ Cannon_L1_Quoin                       (-45.7, -518.5, 276.7)         77 v  quoin wedge
   │  ├─ Cannon_L1_Wheel_FL                    (-98.4, -648.5, 266.7)        196 v  truck wheel FL
   │  ├─ Cannon_L1_Wheel_FR                    (6.6, -648.5, 264.8)          196 v  truck wheel FR
   │  ├─ Cannon_L1_Wheel_BL                    (-98.4, -545.5, 266.7)        196 v  truck wheel BL
   │  └─ Cannon_L1_Wheel_BR                    (6.6, -545.5, 264.8)          196 v  truck wheel BR
   ├─ Cannon_L2                                (-1147.2, -392.7, 283.6)     1522 v  carriage
   │  ├─ Cannon_L2_Barrel                      (-1143.7, -422.7, 363.5)     1556 v  barrel (trunnion axis)
   │  │  └─ Cannon_L2_Muzzle                   (-1143.7, -578.7, 363.5)          -  socket: muzzle face
   │  ├─ Cannon_L2_Quoin                       (-1145.7, -312.7, 316.6)       77 v  quoin wedge
   │  ├─ Cannon_L2_Wheel_FL                    (-1198.7, -442.7, 307.9)      196 v  truck wheel FL
   │  ├─ Cannon_L2_Wheel_FR                    (-1093.8, -442.7, 303.3)      196 v  truck wheel FR
   │  ├─ Cannon_L2_Wheel_BL                    (-1198.7, -339.7, 307.9)      196 v  truck wheel BL
   │  └─ Cannon_L2_Wheel_BR                    (-1093.8, -339.7, 303.3)      196 v  truck wheel BR
   ├─ Cannon_R1                                (-46.3, 598.5, 243.7)        1522 v  carriage
   │  ├─ Cannon_R1_Barrel                      (-44.8, 628.5, 323.7)        1556 v  barrel (trunnion axis)
   │  │  └─ Cannon_R1_Muzzle                   (-44.8, 784.5, 323.7)             -  socket: muzzle face
   │  ├─ Cannon_R1_Quoin                       (-45.7, 518.5, 276.7)          77 v  quoin wedge
   │  ├─ Cannon_R1_Wheel_FL                    (6.6, 648.5, 264.8)           196 v  truck wheel FL
   │  ├─ Cannon_R1_Wheel_FR                    (-98.4, 648.5, 266.7)         196 v  truck wheel FR
   │  ├─ Cannon_R1_Wheel_BL                    (6.6, 545.5, 264.8)           196 v  truck wheel BL
   │  └─ Cannon_R1_Wheel_BR                    (-98.4, 545.5, 266.7)         196 v  truck wheel BR
   └─ Cannon_R2                                (-1147.2, 392.7, 283.6)      1522 v  carriage
      ├─ Cannon_R2_Barrel                      (-1143.7, 422.7, 363.5)      1556 v  barrel (trunnion axis)
      │  └─ Cannon_R2_Muzzle                   (-1143.7, 578.7, 363.5)           -  socket: muzzle face
      ├─ Cannon_R2_Quoin                       (-1145.7, 312.7, 316.6)        77 v  quoin wedge
      ├─ Cannon_R2_Wheel_FL                    (-1093.8, 442.7, 303.3)       196 v  truck wheel FL
      ├─ Cannon_R2_Wheel_FR                    (-1198.7, 442.7, 307.9)       196 v  truck wheel FR
      ├─ Cannon_R2_Wheel_BL                    (-1093.8, 339.7, 303.3)       196 v  truck wheel BL
      └─ Cannon_R2_Wheel_BR                    (-1198.7, 339.7, 307.9)       196 v  truck wheel BR
```

Cannon wheel letters are the cannon's own: F = toward the muzzle (outboard), L = the cannon's left (+Y in its frame), so
on the port guns `Wheel_FL` is the outboard-aft wheel and on the starboard guns the outboard-forward one.
Every bone with its exact position is in `checks/rig/bones_ue.csv`.

## How the weights work

* Every vertex is in exactly one vertex group with weight 1.0 (checked in Blender and again in the FBX: 0 vertices with
  two bones, 0 unweighted, weight sums exactly 1). One group per deforming bone, 105 deforming bones, 13 sockets.
* SM_Airship: weights per loose island from the island classifier (`Docs/Airship/research/sm_airship_vertex_parts.json`).
  The classifier's 1150 islands were checked to still be exactly the mesh's loose parts (same centroids within 2 mm).
  Research part -> bone: Hull, FanMount_L/R, HangStrip_1..4, ChainAft -> `Hull`; Pod_X -> `Thruster_X`; Nozzle_X petal k ->
  `Thruster_X_Petalkk`, the other nozzle islands -> `Thruster_X_Nozzle`; FanHousing_L/R -> `Turbine_L/R` except the
  hanging rod -> `Turbine_*_Rod`; FanRotor -> `Turbine_*_Rotor`; Rudder; SearchLight post -> `SearchLight_*`, head + lens ->
  `SearchLight_*_Head`; ChainFwd; Winch_Fwd/Aft.
* Props: each prop object is 100 % on its bone (pedestal `Helm`, wheel `Helm_Wheel`, carriage `Cannon_X`, barrel
  `Cannon_X_Barrel`, quoin `Cannon_X_Quoin`, wheels `Cannon_X_Wheel_*`).
* Rigid pieces never bend, so a joint shows only where two pieces meet (nozzle in drum, fan nacelle around the pylon, etc.);
  the ranges below say how far each joint can go before that shows.

## Placement (contract section 4)

| Prop | Bone position (UE cm) | How it was placed |
|---|---|---|
| Helm | (-650.0, 0.0, 260.5) | centreline x -6.5 m, z = deck at that point; the base plate reaches 5 cm below its origin, so nothing floats (its aft edge sits 3.8 cm proud of the sloping deck) |
| Helm_Wheel | (-713.0, 0.0, 425.5) | Helm.blend wheel origin offset (-63, 0, 165) cm; axle along X, the helmsman's side faces aft |
| PilotSeat | (-843.0, 0.0, 268.9) | 1.3 m aft of the axle on the deck (the aft hatch starts 47 cm further aft) |
| Cannon_L1 / R1 | (-46.3, -598.5, 243.7) / Y mirrored | rail-post gap middle nearest x -0.46 = Talal's fore mark (see the change log) (gap 0.88 m, rail at 8.4 deg to the ship's axis), muzzle face 0.12 m inside the rail centre line, barrel axis 80 cm above the rail foot (mid bar 55, top bar 110) |
| Cannon_L2 / R2 | (-1147.2, -392.7, 283.6) / Y mirrored | gap middle nearest x -11.3 = Talal's aft mark (gap 0.83 m), moved 0.18 m inboard: muzzle face 0.30 m inside the rail (see deviations) |

The cannons sit on the deck with all four wheels touching (within 1 mm): the deck rises toward the stern
(1.02 deg at the fore pair, 2.52 deg at the aft pair), and that slope runs along the
cannon's axles, so each cannon is rolled by it about its own firing axis. The firing direction (Muzzle - Barrel) is still
exactly +-Y.

## Ranges found

"hard" = last value with no collision (cannons, helm: no triangle contact with anything new; hull parts: no new contact and
nothing pushed more than 2 cm into the closed hull skin or the bow wedge). Directions use the contract's signs.

| Control (contract range) | Safe range found | Notes |
|---|---|---|
| CannonYawDeg L1/R1 (+-20) | -45 .. +45 | free to the 45 deg test limit, also at elevation +9 / -10 and at 60 cm recoil; smallest muzzle-to-rail gap over yaw +-20 x elevation -10/0/+9 x recoil 0/30/60: 2.7 cm |
| CannonYawDeg L2 (+-20) | -45 .. +21.4 | + swings the muzzle aft, toward the rail that closes in there; +21.4 at elevation -10, +22.0 at +9, free with 60 cm recoil; smallest gap at the +-20 corners 2.2 cm |
| CannonYawDeg R2 (+-20) | -21.4 .. +45 | mirror of L2 (- swings it aft) |
| CannonElevDeg (-10..+9) | -14.40 .. +8.75 | limited by the cannon itself (the barrel meets its carriage at +8.75; the chase meets the transom at -14.4), not by the ship (free +-20 against the rail and deck); +9 overshoots by 0.25 deg (a few mm), clamp at +8.75. The quoin must slide back with elevation: slide = clamp(2.4 cm/deg x elev, 0, 15 cm) along -aim |
| CannonRecoilCm (0..60) | 0 .. 120+ | nothing behind any gun within 1.2 m (hatches, helm, fan struts, the other guns); wheels stay on open deck. Wheel spin for rolling: recoil / 22 cm rad, backward |
| Cannon wheels vs deck | +-1.9 cm | at yaw +-20 the deck slope under the turned carriage lifts/sinks a wheel by up to this much (0 at yaw 0) |
| WheelAngleDeg (unbounded) | free | 5 deg steps all round: no new contact with the pedestal; handle tips clear the deck by 7.5 cm |
| NozzlePitchDeg / NozzleRollDeg (+-5) | FL +12.0 / -12.0, +12.0 / -12.0; FR +12.0 / -12.0, +12.0 / -12.0; RL +8.5 / -12.0, +6.0 / -12.0; RR +12.0 / -12.0, +12.0 / -8.5 | pitch + / -, roll + / -; free to the 12 deg test limit except where shown. The joint is flat: the nozzle top drops 14 cm below the drum on one side at 5 deg (research_blender.md 3.2) |
| NozzleFlareDeg (-10..+35) | -16 .. +45 | all four; closing past -16 hits the throat recess |
| Pods (physics jiggle +-3) | FL pitch +0.5 / -3.0, roll +0.5 / -4.0; FR pitch +0.5 / -4.5, roll +4.0 / -0.5; RL pitch +1.0 / -2.5, roll +0.5 / -4.0; RR pitch +1.5 / -4.5, roll +4.0 / -0.5 | pitch +/-, roll +/- (same axes as the nozzle). The pods sit in tight pockets: +-0.5 is clean everywhere, +-1 pushes a rib up to 4 cm into the pocket wall on the tight side, +-3 the ribs and drum up to 15 cm (inside the pocket, so it only shows at close range) |
| TurbineYawDeg (+-12) | L -33 .. +12, R -12 .. +33 | the inboard turn stops at 12 on the steam band, the outboard one at 33 on the hull skin. The 10 steam-pipe ends per side plugged into the intake lip stay on Hull and clip inside the nacelle (allowed, research 3.3) |
| RotorAngleDeg | free | full turn at yaw -12, 0 and +12, clear of the pylon slab |
| RudderDeg (+-30) | +-60 | free to the test limit (hinge part buried in the stern) |
| Turbine rods (small pendulum) | +-20 | both axes, free (not swept in the research) |
| Search light posts (wobble +-4) | +-15 fore/aft; -6 .. +15 sideways | tilting the posts toward port, the AftL post meets the gantry rail at 7 deg; the heads pan freely all round |
| ChainFwd swing | 0 .. +25 (outward only) | + = right-handed about ChainFwd -> ChainFwd_End (Blender), swings the sag out to starboard. Inward the links go into the bow wedge at once (-10 deg: 30 cm). At rest the chain already dips up to 12 cm into the wedge and 5-7 cm into the side panels; swinging out lifts it clear except the last link at end B (in its panel, up to 8 cm at +25). The research's "free to 45 both ways" missed this because the chain touches the wedge at rest |
| Winch spin | free | |

## What to know in Unreal

* Import `SK_Airship.fbx` as a Skeletal Mesh with a new skeleton `SKEL_Airship`: Convert Scene on (default), Force Front X
  Axis off, no unit tricks (the file is cm, UnitScaleFactor 1), Normals: Import, Use T0 As Ref Pose off, no animation,
  materials not created (assign `M_Airship` to slot 0 and `M_AirshipProps` to slot 1). The legacy FBX importer
  (`Interchange.FeatureFlags.Import.FBX false`, as used for SM_Airship) skips a Blender node named `Armature`
  (FbxMainImport.cpp, GetRootSkeleton), so the root bone is `root`, as with the Burrower FBX made the same way.
* Expected after import: 118 bones, root `root` with one child `Hull`; ship about 52 m long, bow +X, Z up; `Cannon_L1` at
  about (-46, -598, 244), `Thruster_FL` at (383, -466, -93). Every bone's reference rotation should be the identity
  (in the file the root LimbNode carries Lcl Rotation (-90, 0, 0), which Unreal's Y-up -> Z-up scene conversion turns into
  the identity; every other node is identity). If an importer shows a different but common rotation on all bones, the rig
  still works: the Control Rig bakes its axes from the rest pose.
* Sockets for C++/Niagara: `Thruster_*_Flame` (exhaust along A = (-0.139, 0, -0.990) in Blender, UE (-0.139, 0, -0.990)),
  `Turbine_*_Exhaust` (blows toward -X), `Cannon_*_Muzzle` (fire along Muzzle - Barrel: +Y Blender = UE -Y for L guns,
  UE +Y for R guns), `PilotSeat`, `ChainFwd_End` (chain swing axis with `ChainFwd`).
* Axes for the Control Rig (from the rest pose, so no local axis is assumed): petal hinge axis = A x d (d = the petal's
  radial unit; the bone sits on the hinge at the top edge, h = 3.90 m along A, r = 1.42 m); fan rotor spins about +X;
  cannon elevation about the true trunnion axis = the cannon's own Y, which is horizontal up to the 2.5 deg deck roll
  (using Z x aim instead moves the trunnion ends by about 2 mm, invisible); cannon wheels spin about the same axis.
* Clamp the controls to the safe ranges above: elevation +8.75, aft yaw of L2/R2 21 deg, chain outward only, pods +-0.5..1
  if close-ups matter. `SK_Airship_testanim.fbx` stays inside those ranges (elevation +8.75 max, chain 0..+25) except the
  pods (+-3, the contract's value) and the extra helper sweeps (rods +-8, posts +-4).
* Triangle count 104,730 (hull 69,210); bounds about 51.9 x 23.9 x 17 m like SM_Airship plus the props.

## Deviations from the contract

1. **Cannons are rolled to the deck** (1.02 / 2.52 deg about the firing axis) instead of "Z up". With Z up the
   uphill wheels sank 1.9 cm (fore pair) and 4.6 cm (aft pair) into the deck. The aim (Muzzle - Barrel) is unchanged; the
   Barrel/Muzzle/Quoin/wheel bones move up to 1.4 cm (fore) / 3.5 cm (aft) along X compared with the unrolled frame. `rig_place.py -- --cannon-roll off`
   restores Z up.
2. **Aft guns 0.18 m further inboard** (muzzle face 0.30 m inside the rail centre line, not 0.12). The rail
   there runs at 23.6 deg to the ship's axis, so with 0.12 m the muzzle hits it before the gun has yawed 10 deg aft.
   The script moves the gun inboard in 1 cm steps until yaw +-20 at elevation -10/0/+9 and recoil 0/30/60 is clear by 2 cm.
   The ball path is unchanged: through the gap between mid and top bar.
3. **Elevation +9** is 0.25 deg past what the cannon model allows (+8.75, the barrel meets its carriage); the test animation uses +8.75.
4. **Export bone axes**: `primary_bone_axis='Z'`, `secondary_bone_axis='X'` instead of the Burrower's Y/X. Everything else
   is the Burrower export (cm, `Armature` node, root `root`, Y-up file with pre-rotated data, no leaf bones, smoothing by face).
   With Y/X our up-pointing Blender bones would arrive in Unreal rotated 90 deg about X; with Z/X they arrive as identity.
5. Petal hinges are taken from the geometry (centre of each petal's top edge): h = 3.90 m along A as in the contract, radius
   1.42 m instead of the formula's 1.45 (the formula's radius is the petal's outer face; the bone sits mid-thickness).
6. The contract's ChainFwd end labels are swapped relative to research end_a/end_b; the contract's coordinates are used
   (`ChainFwd` at (26.545, -2.946, 4.320) m, `ChainFwd_End` at (21.464, -3.353, 2.961) m).
7. Exact socket spots where the contract says "about": `Thruster_*_Flame` on the nozzle axis at the petal tips (h = 4.35 m
   along A); `Turbine_*_Exhaust` at the duct shell's rear rim, x = -18.758 m.

## Change log

* **2026-11-22, fore cannon pair moved forward to Talal's mark.** `Cannon_L1` / `Cannon_R1` (and all their sub-bones
  and sockets) moved from the rail-post gap at x -5.344 m to the gap at x -0.4627 m: UE (+488.1, -7.6, -12.7) cm for
  L1, Y mirrored for R1. Why: the contract read Talal's fore mark in `talal_sketches/3_cannon_spots.png` as "about x -5.3",
  which put the guns between his two marks. With the sketch camera solved from 6 landmarks (within 1.4 px,
  `checks/verify/sketch_camera.json`) the rigged cannon was projected at every port rail gap
  (`scripts/verify_station_fit.py` -> `checks/verify/station_fit.json`): at -0.4627 its silhouette centre is +4 px from the
  mark's centre and 72 % of it lies inside the mark (gap -1.387: +20 px, 45 %; old gap -5.344: +79 px, 0 %). Other readings of
  the same mark: ray hits on the ship median x -0.65; the mark cast onto the rail's vertical surface spans x
  -1.6 .. 2.83 (median 1.07). The aft pair stays at gap -11.472 (ray-hit median -11.33; that mark is seen too
  edge-on to pin it closer than a few metres). `RIG_CONTRACT.md` section 4 was updated. The new muzzle sockets are at UE
  (-44.8, -784.5, 323.7) (L1) and (-44.8, 784.5, 323.7) (R1); `AirshipPawn.h` `CannonMuzzleFallback` (only used when the
  mesh has no muzzle bones) holds these positions too. Other stations: set `CANNON_TARGET_X` L1/R1 in `rig_common.py`
  (-1.3 = the next gap aft, -5.3 = the old station) and run `rig_all.sh`.

## How it was checked

* Blender side (`rig_build.py`): every bone world-aligned (rest matrix = 90 deg about X, head at the pivot), deform flag
  exactly on the bones that have vertices, every vertex one group at 1.0, SM_Airship positions + UVs + face corners hashed
  before and after (unchanged), prop pivots on the placed objects' origins.
* FBX (`rig_fbx_inspect.py`, Blender's raw FBX parser, no importer logic): FBX 7.4, Y-up, UnitScaleFactor 1; 1 Null
  `Armature` (identity) -> 118 LimbNodes, 31 meshes each with one Skin, 105 clusters, every vertex weighted once with sum 1,
  bind poses cover all 118 bones and agree with every cluster's TransformLink, node transforms agree with the bind pose
  (max 0.0002 cm); materials in file order ['M_Airship', 'M_AirshipProps']; Unreal view of every bone
  (Y-up -> Z-up, handedness flip): max rest rotation 1e-05 deg.
* Round trip (`rig_roundtrip.py`): both FBX files re-imported into an empty scene: same 118 bones and parents
  (position error 0.0020 mm, rotation error 0.0 deg), same 55,948 vertices
  (0.0017 mm) and weights (0 differences); the test animation deforms the re-imported meshes like the
  original rig at 16 frames across all segments (max 0.007 mm, while the parts move up to 5.5 m).
* Clearance: `rig_place.py` (cannons and helm, numbers above), `rig_check_motion.py` (every other control).
* Independent verification (not using the rig_* code): `bash rig/scripts/verify_all.sh` (`verify_*.py`, about 1 min) writes
  `checks/verify/` (FBX structure, import + per-bone deform test, prop atlas, sketch camera fits + mark positions) and
  `renders/verify/` (rest/posed colour per bone, Talal's sketch views with his marks laid over, textured props).
* Renders (`renders/rig/`), looked at: colour per bone at rest (side, top, 3/4 above, 3/4 below, close-ups) and both limit
  poses; no tearing (every piece rigid), nothing floating, the only overlaps are the ones listed in the ranges.

## Appendix: all bones (UE cm)

| Bone | Parent | X | Y | Z | Vertices |
|---|---|---:|---:|---:|---:|
| root | - | 0.0 | 0.0 | 0.0 | 0 |
| Hull | root | 0.0 | 0.0 | 0.0 | 26594 |
| Cannon_L1 | Hull | -46.27 | -598.47 | 243.73 | 1522 |
| Cannon_L1_Barrel | Cannon_L1 | -44.845 | -628.47 | 323.717 | 1556 |
| Cannon_L1_Muzzle | Cannon_L1_Barrel | -44.845 | -784.47 | 323.717 | 0 |
| Cannon_L1_Quoin | Cannon_L1 | -45.682 | -518.47 | 276.725 | 77 |
| Cannon_L1_Wheel_BL | Cannon_L1 | -98.37 | -545.47 | 266.661 | 196 |
| Cannon_L1_Wheel_BR | Cannon_L1 | 6.613 | -545.47 | 264.792 | 196 |
| Cannon_L1_Wheel_FL | Cannon_L1 | -98.37 | -648.47 | 266.661 | 196 |
| Cannon_L1_Wheel_FR | Cannon_L1 | 6.613 | -648.47 | 264.792 | 196 |
| Cannon_L2 | Hull | -1147.18 | -392.74 | 283.6 | 1522 |
| Cannon_L2_Barrel | Cannon_L2 | -1143.66 | -422.74 | 363.523 | 1556 |
| Cannon_L2_Muzzle | Cannon_L2_Barrel | -1143.66 | -578.74 | 363.523 | 0 |
| Cannon_L2_Quoin | Cannon_L2 | -1145.728 | -312.74 | 316.568 | 77 |
| Cannon_L2_Wheel_BL | Cannon_L2 | -1198.661 | -339.74 | 307.888 | 196 |
| Cannon_L2_Wheel_BR | Cannon_L2 | -1093.763 | -339.74 | 303.269 | 196 |
| Cannon_L2_Wheel_FL | Cannon_L2 | -1198.661 | -442.74 | 307.888 | 196 |
| Cannon_L2_Wheel_FR | Cannon_L2 | -1093.763 | -442.74 | 303.269 | 196 |
| Cannon_R1 | Hull | -46.27 | 598.47 | 243.73 | 1522 |
| Cannon_R1_Barrel | Cannon_R1 | -44.845 | 628.47 | 323.717 | 1556 |
| Cannon_R1_Muzzle | Cannon_R1_Barrel | -44.845 | 784.47 | 323.717 | 0 |
| Cannon_R1_Quoin | Cannon_R1 | -45.682 | 518.47 | 276.725 | 77 |
| Cannon_R1_Wheel_BL | Cannon_R1 | 6.613 | 545.47 | 264.792 | 196 |
| Cannon_R1_Wheel_BR | Cannon_R1 | -98.37 | 545.47 | 266.661 | 196 |
| Cannon_R1_Wheel_FL | Cannon_R1 | 6.613 | 648.47 | 264.792 | 196 |
| Cannon_R1_Wheel_FR | Cannon_R1 | -98.37 | 648.47 | 266.661 | 196 |
| Cannon_R2 | Hull | -1147.18 | 392.74 | 283.6 | 1522 |
| Cannon_R2_Barrel | Cannon_R2 | -1143.66 | 422.74 | 363.523 | 1556 |
| Cannon_R2_Muzzle | Cannon_R2_Barrel | -1143.66 | 578.74 | 363.523 | 0 |
| Cannon_R2_Quoin | Cannon_R2 | -1145.728 | 312.74 | 316.568 | 77 |
| Cannon_R2_Wheel_BL | Cannon_R2 | -1093.763 | 339.74 | 303.269 | 196 |
| Cannon_R2_Wheel_BR | Cannon_R2 | -1198.661 | 339.74 | 307.889 | 196 |
| Cannon_R2_Wheel_FL | Cannon_R2 | -1093.763 | 442.74 | 303.269 | 196 |
| Cannon_R2_Wheel_FR | Cannon_R2 | -1198.661 | 442.74 | 307.889 | 196 |
| ChainFwd | Hull | 2654.474 | 294.578 | 431.995 | 48 |
| ChainFwd_End | ChainFwd | 2146.412 | 335.334 | 296.082 | 0 |
| Helm | Hull | -650.0 | 0.0 | 260.48 | 1268 |
| Helm_Wheel | Helm | -713.0 | 0.0 | 425.48 | 2016 |
| PilotSeat | Hull | -843.0 | 0.0 | 268.95 | 0 |
| Rudder | Hull | -1636.4 | 0.0 | 70.0 | 54 |
| SearchLight_AftL | Hull | 1120.0 | -280.0 | 655.0 | 12 |
| SearchLight_AftL_Head | SearchLight_AftL | 1120.0 | -280.0 | 970.0 | 40 |
| SearchLight_FwdC | Hull | 3040.0 | -90.0 | 735.0 | 12 |
| SearchLight_FwdC_Head | SearchLight_FwdC | 3040.0 | -90.0 | 1050.0 | 40 |
| SearchLight_MidL | Hull | 2460.0 | -240.0 | 735.0 | 12 |
| SearchLight_MidL_Head | SearchLight_MidL | 2460.0 | -240.0 | 970.0 | 40 |
| SearchLight_MidR | Hull | 2460.0 | 240.0 | 735.0 | 12 |
| SearchLight_MidR_Head | SearchLight_MidR | 2460.0 | 240.0 | 970.0 | 40 |
| Thruster_FL | Hull | 383.303 | -465.572 | -93.381 | 1276 |
| Thruster_FL_Nozzle | Thruster_FL | 349.901 | -465.572 | -371.045 | 408 |
| Thruster_FL_Flame | Thruster_FL_Nozzle | 322.762 | -465.572 | -564.147 | 0 |
| Thruster_FL_Petal00 | Thruster_FL_Nozzle | 469.643 | -465.572 | -539.348 | 8 |
| Thruster_FL_Petal01 | Thruster_FL_Nozzle | 450.804 | -394.572 | -536.7 | 8 |
| Thruster_FL_Petal02 | Thruster_FL_Nozzle | 399.334 | -342.596 | -529.466 | 8 |
| Thruster_FL_Petal03 | Thruster_FL_Nozzle | 329.025 | -323.572 | -519.585 | 8 |
| Thruster_FL_Petal04 | Thruster_FL_Nozzle | 258.716 | -342.596 | -509.704 | 8 |
| Thruster_FL_Petal05 | Thruster_FL_Nozzle | 207.246 | -394.572 | -502.47 | 8 |
| Thruster_FL_Petal06 | Thruster_FL_Nozzle | 188.407 | -465.572 | -499.823 | 8 |
| Thruster_FL_Petal07 | Thruster_FL_Nozzle | 207.246 | -536.572 | -502.47 | 8 |
| Thruster_FL_Petal08 | Thruster_FL_Nozzle | 258.716 | -588.547 | -509.704 | 8 |
| Thruster_FL_Petal09 | Thruster_FL_Nozzle | 329.025 | -607.572 | -519.585 | 8 |
| Thruster_FL_Petal10 | Thruster_FL_Nozzle | 399.334 | -588.547 | -529.466 | 8 |
| Thruster_FL_Petal11 | Thruster_FL_Nozzle | 450.804 | -536.572 | -536.7 | 8 |
| Thruster_FR | Hull | 383.303 | 491.791 | -112.989 | 1276 |
| Thruster_FR_Nozzle | Thruster_FR | 349.901 | 491.791 | -390.653 | 408 |
| Thruster_FR_Flame | Thruster_FR_Nozzle | 322.762 | 491.791 | -583.756 | 0 |
| Thruster_FR_Petal00 | Thruster_FR_Nozzle | 469.643 | 491.791 | -558.956 | 8 |
| Thruster_FR_Petal01 | Thruster_FR_Nozzle | 450.804 | 562.791 | -556.308 | 8 |
| Thruster_FR_Petal02 | Thruster_FR_Nozzle | 399.334 | 614.767 | -549.075 | 8 |
| Thruster_FR_Petal03 | Thruster_FR_Nozzle | 329.025 | 633.791 | -539.194 | 8 |
| Thruster_FR_Petal04 | Thruster_FR_Nozzle | 258.716 | 614.767 | -529.312 | 8 |
| Thruster_FR_Petal05 | Thruster_FR_Nozzle | 207.246 | 562.791 | -522.079 | 8 |
| Thruster_FR_Petal06 | Thruster_FR_Nozzle | 188.407 | 491.791 | -519.431 | 8 |
| Thruster_FR_Petal07 | Thruster_FR_Nozzle | 207.246 | 420.791 | -522.079 | 8 |
| Thruster_FR_Petal08 | Thruster_FR_Nozzle | 258.716 | 368.815 | -529.312 | 8 |
| Thruster_FR_Petal09 | Thruster_FR_Nozzle | 329.025 | 349.791 | -539.194 | 8 |
| Thruster_FR_Petal10 | Thruster_FR_Nozzle | 399.334 | 368.815 | -549.075 | 8 |
| Thruster_FR_Petal11 | Thruster_FR_Nozzle | 450.804 | 420.791 | -556.308 | 8 |
| Thruster_RL | Hull | -716.697 | -513.032 | -120.362 | 1276 |
| Thruster_RL_Nozzle | Thruster_RL | -750.099 | -513.032 | -398.027 | 408 |
| Thruster_RL_Flame | Thruster_RL_Nozzle | -777.238 | -513.032 | -591.129 | 0 |
| Thruster_RL_Petal00 | Thruster_RL_Nozzle | -630.357 | -513.032 | -566.329 | 8 |
| Thruster_RL_Petal01 | Thruster_RL_Nozzle | -649.196 | -442.032 | -563.682 | 8 |
| Thruster_RL_Petal02 | Thruster_RL_Nozzle | -700.666 | -390.057 | -556.448 | 8 |
| Thruster_RL_Petal03 | Thruster_RL_Nozzle | -770.975 | -371.032 | -546.567 | 8 |
| Thruster_RL_Petal04 | Thruster_RL_Nozzle | -841.284 | -390.057 | -536.686 | 8 |
| Thruster_RL_Petal05 | Thruster_RL_Nozzle | -892.754 | -442.032 | -529.452 | 8 |
| Thruster_RL_Petal06 | Thruster_RL_Nozzle | -911.593 | -513.032 | -526.804 | 8 |
| Thruster_RL_Petal07 | Thruster_RL_Nozzle | -892.754 | -584.032 | -529.452 | 8 |
| Thruster_RL_Petal08 | Thruster_RL_Nozzle | -841.284 | -636.008 | -536.686 | 8 |
| Thruster_RL_Petal09 | Thruster_RL_Nozzle | -770.975 | -655.032 | -546.567 | 8 |
| Thruster_RL_Petal10 | Thruster_RL_Nozzle | -700.666 | -636.008 | -556.448 | 8 |
| Thruster_RL_Petal11 | Thruster_RL_Nozzle | -649.196 | -584.032 | -563.682 | 8 |
| Thruster_RR | Hull | -716.697 | 576.756 | -123.902 | 1276 |
| Thruster_RR_Nozzle | Thruster_RR | -750.099 | 576.756 | -401.567 | 408 |
| Thruster_RR_Flame | Thruster_RR_Nozzle | -777.238 | 576.756 | -594.669 | 0 |
| Thruster_RR_Petal00 | Thruster_RR_Nozzle | -630.357 | 576.756 | -569.87 | 8 |
| Thruster_RR_Petal01 | Thruster_RR_Nozzle | -649.196 | 647.756 | -567.222 | 8 |
| Thruster_RR_Petal02 | Thruster_RR_Nozzle | -700.666 | 699.731 | -559.988 | 8 |
| Thruster_RR_Petal03 | Thruster_RR_Nozzle | -770.975 | 718.756 | -550.107 | 8 |
| Thruster_RR_Petal04 | Thruster_RR_Nozzle | -841.284 | 699.731 | -540.226 | 8 |
| Thruster_RR_Petal05 | Thruster_RR_Nozzle | -892.754 | 647.756 | -532.992 | 8 |
| Thruster_RR_Petal06 | Thruster_RR_Nozzle | -911.593 | 576.756 | -530.344 | 8 |
| Thruster_RR_Petal07 | Thruster_RR_Nozzle | -892.754 | 505.756 | -532.992 | 8 |
| Thruster_RR_Petal08 | Thruster_RR_Nozzle | -841.284 | 453.78 | -540.226 | 8 |
| Thruster_RR_Petal09 | Thruster_RR_Nozzle | -770.975 | 434.756 | -550.107 | 8 |
| Thruster_RR_Petal10 | Thruster_RR_Nozzle | -700.666 | 453.78 | -559.988 | 8 |
| Thruster_RR_Petal11 | Thruster_RR_Nozzle | -649.196 | 505.756 | -567.222 | 8 |
| Turbine_L | Hull | -1720.0 | -535.0 | 140.0 | 1014 |
| Turbine_L_Exhaust | Turbine_L | -1875.8 | -760.0 | 140.0 | 0 |
| Turbine_L_Rod | Turbine_L | -1720.0 | -760.0 | -212.6 | 8 |
| Turbine_L_Rotor | Turbine_L | -1720.0 | -760.0 | 140.0 | 336 |
| Turbine_R | Hull | -1720.0 | 535.0 | 140.0 | 1014 |
| Turbine_R_Exhaust | Turbine_R | -1875.8 | 760.0 | 140.0 | 0 |
| Turbine_R_Rod | Turbine_R | -1720.0 | 760.0 | -212.6 | 8 |
| Turbine_R_Rotor | Turbine_R | -1720.0 | 760.0 | 140.0 | 336 |
| Winch_Aft | Hull | 2830.0 | 0.0 | 500.0 | 84 |
| Winch_Fwd | Hull | 3040.0 | 0.0 | 500.0 | 84 |
