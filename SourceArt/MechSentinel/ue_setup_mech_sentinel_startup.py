# Mech Sentinel - StartupMap setup: the swarm on the endless hex path, one sentinel wave per new path segment.
# Run it inside the editor with Play stopped: Tools > Execute Python Script..., the Output Log's Python console,
# -ExecutePythonScript=<this file> or an editor Python call. Needs the real assets (git lfs pull) and editor binaries
# built from source that has the External wave mode; otherwise it stops with a message. It never creates a map.
# Steps: open /Game/Maps/StartupMap, one MechSentinelWaveSpawner in External + curve mode, sentinel waves on the
# AMyHexPathSpawner lanes, save the map, then DA_MechSentinelSwarmRules on BP_MyGameMode, summary. Every check runs
# before the first change.
# Re-running is safe: the spawner is found again by its tag, every value is set again, files are saved only on change.

import math
import os

import unreal

# --------------------------------------------------------------------------------------------------------------------
# Knobs
# --------------------------------------------------------------------------------------------------------------------

# Assets (long package names).
MAP_PATH = "/Game/Maps/StartupMap"
GAME_MODE_PATH = "/Game/Level/BP_MyGameMode"  # StartupMap's GameMode override, an AMyGameMode Blueprint
ENTITY_CONFIG_PATH = "/Game/MechSentinel/Data/DA_MechSentinelConfig"
SWARM_RULES_PATH = "/Game/MechSentinel/Data/DA_MechSentinelSwarmRules"

# GameMode. The swarm reads its rules only from an AMyGameMode, on the server, at BeginPlay.
SET_GAME_MODE_RULES = True  # BP_MyGameMode class defaults: sentinel_swarm_rules = SWARM_RULES_PATH
SET_GAME_MODE_OVERRIDE_IF_EMPTY = True  # an empty World Settings GameMode override becomes GAME_MODE_PATH
REQUIRE_MY_GAME_MODE = True  # stop when the override is not an AMyGameMode (the rules would be ignored)

# The wave spawner actor. It stays level-placed: EntityConfig is not replicated, clients build the template from it.
SPAWNER_TAG = "SentinelWaveSpawner"  # a spawner with this tag is reused first, then any other
SPAWNER_LABEL = "MechSentinelWaveSpawner"
SPAWNER_OFFSET = (0.0, 0.0, 3000.0)  # cm from the PlayerStart for a new spawner (External waves spawn at the path)
MOVE_EXISTING_SPAWNER = False  # True: a reused spawner is moved there too
DESTROY_EXTRA_SPAWNERS = True  # the other MechSentinelWaveSpawners of the map are deleted

# Wave spawner settings (AMechSentinelWaveSpawner, Python names).
ADVANCE_MODE = "EXTERNAL"  # unreal.MechSentinelWaveAdvance member: waves come from the path segments
AUTO_START = True  # External mode: armed at BeginPlay (False: the waves wait for StartWaves)
USE_WAVE_CURVES = True  # every wave = curve_base_wave scaled by wave_curves over the wave number
BIND_TO_PATH_SPAWNERS = True
SPAWNER_IS_FALLBACK_TARGET = False  # a fixed point at the start of an endless level would pull the overflow back
MAX_ALIVE = 500
SPAWN_BATCH_SIZE = 25
SEGMENT_CORNERS = "TOP"  # unreal.MechSentinelSegmentCorners member: TOP, BOTTOM or ALL
CORNER_SPAWN_EXTENT = (800.0, 800.0, 300.0)  # cm, ellipsoid around each corner
MAX_ACTIVE_WAVES = 0  # 0 = unlimited
SPAWN_OBSTACLE_CLEARANCE = 200.0  # cm around the registered platforms
# None = leave as it is (the C++ default on a new spawner).
COUNT_MULTIPLIER = None
CORNER_INSET = None
CORNER_HEIGHT_OFFSET = None
# Any other spawner property, Python name -> value, e.g. {"spawn_extent": unreal.Vector(1500, 1500, 400)}.
SPAWNER_EXTRA = {}

# Curve mode. Empty = leave curve_base_wave and wave_curves alone (their C++ defaults on a new spawner).
# CURVE_BASE_WAVE: MechSentinelWave field -> value, e.g. {"count": 30, "delay_before": 3.0}.
CURVE_BASE_WAVE = {}
# WAVE_CURVES: curve -> keys or asset. Curves: count, health, armor, damage, attack_speed, move_speed, self_buff_chance.
# A list of (wave number, factor) keys replaces the curve (linear, flat before the first key and growing on past the
# last one at its slope, like the C++ defaults); a CurveFloat asset path becomes the curve's External Curve.
# e.g. {"count": [(1, 1.0), (10, 2.0), (40, 6.0)], "health": "/Game/MechSentinel/Data/C_SentinelHealth"}
WAVE_CURVES = {}

