"""Solve the cameras of Talal's sketches (2_steering_wheel_spot.png 1317x576, 3_cannon_spots.png 1303x631) from
hand-picked landmarks (pinhole, Levenberg-Marquardt). Writes rig/checks/verify/sketch_camera.json for verify_render.py.
  <blender>/4.5/python/bin/python3.11 -I rig/scripts/verify_sketch_camera.py"""
import numpy as np, json, math
# (Blender world m) -> (sketch pixel) landmarks: AftL head, Mid head pair midpoint, FwdC head, near fan spinner centre,
# FL nozzle exit centre (Flame bone), RL nozzle exit centre
WORLD = [(11.15, 2.8, 9.70), (24.55, 0.0, 9.70), (30.35, 0.9, 10.50), (-16.65, 7.6, 1.40),
         (3.2276, 4.6557, -5.6415), (-7.7724, 5.1303, -5.9113)]
SKETCH = {'3_cannon_spots': ((1303, 631), [(566, 138), (230, 138), (61, 115), (1061, 289), (733, 453), (905, 431)]),
          '2_steering_wheel_spot': ((1317, 576), [(594, 176), (261, 176), (90, 154), (1094, 328), (762, 488), (932, 466)])}
OUTJ = {}
for key, ((W, H), pix) in SKETCH.items():
    P = np.array(WORLD, float); UV = np.array(pix, float)
    def rot(e):
        a, b, c = e
        Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
        Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
        Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
        return Rz @ Ry @ Rx                      # Blender XYZ euler
    def proj(x):
        C, e, f = x[:3], x[3:6], x[6]
        R = rot(e)
        Xc = (R.T @ (P - C).T).T
        return np.stack([W / 2 + f * Xc[:, 0] / -Xc[:, 2], H / 2 - f * Xc[:, 1] / -Xc[:, 2]], 1)
    def look_euler(C, T):
        d = np.array(T) - np.array(C); d /= np.linalg.norm(d)
        # camera -Z along d, Y up-ish
        z = -d; x = np.cross((0, 0, 1), z); x /= np.linalg.norm(x); y = np.cross(z, x)
        R = np.stack([x, y, z], 1)
        b = -math.asin(R[2, 0]); a = math.atan2(R[2, 1], R[2, 2]); c = math.atan2(R[1, 0], R[0, 0])
        return [a, b, c]
    best = None
    for C0 in [(2, 44, 13), (-5, 45, 15), (5, 50, 20), (0, 60, 18), (-10, 40, 10)]:
        x = np.array(list(C0) + look_euler(C0, (-3, 0, 0.5)) + [941.0])
        lam = 1e-2
        for it in range(400):
            r = (proj(x) - UV).ravel()
            J = np.zeros((len(r), 7))
            for k in range(7):
                dx = np.zeros(7); dx[k] = 1e-5 * (1 + abs(x[k]))
                J[:, k] = ((proj(x + dx) - UV).ravel() - r) / dx[k]
            A = J.T @ J; g = J.T @ r
            step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), -g)
            r2 = (proj(x + step) - UV).ravel()
            if (r2 ** 2).sum() < (r ** 2).sum():
                x = x + step; lam *= 0.5
            else:
                lam *= 4
        err = np.sqrt(((proj(x) - UV) ** 2).sum(1))
        if best is None or err.max() < best[1].max():
            best = (x, err)
    x, err = best
    lens = x[6] * 36.0 / W
    out = {'location': x[:3].round(3).tolist(), 'rotation_euler': x[3:6].round(5).tolist(), 'lens_mm': round(lens, 2),
           'res': [W, H], 'landmark_err_px': err.round(1).tolist()}
    OUTJ[key] = out; print(key, json.dumps(out))

json.dump(OUTJ, open('/mnt/new_partition/BlenderProjects/StylizedAirship/rig/checks/verify/sketch_camera.json', 'w'), indent=1)
