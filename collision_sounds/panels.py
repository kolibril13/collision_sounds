import bpy


class VIEW3D_PT_collision_sounds(bpy.types.Panel):
    bl_label = "Collision Sounds"
    bl_idname = "VIEW3D_PT_collision_sounds"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"

    def draw(self, context):
        pass


class VIEW3D_PT_detect_collisions(bpy.types.Panel):
    bl_label = "Detect Collisions"
    bl_idname = "VIEW3D_PT_detect_collisions"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.collision_sounds

        layout.prop(settings, "targets_collection", icon='GROUP')
        layout.prop(settings, "colliders_collection", icon='GROUP')
        layout.separator()
        layout.prop(settings, "export_json")
        if settings.export_json:
            layout.prop(settings, "output_path")
        layout.separator()
        layout.operator("collision.detect", icon='PLAY')

        if len(settings.events) > 0:
            layout.separator()
            layout.label(text=f"{len(settings.events)} event(s) detected")


class VIEW3D_PT_debug(bpy.types.Panel):
    bl_label = "Debug"
    bl_idname = "VIEW3D_PT_debug"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("collision.debug_visualize", icon='SPHERE')
        layout.operator("collision.debug_clear", icon='TRASH')