# Path spawners (AMyHexPathSpawner; StartupMap has two lanes).
EXPECTED_PATH_SPAWNERS = 2  # another count only warns; none at all stops (External mode would never start a wave)
PATH_SPAWN_SENTINEL_WAVES = True  # each new segment of the lane starts a wave at its corners
PATH_FIRST_SEGMENT_WITH_SENTINEL_WAVE = 1  # segment index that gets wave 1; wave = index - this + 1
# Any other path spawner property, e.g. {"draw_segment_bounds": True} to see the boxes the waves spawn on.
PATH_SPAWNER_EXTRA = {}

# Saving and output.
SAVE = True  # False: change the loaded assets only, save nothing
SAVE_UNCHANGED = False  # True: save StartupMap and BP_MyGameMode even when nothing changed
ALLOW_EXTERNAL_ACTORS = False  # True: go on when StartupMap stores its actors in __ExternalActors__ files
WAVE_PREVIEW = (1, 2, 3, 5, 10, 20, 40, 60)  # wave numbers resolved in the summary

# --------------------------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------------------------

PACKAGE_TAG = b"\xc1\x83\x2a\x9e"  # first bytes of a .umap / .uasset
LFS_POINTER = b"vers"  # first bytes of a Git LFS pointer file ("version https://git-lfs...")
CURVE_NAMES = ("count", "health", "armor", "damage", "attack_speed", "move_speed", "self_buff_chance")
REBUILD = ("Close the editor, build AuraEditor (Development Editor) from the current source and start it again "
           "(Live Coding cannot add properties or enum values).")

EAL = unreal.EditorAssetLibrary


class SetupAborted(RuntimeError):
    """A check failed; the message says what to do."""


def fail(message):
    error = SetupAborted(message)
    error.__suppress_context__ = True  # the message is the report, not the exception that led to it
    raise error


def log(message):
    unreal.log("MechSentinel startup: " + message)


class Report(object):
    """What the run found and changed, for the summary."""

    def __init__(self):
        self.values = []  # (section, name, value text, previous text or None when unchanged)
        self.notes = []
        self.warnings = []
        self.saved = []  # package names
        self.preview = []

    def warn(self, message):
        self.warnings.append(message)
        unreal.log_warning("MechSentinel startup: " + message)

    def record(self, section, name, value_text, previous_text=None):
        self.values.append((section, name, value_text, previous_text))


def fmt(value):
    """Short text of a property value."""
    try:
        if value is None:
            return "None"
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, float):
            return "%g" % value
        if isinstance(value, unreal.Vector):
            return "(%g, %g, %g)" % (value.x, value.y, value.z)
        if isinstance(value, unreal.Object):
            return value.get_path_name()
        if isinstance(value, unreal.EnumBase):
            return value.name
        if isinstance(value, unreal.StructBase):
            return value.export_text()
    except Exception:
        pass
    return str(value)


def same(a, b):
    """Value equality; floats within rounding (the editor stores float32). Unknown cases count as different."""
    try:
        if isinstance(a, float) or isinstance(b, float):
            return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(b)))
        if isinstance(a, unreal.Vector) and isinstance(b, unreal.Vector):
            return same(a.x, b.x) and same(a.y, b.y) and same(a.z, b.z)
        return bool(a == b)
    except Exception:
        return False


def set_value(obj, section, name, value, report):
    """obj.name = value unless it already is. True when it changed."""
    previous = obj.get_editor_property(name)
    if same(previous, value):
        report.record(section, name, fmt(previous))
        return False
    obj.set_editor_property(name, value)
    report.record(section, name, fmt(obj.get_editor_property(name)), fmt(previous))
    return True


def check_properties(obj, names, what):
    """Stops before any change when obj lacks one of the editor properties."""
    for name in names:
        try:
            obj.get_editor_property(name)
            continue
        except Exception as error:
            problem = str(error)
        fail("%s has no property '%s' (%s). If it should have it, the editor binaries are old. %s"
             % (what, name, problem, REBUILD))


def load(path, cls):
    asset = unreal.load_asset(path)
    if asset is None:
        fail("could not load %s (see the Output Log)." % path)
    if not isinstance(asset, cls):
        fail("%s is a %s, not a %s." % (path, asset.get_class().get_name(), cls.__name__))
    return asset


