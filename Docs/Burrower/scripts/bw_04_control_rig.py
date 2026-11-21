# bw_04_control_rig.py -- builds CR_Burrower (control_rig_recipe.md Steps 2-5) in the UE 5.8 editor.
#
# Run (inbox harness in the clone's editor, NOT during PIE; the build is synchronous, it needs no frames):
#   Docs/Burrower/scripts/harness/inbox.sh 04 Docs/Burrower/scripts/bw_04_control_rig.py 600
#   grep the .out for FAIL: / WARN:, the last line is RESULT:. Summary: <project>/Saved/Burrower/bw_04_control_rig.json
# Then run the check: Docs/Burrower/scripts/harness/inbox.sh 04b Docs/Burrower/scripts/bw_04b_cr_check.py 600
#
# Bisecting / options: send a small wrapper through the inbox instead of this file, e.g.
#   BW04_STAGES = {'hoses': False, 'wires': False}      # merged into STAGES below
#   BW04_ROTOR_MODE = 'two_set'                          # see ROTOR_MODE
#   exec(open('/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/bw_04_control_rig.py').read())
# Every BW04_<NAME> global overrides <NAME> below (it is popped, so it does not stick to later runs).
#
# Asset handling (HARD RULES 3/4): only /Game/Assets/Enemies/Burrower/CR_Burrower is created, deleted or saved,
# saved by explicit path. Default MODE 'recreate': an existing CR_Burrower (ours) is force-deleted and created again.
# If another asset references it (ABP_Burrower), the script switches to 'reuse' (same asset, every graph node
# removed and rebuilt, variables kept) unless RECREATE_EVEN_IF_REFERENCED is True, because a force delete nulls
# ABP_Burrower's Control Rig class and loses the hand-ticked "Use Pin" boxes. The .out says which mode ran.
#
# Helpers: bw_cr_helpers.py (same folder, verified against the 5.8 source; file:line refs in notes_cr_core.md).
# Plugin node pins: notes_cr_plugins.md. Every unreal.* name used here was also checked against the generated stub
# Intermediate/PythonStub/unreal.py of the clone (written by the editor 2026-11-21 20:05).
#
# =====================================================================================================================
# DEVIATIONS FROM control_rig_recipe.md (what, why)
# =====================================================================================================================
#  1. Asset creation (Step 2.1): unreal.ControlRigBlueprintFactory.create_new_control_rig_asset(path, False), then
#     hierarchy_controller.import_bones_from_skeletal_mesh(SK_Burrower, '', True, True, False, False, False) and
#     set_preview_mesh, instead of create_control_rig_from_skeletal_mesh_or_skeleton(+rename): that one names the
#     asset itself in the mesh folder. The asset is a LEGACY UControlRigBlueprint (like CR_Mech and Epic's 5.8
#     AnimationAssistant toolset), not the 5.8 content-browser default UControlRigRuntimeAsset (notes_cr_core 1).
#  2. Events (Steps 4, 5): a new rig has NO event nodes, so both are added (RigUnit_PrepareForExecution
#     "Construction", RigUnit_BeginExecution "Forwards Solve"); the recipe assumed an existing Forwards Solve.
#  3. Node names (Step 3): MathQuat* do not exist in 5.8 -> RigVMFunction_MathQuaternionFromAxisAndAngle / Mul /
#     Inverse / RotateVector (same pins). RigVMFunction_MathTransformMake is deprecated since 5.7 and NOT used:
#     the rotor spin quaternion is linked into the Rotation sub-pin of Rotor_M1.A (ROTOR_MODE 'subpin'). If that link
#     is refused, or with ROTOR_MODE 'two_set', the equivalent whole-pin form is built: Rotor_M = Offset * J0G,
#     SetTransform(Rotor, Rotor_M), then SetRotation(Rotor, Rotor_M.Rotation * Spin) (notes_cr_core 10). Same result.
#  4. Error handling: RigVM errors raise RuntimeError in 5.8 and set_pin_default_value returns False also when the
#     value is unchanged; the helpers (bw_cr_helpers.RigGraph.setp/link) handle both, the recipe's
#     "if not ...: raise" checks would not.
#  5. Step 5.2 (speed gate) is SKIPPED: UBurrowerAnimInstance already scales WaveAmplitudeDeg/WavePitchAmplitudeDeg
#     with speed (cpp_notes.md). WaveTime is in cycles, so WaveTimeToRadians stays 2*pi. Speed, RotorSpinSpeed and
#     DeathTime exist as public variables (AnimBP pins) but no node reads them.
#  6. Variables: 'float' makes single-precision FFloatProperty (matches the C++ floats, no conversion). The re-pin
#     variables use cpp type '/Script/CoreUObject.Transform' ('FTransform' is not understood by add_member_variable).
#  7. End re-pin (Step 5.6, "recommended"): implemented with one PRIVATE FTransform variable per chain
#     (EndPin_<chain>), written by mutable Set-variable nodes right after 5.4 (EndPin_Store_*) from a GetTransform
#     used only there, and read back after 5.6 (EndPin_Read_* -> SetTransform EndPin_Set_*, Global, no propagation).
#     Variable getters read the variable memory directly, so RigVM's pure-node reuse cannot hand back a stale value.
#     Only chains whose solver stage is on are re-pinned.
#  8. Hose bodies (C6): Solver is set by sub-pin (Solver.PhysicsSolverComponentKey, Solver.bUseAutomaticSolver)
#     instead of one struct string; SourceBone/TargetBone are left unset because unset already means the owning bone
#     (RigPhysicsSolver.cpp:795-799, 816-820); bIncludeInChecksForReset keeps its default True.
#  9. The optional Set Physics Body Update Kinematic From Simulation nodes (C6) are not added: the flag already
#     defaults to true (notes_cr_plugins row 14).
# 10. PA_Burrower is loaded before its path is set on RagdollFromPA.PhysicsAsset (the pin validator only finds
#     loaded objects, notes_cr_plugins row 8); no details-panel fallback is needed.
# 11. RagdollSolver TeleportDetection.PositionChangeThreshold 500 is set as the recipe says although it has no effect
#     in World simulation space (notes_cr_plugins row 4). Harmless, kept so the node matches the recipe table.
# 12. Step 4.4 instantiate nodes are added (INSTANTIATE_IN_CONSTRUCTION): neither instantiate node checks the event,
#     so they do not warn in Construction (notes_cr_plugins row 17).
# 13. Step 3 check: besides the recipe's OK/MISSING path list (printed as written in the recipe, renamed paths say
#     what 5.8 uses), every struct the enabled stages need is checked and the build aborts if one is missing. Then
#     every core node's pins (bw_cr_helpers.verify_core_pins) and every plugin pin path this script sets or links
#     (PINS_USED) are probed on throw-away nodes; a missing pin aborts too (ABORT_ON_PIN_PROBE_FAIL). The recipe's
#     show_pins probe would fail on events (CanOnlyExistOnce), the helper reads existing events instead.
# 14. Build in stages (STAGES) with a node-name prefix per stage, a block of columns per recipe step and a comment
#     node per block; the recipe used one 12-column grid. Construction is laid out above Forwards Solve.
# 15. Template nodes can silently re-resolve to another permutation; after the build every unit node's resolved
#     struct is compared with the struct that was asked for (FAIL per mismatch).
# 16. The _01 particle pins (C9) are kept although 5.8 already forces the root-most particle of each chain
#     kinematic (notes_cr_plugins row 15): harmless, set PIN_ROOT_PARTICLES False to drop them.
# 17. Compile = rig.recompile_vm() + BlueprintEditorLibrary.compile_blueprint(rig) + status check; save =
#     EditorAssetLibrary.save_asset('/Game/Assets/Enemies/Burrower/CR_Burrower', False), only when the build and
#     the compile succeeded (SAVE_ON_FAIL False). The recipe used save_loaded_asset.
# 18. Step 8.1/8.2 are automated in bw_04b_cr_check.py without PIE (rig instance executed from Python).
# 19. No visualization flags are set (debug only, Step 8.3/8.4): tick them by hand on StepRagdoll/StepHoses/StepWires.
# 20. Idempotency: the task asks for delete-and-recreate; that is the default, but when another asset already
#     references CR_Burrower (ABP_Burrower after bw_05) the script reuses the asset (all nodes removed and rebuilt,
#     variables kept) because a force delete nulls that reference and the hand-ticked "Use Pin" boxes
#     (RECREATE_EVEN_IF_REFERENCED overrides; then re-run bw_05 and re-tick the pins).
# 21. Failure handling: the build stops at the first stage that fails, still compiles (to print the compiler's
#     errors) and does NOT save; the .out names the stage and the BW04_STAGES wrapper to bisect with.
# 22. The Step 3 printout shows the recipe's four MathQuat* paths as MISSING on purpose (they do not exist in 5.8);
#     the "needed" list right after it is what decides whether the build runs.
# =====================================================================================================================

import importlib
import json
import math
import os
import sys
import time
import traceback

import unreal

# ------------------------------------------------------------------------------------------------- knobs
STAGES = {'wave': True, 'ragdoll': True, 'rotor': True, 'hoses': True, 'wires': True, 'repin': True}
MODE = 'recreate'                    # 'recreate' (delete our CR_Burrower, create it again) or 'reuse' (clear graphs)
RECREATE_EVEN_IF_REFERENCED = False  # True: recreate even if ABP_Burrower references CR_Burrower (re-run bw_05 then)
ROTOR_MODE = 'subpin'                # 'subpin' (Spin quat -> Rotor_M1.A.Rotation) or 'two_set' (SetTransform+SetRotation)
INSTANTIATE_IN_CONSTRUCTION = True   # recipe 4.4
PIN_ROOT_PARTICLES = True            # recipe C9 pins _01 too (redundant in 5.8, harmless)
ABORT_ON_PIN_PROBE_FAIL = True
SAVE_ON_FAIL = False

