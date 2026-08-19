"""Tests for auto-start binding the scene's port and syncing the panel flag.

addon.py cannot be imported without bpy, so _blendermcp_on_load_post is lifted
out by AST and executed against stubs.

The bug these cover: auto-start ran at the end of register(), which at Blender
startup happens before any .blend has been read. bpy.context.scene was None
there, so the handler fell back to a hardcoded port 9876 - silently ignoring a
port configured in the file - and the write to blendermcp_server_running was
swallowed by `except AttributeError`. The panel keys its button off that flag,
so it offered "Connect to MCP server" for an already-running server.
"""

from __future__ import annotations

import ast
import types

from conftest import ROOT_ADDON


class _FakeServer:
    """Minimal stand-in for BlenderMCPServer; start() never touches sockets."""

    def __init__(self, port):
        self.port = port
        self.running = False
        self.start_calls = 0

    def start(self):
        self.start_calls += 1
        self.running = True


def _load_handler(scene, server=None, user_stopped=False):
    """Compile _blendermcp_on_load_post from addon.py against stub modules."""
    source = ROOT_ADDON.read_text(encoding="utf-8")
    tree = ast.parse(source)

    body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_blendermcp_on_load_post"
    ]
    assert body, "_blendermcp_on_load_post not found in addon.py"

    bpy = types.ModuleType("bpy")
    bpy.context = types.SimpleNamespace(scene=scene)
    bpy.types = types.SimpleNamespace()
    if server is not None:
        bpy.types.blendermcp_server = server

    namespace = {
        "bpy": bpy,
        "persistent": lambda fn: fn,
        "BlenderMCPServer": _FakeServer,
        "_user_stopped_server": user_stopped,
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), "<addon>", "exec"), namespace)
    return namespace["_blendermcp_on_load_post"], bpy


def _scene(port=9876, auto_start=True, running=False):
    return types.SimpleNamespace(
        blendermcp_port=port,
        blendermcp_auto_start_server=auto_start,
        blendermcp_server_running=running,
    )


def test_starts_on_the_scene_port_not_a_hardcoded_default():
    """A port configured in the .blend is honoured, not replaced by 9876."""
    scene = _scene(port=9999)
    handler, bpy = _load_handler(scene)

    handler()

    assert bpy.types.blendermcp_server.port == 9999
    assert bpy.types.blendermcp_server.running is True


def test_panel_flag_matches_a_running_server():
    """The flag the panel reads is written once a scene exists."""
    scene = _scene()
    handler, _ = _load_handler(scene)

    handler()

    assert scene.blendermcp_server_running is True


def test_panel_flag_resyncs_for_a_server_started_before_the_file_loaded():
    """Opening a file resets the per-scene flag; the handler restores it.

    This is the reported symptom: the server is up, but the freshly loaded
    scene carries the property default (False) and the panel lies.
    """
    server = _FakeServer(port=9876)
    server.running = True
    scene = _scene(running=False)
    handler, _ = _load_handler(scene, server=server)

    handler()

    assert scene.blendermcp_server_running is True
    assert server.start_calls == 0, "an already-running server must not be restarted"


def test_running_server_keeps_its_port_when_the_file_disagrees():
    """Retargeting a live server would drop the connected client."""
    server = _FakeServer(port=9876)
    server.running = True
    scene = _scene(port=9999)
    handler, _ = _load_handler(scene, server=server)

    handler()

    assert server.port == 9876
    assert scene.blendermcp_server_running is True


def test_auto_start_disabled_leaves_the_server_alone():
    scene = _scene(auto_start=False)
    handler, bpy = _load_handler(scene)

    handler()

    assert not hasattr(bpy.types, "blendermcp_server")
    assert scene.blendermcp_server_running is False


def test_no_scene_is_a_no_op():
    """register() calls the handler directly; at startup there is no scene."""
    handler, bpy = _load_handler(None)

    handler()

    assert not hasattr(bpy.types, "blendermcp_server")


def test_manual_disconnect_survives_opening_a_file():
    """Opening a .blend must not resurrect a server the user shut off.

    Disconnect deletes bpy.types.blendermcp_server, so without this guard the
    handler would see no server and happily start a fresh one.
    """
    scene = _scene()
    handler, bpy = _load_handler(scene, user_stopped=True)

    handler()

    assert not hasattr(bpy.types, "blendermcp_server")
    assert scene.blendermcp_server_running is False
