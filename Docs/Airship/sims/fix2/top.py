import json
d = json.load(open('ucx.json'))
def top(h, x, y):
    zt = None; zb = None
    for nx, ny, nz, cx, cy, cz, a in h['faces']:
        if abs(nz) < 1e-4:
            # vertical face: point must be inside
            if nx * (x - cx) + ny * (y - cy) > 1e-6:
                return None
            continue
        z = cz - (nx * (x - cx) + ny * (y - cy)) / nz
        if nz > 0:
            zt = z if zt is None else min(zt, z)
        else:
            zb = z if zb is None else max(zb, z)
    if zt is None or zb is None or zt < zb:
        return None
    return round(zt, 2)
xs = [-16, -14, -12, -10, -8, -6.5, -5, -3, -1, 1, 3, 5, 7, 9]
ys = [0, 1, 2, 2.5, 3, 4, 5, 6, 7, 8]   # Blender +Y = port; UE y = -Blender y
for name in ['UCX_SM_Airship_00', 'UCX_SM_Airship_02']:
    print(name, 'top z (m) rows=Blender y (port), cols=x')
    print('      ' + ' '.join('%6s' % x for x in xs))
    for y in ys:
        print('%5s ' % y + ' '.join('%6s' % top(d[name], x, y) for x in xs))
