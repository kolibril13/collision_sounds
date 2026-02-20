from itertools import combinations

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# Padding added to BVH nodes so that near-contact (typical of rigid body
# sims where the solver prevents deep penetration) is still detected.
COLLISION_EPSILON = 0.01


def detect_collisions(context):
    """Scan the full animation timeline and return collision onset events.

    A collision onset is the first frame where two objects begin overlapping
    (i.e. they were not overlapping on the previous frame).

    In precision mode, once an onset is found between frame N-1 and N, a
    binary search narrows down the exact sub-frame where contact begins.

    Returns a list of event dicts with frame, active/passive names,
    contact position, and velocities.
    """
    scene = context.scene
    settings = scene.collision_sounds
    depsgraph = context.evaluated_depsgraph_get()
    fps = scene.render.fps / scene.render.fps_base
    precision = settings.precision_mode
    substeps = settings.substeps if precision else 1

    objects = [obj for obj in settings.objects_collection.objects if obj.type == 'MESH']
    pairs = list(combinations(objects, 2))

    was_overlapping = {(a.name, b.name): False for a, b in pairs}
    prev_positions = {}
    collision_events = []
    all_objects = {obj.name: obj for obj in objects}

    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        depsgraph.update()

        cur_positions = {}
        cur_velocities = {}
        for name, obj in all_objects.items():
            pos = obj.evaluated_get(depsgraph).matrix_world.translation.copy()
            cur_positions[name] = pos
            if name in prev_positions:
                cur_velocities[name] = (pos - prev_positions[name]) * fps
            else:
                cur_velocities[name] = Vector((0.0, 0.0, 0.0))

        bvh_cache = {}
        for name, obj in all_objects.items():
            bvh = _bvh_from_object(obj, depsgraph)
            if bvh is not None:
                bvh_cache[name] = bvh

        for obj_a, obj_b in pairs:
            bvh_a = bvh_cache.get(obj_a.name)
            bvh_b = bvh_cache.get(obj_b.name)
            if bvh_a is None or bvh_b is None:
                continue

            overlaps = bvh_a.overlap(bvh_b)
            is_overlapping = len(overlaps) > 0
            key = (obj_a.name, obj_b.name)

            if is_overlapping and not was_overlapping[key]:
                if precision and frame > scene.frame_start:
                    precise_frame = _bisect_onset(
                        scene, depsgraph,
                        obj_a, obj_b,
                        frame - 1, frame,
                        substeps,
                    )
                else:
                    precise_frame = float(frame)

                precise_int = int(precise_frame)
                precise_sub = precise_frame - precise_int
                scene.frame_set(precise_int, subframe=precise_sub)
                depsgraph.update()

                pos_a = obj_a.evaluated_get(depsgraph).matrix_world.translation.copy()
                pos_b = obj_b.evaluated_get(depsgraph).matrix_world.translation.copy()

                bvh_b_precise = _bvh_from_object(obj_b, depsgraph)
                contact = _contact_position(bvh_b_precise, pos_a) if bvh_b_precise else pos_a

                half_step = 0.5 / substeps
                prev_t = max(precise_frame - half_step, scene.frame_start)
                prev_int = int(prev_t)
                prev_sub = prev_t - prev_int
                scene.frame_set(prev_int, subframe=prev_sub)
                depsgraph.update()
                prev_a = obj_a.evaluated_get(depsgraph).matrix_world.translation.copy()
                prev_b = obj_b.evaluated_get(depsgraph).matrix_world.translation.copy()

                dt = (precise_frame - prev_t) / fps
                if dt > 0:
                    vel_a = (pos_a - prev_a) / dt
                    vel_b = (pos_b - prev_b) / dt
                else:
                    vel_a = cur_velocities.get(obj_a.name, Vector())
                    vel_b = cur_velocities.get(obj_b.name, Vector())
                rel_vel = vel_a - vel_b

                collision_events.append({
                    "frame": round(precise_frame, 4),
                    "time": round(precise_frame / fps, 6),
                    "active": obj_a.name,
                    "passive": obj_b.name,
                    "position": _round_vec(contact),
                    "velocity": _round_vec(vel_a),
                    "relative_velocity": _round_vec(rel_vel),
                    "speed": round(rel_vel.length, 4),
                })

                scene.frame_set(frame)
                depsgraph.update()

            was_overlapping[key] = is_overlapping

        prev_positions = cur_positions

    return collision_events


def _bisect_onset(scene, depsgraph, obj_a, obj_b, frame_lo, frame_hi, substeps):
    """Binary-search the sub-frame interval [frame_lo, frame_hi] for the
    earliest moment two objects begin overlapping."""
    lo = float(frame_lo)
    hi = float(frame_hi)
    import math
    iterations = max(1, int(math.ceil(math.log2(substeps))))

    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        mid_int = int(mid)
        mid_sub = mid - mid_int
        scene.frame_set(mid_int, subframe=mid_sub)
        depsgraph.update()

        bvh_a = _bvh_from_object(obj_a, depsgraph)
        bvh_b = _bvh_from_object(obj_b, depsgraph)
        if bvh_a is None or bvh_b is None:
            lo = mid
            continue

        overlaps = bvh_a.overlap(bvh_b)
        if len(overlaps) > 0:
            hi = mid
        else:
            lo = mid

    return round(hi, 4)


def _bvh_from_object(obj, depsgraph):
    """Build a world-space BVHTree from the evaluated mesh of an object."""
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    if mesh is None or len(mesh.polygons) == 0:
        eval_obj.to_mesh_clear()
        return None

    mat = eval_obj.matrix_world
    vertices = [mat @ v.co for v in mesh.vertices]
    polygons = [tuple(p.vertices) for p in mesh.polygons]

    bvh = BVHTree.FromPolygons(vertices, polygons, epsilon=COLLISION_EPSILON)
    eval_obj.to_mesh_clear()
    return bvh


def _contact_position(passive_bvh, active_world_pos):
    """Find the closest point on the passive surface to the active object."""
    if passive_bvh is None:
        return active_world_pos
    location, _normal, _index, _dist = passive_bvh.find_nearest(active_world_pos)
    if location is not None:
        return location
    return active_world_pos


def _round_vec(vec, precision=4):
    return [round(v, precision) for v in vec]
