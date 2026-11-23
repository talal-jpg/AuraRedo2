# as_12_control_rig.py -- builds CR_Airship (research_control_rig.md sections 2-6, 7a-f; RIG_CONTRACT.md section 5) in the
# UE 5.8 editor, the Burrower bw_04 way (as_cr_helpers.py = the verified bw_cr_helpers.py with airship paths).
#
# Run (inbox harness in the clone's editor, NOT during PIE; synchronous, needs no frames):
#   Docs/Airship/scripts/harness/inbox.sh 12 Docs/Airship/scripts/ue/as_12_control_rig.py 900
#   grep FAIL:/WARN: in the .out; last line RESULT:. Summary: Saved/Airship/as_12_control_rig.json
# Then: as_12b_cr_dump.py (graph dump for the reviewer), as_13_cr_eval.py (numeric checks on a rig instance).
# Re-runnable: MODE 'reuse' (default) rebuilds every node in place (variables kept); 'recreate' deletes and remakes it
# (fresh editor session only, see MODE). AS12_<KNOB> globals override the knobs below.
#
# WHAT IT BUILDS
#  Variables: the 37 public ones of RIG_CONTRACT 5 (36 float + bool bIsDead), plus private bool bDeathKickDone.
#  Construction: WreckSolver (owner Hull, Component space, world collision All) + 20 Wreck bodies + 8 limp cannon joints,
#    then FxSolver (owner root, Component space, no world collision, zero gravity) + 22 Fx bodies + 21 driven joints,
#    then Instantiate both. Wreck first so its bodies keep the plain name PhysicsBody (the kick refers to them by key);
#    the Fx bodies become PhysicsBody_2 and are only used through links inside Construction.
#  Forwards Solve: controls (nozzle pitch/roll, petal flare per hinge axis A x d baked from the rest pose, turbine yaw,
#    rotor spin, rudder, helm wheel, cannon yaw / recoil (Offset Transform along -aim) / elevation about the trunnion
#    axle / quoin slide / truck wheel roll, searchlight head pan) -> StepFx (Alpha = 1 - bIsDead) -> death kick (once,
#    first dead frame with dt > 0) -> StepWreck (Alpha = bIsDead).
#
# DEVIATIONS FROM research_control_rig.md (it predates the 2026-11-22 contract)
#  1. Variables follow RIG_CONTRACT 5, not the research table: NozzlePitch/Roll/Flare + ThrustAlpha instead of
#     ThrusterPitch/Roll + NozzleScale. Pods have no control (physics jiggle only, soft 3 deg cone); the nozzle bone gets
#     pitch (about +Y) and roll (about +X); the 12 petals per nozzle flare about A x d. ThrustAlpha_* and DeathTime are
#     public but unused by the graph (FX / v2 timed break-offs).
#  2. Cannon yaw is a standard rotation about component +Z (the C++ AAirshipPawn::GetCannonDirLocal uses
#     FQuat(UpVector, Yaw)); README_rig.md's "+ swings L2 aft" is Blender's sign. Rudder / wheel likewise standard
#     rotations about +Z / +X as the contract pins them (the Blender test sweep has the opposite sign on those three).
#  3. Elevation axis = the cannon's truck axle (Wheel_FL - Wheel_FR, rolled 1-2.5 deg by the deck sheer), sign chosen so
#     + raises the muzzle; fallback aim x Z. Wheels roll about the same axis by recoil / 22 cm rad.
#  4. Quoin: slide = clamp(2.4 cm/deg * elev, 0, 15) along -aim (README_rig.md ranges; Blender rig_common.quoin_slide).
#  5. Fx solver gravity is (0,0,0): the parts keep their control pose at rest (a 2-3 Hz drive would let the fan nacelles
#     and barrels sag ~1.6 deg under gravity); the wobble comes from the ship's own accelerations (inertial forces).
#  6. Wreck WorldCollisionType 'All' + bounds expansion 2.5 (Burrower deviation 29: hex tiles are WorldDynamic, 'Static'
#     misses them), not 'Static'.
#  7. Turbine rods get an Fx pendulum body (weak drive, soft 10 deg cone). ChainFwd and the winches stay static.
#  8. Death kick: VelocityChange in Body space (the bones are world-aligned, so Body = component axes at death; World
#     would need a world-space vector), outward/up per break-off part, once per life (latch bDeathKickDone) as the
#     Burrower kick, plus a spin. Starting values; tune in PIE.
#  9. Bones whose rest LOCAL rotation is identity (all of them here) get Q -> SetRotation(LocalSpace) without the
#     Init * Q multiply; others would get the full pattern R. Axes are still baked from the rest pose.
#  10. Searchlight pan: heads AftL/MidL +pan, MidR/FwdC -pan (mirror pair), no extra offsets.
#  11. Wreck Hull body = 4 flat deck pads (one under each cannon's carriage + barrel footprint, top 2 cm below its lowest
#      wheel) instead of one thin sheer-tilted deck box, and the limp carriage joints keep collision with the Hull body
#      (JointData.bDisableCollision False; the maker's Cone/Twist limits linked by sub-pin), so a dead ship's cannons
#      rest on the deck instead of tipping into it (first eval: 15 deg in 0.5 s). Barrels stay collision-free with
#      their carriage (jointed) but hit the pads.
#
# SESSION 3 (2026-11-22, offline CR review findings applied; numbers in the review / the session-3 report)
#  R1. Turbine nacelles: C_FDrvTurbine damping 0.4 -> 1.0 and a soft joint limit C_FJTurbine (twist 3, swing1 = yaw
#      about Z 12, swing2 3 deg; 10 Hz, ratio 1) on C_FJoint_Turbine_L/R: the inboard yaw stop is 12 deg (steam band).
#  R2. Barrels: C_FDrvBarrel damping 0.3 -> 1.0 (C++ CannonElevMaxDeg 9 -> 8.75 on the pawn and the anim instance).
#      0.8 still peaked 9.55 deg (barrel vs carriage) on the C++ 45 deg/s slew: with SkeletalAnimationVelocityMultiplier
#      0.5 the drive lags the ramp by 2 zeta (1 - 0.5) v / omega and overshoots unless zeta >= 1.
#  R3. Death kick also needs DeathTime < 0.5 s (F_KickFresh / F_KickFire2), so a late joiner or a re-initialised rig
#      (bDeathKickDone back at False) does not replay the break-off kick.
#  R4. Wreck WorldCollisionBoundsExpansion 2.5 -> 1.6 (the overlap box is the union of all simulated Wreck bodies, i.e.
#      the whole 51 m ship, times this: 128 x 60 x 38 m at 2.5; 82 x 38 x 24 m at 1.6, still 4.6 m of margin below the
#      lowest part = 2.3 frames at 60 m/s and 30 fps; the review's 1.35 leaves 2.65 m).
#  R5. Wreck Hull body: + deck / gantry slabs (Saved/Airship/deck_slabs.json from as_20a/as_20b: 2 cm under the surveyed
#      surfaces, cut around every Wreck body's rest box), so kicked parts land on the ship instead of falling into it.
#  R6. Turbine rods get Wreck bodies too (limp joint to their nacelle, C_WLimpBarrel + C_WNoDrive), so they do not snap
#      from their Fx wobble to the rest pose at death. They are spawned before Fx: the Fx rods become PhysicsBody_2.
#  R7. Pods: C_FJThruster soft limit 3 -> 1 deg (README_rig.md: +-0.5 clean, +-1 = a rib 4 cm into the pocket wall).
#
# VALIDATION SESSION (2026-11-22, after the C++ fix rounds 2-3; first smoke test: wreck parts scattered 34-120 m, a fast
# searchlight tunnelled the 1 m ground plane after the crash bounce)
#  V1. Death kick: linear x KICK_LIN_SCALE 0.5, spin x KICK_ANG_SCALE 0.6 (KICK_BASE keeps the session-3 values), so the
#      parts land ~10-40 m from a ship that falls from high up instead of 34-120 m. as_13_cr_eval.py mirrors the table.
#  V2. CCD: WreckSolver SolverSettings.bAllowCCD True + BodyData.bEnableCCD on the fast break-off Wreck bodies
#      (pods, nacelles, rods, rudder, searchlight posts; not the jointed cannons, not the kinematic Hull).
#  V3 (tried, reverted): searchlight posts' linear kick x0.5 more (KICK_PART_LIN_SCALE) because they landed 40-60 m from
#      a wreck that fell 279 m; then they stay on their gantry slabs when the ship dies at rest (as_13: 4 FAIL). Left empty.
import importlib
import json
import math
import os
import sys
import time
import traceback

AS12_DIR = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue'
if AS12_DIR not in sys.path:
    sys.path.insert(0, AS12_DIR)
import as_cr_helpers as H  # noqa: E402
importlib.reload(H)

MODE = 'reuse'          # 'reuse' (default): create if missing, else remove every node and rebuild in place (variables
                        # kept). 'recreate' force-deletes first: only in a FRESH editor session - after rig test
                        # instances (as_13) existed, ForceDelete failed ('in use', package 'potentially corrupt') and the
                        # next graph edit crashed UE 5.8 (SIGSEGV URigVMBlueprint::GetDebugInfo, 2026-11-22 11:09 UTC).
