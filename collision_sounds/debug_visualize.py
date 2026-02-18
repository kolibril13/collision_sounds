"""Debug visualization: place colored spheres at collision contact points.

Color is mapped from collision speed — slow impacts are blue, fast are red.
All generated objects are placed in a "Debug Collisions" collection so they
can be toggled or deleted easily.
"""

import bpy
import mathutils

DEBUG_COLLECTION_NAME = "Debug Collisions"
SPHERE_RADIUS = 0.15


class COLLISION_OT_debug_visualize(bpy.types.Operator):
    bl_idname = "collision.debug_visualize"
    bl_label = "Visualize Collisions"
    bl_description = "Place colored spheres at each detected collision point (debug)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.collision_sounds.events) > 0

    def execute(self, context):
        events = context.scene.collision_sounds.events
        if not events:
            self.report({'WARNING'}, "No collision events to visualize")
            return {'CANCELLED'}

        debug_col = _get_or_create_collection(DEBUG_COLLECTION_NAME)
        _clear_collection(debug_col)

        speeds = [e.speed for e in events]
        min_speed = min(speeds)
        max_speed = max(speeds)

        for i, event in enumerate(events):
            name = f"dbg_{event.active}_{event.passive}_f{event.frame}"
            mesh = bpy.data.meshes.new(name)
            obj = bpy.data.objects.new(name, mesh)
            debug_col.objects.link(obj)

            bm = _icosphere_bmesh(radius=SPHERE_RADIUS, subdivisions=2)
            bm.to_mesh(mesh)
            bm.free()

            obj.location = mathutils.Vector(event.position)
            obj.show_in_front = True

            mat = _speed_material(event.speed, min_speed, max_speed)
            obj.data.materials.append(mat)

        self.report({'INFO'}, f"Created {len(events)} debug sphere(s)")
        return {'FINISHED'}


class COLLISION_OT_debug_clear(bpy.types.Operator):
    bl_idname = "collision.debug_clear"
    bl_label = "Clear Visualization"
    bl_description = "Remove all debug collision spheres"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return DEBUG_COLLECTION_NAME in bpy.data.collections

    def execute(self, context):
        if DEBUG_COLLECTION_NAME in bpy.data.collections:
            col = bpy.data.collections[DEBUG_COLLECTION_NAME]
            _clear_collection(col)
            bpy.data.collections.remove(col)
        self.report({'INFO'}, "Cleared debug visualization")
        return {'FINISHED'}


def _get_or_create_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def _clear_collection(col):
    for obj in list(col.objects):
        mesh = obj.data
        col.objects.unlink(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _speed_material(speed, min_speed, max_speed):
    """Create an emissive material colored by speed (blue=slow, red=fast)."""
    t = 0.0
    if max_speed > min_speed:
        t = (speed - min_speed) / (max_speed - min_speed)

    r = t
    g = 0.0
    b = 1.0 - t

    name = f"dbg_speed_{speed:.2f}"
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (r, g, b, 1.0)
    emission.inputs["Strength"].default_value = 3.0

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    return mat


def _icosphere_bmesh(radius=0.15, subdivisions=2):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    return bm
