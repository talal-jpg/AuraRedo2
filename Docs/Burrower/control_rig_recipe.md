# Burrower Control Rig recipe (UE 5.8, ControlRigDynamics + ControlRigPhysics)

For the Claude session on the user's machine (UE 5.8 editor, compiler, editor Python / RigVMController or the editor's
MCP toolsets). Follow the numbered steps in order. Everything the rig does is cosmetic and runs on every machine
(listen server and clients); gameplay (rotor box, hex tile activation, damage, death) is C++ on the server.

What the rig does, in one Forwards Solve per frame:

1. **Body wave**: a travelling sine wave on J1..J4 (yaw about the body's up axis, optional pitch), applied in local
   space on top of the input pose, amplitude ramping up toward the tail.
2. **Ragdoll on death** (ControlRigPhysics, solver "Ragdoll" on `root`): bodies on J0..J4 instantiated from the
   skeletal mesh's physics asset. Bypassed (Alpha 0) while alive, simulated (Alpha 1) once `bIsDead` is true.
3. **Rotor spin**: `Rotor` is parented to `root`, so the rig places it on the head every frame:
   rest offset from J0_Head, spun about the body's long axis by `RotorAngleDeg`. Done after the ragdoll step so the
   rotor stays on the dead head too.
4. **Upper armoured hoses** (ControlRigPhysics, solver "Hoses" on `J1_Forequarters`): rigid-body chains, both ends
   kinematic, joint limits and drives.
5. **Upper cables and side hoses** (ControlRigDynamics, solver "DynamicsSolver" on `root`): "wire" particle chains,
   both ends pinned, gravity, damping, a flank collider.

Sources: every ControlRigDynamics / ControlRigPhysics struct, pin and default below was read from the UE 5.8 plugin
headers and the two .cpp files staged at `/mnt/user-data/uploads/ControlRigDynamics` and
`/mnt/user-data/uploads/ControlRigPhysics`. **Core Control Rig / RigVM nodes** (events, Get/Set Transform, math) and the
**PhysicsControl** structs (`FPhysicsControlModifierData`, `EPhysicsMovementType`) were *not* staged. Their names come
from memory of UE 5.3-5.6 and are marked **[unverified]**. Step 3 has a script that checks every path before you
build anything. Bone positions come from the lead's rig (`SourceArt/Burrower/Burrower_rig_info.json` and the Blender
rig `rig_v2/Burrower_rigged.blend`, read on 2026-11-21).

---

## Conventions used in this recipe

* Control Rig **Global** space = component space of the skeletal mesh: +X forward (head), +Z up, cm.
  **Local** space = relative to the parent bone.
