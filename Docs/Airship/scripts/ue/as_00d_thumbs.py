# as_00d_thumbs.py - renders asset thumbnails (EditorAppToolset.CaptureAssetImage, asynchronous: completes on a later
# tick) into Saved/Airship/thumbs/<name>.png (read-only, no saves).
# Phase 1: set AS_THUMBS = [...] and exec this file -> requests queued in AS_THUMB_PENDING.
# Phase 2: exec it again with AS_THUMBS = None (a later inbox call) -> writes the finished PNGs.
import unreal, os, base64, json
_d = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'thumbs')
os.makedirs(_d, exist_ok=True)
if globals().get('AS_THUMBS'):
    AS_THUMB_PENDING = {}
    for p in AS_THUMBS:
        AS_THUMB_PENDING[p] = unreal.ToolsetRegistry.execute_tool('EditorToolset.EditorAppToolset', 'CaptureAssetImage', json.dumps({'assetPath': p}))
    print('queued', len(AS_THUMB_PENDING))
else:
    for p, r in list(globals().get('AS_THUMB_PENDING', {}).items()):
        if not r.get_editor_property('is_complete'):
            print('pending', p); continue
        err = str(r.get_editor_property('error') or '')
        if err:
            print('fail', p, err); AS_THUMB_PENDING.pop(p); continue
        img = json.loads(str(r.get_editor_property('value')))['returnValue']
        fn = os.path.join(_d, p.split('/')[-1].split('.')[0] + '.png')
        open(fn, 'wb').write(base64.b64decode(img['data']))
        print('ok', fn)
        AS_THUMB_PENDING.pop(p)
