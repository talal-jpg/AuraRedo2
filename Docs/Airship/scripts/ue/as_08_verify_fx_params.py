# as_08_verify_fx_params.py - read-only: lists each airship FX system's user params and every stack input (HLSL expression
# or link) that reads User.Thrust / User.Boost / User.JetScale, per emitter/script/module.
import unreal, os, json
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
for n in ('NS_AirshipThruster', 'NS_AirshipFanWash', 'NS_AirshipMuzzle'):
    S = '/Game/Assets/MyShip/Drivable/FX/%s.%s' % (n, n)
    summ = nt('GetSystemSummary', system=sref(S))
    print('####', n, 'user:', [(u['name'], u['defaultValue']['value']) for u in summ['userVariables']
                                if u['name'] in ('User.Thrust', 'User.Boost', 'User.JetScale', 'User.Use Bullet Shell', 'User.Global Scale')])
    print('   emitters:', [e['emitterName'] for e in summ['emitters']])
    for e in [x['emitterName'] for x in summ['emitters']]:
        for scr in ('EmitterUpdateScript', 'ParticleSpawnScript', 'ParticleUpdateScript'):
            for mod in fx_modules(S, e, scr):
                for i in nt('GetModuleInputValues', moduleRef=ref(S, e, scr, mod)).get('inputs', []):
                    v = i.get('value') or {}
                    t = v.get('struct', {}).get('refPath', '')
                    txt = v['value'].get('hlslExpression', '') if t.endswith('HlslExpression') else (
                        v['value']['linkedVariable']['name'] if t.endswith('Linked') else '')
                    if any(k in txt for k in ('User.Thrust', 'User.Boost', 'User.JetScale')):
                        print('   %s/%s/%s %s = %s' % (e, scr.replace('Script', ''), mod[:22], i['name'], txt[:150]))
