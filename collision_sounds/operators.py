import json
import os

import bpy

from . import detection


class COLLISION_OT_detect(bpy.types.Operator):
    bl_idname = "collision.detect"
    bl_label = "Detect Collisions"
    bl_description = "Scan the timeline for collision events between targets and colliders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.collision_sounds
        original_frame = scene.frame_current

        if settings.targets_collection is None:
            self.report({'ERROR'}, "No targets collection assigned")
            return {'CANCELLED'}
        if settings.colliders_collection is None:
            self.report({'ERROR'}, "No colliders collection assigned")
            return {'CANCELLED'}

        targets = [o for o in settings.targets_collection.objects if o.type == 'MESH']
        colliders = [o for o in settings.colliders_collection.objects if o.type == 'MESH']

        if not targets:
            self.report({'ERROR'}, "Targets collection contains no mesh objects")
            return {'CANCELLED'}
        if not colliders:
            self.report({'ERROR'}, "Colliders collection contains no mesh objects")
            return {'CANCELLED'}

        events = detection.detect_collisions(context)
        scene.frame_set(original_frame)

        # Store results in the blend-file-internal collection property.
        settings.events.clear()
        for e in events:
            item = settings.events.add()
            item.frame = e["frame"]
            item.time = e["time"]
            item.active = e["active"]
            item.passive = e["passive"]
            item.position = e["position"]
            item.velocity = e["velocity"]
            item.relative_velocity = e["relative_velocity"]
            item.speed = e["speed"]

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
