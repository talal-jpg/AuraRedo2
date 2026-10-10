import unreal, os, json
S = '/tmp/claude-1000/-mnt-new-partition-UnrealProjects-AuraRedo3--claude-worktrees-laughing-dijkstra-b1224c/052b27a9-b47f-4504-a779-b1d6635cf958/scratchpad'
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if EAL.does_asset_exist('/Game/Test/L_Impact'):
    EAL.delete_asset('/Game/Test/L_Impact')
unreal.log('ImpactTest: new_level %s' % LES.new_level('/Game/Test/L_Impact'))
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
unreal.log('ImpactTest: world %s' % world)
cfg = json.load(open(S + '/render_cfg.json'))

def log(m):
    unreal.log('ImpactTest: ' + str(m))

mat = unreal.load_asset(cfg.get('mat', '/Game/Level/GAS/GameplayAbilities/GA_Beam/M_PP_ImpactFrames'))
log('loaded %s' % mat)
# Optional: replace the custom node code with the working copy of the HLSL
if cfg.get('override_code'):
    custom = unreal.find_object(None, mat.get_path_name() + ':MaterialExpressionCustom_0')
    src = open(cfg['override_code']).read().split('\n')
    i = 0
    while src[i].startswith('//') or src[i].strip() == '':
        i += 1
    custom.set_editor_property('code', '\n'.join(src[i:]))
    log('code overridden')
MEL.recompile_material(mat)
st = MEL.get_statistics(mat)
log('PP stats pixel=%s samplers=%s' % (st.num_pixel_shader_instructions, st.num_samplers))

def unlit(name, code):
    path = '/Game/Test/' + name
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    m = AT.create_asset(name, '/Game/Test', unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    c = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -400, 0)
    c.set_editor_property('code', code)
    c.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ci = unreal.CustomInput(); ci.set_editor_property('input_name', 'P')
    c.set_editor_property('inputs', [ci])
    wp = MEL.create_material_expression(m, unreal.MaterialExpressionWorldPosition, -800, 0)
    MEL.connect_material_expressions(wp, '', c, 'P')
    MEL.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    return m

floor_m = unlit('M_Floor', 'float c = fmod(floor(P.x/150)+floor(P.y/150)+1000, 2); return lerp(float3(0.30,0.30,0.32), float3(0.45,0.45,0.47), c);')
wall_m = unlit('M_Sky', 'float h = saturate(P.z/3000); return lerp(float3(0.9,0.55,0.35), float3(0.75,0.45,0.4), h);')
mech_m = unlit('M_Mech', 'float s = frac(P.z/40) > 0.8 ? 0.15 : 0.0; float b = frac((P.x+P.y)/90) > 0.85 ? 0.12 : 0.0; return float3(0.35,0.42,0.18) - s - b;')

cube = unreal.load_asset('/Engine/BasicShapes/Cube')
sphere = unreal.load_asset('/Engine/BasicShapes/Sphere')
cyl = unreal.load_asset('/Engine/BasicShapes/Cylinder')

def spawn(mesh, loc, scale, m, custom_depth, rot=(0, 0, 0)):
    a = EAS.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
    a.static_mesh_component.set_static_mesh(mesh)
    a.set_actor_scale3d(unreal.Vector(*scale))
    smc = a.static_mesh_component
    smc.set_material(0, m)
    smc.set_render_custom_depth(custom_depth)
    return a

spawn(cube, (2000, 0, -50), (80, 80, 1), floor_m, False)
spawn(cube, (6000, 0, 1500), (1, 200, 60), wall_m, False)
spawn(cube, (-2000, 0, 1500), (1, 200, 60), wall_m, False)
spawn(cube, (2000, 6000, 1500), (200, 1, 60), wall_m, False)
spawn(cube, (2000, -6000, 1500), (200, 1, 60), wall_m, False)
# mech stand-in: torso, head, two legs, two arms, a gun arm
mx, my = 700, 60
spawn(cube, (mx, my, 330), (1.6, 2.2, 1.6), mech_m, True)
spawn(sphere, (mx, my, 460), (0.9, 0.9, 0.8), mech_m, True)
spawn(cyl, (mx, my - 70, 130), (0.5, 0.5, 2.4), mech_m, True)
spawn(cyl, (mx, my + 70, 130), (0.5, 0.5, 2.4), mech_m, True)
spawn(cyl, (mx - 20, my - 150, 290), (0.35, 0.35, 2.0), mech_m, True, (0, 0, 25))
spawn(cyl, (mx - 60, my + 150, 300), (0.35, 0.35, 2.2), mech_m, True, (40, 0, -20))
spawn(cube, (mx - 260, my + 200, 360), (2.6, 0.3, 0.3), mech_m, True)
# second mech further back
spawn(cube, (2200, -500, 300), (1.4, 1.8, 2.4), mech_m, True)
spawn(sphere, (2200, -500, 470), (0.8, 0.8, 0.7), mech_m, True)

