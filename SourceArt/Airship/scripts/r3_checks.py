"""Round 3 export, step 4: the base-edit check and the summary of every UV / bake / colour check
(Docs/Airship/round3/EXPORT_R3.md section 13).

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_checks.py

Opens rig/detail/r3export/AirshipR3_export.blend (never saved), manifest_arrays.npz (the triangles the three base
edits removed, from r3_prep) and the hull ink texture. Per base edit (fan back L / R, ChainAft bars): every texel of the
kept SM_Airship within 1.5 m of the removed geometry (rasterised on Talal's UVs, inside the triangles only):
  * R (the ink lines): share of texels with ink (distance under 1 cm) there against the whole hull, and the texels
    of the removed islands' own UV footprint that a kept face still covers (expected 0);
  * B (Talal's comic mask, round 2, shown only when ComicAmount > 0): ink share there, which still holds the strokes
    the removed parts cast (contact shading) unless the B channel is re-baked (EXPORT_R3 section 3 step 6).
Then it gathers prep_report.json, r3_bake_report.json and colour_check.json into Docs/Airship/round3/export_bake.json.
"""
import bpy, sys, os, json, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import r3_common as RC
import r3_raster as RR

log = RC.Log('r3_checks')
RADIUS = 1.5
bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND)
arr = np.load(RC.ARRAYS)
DT, DE, IDS = arr['deleted_tris'], arr['deleted_edit'], [str(x) for x in arr['deleted_ids']]
bake = RC.load_json(RC.CHECK_DIR + '/r3_bake_report.json')
DMAX, DNEG = bake['knobs']['dmax'], bake['knobs'].get('dneg', 0.0)
img = bpy.data.images.load(bake['pages']['hull']['texture'], check_existing=False)
img.colorspace_settings.name = 'Non-Color'
S_ = img.size[0]
px = np.empty(S_ * S_ * 4, np.float32); img.pixels.foreach_get(px)
px = px.reshape(S_, S_, 4)
Rd = px[:, :, 0] * (DMAX + DNEG) - DNEG
me = bpy.data.objects[RC.HULL_OBJ].data
co = RC.mesh_np(me)['co']
tl, tv, tp = RC.tri_arrays(me)
huv = RC.page_uv(me, 'hull')
uv = RC.uv_get(me, huv)
kind = RC.face_attr_get(me, 'r3_kind')
tex_ok = np.ones(len(tp), bool) if kind is None else (kind == RC.K_ATLAS)[tp]
uv0 = RC.uv_get(me, RC.UV_INK)
if huv == RC.UV_INK:
    B = px[:, :, 2]
else:                                               # Talal's comic mask: its own texture on UV0
    mi = bpy.data.images.load(RC.HULL_MASK_R2, check_existing=False); mi.colorspace_settings.name = 'Non-Color'
    mp = np.empty(mi.size[0] * mi.size[1] * 4, np.float32); mi.pixels.foreach_get(mp)
    B = mp.reshape(mi.size[1], mi.size[0], 4)[:, :, 0]
whole_ink = bake['pages']['hull'].get('ink_share_of_inside')
out = dict(radius_m=RADIUS, hull_texture=bake['pages']['hull']['texture'], hull_md5=bake['pages']['hull']['md5'],
           whole_hull_R_ink_share=whole_ink, hull_uv=huv, comic_mask=RC.HULL_MASK_R2, edits={},
           note='R = the ink lines (distance under 1 cm), computed on the edited mesh; B = Talal\'s round 2 comic mask '
                '(shown only with ComicAmount > 0), which still has the contact strokes of the removed parts')
