import os

import bpy

from .sound_properties import get_sound_files_from_folder, AUDIO_GROUP_COLOR_ITEMS


# ---------------------------------------------------------------------------
# UIList
# ---------------------------------------------------------------------------

class VIEW3D_UL_audio_groups(bpy.types.UIList):
    bl_idname = "VIEW3D_UL_audio_groups"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.name, icon=f"STRIP_{item.color}")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon=f"STRIP_{item.color}")


# ---------------------------------------------------------------------------
# Add Sounds panel (contains Audio Groups inline)
# ---------------------------------------------------------------------------

class VIEW3D_PT_add_sounds(bpy.types.Panel):
    bl_label = "Add Sounds"
    bl_idname = "VIEW3D_PT_add_sounds"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        settings = context.scene.collision_sound_import

        # ---- Audio Groups ------------------------------------------------
        row = layout.row()
        row.template_list(
            "VIEW3D_UL_audio_groups", "",
            settings, "audio_groups",
            settings, "active_audio_group_index",
            rows=3,
        )
        col = row.column(align=True)
        col.operator("collision.add_audio_group", icon='ADD', text="")
        col.operator("collision.remove_audio_group", icon='REMOVE', text="")

        # Active group sound settings.
        groups = settings.audio_groups
        idx = settings.active_audio_group_index
        active_group = groups[idx] if groups and (0 <= idx < len(groups)) else None

        if active_group:
            # Assign section sits directly under the group list.
            layout.separator()
            selected_points = [
                obj for obj in context.selected_objects
                if "collision_frame" in obj
            ]
            num_selected = len(selected_points)
            if num_selected > 0:
                layout.label(text=f"{num_selected} collision point(s) selected",
                             icon='RESTRICT_SELECT_OFF')
            else:
                layout.label(text="Select Audio Markers in viewport",
                             icon='RESTRICT_SELECT_ON')

            row = layout.row(align=True)
            row.scale_y = 1.3
            row.enabled = num_selected > 0
            row.operator("collision.assign_sound", text="Assign", icon='PINNED')

            # Sound folder and selection below the assign button.
            layout.separator()
            col = layout.column(align=True)
            col.label(text="Sound Folder:", icon='FILE_FOLDER')
            row2 = col.row(align=True)
            if active_group.sound_folder:
                folder_name = os.path.basename(os.path.normpath(active_group.sound_folder))
                row2.label(text=folder_name, icon='CHECKMARK')
            else:
                row2.label(text="Not selected", icon='ERROR')
            row2 = col.row(align=True)
            row2.operator("collision.use_default_group_sounds", text="Use Default", icon='PACKAGE')
            row2.operator("collision.select_group_sound_folder", text="Select Folder...", icon='FILEBROWSER')

            if active_group.sound_folder:
                layout.separator()
                col2 = layout.column(align=True)
                col2.label(text="Sound Selection:", icon='SOUND')
                row3 = col2.row(align=True)
                row3.prop(active_group, "sound_selection_mode", expand=True)

                if active_group.sound_selection_mode == 'SINGLE':
                    col2.separator()
                    col2.prop(active_group, "sound_file", text="")
                else:
                    col2.separator()
                    folder_path = bpy.path.abspath(active_group.sound_folder)
                    count = len(get_sound_files_from_folder(folder_path))
                    col2.label(text=f"Will use {count} sound(s) randomly", icon='INFO')

        # ---- Add assigned ------------------------------------------------
        from .sound_operators import _all_assigned_spheres
        num_assigned = len(_all_assigned_spheres())
        layout.separator()
        if num_assigned > 0:
            layout.label(text=f"{num_assigned} point(s) have sounds assigned",
                         icon='CHECKMARK')
        row = layout.row(align=True)
        row.enabled = num_assigned > 0
        row.operator("collision.readd_assigned_sounds", icon='PLAY_SOUND')

        layout.separator()
        layout.operator("collision.clear_sounds", text="Clear Sounds", icon='TRASH')


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
