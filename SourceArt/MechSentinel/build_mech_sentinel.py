# Mech Sentinel source art - entry point.
# Builds every asset, exports one FBX per asset into <out>/Export, verifies the exports, saves <out>/MechSentinel.blend
# and renders the previews into <out>/Previews.
#
#   <python with bpy> build_mech_sentinel.py --out SourceArt/MechSentinel [--no-render] [--no-verify] [--quick]
#   blender -b -P build_mech_sentinel.py -- --out SourceArt/MechSentinel
#
# Assets (Blender object name == FBX file name == Unreal asset name):
#   SM_MechSentinel_Head        near head, sockets SOCKET_Tentacle_00..07 on the rear collar (tentacles are Niagara ribbons)
#   SM_MechSentinel_Far         far LOD: simplified head + 8 baked trailing tentacles
#   SM_MechSentinel_Tentacle    one straight armored tentacle with its claw (reference look for the ribbon material)
#   SM_MechSentinel_TentacleTip claw alone (Niagara mesh renderer at every ribbon tip)

import argparse
import math
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import bpy  # noqa: E402  (must come before bmesh / mathutils in the bpy module build)
import bmesh  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402

import mech_sentinel_common as C  # noqa: E402
import mech_sentinel_head as H  # noqa: E402
import mech_sentinel_tentacle as T  # noqa: E402

# Contract limits checked after export (see the Unreal side: hit capsule radius 70 cm, half height 140 cm).
LIMITS = {
    H.HEAD_NAME: {"tris": (900, 1600), "length": (2.0, 2.45), "slots": [C.BODY_MATERIAL, C.EYES_MATERIAL], "sockets": 8},
    H.FAR_NAME: {"tris": (700, 1400), "slots": [C.BODY_MATERIAL, C.EYES_MATERIAL], "sockets": 0},
    T.TENTACLE_NAME: {"tris": (300, 700), "length": (2.0, 2.12), "sockets": 0},
    T.TENTACLE_TIP_NAME: {"tris": (1, 160), "slots": [C.BODY_MATERIAL], "sockets": 0},
}
HEAD_MAX_RADIUS = 0.65

# Hero / swarm tentacles: the same chain the game simulates (12 points, 18 cm apart).
HERO_POINTS = C.TENTACLE_SEGMENTS + 1
HERO_LENGTH = C.TENTACLE_SEGMENTS * C.TENTACLE_SEGMENT_LENGTH


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    parser = argparse.ArgumentParser(description="Build the Mech Sentinel source art.")
    parser.add_argument("--out", default=_HERE, help="Output folder (Export/, Previews/ and the .blend go here).")
    parser.add_argument("--no-render", action="store_true", help="Skip the preview renders.")
    parser.add_argument("--no-verify", action="store_true", help="Skip the FBX re-import check.")
    parser.add_argument("--quick", action="store_true", help="Small, noisy previews (iteration).")
    parser.add_argument("--only", default="", help="Comma separated preview names to render (default: all).")
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------------------------------------------------
# Mesh health