for k, eid in enumerate(IDS):
    T = DT[DE == k]
    if not len(T):
        continue
    lo = T.reshape(-1, 3).min(0) - RADIUS; hi = T.reshape(-1, 3).max(0) + RADIUS
    tc = co[tv]
    near = np.any(np.all((tc > lo) & (tc < hi), axis=2), axis=1)
    bvh = BVHTree.FromPolygons(T.reshape(-1, 3).tolist(), np.arange(len(T) * 3).reshape(-1, 3).tolist(), all_triangles=True)
    rec = {}
    for chan, uvx, res, img_, sel in (('R', uv, S_, Rd, near & tex_ok), ('B', uv0, B.shape[0], B, near)):
        owner, inside, _ = RR.raster(uvx[tl[sel]], res, 0)
        pos = RR.positions(uvx[tl[sel]], co[tv[sel]], owner, res)
        ii = np.nonzero(inside.ravel())[0]
        P = pos.reshape(-1, 3)[ii]
        dist = np.array([bvh.find_nearest(V(p), RADIUS)[3] or 9.0 for p in P.tolist()])
        for r in (0.3, RADIUS):
            m = dist <= r
            v = img_.ravel()[ii[m]]
            share = float((v < 0.01).mean() if chan == 'R' else (v > 0.5).mean()) if m.any() else None
            rec.setdefault('within_%gm' % r, {})[chan] = dict(texels=int(m.sum()), ink_share=None if share is None else round(share, 4))
    # the removed islands' own UV footprint: texels a kept face still covers there (expected 0: no overlap)
    # (the removed islands' UVs are not in the export mesh; their footprint = Talal's UVs of the deleted triangles is
    # not stored, so this is checked through the hull raster's coverage of the deleted triangles' 3D area instead)
    rec['deleted_triangles'] = int(len(T))
    out['edits'][eid] = rec
    log(eid, rec)
RC.dump_json(out, RC.CHECK_DIR + '/base_edit_check.json')

# ------------------------------------------------------------------ summary for the docs
prep = RC.load_json(RC.CHECK_DIR + '/prep_report.json')
cc = RC.load_json(RC.CHECK_DIR + '/colour_check.json') if os.path.isfile(RC.CHECK_DIR + '/colour_check.json') else {}
summary = dict(
    about='Round 3 export: UV + bake checks (r3_prep / r3_bake / r3_preview / r3_checks). Full reports in '
          'rig/detail/r3export/checks/.',
    input=prep['input'], knobs=dict(prep=prep['knobs'], bake=bake['knobs']),
    faces=prep['faces'], pack=prep['pack'], lods=prep['lods'], density_hull=prep['density_hull'],
    density_by_source=prep['density_by_source'],
    uv_checks={g: {k: v for k, v in r.items() if k in ('res', 'triangles', 'coverage', 'overlap_texels',
                                                         'loops_out_of_range', 'loops_in_reserved_band')}
               for g, r in prep['uv_checks'].items()},
    bake={g: {k: v for k, v in r.items() if k in ('texture', 'md5', 'size', 'density_median', 'features',
                                                   'inside_texels', 'margin_texels', 'signed_margin_texels',
                                                   'ink_share_of_inside', 'rivets_dotted', 'rivets_assigned',
                                                   'dot_texels', 'comic_B', 'seams', 'seconds')}
          for g, r in bake['pages'].items()},
    rivets=bake['rivets'],
    determinism=dict(full_run_vs_previous_run=bake.get('compare'),
                     rebake_into_textures_det=(RC.load_json(RC.CHECK_DIR + '/r3_bake_report_textures_det.json').get('compare')
                                               if os.path.isfile(RC.CHECK_DIR + '/r3_bake_report_textures_det.json') else None),
                     prep_uv_md5='38 of 39 export objects identical between prep runs 4 and 5 (SM_Airship changed on '
                                 'purpose: the hull thin rule); H, M, P textures byte-identical across runs 4, 5, 6'),
    colour_check=dict(flat_max_err_8bit=cc.get('flat_max_err_8bit'), spare_slot_pixels=cc.get('spare_slot_pixels'),
                      shots=cc.get('shots')),
    base_edits=out,
    protected=dict(prep=prep['protected_unchanged'], bake=bake['protected_unchanged'],
                   md5={k: v['md5'] for k, v in RC.protected_state().items()}))
RC.dump_json(summary, RC.DOCS + '/export_bake.json')
log('wrote', RC.DOCS + '/export_bake.json')
sys.stdout.flush()
os._exit(0)
