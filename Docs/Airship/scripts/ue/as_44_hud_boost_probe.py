# as_44_hud_boost_probe.py - short PIE look check of the ship HUD while boosting (validation session 2026-11-22, after the
# BOOST ink-tag width fix in UAirshipHUDWidget::NativePaint). Standalone PIE (the play settings as left by as_43: check
# first), board at 1.5 s, throttle 1 + boost from 2.5 s, X grab requests (xgrab_loop.sh must run) 'hud_boost_fix' at
# 3.6 s and 'hud_boost_fix2' at 4.4 s, ends its own PIE at 5.5 s. Nothing is saved.
# Run (L_AirshipTest open, no PIE): inbox.sh 44 Docs/Airship/scripts/ue/as_44_hud_boost_probe.py 60
import os, time  # unreal = inbox namespace
AS44_XG = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'val', 'xgrab')
os.makedirs(AS44_XG, exist_ok=True)


class As44(object):
    def __init__(self):
        self.w = None; self.ship = None; self.t0 = None; self.done = set(); self.handle = None; self.wall = time.time()
        self.now = 0.0; self.log = []

    def at(self, t, k, fn):
        if self.now >= t and k not in self.done:
            self.done.add(k)
            try:
                fn()
                self.log.append('%.2f %s' % (self.now, k))
            except Exception as e:  # noqa: BLE001
                self.log.append('%.2f %s FAILED %r' % (self.now, k, e))

    def req(self, label):
        with open(os.path.join(AS44_XG, label + '.req'), 'w') as f:
            f.write(AS44_XG + '\n')

    def tick(self, dt):
        try:
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if self.w is None:
                ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
                if ws:
                    self.w = ws[0]
                elif time.time() - self.wall > 90:
                    self.end()
                return
            if not les.is_in_play_in_editor():
                self.end(); return
            tw = unreal.GameplayStatics.get_time_seconds(self.w)
            if self.ship is None:
                s = unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'))
                if s:
                    self.ship, self.t0 = s[0], tw
                return
            self.now = tw - self.t0
            self.at(1.5, 'board', lambda: unreal.SystemLibrary.execute_console_command(self.w, 'Aura.Airship.Board'))
            self.at(2.5, 'boost', lambda: self.ship.debug_set_input(1.0, 0.0, 0.0, 0.0, True, False))
            self.at(3.6, 'grab1', lambda: self.req('hud_boost_fix'))
            self.at(4.4, 'grab2', lambda: self.req('hud_boost_fix2'))
            if self.now >= 5.5:
                self.end()
        except Exception as e:  # noqa: BLE001
            unreal.log_warning('as_44 %r' % e)

    def end(self):
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            les.editor_request_end_play()
        self.log.append('ended')


if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
    print('FAIL: PIE running')
else:
    _ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
    print('play net mode', unreal.ToolsetLibrary.get_object_properties(_ps, ['PlayNetMode', 'PlayNumberOfClients']))
    AS44 = As44()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
    AS44.handle = unreal.register_slate_post_tick_callback(AS44.tick)
    print('armed')
