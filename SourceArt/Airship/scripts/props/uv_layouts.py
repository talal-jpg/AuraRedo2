"""Rasterise each Cannon mesh's UV layout to rig/renders/props/uv/<name>_uv.png (inspection only, no save).
Islands get random fills; overlaps show red."""
import bpy, bmesh, numpy as np, random
OUT = "/mnt/new_partition/BlenderProjects/StylizedAirship/rig/renders/props/uv/"
RES = 1024
sheet = []
for name in ("Cannon_Barrel", "Cannon_Carriage", "Cannon_Wheel_FL", "Cannon_Quoin"):
    ob = bpy.data.objects[name]
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    # islands via UV-connected faces
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    key = lambda l: (l.vert.index, round(l[uvl].uv.x, 5), round(l[uvl].uv.y, 5))
    for f in bm.faces:
        for l in f.loops:
            a, b = find(("f", f.index)), find(key(l))
            parent[a] = b
    img = np.full((RES, RES, 3), 0.12, np.float32)
    cnt = np.zeros((RES, RES), np.uint8)
    cols = {}
    for f in bm.faces:
        isl = find(("f", f.index))
        c = cols.setdefault(isl, np.array([random.uniform(.3, .9) for _ in range(3)], np.float32))
        pts = [l[uvl].uv.copy() for l in f.loops]
        for i in range(1, len(pts) - 1):
            p = np.array([pts[0], pts[i], pts[i + 1]]) * RES
            x0, y0 = np.maximum(np.floor(p.min(0)).astype(int), 0)
            x1, y1 = np.minimum(np.ceil(p.max(0)).astype(int), RES)
            if x1 <= x0 or y1 <= y0: continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
            (ax, ay), (bx, by), (cx, cy) = p
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-12: continue
            l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / d
            l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / d
            ins = (l1 > 0) & (l2 > 0) & (1 - l1 - l2 > 0)
            sub = img[y0:y1, x0:x1]; sub[ins] = c
            cnt[y0:y1, x0:x1] += ins
    img[cnt > 1] = (1, 0, 0)
    print("uv", name, "islands", len(cols), "coverage", round(float((cnt > 0).mean()), 3), "overlap px", int((cnt > 1).sum()))
    im = bpy.data.images.new(name + "_uv", RES, RES)
    rgba = np.concatenate([img, np.ones((RES, RES, 1), np.float32)], 2)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw = OUT + name + "_uv.png"; im.file_format = "PNG"; im.save()
    bm.free()
    sheet.append(rgba[::2, ::2])
# combined sheet (512 px each, side by side)
S = np.concatenate([np.pad(s, ((8, 8), (8, 8), (0, 0)), constant_values=1.0) for s in sheet], 1)
im = bpy.data.images.new("uv_sheet", S.shape[1], S.shape[0])
im.pixels.foreach_set(S.ravel())
im.filepath_raw = OUT + "uv_sheet.png"; im.file_format = "PNG"; im.save()