_bw04_g = globals()
if 'BW04_STAGES' in _bw04_g:
    STAGES.update(dict(_bw04_g.pop('BW04_STAGES')))
for _bw04_k in ('MODE', 'RECREATE_EVEN_IF_REFERENCED', 'ROTOR_MODE', 'INSTANTIATE_IN_CONSTRUCTION',
                'PIN_ROOT_PARTICLES', 'ABORT_ON_PIN_PROBE_FAIL', 'SAVE_ON_FAIL'):
    if 'BW04_' + _bw04_k in _bw04_g:
        _bw04_g[_bw04_k] = _bw04_g.pop('BW04_' + _bw04_k)

BW04_SCRIPTS_DIR = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts'
if not os.path.isdir(BW04_SCRIPTS_DIR):
    BW04_SCRIPTS_DIR = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs', 'Burrower', 'scripts')
if BW04_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, BW04_SCRIPTS_DIR)
import bw_cr_helpers as H  # noqa: E402
importlib.reload(H)

_bw04_counts = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'INFO': 0}


def _bw04_out(tag, msg):
    _bw04_counts[tag] = _bw04_counts.get(tag, 0) + 1
    print('%s: %s' % (tag, msg))


H._out = _bw04_out          # count the helpers' PASS/FAIL/WARN/INFO lines too (they all go through H._out)
info, warn, passed, fail = H.info, H.warn, H.passed, H.fail

# ------------------------------------------------------------------------------------------------- names
P, D, CR, VM, S = H.P, H.D, H.CR, H.VM, H.S
bone, comp, arr, vec = H.bone, H.comp, H.arr, H.vec
SKEL_PATH = H.BURROWER_DIR + '/SKEL_Burrower'

BODY = ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail']
# chain -> number of numbered bones (_01.._NN), then _end (Burrower_rig_info.json)
HOSE_CHAINS = [('pipe_upperhose_l', 7), ('pipe_upperhose_r', 5)]
CABLE_CHAINS = [('pipe_uppercable_l', 7), ('pipe_uppercable_r', 9)]
SIDE_CHAINS = [('pipe_side_l_a', 7), ('pipe_side_l_b', 7), ('pipe_side_r_a', 7), ('pipe_side_r_b', 7)]
CHAIN_LEN = dict(HOSE_CHAINS + CABLE_CHAINS + SIDE_CHAINS)


def chain_bones(prefix):
    return ['%s_%02d' % (prefix, i) for i in range(1, CHAIN_LEN[prefix] + 1)] + [prefix + '_end']


ALL_BONES = ['root'] + BODY + [b for c, _ in HOSE_CHAINS + CABLE_CHAINS + SIDE_CHAINS for b in chain_bones(c)] + ['Rotor']
EXPECT_PARENT = {'J0_Head': 'root', 'J1_Forequarters': 'J0_Head', 'J2_Midbody': 'J1_Forequarters',
                 'J3_Hindbody': 'J2_Midbody', 'J4_Tail': 'J3_Hindbody', 'Rotor': 'root'}
for _bw04_c in CHAIN_LEN:
    _bw04_bs = chain_bones(_bw04_c)
    EXPECT_PARENT[_bw04_bs[0]] = 'J1_Forequarters'
    for _bw04_i in range(1, len(_bw04_bs)):
        EXPECT_PARENT[_bw04_bs[_bw04_i]] = _bw04_bs[_bw04_i - 1]
EXPECT_REST = {'root': (0.0, 0.0, 0.0), 'J0_Head': (1000.0, 0.0, 180.0), 'J1_Forequarters': (660.0, 0.0, 193.0),
               'J2_Midbody': (260.0, 0.0, 200.0), 'J3_Hindbody': (-260.0, 0.0, 200.0),
               'J4_Tail': (-560.0, 0.0, 202.0)}
ROTOR_REST = (977.9, 0.0, 180.5)

RAGDOLL = comp('root', 'PhysicsSolver')               # SpawnPhysicsSolver names its component PhysicsSolver
HOSE_SOLVER = comp('J1_Forequarters', 'PhysicsSolver')
WIRE = comp('root', 'DynamicsSolver')

# (bone, parent for the axes, index, yaw weight, pitch weight) - recipe 5.1
WAVE_JOINTS = [('J1_Forequarters', 'J0_Head', 1, 0.40, 0.65), ('J2_Midbody', 'J1_Forequarters', 2, 0.60, 0.15),
               ('J3_Hindbody', 'J2_Midbody', 3, 0.80, 0.65), ('J4_Tail', 'J3_Hindbody', 4, 1.00, 1.00)]

# Variables: names and types = UBurrowerAnimInstance properties (Source/Aura/Public/Burrower/BurrowerAnimInstance.h)
PUBLIC_VARS = [('RotorAngleDeg', H.CPP_FLOAT, 0.0), ('RotorSpinSpeed', H.CPP_FLOAT, 0.0), ('WaveTime', H.CPP_FLOAT, 0.0),
               ('WaveAmplitudeDeg', H.CPP_FLOAT, 10.0), ('WavePhasePerJointDeg', H.CPP_FLOAT, 65.0),
               ('WavePitchAmplitudeDeg', H.CPP_FLOAT, 0.0), ('Speed', H.CPP_FLOAT, 0.0), ('bIsDead', H.CPP_BOOL, False),
               ('DeathTime', H.CPP_FLOAT, 0.0)]
PRIVATE_VARS = [('WaveTimeToRadians', H.CPP_FLOAT, 6.2831853)]
REPIN_VAR = 'EndPin_%s'      # + chain name, FTransform, private

# ------------------------------------------------------------------------------------------------- pin values
# Static pin values per node kind (pin path relative to the node -> value). The same dicts feed PINS_USED, which the
# pre-build probe checks, so probe and build cannot drift apart.
RAGDOLL_SOLVER_PINS = {                                  # C1 (notes_cr_plugins 2.1, RigPhysicsData.h:666-836)
    'Owner': bone('root'),
    'SolverSettings.bAutomaticallyAddPhysicsBodyComponents': False,
    'SolverSettings.SimulationSpace': 'World',
    'SolverSettings.CollisionSpace': 'World',
    'SolverSettings.WorldCollisionType': 'Static',
    'SolverSettings.bWorldCollisionIncludePhysics': True,
    'SolverSettings.bWorldCollisionIncludeQuery': False,
    'SolverSettings.WorldCollisionBoundsExpansion': 1.1,
    'SolverSettings.PositionIterations': 8,
    'SolverSettings.VelocityIterations': 2,
    'SolverSettings.ProjectionIterations': 1,
    'SolverSettings.FixedTimeStep': 0.0,
    'SolverSettings.MaxDeltaTime': 0.0334,
    'SolverSettings.MaxTimeSteps': 4,
    'SolverSettings.MaxDepenetrationVelocity': 300.0,
    'TeleportDetection.PositionChangeThreshold': 500.0,
}
RAGDOLL_FROM_PA_PINS = {                                 # C2 (RigPhysicsExecution.h:172-260)
    'PhysicsSolverComponentKey': RAGDOLL,
    'bUseAutomaticSolver': False,
    'PhysicsAsset': H.PA_OBJECT_PATH,
    'BonesToUse': arr([bone(b) for b in BODY]),
    'bEnableJoints': True,
    'bEnableDrives': False,
    'bAddSimSpaceControl': False,
    'bAddParentSpaceControl': False,
    'bMakeHelperBodies': False,
}
RAG_MOVE_PINS = {'MovementType': 'Simulated'}            # C3 + PhysicsBodyComponentKey per body
RAG_DAMP_PINS = {'LinearDamping': 0.1, 'AngularDamping': 1.0}
HOSE_SOLVER_PINS = {                                     # C4
    'Owner': bone('J1_Forequarters'),
    'SolverSettings.bAutomaticallyAddPhysicsBodyComponents': False,
    'SolverSettings.SimulationSpace': 'Component',
    'SolverSettings.CollisionSpace': 'Component',
    'SolverSettings.WorldCollisionType': 'None',
    'SolverSettings.PositionIterations': 12,
    'SolverSettings.VelocityIterations': 1,
    'SolverSettings.FixedTimeStep': 0.0,
    'SolverSettings.MaxDeltaTime': 0.0334,
    'SolverSettings.MaxTimeSteps': 4,
    'SolverSettings.bResetFromEvaluationInterval': True,
    'SolverSettings.EvaluationIntervalThresholdForReset': 0.25,
    'SpaceMotion.InertialForces.Amount': 0.5,
    'SpaceMotion.bClampLinearAcceleration': True,
    'SpaceMotion.MaxLinearAcceleration': 3000.0,
    'SpaceMotion.bClampAngularVelocity': True,
    'SpaceMotion.MaxAngularVelocity': 3.0,              # rad/s (Physics)
    'SpaceMotion.bClampAngularAcceleration': True,
    'SpaceMotion.MaxAngularAcceleration': 20.0,          # rad/s^2
    'SpaceMotion.Drag.LinearDragMultiplier': 0.1,
    'SpaceMotion.Drag.AngularDragMultiplier': 0.3,
    'TeleportDetection.PositionChangeThreshold': 500.0,
    'TeleportDetection.OrientationChangeThreshold': 45.0,
}
HOSE_JOINT_DATA_PINS = {'AngularLimit': vec(12, 12, 12), 'SoftStrength': vec(2, 2, 2), 'SoftDampingRatio': vec(1, 1, 1)}
HOSE_DRIVE_DATA_PINS = {'bEnableAngularDrive': True, 'AngularDriveMode': 'SLERP', 'AngularStrength': 6.0,
                        'AngularDampingRatio': 0.8, 'AngularExtraDamping': 0.0,
                        'SkeletalAnimationVelocityMultiplier': 1.0}
