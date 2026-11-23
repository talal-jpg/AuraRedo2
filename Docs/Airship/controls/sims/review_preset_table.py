"""Review tool (2026-11-23): the union preset table of IMPLEMENTATION_PLAN.md 1.13 (markdown rows) from the bench
presets, with the C++ names (section 6 of the plan) and the spec-only values (feedback, impact, boom lag distance).
Scheme-only properties print "-" for the other schemes.

    cd Docs/Airship/controls/sims; python3 review_preset_table.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
import airship_sim as A
import scheme_galleon as G, scheme_skyracer as S, scheme_pointfly as PF

FD, PD = A.FLIGHT_DEFAULTS, A.PAWN_DEFAULTS
REN = {
    'bSkyLevelGrip': 'bLevelGripForce', 'SkyBrakeAccelMax': 'BrakeMaxAccel', 'PFBrakeAccelMax': 'BrakeMaxAccel',
    'SkyDriftAlphaYawMax': 'DriftAlphaYawMax',
    'SkyAimBankScale': 'GunDeckBankScale', 'GalleonStationsBankScale': 'GunDeckBankScale', 'PFAimBankScale': 'GunDeckBankScale',
    'SkyAimYawScale': 'GunDeckYawScale', 'GalleonStationsHelmScale': 'GunDeckYawScale',
    'SkyAimThrottleScale': 'GunDeckThrottleScale', 'SkyAimBrakeScale': 'GunDeckBrakeScale',
    'CameraTargetOffsetZ': 'CameraBoom->TargetOffset.Z', 'CameraLagSpeed': 'CameraBoom->CameraLagSpeed',
    'CameraRotationLagSpeed': 'CameraBoom->CameraRotationLagSpeed',
    'PFArcAssist': 'bPFArcAssist', 'PFPitchClimb': 'bPFPitchClimb',
    # pawn feedback names of the bench -> shared feedback (spec-only values are added below)
    'SkyCamRollShare': 'CameraRollPerBank', 'SkyCamRollMaxDeg': 'CameraRollMaxDeg', 'SkyShakeRotDeg': 'ShakeRotDeg',
    'SkyFOVMax': 'FOVMaxDeg', 'GalleonCameraRollMaxDeg': 'CameraRollMaxDeg',
}
DROP = {'bSkyDrift', 'GalleonCameraRollPerBankDeg'}   # ActiveScheme; Galleon roll -> CameraRollPerSteerDeg below
rows = {}
V1 = {}
V1.update(G.CLASSIC_NEW); V1.update(S.BASE_FIX_V1); V1.update(S.SKY_FLIGHT_V1); V1.update(S.SKY_PAWN_V1)
V1.update(dict(PFReverseBrakeAccel=0.0, PFTurnLiftComp=0.0, BrakeMaxAccel=0.0, DriftAlphaYawMax=0.0,
               GunDeckBankScale=1.0, GunDeckYawScale=1.0, GunDeckThrottleScale=1.0, GunDeckBrakeScale=1.0,
               bLevelGripForce=False, bLevelGripAlongHeading=False))
PAWN_V1 = dict(ImpactMinSpeed=400.0, ImpactDamagePerMS=6.0, ImpactMaxDamage=500.0, ImpactCooldown=0.4,
               ImpactMaxSpinKickDeg=20.0, ImpactMaxSpeedGain=500.0, ImpactMaxReboundSpeed=250.0,
               ImpactEpisodeAccelUp=0.0, FOVInterpSpeed=4.0, CameraLagMaxDistance=2500.0)
OWNER = {}
def owner_of(name, bench_owner):
    if name.startswith('CameraBoom->'): return 'Boom'
    return bench_owner
def add(scheme, d, defaults, bench_owner):
    for k, v in d.items():
        if k in DROP: continue
        name = REN.get(k, k)
        own = owner_of(name, bench_owner)
        if k in defaults: v1 = defaults[k]
        elif name in V1: v1 = V1[name]
        elif k in V1: v1 = V1[k]
        elif name in PAWN_V1: v1 = PAWN_V1[name]
        else: v1 = None
        r = rows.setdefault(name, dict(owner=own, classic=v1, galleon=None, skyracer=None, pointfly=None))
        if r['classic'] is None: r['classic'] = v1
        r[scheme] = v
for key, cls in (('galleon', G.Galleon), ('skyracer', S.SkyRacer), ('pointfly', PF.PointFly)):
    add(key, cls.flight, FD, 'FC')
    add(key, cls.pawn, PD, 'Pawn')
def put(name, owner, classic, g=None, s=None, p=None):
    r = rows.setdefault(name, dict(owner=owner, classic=classic, galleon=None, skyracer=None, pointfly=None))
    r['owner'], r['classic'] = owner, classic
    for k, v in (('galleon', g), ('skyracer', s), ('pointfly', p)):
        if v is not None: r[k] = v
# corrections and spec-only values
put('bLevelGripAlongHeading', 'FC', False, s=True)
put('GunDeckBankScale', 'FC', 1.0, 0.2, 0.35, 0.4)
put('GunDeckYawScale', 'FC', 1.0, 0.5, 0.8, None)
put('ImpactEpisodeAccelUp', 'Pawn', 0.0, 2050.0, 2650.0, 2000.0)
put('ImpactMaxReboundSpeed', 'Pawn', 250.0, 120.0, 120.0, 120.0)
for k in ('ImpactMinSpeed', 'ImpactDamagePerMS', 'ImpactMaxDamage', 'ImpactCooldown', 'ImpactMaxSpinKickDeg', 'ImpactMaxSpeedGain', 'FOVInterpSpeed'):
    rows[k]['classic'] = PAWN_V1[k]
put('CameraBoom->CameraLagMaxDistance', 'Boom', 2500.0, 3000.0)
# shared feedback (pawn): Classic all off
put('ShakeRotDeg', 'Pawn', 0.0, 1.0, 1.2, 1.2)
put('ShakeLocCm', 'Pawn', 0.0, 20.0, None, None)
put('ShakeFrequency', 'Pawn', 10.0, 8.0, 14.0, 13.0)
put('ShakeDecay', 'Pawn', 2.0, 1.8, 1.8, 2.5)
put('FOVKickDecay', 'Pawn', 3.0, None, 2.5, 5.0)
put('FOVMaxDeg', 'Pawn', 0.0, None, 112.0, None)
put('CameraRollPerBank', 'Pawn', 0.0, None, 0.25, 0.15)
put('CameraRollPerSteerDeg', 'Pawn', 0.0, 6.5, None, None)
put('CameraRollMaxDeg', 'Pawn', 6.0, None, None, 3.0)
put('CameraRollInterpSpeed', 'Pawn', 0.0, 8.0, None, 6.0)
put('RumbleScale', 'Pawn', 0.0, 1.0, 1.0, 1.0)
put('ShakeHitPerMS', 'Pawn', 0.0, 0.06, 0.05, 0.05)
put('ShakeHitMax', 'Pawn', 1.0, None, 0.8, None)
put('RumbleHitPerMS', 'Pawn', 0.0, 0.06, None, 0.067)
put('DriftTraumaBase', 'Pawn', 0.0, None, 0.08, None)
put('DriftTraumaPerCharge', 'Pawn', 0.0, None, 0.12, None)
put('DriftRumbleBase', 'Pawn', 0.0, 0.2, 0.15, None)
put('DriftRumblePerCharge', 'Pawn', 0.0, None, 0.35, None)
EV = 'FAirshipFeedbackEvent'
def ev(t, f, r, rt, large=True):
    return '(%s, %s, %s, %s%s)' % (t, f, r, rt, '' if large else ', small')
put('FeedbackBoostStart', 'Pawn', '0', ev(0.3, 6, 0.4, 0.4), ev(0.35, 6, 0.6, 0.2), ev(0, 5, 0.3, 0.35, False))
put('FeedbackOwnBroadside', 'Pawn', '0', ev(0.35, -3, 0.6, 0.25), None, ev(0.25, -3, 0.5, 0.15))
put('FeedbackDriftKick', 'Pawn', '0', ev(0.25, 4, 0.5, 0.2), None, ev(0.2, 4, 0.6, 0.2))
put('FeedbackTurbo1', 'Pawn', '0', None, ev(0.3, 4, 0.5, 0.25), None)
put('FeedbackTurbo2', 'Pawn', '0', None, ev(0.45, 7, 0.75, 0.25), None)
put('FeedbackTurbo3', 'Pawn', '0', None, ev(0.65, 10, 1.0, 0.25), None)
put('FeedbackOrderChange', 'Pawn', '0', ev(0.06, 1.5, 0.25, 0.08), None, None)
put('FeedbackLockEngage', 'Pawn', '0', None, None, ev(0, 0, 0.15, 0.06, False))
def fmt(v):
    if v is None: return '='
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e7: return '%d' % v
        return '%g' % v
    return str(v)
order = {'FC': 0, 'Pawn': 1, 'Boom': 2}
only_in = {'Galleon': 'galleon', 'Sky': 'skyracer', 'PF': 'pointfly'}
out = []
for name in sorted(rows, key=lambda n: (order[rows[n]['owner']], n.lower())):
    r = rows[name]
    cells = []
    for s in ('galleon', 'skyracer', 'pointfly'):
        v = r[s]
        cells.append('=' if (v is None or v == r['classic']) else fmt(v))
    c = r['classic']
    if c is None:
        # scheme-only property: the C++ default is that scheme's value (only read in that scheme)
        cs = '-'
        cells = ['-' if r[s] is None else fmt(r[s]) for s in ('galleon', 'skyracer', 'pointfly')]
    else:
        cs = fmt(c)
    out.append('| %s | %s | %s | %s | %s | %s |' % (r['owner'], name, cs, cells[0], cells[1], cells[2]))
print('\n'.join(out))
print(len(out), 'rows', file=sys.stderr)
