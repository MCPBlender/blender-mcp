"""Regression coverage for the local Modly integration."""
import asyncio
import importlib.util
import sys
import types

import pytest
from conftest import REPO_ROOT, ROOT_ADDON


def _install_bpy_stubs(monkeypatch, scene):
    bpy = types.ModuleType("bpy")
    bpy.context = types.SimpleNamespace(
        scene=scene,
        selected_objects=[],
        preferences=types.SimpleNamespace(addons={}),
    )
    bpy.types = types.SimpleNamespace(
        AddonPreferences=object,
        Operator=object,
        Panel=object,
        Scene=type("Scene", (), {}),
    )
    bpy.ops = types.SimpleNamespace(
        import_scene=types.SimpleNamespace(gltf=lambda **_kwargs: None),
    )

    props = types.ModuleType("bpy.props")
    for name in ("BoolProperty", "EnumProperty", "FloatProperty", "IntProperty", "StringProperty"):
        setattr(props, name, lambda **_kwargs: None)
    bpy.props = props

    handlers = types.ModuleType("bpy.app.handlers")
    handlers.persistent = lambda fn: fn
    handlers.undo_post = []
    handlers.redo_post = []
    handlers.depsgraph_update_post = []

    app = types.ModuleType("bpy.app")
    app.version = (4, 2, 0)
    app.version_string = "4.2.0"
    app.background = False
    app.handlers = handlers
    app.timers = types.SimpleNamespace(
        is_registered=lambda *_a, **_k: False,
        register=lambda *_a, **_k: None,
        unregister=lambda *_a, **_k: None,
    )
    bpy.app = app

    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "bpy.props", props)
    monkeypatch.setitem(sys.modules, "bpy.app", app)
    monkeypatch.setitem(sys.modules, "bpy.app.handlers", handlers)
    monkeypatch.setitem(sys.modules, "mathutils", types.ModuleType("mathutils"))

    requests = types.ModuleType("requests")
    requests.utils = types.SimpleNamespace(default_headers=dict)
    monkeypatch.setitem(sys.modules, "requests", requests)
    return bpy


def _load_addon(monkeypatch, *, enabled=True):
    scene = types.SimpleNamespace(
        blendermcp_use_polyhaven=False,
        blendermcp_use_hyper3d=False,
        blendermcp_use_hunyuan3d=False,
        blendermcp_use_sketchfab=False,
        blendermcp_use_modly=enabled,
        blendermcp_modly_api_url="http://127.0.0.1:8765",
    )
    bpy = _install_bpy_stubs(monkeypatch, scene)
    spec = importlib.util.spec_from_file_location("blender_mcp_addon_modly_test", ROOT_ADDON)
    addon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(addon)
    return addon, bpy


class _FakeResponse:
    def __init__(self, payload=None, content=b""):
        self._payload = payload
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=8192):
        yield self.content


def test_modly_workspace_path_validation_rejects_traversal(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch)
    validate = addon.BlenderMCPServer._validate_modly_workspace_path

    assert validate("/workspace/Default/model.glb") == "Default/model.glb"
    for value in ("../secret.glb", "Default/../secret.glb", "%2e%2e/secret.glb", "/secret.glb", "C:/secret.glb", "Default\\secret.glb"):
        with pytest.raises(ValueError):
            validate(value)


def test_modly_status_does_not_call_api_when_disabled(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch, enabled=False)
    monkeypatch.setattr(
        addon.requests,
        "get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("unexpected request")),
        raising=False,
    )

    result = addon.BlenderMCPServer().get_modly_status()

    assert result["enabled"] is False
    assert "disabled" in result["message"]


def test_modly_status_checks_health_and_active_model(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch)

    def fake_get(url, **_kwargs):
        if url.endswith("/health"):
            return _FakeResponse({"status": "ok"})
        if url.endswith("/model/status"):
            return _FakeResponse({"id": "trellis/generate", "downloaded": True})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(addon.requests, "get", fake_get, raising=False)

    result = addon.BlenderMCPServer().get_modly_status()

    assert result["enabled"] is True
    assert result["active_model"]["id"] == "trellis/generate"


