"""Gate-course sweep for tuning the Galleon (design aid, not a metric): runs course.run_course for the precise and the
sloppy bot at 0 and 100 ms over several seeds with flight / gain overrides, and prints the means.

Run: python3 galleon_sweep.py [--seeds 7,8,9,10,11] [--gains course=0.7,rate_damp=0.6] [Name=Value ...]
     (one process, about 1 s per course run)
"""
import sys

import course
from airship_sim import load_scheme


def run(flight=None, gains=None, seeds=(7,), key='galleon', skills=('precise', 'sloppy'), lats=(0.0, 100.0)):
    out = {}
    for skill in skills:
        for lat in lats:
            rows = []
            for seed in seeds:
                sch = load_scheme(key)
                if flight:
                    sch.flight = dict(type(sch).flight, **flight)
                g = dict(type(sch).GAINS, **(gains or {}))
                r = course.run_course(sch, skill, lat, seed=seed, gains=g)
                rows.append(r)
            n = len(rows)
            out['%s_%d' % (skill, lat)] = dict(
                missed=sum(r['gates_missed'] for r in rows) / n,
                time=sum((r['completion_time_s'] or 200.0) for r in rows) / n,
                line_mean=sum((r['line_error_mean_m'] or 50.0) for r in rows) / n,
                line_max=max((r['line_error_max_m'] or 50.0) for r in rows),
                contacts=sum(r['ground_contacts'] for r in rows) / n)
    return out


def fmt(res):
    return ' | '.join('%s miss %.1f t %.1f line %.1f/%.1f' % (k, v['missed'], v['time'], v['line_mean'], v['line_max'])
                      for k, v in res.items())


def parse_kv(text):
    d = {}
    for item in text.split(','):
        if item:
            k, v = item.split('=')
            d[k] = (v.lower() == 'true') if v.lower() in ('true', 'false') else float(v)
    return d


def main(argv):
    seeds = (7,)
    gains = {}
    flight = {}
    key = 'galleon'
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--seeds':
            seeds = tuple(int(x) for x in argv[i + 1].split(','))
            i += 1
        elif a == '--gains':
            gains = parse_kv(argv[i + 1])
            i += 1
        elif a == '--key':
            key = argv[i + 1]
            i += 1
        elif '=' in a:
            flight.update(parse_kv(a))
        i += 1
    print(fmt(run(flight, gains, seeds, key)))


if __name__ == '__main__':
    main(sys.argv[1:])
