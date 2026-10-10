# CR_Mech swing section

Status: findings from the committed CR_Mech (git, before the 13:54 local save) plus a preliminary design. A reviewed spec will replace the design part. The live 13:54 graph is the truth: check every node name below against it before building.

## What the committed graph looks like

All of this is read from the asset's RigVM model (nodes, pins and links parsed from the uasset).

### Construction Event

1. Spawn Physics Solver, owner Bone `root0`.
   - SimulationSpace Component, Gravity (0,0,-981), FixedTimeStep 0.02.
   - Inertial forces 1.
   - TeleportDetection on: position change > 100, orientation change > 30°.
2. `Sequence_4.A` runs Instantiate From Physics Asset `SKM_Mech_Physics`.
   - Joints on and drives off.
   - Sim Space and Parent Space controls on, at strength 1 with damping ratio 1, using skeletal animation.
   - `Sequence_4.B` is free.
3. The key arrays are stored in variables: `PhysicsBodyComponentKeys`, `SimSpaceControlComponentKeys` and `ParentSpaceControlComponentKeys`.
4. Every body is set Simulated, then `root0` is set Kinematic, then `chest` is set Kinematic.

The body key format is `(ElementKey=(Type=Bone,Name=<bone>),Name="PhysicsBody")`. The solver key is `(Bone root0, "PhysicsSolver")`.

### Forwards Solve

Forwards Solve runs one Sequence, `RigVMFunction_Sequence_2`, with pins A to E in order:

- **A, beam / flying.** `Branch_7(bIsBeaming)` sets the chest pose. Otherwise `Branch_8(bIsFlying AND bIsBoosting)` aims the limbs and runs Step (alpha 0.2). Otherwise `Sequence_5` does two things:
  - "RotateChestAndChildrenToAim" (`Set Transform_1`). This runs every frame, so it would also run during a swing.
  - `Branch_9(bIsFlying)` runs Step (alpha 0.4).
- **B, shooting arm IK.** Shoulder aim (`Set Transform_5`) and Basic FABRIK on RA/LA_point_1..5, gated by bIsShooting.
- **C, shooting recoil.** Chest noise and the RA/LA_point_4 barrel spin, gated by bIsShooting.
- **D, GA_Beam hit.** While `Clamp(TimeStamp + Duration - ServerTime, 0, 1) > 0.1`, it sets chest Simulated, runs Add Force (BoneName), runs Step (alpha = clamp) and then Remove Force. Nothing sets chest back to Kinematic. The `_8` "chest Kinematic" node exists but isn't connected.
- **E, feet.** Foot-lock traces, then Full Body IK `PBIK_2`, which is ungated and rooted at pelvis. It runs after every physics step.

Neither existing physics section changes control strengths. The flying section never changes movement types; it only steps the solver.

### Skeleton

```
root0
└ pelvis
  ├ chest
  │ ├ head0 ─ head1
  │ ├ LA_point_0 … LA_point_5
  │ └ RA_point_0 … RA_point_5
  ├ LF_point_0 … LF_point_4
  └ RF_point_0 … RF_point_4
```

- Every bone's length axis is local +Z, and all child offsets are (0,0,L).
- The right arm runs from RA_point_0 (shoulder, at about (-1.6, 44.2, 121.1) in rig space) to RA_point_4, which is 105 cm away along the chain. RA_point_4 is the hand/grip and RA_point_5 is the tip.
- +Y is right and +Z is up.
- The bodies come from `SKM_Mech_Physics`. That asset isn't readable from here, so which bones have bodies and joints still has to be checked in the editor.

### Variables and the ABP

- The CR input variables are public bools and values: bIsFlying, bIsBeaming, bIsBoosting, PhysicsStateSetTimeStamp and so on.
- The ABP_MyCharMech Control Rig node binds 16 of them as custom-property pins.
- No swing variable exists yet.

## Preliminary design

1. **Variable.** Add a public bool `bIsSwinging` ("Is Swinging") to CR_Mech. Bind it on the ABP_MyCharMech Control Rig node to the anim instance's `bIsSwinging`, the same way Is Flying is bound.
2. **Placement.** Put `Branch(bIsSwinging)` directly after Forwards Solve.
   - True runs the new swing sequence.
   - False runs the existing `Sequence_2` unchanged.
   - This skips everything that would fight the hang: the chest aim in A, the arm IK in B, the recoil in C, the second Step in D, and the feet IK and PBIK in E.
3. **Swing start.** Edge-detect with a private `bWasSwinging`. On the rising edge:
   - Set `chest` Simulated.
   - Set the right hand body (`RA_point_4`, or the nearest right-arm bone that has a body) Kinematic.
   - Lower the Sim Space controls to about 0 strength so the body stops springing back to the animated pose. Keep the Parent Space controls weak, about 0.2 to 0.3, so the limbs keep their shape.
4. **Every swing frame:**
   - a. Write the right arm straight up. Aim `RA_point_0` +Z at world up (or at a fixed rig-space point above the shoulder), and set `RA_point_1..4` to identity local rotation so the hand ends about 105 cm above the shoulder. The kinematic hand body follows this pose.
   - b. Run one Step Physics Solver (`root0/PhysicsSolver`, alpha 1). The rest of the body hangs from the hand under gravity and lags the capsule's swing through the inertial forces.
   - c. Write nothing on simulated bones after the Step.
5. **Swing end.** On the falling edge:
   - Set `chest` back to Kinematic and the hand back to Simulated.
   - Restore both control arrays to strength 1 / damping 1, the construction values.
   - Optionally reset the solver so it doesn't pop.

## Check in the editor before building

- Is there a joint from `root0` to `pelvis` in `SKM_Mech_Physics`? root0 is Kinematic, so such a joint would pin the pelvis to the feet and stop the body hanging. If it exists, disable that joint or make root0 Simulated during the swing.
- Which right-arm bones have bodies? This decides which one to make Kinematic.
- When the chest is written back, do its children move with it? If they do, re-set the hand's global transform after the Step, or IK the arm from the chest to the fixed hand point.
- Teleport detection at 100 cm per frame can reset the sim during fast swings at a low frame rate. Watch for pops.
- The beam-hit section leaves chest Simulated until the rig reinitializes. The swing end setting chest Kinematic also fixes that state.
