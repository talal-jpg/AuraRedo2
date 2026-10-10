> **Status:** this is the reviewed reference design. What is built in CR_Mech (local commit ff14587 on Talal's PC, nodes named Swing_*) is the simpler version:
> - a Branch(bIsSwinging) at the start of Forwards Solve;
> - only RA_point_4 (and RA_point_1) Kinematic, with the hand placed 105 cm above the shoulder;
> - Sim Space controls 0 and Parent Space 0.25;
> - teleport threshold 600, LinearEulerAmount 0.6 and an acceleration clamp of 3500, all restored on exit.
> Use this spec to fix whatever PIE shows, in particular: the shoulder joint limits (V4), the staged entry and exit (D2, D8), the release hold for chained arcs (D8) and the whole-arm kinematic (D1).

# CR_Mech swing section ("SwingHang"): final implementation spec

**Audience:** an editor session with Unreal MCP access, or Talal building it by hand.

**Scope:**
- the new swing section in `/Game/Assets/Characters/Mech/CR_Mech`;
- the new CR variables and their wiring in `ABP_MyCharMech`;
- two small edits to existing CR nodes;
- the C++ steps Talal said he would do in `GA_GrappleSwing2`, plus one optional anim-instance addition.

**Labels:**
- **[F: source]** a fact read from the provided files.
- **[DOC]** stated in Epic's docs (taken from the API findings).
- **[REV]** a fact from a reviewer's own parse that I did not re-check.
- **[INF]** my inference.
- **[V#]** must be checked in the editor first (§3).

**Paths:**
- `nodes.txt`, `arm/…` and `physx/…` are under `…/scratchpad/assets/wf/`.
- C++ paths are under `…/scratchpad/wt4/Source/Aura/`.
- "cpp" means `Private/AbilitySystem/Abilities/GA_GrappleSwing2.cpp` and "h" means `Public/AbilitySystem/Abilities/GA_GrappleSwing2.h`.

---

## 0. What gets built

1. **CR inputs** (public, bound on the ABP's Control Rig node like `bIsFlying`):
   - **Required:** `bIsSwinging`.
   - **Recommended:** `SwingVelocity` (fed from the existing `UMyAnimInstance::Velocity`) and `bIsOnGround`.
   - **Optional:** `SwingAnchor` and `bHasSwingAnchor`. These need the small anim-instance addition in §4.2. Without them the arm points straight up, which is still a working result.
2. **CR state** (private): `ArmAlpha`, `PhysAlpha`, `SwingOffTime`, `bSwingWanted`, `bSwingActive`, `bHangConfig`, `bBodiesSwing`, `SwingAimDir`. The Construction Event resets all of them.
3. **Placement:** a new Forwards Solve pin **F** on `RigVMFunction_Sequence_2`. It runs last, after feet IK and PBIK, inside a comment box "SwingHang".
4. **Swing start, in stages:**
   - The right arm swings out to the side and then overhead over 0.2 s. Physics passes the pose through unchanged (Step Alpha 0) during this.
   - Then the physics hang begins:
     - the **whole right arm (RA_point_0..5) becomes Kinematic**;
     - **chest becomes Simulated** (it is Kinematic from construction);
     - Sim Space controls switch off;
     - Parent Space controls go to hang strengths;
     - solver Space Motion and Teleport Detection get swing values.
   - Step Alpha then ramps 0 → 1 over 0.2 s.
   - The body hangs from the right shoulder joint under the raised arm.
5. **While hanging:**
   - Exactly one Step Physics Solver per frame.
   - The swing's extra gravity (×1.3 to ×2.0) is compensated, so the body hangs along the rope rather than sideways.
   - Acceleration spikes are clamped.
6. **Swing end, in stages:**
   - A hold of up to 0.45 s bridges auto-chained arcs. It is skipped when hovering or on the ground.
   - Controls and solver settings are restored once.
   - Physics fades out over 0.17 s with the arm still up.
   - Then the arm bodies go back to Simulated and chest goes back to Kinematic, once.
   - Finally the arm lowers over 0.2 s along the reverse path.
7. **Existing nodes:**
   - The three existing Step nodes get a "not while swinging" gate, so the solver is never stepped twice in one frame.
   - The four chest-writing Set Transforms fade out while the arm is up.
   - Beam-hit forces still reach the hanging body, through the swing's own Step.

---

## 1. Evidence baseline

| # | Fact | Source |
|---|---|---|
| E1 | **C++ for the tag and bool is done.** Tag `Event.Swing` exists. `UMyAnimInstance::bIsSwinging` is `UPROPERTY(BlueprintReadOnly)`, set from the tag count and re-read on ASC init. `Velocity` is also BlueprintReadOnly, set from `MovementComponent->Velocity`. | [F: Public/AbilitySystem/Data/MyGameplayTags.h:78; Private/AbilitySystem/Data/MyGameplayTags.cpp:82; Public/MyAnimInstance.h:71,110; Private/MyAnimInstance.cpp:27,142-145,162-164] |
| E2 | **Swing and flying are normally exclusive.** The swing can only activate while `IsFalling()`. `bIsFlying` is true only in MOVE_Flying. | [F: cpp:917; Private/MyAnimInstance.cpp:89-96] |
| E3 | Forwards Solve → `RigVMFunction_Sequence_2` is a RigVMAggregateNode with pins A..E. Its contained graph runs them in order A→E. | [F: nodes.txt:2357, 4701-4740] |
| E4 | **A (flying).** `Branch_7(bIsBeaming)`:<br>• True: `RigUnit_SetTransform`, then `Set Transform_7` (both on chest, Global).<br>• False: `Branch_8(And(bIsFlying, bIsBoosting))`. Its True path is For_Each_11, with `For_Each_11.Completed → StepPhysicsSolver1_1` (Alpha 0.2). Its False path is Sequence_5: A = `Set Transform_1` (chest and children, Local); B = `Branch_9(VariableNode_27 bIsFlying).True → StepPhysicsSolver1_2` (Alpha 0.4). | [F: nodes.txt:2767, 2972-2980, 3087-3093, 3377, 3735, 3760] |
| E5 | **B (shooting).** `Branch_4(bIsShooting)` → shoulder aim `Set Transform_5` on RA/LA_point_0, then Basic FABRIK on RA/LA_point_1..5. | [F: nodes.txt:1894; arm/fwd_outline.txt] |
| E6 | **D (beam hit).** `Branch_10(Greater(Clamp_2, 0.1))`. True → `SetMovementType_7` chest Simulated → `HierarchyAddPhysicsBodyForce` (bone = BoneName variable) → `StepPhysicsSolver1` (Alpha ← Clamp_2, a double → float link) → `HierarchyRemovePhysicsBodyForce`. Nothing ever restores chest to Kinematic. | [F: nodes.txt:4017-4085] |
| E7 | **E (feet).** Foot-lock traces (`Branch_5`/`_6`), then `PBIK_2`, which is ungated. Foot lock is never on at runtime: `SetFootLockLoc()` is commented out, and the ABP's bFootLock vars default to false with no setter. The CR CDO defaults both to True, so they are on in the CR preview only. | [F: Private/Character/MyCharPlayer.cpp:94; REV: wf/integ/abpbp.py; F: physx/model.txt, CDO export 375] |
| E8 | **Construction.**<br>• SpawnPhysicsSolver → Sequence_4.A → Instantiate From Physics Asset (SKM_Mech_Physics).<br>• Instantiate settings: BonesToUse empty, ConstraintProfileName None, joints on, Sim and Parent Space controls on.<br>• Then: every body Simulated → root0 Kinematic → chest Kinematic.<br>• `Sequence_4.B` is unconnected.<br>• ParentSpaceControlData: bEnabled T, LinStr 1, LinDR 1, LinXD 0, MaxF 0, AngStr 1, AngDR 1, AngXD 1, MaxT 0, TVM 1/1, CCP 0/off, bUseSkeletalAnimation T, bDisableCollision **T**, bOnlyControlChildObject F, bUseAccelerationDriveMode T.<br>• SimSpaceControlData is the same except bDisableCollision F. | [F: nodes.txt:1207-1270] |
| E9 | **Solver (SpawnPhysicsSolver pins).**<br>• Owner root0. SimulationSpace Component. Gravity Z **-981**. Every bResetFrom* is False and EvaluationIntervalThresholdForReset is 0.<br>• `TeleportDetection`: all four checks on; PositionChange 100, Orientation 30, LinearAcceleration 1e5, AngularAcceleration 1e5.<br>• `SpaceMotion`: VerticalMotionScale 1; all clamps False, each with max 10000; InertialForces Amount, LinearEuler, AngularEuler, Centrifugal and Coriolis all 1; Drag multipliers 1/1; external vectors 0. | [F: nodes.txt:1275-1360] |
| E10 | **Keys.** A body key is `(ElementKey=(Type=Bone,Name=X),Name="PhysicsBody")`; the solver key is `(Bone root0, "PhysicsSolver")`. A For_Each over control keys exposes `Element.ElementKey.Name`. | [F: nodes.txt:4037-4045, For_Each_17 block] |
| E11 | **Patterns the user already uses:**<br>• `For_Each_16.Element → SetMovementType_3.PhysicsBodyComponentKey.ElementKey` (an item-array loop that sets movement modes);<br>• `For_Each_2.Element.Name → Equals(FName)` + `Or` (a name filter);<br>• For_Each over control keys → Set Physics Control Enabled / Data And Multiplier (unreachable copies). | [F: nodes.txt:1709-1721, 2804, 2439-2500, 4193-4281] |
| E12 | **Right arm.** chest > RA_point_0 > 1 > 2 > 3 > 4 > 5. Right is +Y, up is +Z, and the mech faces +X.<br>Initial rig-space positions: RA_point_0 (-1.62, 44.20, 121.11); RA_point_4 (-10.3, 59.4, 46.1), 77.1 cm from RA_point_0; RA_point_5 (36.3, 71.3, 38.5).<br>RA_point_0 axes: X (0.13,-0.97,-0.21), Y (-0.87,-0.21,0.45), Z (-0.48,0.13,-0.87). | [F: arm/hierarchy.txt:57-71 (own Kraken decode, self-consistent)] |
| E13 | The user's own unreachable "hands kinematic" attempt uses [RA_point_4, RA_point_5, LA_point_4, LA_point_5]. | [F: nodes.txt:1709-1730] |
| E14 | **ABP.** The Control Rig node (GUID D5BA8D31921D408DA0D4D924E0F7359E) is fed by AnimGraph `Get <var>` nodes, e.g. `Get bIsFlying` → "Is Flying". The AnimGraph already reads `MovementComponent` (for Blend Poses by EMovementMode). | [F: abp_fib.txt:540-649, 596] |
| E15 | The mesh pivot pitches only while boosting AND flying, so during a swing rig +Z is world up. | [F: Private/Character/MyCharPlayer.cpp:395-414] |
| E16 | **Swing gravity.**<br>• `A = -Up·G·GravityScale`, where `G = -MoveComp.GetGravityZ()`, which already includes the CMC Gravity Scale.<br>• `GravityScale = Lerp(1.3, 2.0, SmoothStep(-100, 100, -Vz))`.<br>• These are EditDefaultsOnly tuning values, so the ability BP may override them.<br>• Speeds: SoftMax 3000 (drag 500 cm/s² there), HardMax 5000. MinRopeLength 400. | [F: cpp:235, 658-661; h:113-141] |
| E17 | **Swing timeline.**<br>• `StartSwing` applies the root motion source at cpp:1341 and starts the rope cue (Location = anchor) at cpp:1348-1357.<br>• The hook flies for 0.06-0.16 s (h:663-668). The source switches Travel → Swing on attach (cpp:244-266).<br>• `GetGrappleSwing2State` returns true only in Phase Swing (cpp:857-876) and "works on the owner and the server" (h:723-724).<br>• Auto-release at 50° (h:338). The held button re-fires next frame (cpp:1656-1660). An auto-chain waits for the apex (rise < 250, h:653). ChainWindow is 0.6 (h:657). | [F] |
| E18 | **The ability is active without a rope:**<br>• Searching: `bSearchWhileHeld`, h:649; cpp:982.<br>• Rejected: cpp:1277, 1452-1473.<br>• Spent: after Landed/JumpReleased/Timeout with the button held, cpp:1640-1655.<br>The class comment suggests a "grappling" tag in ActivationOwnedTags (h:556). | [F] |
| E19 | **Existing pin values.**<br>• The `Weight` pins on `RigUnit_SetTransform`, `Set Transform_7`, `Set Transform_1` and `Set Transform_3` are unlinked constants 1.0.<br>• Existing Step nodes have bTrackVelocitiesDuringPassThrough True and DeltaTimeOverride 0. | [F: nodes.txt:2767, 3735, 3760, 4289; 4037-4060] |
| E20 | An orphan `Get_Component`/`Set_Component` pair for the solver component exists. `Set_Component`'s defaults include **SimulationSpace World**, so do not reuse it. | [F: nodes.txt:2097, 2560] |

Note: "FlyBoostingCr" and "PhysicsForce" are comment boxes, not collapse nodes [F: arm/boxes.txt]. This spec therefore builds a comment-boxed section. Collapsing it afterwards is optional: it has one exec in and no outputs.

---

## 2. Design decisions

**D1. The whole right arm is Kinematic while hanging, and the body pivots at the right shoulder joint.**
- Reasons [INF]:
  - At the bottom of an arc the load on the bodies is 5-25 g (v²/L with v up to 3000-5000 and L ≥ 400, E16).
  - The arm controls run in acceleration mode at 1 Hz (E8), so they cannot hold an elbow bend under that load. A simulated arm would straighten and its joints would separate. That shows up as a stretched arm and shoulder, and the shoulder ends up about 28 cm low.
  - A rigid kinematic arm leaves a single load-bearing joint (chest–RA_point_0).
  - It also makes the rope-socket bone irrelevant for physics.
- Visually the body still hangs below the raised hand.
- A looser variant (only the hand kinematic) is listed in §12.

**D2. Arm pose: a rigid copy of the reference arm, rotated about a shoulder that is fixed in component space.**
- RA_point_1..5 are reset to their **initial** local transforms. Those reference bends sit inside the joint limits by definition.
- RA_point_0 is set in Global space to Aim Math applied to its **initial** global transform. Translation stays at the initial shoulder (-1.6, 44.2, 121.1).
- Chest edits, animation, aim and recoil therefore cannot move the kinematic arm.
- The raise follows a waypoint, because the shortest-path blend over about 170° is ill-defined [INF]:
  - start direction d0 = initial shoulder→hand ≈ (-0.11, 0.20, -0.97), about 172° from up;
  - waypoint w = (0, 1, 0), straight out to the right;
  - end direction d1.
- Both legs of the path are ≤ 101°, so neither blend is ambiguous.
- The Set Transform weight ramps to 1 over the first quarter of the raise, so there is no pop from the animated arm.

**D3. Aim direction d1.**
- With `bHasSwingAnchor`: the direction from the initial shoulder to `From World(SwingAnchor)`.
- Otherwise: (0, -0.196, 0.981), i.e. up and slightly toward the head.
- It is smoothed at a rate of 8/s and stored in `SwingAimDir`, so the switch from "up" to "anchor" at attach does not jerk the kinematic hand.
- Why the anchor matters [INF]: rope angles at attach and release reach 25-55° (auto-release at 50°, E17). With the arm fixed straight up, a body hanging along the rope would stick out about 0.8 m sideways from the capsule.

**D4. Gravity compensation.**
- [F] The capsule swings under s·g, with s = CMC Gravity Scale × Lerp(1.3, 2.0, …) (E16). The solver uses g = -981 with LinearEulerAmount 1 (E9). [DOC] LinearEuler is the −a_frame pseudo-force.
- [INF] In the capsule frame the bodies feel `a_eff = g − k·a_capsule`, where `a_capsule = s·g + T·u + drag + input`.
  - With k = 1 and s = 2 this leaves a +981 cm/s² upward term. At the arc ends the body would point sideways or even float above the hand.
  - With **k = 1/s** the gravity terms cancel exactly and `a_eff = −(T/s)·u`, which lies along the rope.
- The build computes:
  - t = Clamp(0.5 − 0.005·Vz, 0, 1)
  - s = (1.3 + 0.7·t) × CMCGravityScale
  - k = 1/s
- A linear ramp replaces SmoothStep; the error is about 3 %.
- If `SwingVelocity` is unbound, Vz = 0 and k = 0.606, which is the apex-exact compromise.
- **Without an anchor** (proxies, during the hold, or before §4.2 is done), k = 0.25. Because 0.25 < 1/s_max = 0.5, the upward term can never win, and the body hangs mostly straight down under the vertical arm.

**D5. Loads and spikes** (all [INF] from the reviews' arithmetic; tunables):
- **MaxLinearAcceleration clamp 4000 cm/s²** while hanging.
  - Arc-end accelerations are about 1200-1600 and stay exact.
  - Bottom-of-arc loads and the slack-catch or attach spikes (60000-90000 at 60 fps, below the teleport accel threshold of 1e5) are cut. Bodies then see at most about 3 g.
  - The mid-arc direction error is ≤ about 5°.
- **Teleport PositionChangeThreshold 600** while hanging. At 100 it trips every frame above 100 × fps cm/s (for example 3000 cm/s at 30 fps). Each trip zeroes the inertial input.
- **AngularEuler, Centrifugal and Coriolis 0.2** while hanging, so yaw turns of the mesh do not fling the off-axis body.

**D6. Controls while hanging:**
- **Sim Space controls: all disabled.** At 1 Hz with bUseSkeletalAnimation they pull every body back to its animated pose relative to the capsule, which is the "spring back" that prevents a hang.
- **Parent Space controls: LinearStrength 0.** [DOC] Joints already hold position. The root-most body's control has no parent body and is effectively a global control [DOC via review]; zeroing it frees that body.
- **AngularStrength, by the child bone of the control:**

  | Child bone of the control | AngularStrength | Why |
  |---|---|---|
  | `RA_point_0` (shoulder) | 0.25 | Free enough for the torso to tilt its centre of mass under the shoulder, but restores facing. The target is the *input-pose* relation (arm already raised), so it does not flip the chest. |
  | `pelvis` | 0 | Lets the legs and pelvis hang. |
  | `head0`, `head1` | 4 | The head sits above its pivot, an inverted pendulum. At 1 Hz it would fold. |
  | any other | 1 | The construction value; keeps limb posture. |

- AngularExtraDamping stays 1 everywhere.

**D7. root0.**
- [DOC via review] Helper bodies are made only when BonesToUse selects a subset, and BonesToUse is empty (E8). So root0 is either a real body or there is none.
- If none: the construction "root0 Kinematic" node does nothing, pelvis is the root-most body, and the pelvis 0-class (D6) frees it.
- If a root0 body exists **and** has a constraint to pelvis [V3]: the Kinematic root0 would pin the body at the feet. In that case set root0 Simulated while hanging, put root0 in the 0-class, and restore it on exit (§10.10).

**D8. Stages and rates** (dt is clamped to ≤ 0.05 s):
- `ArmAlpha` rises at 5/s while wanted.
- `PhysAlpha` rises at 5/s only once `ArmAlpha` = 1.
- On release, `PhysAlpha` falls at 6/s (15/s fast). `ArmAlpha` falls at 5/s (10/s fast), but only once `PhysAlpha` = 0.
- Because of the clamp, the raise always takes at least 4 frames of Alpha-0 pass-through steps. These warm the solver back up after a long time without steps (no reset flags are set, E9).
- "Wanted" is `bIsSwinging`, or a **hold** of up to 0.45 s after the tag drops while the section is active. The hold does not apply when flying or on the ground.
  - The hold bridges auto-chained arcs. The gap between arcs is roughly 0.3 s: the rise to the apex plus the search (E17) [INF].
  - "Fast" mode means flying or on the ground.

**D9. What is written every frame and what runs once.**
- **Every hanging frame** (idempotent):
  - movement modes;
  - both control loops;
  - Space Motion and Teleport Detection.
  - Doing this every frame also covers config changes that land on an Alpha-0 frame, which might otherwise not take effect, and a rig re-init.
- **Exactly once:**
  - leaving the hang restores controls, Space Motion and teleport;
  - reaching PhysAlpha 0 restores the movement modes.
- An every-frame "else Kinematic" would fight the beam section.

**D10. Placement and the single-Step rule.**
- F runs after E, so nothing writes the bones after the swing Step.
- The A and D Step nodes are gated by `NOT (bIsSwinging OR bSwingActive)`, where bSwingActive is last frame's value. The proof is in §9.

**D11. Priority.** The swing owns the solver. Beam forces still apply through the swing's single Step. The flying steps wait until the swing has fully ended.

---

## 3. Assumptions to verify in the editor (before building)

| ID | Check | How | If false |
|---|---|---|---|
| V1 | The live graph matches the decode:<br>• Sequence_2 accepts a new pin;<br>• `Sequence_4.B` is free;<br>• the links `For_Each_11.Completed→StepPhysicsSolver1_1`, `Branch_9.True→StepPhysicsSolver1_2` and `HierarchyAddPhysicsBodyForce→StepPhysicsSolver1` exist;<br>• the four Weight pins in E19 are unlinked. | Open CR_Mech and inspect. | Re-target §10.8 to the real nodes. |
| V2 | SKM_Mech_Physics has bodies on chest, pelvis, head0, head1 and **each of RA_point_0..5**. | Physics Asset Editor body list. | Remove missing bones from item arrays C2 and C25 (the setter warns on a missing body). If RA_point_0 has no body, use the first right-arm bone that has one in C10's shoulder test. |
| V2b | Every body except the root-most has a constraint to its parent body. | Physics Asset Editor constraint list. | §10.10: keep LinearStrength 1 on that body's parent-space control. |
| V3 | Does root0 have a body **and** a root0–pelvis constraint? | Physics Asset Editor. | If yes, apply §10.10 "root0". |
| V4 | **Critical.** The right shoulder constraint (chest–RA_point_0) allows the arm about 170° from its reference (overhead). | Physics Asset Editor → that constraint → Angular Limits. | **Ask Talal first.** Option (a): Swing1/Swing2 Motion = Free, Twist stays Limited, either on the default profile or on a new Constraint Profile named in `HierarchyInstantiateFromPhysicsAsset.ConstraintProfileName` (construction-only). Either way it applies to **all** CR physics, including flying and the beam hit; a profile only spares other users of the asset. Re-test flying and the beam after. Option (b), swing-only: needs `Instantiate.PhysicsJointComponentKeys` stored in construction (currently unlinked) plus a runtime joint-limit node whose runtime behaviour is undocumented. Test (b) before relying on it. |
| V5 | Which bone the rope socket is on. | SK_Mech sockets. | Visual only, since the whole arm is kinematic. Make sure it is on RA_point_4 or RA_point_5. |
| V6 | Keys in `ParentSpaceControlComponentKeys` have `ElementKey.Name` = the **child** body's bone, including the root-most global control. | Temporary `Print` of `Element.ElementKey.Name` in loop C8 in the preview. | If the names are the parent bone, shift each test in C10 to the matching parent. If the names are unusable, use one AngularStrength of 0.4 for all and drop C10. |
| V7 | These nodes exist in 5.8:<br>• Get Delta Time<br>• Get Relative Transform<br>• vector Unit, Interpolate, Subtract<br>• double Less, LessEqual, GreaterEqual, Clamp<br>• bool Not<br>• If (dispatch)<br>• **Set Physics Solver Space Motion**<br>• **Set Physics Solver Teleport Detection**<br>The last two are [DOC] only, not seen in the asset. | Node palette search. | Delta time: any node exposing the context delta. Space Motion missing: drop C11/C21 and instead loop over `PhysicsBodyComponentKeys` with Set Physics Body Gravity Multiplier = s while hanging and 1 on exit. That is exact along the rope, but loses the clamp and the angular reduction. Teleport node missing: drop C13/C22 and expect hitches at low fps. |
| V8 | The mesh is upright while swinging (rig +Z = world up). | E15. | Only the no-anchor "up" direction depends on it. |
| V9 | A Kinematic body follows its bone as set *before* the Step in the same Forwards Solve. | Turn on `VisualizationSettings.bShowBodies` on Sw_Step. | Apply fallback F-1 (§10.10). |
| V10 | Gravity values. | BP_MyCharPlayer → Character Movement → Gravity Scale; GA_GrappleSwing2 BP → Swing → GravityScaleAscending, GravityScaleDescending, GravityBlendSpeed. | Put the real numbers into C12: 1.3 → Asc; 0.7 → Desc − Asc; 0.005 → 1/(2·BlendSpeed); CMCGravityScale → the BP value. |
| V11 | The mech faces rig +X (the Secondary aim target). | E12; CR viewport. | Use the facing axis instead. |
| V12 | A variable GET placed after a SET in the same frame reads the new value. | In the preview, ArmAlpha should ramp 0→1 in about 0.2 s. | If blocks lag one frame it still works, but report it. |

---

## 4. Talal's C++ steps (GA_GrappleSwing2 / UMyAnimInstance)

### 4.1 Tag lifetime (required; Talal said he will add the tag)

1. **Turn the tag on** in `UGA_GrappleSwing2::StartSwing`, directly after `RootMotionSourceID=MoveComp->ApplyRootMotionSource(Src);` (cpp:1341):
   ```cpp
   if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
   {
       ASC->SetLooseGameplayTagCount(MyTags::Event_Swing,1);
   }
   ```
2. **Set the count back to 0** in three places:
   - `Poll`, inside `if (bOver)`, right after `RootMotionSourceID=GrappleSwing2::InvalidSourceID;` and before the `if (!bLocal)` split (about cpp:1615). This covers both the owner path and the server-for-remote path.
   - `OnServerRejected`, after the source is removed (about cpp:1465).
   - `EndAbility`, as a safety net.
3. Use `Set…Count`, not Add/Remove, so the count cannot drift.

Why these choices:
- **Hook launch, not attach.** The 0.2 s arm raise then overlaps the hook flight (0.06-0.16 s, E17). The hand is up when the rope catches, and the physics only starts after the raise.
- **Not ActivationOwnedTags.** The ability is active while searching, after a rejection, and while Spent with the button held (E18). The mech would hang from a raised hand on the ground.
- **Not a gameplay event.** `RegisterGameplayTagEvent` counts owned tags only (MyAnimInstance.cpp:162).

### 4.2 Anim-instance inputs (recommended, small)

```cpp
// MyAnimInstance.h, next to bIsSwinging
UPROPERTY(BlueprintReadOnly) FVector SwingAnchor=FVector::ZeroVector;
UPROPERTY(BlueprintReadOnly) bool bHasSwingAnchor=false;
UPROPERTY(BlueprintReadOnly) bool bIsOnGround=false;

// MyAnimInstance.cpp, NativeUpdateAnimation, after "Velocity=..." and BEFORE
// the early "if (!bIsShooting && !bIsBoosting)return;"
bIsOnGround=MovementComponent->IsMovingOnGround();
float RopeLength=0.f; bool bTaut=false;
bHasSwingAnchor=bIsSwinging && MyCharPlayer->IsLocallyControlled()
    && UGA_GrappleSwing2::GetGrappleSwing2State(MyCharPlayer,SwingAnchor,RopeLength,bTaut);
```
- Add `#include "AbilitySystem/Abilities/GA_GrappleSwing2.h"`.
- `GetGrappleSwing2State` is true only after attach (E17).
- `IsLocallyControlled` keeps other machines on the gentle no-anchor hang. Their mesh motion is replicated and smoothed, so inertial forces derived from it would be noise [INF].

Without §4.2:
- leave the three related CR pins unbound;
- the arm points straight up;
- landing uses the slower exit.

### 4.3 Multiplayer (decide later)

- Loose tags do not replicate. The ability runs only on the owner and the server (Local Predicted, h:551-553), so other players' copies never get `Event.Swing` and show no hang. They still see the rope cue.
- To show a hang on other screens: replicate the tag from the authority with the ASC's replicated-loose-tag API.
  - Verify the exact 5.8 name and replication-state enum in `AbilitySystemComponent.h`.
  - Make sure the owner's count cannot reach 2 or stick at 1.
- Those copies then get the no-anchor fallback hang.

---

## 5. Variables and ABP wiring

### 5.1 CR_Mech → My Blueprint → Variables (then Compile)

| Name | Type | Default | Visibility | Purpose |
|---|---|---|---|---|
| `bIsSwinging` | Boolean | false | **Public** (like bIsFlying) | Event.Swing present |
| `SwingVelocity` | Vector | (0,0,0) | Public | character velocity (world); only .Z is used |
| `bIsOnGround` | Boolean | false | Public | fast exit on landing |
| `SwingAnchor` | Vector | (0,0,0) | Public | rope anchor (world) |
| `bHasSwingAnchor` | Boolean | false | Public | anchor valid this frame |
| `ArmAlpha` | Float | 0 | Private (like the key arrays) | arm raise 0..1 |
| `PhysAlpha` | Float | 0 | Private | physics blend 0..1 |
| `SwingOffTime` | Float | 0 | Private | seconds since bIsSwinging went false |
| `bSwingWanted` | Boolean | false | Private | this frame's "swing wanted" |
| `bSwingActive` | Boolean | false | Private | section owned the solver last frame (ArmAlpha > 0) |
| `bHangConfig` | Boolean | false | Private | controls and solver are in hang settings |
| `bBodiesSwing` | Boolean | false | Private | movement modes are in hang settings |
| `SwingAimDir` | Vector | (0, -0.196, 0.981) | Private | smoothed aim direction |

### 5.2 ABP_MyCharMech (after CR_Mech is compiled and saved)

1. Select the **Control Rig** node (GUID D5BA8D31…).
2. In Details, tick the input pins **Is Swinging** and **Swing Velocity**. Also tick **Is On Ground**, **Swing Anchor** and **Has Swing Anchor** if §4.2 is done.
3. If the pins are missing: right-click the node → Refresh Node.
4. Turn on Show Inherited Variables. Wire `Get bIsSwinging` → Is Swinging and `Get Velocity` → Swing Velocity. With §4.2, also wire `Get bIsOnGround`, `Get SwingAnchor` and `Get bHasSwingAnchor` to their pins. This is the same pattern as `Get bIsFlying` → Is Flying (abp_fib.txt:596).
5. Compile and save.
6. Expected result: names such as `__CustomProperty_bIsSwinging_D5BA8D31921D408DA0D4D924E0F7359E`.

---

## 6. Placement and frame order

- **Forwards Solve:** Sequence_2 runs A (fly/beam), B (shoot arm IK), C (recoil), D (beam hit), E (feet / PBIK), then **F (SwingHang, new)**.
- **Inside F**, `Sw_Seq` runs:
  - A: timing and state;
  - B: arm pose;
  - C: physics configuration;
  - D: the single Step;
  - E: store state.
- **Location:** all new nodes go in the main Rig graph (`CR_Mech.RigVMModel`). The free area is below y ≈ 12300 (the lowest existing node is at y 12235, nodes.txt). Suggested: x −4500..7000, y 13600..17500.
- **Double math:** use the variants the user already uses (Add, Multiply, Clamp, Greater, as double). Double → float links are fine (precedent: Clamp_2 → Step Alpha).
- **GET nodes:** use separate, fresh GET nodes in each block. Do not route one block's values through another block's math nodes.

---

## 7. Behaviour timeline

| Phase | What happens |
|---|---|
| **Swing start (t = 0, tag on at hook launch)** | ArmAlpha rises 0→1 in 0.2 s.<br>• Arm path: from the animated arm, blended in over the first 0.05 s, to the reference direction; then out to the right (w); then to d1.<br>• Sw_Step runs at Alpha 0: pass-through, bodies track the pose.<br>• A/D steps are blocked. |
| **Attach (≈ 0.06–0.16 s)** | `bHasSwingAnchor` turns true (§4.2), and `SwingAimDir` eases from up to the anchor direction. |
| **Hang starts (ArmAlpha = 1)** | Every frame:<br>• RA_point_0..5 Kinematic, chest Simulated;<br>• Sim Space controls off;<br>• Parent Space controls at hang strengths;<br>• Space Motion: k, clamp, angular 0.2;<br>• Teleport threshold 600.<br>PhysAlpha ramps 0→1 in 0.2 s. |
| **Hanging** | One Step per frame at Alpha = PhysAlpha. Beam forces, if any, apply in this Step. |
| **Tag off** | Hold up to 0.45 s, skipped if flying or on the ground. If the tag returns inside the hold, nothing visible changes. |
| **Swing end, stage 1** | Once: Sim controls on, Parent controls back to construction values, Space Motion and teleport back to construction values. PhysAlpha falls 1→0 in 0.17 s (0.07 s fast). The arm bodies stay Kinematic at the raised pose, which does not move. |
| **Swing end, stage 2 (PhysAlpha = 0)** | Once: RA_point_0..5 Simulated, chest Kinematic. Then the arm lowers along the reverse path in 0.2 s (0.1 s fast) with Alpha-0 steps. |
| **Idle (ArmAlpha = 0)** | bSwingActive goes false. From the next frame on, the A/D steps run again. |
| **Re-attach mid-exit** | The stages resume from wherever they are. The hang config is re-applied as soon as ArmAlpha is 1. |

---

## 8. Existing nodes changed while swinging ("skipped nodes")

| Existing node | Change | Why |
|---|---|---|
| `StepPhysicsSolver1_1` (A, fly+boost) | **G1** gate in front of it | single Step per frame; the fly+boost pose path itself is unchanged |
| `StepPhysicsSolver1_2` (A, flying) | **G2** gate | same |
| `StepPhysicsSolver1` + `HierarchyRemovePhysicsBodyForce` (D) | **G3** gate after Add Force | the hit force still gets recorded and is applied by Sw_Step |
| `RigUnit_SetTransform`, `Set Transform_7` (beaming chest) | **W1, W2**: Weight ← 1 − ArmAlpha | chest posture targets stay clean while hanging |
| `Set Transform_1` (RotateChestAndChildrenToAim) | **W3**: Weight ← 1 − ArmAlpha | same; it would otherwise twist the torso toward the camera |
| `Set Transform_3` (recoil chest noise) | **W4**: Weight ← 1 − ArmAlpha | the noise would shake the hanging torso |
| B section (`Set Transform_5`, FABRIK) | unchanged | F overrides the whole right arm (RA_point_0 Global + RA_point_1..5 Local at weight 1). The left arm may still aim loosely while shooting. |
| `Set Transform_9` (barrel spin) | unchanged | RA_point_4 is reset by F; the LA spin is harmless |
| foot-lock Branch_5/6, `PBIK_2` | unchanged | foot lock is never on at runtime (E7); PBIK runs before F |

---

## 9. Interaction with the flying and beam-hit sections

**Single Step per frame between {A, D} and F (proof):**
- F steps only when ArmAlpha_new > 0. That requires one of:
  - (i) `bIsSwinging`;
  - (ii) the hold, which needs bSwingActive_prev;
  - (iii) a decaying ArmAlpha, so ArmAlpha_prev > 0 and therefore bSwingActive_prev.
- G1 to G3 block A's and D's Steps whenever `bIsSwinging OR bSwingActive_prev`.

**Beam hit while hanging:**
- D still runs: SetMovementType_7 sets chest Simulated (a no-op here), and Add Force records the force.
- Sw_Step applies the force to the hanging body. D3 removes any leftover record.
- After the swing, if the hit window is still open, D resumes the next frame. That is the existing behaviour, including the existing gap that chest is never restored to Kinematic.

**Flying:**
- Normally exclusive with swinging (E2).
- If hover starts during the hold or exit, the fast exit applies and A's flying Step resumes the frame after.

**Pre-existing and unchanged:** A and D can still both Step in one frame (flying + hit).

**Construction re-run mid-swing:** the K-nodes reset all state and the swing re-enters from the start.

---

## 10. Node-by-node build list

Notes:
- "GET X" and "SET X" are variable nodes.
- Labels such as `Sw_…` exist only in this spec; RigVM assigns its own names.
- Set Physics Body Movement Mode is `FRigUnit_HierarchySetPhysicsBodyMovementType`. Its key is `PhysicsBodyComponentKey` with `ElementKey=(Bone, X)` and `Name=PhysicsBody`.

### 10.1 Construction Event addition
Near `RigVMFunction_Sequence_4` (−8848, 1600), about y 3200. Link **`Sequence_4.B` → K1**, then chain by exec:

| Step | Node |
|---|---|
| K1 | SET ArmAlpha = 0 |
| K2 | SET PhysAlpha = 0 |
| K3 | SET SwingOffTime = 0 |
| K4 | SET bSwingWanted = false |
| K5 | SET bSwingActive = false |
| K6 | SET bHangConfig = false |
| K7 | SET bBodiesSwing = false |
| K8 | SET SwingAimDir = (0, −0.196, 0.981) |

Nothing else in construction changes.

### 10.2 Section F entry
- **F0:** add pin **F** on `RigVMFunction_Sequence_2` and link F → F1.
- **F1:** Reroute (exec) at about (−4464, 13700).
- **F2 `Sw_Seq`:** Sequence with pins **A, B, C, D, E** (add pins). ExecuteContext ← F1.
- Comments:
  - a label "SwingHang" left of F1;
  - a comment box "SwingHang" around all F nodes.

### 10.3 Block A: timing and state (`Sw_Seq.A`)

Pure nodes:

| ID | Expression |
|---|---|
| A1 `Sw_Dt` | Clamp(Get Delta Time, 0, 0.05) |
| A2 `Sw_OffNext` | If(GET bIsSwinging, 0.0, Clamp(GET SwingOffTime + A1, 0, 10)) |
| A3 `Sw_HoldOK` | And(GET bSwingActive, And(Less(GET SwingOffTime, **0.45**), Not(Or(GET bIsFlying, GET bIsOnGround)))) |
| A4 `Sw_Wanted` | Or(GET bIsSwinging, A3) |
| A5 `Sw_Fast` | Or(GET bIsFlying, GET bIsOnGround) |
| A6 `Sw_PhysRate` | If(A4, If(GreaterEqual(GET ArmAlpha, 1.0), **5.0**, 0.0), If(A5, **−15.0**, **−6.0**)) |
| A7 `Sw_ArmRate` | If(A4, **5.0**, If(LessEqual(GET PhysAlpha, 0.0), If(A5, **−10.0**, **−5.0**), 0.0)) |

Exec chain, in this order:
1. **A8** SET SwingOffTime ← A2. ExecuteContext ← `Sw_Seq.A`.
2. **A9** SET bSwingWanted ← A4.
3. **A10** SET PhysAlpha ← Clamp(GET PhysAlpha + A6 × A1, 0, 1).
4. **A11** SET ArmAlpha ← Clamp(GET ArmAlpha + A7 × A1, 0, 1).

Why the order is safe:
- PhysAlpha is set before ArmAlpha, so A6 always sees last frame's ArmAlpha.
- A7 may see the new or the old PhysAlpha; either is correct.
- bSwingActive is written only in Block E, so A3 always reads last frame's value.

### 10.4 Block B: arm pose (`Sw_Seq.B`)

**Gate**
- **B1** Branch. ExecuteContext ← `Sw_Seq.B`. Condition = Greater(GET ArmAlpha, 0.0).

**Constant geometry (pure)**

| ID | Node | Expected value (from E12) |
|---|---|---|
| B2 `Sw_ShoulderInit` | Get Transform: Bone RA_point_0, GlobalSpace, **bInitial true** | translation (−1.6, 44.2, 121.1) |
| B3 | Get Transform: RA_point_4, Global, initial | — |
| B4 `Sw_d0` | Unit(B3.Translation − B2.Translation) | ≈ (−0.11, 0.20, −0.97) |
| B5 | Get Relative Transform: Child RA_point_4 (bChildInitial true), Parent RA_point_0 (bParentInitial true) | — |
| B6 | Get Relative Transform: Child RA_point_5 (initial), Parent RA_point_0 (initial) | — |
| B7 `Sw_PrimaryAxis` | Unit(B5.RelativeTransform.Translation) | ≈ (0.00, −0.38, 0.93) |
| B8 `Sw_SecondaryAxis` | Unit(B6…Translation − B5…Translation) | ≈ (−0.08, −0.95, −0.29) |

**Aim direction (pure)**
- B9 `Sw_AnchorDir` = Unit(From World(GET SwingAnchor) − B2.Translation). From World is `FRigUnit_ToRigSpace_Location`, as used by `From World_8`.
- B10 `Sw_RawDir` = If(GET bHasSwingAnchor, B9, (0, −0.196, 0.981)).
- B11 `Sw_AimDirNext` = Unit(Interpolate(GET SwingAimDir, B10, Clamp(Sw_Dt × **8**, 0, 1))). Sw_Dt is a fresh copy of A1.

**Raise path (pure)**
- B12: t1 = Clamp(2 × GET ArmAlpha, 0, 1) and t2 = Clamp(2 × GET ArmAlpha − 1, 0, 1).
- B13 `Sw_P1` = Unit(Interpolate(B4, **(0, 1, 0)**, t1)).
- B14 `Sw_Dir` = Unit(Interpolate(B13, GET SwingAimDir, t2)).
- B15 `Sw_Aim`: Aim Math (`RigUnit_AimBoneMath`).
  - InputTransform ← B2.Transform.
  - Primary: Axis ← B7; Target ← B14; Kind Direction; Space (None, None); Weight 1.
  - Secondary: Axis ← B8; Target **(1, 0, 0)**; Kind Direction; Space (None, None); Weight 1.
  - Weight 1; Debug off.
- B16 `Sw_PoseW` = Clamp(4 × GET ArmAlpha, 0, 1).

**Exec chain**
1. B1.True → **B17** SET SwingAimDir ← B11.
2. → **B18** For Each over Item Array [Bone RA_point_1, RA_point_2, RA_point_3, RA_point_4, RA_point_5].
3. Loop body: **B19** Set Transform.
   - Item ← Element; LocalSpace; bInitial false.
   - Value ← Get Transform(Item ← Element, LocalSpace, **bInitial true**).Transform.
   - Weight ← B16; bPropagateToChildren **true**.
4. B18.Completed → **B20** Set Transform.
   - Bone **RA_point_0**; GlobalSpace; bInitial false.
   - Value ← B15.Result; Weight ← B16; bPropagateToChildren **true**.

### 10.5 Block C: physics configuration (`Sw_Seq.C`)

- **C1** `Sw_BranchHang`: Branch. ExecuteContext ← `Sw_Seq.C`. Condition = And(GET bSwingWanted, GreaterEqual(GET ArmAlpha, 1.0)).

**C1.True: hang (every frame)**
1. **C2** Item Array [RA_point_0, RA_point_1, RA_point_2, RA_point_3, RA_point_4, RA_point_5] (trim per V2). **C3** For Each over C2.
2. Loop body: **C4** Set Physics Body Movement Mode, `PhysicsBodyComponentKey.ElementKey ← Element`, Name PhysicsBody, **Kinematic**. This is the For_Each_16 / SetMovementType_3 pattern.
3. C3.Completed → **C5** Set Physics Body Movement Mode: chest, **Simulated**. (Add C5b here if V3 applies.)
4. → **C6** For Each over GET SimSpaceControlComponentKeys.
   - Loop body: **C7** Set Physics Control Enabled; key ← Element; **bEnabled false**.
5. C6.Completed → **C8** For Each over GET ParentSpaceControlComponentKeys.
   - Loop body: **C9** Set Physics Control Data And Multiplier; key ← Element; ControlData = **HANG** preset (§10.9) with `ControlData.AngularStrength ← C10`; Multiplier = ALL-1.
   - **C10** `Sw_AngStr` (pure). Let N = C8.Element.ElementKey.Name:
     - If(Equals(N, RA_point_0), **0.25**,
     - else If(Equals(N, pelvis), **0.0**,
     - else If(Or(Equals(N, head0), Equals(N, head1)), **4.0**,
     - else **1.0**))).
6. C8.Completed → **C11** Set Physics Solver Space Motion: solver (Bone root0, PhysicsSolver); values **HANG** (§10.9); `InertialForces.LinearEulerAmount ← C12`.
   - **C12** `Sw_LinEuler` (pure):
     - t = Clamp(0.5 − 0.005 × GET SwingVelocity.Z, 0, 1)
     - s = (1.3 + 0.7 × t) × **1.0** (CMCGravityScale; see V10)
     - kAnchor = 1 / s
     - **C12** = If(GET bHasSwingAnchor, kAnchor, **0.25**)
7. → **C13** Set Physics Solver Teleport Detection: same solver; values **HANG** (§10.9).
8. → **C14** SET bHangConfig = true → **C15** SET bBodiesSwing = true.

**C1.False: restores (each runs once)**
- **C16** `Sw_BranchLeaveHang`: ExecuteContext ← C1.False; Condition GET bHangConfig. On True:
  1. **C17** For Each over GET SimSpaceControlComponentKeys → body **C18** Set Physics Control Enabled, bEnabled **true**.
  2. C17.Completed → **C19** For Each over GET ParentSpaceControlComponentKeys → body **C20** Set Physics Control Data And Multiplier, ControlData = **CONSTRUCTION**, Multiplier ALL-1.
  3. C19.Completed → **C21** Set Physics Solver Space Motion = **CONSTRUCTION**.
  4. → **C22** Set Physics Solver Teleport Detection = **CONSTRUCTION**.
  5. → **C23** SET bHangConfig = false.
- **C24** `Sw_BranchLeaveBodies`: ExecuteContext ← **C16.Completed**; Condition And(GET bBodiesSwing, LessEqual(GET PhysAlpha, 0.0)). On True:
  1. **C25** For Each over the same item array as C2 → body **C26** Set Physics Body Movement Mode, ElementKey ← Element, **Simulated**.
  2. C25.Completed → **C27** chest **Kinematic**. (Add C27b here if V3 applies.)
  3. → **C28** SET bBodiesSwing = false.

### 10.6 Block D: the single Step (`Sw_Seq.D`)
1. **D1** Branch. ExecuteContext ← `Sw_Seq.D`. Condition = Greater(GET ArmAlpha, 0.0). (PhysAlpha > 0 always implies ArmAlpha = 1.)
2. D1.True → **D2** `Sw_Step`: Step Physics Solver (`RigUnit_StepPhysicsSolver1`).
   - PhysicsSolverComponentKey = (Bone root0, PhysicsSolver).
   - DeltaTimeOverride 0; SimulationSpaceDeltaTimeOverride 0.
   - **Alpha ← GET PhysAlpha**.
   - bTrackVelocitiesDuringPassThrough **true**.
   - VisualizationSettings as on StepPhysicsSolver1. Set bShowBodies and bShowJoints true while testing, false afterwards.
3. → **D3** Remove Force: copy and paste `HierarchyRemovePhysicsBodyForce` and link its `PhysicsBodyComponentKey.ElementKey.Name ← GET BoneName`. It clears any beam force record left from D.

### 10.7 Block E: store state (`Sw_Seq.E`)
1. **E1** SET bSwingActive ← Greater(GET ArmAlpha, 0.0).
2. → **E2** SET SwingAimDir ← If(Greater(GET ArmAlpha, 0.0), GET SwingAimDir, (0, −0.196, 0.981)).

### 10.8 Gate and fade edits on existing nodes

**Step gates.** Build `NotSwingBlock` = Not(Or(GET bIsSwinging, GET bSwingActive)). Make one copy near (300, 6200) for A and one near (−500, 9100) for D.

| Gate | Remove link | Add |
|---|---|---|
| **G1** | `For_Each_11.Completed → StepPhysicsSolver1_1.ExecutePin` | Branch (Condition ← NotSwingBlock). `For_Each_11.Completed` → Branch.ExecuteContext; Branch.True → StepPhysicsSolver1_1. Leave `Branch_8.Condition` alone. |
| **G2** | `RigVMFunction_ControlFlowBranch_9.True → StepPhysicsSolver1_2.ExecutePin` | Branch (NotSwingBlock). Branch_9.True → Branch; Branch.True → StepPhysicsSolver1_2. |
| **G3** | `HierarchyAddPhysicsBodyForce → StepPhysicsSolver1.ExecutePin` | Branch (NotSwingBlock). Add Force → Branch; Branch.True → StepPhysicsSolver1, which still chains to Remove Force. Leave `Branch_10.Condition` and `Greater → Print_5 / If_1` alone. |

In every gate, Branch.False stays unconnected.

**Pose fades.** Build `SwingInv` = Subtract(1.0, GET ArmAlpha), one copy per area, and link it to:
- **W1:** `RigUnit_SetTransform.Weight`
- **W2:** `Set Transform_7.Weight`
- **W3:** `Set Transform_1.Weight`
- **W4:** `Set Transform_3.Weight`

All four are currently 1.0 (E19). These run before F, so they read last frame's ArmAlpha, which is fine.

### 10.9 Presets

**Parent Space ControlData:**

| Field | HANG (C9) | CONSTRUCTION (C20) = Instantiate ParentSpaceControlData |
|---|---|---|
| bEnabled | True | True |
| LinearStrength | **0** | 1 |
| LinearDampingRatio / LinearExtraDamping / MaxForce | 1 / 0 / 0 | 1 / 0 / 0 |
| AngularStrength | **← C10** | 1 |
| AngularDampingRatio / AngularExtraDamping / MaxTorque | 1 / 1 / 0 | 1 / 1 / 0 |
| Linear / AngularTargetVelocityMultiplier | 1 / 1 | 1 / 1 |
| CustomControlPoint / bUseCustomControlPoint | 0,0,0 / False | same |
| bUseSkeletalAnimation | True | True |
| bDisableCollision | True | True |
| bOnlyControlChildObject | False | False |
| bUseAccelerationDriveMode | True | True |

- **ALL-1 multiplier:** every Linear*Multiplier vector is (1,1,1) and every Angular*Multiplier scalar is 1. These are the values on the unreachable `HierarchySetControlDataAndMultiplier_1` (nodes.txt:4206).
- **Caution:** that node's AngularExtraDamping is 0, but construction uses 1. Use the table above, not a copy of that node.

**Space Motion:**

| Field | HANG (C11) | CONSTRUCTION (C21) = SpawnPhysicsSolver.SpaceMotion |
|---|---|---|
| VerticalMotionScale | 1 | 1 |
| bClampLinearVelocity / Max | False / 10000 | False / 10000 |
| bClampAngularVelocity / Max | False / 10000 | False / 10000 |
| bClampLinearAcceleration / MaxLinearAcceleration | **True / 4000** | False / 10000 |
| bClampAngularAcceleration / Max | False / 10000 | False / 10000 |
| InertialForces.Amount | 1 | 1 |
| InertialForces.LinearEulerAmount | **← C12** | 1 |
| AngularEuler / Centrifugal / Coriolis Amount | **0.2 / 0.2 / 0.2** | 1 / 1 / 1 |
| Drag: Linear/AngularDragMultiplier; External vectors | 1 / 1; all 0 | 1 / 1; all 0 |

**Teleport Detection:**

| Field | HANG (C13) | CONSTRUCTION (C22) |
|---|---|---|
| bFromPositionChange / PositionChangeThreshold | True / **600** | True / 100 |
| bFromOrientationChange / OrientationChangeThreshold | True / 30 | True / 30 |
| bFromLinearAcceleration / LinearAccelerationThreshold | True / 100000 | True / 100000 |
| bFromAngularAcceleration / AngularAccelerationThreshold | True / 100000 | True / 100000 |

### 10.10 Conditional changes (apply only if a check in §3 says so)

- **root0 (V3: root0 body with a root0–pelvis constraint):**
  - C5b: Set Movement Mode root0 **Simulated**, after C5.
  - C27b: root0 **Kinematic**, after C27.
  - Add `Equals(N, root0)` to the 0.0 branch of C10.
- **Missing bodies (V2):** trim C2 (C25 uses the same array). If RA_point_0 has no body, replace RA_point_0 in C10 with the first right-arm bone that has one.
- **Unconstrained bodies (V2b):** feed `ControlData.LinearStrength` of C9 from If(Equals(N, <unconstrained bone>), 1.0, 0.0). Chain more Equals/Or nodes for more bones.
- **Fallback F-1 (V9 fails, or the raised arm drifts or jitters with the chest after writeback):** after D3, add a Set Transform on RA_point_0, GlobalSpace, Value ← B15.Result, Weight ← B16, propagate true. It overrides only the arm, which is kinematic anyway.
- **Node availability (V7):** apply the fallbacks listed in the V7 row.

### 10.11 Tunables

| What | Where | Default | Effect |
|---|---|---|---|
| Release hold | A3 | 0.45 s | Keeps the arm up between auto-chained arcs. Keep it ≤ ChainWindow 0.6. Lower it if releases feel sluggish. |
| Arm rates | A7 | +5 / −5 (fast −10) | raise and lower times |
| Physics rates | A6 | +5 / −6 (fast −15) | hang fade-in and fade-out times |
| dt clamp | A1 | 0.05 | stops a hitch frame from jumping the arm |
| No-anchor direction | B10, K8, E2 | (0, −0.196, 0.981) | more negative Y puts the hand more over the head |
| Waypoint | B13 | (0, 1, 0) | outward direction of the raise |
| Aim smoothing | B11 | 8 /s | how fast the arm follows the anchor direction |
| Hand facing | B15 Secondary.Target | (1, 0, 0) | gun or claw points forward |
| Shoulder / pelvis / head / posture strength | C10 | 0.25 / 0 / 4 / 1 | more shoulder = less tilt and faster re-facing; posture 0.4-0.7 = limper limbs |
| No-anchor inertia | C12 | 0.25 | 0 = body hangs straight down; keep < 0.5 |
| Gravity parameters | C12 | 1.3, 0.7, 0.005, CMC 1.0 | must match V10 |
| Acceleration clamp | C11 | 4000 | lower = calmer hang, less pendulum feel |
| Angular inertia | C11 | 0.2 | higher = more fling on turns |
| Teleport threshold | C13 | 600 | raise it if hitches appear at low fps |

---

## 11. Test checklist

**CR preview (before PIE):**
1. Temporarily set the CR defaults `bIsSwinging` = true and `bFootLock_L` / `bFootLock_R` = false (the CR defaults them to True, E7). Turn on bShowBodies and bShowJoints on Sw_Step.
2. The arm swings out to the side, then overhead, in about 0.2 s. It must not pass through the head or torso.
3. Over the next 0.2 s the body sags and hangs below the right shoulder:
   - the torso tilts so its centre of mass sits under the shoulder;
   - the legs dangle;
   - the head stays within about 15° of upright;
   - no flip or explosion (if there is one, recheck V4) and no visible joint gaps.
   - In the preview the capsule does not move, so this is the pure −981 hang.
4. Set `bIsSwinging` false. The body returns to the animated pose with the arm still up (about 0.17 s), then the arm lowers along the same path (about 0.2 s). No pop. ArmAlpha and PhysAlpha end at 0, and bSwingActive is false.
5. **Restore the defaults** (bIsSwinging false, foot locks True) before saving.

**PIE, owner:**
1. Compile CR_Mech, then the ABP. No warnings, and no per-frame "component not found" (that would mean V2 is wrong).
2. **Jump and grapple:**
   - the arm rises while the hook flies;
   - the hang starts about 0.2 s after the press;
   - the hand stays fixed relative to the capsule while shooting, beaming and looking around.
3. **With §4.2:**
   - the arm points at the anchor;
   - at the apex and mid-arc of a 45° swing the torso lines up with the rope line from the hand.
   **Without §4.2:** the arm is straight up and the body hangs nearly straight down.
4. **Fast short swing** (rope about 400, about 3000 cm/s) with bShowJoints: no visible separation, and no kick at attach or slack-catch.
5. **Chained arcs:** hold the button through at least 5 auto-chained arcs. The arm stays up and bSwingActive stays true between arcs (check in the CR debugger).
6. **Release and landing:**
   - Release mid-air: the arm stays up at most 0.45 s, then everything blends back.
   - Land (with §4.2): the fast exit totals about 0.2 s.
7. **Hover right after a release:** fast exit. Put temporary Prints on Sw_Step and StepPhysicsSolver1_2; they never fire in the same frame. Afterwards the flying wobble looks as it did before.
8. **Beam hit:** unchanged when not swinging. While hanging, the body gets pushed without exploding.
9. **Shooting while hanging:** the right arm stays up, the left arm aims loosely, and the chest does not jitter.
10. **Steer hard while hanging:** the body does not fling, and the torso drifts back to facing forward.
11. **Low frame rate:** `t.MaxFPS 30` near 3000 cm/s. No hitching.
12. **Contact:** skim low over the ground and pass a wall. Limbs do not snag (if they do, see §12).
13. **After a swing:** with bShowControls on the next flying Step, the controls are back on.
14. **Multiplayer:** only if §4.3 is done. Two clients with PktLag 100; watch the other player.

---

## 12. Optional extras (not part of this build)

- **Anchor on other players' screens:** have the rope GameplayCue (CueParams.Location = anchor, cpp:1352) write the anchor to the character, and feed it in place of §4.2's owner-only value.
- **Solver reset after skipped evaluation:** `SpawnPhysicsSolver.SolverSettings.bResetFromEvaluationInterval` = True with a threshold of about 0.1. This affects flying and the beam too.
- **If joints stretch at high load:** PositionIterations 16 on SpawnPhysicsSolver (all sections).
- **If limbs snag:** MaxDepenetrationVelocity about 300 on SpawnPhysicsSolver, or, while hanging, Set Physics Body Collision Mode on the leg bodies (restore on exit).
- **Free the shoulder only during the swing:** see V4 option (b).
- **Ignore beam pushes while hanging:** move the G3 gate to just before `HierarchyAddPhysicsBodyForce`.
- **Looser arm variant:**
  - C2 and C25 = [RA_point_3, RA_point_4, RA_point_5] only;
  - C10: RA_point_3 → 0 (wrist pivot), RA_point_1 / RA_point_2 → about 6 (stiff elbow), RA_point_0 → 0.25;
  - expect stretching under high loads (D1).
- **Fix the existing beam gap:** the beam section never restores chest to Kinematic. Add an edge-triggered restore on Branch_10's falling edge.
- **Remove the forward lean:** the capsule's swing drag (up to 500 cm/s² at 3000 cm/s, h:129-132) reaches the bodies as a small forward lean of about k·500 [INF]. Compensating it is possible but not needed.

---

## 13. Review notes

**Accepted and applied:**
- Gravity mismatch (api major, feasibility blocker): D4 / C12, with an exact k from `SwingVelocity.Z`. The unbound default equals the api review's 0.6 compromise.
- The kinematic hand target built from the current shoulder (api, integration): D2, using the **initial** RA_point_0 transform, plus fades W1-W4.
- Pass-through frames may not apply control changes (api): D9, hang writes every frame.
- Head as an inverted pendulum (api): head class at 4 in C10.
- LinearStrength 0 assumes joints exist (api): V2b and §10.10.
- Construction state reset (api, integration): §10.1.
- V4 profile wording (api, feasibility): V4 now says it affects all CR physics, and that a runtime change needs `PhysicsJointComponentKeys` stored.
- Wrong root0 helper-body rationale (api): D7 rewritten.
- Acceleration spikes (api, feasibility): clamp in C11.
- Release hysteresis and dt clamp (integration): A3 and A1.
- G1 should not rewire Branch_8 (integration): G1 gates only the Step.
- G3 should keep beam hits (integration): G3 after Add Force, plus D3.
- G5/G6 do nothing (integration): dropped.
- Hand-over to hover or landing (integration): fast exit via A5 and `bIsOnGround`.
- Tag scope (integration, feasibility): §4.1.
- Anchor aiming (feasibility): B9-B11, using the §4.2 inputs.
- Teleport detection (feasibility): C13.
- Entry staging (feasibility): ArmAlpha first, then PhysAlpha, with a waypoint path.
- Exit ramming (feasibility): staged exit; the arm only moves after the physics is at 0.
- Yaw fling (feasibility): angular inertia 0.2.
- Facing restore (feasibility): shoulder at 0.25.
- World collision (feasibility): test 12 and §12.

**Modified:**
- **Clamp value:** used feasibility's 4000, not api's 30000. 30000 still lets about 10 g bottom loads through, while 4000 keeps the arc-end directions exact.
- **Hold time:** 0.45 s instead of 0.35 s. The computed arc gap is about 0.3 s plus search time, so 0.35 s is borderline.
- **Shooting arm IK (integration's G4 / weight fade):** B is left ungated. F overrides the whole right arm at weight 1, and the left arm may aim while swinging.
- **Exit (feasibility):** the arm bodies stay kinematic during the physics fade-out because the arm does not move then. They are released when PhysAlpha reaches 0.
- **Anchor source (feasibility):** `GetGrappleSwing2State` in UMyAnimInstance, not the cue. It needs no BP or cue work; the cue path is in §12 for proxies.
- **Proxy handling (feasibility's bIsSimProxy):** replaced by `IsLocallyControlled` in §4.2. Non-local machines get the no-anchor fallback with no extra CR input.
- **Hand-only kinematic (draft):** replaced by a whole-arm kinematic (D1). This resolves feasibility's arm-straightening and stretch concern and removes the V5 dependency.
- **Warm-start frame counter (api):** replaced by the arm-raise stage, which always gives at least 4 Alpha-0 frames.

**Rejected:**
- **bResetFromEvaluationInterval in construction (api):** it changes flying and beam behaviour, and the staged entry already warms the solver. Moved to §12.
- **PositionIterations 16 (feasibility):** an untested global cost. Moved to §12.
- **SwingInv on Set Transform_9 (integration):** RA_point_4 is reset by F, and the left-arm spin is harmless.
- **Naming `SimulatedTagOnly` / a specific replicated-tag enum (feasibility):** I could not verify the 5.8 API, so §4.3 asks for it to be checked in `AbilitySystemComponent.h`.
- **Tag on at attach via Poll Phase==Swing (feasibility):** tagging at hook launch lets the 0.2 s arm raise overlap the hook flight, and physics still starts only after the raise.
- **bHasSwingAnchor-driven early arm raise (feasibility minor):** unnecessary, because the tag already starts at hook launch.
