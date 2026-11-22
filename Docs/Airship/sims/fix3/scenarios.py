import math, sys
sys.path.insert(0, '.')
from cap_model import New, Old, size, size2

DT = 1.0 / 30.0
D = math.radians
R = math.degrees


def run(model, frames, dead=False):
    """frames: list of (pre_v, pre_w, post_v, post_w, kick) or None (no hit: the state coasts). Returns the last v, w."""
    t = 0.0
    out = []
    for f in frames:
        t += DT
        if f is None:
            continue
        pv, pw, v, w, k = f
        out.append(model.hit(t, DT, pv, pw, v, w, dead, k))
    return out


Z = (0, 0, 0)
res = {}
# S1 obstacle clip at 86 m/s, alive, one frame +26 m/s up
for M in (Old, New):
    o = run(M(), [((8600, 0, 0), Z, (8300, 0, 2600), Z, Z)])
    res.setdefault('S1 clip 86 m/s: up m/s', []).append(round(o[-1][0][2] / 100, 2))
# S1b two frames of push-out
for M in (Old, New):
    m = M(); o1 = m.hit(DT, DT, (8600, 0, 0), Z, (8300, 0, 2600), Z)
    o2 = m.hit(2 * DT, DT, o1[0], Z, (o1[0][0], 0, o1[0][2] + 800), Z)
    res.setdefault('S1b clip, 2-frame push: up m/s', []).append(round(o2[0][2] / 100, 2))
# S2 wreck ground hit at 68 m/s, sideways kick 18 m/s
for M in (Old, New):
    o = run(M(), [((0, 0, -6800), Z, (1800, 0, -300), Z, Z)], dead=True)
    res.setdefault('S2 wreck 68 m/s: sideways m/s', []).append(round(size2(o[-1][0]) / 100, 2))
# S3 wreck bounce: frame 1 -68 -> +15 m/s, frame 2 PBD adds +6 m/s
for M in (Old, New):
    m = M(); o1 = m.hit(DT, DT, (0, 0, -6800), Z, (0, 0, 1500), Z, True)
    o2 = m.hit(2 * DT, DT, o1[0], Z, (0, 0, o1[0][2] + 600), Z, True)
    vz = o2[0][2]
    res.setdefault('S3 wreck bounce: up m/s, height m', []).append((round(vz / 100, 2), round(vz * vz / (2 * 980) / 100, 2)))
# S4 landed 10 s (hits every frame, resting), then a pillar pop (+26 up, +18 sideways)
for M in (Old, New):
    m = M(); t = 0.0
    for i in range(300):
        t += DT
        m.hit(t, DT, (0, 0, -1), Z, (0, 0, 0.5), Z)
    t += DT
    o = m.hit(t, DT, (2000, 0, 0), Z, (3800, 0, 2600), (0, 0, D(60)))
    res.setdefault('S4 after 10 s landed, pop: v (m/s) / spin deg/s', []).append(
        (round(o[0][0] / 100, 2), round(o[0][2] / 100, 2), round(R(o[1][2]), 1)))
# S5 alternating: +800 sideways kick every other frame for 1 s, benign frames between (contact all along)
for M in (Old, New):
    m = M(); t = 0.0; v = [0.0, 0, 0]
    for i in range(30):
        t += DT
        post = (v[0] + (800 if i % 2 == 0 else 0), 0, 0)
        v = list(m.hit(t, DT, v, Z, post, Z)[0])
    res.setdefault('S5 alternating 800 kicks 1 s: gained m/s', []).append(round(v[0] / 100, 2))
# S6 drift kick (600 fwd) while scraping at 30 m/s, noted vs not
m = New(); o = m.hit(DT, DT, (3000, 0, 0), Z, (3600, 0, 0), Z, False, (600, 0, 0))
m2 = New(); o2 = m2.hit(DT, DT, (3000, 0, 0), Z, (3600, 0, 0), Z)
o3 = Old().hit(DT, DT, (3000, 0, 0), Z, (3600, 0, 0), Z)
res['S6 drift kick in contact: new noted / new not noted / old'] = (round(o[0][0] / 100, 2), round(o2[0][0] / 100, 2), round(o3[0][0] / 100, 2))
# S7 spin reversal 30 -> -30 deg/s yaw, alive
for M in (Old, New):
    o = M().hit(DT, DT, Z, (0, 0, D(30)), Z, (0, 0, D(-30)))
    res.setdefault('S7 spin reversal +30 -> -30: deg/s', []).append(round(R(o[1][2]), 1))
# S7b spin axis turned: 30 deg/s yaw -> 30 deg/s roll
for M in (Old, New):
    o = M().hit(DT, DT, Z, (0, 0, D(30)), Z, (D(30), 0, 0))
    res.setdefault('S7b spin axis turned (30 yaw -> 30 roll): w deg/s', []).append([round(R(x), 1) for x in o[1]])
# S8 5 fps, push-out over 3 frames of +1000 each (contact continues)
for M in (Old, New):
    m = M(); v = [0.0, 0, 0]; t = 0.0
    for i in range(3):
        t += 0.2
        v = list(m.hit(t, 0.2, v, Z, (v[0] + 1000, 0, 0), Z)[0])
    res.setdefault('S8 5 fps, 3 x 1000 push: gained m/s', []).append(round(v[0] / 100, 2))
# S9 boost scrape 3 s at 1960 cm/s2 (contact every frame)
for M in (Old, New):
    m = M(); v = [2000.0, 0, 0]; t = 0.0
    for i in range(90):
        t += DT
        v = list(m.hit(t, DT, v, Z, (v[0] + 1960 * DT, 0, 0), Z)[0])
    res.setdefault('S9 boost scrape 3 s from 20 m/s (want 78.8)', []).append(round(v[0] / 100, 2))
# S10 take-off after 2 s landed, lift +0.5 g for 2 s (contact for the first 0.3 s only)
for M in (Old, New):
    m = M(); t = 0.0
    for i in range(60):
        t += DT; m.hit(t, DT, (0, 0, 0), Z, (0, 0, 0), Z)
    v = [0.0, 0, 0]
    for i in range(9):
        t += DT; v = list(m.hit(t, DT, v, Z, (0, 0, v[2] + 490 * DT), Z)[0])
    res.setdefault('S10 take-off, up speed after 0.3 s contact (want 4.9 m/s x 0.3 = 1.47)', []).append(round(v[2] / 100, 2))
# S11 yaw spin-up at 1 rad/s2 for 0.6 s while scraping (contact every frame)
for M in (Old, New):
    m = M(); w = [0.0, 0, 0]; t = 0.0
    for i in range(18):
        t += DT; w = list(m.hit(t, DT, (2000, 0, 0), w, (2000, 0, 0), (0, 0, w[2] + 1.0 * DT))[1])
    res.setdefault('S11 yaw spin-up 1 rad/s2 0.6 s (want 34.4 deg/s)', []).append(round(R(w[2]), 1))
# S12 sustained wedge push 200 cm/s per frame for 1 s
for M in (Old, New):
    m = M(); v = [0.0, 0, 0]; t = 0.0
    for i in range(30):
        t += DT; v = list(m.hit(t, DT, v, Z, (v[0] + 200, 0, 0), Z)[0])
    res.setdefault('S12 wedge push 200/frame 1 s: gained m/s', []).append(round(v[0] / 100, 2))

for k, v in res.items():
    print('%-70s old %-22s new %s' % (k, v[0], v[1]) if isinstance(v, list) else '%-70s %s' % (k, v))
