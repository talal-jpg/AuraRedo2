# CR_Burrower: core Control Rig / RigVM audit against UE 5.8 source

Scope: the core Control Rig / RigVM side of `control_rig_recipe.md` (asset creation, variables, RigVMController,
core node structs and pins, hierarchy reads, compile/save, automated test). ControlRigPhysics / ControlRigDynamics
nodes and the AnimBP are out of scope here. Helper code: `bw_cr_helpers.py` (same folder, nothing runs on import).

Source abbreviations (all under `/mnt/new_partition/5.8/Engine/`):

| Short | Path |
|---|---|
| CRR | `Plugins/Animation/ControlRig/Source/ControlRig` |
| CRD | `Plugins/Animation/ControlRig/Source/ControlRigDeveloper` |
| CRE | `Plugins/Animation/ControlRig/Source/ControlRigEditor` |
| RVM | `Plugins/Runtime/RigVM/Source/RigVM` |
| RVD | `Plugins/Runtime/RigVM/Source/RigVMDeveloper` |
| RVE | `Plugins/Runtime/RigVM/Source/RigVMEditor` |
| PY | `Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private` |
| AAT | `Plugins/Experimental/Toolsets/AnimationAssistantToolset/Content/Python/animation_toolset/toolsets/controlrig.py` |

AAT is Epic's own 5.8 Python Control Rig toolset. It confirms the method names below are used from Python in 5.8.

---

## 0. Short answers

* Build CR_Burrower as a **legacy `UControlRigBlueprint`**, with
  `unreal.ControlRigBlueprintFactory.create_new_control_rig_asset('/Game/Assets/Enemies/Burrower/CR_Burrower', False)`.
  Then import the bones with `rig.get_hierarchy_controller().import_bones_from_skeletal_mesh(skm, '', True, True, False, False, False)`
  and call `rig.set_preview_mesh(skm, True)`. The project's existing CR_Mech is this class, and AAT creates this class too.
* **A new rig has no event nodes.** Add `RigUnit_PrepareForExecution` (event "Construction") and `RigUnit_BeginExecution`
  (event "Forwards Solve") yourself.
* Four FROM_MEMORY names are wrong: `MathQuat*` is `MathQuaternion*` in 5.8. `MathTransformMake` has been deprecated
  since 5.7. Every other FROM_MEMORY path exists, with the pin names the recipe guessed. The execute pin is `ExecutePin`.
* RigVM errors **raise a Python RuntimeError**. They do not come back as a `False` return. `set_pin_default_value` also
  returns `False` when the value is unchanged.
* A full rig test can run **from Python without PIE**: `rig.create_control_rig()` creates an instance, then
  `inst.set_variable_from_string(...)`, `inst.execute('Construction')`, `inst.execute('Forwards Solve')` and
  `inst.get_hierarchy().get_global_transform(key, False)`. It needs no frames and no world. See `run_rig_test()`.

---

## 1. Creating the rig asset

**There are two asset classes in 5.8.**

* `UControlRigBlueprint` is the legacy class, still fully supported (CRD `Public/ControlRigBlueprintLegacy.h:33`,
  derives from `URigVMBlueprint`, which derives from `UBlueprint`). Its factory is `UControlRigBlueprintFactory`
  (CRE `Public/ControlRigBlueprintFactory.h:16-54`), with two static UFUNCTIONs:
  * `CreateNewControlRigAsset(const FString& InDesiredPackagePath, const bool bModularRig = false)` (`:43-44`)
  * `CreateControlRigFromSkeletalMeshOrSkeleton(UObject* InSelectedObject, const bool bModularRig = false)` (`:52-53`)
* `UControlRigRuntimeAsset` is new in 5.8 (CRR `Public/ControlRigRuntimeAsset.h:57`), with editor-only data
  `UControlRigEditorAsset` (CRD `Public/ControlRigEditorAsset.h:421`). Its factory is `UControlRigAssetFactory`
  (CRE `Public/ControlRigAssetFactory.h:71-111`), with the same two statics.
* The CVar `RigVM.BlueprintIndependentAssets` (default **true**, RVE `Private/RigVMEditorModule.cpp:66`) decides which
  one the **content browser** makes. The "Create > Control Rig" menu and the "Add New" menu use the runtime asset
  (CRE `Private/ControlRigAssetActions.cpp:172`, `ControlRigBlueprintFactory.cpp:606-613` `CanCreateNew()` returns false).
  `AssetTools::CreateAsset` does **not** check `CanCreateNew` (Engine `Source/Developer/AssetTools/Private/AssetTools.cpp:1743-1800`).
  So the legacy factory still works from Python, and AAT `controlrig.py:51-70` does exactly that.
* **Recommendation: legacy UControlRigBlueprint.**
  * It is a real `UBlueprint`, so `BlueprintEditorLibrary.compile_blueprint`, the `status` property and the generated
    class `CR_Burrower_C` all work.
  * CR_Mech (`Content/Assets/Characters/Mech/CR_Mech.uasset`) is a `/Script/ControlRigDeveloper.ControlRigBlueprint`
    with a `ControlRigBlueprintGeneratedClass`, and it works in this project.
  * The AnimBP node takes either kind (`FControlRigAssetStrongReference ControlRigAssetReference`,
    CRR `Public/AnimNode_ControlRig.h:61-62`; the reference holds `TSubclassOf<UControlRig> BlueprintRigClass` or a
    runtime asset, CRR `Public/ControlRigAssetReference.h:20-47`).
* "Modular rig" is not a separate asset class. It is the `bModularRig` flag, which sets the parent class to `UModularRig`
  (CRE `ControlRigBlueprintActions.cpp:229-236`). Use `False`.

**Exact creation path (legacy).**

