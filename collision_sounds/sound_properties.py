import os

import bpy

SUPPORTED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.ogg', '.flac', '.aiff', '.aif'}


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


def get_sound_files_enum(self, context):
    """Return a list of sound files for the enum property."""
    settings = context.scene.collision_sound_import
    folder_path = bpy.path.abspath(settings.sound_folder)
    items = []
    sound_files = get_sound_files_from_folder(folder_path)
    if not sound_files:
        items.append(('NONE', "No sounds found", "Select a folder with audio files", 'ERROR', 0))
    else:
        for i, filename in enumerate(sound_files):
            items.append((filename, filename, f"Sound file: {filename}", 'SOUND', i))
    return items


class SoundImportSettings(bpy.types.PropertyGroup):
    sound_folder: bpy.props.StringProperty(
        name="Sound Folder",
        description="Path to folder containing sound files",
        subtype='DIR_PATH',
        default="",
    )
    sound_selection_mode: bpy.props.EnumProperty(
        name="Sound Selection Mode",
        description="How to select sounds for collision events",
        items=[
            ('RANDOM', "Random Sound", "Randomly select a sound file from the folder for each event", 'FILE_REFRESH', 0),
            ('SINGLE', "Single Sound", "Use one selected sound file for every event", 'SOUND', 1),
        ],
        default='RANDOM',
    )
    sound_file: bpy.props.EnumProperty(
        name="Sound File",
        description="Select a sound file from the folder",
        items=get_sound_files_enum,
    )

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


def register():
    bpy.types.Scene.collision_sound_import = bpy.props.PointerProperty(
        type=SoundImportSettings,
    )


def unregister():
    del bpy.types.Scene.collision_sound_import
