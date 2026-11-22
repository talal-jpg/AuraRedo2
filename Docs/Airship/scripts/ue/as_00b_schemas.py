# as_00b_schemas.py - dumps the JSON schemas of the editor toolsets used by the airship session (read-only).
import unreal, json, os
out = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'schemas')
os.makedirs(out, exist_ok=True)
try:
    allj = unreal.ToolsetRegistry.get_all_toolset_json_schemas()
    open(os.path.join(out, 'all.json'), 'w').write(allj if isinstance(allj, str) else json.dumps(allj))
    print('all schemas', len(allj))
except Exception as e:
    print('all schemas failed', e)
for t in ['NiagaraToolsets.NiagaraToolset_System', 'NiagaraToolsets.NiagaraToolset_Emitter']:
    try:
        s = unreal.ToolsetRegistry.get_toolset_json_schema(t)
        open(os.path.join(out, t + '.json'), 'w').write(s)
        print(t, len(s))
    except Exception as e:
        print(t, 'failed', e)
for n in ['InputAction_Factory', 'InputActionFactory', 'InputMappingContext_Factory', 'InputMappingContextFactory',
          'NiagaraSystemFactoryNew', 'PhysicalMaterialFactoryNew', 'BlueprintFactory', 'MaterialFactoryNew']:
    print(n, hasattr(unreal, n))