* `create_new_control_rig_asset(path, False)` (CRE `Private/ControlRigBlueprintActions.cpp:229-247`)
  1. Builds a `UControlRigBlueprintFactory` with `ParentClass = UControlRig`.
  2. Calls `CreateUniqueAssetName(path)`. If the name is taken, the new asset gets a suffix.
  3. Calls `AssetTools.CreateAsset(name, folder, nullptr, factory)`. No dialog: `ConfigureProperties` is not called.
  4. `FactoryCreateNew` (`ControlRigBlueprintFactory.cpp:543-599`) runs `FKismetEditorUtilities::CreateBlueprint(...)`
     and `CreateRootGraphIfRequired` (`:558`).
  5. The constructor's `CommonInitialization` creates the function library and the default model named
     **`RigVMModel`** with its controller (RVD `Private/RigVMEditorAsset.cpp:440-463`; prefix in RVD
     `Public/RigVMModel/RigVMClient.h:340`).
  * The result has **no bones and no event nodes**.
* `create_control_rig_from_skeletal_mesh_or_skeleton(skm)` (`ControlRigBlueprintActions.cpp:249-317`)
  * Names the asset itself: `GetDefaultAssetNameForClass` (`:275`), or `<Mesh>_CtrlRig` as a fallback, in the
    mesh's folder.
  * Imports bones with `ImportBones(RefSkeleton, NAME_None, false, false, false, false)` (`:293`), sets the preview mesh
    (`:309`) and calls `RecompileVM` (`:314`).
  * Because it picks its own name, prefer `create_new_control_rig_asset` with the exact path and import the bones
    yourself.
* Bone import (CRR `Public/Rigs/RigHierarchyController.h`):
  * `import_bones_from_skeletal_mesh(skm, '', True, True, False, False, False)` (`:489-497`). The argument order is
    mesh, namespace (no default, pass `''`), replace_existing, remove_obsolete, select, setup_undo, print_python.
  * Or `import_bones(skeleton, '', True, True, False, False, False)` (`:469-477`, the USkeleton overload is the
    UFUNCTION).
  * Or `import_bones_from_asset(path, '', True, True, False)` (`:530-537`, the form AAT uses).
  * Get the controller with `rig.get_hierarchy_controller()` (CRD `ControlRigBlueprintLegacy.h:247-248`). Edits to the
    hierarchy propagate to the CDO and instances on their own (CRD `Private/ControlRigEditorAsset.cpp:2768-2795`).
* Preview mesh: `rig.set_preview_mesh(skm, True)` (`ControlRigBlueprintLegacy.h:142-143`).
* Optional: `source_hierarchy_import` and `source_curve_import` are EditAnywhere UPROPERTYs (`:282-287`).
  `bw_cr_helpers` sets them inside a try.

**Events in a new rig: none.**

* The editor adds Forwards Solve only when the rig editor opens a default graph that has 0 nodes
  (RVE `Private/Editor/RigVMEditor.cpp:320-325`, which calls `FControlRigBaseEditor::CreateEmptyGraphContentImpl`,
  CRE `Private/Editor/ControlRigEditor.cpp:263-292`; `AddUnitNode(FRigUnit_BeginExecution...)` at `:284`).
* So a rig built from Python has no events until you add them. If someone opened the rig before the build ran, a
  `RigUnit_BeginExecution` node named `RigUnit_BeginExecution` may already exist.

| Event | Struct path | Display name | Event name (`get_event_name()`) | Exec pin |
|---|---|---|---|---|
| Construction | `/Script/ControlRig.RigUnit_PrepareForExecution` | "Construction Event" | `Construction` (CRR `Public/Units/Execution/RigUnit_PrepareForExecution.h:14-29`) | `ExecutePin`, output (`:27`) |
| Forwards Solve | `/Script/ControlRig.RigUnit_BeginExecution` | "Forwards Solve" | `Forwards Solve` (CRR `Public/Units/Execution/RigUnit_BeginExecution.h:14-29`) | `ExecutePin`, output (`:27`) |

* Both events are `CanOnlyExistOnce`.
* Adding an event that already exists anywhere in the rig gives the warning "Event %s already exists" and returns
  `None` (RVD `Private/RigVMModel/RigVMController.cpp:1745-1751`).
* Adding it a second time to the same graph is an error and returns the existing node (`:1753-1764`). In Python that
  error raises, so the existing node is lost.
* Always look for the event first: `RigGraph.ensure_event()`.

---

## 2. Member variables

* Signature: `rig.add_member_variable(name, cpp_type, is_public=False, is_read_only=False, default_value='') -> Name`
  (RVD `Public/RigVMBlueprintLegacy.h:427`, implemented at `Private/RigVMBlueprintLegacy.cpp:1221-1236`).
  * After adding, it **compiles the blueprint synchronously** (`:1225-1230`, `WITH_RIGVMLEGACYEDITOR=1`, RVD
    `RigVMDeveloper.Build.cs:44-45`).
  * It returns the name actually used. If the name is taken, it returns a **suffixed** name
    (`FindHostMemberVariableUniqueName`, `:1490`). If the type string is not understood, it returns `None`/empty
    (`:1481-1485`).
* Public / exposed to the AnimBP:
  * New variables get `CPF_Edit | CPF_BlueprintVisible | CPF_DisableEditOnInstance`.
  * `is_public=True` clears `CPF_DisableEditOnInstance`, which is the "Instance Editable" eye in the editor
    (`RigVMBlueprintLegacy.cpp:1450-1455`). This is the flag the AnimBP Control Rig node uses to list inputs.
  * `is_read_only` adds `CPF_BlueprintReadOnly` (`:1457-1460`).
  * To fix the flag on an existing variable: `unreal.BlueprintEditorLibrary.set_blueprint_variable_instance_editable(rig, name, True)`
    (Engine `Source/Editor/BlueprintEditorLibrary/Public/BlueprintEditorLibrary.h:414-415`).
  * After a compile, `instance.get_script_accessible_variables()` lists the public variables (RVM
    `Public/RigVMHost.h:165-166`, IsPublic filter `Private/RigVMHost.cpp:502-508`).
* Type strings (parsed by `FRigVMExternalVariable::Make`, RVM `Private/RigVMCore/RigVMExternalVariable.cpp:108-148`,
  mapped to pin types in RVD `Private/RigVMDeveloperTypeUtils.cpp:42-58`):

