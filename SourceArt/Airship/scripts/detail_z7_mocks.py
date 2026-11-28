"""Zone 7: quick placement mocks of the stairs (simple boxes), one tmp .blend per option, for the option renders.

  blender_capped.sh --python detail_z7_mocks.py -- [--options central,port,across]

Opens rig/AirshipRig.blend read only, measures the main deck and the platform top, writes
rig/tmp/z7_mock_<option>.blend (collection Detail_Z7, object SM_AirshipDetail_Z7_Stairs) and prints the survey numbers.
"""
import bpy, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_z7_stairs as ST


def top_z(bvh, x, y, z_from=12.0):
    h = bvh.ray_cast(V((x, y, z_from)), V((0, 0, -1)), 20.0)
    return None if h[0] is None else round(h[0][2], 4)


def main():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    opts = a[a.index('--options') + 1].split(',') if '--options' in a else ['central', 'port', 'across']
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    noprops = ship.p_src != 'DeckProps'
    bvh = ship.bvh(noprops)
    surv = {}
    for x in (2.5, 3.5, 4.0, 5.0, 7.0, 8.5, 9.5, 10.3, 10.45):
        surv['deck_x%.2f' % x] = [top_z(bvh, x, y, 5.0) for y in (-3.0, -1.5, 0.0, 0.63, 1.5, 3.0, 4.0)]
    for x in (10.55, 10.7, 11.5, 13.0):
        surv['plat_x%.2f' % x] = [top_z(bvh, x, y) for y in (-2.0, 0.0, 0.63, 2.0)]
    print('[mock] survey', json.dumps(surv))
    z_deck = top_z(bvh, 3.6, 0.63, 5.0)
    z_top = top_z(bvh, 10.8, 0.63)
    print('[mock] z_deck', z_deck, 'z_top', z_top)
    mats = D.ensure_materials()
    keep = set(bpy.data.objects)
    for opt in opts:
        for o in [o for o in bpy.data.objects if o not in keep]:
            bpy.data.objects.remove(o)
        zd = top_z(bvh, *({'central': (3.6, 0.63), 'port': (2.3, 3.97), 'across': (9.6, 3.9)}[opt]), 5.0)
        P = ST.plan(opt, zd, z_top)
        print('[mock]', opt, json.dumps(ST.usability(P)), json.dumps(P['flights']), json.dumps(P['landings']))
        m = D.Mesh('mock')
        m.cur_group = 'Hull'
        ST.build_mock(m, P)
        m.orient_outward()
        coll = bpy.data.collections.get('Detail_Z7') or bpy.data.collections.new('Detail_Z7')
        if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
            bpy.context.scene.collection.children.link(coll)
        m.to_object('SM_AirshipDetail_Z7_Stairs', coll, mats, arm=ship.arm, groups='Hull')
        print('[mock] saved', D.safe_save(D.TMP_DIR + '/z7_mock_%s.blend' % opt))
    sys.stdout.flush()
    os._exit(0)


if __name__ == '__main__':
    main()
