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

        if events:
            self.report({'INFO'}, f"Found {len(events)} collision event(s)")
            for e in events:
                print(f"  Frame {e['frame']}: {e['target']} -> {e['collider']}")
        else:
            self.report({'INFO'}, "No collisions detected")

        return {'FINISHED'}
