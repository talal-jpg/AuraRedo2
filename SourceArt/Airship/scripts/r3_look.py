"""Round 3 review fixes (Docs/Airship/round3/EXPORT_R3.md section 15): the in-game look model shared by r3_shade_calib.py
and r3_preview.py. Pure numpy (runs in Blender or in Blender's bundled python).

What it models
* M_AirshipR3 v2 (Docs/Airship/scripts/ue/as_90_r3_textures_material.py), per pixel, colour c = palette + dots + ink:
      BaseColor = c * LitMix                                      (Default Lit: takes the level's sun / moon and sky light)
      Emissive  = max(Sat(c, LiftSat), 0) * ShadeLift / exposure   (EyeAdaptationInverse, alpha LiftLock = 1: the lift is
                                                                    the same on screen whatever the level's exposure)
  so the colour holds in a level whose light is blue (StartupMap) and the shade side never drops to olive.
* StartupMap's light and post process as they are in the level (the ice-look V2.1 preset, decoded from
  Content/Maps/StartupMap.umap by the review): moon 2.24 lux colour (125,160,255) at pitch -55; sky light 0.70 x colour
  (73,203,255) on the engine's DaylightAmbientCubemap, lower hemisphere (0.10,0.18,0.40); manual exposure EV100 0.5;
  PostProcessVolume2 grading (saturation 1.15, contrast 1.1, shadow gain / offset, highlight gain 1.45 and saturation
  0.72 from luminance 0.12).
* The display: Talal's project's verified offline port of the UE 5.8 Filmic tonemapper + grading + LUT
  (AuraRedo3/Saved/ClaudeTools/icelook/m1/display/display_model.py, read only, imported by path).
What it does not know: the brightness of DaylightAmbientCubemap (an engine asset whose source pixels are not readable
offline), so the sky light's absolute strength is a range (SKY_R below); fog, bloom, vignette, Lumen. The editor stage
calibrates the last 10 % (EDITOR_STAGE_R3.md section 4.8).
"""
import os, sys, json, math
import numpy as np

DM_DIR = '/mnt/new_partition/UnrealProjects/AuraRedo3/Saved/ClaudeTools/icelook/m1/display'
_dm = None


def dm():
    """the display model module (imported once, by path; never written)"""
    global _dm
    if _dm is None:
        if DM_DIR not in sys.path:
            sys.path.insert(0, DM_DIR)
        sys.dont_write_bytecode = True
        import display_model
        _dm = display_model
    return _dm


def s2l8(c):
    c = np.asarray(c, np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def l2s(c):
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


# ------------------------------------------------------------------ StartupMap (match level) light and post process
STARTUP = dict(
    source='Content/Maps/StartupMap.umap = icelook preset V2_1.json (applied 2026-10-26; decoded by the round 3 review)',
    moon_lux=2.24, moon_rgb8=(125, 160, 255), moon_rot_pyr=(-55.0, 178.0, 100.0),
    sky_intensity=0.70, sky_rgb8=(73, 203, 255), sky_lower=(0.10, 0.18, 0.40), sky_cubemap='/Engine/MapTemplates/Sky/DaylightAmbientCubemap',
    ev100=0.5, sky_display_hex='026AB5',
    pp=dict(auto_exposure_bias=-0.5, color_saturation=(1.15, 1.15, 1.15, 1.0), color_contrast=(1.1, 1.1, 1.1, 1.0),
            color_gain_shadows=(1.05, 0.85, 0.85, 1.0), color_offset_shadows=(0.008, 0.013, 0.0275, 0.0),
            color_gain_highlights=(1.45, 1.45, 1.38, 1.0), color_offset_highlights=(0.0, 0.0, 0.0, 0.0),
            color_correction_highlights_min=0.12, color_correction_highlights_max=0.42,
            color_saturation_highlights=(0.72, 0.72, 0.72, 1.0)))
# DaylightAmbientCubemap's mean radiance is not known offline: the sky light is modelled as R x intensity x colour on the
# upper hemisphere, R in this range (the defaults must hold over all of it)
SKY_R = (0.3, 0.6, 1.0)
SKY_R_PREVIEW = 0.6


def moon_dir_blender():
    """direction the moon light travels, in Blender world space (UE: X fwd, Y right, Z up; the rig: Blender y = -UE y)"""
    p, y = math.radians(STARTUP['moon_rot_pyr'][0]), math.radians(STARTUP['moon_rot_pyr'][1])
    f = np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)])
    return np.array([f[0], -f[1], f[2]])


def startup_pp():
    return dm().load_pp(dict(STARTUP['pp']))


def startup_lights(sky_r=SKY_R_PREVIEW):
    """scene-linear light values in UE units (= Blender units: a sun of strength E and a white Lambert surface give E/pi
    in both, measured 2026-11-28 in Blender 4.5 EEVEE: 0.3176 for E = 1)"""
    moon = STARTUP['moon_lux'] * s2l8(STARTUP['moon_rgb8'])
    sky_col = s2l8(STARTUP['sky_rgb8'])
    upper = sky_r * STARTUP['sky_intensity'] * sky_col
    lower = np.array(STARTUP['sky_lower']) * STARTUP['sky_intensity'] * sky_col
    return dict(moon=moon, upper=upper, lower=lower, exposure=2.0 ** -STARTUP['ev100'])


# ------------------------------------------------------------------ the material's look knobs (as_90 v2 defaults)
LOOK_NAMES = ('lit_mix', 'shade_lift', 'lift_sat', 'lift_lock')
LOOK_OFF = dict(lit_mix=1.0, shade_lift=0.0, lift_sat=1.0, lift_lock=1.0)     # = M_AirshipR3 v1 (plain Default Lit)
LUM = np.array([0.2126, 0.7152, 0.0722])


def sat(c, s):
    c = np.asarray(c, np.float64)
    l = (c * LUM).sum(-1, keepdims=True)
    return np.maximum(l + (c - l) * s, 0.0)


def emissive_display(c, look):
    """the emissive term in display-domain linear (after exposure): exposure-locked, so independent of the level"""
    return sat(c, look['lift_sat']) * look['shade_lift']


def display_startup(v_after_exposure, pp=None):
    """display-domain linear (scene x exposure) -> displayed sRGB 0-255 in StartupMap (Filmic + V2.1 grading + LUT)"""
    return dm().forward(np.asarray(v_after_exposure, np.float64).reshape(-1, 3), pp or startup_pp(), 0.0)


def lab(rgb255):
    """sRGB 0-255 -> CIE Lab (D65)"""
    l = s2l8(rgb255)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = l @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def hue_deg(rgb255):
    L = lab(rgb255)
    return np.degrees(np.arctan2(L[..., 2], L[..., 1])) % 360.0