| Want | cpp_type string | Notes |
|---|---|---|
| float (single) | `float` | PC_Real/PC_Float, generated as `FFloatProperty` (Engine `Source/Editor/KismetCompiler/Private/KismetCompilerMisc.cpp:1417-1423`). Matches the `float` members of `UBurrowerAnimInstance`. |
| double | `double` | PC_Real/PC_Double, `FDoubleProperty`. |
| bool | `bool` | default text `False` / `True` |
| FTransform | `/Script/CoreUObject.Transform` | **Not** `FTransform`: that string resolves no struct (`FindObjectFromCPPTypeObjectPath`, RVM `Private/RigVMTypeUtils.cpp:553-595`), so the add returns empty. `get_member_variables()` reports it as `FTransform`. |

* Reading variables back: `rig.get_member_variables()` returns `FRigVMGraphVariableDescription` items
  (`RigVMBlueprintLegacy.h:424`) with fields `name`, `cpp_type`, `cpp_type_object`, `default_value`, `category`,
  `tooltip` (RVM `Public/RigVMCore/RigVMVariableDescription.h:35-63`). Read them with `get_editor_property('cpp_type')`
  and so on. There is no "public" field.
* `change_member_variable_type(name, cpp, ...)` only changes the type. It **ignores public and default**
  (`RigVMBlueprintLegacy.cpp:1283-1308`). Python has no setter for a default on an existing variable, so
  `ensure_variable` keeps an existing variable and warns if the default differs.
* Getter and setter nodes: `controller.add_variable_node(var_name, cpp_type, None, is_getter, '', Vector2D(x, y), node_name, False, False)`
  (RVD `Public/RigVMModel/RigVMController.h:399-400`, implementation `Private/RigVMModel/RigVMController.cpp:1918-2050`).
  * The variable must already exist ("Cannot add variable ... does not exist", `:2015`).
  * The value pin takes its type from the variable, not from `cpp_type` (`:2045`).
  * The getter's output pin is **`Value`** (`Public/RigVMModel/Nodes/RigVMVariableNode.h:95`), so link from
    `<node>.Value`.
  * A setter has an IO execute pin named **`ExecuteContext`** (not `ExecutePin`, `RigVMController.cpp:2030-2034`) and an
    input pin `Value`.

---

## 3. RigVMController

* Controller of the main graph:
  * `rig.get_controller_by_name('RigVMModel')` (`RigVMBlueprintLegacy.h:313`). It matches `Graph->GetName()` or the
    graph name (RVD `Private/RigVMModel/RigVMClient.cpp:599-618`).
  * It **returns None if no controller has been created yet** (`FRigVMClient::GetController`, `:504-534`). Fall back to
    `rig.get_or_create_controller(rig.get_default_model())` (`RigVMBlueprintLegacy.h:316`, `:287`).
  * Models added later are named `RigVMModel <Name>` (`RigVMClient.cpp:664`).
  * The UI tab shows "Rig Graph".
  * The graph: `controller.get_graph()` (`RigVMController.h:271-272`).
* Signatures. All are BlueprintCallable UFUNCTIONs in RVD `Public/RigVMModel/RigVMController.h`. Python names are
  snake_case; pass arguments positionally.

| Function | Signature (Python order) | Line |
|---|---|---|
| add_unit_node_from_struct_path | `(struct_path, method_name='Execute', position=Vector2D(0,0), node_name='', setup_undo_redo=True, print_python_command=False) -> RigVMUnitNode` | 363-364 |
| add_variable_node | `(variable_name, cpp_type, cpp_type_object, is_getter, default_value, position=..., node_name='', setup_undo_redo=True, print_python_command=False)` | 399-400 |
| add_template_node | `(notation, position=..., node_name='', setup_undo_redo=True, print_python_command=False)` | 529-530 |
| resolve_wild_card_pin | `(pin_path, cpp_type, cpp_type_object_path, setup_undo_redo=True, print_python_command=False)` | 549-550 |
| set_pin_default_value | `(pin_path, default_value, resize_arrays=True, setup_undo_redo=True, merge_undo_action=False, print_python_command=False, set_value_on_linked_pins=True) -> bool` | 919-920 |
| add_link | `(output_pin_path, input_pin_path, setup_undo_redo=True, print_python_command=False, user_direction=OUTPUT, create_cast_node=False) -> bool` | 1041-1042 |
| break_link / break_all_links | `(out, in, undo, py)` / `(pin_path, as_input=True, undo, py)` | 1046-1052 |
| remove_node / remove_node_by_name / remove_nodes_by_name | `(node or name or [names], setup_undo_redo=True, print_python_command=False) -> bool` | 703-719 |
| set_node_position_by_name | `(name, Vector2D, undo=True, merge=False, py=False)` | 761-762 |

* Graph (RVD `Public/RigVMModel/RigVMGraph.h`): `get_nodes()` (:44), `get_links()` (:48), `is_root_graph()` (:72),
  `find_node_by_name(name)` (:101), `find_pin(path)` (:110), `get_event_names()`.
* Node (RVD `Public/RigVMModel/RigVMNode.h`): `get_pins()` (:86), `find_execute_pin()` (:148), `is_event()` (:250),
  `get_event_name()` (:254). For unit and template nodes, `get_script_struct()` (`Nodes/RigVMTemplateNode.h:99`)
  returns the resolved struct.
* Pin (RVD `Public/RigVMModel/RigVMPin.h`): `get_pin_path()` (:172), `get_direction()` (:209), `get_cpp_type()` (:284),
  `is_execute_context()` (:302), `get_default_value()` (:336), `get_sub_pins()` (:442), `get_linked_source_pins()`.
  * `is_execute_context()` is true for every execute pin (`FRigVMExecuteContext` derives from `FRigVMExecutePin`:
    RVM `Public/RigVMCore/RigVMExecuteContext.h:295,308`; check at RVD `Private/RigVMModel/RigVMPin.cpp:807-817`).
  * The directions are `unreal.RigVMPinDirection.INPUT/OUTPUT/IO/VISIBLE/HIDDEN` (RVM
    `Public/RigVMCore/RigVMFunction.h:39-48`).