HOSE_BODY_PINS = {'Solver.bUseAutomaticSolver': False, 'Dynamics.MassOverride': 20.0, 'Dynamics.LinearDamping': 0.5,
                  'Dynamics.AngularDamping': 2.0, 'BodyData.CollisionType': 'NoCollision'}
HOSE_END_SPHERES = '((Radius=6.0))'                      # Collision.Spheres on the leaf _end body
WIRE_SOLVER_PINS = {                                     # C7 (RigDynamicsData.h:136-404)
    'Owner': bone('root'),
    'SolverComponentName': 'DynamicsSolver',
    'Settings.SimulationSpace': 'Component',
    'Settings.MaxTimeStep': 0.0167,
    'Settings.MaxNumSteps': 4,
    'Settings.NumIterations': 1,
    'Settings.NumConstraintSubIterations': 4,
    'Settings.bReadBoneOrientations': True,
    'Settings.bReadBonePositions': False,
    'Settings.bResetFromPosition': True,
    'Settings.PositionThresholdForReset': 2000.0,
    'Settings.bResetFromEvaluationInterval': True,
    'Settings.EvaluationIntervalThresholdForReset': 0.25,
    'TeleportDetection.PositionChangeThreshold': 500.0,
    'TeleportDetection.OrientationChangeThreshold': 45.0,
    'SpaceMotion.bClampLinearAcceleration': True,
    'SpaceMotion.MaxLinearAcceleration': 4000.0,
    'SpaceMotion.bClampAngularVelocity': True,
    'SpaceMotion.MaxAngularVelocity': 180.0,             # deg/s (Dynamics)
    'SpaceMotion.bClampAngularAcceleration': True,
    'SpaceMotion.MaxAngularAcceleration': 1440.0,        # deg/s^2
    'SpaceMotion.InertialForces.Amount': 0.6,
    'SpaceMotion.Drag.LinearDragMultiplier': 0.15,
    'SpaceMotion.Drag.AngularDragMultiplier': 0.3,
}
SIDE_PARTICLE_PROPS = dict(Radius=3.6, Mass=1.0, MovementType='Simulated', GravityMultiplier=1.0, Strength=1.5,
                           DampingRatio=0.6, TargetMode=0.7, AngleLimit=40.0, AngleLimitStrength=6.0, Damping=1.5,
                           bCollideWithColliders=True)       # C8 SideHoseChains (node default GravityMultiplier 0!)
CABLE_PARTICLE_PROPS = dict(Radius=3.2, Mass=0.5, MovementType='Simulated', GravityMultiplier=1.0, Strength=3.0,
                            DampingRatio=0.7, TargetMode=0.7, AngleLimit=25.0, AngleLimitStrength=10.0, Damping=2.0,
                            bCollideWithColliders=False)     # C8 CableChains
FLANK_CENTRE_CS = (465.0, 0.0, 170.0)                    # C10, component space; capsule main axis = component +X
FLANK_RADIUS, FLANK_LENGTH = 165.0, 160.0
STEP_RAGDOLL_PINS = {'PhysicsSolverComponentKey': RAGDOLL, 'bTrackVelocitiesDuringPassThrough': True,
                     'DeltaTimeOverride': 0.0, 'SimulationSpaceDeltaTimeOverride': 0.0}   # + Alpha <- DeadAlpha
STEP_HOSES_PINS = {'PhysicsSolverComponentKey': HOSE_SOLVER, 'Alpha': 1.0, 'bTrackVelocitiesDuringPassThrough': True,
                   'DeltaTimeOverride': 0.0}
STEP_WIRES_PINS = {'DynamicsSolverComponentKey': WIRE, 'Alpha': 1.0, 'bTrackVelocitiesDuringPassThrough': True,
                   'DeltaTimeOverride': 0.0}

# struct path -> every pin path (relative to the node) the build sets or links on it
PINS_USED = {
    P + 'RigUnit_SpawnPhysicsSolver': set(RAGDOLL_SOLVER_PINS) | set(HOSE_SOLVER_PINS) | {'PhysicsSolverComponentKey'},
    P + 'RigUnit_HierarchyInstantiateFromPhysicsAsset': set(RAGDOLL_FROM_PA_PINS),
    P + 'RigUnit_HierarchySetPhysicsBodyMovementType': {'PhysicsBodyComponentKey'} | set(RAG_MOVE_PINS),
    P + 'RigUnit_HierarchySetPhysicsBodyDamping': {'PhysicsBodyComponentKey'} | set(RAG_DAMP_PINS),
    P + 'RigUnit_MakeArticulationJointData': set(HOSE_JOINT_DATA_PINS) | {'JointData'},
    P + 'RigUnit_MakeArticulationDriveData': set(HOSE_DRIVE_DATA_PINS) | {'DriveData'},
    P + 'RigUnit_AddPhysicsBody': set(HOSE_BODY_PINS) | {'Owner', 'Solver.PhysicsSolverComponentKey',
                                                         'BodyData.MovementType', 'Collision.Spheres'},
    P + 'RigUnit_AddPhysicsJoint': {'Owner', 'ParentBodyComponentKey', 'ChildBodyComponentKey', 'JointData', 'DriveData'},
    P + 'RigUnit_InstantiatePhysics': {'PhysicsSolverComponentKey'},
    P + 'RigUnit_StepPhysicsSolver1': set(STEP_RAGDOLL_PINS) | set(STEP_HOSES_PINS) | {'Alpha'},
    D + 'RigUnit_SpawnDynamicsSolver1': set(WIRE_SOLVER_PINS) | {'DynamicsSolverComponentKey'},
    D + 'RigUnit_SpawnDynamicsChains': {'DynamicsSolverComponentKey', 'RootBones'} |
                                       {'ParticleProperties.' + k for k in list(SIDE_PARTICLE_PROPS) + list(CABLE_PARTICLE_PROPS)},
    D + 'RigUnit_HierarchySetDynamicsParticleMovementType': {'DynamicsParticleComponentKey', 'MovementType'},
    D + 'RigUnit_SpawnDynamicsCollider': {'Owner', 'DynamicsSolverComponentKey', 'Shapes', 'Shapes.Capsules'},
    D + 'RigUnit_InstantiateDynamics': {'DynamicsSolverComponentKey'},
    D + 'RigUnit_StepDynamicsSolver': set(STEP_WIRES_PINS),
}

# Recipe Step 3 lists, exactly as written in control_rig_recipe.md (printed OK/MISSING as the recipe asks)
RECIPE_VERIFIED = [
    P + 'RigUnit_SpawnPhysicsSolver', P + 'RigUnit_HierarchyInstantiateFromPhysicsAsset',
    P + 'RigUnit_HierarchySetPhysicsBodyMovementType', P + 'RigUnit_HierarchySetPhysicsBodyDamping',
    P + 'RigUnit_AddPhysicsBody', P + 'RigUnit_AddPhysicsJoint', P + 'RigUnit_MakeArticulationJointData',
    P + 'RigUnit_MakeArticulationDriveData', P + 'RigUnit_InstantiatePhysics', P + 'RigUnit_StepPhysicsSolver1',
    P + 'RigUnit_HierarchyAddPhysicsBodyForce', P + 'RigUnit_GetPhysicsSolverSpaceData',
    D + 'RigUnit_SpawnDynamicsSolver1', D + 'RigUnit_SpawnDynamicsChains', D + 'RigUnit_SpawnDynamicsCollider',
    D + 'RigUnit_HierarchySetDynamicsParticleMovementType', D + 'RigUnit_InstantiateDynamics',
    D + 'RigUnit_StepDynamicsSolver', D + 'RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset1',
    D + 'RigUnit_GetDynamicsSolverData',
]
RECIPE_FROM_MEMORY = [
    CR + 'RigUnit_PrepareForExecution', CR + 'RigUnit_BeginExecution', CR + 'RigUnit_GetTransform',
    CR + 'RigUnit_SetTransform', CR + 'RigUnit_SetRotation',
    VM + 'MathFloatMul', VM + 'MathFloatSub', VM + 'MathFloatSin', VM + 'MathFloatCos', VM + 'MathFloatRad',
    VM + 'MathFloatClamp', VM + 'MathBoolToFloat', VM + 'MathQuatFromAxisAndAngle', VM + 'MathQuatMul',
    VM + 'MathQuatInverse', VM + 'MathQuatRotateVector', VM + 'MathTransformMul', VM + 'MathTransformMakeRelative',
    VM + 'MathTransformMake',
]

# ------------------------------------------------------------------------------------------------- layout
BLOCK_COLORS = {'events': (0.35, 0.35, 0.35), 'ragdoll': (0.45, 0.12, 0.12), 'hoses': (0.12, 0.30, 0.45),
                'wires': (0.12, 0.40, 0.18), 'instantiate': (0.30, 0.30, 0.10), 'wave': (0.35, 0.18, 0.45),
                'rotor': (0.50, 0.32, 0.08), 'repin': (0.18, 0.40, 0.40)}
BLOCK_GAP = 420.0


class _Bw04Block(object):
    """A rectangle of node columns for one recipe block; becomes a comment node at the end."""

    def __init__(self, stage, title, x0, y0, dx=380.0, dy=280.0):
        self.stage, self.title = stage, title
        self.x0, self.y0, self.dx, self.dy = float(x0), float(y0), float(dx), float(dy)
        self.lo = None
        self.hi = None

    def at(self, col, row):
        x = self.x0 + self.dx * col
        y = self.y0 + self.dy * row
        self.lo = (x, y) if self.lo is None else (min(self.lo[0], x), min(self.lo[1], y))
        self.hi = (x, y) if self.hi is None else (max(self.hi[0], x), max(self.hi[1], y))
        return unreal.Vector2D(x, y)

    def bottom(self):
        return (self.hi[1] if self.hi else self.y0) + self.dy

    def comment(self, gr, index):
        if self.lo is None:
            return None
        pos = unreal.Vector2D(self.lo[0] - 60.0, self.lo[1] - 110.0)
        size = unreal.Vector2D(self.hi[0] - self.lo[0] + self.dx + 60.0, self.hi[1] - self.lo[1] + self.dy + 150.0)
        r, g_, b = BLOCK_COLORS.get(self.stage, (0.3, 0.3, 0.3))
        color = unreal.LinearColor(r, g_, b, 1.0)
        name = 'Comment_%s_%d' % (self.stage, index)
        # RigVMController.h:463 AddCommentNode(text, position, size, color, node name, undo, python)
        n = H._ue('add_comment_node(%s)' % name, gr.c.add_comment_node, self.title, pos, size, color, name, False, False)
        return n.get_name() if n is not None else None


