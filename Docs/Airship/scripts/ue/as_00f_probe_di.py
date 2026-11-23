# as_00f_probe_di.py - read-only: expands every dynamic-input chain of a system (AS_DI_SYSTEM) and prints the module inputs
# whose chain mentions any of AS_DI_FIND (e.g. 'User.Global Scale'); dumps all chains to Saved/Airship/di_<name>.json.
import unreal, os, json
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_nh.py')).read())
_S = AS_DI_SYSTEM
_out = {}
for e in nt('GetSystemSummary', system=sref(_S))['emitters']:
    en = e['emitterName']
    for m in nt('GetEmitterInputValues', emitterRef=ref(_S, en)):
        mn = m['moduleName']
        # find the script holding this module
        for i in m['inputs']:
            v = i.get('value', {})
            if v.get('struct', {}).get('refPath', '').endswith('DynamicInput'):
                for scr in ('ParticleSpawnScript', 'ParticleUpdateScript', 'EmitterUpdateScript', 'EmitterSpawnScript'):
                    try:
                        ch = nt('GetDynamicInputChain', stackInputRef=ref(_S, en, scr, mn, [i['name']]))
                        _out['%s/%s/%s/%s' % (en, scr, mn, i['name'])] = ch
                        break
                    except Exception:
                        continue
as_dump('di_%s.json' % _S.split('.')[-1], _out)
for k, v in _out.items():
    s = json.dumps(v)
    hits = [f for f in AS_DI_FIND if f in s]
    if hits:
        print(k, hits)
print('chains', len(_out))