* Execute pin names:

| Node kind | Execute pin(s) |
|---|---|
| events | `ExecutePin`, output |
| mutable units (`FRigUnitMutable`) | `ExecutePin`, IO (CRR `Public/Units/RigUnit.h:110-123`) |
| variable setters | `ExecuteContext`, IO |
| `RigVMFunction_ControlFlowBranch` | input `ExecuteContext`; outputs `True`, `False`, `Completed` (RVM `Public/RigVMFunctions/RigVMFunction_ControlFlow.h:20-70`) |
| `RigVMFunction_ControlFlowRunOnce` | input `ExecuteContext`; outputs `Once`, `Completed` (same file `:74-110`) |

  Find them with `is_execute_context()` and the direction (`RigGraph.exec_in` / `exec_out`).
* **Errors are exceptions.**
  * `URigVMController::ReportError` goes to `FScriptExceptionHandler::HandleException(Error)`
    (`RigVMController.cpp:20943-20960`). Python turns that into **RuntimeError**; a warning becomes a RuntimeWarning
    (PY `PyUtil.cpp:617-641`).
  * Examples: "Cannot find struct for path" (`RigVMController.cpp:1554`), "Cannot find pin" (`:10254`, and `:12907-12916`
    for add_link), "Cannot link 'a' to 'b': reason" (from AddLink).
  * The recipe's `if not C.add_link(...)` checks never see these failures. Wrap the calls (`bw_cr_helpers._ue`).
* **set_pin_default_value**:
  * It returns `False` with no message when the value fails validation. It also returns `False` when a leaf pin already
    holds exactly that value, because nothing changed (`RigVMController.cpp:10423-10467`). The helper compares with
    `get_default_value()` before treating `False` as an error.
  * Validation (`RigVMPin.cpp:1197-1350`):
    * bool is exactly `True`/`False`, case sensitive (`:1336-1342`).
    * float and double must be valid float strings (`:1315-1328`).
    * enums are the value name (`GlobalSpace`), checked with `GenerateFullEnumName` (`:1300-1312`).
    * structs go through ImportText (`(X=1.0,Y=0.0,Z=0.0)`, `(Type=Bone,Name="J0_Head")`).
  * **Object pin (`TObjectPtr<UPhysicsAsset>`)**: give the full object path
    `/Game/Assets/Enemies/Burrower/PA_Burrower.PA_Burrower`.
    * It is validated with `FindObjectFromCPPTypeObjectPath`, a FindObject (`RigVMPin.cpp:1236-1265`), so **the asset
      must be loaded first** (`unreal.load_object(None, path)`). Otherwise the set returns False.
    * The value is stored as `DefaultValueObject` (`RigVMController.cpp:10438-10441`).
  * **Arrays**: `(a,b,c)`, with `resize_arrays=True`. True is the default and the helper always passes it. With False
    and a different count the controller hits `ensure(Elements.Num() == SubPins.Num())` (`:10356-10379`).
* **Template nodes.**
  * Every struct with `TemplateName` meta, such as Multiply, Subtract, Sin, Cos, Radians, Clamp, Cast, FromAxisAndAngle,
    Inverse, Rotate Vector, Make Relative and Set Transform, is created through `AddTemplateNode` and then resolved to
    the permutation of the struct you asked for (`RigVMController.cpp:1663-1712`).
  * The node is still a `RigVMUnitNode` named as requested, with the same pin names.
  * Such a node can **re-resolve to another permutation** if you later link a pin of a different type. For example, a
    quat into a float Multiply, or an FTransform into Set Rotation's Value, which shares the "Set Transform" template
    with SetTransform and SetTranslation (CRR `Public/Units/Hierarchy/RigUnit_SetTransform.h:17,82,147`).
  * After the build, check with `node.get_script_struct().get_name()` (`RigGraph.verify_struct`).
* Float and double linking:
  * `CanLink` accepts float to double and double to float (`CanMatchTypes(..., true)` = allow floating point casts,
    RVD `Private/RigVMModel/RigVMPin.cpp:2499-2506`).
  * Still keep everything `float` so no template re-resolves.
* Node names:
  * An empty name gives the struct name, for example `RigUnit_BeginExecution`.
  * A taken name gets a suffix (`GetValidNodeName`, `RigVMController.cpp:1670,1767`). Use the returned
    `node.get_name()`.
* Speed during the build:
  * Pass `setup_undo_redo=False`, as AAT does.
  * Turn auto VM recompile off first (`rig.set_auto_vm_recompile(False)`, `RigVMBlueprintLegacy.h:276`) and back on at
    the end (`compile_rig()` does that), the same way the engine's generated Python does
    (CRD `ControlRigBlueprintLegacy.cpp:390-414`).

---

## 4. Core nodes in the recipe's FROM_MEMORY list

Prefixes: `CR = /Script/ControlRig.`, `VM = /Script/RigVM.RigVMFunction_`. "Pure" means the node has no execute pin.
Pin C++ types are the struct member types.

