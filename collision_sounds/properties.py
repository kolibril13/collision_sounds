import os

import bpy


class CollisionEvent(bpy.types.PropertyGroup):
    frame: bpy.props.FloatProperty(name="Frame")
    time: bpy.props.FloatProperty(name="Time")
    active: bpy.props.StringProperty(name="Active")
    passive: bpy.props.StringProperty(name="Passive")
    position: bpy.props.FloatVectorProperty(name="Position", size=3)
    velocity: bpy.props.FloatVectorProperty(name="Velocity", size=3)
    relative_velocity: bpy.props.FloatVectorProperty(name="Relative Velocity", size=3)
    speed: bpy.props.FloatProperty(name="Speed")


class CollisionSoundsSettings(bpy.types.PropertyGroup):
    targets_collection: bpy.props.PointerProperty(
        name="Targets",
        description="Collection of objects that hit things (e.g. falling balls)",
        type=bpy.types.Collection,
    )
    colliders_collection: bpy.props.PointerProperty(
        name="Colliders",
        description="Collection of surfaces/objects that get hit (e.g. ground, walls)",
        type=bpy.types.Collection,
    )
    events: bpy.props.CollectionProperty(
        name="Collision Events",
        type=CollisionEvent,
    )
    precision_mode: bpy.props.BoolProperty(
        name="Precision Mode",
        description="Scan at sub-frame intervals for more accurate collision timing",
        default=False,
    )
    substeps: bpy.props.IntProperty(
        name="Substeps",
        description="Number of sub-frame steps per frame",
        default=8,
        min=2,
        max=64,
    )
    export_json: bpy.props.BoolProperty(
        name="Export JSON",
        description="Also write collision events to a JSON file",
        default=False,
    )
    output_path: bpy.props.StringProperty(
        name="Output",
        description="Path to save collision events JSON",
        default=os.path.join(os.path.expanduser("~"), "Downloads", "collision_events.json"),
        subtype='FILE_PATH',
    )


def register():
    bpy.types.Scene.collision_sounds = bpy.props.PointerProperty(
        type=CollisionSoundsSettings,
    )


def unregister():
    del bpy.types.Scene.collision_sounds
