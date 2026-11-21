# Burrower: editor session on the user's machine

This is the work order for the Claude Code session that runs on the user's machine (UE 5.8 source build at
`/mnt/new_partition/5.8`, project `/mnt/new_partition/UnrealProjects/AuraRedo3`, Linux). Everything that needs the
compiler or the editor is here. The C++, the FBX and the research were done in the cloud on branch
`claude/project-thread-78otz4` (made from `redo3`).

The user's request, in short: a Burrower character from the FBX that (1) spawns behind each player at a distance,
after an interval, per player, (2) follows its player, (3) has an ASC with attributes and takes damage,
(4) has a physics asset with simple shapes and goes ragdoll in the Control Rig when it dies, (5) has bones and
weights for the upper and side pipes driven by Control Rig dynamics (rigid body and wire where each makes sense),
(6) moves its whole body in a travelling sine wave, (7) spins its cutter rotor, and a padded box on the rotor
activates (collapses) HexPlatform tiles as soon as it overlaps them.

Read these first (all in `Docs/Burrower/`):
* `cpp_notes.md`: what the C++ does, what assets and settings it expects (section "What the editor session must
  create or set"), what is unverified.
* `control_rig_recipe.md`: CR_Burrower step by step (rotor spin, body wave, pipe dynamics, ragdoll, AnimBP).
* `gas_patterns.md`, `hex_api.md`: background for the GAS setup and the hex tile API.
* `../../SourceArt/Burrower/Burrower_rig_info.json`: the skeleton's pipe chains (bones, anchor, wire / rigid body
  type, lengths), rotor centre and size.

## Ground rules

* Do not lose the user's work. First run `git status` in the project. If there are uncommitted changes, do not
  stash, reset or check out over them: stop and report back what is uncommitted. If the tree is clean:
  `git fetch origin claude/project-thread-78otz4 && git checkout claude/project-thread-78otz4 && git lfs pull`.
  Work and commit on that branch only; push with `git push -u origin claude/project-thread-78otz4`. Never push
  to `redo3` or `main`.
* If the Unreal Editor is already running with this project, do not kill it (it may hold unsaved work). Report back
  and wait, or use the editor's MCP server (the ModelContextProtocol and AllToolsets plugins are enabled in the
  project) if it is reachable.
* Build with the engine's tools (for example `/mnt/new_partition/5.8/Engine/Build/BatchFiles/Linux/Build.sh
  AuraEditor Linux Development -Project=/mnt/new_partition/UnrealProjects/AuraRedo3/Aura.uproject`, or the
  project's Makefile). Fix compile errors in the Burrower code and the small `AMyHexPlatform` change; keep fixes
  minimal and do not change shared gameplay code beyond what the notes call out.
* Editor-side assets can be made headless (`UnrealEditor-Cmd Aura.uproject -run=pythonscript -script=...`) or in a
  running editor through Python / MCP. Prefer scripts you keep under `Docs/Burrower/scripts/` and commit, so the
  work can be repeated.
* Commit assets (they go to LFS through `.gitattributes`) and config together with a clear message.

## Steps

1. **Branch and build.** Check out the branch (rules above), build `AuraEditor`. The uproject now enables
   `ControlRigPhysics` (beta engine plugin, depends on ControlRig and PhysicsControl) next to ControlRigDynamics.
2. **Import** `SourceArt/Burrower/Burrower_UE.fbx` to `/Game/Assets/Enemies/Burrower/` as skeletal mesh
   `SK_Burrower` with a new skeleton `SKEL_Burrower`. The file is in centimetres (UnitScaleFactor 1), head toward
   +X, Z up, 45 mesh parts each with its own material slot `M_SEG_<id>`, 71 bones. Import with no unit conversion
   tricks, no "Force Front X Axis", normals imported, no animations. Then check:
   * the root bone is `root` (the FBX's "Armature" node must not become a bone; if it does, report it and either
     re-import or accept it and adjust the rig), `root` has children `J0_Head` and `Rotor`;
   * the mesh is about 2023 cm long (x from -1017 to +1006, y within ±207, z from -31 to +628), upright, head at +X, `J0_Head` at about (1000, 0, 180),
     `Rotor` at about (978, 0, 180.5);
   * all 45 parts are in one skeletal mesh and skinned (pose a bone in the skeleton editor).
   The model has about 1.24 M triangles; if the editor or the game struggles, enable Nanite on the skeletal mesh
   (5.8 supports it) and say so in the report. Materials: a simple grey material on every slot is fine for now
   (or keep the generated ones).
3. **Physics asset** `PA_Burrower`, simple shapes only: capsules along `J0_Head`..`J4_Tail` sized to the body
   (radius about 120-180 cm, see the recipe's Step 1.3), optionally one box on `Rotor`; no bodies on the pipe bones.
   Constraints between neighbours with limited swing/twist (about 20 deg). Set it as SK_Burrower's physics asset.
   Check the bodies cover the body in the physics asset editor and that a simulation in the editor does not explode.
4. **CR_Burrower** (Control Rig on SKEL_Burrower) following `control_rig_recipe.md`: variables, construction
   (ragdoll solver from PA_Burrower, rigid-body hoses, wire cables/side hoses), forwards solve in the recipe's order
   (body wave on J1..J4, ragdoll step driven by bIsDead, rotor spin on top of J0_Head, hose step, wire step). Run the
   recipe's Step 3 node-path check first and fix the recipe's node names where 5.8 differs (note what you changed).
5. **ABP_Burrower**: parent class `BurrowerAnimInstance`, skeleton SKEL_Burrower, AnimGraph = Control Rig node
   (CR_Burrower) -> Output Pose, every rig variable bound to the anim instance property of the same name. If the
   AnimGraph cannot be built from Python or MCP, build everything else, then report back the exact clicks the user
   needs (keep it short), and continue with the rest.
6. **BP_Burrower**: parent `BurrowerCharacter`, per `cpp_notes.md` "What the editor session must create or set"
   (mesh, anim class, health bar widget class, no startup abilities, collision presets inherited, do not call
   InitializeEnemyAttributes, `bUseMeshRagdollFallback` true until the Control Rig ragdoll is verified, then false).
   Check `DA_CharClassInfo` has an entry for the Burrower's CharacterClass with an XP reward curve.
7. **Project settings**: Project Settings > Game > Burrower: Burrower Class = BP_Burrower (writes DefaultGame.ini),
   and add BP_Burrower's folder to DirectoriesToAlwaysCook.
8. **Test in PIE** (listen server + 1 client) on the hex platform map: `Aura.Burrower.SpawnNow`,
   `Aura.Burrower.DebugRotorBox 1`, `Aura.Burrower.KillAll`. Check: a Burrower spawns behind each player after the
   interval and follows; the body waves head to tail; the rotor spins; tiles collapse where the rotor box touches
   them (on server and client); pipes swing and stay attached at their ends; gunfire damages it (health bar) and it
   dies into a ragdoll; a new one comes after the interval. Capture a few screenshots or a short log of each check
   if you can (`HighResShot` or the viewport), save them under `Saved/Burrower/`, and list them in the report.
9. **Commit and push** to `claude/project-thread-78otz4`: build fixes, assets, config, scripts.

## Report back

When done (or blocked), report: what was built and where, what works, what does not yet, every deviation from the
recipe or notes (with the reason), screenshots' paths, and any step that needs the user's hands, with exact clicks.