| Recipe path | 5.8 status | Pins (C++ type, direction) | Source |
|---|---|---|---|
| CR RigUnit_PrepareForExecution | OK, event "Construction" | ExecutePin (out) | CRR `Units/Execution/RigUnit_PrepareForExecution.h:14-29` |
| CR RigUnit_BeginExecution | OK, event "Forwards Solve" | ExecutePin (out) | CRR `Units/Execution/RigUnit_BeginExecution.h:14-29` |
| CR RigUnit_GetTransform | OK, pure, `Varying` | Item (FRigElementKey, in; default bone None), Space (ERigVMTransformSpace, in; default GlobalSpace), bInitial (bool, in; false), Transform (FTransform, out); hidden CachedIndex | CRR `Units/Hierarchy/RigUnit_GetTransform.h:13-57` |
| CR RigUnit_SetTransform | OK, mutable | ExecutePin (IO), Item, Space (default GlobalSpace), bInitial (false), Value (FTransform), Weight (float, 1.0), bPropagateToChildren (bool, **true**) | CRR `Units/Hierarchy/RigUnit_SetTransform.h:17-77` |
| CR RigUnit_SetRotation | OK, mutable | same as SetTransform, but Value is **FQuat** | same file `:147-207` |
| VM MathFloatMul | OK (template "Multiply") | A, B (float, in, Aggregate), Result (float, out) | RVM `RigVMFunctions/Math/RigVMFunction_MathFloat.h:89-110,229-236` |
| VM MathFloatSub | OK (template "Subtract") | A, B, Result (float) | same `:217-224` |
| VM MathFloatSin / MathFloatCos | OK | Value (float, radians), Result (float) | same `:41-57,976-995` |
| VM MathFloatRad | OK | Value (float, degrees), Result (float, radians) | same `:964-971` |
| VM MathFloatClamp | OK | Value, Minimum, Maximum, Result (float) | same `:527-552` |
| VM MathBoolToFloat | OK (template "Cast") | Value (bool, in), Result (float, out, 0 or 1) | RVM `Math/RigVMFunction_MathBool.h:394-413` |
| VM MathQuatFromAxisAndAngle | **WRONG NAME**: use `VM MathQuaternionFromAxisAndAngle` | Axis (FVector, default (1,0,0)), Angle (float, **radians**), Result (FQuat). The axis is normalized; a zero axis warns and gives identity (`.cpp:16-25`) | RVM `Math/RigVMFunction_MathQuaternion.h:134-163` |
| VM MathQuatMul | **WRONG NAME**: use `VM MathQuaternionMul` | A, B, Result (FQuat), Result = A*B (`.cpp:134-137`) | same `:458-467` |
| VM MathQuatInverse | **WRONG NAME**: use `VM MathQuaternionInverse` | Value, Result (FQuat) | same `:23-44,469-478` |
| VM MathQuatRotateVector | **WRONG NAME**: use `VM MathQuaternionRotateVector` | **Transform** (FQuat), Vector (FVector), Result (FVector), Result = Transform.RotateVector(Vector) (`.cpp:190-193`) | same `:648-676` |
| VM MathTransformMul | OK | A, B, Result (FTransform), Result = A*B (`.cpp:61-64`) | RVM `Math/RigVMFunction_MathTransform.h:80-101,253-259` |
| VM MathTransformMakeRelative | OK | Global, Parent (in), Local (out) (FTransform), Local = Global.GetRelativeTransform(Parent) (`.cpp:66-70`) | same `:264-291` |
| VM MathTransformMake | **DEPRECATED 5.7** (`Deprecated="5.7"`). It upgrades to the dispatch `FRigVMDispatch_Constant` with pin `Value` (`.cpp:15-26`). The controller still adds it (no deprecation check in `AddUnitNodeWithDefaults` or the schema, RVD `RigVMSchema.cpp:77-105`), but do not use it. | Translation (FVector), Rotation (FQuat), Scale (FVector), Result (FTransform) | same `:106-136` |

* Enum and key text:
  * `ERigVMTransformSpace` values are **`LocalSpace`** and **`GlobalSpace`** (RVM `Public/RigVMFunctions/RigVMFunctionDefines.h:10-21`).
  * `FRigElementKey` text is `(Type=Bone,Name="J0_Head")` (fields `Type`, `Name`, CRR `Public/Rigs/RigHierarchyDefines.h:1762-1774`;
    enum `ERigElementType` is `Bone`, `:26-47`). It has no custom import/export.
  * `FRigComponentKey` text is `(ElementKey=(Type=Bone,Name="x"),Name="Comp")` (`:1927-1931`).
* Float or double: **MathFloat\* are single-precision `float`** (all their pins are `float`). Double versions exist as
  `RigVMFunction_MathDouble*`, for example `MathDoubleMul` (RVM `Math/RigVMFunction_MathDouble.h:216-954`). A `float`
  rig variable getter (`Value` is float) links directly to them. FromAxisAndAngle.Angle, SetTransform.Weight and
  BoolToFloat.Result are float too.
* FTransform sub-pins are **`Rotation`, `Translation`, `Scale3D`** (Engine `Source/Runtime/CoreUObject/Public/UObject/NoExportTypes.h:2116-2130`),
  so `X.Transform.Rotation` is valid and `X.Value.Scale` is not.
* **Replacement for the recipe's Rotor_Spin (MathTransformMake).** Drop the Make node. Link the spin quaternion into
  the `Rotation` sub-pin of the first Multiply's A input; A keeps identity Translation and Scale3D:
  ```python
  m1 = g.node(H.S['MathTransformMul'], 'Rotor_M1')
  g.link(q + '.Result', m1 + '.A.Rotation')      # Spin = Transform(Rotation = q)
  g.link(rel + '.Local', m1 + '.B')
  ```
  Linking into input sub-pins is ordinary RigVM practice, but this audit did not run it (see Unverified).
* Recipe caveat on pure nodes being evaluated once and reused:
  * GetTransform is declared `Varying` (`RigUnit_GetTransform.h:13`), which keeps it out of constant folding (RVD
    `Private/RigVMCompiler/RigVMAST.cpp:851-861`).
  * This audit did not trace per-consumer re-evaluation in the compiler. Separate getters before and after a step, as
    the recipe says, are harmless; keep them.

---

## 5. Hierarchy reads in Python

* Hierarchy of the rig asset: `rig.get_editor_property('hierarchy')` (BlueprintReadOnly `Hierarchy`,
  `ControlRigBlueprintLegacy.h:244-245`). `rig.hierarchy` and `rig.get_hierarchy()` also work. The last one is the
  interface UFUNCTION (CRD `ControlRigEditorAsset.h:61-62`); Python adds interface UFUNCTIONs to implementing classes
  (PY `PyWrapperTypeRegistry.cpp:1991-2004`).
