"""
Minimal Dataset B trajectory capture for Blender MCP.

Persists Intent → State → Action → State′ → Observation → Feedback
to Supabase only (no local/JSONL storage). Reuses telemetry config + consent.
"""

from __future__ import annotations

import contextlib
import logging
import platform
import queue
import threading
import time
import uuid
from collections import deque
from typing import Any

import httpx

from .telemetry import MCP_VERSION, get_telemetry

logger = logging.getLogger("blender-mcp-trajectory")

# Fallbacks if TelemetryConfig lacks the fields.
TRAJECTORY_STEPS_TABLE = "trajectory_steps"
TRAJECTORY_FEEDBACK_TABLE = "trajectory_feedback"
# 3: object entries carry aabb_min/aabb_max/dimensions and parent/constraint
# relations. Rows at <=2 have positions but no geometry, so contact- and
# collision-style analysis must filter on this.
SCHEMA_VERSION = 3
MAX_RAW_CODE_LENGTH = 8000
MAX_AGENT_OBS_BUFFER = 8
MAX_OBS_SUMMARY_CHARS = 2000
MAX_PENDING_ROWS = 256

# Auto-capture: VLM-judged metrics need an image for the step being judged, but
# the agent only screenshots when it chooses to, so most mutating steps have
# none. Render a small offscreen frame ourselves — sampled, not every step, so
# the added latency stays off the common path.
AUTO_CAPTURE_MAX_SIZE = 512
AUTO_CAPTURE_MIN_INTERVAL = 20.0

# Fallback probe for older addons lacking get_world_state_snapshot.
_SNAPSHOT_VIA_EXECUTE_CODE = r'''
import json
import bpy
import mathutils

scene = bpy.context.scene
selected = [obj.name for obj in bpy.context.selected_objects]
objects = []
for i, obj in enumerate(scene.objects):
    if i >= 50:
        break
    materials = []
    if getattr(obj, "material_slots", None):
        materials = [slot.material.name for slot in obj.material_slots if slot.material]
    entry = {
        "name": obj.name,
        "type": obj.type,
        "location": [round(float(obj.location.x), 3), round(float(obj.location.y), 3), round(float(obj.location.z), 3)],
        "rotation": [round(float(obj.rotation_euler.x), 3), round(float(obj.rotation_euler.y), 3), round(float(obj.rotation_euler.z), 3)],
        "scale": [round(float(obj.scale.x), 3), round(float(obj.scale.y), 3), round(float(obj.scale.z), 3)],
        "visible": bool(obj.visible_get()),
        "materials": materials,
    }
    bound_box = getattr(obj, "bound_box", None)
    if bound_box:
        try:
            mw = obj.matrix_world
            pts = [mw @ mathutils.Vector(c) for c in bound_box]
            entry["aabb_min"] = [round(min(p[k] for p in pts), 3) for k in range(3)]
            entry["aabb_max"] = [round(max(p[k] for p in pts), 3) for k in range(3)]
            entry["dimensions"] = [round(float(obj.dimensions.x), 3), round(float(obj.dimensions.y), 3), round(float(obj.dimensions.z), 3)]
        except Exception:
            pass
    if obj.parent:
        entry["parent"] = obj.parent.name
        entry["parent_type"] = obj.parent_type
        loc = obj.matrix_local.translation
        entry["local_location"] = [round(float(loc.x), 3), round(float(loc.y), 3), round(float(loc.z), 3)]
    constraints = []
    for c in (getattr(obj, "constraints", None) or [])[:8]:
        centry = {"type": c.type}
        target = getattr(c, "target", None)
        if target:
            centry["target"] = target.name
        constraints.append(centry)
    if constraints:
        entry["constraints"] = constraints
    modifiers = [m.type for m in (getattr(obj, "modifiers", None) or [])[:8]]
    if modifiers:
        entry["modifiers"] = modifiers
    objects.append(entry)

camera = scene.camera
camera_info = None
if camera:
    camera_info = {
        "name": camera.name,
        "location": [round(float(camera.location.x), 3), round(float(camera.location.y), 3), round(float(camera.location.z), 3)],
        "rotation": [round(float(camera.rotation_euler.x), 3), round(float(camera.rotation_euler.y), 3), round(float(camera.rotation_euler.z), 3)],
    }
    if camera.type == "CAMERA" and camera.data:
        camera_info["lens"] = round(float(camera.data.lens), 3)
        camera_info["sensor_width"] = round(float(camera.data.sensor_width), 3)

lights = []
for obj in scene.objects:
    if obj.type != "LIGHT":
        continue
    light_entry = {
        "name": obj.name,
        "location": [round(float(obj.location.x), 3), round(float(obj.location.y), 3), round(float(obj.location.z), 3)],
    }
    if obj.data:
        light_entry["light_type"] = obj.data.type
        light_entry["energy"] = round(float(obj.data.energy), 3)
    lights.append(light_entry)
    if len(lights) >= 20:
        break

print(json.dumps({
    "name": scene.name,
    "object_count": len(scene.objects),
    "selected": selected,
    "objects": objects,
    "active_camera": camera.name if camera else None,
    "camera": camera_info,
    "lights": lights,
    "materials_count": len(bpy.data.materials),
    "blender_version": bpy.app.version_string,
    "snapshot_source": "execute_code_fallback",
}))
'''


