import time
import json
import os

import bpy

from . import detection

DETECTION_INTERMEDIATE = None

class COLLISION_OT_detect(bpy.types.Operator):
    bl_idname = "collision.detect"
    bl_label = "Detect Collisions"
    bl_description = "Scan the timeline for collision events between targets and colliders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.collision_sounds

        if settings.targets_collection is None:
            self.report({'ERROR'}, "No targets collection assigned")
            return {'CANCELLED'}
        if settings.colliders_collection is None:
            self.report({'ERROR'}, "No colliders collection assigned")
            return {'CANCELLED'}

        targets = [o for o in settings.targets_collection.objects if o.type == 'MESH']
        colliders = [o for o in settings.colliders_collection.objects if o.type == 'MESH']
        if not targets:
            self.report({'ERROR'}, "Targets collection has no mesh objects")
            return {'CANCELLED'}
        if not colliders:
            self.report({'ERROR'}, "Colliders collection has no mesh objects")
            return {'CANCELLED'}

        global DETECTION_INTERMEDIATE
        DETECTION_INTERMEDIATE = detection.DetectionIntermediate(context)
        bpy.ops.collision.detect_modal("INVOKE_DEFAULT")

        return {'FINISHED'}



class COLLISION_OT_detect_modal(bpy.types.Operator):
    bl_idname = "collision.detect_modal"
    bl_label = "Detect Collisions Modal"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None

    def invoke(self, context, event):
        self._timer = context.window_manager.event_timer_add(
            time_step=0, window=context.window
        )
        context.window_manager.progress_begin(context.scene.frame_start, context.scene.frame_end)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global DETECTION_INTERMEDIATE
        assert isinstance(DETECTION_INTERMEDIATE, detection.DetectionIntermediate)

        scene = context.scene
        settings = scene.collision_sounds

        if event.type in {"RIGHTMOUSE", "ESC"}:
            context.window_manager.event_timer_remove(self._timer)
            DETECTION_INTERMEDIATE = None
            self.report({"WARNING"}, "User cancellation.")
            return {'FINISHED'}

        events = DETECTION_INTERMEDIATE.step()
        if events is None:
            context.window_manager.progress_update(scene.frame_current)
            return {"RUNNING_MODAL"}

        context.scene.frame_set(DETECTION_INTERMEDIATE.original_frame)
        DETECTION_INTERMEDIATE = None
        context.window_manager.progress_end()

        # Store results in the blend-file-internal collection property.
        settings.events.clear()
        for e in events:
            item = settings.events.add()
            item.frame = e["frame"]
            item.time = e["time"]
            item.active = e["target"]
            item.passive = e["collider"]
            item.position = e["position"]
            item.velocity = e["velocity"]
            item.relative_velocity = e["relative_velocity"]
            item.speed = e["speed"]

        # Create collision visualization spheres (same as former "Visualize Collisions" button).
        if events:
            bpy.ops.collision.visualize_collisions()

        # Optionally export to JSON.
        if settings.export_json:
            filepath = bpy.path.abspath(settings.output_path)
            if not filepath:
                self.report({'ERROR'}, "No output path set")
                return {'CANCELLED'}

            fps = scene.render.fps / scene.render.fps_base
            output = {
                "metadata": {
                    "epsilon": detection.COLLISION_EPSILON,
                    "fps": fps,
                    "frame_start": scene.frame_start,
                    "frame_end": scene.frame_end,
                    "targets_collection": settings.targets_collection.name,
                    "colliders_collection": settings.colliders_collection.name,
                },
                "events": events,
            }

            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(output, f, indent=2)

            self.report({'INFO'}, f"Found {len(events)} collision event(s) — exported to {filepath}")
        else:
            self.report({'INFO'}, f"Found {len(events)} collision event(s)")

        return {'FINISHED'}


def _events_to_export_list(settings):
    """Build list of event dicts from stored settings.events (same format as detection output)."""
    return [
        {
            "frame": e.frame,
            "time": e.time,
            "target": e.active,
            "collider": e.passive,
            "position": list(e.position),
            "velocity": list(e.velocity),
            "relative_velocity": list(e.relative_velocity),
            "speed": e.speed,
        }
        for e in settings.events
    ]


class COLLISION_OT_export_json(bpy.types.Operator):
    bl_idname = "collision.export_json"
    bl_label = "Export JSON"
    bl_description = "Export current collision events to a JSON file (run after detection)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        settings = scene.collision_sounds
        filepath = bpy.path.abspath(settings.output_path)
        if not filepath:
            self.report({'ERROR'}, "No output path set")
            return {'CANCELLED'}

        events = _events_to_export_list(settings)
        fps = scene.render.fps / scene.render.fps_base
        output = {
            "metadata": {
                "epsilon": detection.COLLISION_EPSILON,
                "fps": fps,
                "frame_start": scene.frame_start,
                "frame_end": scene.frame_end,
                "targets_collection": settings.targets_collection.name if settings.targets_collection else "",
                "colliders_collection": settings.colliders_collection.name if settings.colliders_collection else "",
            },
            "events": events,
        }

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)

        self.report({'INFO'}, f"Exported {len(events)} event(s) to {filepath}")
        return {'FINISHED'}


# --- Panels (UI for the operators above) ---


class VIEW3D_PT_collision_sounds(bpy.types.Panel):
    bl_label = "Collision Sounds"
    bl_idname = "VIEW3D_PT_collision_sounds"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"

    def draw(self, context):
        pass


class VIEW3D_PT_export(bpy.types.Panel):
    bl_label = "Export"
    bl_idname = "VIEW3D_PT_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"
    bl_order = 3
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.label(icon='EXPORT')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.collision_sounds

        layout.prop(settings, "output_path")
        layout.prop(settings, "export_json", text="Export when detecting")
        layout.separator()
        row = layout.row()
        row.enabled = bool(settings.events)
        row.operator("collision.export_json", text="Export JSON", icon='EXPORT')
        if not settings.events:
            layout.label(text="Run detection first", icon='INFO')

        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("collision.render_audio", text="Render Audio", icon='FILE_SOUND')


class VIEW3D_PT_detect_collisions(bpy.types.Panel):
    bl_label = "Detect Collisions"
    bl_idname = "VIEW3D_PT_detect_collisions"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Collision Sounds"
    bl_parent_id = "VIEW3D_PT_collision_sounds"
    bl_order = 0
    # bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.label(icon='TRACKER')

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
        layout.operator("collision.detect", icon='PLAY')
        layout.operator("collision.clear_visualization", icon='TRASH')

        if settings.events:
            layout.separator()
            layout.label(text=f"{len(settings.events)} event(s) detected")