# ------------------------------------------------------------------------------------------------- build state
class _Bw04Build(object):
    def __init__(self, rig):
        self.rig = rig
        self.g = H.RigGraph(rig)
        self.nodes = {}           # stage -> [node names]
        self.expect = {}          # unit node name -> requested struct short name
        self.blocks = []
        self.rotor_mode = ROTOR_MODE
        self.c = None             # construction exec chain
        self.f = None             # forwards exec chain
        self.y = 0.0

    def _add(self, stage, name):
        self.nodes.setdefault(stage, []).append(name)
        return name

    def unit(self, stage, path, name, pos):
        n = self.g.node(path, name, pos)
        self.expect[n] = path.rsplit('.', 1)[1]
        return self._add(stage, n)

    def var_get(self, stage, var, name, pos):
        pin = self.g.var_get(var, name, pos)
        self._add(stage, pin.rsplit('.', 1)[0])
        return pin

    def var_set(self, stage, var, name, pos):
        return self._add(stage, self.g.var_set(var, name, pos))

    def remove(self, stage, name):
        self.g.remove(name)
        if name in self.nodes.get(stage, []):
            self.nodes[stage].remove(name)
        self.expect.pop(name, None)

    def setmany(self, node, pins):
        for k, v in pins.items():
            self.g.setp(node + '.' + k, v)

    def block(self, stage, title, dx=380.0, dy=280.0):
        b = _Bw04Block(stage, title, 0.0, self.y, dx, dy)
        self.blocks.append(b)
        return b

    def close(self, b):
        self.y = b.bottom() + BLOCK_GAP


# ------------------------------------------------------------------------------------------------- steps
def _bw04_needed_paths():
    need = [S['PrepareForExecution'], S['BeginExecution']]
    if STAGES['wave']:
        need += [S['GetTransform'], S['SetRotation'], S['MathFloatMul'], S['MathFloatSub'], S['MathFloatSin'],
                 S['MathFloatCos'], S['MathFloatRad'], S['MathQuaternionInverse'], S['MathQuaternionRotateVector'],
                 S['MathQuaternionFromAxisAndAngle'], S['MathQuaternionMul']]
    if STAGES['ragdoll']:
        need += [P + 'RigUnit_SpawnPhysicsSolver', P + 'RigUnit_HierarchyInstantiateFromPhysicsAsset',
                 P + 'RigUnit_HierarchySetPhysicsBodyMovementType', P + 'RigUnit_HierarchySetPhysicsBodyDamping',
                 P + 'RigUnit_StepPhysicsSolver1', S['MathBoolToFloat']]
    if STAGES['rotor']:
        need += [S['GetTransform'], S['SetTransform'], S['MathTransformMakeRelative'], S['MathQuaternionInverse'],
                 S['MathQuaternionRotateVector'], S['MathFloatRad'], S['MathQuaternionFromAxisAndAngle'],
                 S['MathTransformMul'], S['SetRotation'], S['MathQuaternionMul']]   # last two: 'two_set' fallback
    if STAGES['hoses']:
        need += [P + 'RigUnit_SpawnPhysicsSolver', P + 'RigUnit_MakeArticulationJointData',
                 P + 'RigUnit_MakeArticulationDriveData', P + 'RigUnit_AddPhysicsBody', P + 'RigUnit_AddPhysicsJoint',
                 P + 'RigUnit_StepPhysicsSolver1']
    if STAGES['wires']:
        need += [D + 'RigUnit_SpawnDynamicsSolver1', D + 'RigUnit_SpawnDynamicsChains',
                 D + 'RigUnit_HierarchySetDynamicsParticleMovementType', D + 'RigUnit_SpawnDynamicsCollider',
                 D + 'RigUnit_StepDynamicsSolver']
    if INSTANTIATE_IN_CONSTRUCTION:
        if STAGES['ragdoll'] or STAGES['hoses']:
            need.append(P + 'RigUnit_InstantiatePhysics')
        if STAGES['wires']:
            need.append(D + 'RigUnit_InstantiateDynamics')
    if STAGES['repin'] and _bw04_repin_chains():
        need += [S['GetTransform'], S['SetTransform']]
    out = []
    for p in need:
        if p not in out:
            out.append(p)
    return out


def _bw04_repin_chains():
    out = []
    if STAGES['hoses']:
        out += [c for c, _ in HOSE_CHAINS]
    if STAGES['wires']:
        out += [c for c, _ in CABLE_CHAINS + SIDE_CHAINS]
    return out


def _bw04_load_struct(p):
    try:
        return unreal.load_object(None, p)
    except Exception:  # noqa: BLE001
        return None


def _bw04_step3_path_check():
    """Recipe Step 3 (as written) + the structs this build needs. Returns False if a needed struct is missing."""
    info('recipe Step 3 node-path check, paths exactly as written in control_rig_recipe.md:')
    for p in RECIPE_VERIFIED + RECIPE_FROM_MEMORY:
        found = _bw04_load_struct(p) is not None
        note = ''
        if p in H.RECIPE_RENAMES:
            note = '   -> 5.8 name: %s (used instead)' % H.RECIPE_RENAMES[p]
        elif p in H.DEPRECATED:
            note = '   -> %s (not used)' % H.DEPRECATED[p]
        print('%s %s%s' % ('OK     ' if found else 'MISSING', p, note))
    info('structs needed by the enabled stages %s:' % sorted(k for k, v in STAGES.items() if v))
    missing = []
    for p in _bw04_needed_paths():
        found = _bw04_load_struct(p) is not None
        print('%s %s' % ('OK     ' if found else 'MISSING', p))
        if not found:
            missing.append(p)
    if missing:
        fail('%d needed node struct(s) missing: %s. Is the plugin enabled (ControlRigPhysics / ControlRigDynamics in '
             'Aura.uproject, editor restarted)? Nothing was built.' % (len(missing), ', '.join(missing)))
        return False
    passed('all %d needed node structs exist' % len(_bw04_needed_paths()))
    return True


def _bw04_prereqs():
    eal = unreal.EditorAssetLibrary
    ok = True
    objs = {}
    for path, cls, what in ((H.SKM_PATH, unreal.SkeletalMesh, 'skeletal mesh'), (SKEL_PATH, unreal.Skeleton, 'skeleton'),
                            (H.PA_PATH, unreal.PhysicsAsset, 'physics asset')):
        if not eal.does_asset_exist(path):
            fail('%s %s does not exist. Run the import (bw_02) / physics asset (bw_03) scripts first.' % (what, path))
            ok = False
            continue
        o = eal.load_asset(path)
        if o is None or not isinstance(o, cls):
            fail('%s is a %s, expected %s' % (path, o.get_class().get_name() if o else 'None', cls.__name__))
            ok = False
            continue
        passed('%s %s exists' % (what, path))
        objs[path] = o
    if not ok:
        return False, objs
    skm = objs[H.SKM_PATH]
    try:
        sk = skm.get_editor_property('skeleton')
        if sk is not None and sk.get_path_name() == objs[SKEL_PATH].get_path_name():
            passed('SK_Burrower uses SKEL_Burrower')
        else:
            warn('SK_Burrower skeleton is %s, expected %s' % (sk.get_path_name() if sk else None, SKEL_PATH))
    except Exception as e:  # noqa: BLE001
        warn('cannot read SK_Burrower.skeleton: %s' % e)
    try:
        pa = skm.get_editor_property('physics_asset')
        if pa is not None and pa.get_path_name() == objs[H.PA_PATH].get_path_name():
            passed('SK_Burrower physics asset is PA_Burrower')
        else:
            warn('SK_Burrower physics asset is %s (expected PA_Burrower; the rig reads PA_Burrower directly, the C++ '
                 'hit collision and fallback ragdoll use the mesh\'s)' % (pa.get_path_name() if pa else None))
    except Exception as e:  # noqa: BLE001
        warn('cannot read SK_Burrower.physics_asset: %s' % e)
    return True, objs


def _bw04_get_rig():
    eal = unreal.EditorAssetLibrary
    mode = MODE
    if mode not in ('recreate', 'reuse'):
        raise H.BwError("MODE must be 'recreate' or 'reuse', not %r" % mode)
    if eal.does_asset_exist(H.RIG_PATH):
        refs = []
        try:
            # EditorAssetLibrary.h:95 FindPackageReferencersForAsset (asset registry, package names)
            refs = [str(r) for r in eal.find_package_referencers_for_asset(H.RIG_PATH, False)]
        except Exception as e:  # noqa: BLE001
            warn('find_package_referencers_for_asset failed (%s); assuming no referencers' % e)
        refs = [r for r in refs if r != H.RIG_PATH]
        if refs:
            info('assets referencing CR_Burrower: %s' % ', '.join(refs))
        if mode == 'recreate' and refs and not RECREATE_EVEN_IF_REFERENCED:
            warn('CR_Burrower is referenced (%s): REUSING it instead of delete-and-recreate (a force delete would null '
                 'the reference, e.g. ABP_Burrower\'s Control Rig class and its "Use Pin" ticks). Every graph node is '
                 'removed and rebuilt, variables are kept. Set BW04_RECREATE_EVEN_IF_REFERENCED = True to recreate.'
                 % ', '.join(refs))
            mode = 'reuse'
        if mode == 'recreate':
            info('MODE recreate: deleting our own %s and creating it again' % H.RIG_PATH)
        else:
            info('MODE reuse: keeping %s, clearing its graphs' % H.RIG_PATH)
    else:
        info('%s does not exist yet: creating it' % H.RIG_PATH)
    rig = H.get_or_create_rig(H.RIG_PATH, H.SKM_PATH, recreate=(mode == 'recreate'), import_bones=True)
    return rig, mode