SEMANTIC_ACTIONS: dict[str, str] = {
    "execute_blender_code": "EXECUTE_CODE",
    "download_polyhaven_asset": "DOWNLOAD_ASSET",
    "set_texture": "SET_TEXTURE",
    "download_sketchfab_model": "DOWNLOAD_MODEL",
    "generate_hyper3d_model_via_text": "GENERATE_3D",
    "generate_hyper3d_model_via_images": "GENERATE_3D",
    "import_generated_asset": "IMPORT_ASSET",
    "generate_hunyuan3d_model": "GENERATE_3D",
    "import_generated_asset_hunyuan": "IMPORT_ASSET",
    "get_scene_info": "OBSERVE",
    "get_object_info": "OBSERVE",
    "get_viewport_screenshot": "OBSERVE",
}


def semantic_action_for_tool(tool_name: str) -> str:
    """Map an MCP tool name to a coarse semantic action label."""
    return SEMANTIC_ACTIONS.get(tool_name, "UNKNOWN")


# Human operators mapped to the same vocabulary as agent actions.
HUMAN_SEMANTIC_ACTIONS: dict[str, str] = {
    "transform.translate": "MOVE",
    "transform.rotate": "ROTATE",
    "transform.resize": "SCALE",
    "object.delete": "DELETE",
    "object.duplicate_move": "DUPLICATE",
    "object.duplicate": "DUPLICATE",
    "mesh.extrude_region_move": "EDIT_MESH",
    "mesh.extrude_region": "EDIT_MESH",
    "mesh.subdivide": "EDIT_MESH",
    "mesh.loopcut_slide": "EDIT_MESH",
    "mesh.bevel": "EDIT_MESH",
    "mesh.inset": "EDIT_MESH",
    "object.modifier_add": "ADD_MODIFIER",
    "object.material_slot_assign": "ASSIGN_MATERIAL",
    "material.new": "ASSIGN_MATERIAL",
    "object.shade_smooth": "MODIFY_MATERIAL",
    "object.shade_flat": "MODIFY_MATERIAL",
    "object.select_all": "SELECT",
    "view3d.select": "SELECT",
}

# Fallback for operators not listed above.
_HUMAN_SEMANTIC_PREFIXES: tuple[tuple[str, str], ...] = (
    ("mesh.", "EDIT_MESH"),
    ("object.modifier", "ADD_MODIFIER"),
    ("material.", "MODIFY_MATERIAL"),
    ("object.light", "ADD_LIGHT"),
    ("transform.", "TRANSFORM"),
    ("object.", "OBJECT_OP"),
)


def semantic_action_for_operator(bl_idname: str) -> str:
    """Map a Blender operator id to a coarse semantic action label."""
    if not bl_idname:
        return "UNKNOWN"
    mapped = HUMAN_SEMANTIC_ACTIONS.get(bl_idname)
    if mapped:
        return mapped
    for prefix, label in _HUMAN_SEMANTIC_PREFIXES:
        if bl_idname.startswith(prefix):
            return label
    return "UNKNOWN"


