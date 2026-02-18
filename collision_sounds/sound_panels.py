import os

import bpy

from .sound_properties import get_sound_files_from_folder


class VIEW3D_PT_add_sounds(bpy.types.Panel):
    bl_label = "Add Sounds"
    bl_idname = "VIEW3D_PT_add_sounds"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.collision_sound_import
        events = context.scene.collision_sounds.events

        # Sound folder selection.
        col = layout.column(align=True)
        col.label(text="Sound Folder:", icon='FILE_FOLDER')
        row = col.row(align=True)
        if settings.sound_folder:
            folder_name = os.path.basename(os.path.normpath(settings.sound_folder))
            row.label(text=folder_name, icon='CHECKMARK')
        else:
            row.label(text="Not selected", icon='ERROR')
        col.operator("collision.select_sound_folder", text="Select Folder...", icon='FILEBROWSER')

        if settings.sound_folder:
            layout.separator()
            col = layout.column(align=True)
            col.label(text="Sound Selection:", icon='SOUND')
            row = col.row(align=True)
            row.prop(settings, "sound_selection_mode", expand=True)

            if settings.sound_selection_mode == 'SINGLE':
                col.separator()
                col.prop(settings, "sound_file", text="")
            else:
                col.separator()
                folder_path = bpy.path.abspath(settings.sound_folder)
                count = len(get_sound_files_from_folder(folder_path))
                col.label(text=f"Will use {count} sound(s) randomly", icon='INFO')

        # Load from JSON.
        layout.separator()
        layout.operator("collision.load_json_events", icon='IMPORT')

        # Add / clear sounds.
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.enabled = len(events) > 0
        row.operator("collision.add_sounds", icon='PLAY_SOUND')
        layout.operator("collision.clear_sounds", icon='TRASH')


class VIEW3D_PT_speed_volume(bpy.types.Panel):
    bl_label = "Collision Speed → Volume"
    bl_idname = "VIEW3D_PT_speed_volume"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_add_sounds"
    bl_order = 1

    def draw_header(self, context):
        self.layout.prop(context.scene.collision_sound_import, "use_speed_volume", text="")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.collision_sound_import
        layout.active = settings.use_speed_volume
        col = layout.column(align=True)
        col.prop(settings, "speed_volume_softer", text="Softer (slowest)", slider=True)
        col.prop(settings, "speed_volume_louder", text="Louder (fastest)", slider=True)


class VIEW3D_PT_camera_volume_pan(bpy.types.Panel):
    bl_label = "Camera Distance → Volume & Pan"
    bl_idname = "VIEW3D_PT_camera_volume_pan"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_add_sounds"
    bl_order = 2

    def draw_header(self, context):
        self.layout.prop(context.scene.collision_sound_import, "use_camera_volume_pan", text="")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.collision_sound_import
        layout.active = settings.use_camera_volume_pan
        col = layout.column(align=True)
        col.prop(settings, "camera_volume_softer", text="Softer (farthest)", slider=True)
        col.prop(settings, "camera_volume_louder", text="Louder (nearest)", slider=True)
        col.separator()
        col.label(text="Pan follows camera angle", icon='INFO')


class VIEW3D_PT_randomize_volume(bpy.types.Panel):
    bl_label = "Randomize Volume"
    bl_idname = "VIEW3D_PT_randomize_volume"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_add_sounds"
    bl_order = 3

    def draw_header(self, context):
        self.layout.prop(context.scene.collision_sound_import, "use_volume_randomness", text="")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.collision_sound_import
        layout.active = settings.use_volume_randomness
        col = layout.column(align=True)
        col.prop(settings, "volume_randomness", text="Amount", slider=True)


class VIEW3D_PT_render_audio(bpy.types.Panel):
    bl_label = "Render Audio"
    bl_idname = "VIEW3D_PT_render_audio"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_add_sounds"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("collision.render_audio", text="Render Audio", icon='FILE_SOUND')
