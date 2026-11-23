# as_01_input.py - creates the airship Enhanced Input assets of CPP_NOTES section 2 in /Game/Assets/MyShip/Drivable/Input/
# (11 IA_Airship* + IA_AirshipBoard, IMC_Airship, IMC_AirshipBoard), then reads every mapping back.
# Re-runnable: existing assets are reused and their mappings rebuilt. Saves only these assets.
# IA_AirshipLook's Mouse2D mapping copies the modifiers IA_Rotate has in /Game/Level/PlayerInput/IMC_PlayerMappings
# (2026-11-22: none, IA_Rotate itself has none either; the C++ applies the Options sensitivity/invert like the PC does).
import unreal

AS_IN = '/Game/Assets/MyShip/Drivable/Input'
_at = unreal.AssetToolsHelpers.get_asset_tools()
_eal = unreal.EditorAssetLibrary
VT = unreal.InputActionValueType

# name -> value type (CPP_NOTES 2). bConsumeInput stays at its default (true).
AS_ACTIONS = [
    ('IA_AirshipThrottle', VT.AXIS1D), ('IA_AirshipSteer', VT.AXIS1D), ('IA_AirshipLift', VT.AXIS1D),
    ('IA_AirshipStrafe', VT.AXIS1D), ('IA_AirshipBoost', VT.BOOLEAN), ('IA_AirshipBrake', VT.BOOLEAN),
    ('IA_AirshipFire', VT.BOOLEAN), ('IA_AirshipLook', VT.AXIS2D), ('IA_AirshipZoom', VT.AXIS1D),
    ('IA_AirshipExit', VT.BOOLEAN), ('IA_AirshipAim', VT.BOOLEAN), ('IA_AirshipBoard', VT.BOOLEAN),
]

# modifier specs: ('neg',), ('dz', lower, upper), ('exp', e), ('copy_rotate',)
AS_IMC = {
    'IMC_Airship': [
        ('IA_AirshipThrottle', 'W', []), ('IA_AirshipThrottle', 'S', [('neg',)]), ('IA_AirshipThrottle', 'Gamepad_LeftY', []),
        ('IA_AirshipSteer', 'D', []), ('IA_AirshipSteer', 'A', [('neg',)]),
        ('IA_AirshipSteer', 'Gamepad_LeftX', [('dz', 0.15, 1.0), ('exp', 1.6)]),
        ('IA_AirshipLift', 'SpaceBar', []), ('IA_AirshipLift', 'LeftControl', [('neg',)]), ('IA_AirshipLift', 'C', [('neg',)]),
        ('IA_AirshipLift', 'Gamepad_RightTriggerAxis', []), ('IA_AirshipLift', 'Gamepad_LeftTriggerAxis', [('neg',)]),
        ('IA_AirshipStrafe', 'E', []), ('IA_AirshipStrafe', 'Q', [('neg',)]),
        ('IA_AirshipStrafe', 'Gamepad_DPad_Right', []), ('IA_AirshipStrafe', 'Gamepad_DPad_Left', [('neg',)]),
        ('IA_AirshipBoost', 'LeftShift', []), ('IA_AirshipBoost', 'Gamepad_FaceButton_Bottom', []),
        ('IA_AirshipBrake', 'X', []), ('IA_AirshipBrake', 'Gamepad_FaceButton_Right', []),
        ('IA_AirshipFire', 'LeftMouseButton', []), ('IA_AirshipFire', 'Gamepad_RightShoulder', []),
        ('IA_AirshipLook', 'Mouse2D', [('copy_rotate',)]), ('IA_AirshipLook', 'Gamepad_Right2D', [('exp', 2.0)]),
        ('IA_AirshipZoom', 'MouseWheelAxis', []), ('IA_AirshipZoom', 'Gamepad_DPad_Up', []),
        ('IA_AirshipZoom', 'Gamepad_DPad_Down', [('neg',)]),
        ('IA_AirshipExit', 'F', []), ('IA_AirshipExit', 'Gamepad_FaceButton_Top', []),
        ('IA_AirshipAim', 'RightMouseButton', []), ('IA_AirshipAim', 'Gamepad_LeftShoulder', []),
    ],
    'IMC_AirshipBoard': [
        ('IA_AirshipBoard', 'F', []), ('IA_AirshipBoard', 'Gamepad_FaceButton_Top', []),
    ],
}


def _as01_get_or_create(name, cls, factory):
    path = '%s/%s' % (AS_IN, name)
    if _eal.does_asset_exist(path):
        a = _eal.load_asset(path)
        if a is not None and isinstance(a, cls):
            return a, False
        raise RuntimeError('%s exists but is not a %s' % (path, cls.__name__))
    a = _at.create_asset(name, AS_IN, cls, factory)
    if a is None:
        raise RuntimeError('create_asset failed for ' + path)
    return a, True


def _as01_rotate_modifiers():
    """The modifiers of IA_Rotate's mapping(s) in IMC_PlayerMappings (class + editable props)."""
    imc = unreal.load_asset('/Game/Level/PlayerInput/IMC_PlayerMappings')
    out = []
    for m in imc.get_editor_property('default_key_mappings').get_editor_property('mappings'):
        a = m.get_editor_property('action')
        if a and a.get_name() == 'IA_Rotate':
            out.append((m.get_editor_property('key').get_editor_property('key_name'), list(m.get_editor_property('modifiers'))))
    return out