* Hierarchy of a rig instance: `inst.get_hierarchy()`.
* `unreal.RigElementKey(type=unreal.RigElementType.BONE, name='J1_Forequarters')` (struct BlueprintType with
  BlueprintReadWrite fields `Type`/`Name`, RigHierarchyDefines.h:1762-1774).
* URigHierarchy UFUNCTIONs (CRR `Public/Rigs/RigHierarchy.h`):
  * `get_global_transform(key, initial=False)` (:2276-2277). `initial=True` gives the imported rest/ref pose in
    component space.
  * `get_local_transform(key, initial)` (:2180-2181).
  * `get_global_transform_by_index` / `get_local_transform_by_index`.
  * `get_bones(traverse=True)` (ScriptName of GetBoneKeys, :1143-1144).
  * `get_all_keys()` (:3871-3872).
  * `contains(key)` (:400-401).
  * `get_first_parent(key)` (:3455-3456).
  * `reset_pose_to_initial(unreal.RigElementType.BONE)` (:291-292).
  * `get_controller()` (:3978-3979).
* `unreal.MathLibrary.make_rot_from_z(vector) -> Rotator` (Engine `Source/Runtime/Engine/Classes/Kismet/KismetMathLibrary.h:2266-2268`).
* `unreal.MathLibrary.make_relative_transform(a, relative_to)` (:4017-4018) computes `A * inverse(RelativeTo)`. The
  ScriptMethod alias is `a.make_relative(relative_to)`.
* `unreal.Transform(location=Vector, rotation=Rotator, scale=Vector)`: native make, `MakeTransform`
  (NoExportTypes.h:2116, KismetMathLibrary.h:3930-3932). Fields are `t.translation`, `t.rotation` (Quat) and `t.scale3d`.
* `t.export_text()` gives `(Rotation=(X=..,Y=..,Z=..,W=..),Translation=(..),Scale3D=(..))` (PY `PyWrapperStruct.cpp:1310`),
  which you can pass straight to `set_pin_default_value`.
* The recipe's C10 code (`H.get_global_transform(RigElementKey(...), True)`, `make_rot_from_z`,
  `make_relative_transform(tm_comp, j1)`, `tm_local.export_text()`) is correct as written. In `bw_cr_helpers` it is
  `comp_to_bone_local()` plus `capsule_tm_along()`.

---

## 6. Compile, errors, save

* `rig.recompile_vm()` rebuilds the VM only (`RigVMBlueprintLegacy.h:270`).
  `unreal.BlueprintEditorLibrary.compile_blueprint(rig)` compiles the blueprint (and the VM through the RigVM blueprint
  compiler) and refreshes `CR_Burrower_C` and its CDO (Engine `BlueprintEditorLibrary.h:200`). Call both; `compile_rig()`
  does. Also available: `request_auto_vm_recompilation()`, `recompile_vm_if_required()`, `set_auto_vm_recompile(bool)`
  (`RigVMBlueprintLegacy.h:270-278`).
* Reading the compile result:
  1. Compiler errors and warnings go through `IRigVMEditorAssetInterface::HandleReportFromCompiler`
     (RVD `Private/RigVMEditorAsset.cpp:2077-2136`). It calls `FScriptExceptionHandler::HandleException`, so the
     `recompile_vm()` / `compile_blueprint()` call **raises RuntimeError** with the message (PY `PyUtil.cpp:617-641`).
     Warnings become RuntimeWarning. This holds unless `SurpressErrors` is set; it defaults to false
     (RVD `Private/RigVMCompiler/RigVMCompiler.cpp:87`).
  2. Afterwards read `rig.get_editor_property('status')` (BlueprintReadOnly, Engine `Source/Runtime/Engine/Classes/Engine/Blueprint.h:507-508`).
     It is one of `unreal.BlueprintStatus.BS_UP_TO_DATE`, `BS_UP_TO_DATE_WITH_WARNINGS`, `BS_ERROR` or `BS_DIRTY`.
     RigVM errors set `BS_ERROR` (`RigVMBlueprintLegacy.cpp:260-271`). Epic's helper does the same check
     (`Plugins/Experimental/ToolsetRegistry/Content/Python/toolset_registry/helpers.py:30-44`).
  3. A rig that compiled with errors fails `InitializeVM` because the external variable count differs
     (RVM `Private/RigVMHost.cpp:331-336`), so `inst.execute(...)` returns False.
  4. Full text: Output Log categories LogRigVM and LogControlRig, or the rig editor's Compiler Results.
* Save: `unreal.EditorAssetLibrary.save_asset('/Game/Assets/Enemies/Burrower/CR_Burrower', False)`
  (Plugins `Editor/EditorScriptingUtilities/Source/EditorScriptingUtilities/Public/EditorAssetLibrary.h:281`). Not
  during PIE; check `LevelEditorSubsystem.is_in_play_in_editor()` (Engine `Source/Editor/LevelEditor/Public/LevelEditorSubsystem.h:83-84`).
* Delete and recreate:
  * `EditorAssetLibrary.delete_asset(path)` force-deletes without a dialog (Engine
    `Source/Editor/UnrealEd/Private/Subsystems/EditorAssetSubsystem.cpp:795-815`, `ForceDeleteObjects(..., false)`).
  * Referencers such as ABP_Burrower then lose the reference.
  * So `get_or_create_rig()` **reuses** an existing rig by default, `clear_rig_graphs()` drops all nodes, and existing
    variables are kept so AnimBP bindings survive. Pass `recreate=True` for a clean asset.

---

## 7. Automated rig test without PIE

This works. The recipe is verified step by step and implemented as `bw_cr_helpers.run_rig_test()`.

