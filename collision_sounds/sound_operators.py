import json
import math
import os
import random

import bpy
from mathutils import Vector

from .sound_properties import get_sound_files_from_folder, AUDIO_GROUP_COLOR_ITEMS, GROUP_COLOR_CYCLE

# RGB values matching Blender's STRIP_COLOR_01–09 (linear color space).
GROUP_COLORS = {
    'COLOR_01': (0.90, 0.26, 0.26, 1.0),  # Red
    'COLOR_02': (0.87, 0.56, 0.16, 1.0),  # Orange
    'COLOR_03': (0.80, 0.74, 0.11, 1.0),  # Yellow
    'COLOR_04': (0.36, 0.75, 0.32, 1.0),  # Green
    'COLOR_05': (0.22, 0.54, 0.87, 1.0),  # Blue
    'COLOR_06': (0.54, 0.32, 0.87, 1.0),  # Purple
    'COLOR_07': (0.87, 0.43, 0.67, 1.0),  # Pink
    'COLOR_08': (0.62, 0.42, 0.24, 1.0),  # Brown
    'COLOR_09': (0.50, 0.50, 0.50, 1.0),  # Gray
}


# ---------------------------------------------------------------------------
# VSE helpers (compatible with Blender 4.x and 5.0+)
# ---------------------------------------------------------------------------

def _get_sequencer_scene(context):
    if hasattr(context, 'sequencer_scene') and context.sequencer_scene:
        return context.sequencer_scene
    return context.scene


def _add_sound_strip(sed, name, filepath, channel, frame_start):
    if hasattr(sed, 'strips') and hasattr(sed.strips, 'new_sound'):
        return sed.strips.new_sound(name=name, filepath=filepath, channel=channel, frame_start=frame_start)
    if hasattr(sed, 'sequences') and hasattr(sed.sequences, 'new_sound'):
        return sed.sequences.new_sound(name=name, filepath=filepath, channel=channel, frame_start=frame_start)
    raise RuntimeError("Could not find API to add sound strips")


def _get_all_strips(sed):
    for attr in ('strips_all', 'strips', 'sequences_all', 'sequences'):
        val = getattr(sed, attr, None)
        if val is not None:
            return list(val)
    return []  


def _find_next_available_channel(sed):
    all_strips = _get_all_strips(sed)
    if not all_strips:
        return 1
    return max(s.channel for s in all_strips) + 1


def _strips_overlap(a, b):
    s1 = getattr(a, 'frame_final_start', a.frame_start)
    e1 = getattr(a, 'frame_final_end', a.frame_start + 48)
    s2 = getattr(b, 'frame_final_start', b.frame_start)
    e2 = getattr(b, 'frame_final_end', b.frame_start + 48)
    return s1 < e2 and s2 < e1


def _separate_overlapping_strips(strips, base_channel):
    sorted_strips = sorted(
        strips,
        key=lambda s: getattr(s, 'frame_final_start', s.frame_start),
    )
    channel_strips = {}
    for strip in sorted_strips:
        ch = base_channel
        while True:
            if ch not in channel_strips:
                channel_strips[ch] = [strip]
                strip.channel = ch
                break
            if not any(_strips_overlap(strip, ex) for ex in channel_strips[ch]):
                channel_strips[ch].append(strip)
                strip.channel = ch
                break
            ch += 1


def _apply_strip_color(strip, obj_name, color_map):
    if not hasattr(strip, 'color_tag'):
        return
    if obj_name not in color_map:
        color_map[obj_name] = (len(color_map) % 9) + 1
    strip.color_tag = f'COLOR_{color_map[obj_name]:02d}'


def _random_volume(base, randomness):
    if randomness <= 0:
        return base
    return random.uniform(base * (1.0 - randomness), base)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def _selected_collision_spheres(context):
    return [obj for obj in context.selected_objects if "collision_frame" in obj]


def _all_assigned_spheres():
    from .visualize_collisions import VIS_COLLECTION_NAME
    if VIS_COLLECTION_NAME not in bpy.data.collections:
        return []
    col = bpy.data.collections[VIS_COLLECTION_NAME]
    return [obj for obj in col.objects if "audio_group_id" in obj]


def _store_group_assignment(obj, group_id):
    """Persist the audio group ID on a collision sphere."""
    obj["audio_group_id"] = group_id


