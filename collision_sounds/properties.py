import bpy


class CollisionSoundsSettings(bpy.types.PropertyGroup):
    targets_collection: bpy.props.PointerProperty(
        name="Targets",
        description="Collection of objects that hit things",
        type=bpy.types.Collection,
    )
    colliders_collection: bpy.props.PointerProperty(
        name="Colliders",
        description="Collection of surfaces/objects that get hit",
        type=bpy.types.Collection,
    )
    output_path: bpy.props.StringProperty(
        name="Output",
        description="Path to save collision events JSON",
        default="//collision_events.json",
        subtype='FILE_PATH',
    )


def register():
    bpy.types.Scene.collision_sounds = bpy.props.PointerProperty(
        type=CollisionSoundsSettings,
    )


def unregister():
    del bpy.types.Scene.collision_sounds