1. `inst = rig.create_control_rig()` (`ControlRigBlueprintLegacy.h:135-136`).
   * This calls `RecompileVMIfRequired()`, then `NewObject<UControlRig>(outer = the blueprint, CR_Burrower_C)`, then
     `Initialize(true)` (RVD `RigVMEditorAsset.cpp:3154-3161`, `RigVMBlueprintLegacy.cpp:326-329`).
   * `Initialize` copies the CDO hierarchy and VM (`InitializeFromCDO`, CRR `Private/ControlRig.cpp:353-395,774-800`).
   * The instance is not transient and lives inside the CR package, so the helper moves it to the transient package
     with `inst.rename(unique_name, unreal.find_package('/Engine/Transient'))` (Obj.cpp:5912).
   * There is no `unreal.get_transient_package()` in 5.8 (PY `PyCore.cpp:2055-2100` method table).
   * Renaming onto an existing name is Fatal (`Obj.cpp:383`), so the name must be unique.
2. `inst.set_variable_from_string('WaveTime', '0.25')`: any variable, public or private, returns bool (RVM
   `RigVMHost.h:177-178`, `RigVMHost.cpp:583-593`). Bool text `True`/`False`. `get_variable_as_string(name)` reads it back.
3. `inst.set_absolute_and_delta_time(t, dt)` (`RigVMHost.h:85-86`).
4. `inst.execute('Construction')`, then `inst.execute('Forwards Solve')` (UFUNCTION `Execute(FName)`, `RigVMHost.h:217-218`).
   * `UControlRig::Execute` initialises the VM on the first call (CRR `ControlRig.cpp:966-976`) and sets the event name
     on the context (`:1013`). That is what the physics and dynamics "construction only" checks read.
   * For Construction it resets the hierarchy to the default and to the initial pose first (`:1296-1331`).
   * The anim node also calls `Execute(Construction)` directly (CRR `Private/AnimNode_ControlRigBase.cpp:446`).
5. Before each Forwards Solve, reset the bones with `h.reset_pose_to_initial(unreal.RigElementType.BONE)`. This mimics
   the AnimBP's reference-pose input. Without it, the wave's local rotations stack frame after frame.
6. Read the result with `h = inst.get_hierarchy()` and `h.get_global_transform(bone_key, False)`.
7. World:
   * The instance has no world: its outer is the transient package, and `PublicContext.SetWorld(Outer->GetWorld())`
     gives null (`ControlRig.cpp:1159-1165`).
   * Physics solvers still simulate. World collision is skipped because the world gather pins a weak world pointer and
     does nothing when it is null (Plugins `Experimental/ControlRigPhysics/Source/ControlRigPhysics/Private/RigPhysicsSolver_WorldObjects.cpp:197-216`;
     the step receives `ControlRig->GetWorld()`, `RigPhysicsSolverExecution.cpp:235`).
   * Dynamics uses the world only for visualization (`RigDynamicsSolverExecution.cpp:274`).
   * So ground collision of the ragdoll **cannot** be tested this way. Everything else can: the wave, the rotor, and
     the ragdoll, hose and wire stepping without world contact.
8. Physics and dynamics accumulate time from `dt` per execute. For settling tests, run many frames (`frames=120`).
9. The run is synchronous: no slate tick and no state machine. Results go to `Saved/Burrower/<out_name>.json`.

Example checks for the build script:

```python
r = H.run_rig_test(rig, bones=['Rotor', 'J0_Head'], variables={'RotorAngleDeg': 90.0, 'WaveAmplitudeDeg': 0.0})
# Rotor stays at its rest centre and is rotated 90 deg about the body's long axis
assert H.dist(r['bones']['Rotor']['global_pos'], r['bones']['Rotor']['rest_pos']) < 0.5
assert abs(H.quat_angle_deg(r['bones']['Rotor']['global_quat'], r['bones']['Rotor']['rest_quat']) - 90.0) < 1.0
```

---

## 8. Corrections: recipe says, 5.8 actual

