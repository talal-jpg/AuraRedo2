# as_40_fx_inspect.py - validation session 2026-11-22 (read-only): which EXISTING project materials can replace the
# green jet (M_Fire on SM_Thruster) and the square puffs (MI_Popcorn_Puff) of our FX copies.
#  * T3D export of candidate materials -> Saved/Airship/val/t3d/<name>.t3d (graph + default values, parsed offline)
#  * base material blend / shading / Niagara usage flags, MI parameter values (scalar, vector, texture, static switch)
#  * renderer data (materials, meshes) of every emitter of NS_AirshipThruster / NS_AirshipFanWash / NS_AirshipMuzzle
#  * thumbnails queued (EditorAppToolset.CaptureAssetImage, latent): collect with AS_THUMBS = None + as_00d_thumbs.py
# Nothing is saved. Run: inbox.sh 40 Docs/Airship/scripts/ue/as_40_fx_inspect.py 120
import unreal, os, json, traceback
_AS_UE = os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue')
exec(open(os.path.join(_AS_UE, 'as_nh.py')).read())
exec(open(os.path.join(_AS_UE, 'as_fxlib.py')).read())
VAL = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'val')
T3D = os.path.join(VAL, 't3d')
os.makedirs(T3D, exist_ok=True)
MEL = unreal.MaterialEditingLibrary
MATS = ['/Game/Assets/Effects/MyThruster/M_Fire', '/Game/Assets/Effects/Projectiles/FireExplosion/M_ExplosionSphere',
        '/Game/VFXASandbox/Core/Spells/Default_Spells/Spell_Fireball/Materials/M_Flame_MeshRing',
        '/Game/Assets/Effects/Shared/M_DefaultSprite_trans']
MIS = ['/Game/VFXASandbox/VFX/00_Common/Materials/MI_Ball_01', '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Popcorn_Puff',
       '/Game/VFXASandbox/Core/Spells/Default_Spells/Spell_Fireball/Materials/MI_Flame_MeshRing',
       '/Game/VFXASandbox/VFX/Xtra_Fire/Material_Instances/MI_Fire_Glow',
       '/Game/VFXASandbox/VFX/Xtra_Fire/Material_Instances/MI_Fire_Wisp',
       '/Game/VFXASandbox/Core/Spells/Default_Spells/Spell_Fireball/Materials/MI_Smoke_Puff']
SYSTEMS = {'NS_AirshipThruster': ['JetShell', 'JetCore', 'Puffs'], 'NS_AirshipFanWash': ['Streaks', 'Wash'],
           'NS_AirshipMuzzle': None}
R = {'materials': {}, 'mis': {}, 'renderers': {}, 'errors': []}


def base_info(m):
    b = m if isinstance(m, unreal.Material) else m.get_base_material()
    d = {'class': m.get_class().get_name(), 'base': b.get_path_name()}
    for p in ('blend_mode', 'shading_model', 'two_sided', 'used_with_niagara_sprites', 'used_with_niagara_mesh_particles',
              'used_with_niagara_ribbons', 'used_with_skeletal_mesh', 'used_with_nanite', 'opacity_mask_clip_value'):
        try:
            d[p] = str(b.get_editor_property(p))
        except Exception as e:  # noqa: BLE001
            d[p] = 'ERR %s' % e
    return d


for mp in MATS:
    try:
        m = unreal.load_asset(mp)
        d = base_info(m)
        try:
            d['scalars'] = [str(x) for x in MEL.get_scalar_parameter_names(m)]
            d['vectors'] = [str(x) for x in MEL.get_vector_parameter_names(m)]
            d['textures'] = [t.get_name() for t in MEL.get_used_textures(m)]
            d['n_expr'] = MEL.get_num_material_expressions(m)
        except Exception as e:  # noqa: BLE001
            d['params_err'] = str(e)
        t = unreal.AssetExportTask()
        t.set_editor_property('object', m)
        t.set_editor_property('filename', os.path.join(T3D, mp.split('/')[-1] + '.t3d'))
        t.set_editor_property('automated', True)
        t.set_editor_property('prompt', False)
        t.set_editor_property('replace_identical', True)
        d['t3d'] = bool(unreal.Exporter.run_asset_export_task(t))
        R['materials'][mp] = d
    except Exception:  # noqa: BLE001
        R['errors'].append('%s: %s' % (mp, traceback.format_exc()[-400:]))

