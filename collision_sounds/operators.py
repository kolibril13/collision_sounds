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