ppt = AT.create_asset('M_PPTest', '/Game/Test', unreal.Material, unreal.MaterialFactoryNew()) if not EAL.does_asset_exist('/Game/Test/M_PPTest') else unreal.load_asset('/Game/Test/M_PPTest')
ppt.set_editor_property('material_domain', unreal.MaterialDomain.MD_POST_PROCESS)
ppt.set_editor_property('blendable_location', unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
stx = MEL.create_material_expression(ppt, unreal.MaterialExpressionSceneTexture, -600, 0)
stx.set_editor_property('scene_texture_id', unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0)
om = MEL.create_material_expression(ppt, unreal.MaterialExpressionOneMinus, -300, 0)
MEL.connect_material_expressions(stx, 'Color', om, '')
MEL.connect_material_property(om, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
MEL.recompile_material(ppt)
st2 = MEL.get_statistics(ppt)
log('PPTest stats pixel=%s' % st2.num_pixel_shader_instructions)
cap = EAS.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(-120, -40, 260), unreal.Rotator(roll=0, pitch=-4, yaw=6))
comp = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
W, H = cfg.get('w', 960), cfg.get('h', 540)
rt = unreal.RenderingLibrary.create_render_target2d(world, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA8)
comp.set_editor_property('texture_target', rt)
comp.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
comp.set_editor_property('fov_angle', 90.0)
comp.set_editor_property('capture_every_frame', False)
comp.set_editor_property('capture_on_movement', False)
comp.set_editor_property('always_persist_rendering_state', True)
mid = unreal.MaterialLibrary.create_dynamic_material_instance(world, mat)
for k, v in cfg.get('scalars', {}).items():
    mid.set_scalar_parameter_value(k, v)
pps = comp.get_editor_property('post_process_settings')
wb = unreal.WeightedBlendables()
b = unreal.WeightedBlendable()
b.set_editor_property('weight', 1.0)
b.set_editor_property('object', mid)
wb.set_editor_property('array', [b])
pps.set_editor_property('weighted_blendables', wb)
comp.set_editor_property('post_process_settings', pps)
comp.set_editor_property('post_process_blend_weight', 1.0)

def set_blend(obj):
    pps = comp.get_editor_property('post_process_settings')
    wb = unreal.WeightedBlendables()
    b = unreal.WeightedBlendable()
    b.set_editor_property('weight', 1.0)
    b.set_editor_property('object', obj)
    wb.set_editor_property('array', [b])
    pps.set_editor_property('weighted_blendables', wb)
    comp.set_editor_property('post_process_settings', pps)
    log('blendables now %s' % comp.get_editor_property('post_process_settings').get_editor_property('weighted_blendables').get_editor_property('array'))
set_blend(ppt)
comp.capture_scene()
unreal.RenderingLibrary.export_render_target(world, rt, S + '/shots/', 'pptest')
set_blend(mid)
# warm up so shaders are ready
for i in range(cfg.get('warm', 3)):
    mid.set_scalar_parameter_value('PreviewT', 0.3)
    comp.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, S + '/shots/', 'warm')

for t in cfg['ts']:
    mid.set_scalar_parameter_value('PreviewT', t)
    comp.capture_scene()
    name = cfg.get('prefix','shot') + '_%03d' % int(round(t * 100)) if t >= 0 else 'shot_base'
    unreal.RenderingLibrary.export_render_target(world, rt, S + '/shots/', name)
    log('exported ' + name)
log('done')