def _resolve_group_sound_path(obj, context):
    """Pick a sound file path from the group assignment stored on *obj*."""
    group_id = obj.get("audio_group_id", None)
    if group_id is None:
        return None
    settings = context.scene.collision_sound_import
    group = next((g for g in settings.audio_groups if g.group_id == group_id), None)
    if group is None:
        return None
    folder = bpy.path.abspath(group.sound_folder)
    if not folder or not os.path.isdir(folder):
        return None
    available = get_sound_files_from_folder(folder)
    if not available:
        return None
    if group.sound_selection_mode == 'SINGLE':
        fname = group.sound_file
        if fname and fname != 'NONE':
            path = os.path.join(folder, fname)
            if os.path.exists(path):
                return path
    return os.path.join(folder, random.choice(available))


def _add_strips_for_spheres(context, spheres, report_fn):
    """Create VSE strips for *spheres* using their stored group assignments.

    Returns the number of strips created.
    """
    settings = context.scene.collision_sound_import
    scene = context.scene

    resolved = []
    for obj in spheres:
        path = _resolve_group_sound_path(obj, context)
        if path:
            resolved.append((obj, path))
    if not resolved:
        report_fn({'ERROR'}, "No valid sound assignments on the given points")
        return 0

    camera_obj = None
    if settings.use_camera_volume_pan:
        camera_obj = scene.camera
        if not camera_obj:
            report_fn({'ERROR'},
                      "No active camera. Set one or disable Camera Distance option.")
            return 0

    speeds = [obj["collision_raw_speed"] for obj, _ in resolved]
    min_speed = min(speeds)
    max_speed = max(speeds)
    speed_range = max_speed - min_speed if max_speed > min_speed else 1.0

    cam_data_cache = None
    if camera_obj:
        positions = [Vector(obj["collision_position"]) for obj, _ in resolved]
        cam_data_cache = _precompute_camera_data(context, positions, camera_obj)

    seq_scene = _get_sequencer_scene(context)
    if not seq_scene.sequence_editor:
        seq_scene.sequence_editor_create()
    sed = seq_scene.sequence_editor
    base_channel = _find_next_available_channel(sed)

    new_strips = []

    for obj, sound_path in resolved:
        speed = obj["collision_raw_speed"]
        frame = obj["collision_frame"]
        position = Vector(obj["collision_position"])
        active = obj["collision_active"]
        passive = obj["collision_passive"]

        volume = 1.0
        pan = 0.0

        if settings.use_speed_volume:
            t = (speed - min_speed) / speed_range if speed_range > 0 else 1.0
            volume *= (settings.speed_volume_softer
                       + t * (settings.speed_volume_louder - settings.speed_volume_softer))

        if camera_obj and cam_data_cache:
            cam_vol, cam_pan = _camera_volume_pan(
                position, camera_obj, frame, cam_data_cache,
            )
            volume *= cam_vol
            pan = cam_pan

        if settings.use_volume_randomness:
            volume = _random_volume(volume, settings.volume_randomness)

        frame_int = int(round(frame))
        vol_pct = int(round(volume * 100))
        name = f"{active}_{passive}_v{vol_pct}"

        strip = _add_sound_strip(sed, name, sound_path, base_channel, frame_int)

        if hasattr(strip, 'volume'):
            strip.volume = volume
        if hasattr(strip, 'sound') and hasattr(strip.sound, 'use_mono'):
            strip.sound.use_mono = True
        if settings.use_camera_volume_pan and hasattr(strip, 'pan'):
            strip.pan = pan

        # Apply the audio group's color to the strip.
        group_id = obj.get("audio_group_id")
        if group_id is not None:
            group = next((g for g in settings.audio_groups if g.group_id == group_id), None)
            if group and hasattr(strip, 'color_tag'):
                strip.color_tag = group.color

        new_strips.append(strip)

    if new_strips:
        _separate_overlapping_strips(new_strips, base_channel)

    return len(new_strips)


# ---- Audio group operators ------------------------------------------------

class COLLISION_OT_add_audio_group(bpy.types.Operator):
    """Add a new audio group"""
    bl_idname = "collision.add_audio_group"
    bl_label = "Add Audio Group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.collision_sound_import
        groups = settings.audio_groups

        next_color = GROUP_COLOR_CYCLE[len(groups) % len(GROUP_COLOR_CYCLE)]

        # Find the next available "Group N" number.
        n = len(groups) + 1
        existing_names = {g.name for g in groups}
        while f"Group {n}" in existing_names:
            n += 1
        name = f"Group {n}"

        group = groups.add()
        group.group_id = settings.next_group_id
        group.color = next_color
        group.name = name
        settings.next_group_id += 1
        settings.active_audio_group_index = len(groups) - 1

        return {'FINISHED'}


