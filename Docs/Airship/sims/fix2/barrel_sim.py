import math
def run(limit, settle, f=3.0, zeta=1.0, kff=0.5, slew=45.0, start=0.0, frame=1/30.0, sub=40):
    w = 2*math.pi*f
    th, v = start, 0.0
    tgt = start
    peak = -1e9
    prev_t = tgt
    for n in range(int(4.0/frame)):
        err = limit - tgt
        rate = slew if settle <= 0 else min(slew, abs(err)*settle)
        step = min(abs(err), rate*frame)
        tgt += math.copysign(step, err)
        tvel = (tgt - prev_t)/frame
        prev_t = tgt
        h = frame/sub
        for _ in range(sub):
            a = w*w*(tgt - th) + 2*zeta*w*(kff*tvel - v)
            v += a*h; th += v*h
        peak = max(peak, th)
    return peak
for lim in (8.75, 8.5):
    for st in (0, 8, 12):
        print('limit %.2f settle %2d: peak %.3f (over %.3f)' % (lim, st, run(lim, st), run(lim, st)-lim))
