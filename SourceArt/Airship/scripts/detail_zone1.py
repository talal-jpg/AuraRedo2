"""Zone 1 of the airship detail pass (round 3, 2026-11-28): a style and density sample for Talal.

Zone 1 = the PORT hull flank between the aft and the forward cannon stations (x -11.47 .. -0.46), from the deck edge
down to the turn of the bilge, carried on forward over the front-left pod's hull pocket (plates end at the pocket's fore
rim strap, x ~6.9), plus the front-left thruster pod Thruster_FL (pod, nozzle, the 12 petals) and the cavity of its hull
pocket.

  blender -b --factory-startup --python detail_zone1.py [-- --no-save]

Opens rig/AirshipRig.blend (never saved), adds the zone's detail objects to collection Detail_Z1 and saves the copy
rig/detail/zones/AirshipRig_detail_z1.blend (D.safe_save). Since 2026-11-28 nothing writes rig/detail/AirshipRig_detail.blend
(the approved pass 2 file, read only). SM_Airship (Talal's mesh), its UVs and the props are untouched.

Objects (all parented to the Armature, Armature modifier, every vertex 100 % on one bone):
  SM_AirshipDetail_Z1_Hull            -> Hull
  SM_AirshipDetail_Z1_Pod_FL          -> Thruster_FL
  SM_AirshipDetail_Z1_Nozzle_FL       -> Thruster_FL_Nozzle
  SM_AirshipDetail_Z1_Petals_FL       -> Thruster_FL_Petal00 .. 11 (one vertex group per petal)
Report: rig/detail/zones/z1_report.json (parameters, triangles per object / kind, checks, extrapolation).

Pass 2 (after review): colour by role, three depth levels (base plates 4.5 cm, layers / ribs / teeth 10-13 cm,
machinery bays and pipe channel 18-20 cm), picture-frame and slotted plates, a riveted strake with big rectangular teeth on
a dark backing, a pipe channel with two big pipes, machinery bays with housings / pump / bottle, conduits ending in
glands, low domed rivets only on straps / ribs / corners, floating-piece check. No round grilles, louvre boxes, exhaust
stubs, cable loops, chain or junction boxes on the flank any more.
"""
import bpy, sys, os, math, random, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S

DETAIL_DIR = D.ZONES_DIR                   # since 2026-11-28: never rig/detail/AirshipRig_detail.blend (approved, read only)
OUT_BLEND = D.zone_blend(1)                # rig/detail/zones/AirshipRig_detail_z1.blend
REPORT = DETAIL_DIR + '/z1_report.json'
CONTINUITY = DETAIL_DIR + '/z1_continuity.json'     # copied to Docs/Airship/round3/z1_continuity.json
COLL = 'Detail_Z1'
PREFIX = 'SM_AirshipDetail_Z1_'
YELLOWS = (('paint_yellow', 0.5), ('paint_ochre', 0.5))