def _bw04_check_bones(rig):
    names = H.bone_names(rig)
    have = set(names)
    missing = [b for b in ALL_BONES if b not in have]
    if missing:
        fail('rig hierarchy lacks %d bone(s) the rig needs: %s. Fix the import (bw_02) and re-run.'
             % (len(missing), ', '.join(missing[:12]) + (' ...' if len(missing) > 12 else '')))
        return False
    passed('all %d bones the rig uses are in the hierarchy (hierarchy has %d bones)' % (len(ALL_BONES), len(names)))
    extra = [b for b in names if b not in set(ALL_BONES)]
    if extra:
        warn('extra bones in the hierarchy (harmless if they are above root): %s' % ', '.join(extra))
    bad = 0
    for b, p in sorted(EXPECT_PARENT.items()):
        got = H.parent_of(rig, b)
        if got != p:
            fail('bone %s has parent %s, expected %s (the wave axes and chains assume the recipe hierarchy)' % (b, got, p))
            bad += 1
    if not bad:
        passed('all %d parent links match the recipe hierarchy' % len(EXPECT_PARENT))
    H.rest_pose_report(rig, sorted(EXPECT_REST), EXPECT_REST, tol=5.0)
    H.rest_pose_report(rig, ['Rotor'], {'Rotor': ROTOR_REST}, tol=2.0)
    for c in sorted(CHAIN_LEN):
        try:
            p0 = H.tf_pos(H.global_tf(rig, c + '_01', True))
            p1 = H.tf_pos(H.global_tf(rig, c + '_end', True))
            info('chain %-18s _01 (%.1f, %.1f, %.1f)  _end (%.1f, %.1f, %.1f)' % ((c,) + tuple(p0) + tuple(p1)))
        except H.BwError as e:
            warn(str(e))
    try:
        y = H.tf_pos(H.global_tf(rig, 'pipe_side_l_a_01', True))[1]
        info('_l chains are at %s UE Y (recipe expects negative; no effect on the rig, all shapes are Y-symmetric)'
             % ('negative' if y < 0 else 'POSITIVE'))
    except H.BwError:
        pass
    return True


def _bw04_probe_plugin_pins(b):
    needed = set(_bw04_needed_paths())
    ok = True
    for path in sorted(PINS_USED):
        if path not in needed:
            continue
        short = path.rsplit('.', 1)[1]
        tmp = 'BW04_Probe'
        b.g.remove(tmp)
        try:
            name = b.g.node(path, tmp, unreal.Vector2D(-6000.0, -6000.0))
        except H.BwError as e:
            fail('probe %s: %s' % (short, e))
            ok = False
            continue
        try:
            missing = [p for p in sorted(PINS_USED[path]) if b.g.g.find_pin(name + '.' + p) is None]
            if missing:
                tops = [x.get_name() for x in b.g.node_obj(name).get_pins()]
                fail('probe %s: missing pin(s) %s (top-level pins: %s)' % (short, ', '.join(missing), ', '.join(tops)))
                ok = False
            else:
                passed('probe %s: all %d pin paths used by the build exist' % (short, len(PINS_USED[path])))
        finally:
            b.g.remove(name)
    return ok


def _bw04_variables(rig):
    for name, cpp, default in PUBLIC_VARS:
        H.ensure_variable(rig, name, cpp, True, False, default)
    for name, cpp, default in PRIVATE_VARS:
        H.ensure_variable(rig, name, cpp, False, False, default)
    if STAGES['repin']:
        for c in _bw04_repin_chains():
            H.ensure_variable(rig, REPIN_VAR % c, H.CPP_TRANSFORM, False, False, '')
    have = H.member_variables(rig)
    for name, _, _ in PUBLIC_VARS + PRIVATE_VARS:
        v = have.get(name)
        if v is None:
            fail('variable %s missing after ensure_variable' % name)
            continue
        try:
            pub = bool(v.get_editor_property('public'))   # FRigVMGraphVariableDescription.bPublic (RigVMBlueprintLegacy.cpp:998-1001)
        except Exception as e:  # noqa: BLE001
            warn('cannot read the public flag of %s (%s); bw_04b checks it on an instance' % (name, e))
            continue
        want = any(name == n for n, _, _ in PUBLIC_VARS)
        if pub == want:
            passed('variable %s public=%s' % (name, pub))
        else:
            fail('variable %s public=%s, expected %s (eye icon / Instance Editable in the rig editor)' % (name, pub, want))


# ---------------------------------------------------------------------------- Construction blocks
def _bw04_c_ragdoll(b):
    blk = b.block('ragdoll', '4.1 Ragdoll: solver on root (World space, Static world collision), bodies J0..J4 from '
                  'PA_Burrower, all Simulated, damping 0.1 / 1.0', dx=440.0, dy=330.0)
    s = b.c.add(b.unit('ragdoll', P + 'RigUnit_SpawnPhysicsSolver', 'RagdollSolver', blk.at(0, 0)))
    b.setmany(s, RAGDOLL_SOLVER_PINS)
    i = b.c.add(b.unit('ragdoll', P + 'RigUnit_HierarchyInstantiateFromPhysicsAsset', 'RagdollFromPA', blk.at(1, 0)))
    b.setmany(i, RAGDOLL_FROM_PA_PINS)
    for k, bn in enumerate(BODY):
        m = b.c.add(b.unit('ragdoll', P + 'RigUnit_HierarchySetPhysicsBodyMovementType', 'RagSim_' + bn, blk.at(k, 1)))
        b.g.setp(m + '.PhysicsBodyComponentKey', comp(bn, 'PhysicsBody'))
        b.setmany(m, RAG_MOVE_PINS)
        d = b.c.add(b.unit('ragdoll', P + 'RigUnit_HierarchySetPhysicsBodyDamping', 'RagDamp_' + bn, blk.at(k, 2)))
        b.g.setp(d + '.PhysicsBodyComponentKey', comp(bn, 'PhysicsBody'))
        b.setmany(d, RAG_DAMP_PINS)
    b.close(blk)


def _bw04_c_hoses(b):
    blk = b.block('hoses', '4.2 Upper armoured hoses: rigid-body solver on J1_Forequarters (Component space), bodies '
                  '_01.._end (ends kinematic), joints 12 deg + SLERP drive', dx=420.0, dy=330.0)
    hs = b.c.add(b.unit('hoses', P + 'RigUnit_SpawnPhysicsSolver', 'HoseSolver', blk.at(0, 0)))
    b.setmany(hs, HOSE_SOLVER_PINS)
    mj = b.unit('hoses', P + 'RigUnit_MakeArticulationJointData', 'HoseJointData', blk.at(1, 0))
    b.setmany(mj, HOSE_JOINT_DATA_PINS)
    md = b.unit('hoses', P + 'RigUnit_MakeArticulationDriveData', 'HoseDriveData', blk.at(2, 0))
    b.setmany(md, HOSE_DRIVE_DATA_PINS)
    row = 1
    for chain, _ in HOSE_CHAINS:
        bones = chain_bones(chain)
        last = len(bones) - 1
        for k, bn in enumerate(bones):
            n = b.c.add(b.unit('hoses', P + 'RigUnit_AddPhysicsBody', 'HoseBody_' + bn, blk.at(k, row)))
            b.g.setp(n + '.Owner', bone(bn))
            b.g.setp(n + '.Solver.PhysicsSolverComponentKey', HOSE_SOLVER)
            b.setmany(n, HOSE_BODY_PINS)
            b.g.setp(n + '.BodyData.MovementType', 'Kinematic' if k in (0, last) else 'Simulated')
            if k == last:
                b.g.setp(n + '.Collision.Spheres', HOSE_END_SPHERES)
            if k > 0:
                j = b.c.add(b.unit('hoses', P + 'RigUnit_AddPhysicsJoint', 'HoseJoint_' + bn, blk.at(k, row + 1)))
                b.g.setp(j + '.Owner', bone(bn))
                b.g.setp(j + '.ParentBodyComponentKey', comp(bones[k - 1], 'PhysicsBody'))
                b.g.setp(j + '.ChildBodyComponentKey', comp(bn, 'PhysicsBody'))
                b.g.link(mj + '.JointData', j + '.JointData')
                b.g.link(md + '.DriveData', j + '.DriveData')
        row += 2
    b.close(blk)


def _bw04_flank_shapes(rig):
    tm_comp = H.capsule_tm_along(unreal.Vector(1.0, 0.0, 0.0), unreal.Vector(*FLANK_CENTRE_CS))
    tm_local = H.comp_to_bone_local(rig, tm_comp, 'J1_Forequarters')
    j1 = H.global_tf(rig, 'J1_Forequarters', True)
    try:
        back = unreal.MathLibrary.compose_transforms(tm_local, j1)     # KismetMathLibrary.h:3963, A * B
        err = H.dist(H.tf_pos(back), FLANK_CENTRE_CS)
        (passed if err < 0.5 else fail)('flank capsule TM in J1 space maps back to component centre %s (error %.3f cm)'
                                        % (FLANK_CENTRE_CS, err))
    except Exception as e:  # noqa: BLE001
        warn('round-trip check of the flank TM skipped: %s' % e)
    t = tm_local.translation
    q = tm_local.rotation
    info('flank capsule TM in J1_Forequarters space: T (%.2f, %.2f, %.2f) Q (%.4f, %.4f, %.4f, %.4f)'
         % (t.x, t.y, t.z, q.x, q.y, q.z, q.w))
    return tm_local


