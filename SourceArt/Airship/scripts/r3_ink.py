"""Round 3: Talal's comic ink shader (StylizedAirship/scripts/comic_lines.py) as a reusable, parametrised material.

comic_lines.py runs its bake when it is executed, so it cannot be imported. This module reads its source (read only),
keeps only the shader builder (build(), lin(), LIGHT, PAPER, INK) and executes that in a private namespace, so the ink
logic stays HIS, line for line. Two checked text patches (each must match exactly once, else nothing runs) add the
round 3 knobs R3_HATCH and R3_PANEL (multipliers on the hatch and panel-line terms; 1.0 = his shader unchanged).
The other knobs are his own globals (COMIC_BEVEL, COMIC_EDGE_THR, COMIC_HATCH_FREQ) plus the two AO distances, set on
the built nodes afterwards (crease AO 0.15 m and the "spotted black" AO_Main 1.2 m in his file).

  import r3_ink
  mat = r3_ink.comic_material('R3_Comic', bevel=0.025, crease=0.05, spot=0.4)   # node 'BakeMask' -> emission of the mask
  r3_ink.post_process(mask_float_2d)                                             # his blur + smoothstep

Also: link_mask_output(mat) wires BakeMask to the output (what hull_ink_drivable.py does before baking).
"""
import ast, os
import numpy as np

COMIC_SCRIPT = '/mnt/new_partition/BlenderProjects/StylizedAirship/scripts/comic_lines.py'
HIS = dict(bevel=0.08, edge_thr=0.26, hatch_freq=2.4, crease=0.15, spot=1.2, hatch=1.0, panel=1.0)
SMOOTH, INK_CUT = 2, (0.38, 0.52)                      # comic_lines.py COMIC_SMOOTH, COMIC_INK_CUT
PAPER_HEX, INK_HEX = 'F3EEE4', '1C2230'
_PATCHES = [
    ('    lines = math_("MAXIMUM", lines, hatch)\n',
     '    lines = math_("MAXIMUM", lines, math_("MULTIPLY", hatch, globals().get("R3_HATCH", 1.0)))\n'),
    ('    lines = math_("MAXIMUM", lines, math_("MULTIPLY", panel, 0.9))\n',
     '    lines = math_("MAXIMUM", lines, math_("MULTIPLY", panel, 0.9 * globals().get("R3_PANEL", 1.0)))\n'),
]
_KEEP_FUNCS = ('lin', 'build')
_KEEP_NAMES = ('P', 'TEX', 'LIGHT', 'PAPER', 'INK')


def _source():
    src = open(COMIC_SCRIPT).read()
    for old, new in _PATCHES:
        n = src.count(old)
        if n != 1:
            raise RuntimeError('comic_lines.py changed: patch target found %d times: %r' % (n, old.strip()))
        src = src.replace(old, new)
    return src


def _names(t):
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        return [x for e in t.elts for x in _names(e)]
    return []


def builder(**knobs):
    """his build() in a private namespace with the given knobs; returns the function"""
    tree = ast.parse(_source(), COMIC_SCRIPT)
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in _KEEP_FUNCS:
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(n in _KEEP_NAMES for t in node.targets for n in _names(t)):
            keep.append(node)
    got = {n.name for n in keep if isinstance(n, ast.FunctionDef)}
    assert got == set(_KEEP_FUNCS), got
    g = {'__name__': 'r3_comic_lines', 'COMIC_BEVEL': knobs['bevel'], 'COMIC_EDGE_THR': knobs['edge_thr'],
         'COMIC_HATCH_FREQ': knobs['hatch_freq'], 'R3_HATCH': knobs['hatch'], 'R3_PANEL': knobs['panel']}
    exec(compile(ast.Module(body=keep, type_ignores=[]), COMIC_SCRIPT, 'exec'), g)
    return g['build']


def comic_material(name, **kw):
    """a NEW material `name` with his comic node tree and these knobs (defaults = his values). His stored
    M_ComicLines (if the open file has one) is left as it is."""
    import bpy
    knobs = dict(HIS)
    knobs.update(kw)
    build = builder(**knobs)
    stored = bpy.data.materials.get('M_ComicLines')
    if stored is not None:
        stored.name = '_r3_stored_M_ComicLines'
    try:
        m = build()                      # creates a fresh "M_ComicLines"
        m.name = name
        m.use_fake_user = False
    finally:
        if stored is not None:
            stored.name = 'M_ComicLines'
    ao = [n for n in m.node_tree.nodes if n.type == 'AMBIENT_OCCLUSION']
    assert len(ao) == 2 and sum(n.name == 'AO_Main' for n in ao) == 1, [n.name for n in ao]
    for n in ao:
        n.inputs['Distance'].default_value = knobs['spot'] if n.name == 'AO_Main' else knobs['crease']
    m['r3_knobs'] = str(knobs)
    return m


def link_mask_output(m):
    nt = m.node_tree
    nt.links.new(nt.nodes['BakeMask'].outputs[0], nt.nodes['Out'].inputs['Surface'])


def post_process(m, smooth=SMOOTH, cut=INK_CUT):
    """comic_lines.py's post-process on a 2-D float mask: `smooth` passes of a [1,2,1] blur, smoothstep cut"""
    m = np.asarray(m, np.float32).copy()
    for _ in range(smooth):
        for ax in (0, 1):
            m = (np.roll(m, 1, ax) + 2 * m + np.roll(m, -1, ax)) * 0.25
    lo, hi = cut
    t = np.clip((m - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def hex_rgb(h):
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