for mp in MIS:
    try:
        m = unreal.load_asset(mp)
        d = base_info(m)
        d['parent'] = m.get_editor_property('parent').get_path_name() if m.get_editor_property('parent') else None
        d['scalars'] = [(str(p.get_editor_property('parameter_info').get_editor_property('name')), round(p.get_editor_property('parameter_value'), 4))
                        for p in m.get_editor_property('scalar_parameter_values')]
        d['vectors'] = [(str(p.get_editor_property('parameter_info').get_editor_property('name')), str(p.get_editor_property('parameter_value')))
                        for p in m.get_editor_property('vector_parameter_values')]
        d['textures'] = [(str(p.get_editor_property('parameter_info').get_editor_property('name')),
                          p.get_editor_property('parameter_value').get_path_name() if p.get_editor_property('parameter_value') else None)
                         for p in m.get_editor_property('texture_parameter_values')]
        sw = {}
        try:
            for n in MEL.get_static_switch_parameter_names(m):
                try:
                    sw[str(n)] = MEL.get_material_instance_static_switch_parameter_value(m, n)
                except Exception as e:  # noqa: BLE001
                    sw[str(n)] = 'ERR %s' % e
        except Exception as e:  # noqa: BLE001
            sw['_err'] = str(e)
        d['switches'] = sw
        R['mis'][mp] = d
    except Exception:  # noqa: BLE001
        R['errors'].append('%s: %s' % (mp, traceback.format_exc()[-400:]))

for sn, ems in SYSTEMS.items():
    S = '/Game/Assets/MyShip/Drivable/FX/%s.%s' % (sn, sn)
    try:
        summ = nt('GetSystemSummary', system=sref(S))
        names = [e['emitterName'] for e in summ.get('emitters', [])]
        R['renderers'][sn] = {'emitters': names}
        for em in (ems or names):
            topo = nt('GetEmitterTopology', emitterRef=ref(S, em))
            nr = len(topo.get('renderers', topo.get('rendererClasses', [])))
            rs = []
            for i in range(nr):
                pv = fx_renderer_get(S, em, i)
                rs.append({'i': i, 'Material': (pv.get('Material') or {}).get('refPath'),
                           'bOverrideMaterials': pv.get('bOverrideMaterials'),
                           'OverrideMaterials': [(o.get('explicitMat') or {}).get('refPath') for o in (pv.get('OverrideMaterials') or [])],
                           'Meshes': [((x.get('mesh') or {}).get('refPath')) for x in (pv.get('Meshes') or [])],
                           'SubImageSize': pv.get('SubImageSize'), 'Alignment': pv.get('Alignment'), 'SortMode': pv.get('SortMode')})
            R['renderers'][sn][em] = rs
    except Exception:  # noqa: BLE001
        R['errors'].append('%s: %s' % (sn, traceback.format_exc()[-600:]))

with open(os.path.join(VAL, 'fx_inspect.json'), 'w') as f:
    json.dump(R, f, indent=1, default=str)
print(json.dumps(R, indent=1, default=str)[:12000])

AS_THUMBS = ['/Game/VFXASandbox/VFX/00_Common/Materials/MI_Ball_01', '/Game/Assets/Effects/Projectiles/FireExplosion/M_ExplosionSphere',
             '/Game/VFXASandbox/Core/Spells/Default_Spells/Spell_Fireball/Materials/MI_Flame_MeshRing',
             '/Game/Assets/Effects/Shared/M_DefaultSprite_trans', '/Game/Assets/Effects/MyThruster/M_Fire',
             '/Game/VFXASandbox/Core/Spells/Default_Spells/Spell_Fireball/Materials/MI_Smoke_Puff']
exec(open(os.path.join(_AS_UE, 'as_00d_thumbs.py')).read())