RECREATE_EVEN_IF_REFERENCED = False
DEATH_KICK = True
ABORT_ON_PIN_PROBE_FAIL = True
SAVE_ON_FAIL = False
for _k in ('MODE', 'RECREATE_EVEN_IF_REFERENCED', 'DEATH_KICK', 'ABORT_ON_PIN_PROBE_FAIL', 'SAVE_ON_FAIL'):
    if 'AS12_' + _k in globals():
        globals()[_k] = globals().pop('AS12_' + _k)

_as12_counts = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def _as12_out(tag, msg):
    _as12_counts[tag] = _as12_counts.get(tag, 0) + 1
    print('%s: %s' % (tag, msg))


H._out = _as12_out
info, warn, passed, fail = H.info, H.warn, H.passed, H.fail
bone, comp, vec, arr, S = H.bone, H.comp, H.vec, H.arr, H.S
P = '/Script/ControlRigPhysics.'
CRS = '/Script/ControlRig.'
VM = '/Script/RigVM.RigVMFunction_'

# ------------------------------------------------------------------------------------------------- names
PODS = ['FL', 'FR', 'RL', 'RR']
FANS = ['L', 'R']
CANNONS = ['L1', 'L2', 'R1', 'R2']
LIGHTS = ['AftL', 'MidL', 'MidR', 'FwdC']
LIGHT_PAN_SIGN = {'AftL': 1.0, 'MidL': 1.0, 'MidR': -1.0, 'FwdC': -1.0}
WRECK = comp('Hull', 'PhysicsSolver')
FX = comp('root', 'PhysicsSolver')
BOUNDS_JSON = 'part_bounds.json'

FLOAT_VARS = (['NozzlePitchDeg_' + p for p in PODS] + ['NozzleRollDeg_' + p for p in PODS] +
              ['NozzleFlareDeg_' + p for p in PODS] + ['ThrustAlpha_' + p for p in PODS] +
              ['TurbineYawDeg_' + s for s in FANS] + ['RotorAngleDeg_' + s for s in FANS] +
              ['RudderDeg', 'WheelAngleDeg'] + ['CannonYawDeg_' + c for c in CANNONS] +
              ['CannonElevDeg_' + c for c in CANNONS] + ['CannonRecoilCm_' + c for c in CANNONS] +
              ['SearchLightPanDeg', 'DeathTime'])
PUBLIC_VARS = [(n, H.CPP_FLOAT, 0.0) for n in FLOAT_VARS] + [('bIsDead', H.CPP_BOOL, False)]
PRIVATE_VARS = [('bDeathKickDone', H.CPP_BOOL, False)]

QUOIN_CM_PER_DEG, QUOIN_MAX_CM = 2.4, 15.0
WHEEL_RADIUS_CM = 22.0

# ------------------------------------------------------------------------------------------------- physics values
WRECK_SOLVER_PINS = {
    'Owner': bone('Hull'),
    'SolverSettings.bAutomaticallyAddPhysicsBodyComponents': False,
    'SolverSettings.SimulationSpace': 'Component',
    'SolverSettings.CollisionSpace': 'Component',
    'SolverSettings.WorldCollisionType': 'All',
    'SolverSettings.bWorldCollisionIncludePhysics': True,
    'SolverSettings.bWorldCollisionIncludeQuery': False,
    'SolverSettings.WorldCollisionBoundsExpansion': 1.6,      # R4 (was 2.5)
    'SolverSettings.PositionIterations': 8,
    'SolverSettings.VelocityIterations': 2,
    'SolverSettings.ProjectionIterations': 1,
    'SolverSettings.FixedTimeStep': 0.0,
    'SolverSettings.MaxDeltaTime': 0.0334,
    'SolverSettings.MaxTimeSteps': 4,
    'SolverSettings.MaxDepenetrationVelocity': 500.0,
    'SolverSettings.bAllowCCD': True,                         # V2 (the bodies opt in with BodyData.bEnableCCD)
    'SolverSettings.bResetFromPosition': False,
    'SolverSettings.bResetFromKinematicSpeed': False,
    'SolverSettings.bResetFromKinematicAcceleration': False,
    'SolverSettings.bResetFromEvaluationInterval': False,
    'TeleportDetection.PositionChangeThreshold': 3000.0,
    'TeleportDetection.OrientationChangeThreshold': 90.0,
    'TeleportDetection.LinearAccelerationThreshold': 1000000.0,
    'TeleportDetection.AngularAccelerationThreshold': 1000000.0,
    'SpaceMotion.InertialForces.Amount': 1.0,
    'SpaceMotion.Drag.LinearDragMultiplier': 1.0,
    'SpaceMotion.Drag.AngularDragMultiplier': 1.0,
}
FX_SOLVER_PINS = {
    'Owner': bone('root'),
    'SolverSettings.bAutomaticallyAddPhysicsBodyComponents': False,
    'SolverSettings.SimulationSpace': 'Component',
    'SolverSettings.CollisionSpace': 'Component',
    'SolverSettings.WorldCollisionType': 'None',
    'SolverSettings.Gravity': vec(0, 0, 0),             # deviation 5
    'SolverSettings.PositionIterations': 8,
    'SolverSettings.VelocityIterations': 1,
    'SolverSettings.FixedTimeStep': 0.0,
    'SolverSettings.MaxDeltaTime': 0.0334,
    'SolverSettings.MaxTimeSteps': 4,
    'SolverSettings.bResetFromEvaluationInterval': True,
    'SolverSettings.EvaluationIntervalThresholdForReset': 0.25,
    'TeleportDetection.PositionChangeThreshold': 2000.0,
    'TeleportDetection.OrientationChangeThreshold': 45.0,
    'SpaceMotion.VerticalMotionScale': 1.0,
    'SpaceMotion.bClampLinearVelocity': True,
    'SpaceMotion.MaxLinearVelocity': 4000.0,
    'SpaceMotion.bClampLinearAcceleration': True,
    'SpaceMotion.MaxLinearAcceleration': 4000.0,
    'SpaceMotion.bClampAngularVelocity': True,
    'SpaceMotion.MaxAngularVelocity': 2.5,             # rad/s (Physics)
    'SpaceMotion.bClampAngularAcceleration': True,
    'SpaceMotion.MaxAngularAcceleration': 15.0,        # rad/s^2
    'SpaceMotion.InertialForces.Amount': 1.0,
    'SpaceMotion.Drag.LinearDragMultiplier': 1.0,
    'SpaceMotion.Drag.AngularDragMultiplier': 0.0,
}
BODY_COMMON_WRECK = {'Solver.PhysicsSolverComponentKey': WRECK, 'Solver.bUseAutomaticSolver': False,
                     'BodyData.CollisionType': 'PhysicsOnly', 'BodyData.GravityMultiplier': 1.0}
BODY_COMMON_FX = {'Solver.PhysicsSolverComponentKey': FX, 'Solver.bUseAutomaticSolver': False,
                  'BodyData.CollisionType': 'NoCollision', 'BodyData.GravityMultiplier': 1.0}
# kind -> (movement, mass, lin damp, ang damp)
WRECK_KIND = {'hull': ('Kinematic', 1.0, 0.0, 0.0), 'thruster': ('Simulated', 4.0, 0.05, 0.3),
              'turbine': ('Simulated', 6.0, 0.05, 0.3), 'rudder': ('Simulated', 3.0, 0.05, 0.3),
              'rod': ('Simulated', 1.0, 0.05, 0.3),
              'carriage': ('Simulated', 3.0, 0.1, 0.5), 'barrel': ('Simulated', 2.0, 0.1, 0.5),
              'light': ('Simulated', 1.0, 0.05, 0.3)}
FX_KIND = {'hull': ('Kinematic', 1.0, 0.0, 0.0), 'thruster': ('Simulated', 4.0, 0.0, 0.5),
           'turbine': ('Simulated', 6.0, 0.0, 0.5), 'rod': ('Simulated', 1.0, 0.0, 0.3),
           'rudder': ('Simulated', 3.0, 0.0, 0.5), 'carriage': ('Simulated', 5.0, 0.0, 0.5),
           'barrel': ('Simulated', 3.0, 0.0, 0.3), 'light': ('Simulated', 1.0, 0.1, 0.3)}
