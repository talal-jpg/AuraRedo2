# Mech Sentinel source art - shared helpers (scene reset, materials, export, verification, preview renders).
# Runs with Blender 5.x, either the `bpy` Python module or `blender -b -P`.

import math
import os
import re

import bmesh
import bpy
from mathutils import Matrix, Vector

BODY_MATERIAL = "MI_MechSentinel_Body"
EYES_MATERIAL = "MI_MechSentinel_Eyes"

# Socket naming understood by the Unreal FBX importer (SOCKET_<Name> children become static mesh sockets).
SOCKET_PREFIX = "SOCKET_Tentacle_"
NUM_TENTACLES = 8

# Must match FMechSentinelTentacleParams defaults on the C++ side (12 points, 18 cm segments).
TENTACLE_SEGMENTS = 11
TENTACLE_SEGMENT_LENGTH = 0.18
TENTACLE_ROOT_DIAMETER = 0.18
TENTACLE_SHAFT_END_DIAMETER = 0.035


# ---------------------------------------------------------------------------------------------------------------------
# Scene

def reset_scene():
    """Empty scene, meters, Z up. Deterministic starting point for every build."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'
    return scene


def ensure_collection(name, parent=None):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def link_to(obj, collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------------------------------------------------
# Materials (preview look only: Unreal uses its own materials, only the slot names and order matter)

def get_body_material():
    mat = bpy.data.materials.get(BODY_MATERIAL)
    if mat is None:
        mat = bpy.data.materials.new(BODY_MATERIAL)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.045, 0.05, 0.058, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.85
        bsdf.inputs["Roughness"].default_value = 0.42
    return mat


def get_eyes_material():
    mat = bpy.data.materials.get(EYES_MATERIAL)
    if mat is None:
        mat = bpy.data.materials.new(EYES_MATERIAL)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.25
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.03, 0.01, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 6.0
    return mat


def assign_slots(obj, with_eyes=True):
    """Slot 0 = body, slot 1 = eyes (always in this order so Unreal material indices are stable).
    Keeps the per-face material indices set while building (materials.clear() resets them to 0)."""
    me = obj.data
    indices = [0] * len(me.polygons)
    me.polygons.foreach_get("material_index", indices)
    me.materials.clear()
    me.materials.append(get_body_material())
    if with_eyes:
        me.materials.append(get_eyes_material())
    max_index = len(me.materials) - 1
    me.polygons.foreach_set("material_index", [min(i, max_index) for i in indices])
    me.update()


# ---------------------------------------------------------------------------------------------------------------------
# Mesh helpers

def mesh_object_from_bmesh(name, bm, collection=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.validate(clean_customdata=False)
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def triangle_count(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def recalc_normals_outside(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def smart_uv(obj, angle_deg=55.0, margin=0.01):
    """Non-overlapping UV0 unwrap."""
    view_layer = bpy.context.view_layer
    for o in view_layer.objects:
        o.select_set(False)
    view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle_deg), island_margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)


def apply_transforms(obj):
    view_layer = bpy.context.view_layer
    for o in view_layer.objects:
        o.select_set(False)
    view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)


def add_socket(parent, index, location, direction, collection=None):
    """Empty SOCKET_Tentacle_XX parented to `parent`; its local +X points along `direction`."""
    name = f"{SOCKET_PREFIX}{index:02d}"
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'ARROWS'
    empty.empty_display_size = 0.15
    (collection or parent.users_collection[0]).objects.link(empty)
    x_axis = Vector(direction).normalized()
    up_hint = Vector((0.0, 0.0, 1.0)) if abs(x_axis.z) < 0.95 else Vector((0.0, 1.0, 0.0))
    y_axis = up_hint.cross(x_axis).normalized()
    z_axis = x_axis.cross(y_axis).normalized()
    rot = Matrix((x_axis, y_axis, z_axis)).transposed().to_4x4()
    empty.matrix_world = Matrix.Translation(Vector(location)) @ rot
    empty.parent = parent
    empty.matrix_parent_inverse = parent.matrix_world.inverted()
    return empty


# ---------------------------------------------------------------------------------------------------------------------
# Export + verification

def export_fbx(obj, filepath, include_children=True):
    """Exports one asset (and its SOCKET_ children) with the settings Unreal expects (see mech_art_contract)."""
    view_layer = bpy.context.view_layer
    for o in view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    if include_children:
        for child in obj.children:
            if child.name.startswith("SOCKET_"):
                child.select_set(True)
    view_layer.objects.active = obj
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=True,
        object_types={'MESH', 'EMPTY'},
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_UNITS',
        axis_forward='-Z',
        axis_up='Y',
        use_space_transform=True,
        use_mesh_modifiers=True,
        mesh_smooth_type='FACE',
        use_triangles=True,
        add_leaf_bones=False,
        bake_anim=False,
        use_custom_props=False,
        path_mode='STRIP',
    )
    for o in view_layer.objects:
        o.select_set(False)
    return filepath


def verify_fbx(filepath):
    """Re-imports an FBX into a temporary scene and returns a summary dict (dimensions, tris, slots, sockets)."""
    tmp_scene = bpy.data.scenes.new("VerifyScene")
    window_scene = bpy.context.window.scene if bpy.context.window else None
    if bpy.context.window:
        bpy.context.window.scene = tmp_scene
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=filepath)
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == 'MESH']
    sockets = sorted((o for o in imported if o.type == 'EMPTY' and o.name.startswith("SOCKET_")), key=lambda o: o.name)
    summary = {"file": os.path.basename(filepath), "meshes": []}
    for m in meshes:
        bpy.context.view_layer.update()
        summary["meshes"].append({
            "name": re.sub(r"\.\d{3}$", "", m.name),
            "dimensions_m": tuple(round(d, 3) for d in m.dimensions),
            "triangles": triangle_count(m),
            "slots": [s.material.name.split(".")[0] if s.material else None for s in m.material_slots],
        })
    summary["sockets"] = [(re.sub(r"\.\d{3}$", "", s.name), tuple(round(c, 3) for c in s.matrix_world.translation)) for s in sockets]
    for o in imported:
        bpy.data.objects.remove(o, do_unlink=True)
    if window_scene is not None:
        bpy.context.window.scene = window_scene
    bpy.data.scenes.remove(tmp_scene)
    return summary


# ---------------------------------------------------------------------------------------------------------------------
# Preview rendering (Cycles CPU only: no GPU context in headless bpy)

def setup_render(scene, resolution=(1280, 720), samples=48):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'AgX'

    world = scene.world or bpy.data.worlds.new("MechSentinelWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.018, 0.024, 0.036, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    return scene


def add_preview_lights(scene, collection=None, target=(0.0, 0.0, 0.0)):
    coll = collection or scene.collection
    key_data = bpy.data.lights.new("KeyShaft", type='SPOT')
    key_data.energy = 9000.0
    key_data.spot_size = math.radians(38.0)
    key_data.spot_blend = 0.6
    key_data.color = (0.78, 0.86, 1.0)
    key = bpy.data.objects.new("KeyShaft", key_data)
    key.location = (target[0] + 0.6, target[1] - 0.4, target[2] + 7.0)
    coll.objects.link(key)
    _look_at(key, Vector(target))

    rim_data = bpy.data.lights.new("Rim", type='AREA')
    rim_data.energy = 350.0
    rim_data.size = 3.0
    rim_data.color = (0.55, 0.65, 0.9)
    rim = bpy.data.objects.new("Rim", rim_data)
    rim.location = (target[0] - 4.0, target[1] + 3.0, target[2] + 1.5)
    coll.objects.link(rim)
    _look_at(rim, Vector(target))
    return key, rim


def add_camera(scene, location, target, lens=50.0, collection=None):
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    (collection or scene.collection).objects.link(cam)
    cam.location = Vector(location)
    _look_at(cam, Vector(target))
    scene.camera = cam
    return cam


def render_to(scene, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    return filepath


def _look_at(obj, target):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
