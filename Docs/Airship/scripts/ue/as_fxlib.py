# as_fxlib.py - Niagara build helpers for the airship FX scripts (exec'd after as_nh.py into the inbox namespace).
import unreal, json

T_FLOAT = '/Script/Niagara.NiagaraFloat'
T_BOOL = '/Script/Niagara.NiagaraBool'
T_INT = '/Script/Niagara.NiagaraInt32'
T_VEC3 = '/Script/CoreUObject.Vector3f'
T_VEC2 = '/Script/CoreUObject.Vector2f'
T_QUAT = '/Script/CoreUObject.Quat4f'
T_COLOR = '/Script/CoreUObject.LinearColor'
T_POS = '/Script/Niagara.NiagaraPosition'

_DEF = {T_FLOAT: {'value': 0.0}, T_INT: {'value': 0}, T_BOOL: {'value': 0}, T_VEC3: {'x': 0, 'y': 0, 'z': 0},
        T_VEC2: {'x': 0, 'y': 0}, T_QUAT: {'x': 0, 'y': 0, 'z': 0, 'w': 1}, T_COLOR: {'r': 1, 'g': 1, 'b': 1, 'a': 1},
        T_POS: {'x': 0, 'y': 0, 'z': 0}}


def fx_val(typ, value=None):
    return {'struct': {'refPath': typ}, 'value': value if value is not None else _DEF[typ]}


def fx_user_vars(system, items):
    """items: [(name without 'User.', type, value dict)] -> AddUserVariables (replaces same-named)."""
    vs = [{'name': 'User.' + n, 'type': {'classStructOrEnum': {'refPath': t}}, 'description': d,
           'defaultValue': fx_val(t, v)} for n, t, v, d in items]
    return nt('AddUserVariables', system=sref(system), variablesToAdd=vs)


def fx_emitter_props(system, emitter, props):
    return nt('SetEmitterData', emitter=ref(system, emitter), emitterData={'propertyValues': json.dumps(props)})


def fx_renderer_props(system, emitter, index, props):
    return nt('SetRendererData', renderer=ref(system, emitter, renderer=index), rendererData={'propertyValues': json.dumps(props)})


def fx_renderer_get(system, emitter, index):
    return json.loads(nt('GetRendererData', rendererRef=ref(system, emitter, renderer=index))['propertyValues'])


def fx_mesh_renderer(system, emitter, mesh_path, remove_first=True):
    """Replaces renderer 0 by a mesh renderer drawing mesh_path (its own materials). Returns the new index."""
    if remove_first:
        nt('RemoveRenderer', rendererToRemove=ref(system, emitter, renderer=0))
    r = nt('AddRenderer', newRendererLocation=ref(system, emitter), rendererClass={'refPath': '/Script/Niagara.NiagaraMeshRendererProperties'})
    idx = r.get('rendererIndex', r.get('index', 0)) if isinstance(r, dict) else 0
    cur = fx_renderer_get(system, emitter, idx)
    meshes = cur.get('Meshes') or [{}]
    meshes[0]['mesh'] = {'refPath': mesh_path}
    fx_renderer_props(system, emitter, idx, {'Meshes': meshes})
    return idx


def fx_set(system, emitter, script, module, name, data):
    return set_input(system, emitter, script, module, [name], data)


def fx_setparams(system, emitter, script, entries):
    """entries: [(var name, type, expression or None, value dict or None)] -> new SetParameters module; returns its name."""
    params = [{'variable': {'name': n, 'type': {'classStructOrEnum': {'refPath': t}}}, 'defaultValue': fx_val(t, v)}
              for n, t, e, v in entries]
    topo = nt('AddSetParametersModule', moduleLocationRef=ref(system, emitter, script), parameters=params)
    mod = topo['moduleName']
    for n, t, e, v in entries:
        if e is not None:
            fx_set(system, emitter, script, mod, n, f_expr(e))
    return mod


def fx_remove_module(system, emitter, script, module):
    return nt('RemoveModule', moduleToRemove=ref(system, emitter, script, module))


def fx_add_module(system, emitter, script, module_asset):
    return nt('AddModule', moduleLocationRef=ref(system, emitter, script), moduleAsset={'refPath': module_asset})['moduleName']


def fx_enum(enum_path, name):
    return {'struct': {'refPath': '/Script/NiagaraEditor.NiagaraExt_StackInputData_Enum'},
            'value': {'enum': {'refPath': enum_path}, 'enumName': name, 'displayName': name.split('::')[-1]}}