def test_modly_api_url_can_come_from_environment(monkeypatch):
    addon, bpy = _load_addon(monkeypatch)
    bpy.context.scene.blendermcp_modly_api_url = ""
    monkeypatch.setenv("BLENDERMCP_MODLY_API_URL", "http://192.0.2.10:8765")

    assert addon.BlenderMCPServer()._get_modly_api_url() == "http://192.0.2.10:8765"


def test_create_modly_job_uses_canonical_workflow_endpoint(monkeypatch, tmp_path):
    addon, _bpy = _load_addon(monkeypatch)
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"png")
    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return _FakeResponse({"id": "hunyuan3d-mini/generate", "downloaded": True})

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        assert kwargs["data"]["model_id"] == "hunyuan3d-mini/generate"
        assert kwargs["data"]["params"] == '{"seed":42}'
        assert kwargs["files"]["image"][0] == "reference.png"
        return _FakeResponse({"run_id": "run-123", "status": "pending"})

    monkeypatch.setattr(addon.requests, "get", fake_get, raising=False)
    monkeypatch.setattr(addon.requests, "post", fake_post, raising=False)

    result = addon.BlenderMCPServer().create_modly_job(str(image_path), params={"seed": 42})

    assert result == {
        "run_id": "run-123",
        "status": "pending",
        "model_id": "hunyuan3d-mini/generate",
    }
    assert calls[0][1].endswith("/model/status")
    assert calls[1][1].endswith("/workflow-runs/from-image")


def test_import_modly_asset_exports_glb_and_imports_into_blender(monkeypatch):
    addon, bpy = _load_addon(monkeypatch)
    requested = {}

    mesh = types.SimpleNamespace(
        type="MESH",
        name="Imported",
        location=types.SimpleNamespace(x=0, y=0, z=0),
        rotation_euler=types.SimpleNamespace(x=0, y=0, z=0),
        scale=types.SimpleNamespace(x=1, y=1, z=1),
    )

    def gltf_import(**kwargs):
        requested["filepath"] = kwargs["filepath"]
        bpy.context.selected_objects = [mesh]

    def fake_get(url, **kwargs):
        requested["url"] = url
        requested["params"] = kwargs["params"]
        return _FakeResponse(content=b"glb-bytes")

    bpy.ops.import_scene.gltf = gltf_import
    monkeypatch.setattr(addon.requests, "get", fake_get, raising=False)
    server = addon.BlenderMCPServer()
    monkeypatch.setattr(server, "_get_aabb", lambda _obj: [0, 0, 0, 1, 1, 1])

    result = server.import_generated_asset_modly("Chair", "Default/chair.obj")

    assert result["success"] is True
    assert result["name"] == "Chair"
    assert result["world_bounding_box"] == [0, 0, 0, 1, 1, 1]
    assert requested["url"].endswith("/export/glb")
    assert requested["params"] == {"path": "Default/chair.obj"}


def test_bundled_addon_stays_in_sync():
    bundled = REPO_ROOT / "src" / "blender_mcp" / "bundled" / "addon.py"
    assert ROOT_ADDON.read_bytes() == bundled.read_bytes()


def test_modly_mcp_tools_are_registered():
    from blender_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert {
        "get_modly_status",
        "list_modly_models",
        "generate_modly_model",
        "poll_modly_job_status",
        "import_generated_asset_modly",
    } <= {tool.name for tool in tools}


def test_modly_mutations_have_trajectory_semantics():
    from blender_mcp.trajectory import semantic_action_for_tool

    assert semantic_action_for_tool("generate_modly_model") == "GENERATE_3D"
    assert semantic_action_for_tool("import_generated_asset_modly") == "IMPORT_ASSET"
