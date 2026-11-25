"""Look check for hull_ink_drivable.py: the drivable rig (rig/AirshipRig.blend, the five deck pieces removed) rendered
with Talal's hull texture (before) and with T_AirshipDrivable_ComicLines.png (after), same views as round2_render.py.
Never saves the .blend.

  blender -b --factory-startup --python SourceArt/Airship/scripts/hull_ink_render.py
  python3 -B SourceArt/Airship/scripts/hull_ink_media.py        # -> Docs/Airship/round2/media/deck_ink_before_after.jpg

Workbench, studio light, the material's texture (M_Airship's ComicLines image node: Talal's PNG, then the new one),
hull + helm + cannons in the rest pose. Views: top (round2_render's TOP: bow down, port right), persp_fwd (round2_render
highlight's persp_fwd = media/removed_pieces_persp.jpg) and persp_aft (the aft quarter, for pieces 1 and 2).
Output rig/renders/hull_ink/{before,after}_<view>.png and hull_ink_render.json: per view the pixels that differ between
before and after (any channel > 2 / 255) and how many of them fall outside the screen boxes of the removed pieces
grown by the fix radius (1.5 m), which must be 0.
"""
import sys, os, json
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
from mathutils import Vector as V, Matrix
from bpy_extras.object_utils import world_to_camera_view
import rig_common as C

NEW = C.SOURCE_ART + '/textures/T_AirshipDrivable_ComicLines.png'
OUT = C.RIG + '/renders/hull_ink'
RADIUS = 1.5
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
sc = bpy.context.scene
ship = bpy.data.objects[C.HULL_OBJ]
arm = bpy.data.objects['Armature']
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
if arm.animation_data:
    arm.animation_data.action = None
show = [ship] + [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(C.PROP_PREFIX)]
for o in bpy.data.objects:
    o.hide_render = o not in show
    o.hide_viewport = False
for coll in bpy.data.collections:
    coll.hide_render = False

mat = ship.data.materials[0]
nt = mat.node_tree
node = nt.nodes['ComicLines']
old_img = node.image
assert old_img.name == 'T_Airship_ComicLines', old_img.name
new_img = bpy.data.images.load(NEW, check_existing=False)
new_img.colorspace_settings.name = old_img.colorspace_settings.name
assert tuple(new_img.size) == tuple(old_img.size), (new_img.size[:], old_img.size[:])
nt.nodes.active = node

sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.color_type = 'TEXTURE'
sh.show_object_outline = True
sh.object_outline_color = (0.05, 0.05, 0.08)
sh.show_cavity = False
sh.show_backface_culling = False
sc.display.render_aa = '8'
sc.render.film_transparent = False
sc.world = sc.world or bpy.data.worlds.new('W')
sc.world.color = (0.22, 0.23, 0.25)
sc.render.image_settings.file_format = 'PNG'
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = 'Standard'
cd = bpy.data.cameras.new('HICam')
cam = bpy.data.objects.new('HICam', cd)
sc.collection.objects.link(cam)
sc.camera = cam
cd.clip_start, cd.clip_end = 0.05, 400

VIEWS = {   # round2_render.py's framings
    'top': dict(loc=(6.5, 0.0, 80.0), at=(6.5, 0.0, 0.0), up=(-1, 0, 0), ortho=55.0, res=(760, 1400)),
    'persp_fwd': dict(loc=(-6.0, 9.0, 16.0), at=(12.0, 0.0, 5.0), lens=30, res=(1400, 900)),
    'persp_aft': dict(loc=(-24.0, 10.0, 13.0), at=(-4.0, 0.0, 2.5), lens=30, res=(1400, 900)),
}


def place(loc, at, up=(0, 0, 1), ortho=None, lens=40, res=(1400, 1000)):
    cam.location = V(loc)
    fwd = (V(at) - V(loc)).normalized()
    right = fwd.cross(V(up)).normalized()
    upv = right.cross(fwd).normalized()
    cam.rotation_euler = Matrix((right, upv, -fwd)).transposed().to_euler()
    cd.sensor_fit = 'AUTO'
    if ortho:
        cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else:
        cd.type = 'PERSP'; cd.lens = lens
    sc.render.resolution_x, sc.render.resolution_y = res
    bpy.context.view_layer.update()


def render(path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path, check_existing=False)
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(img.size[1], img.size[0], 4)[::-1, :, :3]          # top row first
    bpy.data.images.remove(img)
    return a


def piece_screen_boxes(res):
    """screen boxes (x0, y0, x1, y1, top row first) of each removed piece's box grown by RADIUS"""
    out = []
    for p in C.deck_removals()['pieces']:
        lo, hi = np.array(p['bbox_min']) - RADIUS, np.array(p['bbox_max']) + RADIUS
        pts = [world_to_camera_view(sc, cam, V((x, y, z))) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
               for z in (lo[2], hi[2])]
        xs = [q.x * res[0] for q in pts]
        ys = [(1.0 - q.y) * res[1] for q in pts]
        out.append([int(np.floor(min(xs))), int(np.floor(min(ys))), int(np.ceil(max(xs))), int(np.ceil(max(ys)))])
    return out


rep = {'new_texture': NEW, 'old_texture': old_img.filepath, 'views': {}}
for name, v in VIEWS.items():
    place(**v)
    node.image = old_img
    a = render(os.path.join(OUT, 'before_%s.png' % name))
    node.image = new_img
    b = render(os.path.join(OUT, 'after_%s.png' % name))
    diff = np.abs(a - b).max(axis=2) > 2.0 / 255.0
    boxes = piece_screen_boxes(v['res'])
    inside = np.zeros(diff.shape, bool)
    for x0, y0, x1, y1 in boxes:
        inside[max(0, y0):max(0, y1 + 1), max(0, x0):max(0, x1 + 1)] = True
    ys, xs = np.nonzero(diff)
    rep['views'][name] = dict(pixels=int(diff.size), changed=int(diff.sum()), changed_outside_piece_boxes=int((diff & ~inside).sum()),
                              changed_box=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                              piece_boxes=boxes)
    # diff picture: after in grey, changed pixels red, piece boxes outlined blue
    g = b.mean(axis=2, keepdims=True).repeat(3, axis=2) * 0.8
    g[diff] = (1.0, 0.1, 0.1)
    for x0, y0, x1, y1 in boxes:
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(diff.shape[1] - 1, x1), min(diff.shape[0] - 1, y1)
        if x1 > x0 and y1 > y0:
            g[y0, x0:x1] = g[y1, x0:x1] = (0.2, 0.4, 1.0)
            g[y0:y1, x0] = g[y0:y1, x1] = (0.2, 0.4, 1.0)
    im = bpy.data.images.new('_diff_' + name, diff.shape[1], diff.shape[0])
    px = np.ones((diff.shape[0], diff.shape[1], 4), np.float32)
    px[:, :, :3] = g[::-1]
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw = os.path.join(OUT, 'diff_%s.png' % name)
    im.file_format = 'PNG'
    im.save()
    print('[hull_ink_render] %-9s changed %7d px, outside the piece boxes %d' % (name, rep['views'][name]['changed'],
                                                                             rep['views'][name]['changed_outside_piece_boxes']))
with open(os.path.join(OUT, 'hull_ink_render.json'), 'w') as f:
    json.dump(rep, f, indent=1)
print('[hull_ink_render] wrote', OUT)
