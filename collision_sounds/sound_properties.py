import os

import bpy

SUPPORTED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.ogg', '.flac', '.aiff', '.aif'}

AUDIO_GROUP_COLOR_ITEMS = [
    ('COLOR_01', "Red",    "Red",    'STRIP_COLOR_01', 0),
    ('COLOR_02', "Orange", "Orange", 'STRIP_COLOR_02', 1),
    ('COLOR_03', "Yellow", "Yellow", 'STRIP_COLOR_03', 2),
    ('COLOR_04', "Green",  "Green",  'STRIP_COLOR_04', 3),
    ('COLOR_05', "Blue",   "Blue",   'STRIP_COLOR_05', 4),
    ('COLOR_06', "Purple", "Purple", 'STRIP_COLOR_06', 5),
    ('COLOR_07', "Pink",   "Pink",   'STRIP_COLOR_07', 6),
    ('COLOR_08', "Brown",  "Brown",  'STRIP_COLOR_08', 7),
    ('COLOR_09', "Gray",   "Gray",   'STRIP_COLOR_09', 8),
]

# Contrasting color order: each successive color is visually distinct from the previous.
GROUP_COLOR_CYCLE = [
    'COLOR_05',  # Blue
    'COLOR_01',  # Red
    'COLOR_04',  # Green
    'COLOR_03',  # Yellow
    'COLOR_06',  # Purple
    'COLOR_02',  # Orange
    'COLOR_07',  # Pink
    'COLOR_08',  # Brown
    'COLOR_09',  # Gray
]


def default_sounds_folder():
    """Return the path to the bundled default sounds folder, or empty string if missing."""
    from pathlib import Path
    folder = str(Path(__file__).resolve().parent / "sounds")
    return folder if os.path.isdir(folder) else ""


def get_sound_files_from_folder(folder_path):
    """Get all supported audio files from a folder."""
    if not folder_path or not os.path.isdir(folder_path):
        return []
    sound_files = []
    for filename in os.listdir(folder_path):
        ext = os.path.splitext(filename)[1].lower()
        if ext in SUPPORTED_AUDIO_EXTENSIONS:
            sound_files.append(filename)
    return sorted(sound_files)


def get_group_sound_files_enum(self, context):
    """Return a list of sound files for a per-group enum property."""
    folder_path = bpy.path.abspath(self.sound_folder) if self.sound_folder else ""
    items = []
    sound_files = get_sound_files_from_folder(folder_path)
    if not sound_files:
        items.append(('NONE', "No sounds found", "Select a folder with audio files", 'ERROR', 0))
    else:
        for i, filename in enumerate(sound_files):
            items.append((filename, filename, f"Sound file: {filename}", 'SOUND', i))
    return items


class AudioGroup(bpy.types.PropertyGroup):
    group_id: bpy.props.IntProperty(
        name="Group ID",
        description="Unique identifier for this group",
        default=-1,
    )
    color: bpy.props.EnumProperty(
        name="Color",
        description="Color tag for this audio group",
        items=AUDIO_GROUP_COLOR_ITEMS,
        default='COLOR_01',
    )
    name: bpy.props.StringProperty(
        name="Name",
        description="Display name for this audio group",
        default="Group",
    )
    sound_folder: bpy.props.StringProperty(
        name="Sound Folder",
        description="Path to folder containing sound files for this group",
        subtype='DIR_PATH',
        default="",
    )
    sound_selection_mode: bpy.props.EnumProperty(
        name="Sound Selection Mode",
        description="How to select sounds for collision events in this group",
        items=[
            ('SINGLE', "Single Sound", "Use one selected sound file for every event", 'SOUND', 0),
            ('RANDOM', "Random Sound", "Randomly select a sound file from the folder for each event", 'FILE_REFRESH', 1),
        ],
        default='SINGLE',
    )
    sound_file: bpy.props.EnumProperty(
        name="Sound File",
        description="Select a sound file from the folder",
        items=get_group_sound_files_enum,
    )