def mesh_health(obj):
    """Loose verts, degenerate faces, non-manifold edges and the max distance from the X axis."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    loose = sum(1 for v in bm.verts if not v.link_faces)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    radius = max((math.hypot(v.co.y, v.co.z) for v in bm.verts), default=0.0)
    bm.free()
    return {"loose_verts": loose, "degenerate_faces": degenerate, "non_manifold_edges": non_manifold,
            "max_radius_m": round(radius, 3)}


def check_summary(summary, health):
    """Returns a list of contract violations for one exported asset."""
    problems = []
    for mesh in summary["meshes"]:
        limits = LIMITS.get(mesh["name"])
        if limits is None:
            problems.append(f"unexpected mesh {mesh['name']}")
            continue
        lo, hi = limits["tris"]
        if not lo <= mesh["triangles"] <= hi:
            problems.append(f"{mesh['name']}: {mesh['triangles']} triangles, expected {lo}-{hi}")
        if "length" in limits:
            lo, hi = limits["length"]
            if not lo <= mesh["dimensions_m"][0] <= hi:
                problems.append(f"{mesh['name']}: length {mesh['dimensions_m'][0]} m, expected {lo}-{hi}")
        if "slots" in limits and mesh["slots"] != limits["slots"]:
            problems.append(f"{mesh['name']}: slots {mesh['slots']}, expected {limits['slots']}")
        if len(summary["sockets"]) != limits["sockets"]:
            problems.append(f"{mesh['name']}: {len(summary['sockets'])} sockets, expected {limits['sockets']}")
    h = health
    if h["loose_verts"] or h["degenerate_faces"]:
        problems.append(f"loose verts {h['loose_verts']}, degenerate faces {h['degenerate_faces']}")
    return problems


# ---------------------------------------------------------------------------------------------------------------------
# Preview rig: a head copy with 8 armored tentacles swept along the curves the in-game chains settle into

def build_hero(head, collection):
    hero_head = head.copy()  # linked duplicate: shares the head mesh, sockets stay on the original
    hero_head.name = "PV_HeroHead"
    collection.objects.link(hero_head)
    for i, (loc, d) in enumerate(H.get_socket_frames()):
        root = loc - d * 0.05  # sink the root into the port boss
        pts = T.make_trailing_curve(root, d, length=HERO_LENGTH, num_points=HERO_POINTS,
                                    droop=0.38 + 0.04 * (i % 3), sway=0.13, seed=i + 3)
        T.sweep_tentacle(pts, T.ROOT_RADIUS, T.SHAFT_END_RADIUS, T.TENTACLE_SIDES, f"PV_HeroTentacle_{i:02d}",
                         collection, with_claw=True, armored=True, glow=True, sleeve_count=C.TENTACLE_SEGMENTS,
                         cap_root=False, uv=False)
    return hero_head


def add_instance(collection_to_instance, location, rotation_deg, parent_collection, name):
    empty = bpy.data.objects.new(name, None)
    empty.instance_type = 'COLLECTION'
    empty.instance_collection = collection_to_instance
    empty.location = Vector(location)
    empty.rotation_euler = Euler([math.radians(a) for a in rotation_deg], 'XYZ')
    parent_collection.objects.link(empty)
    return empty


def set_visible(collections, visible_names):
    for coll in collections:
        coll.hide_render = coll.name not in visible_names
        coll.hide_viewport = coll.name not in visible_names


# ---------------------------------------------------------------------------------------------------------------------

def main():
    args = parse_args()
    out_dir = os.path.abspath(args.out)
    export_dir = os.path.join(out_dir, "Export")
    preview_dir = os.path.join(out_dir, "Previews")
    t0 = time.time()

    scene = C.reset_scene()
    c_head = C.ensure_collection("Head")
    c_far = C.ensure_collection("FarLOD")
    c_tentacle = C.ensure_collection("Tentacle")
    c_hero = C.ensure_collection("PV_HeroSource")
    c_shots = C.ensure_collection("PV_Shots")

    head = H.build_head(c_head)
    tentacle = T.build_tentacle(c_tentacle)
    tip = T.build_tentacle_tip(c_tentacle)
    far = H.build_far_lod(
        lambda pts, r0, r1, sides, name: T.sweep_tentacle(pts, r0, r1, sides, name, c_far, armored=False,
                                                          cap_root=False, uv=False),
        c_far)

    assets = [head, far, tentacle, tip]
    exported = {}
    for obj in assets:
        exported[obj.name] = C.export_fbx(obj, os.path.join(export_dir, f"{obj.name}.fbx"))

    # Verification table ------------------------------------------------------------------------------------------
    failures = []
    if not args.no_verify:
        print("\n%-28s %8s  %-22s %-36s %s" % ("asset", "tris", "dimensions (m)", "slots", "health"))
        print("-" * 130)
        for obj in assets:
            summary = C.verify_fbx(exported[obj.name])
            health = mesh_health(obj)
            for mesh in summary["meshes"]:
                print("%-28s %8d  %-22s %-36s %s" % (mesh["name"], mesh["triangles"], mesh["dimensions_m"],
                                                     mesh["slots"], health))
            for name, loc in summary["sockets"]:
                print("    %-24s %s" % (name, loc))
            problems = check_summary(summary, health)
            if obj is head and health["max_radius_m"] > HEAD_MAX_RADIUS:
                problems.append(f"head reaches {health['max_radius_m']} m from the X axis (max {HEAD_MAX_RADIUS})")
            for p in problems:
                print("    !! " + p)
            failures += problems
        print("-" * 130)
        print("verify: %s\n" % ("OK" if not failures else f"{len(failures)} problem(s)"))

    # Preview rig ----------------------------------------------------------------------------------------------
    build_hero(head, c_hero)
    hero_layer = bpy.context.view_layer.layer_collection.children[c_hero.name]
    hero_layer.exclude = True  # only drawn through collection instances

    c_hero_shot = C.ensure_collection("PV_HeroShot", c_shots)
    add_instance(c_hero, (0, 0, 0), (0, 0, 0), c_hero_shot, "PV_Hero")
    c_swarm = C.ensure_collection("PV_SwarmShot", c_shots)
    swarm_layout = [
        ((0.0, 0.0, 0.0), (0, 0, 0)),
        ((-4.5, 5.0, 1.6), (0, -6, 25)),
        ((-1.5, 9.0, -1.4), (0, 8, -18)),
        ((-8.5, 12.0, 2.8), (0, -4, 40)),
        ((-11.0, 4.0, -0.6), (0, 10, 10)),
        ((-5.5, 15.5, -2.4), (0, 3, -32)),
        ((-14.0, 9.0, 0.9), (0, -12, 15)),
    ]
    for i, (loc, rot) in enumerate(swarm_layout):
        add_instance(c_hero, loc, rot, c_swarm, f"PV_Swarm_{i}")

    # Lights + camera live in their own collection so every shot can reuse them.
    c_rig = C.ensure_collection("PV_Rig", c_shots)
    key, rim = C.add_preview_lights(scene, c_rig)
    cam = C.add_camera(scene, (3, -3, 1), (0, 0, 0), collection=c_rig)

    blend_path = os.path.join(out_dir, "MechSentinel.blend")
    view_collections = [c_head, c_far, c_tentacle, c_hero_shot, c_swarm]
    set_visible(view_collections, {c_head.name, c_far.name, c_tentacle.name})
    for o in (head, far, tentacle, tip):
        o.hide_render = False
    # Spread the assets out in the saved file so they do not overlap when opened (export already happened).
    far.location = (0.0, 4.0, 0.0)
    tentacle.location = (0.0, -2.5, 0.0)
    tip.location = (0.0, -3.2, 0.0)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, check_existing=False)
    far.location = tentacle.location = tip.location = (0.0, 0.0, 0.0)

    if not args.no_render:
        res = (640, 360) if args.quick else (1280, 720)
        samples = 12 if args.quick else 40
        C.setup_render(scene, res, samples)
        shots = {
            # name: (visible collections, camera location, camera target, lens, light target)
            "head_threequarter": ({c_head.name}, (2.7, -2.9, 1.25), (0.05, 0.0, -0.05), 50.0, (0, 0, 0)),
            "tentacle": ({c_tentacle.name}, (1.35, -2.35, 0.75), (1.05, 0.0, 0.0), 40.0, (1.0, 0, 0)),
            "far_lod": ({c_far.name}, (2.2, -5.6, 1.9), (-1.0, 0.0, -0.45), 40.0, (-0.8, 0, 0)),
            "hero": ({c_hero_shot.name}, (2.4, -5.8, 1.7), (-1.0, 0.0, -0.45), 40.0, (-0.8, 0, 0)),
            "swarm": ({c_swarm.name}, (5.5, -9.5, 2.6), (-7.0, 7.5, -0.2), 30.0, (-6.0, 7.0, 0.0)),
        }
        only = {s.strip() for s in args.only.split(",") if s.strip()}
        tip.hide_render = True  # the tentacle shot shows the claw on the tentacle itself
        for name, (visible, cam_loc, cam_target, lens, light_target) in shots.items():
            if only and name not in only:
                continue
            set_visible(view_collections, visible)
            cam.location = Vector(cam_loc)
            cam.data.lens = lens
            C._look_at(cam, Vector(cam_target))
            lt = Vector(light_target)
            key.location = lt + Vector((0.6, -0.4, 16.0 if name == "swarm" else 7.0))
            C._look_at(key, lt)
            rim.location = lt + Vector((-4.0, 3.0, 1.5))
            C._look_at(rim, lt)
            key.data.spot_size = math.radians(75.0 if name == "swarm" else 38.0)
            key.data.energy = 60000.0 if name == "swarm" else 9000.0
            rim.data.energy = 1500.0 if name == "swarm" else 350.0
            rim.data.size = 8.0 if name == "swarm" else 3.0
            t = time.time()
            C.render_to(scene, os.path.join(preview_dir, f"{name}.png"))
            print("rendered %-20s %.1fs" % (name, time.time() - t))

    print("done in %.1fs -> %s" % (time.time() - t0, out_dir))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