def _bw04_c_wires(b):
    blk = b.block('wires', '4.3 Upper cables + side hoses: wire solver on root (Component space), chains, both ends '
                  'kinematic, flank capsule collider on J1', dx=400.0, dy=300.0)
    ds = b.c.add(b.unit('wires', D + 'RigUnit_SpawnDynamicsSolver1', 'WireSolver', blk.at(0, 0)))
    b.setmany(ds, WIRE_SOLVER_PINS)
    for col, (name, chains, props) in ((1, ('SideHoseChains', SIDE_CHAINS, SIDE_PARTICLE_PROPS)),
                                       (2, ('CableChains', CABLE_CHAINS, CABLE_PARTICLE_PROPS))):
        n = b.c.add(b.unit('wires', D + 'RigUnit_SpawnDynamicsChains', name, blk.at(col, 0)))
        b.g.setp(n + '.DynamicsSolverComponentKey', WIRE)
        b.g.setp(n + '.RootBones', arr([bone(c + '_01') for c, _ in chains]))
        b.setmany(n, dict(('ParticleProperties.' + k, v) for k, v in props.items()))
    for col, (ch, _) in enumerate(SIDE_CHAINS + CABLE_CHAINS):
        for row, suffix in ((1, '_01'), (2, '_end')):
            if suffix == '_01' and not PIN_ROOT_PARTICLES:
                continue
            bn = ch + suffix
            m = b.c.add(b.unit('wires', D + 'RigUnit_HierarchySetDynamicsParticleMovementType', 'Pin_' + bn,
                               blk.at(col, row)))
            b.g.setp(m + '.DynamicsParticleComponentKey', comp(bn, 'DynamicsParticle'))
            b.g.setp(m + '.MovementType', 'Kinematic')
    col_n = b.c.add(b.unit('wires', D + 'RigUnit_SpawnDynamicsCollider', 'FlankCollider', blk.at(3, 0)))
    b.g.setp(col_n + '.Owner', bone('J1_Forequarters'))
    b.g.setp(col_n + '.DynamicsSolverComponentKey', WIRE)
    tm_local = _bw04_flank_shapes(b.rig)
    tm_text = tm_local.export_text()
    capsule = '(Name="Flank",TM=%s,Radius=%r,Length=%r)' % (tm_text, FLANK_RADIUS, FLANK_LENGTH)
    try:
        b.g.setp(col_n + '.Shapes', '(Capsules=(%s))' % capsule)
    except H.BwError as e:
        warn('setting FlankCollider.Shapes as one struct failed (%s); trying the array and its element sub-pins' % e)
        b.g.setp(col_n + '.Shapes.Capsules', '((Name="Flank",Radius=%r,Length=%r))' % (FLANK_RADIUS, FLANK_LENGTH))
        el = col_n + '.Shapes.Capsules.0.TM'                 # array element sub-pins are named 0, 1, ...
        try:
            b.g.setp(el, tm_text)
        except H.BwError:
            q, t = tm_local.rotation, tm_local.translation
            b.g.setp(el + '.Rotation', '(X=%r,Y=%r,Z=%r,W=%r)' % (q.x, q.y, q.z, q.w))
            b.g.setp(el + '.Translation', vec(t.x, t.y, t.z))
    got = '%s | %s' % (b.g.pin(col_n + '.Shapes').get_default_value(),
                       b.g.pin(col_n + '.Shapes.Capsules').get_default_value())
    info('FlankCollider.Shapes | .Capsules = %s' % got)
    if 'Flank' not in got:
        fail('FlankCollider.Shapes does not contain the Flank capsule; set it by hand (centre %s comp space, axis +X, '
             'r %.0f, core %.0f)' % (FLANK_CENTRE_CS, FLANK_RADIUS, FLANK_LENGTH))
    b.close(blk)


def _bw04_c_instantiate(b):
    blk = b.block('instantiate', '4.4 Instantiate the solvers at spawn (end of Construction)', dx=400.0, dy=280.0)
    col = 0
    if STAGES['ragdoll']:
        n = b.c.add(b.unit('ragdoll', P + 'RigUnit_InstantiatePhysics', 'InstRagdoll', blk.at(col, 0)))
        b.g.setp(n + '.PhysicsSolverComponentKey', RAGDOLL)
        col += 1
    if STAGES['hoses']:
        n = b.c.add(b.unit('hoses', P + 'RigUnit_InstantiatePhysics', 'InstHoses', blk.at(col, 0)))
        b.g.setp(n + '.PhysicsSolverComponentKey', HOSE_SOLVER)
        col += 1
    if STAGES['wires']:
        n = b.c.add(b.unit('wires', D + 'RigUnit_InstantiateDynamics', 'InstWires', blk.at(col, 0)))
        b.g.setp(n + '.DynamicsSolverComponentKey', WIRE)
    b.close(blk)


# ---------------------------------------------------------------------------- Forwards Solve blocks
def _bw04_f_events(b):
    b.y += 1200.0
    ev = b.g.ensure_event(H.EV_FORWARDS, 'ForwardsSolve', unreal.Vector2D(-700.0, b.y))
    b._add('events', ev)
    b.f = b.g.chain(ev)
    info('Forwards Solve starts at y=%.0f' % b.y)


def _bw04_f_wave(b):
    blk = b.block('wave', '5.1 Body wave on J1..J4: theta_i = WaveTime*2pi - i*Phase; yaw about the body up, pitch '
                  'about the body side, both in the parent rest frame; NewLocal = QDelta * Local', dx=300.0, dy=230.0)
    gt = b.var_get('wave', 'WaveTime', 'Wave_Get_WaveTime', blk.at(0, 0))
    gk = b.var_get('wave', 'WaveTimeToRadians', 'Wave_Get_WaveTimeToRadians', blk.at(1, 0))
    gp = b.var_get('wave', 'WavePhasePerJointDeg', 'Wave_Get_WavePhasePerJointDeg', blk.at(2, 0))
    ga = b.var_get('wave', 'WaveAmplitudeDeg', 'Wave_Get_WaveAmplitudeDeg', blk.at(3, 0))
    gpa = b.var_get('wave', 'WavePitchAmplitudeDeg', 'Wave_Get_WavePitchAmplitudeDeg', blk.at(4, 0))
    th0 = b.unit('wave', S['MathFloatMul'], 'Wave_Theta0', blk.at(5, 0))
    b.g.link(gt, th0 + '.A')
    b.g.link(gk, th0 + '.B')
    phi = b.unit('wave', S['MathFloatRad'], 'Wave_Phi', blk.at(6, 0))
    b.g.link(gp, phi + '.Value')
    for bn, parent, i, wy, wp in WAVE_JOINTS:
        t = 'W%d_' % i
        ra, rb = 1 + 2 * (i - 1), 2 + 2 * (i - 1)
        lag = b.unit('wave', S['MathFloatMul'], t + 'Lag', blk.at(0, ra))
        b.g.link(phi + '.Result', lag + '.A')
        b.g.setp(lag + '.B', float(i))
        th = b.unit('wave', S['MathFloatSub'], t + 'Theta', blk.at(1, ra))
        b.g.link(th0 + '.Result', th + '.A')
        b.g.link(lag + '.Result', th + '.B')
        sn = b.unit('wave', S['MathFloatSin'], t + 'Sin', blk.at(2, ra))
        b.g.link(th + '.Result', sn + '.Value')
        cs = b.unit('wave', S['MathFloatCos'], t + 'Cos', blk.at(3, ra))
        b.g.link(th + '.Result', cs + '.Value')

        def scaled(amp_pin, weight, trig, tag, col0):
            a = b.unit('wave', S['MathFloatMul'], t + tag + 'Amp', blk.at(col0, ra))
            b.g.link(amp_pin, a + '.A')
            b.g.setp(a + '.B', float(weight))
            r = b.unit('wave', S['MathFloatRad'], t + tag + 'Rad', blk.at(col0 + 1, ra))
            b.g.link(a + '.Result', r + '.Value')
            o = b.unit('wave', S['MathFloatMul'], t + tag, blk.at(col0 + 2, ra))
            b.g.link(r + '.Result', o + '.A')
            b.g.link(trig + '.Result', o + '.B')
            return o + '.Result'

        yaw = scaled(ga, wy, sn, 'Yaw', 4)
        pitch = scaled(gpa, wp, cs, 'Pitch', 7)
        pi_ = b.unit('wave', S['GetTransform'], t + 'ParentInit', blk.at(0, rb))
        b.g.setp(pi_ + '.Item', bone(parent))
        b.g.setp(pi_ + '.Space', 'GlobalSpace')
        b.g.setp(pi_ + '.bInitial', True)
        inv = b.unit('wave', S['MathQuaternionInverse'], t + 'ParentInv', blk.at(1, rb))
        b.g.link(pi_ + '.Transform.Rotation', inv + '.Value')
        up = b.unit('wave', S['MathQuaternionRotateVector'], t + 'Up', blk.at(2, rb))
        b.g.link(inv + '.Result', up + '.Transform')
        b.g.setp(up + '.Vector', vec(0, 0, 1))
        side = b.unit('wave', S['MathQuaternionRotateVector'], t + 'Side', blk.at(3, rb))
        b.g.link(inv + '.Result', side + '.Transform')
        b.g.setp(side + '.Vector', vec(0, 1, 0))
        qy = b.unit('wave', S['MathQuaternionFromAxisAndAngle'], t + 'QYaw', blk.at(4, rb))
        b.g.link(up + '.Result', qy + '.Axis')
        b.g.link(yaw, qy + '.Angle')
        qp = b.unit('wave', S['MathQuaternionFromAxisAndAngle'], t + 'QPitch', blk.at(5, rb))
        b.g.link(side + '.Result', qp + '.Axis')
        b.g.link(pitch, qp + '.Angle')
        qd = b.unit('wave', S['MathQuaternionMul'], t + 'QDelta', blk.at(6, rb))
        b.g.link(qy + '.Result', qd + '.A')
        b.g.link(qp + '.Result', qd + '.B')
        lo = b.unit('wave', S['GetTransform'], t + 'Local', blk.at(7, rb))
        b.g.setp(lo + '.Item', bone(bn))
        b.g.setp(lo + '.Space', 'LocalSpace')
        b.g.setp(lo + '.bInitial', False)
        qn = b.unit('wave', S['MathQuaternionMul'], t + 'QNew', blk.at(8, rb))
        b.g.link(qd + '.Result', qn + '.A')
        b.g.link(lo + '.Transform.Rotation', qn + '.B')
        sr = b.f.add(b.unit('wave', S['SetRotation'], t + 'Set', blk.at(9, rb)))
        b.g.setp(sr + '.Item', bone(bn))
        b.g.setp(sr + '.Space', 'LocalSpace')
        b.g.setp(sr + '.bInitial', False)
        b.g.setp(sr + '.Weight', 1.0)
        b.g.setp(sr + '.bPropagateToChildren', True)
        b.g.link(qn + '.Result', sr + '.Value')
    b.close(blk)


