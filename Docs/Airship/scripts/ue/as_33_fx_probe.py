# as_33_fx_probe.py - PIE probe (read-mostly): why are the ThrusterFX_* Niagara components of BP_AirshipPawn inactive in PIE
# while TurbineFX_* run? Starts PIE (Standalone) on the open L_AirshipTest, waits ~60 frames, records every Niagara
# component's asset / IsActive / auto-activate / execution state, calls Activate(true) on the inactive ones, records
# again after 30 and 90 frames, ends its own PIE. Writes Saved/Airship/fx_probe.json. Nothing is saved.
import json, os, time, traceback  # unreal = inbox namespace

AS33_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'fx_probe.json')
AS33_SHIP = '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'


class As33(object):
    def __init__(self):
        self.n = 0
        self.R = {'snap': {}, 'errors': []}
        self.w = None
        self.ship = None
        self.handle = None
        self.t0 = time.time()

    def comps(self):
        out = {}
        for c in ('ThrusterFX_FL', 'ThrusterFX_FR', 'ThrusterFX_RL', 'ThrusterFX_RR', 'TurbineFX_L', 'TurbineFX_R'):
            nc = self.ship.get_editor_property(c)
            d = {'asset': nc.get_asset().get_path_name() if nc.get_asset() else None, 'active': bool(nc.is_active())}
            for p in ('auto_activate', 'b_auto_activate'):
                try:
                    d['auto_activate'] = bool(nc.get_editor_property(p))
                    break
                except Exception:  # noqa: BLE001
                    pass
            for f in ('is_paused', 'is_visible', 'is_registered'):
                try:
                    d[f] = bool(getattr(nc, f)())
                except Exception:  # noqa: BLE001
                    pass
            try:
                d['execution_state'] = str(nc.get_editor_property('ExecutionState'))
            except Exception:  # noqa: BLE001
                pass
            try:
                x = nc.get_variable_float('Thrust')
                d['thrust'] = x
            except Exception:  # noqa: BLE001
                pass
            out[c] = d
        return out

    def tick(self, dt):
        try:
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if self.w is None:
                ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
                if ws:
                    self.w = ws[0]
                elif time.time() - self.t0 > 120:
                    self.end('no PIE')
                return
            if self.ship is None:
                s = unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, AS33_SHIP))
                if s:
                    self.ship = s[0]
                return
            self.n += 1
            if self.n == 60:
                self.R['snap']['f60'] = self.comps()
                for c, d in self.R['snap']['f60'].items():
                    if not d['active']:
                        self.ship.get_editor_property(c).activate(True)
                self.R['activated'] = [c for c, d in self.R['snap']['f60'].items() if not d['active']]
            if self.n == 90:
                self.R['snap']['f90_after_activate'] = self.comps()
            if self.n == 150:
                self.R['snap']['f150'] = self.comps()
                self.end('done')
        except Exception:  # noqa: BLE001
            self.R['errors'].append(traceback.format_exc()[-800:])
            if len(self.R['errors']) > 20:
                self.end('errors')

    def end(self, why):
        self.R['why'] = why
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            les.editor_request_end_play()
        with open(AS33_OUT, 'w') as f:
            json.dump(self.R, f, indent=1, default=str)


if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
    print('FAIL: PIE running')
else:
    AS33 = As33()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
    AS33.handle = unreal.register_slate_post_tick_callback(AS33.tick)
    print('armed')
