"""Self test of the shared detail modules on the parts zone 1 never built: the starboard flank (FlankChart side -1),
pods FR, RL, RR, the FR / RL pocket rims and cavities. Proves the mirrored / per-pod code paths before the zone agents
use them. Not a zone: nothing it builds is kept (a scratch .blend in rig/tmp for a look).

  blender_capped.sh --python detail_selftest.py -- [--out rig/tmp/detail_selftest.blend] [--report FILE.json]

Uses zone 1's knobs (detail_zone1.K) with other seeds. Writes a report (counts, per-object checklist, inside-out pieces
before orient_outward, starboard continuity lines) and saves collection Detail_ZT (objects SM_AirshipDetail_ZT_*).
"""
import bpy, sys, os, random, json, time, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_checks as CK
from detail_flank import Flank, build_flank
from detail_pod import pocket_rim, cavity, build_pod, pod_islands
import detail_zone1 as Z1


def main():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    out = g('--out', D.TMP_DIR + '/detail_selftest.blend')
    report = g('--report', D.TMP_DIR + '/detail_selftest.json')
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    K = copy.deepcopy(Z1.K)
    rep = dict(pod_islands={p: pod_islands(ship, p) for p in C.PODS})
    meshes = {}
    # ---- starboard flank (+ FR pocket rim and cavity), zone 1's knobs mirrored
    log_s = {}
    fl_s = Flank(ship, K, side=-1)
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    rim = pocket_rim(hull, fl_s, ship, K, random.Random(2302), log_s, pod='FR')
    build_flank(hull, fl_s, ship, K, random.Random(2301), log_s, rim)
    cavity(hull, ship, fl_s, K, random.Random(2303), log_s, pod='FR')
    cont = log_s.pop('continuity')
    rep['starboard_log'] = log_s
    rep['starboard_continuity_summary'] = {k: cont[k] for k in ('strake_runs', 'channel_spans', 'lower_bays', 'upper_bays')}
    C.dump_json(cont, D.TMP_DIR + '/selftest_stbd_continuity.json')
    # ---- RL pocket rim + cavity on the port chart (cols from the pod's x)
    log_p = {}
    Kp = copy.deepcopy(K); Kp['pocket'].pop('cols', None)
    fl_p = Flank(ship, Kp, side=1)
    rim_rl = pocket_rim(hull, fl_p, ship, Kp, random.Random(3302), log_p, pod='RL')
    cavity(hull, ship, fl_p, Kp, random.Random(3303), log_p, pod='RL')
    rep['rl_pocket_log'] = log_p
    meshes['Hull'] = (hull, 'Hull')
    # ---- the three other pods
    for i, p in enumerate(('FR', 'RL', 'RR')):
        lg = {}
        pod = D.Mesh('pod'); pod.cur_group = 'Thruster_' + p
        noz = D.Mesh('noz'); noz.cur_group = 'Thruster_%s_Nozzle' % p
        pet = D.Mesh('pet'); pet.cur_group = None
        build_pod(pod, noz, pet, ship, K, random.Random(4400 + i), lg, skin=fl_s.skin, which=p)
        rep['pod_log_' + p] = lg
        meshes['Pod_' + p] = (pod, 'Thruster_' + p)
        meshes['Nozzle_' + p] = (noz, 'Thruster_%s_Nozzle' % p)
        meshes['Petals_' + p] = (pet, None)
    ship_bvh = ship.bvh(np.ones(len(ship.polys), bool))
    rep['floating_removed'], rep['inside_out_flipped'] = {}, {}
    for name, (m, _) in meshes.items():
        for _ in range(3):
            d = D.drop_floating(m, [ship_bvh], tol=K['touch_tol'])
            if not d:
                break
            rep['floating_removed'][name] = d
        rep['inside_out_flipped'][name] = m.orient_outward()
    coll = bpy.data.collections.new('Detail_ZT')
    bpy.context.scene.collection.children.link(coll)
    objs = [m.to_object('SM_AirshipDetail_ZT_' + n, coll, mats, arm=ship.arm, groups=b if b else list(m.g))
            for n, (m, b) in meshes.items() if m.f]
    rep['objects'] = [CK.object_report(o, 'ZT') for o in objs]
    rep['tris'] = {o.name: int(sum(len(p.vertices) - 2 for p in o.data.polygons)) for o in objs}
    rep['seconds'] = round(time.time() - t0, 1)
    C.dump_json(rep, report)
    print('[selftest] pod islands', rep['pod_islands'])
    print('[selftest] tris', rep['tris'])
    print('[selftest] starboard', json.dumps(rep['starboard_continuity_summary']))
    print('[selftest] inside-out flipped', rep['inside_out_flipped'], 'floating removed', rep['floating_removed'])
    print('[selftest] objects', json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces', 'nonmanifold_edges',
                                                                 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[selftest] saved', D.safe_save(out), rep['seconds'], 's')
    sys.stdout.flush()


if __name__ == '__main__':
    main()