# pure makers: name -> (struct, pins)
ART_JOINT = P + 'RigUnit_MakeArticulationJointData'
ART_DRIVE = P + 'RigUnit_MakeArticulationDriveData'
MAKE_DRIVE = P + 'RigUnit_MakeDriveData'
MAKERS_WRECK = {
    'C_WLimpCarriage': (ART_JOINT, {'AngularLimit': vec(30, 20, 20), 'SoftStrength': vec(3, 3, 3),
                                    'SoftDampingRatio': vec(0.8, 0.8, 0.8)}),
    'C_WLimpBarrel': (ART_JOINT, {'AngularLimit': vec(30, 30, 30), 'SoftStrength': vec(3, 3, 3),
                                  'SoftDampingRatio': vec(0.8, 0.8, 0.8)}),
    'C_WNoDrive': (ART_DRIVE, {'bEnableAngularDrive': False}),
}
MAKERS_FX = {
    'C_FJThruster': (ART_JOINT, {'AngularLimit': vec(1, 1, 1), 'SoftStrength': vec(6, 6, 6),       # R7 (was 3)
                                 'SoftDampingRatio': vec(1, 1, 1)}),
    'C_FJTurbine': (ART_JOINT, {'AngularLimit': vec(3, 12, 3), 'SoftStrength': vec(10, 10, 10),     # R1: Y = swing1 = yaw
                                'SoftDampingRatio': vec(1, 1, 1)}),
    'C_FJPost': (ART_JOINT, {'AngularLimit': vec(4, 4, 4), 'SoftStrength': vec(6, 6, 6),
                             'SoftDampingRatio': vec(1, 1, 1)}),
    'C_FJRod': (ART_JOINT, {'AngularLimit': vec(10, 10, 10), 'SoftStrength': vec(4, 4, 4),
                            'SoftDampingRatio': vec(0.7, 0.7, 0.7)}),
    'C_FDrvThruster': (ART_DRIVE, {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 3.0,
                                   'AngularDampingRatio': 0.35, 'AngularExtraDamping': 0.0,
                                   'SkeletalAnimationVelocityMultiplier': 0.5}),
    'C_FDrvTurbine': (ART_DRIVE, {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 2.0,
                                  'AngularDampingRatio': 1.0, 'AngularExtraDamping': 0.0,         # R1 (was 0.4)
                                  'SkeletalAnimationVelocityMultiplier': 0.5}),
    'C_FDrvRod': (ART_DRIVE, {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 0.8,
                              'AngularDampingRatio': 0.15, 'AngularExtraDamping': 0.0,
                              'SkeletalAnimationVelocityMultiplier': 0.3}),
    'C_FDrvRudder': (ART_DRIVE, {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 3.0,
                                 'AngularDampingRatio': 0.5, 'AngularExtraDamping': 0.0,
                                 'SkeletalAnimationVelocityMultiplier': 0.7}),
    'C_FDrvBarrel': (ART_DRIVE, {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 3.0,
                                 'AngularDampingRatio': 1.0, 'AngularExtraDamping': 0.0,          # R2 (was 0.3)
                                 'SkeletalAnimationVelocityMultiplier': 0.5}),
    'C_FDrvPost': (ART_DRIVE, {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 2.5,
                               'AngularDampingRatio': 0.2, 'AngularExtraDamping': 0.0,
                               'SkeletalAnimationVelocityMultiplier': 1.0}),
    'C_FDrvCarriage': (MAKE_DRIVE, {'bEnableLinearDrive': True, 'LinearStrength': 9.0, 'LinearDampingRatio': 0.55,
                                    'LinearExtraDamping': 0.0, 'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP',
                                    'AngularStrength': 4.0, 'AngularDampingRatio': 0.5, 'AngularExtraDamping': 0.0,
                                    'SkeletalAnimationVelocityMultiplier': 1.0}),
}
CARRIAGE_JOINT_PINS = {'JointData.LinearConstraint.XMotion': 'LCM_Limited', 'JointData.LinearConstraint.YMotion': 'LCM_Limited',
                       'JointData.LinearConstraint.ZMotion': 'LCM_Limited', 'JointData.LinearConstraint.Limit': 80.0}
STEP_FX_PINS = {'PhysicsSolverComponentKey': FX, 'bTrackVelocitiesDuringPassThrough': False, 'DeltaTimeOverride': 0.0,
                'SimulationSpaceDeltaTimeOverride': 0.0}
STEP_WRECK_PINS = {'PhysicsSolverComponentKey': WRECK, 'bTrackVelocitiesDuringPassThrough': True,
                   'DeltaTimeOverride': 0.0, 'SimulationSpaceDeltaTimeOverride': 0.0}
VEC_ZERO = '(X=0.000000,Y=0.000000,Z=0.000000)'
KICK_FORCE_PINS = {'ForceAndTorque.Type': 'VelocityChange', 'ForceAndTorque.ForceAndTorqueSpace': 'Body',
                   'ForceAndTorque.LocationSpace': 'Body', 'ForceAndTorque.Location': VEC_ZERO, 'Name': 'DeathKick'}
# break-off part -> (linear cm/s, angular rad/s), component axes (= body axes at death: world-aligned bones)
KICK_LIN_SCALE, KICK_ANG_SCALE = 0.5, 0.6     # V1 (validation 2026-11-22): KICK = KICK_BASE scaled
KICK_BASE = {
    'Thruster_FL': ((60, -260, -120), (-1.2, 0.8, 0.6)), 'Thruster_FR': ((60, 260, -120), (1.2, 0.8, -0.6)),
    'Thruster_RL': ((-60, -260, -120), (-1.0, -0.9, 0.5)), 'Thruster_RR': ((-60, 260, -120), (1.0, -0.9, -0.5)),
    'Turbine_L': ((-180, -320, 160), (-1.5, 0.6, 1.0)), 'Turbine_R': ((-180, 320, 160), (1.5, 0.6, -1.0)),
    'Rudder': ((-220, 0, 120), (0.0, -1.2, 1.6)),   # session 3: -Y spin, the top tips aft (+1.2 flipped it onto the stern deck)
    'SearchLight_AftL': ((0, -150, 380), (-2.0, 0.5, 0.0)), 'SearchLight_MidL': ((60, -170, 400), (-1.8, -0.6, 0.0)),
    'SearchLight_MidR': ((60, 170, 400), (1.8, -0.6, 0.0)), 'SearchLight_FwdC': ((120, -60, 420), (-0.6, -1.9, 0.0)),
}
# Per-part extra linear scale (empty). Tried in the validation session (V3): the searchlight posts x0.5 more, because after
# V1 they landed 40-60 m from a wreck that fell 279 m (pods / nacelles / rudder 7.5-32 m). Reverted: with a 0.95-1.05 m/s
# up-kick the posts no longer leave their gantry slabs on a ship that dies at rest (as_13 t_death: |d| 2-9 cm, 4 FAIL).
KICK_PART_LIN_SCALE = {}
KICK = dict((k, (tuple(round(x * KICK_LIN_SCALE * KICK_PART_LIN_SCALE.get(k, 1.0), 3) for x in lin),
                 tuple(round(x * KICK_ANG_SCALE, 3) for x in ang)))
            for k, (lin, ang) in KICK_BASE.items())
WRECK_CCD_KINDS = ('thruster', 'turbine', 'rod', 'rudder', 'light')   # V2

K_DT = VM + 'GetDeltaTime'
K_NOT = VM + 'MathBoolNot'
K_AND = VM + 'MathBoolAnd'
K_GREATER = VM + 'MathFloatGreater'
K_LESS = VM + 'MathFloatLess'
KICK_FRESH_S = 0.5          # R3: the kick only within this long after the death (DeathTime from the ship's clock)
SLABS_JSON = 'deck_slabs.json'
K_FORCE = P + 'RigUnit_HierarchyAddPhysicsBodyForce'
K_VSCALE = VM + 'MathVectorScale'
K_OFFSET = CRS + 'RigUnit_OffsetTransformForItem'

PINS_USED = {
    P + 'RigUnit_SpawnPhysicsSolver': set(WRECK_SOLVER_PINS) | set(FX_SOLVER_PINS) | {'PhysicsSolverComponentKey'},
    P + 'RigUnit_AddPhysicsBody': set(BODY_COMMON_WRECK) | {'Owner', 'BodyData.MovementType', 'Dynamics.MassOverride', 'BodyData.bEnableCCD',
                                                           'Dynamics.LinearDamping', 'Dynamics.AngularDamping',
                                                           'Collision.Boxes', 'Collision.Spheres', 'PhysicsBodyComponentKey'},
    P + 'RigUnit_AddPhysicsJoint': {'Owner', 'ParentBodyComponentKey', 'ChildBodyComponentKey', 'JointData', 'DriveData',
                                    'PhysicsJointComponentKey', 'JointData.ConeConstraint', 'JointData.TwistConstraint',
                                    'JointData.bDisableCollision'} | set(CARRIAGE_JOINT_PINS),
    ART_JOINT: {'AngularLimit', 'SoftStrength', 'SoftDampingRatio', 'JointData', 'JointData.ConeConstraint',
                'JointData.TwistConstraint'},
    ART_DRIVE: {'bEnableAngularDrive', 'AngularDriveMode', 'AngularStrength', 'AngularDampingRatio', 'AngularExtraDamping',
                'SkeletalAnimationVelocityMultiplier', 'DriveData'},
    MAKE_DRIVE: set(MAKERS_FX['C_FDrvCarriage'][1]) | {'DriveData'},
    P + 'RigUnit_InstantiatePhysics': {'PhysicsSolverComponentKey'},
    P + 'RigUnit_StepPhysicsSolver1': set(STEP_FX_PINS) | set(STEP_WRECK_PINS) | {'Alpha'},
    K_FORCE: set(KICK_FORCE_PINS) | {'PhysicsBodyComponentKey', 'ForceAndTorque.Linear', 'ForceAndTorque.Angular'},
    K_DT: {'Result'}, K_NOT: {'Value', 'Result'}, K_AND: {'A', 'B', 'Result'}, K_GREATER: {'A', 'B', 'Result'},
    K_LESS: {'A', 'B', 'Result'},
    K_VSCALE: {'Value', 'Factor', 'Result'},
    K_OFFSET: {'Item', 'OffsetTransform', 'OffsetTransform.Translation', 'Weight', 'bPropagateToChildren'},
    S['MathFloatClamp']: {'Value', 'Minimum', 'Maximum', 'Result'},
    S['MathFloatMul']: {'A', 'B', 'Result'},
}
NEEDED = sorted(set(list(PINS_USED) + [S['PrepareForExecution'], S['BeginExecution'], S['GetTransform'],
                                       S['SetRotation'], S['MathFloatRad'], S['MathFloatSub'], S['MathBoolToFloat'],
                                       S['MathQuaternionFromAxisAndAngle'], S['MathQuaternionMul'],
                                       S['ControlFlowBranch']]))

