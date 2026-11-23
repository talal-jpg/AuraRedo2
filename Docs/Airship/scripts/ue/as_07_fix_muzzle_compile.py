# as_07_fix_muzzle_compile.py - compile fix for NS_AirshipMuzzle (built by as_06_muzzle.py): Blast_Puffs' HLSL expression
# inputs used "User.Global Scale", and a name with a space can't be read in a custom HLSL expression ("Cannot use variable
# in custom expression, it hasn't been encountered yet: User.Global"). Replaces it with the asset's User.Global Scale
# default (5.0) as a literal in every Blast_Puffs expression input; nothing else is changed. Then saves.
import unreal, os, json
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
S = '/Game/Assets/MyShip/Drivable/FX/NS_AirshipMuzzle.NS_AirshipMuzzle'
E = 'Blast_Puffs'
gs = [u['defaultValue']['value']['value'] for u in nt('GetUserVariables', system=sref(S))['userVariables'] if u['name'] == 'User.Global Scale'][0]
lit = '%.1f' % gs
n = 0
for scr in ('EmitterSpawnScript', 'EmitterUpdateScript', 'ParticleSpawnScript', 'ParticleUpdateScript'):
    for mod in fx_modules(S, E, scr):
        vals = nt('GetModuleInputValues', moduleRef=ref(S, E, scr, mod))
        for i in vals.get('inputs', []):
            v = i.get('value') or {}
            if v.get('struct', {}).get('refPath', '').endswith('HlslExpression'):
                ex = v['value']['hlslExpression']
                if 'User.Global Scale' in ex:
                    new = ex.replace('User.Global Scale', lit)
                    set_input(S, E, scr, mod, [i['name']], f_expr(new))
                    print('fixed %s/%s/%s: %s -> %s' % (scr, mod, i['name'], ex, new))
                    n += 1
print('inputs fixed', n, 'Global Scale literal', lit)
print('saved', save_paths([S.split('.')[0]]))
