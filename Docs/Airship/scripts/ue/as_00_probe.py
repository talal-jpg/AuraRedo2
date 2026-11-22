# as_00_probe.py - read-only probe of the source assets the airship session 1 copies from (no saves).
import unreal, json

def _p(*a):
    print(*a)

imc = unreal.load_asset('/Game/Level/PlayerInput/IMC_PlayerMappings')
_p('IMC_PlayerMappings', imc)
try:
    maps = imc.get_editor_property('default_key_mappings')
    _p('default_key_mappings type', type(maps))
    try:
        mlist = maps.get_editor_property('mappings')
    except Exception as e:
        _p('no mappings prop on struct', e); mlist = []
except Exception as e:
    _p('default_key_mappings failed', e)
    mlist = imc.get_editor_property('mappings')
for m in mlist:
    a = m.get_editor_property('action')
    k = m.get_editor_property('key')
    mods = m.get_editor_property('modifiers')
    trig = m.get_editor_property('triggers')
    _p('  map', a.get_name() if a else None, k.export_text() if hasattr(k, 'export_text') else k,
       'mods', [(type(x).__name__, x.get_name()) for x in mods], 'trig', [type(x).__name__ for x in trig])
    for x in mods:
        try:
            _p('     mod json', unreal.ToolsetLibrary.get_object_properties(x, []))
        except Exception as e:
            _p('     mod json failed', e)

ia = unreal.load_asset('/Game/Level/PlayerInput/IA_Rotate')
_p('IA_Rotate value_type', ia.get_editor_property('value_type'), 'mods', [type(x).__name__ for x in ia.get_editor_property('modifiers')],
   'trig', [type(x).__name__ for x in ia.get_editor_property('triggers')])

# toolsets available
try:
    for t in ['NiagaraToolsets.NiagaraToolset_System', 'EditorAppToolset.EditorAppToolset']:
        _p('toolset registered', t, unreal.ToolsetRegistry.is_toolset_registered(t))
except Exception as e:
    _p('ToolsetRegistry probe failed', e)
try:
    _p('registered toolsets', unreal.ToolsetRegistry.get_registered_toolsets() if hasattr(unreal.ToolsetRegistry, 'get_registered_toolsets') else dir(unreal.ToolsetRegistry))
except Exception as e:
    _p('list toolsets failed', e)

# material M_Airship
mat = unreal.load_asset('/Game/Assets/MyShip/M_Airship')
_p('M_Airship', mat, 'shading', mat.get_editor_property('shading_model'), 'blend', mat.get_editor_property('blend_mode'))
try:
    exprs = unreal.ToolsetLibrary.get_object_properties(mat, ['Expressions']) if False else None
except Exception:
    pass
for t in ['TextureSample', 'Constant', 'TextureCoordinate', 'Multiply', 'TextureSampleParameter2D', 'ScalarParameter', 'VectorParameter', 'Constant3Vector', 'OneMinus', 'LinearInterpolate']:
    pass
mel = unreal.MaterialEditingLibrary
_p('num expressions', mel.get_num_material_expressions(mat))
_p('used textures', [t.get_path_name() for t in mel.get_used_textures(mat)])
