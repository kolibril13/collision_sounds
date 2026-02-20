import math
from itertools import product

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

COLLISION_EPSILON = 0.01
DEFAULT_MARGIN = 0.04


def detect_collisions(context):
    """Scan the full animation timeline and return collision onset events.

    Checks every (target, collider) pair each frame.  A collision onset is
    the first frame where a target comes within contact distance of a
    collider (i.e. they were farther apart on the previous frame).

    Contact distance is derived from each object's rigid-body collision margin
    so the detector matches what the physics solver considers a collision,
    even when mesh surfaces never truly interpenetrate (round objects, etc.).

    Detection runs as two passes:
      Pass 1 – scan every frame sequentially (never jumping) so the rigid-body
               cache stays intact and all onsets are found.
      Pass 2 – (precision mode only) revisit each onset to bisect the exact
               sub-frame and recompute velocities at the precise moment.

    Returns a list of event dicts with frame, target/collider names,
    contact position, and velocities.
    """
    scene = context.scene
    settings = scene.collision_sounds
    depsgraph = context.evaluated_depsgraph_get()
    fps = scene.render.fps / scene.render.fps_base
    precision = settings.precision_mode
    substeps = settings.substeps if precision else 1

    targets = [obj for obj in settings.targets_collection.objects if obj.type == 'MESH']
    colliders = [obj for obj in settings.colliders_collection.objects if obj.type == 'MESH']
    pairs = list(product(targets, colliders))

    was_in_contact = {(t.name, c.name): False for t, c in pairs}
    prev_positions = {}
    collision_events = []
    all_objects = {}
    for obj in targets:
        all_objects[obj.name] = obj
    for obj in colliders:
        all_objects[obj.name] = obj

    pair_thresholds = {}
    for target, collider in pairs:
        pair_thresholds[(target.name, collider.name)] = _collision_threshold(target, collider)

    # ------------------------------------------------------------------
    # Pass 1: sequential frame scan – no frame jumping so the rigid-body
    # simulation cache is never invalidated.
    # ------------------------------------------------------------------
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

        for target, collider in pairs:
            bvh_t = bvh_cache.get(target.name)
            bvh_c = bvh_cache.get(collider.name)
            if bvh_t is None or bvh_c is None:
                continue

            threshold = pair_thresholds[(target.name, collider.name)]
            is_in_contact = _surfaces_within_distance(
                bvh_t, bvh_c,
                cur_positions[target.name], cur_positions[collider.name],
                threshold,
            )
            key = (target.name, collider.name)

            if is_in_contact and not was_in_contact[key]:
                pos_t = cur_positions[target.name]
                contact = _contact_position(bvh_c, pos_t) if bvh_c else pos_t
                vel_t = cur_velocities.get(target.name, Vector())
                vel_c = cur_velocities.get(collider.name, Vector())
                rel_vel = vel_t - vel_c

                collision_events.append({
                    "frame": float(frame),
                    "time": round(frame / fps, 6),
                    "target": target.name,
                    "collider": collider.name,
                    "position": _round_vec(contact),
                    "velocity": _round_vec(vel_t),
                    "relative_velocity": _round_vec(rel_vel),
                    "speed": round(rel_vel.length, 4),
                })

            was_in_contact[key] = is_in_contact

        prev_positions = cur_positions

    # ------------------------------------------------------------------
    # Pass 2 (precision mode only): refine each onset to a sub-frame time
    # and recompute velocities at that precise moment.
    # ------------------------------------------------------------------
    if precision and collision_events:
        collision_events = _refine_events(
            scene, depsgraph, collision_events, all_objects,
            pair_thresholds, substeps, fps,
        )

    return collision_events


def _refine_events(scene, depsgraph, events, all_objects,
                   pair_thresholds, substeps, fps):
    """Revisit each onset and bisect for sub-frame precision."""
    refined = []
    for ev in events:
        frame = int(ev["frame"])
        target = all_objects[ev["target"]]
        collider = all_objects[ev["collider"]]
        threshold = pair_thresholds[(target.name, collider.name)]

        if frame > scene.frame_start:
            precise_frame = _bisect_onset(
                scene, depsgraph, target, collider,
                frame - 1, frame, substeps, threshold,
            )
        else:
            precise_frame = float(frame)

        precise_int = int(precise_frame)
        precise_sub = precise_frame - precise_int
        scene.frame_set(precise_int, subframe=precise_sub)
        depsgraph.update()

        pos_t = target.evaluated_get(depsgraph).matrix_world.translation.copy()
        pos_c = collider.evaluated_get(depsgraph).matrix_world.translation.copy()

        bvh_c = _bvh_from_object(collider, depsgraph)
        contact = _contact_position(bvh_c, pos_t) if bvh_c else pos_t

        half_step = 0.5 / substeps
        prev_t = max(precise_frame - half_step, scene.frame_start)
        prev_int = int(prev_t)
        prev_sub = prev_t - prev_int
        scene.frame_set(prev_int, subframe=prev_sub)
        depsgraph.update()
        prev_pos_t = target.evaluated_get(depsgraph).matrix_world.translation.copy()
        prev_pos_c = collider.evaluated_get(depsgraph).matrix_world.translation.copy()

        dt = (precise_frame - prev_t) / fps
        if dt > 0:
            vel_t = (pos_t - prev_pos_t) / dt
            vel_c = (pos_c - prev_pos_c) / dt
        else:
            vel_t = Vector(ev["velocity"])
            vel_c = Vector((0.0, 0.0, 0.0))
        rel_vel = vel_t - vel_c

        refined.append({
            "frame": round(precise_frame, 4),
            "time": round(precise_frame / fps, 6),
            "target": target.name,
            "collider": collider.name,
            "position": _round_vec(contact),
            "velocity": _round_vec(vel_t),
            "relative_velocity": _round_vec(rel_vel),
            "speed": round(rel_vel.length, 4),
        })

    return refined


def _collision_threshold(obj_a, obj_b):
    """Surface-distance threshold below which two objects count as in contact."""
    margin_a = obj_a.rigid_body.collision_margin if obj_a.rigid_body else DEFAULT_MARGIN
    margin_b = obj_b.rigid_body.collision_margin if obj_b.rigid_body else DEFAULT_MARGIN
    return margin_a + margin_b + COLLISION_EPSILON


def _surfaces_within_distance(bvh_a, bvh_b, pos_a, pos_b, threshold):
    """Test whether the closest surface-to-surface gap is within *threshold*.

    Uses a two-step nearest-point query (exact for convex objects): find the
    closest point on B to A's centre, then the closest point on A back to
    that location.  The distance between the two resulting surface points is
    the approximate surface gap.
    """
    loc_on_b, _n, _i, _d = bvh_b.find_nearest(pos_a)
    if loc_on_b is None:
        return False
    loc_on_a, _n, _i, _d = bvh_a.find_nearest(loc_on_b)
    if loc_on_a is None:
        return False
    return (loc_on_a - loc_on_b).length <= threshold


def _bisect_onset(scene, depsgraph, obj_a, obj_b, frame_lo, frame_hi,
                  substeps, threshold):
    """Binary-search the sub-frame interval [frame_lo, frame_hi] for the
    earliest moment two objects come within contact distance."""
    lo = float(frame_lo)
    hi = float(frame_hi)
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

        pos_a = obj_a.evaluated_get(depsgraph).matrix_world.translation.copy()
        pos_b = obj_b.evaluated_get(depsgraph).matrix_world.translation.copy()

        if _surfaces_within_distance(bvh_a, bvh_b, pos_a, pos_b, threshold):
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
