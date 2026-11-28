"""Agreed edits to the ship's own mesh (SM_Airship) for the round 3 detail pass: the single place they are applied.

Each zone may add ONE entry file to scripts/base_edits/ (z6.json for zone 6 ...) and never edits this module.
An edit only ever DELETES faces of SM_Airship, chosen by research island metadata (sm_airship_islands.json; the rig keeps
those ids). New geometry is always a detail object, never added into SM_Airship. Edits are applied to an in-memory
copy (renders, rig checks) or to an output copy (the assembler); AirshipRig.blend and Talal's files are never changed.

Entry file (base_edits/zN.json):
  {"zone": "Z6", "about": "...",
   "edits": [
     {"id": "z6_fan_back_L", "why": "open the back of the port fan (Talal 2026-11-28, point 4)",
      "select": {"part": "FanHousing_L", "piece": ["duct_back_wall", "tail_cone"]},   # or "islands": [1028, 1030]
      "where": {"box": [x0, x1, y0, y1, z0, z1], "normal": [nx, ny, nz, min_dot]},     # optional face filter
      "expect_faces": 62, "expect_tris": 216}]}                                         # guards (optional)
  select keys (all given keys must match an island): islands (ids), src, part (exact or "Prefix*"), piece (str or
  list), index. "where" keeps only faces whose centre is in the box and / or whose normal . (nx, ny, nz) >= min_dot;
  without it whole islands go (the clean case: no open edges). A partial island leaves an open border: hide it with
  a detail object (a rim, a lip) and say so in the zone doc.

Round 2's deck_removals.json (5 deck pieces, 21 islands) is applied by rig_build.py when AirshipRig.blend is built;
it is NOT part of this registry (those faces are already gone from the rig). Its consequences, which apply here too:
  * SM_Airship keeps its UVs and its baked comic ink texture. Deleting faces is safe for the UVs, but the baked ink
    (ambient-occlusion 'spotted black' and contact lines) still shows where the deleted geometry touched the rest:
    round 2 had to re-bake it locally (hull_ink_drivable.py -> T_AirshipDrivable_ComicLines.png). Every round 3 edit
    needs the same local re-bake round the deleted faces (the lead's Unreal stage; list the edit ids there).
  * rig vertex i = source vertex kept_vertex_index()[i] only for the round 2 removals. Zone builds run on the
    unedited rig mesh and use deleted_mask() to treat the faces as absent; the edits are applied once, at the end
    (assembler / export), so the mapping detail_ship.Ship relies on never breaks during the zone work.
  * verify_import.py and rig_export.py know only deck_removals.json: the export stage must add these edits (counts in
    the assembler's report) before the Unreal import check can pass.
  * Physics: PA_Airship is separate and unchanged; an edit never changes collision.

  blender_capped.sh --python detail_base_edits.py -- --list            # resolve every entry, print the face counts
"""
import json, os, sys, glob
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.environ.get('DETAIL_BASE_EDITS_DIR') or os.path.join(HERE, 'base_edits')   # env: try edits from a scratch dir


def load_entries(which='all'):
    """which: 'all', 'none', or a comma list of zone file names ('z6,z7'). Returns [(file, edit dict)]"""
    if which in (None, '', 'none'):
        return []
    files = sorted(glob.glob(os.path.join(REGISTRY, 'z*.json')))
    if which != 'all':
        want = {w.strip().lower() for w in which.split(',')}
        files = [f for f in files if os.path.basename(f)[:-5].lower() in want]
    out = []
    for f in files:
        d = json.load(open(f))
        for e in d.get('edits', []):
            out.append((os.path.basename(f), dict(e, zone=d.get('zone'))))
    return out


def _island_ok(rec, iid, sel):
    if 'islands' in sel and iid not in sel['islands']:
        return False
    if 'src' in sel and rec['src'] != sel['src']:
        return False
    if 'part' in sel:
        p = sel['part']
        if p.endswith('*'):
            if not rec['part'].startswith(p[:-1]):
                return False
        elif rec['part'] != p:
            return False
    if 'piece' in sel:
        pc = sel['piece'] if isinstance(sel['piece'], list) else [sel['piece']]
        if rec.get('piece', '') not in pc:
            return False
    if 'index' in sel and rec.get('index') != sel['index']:
        return False
    return True