def fx_modules(system, emitter, script):
    return [m['moduleName'] for m in nt('GetScriptStackTopology', scriptRef=ref(system, emitter, script))['modules']]


def fx_fountain_to(system, em, rate_expr, life, color, size_min, size_max, vel_dir_expr, speed_expr, gravity_z, drag,
                   material, growth=None, sort='ViewDepth', alignment=None, shape_radius=None, size_vec_expr=None,
                   burst=None, pos_offset_expr=None):
    """Configures an emitter made from the engine 'Fountain' template (world space).
    rate_expr: spawn rate HLSL (or burst=int: SpawnRate removed, SpawnBurst_Instantaneous added).
    vel_dir_expr: float3 direction in the component's LOCAL space (rotated to world with SystemLocalToWorldNoScale).
    growth: HLSL factor of NormalizedAge for the sprite size (None = keep the spawn size).
    size_vec_expr: float2 HLSL for a non-uniform spawn size (velocity-aligned streaks), else uniform min/max."""
    PS_, PU_, EU_ = 'ParticleSpawnScript', 'ParticleUpdateScript', 'EmitterUpdateScript'
    if burst is not None:
        fx_remove_module(system, em, EU_, 'SpawnRate')
        mb = fx_add_module(system, em, EU_, '/Niagara/Modules/Emitter/SpawnBurst_Instantaneous.SpawnBurst_Instantaneous')
        fx_set(system, em, EU_, mb, 'Spawn Count', fx_val(T_INT, {'value': int(burst)}))
    else:
        fx_set(system, em, EU_, 'SpawnRate', 'SpawnRate', f_expr(rate_expr))
    fx_set(system, em, PS_, 'InitializeParticle', 'Lifetime Min', f_float(life[0]))
    fx_set(system, em, PS_, 'InitializeParticle', 'Lifetime Max', f_float(life[1]))
    fx_set(system, em, PS_, 'InitializeParticle', 'Color', fx_val(T_COLOR, color))
    fx_set(system, em, PS_, 'InitializeParticle', 'Uniform Sprite Size Min', f_expr(size_min))
    fx_set(system, em, PS_, 'InitializeParticle', 'Uniform Sprite Size Max', f_expr(size_max))
    if pos_offset_expr:
        fx_set(system, em, PS_, 'InitializeParticle', 'UsePositionOffset', fx_val(T_BOOL, {'value': -1}))
        fx_set(system, em, PS_, 'InitializeParticle', 'Position Offset', f_expr(pos_offset_expr))
        fx_set(system, em, PS_, 'InitializeParticle', 'Position Offset Coordinate Space',
               fx_enum('/Niagara/Enums/ENiagaraCoordinateSpace.ENiagaraCoordinateSpace', 'ENiagaraCoordinateSpace::Local'))
    if shape_radius:
        fx_set(system, em, PS_, 'ShapeLocation', 'Sphere Radius', f_expr(shape_radius))
    fx_remove_module(system, em, PS_, 'AddVelocity')
    vel = 'mul(float4(normalize(%s) * (%s), 0.0), Engine.Owner.SystemLocalToWorldNoScale).xyz' % (vel_dir_expr, speed_expr)
    # velocity-aligned sprites (streaks) keep rotation 0, else SpriteRotation would turn them off the velocity axis
    rot = '0.0' if alignment == 'VelocityAligned' else 'rand(360.0)'
    ent = [('Particles.Velocity', T_VEC3, vel, None), ('Particles.SpriteRotation', T_FLOAT, rot, None)]
    if size_vec_expr:
        ent.append(('Particles.SpriteSize', T_VEC2, size_vec_expr, {'x': 10, 'y': 10}))
    fx_setparams(system, em, PS_, ent)
    if growth:
        fx_setparams(system, em, PS_, [('Particles.BaseSize', T_VEC2, 'Particles.SpriteSize', {'x': 100, 'y': 100})])
        fx_setparams(system, em, PU_, [('Particles.SpriteSize', T_VEC2, 'Particles.BaseSize * (%s)' % growth, {'x': 100, 'y': 100})])
    fx_set(system, em, PU_, 'GravityForce', 'Gravity', fx_val(T_VEC3, {'x': 0, 'y': 0, 'z': gravity_z}))
    fx_set(system, em, PU_, 'Drag', 'Drag', f_float(drag))
    rp = {'Material': {'refPath': material}, 'SortMode': sort}
    if alignment:
        rp['Alignment'] = alignment
    fx_renderer_props(system, em, 0, rp)
    return {s: fx_modules(system, em, s) for s in (EU_, PS_, PU_)}
