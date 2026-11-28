"""Zone 2 cross-zone check: the Detail_Z2 objects at rest against every other done zone's detail objects (no shared
triangles, smallest distance) and against the two front turrets' reach (keep-clear volumes). Read only.

  blender_capped.sh --python detail_z2_xcheck.py -- [--zones 1,6,7] [--out Docs/Airship/round3/z2_xcheck.json]
"""
import bpy, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_zones as Z
import detail_checks as CK


def bvh_of(ob):
    co = CK.world_co(ob)
    return BVHTree.FromPolygons(co.tolist(), [list(p.vertices) for p in ob.data.polygons]), co


def main():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    zones = [z for z in g('--zones', '1,3,4,5,6,7').split(',') if z]
    out = g('--out', '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/z2_xcheck.json')
    bpy.ops.wm.open_mainfile(filepath=D.zone_blend(2))
    loaded, missing = [], []
    for z in zones:
        (loaded if D.append_zone(z) is not None else missing).append(z)
    mine = D.detail_objects(['Detail_Z2'])
    others = [o for o in D.detail_objects() if o not in mine]
    rep = dict(zones_loaded=loaded, zones_missing=missing, pairs={})
    mb = {o.name: bvh_of(o) for o in mine}
    for ob in others:
        ob_b, ob_co = bvh_of(ob)
        for n, (b, co) in mb.items():
            ov = len(b.overlap(ob_b))
            # smallest distance: my vertices to the other object (every 3rd vertex), capped at 1 m
            dmin = 9.0
            for p in co[::3]:
                r = ob_b.find_nearest(V(p), 1.0)
                if r[0] is not None:
                    dmin = min(dmin, r[3])
            if ov or dmin < 1.0:
                rep['pairs']['%s | %s' % (n, ob.name)] = dict(overlap_tri_pairs=ov, min_dist_m=round(dmin, 3))
    allco = np.concatenate([CK.world_co(o) for o in mine])
    rep['keep_clear_hits'] = Z.keep_clear_hits(allco)
    rep['overlaps_total'] = sum(v['overlap_tri_pairs'] for v in rep['pairs'].values())
    rep['RESULT'] = 'PASS' if rep['overlaps_total'] == 0 and not rep['keep_clear_hits'] else 'FAIL'
    C.dump_json(rep, out)
    print('[xcheck]', json.dumps(rep))
    sys.stdout.flush()
    os._exit(0)


if __name__ == '__main__':
    main()