# ------------------------------------------------------------------------------------------------- layout
BLOCK_GAP = 380.0
COLORS = {'construction': (0.30, 0.30, 0.30), 'wreck': (0.45, 0.12, 0.12), 'fx': (0.12, 0.30, 0.45),
          'thruster': (0.40, 0.25, 0.08), 'turbine': (0.12, 0.40, 0.18), 'steer': (0.35, 0.18, 0.45),
          'cannon': (0.45, 0.35, 0.10), 'light': (0.18, 0.40, 0.40), 'death': (0.50, 0.10, 0.10)}


class Block(object):
    def __init__(self, stage, title, x0, y0, dx=330.0, dy=240.0):
        self.stage, self.title, self.x0, self.y0, self.dx, self.dy = stage, title, x0, y0, dx, dy
        self.lo = self.hi = None

    def at(self, col, row):
        x, y = self.x0 + self.dx * col, self.y0 + self.dy * row
        self.lo = (x, y) if self.lo is None else (min(self.lo[0], x), min(self.lo[1], y))
        self.hi = (x, y) if self.hi is None else (max(self.hi[0], x), max(self.hi[1], y))
        return unreal.Vector2D(x, y)

    def bottom(self):
        return (self.hi[1] if self.hi else self.y0) + self.dy

    def comment(self, gr, i):
        if self.lo is None:
            return
        pos = unreal.Vector2D(self.lo[0] - 60.0, self.lo[1] - 110.0)
        size = unreal.Vector2D(self.hi[0] - self.lo[0] + self.dx + 60.0, self.hi[1] - self.lo[1] + self.dy + 150.0)
        c = COLORS.get(self.stage, (0.3, 0.3, 0.3))
        H._ue('comment', gr.c.add_comment_node, self.title, pos, size, unreal.LinearColor(c[0], c[1], c[2], 1.0),
              'Comment_%s_%d' % (self.stage, i), False, False)


class Build(object):
    def __init__(self, rig):
        self.rig = rig
        self.g = H.RigGraph(rig)
        self.nodes = {}
        self.expect = {}
        self.blocks = []
        self.c = None
        self.f = None
        self.y = 0.0
        self.data = {}            # baked axes etc. for the summary

    def _add(self, stage, n):
        self.nodes.setdefault(stage, []).append(n)
        return n

    def unit(self, stage, path, name, pos):
        n = self.g.node(path, name, pos)
        self.expect[n] = path.rsplit('.', 1)[1]
        return self._add(stage, n)

    def vec_unit(self, stage, path, name, pos, pin):
        """Template node that must keep its FVector permutation (Burrower _bw04_vec_unit)."""
        n = self.unit(stage, path, name, pos)
        want = path.rsplit('.', 1)[1]
        got = self.g.struct_of(n)
        if got != want:
            self.g.c.unresolve_template_nodes([n], False, False)
            self.g.c.resolve_wild_card_pin(n + '.' + pin, 'FVector', '/Script/CoreUObject.Vector', False, False)
            now = self.g.struct_of(n)
            if now != want:
                raise H.BwError('%s is %s after re-resolve (wanted %s)' % (n, now, want))
            info('%s: template resolved to %s, moved to %s' % (n, got, want))
        return n

    def var_get(self, stage, var, name, pos):
        pin = self.g.var_get(var, name, pos)
        self._add(stage, pin.rsplit('.', 1)[0])
        return pin

    def var_set(self, stage, var, name, pos):
        return self._add(stage, self.g.var_set(var, name, pos))

    def setmany(self, node, pins):
        for k, v in pins.items():
            self.g.setp(node + '.' + k, v)

    def block(self, stage, title, dx=330.0, dy=240.0):
        b = Block(stage, title, 0.0, self.y, dx, dy)
        self.blocks.append(b)
        return b

    def close(self, b):
        self.y = b.bottom() + BLOCK_GAP


# ------------------------------------------------------------------------------------------------- geometry
def _v(t):
    return [t.x, t.y, t.z]


def _norm(a):
    n = math.sqrt(sum(x * x for x in a))
    return [x / n for x in a]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


class Geo(object):
    """Rest pose (rig hierarchy initial globals) + part bounds; bakes bone-local axes."""

    def __init__(self, rig):
        self.rig = rig
        self.pb = H.read_json(BOUNDS_JSON)['bones']
        self._g = {}

    def g(self, b):
        if b not in self._g:
            self._g[b] = H.global_tf(self.rig, b, True)
        return self._g[b]

    def pos(self, b):
        return _v(self.g(b).translation)

    def local_axis(self, b, axis_cs):
        q = self.g(b).rotation
        a = q.unrotate_vector(unreal.Vector(*axis_cs))
        return _norm([a.x, a.y, a.z])

    def local_vec(self, b, v_cs):
        a = self.g(b).rotation.unrotate_vector(unreal.Vector(*v_cs))
        return [a.x, a.y, a.z]

    def local_rest_identity(self, b):
        q = H.local_tf(self.rig, b, True).rotation
        return abs(abs(q.w) - 1.0) < 1e-6

    def aabb(self, *bones, pad=0.0):
        mn, mx = [1e9] * 3, [-1e9] * 3
        for b in bones:
            for i in range(3):
                mn[i] = min(mn[i], self.pb[b]['min'][i])
                mx[i] = max(mx[i], self.pb[b]['max'][i])
        return [x - pad for x in mn], [x + pad for x in mx]

    def box_text(self, owner, mn, mx, name, rot=None):
        """FRigPhysicsCollisionBox text in the owner bone's frame from a component-space AABB (+ optional rotator)."""
        c_cs = [0.5 * (mn[i] + mx[i]) for i in range(3)]
        ext = [mx[i] - mn[i] for i in range(3)]
        c_loc = self.local_vec(owner, _sub(c_cs, self.pos(owner)))
        r = rot if rot is not None else unreal.Rotator(0.0, 0.0, 0.0)
        tm = unreal.Transform(location=unreal.Vector(*c_loc), rotation=r, scale=unreal.Vector(1.0, 1.0, 1.0))
        return '(TM=%s,Extents=%s,Name="%s")' % (tm.export_text(), vec(*ext), name)

    def nozzle_axis(self, p):
        """A = exhaust direction = Flame - Nozzle (both on the nozzle axis)."""
        return _norm(_sub(self.pos('Thruster_%s_Flame' % p), self.pos('Thruster_%s_Nozzle' % p)))

    def petal_hinge(self, p, k):
        """hinge axis h = A x d (d = radial unit from the nozzle axis to the petal hinge); + rotation moves the tip
        (along A below the hinge) outward: (A x d) x A = d."""
        A = self.nozzle_axis(p)
        rel = _sub(self.pos('Thruster_%s_Petal%02d' % (p, k)), self.pos('Thruster_%s_Nozzle' % p))
        rad = _sub(rel, [_dot(rel, A) * a for a in A])
        d = _norm(rad)
        return _norm(_cross(A, d)), d, A

    def cannon_axes(self, c):
        """aim = Muzzle - Barrel (rest); e = elevation axis = truck axle Wheel_FL - Wheel_FR made perpendicular to aim,
        sign so that e x aim points up (+ raises the muzzle); fallback aim x Z."""
        b = 'Cannon_' + c
        aim = _norm(_sub(self.pos(b + '_Muzzle'), self.pos(b + '_Barrel')))
        ref = _cross(aim, [0.0, 0.0, 1.0])
        try:
            ax = _sub(self.pos(b + '_Wheel_FL'), self.pos(b + '_Wheel_FR'))
            ax = _sub(ax, [_dot(ax, aim) * a for a in aim])
            e = _norm(ax)
            if _dot(e, ref) < 0:
                e = [-x for x in e]
            route = 'truck axle'
        except Exception:  # noqa: BLE001
            e = _norm(ref)
            route = 'aim x Z'
        return aim, e, route


