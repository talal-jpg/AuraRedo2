# as_nh.py - helpers for the airship scripts (exec'd into the inbox namespace by the as_* scripts).
# nt(tool, **args): calls NiagaraToolsets.NiagaraToolset_System.<tool> through unreal.ToolsetRegistry and returns the
# parsed returnValue (raises on error). ref(...): builds a NiagaraExt_StackItemReference.
import unreal, json, os

AS_SAVED = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
AS_NS_TS = 'NiagaraToolsets.NiagaraToolset_System'
AS_APP_TS = 'EditorToolset.EditorAppToolset'
if not isinstance(globals().get('AS_LATENT'), dict):
    AS_LATENT = {}


def as_pending_read(tool):
    res = AS_LATENT.get(tool)
    if res is None or not res.get_editor_property('is_complete'):
        return None
    AS_LATENT.pop(tool)
    err = str(res.get_editor_property('error') or '')
    if err:
        raise RuntimeError('%s -> %s' % (tool, err))
    d = json.loads(str(res.get_editor_property('value') or 'null'))
    return d.get('returnValue', d) if isinstance(d, dict) else d


def as_tool(toolset, tool, args):
    res = unreal.ToolsetRegistry.execute_tool(toolset, tool, json.dumps(args))
    if not res.get_editor_property('is_complete'):
        # latent tool (CaptureAssetImage, GetSystemCompileState, GetStackIssues...): finishes on a later tick.
        # Keep the result object and read it from a later inbox call (as_pending_read).
        AS_LATENT[tool] = res
        return None
    err = str(res.get_editor_property('error') or '')
    if err:
        raise RuntimeError('%s.%s -> %s' % (toolset.split('.')[-1], tool, err))
    raw = str(res.get_editor_property('value') or '')
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return raw
    return d.get('returnValue', d) if isinstance(d, dict) else d


def nt(tool, **args):
    return as_tool(AS_NS_TS, tool, args)


def app(tool, **args):
    return as_tool(AS_APP_TS, tool, args)


def ref(system, emitter='None', script='None', module='None', inputs=None, renderer=-1):
    return {'system': {'refPath': system}, 'emitterName': emitter, 'scriptName': script, 'moduleName': module,
            'rendererIndex': renderer, 'inputNameStack': inputs or []}


def sref(system):
    return {'refPath': system}


def as_dump(name, obj):
    os.makedirs(AS_SAVED, exist_ok=True)
    p = os.path.join(AS_SAVED, name)
    with open(p, 'w') as f:
        f.write(json.dumps(obj, indent=1) if not isinstance(obj, str) else obj)
    return p


def f_expr(expr):
    return {'struct': {'refPath': '/Script/NiagaraEditor.NiagaraExt_StackInputData_HlslExpression'},
            'value': {'hlslExpression': expr}}


def f_float(v):
    return {'struct': {'refPath': '/Script/Niagara.NiagaraFloat'}, 'value': {'value': float(v)}}


def f_link(name, typ='/Script/Niagara.NiagaraFloat'):
    return {'struct': {'refPath': '/Script/NiagaraEditor.NiagaraExt_StackInputData_Linked'},
            'value': {'linkedVariable': {'name': name, 'type': {'classStructOrEnum': {'refPath': typ}}}}}


def set_input(system, emitter, script, module, inputs, data):
    if isinstance(inputs, str):
        inputs = [inputs]
    return nt('SetStackInputData', stackInputRef=ref(system, emitter, script, module, inputs), inputData=data)


def compile_request(system):
    """Phase 1 (latent tools): queue GetSystemCompileState + GetStackIssues; read them with compile_state() later."""
    a = nt('GetSystemCompileState', system=sref(system))
    b = nt('GetStackIssues', system=sref(system))
    AS_LATENT['_cs_now'] = (a, b)


def compile_state(system=None):
    """Phase 2: the results of compile_request (or None while still pending)."""
    a, b = AS_LATENT.pop('_cs_now', (None, None))
    cs = a if a is not None else as_pending_read('GetSystemCompileState')
    si = b if b is not None else as_pending_read('GetStackIssues')
    if cs is None or si is None:
        if cs is not None or si is not None:
            AS_LATENT['_cs_now'] = (cs, si)
        return None
    errs = []
    for s in cs.get('scripts', []):
        for ev in s.get('compileEvents', []):
            if ev.get('severity') in ('Error', 'Warning'):
                errs.append('%s/%s %s: %s' % (s.get('emitterName'), s.get('scriptName'), ev.get('severity'), str(ev.get('message', ''))[:300]))
    iss = ['%s %s/%s/%s: %s' % (i.get('severity'), i['location'].get('emitterName'), i['location'].get('scriptName'),
                                i['location'].get('moduleName'), i.get('shortDescription')) for i in si.get('issues', [])
           if i.get('severity') in ('Error', 'Warning') and not i.get('bIsDismissed')]
    return {'status': cs.get('aggregateStatus'), 'errors': cs.get('bHasErrors'), 'warnings': cs.get('bHasWarnings'),
            'events': errs, 'numIssueErrors': si.get('numErrors'), 'numIssueWarnings': si.get('numWarnings'), 'issues': iss}


def save_paths(paths):
    """Saves exactly these assets (never an empty list)."""
    assert paths, 'refusing to save an empty list'
    out = []
    for p in paths:
        out.append((p, unreal.EditorAssetLibrary.save_asset(p, only_if_is_dirty=False)))
    return out
