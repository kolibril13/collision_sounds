import os

import bpy


def _sync_audio_markers_viewport_visibility(context):
    """Apply scene.show_audio_markers_viewport to the Audio Markers collection if it exists."""
    from .visualize_collisions import VIS_COLLECTION_NAME
    if VIS_COLLECTION_NAME not in bpy.data.collections:
        return
    col = bpy.data.collections[VIS_COLLECTION_NAME]
    col.hide_viewport = not context.scene.collision_sounds.show_audio_markers_viewport


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
    static_collection: bpy.props.PointerProperty(
        name="Static",
        description="Collection of objects that hit things (e.g. falling balls)",
        type=bpy.types.Collection,
    )
    dynamic_collection: bpy.props.PointerProperty(
        name="Dynamic",
        description="Collection of surfaces/objects that get hit (e.g. ground, walls)",
        type=bpy.types.Collection,
    )
    events: bpy.props.CollectionProperty(
        name="Collision Events",
        type=CollisionEvent,
    )
    show_audio_markers_viewport: bpy.props.BoolProperty(
        name="Show Audio Markers in Viewport",
        description="Toggle visibility of audio marker spheres in the 3D viewport (they are never rendered)",
        default=True,
        update=lambda self, context: _sync_audio_markers_viewport_visibility(context),
    )
    export_json: bpy.props.BoolProperty(
        name="Export when detecting",
        description="Automatically write collision events to the output path when running detection",
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
