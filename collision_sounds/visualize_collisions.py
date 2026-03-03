"""Visualize collisions: place colored spheres at collision contact points.

Color and size are mapped from collision speed: blue = slow (small spheres),
red = fast (large spheres).  A shared material reads each object's
``collision_speed`` custom property (Attribute node + Color Ramp).  All generated
objects are in the "Collision Visualization" collection.
"""

import bpy
import mathutils

VIS_COLLECTION_NAME = "Collision Visualization"
SPEED_MATERIAL_NAME = "collision_vis_speed"
SPHERE_RADIUS_SLOW = 0.16   # radius for slow collisions (blue)
SPHERE_RADIUS_FAST = 0.50   # radius for fast collisions (red)


class COLLISION_OT_visualize_collisions(bpy.types.Operator):
    bl_idname = "collision.visualize_collisions"
    bl_label = "Visualize Collisions"
    bl_description = "Place colored spheres at each detected collision point"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.collision_sounds.events) > 0

    def execute(self, context):
        events = context.scene.collision_sounds.events
        if not events:
            self.report({'WARNING'}, "No collision events to visualize")
            return {'CANCELLED'}

        vis_col = _get_or_create_collection(VIS_COLLECTION_NAME)
        _clear_collection(vis_col)

        speeds = [e.speed for e in events]
        min_speed = min(speeds)
        max_speed = max(speeds)
        speed_range = max_speed - min_speed

        mat = _get_or_create_speed_material()

        for i, event in enumerate(events):
            name = f"vis_{event.active}_{event.passive}_f{event.frame}"
            mesh = bpy.data.meshes.new(name)
            obj = bpy.data.objects.new(name, mesh)
            vis_col.objects.link(obj)

            t = (event.speed - min_speed) / speed_range if speed_range > 0 else 0.0
            radius = SPHERE_RADIUS_SLOW + t * (SPHERE_RADIUS_FAST - SPHERE_RADIUS_SLOW)
            bm = _icosphere_bmesh(radius=radius, subdivisions=2)
            bm.to_mesh(mesh)
            bm.free()

            obj.location = mathutils.Vector(event.position)
            obj.show_in_front = True

            obj["collision_speed"] = t
            obj["collision_frame"] = event.frame
            obj["collision_time"] = event.time
            obj["collision_active"] = event.active
            obj["collision_passive"] = event.passive
            obj["collision_position"] = list(event.position)
            obj["collision_velocity"] = list(event.velocity)
            obj["collision_rel_velocity"] = list(event.relative_velocity)
            obj["collision_raw_speed"] = event.speed
            obj.data.materials.append(mat)

        self.report({'INFO'}, f"Created {len(events)} collision sphere(s)")
        return {'FINISHED'}


class COLLISION_OT_clear_visualization(bpy.types.Operator):
    bl_idname = "collision.clear_visualization"
    bl_label = "Clear Visualization"
    bl_description = "Remove all collision visualization spheres"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return VIS_COLLECTION_NAME in bpy.data.collections

    def execute(self, context):
        if VIS_COLLECTION_NAME in bpy.data.collections:
            col = bpy.data.collections[VIS_COLLECTION_NAME]
            _clear_collection(col)
            bpy.data.collections.remove(col)
        if SPEED_MATERIAL_NAME in bpy.data.materials:
            bpy.data.materials.remove(bpy.data.materials[SPEED_MATERIAL_NAME])
        self.report({'INFO'}, "Cleared collision visualization")
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


def _get_or_create_speed_material():
    """Shared emissive material: Attribute (collision_speed) → Color Ramp → Emission.

    Each object stores its normalized speed (0-1) as the custom property
    ``collision_speed``.  An Attribute node (Instancer) reads that value and
    a Color Ramp maps 0 → blue, 1 → red.
    """
    if SPEED_MATERIAL_NAME in bpy.data.materials:
        return bpy.data.materials[SPEED_MATERIAL_NAME]

    mat = bpy.data.materials.new(SPEED_MATERIAL_NAME)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    attr = tree.nodes.new("ShaderNodeAttribute")
    attr.location = (-400, 0)
    attr.attribute_type = 'INSTANCER'
    attr.attribute_name = "collision_speed"

    color_ramp = tree.nodes.new("ShaderNodeValToRGB")
    color_ramp.location = (-150, 0)
    color_ramp.color_ramp.elements[0].color = (0.0, 0.0, 1.0, 1.0)
    color_ramp.color_ramp.elements[1].color = (1.0, 0.0, 0.0, 1.0)
    tree.links.new(attr.outputs["Fac"], color_ramp.inputs["Fac"])

    emission = tree.nodes.new("ShaderNodeEmission")
    emission.location = (150, 0)
    emission.inputs["Strength"].default_value = 3.0
    tree.links.new(color_ramp.outputs["Color"], emission.inputs["Color"])

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (350, 0)
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    return mat


def _icosphere_bmesh(radius=0.15, subdivisions=2):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    return bm
