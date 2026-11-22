# as_00c_probe_fx.py - read-only dump of the Niagara systems the airship FX are copied from (no saves).
# Output: Saved/Airship/probe_<name>.json
import unreal, json, os
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_nh.py')).read())

AS_PROBE = globals().get('AS_PROBE') or ['/Game/NiagaraExamples/FX_Misc/NS_Boost.NS_Boost', '/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash.NS_MuzzleFlash']
for sysp in AS_PROBE:
    out = {}
    try:
        summ = nt('GetSystemSummary', system=sref(sysp))
        out['summary'] = summ
        out['systemData'] = nt('GetSystemData', system=sref(sysp))
        for scr in ['SystemSpawnScript', 'SystemUpdateScript']:
            try:
                out['sys_' + scr] = nt('GetScriptStackTopology', scriptRef=ref(sysp, 'None', scr))
            except Exception as e:
                out['sys_' + scr] = str(e)
        emitters = [e['emitterName'] for e in summ.get('emitters', summ.get('emitterSummaries', []))]
        out['emitterNames'] = emitters
        for em in emitters:
            d = {}
            try:
                d['topology'] = nt('GetEmitterTopology', emitterRef=ref(sysp, em))
            except Exception as e:
                d['topology'] = str(e)
            try:
                d['values'] = nt('GetEmitterInputValues', emitterRef=ref(sysp, em))
            except Exception as e:
                d['values'] = str(e)
            try:
                d['emitterData'] = nt('GetEmitterData', emitterRef=ref(sysp, em))
            except Exception as e:
                d['emitterData'] = str(e)
            rends = []
            try:
                nr = len(d['topology'].get('renderers', d['topology'].get('rendererClasses', [])))
            except Exception:
                nr = 0
            for i in range(nr):
                try:
                    rends.append(nt('GetRendererData', rendererRef=ref(sysp, em, renderer=i)))
                except Exception as e:
                    rends.append(str(e))
            d['renderers'] = rends
            out['em_' + em] = d
    except Exception as e:
        out['error'] = str(e)
    p = as_dump('probe_%s.json' % sysp.split('.')[-1], out)
    print(sysp, '->', p, 'emitters', out.get('emitterNames'))
