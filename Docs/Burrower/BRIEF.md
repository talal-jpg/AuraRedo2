# Burrower in UE: shared brief for all agents

## The user's request (verbatim)
"add one more bone for the cutter rotor only parented to the root (to make the rotor spin in the control rig), then import
the fbx in UE project, make a character and 1. make it spawn behind a certain distance of each player, after a certain
interval of time for each player, 2. it follows each player character 3. it has ability system component (attribute set,
takes damage etc.), 4. make physics asset with simple collision shapes and activate rag doll in control rig when the
character dies, 5. add bones and weights for the upper and side pipes as well and make them driven by control rig
dynamics (rigid body and wire type where makes sense), 6. the whole body should sinusoidal movement like this
https://www.youtube.com/watch?v=_Fp2nJuU7Q0 at 5 40 the third part of the video, 7. the cutter rotor should spin and
should activate the HexPlatform tiles as soon as a collision box that is attached to the rotor with some padding
overlaps a HexPlatform tile."

The video ("How to Make INSANE Procedural Animations with Control Rig in Unreal Engine 5") could not be opened from
here. Reading chosen: a travelling sine wave along the body (snake / worm style lateral undulation, phase shifted per
joint from head to tail), speed-linked, amplitude and wavelength exposed as parameters.

## The creature
"Burrower": a 20.2 m long fish-like burrowing machine. Head with a spinning cutter rotor at the front (+X).
Skeleton after the Blender update (names fixed, C++ may rely on `root`, `J0_Head`..`J4_Tail`, `Rotor`):
```
root                      at the origin (ground level under the body centre)
├─ J0_Head                maw front   x = +1000 cm, z = 180 cm
│  └─ J1_Forequarters     x = +660 cm   (pipe bone chains hang under this joint)
│     └─ J2_Midbody       x = +260 cm
│        └─ J3_Hindbody   x = -260 cm
│           └─ J4_Tail    x = -560 cm (tail tip at -1017 cm)
└─ Rotor                  rotor centre about (980, 0, 180.5) cm, spins about the body's long axis (X)
```
Rotor geometry (cm, mesh space): x 950..988, |y| <= 106, z 75..286 (a disc of radius ~106 cm, 38 cm deep).
Mesh space: +X forward (head), Z up, cm, origin under the body centre at ground level. Body axis height ~180-200 cm.
Pipe bone chains (names decided in Blender, not needed by C++): upper pipes (two armoured hoses on the back running from the
collar up to the front of the dorsal canisters) and side pipes (hoses hanging under the shoulder hubs, two per side).

