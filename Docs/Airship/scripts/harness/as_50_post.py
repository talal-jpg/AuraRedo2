#!/usr/bin/env python3
"""as_50_post.py - after the as_50 control-scheme PIE run: videos, contact sheets and compare.md for the judges.

Runs OUTSIDE the editor (system python3; as_50_pie_controls.py starts it in the background when PIE has ended, or by
hand):  python3 -I Docs/Airship/scripts/harness/as_50_post.py [--root Saved/Airship/controls] [--keys classic,galleon]
                 [--no-video] [--clean-frames]
Per scheme folder <root>/<key>/ with chase/chase_NNNNN.png + chase/frames.json (the precise bot's gate course, the
pilot's camera, every 4th frame):
  course_<key>.mp4    the frames at their real-time rate (30 / every), 30 fps out, H.264; the scheme, time, speed,
                      height, next gate and drift / boost / turbo burned in from frames.json (libass subtitles; falls
                      back to a soft subtitle track, then to no text)
  contact_<key>.png   ~30 frames of the run, evenly spaced, labelled (ImageMagick montage)
  stills_<key>.png    the key-moment stills (pilot view | wide view), labelled
<root>/compare_course_2x2.mp4: the course videos side by side (2-4 schemes; shorter runs hold their last frame).
<root>/compare.md: rewritten with the media paths (as_50_protocol.write_compare). Log: <root>/post_log.txt (when
started by the harness). CPU: ffmpeg at nice 10, about 1-3 min for four schemes.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

W = '/mnt/new_partition/UnrealProjects/_AirshipWork'
UE = os.path.join(W, 'Docs', 'Airship', 'scripts', 'ue')
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
ORDER = ['classic', 'galleon', 'skyracer', 'pointfly']
LABELS = {'classic': 'Classic (v1)', 'galleon': 'Galleon', 'skyracer': 'Sky Racer', 'pointfly': 'Point & Fly'}


def log(msg):
    print('[as_50_post %s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def run(cmd, timeout=900):
    nice = ['nice', '-n', '10'] if shutil.which('nice') else []
    try:
        p = subprocess.run(nice + cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        out = p.stdout.decode('utf-8', 'replace')
        if p.returncode != 0:
            log('FAILED (%d): %s\n%s' % (p.returncode, ' '.join(cmd)[:400], out[-1500:]))
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        log('FAILED: %s: %r' % (' '.join(cmd)[:300], e))
        return False


def srt_time(t):
    ms = int(round(t * 1000.0))
    return '%02d:%02d:%02d,%03d' % (ms // 3600000, (ms // 60000) % 60, (ms // 1000) % 60, ms % 1000)


def write_srt(key, meta, path):
    frames = meta.get('frames') or []
    fps = float(meta.get('fps') or 7.5)
    alt0 = frames[0].get('alt_m') if frames else 0.0
    with open(path, 'w') as f:
        for i, fr in enumerate(frames):
            tags = []
            if fr.get('drift'):
                tags.append('DRIFT')
            if (fr.get('boost') or 0) > 0.3:
                tags.append('BOOST %.1f' % fr['boost'])
            if (fr.get('turbo') or 0) > 0.05:
                tags.append('TURBO')
            txt = '%s   t %5.1f s   %4.1f m/s   height %+5.1f m   next %s %s' % (
                LABELS.get(key, key), fr.get('t') or 0.0, fr.get('speed_ms') or 0.0, (fr.get('alt_m') or 0.0) - (alt0 or 0.0),
                fr.get('next_gate') or 'finish', ('  ' + '  '.join(tags)) if tags else '')
            f.write('%d\n%s --> %s\n%s\n\n' % (i + 1, srt_time(i / fps), srt_time((i + 1) / fps), txt))
    return len(frames)


def make_video(root, key, clean):
    d = os.path.join(root, key, 'chase')
    mf = os.path.join(d, 'frames.json')
    if not os.path.exists(mf):
        return None
    meta = json.load(open(mf))
    n = len(glob.glob(os.path.join(d, 'chase_*.png')))
    if n < 2:
        log('%s: %d chase frames, no video' % (key, n))
        return None
    fps = float(meta.get('fps') or 7.5)
    srt = os.path.join(d, 'course.srt')
    write_srt(key, meta, srt)
    out = os.path.join(root, key, 'course_%s.mp4' % key)
    base = ['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '%g' % fps, '-i', os.path.join(d, 'chase_%05d.png')]
    enc = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30', '-movflags', '+faststart']
    even = 'scale=trunc(iw/2)*2:trunc(ih/2)*2'
    style = "force_style='FontName=DejaVu Sans,FontSize=14,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4,Alignment=7,MarginV=12'"
    ok = run(base + ['-vf', '%s,subtitles=%s:%s' % (even, srt, style)] + enc + [out])
    how = 'burned-in labels'
    if not ok:
        ok = run(base + ['-i', srt, '-map', '0:v', '-map', '1:s', '-vf', even] + enc + ['-c:s', 'mov_text', out])
        how = 'soft subtitle track'
    if not ok:
        ok = run(base + ['-vf', even] + enc + [out])
        how = 'no labels'
    if not ok:
        return None
    log('%s: %s (%d frames at %g fps, %s)' % (key, out, n, fps, how))
    if clean:
        for p in glob.glob(os.path.join(d, 'chase_*.png')):
            os.remove(p)
        log('%s: chase PNGs removed (--clean-frames)' % key)
    return out, n / fps


def make_contact(root, key):
    if not shutil.which('montage'):
        return None
    d = os.path.join(root, key, 'chase')
    mf = os.path.join(d, 'frames.json')
    files = sorted(glob.glob(os.path.join(d, 'chase_*.png')))
    if not files:
        return None
    meta = json.load(open(mf)) if os.path.exists(mf) else {'frames': []}
    by = dict((fr['file'], fr) for fr in meta.get('frames') or [])
    k = max(1, len(files) // 30)
    pick = files[::k][:36]
    args = ['montage']
    for p in pick:
        fr = by.get(os.path.basename(p), {})
        args += ['-label', 't %.1f s  %s  %.0f m/s' % (fr.get('t') or 0.0, fr.get('next_gate') or '', fr.get('speed_ms') or 0.0), p]
    out = os.path.join(root, key, 'contact_%s.png' % key)
    args += ['-tile', '6x', '-geometry', '320x180+3+3', '-pointsize', '13', '-background', '#1c1c1c', '-fill', '#eeeeee',
             '-title', '%s: gate course, precise bot (pilot camera)' % LABELS.get(key, key), out]
    return out if run(args) else None


def make_stills_sheet(root, key):
    if not shutil.which('montage'):
        return None
    d = os.path.join(root, key, 'stills')
    pilots = sorted(glob.glob(os.path.join(d, '*_pilot.png')))
    if not pilots:
        return None
    args = ['montage']
    for p in pilots:
        base = os.path.basename(p)[:-len('_pilot.png')]
        args += ['-label', '%s (pilot)' % base[3:], p]
        w = os.path.join(d, base + '_wide.png')
        if os.path.exists(w):
            args += ['-label', '%s (wide)' % base[3:], w]
    out = os.path.join(root, key, 'stills_%s.png' % key)
    args += ['-tile', '2x', '-geometry', '640x360+4+4', '-pointsize', '16', '-background', '#1c1c1c', '-fill', '#eeeeee',
             '-title', '%s: key moments' % LABELS.get(key, key), out]
    return out if run(args) else None


def make_grid(root, vids):
    keys = [k for k in ORDER if k in vids]
    if len(keys) < 2:
        return None
    dur = max(vids[k][1] for k in keys)
    out = os.path.join(root, 'compare_course_2x2.mp4')
    for labels in (True, False):
        args = ['ffmpeg', '-y', '-loglevel', 'error']
        for k in keys:
            args += ['-i', vids[k][0]]
        fc = []
        for i, k in enumerate(keys):
            pad = max(0.0, dur - vids[k][1]) + 0.5
            f = '[%d:v]scale=960:540,setsar=1,tpad=stop_mode=clone:stop_duration=%.2f' % (i, pad)
            if labels and os.path.exists(FONT):
                f += ",drawtext=fontfile=%s:text='%s':x=14:y=h-44:fontsize=30:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8" % (
                    FONT, LABELS[k].replace(':', ' '))
            fc.append(f + '[v%d]' % i)
        ins = ''.join('[v%d]' % i for i in range(len(keys)))
        if len(keys) == 2:
            fc.append('%shstack=inputs=2[out]' % ins)
        else:
            lay = '0_0|w0_0|0_h0|w0_h0' if len(keys) == 4 else '0_0|w0_0|0_h0'
            fc.append('%sxstack=inputs=%d:layout=%s:fill=black[out]' % (ins, len(keys), lay))
        args += ['-filter_complex', ';'.join(fc), '-map', '[out]', '-t', '%.2f' % (dur + 0.5), '-c:v', 'libx264', '-preset', 'medium',
                 '-crf', '22', '-pix_fmt', 'yuv420p', '-r', '30', '-movflags', '+faststart', out]
        if run(args, timeout=1800):
            log('comparison video %s (%s)' % (out, ', '.join(keys)))
            return out
    return None


def main(argv):
    root = os.path.join(W, 'Saved', 'Airship', 'controls')
    keys, video, clean = list(ORDER), True, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--root':
            root = argv[i + 1]
            i += 1
        elif a == '--keys':
            keys = [k.strip() for k in argv[i + 1].split(',') if k.strip()]
            i += 1
        elif a == '--no-video':
            video = False
        elif a == '--clean-frames':
            clean = True
        i += 1
    log('root %s, schemes %s, video %s, ffmpeg %s, montage %s' % (root, keys, video, shutil.which('ffmpeg'), shutil.which('montage')))
    vids = {}
    summary = {}
    for k in keys:
        if not os.path.isdir(os.path.join(root, k)):
            continue
        media = {}
        if video and shutil.which('ffmpeg'):
            v = make_video(root, k, clean=False)
            if v:
                vids[k] = v
                media['video'] = os.path.relpath(v[0], root)
        c = make_contact(root, k)
        if c:
            media['contact'] = os.path.relpath(c, root)
        s = make_stills_sheet(root, k)
        if s:
            media['stills_sheet'] = os.path.relpath(s, root)
        summary[k] = media
        mp = os.path.join(root, k, 'metrics.json')
        if media and os.path.exists(mp):
            try:
                m = json.load(open(mp))
                m.setdefault('meta', {}).setdefault('media', {}).update(media)
                with open(mp, 'w') as f:
                    json.dump(m, f, indent=1, default=str)
            except (OSError, ValueError) as e:
                log('%s: metrics.json not updated: %r' % (k, e))
    if video and shutil.which('ffmpeg'):
        g = make_grid(root, vids)
        if g:
            summary['_grid'] = os.path.relpath(g, root)
    if clean:
        for k in vids:
            for p in glob.glob(os.path.join(root, k, 'chase', 'chase_*.png')):
                os.remove(p)
    try:
        sys.path.insert(0, UE)
        import as_50_protocol as P
        lines = ['## Media', '']
        for k, m in summary.items():
            if k == '_grid':
                lines.append('* all schemes side by side: `%s`' % m)
            else:
                lines.append('* %s: %s' % (LABELS.get(k, k), ', '.join('%s `%s`' % (a, b) for a, b in m.items()) or 'none'))
        p = P.write_compare(root, extra_lines=lines + [''])
        log('compare.md: %s' % p)
    except Exception as e:  # noqa: BLE001
        log('compare.md not written: %r' % e)
    with open(os.path.join(root, 'post_summary.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    log('done: %s' % json.dumps(summary))


if __name__ == '__main__':
    main(sys.argv[1:])