def _as01_key(name):
    k = unreal.Key()
    k.import_text(name)
    if str(k.get_editor_property('key_name')) != name:
        raise RuntimeError('key %s did not import (%s)' % (name, k.get_editor_property('key_name')))
    return k


def _as01_make_mods(imc, specs, rotate_mods):
    mods = []
    for s in specs:
        if s[0] == 'neg':
            mods.append(unreal.new_object(unreal.InputModifierNegate, imc))
        elif s[0] == 'dz':
            m = unreal.new_object(unreal.InputModifierDeadZone, imc)
            m.set_editor_property('lower_threshold', s[1])
            m.set_editor_property('upper_threshold', s[2])
            mods.append(m)
        elif s[0] == 'exp':
            m = unreal.new_object(unreal.InputModifierResponseCurveExponential, imc)
            m.set_editor_property('curve_exponent', unreal.Vector(s[1], s[1], s[1]))
            mods.append(m)
        elif s[0] == 'copy_rotate':
            for src in rotate_mods:
                m = unreal.new_object(type(src), imc)
                # copy every editable property the source has
                for p in ('lower_threshold', 'upper_threshold', 'type', 'curve_exponent', 'scalar', 'order', 'b_x', 'b_y', 'b_z'):
                    try:
                        m.set_editor_property(p, src.get_editor_property(p))
                    except Exception:
                        pass
                mods.append(m)
    return mods


def _as01_describe_mod(m):
    n = type(m).__name__.replace('InputModifier', '')
    try:
        if n == 'DeadZone':
            return 'DeadZone(%.2f..%.2f, %s)' % (m.get_editor_property('lower_threshold'), m.get_editor_property('upper_threshold'),
                                                 str(m.get_editor_property('type')).split('.')[-1])
        if n == 'ResponseCurveExponential':
            v = m.get_editor_property('curve_exponent')
            return 'ResponseCurveExponential(%.2f, %.2f, %.2f)' % (v.x, v.y, v.z)
        if n == 'Negate':
            return 'Negate(%s, outer=%s)' % (unreal.ToolsetLibrary.get_object_properties(m, ['bX', 'bY', 'bZ']).replace('\n', '').replace('\t', ''),
                                             m.get_outer().get_name())
    except Exception as e:
        return n + '(?%r)' % e
    return n


def as01_run():
    report = []
    actions = {}
    for name, vt in AS_ACTIONS:
        a, new = _as01_get_or_create(name, unreal.InputAction, unreal.InputAction_Factory())
        a.set_editor_property('value_type', vt)
        actions[name] = a
        report.append('%s %s value_type=%s consume=%s' % ('created' if new else 'reused ', name, str(vt).split('.')[-1],
                                                           a.get_editor_property('consume_input')))
    rot = _as01_rotate_modifiers()
    report.append('IMC_PlayerMappings IA_Rotate mappings: %s' % [(str(k), [type(x).__name__ for x in ms]) for k, ms in rot])
    rot_mods = [m for k, ms in rot for m in ms if str(k) == 'Mouse2D'] or [m for k, ms in rot for m in ms]
    saved = [a.get_path_name().split('.')[0] for a in actions.values()]
    for imc_name, maps in AS_IMC.items():
        imc, new = _as01_get_or_create(imc_name, unreal.InputMappingContext, unreal.InputMappingContext_Factory())
        imc.unmap_all()
        for an, key, specs in maps:
            imc.map_key(actions[an], _as01_key(key))
        data = imc.get_editor_property('default_key_mappings')
        ml = list(data.get_editor_property('mappings'))
        if len(ml) != len(maps):
            raise RuntimeError('%s: %d mappings after map_key, expected %d' % (imc_name, len(ml), len(maps)))
        for i, (an, key, specs) in enumerate(maps):
            m = ml[i]
            if m.get_editor_property('action').get_name() != an or str(m.get_editor_property('key').get_editor_property('key_name')) != key:
                raise RuntimeError('%s mapping %d order mismatch' % (imc_name, i))
            m.set_editor_property('modifiers', _as01_make_mods(imc, specs, rot_mods))
            m.set_editor_property('triggers', [])
            ml[i] = m
        data.set_editor_property('mappings', ml)
        imc.set_editor_property('default_key_mappings', data)
        imc.modify()
        saved.append('%s/%s' % (AS_IN, imc_name))
        report.append('%s %s' % ('created' if new else 'rebuilt', imc_name))
    for p in saved:
        ok = _eal.save_asset(p, only_if_is_dirty=False)
        report.append('saved %s %s' % (p, ok))
    return report


def as01_verify():
    out = []
    for imc_name in AS_IMC:
        imc = unreal.load_asset('%s/%s' % (AS_IN, imc_name))
        ml = imc.get_editor_property('default_key_mappings').get_editor_property('mappings')
        out.append('%s: %d mappings' % (imc_name, len(ml)))
        for m in ml:
            a = m.get_editor_property('action')
            out.append('  %-20s %-26s mods=[%s] trig=%s | IA type=%s consume=%s' % (
                a.get_name(), m.get_editor_property('key').get_editor_property('key_name'),
                ', '.join(_as01_describe_mod(x) for x in m.get_editor_property('modifiers')),
                [type(t).__name__ for t in m.get_editor_property('triggers')],
                str(a.get_editor_property('value_type')).split('.')[-1], a.get_editor_property('consume_input')))
    return out


if not globals().get('AS01_VERIFY_ONLY'):
    for l in as01_run():
        print(l)
print('---- verify (read back from the saved assets)')
for l in as01_verify():
    print(l)
