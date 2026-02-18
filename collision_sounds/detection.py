import bpy
from mathutils.bvhtree import BVHTree


def detect_collisions(context):
    """Scan the full animation timeline and return collision onset events.

    A collision onset is the first frame where two objects begin overlapping
    (i.e. they were not overlapping on the previous frame).

    Returns a list of dicts: {"frame": int, "target": str, "collider": str}
    """
    scene = context.scene
    settings = scene.collision_sounds
    depsgraph = context.evaluated_depsgraph_get()

    targets = [obj for obj in settings.targets_collection.objects if obj.type == 'MESH']
    colliders = [obj for obj in settings.colliders_collection.objects if obj.type == 'MESH']

    # Track overlap state per (target, collider) pair from the previous frame.
    was_overlapping = {}
    for target in targets:
        for collider in colliders:
            was_overlapping[(target.name, collider.name)] = False

    collision_events = []

    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        depsgraph.update()

        for target in targets:
            bvh_target = _bvh_from_object(target, depsgraph)
            if bvh_target is None:
                continue

            for collider in colliders:
                bvh_collider = _bvh_from_object(collider, depsgraph)
                if bvh_collider is None:
                    continue

                overlaps = bvh_target.overlap(bvh_collider)
                is_overlapping = len(overlaps) > 0
                key = (target.name, collider.name)

                if is_overlapping and not was_overlapping[key]:
                    collision_events.append({
                        "frame": frame,
                        "target": target.name,
                        "collider": collider.name,
                    })

                was_overlapping[key] = is_overlapping

    return collision_events


def _bvh_from_object(obj, depsgraph):
    """Build a BVHTree from the evaluated mesh of an object."""
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    if mesh is None or len(mesh.polygons) == 0:
        return None
    bvh = BVHTree.FromObject(eval_obj, depsgraph)
    eval_obj.to_mesh_clear()
    return bvh
