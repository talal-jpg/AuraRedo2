"""Template for a control scheme module. Copy it to scheme_<key>.py (key = galleon, skyracer, pointfly, ...), rename
the class, set key / enum / label, and override only what your scheme changes. Every hook below shows the Classic
behaviour it replaces. Run your scheme with:

    python3 metrics.py <key>          -> <key>_metrics.json (M1..M12)
    python3 course.py <key>           -> the gate course, both bots, 0 and 100 ms
    python3 course.py <key> --tune    -> bot gains for your scheme's precise bot (paste into GAINS)
    python3 compare.py classic <key>  -> side by side

As shipped this template changes nothing, so its metrics must equal classic_metrics.json (a plug-in self-test).
"""
from airship_sim import (Scheme, Classic, RawInput, PilotInput, Command, Intent, register_scheme, quantize_ext, ext_to_float,
                         BUTTON_BOOST, BUTTON_BRAKE, BUTTON_AIM, BUTTON_HAS_AIM, clamp, wrap180)


@register_scheme
class Template(Classic):
    key = 'template'
    enum = 99                 # the contract's EAirshipControlScheme value (Classic 0, Galleon 1, SkyRacer 2, PointFly 3)
    label = 'Template (= Classic)'

    # Preset table: UAirshipFlightComponent properties (airship_sim.FLIGHT_DEFAULTS names, C++ units: cm, cm/s, s)
    # and pawn / anim properties (PAWN_DEFAULTS). Applying the scheme sets all of them; Classic = the defaults.
    flight = {}               # e.g. {'SteerTau': 0.10, 'YawRateAtTop': 40.0}
    pawn = {}                 # e.g. {'RecenterDelay': 0.8}
    ctrl_inertia = 'chaos'    # 'hull' models the ApplyForces inertia fix (README: Finding 1)

    # Extra FAirshipPilotInput fields (small, quantized): name -> (bits, scale, signed). Example:
    #   ext_fields = {'HeadingCdeg': (16, 0.01, True)}   # heading target in 0.01 deg
    ext_fields = {}

    # Bot gains (course.py --tune finds them for your scheme)
    GAINS = dict(Classic.GAINS)

    def reset(self, sim):
        """Scheme-local runtime state, reset on a switch and on board / exit (contract)."""
        sim.pilot_state = {}      # e.g. {'order': 0.0} for a telegraph, {'heading': None} for a heading target
        sim.server_state = {}

    # ---- pilot's machine -------------------------------------------------------------------------------------------
    def camera(self, sim, raw, cam, view, dt):
        """raw.cam_yaw / cam_pitch (the control rotation the harness or mouse set), raw.look (look input this frame),
        view = the ship as this machine sees it (dict, see Sim.tele_server). Set cam.control_yaw / control_pitch /
        free_look; call self.camera_lag(sim, cam, dt) last."""
        Classic.camera(self, sim, raw, cam, view, dt)

    def pilot_input(self, sim, raw, cam, view, dt):
        """Raw keys + camera + the pilot's view of the ship -> FAirshipPilotInput (int8 axes, quantized like the RPC).
        Telegraph, heading targets, camera-to-steer all go here (or on the server, from an ext field)."""
        p = Classic.pilot_input(self, sim, raw, cam, view, dt)
        # e.g. p.ext['HeadingCdeg'] = quantize_ext(cam.control_yaw, self.ext_fields['HeadingCdeg'])
        return p

    # ---- server ----------------------------------------------------------------------------------------------------
    def server_controls(self, sim, controls, dt):
        """After the input arrived and the boost was gated, before RepInput and the shaping: e.g. turn a heading
        target into Steer from the authoritative heading (sim.body, sim.tele()), so every machine's cosmetics follow."""
        return controls

    def shaping_targets(self, sim, fm, controls, targets, fwd_speed):
        """Every machine, inside ShapeControls: change targets['throttle'|'boost'|'lift'|'steer'|'strafe'|'brake'|
        'drifting'] before the filters run (fm = that machine's flight model)."""
        return None

    def server_commands(self, sim, fm, cmd):
        """Inside ApplyForces, before the allocation: cmd['AFanCmd'], 'ADrag', 'ABrake' (cm/s^2), 'VzCmd' (cm/s),
        'BankDeg', 'PitchExtraDeg', 'YawRateCmd' (rad/s), 'Klat', 'ALatMax', 'Eta', 'VlTarget' (cm/s)."""
        return None

    def server_forces(self, sim, fm, cmd, out):
        """After the forces: add exact accelerations to out['ACom'] (world cm/s^2) / out['AlphaCom'] (world rad/s^2)."""
        return None

    def telemetry(self, sim, tele):
        """FAirshipFlightTelemetry scheme fields (contract): Scheme, ThrottleOrder (-2 = none), DriftCharge,
        bHeadingTargetActive, HeadingTargetDeg, bFreeLook."""
        Classic.telemetry(self, sim, tele)
        tele['Scheme'] = self.enum

    # ---- bench adapters ----------------------------------------------------------------------------------------------
    def command_raw(self, sim, cmd):
        """Open-loop maneuver (Command: thrust, steer, lift, strafe, boost, brake, drift, aim, look_yaw/pitch) -> the RAW
        inputs YOUR controls need for it. Classic holds the matching keys. A telegraph scheme taps W until its order
        is full ahead; a camera-steered scheme turns the camera; keep any state in sim.pilot_state."""
        return Classic.command_raw(self, sim, cmd)

    def intent_raw(self, sim, intent, view, gains=None):
        """Closed-loop goal (Intent: course_deg, speed, alt, look_at, yaw_rate_ff, brake_hint) -> RAW inputs. The bots
        call it every frame; the sloppy bot then turns the KEY_AXES into on/off keys with a 0.1 s minimum press."""
        return Classic.intent_raw(self, sim, intent, view, gains)

    KEY_AXES = ('throttle', 'steer', 'lift', 'strafe')   # raw axes that are keys on a keyboard (sloppy bot)