class COLLISION_OT_remove_audio_group(bpy.types.Operator):
    """Remove the active audio group"""
    bl_idname = "collision.remove_audio_group"
    bl_label = "Remove Audio Group"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.collision_sound_import.audio_groups) > 1

    def execute(self, context):
        settings = context.scene.collision_sound_import
        groups = settings.audio_groups
        idx = settings.active_audio_group_index

        if not (0 <= idx < len(groups)):
            return {'CANCELLED'}

        removed_id = groups[idx].group_id
        groups.remove(idx)
        settings.active_audio_group_index = max(0, min(idx, len(groups) - 1))

        # Clear the group assignment and reset the viewport color on affected spheres.
        from .visualize_collisions import VIS_COLLECTION_NAME
        if VIS_COLLECTION_NAME in bpy.data.collections:
            col = bpy.data.collections[VIS_COLLECTION_NAME]
            for obj in col.objects:
                if obj.get("audio_group_id") == removed_id:
                    del obj["audio_group_id"]
                    obj.color = (1.0, 1.0, 1.0, 1.0)

        return {'FINISHED'}


# ---- Per-group folder selection operators ------------------------------------------------

class COLLISION_OT_select_group_sound_folder(bpy.types.Operator):
    """Open a file browser to select a sound folder for the active audio group"""
    bl_idname = "collision.select_group_sound_folder"
    bl_label = "Select Sound Folder"
    bl_options = {'REGISTER'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH')

    def execute(self, context):
        settings = context.scene.collision_sound_import
        idx = settings.active_audio_group_index
        if 0 <= idx < len(settings.audio_groups):
            settings.audio_groups[idx].sound_folder = self.directory
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class COLLISION_OT_use_default_group_sounds(bpy.types.Operator):
    """Use the bundled default sound files for the active audio group"""
    bl_idname = "collision.use_default_group_sounds"
    bl_label = "Use Default Sounds"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from pathlib import Path
        sounds_folder = str(Path(__file__).resolve().parent / "sounds")
        if not os.path.isdir(sounds_folder):
            self.report({'ERROR'}, "Default sounds folder not found — add .wav files to the addon's sounds/ folder")
            return {'CANCELLED'}

        settings = context.scene.collision_sound_import
        idx = settings.active_audio_group_index
        if not (0 <= idx < len(settings.audio_groups)):
            self.report({'ERROR'}, "No active audio group")
            return {'CANCELLED'}

        settings.audio_groups[idx].sound_folder = sounds_folder
        count = len(get_sound_files_from_folder(sounds_folder))
        self.report({'INFO'}, f"Using default sounds ({count} file(s))")
        return {'FINISHED'}


# ---- Selection-based assignment operator ------------------------------------------------

class COLLISION_OT_assign_sound(bpy.types.Operator):
    """Assign the active audio group to the selected collision points"""
    bl_idname = "collision.assign_sound"
    bl_label = "Assign to Group"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not _selected_collision_spheres(context):
            return False
        settings = context.scene.collision_sound_import
        idx = settings.active_audio_group_index
        return 0 <= idx < len(settings.audio_groups)

    def execute(self, context):
        settings = context.scene.collision_sound_import
        idx = settings.active_audio_group_index
        if not (0 <= idx < len(settings.audio_groups)):
            self.report({'ERROR'}, "No active audio group")
            return {'CANCELLED'}

        group = settings.audio_groups[idx]
        color = GROUP_COLORS.get(group.color, (1.0, 1.0, 1.0, 1.0))
        selected = _selected_collision_spheres(context)
        for obj in selected:
            _store_group_assignment(obj, group.group_id)
            obj.color = color

        self.report({'INFO'}, f"Assigned {len(selected)} point(s) to group \"{group.name}\"")
        return {'FINISHED'}


class COLLISION_OT_readd_assigned_sounds(bpy.types.Operator):
    """Create VSE strips for all collision points that have a sound group assigned"""
    bl_idname = "collision.readd_assigned_sounds"
    bl_label = "Place Sounds on Markers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(_all_assigned_spheres()) > 0

    def execute(self, context):
        spheres = _all_assigned_spheres()
        count = _add_strips_for_spheres(context, spheres, self.report)
        if count == 0:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Added {count} sound strip(s)")
        return {'FINISHED'}


class COLLISION_OT_load_json_events(bpy.types.Operator):
    """Load collision events from a JSON file into the internal data"""
    bl_idname = "collision.load_json_events"
    bl_label = "Load Events from JSON"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        if not self.filepath or not os.path.exists(self.filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        with open(self.filepath, "r") as f:
            data = json.load(f)

        json_events = data.get("events", [])
        if not json_events:
            self.report({'WARNING'}, "JSON contains no events")
            return {'CANCELLED'}

        settings = context.scene.collision_sounds
        settings.events.clear()
        for e in json_events:
            item = settings.events.add()
            item.frame = e.get("frame", 0)
            item.time = e.get("time", 0.0)
            item.active = e.get("target", e.get("active", ""))
            item.passive = e.get("collider", e.get("passive", ""))
            item.position = e.get("position", [0, 0, 0])
            item.velocity = e.get("velocity", [0, 0, 0])
            item.relative_velocity = e.get("relative_velocity", [0, 0, 0])
            item.speed = e.get("speed", 0.0)

        self.report({'INFO'}, f"Loaded {len(json_events)} event(s) from JSON")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class COLLISION_OT_clear_sounds(bpy.types.Operator):
    """Remove all sound strips that were added by this addon"""
    bl_idname = "collision.clear_sounds"
    bl_label = "Clear All Sounds"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        seq_scene = _get_sequencer_scene(context)
        if not seq_scene.sequence_editor:
            self.report({'INFO'}, "No strips to remove")
            return {'CANCELLED'}

        sed = seq_scene.sequence_editor
        all_strips = _get_all_strips(sed)
        to_remove = [s for s in all_strips if s.type == 'SOUND']

        if not to_remove:
            self.report({'INFO'}, "No sound strips to remove")
            return {'CANCELLED'}

        for strip in to_remove:
            if hasattr(sed, 'strips'):
                sed.strips.remove(strip)
            elif hasattr(sed, 'sequences'):
                sed.sequences.remove(strip)

        self.report({'INFO'}, f"Removed {len(to_remove)} sound strip(s)")
        return {'FINISHED'}


class COLLISION_OT_render_audio(bpy.types.Operator):
    """Render the scene's audio (same as Render > Render Audio)"""
    bl_idname = "collision.render_audio"
    bl_label = "Render Audio"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.sound.mixdown('INVOKE_DEFAULT')
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def _precompute_camera_data(context, positions, camera_obj):
    """Pre-compute distance range and horizontal FOV for camera-based volume."""
    cam_pos = camera_obj.matrix_world.translation
    distances = [(p - cam_pos).length for p in positions]

    min_d = min(distances) if distances else 0.0
    max_d = max(distances) if distances else 1.0
    d_range = max_d - min_d if max_d > min_d else 1.0

    cam = camera_obj.data
    render = context.scene.render
    ax = render.resolution_x * render.pixel_aspect_x
    ay = render.resolution_y * render.pixel_aspect_y
    if cam.sensor_fit == 'VERTICAL':
        h_fov = 2 * math.atan(math.tan(cam.angle / 2) * (ax / ay))
    elif cam.sensor_fit == 'HORIZONTAL':
        h_fov = cam.angle
    else:
        h_fov = cam.angle if ax >= ay else 2 * math.atan(math.tan(cam.angle / 2) * (ax / ay))

    return {
        'min_d': min_d,
        'max_d': max_d,
        'd_range': d_range,
        'half_fov': (h_fov / 2) if h_fov > 0 else math.radians(30),
    }


def _camera_volume_pan(position, camera_obj, frame, cache):
    """Compute volume and stereo pan for a collision position relative to camera."""
    settings = bpy.context.scene.collision_sound_import
    cam_pos = camera_obj.matrix_world.translation
    distance = (position - cam_pos).length

    t = 1.0 - (distance - cache['min_d']) / cache['d_range'] if cache['d_range'] > 0 else 1.0
    vol = settings.camera_volume_softer + t * (settings.camera_volume_louder - settings.camera_volume_softer)

    cam_inv = camera_obj.matrix_world.inverted()
    local = cam_inv @ position
    depth = -local.z
    if depth > 0:
        angle = math.atan2(local.x, depth)
        pan = max(-1.0, min(1.0, angle / cache['half_fov']))
    else:
        pan = 0.0

    return vol, pan
