# as_check_compile.py - opens the Niagara system editor (compile errors only show with it open, see memory notes), queues
# GetSystemCompileState + GetStackIssues (latent) and, on the next call, prints them. Set AS_CC_SYSTEM before exec.
# Call 1: AS_CC_PHASE = 'open'   Call 2 (a few s later): AS_CC_PHASE = 'request'   Call 3: AS_CC_PHASE = 'read'
import unreal, os, json
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_nh.py')).read())
_ph = globals().get('AS_CC_PHASE', 'read')
if _ph == 'open':
    print('open editor', app('OpenEditorForAsset', assetPath=AS_CC_SYSTEM.split('.')[0]))
elif _ph == 'request':
    compile_request(AS_CC_SYSTEM)
    print('requested')
elif _ph == 'read':
    r = compile_state(AS_CC_SYSTEM)
    print(json.dumps(r, indent=1) if r is not None else 'PENDING')
# AS_CC_PHASE = 'reopen': closes the system's asset editor and opens it again (the open editor did not recompile after
# toolset edits made while it was open; reopening does)
if _ph == 'reopen':
    _a = unreal.load_asset(AS_CC_SYSTEM.split('.')[0])
    print('closed', unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(_a))
    print('open editor', app('OpenEditorForAsset', assetPath=AS_CC_SYSTEM.split('.')[0]))
