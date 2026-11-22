# as_10c_fix_anim_root.py - A_Airship_TestSweep (ours, checks only): the legacy FBX anim import kept the Blender export's
# root LimbNode rotation (+90 deg about X) on the 'root' track, while the mesh ref pose (and every other track) has the
# Y-up -> Z-up conversion applied (identity). Played on SK_Airship the whole ship would roll 90 deg. This sets the
# root track to identity (translation 0, scale 1) for every key through the AnimationDataController, verifies, saves.
# Run: inbox.sh 10c Docs/Airship/scripts/ue/as_10c_fix_anim_root.py 300
P = '/Game/Assets/MyShip/Drivable/A_Airship_TestSweep'
APE = unreal.AnimPoseExtensions
anim = unreal.EditorAssetLibrary.load_asset(P)
opts = unreal.AnimPoseEvaluationOptions()
def root_q(t):
    r = APE.get_bone_pose(APE.get_anim_pose_at_time(anim, t, opts), 'root', unreal.AnimPoseSpaces.LOCAL)
    return r
r0 = root_q(0.0)
print('INFO: root at t=0 before: T %s Q %s' % (r0.translation, r0.rotation))
n = unreal.AnimationLibrary.get_num_keys(anim)
nf = unreal.AnimationLibrary.get_num_frames(anim)
print('INFO: keys %d frames %d' % (n, nf))
if abs(abs(r0.rotation.w) - 1.0) < 1e-6 and r0.translation.length() < 1e-4:
    print('PASS: root track already identity: nothing to do')
else:
    ctl = anim.controller
    ok = ctl.set_bone_track_keys('root', [unreal.Vector(0.0, 0.0, 0.0)] * n, [unreal.Quat(0.0, 0.0, 0.0, 1.0)] * n,
                                 [unreal.Vector(1.0, 1.0, 1.0)] * n, False)
    print('%s: set_bone_track_keys(root, %d identity keys) -> %s' % ('PASS' if ok else 'FAIL', n, ok))
worst = 0.0
for t in (0.0, 0.5, 4.5, 16.0, 31.9):
    r = root_q(t)
    worst = max(worst, 2.0 * __import__('math').degrees(__import__('math').acos(min(1.0, abs(r.rotation.w)))), r.translation.length())
pose = APE.get_anim_pose_at_time(anim, 0.0, opts)
ref = APE.get_reference_pose(unreal.EditorAssetLibrary.load_asset('/Game/Assets/MyShip/Drivable/SKEL_Airship'))
dmax = 0.0
for b in [str(x) for x in APE.get_bone_names(ref)]:
    a = APE.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD).translation
    e = APE.get_ref_bone_pose(ref, b, unreal.AnimPoseSpaces.WORLD).translation
    dmax = max(dmax, (a - e).length())
print('%s: root track identity at 5 sample times (worst %.5f); anim t=0 component-space positions vs ref pose: worst %.4f cm' % (
    'PASS' if worst < 1e-3 and dmax < 0.1 else 'FAIL', worst, dmax))
if worst < 1e-3 and dmax < 0.1:
    print('%s: saved %s' % ('PASS' if unreal.EditorAssetLibrary.save_asset(P, only_if_is_dirty=False) else 'FAIL', P))
