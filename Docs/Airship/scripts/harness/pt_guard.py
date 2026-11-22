# Guard for inbox scripts (2026-10-25): swaps `unreal` in the inbox namespace (and `import unreal` there) for a proxy
# that blocks editor calls known to crash UE 5.8 here. Everything else passes straight through.
# Crashes so far: (1) MaterialEditingLibrary.get_material_property_input_node (SIGSEGV, null hidden input),
# (2) texture export via Exporter.run_asset_export_task (check SupportsTexture, R32F source),
# (3) StaticMeshEditorSubsystem.has_vertex_colors (SIGSEGV, LOD without a mesh description).
# (4) MaterialEditingLibrary.delete_all_material_expressions_in_function / delete_material_expression_in_function on a loaded MF
#     (check !IsRooted in MarkAsGarbage, 2026-10-25 22:58).
import builtins, types, sys
_il_real_unreal = sys.modules['unreal']
_IL_WHY = {
    'get_material_property_input_node': 'SIGSEGV at MaterialEditingLibrary.cpp:1153 (GetExpressionInputForProperty returns null for inputs hidden for the domain/shading model). Walk expressions or export the MATERIAL to T3D and parse it.',
    'get_material_property_input_node_output_name': 'same null deref as get_material_property_input_node. Walk expressions or export the MATERIAL to T3D.',
    'delete_all_material_expressions_in_function': 'check(!IsRooted()) in MarkAsGarbage via DeleteMaterialExpressionInFunction on a material function loaded from disk (2026-10-25 22:58, ice look). Rebuild a function by moving its .uasset aside with the editor closed and creating it fresh.',
    'delete_material_expression_in_function': 'same check(!IsRooted()) as delete_all_material_expressions_in_function (expressions of a function loaded from disk are rooted). Move the .uasset aside with the editor closed and recreate it.',
    'has_vertex_colors': 'SIGSEGV at StaticMeshEditorSubsystem.cpp:1925 (derefs a null mesh description for LODs without source data). Read vertex colours another way (e.g. GeometryScript copy_mesh_from_static_mesh into a DynamicMesh) or skip.',
}
def _il_block(name):
    def f(*a, **k):
        raise RuntimeError('BLOCKED by pt_guard: %s CRASHED THE EDITOR on 2026-10-25: %s' % (name, _IL_WHY[name]))
    return f
def _il_blocked_tex():
    raise RuntimeError('BLOCKED by pt_guard: exporting a Texture through Exporter.run_asset_export_task(s) CRASHED THE EDITOR on 2026-10-25 (check SupportsTexture, EditorFactories.cpp:4698, e.g. PNG export of an R32F/HDR source). Read texture info from asset registry tags (Dimensions etc.) instead; for a preview, draw it into a render target with a material and export the render target.')
def _il_is_tex(o):
    try:
        return isinstance(o, _il_real_unreal.Texture)
    except Exception:
        return False
_IL_CLASS_BLOCK = {
    'MaterialEditingLibrary': ('get_material_property_input_node', 'get_material_property_input_node_output_name',
                               'delete_all_material_expressions_in_function', 'delete_material_expression_in_function'),
    'EditorStaticMeshLibrary': ('has_vertex_colors',),
}
_IL_INST_BLOCK = {'StaticMeshEditorSubsystem': ('has_vertex_colors',)}
class _ILClassProxy(object):
    def __init__(self, cls, blocked):
        object.__setattr__(self, '_c', cls); object.__setattr__(self, '_b', blocked)
    def __getattr__(self, n):
        if n in self._b:
            return _il_block(n)
        return getattr(self._c, n)
    def __call__(self, *a, **k):
        return self._c(*a, **k)
class _ILInstProxy(object):
    def __init__(self, obj, blocked):
        object.__setattr__(self, '_o', obj); object.__setattr__(self, '_b', blocked)
    def __getattr__(self, n):
        if n in self._b:
            return _il_block(n)
        return getattr(self._o, n)
class _ILExporter(object):
    def __getattr__(self, n):
        f = getattr(_il_real_unreal.Exporter, n)
        if n == 'run_asset_export_task':
            def g(task, *a, **k):
                if _il_is_tex(task.get_editor_property('object')):
                    _il_blocked_tex()
                return f(task, *a, **k)
            return g
        if n == 'run_asset_export_tasks':
            def g(tasks, *a, **k):
                for t in tasks:
                    if _il_is_tex(t.get_editor_property('object')):
                        _il_blocked_tex()
                return f(tasks, *a, **k)
            return g
        return f
def _il_get_editor_subsystem(cls, *a, **k):
    real_cls = cls._c if isinstance(cls, _ILClassProxy) else cls
    s = _il_real_unreal.get_editor_subsystem(real_cls, *a, **k)
    try:
        nm = real_cls.__name__
    except Exception:
        nm = ''
    if nm in _IL_INST_BLOCK and s is not None:
        return _ILInstProxy(s, _IL_INST_BLOCK[nm])
    return s
class _ILUnreal(types.ModuleType):
    def __getattr__(self, n):
        if n in _IL_CLASS_BLOCK:
            return _ILClassProxy(getattr(_il_real_unreal, n), _IL_CLASS_BLOCK[n])
        if n == 'Exporter':
            return _ILExporter()
        if n == 'get_editor_subsystem':
            return _il_get_editor_subsystem
        return getattr(_il_real_unreal, n)
_il_proxy = _ILUnreal('unreal')
_il_orig_import = builtins.__import__
def _il_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'unreal' and level == 0:
        return _il_proxy
    return _il_orig_import(name, globals, locals, fromlist, level)
_il_b = dict(builtins.__dict__); _il_b['__import__'] = _il_import
globals()['__builtins__'] = _il_b
globals()['unreal'] = _il_proxy
