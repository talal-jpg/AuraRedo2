#!/usr/bin/env python3
"""Lint editor scripts against the generated UE Python stub (Intermediate/PythonStub/unreal.py).

The stub is written by the editor at startup when Python Developer Mode is on
([/Script/PythonScriptPlugin.PythonScriptPluginUserSettings] bDeveloperMode=True in
Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini). It lists exactly what this project's
editor exposes to Python (engine, plugins and the Aura module).

usage: python3 stub_lint.py [--stub path/to/unreal.py] script.py [script.py ...]
Reports:
  unreal.X            X must be a module-level class/function/constant of the stub
  unreal.X.y          y must be a member (method, property, enum value) of X or its bases
  get/set_editor_property('name')  'name' must be an editor property of some class (or of the class
                      the receiver is known to be, when the script did x = unreal.X(...))
  obj.method(...)     method names that exist nowhere in the stub (and are not Python builtins)
"""
import ast, os, re, sys, pickle

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STUB = os.path.normpath(os.path.join(HERE, '../../../../Intermediate/PythonStub/unreal.py'))


def parse_stub(path):
    cache = path + '.lintcache'
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        with open(cache, 'rb') as f:
            return pickle.load(f)
    classes, module_names, all_methods, all_props = {}, set(), set(), set()
    cur = None
    re_class = re.compile(r'^class (\w+)\(([^)]*)\):')
    re_mdef = re.compile(r'^    def (\w+)\(')
    re_fdef = re.compile(r'^def (\w+)\(')
    re_assign = re.compile(r'^(\w+)\s*[:=]')
    re_member = re.compile(r'^    (\w+)\s*:\s*[\w\[\], .]+\s*=')
    re_prop = re.compile(r'^    - ``(\w+)`` \(')
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            m = re_class.match(line)
            if m:
                cur = m.group(1)
                classes[cur] = {'bases': [b.strip() for b in m.group(2).split(',') if b.strip()],
                                'members': set(), 'props': set()}
                module_names.add(cur)
                continue
            m = re_fdef.match(line)
            if m:
                module_names.add(m.group(1)); cur = None; continue
            if line and not line[0].isspace():
                m = re_assign.match(line)
                if m:
                    module_names.add(m.group(1))
                if not line.startswith('class '):
                    cur = None
                continue
            if cur is None:
                continue
            m = re_mdef.match(line)
            if m:
                classes[cur]['members'].add(m.group(1)); all_methods.add(m.group(1)); continue
            m = re_member.match(line)
            if m:
                classes[cur]['members'].add(m.group(1)); continue
            m = re_prop.match(line)
            if m:
                classes[cur]['props'].add(m.group(1)); all_props.add(m.group(1))
    data = (classes, module_names, all_methods, all_props)
    try:
        with open(cache, 'wb') as f:
            pickle.dump(data, f)
    except OSError:
        pass
    return data


def mro(classes, name, seen=None):
    seen = seen or []
    if name in seen or name not in classes:
        return seen
    seen.append(name)
    for b in classes[name]['bases']:
        mro(classes, b, seen)
    return seen


def has_member(classes, cls, member):
    for c in mro(classes, cls):
        if member in classes[c]['members'] or member in classes[c]['props']:
            return True
    return False


def has_prop(classes, cls, prop):
    for c in mro(classes, cls):
        if prop in classes[c]['props'] or prop in classes[c]['members']:
            return True
    return False


PY_BUILTIN_METHODS = set(dir(str)) | set(dir(list)) | set(dir(dict)) | set(dir(set)) | set(dir(bytes)) | {
    'read', 'write', 'close', 'readlines', 'flush', 'seek', 'group', 'groups', 'match', 'search', 'findall', 'sub',
    'split', 'dump', 'dumps', 'load', 'loads', 'join', 'exists', 'isfile', 'isdir', 'makedirs', 'listdir', 'remove',
    'rename', 'getmtime', 'abspath', 'dirname', 'basename', 'normpath', 'splitext', 'getvalue', 'time', 'sleep',
    'strftime', 'utcnow', 'now', 'isoformat', 'sqrt', 'atan2', 'degrees', 'radians', 'cos', 'sin', 'acos', 'asin',
    'hypot', 'floor', 'ceil', 'isnan', 'isfinite', 'fabs', 'format_exc', 'print_exc', 'redirect_stdout',
    'getcwd', 'environ', 'get', 'copy', 'deepcopy', 'tan', 'pi', 'exp', 'log', 'pow', 'mean', 'append'}


def lint(path, classes, module_names, all_methods, all_props):
    src = open(path, encoding='utf-8').read()
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return ['%s:%s SYNTAX ERROR %s' % (path, e.lineno, e.msg)]
    out = []
    known_types = {}  # variable name -> unreal class name, from x = unreal.X(...) / unreal.X.cast / load_asset is unknown

    def uattr(node):
        """unreal.X or unreal.X.y -> list of names, else None"""
        names = []
        while isinstance(node, ast.Attribute):
            names.append(node.attr); node = node.value
        if isinstance(node, ast.Name) and node.id == 'unreal':
            return list(reversed(names))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v = node.value
            if isinstance(v, ast.Call):
                ch = uattr(v.func)
                if ch and len(ch) == 1 and ch[0] in classes:
                    known_types[node.targets[0].id] = ch[0]
                if ch and len(ch) == 2 and ch[1] in ('get_default_object', 'cast') and ch[0] in classes:
                    known_types[node.targets[0].id] = ch[0]
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            ch = uattr(node)
            if ch:
                key = '.'.join(ch)
                if key in seen:
                    continue
                seen.add(key)
                if ch[0] not in module_names:
                    out.append('%s:%d unreal.%s: not in stub' % (path, node.lineno, ch[0]))
                elif len(ch) >= 2 and ch[0] in classes and not has_member(classes, ch[0], ch[1]):
                    out.append('%s:%d unreal.%s.%s: %s has no member %s' % (path, node.lineno, ch[0], ch[1], ch[0], ch[1]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            meth = node.func.attr
            recv = node.func.value
            if meth in ('get_editor_property', 'set_editor_property') and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                prop = node.args[0].value
                cls = known_types.get(recv.id) if isinstance(recv, ast.Name) else None
                if cls:
                    if not has_prop(classes, cls, prop):
                        out.append('%s:%d %s(%r): not an editor property of %s (or its bases)' % (path, node.lineno, meth, prop, cls))
                elif prop not in all_props:
                    out.append('%s:%d %s(%r): no class in the stub has this editor property' % (path, node.lineno, meth, prop))
            elif uattr(node.func) is None and meth not in all_methods and meth not in PY_BUILTIN_METHODS \
                    and not meth.startswith('_'):
                key = 'm:' + meth
                if key not in seen:
                    seen.add(key)
                    out.append('%s:%d .%s(): no method of that name anywhere in the stub (fine if it is a local helper/py object)' % (path, node.lineno, meth))
    return out


def main(argv):
    stub = DEFAULT_STUB
    if len(argv) > 2 and argv[1] == '--stub':
        stub = argv[2]; argv = argv[2:]
    data = parse_stub(stub)
    print('stub: %s (%d classes)' % (stub, len(data[0])))
    n = 0
    for p in argv[1:]:
        for line in lint(p, *data):
            print(line); n += 1
    print('%d findings' % n)


if __name__ == '__main__':
    main(sys.argv)