# ------------------------------------------------------------------------------------------------- steps
def _prereqs():
    eal = unreal.EditorAssetLibrary
    ok = True
    for p, cls in ((H.SKM_PATH, unreal.SkeletalMesh), (H.PA_PATH, unreal.PhysicsAsset)):
        o = eal.load_asset(p) if eal.does_asset_exist(p) else None
        if not isinstance(o, cls):
            fail('%s missing (run as_10 / as_11 first)' % p)
            ok = False
        else:
            passed('%s exists' % p)
    try:
        H.read_json(BOUNDS_JSON)
        passed('Saved/Airship/%s readable' % BOUNDS_JSON)
    except Exception as e:  # noqa: BLE001
        fail('Saved/Airship/%s missing (run as_09_part_bounds_blender.py): %s' % (BOUNDS_JSON, e))
        ok = False
    try:
        n = len(H.read_json(SLABS_JSON)['boxes'])
        passed('Saved/Airship/%s readable: %d slabs' % (SLABS_JSON, n))
    except Exception as e:  # noqa: BLE001
        fail('Saved/Airship/%s missing (run as_20a in Blender, then as_20b): %s' % (SLABS_JSON, e))
        ok = False
    return ok


def _paths_ok():
    miss = []
    for p in NEEDED:
        try:
            o = unreal.load_object(None, p)
        except Exception:  # noqa: BLE001
            o = None
        print('%s %s' % ('OK     ' if o else 'MISSING', p))
        if o is None:
            miss.append(p)
    if miss:
        fail('missing structs: %s' % miss)
        return False
    passed('all %d needed node structs exist' % len(NEEDED))
    return True


def _probe(b):
    ok = True
    for path in sorted(PINS_USED):
        short = path.rsplit('.', 1)[1]
        b.g.remove('AS12_Probe')
        try:
            n = b.g.node(path, 'AS12_Probe', unreal.Vector2D(-6000.0, -6000.0))
        except H.BwError as e:
            fail('probe %s: %s' % (short, e))
            ok = False
            continue
        try:
            got = b.g.struct_of(n)
            miss = [p for p in sorted(PINS_USED[path]) if b.g.g.find_pin(n + '.' + p) is None]
            if miss:
                fail('probe %s (%s): missing pins %s (top: %s)' % (short, got, miss,
                                                                  [x.get_name() for x in b.g.node_obj(n).get_pins()]))
                ok = False
            else:
                passed('probe %s (%s): %d pin paths exist' % (short, got, len(PINS_USED[path])))
        finally:
            b.g.remove(n)
    return ok


def _get_rig():
    eal = unreal.EditorAssetLibrary
    mode = MODE
    if eal.does_asset_exist(H.RIG_PATH):
        refs = [str(r) for r in eal.find_package_referencers_for_asset(H.RIG_PATH, False) if str(r) != H.RIG_PATH]
        if refs:
            info('referencers of CR_Airship: %s' % refs)
        if mode == 'recreate' and refs and not RECREATE_EVEN_IF_REFERENCED:
            warn('CR_Airship is referenced (%s): REUSING it (nodes rebuilt, variables kept)' % refs)
            mode = 'reuse'
    rig = H.get_or_create_rig(H.RIG_PATH, H.SKM_PATH, recreate=(mode == 'recreate'), import_bones=True)
    return rig, mode


def _check_bones(rig):
    names = H.bone_names(rig)
    ok = len(names) == 118
    (passed if ok else fail)('rig hierarchy has %d bones (want 118)' % len(names))
    bad = [b for b in names if b != 'root' and H.parent_of(rig, b) in ('', 'None')]
    if bad:
        fail('bones without parent: %s' % bad)
        ok = False
    for b in ['Hull'] + ['Thruster_' + p for p in PODS] + ['Turbine_' + s for s in FANS] + ['Rudder', 'Helm'] + \
            ['Cannon_' + c for c in CANNONS] + ['SearchLight_' + L for L in LIGHTS]:
        want = 'root' if b == 'Hull' else 'Hull'
        if H.parent_of(rig, b) != want:
            fail('%s parent %s (want %s)' % (b, H.parent_of(rig, b), want))
            ok = False
    return ok, names


def _variables(rig):
    for n, cpp, d in PUBLIC_VARS:
        H.ensure_variable(rig, n, cpp, True, False, d)
    for n, cpp, d in PRIVATE_VARS:
        H.ensure_variable(rig, n, cpp, False, False, d)
    have = H.member_variables(rig)
    want = dict((n, cpp) for n, cpp, _ in PUBLIC_VARS + PRIVATE_VARS)
    extra = sorted(set(have) - set(want))
    if extra:
        warn('extra rig variables (kept): %s' % extra)
    for n, cpp in want.items():
        v = have.get(n)
        if v is None:
            fail('variable %s missing' % n)
            continue
        pub = bool(v.get_editor_property('public'))
        wpub = n != 'bDeathKickDone'
        t = str(v.get_editor_property('cpp_type'))
        if pub != wpub or t != cpp:
            fail('variable %s: %s public=%s (want %s public=%s)' % (n, t, pub, cpp, wpub))