def edit_mask(ship, edit, cen=None, nrm=None):
    """bool per SM_Airship polygon: the faces this edit deletes"""
    sel = edit['select']
    ids = [i for i, r in ship.islands.items() if _island_ok(r, i, sel)]
    m = np.isin(ship.p_island, ids)
    w = edit.get('where')
    if w:
        me = ship.ob.data
        if cen is None:
            cen = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
            nrm = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
        if 'box' in w:
            x0, x1, y0, y1, z0, z1 = w['box']
            m &= (cen[:, 0] >= x0) & (cen[:, 0] <= x1) & (cen[:, 1] >= y0) & (cen[:, 1] <= y1) & \
                 (cen[:, 2] >= z0) & (cen[:, 2] <= z1)
        if 'normal' in w:
            nx, ny, nz, md = w['normal']
            m &= nrm @ np.array([nx, ny, nz], float) >= md
    return m


def deleted_mask(ship, which='all', report=None):
    """bool per SM_Airship polygon: deleted by any selected edit. report (dict): filled with per-edit counts and guard
    results; a guard mismatch (expect_faces / expect_tris) raises, so a stale entry never deletes the wrong faces"""
    me = ship.ob.data
    cen = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
    nrm = np.empty(len(me.polygons) * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
    tris = np.array([len(p) - 2 for p in ship.polys])
    allm = np.zeros(len(ship.polys), bool)
    for f, e in load_entries(which):
        m = edit_mask(ship, e, cen, nrm)
        nf, nt = int(m.sum()), int(tris[m].sum())
        ok = (e.get('expect_faces') in (None, nf)) and (e.get('expect_tris') in (None, nt))
        if report is not None:
            report[e['id']] = dict(file=f, zone=e.get('zone'), faces=nf, tris=nt, guard_ok=ok, why=e.get('why'))
        if not ok:
            raise RuntimeError('base edit %s (%s): selects %d faces / %d tris, expected %s / %s' %
                               (e['id'], f, nf, nt, e.get('expect_faces'), e.get('expect_tris')))
        allm |= m
    return allm


def edited_copy(bpy, ship_ob, mask, name='SM_Airship_Edited'):
    """a new object with SM_Airship's mesh minus the masked faces (and the vertices only they used); same parent,
    modifiers (armature), vertex groups, UVs and materials. The original object is left as it is."""
    import bmesh
    me = ship_ob.data.copy()
    me.name = name
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    kill = [bm.faces[i] for i in np.nonzero(mask)[0].tolist()]
    bmesh.ops.delete(bm, geom=kill, context='FACES_ONLY')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    loose_e = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    for c in ship_ob.users_collection:
        c.objects.link(ob)
    ob.parent = ship_ob.parent
    ob.matrix_parent_inverse = ship_ob.matrix_parent_inverse.copy()
    ob.matrix_world = ship_ob.matrix_world.copy()
    for md in ship_ob.modifiers:
        if md.type == 'ARMATURE':
            n = ob.modifiers.new(md.name, 'ARMATURE')
            n.object = md.object
            n.use_vertex_groups = md.use_vertex_groups
            n.use_bone_envelopes = md.use_bone_envelopes
    for g in ship_ob.vertex_groups:
        if g.name not in ob.vertex_groups:
            ob.vertex_groups.new(name=g.name)
    return ob


def open_border_edges(bpy, ob):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if e.is_boundary)
    bm.free()
    return n


if __name__ == '__main__':
    import bpy
    sys.path.insert(0, HERE)
    import rig_common as C
    import detail_ship as S
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    which = a[a.index('--which') + 1] if '--which' in a else 'all'
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    rep = {}
    m = deleted_mask(ship, which, rep)
    ob = edited_copy(bpy, ship.ob, m)
    print('[base_edits] entries', json.dumps(rep, indent=1))
    print('[base_edits] faces deleted', int(m.sum()), 'of', len(m), '; open border edges before / after',
          open_border_edges(bpy, ship.ob), open_border_edges(bpy, ob))
    sys.stdout.flush()
    os._exit(0)
