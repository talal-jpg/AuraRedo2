"""Round 3 review fixes (EXPORT_R3.md section 15): offline compile check of M_AirshipR3's Custom node bodies, no editor.

  python3 -I -B SourceArt/Airship/scripts/r3_hlsl_check.py        (exit 0 = every node compiled; run it unpiped: the DXC
                                                                    library aborts at exit and can eat piped output)

Reads the code strings straight out of Docs/Airship/scripts/ue/as_90_r3_textures_material.py (AS90_PAL_CODE,
AS90_INK_CODE, AS90_SIL_CODE, AS90_FINAL_CODE, AS90_LIFT_CODE: their Python expressions evaluated with nothing but
range), wraps each body the way UE's HLSL translator wraps a Custom node ("<type> CustomExpressionN(FMaterialPixelParameters
Parameters, <inputs>)", as_90's input names and output types) and compiles one pixel shader that calls them in graph order
with the engine's own DXC (libdxcompiler.so of UE 5.8's ShaderConductor) for ps_6_0 and SPIR-V, HLSL 2018 and 2021.
The DXC binding is Talal's project's verified one (AuraRedo3/Saved/ClaudeTools/icelook/m1/hlsl_check_ice.py, imported
read only; only its compile function is used). Writes Docs/Airship/round3/export_hlsl_check.json and the source next
to it (_hlsl_check_source.hlsl in rig/detail/r3export/checks).
"""
import ast, json, os, sys
sys.dont_write_bytecode = True
AS90 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_90_r3_textures_material.py'
ICE = '/mnt/new_partition/UnrealProjects/AuraRedo3/Saved/ClaudeTools/icelook/m1'
OUT_JSON = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/export_hlsl_check.json'
OUT_SRC = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/r3export/checks/_hlsl_check_source.hlsl'
sys.path.insert(0, ICE)
import hlsl_check_ice as H

tree = ast.parse(open(AS90).read())
codes = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and \
            node.targets[0].id.endswith('_CODE'):
        codes[node.targets[0].id] = eval(compile(ast.Expression(node.value), AS90, 'eval'), {'__builtins__': {}, 'range': range})
F, F3, F4 = 'float', 'float3', 'float4'
# (as_90 name, return type, [(input, type)]) in graph order
NODES = [
    ('AS90_PAL_CODE', 'MaterialFloat3', [('UV1', 'float2')] + [('P%d' % k, F3) for k in range(24)]),
    ('AS90_INK_CODE', 'MaterialFloat', [('S', F4), ('PixelDepth', F), ('TanHalfFov', 'float2'), ('ViewSize', 'float2'), ('DMax', F),
                                        ('DNeg', F), ('PxNear', F), ('PxFar', F), ('FarStart', F), ('FarEnd', F), ('MinHalfWidth', F),
                                        ('FadeStart', F), ('FadeEnd', F), ('OpacityFar', F)]),
    ('AS90_SIL_CODE', 'MaterialFloat', [('N', F3), ('V', F3), ('PixelDepth', F), ('WidthPx', F), ('FadeStart', F), ('FadeEnd', F),
                                        ('MinSlope', F)]),
    ('AS90_FINAL_CODE', 'MaterialFloat3', [('Col', F3), ('Dot', F), ('Line', F), ('Comic', F), ('Sil', F), ('Bolt', F3), ('Ink', F3),
                                           ('Opacity', F)]),
    ('AS90_LIFT_CODE', 'MaterialFloat3', [('C', F3), ('LiftSat', F), ('ShadeLift', F)]),
]
parts = [H.PRELUDE]
for i, (name, rt, ins) in enumerate(NODES):
    body = codes[name]
    for bad in ('discard', 'clip('):
        assert bad not in body, (name, bad)
    decl = ''.join(', %s %s' % (t, n) for n, t in ins)
    parts.append('// ---- %s ----\n%s CustomExpression%d(FMaterialPixelParameters Parameters%s)\n{\n%s\n}\n' % (name, rt, i, decl, body))
pal_args = ', '.join('float3(%d.0/24.0, 0.5, 0.2)' % k for k in range(24))
parts.append(r'''
float4 main(float4 SvPosition : SV_Position, float2 Uv0 : TEXCOORD0, float2 Uv1 : TEXCOORD1, float3 Nin : TEXCOORD2,
            float3 Vin : TEXCOORD3, float4 S : TEXCOORD4, float Depth : TEXCOORD5) : SV_Target0
{
	FMaterialPixelParameters Pa; Pa.SvPosition = SvPosition;
	float3 col = CustomExpression0(Pa, Uv1, %s);
	float ln = CustomExpression1(Pa, S, Depth, float2(0.916, 0.515), float2(1920, 1080), 12, 2, 2.2, 1.2, 4000, 12000, 0.2, 20000, 40000, 1);
	float sil = CustomExpression2(Pa, Nin, Vin, Depth, 2.4, 6000, 12000, 0.02);
	float3 c = CustomExpression3(Pa, col, S.g, ln, 0, sil, float3(0.33, 0.3, 0.27), float3(0.011, 0.016, 0.03), 1);
	float3 e = CustomExpression4(Pa, c, 1.3, 0.55);
	return float4(c * 0.5 + e, 1);
}
''' % pal_args)
src = '\n'.join(parts)
os.makedirs(os.path.dirname(OUT_SRC), exist_ok=True)
open(OUT_SRC, 'w').write(src)
res, ok = {}, True
for hv in ('2018', '2021'):
    for target in (['-T', 'ps_6_0'], ['-T', 'ps_6_0', '-spirv']):
        st, txt = H.compile_dxc(src, ['-E', 'main'] + target + ['-HV', hv, '-O3'])
        tag = 'HV %s %s' % (hv, ' '.join(target))
        res[tag] = dict(ok=st == 0, messages=txt.strip()[:3000])
        ok = ok and st == 0
json.dump(dict(about=__doc__.strip().splitlines()[0], as90=AS90, nodes=[n for n, _, _ in NODES], results=res, all_ok=ok,
               source=OUT_SRC), open(OUT_JSON, 'w'), indent=1)
print('r3_hlsl_check:', 'ALL OK' if ok else 'FAILED', {k: v['ok'] for k, v in res.items()}, flush=True)
for k, v in res.items():
    if v['messages']:
        print(k, v['messages'][:1500], flush=True)
os._exit(0 if ok else 1)