# ---------------------------------------------------------------------------------- Construction
def _c_bodies(b, geo, solver, prefix, kinds, common, plan, blk, row0):
    """plan: [(bone, kind, collision_dict)], returns {bone: node name}"""
    out = {}
    for i, (bn, kind, coll) in enumerate(plan):
        mv, mass, ld, ad = kinds[kind]
        n = b.c.add(b.unit(solver, P + 'RigUnit_AddPhysicsBody', prefix + bn, blk.at(i % 8, row0 + i // 8)))
        b.g.setp(n + '.Owner', bone(bn))
        b.setmany(n, common)
        b.setmany(n, {'BodyData.MovementType': mv, 'Dynamics.MassOverride': mass, 'Dynamics.LinearDamping': ld,
                      'Dynamics.AngularDamping': ad})
        if solver == 'wreck' and kind in WRECK_CCD_KINDS:
            b.setmany(n, {'BodyData.bEnableCCD': True})       # V2
        for k, v in coll.items():
            b.g.setp(n + '.Collision.' + k, v)
        out[bn] = n
    return out


def _part_plan(geo, for_wreck):
    plan = []
    if for_wreck:
        # one flat deck pad per cannon under its carriage + barrel footprint (+-20 cm), top 2 cm below the carriage's lowest
        # wheel, 30 cm thick: the limp carriages (collision with the hull re-enabled on their joints) rest on it
        pads = []
        for c in CANNONS:
            cb = 'Cannon_' + c
            cmn, cmx = geo.aabb(cb, cb + '_Quoin', cb + '_Wheel_FL', cb + '_Wheel_FR', cb + '_Wheel_BL', cb + '_Wheel_BR')
            bmn, bmx = geo.aabb(cb + '_Barrel')
            top = cmn[2] - 2.0
            mn = [min(cmn[0], bmn[0]) - 20.0, min(cmn[1], bmn[1]) - 20.0, top - 30.0]
            mx = [max(cmx[0], bmx[0]) + 20.0, max(cmx[1], bmx[1]) + 20.0, top]
            pads.append(geo.box_text('Hull', mn, mx, 'DeckPad_' + c))
            b_data = geo.__dict__.setdefault('pads', {})
            b_data[c] = {'min': [round(x, 1) for x in mn], 'max': [round(x, 1) for x in mx]}
        # R5: deck / gantry slabs (as_20b), 2 cm under the surveyed surfaces, already cut around the Wreck bodies
        slabs = H.read_json(SLABS_JSON)['boxes']
        for sb in slabs:
            pads.append(geo.box_text('Hull', sb['min'], sb['max'], sb['name']))
        geo.__dict__['slab_count'] = len(slabs)
        plan.append(('Hull', 'hull', {'Boxes': '(%s)' % ','.join(pads)}))
    else:
        plan.append(('Hull', 'hull', {'Spheres': '((Radius=50.0))'}))
    for p in PODS:
        t = 'Thruster_' + p
        mn, mx = geo.aabb(t) if for_wreck else geo.aabb(t, t + '_Nozzle')
        plan.append((t, 'thruster', {'Boxes': '(%s)' % geo.box_text(t, mn, mx, 'Pod')}))
    for s in FANS:
        t = 'Turbine_' + s
        mn, mx = geo.aabb(t, t + '_Rotor')
        plan.append((t, 'turbine', {'Boxes': '(%s)' % geo.box_text(t, mn, mx, 'Nacelle')}))
        mn, mx = geo.aabb(t + '_Rod')                        # R6: Wreck rods too (limp, see _c_wreck)
        plan.append((t + '_Rod', 'rod', {'Boxes': '(%s)' % geo.box_text(t + '_Rod', mn, mx, 'Rod')}))
    mn, mx = geo.aabb('Rudder')
    plan.append(('Rudder', 'rudder', {'Boxes': '(%s)' % geo.box_text('Rudder', mn, mx, 'Blade')}))
    for c in CANNONS:
        cb = 'Cannon_' + c
        mn, mx = geo.aabb(cb, cb + '_Quoin', cb + '_Wheel_FL', cb + '_Wheel_FR', cb + '_Wheel_BL', cb + '_Wheel_BR')
        plan.append((cb, 'carriage', {'Boxes': '(%s)' % geo.box_text(cb, mn, mx, 'Carriage')}))
        mn, mx = geo.aabb(cb + '_Barrel')
        plan.append((cb + '_Barrel', 'barrel', {'Boxes': '(%s)' % geo.box_text(cb + '_Barrel', mn, mx, 'Barrel')}))
    for L in LIGHTS:
        sb = 'SearchLight_' + L
        mn, mx = geo.aabb(sb, sb + '_Head')
        plan.append((sb, 'light', {'Boxes': '(%s)' % geo.box_text(sb, mn, mx, 'PostHead')}))
    return plan


def _c_wreck(b, geo):
    blk = b.block('wreck', 'Construction 1: WreckSolver on Hull (Component space, world collision All x1.6): kinematic '
                  'Hull = cannon deck pads + deck / gantry slabs; break-off parts (pods, nacelles, rudder, searchlight '
                  'posts) without joints; cannons and turbine rods jointed limp (soft 20-30 deg, no drive). Spawned '
                  'FIRST: these bodies are K(bone, PhysicsBody)', dx=380.0, dy=300.0)
    s = b.c.add(b.unit('wreck', P + 'RigUnit_SpawnPhysicsSolver', 'C_WreckSolver', blk.at(0, 0)))
    b.setmany(s, WRECK_SOLVER_PINS)
    mk = {}
    for i, (name, (path, pins)) in enumerate(sorted(MAKERS_WRECK.items())):
        mk[name] = b.unit('wreck', path, name, blk.at(1 + i, 0))
        b.setmany(mk[name], pins)
    plan = _part_plan(geo, True)
    bodies = _c_bodies(b, geo, 'wreck', 'C_WBody_', WRECK_KIND, BODY_COMMON_WRECK, plan, blk, 1)
    b.data['wreck_bodies'] = [p[0] for p in plan]
    b.data['deck_pads'] = getattr(geo, 'pads', {})
    b.data['deck_slabs'] = getattr(geo, 'slab_count', 0)
    joints = []
    wj = []
    for c in CANNONS:
        cb = 'Cannon_' + c
        wj += [(cb, 'Hull', 'C_WLimpCarriage'), (cb + '_Barrel', cb, 'C_WLimpBarrel')]
    for s_ in FANS:                                           # R6: limp rods on their (break-off) nacelles
        wj.append(('Turbine_%s_Rod' % s_, 'Turbine_' + s_, 'C_WLimpBarrel'))
    for k, (child, parent, jd) in enumerate(wj):
        n = b.c.add(b.unit('wreck', P + 'RigUnit_AddPhysicsJoint', 'C_WJoint_' + child, blk.at(k % 8, 5 + k // 8)))
        b.g.setp(n + '.Owner', bone(child))
        b.g.link(bodies[parent] + '.PhysicsBodyComponentKey', n + '.ParentBodyComponentKey')
        b.g.link(bodies[child] + '.PhysicsBodyComponentKey', n + '.ChildBodyComponentKey')
        if parent == 'Hull':
            # carriage: the maker's cone/twist limits by sub-pin link, collision with the hull deck pads kept on
            b.g.link(mk[jd] + '.JointData.ConeConstraint', n + '.JointData.ConeConstraint')
            b.g.link(mk[jd] + '.JointData.TwistConstraint', n + '.JointData.TwistConstraint')
            b.g.setp(n + '.JointData.bDisableCollision', False)
        else:
            b.g.link(mk[jd] + '.JointData', n + '.JointData')
        b.g.link(mk['C_WNoDrive'] + '.DriveData', n + '.DriveData')
        joints.append(child)
    b.data['wreck_joints'] = joints
    b.close(blk)


def _c_fx(b, geo):
    blk = b.block('fx', 'Construction 2: FxSolver on root (Component space, no world collision, gravity 0): kinematic '
                  'Hull; pods (soft 1 deg cone), nacelles (soft yaw stop 12 deg), rods (pendulum), rudder, cannon carriages (linear+angular '
                  'drive, 80 cm linear sphere) and barrels, searchlight posts (soft 4 deg); SLERP drives to the control '
                  'pose. Keys linked from the body nodes (these are PhysicsBody_2)', dx=380.0, dy=300.0)
    s = b.c.add(b.unit('fx', P + 'RigUnit_SpawnPhysicsSolver', 'C_FxSolver', blk.at(0, 0)))
    b.setmany(s, FX_SOLVER_PINS)
    mk = {}
    for i, (name, (path, pins)) in enumerate(sorted(MAKERS_FX.items())):
        mk[name] = b.unit('fx', path, name, blk.at(1 + i, 0))
        b.setmany(mk[name], pins)
    plan = _part_plan(geo, False)
    bodies = _c_bodies(b, geo, 'fx', 'C_FBody_', FX_KIND, BODY_COMMON_FX, plan, blk, 1)
    b.data['fx_bodies'] = [p[0] for p in plan]
    jplan = []
    for p in PODS:
        jplan.append(('Thruster_' + p, 'Hull', 'C_FJThruster', 'C_FDrvThruster', None))
    for s_ in FANS:
        jplan.append(('Turbine_' + s_, 'Hull', 'C_FJTurbine', 'C_FDrvTurbine', None))     # R1: soft yaw stop at 12
        jplan.append(('Turbine_%s_Rod' % s_, 'Turbine_' + s_, 'C_FJRod', 'C_FDrvRod', None))
    jplan.append(('Rudder', 'Hull', None, 'C_FDrvRudder', None))
    for c in CANNONS:
        jplan.append(('Cannon_' + c, 'Hull', None, 'C_FDrvCarriage', CARRIAGE_JOINT_PINS))
        jplan.append(('Cannon_%s_Barrel' % c, 'Cannon_' + c, None, 'C_FDrvBarrel', None))
    for L in LIGHTS:
        jplan.append(('SearchLight_' + L, 'Hull', 'C_FJPost', 'C_FDrvPost', None))
    for i, (child, parent, jd, dd, extra) in enumerate(jplan):
        n = b.c.add(b.unit('fx', P + 'RigUnit_AddPhysicsJoint', 'C_FJoint_' + child, blk.at(i % 8, 5 + i // 8)))
        b.g.setp(n + '.Owner', bone(child))
        b.g.link(bodies[parent] + '.PhysicsBodyComponentKey', n + '.ParentBodyComponentKey')
        b.g.link(bodies[child] + '.PhysicsBodyComponentKey', n + '.ChildBodyComponentKey')
        if jd:
            b.g.link(mk[jd] + '.JointData', n + '.JointData')
        if extra:
            b.setmany(n, extra)
        b.g.link(mk[dd] + '.DriveData', n + '.DriveData')
    b.data['fx_joints'] = [j[0] for j in jplan]
    b.close(blk)


def _c_instantiate(b):
    blk = b.block('construction', 'Construction 3: instantiate both solvers at spawn', dx=380.0)
    for i, (nm, key) in enumerate((('C_InstWreck', WRECK), ('C_InstFx', FX))):
        n = b.c.add(b.unit('construction', P + 'RigUnit_InstantiatePhysics', nm, blk.at(i, 0)))
        b.g.setp(n + '.PhysicsSolverComponentKey', key)
    b.close(blk)


# ---------------------------------------------------------------------------------- Forwards Solve
def _rad(b, stage, var, tag, pos_get, pos_rad):
    gv = b.var_get(stage, var, 'F_Get_' + tag, pos_get)
    r = b.unit(stage, S['MathFloatRad'], 'F_Rad_' + tag, pos_rad)
    b.g.link(gv, r + '.Value')
    return r + '.Result', gv


def _quat(b, stage, name, axis_local, angle_pin, pos):
    q = b.unit(stage, S['MathQuaternionFromAxisAndAngle'], name, pos)
    b.g.setp(q + '.Axis', vec(*axis_local))
    b.g.link(angle_pin, q + '.Angle')
    return q + '.Result'


def _set_rot(b, geo, stage, bn, quat_pin, blk, col, row):
    """Local rotation = rest local rotation * Q (Q about a bone-local axis); identity rest -> Q directly."""
    src = quat_pin
    if not geo.local_rest_identity(bn):
        it = b.unit(stage, S['GetTransform'], 'F_Init_' + bn, blk.at(col, row + 1))
        b.setmany(it, {'Item': bone(bn), 'Space': 'LocalSpace', 'bInitial': True})
        qm = b.unit(stage, S['MathQuaternionMul'], 'F_QNew_' + bn, blk.at(col + 1, row + 1))
        b.g.link(it + '.Transform.Rotation', qm + '.A')
        b.g.link(quat_pin, qm + '.B')
        src = qm + '.Result'
        b.data.setdefault('non_identity_rest', []).append(bn)
    s = b.f.add(b.unit(stage, S['SetRotation'], 'F_Set_' + bn, blk.at(col, row)))
    b.setmany(s, {'Item': bone(bn), 'Space': 'LocalSpace', 'bInitial': False, 'Weight': 1.0,
                  'bPropagateToChildren': True})
    b.g.link(src, s + '.Value')
    return s


def _f_thrusters(b, geo):
    blk = b.block('thruster', 'Forwards 1: nozzles (pitch about +Y: + swings the exit aft; roll about +X: + exit toward '
                  '+Y) and petal flare (each petal about its hinge axis A x d, baked from the rest pose; + opens)',
                  dx=300.0, dy=220.0)
    axes = {}
    for i, p in enumerate(PODS):
        r0 = 3 * i
        t = 'Thruster_' + p
        nz = t + '_Nozzle'
        pr, _ = _rad(b, 'thruster', 'NozzlePitchDeg_' + p, 'Pitch_' + p, blk.at(0, r0), blk.at(1, r0))
        rr, _ = _rad(b, 'thruster', 'NozzleRollDeg_' + p, 'Roll_' + p, blk.at(0, r0 + 1), blk.at(1, r0 + 1))
        qp = _quat(b, 'thruster', 'F_QPitch_' + p, geo.local_axis(nz, (0, 1, 0)), pr, blk.at(2, r0))
        qr = _quat(b, 'thruster', 'F_QRoll_' + p, geo.local_axis(nz, (1, 0, 0)), rr, blk.at(2, r0 + 1))
        qc = b.unit('thruster', S['MathQuaternionMul'], 'F_QNozzle_' + p, blk.at(3, r0))
        b.g.link(qp, qc + '.A')
        b.g.link(qr, qc + '.B')
        _set_rot(b, geo, 'thruster', nz, qc + '.Result', blk, 4, r0)
        fr, _ = _rad(b, 'thruster', 'NozzleFlareDeg_' + p, 'Flare_' + p, blk.at(5, r0), blk.at(6, r0))
        A = geo.nozzle_axis(p)
        axes[p] = {'A': [round(x, 5) for x in A], 'petals': {}}
        for k in range(12):
            pt = '%s_Petal%02d' % (t, k)
            h, d, _ = geo.petal_hinge(p, k)
            hl = geo.local_axis(pt, h)
            col = 7 + (k % 6) * 2
            row = r0 + (k // 6)
            q = _quat(b, 'thruster', 'F_QFlare_%s_%02d' % (p, k), hl, fr, blk.at(col, row))
            _set_rot(b, geo, 'thruster', pt, q, blk, col + 1, row)
            axes[p]['petals'][pt] = {'h_cs': [round(x, 5) for x in h], 'd_cs': [round(x, 5) for x in d]}
    b.data['thruster_axes'] = axes
    b.close(blk)


def _f_turbines(b, geo):
    blk = b.block('turbine', 'Forwards 2: turbine yaw about +Z (+ turns the fan axis from +X toward +Y), rotor spin about '
                  'the duct axis (+X at rest, follows the yaw)', dx=300.0)
    for i, s in enumerate(FANS):
        t = 'Turbine_' + s
        yr, _ = _rad(b, 'turbine', 'TurbineYawDeg_' + s, 'Yaw_' + s, blk.at(0, 2 * i), blk.at(1, 2 * i))
        q = _quat(b, 'turbine', 'F_QYaw_' + s, geo.local_axis(t, (0, 0, 1)), yr, blk.at(2, 2 * i))
        _set_rot(b, geo, 'turbine', t, q, blk, 3, 2 * i)
        rr, _ = _rad(b, 'turbine', 'RotorAngleDeg_' + s, 'Rotor_' + s, blk.at(4, 2 * i), blk.at(5, 2 * i))
        q = _quat(b, 'turbine', 'F_QRotor_' + s, geo.local_axis(t + '_Rotor', (1, 0, 0)), rr, blk.at(6, 2 * i))
        _set_rot(b, geo, 'turbine', t + '_Rotor', q, blk, 7, 2 * i)
    b.close(blk)


def _f_steer(b, geo):
    blk = b.block('steer', 'Forwards 3: rudder about +Z (+ trailing edge toward -Y), helm wheel about +X (axle), '
                  'standard rotations as RIG_CONTRACT 5 pins them', dx=300.0)
    rr, _ = _rad(b, 'steer', 'RudderDeg', 'Rudder', blk.at(0, 0), blk.at(1, 0))
    q = _quat(b, 'steer', 'F_QRudder', geo.local_axis('Rudder', (0, 0, 1)), rr, blk.at(2, 0))
    _set_rot(b, geo, 'steer', 'Rudder', q, blk, 3, 0)
    wr, _ = _rad(b, 'steer', 'WheelAngleDeg', 'Wheel', blk.at(0, 1), blk.at(1, 1))
    q = _quat(b, 'steer', 'F_QWheel', geo.local_axis('Helm_Wheel', (1, 0, 0)), wr, blk.at(2, 1))
    _set_rot(b, geo, 'steer', 'Helm_Wheel', q, blk, 3, 1)
    b.close(blk)


def _offset(b, stage, bn, vec_pin, pos):
    n = b.f.add(b.unit(stage, K_OFFSET, 'F_Offset_' + bn, pos))
    b.setmany(n, {'Item': bone(bn), 'Weight': 1.0, 'bPropagateToChildren': True})
    b.g.link(vec_pin, n + '.OffsetTransform.Translation')
    return n


def _f_cannons(b, geo):
    blk = b.block('cannon', 'Forwards 4: cannons: yaw about +Z; recoil = Offset Transform (applied in the yawed carriage '
                  'frame) along -aim by CannonRecoilCm; elevation about the truck axle e (e x aim = up: + raises the '
                  'muzzle); quoin slides clamp(2.4 cm/deg * elev, 0, 15) along -aim; truck wheels roll recoil/22 cm rad '
                  'about e', dx=300.0, dy=220.0)
    axes = {}
    for i, c in enumerate(CANNONS):
        r0 = 3 * i
        cb = 'Cannon_' + c
        aim, e, route = geo.cannon_axes(c)
        axes[c] = {'aim_cs': [round(x, 5) for x in aim], 'elev_axis_cs': [round(x, 5) for x in e], 'route': route}
        # yaw
        yr, _ = _rad(b, 'cannon', 'CannonYawDeg_' + c, 'CYaw_' + c, blk.at(0, r0), blk.at(1, r0))
        q = _quat(b, 'cannon', 'F_QCYaw_' + c, geo.local_axis(cb, (0, 0, 1)), yr, blk.at(2, r0))
        _set_rot(b, geo, 'cannon', cb, q, blk, 3, r0)
        # recoil along -aim (carriage frame)
        grec = b.var_get('cannon', 'CannonRecoilCm_' + c, 'F_Get_Recoil_' + c, blk.at(4, r0))
        sc = b.vec_unit('cannon', K_VSCALE, 'F_RecoilVec_' + c, blk.at(5, r0), 'Value')
        b.g.setp(sc + '.Value', vec(*geo.local_vec(cb, [-x for x in aim])))
        b.g.link(grec, sc + '.Factor')
        _offset(b, 'cannon', cb, sc + '.Result', blk.at(6, r0))
        # elevation
        er, gel = _rad(b, 'cannon', 'CannonElevDeg_' + c, 'CElev_' + c, blk.at(7, r0), blk.at(8, r0))
        q = _quat(b, 'cannon', 'F_QCElev_' + c, geo.local_axis(cb + '_Barrel', e), er, blk.at(9, r0))
        _set_rot(b, geo, 'cannon', cb + '_Barrel', q, blk, 10, r0)
        # quoin
        qm = b.unit('cannon', S['MathFloatMul'], 'F_QuoinMul_' + c, blk.at(7, r0 + 1))
        b.g.link(gel, qm + '.A')
        b.g.setp(qm + '.B', QUOIN_CM_PER_DEG)
        cl = b.unit('cannon', S['MathFloatClamp'], 'F_QuoinClamp_' + c, blk.at(8, r0 + 1))
        b.g.link(qm + '.Result', cl + '.Value')
        b.setmany(cl, {'Minimum': 0.0, 'Maximum': QUOIN_MAX_CM})
        qv = b.vec_unit('cannon', K_VSCALE, 'F_QuoinVec_' + c, blk.at(9, r0 + 1), 'Value')
        b.g.setp(qv + '.Value', vec(*geo.local_vec(cb + '_Quoin', [-x for x in aim])))
        b.g.link(cl + '.Result', qv + '.Factor')
        _offset(b, 'cannon', cb + '_Quoin', qv + '.Result', blk.at(10, r0 + 1))
        # truck wheels: angle (rad) = recoil / radius about e
        wm = b.unit('cannon', S['MathFloatMul'], 'F_WheelRoll_' + c, blk.at(4, r0 + 1))
        b.g.link(grec, wm + '.A')
        b.g.setp(wm + '.B', 1.0 / WHEEL_RADIUS_CM)
        for j, w in enumerate(('FL', 'FR', 'BL', 'BR')):
            wb = '%s_Wheel_%s' % (cb, w)
            q = _quat(b, 'cannon', 'F_QWheel_%s_%s' % (c, w), geo.local_axis(wb, e), wm + '.Result',
                      blk.at(11 + 2 * j, r0))
            _set_rot(b, geo, 'cannon', wb, q, blk, 12 + 2 * j, r0)
    b.data['cannon_axes'] = axes
    b.close(blk)


def _f_lights(b, geo):
    blk = b.block('light', 'Forwards 5: searchlight heads pan about +Z by SearchLightPanDeg (AftL/MidL +, MidR/FwdC -)',
                  dx=300.0)
    pr, _ = _rad(b, 'light', 'SearchLightPanDeg', 'Pan', blk.at(0, 0), blk.at(1, 0))
    for i, L in enumerate(LIGHTS):
        hb = 'SearchLight_%s_Head' % L
        q = _quat(b, 'light', 'F_QPan_' + L, geo.local_axis(hb, (0, 0, LIGHT_PAN_SIGN[L])), pr, blk.at(2 + 2 * i, 0))
        _set_rot(b, geo, 'light', hb, q, blk, 3 + 2 * i, 0)
    b.close(blk)


def _f_death(b, geo):
    blk = b.block('death', 'Forwards 6: StepFx (Alpha = 1 - bIsDead) -> death kick (once: bIsDead and not '
                  'bDeathKickDone and dt > 0 and DeathTime < 0.5 s; VelocityChange in Body space on the Wreck break-off bodies) -> StepWreck '
                  '(Alpha = bIsDead, tracks velocities while alive)', dx=330.0, dy=240.0)
    gd = b.var_get('death', 'bIsDead', 'F_Get_bIsDead', blk.at(0, 0))
    da = b.unit('death', S['MathBoolToFloat'], 'F_DeadAlpha', blk.at(1, 0))
    b.g.link(gd, da + '.Value')
    aa = b.unit('death', S['MathFloatSub'], 'F_AliveAlpha', blk.at(2, 0))
    b.g.setp(aa + '.A', 1.0)
    b.g.link(da + '.Result', aa + '.B')
    sf = b.f.add(b.unit('death', P + 'RigUnit_StepPhysicsSolver1', 'F_StepFx', blk.at(3, 0)))
    b.setmany(sf, STEP_FX_PINS)
    b.g.link(aa + '.Result', sf + '.Alpha')
    if DEATH_KICK:
        gdone = b.var_get('death', 'bDeathKickDone', 'F_Get_KickDone', blk.at(0, 1))
        nd = b.unit('death', K_NOT, 'F_KickNotDone', blk.at(1, 1))
        b.g.link(gdone, nd + '.Value')
        dtn = b.unit('death', K_DT, 'F_KickDT', blk.at(0, 2))
        dtp = b.unit('death', K_GREATER, 'F_KickDTPos', blk.at(1, 2))
        b.g.link(dtn + '.Result', dtp + '.A')
        b.g.setp(dtp + '.B', 0.0)
        a1 = b.unit('death', K_AND, 'F_KickAnd', blk.at(2, 1))
        b.g.link(gd, a1 + '.A')
        b.g.link(nd + '.Result', a1 + '.B')
        fire = b.unit('death', K_AND, 'F_KickFire', blk.at(3, 1))
        b.g.link(a1 + '.Result', fire + '.A')
        b.g.link(dtp + '.Result', fire + '.B')
        # R3: only a fresh death kicks (DeathTime < KICK_FRESH_S): late joiners / re-initialised rigs skip it
        gdt = b.var_get('death', 'DeathTime', 'F_Get_DeathTime', blk.at(2, 3))
        fresh = b.unit('death', K_LESS, 'F_KickFresh', blk.at(3, 3))
        b.g.link(gdt, fresh + '.A')
        b.g.setp(fresh + '.B', KICK_FRESH_S)
        fire2 = b.unit('death', K_AND, 'F_KickFire2', blk.at(4, 2))
        b.g.link(fire + '.Result', fire2 + '.A')
        b.g.link(fresh + '.Result', fire2 + '.B')
        br = b.f.add(b.unit('death', S['ControlFlowBranch'], 'F_KickBranch', blk.at(4, 0)))
        b.g.link(fire2 + '.Result', br + '.Condition')
        t = b.g.chain(br, 'True')
        for i, (bn, (lin, ang)) in enumerate(sorted(KICK.items())):
            n = t.add(b.unit('death', K_FORCE, 'F_Kick_' + bn, blk.at(5 + i % 6, 1 + i // 6)))
            b.g.setp(n + '.PhysicsBodyComponentKey', comp(bn, 'PhysicsBody'))
            b.setmany(n, KICK_FORCE_PINS)
            b.g.setp(n + '.ForceAndTorque.Linear', vec(*geo.local_vec(bn, lin)))
            b.g.setp(n + '.ForceAndTorque.Angular', vec(*geo.local_vec(bn, ang)))
        sd = t.add(b.var_set('death', 'bDeathKickDone', 'F_KickSetDone', blk.at(5, 3)))
        b.g.setp(sd + '.Value', True)
    sw = b.f.add(b.unit('death', P + 'RigUnit_StepPhysicsSolver1', 'F_StepWreck', blk.at(12, 0)))
    b.setmany(sw, STEP_WRECK_PINS)
    b.g.link(da + '.Result', sw + '.Alpha')
    b.close(blk)


def _verify_structs(b):
    bad = [(n, s, b.g.struct_of(n)) for n, s in sorted(b.expect.items()) if b.g.struct_of(n) != s]
    for n, s, got in bad:
        fail('node %s resolved to %r, expected %s' % (n, got, s))
    if not bad:
        passed('all %d unit nodes resolved to the asked-for struct' % len(b.expect))
    return not bad


def _summary(b, summary):
    g = b.g.g
    nodes = list(g.get_nodes())
    summary['total_nodes'] = len(nodes)
    summary['comment_nodes'] = len([n for n in nodes if isinstance(n, unreal.RigVMCommentNode)])
    summary['total_links'] = len(list(g.get_links()))
    summary['stages'] = dict((k, len(v)) for k, v in b.nodes.items())
    info('graph: %d nodes (%d comments), %d links; per stage %s' % (len(nodes), summary['comment_nodes'],
                                                                 summary['total_links'], summary['stages']))


def _main():
    t0 = time.time()
    summary = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'mode': MODE, 'saved': False, 'death_kick': DEATH_KICK}
    if H.pie_running():
        fail('PIE running: nothing changed')
        return summary
    if not _prereqs() or not _paths_ok():
        return summary
    try:
        rig, mode = _get_rig()
    except H.BwError as e:
        fail('rig: %s' % e)
        return summary
    summary['mode'] = mode
    rig.set_auto_vm_recompile(False)
    H.clear_rig_graphs(rig)
    ok, names = _check_bones(rig)
    if not ok:
        fail('hierarchy wrong: not built, not saved')
        return summary
    b = Build(rig)
    if not _probe(b):
        if ABORT_ON_PIN_PROBE_FAIL:
            fail('pin probe failed: nothing built, not saved')
            return summary
    try:
        _variables(rig)
    except H.BwError as e:
        fail('variables: %s' % e)
        return summary
    geo = Geo(rig)
    ev_c = b.g.ensure_event(H.EV_CONSTRUCTION, 'ConstructionEvent', unreal.Vector2D(-700.0, 0.0))
    b._add('construction', ev_c)
    b.c = b.g.chain(ev_c)
    steps = [('Construction wreck', _c_wreck), ('Construction fx', _c_fx), ('Construction instantiate', _c_instantiate),
             ('Forwards event', None), ('Forwards thrusters', _f_thrusters), ('Forwards turbines', _f_turbines),
             ('Forwards steer', _f_steer), ('Forwards cannons', _f_cannons), ('Forwards lights', _f_lights),
             ('Forwards death', _f_death)]
    build_ok = True
    for label, fn in steps:
        ts = time.time()
        try:
            if fn is None:
                b.y += 900.0
                ev = b.g.ensure_event(H.EV_FORWARDS, 'ForwardsSolve', unreal.Vector2D(-700.0, b.y))
                b._add('construction', ev)
                b.f = b.g.chain(ev)
                info('Forwards Solve at y=%.0f' % b.y)
            elif fn in (_c_instantiate,):
                fn(b)
            else:
                fn(b, geo)
            passed('%s built in %.1f s' % (label, time.time() - ts))
        except Exception as e:  # noqa: BLE001
            fail('%s failed: %s' % (label, e))
            for line in traceback.format_exc().rstrip().split('\n'):
                print('INFO:   ' + line)
            build_ok = False
            break
    for i, blk in enumerate(b.blocks):
        try:
            blk.comment(b.g, i)
        except Exception as e:  # noqa: BLE001
            warn('comment: %s' % e)
    structs_ok = _verify_structs(b)
    _summary(b, summary)
    summary['baked'] = b.data
    compile_ok = H.compile_rig(rig)
    summary['status'] = str(rig.get_editor_property('status'))
    summary.update({'build_ok': build_ok, 'compile_ok': compile_ok, 'structs_ok': structs_ok})
    if build_ok and compile_ok and structs_ok:
        summary['saved'] = H.save_rig(H.RIG_PATH)
    elif SAVE_ON_FAIL:
        summary['saved'] = H.save_rig(H.RIG_PATH)
    else:
        warn('CR_Airship NOT saved (build %s compile %s structs %s)' % (build_ok, compile_ok, structs_ok))
    summary['seconds'] = round(time.time() - t0, 1)
    return summary


_as12_summary = {}
try:
    _as12_summary = _main() or {}
except Exception as _e:  # noqa: BLE001
    fail('unexpected: %r' % (_e,))
    for _l in traceback.format_exc().rstrip().split('\n'):
        print('INFO:   ' + _l)
_as12_summary['counts'] = dict(_as12_counts)
try:
    H.write_json('as_12_control_rig', _as12_summary)
except Exception as _e:  # noqa: BLE001
    print('WARN: summary not written %r' % (_e,))
print('RESULT: %s (%d FAIL, %d WARN, %d PASS)' % ('PASS' if not _as12_counts.get('FAIL') else 'FAIL',
                                                 _as12_counts.get('FAIL', 0), _as12_counts.get('WARN', 0),
                                                 _as12_counts.get('PASS', 0)))