* UE transform order: `A * B` means "apply A, then B" (A is in B's frame). So "parent global ∘ offset ∘ spin"
  written parent-first in maths is `Spin * Offset * ParentGlobal` in UE and in `RigVMFunction_MathTransformMul`
  (A=first, B=second).
* Bone **local axes are not assumed anywhere.** Blender bones come through FBX with arbitrary local axes, so every axis
  below is computed in the graph from the initial (rest) global transforms. Shapes whose placement depends on axes are
  either axis-free (spheres, auto-calculated capsules) or converted in Python from component space using the rig
  hierarchy's initial transforms.
* Shorthand: `P = /Script/ControlRigPhysics.`, `D = /Script/ControlRigDynamics.`, `CR = /Script/ControlRig.`,
  `VM = /Script/RigVM.` (struct path = module + struct name without the `F`).

---

## Step 0: Skeleton facts to verify after the FBX import

71 bones. Expected **initial global positions in UE (cm)**. With Blender's default FBX axes, UE Y = -Blender Y, so the
`_l` chains should come out at **negative** UE Y (the creature's left in UE). If they come out positive, nothing in
the rig changes, because every shape used is symmetric in Y; just note it.

| Bone | Parent | UE position (cm) |
|---|---|---|
| root | (none) | (0, 0, 0) |
| J0_Head | root | (1000, 0, 180), the maw front |
| J1_Forequarters | J0_Head | (660, 0, 193) |
| J2_Midbody | J1_Forequarters | (260, 0, 200) |
| J3_Hindbody | J2_Midbody | (-260, 0, 200) |
| J4_Tail | J3_Hindbody | (-560, 0, 202); the tail tip is at x = -1017 |
| Rotor | **root** | (977.9, 0, 180.5) = rotor centre; disc r = 105.8, depth 55.8, spin axis +X |

Pipe chains. Every chain root `_01` is parented to `J1_Forequarters`, and the chain is `_01 -> _02 -> ... -> _NN -> _end`.

| Chain | Bones | `_01` (UE cm) | `_end` (UE cm) | Radius | Length / chord (slack) | Solver |
|---|---|---|---|---|---|---|
| pipe_upperhose_l | _01.._07, _end | (700, -33.6, 383.8) | (507.2, -42.0, 424.7) | 11 cm | 202 / 197 cm (2.6 %) | **Physics (rigid body)** |
| pipe_upperhose_r | _01.._05, _end | (700, 33.6, 383.8) | (542.6, 40.3, 410.4) | 11 cm | 163 / 160 cm (2.2 %) | **Physics (rigid body)** |
| pipe_uppercable_l | _01.._07, _end | (706.3, -47.6, 384.5) | (507.9, -66.1, 429.9) | 3.2 cm | 210 / 204 cm (2.7 %) | **Dynamics (wire)** |
| pipe_uppercable_r | _01.._09, _end | (706.3, 47.6, 384.5) | (479.2, 66.1, 472.7) | 3.2 cm | 260 / 244 cm (6.6 %) | **Dynamics (wire)** |
| pipe_side_l_a | _01.._07, _end | (543.0, -169.7, 110.1) | (391.7, -158.3, 69.6) | 3.6 cm | 183 / 157 cm (16.6 %) | **Dynamics (wire)** |
| pipe_side_l_b | _01.._07, _end | (543.1, -180.0, 144.5) | (410.2, -165.7, 85.2) | 3.6 cm | 189 / 146 cm (29.1 %) | **Dynamics (wire)** |
| pipe_side_r_a / _r_b | mirror of _l_a / _l_b | mirror (+Y) | mirror (+Y) | 3.6 cm | same | **Dynamics (wire)** |

Checks, in the Control Rig editor after Step 2 or with the Python in Step 3:

* All 71 bones exist with these names. An extra top bone above `root` (for example `Burrower_Rig`, if the importer
  kept the armature node) does no harm to the rig; it only has to be a parent of `root`.
* `Rotor`'s initial global translation is about (977.9, 0, 180.5). The rotor spins about its bone origin, so if the
  origin were not at the rotor centre the disc would wobble. Fix that in Blender, not in the rig.

### Which pipe uses which solver, and why

* **Upper armoured hoses → rigid body (ControlRigPhysics).** These are thick (r = 11 cm), banded with rigid rider rings
  (20 fittings each in the rig info) and tight between two fixed fittings (collar coupling at x = 7.0 m, canister
  nozzle at x ≈ 5.1-5.4 m, both riding rigidly on J1). They have only 2-3 % slack. A particle wire with that little
  slack either does nothing or looks rubbery. Segments with mass and inertia, per-joint swing/twist limits and an
  angular drive back to the modelled shape read as stiff armour that jolts when the body turns. Joint limits and drives
  exist only in the rigid-body solver.
* **Upper cables → wire (ControlRigDynamics).** These are thin (3.2 cm) and light. They lie on the back between the
  same two fittings, with a little slack. Cheap position-based particles are enough.
* **Side hoses → wire (ControlRigDynamics).** These hang under the shoulder hubs (fixed at the hub, x ≈ 5.43 m) down to
  the flank (x ≈ 3.9-4.1 m, still on J1). They have a lot of slack (17-29 %), so the look is gravity sag, swing and
  lag, which is what distance-constrained particles do well. They need collision against the flank, which Dynamics
  colliders give.

Both ends of every chain are fixed. `_01` and `_end` are kinematic, the middle bones simulate. `_end` follows J1
through the input pose: the input pose of the pipe bones is the reference pose, so `_end` is a fixed offset from J1
every frame. This depends on the anim node's **Transfer Input Pose** (Step 6).

---

## Step 1: Prerequisites

1. **Plugins.** `ControlRigDynamics` is already enabled in `Aura.uproject`. `ControlRigPhysics` must also be
   `"Enabled": true`; the C++ change adds it next to ControlRigDynamics. Check it, accept any dependent-plugin prompt
   (ControlRigDynamics depends on `ControlRig` and `PhysicsControl`; ControlRigPhysics' .uplugin was not staged, so its
   dependency list is unknown), and **restart the editor**. Both plugins are experimental:
   `ControlRigDynamics.uplugin` has `"IsExperimentalVersion": true`, and ControlRigPhysics should be treated the same.
2. **Assets** (example paths, adapt to what the import step created):
   `/Game/Assets/Enemies/Burrower/SK_Burrower` (+ its Skeleton), `PA_Burrower` (physics asset), and later
   `CR_Burrower` (this rig), `ABP_Burrower`, `BP_Burrower`.
3. **Physics asset requirements for the rig ragdoll** (the same asset gives the C++ hit collision and the C++ fallback
   ragdoll):
   * Bodies **only on J0_Head..J4_Tail**. Delete any auto-generated bodies on `root`, `Rotor` and the pipe bones.
     The rig handles the pipes, and the Rotor is re-attached by the rig. A Rotor body would be parented to `root` and
     would fall off on its own in the C++ fallback ragdoll.
   * Simple capsules along the body (component X). Suggested sizes, from the skinned-vertex bounds per joint
     (centre, radius, core length along X; they meet without overlapping):

     | Body | Centre (cm) | Radius | Core length | Covers x |
     |---|---|---|---|---|
     | J0_Head | (830, 0, 187) | 160 | 40 | 650..1010 |
     | J1_Forequarters | (460, 0, 195) | 185 | 30 | 260..660 |
     | J2_Midbody | (0, 0, 200) | 175 | 170 | -260..260 |
     | J3_Hindbody | (-410, 0, 210) | 125 | 50 | -560..-260 |
     | J4_Tail | (-785, 0, 205) | 85 | 290 | -1015..-555 |

   * Constraints J1-J0, J2-J1, J3-J2, J4-J3: linear locked, angular limited **20° on all three axes** (swing 1, swing 2
     and twist). Equal limits on all three axes mean you need not check which constraint axis is "twist" for these
     Blender bones. Leave every body's Physics Type at **Default**. The rig turns them to Simulated itself, and
     "Simulated" in the asset could start a mesh ragdoll outside the rig.
   * Collision Response Enabled. The rig then gets `PhysicsOnly` bodies, which it needs for world collision.

---

## Step 2: Create CR_Burrower and its variables (part e)

1. Right-click SK_Burrower → Create → Control Rig, or in Python
   `rig = unreal.ControlRigBlueprintFactory.create_control_rig_from_skeletal_mesh_or_skeleton(selected_object=skm)`
   **[unverified name]**, then rename/move it to `CR_Burrower`. The hierarchy must contain all 71 bones. If the FBX is
   re-imported later, refresh or re-import the hierarchy in the rig editor.
2. Add the **public** (instance-editable, exposed to the AnimBP node) variables. Names and types must match
   `UBurrowerAnimInstance` exactly, so the AnimBP pins line up:

| Variable | Type | Default (for editor preview) | Meaning in the rig |
|---|---|---|---|
| `RotorAngleDeg` | float | 0 | Rotor spin angle, accumulated in C++ and best wrapped to [0, 360) |
| `RotorSpinSpeed` | float | 0 | Not used by the graph (C++ integrates the angle); exposed for completeness |
| `WaveTime` | float | 0 | Wave phase accumulated in C++ (speed-linked). **Contract: in cycles (1.0 = one period)**, see open question 1 |
| `WaveAmplitudeDeg` | float | 10 | Peak yaw per joint at the tail (weights below ramp it down toward the head) |
| `WavePhasePerJointDeg` | float | 65 | Phase lag between successive joints, so the wave travels head → tail |
| `WavePitchAmplitudeDeg` | float | 0 (3 to preview) | Peak pitch at the tail (optional vertical wave) |
| `Speed` | float | 0 | Optional amplitude gate (Step 5.2, off by default) |
| `bIsDead` | bool | false | Switches the ragdoll on |
| `DeathTime` | float | 0 | Optional (ragdoll Alpha ramp); **contract: seconds since death, 0 while alive**, see open question 1 |

   Add one **private** variable: `WaveTimeToRadians` (float, default `6.2831853`). If the C++ delivers `WaveTime` in
   radians, set it to 1; if in degrees, to 0.0174533. No graph change is needed.

   Python **[unverified signature]**:
   `rig.add_member_variable('RotorAngleDeg', 'float', True, False, '0.0')` (name, C++ type, is_public, is_read_only,
   default). Use `'bool'` and `'False'` for `bIsDead`. Keep the C++ properties as `float` (single precision); the
   AnimGraph converts if the rig variable is created as double.

---

## Step 3: Check the node paths before building (run once)

```python
import unreal
RIG_PATH = '/Game/Assets/Enemies/Burrower/CR_Burrower'
P, D, CR, VM = ('/Script/ControlRigPhysics.', '/Script/ControlRigDynamics.',
                '/Script/ControlRig.', '/Script/RigVM.RigVMFunction_')
VERIFIED = [  # read from the staged UE 5.8 headers
  P+'RigUnit_SpawnPhysicsSolver', P+'RigUnit_HierarchyInstantiateFromPhysicsAsset',
  P+'RigUnit_HierarchySetPhysicsBodyMovementType', P+'RigUnit_HierarchySetPhysicsBodyDamping',
  P+'RigUnit_AddPhysicsBody', P+'RigUnit_AddPhysicsJoint', P+'RigUnit_MakeArticulationJointData',
  P+'RigUnit_MakeArticulationDriveData', P+'RigUnit_InstantiatePhysics', P+'RigUnit_StepPhysicsSolver1',
  P+'RigUnit_HierarchyAddPhysicsBodyForce', P+'RigUnit_GetPhysicsSolverSpaceData',
  D+'RigUnit_SpawnDynamicsSolver1', D+'RigUnit_SpawnDynamicsChains', D+'RigUnit_SpawnDynamicsCollider',
  D+'RigUnit_HierarchySetDynamicsParticleMovementType', D+'RigUnit_InstantiateDynamics',
  D+'RigUnit_StepDynamicsSolver', D+'RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset1',
  D+'RigUnit_GetDynamicsSolverData',
]
FROM_MEMORY = [  # core Control Rig / RigVM, not staged: [unverified]
  CR+'RigUnit_PrepareForExecution', CR+'RigUnit_BeginExecution', CR+'RigUnit_GetTransform',
  CR+'RigUnit_SetTransform', CR+'RigUnit_SetRotation',
  VM+'MathFloatMul', VM+'MathFloatSub', VM+'MathFloatSin', VM+'MathFloatCos', VM+'MathFloatRad',
  VM+'MathFloatClamp', VM+'MathBoolToFloat', VM+'MathQuatFromAxisAndAngle', VM+'MathQuatMul',
  VM+'MathQuatInverse', VM+'MathQuatRotateVector', VM+'MathTransformMul', VM+'MathTransformMakeRelative',
  VM+'MathTransformMake',
]
for p in VERIFIED + FROM_MEMORY:
    print('OK     ' if unreal.load_object(None, p) else 'MISSING', p)

rig = unreal.load_asset(RIG_PATH)
C = rig.get_controller_by_name('RigVMModel')     # main graph; if None: rig.get_controller(rig.get_model())
G = C.get_graph()
def show_pins(struct_path):                          # add a throw-away node and list its pins
    n = C.add_unit_node_from_struct_path(struct_path, 'Execute', unreal.Vector2D(0, 0), 'Probe')
    print(struct_path, [(p.get_name(), p.get_cpp_type()) for p in n.get_pins()])
    C.remove_node_by_name('Probe')
for p in FROM_MEMORY: show_pins(p)
```

If something is MISSING, open the node menu in the rig editor, place the node by its display name and read its struct
from the node's details or tooltip. Placing it by hand once and copying the Python the editor echoes also works. The
pin names to confirm: `A/B/Result`, `Value/Result`, `Axis/Angle`, `Transform/Vector` (QuatRotateVector),
`Global/Parent/Local` (MakeRelative), `Translation/Rotation/Scale` (TransformMake), `Item/Space/bInitial/Transform`
(GetTransform), and `Item/Space/bInitial/Value/Weight/bPropagateToChildren` (Set*). The execute pin's name changed
across 5.x (`ExecuteContext` / `ExecutePin`), so the helpers below find it with `pin.is_execute_context()`.

Two pairs of nodes share a display name, one deprecated in 5.8 and one current. Always use the current one:

| Use (5.8) | Not (deprecated 5.8, same display name) |
|---|---|
| `RigUnit_SpawnDynamicsSolver1` "Spawn Dynamics Solver" | `RigUnit_SpawnDynamicsSolver` |
| `RigUnit_SpawnPhysicsSolver` "Spawn Physics Solver" | `RigUnit_AddPhysicsSolver` |
| `RigUnit_StepPhysicsSolver1` "Step Physics Solver" | `RigUnit_StepPhysicsSolver` |
| `RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset1` | `RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset` |
| Step Physics Solver with Alpha = 0 | `RigUnit_TrackInputPose` "Set Solver Track Input Pose" |

### Python helpers (used in Steps 4 and 5)

```python
H = rig.hierarchy                                # URigHierarchy; initial = skeleton ref pose
_pos = [0]
def node(path, name):
    _pos[0] += 1
    n = C.add_unit_node_from_struct_path(path, 'Execute', unreal.Vector2D(300 * (_pos[0] % 12), 250 * (_pos[0] // 12)), name)
    if not n: raise RuntimeError('cannot add ' + path)
    return n.get_name()
def var_get(var, cpp='float'):                   # a new getter node each call; output pin 'Value'
    _pos[0] += 1
    n = C.add_variable_node(var, cpp, None, True, '', unreal.Vector2D(-400, 120 * _pos[0]), 'Get_%s_%d' % (var, _pos[0]))
    return n.get_name() + '.Value'
def setp(pin, value):
    if not C.set_pin_default_value(pin, str(value), True): raise RuntimeError('cannot set ' + pin)
def link(a, b):
    if not C.add_link(a, b): raise RuntimeError('cannot link %s -> %s' % (a, b))
def exec_pin(node_name, output):
    for p in G.find_node_by_name(node_name).get_pins():
        if p.is_execute_context():
            d = p.get_direction()
            if d == unreal.RigVMPinDirection.IO or (d == unreal.RigVMPinDirection.OUTPUT) == output:
                return p.get_pin_path()
    raise RuntimeError('no execute pin on ' + node_name)
class Chain:                                     # chains mutable nodes in execution order
    def __init__(self, start): self.last = start
    def add(self, n):
        link(exec_pin(self.last, True), exec_pin(n, False)); self.last = n; return n
def bone(n):    return '(Type=Bone,Name="%s")' % n
def comp(b, c): return '(ElementKey=(Type=Bone,Name="%s"),Name="%s")' % (b, c)   # FRigComponentKey
def arr(xs):    return '(' + ','.join(xs) + ')'
J = ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail']
def chain_bones(prefix, n): return ['%s_%02d' % (prefix, i) for i in range(1, n + 1)] + [prefix + '_end']
HOSES  = [chain_bones('pipe_upperhose_l', 7), chain_bones('pipe_upperhose_r', 5)]
CABLES = ['pipe_uppercable_l', 'pipe_uppercable_r']
SIDES  = ['pipe_side_l_a', 'pipe_side_l_b', 'pipe_side_r_a', 'pipe_side_r_b']
RAGDOLL = comp('root', 'PhysicsSolver')
HOSE_SOLVER = comp('J1_Forequarters', 'PhysicsSolver')
WIRE = comp('root', 'DynamicsSolver')
```

Text formats: enums by name (`World`, `Component`, `Kinematic`, `Simulated`, `NoCollision`, `GlobalSpace`,
`LocalSpace`), bools `True`/`False`, vectors `(X=..,Y=..,Z=..)`, arrays `(a,b,c)`, nested sub-pins with dots
(`Node.SolverSettings.SimulationSpace`). Component keys are `(ElementKey=(Type=Bone,Name="x"),Name="Comp")`; the
`ElementKey` and `Name` member names are confirmed by the plugin .cpp files.

All Dynamics nodes default their solver key to bone **"Root"** (capital R). FName comparison ignores case, so it would
probably resolve to `root`, but **always set the key explicitly** as below.

---

## Step 4: Construction Event graph

The spawn/setup nodes only work in the Construction Event (`RigUnit_PrepareForExecution`). The physics .cpp files
check `ExecuteContext.GetEventName() != FRigUnit_PrepareForExecution::EventName` and report "... can only be used
during Setup". The Dynamics spawn nodes say "only runs as part of the construction event". The step nodes run in
Forwards Solve. No Pre-/Post-Forwards-Solve events are needed.

```python
ev_c = node(CR + 'RigUnit_PrepareForExecution', 'ConstructionEvent')   # skip if the rig already has one
c = Chain(ev_c)
```

### 4.1 Ragdoll solver and bodies (part d)

**C1 `Spawn Physics Solver`** (`P RigUnit_SpawnPhysicsSolver`), node name `RagdollSolver`:

| Pin | Value | Why |
|---|---|---|
| `Owner` | `root` | Output key = (root, `PhysicsSolver`); the node has no name pin, the name is the default |
| `SolverSettings.bAutomaticallyAddPhysicsBodyComponents` | False | Two physics solvers exist; bodies are assigned explicitly |
| `SolverSettings.SimulationSpace` | **World** | While alive the solver is bypassed; once dead the actor stops and the body should keep its world momentum. Component space would turn the abrupt stop into a pseudo-force spike that can trip teleport detection |
| `SolverSettings.CollisionSpace` | World | |
| `SolverSettings.WorldCollisionType` | **Static** | Ground: collide with static and kinematic world objects (hex tiles: ISM, QueryAndPhysics, block all) |
| `SolverSettings.bWorldCollisionIncludePhysics` | True (default) | QueryAndPhysics world bodies |
| `SolverSettings.bWorldCollisionIncludeQuery` | False (default) | Excludes the Burrower's own QueryOnly mesh bodies and RotorBox |
| `SolverSettings.WorldCollisionBoundsExpansion` | 1.1 (default) | |
| `SolverSettings.PositionIterations` / `VelocityIterations` / `ProjectionIterations` | 8 / 2 / 1 | |
| `SolverSettings.FixedTimeStep` | **0** | Variable step (no stutter); sub-steps come from MaxDeltaTime |
| `SolverSettings.MaxDeltaTime` / `MaxTimeSteps` | 0.0334 / 4 | Sub-steps below 30 fps, capped |
| `SolverSettings.MaxDepenetrationVelocity` | 300 | The worm may die partly inside tiles; push out gently (default 0) |
| `SolverSettings.Gravity` | (0, 0, -981) default | |
| `TeleportDetection.PositionChangeThreshold` | 500 | Default 100 cm per update is too low for a fast flyer at low fps |
| `SpaceMotion` | defaults | Not used in World space |

**C2 `Instantiate From Physics Asset`** (`P RigUnit_HierarchyInstantiateFromPhysicsAsset`), name `RagdollFromPA`.
The plugin **can** instantiate from a physics asset. It reads `PhysicsAsset->SkeletalBodySetups` and `ConstraintSetup`,
copies box, sphere, sphyl and convex shapes, the material, mass (`CalculateMass()`), damping, CCD and the
collision-disable table, and builds joints from the constraint frames and the chosen constraint profile.

| Pin | Value |
|---|---|
| `PhysicsSolverComponentKey` | `RAGDOLL` = (root, PhysicsSolver) |
| `bUseAutomaticSolver` | False |
| `PhysicsAsset` | `/Game/Assets/Enemies/Burrower/PA_Burrower.PA_Burrower` (if the text default is refused, pick it in the details panel) |
| `ConstraintProfileName` | (empty = default profile) |
| `BonesToUse` (display "Bone Mask") | `arr([bone(b) for b in J])` = J0..J4 only |
| `bEnableJoints` | True |
| `bEnableDrives` | **False** (a limp, joint-limited corpse; no drive back toward the still-waving input pose) |
| `bAddSimSpaceControl` / `bAddParentSpaceControl` | False / False |
| `bMakeHelperBodies` | False (no body on root; J0_Head is the free root-most body) |

The body components are named `PhysicsBody` on each bone, so the keys are (J0_Head, PhysicsBody) and so on. Physics
Type *Default* in the asset becomes **Kinematic** here (from the .cpp: only `PhysType_Simulated` maps to Simulated).
The collision type becomes `PhysicsOnly` when the body's Collision Response is Enabled.

**C3** For each `b` in J: **`Set Physics Body Movement Mode`** (`P RigUnit_HierarchySetPhysicsBodyMovementType`),
`PhysicsBodyComponentKey = comp(b,'PhysicsBody')`, `MovementType = Simulated`. Then **`Set Physics Body Damping`**
(`P RigUnit_HierarchySetPhysicsBodyDamping`): `LinearDamping 0.1`, `AngularDamping 1.0`. The solver re-reads damping
each step.
*Why Simulated already here:* while alive, the step node runs with `Alpha = 0`, which per the header "bypasses the
simulation entirely" and, with `bTrackVelocitiesDuringPassThrough = true`, "still tracks source bone transforms each
frame so that velocities are valid when Alpha increases". At death Alpha becomes 1 and the already-simulated bodies
start from the current pose and velocity. Nothing switches per frame, and nothing costs anything while alive. If this
shows a pop at death in practice, see the fallback in Step 9.

Leave `SourceBone` / `TargetBone` unset for these bodies (Instantiate does not set them; they default to the owning
bone).

```python
s = c.add(node(P + 'RigUnit_SpawnPhysicsSolver', 'RagdollSolver'))
setp(s + '.Owner', bone('root'))
for k, v in {'bAutomaticallyAddPhysicsBodyComponents': False, 'SimulationSpace': 'World', 'CollisionSpace': 'World',
             'WorldCollisionType': 'Static', 'PositionIterations': 8, 'VelocityIterations': 2, 'FixedTimeStep': 0.0,
             'MaxDeltaTime': 0.0334, 'MaxTimeSteps': 4, 'MaxDepenetrationVelocity': 300.0}.items():
    setp(s + '.SolverSettings.' + k, v)
setp(s + '.TeleportDetection.PositionChangeThreshold', 500.0)
i = c.add(node(P + 'RigUnit_HierarchyInstantiateFromPhysicsAsset', 'RagdollFromPA'))
setp(i + '.PhysicsSolverComponentKey', RAGDOLL); setp(i + '.bUseAutomaticSolver', False)
setp(i + '.PhysicsAsset', '/Game/Assets/Enemies/Burrower/PA_Burrower.PA_Burrower')
setp(i + '.BonesToUse', arr([bone(b) for b in J]))
setp(i + '.bEnableDrives', False); setp(i + '.bMakeHelperBodies', False)
for b in J:
    m = c.add(node(P + 'RigUnit_HierarchySetPhysicsBodyMovementType', 'RagSim_' + b))
    setp(m + '.PhysicsBodyComponentKey', comp(b, 'PhysicsBody')); setp(m + '.MovementType', 'Simulated')
    d = c.add(node(P + 'RigUnit_HierarchySetPhysicsBodyDamping', 'RagDamp_' + b))
    setp(d + '.PhysicsBodyComponentKey', comp(b, 'PhysicsBody'))
    setp(d + '.LinearDamping', 0.1); setp(d + '.AngularDamping', 1.0)
```

Fallback if no physics asset is usable: one `Spawn Physics Body` (`P RigUnit_AddPhysicsBody`) per J bone with an
empty `Collision` (the node then auto-calculates a shape from the joint positions), then `Calculate Physics Collision`
(`P RigUnit_HierarchyAutoCalculateCollision`, `MinSize` = the radii above, which for capsules is the minimum radius),
plus `Spawn Physics Joint` per J1..J4 with `Make Articulation Joint Data` `AngularLimit (20,20,20)`. Body settings are
as in 4.2.

### 4.2 Upper armoured hoses: rigid-body solver (part c)

**C4 `Spawn Physics Solver`**, name `HoseSolver`, `Owner = J1_Forequarters`, so the key is (J1_Forequarters,
PhysicsSolver):

| Pin | Value |
|---|---|
| `SolverSettings.bAutomaticallyAddPhysicsBodyComponents` | False |
| `SolverSettings.SimulationSpace` / `CollisionSpace` | **Component** / Component |
| `SolverSettings.WorldCollisionType` | None |
| `SolverSettings.PositionIterations` / `VelocityIterations` | 12 / 1 (no contacts) |
| `SolverSettings.FixedTimeStep` / `MaxDeltaTime` / `MaxTimeSteps` | 0 / 0.0334 / 4 |
| `SolverSettings.bResetFromEvaluationInterval` + `EvaluationIntervalThresholdForReset` | True, 0.25 s |
| `SpaceMotion.InertialForces.Amount` | 0.5 |
| `SpaceMotion.bClampLinearAcceleration` + `MaxLinearAcceleration` | True, 3000 (cm/s²) |
| `SpaceMotion.bClampAngularVelocity` + `MaxAngularVelocity` | True, **3.0 rad/s** (Physics uses rad/s; Dynamics uses deg/s) |
| `SpaceMotion.bClampAngularAcceleration` + `MaxAngularAcceleration` | True, **20 rad/s²** |
| `SpaceMotion.Drag.LinearDragMultiplier` / `AngularDragMultiplier` | 0.1 / 0.3 |
| `TeleportDetection.PositionChangeThreshold` / `OrientationChangeThreshold` | 500 / 45 |

**C5 shared pure nodes**:
* `Make Articulation Joint Data` (`P RigUnit_MakeArticulationJointData`), name `HoseJointData`:
  `AngularLimit = (X=12,Y=12,Z=12)` (twist, swing1, swing2 in degrees; equal values because which local axis is
  "twist" is unknown for these bones), `SoftStrength = (X=2,Y=2,Z=2)` (negative = hard, 1 = "reasonably soft"),
  `SoftDampingRatio = (1,1,1)`. The output locks linear motion.
* `Make Articulation Drive Data` (`P RigUnit_MakeArticulationDriveData`), name `HoseDriveData`:
  `bEnableAngularDrive True`, `AngularDriveMode SLERP`, `AngularStrength 6`, `AngularDampingRatio 0.8`,
  `AngularExtraDamping 0`, `SkeletalAnimationVelocityMultiplier 1`. `FRigPhysicsDriveData.bUseSkeletalAnimation`
  defaults to true, so the drive pulls back toward the modelled (input) shape.

**C6 per hose bone** `b` at index `k` in `chain_bones(...)` (`_01` .. `_NN`, `_end`):
* `Spawn Physics Body` (`P RigUnit_AddPhysicsBody`), name `HoseBody_<b>`:
  `Owner = b`;
  `Solver = (PhysicsSolverComponentKey=HOSE_SOLVER, bUseAutomaticSolver=False, SourceBone=b, TargetBone=b, bIncludeInChecksForReset=True)`;
  `Dynamics.MassOverride 20`, `Dynamics.LinearDamping 0.5`, `Dynamics.AngularDamping 2.0`;
  `BodyData.MovementType` = **Kinematic** for `_01` and `_end`, **Simulated** for the rest;
  `BodyData.CollisionType = NoCollision` (the hoses need no contacts; joints, limits and drives make the look);
  `Collision`: leave empty for `_01`..`_NN`, so the node auto-calculates a capsule from the bone to its child
  without any axis assumptions. For the leaf `_end` set `Collision.Spheres = ((Radius=6.0))` (a sphere at the bone
  origin, also axis-free).
* For `k > 0`: `Spawn Physics Joint` (`P RigUnit_AddPhysicsJoint`), name `HoseJoint_<b>`: `Owner = b`,
  `ParentBodyComponentKey = comp(prev,'PhysicsBody')`, `ChildBodyComponentKey = comp(b,'PhysicsBody')`; link
  `HoseJointData.JointData` and `HoseDriveData.DriveData` to it. The joint for `_end` connects the last simulated
  segment to the kinematic far anchor (canister nozzle).
* Optional: `Set Physics Body Update Kinematic From Simulation` (`P ...UpdateKinematicFromSimulation`) True on the
  `_end` bodies, so the kinematic anchor is written back after its simulated parent moves it. Step 5.6 also re-pins it.

```python
hs = c.add(node(P + 'RigUnit_SpawnPhysicsSolver', 'HoseSolver'))
setp(hs + '.Owner', bone('J1_Forequarters'))
for k, v in {'bAutomaticallyAddPhysicsBodyComponents': False, 'SimulationSpace': 'Component',
             'CollisionSpace': 'Component', 'WorldCollisionType': 'None', 'PositionIterations': 12,
             'VelocityIterations': 1, 'FixedTimeStep': 0.0, 'MaxDeltaTime': 0.0334, 'MaxTimeSteps': 4,
             'bResetFromEvaluationInterval': True, 'EvaluationIntervalThresholdForReset': 0.25}.items():
    setp(hs + '.SolverSettings.' + k, v)
for k, v in {'InertialForces.Amount': 0.5, 'bClampLinearAcceleration': True, 'MaxLinearAcceleration': 3000.0,
             'bClampAngularVelocity': True, 'MaxAngularVelocity': 3.0, 'bClampAngularAcceleration': True,
             'MaxAngularAcceleration': 20.0, 'Drag.LinearDragMultiplier': 0.1, 'Drag.AngularDragMultiplier': 0.3}.items():
    setp(hs + '.SpaceMotion.' + k, v)
setp(hs + '.TeleportDetection.PositionChangeThreshold', 500.0)
setp(hs + '.TeleportDetection.OrientationChangeThreshold', 45.0)
mj = node(P + 'RigUnit_MakeArticulationJointData', 'HoseJointData')
setp(mj + '.AngularLimit', '(X=12.0,Y=12.0,Z=12.0)'); setp(mj + '.SoftStrength', '(X=2.0,Y=2.0,Z=2.0)')
md = node(P + 'RigUnit_MakeArticulationDriveData', 'HoseDriveData')
setp(md + '.AngularStrength', 6.0); setp(md + '.AngularDampingRatio', 0.8)
for bones in HOSES:
    for k, b in enumerate(bones):
        kin = k == 0 or k == len(bones) - 1
        n = c.add(node(P + 'RigUnit_AddPhysicsBody', 'HoseBody_' + b))
        setp(n + '.Owner', bone(b))
        setp(n + '.Solver', '(PhysicsSolverComponentKey=%s,bUseAutomaticSolver=False,SourceBone=%s,TargetBone=%s,'
                            'bIncludeInChecksForReset=True)' % (HOSE_SOLVER, bone(b), bone(b)))
        setp(n + '.Dynamics.MassOverride', 20.0)
        setp(n + '.Dynamics.LinearDamping', 0.5); setp(n + '.Dynamics.AngularDamping', 2.0)
        setp(n + '.BodyData.MovementType', 'Kinematic' if kin else 'Simulated')
        setp(n + '.BodyData.CollisionType', 'NoCollision')
        if k == len(bones) - 1:
            setp(n + '.Collision.Spheres', '((Radius=6.0))')
        if k > 0:
            j = c.add(node(P + 'RigUnit_AddPhysicsJoint', 'HoseJoint_' + b))
            setp(j + '.Owner', bone(b))
            setp(j + '.ParentBodyComponentKey', comp(bones[k - 1], 'PhysicsBody'))
            setp(j + '.ChildBodyComponentKey', comp(b, 'PhysicsBody'))
            link(mj + '.JointData', j + '.JointData'); link(md + '.DriveData', j + '.DriveData')
```

That is 14 bodies and 12 joints. Upper hoses get no collider: they cannot reach the body with 2-3 % slack, and both
ends are fixed.

### 4.3 Upper cables and side hoses: wire solver (part c)

**C7 `Spawn Dynamics Solver`** (`D RigUnit_SpawnDynamicsSolver1`), name `WireSolver`:

| Pin | Value | Why |
|---|---|---|
| `Owner` | root | |
| `SolverComponentName` | DynamicsSolver (default) | Key (root, DynamicsSolver); read the output pin if the hierarchy appended a suffix |
| `Settings.SimulationSpace` | **Component** | The actor flies fast; the wave moves the J1 anchors truly kinematically inside component space, and actor motion arrives as conditioned pseudo-forces |
| `Settings.Gravity` | (0, 0, -981) default | |
| `Settings.MaxTimeStep` / `MaxNumSteps` | **0.0167** / 4 | Default 1.0 s means no sub-steps |
| `Settings.NumIterations` | 1 | |
| `Settings.NumConstraintSubIterations` | **4** | With 1 the last pass is one-way down the chain, so a kinematic `_end` could never pull its parent; two pinned ends need several two-way passes |
| `Settings.bReadBoneOrientations` / `bReadBonePositions` | True / False | Bones rotate toward the particles and keep their lengths |
| `Settings.bResetFromPosition` + `PositionThresholdForReset` | True, 2000 | Explosion guard (pipes live within ~8 m of the origin) |
| `Settings.bResetFromEvaluationInterval` + threshold | True, 0.25 s | Mesh not ticked while unseen, then seen again |
| `TeleportDetection.PositionChangeThreshold` / `OrientationChangeThreshold` | 500 / 45 | |
| `SpaceMotion.bClampLinearAcceleration` + `MaxLinearAcceleration` | True, 4000 | |
| `SpaceMotion.bClampAngularVelocity` + `MaxAngularVelocity` | True, **180 deg/s** | |
| `SpaceMotion.bClampAngularAcceleration` + `MaxAngularAcceleration` | True, **1440 deg/s²** | |
| `SpaceMotion.InertialForces.Amount` | 0.6 | |
| `SpaceMotion.Drag.LinearDragMultiplier` / `AngularDragMultiplier` | 0.15 / 0.3 | Otherwise at full speed the hoses stream backward |

**C8 `Spawn Dynamics Chains`** (`D RigUnit_SpawnDynamicsChains`), twice. `RootBones` = the `_01` bone of each chain;
the node follows all descendants, so each chain gets particles on `_01`.. `_NN` and `_end`. **This node's constructor
sets `ParticleProperties.GravityMultiplier = 0`; set it to 1.**

| ParticleProperties | `SideHoseChains` (4 side hoses) | `CableChains` (2 upper cables) |
|---|---|---|
| `DynamicsSolverComponentKey` | WIRE | WIRE |
| `RootBones` | pipe_side_l_a_01, _l_b_01, _r_a_01, _r_b_01 | pipe_uppercable_l_01, pipe_uppercable_r_01 |
| `Radius` | 3.6 | 3.2 |
| `Mass` | 1 | 0.5 |
| `MovementType` | Simulated | Simulated |
| `GravityMultiplier` | **1** | **1** |
| `Strength` (Hz, target tracking) | 1.5 | 3.0 |
| `DampingRatio` | 0.6 | 0.7 |
| `TargetMode` | 0.7 (mostly directional) | 0.7 |
| `AngleLimit` / `AngleLimitStrength` | 40° / 6 Hz | 25° / 10 Hz |
| `Damping` (air, Hz) | 1.5 | 2.0 |
| `bCollideWithColliders` | True | False |

`ChainCurves`: leave flat. The output keys are (bone, `DynamicsParticle`).

**C9** Pin both ends. For each chain in SIDES + CABLES and each of `<chain>_01` and `<chain>_end`:
`Set Dynamics Particle Movement Type` (`D RigUnit_HierarchySetDynamicsParticleMovementType`),
`DynamicsParticleComponentKey = comp(b,'DynamicsParticle')`, `MovementType = Kinematic` (12 nodes). Kinematic
particles track their bone's input pose.

**C10 flank collider** for the side hoses: `Spawn Dynamics Collider` (`D RigUnit_SpawnDynamicsCollider`), name
`FlankCollider`, `Owner = J1_Forequarters`, `DynamicsSolverComponentKey = WIRE`, `Shapes.Capsules` = one capsule named
`Flank`. In **component** space it is: centre (465, 0, 170), axis along +X, `Radius 165`, `Length 160` (core; total =
Length + 2·Radius). That puts it 11 cm inside the closest side-hose rest point, so it only stops large swings into the
body and never pushes a hose at rest. One capsule on Y = 0 serves both sides. The shape `TM` must be in J1's local
frame and the capsule's main axis is its +Z, so convert in Python from the rig's initial pose:

```python
j1 = H.get_global_transform(unreal.RigElementKey(type=unreal.RigElementType.BONE, name='J1_Forequarters'), True)
tm_comp = unreal.Transform(location=unreal.Vector(465, 0, 170),
                           rotation=unreal.MathLibrary.make_rot_from_z(unreal.Vector(1, 0, 0)),
                           scale=unreal.Vector(1, 1, 1))
tm_local = unreal.MathLibrary.make_relative_transform(tm_comp, j1)     # = tm_comp * inverse(j1)
```

Why not just import colliders from the physics asset (`D RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset1`,
`ElementIncludeMask = [J1_Forequarters]`)? The body-sized J1 capsule (r ≈ 185 around z ≈ 195) passes through the hose
rest positions (they are 180-209 cm from that axis), so it would shove the hoses outward at rest. The node is fine for
a quick look with `bShowColliders`.

Colliders follow the hierarchy pose at step time, not the simulated pose. Here that is the pose after the ragdoll step,
because the wire step runs later (Step 5), so the collider follows a dead J1 too.

```python
ds = c.add(node(D + 'RigUnit_SpawnDynamicsSolver1', 'WireSolver'))
setp(ds + '.Owner', bone('root')); setp(ds + '.SolverComponentName', 'DynamicsSolver')
for k, v in {'SimulationSpace': 'Component', 'MaxTimeStep': 0.0167, 'MaxNumSteps': 4, 'NumConstraintSubIterations': 4,
             'bResetFromPosition': True, 'PositionThresholdForReset': 2000.0,
             'bResetFromEvaluationInterval': True, 'EvaluationIntervalThresholdForReset': 0.25}.items():
    setp(ds + '.Settings.' + k, v)
setp(ds + '.TeleportDetection.PositionChangeThreshold', 500.0)
setp(ds + '.TeleportDetection.OrientationChangeThreshold', 45.0)
for k, v in {'bClampLinearAcceleration': True, 'MaxLinearAcceleration': 4000.0, 'bClampAngularVelocity': True,
             'MaxAngularVelocity': 180.0, 'bClampAngularAcceleration': True, 'MaxAngularAcceleration': 1440.0,
             'InertialForces.Amount': 0.6, 'Drag.LinearDragMultiplier': 0.15, 'Drag.AngularDragMultiplier': 0.3}.items():
    setp(ds + '.SpaceMotion.' + k, v)
def chains(name, roots, props):
    n = c.add(node(D + 'RigUnit_SpawnDynamicsChains', name))
    setp(n + '.DynamicsSolverComponentKey', WIRE)
    setp(n + '.RootBones', arr([bone(r + '_01') for r in roots]))
    for k, v in props.items(): setp(n + '.ParticleProperties.' + k, v)
chains('SideHoseChains', SIDES, dict(Radius=3.6, Mass=1.0, GravityMultiplier=1.0, Strength=1.5, DampingRatio=0.6,
       TargetMode=0.7, AngleLimit=40.0, AngleLimitStrength=6.0, Damping=1.5, bCollideWithColliders=True))
chains('CableChains', CABLES, dict(Radius=3.2, Mass=0.5, GravityMultiplier=1.0, Strength=3.0, DampingRatio=0.7,
       TargetMode=0.7, AngleLimit=25.0, AngleLimitStrength=10.0, Damping=2.0, bCollideWithColliders=False))
for ch in SIDES + CABLES:
    for b in (ch + '_01', ch + '_end'):
        m = c.add(node(D + 'RigUnit_HierarchySetDynamicsParticleMovementType', 'Pin_' + b))
        setp(m + '.DynamicsParticleComponentKey', comp(b, 'DynamicsParticle')); setp(m + '.MovementType', 'Kinematic')
col = c.add(node(D + 'RigUnit_SpawnDynamicsCollider', 'FlankCollider'))
setp(col + '.Owner', bone('J1_Forequarters')); setp(col + '.DynamicsSolverComponentKey', WIRE)
setp(col + '.Shapes', '(Capsules=((Name="Flank",TM=%s,Radius=165.0,Length=160.0)))' % tm_local.export_text())
```

### 4.4 Instantiate (optional, at the end of Construction)

`Instantiate physics` (`P RigUnit_InstantiatePhysics`) for RAGDOLL and for HOSE_SOLVER, then `Instantiate dynamics`
(`D RigUnit_InstantiateDynamics`) for WIRE. These happen on the first step anyway; doing them here moves the
allocation to spawn time instead of the first frame (or, for the ragdoll, possibly the death frame). If one of them
warns in the Construction Event, delete it.

---

## Step 5: Forwards Solve graph (execution order matters)

Chain from the existing **Forwards Solve** event (`CR RigUnit_BeginExecution`):

```python
ev_f = next(n.get_name() for n in G.get_nodes()
            if isinstance(n, unreal.RigVMUnitNode) and n.get_script_struct().get_name() == 'RigUnit_BeginExecution')
f = Chain(ev_f)
```

Order: **5.1 wave (J1..J4) → 5.3 ragdoll step → 5.4 rotor → 5.5 hose step → 5.6 wire step → (5.6 re-pin ends)**.
The wave is first, so the kinematic anchors and the ragdoll's pass-through tracking see the waved body. The rotor comes
after the ragdoll so it sits on the dead head. Pipes come last so they follow both.

**RigVM caveat:** pure nodes are evaluated just before the first mutable node that needs them, and the result is then
reused. Do not share a `Get Transform` node between a consumer before a step and one after it. Each block below makes
its own getters.

### 5.1 Travelling sine wave on J1..J4 (part b)

Shared pure nodes:
* `Theta0 = WaveTime * WaveTimeToRadians` (MathFloatMul)
* `Phi = Rad(WavePhasePerJointDeg)` (MathFloatRad)

Per joint `i` (head → tail) with yaw weight `wy` and pitch weight `wp`:

| i | Bone | Parent (for the axes) | wy | wp | At WaveAmplitudeDeg 14 / WavePitchAmplitudeDeg 6 |
|---|---|---|---|---|---|
| 1 | J1_Forequarters | J0_Head | 0.40 | 0.65 | 5.6° / 3.9° |
| 2 | J2_Midbody | J1_Forequarters | 0.60 | **0.15** | 8.4° / 0.9° |
| 3 | J3_Hindbody | J2_Midbody | 0.80 | 0.65 | 11.2° / 3.9° |
| 4 | J4_Tail | J3_Hindbody | 1.00 | 1.00 | 14° / 6° |

The yaw ramp rises toward the tail as requested. The pitch weight is low at J2 because the rig's own limits say J2 can
lift only about 2° before the vent housing (on J2) hits the canister pack (on J1). The lead's "comfortable range" per
joint is 10/6/14/18° sideways and 4/1/4/6° up-down; beyond 10-15° the armour seams open. So keep
`WaveAmplitudeDeg ≤ 14` and `WavePitchAmplitudeDeg ≤ 6`. J0_Head gets no wave: the head keeps facing the target and
the rotor box stays where the C++ expects it.

Maths per joint (radians), wave travelling head → tail:

```
theta_i = Theta0 - i * Phi
yaw_i   = Rad(WaveAmplitudeDeg * wy) * sin(theta_i)
pitch_i = Rad(WavePitchAmplitudeDeg * wp) * cos(theta_i)       // 90° ahead of yaw: a slight corkscrew
UpAxis_i   = Inverse(ParentInitialGlobal.Rotation) rotates (0,0,1)   // the body's up, in the parent's frame
SideAxis_i = Inverse(ParentInitialGlobal.Rotation) rotates (0,1,0)   // the body's lateral axis, in the parent's frame
QDelta_i = QuatFromAxisAndAngle(UpAxis_i, yaw_i) * QuatFromAxisAndAngle(SideAxis_i, pitch_i)
NewLocalRot_i = QDelta_i * Local_i.Rotation       // pre-multiply = rotate in the parent's frame about the joint
Set Rotation (Ji, LocalSpace, NewLocalRot_i, PropagateToChildren = true)
```

The axes come from the rest pose (`bInitial = true`), so no bone-local axis is assumed. Rotations are added to the
input local rotation, so any future animation input still works underneath. Local rotations compound down the chain,
which turns the per-joint sine into a smooth body curve.

```python
M = VM
th0 = node(M + 'MathFloatMul', 'Wave_Theta0'); link(var_get('WaveTime'), th0 + '.A'); link(var_get('WaveTimeToRadians'), th0 + '.B')
phi = node(M + 'MathFloatRad', 'Wave_Phi'); link(var_get('WavePhasePerJointDeg'), phi + '.Value')
ampY, ampP = var_get('WaveAmplitudeDeg'), var_get('WavePitchAmplitudeDeg')
for b, parent, i, wy, wp in [('J1_Forequarters', 'J0_Head', 1, 0.40, 0.65), ('J2_Midbody', 'J1_Forequarters', 2, 0.60, 0.15),
                             ('J3_Hindbody', 'J2_Midbody', 3, 0.80, 0.65), ('J4_Tail', 'J3_Hindbody', 4, 1.00, 1.00)]:
    t = 'W%d_' % i
    lag = node(M + 'MathFloatMul', t + 'Lag'); link(phi + '.Result', lag + '.A'); setp(lag + '.B', float(i))
    th = node(M + 'MathFloatSub', t + 'Theta'); link(th0 + '.Result', th + '.A'); link(lag + '.Result', th + '.B')
    sn = node(M + 'MathFloatSin', t + 'Sin'); link(th + '.Result', sn + '.Value')
    cs = node(M + 'MathFloatCos', t + 'Cos'); link(th + '.Result', cs + '.Value')
    def scaled(amp, w, trig, tag):
        a = node(M + 'MathFloatMul', t + tag + 'Amp'); link(amp, a + '.A'); setp(a + '.B', w)
        r = node(M + 'MathFloatRad', t + tag + 'Rad'); link(a + '.Result', r + '.Value')
        o = node(M + 'MathFloatMul', t + tag); link(r + '.Result', o + '.A'); link(trig + '.Result', o + '.B')
        return o + '.Result'
    yaw, pitch = scaled(ampY, wy, sn, 'Yaw'), scaled(ampP, wp, cs, 'Pitch')
    pi_ = node(CR + 'RigUnit_GetTransform', t + 'ParentInit')
    setp(pi_ + '.Item', bone(parent)); setp(pi_ + '.Space', 'GlobalSpace'); setp(pi_ + '.bInitial', True)
    inv = node(M + 'MathQuatInverse', t + 'ParentInv'); link(pi_ + '.Transform.Rotation', inv + '.Value')
    def axis(vec, tag):
        a = node(M + 'MathQuatRotateVector', t + tag); link(inv + '.Result', a + '.Transform'); setp(a + '.Vector', vec)
        return a + '.Result'
    qy = node(M + 'MathQuatFromAxisAndAngle', t + 'QYaw'); link(axis('(X=0.0,Y=0.0,Z=1.0)', 'Up'), qy + '.Axis'); link(yaw, qy + '.Angle')
    qp = node(M + 'MathQuatFromAxisAndAngle', t + 'QPitch'); link(axis('(X=0.0,Y=1.0,Z=0.0)', 'Side'), qp + '.Axis'); link(pitch, qp + '.Angle')
    qd = node(M + 'MathQuatMul', t + 'QDelta'); link(qy + '.Result', qd + '.A'); link(qp + '.Result', qd + '.B')
    lo = node(CR + 'RigUnit_GetTransform', t + 'Local'); setp(lo + '.Item', bone(b)); setp(lo + '.Space', 'LocalSpace')
    qn = node(M + 'MathQuatMul', t + 'QNew'); link(qd + '.Result', qn + '.A'); link(lo + '.Transform.Rotation', qn + '.B')
    sr = f.add(node(CR + 'RigUnit_SetRotation', t + 'Set'))
    setp(sr + '.Item', bone(b)); setp(sr + '.Space', 'LocalSpace'); setp(sr + '.bPropagateToChildren', True)
    link(qn + '.Result', sr + '.Value')
```

### 5.2 Optional: speed gate on the amplitude

Use this only if the C++ does not already scale the amplitude with speed (open question 2). Multiply both amplitude
getters by `Clamp(Speed / 800, 0.3, 1.0)` (MathFloatDiv or Mul by 1/800, then MathFloatClamp) before they enter
`scaled(...)`. `RotorSpinSpeed` is not used by the graph.

### 5.3 Ragdoll step (part d)

* `DeadAlpha = BoolToFloat(bIsDead)` (`VM MathBoolToFloat` [unverified]; alternatives are an `If` node on float, or
  `Clamp(DeathTime / 0.1, 0, 1)` if DeathTime is seconds since death, for a 0.1 s blend-in).
* **`Step Physics Solver`** (`P RigUnit_StepPhysicsSolver1`), name `StepRagdoll`:
  `PhysicsSolverComponentKey = RAGDOLL`, `Alpha ← DeadAlpha`, `bTrackVelocitiesDuringPassThrough = True`,
  `DeltaTimeOverride 0`, `SimulationSpaceDeltaTimeOverride 0`. Debug only: `VisualizationSettings.bShowBodies`,
  `bShowJoints`, `bShowWorldObjects`, `bShowWorldOverlapBox`, `bShowActiveContacts`; the CVar
  `ControlRig.Physics.AllowVisualization` gates them.
* How the switch works: Alpha 0 = pass-through (no simulation, no write-back, near-zero cost, velocities tracked).
  Alpha 1 = the bodies, already Simulated since Construction, take over J0..J4. The effective blend per body is
  `Alpha * PhysicsBlendWeight`, and `PhysicsBlendWeight` defaults to 1. J0_Head has no joint to anything, so the whole
  chain falls; J1..J4 hang off it through the asset's limited constraints.
* World collision (ground): `SolverSettings.WorldCollisionType = Static` from C1. A game-thread task gathers world
  objects inside the bodies' bounds × `WorldCollisionBoundsExpansion` and adds them to the simulation as kinematic
  collision. Only QueryAndPhysics objects are used here (`bWorldCollisionIncludePhysics`). This setting has **no
  runtime setter** in the 5.8 headers; it is fixed at construction. Dynamics (wires) has no world collision at all in
  5.8; its solver header says world collision is only "in anticipation".
* Optional death kick: on the first dead frame, `Add Force` (`P RigUnit_HierarchyAddPhysicsBodyForce`) on
  (J0_Head, PhysicsBody) with a small downward/forward impulse. Gate it with a once-only node.

```python
b2f = node(VM + 'MathBoolToFloat', 'DeadAlpha'); link(var_get('bIsDead', 'bool'), b2f + '.Value')
rs = f.add(node(P + 'RigUnit_StepPhysicsSolver1', 'StepRagdoll'))
setp(rs + '.PhysicsSolverComponentKey', RAGDOLL); setp(rs + '.bTrackVelocitiesDuringPassThrough', True)
link(b2f + '.Result', rs + '.Alpha')
```

### 5.4 Rotor spin (part a)

```
J0G       = Get Transform (J0_Head, Global, bInitial=false)   // after the ragdoll step
J0I       = Get Transform (J0_Head, Global, bInitial=true)
RI        = Get Transform (Rotor,   Global, bInitial=true)
Offset    = MakeRelative(Global=RI, Parent=J0I)                // rest-pose offset J0_Head -> Rotor
AxisLocal = Inverse(RI.Rotation) rotates (1,0,0)               // the body's long axis in the rotor's own frame
Spin      = Transform(Rotation = QuatFromAxisAndAngle(AxisLocal, Rad(RotorAngleDeg)))
Final     = Spin * Offset * J0G                               // maths: J0G ∘ Offset ∘ Spin
Set Transform (Rotor, Global, Final, PropagateToChildren=false)
```

The spin is applied first, in the rotor's own frame, so it turns about the rotor bone origin, which is the rotor
centre (977.9, 0, 180.5). Alive, J0_Head is not moved by the wave, so the rotor stays exactly at its rest place and
only spins. That is also where the C++ `RotorBox` expects it.

```python
j0 = node(CR + 'RigUnit_GetTransform', 'Rotor_J0'); setp(j0 + '.Item', bone('J0_Head')); setp(j0 + '.Space', 'GlobalSpace')
j0i = node(CR + 'RigUnit_GetTransform', 'Rotor_J0Init'); setp(j0i + '.Item', bone('J0_Head')); setp(j0i + '.Space', 'GlobalSpace'); setp(j0i + '.bInitial', True)
ri = node(CR + 'RigUnit_GetTransform', 'Rotor_Init'); setp(ri + '.Item', bone('Rotor')); setp(ri + '.Space', 'GlobalSpace'); setp(ri + '.bInitial', True)
rel = node(VM + 'MathTransformMakeRelative', 'Rotor_Offset'); link(ri + '.Transform', rel + '.Global'); link(j0i + '.Transform', rel + '.Parent')
inv = node(VM + 'MathQuatInverse', 'Rotor_InitInv'); link(ri + '.Transform.Rotation', inv + '.Value')
ax = node(VM + 'MathQuatRotateVector', 'Rotor_Axis'); link(inv + '.Result', ax + '.Transform'); setp(ax + '.Vector', '(X=1.0,Y=0.0,Z=0.0)')
ang = node(VM + 'MathFloatRad', 'Rotor_Rad'); link(var_get('RotorAngleDeg'), ang + '.Value')
q = node(VM + 'MathQuatFromAxisAndAngle', 'Rotor_Q'); link(ax + '.Result', q + '.Axis'); link(ang + '.Result', q + '.Angle')
sp = node(VM + 'MathTransformMake', 'Rotor_Spin'); link(q + '.Result', sp + '.Rotation')
m1 = node(VM + 'MathTransformMul', 'Rotor_M1'); link(sp + '.Result', m1 + '.A'); link(rel + '.Local', m1 + '.B')
m2 = node(VM + 'MathTransformMul', 'Rotor_M2'); link(m1 + '.Result', m2 + '.A'); link(j0 + '.Transform', m2 + '.B')
st = f.add(node(CR + 'RigUnit_SetTransform', 'Rotor_Set'))
setp(st + '.Item', bone('Rotor')); setp(st + '.Space', 'GlobalSpace'); setp(st + '.bPropagateToChildren', False)
link(m2 + '.Result', st + '.Value')
```

### 5.5 Hose step

`Step Physics Solver` (`P RigUnit_StepPhysicsSolver1`), name `StepHoses`: `PhysicsSolverComponentKey = HOSE_SOLVER`,
`Alpha 1`, `bTrackVelocitiesDuringPassThrough True`.

### 5.6 Wire step and end re-pin

`Step Dynamics Solver` (`D RigUnit_StepDynamicsSolver`), name `StepWires`: `DynamicsSolverComponentKey = WIRE`,
`Alpha 1`, `bTrackVelocitiesDuringPassThrough True`, `DeltaTimeOverride 0` (a negative value freezes the solver, which
is useful for a distance LOD later). Debug only: `VisualizationSettings.bShowParticles`, `bShowColliders`,
`bShowSkeletalConstraints`, `bShowAngleLimits`; the CVar `ControlRig.Dynamics.AllowVisualization` gates them.

**End re-pin (recommended):** right after 5.4 and before 5.5, read `Get Transform (<chain>_end, Global)` for all 8
chains and store each in a rig variable of type FTransform (`Set Variable` nodes) or keep the getter's value. After
5.6, `Set Transform (<chain>_end, Global, stored, PropagateToChildren=false)`. Rotating the parent bones toward the
particles can leave the `_end` fitting a few cm off its anchor when a constraint is not fully satisfied; this puts it
back exactly. Skip it if the `_end` bones carry no skin weights.

```python
for nm, path, keypin, key in (('StepHoses', P + 'RigUnit_StepPhysicsSolver1', 'PhysicsSolverComponentKey', HOSE_SOLVER),
                              ('StepWires', D + 'RigUnit_StepDynamicsSolver', 'DynamicsSolverComponentKey', WIRE)):
    n = f.add(node(path, nm)); setp(n + '.' + keypin, key); setp(n + '.Alpha', 1.0)
    setp(n + '.bTrackVelocitiesDuringPassThrough', True)
unreal.BlueprintEditorLibrary.compile_blueprint(rig)     # or rig.recompile_vm()  [unverified]
unreal.EditorAssetLibrary.save_loaded_asset(rig)
```

---

## Step 6: AnimBP (part e)

1. Create **ABP_Burrower**. Skeleton = the Burrower skeleton; **Parent Class = `BurrowerAnimInstance`** (the C++ class
   fills the properties in its thread-safe update).
2. **AnimGraph:** `Control Rig` node (class `CR_Burrower`) → `Output Pose`. Leave its source pose unconnected or feed
   it nothing else; an unlinked pose input evaluates to the reference pose. **No state machine, no other nodes.**
3. In the Control Rig node's details, under Input, expose each variable as a pin and connect the anim instance's
   properties of the same name (the C++ members are thread-safe, fast-path getters): RotorAngleDeg, RotorSpinSpeed,
   WaveTime, WaveAmplitudeDeg, WavePhasePerJointDeg, WavePitchAmplitudeDeg, Speed, bIsDead, DeathTime. The private
   `WaveTimeToRadians` stays internal.
4. Node settings: Alpha 1, LOD Threshold -1 (the 20 m creature stays visible from far away), **Transfer Input Pose
   on** (the default). This matters: every frame it resets the pipe bones to the reference pose before the rig runs,
   which is what keeps the kinematic `_end` anchors fixed to J1 and stops the simulated pose from feeding back into
   itself.
5. EventGraph: empty. Class Settings: Use Multi-Threaded Animation Update on (the default).
6. BP_Burrower: Mesh → Anim Class = ABP_Burrower.

The AnimGraph probably cannot be built with stock editor Python. Do these few clicks by hand, or use an MCP toolset if
the editor's `AllToolsets` plugin offers AnimGraph editing.

---

## Step 7: Coupling to the C++ death flow (check in BP_Burrower / ABurrowerCharacter)

* The base `AMyCharBase::MulticastHandleDeath_Implementation` (MyCharBase.cpp lines 132-149) calls
  `GetMesh()->SetSimulatePhysics(true)`. A simulating skeletal mesh takes the bones away from the AnimBP, so the
  Control Rig ragdoll would never be seen. `ABurrowerCharacter` must override it so that, with
  `bUseMeshRagdollFallback = false`, the mesh does **not** simulate. Its collision stays QueryOnly or is set to
  NoCollision. Once the rig ragdoll works, set **bUseMeshRagdollFallback = false** in BP_Burrower.
* Keep `GetCapsuleComponent()->SetCollisionEnabled(NoCollision)` on death (the base already does it). Otherwise the
  rig's world collision gathers the Burrower's own capsule (QueryAndPhysics, Pawn) and the corpse lands on it.
* Stop and disable movement on death (`DisableMovement`). With a NoCollision capsule in flying or falling mode, the
  actor would otherwise drift or fall through the world. The World-space ragdoll does not care, but culling and bounds
  follow the actor.
* `bIsDead` must become true on every machine. The base sets `bIsDead` inside the multicast, so the anim instance
  reading the character's `bIsDead` works on clients. `AMyEnemyChar::LifeSpan` (5 s) gives the ragdoll its time.
* RotorBox is attached to the mesh (no socket) at the rotor's rest centre (977.9, 0, 180.5). **Do not give it a
  Parent Socket in BP_Burrower**: a server that does not render the Burrower does not refresh its bones, so a box on
  the `Rotor` bone would cut with a stale pose there, on the Blender bone's axes. Alive, the rig keeps the Rotor bone
  at that spot and only spins it (J0_Head gets no wave), so the box matches the visual rotor. Its Y and Z
  half-extents are equal (105.8 + padding each), so the spin does not change the coverage.

---

## Step 8: Test plan

1. **Rig editor, wave:** set the defaults WaveAmplitudeDeg 10, WavePhasePerJointDeg 65, WavePitchAmplitudeDeg 3. Set
   WaveTime to 0, 0.25, 0.5, 0.75: the body should bend left/right with the crest moving tailward; J0 and the rotor
   should not move. To animate in the editor, temporarily add the rig's accumulated time to WaveTime, or test in PIE.
2. **Rig editor, rotor:** RotorAngleDeg 0 / 45 / 90 should spin the disc about the body's long axis with no wobble or
   drift; the centre stays at (977.9, 0, 180.5).
3. **Rig editor, pipes:** turn on the visualization flags on StepHoses and StepWires. All 8 chains should show both
   ends pinned (kinematic), the middles sagging slightly, the flank capsule clear of the side hoses at rest, and the
   upper hoses holding their modelled shape. Moving the preview mesh or changing WaveTime should make them lag and
   swing, then settle.
4. **Rig editor, ragdoll:** set bIsDead default = true; the body should drop and fold within the joint limits. The
   preview has no game world, so for this test only you can add a ground box to RagdollSolver
   `SolverSettings.Collision` (World collision space, top at z = 0). **Remove it afterwards**: the hex platforms float,
   and there is no real ground at a fixed height in game.
5. **PIE (listen server + 1 client):** `Aura.Burrower.SpawnNow`. Check wave, rotor and pipes on both machines. Kill it
   with abilities: it should collapse onto the tiles (with `bShowWorldObjects` you see the gathered tiles), the pipes
   should follow the corpse, the rotor should stay on the head, and nothing should pop on the death frame. Try a death
   while the body is partly inside tiles: it should push out slowly (MaxDepenetrationVelocity).
6. **Cost:** `stat anim` with 4 Burrowers alive. The ragdoll costs about nothing while alive (pass-through).

---

## Step 9: Pitfalls (part f)

* **Plugin and experimental status.** ControlRigPhysics must be enabled in Aura.uproject (the brief says it was not
  yet; the C++ change adds it), and the editor restarted. Both plugins are experimental, and 5.8 already deprecated
  several nodes with identical display names (table in Step 3). Pick nodes by struct path, not by display name.
* **Events.** The spawn, instantiate-from-asset, collision and target-bone setup nodes work only in the Construction
  Event; elsewhere they log "can only be used during Setup" and do nothing. The movement type, damping, gravity, blend
  weight, force, Set-Solver-SpaceMotion/TeleportDetection and step nodes run in Forwards Solve. No Pre-/Post-Forwards
  Solve events are needed.
* **Defaults that bite:** `Spawn Dynamics Chains` sets GravityMultiplier = 0. The Dynamics node defaults point at a bone
  named "Root". Dynamics `MaxTimeStep` = 1 s means no sub-steps. `NumConstraintSubIterations` = 1 cannot hold two
  pinned ends. Teleport `PositionChangeThreshold` = 100 cm per update is hit by a fast flyer at low fps. Physics
  `FixedTimeStep` = 0.02 (fixed 50 Hz steps without interpolation can stutter at 60/120 fps; this recipe uses variable
  steps). Instantiate-from-PA makes *Default* bodies **Kinematic**.
* **Units differ between the plugins:** Physics `SpaceMotion.MaxAngularVelocity/Acceleration` are rad/s and rad/s²;
  Dynamics uses deg/s and deg/s².
* **Simulation space.** The pipes use Component space: the actor moves fast (MaxFlySpeed in the thousands of cm/s), so
  World space would need long sub-steps, would stream the hoses in the drag, and would see every spawn or teleport as a
  huge kinematic jump. In Component space the body wave is exact kinematic motion of the anchors, and actor motion
  comes in as clamped, scaled pseudo-forces (InertialForces.Amount, clamps, Drag multipliers). The ragdoll uses World
  space: it only simulates after death, when the actor stops and the corpse must keep its momentum and fall in world
  coordinates.
* **Spawn and reset.** A new Burrower builds a fresh rig (Construction runs when the anim instance initialises), so no
  reset is needed at spawn. If the C++ ever teleports a live Burrower, teleport detection zeroes the velocities for
  that frame. For a hard reset, run the pipe steps with Alpha 0 and `bTrackVelocitiesDuringPassThrough = false` for one
  frame (they re-initialise with zero velocity). Driving that from a public bool rig variable is optional.
  `bResetFromEvaluationInterval` (0.25 s) covers the mesh not being ticked while off screen
  (`VisibilityBasedAnimTickOption`).
* **Ragdoll fallback if Alpha-0 pass-through pops at death:** keep `StepRagdoll.Alpha = 1` always, leave the bodies
  Kinematic in Construction (delete the RagSim nodes), and in Forwards Solve before StepRagdoll set
  `Set Physics Body Movement Mode` to Simulated on J0..J4 only when bIsDead (Branch on bIsDead). This costs a full
  ragdoll simulation every frame while alive.
* **World collision unknowns.** Whether the gathered world objects include individual ISM instances (the hex tiles are
  one ISM component with many instances) and whether the owner's own components are excluded cannot be read from the
  headers. Check with `bShowWorldObjects` / `bShowWorldOverlapBox`. If tiles are not seen, accept falling through, or
  try WorldCollisionType All. Collapsing tiles that become Geometry Collections are dynamic and not collided with
  `Static`.
* **Mesh simulation conflict:** see Step 7. A skeletal mesh with SimulatePhysics(true) overrides the rig.
* **Pure-node evaluation order:** see Step 5. Separate getters for before and after the steps.
* **Axis assumptions:** none are made in the graph. If a hand-built shape ends up rotated wrong, it is because a TM was
  typed in bone-local space; convert from component space as in C10.
* **Multiplayer:** all of this runs on every machine and is cosmetic, so corpses differ slightly per machine. Gameplay
  does not read pipe or ragdoll bones. The RotorBox is on the mesh at the rotor's rest centre, not on a bone, and alive
  the `Rotor` bone stays there (a fixed offset from `root` plus spin).
* **Visualization costs a lot:** turn every bShow flag off before profiling or shipping.

---

## Step 10: Tuning cheat sheet

| Want | Change |
|---|---|
| Bigger or smaller body swing | `WaveAmplitudeDeg` (≤ 14), the per-joint `wy` weights |
| Longer or shorter wavelength along the body | `WavePhasePerJointDeg` (45 = long, 90 = about one full wave over J1..J4) |
| Side hoses floppier | lower `Strength` (1.0), lower `AngleLimitStrength`, raise `InertialForces.Amount` |
| Side hoses calmer | raise `Damping` (2-3), raise `DampingRatio` (0.8) |
| Hoses fly out on sharp turns | lower `MaxAngularVelocity/Acceleration`, lower `InertialForces.Amount` |
| Upper hoses stiffer | raise `HoseDriveData.AngularStrength` (10), lower `AngularLimit` (8) |
| Corpse too floppy or too stiff | asset constraint limits (20° → 10-30°), `RagDamp` angular damping |
| Corpse jumps out of tiles | lower `MaxDepenetrationVelocity` (100) |

---

## Open questions and unverified items

1. **WaveTime and DeathTime units** must match `UBurrowerAnimInstance`. The rig assumes WaveTime is in cycles (the
   rig variable `WaveTimeToRadians` adapts it: 2π, 1 or π/180) and DeathTime is seconds since death (used only by the
   optional Alpha ramp).
2. Does the C++ already scale `WaveAmplitudeDeg` with speed? If yes, skip Step 5.2.
3. **[unverified]** Core Control Rig / RigVM struct paths and pin names (events, Get/Set Transform/Rotation, RigVM
   math, `MathBoolToFloat`, the execute pin name) and the editor Python method names
   (`create_control_rig_from_skeletal_mesh_or_skeleton`, `add_member_variable`, `add_unit_node_from_struct_path`,
   `add_variable_node`, `set_pin_default_value`, `hierarchy.get_global_transform`, `make_rot_from_z`,
   `make_relative_transform`, `export_text`). These headers were not staged; Step 3 checks them.
4. **[unverified]** PhysicsControl types (`FPhysicsControlModifierData` field defaults, `EPhysicsMovementType` value
   names beyond Kinematic/Simulated, `EAngularDriveMode::SLERP` text) were not staged. The field names MovementType,
   CollisionType, bEnableCCD, KinematicTargetSpace, GravityMultiplier, PhysicsBlendWeight and
   bUpdateKinematicFromSimulation are confirmed by the plugin .cpp files.
5. ControlRigPhysics' .uplugin (its dependencies and experimental flag) was not staged.
6. The RigVM text format for an object pin default (`PhysicsAsset`): set it in the details panel if the string is
   refused.
7. Whether Alpha-0 pass-through resumes Simulated bodies cleanly at death (the header says it does; the fallback is in
   Step 9).
8. Whether world collision sees ISM tile instances and excludes the Burrower's own components (Step 9).
9. The Y sign of the `_l` chains in UE (expected negative) and whether the importer adds a bone above `root`
   (Step 0). Neither changes the rig.