# ------------------------------------------------------------------ knobs (all metres / degrees)
K = dict(
    seed=1301,
    x_aft=-11.55, x_fwd=8.6,                 # aft cannon station .. forward end of the FL pocket
    x_fwd_plates=6.95,                       # plates end at the pocket's fore rim strap (a clean zone edge)
    chart_x=(-12.0, 9.0, 0.05), chart_phi=(30.0, -80.0, -0.5), chart_clear=0.30,
    bilge_phi=-56.0,                         # lower limit of the zone (turn of the bilge) as a chart angle
    touch_tol=0.02,                          # every loose piece touches the ship or another piece within this
    step_tol=0.012,                          # a plate whose skin patch departs from a smooth fit by more is skipped
    plate=dict(gap=0.015, t=0.045, bevel=0.014, cell_u=0.6, cell_v=0.25, cut=(0.07, 0.17), cut_p=0.3),
    layer=0.006,                             # clearance between stacked layers
    seam=0.024,
    rivet=dict(r=0.022, h=0.012, inset=0.07, spacing=0.28),
    upper=dict(w=(0.8, 1.7), row_h=(0.55, 0.95), top_off=0.27, min_w=0.35, min_h=0.22, keep=0.25, mats=YELLOWS),
    lower=dict(w=(0.8, 1.6), row_h=(0.7, 1.1), top_off=0.04, min_w=0.35, min_h=0.22, keep=0.25, mats=YELLOWS),
    fill=dict(w=(0.35, 0.8), h=(0.3, 0.6), min_w=0.3, min_h=0.24, mats=YELLOWS),
    shingle=dict(p=0.3, overlap=0.08, t=0.04, armour=0.5),
    frame=dict(p=0.65, rim=0.075, t=0.035, inset_p=0.0, min_w=0.6, min_h=0.45, edge=0.09),
    patch=dict(p=0.7, t=0.04, w=(0.4, 0.8), h=(0.3, 0.55), mats=(('rust_red', 0.7), ('paint_ochre', 0.3))),
    batten=dict(p=0.75, w=0.12, t=0.05, mat='rust_red'),
    slots=dict(up=3, mid=2, w=(0.55, 0.8), h=(0.32, 0.45), n=(3, 4), slot_w=0.05, ang=58.0),
    strake=dict(h=0.2, t=0.085, back_h=0.6, back_t=0.02, smooth=0.9),
    teeth=dict(w=(0.7, 0.9), h=(0.62, 0.78), gap=(0.14, 0.2), t=0.09, chamfer=0.07),
    channel=dict(v=(1.02, 1.52), r=(0.07, 0.058), clamp_step=1.0),
    bay=dict(v=(1.62, 2.78), w=(2.1, 1.6), rim=0.1, rim_t=0.05, depth=0.11, pump_r=0.068),
    ubay=dict(v=(0.1, 0.86), w=(1.8, 1.6), x_pref=(-7.4, -2.3), rim=0.08, depth=0.1),
    conduit=dict(r_up=(0.03, 0.026), clamp_step=0.7, fittings=3, smooth=0.75),
    gusset=dict(step=0.51, depth=0.10, height=0.22, t=0.025),
    pocket=dict(r=2.85, rim_w=(0.03, 0.19), rim_t=0.05, cavity_bottom_h=-1.84, roof_h=-2.8, cols=(-0.5, 9.5)),
    pod=dict(gap=0.012, t=0.035, bevel=0.01, rib_rivet_step=20.0, hull_clear=0.05, bundle_r=0.05, hug_r=(0.06, 0.05),
             act_r=2.04, hoops=(3.25, 3.6), mats=(('rust_red', 0.45), ('rust_dark', 0.35), ('dark_metal', 0.2))),
    pa_boxes='/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/pa_hull_boxes.json',
)


from detail_flank import Flank, build_flank
from detail_pod import pocket_rim, cavity, build_pod
from detail_checks import dist_report, pod_frame_coords, silhouette_table, envelope_report, vertex_kinds, pa_report


