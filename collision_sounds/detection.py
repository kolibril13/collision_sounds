from itertools import product

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

COLLISION_EPSILON = 0.01
DEFAULT_MARGIN = 0.04


class DetectionIntermediate:
    """Scan the full animation timeline and return collision onset events.

    Checks every (target, collider) pair each frame.  A collision onset is
    the first frame where at least one vertex of either object comes within
    contact distance of a face of the other (i.e. they were farther apart on
    the previous frame).

    Contact is vertex-vs-face: for each vertex of object A we find the
    nearest point on the surface of object B; if that distance is within
    the pair's threshold, that vertex is counted as colliding with a face.
    Contact distance is derived from each object's rigid-body collision margin.

    Detection scans every frame sequentially (never jumping) so the rigid-body
    cache stays intact and all onsets are found.

    Returns a list of event dicts, one per colliding vertex, with frame,
    target/collider names, position (vertex location), and velocities.
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
            vertex_cache = {}
            for name, obj in self.all_objects.items():
                bvh, verts = _bvh_and_vertices_from_object(obj, self.depsgraph)
                if bvh is not None:
                    bvh_cache[name] = bvh
                    vertex_cache[name] = verts
                else:
                    vertex_cache[name] = []

            for target, collider in self.pairs:
                bvh_t = bvh_cache.get(target.name)
                bvh_c = bvh_cache.get(collider.name)
                if bvh_t is None or bvh_c is None:
                    continue

                threshold = self.pair_thresholds[(target.name, collider.name)]
                # Vertices of target that are in contact with collider's faces
                target_verts_hitting = _vertices_in_contact_with_surface(
                    vertex_cache[target.name], bvh_c, threshold
                )
                # Vertices of collider that are in contact with target's faces
                collider_verts_hitting = _vertices_in_contact_with_surface(
                    vertex_cache[collider.name], bvh_t, threshold
                )
                is_in_contact = len(target_verts_hitting) > 0 or len(collider_verts_hitting) > 0
                key = (target.name, collider.name)

                if is_in_contact and not self.was_in_contact[key]:
                    vel_t = cur_velocities.get(target.name, Vector())
                    vel_c = cur_velocities.get(collider.name, Vector())
                    rel_vel_t = vel_t - vel_c
                    rel_vel_c = vel_c - vel_t

                    for pos in target_verts_hitting:
                        self.collision_events.append(
                            {
                                "frame": float(self.next_frame),
                                "time": round(self.next_frame / self.fps, 6),
                                "target": target.name,
                                "collider": collider.name,
                                "position": _round_vec(pos),
                                "velocity": _round_vec(vel_t),
                                "relative_velocity": _round_vec(rel_vel_t),
                                "speed": round(rel_vel_t.length, 4),
                            }
                        )
                    for pos in collider_verts_hitting:
                        self.collision_events.append(
                            {
                                "frame": float(self.next_frame),
                                "time": round(self.next_frame / self.fps, 6),
                                "target": target.name,
                                "collider": collider.name,
                                "position": _round_vec(pos),
                                "velocity": _round_vec(vel_c),
                                "relative_velocity": _round_vec(rel_vel_c),
                                "speed": round(rel_vel_c.length, 4),
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


def _vertices_in_contact_with_surface(vertex_positions_world, surface_bvh, threshold):
    """Return world-space positions of vertices that are within *threshold* of the surface.

    Each vertex is tested by finding the nearest point on the surface (face) of the
    other object; if that distance is within threshold, the vertex is considered
    in contact with a face.
    """
    colliding = []
    for pos in vertex_positions_world:
        loc, _n, _i, dist = surface_bvh.find_nearest(pos)
        if loc is not None and dist <= threshold:
            colliding.append(pos.copy())
    return colliding


def _bvh_from_object(obj, depsgraph):
    """Build a world-space BVHTree from the evaluated mesh of an object."""
    bvh, _ = _bvh_and_vertices_from_object(obj, depsgraph)
    return bvh


def _bvh_and_vertices_from_object(obj, depsgraph):
    """Build BVH and world-space vertex list in one mesh evaluation. Returns (bvh, vertices)."""
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    if mesh is None or len(mesh.polygons) == 0:
        eval_obj.to_mesh_clear()
        return None, []

    mat = eval_obj.matrix_world
    vertices = [mat @ v.co for v in mesh.vertices]
    polygons = [tuple(p.vertices) for p in mesh.polygons]

    bvh = BVHTree.FromPolygons(vertices, polygons, epsilon=COLLISION_EPSILON)
    eval_obj.to_mesh_clear()
    return bvh, vertices


def _round_vec(vec, precision=4):
    return [round(v, precision) for v in vec]
