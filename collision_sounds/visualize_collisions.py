"""Visualize collisions: place colored spheres at collision contact points.

Size is mapped from collision speed.  Color comes from ``obj.color`` (set when
the sphere is assigned to an audio group) via an Object Info → Emission material.
All generated objects are in the "Audio Markers" collection.
"""

import bpy
import mathutils

VIS_COLLECTION_NAME = "Audio Markers"
SPEED_MATERIAL_NAME = "collision_vis_speed"   # legacy name kept so old materials are cleaned up
VIS_MATERIAL_NAME = "collision_vis_group"
SPHERE_RADIUS_SLOW = 0.08   # radius for slow collisions (blue)
SPHERE_RADIUS_FAST = 0.40   # radius for fast collisions (red)


class COLLISION_OT_visualize_collisions(bpy.types.Operator):
    bl_idname = "collision.visualize_collisions"
    bl_label = "Audio Markers"
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

        vis_col = _get_or_create_collection(context, VIS_COLLECTION_NAME)
        _clear_collection(vis_col)

        speeds = [e.speed for e in events]
        min_speed = min(speeds)
        max_speed = max(speeds)
        speed_range = max_speed - min_speed

        mat = _get_or_create_vis_material()

        for i, event in enumerate(events):
            name = f"vis_{event.active}_{event.passive}_f{event.frame}_{i}"
            mesh = bpy.data.meshes.new(name)
            obj = bpy.data.objects.new(name, mesh)
            vis_col.objects.link(obj)

            t = (event.speed - min_speed) / speed_range if speed_range > 0 else 0.0
            radius = SPHERE_RADIUS_SLOW + t * (SPHERE_RADIUS_FAST - SPHERE_RADIUS_SLOW)
            bm = _icosphere_bmesh(radius=radius, subdivisions=2)
            bm.to_mesh(mesh)
            bm.free()
            for poly in mesh.polygons:
                poly.use_smooth = True

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
    bl_label = "Clear Audio Markers"
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
        for mat_name in (SPEED_MATERIAL_NAME, VIS_MATERIAL_NAME):
            if mat_name in bpy.data.materials:
                bpy.data.materials.remove(bpy.data.materials[mat_name])
        self.report({'INFO'}, "Cleared collision visualization")
        return {'FINISHED'}


def _get_or_create_collection(context, name):
    if name in bpy.data.collections:
        col = bpy.data.collections[name]
    else:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    col.hide_render = True
    settings = context.scene.collision_sounds
    col.hide_viewport = not settings.show_audio_markers_viewport
    return col


def _clear_collection(col):
    for obj in list(col.objects):
        mesh = obj.data
        col.objects.unlink(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _get_or_create_vis_material():
    """Shared emissive material: Object Info → HSV (boost saturation/value) → Emission.

    Each sphere's ``obj.color`` is set to the audio group's color when assigned,
    so the viewport color reflects the group without needing per-object materials.
    HSV node makes colors more vibrant without changing their hue.
    """
    if VIS_MATERIAL_NAME in bpy.data.materials:
        return bpy.data.materials[VIS_MATERIAL_NAME]

    mat = bpy.data.materials.new(VIS_MATERIAL_NAME)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    obj_info = tree.nodes.new("ShaderNodeObjectInfo")
    obj_info.location = (-380, 0)

    hsv = tree.nodes.new("ShaderNodeHueSaturation")
    hsv.location = (-160, 0)
    hsv.inputs["Saturation"].default_value = 2.0
    hsv.inputs["Value"].default_value = 1.0
    tree.links.new(obj_info.outputs["Color"], hsv.inputs["Color"])

    emission = tree.nodes.new("ShaderNodeEmission")
    emission.location = (60, 0)
    emission.inputs["Strength"].default_value = 2.0
    tree.links.new(hsv.outputs["Color"], emission.inputs["Color"])

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (280, 0)
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    return mat


def _icosphere_bmesh(radius=0.15, subdivisions=2):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    return bm