def enum_value(enum_type, member, constant):
    value = getattr(enum_type, member, None)
    if value is None:
        fail("%s = %r: unreal.%s has no such member." % (constant, member, enum_type.__name__))
    return value


def label(actor):
    try:
        return actor.get_actor_label()
    except Exception:
        return actor.get_name()


def has_tag(actor, tag):
    try:
        return any(str(t) == tag for t in actor.get_editor_property("tags"))
    except Exception:
        return False


def world_package(world):
    return world.get_path_name().split(".")[0] if world else ""


def in_map(actor):
    """True when the actor is in StartupMap's persistent level (what save_current_level writes)."""
    path = actor.get_path_name()
    return path.startswith(MAP_PATH + ".") and ":PersistentLevel." in path


def is_my_game_mode(cls):
    """AMyGameMode or a child of it (native or Blueprint)."""
    try:
        return isinstance(unreal.get_default_object(cls), unreal.MyGameMode)
    except Exception:
        return False


def dirty_maps():
    """Names of the map packages with unsaved changes; None when the editor cannot tell."""
    try:
        return [package.get_name() for package in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    except Exception:
        return None


def content_dir():
    path = unreal.Paths.project_content_dir()
    try:
        return unreal.Paths.convert_relative_path_to_full(path)
    except Exception:
        return os.path.abspath(path)


def package_file(package_name, extension):
    """Disk file of a /Game package; None for other mount points."""
    if not package_name.startswith("/Game/"):
        return None
    return os.path.normpath(os.path.join(content_dir(), package_name[len("/Game/"):] + extension))


def relative_file(package_name):
    return "Content/" + package_name[len("/Game/"):] + (".umap" if package_name == MAP_PATH else ".uasset")


def file_kind(path):
    """'package', 'lfs pointer', 'missing' or 'unknown'."""
    if not path or not os.path.isfile(path):
        return "missing"
    try:
        with open(path, "rb") as stream:
            head = stream.read(4)
    except (IOError, OSError):
        return "unknown"
    if head == PACKAGE_TAG:
        return "package"
    if head == LFS_POINTER:
        return "lfs pointer"
    return "unknown"


# --------------------------------------------------------------------------------------------------------------------
# Checks (nothing changes until all of them passed)
# --------------------------------------------------------------------------------------------------------------------

def editor_subsystems():
    subsystems = []
    for cls in (unreal.LevelEditorSubsystem, unreal.EditorActorSubsystem, unreal.UnrealEditorSubsystem):
        subsystem = unreal.get_editor_subsystem(cls)
        if subsystem is None:
            fail("run this inside the Unreal editor (no %s)." % cls.__name__)
        subsystems.append(subsystem)
    return subsystems


def check_binaries():
    """The Aura names this script sets; editor binaries built before the path segment waves lack them."""
    for name in ("MechSentinelWaveSpawner", "MechSentinelWaveAdvance", "MechSentinelSegmentCorners", "MechSentinelWave",
                 "MechSentinelSwarmRules", "MassEntityConfigAsset", "MyHexPathSpawner", "MyGameMode"):
        if not hasattr(unreal, name):
            fail("unreal.%s does not exist: the editor runs without the Aura module or with old binaries. %s"
                 % (name, REBUILD))
    if getattr(unreal.MechSentinelWaveAdvance, "EXTERNAL", None) is None:
        fail("unreal.MechSentinelWaveAdvance has no EXTERNAL: the editor binaries predate the path segment waves. "
             + REBUILD)
    spawner = unreal.get_default_object(unreal.MechSentinelWaveSpawner.static_class())
    try:
        spawner.get_editor_property("use_wave_curves")
        return spawner
    except Exception:
        pass
    fail("MechSentinelWaveSpawner has no 'use_wave_curves': the editor binaries predate the wave curves. " + REBUILD)


def check_not_playing(level_editor, editor):
    playing = False
    try:
        playing = bool(level_editor.is_in_play_in_editor())
    except Exception:
        pass
    try:
        playing = playing or editor.get_game_world() is not None
    except Exception:
        pass
    if playing:
        fail("Play In Editor is running: stop it, then run this again.")


def check_files(report):
    """The packages on disk must be real files, not Git LFS pointers (the editor cannot load those, and saving the map
    over a missing dependency loses data)."""
    needed = [(MAP_PATH, ".umap"), (ENTITY_CONFIG_PATH, ".uasset")]
    if SET_GAME_MODE_RULES or SET_GAME_MODE_OVERRIDE_IF_EMPTY:
        needed.append((GAME_MODE_PATH, ".uasset"))
    if SET_GAME_MODE_RULES:
        needed.append((SWARM_RULES_PATH, ".uasset"))
    for package, extension in needed:
        path = package_file(package, extension)
        if path is None:
            report.warn("cannot check the file of %s (not under /Game)." % package)
            continue
        kind = file_kind(path)
        if kind == "lfs pointer":
            fail("%s is a Git LFS pointer file, not the asset. Run `git lfs pull` (with git-lfs installed), restart "
                 "the editor and run this again." % path)
        if kind == "missing":
            fail("%s not found (%s)." % (path, package))
        if kind != "package":
            report.warn("%s does not start with the Unreal package tag; going on." % path)
        # The files this script saves: found read-only now rather than after the first save.
        saved_here = package == MAP_PATH or (package == GAME_MODE_PATH and SET_GAME_MODE_RULES)
        if SAVE and saved_here and not os.access(path, os.W_OK):
            fail("%s is read-only: clear the read-only flag (or check it out), then run this again." % path)

    built_data = package_file(MAP_PATH + "_BuiltData", ".uasset")
    kind = file_kind(built_data) if built_data else "package"
    if kind == "lfs pointer":
        report.warn("%s is a Git LFS pointer: StartupMap's lighting build data is not loaded, and saving the map may "
                    "drop or replace its MapBuildData reference. Better run `git lfs pull` first; check git status "
                    "after the save." % built_data)
    elif kind != "package":
        report.warn("%s: %s (StartupMap references it)." % (built_data, kind))


def check_external_actors(report):
    """This script saves the single-file map; actors in __ExternalActors__ files would need Save All and new files."""
    if not MAP_PATH.startswith("/Game/"):
        return
    folder = os.path.join(content_dir(), "__ExternalActors__", MAP_PATH[len("/Game/"):])
    if not any(files for _, _, files in os.walk(folder)):
        return
    message = ("%s stores its actors in their own files (%s), while this script was written for the single-file map: "
               "a new spawner gets a new file there." % (MAP_PATH, folder))
    if not ALLOW_EXTERNAL_ACTORS:
        fail(message + " Set ALLOW_EXTERNAL_ACTORS = True to go on (then File > Save All and add the new file to git).")
    report.warn(message + " Use File > Save All afterwards and add the new file to git.")


def open_map(level_editor, editor, report):
    """The editor world as StartupMap: loaded when another map is open, never created."""
    world = editor.get_editor_world()
    current = world_package(world)
    dirty = dirty_maps()
    if current == MAP_PATH:
        if dirty and MAP_PATH in dirty:
            report.warn("%s already had unsaved changes: if this script saves the map, they are saved too." % MAP_PATH)
        return world

    # Loading another map over unsaved changes would ask (or save) on its own.
    if dirty:
        fail("%s is open with unsaved changes (%s): save or discard them, or open %s yourself, then run this again."
             % (current or "a map", ", ".join(dirty), MAP_PATH))
    if dirty is None:
        report.warn("could not check %s for unsaved changes before opening %s." % (current or "the open map", MAP_PATH))
    log("opening %s (%s is open)" % (MAP_PATH, current or "no map"))
    if not level_editor.load_level(MAP_PATH):
        fail("could not open %s (see the Output Log). This script never creates the map." % MAP_PATH)
    world = editor.get_editor_world()
    if world_package(world) != MAP_PATH:
        fail("opened %s, but the editor world is %s." % (MAP_PATH, world_package(world) or "none"))
    return world


def check_game_mode(world, game_mode_class, report):
    """The World Settings GameMode override must be an AMyGameMode. Returns the class to set as the override (when it
    is empty), else None."""
    override = world.get_world_settings().get_editor_property("default_game_mode")
    if override is None:
        if SET_GAME_MODE_OVERRIDE_IF_EMPTY and game_mode_class is not None:
            return game_mode_class
        report.warn("%s has no GameMode override: the project's default GameMode must be an AMyGameMode for the swarm "
                    "rules to apply." % MAP_PATH)
        return None
    if not is_my_game_mode(override):
        message = ("%s's GameMode override %s is not an AMyGameMode: the swarm reads its rules only from an "
                   "AMyGameMode, so %s would be ignored." % (MAP_PATH, override.get_path_name(), SWARM_RULES_PATH))
        if REQUIRE_MY_GAME_MODE:
            fail(message + " Set REQUIRE_MY_GAME_MODE = False to go on anyway.")
        report.warn(message)
    elif game_mode_class is not None and override.get_path_name() != game_mode_class.get_path_name():
        rules = unreal.get_default_object(override).get_editor_property("sentinel_swarm_rules")
        report.warn("%s's GameMode override is %s, not %s: its own sentinel_swarm_rules apply (%s)."
                    % (MAP_PATH, override.get_path_name(), GAME_MODE_PATH, fmt(rules)))
    report.notes.append("GameMode override: %s" % override.get_path_name())
    return None


def find_actors(actors, report):
    """(path spawners, PlayerStart or None, wave spawners in the map), sorted by label."""
    level_actors = actors.get_all_level_actors()
    paths = sorted((a for a in level_actors if isinstance(a, unreal.MyHexPathSpawner)), key=label)
    starts = sorted((a for a in level_actors if isinstance(a, unreal.PlayerStart)), key=label)
    spawners = []
    for actor in sorted((a for a in level_actors if isinstance(a, unreal.MechSentinelWaveSpawner)), key=label):
        if in_map(actor):
            spawners.append(actor)
        else:
            report.warn("wave spawner '%s' is in another level (%s): left alone. In External mode bound to the "
                        "path spawners it starts its own waves on every segment too."
                        % (label(actor), actor.get_path_name()))

    if not paths:
        fail("%s has no AMyHexPathSpawner: External mode would never start a wave. Is the map loaded correctly?"
             % MAP_PATH)
    if len(paths) != EXPECTED_PATH_SPAWNERS:
        report.warn("%d path spawners, expected %d: every one of them gets the sentinel wave settings."
                    % (len(paths), EXPECTED_PATH_SPAWNERS))
    if not starts:
        report.warn("no PlayerStart: a new spawner goes to the world origin + SPAWNER_OFFSET.")
    elif len(starts) > 1:
        report.warn("%d PlayerStarts: a new spawner goes above '%s'." % (len(starts), label(starts[0])))
    return paths, (starts[0] if starts else None), spawners


# --------------------------------------------------------------------------------------------------------------------
# Values (resolved and checked before the first change)
# --------------------------------------------------------------------------------------------------------------------

def spawner_plan(config):
    """(property, value) for the wave spawner, in the order they are set."""
    plan = [
        ("entity_config", config),
        ("advance_mode", enum_value(unreal.MechSentinelWaveAdvance, ADVANCE_MODE, "ADVANCE_MODE")),
        ("auto_start", AUTO_START),
        ("use_wave_curves", USE_WAVE_CURVES),
        ("bind_to_path_spawners", BIND_TO_PATH_SPAWNERS),
        ("spawner_is_fallback_target", SPAWNER_IS_FALLBACK_TARGET),
        ("max_alive", MAX_ALIVE),
        ("spawn_batch_size", SPAWN_BATCH_SIZE),
        ("segment_corners", enum_value(unreal.MechSentinelSegmentCorners, SEGMENT_CORNERS, "SEGMENT_CORNERS")),
        ("corner_spawn_extent", unreal.Vector(*[float(v) for v in CORNER_SPAWN_EXTENT])),
        ("max_active_waves", MAX_ACTIVE_WAVES),
        ("spawn_obstacle_clearance", SPAWN_OBSTACLE_CLEARANCE),
    ]
    for name, value in (("count_multiplier", COUNT_MULTIPLIER), ("corner_inset", CORNER_INSET),
                        ("corner_height_offset", CORNER_HEIGHT_OFFSET)):
        if value is not None:
            plan.append((name, value))
    plan.extend(SPAWNER_EXTRA.items())
    return plan


def curve_base_plan():
    if CURVE_BASE_WAVE:
        check_properties(unreal.MechSentinelWave(), CURVE_BASE_WAVE, "CURVE_BASE_WAVE: unreal.MechSentinelWave")
    return list(CURVE_BASE_WAVE.items())


def keyed_curve(name, keys):
    """RuntimeFloatCurve with linear keys, flat before the first one and growing on past the last one."""
    try:
        points = sorted((float(x), float(y)) for x, y in keys)
    except (TypeError, ValueError):
        points = None
    if not points or len(set(x for x, _ in points)) != len(points):
        fail("WAVE_CURVES['%s']: expected (wave number, factor) pairs with distinct wave numbers, or a CurveFloat "
             "path; got %r." % (name, keys))
    text = ("(EditorCurveData=(PreInfinityExtrap=RCCE_Constant,PostInfinityExtrap=RCCE_Linear,Keys=(%s)),"
            "ExternalCurve=None)" % ",".join("(InterpMode=RCIM_Linear,Time=%.6f,Value=%.6f)" % p for p in points))
    curve = unreal.RuntimeFloatCurve()
    if not curve.import_text(text):
        fail("WAVE_CURVES['%s']: could not build the curve from %s." % (name, text))
    return curve, "keys " + ", ".join("(%g, %g)" % p for p in points)


def curve_plan():
    """(curve, CurveFloat asset or RuntimeFloatCurve, description)."""
    if not any(spec is not None for spec in WAVE_CURVES.values()):
        return []
    for name in ("MechSentinelWaveCurves", "RuntimeFloatCurve", "CurveFloat"):
        if not hasattr(unreal, name):
            fail("WAVE_CURVES needs unreal.%s, which this editor does not have. %s" % (name, REBUILD))
    plan = []
    for name, spec in WAVE_CURVES.items():
        if spec is None:
            continue
        if name not in CURVE_NAMES:
            fail("WAVE_CURVES: there is no curve '%s' (curves: %s)." % (name, ", ".join(CURVE_NAMES)))
        if isinstance(spec, str):
            asset = load(spec, unreal.CurveFloat)
            plan.append((name, asset, "External Curve " + asset.get_path_name()))
        else:
            curve, description = keyed_curve(name, spec)
            plan.append((name, curve, description))
    if plan:
        check_properties(unreal.MechSentinelWaveCurves(), [name for name, _, _ in plan],
                         "unreal.MechSentinelWaveCurves")
        check_properties(unreal.RuntimeFloatCurve(), ["external_curve"], "unreal.RuntimeFloatCurve")
    return plan


def path_plan():
    plan = [("spawn_sentinel_waves", PATH_SPAWN_SENTINEL_WAVES),
            ("first_segment_with_sentinel_wave", PATH_FIRST_SEGMENT_WITH_SENTINEL_WAVE)]
    plan.extend(PATH_SPAWNER_EXTRA.items())
    return plan


# --------------------------------------------------------------------------------------------------------------------
# Changes
# --------------------------------------------------------------------------------------------------------------------

def set_game_mode_rules(game_mode, rules, report):
    cdo = unreal.get_default_object(game_mode.generated_class())
    changed = set_value(cdo, GAME_MODE_PATH + " (class defaults)", "sentinel_swarm_rules", rules, report)
    if SAVE and (changed or SAVE_UNCHANGED):
        if not EAL.save_loaded_asset(game_mode, False):
            fail("could not save %s (read-only file? see the Output Log)." % GAME_MODE_PATH)
        report.saved.append(GAME_MODE_PATH)
        log("saved " + GAME_MODE_PATH)
    elif changed:
        report.notes.append("SAVE = False: %s was changed but not saved." % GAME_MODE_PATH)


def place_spawner(actors, spawners, start, report):
    """Reuses the tagged (else any) wave spawner of the map and deletes the others, or spawns one. Returns
    (spawner, map changed)."""
    tagged = [s for s in spawners if has_tag(s, SPAWNER_TAG)]
    spawner = tagged[0] if tagged else (spawners[0] if spawners else None)
    changed = False

    for extra in [s for s in spawners if s is not spawner]:
        name = label(extra)
        if not DESTROY_EXTRA_SPAWNERS:
            report.warn("another wave spawner stays in the map: '%s'." % name)
        elif actors.destroy_actor(extra):
            report.notes.append("deleted the extra wave spawner '%s'" % name)
            changed = True
        else:
            report.warn("could not delete the extra wave spawner '%s'." % name)

    base = start.get_actor_location() if start else unreal.Vector(0.0, 0.0, 0.0)
    location = unreal.Vector(base.x + SPAWNER_OFFSET[0], base.y + SPAWNER_OFFSET[1], base.z + SPAWNER_OFFSET[2])
    if spawner is None:
        spawner = actors.spawn_actor_from_class(unreal.MechSentinelWaveSpawner, location)
        if spawner is None:
            fail("could not spawn a MechSentinelWaveSpawner in %s." % MAP_PATH)
        if not in_map(spawner):
            path = spawner.get_path_name()
            actors.destroy_actor(spawner)
            fail("the new spawner landed in %s, not in %s's persistent level: make the persistent level current "
                 "(Levels panel) and run this again." % (path, MAP_PATH))
        report.notes.append("spawned a new wave spawner at %s" % fmt(spawner.get_actor_location()))
        changed = True
    else:
        report.notes.append("reused the wave spawner '%s' at %s" % (label(spawner), fmt(spawner.get_actor_location())))
        if MOVE_EXISTING_SPAWNER and not same(spawner.get_actor_location(), location):
            spawner.set_actor_location(location, False, False)
            report.notes.append("moved it to %s" % fmt(spawner.get_actor_location()))
            changed = True

    section = "wave spawner"
    previous_label = label(spawner)
    if previous_label != SPAWNER_LABEL:
        spawner.set_actor_label(SPAWNER_LABEL)
        report.record(section, "label", label(spawner), previous_label)
        changed = True
    else:
        report.record(section, "label", previous_label)
    tags = list(spawner.get_editor_property("tags"))
    if not has_tag(spawner, SPAWNER_TAG):
        spawner.set_editor_property("tags", tags + [unreal.Name(SPAWNER_TAG)])
        report.record(section, "tags", ", ".join(str(t) for t in spawner.get_editor_property("tags")),
                      ", ".join(str(t) for t in tags) or "none")
        changed = True
    else:
        report.record(section, "tags", ", ".join(str(t) for t in tags))

    try:
        if not spawner.get_editor_property("net_load_on_client"):
            report.warn("the spawner's net_load_on_client is off: clients will not load it, so they cannot build the "
                        "sentinel template.")
    except Exception:
        pass
    return spawner, changed


def curve_text(curve):
    try:
        return curve.export_text()
    except Exception:
        return None


def apply_curves(spawner, base_plan, curves_plan, report):
    """CURVE_BASE_WAVE and WAVE_CURVES (both empty by default: the C++ defaults stay). True when something changed."""
    section = "wave spawner"
    changed = False

    if base_plan:
        base = spawner.get_editor_property("curve_base_wave")
        base_changed = False
        for name, value in base_plan:
            previous = base.get_editor_property(name)
            if same(previous, value):
                report.record(section, "curve_base_wave." + name, fmt(previous))
                continue
            base.set_editor_property(name, value)
            report.record(section, "curve_base_wave." + name, fmt(base.get_editor_property(name)), fmt(previous))
            base_changed = True
        if base_changed:
            spawner.set_editor_property("curve_base_wave", base)
            changed = True
    else:
        report.record(section, "curve_base_wave", "left as it is (CURVE_BASE_WAVE is empty)")

    if curves_plan:
        curves = spawner.get_editor_property("wave_curves")
        curves_changed = False
        for name, value, description in curves_plan:
            curve = curves.get_editor_property(name)
            if isinstance(value, unreal.CurveFloat):
                if same(curve.get_editor_property("external_curve"), value):
                    report.record(section, "wave_curves." + name, description)
                    continue
                curve.set_editor_property("external_curve", value)
            else:
                old_text = curve_text(curve)
                if old_text is not None and old_text == curve_text(value):
                    report.record(section, "wave_curves." + name, description)
                    continue
                curve = value
            curves.set_editor_property(name, curve)
            report.record(section, "wave_curves." + name, description, "the previous curve")
            curves_changed = True
        if curves_changed:
            spawner.set_editor_property("wave_curves", curves)
            changed = True
    else:
        report.record(section, "wave_curves", "left as they are (WAVE_CURVES is empty)")
    return changed


def wave_preview(spawner, lanes):
    """What the first waves spawn with (GetWaveDefinition: curves and clamps applied)."""
    multiplier = spawner.get_editor_property("count_multiplier")
    lines = []
    for number in WAVE_PREVIEW:
        wave = spawner.get_wave_definition(number)
        get = wave.get_editor_property
        count = max(0, int(math.floor(get("count") * multiplier + 0.5)))
        lines.append("wave %3d: %4d per lane (%d lanes), health x%.2f, armor x%.2f, damage x%.2f, attack speed x%.2f, "
                     "move speed x%.2f, self-buff chance x%.2f, countdown %.0f s, spawned over %.0f s"
                     % (number, count, lanes, get("health_multiplier"), get("armor_multiplier"),
                        get("damage_multiplier"), get("attack_speed_multiplier"), get("move_speed_multiplier"),
                        get("self_buff_chance_multiplier"), get("delay_before"), get("spawn_duration")))
    return lines


# --------------------------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------------------------

def run(report):
    level_editor, actors, editor = editor_subsystems()

    # Checks and values: nothing changes until all of them passed.
    spawner_cdo = check_binaries()
    check_not_playing(level_editor, editor)
    check_files(report)
    check_external_actors(report)

    config = load(ENTITY_CONFIG_PATH, unreal.MassEntityConfigAsset)
    rules = load(SWARM_RULES_PATH, unreal.MechSentinelSwarmRules) if SET_GAME_MODE_RULES else None
    game_mode = None
    game_mode_class = None
    if SET_GAME_MODE_RULES or SET_GAME_MODE_OVERRIDE_IF_EMPTY:
        game_mode = load(GAME_MODE_PATH, unreal.Blueprint)
        game_mode_class = game_mode.generated_class()
        if not is_my_game_mode(game_mode_class):
            fail("%s is not an AMyGameMode Blueprint: the swarm reads its rules only from an AMyGameMode."
                 % GAME_MODE_PATH)

    spawner_values = spawner_plan(config)
    check_properties(spawner_cdo, [name for name, _ in spawner_values] + ["curve_base_wave", "wave_curves", "tags"],
                     "MechSentinelWaveSpawner")
    base_values = curve_base_plan()
    curve_values = curve_plan()
    path_values = path_plan()

    world = open_map(level_editor, editor, report)
    override = check_game_mode(world, game_mode_class, report)
    paths, start, spawners = find_actors(actors, report)
    for path in paths:
        check_properties(path, [name for name, _ in path_values], "path spawner '%s'" % label(path))

    # Changes. The map first: its steps can still stop the run (spawning the spawner, a wrong level, a knob of the
    # wrong type), and BP_MyGameMode must not be saved alone then.
    map_changed = False
    if override is not None:
        map_changed |= set_value(world.get_world_settings(), "World Settings", "default_game_mode", override, report)
    spawner, changed = place_spawner(actors, spawners, start, report)
    map_changed |= changed
    for name, value in spawner_values:
        map_changed |= set_value(spawner, "wave spawner", name, value, report)
    map_changed |= apply_curves(spawner, base_values, curve_values, report)
    for path in paths:
        for name, value in path_values:
            map_changed |= set_value(path, "path spawner '%s'" % label(path), name, value, report)

    if SAVE and (map_changed or SAVE_UNCHANGED):
        if not level_editor.save_current_level():
            fail("could not save %s (read-only file? see the Output Log)." % MAP_PATH)
        report.saved.append(MAP_PATH)
        log("saved " + MAP_PATH)
    elif map_changed:
        report.notes.append("SAVE = False: %s was changed but not saved." % MAP_PATH)

    if SET_GAME_MODE_RULES:
        set_game_mode_rules(game_mode, rules, report)

    # Information only, after the save.
    try:
        lanes = sum(1 for p in paths if p.get_editor_property("spawn_sentinel_waves"))
        report.preview = wave_preview(spawner, lanes)
    except Exception as error:
        report.preview = ["(no preview: %s)" % error]


def print_summary(report, outcome):
    lines = ["==== Mech Sentinel StartupMap setup: %s ====" % outcome]
    section = None
    for value_section, name, value_text, previous_text in report.values:
        if value_section != section:
            section = value_section
            lines.append(section + ":")
        if previous_text is None:
            lines.append("      %s = %s" % (name, value_text))
        else:
            lines.append("    * %s = %s   (was %s)" % (name, value_text, previous_text))
    if report.values:
        lines.append("(* = set by this run, the others already had the value)")
    for note in report.notes:
        lines.append("Note: " + note)
    if report.preview:
        lines.append("Waves (count after count_multiplier; each lane's segment k starts wave k - "
                     "first_segment_with_sentinel_wave + 1 at its corners):")
        lines.extend("    " + line for line in report.preview)
    if report.saved:
        lines.append("Saved. git status should show these files as modified, and nothing else:")
        lines.extend("    " + relative_file(package) for package in report.saved)
    else:
        lines.append("Nothing was saved%s." % ("" if SAVE else " (SAVE = False)"))
    for warning in report.warnings:
        lines.append("Warning: " + warning)
    for line in lines:
        unreal.log("MechSentinel startup: " + line)


def main():
    report = Report()
    try:
        run(report)
    except Exception as error:
        print_summary(report, "ABORTED")
        if isinstance(error, SetupAborted):
            unreal.log_error("MechSentinel startup: ABORTED: %s" % error)
        else:
            unreal.log_error("MechSentinel startup: FAILED on an unexpected error (traceback below): %r" % error)
        raise
    print_summary(report, "done")
    return report


# Tools > Execute Python Script, -ExecutePythonScript and the Python console run this as __main__. Run with exec() by an
# editor tool or another script it has another __name__ and runs too; only `import ue_setup_mech_sentinel_startup`
# leaves it to the caller to call main().
if __name__ == "__main__":
    main()
elif __name__.rpartition(".")[2] != "ue_setup_mech_sentinel_startup":
    main()
