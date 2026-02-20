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
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.collision_sounds
        fps = scene.render.fps / scene.render.fps_base

        layout.prop(settings, "targets_collection", icon='GROUP')
        layout.prop(settings, "colliders_collection", icon='GROUP')

        layout.separator()
        layout.prop(settings, "precision_mode")
        if settings.precision_mode:
            layout.prop(settings, "substeps")
            accuracy_ms = 1000.0 / (fps * settings.substeps)
            col = layout.column(align=True)
            col.label(text=f"FPS: {fps:g}  |  Accuracy: {accuracy_ms:.2f} ms")
            if accuracy_ms > 5.0:
                col.label(text="Human perception is ~5 ms", icon='INFO')

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
    bl_label = "Visualize Collisions"
    bl_idname = "VIEW3D_PT_debug"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        layout.operator("collision.debug_visualize", icon='SPHERE')
        layout.operator("collision.debug_clear", icon='TRASH')