def _update_marker_threshold_colors(context):
    """Set markers below the speed threshold to black; restore others to their group color."""
    from .visualize_collisions import VIS_COLLECTION_NAME
    from .sound_operators import GROUP_COLORS

    if VIS_COLLECTION_NAME not in bpy.data.collections:
        return
    col = bpy.data.collections[VIS_COLLECTION_NAME]
    settings = context.scene.collision_sound_import
    threshold = settings.markers_sound_threshold

    for obj in col.objects:
        speed_t = obj.get("collision_speed", 0.0)
        if speed_t < threshold:
            obj.color = (0.0, 0.0, 0.0, 1.0)
        else:
            group_id = obj.get("audio_group_id")
            if group_id is not None:
                group = next((g for g in settings.audio_groups if g.group_id == group_id), None)
                if group:
                    obj.color = GROUP_COLORS.get(group.color, (1.0, 1.0, 1.0, 1.0))
                else:
                    obj.color = (1.0, 1.0, 1.0, 1.0)
            else:
                obj.color = (1.0, 1.0, 1.0, 1.0)


class SoundImportSettings(bpy.types.PropertyGroup):
    use_speed_volume: bpy.props.BoolProperty(
        name="Collision Speed → Volume",
        description="Map collision speed to strip volume",
        default=True,
    )
    speed_volume_softer: bpy.props.FloatProperty(
        name="Softer",
        description="Volume for the slowest collisions",
        default=0.3, min=0.0, max=1.0, subtype='FACTOR',
    )
    speed_volume_louder: bpy.props.FloatProperty(
        name="Louder",
        description="Volume for the fastest collisions",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
    )

    use_camera_volume_pan: bpy.props.BoolProperty(
        name="Camera Distance → Volume & Pan",
        description="Volume from camera distance, stereo pan from horizontal angle",
        default=False,
    )
    camera_volume_softer: bpy.props.FloatProperty(
        name="Softer",
        description="Volume for collisions farthest from camera",
        default=0.3, min=0.0, max=1.0, subtype='FACTOR',
    )
    camera_volume_louder: bpy.props.FloatProperty(
        name="Louder",
        description="Volume for collisions nearest to camera",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
    )

    use_volume_randomness: bpy.props.BoolProperty(
        name="Randomize Volume",
        description="Add random variation to the final volume",
        default=True,
    )
    volume_randomness: bpy.props.FloatProperty(
        name="Amount",
        description="Random variation amount (0 = none, 1 = can reduce to 0)",
        default=0.2, min=0.0, max=1.0, subtype='FACTOR',
    )

    markers_sound_threshold: bpy.props.FloatProperty(
        name="Markers Sound Threshold",
        description="Ignore markers with a normalized speed below this value. They turn black and are excluded from sound placement",
        default=0.0, min=0.0, max=1.0, subtype='FACTOR',
        update=lambda self, ctx: _update_marker_threshold_colors(ctx),
    )

    # Audio groups.
    audio_groups: bpy.props.CollectionProperty(type=AudioGroup)
    active_audio_group_index: bpy.props.IntProperty(
        name="Active Audio Group",
        default=0,
    )
    next_group_id: bpy.props.IntProperty(
        name="Next Group ID",
        description="Internal counter used to generate unique group IDs",
        default=0,
        options={'HIDDEN'},
    )


def _ensure_default_groups():
    """Create a default 'Group 1' on every scene that has no audio groups."""
    for scene in bpy.data.scenes:
        settings = scene.collision_sound_import
        if len(settings.audio_groups) == 0:
            group = settings.audio_groups.add()
            group.group_id = settings.next_group_id
            group.color = GROUP_COLOR_CYCLE[0]
            group.name = "Group 1"
            group.sound_folder = default_sounds_folder()
            settings.next_group_id += 1
            settings.active_audio_group_index = 0
    return None  # one-shot timer


@bpy.app.handlers.persistent
def _load_post_handler(dummy):
    bpy.app.timers.register(_ensure_default_groups, first_interval=0.0)


def register():
    bpy.types.Scene.collision_sound_import = bpy.props.PointerProperty(
        type=SoundImportSettings,
    )
    bpy.app.handlers.load_post.append(_load_post_handler)
    bpy.app.timers.register(_ensure_default_groups, first_interval=0.1)


def unregister():
    if _load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post_handler)
    del bpy.types.Scene.collision_sound_import