| Recipe says | 5.8 actual |
|---|---|
| `ControlRigBlueprintFactory.create_control_rig_from_skeletal_mesh_or_skeleton(selected_object=skm)` [unverified], then rename to CR_Burrower | Exists (CRE `ControlRigBlueprintFactory.h:52-53`), but it names the asset itself (default name for the class) in the mesh folder. Use `create_new_control_rig_asset('/Game/Assets/Enemies/Burrower/CR_Burrower', False)`, then `get_hierarchy_controller().import_bones_from_skeletal_mesh(skm, '', True, True, False, False, False)` and `set_preview_mesh(skm, True)`. |
| (implied) Control Rig asset = UControlRigBlueprint | Still valid and recommended. The 5.8 UI default is `UControlRigRuntimeAsset` (+ `UControlRigEditorAsset`) via CVar `RigVM.BlueprintIndependentAssets=true`. |
| "skip if the rig already has one" (Construction); Forwards Solve "existing" | A new rig has **no** events. Add both. A duplicate gives a warning/error and returns None (in Python the error raises). |
| `rig.add_member_variable('RotorAngleDeg', 'float', True, False, '0.0')` [unverified] | Correct signature. It returns the actual name (suffixed on a clash, empty on an unknown type) and compiles the blueprint each time. |
| "Keep C++ float; the AnimGraph converts if the rig variable is double" | `'float'` creates a single-precision FFloatProperty, so no conversion is needed. MathFloat\* are float. |
| FTransform variable type (5.6 end re-pin) | cpp_type must be `/Script/CoreUObject.Transform`. `FTransform` fails. |
| `C = rig.get_controller_by_name('RigVMModel')` | Correct name. It can return None; fall back to `get_or_create_controller(get_default_model())`. |
| `add_unit_node_from_struct_path(path, 'Execute', Vector2D, name)` | Correct. Optional 5th and 6th arguments: `setup_undo_redo`, `print_python_command`. A taken name gets a suffix. |
| `add_variable_node(var, cpp, None, True, '', pos, name)` with output `.Value` | Correct. The variable must exist first. A setter's execute pin is `ExecuteContext`. |
| `if not C.set_pin_default_value(pin, str(value), True): raise` | The third argument is `resize_arrays`. Returns False **also when the value is unchanged**; validation failures return False silently; a missing pin raises RuntimeError. Bools must be `True`/`False`. |
| `if not C.add_link(a, b): raise` | Failures **raise RuntimeError** with the reason. A False return is rare. |
| `setp(i + '.PhysicsAsset', '/Game/.../PA_Burrower.PA_Burrower')` "if refused, set by hand" | Works if PA_Burrower is **loaded** first (`unreal.load_object(None, path)`): the validator does a FindObject. |
| `setp(..., arr([...]))` | Correct with `resize_arrays=True`. |
| `exec_pin` via `is_execute_context()`, name "ExecuteContext/ExecutePin changed across 5.x" | Correct approach. 5.8 names: `ExecutePin` (units, events); `ExecuteContext` (variable setters, Branch, RunOnce inputs); `True`/`False`/`Completed`/`Once` (control-flow outputs). |
| `VM MathQuatFromAxisAndAngle` / `MathQuatMul` / `MathQuatInverse` / `MathQuatRotateVector` | `VM MathQuaternionFromAxisAndAngle` / `MathQuaternionMul` / `MathQuaternionInverse` / `MathQuaternionRotateVector`. Pins as the recipe guessed: Axis/Angle(rad)/Result, A/B/Result, Value/Result, **Transform**/Vector/Result. |
| `VM MathTransformMake` (Rotor_Spin, `.Rotation` → `.Result`) | Deprecated 5.7 (dispatch Constant). Link `q.Result → Rotor_M1.A.Rotation` instead (section 4). |
| `VM MathBoolToFloat` [unverified] | Exists: Value (bool) → Result (float). |
| `VM MathFloatClamp` | Exists: Value, **Minimum, Maximum**, Result (not Min/Max). |
| `Transform/Vector` on RotateVector, `Global/Parent/Local` on MakeRelative, `Item/Space/bInitial/Transform` on GetTransform, `Item/Space/bInitial/Value/Weight/bPropagateToChildren` on Set* | All correct. Set*/Get* default Space is **GlobalSpace** and bPropagateToChildren defaults to **true**. |
| Enum text `GlobalSpace` / `LocalSpace`, key `(Type=Bone,Name="x")`, component `(ElementKey=...,Name=...)` | Correct. |
| `Translation/Rotation/Scale` (TransformMake) | Make is deprecated. FTransform **sub-pins** are `Rotation`, `Translation`, `Scale3D`. |
| `ev_f = next(... get_script_struct().get_name() == 'RigUnit_BeginExecution')` | Works only if the event exists (StopIteration otherwise). Use `ensure_event(EV_FORWARDS)`. |
| `show_pins` probe in Step 3 adds each struct, events included | Probing an event that already exists fails (duplicate). `verify_core_pins()` reads existing events instead. |
| `H = rig.hierarchy`; `H.get_global_transform(key, True)`; `MathLibrary.make_rot_from_z`; `make_relative_transform`; `export_text` | All correct. |
| `unreal.BlueprintEditorLibrary.compile_blueprint(rig)  # or rig.recompile_vm() [unverified]` | Both exist. Call both, then read `rig.get_editor_property('status')`. Errors raise RuntimeError. |
| `unreal.EditorAssetLibrary.save_loaded_asset(rig)` | Works. The HARD RULES prefer `save_asset('/Game/Assets/Enemies/Burrower/CR_Burrower', False)`. Not during PIE. |
| Step 8.1 "temporarily add the rig's accumulated time to WaveTime, or test in PIE" | Testable from Python without PIE: `run_rig_test(rig, variables=lambda f: {'WaveTime': f / 60.0}, frames=N)`. |

---

## 9. Pitfalls found (beyond the table)

* Every RigVM edit triggers a VM recompile when auto-recompile is on. With about 300 nodes, turn it off first.
* `add_member_variable` compiles the blueprint on every call (9 to 10 compiles for this rig), which is fine.
* Template nodes (Multiply, Set Transform, Cast and others) silently change permutation if a wrong type is linked. Run
  `verify_struct` on key nodes after the build.
* `rig.create_control_rig()` creates its object inside the asset package. Rename it to the transient package, as
  `make_test_instance()` does, before any save.
* Python `warnings` from UE (RuntimeWarning) are printed by `_ue()` as `WARN:` lines. Many "already exists" style
  messages come as warnings, not errors.
* Node names that are already taken come back suffixed. Always use the returned name.

## 10. Unverified (with fallbacks in the code)

* **Linking into a sub-pin of an input** (`Rotor_M1.A.Rotation`). `CanLink` has no rule against it and it is ordinary
  RigVM usage, but this audit did not execute it. Fallback that uses only whole pins and output sub-pins (the recipe
  already relies on those, e.g. `X.Transform.Rotation`): `M = MathTransformMul(A = Offset, B = J0G)`, then
  `QFinal = MathQuaternionMul(A = M.Result.Rotation, B = SpinQ)` (= M.Rot * Spin, the spin applied first in the rotor's
  own frame). Then `SetTransform(Rotor, GlobalSpace, Value = M.Result, bPropagateToChildren False)`, followed in the
  chain by `SetRotation(Rotor, GlobalSpace, Value = QFinal.Result, bPropagateToChildren False)`. The result is the
  same as `Spin * Offset * J0G`.
* Setting `source_hierarchy_import` / `source_curve_import` with `set_editor_property`: these are private EditAnywhere
  `TSoftObjectPtr<UObject>`. The call is wrapped in try and only matters for "refresh hierarchy" in the editor.
* `rig.get_asset_variables()` as a fallback for `get_member_variables()` on the legacy class is not confirmed as a
  UFUNCTION there. It is only used if the first call fails.
* `inst.rename(name, transient_package)` on a UControlRig instance: plain UObject rename, no linker involved (fresh
  object). If it fails, the helper warns not to save while the instance lives.
* How the RigVM compiler caches pure nodes (the recipe's "pure node reuse" caveat) was not traced.
* Nothing here was executed in an editor (no Unreal process allowed). Run `H.core_audit(rig)` first in the editor
  (= `check_struct_paths()` + `verify_core_pins(rig)`, probe nodes removed again, nothing saved): it prints PASS/FAIL
  per struct and per pin. Pass the recipe's VERIFIED Physics/Dynamics list as `extra_paths` to check those paths too.
