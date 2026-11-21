# bw_03_physics_asset.py - PA_Burrower: create (or reuse), build, verify, assign to SK_Burrower, save.
# EDITOR_SESSION.md step 3 / control_rig_recipe.md Step 1.3.
# Run in the clone editor through the inbox harness (not PIE):
#   Docs/Burrower/scripts/harness/inbox.sh 03 Docs/Burrower/scripts/bw_03_physics_asset.py 300
# Then the simulation check: bw_03b_sim_test.py (starts SIE), later bw_03c_sim_result.py.
# grep the output for PASS:/FAIL:/WARN:/INFO:.
#
# Route (all read in the UE 5.8 source; file:line refs in the report):
#  * PA asset: AssetTools.create_asset(name, folder, PhysicsAsset, factory=None) is a plain NewObject (AssetTools.cpp
#    1787); PhysicsAssetFactory would open modal dialogs (PhysicsAssetFactory.cpp 79/126). The asset starts with an
#    empty CollisionDisableTable. Re-runs REUSE PA_Burrower (it is referenced by SK_Burrower): every body and
#    constraint is removed and rebuilt.
#  * UPhysicsAsset::SkeletalBodySetups / ConstraintSetup are UPROPERTY(instanced) without Edit flags, so neither
#    Python nor ToolsetLibrary can touch them. The PhysicsToolsets plugin's UPhysicsAssetToolset (AICallable statics,
#    no BlueprintCallable, so no Python glue) does the array work and refreshes UpdateBodySetupIndexMap /
#    UpdateBoundsBodiesArray / RefreshPhysicsAssetChange. It is called through
#    unreal.ToolsetRegistry.execute_tool('PhysicsToolsets.PhysicsAssetToolset', Tool, json) (fallback: call_method
#    on the toolset CDO). Tools used: GetBodyNames, RemoveBody, GetConstraints, RemoveConstraint, AddBody, SetCapsule,
#    (SetBox), AddConstraint, Set/GetBodyPhysicsMode, GetBodyShapes.
#  * What the toolset leaves wrong is fixed with unreal.ToolsetLibrary.set_object_properties on the new
#    sub-objects: AddConstraint leaves both constraint frames at the bone origins (identity) and bDisableCollision
#    false (default), and its SetConstraintLimits never updates the template's DefaultProfile, which is what gets
#    SAVED (PhysicsConstraintTemplate.cpp 36-39) and what PIE/ControlRigPhysics use (SkeletalMeshComponentPhysics.cpp
#    1127, RigPhysicsExecution.cpp 535). set_object_properties sends PostEditChangeChainProperty per field, which
#    runs UPhysicsConstraintTemplate::UpdateProfileInstance -> DefaultProfile in sync. Bodies get
#    CollisionTraceFlag = UseSimpleAsComplex like the editor's own CreateNewBody (PhysicsAssetUtils.cpp 113), so
#    complex traces (MyPlayerController2.cpp bTraceComplex) hit them.
#  * Capsules are converted from component space with the bones' reference-pose globals (AnimPose of SKEL_Burrower,
#    fallback: transient SkeletalMeshComponent ref pose). FKSphylElem long axis = element local Z.
#  * Constraint frames as FConstraintInstance::SnapTransformsToDefault does: frame 1 = child bone (identity),
#    frame 2 = child bone relative to parent bone.
# Known limit: PreviewSkeletalMesh of a fresh PA cannot be set from Python (UPROPERTY() without Edit). The first
# time the Physics Asset Editor opens PA_Burrower it warns and shows a cube: pick SK_Burrower as Preview Mesh in its
# toolbar and save (see manual steps). CREATE_VIA_AUTOGEN_FOR_PREVIEW_MESH avoids that at a cost (see below).
import unreal, json, math, time, traceback


