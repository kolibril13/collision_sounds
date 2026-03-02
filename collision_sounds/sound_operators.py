import json
import math
import os
import random

import bpy
from mathutils import Vector

from .sound_properties import get_sound_files_from_folder


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

class COLLISION_OT_add_sounds(bpy.types.Operator):
    """Add sound strips to the VSE for each detected collision event"""
    bl_idname = "collision.add_sounds"
    bl_label = "Add Sounds"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.collision_sounds.events) > 0

    def execute(self, context):
        scene = context.scene
        events = scene.collision_sounds.events
        settings = scene.collision_sound_import

        sound_folder = bpy.path.abspath(settings.sound_folder)
        if not sound_folder or not os.path.isdir(sound_folder):
            self.report({'ERROR'}, "Select a valid sound folder first")
            return {'CANCELLED'}

        available = get_sound_files_from_folder(sound_folder)
        if not available:
            self.report({'ERROR'}, "No audio files found in the selected folder")
            return {'CANCELLED'}

        if settings.sound_selection_mode == 'SINGLE':
            if not settings.sound_file or settings.sound_file == 'NONE':
                self.report({'ERROR'}, "Select a sound file")
                return {'CANCELLED'}
            single_path = os.path.join(sound_folder, settings.sound_file)
            if not os.path.exists(single_path):
                self.report({'ERROR'}, f"Sound file not found: {single_path}")
                return {'CANCELLED'}

        # Camera setup (if enabled).
        camera_obj = None
        if settings.use_camera_volume_pan:
            camera_obj = scene.camera
            if not camera_obj:
                self.report({'ERROR'}, "No active camera. Set one or disable Camera Distance option.")
                return {'CANCELLED'}

        # Pre-compute speed range for volume mapping.
        speeds = [e.speed for e in events]
        min_speed = min(speeds)
        max_speed = max(speeds)
        speed_range = max_speed - min_speed if max_speed > min_speed else 1.0

        # Pre-compute camera distance range and FOV.
        cam_data_cache = None
        if camera_obj:
            cam_data_cache = _precompute_camera_data(
                context, [Vector(e.position) for e in events], camera_obj,
            )

        # Ensure VSE exists.
        seq_scene = _get_sequencer_scene(context)
        if not seq_scene.sequence_editor:
            seq_scene.sequence_editor_create()
        sed = seq_scene.sequence_editor
        base_channel = _find_next_available_channel(sed)

        # Insert strips.
        new_strips = []
        color_map = {}
        strip_obj_map = {}

        for event in events:
            sound_path = (
                os.path.join(sound_folder, random.choice(available))
                if settings.sound_selection_mode == 'RANDOM'
                else single_path
            )

            volume = 1.0
            pan = 0.0

            if settings.use_speed_volume:
                t = (event.speed - min_speed) / speed_range if speed_range > 0 else 1.0
                volume *= settings.speed_volume_softer + t * (settings.speed_volume_louder - settings.speed_volume_softer)

            if camera_obj and cam_data_cache:
                cam_vol, cam_pan = _camera_volume_pan(
                    Vector(event.position), camera_obj, event.frame, cam_data_cache,
                )
                volume *= cam_vol
                pan = cam_pan

            if settings.use_volume_randomness:
                volume = _random_volume(volume, settings.volume_randomness)

            frame_int = int(round(event.frame))
            vol_pct = int(round(volume * 100))
            name = f"{event.active}_{event.passive}_v{vol_pct}"

            strip = _add_sound_strip(sed, name, sound_path, base_channel, frame_int)

            if hasattr(strip, 'volume'):
                strip.volume = volume
            if hasattr(strip, 'sound') and hasattr(strip.sound, 'use_mono'):
                strip.sound.use_mono = True
            if settings.use_camera_volume_pan and hasattr(strip, 'pan'):
                strip.pan = pan

            _apply_strip_color(strip, event.active, color_map)
            strip_obj_map[strip] = event.active
            new_strips.append(strip)

        if new_strips:
            _separate_overlapping_strips(new_strips, base_channel)
            for strip in new_strips:
                _apply_strip_color(strip, strip_obj_map[strip], color_map)

        self.report({'INFO'}, f"Added {len(new_strips)} sound strip(s) (channel {base_channel}+)")
        return {'FINISHED'}


def _selected_collision_spheres(context):
    return [obj for obj in context.selected_objects if "collision_frame" in obj]


def _all_assigned_spheres():
    from .debug_visualize import DEBUG_COLLECTION_NAME
    if DEBUG_COLLECTION_NAME not in bpy.data.collections:
        return []
    col = bpy.data.collections[DEBUG_COLLECTION_NAME]
    return [obj for obj in col.objects if "sound_folder" in obj]


def _store_sound_assignment(obj, settings):
    """Persist the current sound folder/mode on a collision sphere."""
    obj["sound_folder"] = bpy.path.abspath(settings.sound_folder)
    obj["sound_selection_mode"] = settings.sound_selection_mode
    if settings.sound_selection_mode == 'SINGLE':
        obj["sound_file"] = settings.sound_file


