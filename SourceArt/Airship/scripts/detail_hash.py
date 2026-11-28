"""Geometry fingerprint of detail objects, to prove a rebuild is identical (round 3).

  blender_capped.sh --python detail_hash.py -- --blend FILE [--prefix SM_AirshipDetail_Z1_] --out OUT.json \
      [--compare OTHER.json]

Opens FILE read only (never saved). For every mesh object whose name starts with the prefix: vertex / face / triangle
counts, md5 of the world coordinates rounded to 0.1 mm, md5 of the face vertex lists, md5 of the face roles (the
material's palette_key, so a material rename does not count as a change), md5 of the per-vertex bone, parent and
modifiers. --compare: prints SAME / DIFF per object and per field against an earlier fingerprint and exits 1 on any
geometry difference (counts, coordinates, faces).
"""
import bpy, sys, os, json, hashlib
import numpy as np

GEOM_FIELDS = ('verts', 'faces', 'tris', 'co_0p1mm_md5', 'faces_md5')


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def md5(*arrays):
    h = hashlib.md5()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def fingerprint(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get('co', co)
    M = np.array(ob.matrix_world)
    w = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    q = np.round(w * 1e4).astype(np.int64)                       # 0.1 mm
    lt = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get('loop_total', lt)
    lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv)
    mi = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get('material_index', mi)
    keys = [((m.get('palette_key') or m.name) if m else '') for m in me.materials]
    roles = '|'.join(keys[i] if i < len(keys) else '?' for i in mi.tolist())
    gname = {g.index: g.name for g in ob.vertex_groups}
    vb = '|'.join(','.join('%s:%.4f' % (gname[g.group], g.weight) for g in v.groups) for v in me.vertices)
    return dict(verts=n, faces=len(me.polygons), tris=int((lt - 2).sum()), co_0p1mm_md5=md5(q),
                faces_md5=md5(lt, lv), roles_md5=hashlib.md5(roles.encode()).hexdigest(),
                bones_md5=hashlib.md5(vb.encode()).hexdigest(),
                materials=[m.name if m else None for m in me.materials],
                parent=ob.parent.name if ob.parent else None,
                modifiers=[[m.type, getattr(m, 'object', None) and m.object.name] for m in ob.modifiers],
                collections=[c.name for c in ob.users_collection])


def main():
    o = opts()
    blend = o['blend']
    bpy.ops.wm.open_mainfile(filepath=blend)
    prefix = o.get('prefix', 'SM_AirshipDetail_')
    out = {ob.name: fingerprint(ob) for ob in sorted(bpy.data.objects, key=lambda x: x.name)
           if ob.type == 'MESH' and ob.name.startswith(prefix)}
    rep = dict(blend=blend, prefix=prefix, objects=out)
    if o.get('out'):
        os.makedirs(os.path.dirname(o['out']), exist_ok=True)
        with open(o['out'], 'w') as f:
            json.dump(rep, f, indent=1)
    for k, v in out.items():
        print('[hash]', k, {f: v[f] for f in GEOM_FIELDS + ('roles_md5', 'bones_md5')})
    bad = 0
    if o.get('compare'):
        ref = json.load(open(o['compare']))['objects']
        for k in sorted(set(ref) | set(out)):
            if k not in ref or k not in out:
                print('[hash] DIFF missing object', k, 'in', 'reference' if k not in ref else 'this file')
                bad += 1
                continue
            for f in GEOM_FIELDS + ('roles_md5', 'bones_md5', 'parent', 'modifiers'):
                same = ref[k].get(f) == out[k].get(f)
                if not same and f in GEOM_FIELDS:
                    bad += 1
                print('[hash]', 'SAME' if same else 'DIFF', k, f, '' if same else (ref[k].get(f), out[k].get(f)))
        print('[hash] RESULT', 'IDENTICAL GEOMETRY' if bad == 0 else '%d GEOMETRY DIFFERENCES' % bad)
    sys.stdout.flush()
    os._exit(1 if bad else 0)


if __name__ == '__main__':
    main()