def _bw03_module():
    """All code lives in this function scope: the inbox harness execs every script in one shared namespace."""
    import unreal, json, math, time, traceback  # local: closures below never see names rebound by other inbox scripts

    # ----------------------------------------------------------------------------------------------- settings
    FOLDER = '/Game/Assets/Enemies/Burrower'
    SK_PATH = FOLDER + '/SK_Burrower'
    PA_NAME = 'PA_Burrower'
    PA_PATH = FOLDER + '/' + PA_NAME
    PA_OBJ = PA_PATH + '.' + PA_NAME

    # Opt-in: a kinematic box body on Rotor (recipe default: none; a simulated Rotor body parented to root would fall
    # off in the C++ fallback ragdoll; kinematic it stays on the animated Rotor bone). Its shape is made QueryOnly
    # because it overlaps the J0 capsule without a constraint. ControlRigPhysics ignores it (BonesToUse = J0..J4).
    ADD_ROTOR_BOX = False
    ROTOR_CENTRE_CS = (977.9, 0.0, 180.5)       # rig info centre_m * 100
    ROTOR_BOX_FULL_EXTENT = (55.8, 211.6, 211.6)  # X depth, Y/Z = disc diameter (rig info depth_m / radius_m)

    # Opt-in: first creation through SkeletalMeshEditorSubsystem.create_physics_asset (+ rename) so the PA gets its
    # PreviewSkeletalMesh. Cost: the auto-generated CollisionDisableTable pairs stay (index pairs, not reachable from
    # Python, RemoveBody does not clean them) and may disable some self-collision pairs among the 5 bodies.
    CREATE_VIA_AUTOGEN_FOR_PREVIEW_MESH = False

    SAVE_IF_CHECKS_FAIL = False
    LIMIT_DEG = 20.0
    # Swing/twist limits stay SOFT like every editor-made constraint (FConeConstraint/FTwistConstraint ctors:
    # bSoftConstraint true, stiffness 50, damping 5; ConstraintTypes.cpp 54-70). True = hard 20 deg limits.
    HARD_ANGULAR_LIMITS = False
    TOL_CM = 2.0          # capsule centre/radius/length tolerance (task)
    TOL_FRAME_CM = 0.5    # constraint frame position tolerance
    TOL_DEG = 0.5         # axis tolerance

    # bone, component-space centre (cm), radius, core length along component X (control_rig_recipe.md Step 1.3)
    BODIES = [
        ('J0_Head',         (830.0, 0.0, 187.0), 160.0, 40.0),
        ('J1_Forequarters', (460.0, 0.0, 195.0), 185.0, 30.0),
        ('J2_Midbody',      (0.0,   0.0, 200.0), 175.0, 170.0),
        ('J3_Hindbody',     (-410.0, 0.0, 210.0), 125.0, 50.0),
        ('J4_Tail',         (-785.0, 0.0, 205.0), 85.0, 290.0),
    ]
    # (child = ConstraintBone1, parent = ConstraintBone2)
    JOINTS = [('J1_Forequarters', 'J0_Head'), ('J2_Midbody', 'J1_Forequarters'),
              ('J3_Hindbody', 'J2_Midbody'), ('J4_Tail', 'J3_Hindbody')]
    EXPECT_BONE_POS = {'J0_Head': (1000, 0, 180), 'J1_Forequarters': (660, 0, 193), 'J2_Midbody': (260, 0, 200),
                       'J3_Hindbody': (-260, 0, 200), 'J4_Tail': (-560, 0, 202), 'Rotor': (977.9, 0, 180.5)}
    EXPECT_PARENT = {'J0_Head': 'root', 'J1_Forequarters': 'J0_Head', 'J2_Midbody': 'J1_Forequarters',
                     'J3_Hindbody': 'J2_Midbody', 'J4_Tail': 'J3_Hindbody', 'Rotor': 'root'}
    TOOLSET = 'PhysicsToolsets.PhysicsAssetToolset'
    TOOLSET_CLASS = '/Script/PhysicsToolsets.PhysicsAssetToolset'

    # enum values (PhysicsCore/Public/Chaos/ChaosEngineInterface.h 113/186, BodySetupEnums.h)
    ACM_LIMITED, LCM_LOCKED = 1, 2
    PHYS_DEFAULT, PHYS_KINEMATIC = 0, 1
    BODY_COLLISION_ENABLED = 0
    CTF_USE_SIMPLE_AS_COMPLEX = 2
    QUERY_ONLY = 1  # ECollisionEnabled::QueryOnly (EngineTypes.h)

    _BW03 = {'fail': 0, 'warn': 0, 'mode': None, 'cdo': None, 'pa': None}


    def _p(tag, msg):
        if tag == 'FAIL':
            _BW03['fail'] += 1
        elif tag == 'WARN':
            _BW03['warn'] += 1
        print('%s: %s' % (tag, msg))


    # ----------------------------------------------------------------------------------------------- math (UE conventions)
    def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
    def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
    def _cmul(a, b): return (a[0] * b[0], a[1] * b[1], a[2] * b[2])
    def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    def _len(a): return math.sqrt(_dot(a, a))


    def _unit(a):
        n = _len(a)
        return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


    def _ang(a, b):
        a, b = _unit(a), _unit(b)
        return math.degrees(math.acos(max(-1.0, min(1.0, _dot(a, b)))))


    def _qnorm(q):
        n = math.sqrt(sum(c * c for c in q))
        return tuple(c / n for c in q) if n > 1e-12 else (0.0, 0.0, 0.0, 1.0)


    def _qconj(q): return (-q[0], -q[1], -q[2], q[3])


    def _qmul(a, b):  # (a*b).rotate(v) == a.rotate(b.rotate(v)), same as FQuat operator*
        ax, ay, az, aw = a; bx, by, bz, bw = b
        return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


    def _qrot(q, v):  # FQuat::RotateVector
        q = _qnorm(q); u = (q[0], q[1], q[2]); w = q[3]
        t = _mul(_cross(u, v), 2.0)
        return _add(_add(v, _mul(t, w)), _cross(u, t))


    def _qirot(q, v): return _qrot(_qconj(_qnorm(q)), v)


    def _rot_axes(p, y, r):  # rows of FRotationTranslationMatrix (RotationTranslationMatrix.h 72-85): X, Y, Z axes
        sp, cp = math.sin(math.radians(p)), math.cos(math.radians(p))
        sy, cy = math.sin(math.radians(y)), math.cos(math.radians(y))
        sr, cr = math.sin(math.radians(r)), math.cos(math.radians(r))
        return ((cp * cy, cp * sy, sp),
                (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp),
                (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp))


    def _rotator_from_axes(X, Y, Z):  # FMatrix::Rotator
        p = math.degrees(math.atan2(X[2], math.sqrt(X[0] ** 2 + X[1] ** 2)))
        y = math.degrees(math.atan2(X[1], X[0]))
        sy_axis = _rot_axes(p, y, 0.0)[1]
        return (p, y, math.degrees(math.atan2(_dot(Z, sy_axis), _dot(Y, sy_axis))))


    def _rotator_from_z(a):  # rotator (pitch, yaw, roll=0) whose Z axis is a
        a = _unit(a); h = math.sqrt(a[0] ** 2 + a[1] ** 2)
        if h < 1e-9:
            return (0.0, 0.0, 0.0) if a[2] > 0 else (180.0, 0.0, 0.0)
        return (math.degrees(math.atan2(-h, a[2])), math.degrees(math.atan2(a[1], a[0])), 0.0)


    def _vt(v): return (float(v.x), float(v.y), float(v.z))
    def _xf(t): return (_vt(t.translation), (float(t.rotation.x), float(t.rotation.y), float(t.rotation.z), float(t.rotation.w)), _vt(t.scale3d))
    def _fmt(v): return '(%.1f, %.1f, %.1f)' % tuple(v)
    def _vj(v): return {'X': float(v[0]), 'Y': float(v[1]), 'Z': float(v[2])}


    def _jv(d):  # lower-cased JSON vector dict -> tuple
        return (float(d.get('x', 0.0)), float(d.get('y', 0.0)), float(d.get('z', 0.0)))


    def _lower(o):
        if isinstance(o, dict):
            return {str(k).lower(): _lower(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_lower(v) for v in o]
        return o


    def _enum_is(v, num, word):
        """True if a JSON/Python enum value is number num or a name containing word (case-insensitive)."""
        if v is None:
            return False
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return int(v) == num
        val = getattr(v, 'value', None)
        if val is not None and not isinstance(v, str):
            try:
                return int(val) == num
            except Exception:
                pass
        return word.lower() in str(getattr(v, 'name', v)).lower()


    # ----------------------------------------------------------------------------------------------- reference pose
    def _ref_globals(skm, bones):
        """bone -> (T, Q(x,y,z,w), S) in component space, from the reference pose. Returns (dict, route, all_names)."""
        out, names, route = {}, [], None
        try:  # UAnimPoseExtensions (AnimationBlueprintLibrary/Public/AnimPose.h 193/329), World = component space
            skel = skm.get_editor_property('skeleton')
            pose = unreal.AnimPoseExtensions.get_reference_pose(skel)
            names = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
            for b in bones:
                if b in names:
                    out[b] = _xf(unreal.AnimPoseExtensions.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD))
            route = 'AnimPose reference pose of ' + skel.get_name()
        except Exception as e:
            _p('WARN', 'AnimPose reference pose failed (%r); trying a transient SkeletalMeshComponent' % (e,))
        if route and all(b in out for b in bones):
            return out, route, names
        try:  # USkinnedMeshComponent GetBoneIndex/GetParentBone/GetRefPoseTransform (SkinnedMeshComponent.h 1156/1263/2053)
            comp = unreal.new_object(unreal.SkeletalMeshComponent)
            comp.set_skeletal_mesh_asset(skm)
            n = comp.get_num_bones()
            names = [str(comp.get_bone_name(i)) for i in range(n)]
            cache = {}

            def glob(b):
                if b in cache:
                    return cache[b]
                loc = _xf(comp.get_ref_pose_transform(comp.get_bone_index(b)))
                par = str(comp.get_parent_bone(b))
                if par in ('None', ''):
                    g = loc
                else:
                    pt, pq, ps = glob(par)
                    g = (_add(pt, _qrot(pq, _cmul(ps, loc[0]))), _qnorm(_qmul(pq, loc[1])), _cmul(ps, loc[2]))
                cache[b] = g
                return g
            for b in bones:
                if b in names:
                    out[b] = glob(b)
            route = 'transient SkeletalMeshComponent ref pose'
        except Exception as e:
            _p('FAIL', 'cannot read the reference pose of SK_Burrower (%r)' % (e,))
        return out, route, names


    # ----------------------------------------------------------------------------------------------- toolset access
    class _Vec(tuple): pass
    class _Rot(tuple): pass          # (pitch, yaw, roll)
    class _Mode(int): pass           # EBodyPhysicsMode: 0 Default, 1 Kinematic, 2 Simulated
    class _PARef(object): pass
    _PA = _PARef()


    def _tool_init():
        try:
            if unreal.ToolsetRegistry.is_toolset_registered(TOOLSET):
                _BW03['mode'] = 'registry'
                return True
            _p('WARN', 'toolset %s not registered (filtered or plugin off?); trying call_method on its CDO' % TOOLSET)
        except Exception as e:
            _p('WARN', 'ToolsetRegistry not usable (%r); trying call_method on the toolset CDO' % (e,))
        try:
            cls = unreal.load_class(None, TOOLSET_CLASS)
            _BW03['cdo'] = unreal.get_default_object(cls)
            _BW03['mode'] = 'call_method'
            return True
        except Exception as e:
            _p('FAIL', 'PhysicsAssetToolset not available (%r). Enable the PhysicsToolsets plugin (AllToolsets enables it) '
                   'and restart the editor.' % (e,))
            return False


    def _to_json(v):
        if isinstance(v, _PARef):
            return PA_OBJ
        if isinstance(v, _Vec):
            return _vj(v)
        if isinstance(v, _Rot):
            return {'Pitch': float(v[0]), 'Yaw': float(v[1]), 'Roll': float(v[2])}
        if isinstance(v, _Mode):
            return int(v)
        return v


    def _to_py(v):
        if isinstance(v, _PARef):
            return _BW03['pa']
        if isinstance(v, _Vec):
            return unreal.Vector(float(v[0]), float(v[1]), float(v[2]))
        if isinstance(v, _Rot):
            return unreal.Rotator(roll=float(v[2]), pitch=float(v[0]), yaw=float(v[1]))
        if isinstance(v, _Mode):
            return getattr(unreal.BodyPhysicsMode, ['DEFAULT', 'KINEMATIC', 'SIMULATED'][int(v)])
        return v


    _STRUCT_FIELDS = [('shapename', 'ShapeName', 'shape_name'), ('shapetype', 'ShapeType', 'shape_type'),
                      ('center', 'Center', 'center'), ('rotation', 'Rotation', 'rotation'), ('radius', 'Radius', 'radius'),
                      ('length', 'Length', 'length'), ('extentx', 'ExtentX', 'extent_x'), ('extenty', 'ExtentY', 'extent_y'),
                      ('extentz', 'ExtentZ', 'extent_z'), ('bone1name', 'Bone1Name', 'bone1_name'),
                      ('bone2name', 'Bone2Name', 'bone2_name'), ('swing1motion', 'Swing1Motion', 'swing1_motion'),
                      ('swing1limitdegrees', 'Swing1LimitDegrees', 'swing1_limit_degrees'),
                      ('swing2motion', 'Swing2Motion', 'swing2_motion'),
                      ('swing2limitdegrees', 'Swing2LimitDegrees', 'swing2_limit_degrees'),
                      ('twistmotion', 'TwistMotion', 'twist_motion'),
                      ('twistlimitdegrees', 'TwistLimitDegrees', 'twist_limit_degrees')]


    def _from_py(o):
        if o is None or isinstance(o, (bool, int, float, str)):
            return o
        if isinstance(o, (list, tuple)):
            return [_from_py(x) for x in o]
        if isinstance(o, unreal.Vector):
            return {'x': o.x, 'y': o.y, 'z': o.z}
        if isinstance(o, unreal.Rotator):
            return {'pitch': o.pitch, 'yaw': o.yaw, 'roll': o.roll}
        if hasattr(o, 'value') and hasattr(o, 'name') and not hasattr(o, 'get_editor_property'):
            return str(o.name)
        if isinstance(o, unreal.Name):
            return str(o)
        if hasattr(o, 'get_editor_property'):  # PhysicsShapeInfo / PhysicsConstraintInfo structs
            d = {}
            for key, cpp, py in _STRUCT_FIELDS:
                val, ok = None, False
                for nm in (cpp, py):
                    try:
                        val = o.get_editor_property(nm); ok = True
                        break
                    except Exception:
                        pass
                if ok:
                    d[key] = _from_py(val)
            return d
        return str(o)


    def _tool(fn, params):
        """Call a PhysicsAssetToolset tool. params: list of (C++ param name, value). Returns the lower-cased result."""
        if _BW03['mode'] == 'registry':
            js = json.dumps({k: _to_json(v) for k, v in params})
            res = unreal.ToolsetRegistry.execute_tool(TOOLSET, fn, js)
            err = str(res.get_editor_property('error') or '')
            if err:
                raise RuntimeError('%s(%s) -> %s' % (fn, js, err))
            if not res.get_editor_property('is_complete'):
                raise RuntimeError('%s did not complete synchronously' % fn)
            raw = str(res.get_editor_property('value') or '')
            if not raw:
                return None
            d = _lower(json.loads(raw))
            return d.get('returnvalue') if isinstance(d, dict) else d
        out = _BW03['cdo'].call_method(fn, tuple(_to_py(v) for k, v in params))
        return _lower(_from_py(out))


    def t_names(): return [str(n) for n in (_tool('GetBodyNames', [('PhysicsAsset', _PA)]) or [])]
    def t_shapes(b): return _tool('GetBodyShapes', [('PhysicsAsset', _PA), ('BoneName', b)]) or []
    def t_add_body(b): _tool('AddBody', [('PhysicsAsset', _PA), ('BoneName', b)])
    def t_remove_body(b): _tool('RemoveBody', [('PhysicsAsset', _PA), ('BoneName', b)])
    def t_constraints(): return _tool('GetConstraints', [('PhysicsAsset', _PA)]) or []
    def t_add_constraint(c, p): _tool('AddConstraint', [('PhysicsAsset', _PA), ('Bone1Name', c), ('Bone2Name', p)])
    def t_remove_constraint(a, b): _tool('RemoveConstraint', [('PhysicsAsset', _PA), ('Bone1Name', a), ('Bone2Name', b)])
    def t_set_mode(b, m): _tool('SetBodyPhysicsMode', [('PhysicsAsset', _PA), ('BoneName', b), ('Mode', _Mode(m))])
    def t_get_mode(b): return _tool('GetBodyPhysicsMode', [('PhysicsAsset', _PA), ('BoneName', b)])


    def t_set_capsule(b, name, c, rot, r, l):
        _tool('SetCapsule', [('PhysicsAsset', _PA), ('BoneName', b), ('ShapeName', name), ('Center', _Vec(c)),
                             ('Rotation', _Rot(rot)), ('Radius', float(r)), ('Length', float(l))])


    def t_set_box(b, name, c, rot, ex, ey, ez):
        _tool('SetBox', [('PhysicsAsset', _PA), ('BoneName', b), ('ShapeName', name), ('Center', _Vec(c)),
                         ('Rotation', _Rot(rot)), ('ExtentX', float(ex)), ('ExtentY', float(ey)), ('ExtentZ', float(ez))])


    # ----------------------------------------------------------------------------------------------- object helpers
    def _children(pa, cls):
        """All loaded objects of cls whose outer is pa (live and removed ones), keyed by path name."""
        pp, out = pa.get_path_name(), {}
        for o in unreal.ObjectIterator(cls):
            try:
                ou = o.get_outer()
                if ou is not None and ou.get_path_name() == pp:
                    out[o.get_path_name()] = o
            except Exception:
                pass
        return out


    def _get_props(obj, names):
        raw = unreal.ToolsetLibrary.get_object_properties(obj, names)
        return _lower(json.loads(raw)) if raw else {}


    def _set_props(obj, d):
        ok = unreal.ToolsetLibrary.set_object_properties(obj, json.dumps(d))
        return bool(ok)


    def _strip_acc(res):
        """Python returns (out params...) for the BP library getters; drop the UPARAM(ref) accessor."""
        if not isinstance(res, tuple):
            res = (res,)
        return [x for x in res if not isinstance(x, unreal.ConstraintInstanceAccessor)]


    def _bool_ret(res):
        if res is None:
            return False
        if isinstance(res, bool):
            return res
        if isinstance(res, tuple):
            b = [x for x in res if isinstance(x, bool)]
            return b[0] if b else True
        return True  # the accessor itself: the function returned true


    def _accessor_read(pa, child, parent):
        """Limits through UPhysicsAsset::GetConstraintByBoneNames + UConstraintInstanceBlueprintLibrary (editor build).
        The accessor's OnRelease runs UpdateProfileInstance; it is dropped before returning (no stale index later)."""
        lib = unreal.ConstraintInstanceBlueprintLibrary
        acc = pa.get_constraint_by_bone_names(child, parent)
        try:
            names = _strip_acc(lib.get_attached_body_names(acc))
            ang = _strip_acc(lib.get_angular_limits(acc))
            lin = _strip_acc(lib.get_linear_limits(acc))
            # bool return + ref param: Python returns the accessor for True and None for False (PyGenUtil.cpp 1161)
            dis = lib.get_disable_collsion(acc)
            return {'parent': str(names[0]) if names else '', 'child': str(names[1]) if len(names) > 1 else '',
                    'ang': ang, 'lin': lin, 'disable_collision': _bool_ret(dis)}
        finally:
            del acc


    def _enum_member(enum_cls, word):
        for nm in dir(enum_cls):
            if nm.isupper() and word in nm:
                return getattr(enum_cls, nm)
        return None


    def _accessor_write(pa, child, parent):
        """Fallback writer for limits/collision through the BP library (accessor release syncs DefaultProfile)."""
        lib = unreal.ConstraintInstanceBlueprintLibrary
        lim = _enum_member(unreal.AngularConstraintMotion, 'LIMITED')
        lock = _enum_member(unreal.LinearConstraintMotion, 'LOCKED')
        acc = pa.get_constraint_by_bone_names(child, parent)
        try:
            lib.set_angular_limits(acc, lim, LIMIT_DEG, lim, LIMIT_DEG, lim, LIMIT_DEG)
            lib.set_linear_limits(acc, lock, lock, lock, 0.0)
            lib.set_disable_collision(acc, True)
        finally:
            del acc


    # ----------------------------------------------------------------------------------------------- build steps
    def _get_or_create_pa(skm):
        eal = unreal.EditorAssetLibrary
        existing = None
        try:
            if eal.does_asset_exist(PA_PATH):
                existing = unreal.load_asset(PA_PATH)
        except Exception as e:
            _p('WARN', 'does_asset_exist/load_asset(%s) raised %r' % (PA_PATH, e))
        if existing is None:
            existing = unreal.find_object(None, PA_OBJ)
        if existing is not None:
            if not isinstance(existing, unreal.PhysicsAsset) or existing.get_path_name() != PA_OBJ:
                _p('FAIL', '%s exists but is %s at %s (not a PhysicsAsset here). Not touching it; delete it by hand.'
                   % (PA_PATH, existing.get_class().get_name(), existing.get_path_name()))
                return None
            _p('INFO', 'reusing existing %s: all bodies and constraints are removed and rebuilt (keeps the preview mesh '
                       'and the reference from SK_Burrower)' % PA_PATH)
            return existing
        if CREATE_VIA_AUTOGEN_FOR_PREVIEW_MESH:
            tmp_path = FOLDER + '/SK_Burrower_PhysicsAsset'
            if eal.does_asset_exist(tmp_path):
                _p('FAIL', '%s already exists; CREATE_VIA_AUTOGEN_FOR_PREVIEW_MESH would regenerate and rename it. '
                           'Delete it by hand or set the flag False.' % tmp_path)
                return None
            smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
            tmp = smes.create_physics_asset(skm, False, 0)  # SkeletalMeshEditorSubsystem.h 325, sets PreviewSkeletalMesh
            if not tmp:
                _p('FAIL', 'SkeletalMeshEditorSubsystem.create_physics_asset returned None (see the log)')
                return None
            if not eal.rename_loaded_asset(tmp, PA_PATH):
                _p('FAIL', 'rename %s -> %s failed; %s is left in the folder' % (tmp.get_path_name(), PA_PATH, tmp_path))
                return None
            _p('WARN', 'created through auto-generation + rename: preview mesh set, but the auto CollisionDisableTable '
                       'pairs are kept (not reachable from Python)')
            return unreal.load_asset(PA_PATH)
        at = unreal.AssetToolsHelpers.get_asset_tools()
        pa = at.create_asset(PA_NAME, FOLDER, unreal.PhysicsAsset, None)
        if not pa:
            _p('FAIL', 'AssetTools.create_asset(%s) returned None (see the log)' % PA_PATH)
            return None
        _p('INFO', 'created new empty %s (no factory: no dialog, empty CollisionDisableTable)' % PA_PATH)
        return pa


    def _clear(pa):
        names = t_names()
        for n in names:
            t_remove_body(n)
        for c in t_constraints():
            try:
                t_remove_constraint(c.get('bone1name'), c.get('bone2name'))
            except Exception as e:
                _p('WARN', 'RemoveConstraint %s-%s: %r' % (c.get('bone1name'), c.get('bone2name'), e))
        left_b, left_c = t_names(), t_constraints()
        if left_b or left_c:
            _p('FAIL', 'could not clear the asset: bodies %s, constraints %d' % (left_b, len(left_c)))
            return False
        _p('INFO', 'cleared %d old bodies (and their constraints)' % len(names))
        return True


    def _capsule_local(g, centre_cs):
        t, q, s = g
        c_local = _qirot(q, _sub(centre_cs, t))
        c_local = (c_local[0] / s[0], c_local[1] / s[1], c_local[2] / s[2])
        a_local = _qirot(q, (1.0, 0.0, 0.0))
        return c_local, _rotator_from_z(a_local)


    def _build_bodies(pa, G):
        bcls = unreal.load_class(None, '/Script/Engine.SkeletalBodySetup')
        before = _children(pa, bcls)
        plan = list(BODIES)
        for bone, centre, r, l in plan:
            t_add_body(bone)
            c_local, rot = _capsule_local(G[bone], centre)
            t_set_capsule(bone, bone + '_capsule', c_local, rot, r, l)
            _p('INFO', 'body %-16s capsule local centre %s rot (P %.2f, Y %.2f, R %.2f) r %.0f len %.0f'
               % (bone, _fmt(c_local), rot[0], rot[1], rot[2], r, l))
        if ADD_ROTOR_BOX:
            t, q, s = G['Rotor']
            c_local = _qirot(q, _sub(ROTOR_CENTRE_CS, t))
            rot = _rotator_from_axes(_qirot(q, (1, 0, 0)), _qirot(q, (0, 1, 0)), _qirot(q, (0, 0, 1)))
            t_add_body('Rotor')
            t_set_box('Rotor', 'Rotor_box', c_local, rot, *ROTOR_BOX_FULL_EXTENT)
            _p('INFO', 'body Rotor box local centre %s extents %s (kinematic)' % (_fmt(c_local), _fmt(ROTOR_BOX_FULL_EXTENT)))
        after = _children(pa, bcls)
        new = [o for k, o in after.items() if k not in before]
        objs = {}
        for o in new:
            try:
                bn = str(_get_props(o, ['BoneName']).get('bonename'))
                objs[bn] = o
            except Exception as e:
                _p('WARN', 'cannot read BoneName of %s: %r' % (o.get_path_name(), e))
        wanted = [b[0] for b in plan] + (['Rotor'] if ADD_ROTOR_BOX else [])
        for bone in wanted:
            o = objs.get(bone)
            if o is None:
                _p('WARN', 'new body object for %s not found; PhysicsType/CollisionReponse/CollisionTraceFlag stay at '
                           'their defaults (Default/Enabled/ProjectDefault)' % bone)
                continue
            ptype = PHYS_KINEMATIC if bone == 'Rotor' else PHYS_DEFAULT
            if not _set_props(o, {'PhysicsType': ptype, 'CollisionReponse': BODY_COLLISION_ENABLED,
                                  'CollisionTraceFlag': CTF_USE_SIMPLE_AS_COMPLEX}):
                _p('WARN', 'ToolsetLibrary.set_object_properties on body %s returned False (see the log)' % bone)
            if bone == 'Rotor':
                # The Rotor box overlaps the J0 capsule and has no constraint (CollisionDisableTable is not reachable
                # from Python), so its shape is QueryOnly (FKShapeElem::CollisionEnabled, ShapeElem.h 163): traces hit
                # it, physics contacts never happen.
                if not _set_props(o, {'AggGeom': {'BoxElems': [{'CollisionEnabled': QUERY_ONLY}]}}):
                    _p('WARN', 'could not make the Rotor box QueryOnly: it may push J0_Head in a ragdoll')
        return objs


    def _frames(G, child, parent):
        tc, qc, _ = G[child]
        tp, qp, _ = G[parent]
        pos2 = _qirot(qp, _sub(tc, tp))
        pri2 = _qirot(qp, _qrot(qc, (1.0, 0.0, 0.0)))
        sec2 = _qirot(qp, _qrot(qc, (0.0, 1.0, 0.0)))
        return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), pos2, pri2, sec2


    def _constraint_json(G, child, parent):
        p1, a1, s1, p2, a2, s2 = _frames(G, child, parent)
        d = _constraint_json_base(child, parent, p1, a1, s1, p2, a2, s2)
        if HARD_ANGULAR_LIMITS:
            prof = d['DefaultInstance']['ProfileInstance']
            prof['ConeLimit']['bSoftConstraint'] = False   # FConstraintBaseParams (ConstraintTypes.h 35)
            prof['TwistLimit']['bSoftConstraint'] = False
        return d


    def _constraint_json_base(child, parent, p1, a1, s1, p2, a2, s2):
        return {'DefaultInstance': {
            'JointName': child, 'ConstraintBone1': child, 'ConstraintBone2': parent,
            'Pos1': _vj(p1), 'PriAxis1': _vj(a1), 'SecAxis1': _vj(s1),
            'Pos2': _vj(p2), 'PriAxis2': _vj(a2), 'SecAxis2': _vj(s2),
            'AngularRotationOffset': {'Pitch': 0.0, 'Yaw': 0.0, 'Roll': 0.0},
            'ProfileInstance': {
                'bDisableCollision': True,
                'LinearLimit': {'XMotion': LCM_LOCKED, 'YMotion': LCM_LOCKED, 'ZMotion': LCM_LOCKED, 'Limit': 0.0},
                'ConeLimit': {'Swing1Motion': ACM_LIMITED, 'Swing2Motion': ACM_LIMITED,
                              'Swing1LimitDegrees': LIMIT_DEG, 'Swing2LimitDegrees': LIMIT_DEG},
                'TwistLimit': {'TwistMotion': ACM_LIMITED, 'TwistLimitDegrees': LIMIT_DEG}}}}


    def _build_constraints(pa, G):
        ccls = unreal.load_class(None, '/Script/Engine.PhysicsConstraintTemplate')
        before = _children(pa, ccls)
        for child, parent in JOINTS:
            t_add_constraint(child, parent)
        after = _children(pa, ccls)
        new = [o for k, o in after.items() if k not in before]
        objs = {}
        for o in new:
            di = _get_props(o, ['DefaultInstance']).get('defaultinstance', {})
            objs[(str(di.get('constraintbone1')), str(di.get('constraintbone2')))] = o
        for child, parent in JOINTS:
            o = objs.get((child, parent))
            if o is None:
                _p('FAIL', 'new constraint template %s-%s not found among %d new objects; frames NOT set' % (child, parent, len(new)))
                continue
            if not _set_props(o, _constraint_json(G, child, parent)):
                _p('WARN', 'set_object_properties on constraint %s-%s returned False; trying the BP library for limits'
                   % (child, parent))
                try:
                    _accessor_write(pa, child, parent)
                except Exception as e:
                    _p('FAIL', 'BP library fallback for %s-%s failed: %r' % (child, parent, e))
        return objs


    # ----------------------------------------------------------------------------------------------- verification
    def _verify(pa, skm, G, bobjs, cobjs):
        want = [b[0] for b in BODIES] + (['Rotor'] if ADD_ROTOR_BOX else [])
        names = t_names()
        if sorted(names) == sorted(want):
            _p('PASS', 'body count = %d: %s' % (len(names), ', '.join(names)))
        else:
            _p('FAIL', 'bodies %s, expected %s' % (names, want))
        for bone, centre, r, l in BODIES:
            if bone not in names:
                continue
            shapes = t_shapes(bone)
            caps = [s for s in shapes if 'CAPSULE' in str(s.get('shapetype', '')).upper()]
            if len(shapes) != 1 or len(caps) != 1:
                _p('FAIL', '%s: expected exactly one capsule, got %s' % (bone, [s.get('shapetype') for s in shapes]))
                continue
            s = caps[0]
            t, q, sc = G[bone]
            c_local = _jv(s.get('center', {}))
            ro = s.get('rotation', {})
            z_local = _rot_axes(float(ro.get('pitch', 0)), float(ro.get('yaw', 0)), float(ro.get('roll', 0)))[2]
            c_cs = _add(t, _qrot(q, _cmul(sc, c_local)))
            axis_cs = _qrot(q, z_local)
            derr = _len(_sub(c_cs, centre))
            aerr = min(_ang(axis_cs, (1, 0, 0)), _ang(axis_cs, (-1, 0, 0)))
            rr, ll = float(s.get('radius', 0)), float(s.get('length', 0))
            ok = derr <= TOL_CM and abs(rr - r) <= TOL_CM and abs(ll - l) <= TOL_CM and aerr <= TOL_DEG
            half = ll * 0.5 + rr
            _p('PASS' if ok else 'FAIL', '%-16s centre %s (want %s, err %.2f cm) r %.1f (want %.0f) len %.1f (want %.0f) '
               'axis off X %.2f deg, covers x %.0f..%.0f'
               % (bone, _fmt(c_cs), _fmt(centre), derr, rr, r, ll, l, aerr, c_cs[0] - half, c_cs[0] + half))
        if ADD_ROTOR_BOX and 'Rotor' in names:
            boxes = [s for s in t_shapes('Rotor') if 'BOX' in str(s.get('shapetype', '')).upper()]
            _p('PASS' if len(boxes) == 1 else 'FAIL', 'Rotor box shapes: %d' % len(boxes))
            o = bobjs.get('Rotor')
            if o is not None:
                try:
                    be = (_get_props(o, ['AggGeom']).get('agggeom', {}).get('boxelems') or [{}])[0]
                    ce = be.get('collisionenabled')
                    _p('PASS' if _enum_is(ce, QUERY_ONLY, 'queryonly') else 'WARN', 'Rotor box shape collision = %s' % ce)
                except Exception as e:
                    _p('WARN', 'reading the Rotor box collision: %r' % (e,))
        for bone in want:
            if bone not in names:
                continue
            try:
                mode = t_get_mode(bone)
                wanted_mode = 'KINEMATIC' if bone == 'Rotor' else 'DEFAULT'
                _p('PASS' if wanted_mode in str(mode).upper() else 'FAIL', '%s Physics Type = %s' % (bone, mode))
            except Exception as e:
                _p('WARN', 'GetBodyPhysicsMode(%s): %r' % (bone, e))
            o = bobjs.get(bone)
            if o is not None:
                try:
                    pr = _get_props(o, ['CollisionReponse', 'CollisionTraceFlag'])
                    cr, tf = pr.get('collisionreponse'), pr.get('collisiontraceflag')
                    _p('PASS' if _enum_is(cr, BODY_COLLISION_ENABLED, 'enabled') else 'FAIL', '%s Collision Response = %s' % (bone, cr))
                    _p('PASS' if _enum_is(tf, CTF_USE_SIMPLE_AS_COMPLEX, 'simpleascomplex') else 'WARN',
                       '%s Collision Complexity = %s' % (bone, tf))
                except Exception as e:
                    _p('WARN', 'reading body props of %s: %r' % (bone, e))
        # constraints: toolset view
        cons = t_constraints()
        pairs = sorted((str(c.get('bone1name')), str(c.get('bone2name'))) for c in cons)
        if pairs == sorted(JOINTS):
            _p('PASS', '%d constraints: %s' % (len(cons), ', '.join('%s-%s' % p for p in pairs)))
        else:
            _p('FAIL', 'constraints %s, expected %s' % (pairs, sorted(JOINTS)))
        for c in cons:
            lim = all(_enum_is(c.get(k + 'motion'), ACM_LIMITED, 'limited') and
                      abs(float(c.get(k + 'limitdegrees', -1)) - LIMIT_DEG) < 0.01 for k in ('swing1', 'swing2', 'twist'))
            _p('PASS' if lim else 'FAIL', 'constraint %s-%s swing1 %s %.1f, swing2 %s %.1f, twist %s %.1f'
               % (c.get('bone1name'), c.get('bone2name'), c.get('swing1motion'), float(c.get('swing1limitdegrees', -1)),
                  c.get('swing2motion'), float(c.get('swing2limitdegrees', -1)), c.get('twistmotion'),
                  float(c.get('twistlimitdegrees', -1))))
        # constraints: frames + profile through the template's JSON
        for child, parent in JOINTS:
            o = cobjs.get((child, parent))
            if o is None:
                _p('FAIL', 'constraint %s-%s: template object not found, frames unchecked' % (child, parent))
                continue
            di = _get_props(o, ['DefaultInstance']).get('defaultinstance', {})
            tc, qc, _ = G[child]
            tp, qp, _ = G[parent]
            p1, a1, s1 = _jv(di.get('pos1', {})), _jv(di.get('priaxis1', {})), _jv(di.get('secaxis1', {}))
            p2, a2, s2 = _jv(di.get('pos2', {})), _jv(di.get('priaxis2', {})), _jv(di.get('secaxis2', {}))
            w1 = _add(tc, _qrot(qc, p1))
            w2 = _add(tp, _qrot(qp, p2))
            e_child = _len(_sub(w1, tc)); e_par = _len(_sub(w2, tc))
            e_pri = _ang(_qrot(qc, a1), _qrot(qp, a2)); e_sec = _ang(_qrot(qc, s1), _qrot(qp, s2))
            ok = e_child <= TOL_FRAME_CM and e_par <= TOL_FRAME_CM and e_pri <= TOL_DEG and e_sec <= TOL_DEG
            _p('PASS' if ok else 'FAIL', 'constraint %s-%s frames: joint at child origin (frame1 %.2f cm, frame2 %.2f cm), '
               'axes agree (%.2f / %.2f deg), joint at %s' % (child, parent, e_child, e_par, e_pri, e_sec, _fmt(w2)))
            pi = di.get('profileinstance', {})
            ll = pi.get('linearlimit', {})
            lin_ok = all(_enum_is(ll.get(k), LCM_LOCKED, 'locked') for k in ('xmotion', 'ymotion', 'zmotion'))
            _p('PASS' if lin_ok else 'FAIL', 'constraint %s-%s linear X/Y/Z = %s/%s/%s'
               % (child, parent, ll.get('xmotion'), ll.get('ymotion'), ll.get('zmotion')))
            _p('PASS' if pi.get('bdisablecollision') is True else 'FAIL',
               'constraint %s-%s collision between the two bodies disabled = %s' % (child, parent, pi.get('bdisablecollision')))
            cl, tl = pi.get('conelimit', {}), pi.get('twistlimit', {})
            _p('INFO', 'constraint %s-%s angular limits soft: swing %s (stiffness %s, damping %s), twist %s (stiffness %s, damping %s)'
               % (child, parent, cl.get('bsoftconstraint'), cl.get('stiffness'), cl.get('damping'),
                  tl.get('bsoftconstraint'), tl.get('stiffness'), tl.get('damping')))
        # constraints: engine BP library view (FConstraintInstanceAccessor on the asset)
        for child, parent in JOINTS:
            try:
                r = _accessor_read(pa, child, parent)
                ang, lin = r['ang'], r['lin']
                ok = (r['child'] == child and r['parent'] == parent and len(ang) == 6 and len(lin) == 4 and
                      all(_enum_is(ang[i], ACM_LIMITED, 'limited') and abs(float(ang[i + 1]) - LIMIT_DEG) < 0.01 for i in (0, 2, 4)) and
                      all(_enum_is(lin[i], LCM_LOCKED, 'locked') for i in (0, 1, 2)) and r['disable_collision'] is True)
                _p('PASS' if ok else 'FAIL', 'BP library %s-%s: angular %s, linear %s, disable collision %s'
                   % (child, parent, [getattr(x, 'name', x) for x in ang], [getattr(x, 'name', x) for x in lin], r['disable_collision']))
            except Exception as e:
                _p('WARN', 'BP library read %s-%s failed: %r' % (child, parent, e))


    # ----------------------------------------------------------------------------------------------- main
    def _bw03_main():
        t0 = time.time()
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les is not None and les.is_in_play_in_editor():
            _p('FAIL', 'PIE/SIE is running: stop it first (assets cannot be saved during PIE). Nothing changed.')
            return
        skm = unreal.load_asset(SK_PATH)
        if not isinstance(skm, unreal.SkeletalMesh):
            _p('FAIL', '%s not found or not a SkeletalMesh (run the import step bw_02 first). Nothing changed.' % SK_PATH)
            return
        bones = [b[0] for b in BODIES] + ['Rotor', 'root']
        G, route, all_names = _ref_globals(skm, bones)
        _p('INFO', 'reference pose from %s (%d bones)' % (route, len(all_names)))
        missing = [b for b in [x[0] for x in BODIES] + (['Rotor'] if ADD_ROTOR_BOX else []) if b not in G]
        if missing:
            _p('FAIL', 'bones missing in SK_Burrower: %s. Nothing changed.' % missing)
            return
        for b in bones:
            if b not in G:
                _p('WARN', 'bone %s not found (informational)' % b)
                continue
            t, q, s = G[b]
            if max(abs(c - 1.0) for c in s) > 1e-3:
                _p('WARN', 'bone %s reference scale %s is not 1: capsules are authored in bone space and would scale' % (b, _fmt(s)))
            if b in EXPECT_BONE_POS:
                d = _len(_sub(t, EXPECT_BONE_POS[b]))
                _p('INFO' if d < 25.0 else 'WARN', 'bone %-16s at %s (recipe %s, off %.1f cm)' % (b, _fmt(t), _fmt(EXPECT_BONE_POS[b]), d))
        try:
            smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
            for b, par in EXPECT_PARENT.items():
                got = str(smes.get_bone_parent(skm, b))
                if got != par:
                    _p('WARN', 'bone %s parent is %s (recipe: %s)' % (b, got, par))
        except Exception as e:
            _p('WARN', 'parent check skipped: %r' % (e,))
        try:
            prev = skm.get_editor_property('physics_asset')
            _p('INFO', 'SK_Burrower physics asset before: %s' % (prev.get_path_name() if prev else 'None'))
        except Exception:
            pass

        if not _tool_init():
            return
        _p('INFO', 'PhysicsAssetToolset via %s' % _BW03['mode'])
        pa = _get_or_create_pa(skm)
        if pa is None:
            return
        _BW03['pa'] = pa
        try:
            n = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(pa)
            if n:
                _p('INFO', 'closed %d open editor(s) of PA_Burrower before editing' % n)
        except Exception as e:
            _p('WARN', 'close_all_editors_for_asset: %r (close the Physics Asset Editor by hand if it is open)' % (e,))

        try:
            if not _clear(pa):
                return
            bobjs = _build_bodies(pa, G)
            cobjs = _build_constraints(pa, G)
            for bone in [b[0] for b in BODIES]:  # last toolset edit per body: Default + NotifyAssetChanged refresh
                t_set_mode(bone, PHYS_DEFAULT)
            if ADD_ROTOR_BOX:
                t_set_mode('Rotor', PHYS_KINEMATIC)
        except Exception as e:
            _p('FAIL', 'build step raised: %r\n%s' % (e, traceback.format_exc()))
            _p('INFO', 'nothing saved; fix and re-run (the script reuses and rebuilds PA_Burrower)')
            return

        try:
            _verify(pa, skm, G, bobjs, cobjs)
        except Exception as e:
            _p('FAIL', 'verification raised: %r\n%s' % (e, traceback.format_exc()))
        finally:
            bobjs = cobjs = None

        # assign to the mesh
        try:
            smes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
            ok = smes.assign_physics_asset(skm, pa)  # SkeletalMeshEditorSubsystem.h 349 (compat check + refresh)
            if not ok:
                _p('WARN', 'assign_physics_asset returned False (bone mismatch?); trying set_editor_property')
                skm.set_editor_property('physics_asset', pa)
        except Exception as e:
            _p('WARN', 'assign_physics_asset raised %r; trying set_editor_property' % (e,))
            try:
                skm.set_editor_property('physics_asset', pa)
            except Exception as e2:
                _p('FAIL', 'cannot assign the physics asset: %r' % (e2,))
        cur = skm.get_editor_property('physics_asset')
        _p('PASS' if cur is not None and cur.get_path_name() == PA_OBJ else 'FAIL',
           'SK_Burrower.physics_asset == %s' % (cur.get_path_name() if cur else 'None'))

        if _BW03['fail'] and not SAVE_IF_CHECKS_FAIL:
            _p('FAIL', '%d check(s) failed: NOT saved (set SAVE_IF_CHECKS_FAIL to save anyway). The changes are in memory.'
               % _BW03['fail'])
            return
        eal = unreal.EditorAssetLibrary
        for path in (PA_PATH, SK_PATH):
            try:
                ok = eal.save_asset(path, only_if_is_dirty=False)
                _p('PASS' if ok else 'FAIL', 'saved %s' % path if ok else 'save_asset(%s) returned False' % path)
            except Exception as e:
                _p('FAIL', 'save_asset(%s) raised %r' % (path, e))
        _p('INFO', 'bw_03 finished in %.1f s: %d FAIL, %d WARN' % (time.time() - t0, _BW03['fail'], _BW03['warn']))
        if not _BW03['fail']:
            _p('PASS', 'PA_Burrower built, verified, assigned and saved. Next: bw_03b_sim_test.py')
        _p('INFO', 'manual (once): open PA_Burrower; if it warns "no skeletal mesh assigned", OK, then toolbar Preview '
                   'Mesh -> SK_Burrower, Save')


    def _bw03_run():
        try:
            _bw03_main()
        except Exception as e:
            print('FAIL: bw_03 crashed in Python: %r\n%s' % (e, traceback.format_exc()))
        finally:
            _BW03['pa'] = None
            _BW03['cdo'] = None
    return _bw03_run


try:
    _bw03_module()()
except Exception as _e:
    print('FAIL: bw_03 could not start: %r' % (_e,))
