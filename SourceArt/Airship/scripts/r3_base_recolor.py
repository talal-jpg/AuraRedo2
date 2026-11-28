"""Round 3 base colour overrides for SM_Airship: the single place they are defined and applied (2026-11-28).

Talal's answer of 2026-11-28 made the base model's grey keel block rust. SM_Airship is Talal's mesh with one material
(M_Airship); its faces get their colour from a palette class per face (detail_render.ship_face_classes for the toon
previews, EXPORT_R3.md section 2.1 for the game: palette index per face). An override changes that class for chosen
faces; it never changes geometry, UVs, material slots or Talal's files.

Registry (like base_edits/): scripts/base_recolor/zN.json, one per zone, never this module:
  {"zone": "Z4", "about": "...",
   "recolors": [
     {"id": "z4_keel_block_rust", "why": "...",
      "select": {"islands": [1147, 1148, 1149], "src": "Underside_Front"},   # detail_base_edits select keys
      "slot": "keel_block",            # palette slot the faces get (EXPORT_R3.md section 2.1: slot 16)
      "colour_key": "rust_red",        # its default colour: a detail_common.PALETTE key
      "expect_faces": 8381, "expect_tris": 8998}]}                          # guards: a stale entry raises
Select keys and guards work like detail_base_edits (whole islands, research island ids of sm_airship_islands.json).

Who applies it:
  * detail_render.py (toon / paper looks): the 'after' state draws the overridden faces with the slot's colour; the
    'before' state keeps the old classes (the ship as it is).
  * detail_assemble.py: writes the override into the full file's SM_Airship as the FACE integer attribute
    'r3_recolor' (0 = none, k = entry k of the list below, 1-based) and the custom property
    SM_Airship['round3_base_recolor'] (JSON list: id, slot, colour_key, value, faces, tris, islands), after the base
    edits are applied (the face indices are those of the edited mesh).
  * the round 3 bake / prep (r3_prep.py, r3_bake.py, EXPORT_R3.md): palette slot per SM_Airship face =
    face_slots(...) on the rig (or read_from_object(...) on the full file), else the part class.

  blender_capped.sh --python r3_base_recolor.py -- --list        # resolve every entry on the rig, print the counts
"""
import json, os, sys, glob
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.environ.get('R3_BASE_RECOLOR_DIR') or os.path.join(HERE, 'base_recolor')
ATTR = 'r3_recolor'
PROP = 'round3_base_recolor'


def load_entries(which='all'):
    """which: 'all', 'none', or a comma list of zone file names ('z4'). Returns [(file, entry dict)]"""
    if which in (None, '', 'none'):
        return []
    files = sorted(glob.glob(os.path.join(REGISTRY, 'z*.json')))
    if which != 'all':
        want = {w.strip().lower() for w in which.split(',')}
        files = [f for f in files if os.path.basename(f)[:-5].lower() in want]
    out = []
    for f in files:
        d = json.load(open(f))
        for e in d.get('recolors', []):
            out.append((os.path.basename(f), dict(e, zone=d.get('zone'))))
    return out


def entry_mask(ship, e):
    """bool per SM_Airship polygon (rig mesh, detail_ship.Ship): the faces this entry recolours"""
    import detail_base_edits as BE
    return BE.edit_mask(ship, e)


def face_slots(ship, which='all', report=None, deleted=None):
    """palette slot per SM_Airship polygon of the rig mesh (None = no override). report (dict): per entry counts and
    guard results; a guard mismatch raises. deleted (bool per polygon, optional): the base edits' faces; an override
    on a deleted face is reported (it would vanish with the face)"""
    tris = np.array([len(p) - 2 for p in ship.polys])
    slots = np.array([None] * len(ship.polys), dtype=object)
    for f, e in load_entries(which):
        m = entry_mask(ship, e)
        nf, nt = int(m.sum()), int(tris[m].sum())
        ok = (e.get('expect_faces') in (None, nf)) and (e.get('expect_tris') in (None, nt))
        if report is not None:
            rec = dict(file=f, zone=e.get('zone'), slot=e['slot'], colour_key=e.get('colour_key'), faces=nf, tris=nt,
                       guard_ok=ok, why=e.get('why'),
                       overlaps_earlier_entry=int(sum(1 for s in slots[m] if s is not None)))
            if deleted is not None:
                rec['on_deleted_faces'] = int((m & deleted).sum())
            report[e['id']] = rec
        if not ok:
            raise RuntimeError('base recolour %s (%s): selects %d faces / %d tris, expected %s / %s' %
                               (e['id'], f, nf, nt, e.get('expect_faces'), e.get('expect_tris')))
        slots[m] = e['slot']
    return slots


def slot_colours(which='all'):
    """{slot: colour_key} of the registered overrides (the slot's default colour)"""
    return {e['slot']: e.get('colour_key') for _, e in load_entries(which)}


def apply_to_object(ob, slots_kept, report):
    """write the overrides into a mesh object (the full file's SM_Airship after the base edits): FACE INT attribute
    ATTR and the JSON custom property PROP. slots_kept: slot per polygon of ob (None = no override)"""
    me = ob.data
    assert len(slots_kept) == len(me.polygons), (len(slots_kept), len(me.polygons))
    entries = []
    val = np.zeros(len(me.polygons), np.int32)
    tri = np.array([len(p.vertices) - 2 for p in me.polygons])
    for k, (f, e) in enumerate(load_entries('all')):
        m = np.array([s == e['slot'] for s in slots_kept])
        val[m] = k + 1
        entries.append(dict(id=e['id'], value=k + 1, slot=e['slot'], colour_key=e.get('colour_key'),
                            faces=int(m.sum()), tris=int(tri[m].sum()), select=e.get('select'), file=f))
    a = me.attributes.get(ATTR)
    if a is not None:
        me.attributes.remove(a)
    a = me.attributes.new(ATTR, 'INT', 'FACE')
    a.data.foreach_set('value', val)
    ob[PROP] = json.dumps(entries)
    return dict(attribute=ATTR, property=PROP, entries=entries, faces_overridden=int((val > 0).sum()))


def read_from_object(ob):
    """slot per polygon of a mesh object that carries the attribute (None = no override), and the entry list"""
    me = ob.data
    a = me.attributes.get(ATTR)
    entries = json.loads(ob.get(PROP, '[]'))
    if a is None:
        return np.array([None] * len(me.polygons), dtype=object), entries
    val = np.zeros(len(me.polygons), np.int32)
    a.data.foreach_get('value', val)
    by = {e['value']: e['slot'] for e in entries}
    return np.array([by.get(int(v)) for v in val], dtype=object), entries


if __name__ == '__main__':
    import bpy
    sys.path.insert(0, HERE)
    import rig_common as C
    import detail_ship as S
    import detail_base_edits as BE
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    deleted = BE.deleted_mask(ship, 'all')
    rep = {}
    sl = face_slots(ship, 'all', rep, deleted)
    print('[base_recolor] entries', json.dumps(rep, indent=1))
    print('[base_recolor] faces overridden', int(sum(1 for s in sl if s is not None)), 'of', len(sl))
    sys.stdout.flush()
    os._exit(0)