# ================================================================== main
def main(save=True):
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    log = {}
    fl = Flank(ship, K)
    log['chart_s'] = round(time.time() - t0, 1)
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    pod = D.Mesh('pod'); pod.cur_group = 'Thruster_FL'
    noz = D.Mesh('noz'); noz.cur_group = 'Thruster_FL_Nozzle'
    pet = D.Mesh('pet'); pet.cur_group = None
    rim_pts = pocket_rim(hull, fl, ship, K, random.Random(K['seed'] + 2), log)
    build_flank(hull, fl, ship, K, random.Random(K['seed'] + 1), log, rim_pts)
    cavity(hull, ship, fl, K, random.Random(K['seed'] + 3), log)
    build_pod(pod, noz, pet, ship, K, random.Random(K['seed'] + 4), log, skin=fl.skin)
    # every loose piece must touch the ship or another piece within 2 cm (repeat: removing one can strand another)
    ship_bvh = ship.bvh(np.ones(len(ship.polys), bool))
    dropped = {}
    for name, m in (('hull', hull), ('pod', pod), ('noz', noz), ('pet', pet)):
        for _ in range(3):
            d = D.drop_floating(m, [ship_bvh], tol=K['touch_tol'])
            if not d:
                break
            for k_, v_ in d.items():
                dropped.setdefault(name, {})[k_] = dropped.get(name, {}).get(k_, 0) + v_
    log['floating_pieces_removed'] = dropped
    log['build_s'] = round(time.time() - t0, 1)
    # the lines and runs the neighbouring zones continue (Z2 mirrors them, Z3 / Z4 / Z5 start from them)
    cont = log.pop('continuity')
    cont['pocket_rim_points'] = len(rim_pts)
    C.dump_json(cont, CONTINUITY)

    # ---- objects
    coll = bpy.data.collections.get(COLL) or bpy.data.collections.new(COLL)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    arm = ship.arm
    objs = {}
    for m, name, bone in ((hull, 'Hull', 'Hull'), (pod, 'Pod_FL', 'Thruster_FL'), (noz, 'Nozzle_FL', 'Thruster_FL_Nozzle'),
                          (pet, 'Petals_FL', None)):
        groups = bone if bone else list(m.g)
        ob = m.to_object(PREFIX + name, coll, mats, arm=arm, groups=groups)
        objs[name] = ob
    # ---- checks
    pod_mask = np.char.startswith(ship.p_bone.astype(str), 'Thruster_FL')
    pod_surf = ship.surface(pod_mask)
    O, T0, A, NP = ship.pod_frame('FL')
    e0, e90 = S.pod_basis(A)
    R = K['pocket']['r']
    hv = np.array(hull.v)
    h_, th_, r_ = pod_frame_coords(hv, T0, A, e0, e90)
    in_cav = (r_ < R + 0.1) & (h_ > K['pocket']['roof_h'] - 0.1) & (h_ < 1.3)
    pod_co = ship.co[np.char.startswith(ship.v_bone.astype(str), 'Thruster_FL')]
    pv = np.array(pod.v)
    sil = silhouette_table(pod_surf.bvh, T0, A, e0, e90, pod_co=pod_co)
    checks = dict(
        hull_flank_vs_skin=dist_report(hv[~in_cav], fl.skin, 'hull details outside the FL pocket vs hull skin', 0.20,
                                       vkind=[k_ for k_, c_ in zip(vertex_kinds(hull), ~in_cav) if c_]),
        hull_cavity_vs_skin=dist_report(hv[in_cav], fl.skin, 'FL pocket cavity details vs hull skin (inside the cavity, no silhouette)', 0.20),
        pod_vs_pod=dist_report(pv, pod_surf, 'pod details vs pod surface', 0.15, vkind=vertex_kinds(pod)),
        nozzle_vs_pod=dist_report(noz.v, pod_surf, 'nozzle details vs pod surface', 0.15),
        petals_vs_pod=dist_report(pet.v, pod_surf, 'petal details vs pod surface', 0.15),
        pod_envelope=envelope_report(pv, pod_surf.bvh, T0, A, e0, e90, 'pod details outside the pod radial envelope',
                                     sil=sil, vkind=vertex_kinds(pod)),
        nozzle_envelope=envelope_report(noz.v, pod_surf.bvh, T0, A, e0, e90, 'nozzle details outside the pod radial envelope',
                                        sil=sil, vkind=vertex_kinds(noz)),
        petal_envelope=envelope_report(pet.v, pod_surf.bvh, T0, A, e0, e90, 'petal details outside the pod radial envelope',
                                       sil=sil, vkind=vertex_kinds(pet)),
        pa_boxes=pa_report(np.concatenate([hv, pv]) if len(pv) else hv, K['pa_boxes']),
        hull_details_max_z=round(float(hv[:, 2].max()), 3) if len(hv) else None,
    )
    nm = {n: D.nonmanifold_edges(o) for n, o in objs.items()}
    tri = {n: sum(len(p.vertices) - 2 for p in o.data.polygons) for n, o in objs.items()}
    kinds = {}
    for m in (hull, pod, noz, pet):
        for k, v in m.tris_by_kind().items():
            kinds[k] = kinds.get(k, 0) + v
    bones = {n: sorted({g.name for g in o.vertex_groups}) for n, o in objs.items()}
    rep = dict(knobs=K, log=log, tris=tri, tris_total=sum(tri.values()), tris_by_kind=kinds, nonmanifold_edges=nm,
               bones=bones, checks=checks, ship_tris_before=sum(len(p.vertices) - 2 for p in ship.ob.data.polygons),
               seconds=round(time.time() - t0, 1))
    os.makedirs(DETAIL_DIR, exist_ok=True)
    C.dump_json(rep, REPORT)
    print('[zone1] tris', tri, 'total', rep['tris_total'])
    print('[zone1] kinds', kinds)
    print('[zone1] checks', json.dumps(checks))
    print('[zone1] log', json.dumps(log))
    print('[zone1] nonmanifold', nm)
    if save:
        D.safe_save(OUT_BLEND)
        print('[zone1] saved', OUT_BLEND)
    print('[zone1] done %.1f s' % (time.time() - t0))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    main(save='--no-save' not in argv)