def _validate_sound_settings(settings, report_fn):
    """Check current panel sound settings. Returns (folder, single_path) or None."""
    sound_folder = bpy.path.abspath(settings.sound_folder)
    if not sound_folder or not os.path.isdir(sound_folder):
        report_fn({'ERROR'}, "Select a valid sound folder first")
        return None

    available = get_sound_files_from_folder(sound_folder)
    if not available:
        report_fn({'ERROR'}, "No audio files found in the selected folder")
        return None

    single_path = None
    if settings.sound_selection_mode == 'SINGLE':
        if not settings.sound_file or settings.sound_file == 'NONE':
            report_fn({'ERROR'}, "Select a sound file")
            return None
        single_path = os.path.join(sound_folder, settings.sound_file)
        if not os.path.exists(single_path):
            report_fn({'ERROR'}, f"Sound file not found: {single_path}")
            return None

    return sound_folder, single_path


def _resolve_sound_path(obj):
    """Pick a sound file path from the assignment stored on *obj*."""
    folder = obj.get("sound_folder", "")
    if not folder or not os.path.isdir(folder):
        return None
    available = get_sound_files_from_folder(folder)
    if not available:
        return None
    mode = obj.get("sound_selection_mode", "RANDOM")
    if mode == 'SINGLE':
        fname = obj.get("sound_file", "")
        path = os.path.join(folder, fname)
        if os.path.exists(path):
            return path
    return os.path.join(folder, random.choice(available))


def _add_strips_for_spheres(context, spheres, report_fn):
    """Create VSE strips for *spheres* using their stored sound assignments.

    Returns the number of strips created.
    """
    settings = context.scene.collision_sound_import
    scene = context.scene

    resolved = []
    for obj in spheres:
        path = _resolve_sound_path(obj)
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
    color_map = {}
    strip_obj_map = {}

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

        _apply_strip_color(strip, active, color_map)
        strip_obj_map[strip] = active
        new_strips.append(strip)

    if new_strips:
        _separate_overlapping_strips(new_strips, base_channel)
        for strip in new_strips:
            _apply_strip_color(strip, strip_obj_map[strip], color_map)

    return len(new_strips)


# ---- Selection-based operators ------------------------------------------------

class COLLISION_OT_assign_sound(bpy.types.Operator):
    """Remember the current sound folder for the selected collision points"""
    bl_idname = "collision.assign_sound"
    bl_label = "Assign Sound"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(_selected_collision_spheres(context)) > 0

    def execute(self, context):
        settings = context.scene.collision_sound_import
        if _validate_sound_settings(settings, self.report) is None:
            return {'CANCELLED'}

        selected = _selected_collision_spheres(context)
        for obj in selected:
            _store_sound_assignment(obj, settings)

        self.report({'INFO'}, f"Assigned sound to {len(selected)} point(s)")
        return {'FINISHED'}


class COLLISION_OT_assign_and_add_sound(bpy.types.Operator):
    """Assign the current sound folder and immediately add VSE strips for the selection"""
    bl_idname = "collision.assign_and_add_sound"
    bl_label = "Assign & Add"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(_selected_collision_spheres(context)) > 0

    def execute(self, context):
        settings = context.scene.collision_sound_import
        if _validate_sound_settings(settings, self.report) is None:
            return {'CANCELLED'}

        selected = _selected_collision_spheres(context)
        for obj in selected:
            _store_sound_assignment(obj, settings)

        count = _add_strips_for_spheres(context, selected, self.report)
        if count == 0:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Assigned & added {count} sound strip(s)")
        return {'FINISHED'}


class COLLISION_OT_readd_assigned_sounds(bpy.types.Operator):
    """Re-create VSE strips for all collision points that have a sound assigned"""
    bl_idname = "collision.readd_assigned_sounds"
    bl_label = "Re-add All Assigned"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(_all_assigned_spheres()) > 0

    def execute(self, context):
        spheres = _all_assigned_spheres()
        count = _add_strips_for_spheres(context, spheres, self.report)
        if count == 0:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Re-added {count} sound strip(s)")
        return {'FINISHED'}


class COLLISION_OT_clear_assignments(bpy.types.Operator):
    """Remove sound assignments from all collision points"""
    bl_idname = "collision.clear_assignments"
    bl_label = "Clear Assignments"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(_all_assigned_spheres()) > 0

    def execute(self, context):
        spheres = _all_assigned_spheres()
        for obj in spheres:
            for key in ("sound_folder", "sound_selection_mode", "sound_file"):
                if key in obj:
                    del obj[key]
        self.report({'INFO'}, f"Cleared assignments from {len(spheres)} point(s)")
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


class COLLISION_OT_select_sound_folder(bpy.types.Operator):
    """Open file browser to select a folder containing sound files"""
    bl_idname = "collision.select_sound_folder"
    bl_label = "Select Sound Folder"
    bl_options = {'REGISTER'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH')

    def execute(self, context):
        context.scene.collision_sound_import.sound_folder = self.directory
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class COLLISION_OT_use_default_sounds(bpy.types.Operator):
    """Use the bundled default sound files"""
    bl_idname = "collision.use_default_sounds"
    bl_label = "Use Default Sounds"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from pathlib import Path
        sounds_folder = str(Path(__file__).resolve().parent / "sounds")
        if os.path.isdir(sounds_folder):
            context.scene.collision_sound_import.sound_folder = sounds_folder
            from .sound_properties import get_sound_files_from_folder
            count = len(get_sound_files_from_folder(sounds_folder))
            self.report({'INFO'}, f"Using default sounds ({count} file(s))")
            return {'FINISHED'}
        self.report({'ERROR'}, "Default sounds folder not found — add .wav files to the addon's sounds/ folder")
        return {'CANCELLED'}


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