def compute_state_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute a compact object-level delta between two world snapshots."""
    before = before or {}
    after = after or {}

    before_objs = {
        obj["name"]: obj
        for obj in before.get("objects") or []
        if isinstance(obj, dict) and "name" in obj
    }
    after_objs = {
        obj["name"]: obj
        for obj in after.get("objects") or []
        if isinstance(obj, dict) and "name" in obj
    }

    objects_added = [name for name in after_objs if name not in before_objs]
    objects_removed = [name for name in before_objs if name not in after_objs]
    objects_changed: list[dict[str, Any]] = []
    for name in before_objs:
        if name in after_objs and before_objs[name] != after_objs[name]:
            objects_changed.append({
                "name": name,
                "before": before_objs[name],
                "after": after_objs[name],
            })

    return {
        "objects_added": objects_added,
        "objects_removed": objects_removed,
        "objects_changed": objects_changed,
        "selection_changed": before.get("selected") != after.get("selected"),
        "camera_changed": before.get("active_camera") != after.get("active_camera"),
        "object_count_before": before.get("object_count"),
        "object_count_after": after.get("object_count"),
    }


def _normalize_goal(goal: str | None) -> str:
    return (goal or "").strip()


def _cap_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    try:
        limit_i = int(limit)
    except (TypeError, ValueError):
        limit_i = 1000
    if limit_i <= 0:
        return value
    if len(value) <= limit_i:
        return value
    return value[:limit_i] + "..."


def _summarize_agent_payload(payload: Any) -> Any:
    """Keep agent observation summaries small for Supabase rows."""
    if payload is None:
        return None
    if isinstance(payload, str):
        return _cap_text(payload, MAX_OBS_SUMMARY_CHARS)
    if isinstance(payload, dict):
        keys = set(payload.keys())
        is_scene_summary = keys <= {
            "name", "object_count", "objects", "selected", "materials_count",
            "active_camera", "lights", "camera",
        }
        is_object_summary = "name" in payload and "type" in payload
        if is_scene_summary or is_object_summary:
            return payload
        try:
            import json
            return _cap_text(json.dumps(payload, default=str), MAX_OBS_SUMMARY_CHARS)
        except Exception:
            return _cap_text(str(payload), MAX_OBS_SUMMARY_CHARS)
    return _cap_text(str(payload), MAX_OBS_SUMMARY_CHARS)


class TrajectoryRecorder:
    """Consent-gated, best-effort writer for trajectory_steps / trajectory_feedback."""

    def __init__(self):
        self._lock = threading.Lock()
        self._queue: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue(
            maxsize=MAX_PENDING_ROWS
        )
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="trajectory-writer"
        )
        self._worker.start()
        self._trajectory_id: str = str(uuid.uuid4())
        self._step_index: int = 0
        self._current_goal: str | None = None
        # What the agent requested, not the privileged full state.
        self._agent_obs: deque[dict[str, Any]] = deque(maxlen=MAX_AGENT_OBS_BUFFER)
        self._last_screenshot_ref: str | None = None
        # None = unknown, True = addon has get_world_state_snapshot, False = fallback.
        self._native_snapshot_supported: bool | None = None
        self._last_auto_capture: float = 0.0
        self._auto_capture_supported: bool = True

    def _telemetry(self):
        return get_telemetry()

    def _config(self):
        return self._telemetry().config

    def _steps_table(self) -> str:
        return getattr(self._config(), "trajectory_steps_table", TRAJECTORY_STEPS_TABLE)

    def _feedback_table(self) -> str:
        return getattr(
            self._config(), "trajectory_feedback_table", TRAJECTORY_FEEDBACK_TABLE
        )

    def _can_write(self) -> bool:
        try:
            telemetry = self._telemetry()
            if not telemetry.config.enabled:
                return False
            return bool(telemetry._check_user_consent())
        except Exception as e:
            logger.debug(f"Trajectory consent check failed: {e}")
            return False

    def _snapshot_via_execute_code(self, blender) -> dict[str, Any] | None:
        """Older addons: run snapshot script through execute_code and parse JSON."""
        import json

        result = blender.send_command("execute_code", {"code": _SNAPSHOT_VIA_EXECUTE_CODE})
        raw = result.get("result", "") if isinstance(result, dict) else ""
        if not isinstance(raw, str) or not raw.strip():
            logger.debug("execute_code snapshot returned empty output")
            return None
        # Addon may append other stdout; take the last JSON object line.
        for line in reversed(raw.strip().splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "objects" in parsed:
                return parsed
        logger.debug("Could not parse execute_code snapshot JSON")
        return None

    def _snapshot_via_scene_info(self, blender) -> dict[str, Any] | None:
        """Last-resort compact snapshot using get_scene_info (very old addons)."""
        result = blender.send_command("get_scene_info")
        if not isinstance(result, dict) or "error" in result:
            return None
        objects = result.get("objects") or []
        return {
            "name": result.get("name"),
            "object_count": result.get("object_count", len(objects)),
            "selected": [],
            "objects": objects,
            "active_camera": None,
            "camera": None,
            "lights": [],
            "materials_count": result.get("materials_count"),
            "blender_version": None,
            "snapshot_source": "get_scene_info_fallback",
        }

    def snapshot_world_state(self) -> dict[str, Any] | None:
        """Fetch a compact world snapshot from Blender. Never raises.

        Prefer native addon handler; if the installed addon is older and lacks
        get_world_state_snapshot (common when users only update the MCP server),
        fall back to execute_code, then get_scene_info.
        """
        try:
            from .server import get_blender_connection

            blender = get_blender_connection()

            use_native = self._native_snapshot_supported is not False
            if use_native:
                try:
                    result = blender.send_command("get_world_state_snapshot")
                    if isinstance(result, dict) and "error" not in result:
                        self._native_snapshot_supported = True
                        if "snapshot_source" not in result:
                            result = {**result, "snapshot_source": "native"}
                        return result
                    logger.debug(f"World snapshot error payload: {result}")
                except Exception as e:
                    msg = str(e).lower()
                    if "unknown command" in msg or "get_world_state_snapshot" in msg:
                        self._native_snapshot_supported = False
                        logger.debug(
                            "Addon lacks get_world_state_snapshot; "
                            "using execute_code fallback for existing installs"
                        )
                    else:
                        logger.debug(f"Native world snapshot failed: {e}")

            if self._native_snapshot_supported is False or not use_native:
                try:
                    parsed = self._snapshot_via_execute_code(blender)
                    if parsed is not None:
                        return parsed
                except Exception as e:
                    logger.debug(f"execute_code snapshot fallback failed: {e}")

                try:
                    return self._snapshot_via_scene_info(blender)
                except Exception as e:
                    logger.debug(f"get_scene_info snapshot fallback failed: {e}")
                    return None

            try:
                parsed = self._snapshot_via_execute_code(blender)
                if parsed is not None:
                    return parsed
            except Exception as e:
                logger.debug(f"execute_code snapshot fallback failed: {e}")
            try:
                return self._snapshot_via_scene_info(blender)
            except Exception as e:
                logger.debug(f"get_scene_info snapshot fallback failed: {e}")
                return None
        except Exception as e:
            logger.debug(f"Failed to snapshot world state: {e}")
            return None

    def _should_auto_capture(self, changed: bool) -> bool:
        """Rate-limit auto-capture. Caller holds no lock."""
        if not changed or not self._auto_capture_supported:
            return False
        now = time.time()
        with self._lock:
            if now - self._last_auto_capture < AUTO_CAPTURE_MIN_INTERVAL:
                return False
            self._last_auto_capture = now
        return True

    def maybe_auto_capture(self, state_delta: dict[str, Any] | None) -> str | None:
        """Render + upload a frame for a step the agent did not screenshot.

        Only fires when the step actually changed the scene and the rate limit
        allows, so an unattended session does not upload a frame per call.
        Returns a storage ref, or None. Never raises.
        """
        try:
            if not self._can_write():
                return None
            delta = state_delta or {}
            changed = bool(
                delta.get("objects_added")
                or delta.get("objects_removed")
                or delta.get("objects_changed")
            )
            if not self._should_auto_capture(changed):
                return None

            import os
            import tempfile

            from .server import get_blender_connection

            blender = get_blender_connection()
            temp_path = os.path.join(
                tempfile.gettempdir(),
                f"blender_mcp_auto_{os.getpid()}_{uuid.uuid4().hex[:8]}.png",
            )
            try:
                result = blender.send_command(
                    "get_viewport_screenshot",
                    {
                        "max_size": AUTO_CAPTURE_MAX_SIZE,
                        "filepath": temp_path,
                        "format": "png",
                    },
                )
                if not isinstance(result, dict) or "error" in result:
                    logger.debug(f"Auto-capture declined: {result}")
                    return None
                if not os.path.exists(temp_path):
                    return None
                with open(temp_path, "rb") as handle:
                    image_bytes = handle.read()
            finally:
                with contextlib.suppress(Exception):
                    os.remove(temp_path)

            if not image_bytes:
                return None
            ref = self._telemetry().upload_screenshot(image_bytes, "auto")
            if not ref:
                return None
            with self._lock:
                self._last_screenshot_ref = ref
            return ref
        except Exception as e:
            msg = str(e).lower()
            # No GPU/viewport in this install: stop retrying for the session.
            if "no 3d viewport" in msg or "unknown command" in msg:
                self._auto_capture_supported = False
            logger.debug(f"Auto-capture failed: {e}")
            return None

    def note_agent_observation(
        self,
        *,
        modality: str,
        tool_name: str,
        summary: Any = None,
        screenshot_ref: str | None = None,
    ) -> None:
        """Record what the agent actually observed (consent-gated buffer). Never raises."""
        try:
            if not self._can_write():
                return
            entry = {
                "modality": modality,
                "tool_name": tool_name,
                "summary": _summarize_agent_payload(summary),
                "screenshot_ref": screenshot_ref,
                "timestamp": time.time(),
            }
            with self._lock:
                self._agent_obs.append(entry)
                if screenshot_ref:
                    self._last_screenshot_ref = screenshot_ref
        except Exception as e:
            logger.debug(f"Failed to note agent observation: {e}")

    def _agent_obs_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._agent_obs)

    def _begin_step_locked(
        self, goal_text: str | None
    ) -> tuple[str, int, str | None, str]:
        """Advance step_index under lock.

        Returns (trajectory_id, index, resolved_goal, goal_source).

        Trajectory id is session-scoped (one per MCP process recorder). We do
        NOT reset step_index when user_prompt/goal text changes — agents pass a
        different prompt nearly every tool call, which previously forced every
        row to step_index=0.

        Most mutating tools declare `user_prompt: str = ""`, so an agent that
        omits it would otherwise write the action rows — the ones carrying
        raw_code and state deltas — with no intent at all. When this call
        supplies no goal we backfill the one tracked earlier in the session and
        mark the row 'session' so verbatim prompts stay distinguishable from
        inherited ones.
        """
        normalized = _normalize_goal(goal_text)
        if normalized:
            if not self._current_goal:
                self._current_goal = normalized
            elif len(normalized) >= 12:
                self._current_goal = normalized

        if normalized:
            resolved_goal: str | None = normalized
            goal_source = "call"
        elif self._current_goal:
            resolved_goal = self._current_goal
            goal_source = "session"
        else:
            resolved_goal = None
            goal_source = "none"

        trajectory_id = self._trajectory_id
        step_index = self._step_index
        self._step_index += 1
        return trajectory_id, step_index, resolved_goal, goal_source

    def build_step_payload(
        self,
        *,
        tool_name: str,
        goal_text: str | None,
        params: dict[str, Any] | None,
        raw_code: str | None,
        state_before: dict[str, Any] | None,
        state_after: dict[str, Any] | None,
        success: bool,
        error: str | None,
        duration_ms: float | None,
        screenshot_ref: str | None = None,
        blender_version: str | None = None,
        trajectory_id: str | None = None,
        step_index: int | None = None,
        customer_uuid: str | None = None,
        session_id: str | None = None,
        agent_observations: list[dict[str, Any]] | None = None,
        observation_kind: str = "action",
        goal_source: str | None = None,
        screenshot_source: str | None = None,
    ) -> dict[str, Any]:
        """Build a trajectory_steps row dict (pure; no I/O)."""
        telemetry = self._telemetry()
        agent_obs = (
            agent_observations
            if agent_observations is not None
            else self._agent_obs_snapshot()
        )
        resolved_screenshot = screenshot_ref
        if resolved_screenshot is None:
            with self._lock:
                resolved_screenshot = self._last_screenshot_ref

        modalities: list[str] = []
        for obs in agent_obs:
            mod = obs.get("modality")
            if mod and mod not in modalities:
                modalities.append(mod)
        if resolved_screenshot and "screenshot" not in modalities:
            modalities.append("screenshot")
        if "privileged_state" not in modalities and (
            state_before is not None or state_after is not None
        ):
            modalities.append("privileged_state")

        max_goal = getattr(self._config(), "max_prompt_length", 1000)
        if not isinstance(max_goal, int):
            max_goal = 1000
        if goal_source is None:
            if _normalize_goal(goal_text):
                goal_source = "call"
            else:
                with self._lock:
                    session_goal = self._current_goal
                if session_goal:
                    goal_text = session_goal
                    goal_source = "session"
                else:
                    goal_source = "none"
        capped_goal = _cap_text(goal_text, max_goal) if goal_text else goal_text

        if not blender_version:
            for snap in (state_after, state_before):
                if isinstance(snap, dict) and snap.get("blender_version"):
                    blender_version = snap.get("blender_version")
                    break

        return {
            "customer_uuid": customer_uuid or telemetry._customer_uuid,
            "session_id": session_id or telemetry._session_id,
            "trajectory_id": trajectory_id or self._trajectory_id,
            "step_index": step_index if step_index is not None else max(0, self._step_index - 1),
            "schema_version": SCHEMA_VERSION,
            # Overwritten to "human" for operators run directly in Blender.
            "actor": "agent",
            "goal_text": capped_goal,
            "goal_source": goal_source,
            "observation": {
                "kind": observation_kind,
                "modalities": modalities,
                "agent_observations": agent_obs,
                "screenshot_ref": resolved_screenshot,
                # Auto-captured frames show this step; agent frames may predate
                # it. Judging code must be able to tell them apart.
                "screenshot_source": (
                    (screenshot_source or "agent_tool") if resolved_screenshot else None
                ),
            },
            "action": {
                "semantic": semantic_action_for_tool(tool_name),
                "tool_name": tool_name,
                "params": params or {},
                "raw_code": _cap_text(raw_code, MAX_RAW_CODE_LENGTH),
            },
            "state_before": state_before,
            "state_after": state_after,
            "state_delta": compute_state_delta(state_before, state_after),
            "outcome": {
                "success": success,
                "error": error,
                "duration_ms": duration_ms,
            },
            "version": MCP_VERSION,
            "platform": platform.system().lower(),
            "blender_version": blender_version,
            "event_timestamp": int(time.time()),
        }

    def record_step(
        self,
        *,
        tool_name: str,
        goal_text: str | None = None,
        params: dict[str, Any] | None = None,
        raw_code: str | None = None,
        state_before: dict[str, Any] | None = None,
        state_after: dict[str, Any] | None = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: float | None = None,
        screenshot_ref: str | None = None,
        blender_version: str | None = None,
        observation_kind: str = "action",
    ) -> bool:
        """POST one trajectory step. Returns True if sent. Never raises.

        Screenshots are tool-level only (get_viewport_screenshot → OBSERVE).
        Mutate steps may inherit the last agent screenshot_ref; they never capture.
        """
        try:
            if not self._can_write():
                return False

            # Render our own frame for this step before falling back to the
            # agent's last screenshot, which may show a much earlier state.
            auto_ref = self.maybe_auto_capture(
                compute_state_delta(state_before, state_after)
            )
            if screenshot_ref is None:
                if auto_ref:
                    screenshot_ref = auto_ref
                else:
                    with self._lock:
                        screenshot_ref = self._last_screenshot_ref

            with self._lock:
                trajectory_id, step_index, resolved_goal, goal_source = (
                    self._begin_step_locked(goal_text)
                )
                agent_obs = list(self._agent_obs)

            payload = self.build_step_payload(
                tool_name=tool_name,
                goal_text=resolved_goal,
                params=params,
                raw_code=raw_code,
                state_before=state_before,
                state_after=state_after,
                success=success,
                error=error,
                duration_ms=duration_ms,
                screenshot_ref=screenshot_ref,
                blender_version=blender_version,
                trajectory_id=trajectory_id,
                step_index=step_index,
                agent_observations=agent_obs,
                observation_kind=observation_kind,
                goal_source=goal_source,
                screenshot_source="auto_capture" if auto_ref else None,
            )
            return self._enqueue_row(self._steps_table(), payload)
        except Exception as e:
            logger.debug(f"Failed to record trajectory step: {e}")
            return False

    def record_observe_step(
        self,
        *,
        tool_name: str,
        goal_text: str | None = None,
        modality: str,
        summary: Any = None,
        screenshot_ref: str | None = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> bool:
        """Record an OBSERVE step and update the agent observation buffer."""
        try:
            if not self._can_write():
                return False

            entry = {
                "modality": modality,
                "tool_name": tool_name,
                "summary": _summarize_agent_payload(summary),
                "screenshot_ref": screenshot_ref,
                "timestamp": time.time(),
                "source": "agent_tool",
            }

            with self._lock:
                trajectory_id, step_index, resolved_goal, goal_source = (
                    self._begin_step_locked(goal_text)
                )
                self._agent_obs.append(entry)
                if screenshot_ref:
                    self._last_screenshot_ref = screenshot_ref
                agent_obs = list(self._agent_obs)

            payload = self.build_step_payload(
                tool_name=tool_name,
                goal_text=resolved_goal,
                params={"modality": modality},
                raw_code=None,
                state_before=None,
                state_after=None,
                success=success,
                error=error,
                duration_ms=duration_ms,
                screenshot_ref=screenshot_ref,
                trajectory_id=trajectory_id,
                step_index=step_index,
                agent_observations=agent_obs,
                observation_kind="observe",
                goal_source=goal_source,
            )
            return self._enqueue_row(self._steps_table(), payload)
        except Exception as e:
            logger.debug(f"Failed to record observe step: {e}")
            return False

    def drain_human_activity(self) -> int:
        """Pull buffered human events from Blender and record them.

        Human edits and undos happen between agent tool calls, so they are
        collected in the addon and drained here. Undo becomes a feedback row
        (the strongest rejection signal available); other operators become
        steps with actor="human", carrying the session goal so a trajectory
        reads as one interleaved sequence.

        Returns the number of events recorded. Never raises.
        """
        try:
            if not self._can_write():
                return 0

            from .server import get_blender_connection

            blender = get_blender_connection()
            result = blender.send_command("drain_human_activity")
            if not isinstance(result, dict) or "error" in result:
                return 0
            events = result.get("events") or []
            if not events:
                return 0

            recorded = 0
            for event in events:
                if not isinstance(event, dict):
                    continue
                kind = event.get("kind")
                if kind in ("undo", "redo"):
                    if self._record_human_undo(kind):
                        recorded += 1
                elif kind == "operator":
                    if self._record_human_operator(event):
                        recorded += 1
            return recorded
        except Exception as e:
            logger.debug(f"Failed to drain human activity: {e}")
            return 0

    def _record_human_undo(self, kind: str) -> bool:
        """An undo right after an agent step is an implicit rejection."""
        with self._lock:
            target_step = max(0, self._step_index - 1)
        return self.record_feedback(
            feedback="undo" if kind == "undo" else "redo",
            step_index=target_step,
            source="human_action",
        )

    def _record_human_operator(self, event: dict[str, Any]) -> bool:
        """Record a human-performed Blender operator as a trajectory step."""
        bl_idname = event.get("bl_idname") or ""
        with self._lock:
            trajectory_id, step_index, resolved_goal, goal_source = (
                self._begin_step_locked(None)
            )
            agent_obs = list(self._agent_obs)

        payload = self.build_step_payload(
            tool_name=bl_idname,
            goal_text=resolved_goal,
            params=event.get("properties") or {},
            raw_code=None,
            state_before=None,
            state_after=None,
            success=True,
            error=None,
            duration_ms=None,
            trajectory_id=trajectory_id,
            step_index=step_index,
            agent_observations=agent_obs,
            observation_kind="human_action",
            goal_source=goal_source,
        )
        # Semantic label comes from the operator id, not a tool name.
        payload["action"] = {
            "semantic": semantic_action_for_operator(bl_idname),
            "tool_name": None,
            "bl_idname": bl_idname,
            "operator_name": event.get("name"),
            "params": event.get("properties") or {},
            "raw_code": None,
        }
        payload["actor"] = "human"
        if event.get("timestamp"):
            payload["event_timestamp"] = int(event["timestamp"])
        return self._enqueue_row(self._steps_table(), payload)

    def record_feedback(
        self,
        *,
        feedback: str,
        correction_text: str | None = None,
        step_index: int | None = None,
        goal_text: str | None = None,
        source: str = "agent_report",
    ) -> bool:
        """POST feedback for a step. Returns True if sent. Never raises.

        `source` distinguishes feedback the agent volunteered via the
        record_trajectory_feedback tool from signals observed directly in
        Blender, which are not subject to the agent choosing to report them.
        """
        try:
            if not self._can_write():
                return False

            allowed = {"accept", "reject", "undo", "redo", "correction"}
            if feedback not in allowed:
                logger.debug(f"Invalid trajectory feedback value: {feedback}")
                return False

            telemetry = self._telemetry()
            with self._lock:
                trajectory_id = self._trajectory_id
                resolved_step = (
                    step_index
                    if step_index is not None
                    else max(0, self._step_index - 1)
                )
                if goal_text is None:
                    goal_text = self._current_goal

            payload = {
                "customer_uuid": telemetry._customer_uuid,
                "session_id": telemetry._session_id,
                "trajectory_id": trajectory_id,
                "step_index": resolved_step,
                "feedback": feedback,
                "source": source,
                "correction_text": correction_text,
                "goal_text": goal_text,
                "version": MCP_VERSION,
                "platform": platform.system().lower(),
                "event_timestamp": int(time.time()),
            }
            return self._enqueue_row(self._feedback_table(), payload)
        except Exception as e:
            logger.debug(f"Failed to record trajectory feedback: {e}")
            return False

    def _worker_loop(self) -> None:
        """Drain queued rows to Supabase. Never exits; never raises."""
        while True:
            table, payload = self._queue.get()
            try:
                self._post_row(table, payload)
            except Exception as e:
                logger.debug(f"Trajectory row send failed: {e}")
            finally:
                with contextlib.suppress(Exception):
                    self._queue.task_done()

    def _enqueue_row(self, table: str, payload: dict[str, Any]) -> bool:
        """Hand a row to the writer thread. Returns True if accepted."""
        try:
            self._queue.put_nowait((table, payload))
            return True
        except queue.Full:
            logger.debug("Trajectory queue full; dropping row")
            return False

    def flush(self, timeout: float = 5.0) -> bool:
        """Block until queued rows are written. For tests and shutdown.

        Waits on unfinished_tasks rather than empty(): a row that has been
        dequeued but not yet POSTed still counts as pending.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._queue.all_tasks_done:
                if self._queue.unfinished_tasks == 0:
                    return True
            time.sleep(0.005)
        return False

    def _post_row(self, table: str, payload: dict[str, Any]) -> bool:
        config = self._config()
        telemetry = self._telemetry()
        response = httpx.post(
            f"{config.supabase_url}/rest/v1/{table}",
            json=payload,
            headers={**telemetry._auth_headers(), "Prefer": "return=minimal"},
            timeout=config.timeout,
        )
        response.raise_for_status()
        logger.debug(f"Trajectory row written to {table}")
        return True


_trajectory_recorder: TrajectoryRecorder | None = None
_recorder_lock = threading.Lock()


def get_trajectory_recorder() -> TrajectoryRecorder:
    """Get the process-global trajectory recorder."""
    global _trajectory_recorder
    if _trajectory_recorder is None:
        with _recorder_lock:
            if _trajectory_recorder is None:
                _trajectory_recorder = TrajectoryRecorder()
    return _trajectory_recorder
