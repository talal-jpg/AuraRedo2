"""Zone 4: list where Z4 detail vertices sit on a seam or inside the 10 cm margin of another zone (the ownership check
counts them; this says where and on which material), so ZONE_4.md can explain each one.

  blender_capped.sh --python detail_z4_seams.py -- [--blend FILE] [--out FILE]

Read only: opens the zone 4 file and never saves it.
"""
import bpy, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_zones as Z


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def main():
    o = opts()
    blend = o.get('blend', D.zone_blend(4))
    out = o.get('out', '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/z4_seams.json')
    bpy.ops.wm.open_mainfile(filepath=blend)
    ship = S.Ship(bpy)
    zi = Z.ZoneIndex(ship)
    rep = {}
    for ob in [o_ for o_ in bpy.data.objects if o_.name.startswith('SM_AirshipDetail_Z4_') and o_.type == 'MESH']:
        me = ob.data
        mw = ob.matrix_world
        vrole = {}
        for p in me.polygons:
            m = ob.material_slots[p.material_index].material if p.material_index < len(ob.material_slots) else None
            for vi in p.vertices:
                vrole[vi] = (m.get('role') if m else None) or (m.name if m else '?')
        hits = []
        for vi_ in range(0, len(me.vertices), 2):
            v = me.vertices[vi_]
            p = mw @ v.co
            q = np.array(p)
            if Z.volume_owner(q) is None and 'Z4' in zi.zones_within(q, Z.MARGIN + 0.2):
                own = zi.zone_at(q)
                if own != 'Z4':
                    hits.append(('on_seam', own, vrole.get(v.index, '?'), [round(float(c), 2) for c in q]))
                    continue
            for oz in zi.near_other(q, 'Z4', Z.MARGIN):
                hits.append(('within_margin', oz, vrole.get(v.index, '?'), [round(float(c), 2) for c in q]))
        groups = {}
        for kind, zz, role, pos in hits:
            key = '%s %s %s' % (kind, zz, role)
            g = groups.setdefault(key, dict(n=0, x=[99, -99], examples=[]))
            g['n'] += 1
            g['x'] = [min(g['x'][0], pos[0]), max(g['x'][1], pos[0])]
            if len(g['examples']) < 4:
                g['examples'].append(pos)
        rep[ob.name] = groups
    C.dump_json(rep, out)
    print('[z4seams]', json.dumps(rep)[:4000])


main()
