import math
def run(limit, settle, ratio, fc=4.0, zc=0.55, f=3.0, zeta=1.0, kff=0.5, slew=45.0, frame=1/30.0, sub=40):
    w = 2*math.pi*f; wc = 2*math.pi*fc
    th = v = 0.0      # barrel absolute
    ph = vp = 0.0     # carriage
    tgt = prev = 0.0
    peak_rel = peak_abs = -1e9
    for n in range(int(4.0/frame)):
        err = limit - tgt
        rate = slew if settle <= 0 else min(slew, abs(err)*settle)
        tgt += math.copysign(min(abs(err), rate*frame), err)
        tvel = (tgt - prev)/frame; prev = tgt
        h = frame/sub
        for _ in range(sub):
            ab = w*w*(ph + tgt - th) + 2*zeta*w*(kff*tvel + vp - v)   # barrel accel from its drive (relative to carriage)
            ac = wc*wc*(0 - ph) + 2*zc*wc*(0 - vp) - ratio*ab         # carriage: own drive + reaction (Ib/Ic * ab)
            v += ab*h; th += v*h; vp += ac*h; ph += vp*h
        peak_rel = max(peak_rel, th - ph); peak_abs = max(peak_abs, th)
    return peak_rel, peak_abs
for ratio in (0.5, 1.0, 2.0, 3.0):
    r = run(8.75, 0, ratio)
    print('ratio %.1f const slew 8.75: rel %.2f abs %.2f' % (ratio, r[0], r[1]))
for ratio in (1.0, 2.0, 3.0):
    for lim, st in ((8.5, 0), (8.5, 8), (8.75, 8), (8.5, 12)):
        r = run(lim, st, ratio)
        print('ratio %.1f limit %.2f settle %2d: rel %.2f abs %.2f' % (ratio, lim, st, r[0], r[1]))
