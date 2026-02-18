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

    Returns a list of event dicts with frame, active/passive names,
    contact position, and velocities.
    """
    scene = context.scene
    settings = scene.collision_sounds
    depsgraph = context.evaluated_depsgraph_get()
    fps = scene.render.fps / scene.render.fps_base

    targets = [obj for obj in settings.targets_collection.objects if obj.type == 'MESH']
    colliders = [obj for obj in settings.colliders_collection.objects if obj.type == 'MESH']

    pairs = [
        (t, c)
        for t in targets
        for c in colliders
        if t.name != c.name
    ]

    substeps = settings.substeps if settings.precision_mode else 1
    step = 1.0 / substeps
    # Velocity scaling: displacement per sub-step -> units per second.
    vel_scale = fps * substeps

    was_overlapping = {(t.name, c.name): False for t, c in pairs}
    prev_positions = {}
    collision_events = []
    all_objects = {obj.name: obj for obj in set(targets) | set(colliders)}

    for frame_int in range(scene.frame_start, scene.frame_end + 1):
        for sub in range(substeps):
            subframe = sub * step
            scene.frame_set(frame_int, subframe=subframe)
            depsgraph.update()

            current_frame = frame_int + subframe

            # Compute world positions and velocities for every relevant object.
            cur_positions = {}
            cur_velocities = {}
            for name, obj in all_objects.items():
                pos = obj.evaluated_get(depsgraph).matrix_world.translation.copy()
                cur_positions[name] = pos
                if name in prev_positions:
                    cur_velocities[name] = (pos - prev_positions[name]) * vel_scale
                else:
                    cur_velocities[name] = Vector((0.0, 0.0, 0.0))

            # Build BVH trees (cache per sub-step so each mesh is tessellated once).
            bvh_cache = {}
            for name, obj in all_objects.items():
                mesh_bvh = _bvh_from_object(obj, depsgraph)
                if mesh_bvh is not None:
                    bvh_cache[name] = mesh_bvh

            for target, collider in pairs:
                bvh_target = bvh_cache.get(target.name)
                bvh_collider = bvh_cache.get(collider.name)
                if bvh_target is None or bvh_collider is None:
                    continue

                overlaps = bvh_target.overlap(bvh_collider)
                is_overlapping = len(overlaps) > 0
                key = (target.name, collider.name)

                if is_overlapping and not was_overlapping[key]:
                    active_pos = cur_positions[collider.name]
                    contact = _contact_position(bvh_target, active_pos)
                    active_vel = cur_velocities.get(collider.name, Vector())
                    passive_vel = cur_velocities.get(target.name, Vector())
                    rel_vel = active_vel - passive_vel

                    collision_events.append({
                        "frame": round(current_frame, 4),
                        "time": round(current_frame / fps, 6),
                        "active": collider.name,
                        "passive": target.name,
                        "position": _round_vec(contact),
                        "velocity": _round_vec(active_vel),
                        "relative_velocity": _round_vec(rel_vel),
                        "speed": round(rel_vel.length, 4),
                    })

                was_overlapping[key] = is_overlapping

            prev_positions = cur_positions

    return collision_events


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
    location, _normal, _index, _dist = passive_bvh.find_nearest(active_world_pos)
    if location is not None:
        return location
    return active_world_pos


def _round_vec(vec, precision=4):
    return [round(v, precision) for v in vec]