def _bw04_f_ragdoll(b):
    blk = b.block('ragdoll', '5.3 Ragdoll step: Alpha = bIsDead (0 alive = pass-through with velocity tracking, '
                  '1 dead = simulated)', dx=380.0, dy=280.0)
    gd = b.var_get('ragdoll', 'bIsDead', 'Rag_Get_bIsDead', blk.at(0, 0))
    a = b.unit('ragdoll', S['MathBoolToFloat'], 'DeadAlpha', blk.at(1, 0))
    b.g.link(gd, a + '.Value')
    rs = b.f.add(b.unit('ragdoll', P + 'RigUnit_StepPhysicsSolver1', 'StepRagdoll', blk.at(2, 0)))
    b.setmany(rs, STEP_RAGDOLL_PINS)
    b.g.link(a + '.Result', rs + '.Alpha')
    b.close(blk)


def _bw04_f_rotor(b):
    blk = b.block('rotor', '5.4 Rotor spin on J0_Head: Final = Spin * Offset(J0 rest -> Rotor rest) * J0 now; Spin about '
                  'the body long axis by RotorAngleDeg, in the rotor frame', dx=340.0, dy=250.0)
    j0 = b.unit('rotor', S['GetTransform'], 'Rotor_J0', blk.at(0, 0))
    b.g.setp(j0 + '.Item', bone('J0_Head'))
    b.g.setp(j0 + '.Space', 'GlobalSpace')
    b.g.setp(j0 + '.bInitial', False)
    j0i = b.unit('rotor', S['GetTransform'], 'Rotor_J0Init', blk.at(0, 1))
    b.g.setp(j0i + '.Item', bone('J0_Head'))
    b.g.setp(j0i + '.Space', 'GlobalSpace')
    b.g.setp(j0i + '.bInitial', True)
    ri = b.unit('rotor', S['GetTransform'], 'Rotor_Init', blk.at(0, 2))
    b.g.setp(ri + '.Item', bone('Rotor'))
    b.g.setp(ri + '.Space', 'GlobalSpace')
    b.g.setp(ri + '.bInitial', True)
    rel = b.unit('rotor', S['MathTransformMakeRelative'], 'Rotor_Offset', blk.at(1, 1))
    b.g.link(ri + '.Transform', rel + '.Global')
    b.g.link(j0i + '.Transform', rel + '.Parent')
    inv = b.unit('rotor', S['MathQuaternionInverse'], 'Rotor_InitInv', blk.at(1, 2))
    b.g.link(ri + '.Transform.Rotation', inv + '.Value')
    ax = b.unit('rotor', S['MathQuaternionRotateVector'], 'Rotor_Axis', blk.at(2, 2))
    b.g.link(inv + '.Result', ax + '.Transform')
    b.g.setp(ax + '.Vector', vec(1, 0, 0))
    ga = b.var_get('rotor', 'RotorAngleDeg', 'Rotor_Get_RotorAngleDeg', blk.at(2, 3))
    rad = b.unit('rotor', S['MathFloatRad'], 'Rotor_Rad', blk.at(3, 3))
    b.g.link(ga, rad + '.Value')
    q = b.unit('rotor', S['MathQuaternionFromAxisAndAngle'], 'Rotor_Q', blk.at(3, 2))
    b.g.link(ax + '.Result', q + '.Axis')
    b.g.link(rad + '.Result', q + '.Angle')
    mode = b.rotor_mode
    if mode not in ('subpin', 'two_set'):
        raise H.BwError("ROTOR_MODE must be 'subpin' or 'two_set', not %r" % mode)
    if mode == 'subpin':
        m1 = b.unit('rotor', S['MathTransformMul'], 'Rotor_M1', blk.at(4, 1))
        try:
            b.g.link(q + '.Result', m1 + '.A.Rotation')      # Spin = (Rotation q, Translation 0, Scale 1): A's other sub-pins stay identity
            passed('linked the spin quaternion into Rotor_M1.A.Rotation (input sub-pin link works)')
        except H.BwError as e:
            warn('linking into the input sub-pin Rotor_M1.A.Rotation failed (%s): falling back to ROTOR_MODE two_set' % e)
            b.remove('rotor', m1)
            mode = 'two_set'
    if mode == 'subpin':
        b.g.link(rel + '.Local', m1 + '.B')
        m2 = b.unit('rotor', S['MathTransformMul'], 'Rotor_M2', blk.at(5, 1))
        b.g.link(m1 + '.Result', m2 + '.A')
        b.g.link(j0 + '.Transform', m2 + '.B')
        st = b.f.add(b.unit('rotor', S['SetTransform'], 'Rotor_Set', blk.at(6, 1)))
        b.g.setp(st + '.Item', bone('Rotor'))
        b.g.setp(st + '.Space', 'GlobalSpace')
        b.g.setp(st + '.bInitial', False)
        b.g.setp(st + '.bPropagateToChildren', False)
        b.g.link(m2 + '.Result', st + '.Value')
    else:
        m = b.unit('rotor', S['MathTransformMul'], 'Rotor_M', blk.at(4, 1))     # Offset * J0G (rotor rest frame on the head)
        b.g.link(rel + '.Local', m + '.A')
        b.g.link(j0 + '.Transform', m + '.B')
        qf = b.unit('rotor', S['MathQuaternionMul'], 'Rotor_QFinal', blk.at(5, 2))   # M.Rotation * Spin = spin first
        b.g.link(m + '.Result.Rotation', qf + '.A')
        b.g.link(q + '.Result', qf + '.B')
        st = b.f.add(b.unit('rotor', S['SetTransform'], 'Rotor_Set', blk.at(6, 1)))
        b.g.setp(st + '.Item', bone('Rotor'))
        b.g.setp(st + '.Space', 'GlobalSpace')
        b.g.setp(st + '.bInitial', False)
        b.g.setp(st + '.bPropagateToChildren', False)
        b.g.link(m + '.Result', st + '.Value')
        sr = b.f.add(b.unit('rotor', S['SetRotation'], 'Rotor_SetRot', blk.at(7, 1)))
        b.g.setp(sr + '.Item', bone('Rotor'))
        b.g.setp(sr + '.Space', 'GlobalSpace')
        b.g.setp(sr + '.bInitial', False)
        b.g.setp(sr + '.bPropagateToChildren', False)
        b.g.link(qf + '.Result', sr + '.Value')
    b.rotor_mode = mode
    info('rotor built in mode %s' % mode)
    b.close(blk)


def _bw04_f_repin_store(b):
    chains = _bw04_repin_chains()
    if not chains:
        info('repin: no hose/wire stage enabled, nothing to re-pin')
        return
    blk = b.block('repin', '5.6a Store the _end anchors right after 5.4 (mutable Set-variable nodes, one FTransform '
                  'variable per chain)', dx=340.0, dy=250.0)
    for col, ch in enumerate(chains):
        gtn = b.unit('repin', S['GetTransform'], 'EndPin_Get_' + ch, blk.at(col, 0))
        b.g.setp(gtn + '.Item', bone(ch + '_end'))
        b.g.setp(gtn + '.Space', 'GlobalSpace')
        b.g.setp(gtn + '.bInitial', False)
        sv = b.f.add(b.var_set('repin', REPIN_VAR % ch, 'EndPin_Store_' + ch, blk.at(col, 1)))
        b.g.link(gtn + '.Transform', sv + '.Value')
    b.close(blk)


def _bw04_f_hoses(b):
    blk = b.block('hoses', '5.5 Hose step (rigid body, Alpha 1)', dx=380.0, dy=280.0)
    n = b.f.add(b.unit('hoses', P + 'RigUnit_StepPhysicsSolver1', 'StepHoses', blk.at(0, 0)))
    b.setmany(n, STEP_HOSES_PINS)
    b.close(blk)


def _bw04_f_wires(b):
    blk = b.block('wires', '5.6 Wire step (Dynamics, Alpha 1)', dx=380.0, dy=280.0)
    n = b.f.add(b.unit('wires', D + 'RigUnit_StepDynamicsSolver', 'StepWires', blk.at(0, 0)))
    b.setmany(n, STEP_WIRES_PINS)
    b.close(blk)


