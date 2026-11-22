# as_00e_probe_thruster_mesh.py - read-only: the mech jet flame mesh (Thruster_ftl) bounds/materials and how BP_MyCharMech
# places it, plus M_Thruster / M_Fire parameters and MI_Popcorn_Puff parent/params.
import unreal
sm = unreal.load_asset('/Game/Assets/Effects/MyThruster/Thruster_ftl')
bb = sm.get_bounding_box()
print('Thruster_ftl bounds min', bb.min, 'max', bb.max)
print('lods', sm.get_num_lods(), 'tris lod0', unreal.EditorStaticMeshLibrary.get_number_verts(sm, 0) if hasattr(unreal.EditorStaticMeshLibrary, 'get_number_verts') else '?')
print('materials', [(m.get_editor_property('material_slot_name'), m.get_editor_property('material_interface').get_path_name() if m.get_editor_property('material_interface') else None) for m in sm.get_editor_property('static_materials')])
sm2 = unreal.load_asset('/Game/Assets/Effects/MyThruster/SM_Thruster')
print('SM_Thruster bounds', sm2.get_bounding_box().min, sm2.get_bounding_box().max, 'mats', [m.get_editor_property('material_interface').get_name() for m in sm2.get_editor_property('static_materials') if m.get_editor_property('material_interface')])
for mp in ['/Game/Assets/Effects/MyThruster/M_Thruster', '/Game/Assets/Effects/MyThruster/M_Fire', '/Game/VFXASandbox/VFX/00_Common/Materials/MI_Popcorn_Puff',
           '/Game/VFXASandbox/VFX/Xtra_Fire/Material_Instances/MI_Fire_Flip_Mult_Scrolling']:
    m = unreal.load_asset(mp)
    mel = unreal.MaterialEditingLibrary
    base = m.get_base_material() if hasattr(m, 'get_base_material') else m
    print('---', mp, m.get_class().get_name(), 'base', base.get_path_name())
    try:
        print('   blend', base.get_editor_property('blend_mode'), 'shading', base.get_editor_property('shading_model'), 'domain', base.get_editor_property('material_domain'),
              'usage niagara sprites', base.get_editor_property('used_with_niagara_sprites'), 'meshes', base.get_editor_property('used_with_niagara_mesh_particles'))
    except Exception as e:
        print('   base props', e)
    try:
        print('   scalars', mel.get_scalar_parameter_names(base), 'vectors', mel.get_vector_parameter_names(base), 'textures', mel.get_texture_parameter_names(base))
    except Exception as e:
        print('   params', e)
    if isinstance(m, unreal.MaterialInstanceConstant):
        print('   MI scalar values', [(str(p.get_editor_property('parameter_info').get_editor_property('name')), p.get_editor_property('parameter_value')) for p in m.get_editor_property('scalar_parameter_values')])
        print('   MI tex values', [(str(p.get_editor_property('parameter_info').get_editor_property('name')), p.get_editor_property('parameter_value').get_path_name() if p.get_editor_property('parameter_value') else None) for p in m.get_editor_property('texture_parameter_values')])
        print('   MI vec values', [(str(p.get_editor_property('parameter_info').get_editor_property('name')), p.get_editor_property('parameter_value')) for p in m.get_editor_property('vector_parameter_values')])
    print('   used textures', [t.get_name() for t in mel.get_used_textures(base)])
bp = unreal.load_asset('/Game/Level/MechChar/BP_MyCharMech')
cdo = unreal.get_default_object(bp.generated_class())
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
lib = unreal.SubobjectDataBlueprintFunctionLibrary
for h in sds.k2_gather_subobject_data_for_blueprint(bp):
    d = lib.get_data(h)
    o = lib.get_associated_object(d)
    if o and isinstance(o, (unreal.StaticMeshComponent, unreal.NiagaraComponent)):
        nm = str(lib.get_variable_name(d))
        extra = ''
        if isinstance(o, unreal.StaticMeshComponent) and o.get_editor_property('static_mesh'):
            extra = o.get_editor_property('static_mesh').get_name() + ' mats=' + str([x.get_name() if x else None for x in o.get_editor_property('override_materials')])
        if isinstance(o, unreal.NiagaraComponent):
            extra = str(o.get_editor_property('asset').get_name() if o.get_editor_property('asset') else None)
        print('mech comp', nm, type(o).__name__, extra, 'socket', o.get_editor_property('attach_socket_name'), 'loc', o.get_editor_property('relative_location'), 'rot', o.get_editor_property('relative_rotation'), 'scale', o.get_editor_property('relative_scale3d'))
