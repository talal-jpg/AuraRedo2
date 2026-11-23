"""Side-by-side table of <scheme>_metrics.json files (sim or PIE harness output, same keys).

Run: python3 compare.py classic galleon skyracer pointfly        (reads ./<key>_metrics.json)
     python3 compare.py path/to/a_metrics.json path/to/b_metrics.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(arg):
    path = arg if arg.endswith('.json') else os.path.join(HERE, '%s_metrics.json' % arg)
    return os.path.basename(path).replace('_metrics.json', ''), json.load(open(path))


def flat(d, prefix=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, prefix + k + '.'))
        elif isinstance(v, (int, float)) or v is None or isinstance(v, bool):
            out[prefix + k] = v
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return
    runs = [load(a) for a in argv]
    rows = {}
    order = []
    for name, d in runs:
        for m in ['M%d' % i for i in range(1, 13)]:
            for k, v in flat(d.get(m, {}), m + '.').items():
                if k not in rows:
                    rows[k] = {}
                    order.append(k)
                rows[k][name] = v
    names = [n for n, _ in runs]
    w = max(len(k) for k in order) + 2
    print(''.join(['%-*s' % (w, 'metric')] + ['%14s' % n for n in names]))
    for k in order:
        cells = []
        for n in names:
            v = rows[k].get(n)
            cells.append('%14s' % ('-' if v is None else (('%.2f' % v) if isinstance(v, float) else str(v))))
        print('%-*s' % (w, k) + ''.join(cells))


if __name__ == '__main__':
    main(sys.argv[1:])