def _bw04_f_repin_restore(b):
    chains = _bw04_repin_chains()
    if not chains:
        return
    blk = b.block('repin', '5.6b Re-pin the 8 _end bones to the stored anchors (Global, no propagation)',
                  dx=340.0, dy=250.0)
    for col, ch in enumerate(chains):
        gv = b.var_get('repin', REPIN_VAR % ch, 'EndPin_Read_' + ch, blk.at(col, 0))
        st = b.f.add(b.unit('repin', S['SetTransform'], 'EndPin_Set_' + ch, blk.at(col, 1)))
        b.g.setp(st + '.Item', bone(ch + '_end'))
        b.g.setp(st + '.Space', 'GlobalSpace')
        b.g.setp(st + '.bInitial', False)
        b.g.setp(st + '.bPropagateToChildren', False)
        b.g.link(gv, st + '.Value')
    b.close(blk)


# ------------------------------------------------------------------------------------------------- summary
def _bw04_summary(b, summary):
    g = b.g.g
    node_stage = {}
    for st, names in b.nodes.items():
        for n in names:
            node_stage[n] = st
    links = list(g.get_links())
    per_stage_links = {}
    for lk in links:
        try:
            tn = lk.get_target_pin().get_node().get_name()
        except Exception:  # noqa: BLE001
            tn = ''
        st = node_stage.get(tn, 'other')
        per_stage_links[st] = per_stage_links.get(st, 0) + 1
    nodes = list(g.get_nodes())
    comments = [n for n in nodes if isinstance(n, unreal.RigVMCommentNode)]
    summary['stages'] = {}
    for st in ['events'] + list(STAGES):
        on = STAGES.get(st, True)
        cnt = len(b.nodes.get(st, []))
        lks = per_stage_links.get(st, 0)
        summary['stages'][st] = {'enabled': on, 'nodes': cnt, 'links_into': lks}
        info('stage %-8s %-3s nodes %4d   links into its nodes %4d' % (st, 'on' if on else 'OFF', cnt, lks))
    summary['total_nodes'] = len(nodes)
    summary['comment_nodes'] = len(comments)
    summary['total_links'] = len(links)
    info('graph %s: %d nodes (%d of them comments), %d links' % (g.get_name(), len(nodes), len(comments), len(links)))


def _bw04_verify_structs(b):
    bad = 0
    for n, short in sorted(b.expect.items()):
        got = b.g.struct_of(n)
        if got != short:
            fail('node %s resolved to %r, expected %s (a template node re-resolved after a link of another type)'
                 % (n, got, short))
            bad += 1
    if not bad:
        passed('all %d unit nodes resolved to the struct that was asked for' % len(b.expect))
    return bad == 0


# ------------------------------------------------------------------------------------------------- main
def _bw04_main():
    t0 = time.time()
    summary = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'stages_requested': dict(STAGES), 'mode': MODE,
               'rotor_mode_requested': ROTOR_MODE, 'saved': False}
    info('bw_04_control_rig: STAGES %s, MODE %s, ROTOR_MODE %s, INSTANTIATE %s' % (STAGES, MODE, ROTOR_MODE,
                                                                                  INSTANTIATE_IN_CONSTRUCTION))
    unknown = [k for k in STAGES if k not in ('wave', 'ragdoll', 'rotor', 'hoses', 'wires', 'repin')]
    if unknown:
        fail('unknown STAGES keys %s' % unknown)
        return summary
    if H.pie_running():
        fail('PIE is running: stop it first (assets cannot be saved during PIE). Nothing was changed.')
        return summary

    ok, _ = _bw04_prereqs()
    if not ok:
        fail('prerequisites missing: nothing was changed')
        return summary
    if not _bw04_step3_path_check():
        return summary

    try:
        rig, mode = _bw04_get_rig()
    except H.BwError as e:
        fail('could not create/reuse CR_Burrower: %s' % e)
        return summary
    summary['mode'] = mode
    try:
        rig.set_auto_vm_recompile(False)                  # RigVMBlueprintLegacy.h:276; compile_rig turns it back on
    except Exception as e:  # noqa: BLE001
        warn('set_auto_vm_recompile(False) failed (%s): the build will be slower' % e)
    H.clear_rig_graphs(rig)

    if not _bw04_check_bones(rig):
        fail('CR_Burrower was %s in memory but NOT saved (bones missing).' % ('recreated' if mode == 'recreate' else 'cleared'))
        return summary

    b = _Bw04Build(rig)
    probe_ok = True
    try:
        core_specs = dict((k, v) for k, v in H.CORE_PIN_SPECS.items() if k in set(_bw04_needed_paths()))
        probe_ok = H.verify_core_pins(rig, core_specs) and probe_ok
        probe_ok = _bw04_probe_plugin_pins(b) and probe_ok
    except H.BwError as e:
        fail('pin probe error: %s' % e)
        probe_ok = False
    if not probe_ok:
        if ABORT_ON_PIN_PROBE_FAIL:
            fail('pin probe failed: nothing built, CR_Burrower NOT saved. Fix the names above (or set '
                 'BW04_ABORT_ON_PIN_PROBE_FAIL = False to try anyway).')
            return summary
        warn('pin probe failed but ABORT_ON_PIN_PROBE_FAIL is False: building anyway')

    try:
        _bw04_variables(rig)
    except H.BwError as e:
        fail('variables: %s. Nothing built, CR_Burrower NOT saved.' % e)
        return summary

    ev_c = b.g.ensure_event(H.EV_CONSTRUCTION, 'ConstructionEvent', unreal.Vector2D(-700.0, 0.0))
    b._add('events', ev_c)
    b.c = b.g.chain(ev_c)

    any_solver = STAGES['ragdoll'] or STAGES['hoses'] or STAGES['wires']
    steps = [
        ('ragdoll', 'Construction 4.1', _bw04_c_ragdoll, STAGES['ragdoll']),
        ('hoses', 'Construction 4.2', _bw04_c_hoses, STAGES['hoses']),
        ('wires', 'Construction 4.3', _bw04_c_wires, STAGES['wires']),
        ('instantiate', 'Construction 4.4', _bw04_c_instantiate, INSTANTIATE_IN_CONSTRUCTION and any_solver),
        ('events', 'Forwards Solve event', _bw04_f_events, True),
        ('wave', 'Forwards 5.1', _bw04_f_wave, STAGES['wave']),
        ('ragdoll', 'Forwards 5.3', _bw04_f_ragdoll, STAGES['ragdoll']),
        ('rotor', 'Forwards 5.4', _bw04_f_rotor, STAGES['rotor']),
        ('repin', 'Forwards 5.6a store', _bw04_f_repin_store, STAGES['repin'] and bool(_bw04_repin_chains())),
        ('hoses', 'Forwards 5.5', _bw04_f_hoses, STAGES['hoses']),
        ('wires', 'Forwards 5.6', _bw04_f_wires, STAGES['wires']),
        ('repin', 'Forwards 5.6b restore', _bw04_f_repin_restore, STAGES['repin'] and bool(_bw04_repin_chains())),
    ]
    build_ok = True
    for stage, label, fn, on in steps:
        if not on:
            info('%s (%s): skipped (stage off)' % (label, stage))
            continue
        ts = time.time()
        try:
            fn(b)
            passed('%s (%s) built in %.1f s' % (label, stage, time.time() - ts))
        except Exception as e:  # noqa: BLE001 - BwError and anything unexpected
            fail('%s (stage %r) failed: %s' % (label, stage, e))
            for line in traceback.format_exc().rstrip().split('\n'):
                print('INFO:   ' + line)
            if stage == 'instantiate':
                info('bisect: re-run with BW04_INSTANTIATE_IN_CONSTRUCTION = False')
            elif stage in STAGES:
                info('bisect: re-run with BW04_STAGES = {%r: False} (and the stages after it if needed)' % stage)
            build_ok = False
            break
    summary['rotor_mode_built'] = b.rotor_mode

    for i, blk in enumerate(b.blocks):
        try:
            blk.comment(b.g, i)
        except H.BwError as e:
            warn('comment node for %s: %s (cosmetic)' % (blk.title[:40], e))

    structs_ok = _bw04_verify_structs(b)
    _bw04_summary(b, summary)

    compile_ok = H.compile_rig(rig)
    try:
        summary['status'] = str(rig.get_editor_property('status'))
    except Exception:  # noqa: BLE001
        pass
    summary['build_ok'], summary['compile_ok'], summary['structs_ok'] = build_ok, compile_ok, structs_ok

    if build_ok and compile_ok and structs_ok:
        summary['saved'] = H.save_rig(H.RIG_PATH)
    elif SAVE_ON_FAIL:
        warn('saving although the build/compile failed (SAVE_ON_FAIL)')
        summary['saved'] = H.save_rig(H.RIG_PATH)
    else:
        warn('CR_Burrower NOT saved (build_ok %s, compile_ok %s, structs_ok %s). It stays in memory: open it in the '
             'rig editor to look, or fix and re-run.' % (build_ok, compile_ok, structs_ok))
    summary['seconds'] = round(time.time() - t0, 1)
    if summary['saved']:
        info('next: run bw_04b_cr_check.py (numeric wave/rotor checks), then bw_05_anim_bp.py')
    return summary


_bw04_summary_data = {}
try:
    _bw04_summary_data = _bw04_main() or {}
except Exception as _bw04_e:  # noqa: BLE001
    fail('unexpected error: %r' % (_bw04_e,))
    for _bw04_line in traceback.format_exc().rstrip().split('\n'):
        print('INFO:   ' + _bw04_line)
_bw04_summary_data['counts'] = dict(_bw04_counts)
try:
    H.write_json('bw_04_control_rig', _bw04_summary_data)
except Exception as _bw04_e:  # noqa: BLE001
    print('WARN: could not write the summary json: %r' % (_bw04_e,))
print('RESULT: %s (%d FAIL, %d WARN, %d PASS)' % ('PASS' if _bw04_counts.get('FAIL', 0) == 0 else 'FAIL',
                                                 _bw04_counts.get('FAIL', 0), _bw04_counts.get('WARN', 0),
                                                 _bw04_counts.get('PASS', 0)))