## UE project
Local clone: /home/claude/AuraRedo2, branch `claude/project-thread-78otz4` (made from origin/redo3, which is exactly what is on
the user's machine). UE 5.8 source build on the user's machine (Linux). Module `Aura`, public headers in
Source/Aura/Public, sources in Source/Aura/Private. Multiplayer (listen server, EOS/Steam), GAS everywhere.
Existing patterns to reuse: AMyCharBase / AMyEnemyChar (ASC + UMyAttributeSet + death via IMyCombatInterface::Die and
MulticastHandleDeath), UMyAbilitySystemComponent, ExecCalc_Damage, MyGameplayTags, UDeveloperSettings pattern
(MyHexBridgeSettings, MyHexMinimapSettings), AMyHexPlatform (hex tiles as ISM instances, server activates a tile with
ActivateHex -> replicated ActivatedTiles -> ActivateHexLocal on every machine), AMyGameState (lead player ranking),
MechSentinel swarm (Mass) with its own GAS proxy.

Engine plugin headers staged read-only at /mnt/user-data/uploads/ControlRigDynamics and
/mnt/user-data/uploads/ControlRigPhysics (UE 5.8 experimental plugins; ControlRigDynamics is already enabled in
Aura.uproject, ControlRigPhysics is not). Some project files from the user's machine are staged under
/mnt/user-data/uploads/AuraRedo3 (identical to the clone except comments).

## Split of the work
* Cloud (this run): Blender rig update and FBX (done by the lead, not by you), all C++ (you), reviewed.
* User's machine (a later Claude Code session with the editor and compiler): build, fix compile errors, import FBX,
  physics asset, Control Rig asset (rotor spin, body wave, pipe dynamics, ragdoll on death), AnimBP, BP_Burrower,
  project settings, PIE test. It will follow a recipe written by this run.

## C++ design (fixed decisions; improve details, do not change the shape without a strong reason)
New files under Source/Aura/Public/Burrower and Source/Aura/Private/Burrower:
1. `UBurrowerSettings` (UDeveloperSettings, Config=Game, defaultconfig, Project Settings > Game > Burrower):
   BurrowerClass (TSoftClassPtr<ABurrowerCharacter>), bEnabled, FirstSpawnDelay, SpawnInterval (seconds after the
   player's previous burrower died / was removed, or since join), SpawnDistanceBehind (cm), SpawnHeightOffset (cm),
   MaxAlivePerPlayer (default 1), bRespawnAfterDeath, DespawnDistance (cm, optional, 0 = never).
2. `UBurrowerSpawnSubsystem` (UWorldSubsystem, server only: authority / not NM_Client, game worlds only): keeps one
   entry per player pawn/controller (handles join/leave/respawn of the player pawn), a timer per player, spawns
   BurrowerClass behind the player (location = player location - player forward (or -velocity dir when moving)
   * SpawnDistanceBehind + up * SpawnHeightOffset, facing the player), sets its target player, tracks it, re-arms after
   its death. Console command `Aura.Burrower.SpawnNow` for testing. Uses AlwaysSpawn collision handling.
3. `ABurrowerCharacter` — USER DECISION (2026-11-21): derive from AMyEnemyChar. This is fixed; do not derive from
   AMyCharBase. Where AMyEnemyChar brings behaviour that does not fit a 20 m flying worm, override or neutralise it in
   the subclass instead of changing the base class:
   * replicated TargetPlayer (APawn), set by the spawner; server-side follow: flying movement mode (no navmesh, the
     hex platforms float and collapse), steering toward the target with smooth turn rate, MaxFlySpeed, stop distance,
     optional "keep behind" distance; rotation follows velocity smoothly; AIController possession (AutoPossessAI
     PlacedInWorldOrSpawned, AIControllerClass = AAIController or a small ABurrowerAIController) so AddMovementInput works.
   * capsule sized for the head region; mesh relative transform so the 20 m mesh sits correctly (mesh faces +X).
   * GAS: ASC (project's UMyAbilitySystemComponent) + attribute set (project's UMyAttributeSet unless a dedicated set is
     clearly better), init like the project's enemies (default attribute effects / class info), replicated, takes
     damage through the project's existing damage pipeline so player abilities hurt it; dies via the project's death flow.
   * death: server Die() -> multicast -> stop movement, disable rotor box, set bIsDead on the anim instance (the Control
     Rig switches to ragdoll), with a C++ fallback (bUseMeshRagdollFallback: SetAllBodiesSimulatePhysics on the physics
     asset) for when the Control Rig ragdoll is not wired yet; LifeSpan after death.
   * mesh collision for hits: QueryOnly with the physics asset bodies, so traces and projectiles hit the body.
   * rotor: `UBoxComponent* RotorBox` attached to the mesh at socket/bone `Rotor`, extent = rotor half size + padding
     (RotorBoxPadding, default 50 cm), collision QueryOnly, no physics, does not block pawns; server checks every
     RotorCheckInterval (e.g. 0.05 s): finds AMyHexPlatform actors whose tiles intersect the oriented box and activates
     those tiles through a new public server API on AMyHexPlatform; RotorSpinSpeed (deg/s) exposed; rotor visual spin is
     done by the Control Rig (cosmetic, every machine), fed from the anim instance.
   * cosmetic body wave parameters (amplitude deg per joint, wavelength / phase per joint, frequency, speed-linked
     frequency) exposed on the character and read by the anim instance.
4. `UBurrowerAnimInstance` (UAnimInstance): thread-safe properties read by the AnimBP and passed to the Control Rig
   node as variables: RotorAngleDeg (accumulated), RotorSpinSpeed, WaveTime (accumulated, speed-linked), WaveAmplitudeDeg,
   WavePhasePerJointDeg, WavePitchAmplitudeDeg, Speed, bIsDead, DeathTime.
5. AMyHexPlatform: add a minimal public server API, e.g. `int32 ActivateTilesInWorldBox(const FTransform& BoxToWorld,
   const FVector& BoxExtent)` that activates every live tile whose pillar (LocalBounds in actor space) intersects the box,
   through the same path the platform's own collapse uses (so replication, effects, props, bridges keep working). Keep
   the change small and in the file's style.
6. Aura.Build.cs: add modules you need (AIModule, ControlRig only if C++ touches it, etc.). Aura.uproject: enable
   ControlRigPhysics (Enabled true) next to ControlRigDynamics.
7. Console variables or settings for debug drawing of the rotor box (Aura.Burrower.DebugRotorBox).

Code style: match the project (UPROPERTY categories, comments short and plain, Linux build with clang, UE 5.8 APIs).
Must compile on UE 5.8 without the editor open; do not use APIs you are not sure exist; prefer stable, old APIs.
