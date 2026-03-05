from itertools import product

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

COLLISION_EPSILON = 0.01
DEFAULT_MARGIN = 0.04


class DetectionIntermediate:
    """Scan the full animation timeline and return collision onset events.

    Checks every (target, collider) pair each frame.  A collision onset is
    the first frame where a target comes within contact distance of a
    collider (i.e. they were farther apart on the previous frame).

    Contact distance is derived from each object's rigid-body collision margin
    so the detector matches what the physics solver considers a collision,
    even when mesh surfaces never truly interpenetrate (round objects, etc.).

    Detection scans every frame sequentially (never jumping) so the rigid-body
    cache stays intact and all onsets are found.

    Returns a list of event dicts with frame, target/collider names,
    contact position, and velocities.
    """

    def __init__(self, context):
        self.original_frame = context.scene.frame_current

        self.scene = context.scene
        self.settings = self.scene.collision_sounds
        self.depsgraph = context.evaluated_depsgraph_get()
        self.fps = self.scene.render.fps / self.scene.render.fps_base

        self.static_objects = [
            obj
            for obj in self.settings.static_collection.objects
            if obj.type == "MESH"
        ]
        self.dynamic_objects = [
            obj
            for obj in self.settings.dynamic_collection.objects
            if obj.type == "MESH"
        ]
        self.pairs = list(product(self.static_objects, self.dynamic_objects))

        self.was_in_contact = {(t.name, c.name): False for t, c in self.pairs}
        self.prev_positions = {}
        self.collision_events = []
        self.all_objects = {}
        for obj in self.static_objects:
            self.all_objects[obj.name] = obj
        for obj in self.dynamic_objects:
            self.all_objects[obj.name] = obj

        self.pair_thresholds = {}
        for target, collider in self.pairs:
            self.pair_thresholds[(target.name, collider.name)] = _collision_threshold(
                target, collider
            )

        self.next_frame = self.scene.frame_start

    def run_to_completion(self):
        while True:
            result = self.step()
            if result is not None:
                return result

    def step(self) -> None | list:
        # ------------------------------------------------------------------
        # Pass 1: sequential frame scan – no frame jumping so the rigid-body
        # simulation cache is never invalidated.
        # ------------------------------------------------------------------
        if self.next_frame != self.scene.frame_end + 1:
            self.scene.frame_set(self.next_frame)
            self.depsgraph.update()

            cur_positions = {}
            cur_velocities = {}
            for name, obj in self.all_objects.items():
                pos = obj.evaluated_get(self.depsgraph).matrix_world.translation.copy()
                cur_positions[name] = pos
                if name in self.prev_positions:
                    cur_velocities[name] = (pos - self.prev_positions[name]) * self.fps
                else:
                    cur_velocities[name] = Vector((0.0, 0.0, 0.0))

            bvh_cache = {}
            for name, obj in self.all_objects.items():
                bvh = _bvh_from_object(obj, self.depsgraph)
                if bvh is not None:
                    bvh_cache[name] = bvh

            for target, collider in self.pairs:
                bvh_t = bvh_cache.get(target.name)
                bvh_c = bvh_cache.get(collider.name)
                if bvh_t is None or bvh_c is None:
                    continue

                threshold = self.pair_thresholds[(target.name, collider.name)]
                is_in_contact = _surfaces_within_distance(
                    bvh_t,
                    bvh_c,
                    cur_positions[target.name],
                    cur_positions[collider.name],
                    threshold,
                )
                key = (target.name, collider.name)

                if is_in_contact and not self.was_in_contact[key]:
                    pos_t = cur_positions[target.name]
                    contact = _contact_position(bvh_c, pos_t) if bvh_c else pos_t
                    vel_t = cur_velocities.get(target.name, Vector())
                    vel_c = cur_velocities.get(collider.name, Vector())
                    rel_vel = vel_t - vel_c

                    self.collision_events.append(
                        {
                            "frame": float(self.next_frame),
                            "time": round(self.next_frame / self.fps, 6),
                            "target": target.name,
                            "collider": collider.name,
                            "position": _round_vec(contact),
                            "velocity": _round_vec(vel_t),
                            "relative_velocity": _round_vec(rel_vel),
                            "speed": round(rel_vel.length, 4),
                        }
                    )

                self.was_in_contact[key] = is_in_contact

            self.prev_positions = cur_positions

            self.next_frame += 1
            return None

        return self.collision_events


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
