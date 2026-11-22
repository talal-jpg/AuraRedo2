# as_04a_fx_create.py - creates an FX system skeleton: an empty Niagara system with emitters copied from engine templates,
# then dumps its topology + input values to Saved/Airship/fx_<name>_topo.json for the configure step (as_04b/as_05/...).
# Set AS_FX = {'name': 'NS_AirshipThruster', 'emitters': [('JetCore', '<template emitter path>'), ...]} before exec.
# Refuses to touch an existing system unless AS_FX['recreate'] is True (then it deletes and recreates OUR asset).
import unreal, os, json
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_nh.py')).read())

AS_FX_DIR = '/Game/Assets/MyShip/Drivable/FX'


def as04a_create(spec):
    name = spec['name']
    path = '%s/%s' % (AS_FX_DIR, name)
    full = '%s.%s' % (path, name)
    eal = unreal.EditorAssetLibrary
    if eal.does_asset_exist(path):
        if not spec.get('recreate'):
            print('exists, not recreated:', path)
            return full
        assert path.startswith('/Game/Assets/MyShip/Drivable/FX/'), path
        eal.delete_asset(path)
        print('deleted (recreate)', path)
    sysobj = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, AS_FX_DIR, unreal.NiagaraSystem, unreal.NiagaraSystemFactoryNew())
    print('created', sysobj.get_path_name())
    for ename, tpl in spec['emitters']:
        topo = nt('AddEmitter', system=sref(full), templateEmitter={'refPath': tpl}, emitterName=ename)
        print('added emitter', ename, 'from', tpl, '->', topo.get('emitterName'))
    return full


def as04a_dump(full):
    out = {'summary': nt('GetSystemSummary', system=sref(full))}
    for scr in ['SystemSpawnScript', 'SystemUpdateScript']:
        out['sys_' + scr] = nt('GetScriptStackTopology', scriptRef=ref(full, 'None', scr))
    for e in out['summary'].get('emitters', []):
        en = e['emitterName']
        d = {'topology': nt('GetEmitterTopology', emitterRef=ref(full, en)),
             'values': nt('GetEmitterInputValues', emitterRef=ref(full, en)),
             'emitterData': nt('GetEmitterData', emitterRef=ref(full, en))}
        d['renderers'] = [nt('GetRendererData', rendererRef=ref(full, en, renderer=r['rendererIndex'])) for r in d['topology'].get('renderers', [])]
        out['em_' + en] = d
    p = as_dump('fx_%s_topo.json' % full.split('.')[-1], out)
    print('dumped', p)
    return out


if globals().get('AS_FX'):
    _full = as04a_create(AS_FX)
    as04a_dump(_full)
