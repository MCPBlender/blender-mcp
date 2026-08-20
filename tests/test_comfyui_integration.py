"""Regression coverage for ComfyUI Desktop workflow integration."""
import asyncio
import importlib.util
import json
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
        import_scene=types.SimpleNamespace(
            gltf=lambda **_kwargs: None,
            obj=lambda **_kwargs: None,
            fbx=lambda **_kwargs: None,
        ),
        wm=types.SimpleNamespace(
            obj_import=lambda **_kwargs: None,
            stl_import=lambda **_kwargs: None,
            ply_import=lambda **_kwargs: None,
        ),
        import_mesh=types.SimpleNamespace(
            stl=lambda **_kwargs: None,
            ply=lambda **_kwargs: None,
        ),
    )

    props = types.ModuleType("bpy.props")
    for prop_name in ("BoolProperty", "EnumProperty", "FloatProperty", "IntProperty", "StringProperty"):
        setattr(props, prop_name, lambda **_kwargs: None)
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
        blendermcp_use_comfyui=enabled,
        blendermcp_comfyui_api_url="http://127.0.0.1:8188",
    )
    bpy = _install_bpy_stubs(monkeypatch, scene)
    spec = importlib.util.spec_from_file_location("blender_mcp_addon_comfyui_test", ROOT_ADDON)
    addon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(addon)
    return addon, bpy


class _FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200, text=""):
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=8192):
        yield self.content


def _api_workflow():
    return {
        "3": {"class_type": "KSampler", "inputs": {"seed": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "chair"}},
        "10": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "20": {"class_type": "Preview3D", "inputs": {"model_file": ["19", 0]}},
    }


def test_comfyui_status_skips_api_when_disabled(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch, enabled=False)
    monkeypatch.setattr(
        addon.requests,
        "get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("unexpected request")),
        raising=False,
    )

    result = addon.BlenderMCPServer().get_comfyui_status()

    assert result["enabled"] is False
    assert "disabled" in result["message"]


def test_comfyui_status_uses_system_stats(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch)
    monkeypatch.setattr(
        addon.requests,
        "get",
        lambda url, **_kwargs: _FakeResponse({"system": {"comfyui_version": "1.2.3"}}),
        raising=False,
    )

    result = addon.BlenderMCPServer().get_comfyui_status()

    assert result["enabled"] is True
    assert result["system_stats"]["system"]["comfyui_version"] == "1.2.3"


def test_comfyui_api_url_can_come_from_environment(monkeypatch):
    addon, bpy = _load_addon(monkeypatch)
    bpy.context.scene.blendermcp_comfyui_api_url = ""
    monkeypatch.setenv("BLENDERMCP_COMFYUI_API_URL", "http://192.0.2.20:8188")

    assert addon.BlenderMCPServer()._get_comfyui_api_url() == "http://192.0.2.20:8188"


def test_comfyui_rejects_ui_format_workflow(monkeypatch, tmp_path):
    addon, _bpy = _load_addon(monkeypatch)
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(json.dumps({"nodes": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="API Format"):
        addon.BlenderMCPServer._load_comfyui_api_workflow(str(workflow_path))


def test_run_comfyui_workflow_uploads_image_and_applies_overrides(monkeypatch, tmp_path):
    addon, _bpy = _load_addon(monkeypatch)
    workflow_path = tmp_path / "workflow_api.json"
    workflow_path.write_text(json.dumps(_api_workflow()), encoding="utf-8")
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"png")
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/upload/image"):
            assert kwargs["files"]["image"][0] == "reference.png"
            return _FakeResponse({"name": "reference (1).png", "subfolder": "", "type": "input"})
        if url.endswith("/prompt"):
            prompt = kwargs["json"]["prompt"]
            assert prompt["3"]["inputs"]["seed"] == 42
            assert prompt["6"]["inputs"]["text"] == "wooden chair"
            assert prompt["10"]["inputs"]["image"] == "reference (1).png"
            assert kwargs["json"]["client_id"]
            return _FakeResponse({"prompt_id": "prompt-123", "number": 7, "node_errors": {}})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(addon.requests, "post", fake_post, raising=False)

    result = addon.BlenderMCPServer().run_comfyui_workflow(
        str(workflow_path),
        input_overrides={"3": {"seed": 42}, "6": {"text": "wooden chair"}},
        input_image_path=str(image_path),
        input_image_node_id="10",
    )

    assert result["prompt_id"] == "prompt-123"
    assert result["status"] == "queued"
    assert result["uploaded_image"] == "reference (1).png"
    assert len(calls) == 2


def test_run_comfyui_workflow_returns_validation_details(monkeypatch, tmp_path):
    addon, _bpy = _load_addon(monkeypatch)
    workflow_path = tmp_path / "workflow_api.json"
    workflow_path.write_text(json.dumps(_api_workflow()), encoding="utf-8")
    monkeypatch.setattr(
        addon.requests,
        "post",
        lambda *_a, **_k: _FakeResponse(
            {"error": {"message": "invalid prompt"}},
            status_code=400,
            text='{"error":{"message":"invalid prompt"}}',
        ),
        raising=False,
    )

    result = addon.BlenderMCPServer().run_comfyui_workflow(str(workflow_path))

    assert "status 400" in result["error"]
    assert "invalid prompt" in result["error"]


def test_poll_comfyui_workflow_returns_3d_outputs(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch)
    prompt_id = "prompt-123"
    history = {
        prompt_id: {
            "status": {"status_str": "success", "completed": True, "messages": []},
            "outputs": {
                "20": {"result": ["previews/preview3d_model.glb", None]},
                "21": {
                    "3d": [
                        {
                            "filename": "mesh.obj",
                            "subfolder": "models",
                            "type": "output",
                        }
                    ]
                },
            },
        }
    }
    monkeypatch.setattr(
        addon.requests,
        "get",
        lambda url, **_kwargs: _FakeResponse(history),
        raising=False,
    )

    result = addon.BlenderMCPServer().poll_comfyui_workflow(prompt_id)

    assert result["status"] == "done"
    assert [item["filename"] for item in result["outputs"]] == ["preview3d_model.glb", "mesh.obj"]
    assert result["outputs"][0]["subfolder"] == "previews"
    assert result["outputs"][1]["subfolder"] == "models"


def test_poll_comfyui_workflow_checks_pending_queue(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch)
    prompt_id = "prompt-queued"

    def fake_get(url, **_kwargs):
        if "/history/" in url:
            return _FakeResponse({})
        if url.endswith("/queue"):
            return _FakeResponse({"queue_running": [], "queue_pending": [[4, prompt_id, {}, {}, []]]})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(addon.requests, "get", fake_get, raising=False)

    result = addon.BlenderMCPServer().poll_comfyui_workflow(prompt_id)

    assert result == {"prompt_id": prompt_id, "status": "queued", "outputs": []}


def test_comfyui_output_reference_rejects_traversal(monkeypatch):
    addon, _bpy = _load_addon(monkeypatch)
    validate = addon.BlenderMCPServer._validate_comfyui_output_reference

    assert validate("model.glb", "models/chairs", "output") == (
        "model.glb",
        "models/chairs",
        "output",
        ".glb",
    )
    for filename, subfolder in (
        ("../model.glb", ""),
        ("%2e%2e%2fmodel.glb", ""),
        ("model.glb", "../secret"),
        ("model.glb", "models\\secret"),
        ("model.glb", "/absolute/path"),
    ):
        with pytest.raises(ValueError):
            validate(filename, subfolder, "output")


def test_import_comfyui_glb_uses_view_endpoint(monkeypatch):
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

    result = server.import_comfyui_output("Chair", "chair.glb", "models", "output")

    assert result["success"] is True
    assert result["name"] == "Chair"
    assert result["world_bounding_box"] == [0, 0, 0, 1, 1, 1]
    assert requested["url"].endswith("/view")
    assert requested["params"] == {
        "filename": "chair.glb",
        "subfolder": "models",
        "type": "output",
    }


def test_bundled_addon_stays_in_sync():
    bundled = REPO_ROOT / "src" / "blender_mcp" / "bundled" / "addon.py"
    assert ROOT_ADDON.read_bytes() == bundled.read_bytes()


def test_comfyui_mcp_tools_are_registered():
    from blender_mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert {
        "get_comfyui_status",
        "run_comfyui_workflow",
        "poll_comfyui_workflow",
        "import_comfyui_output",
    } <= {tool.name for tool in tools}


def test_comfyui_mutations_have_trajectory_semantics():
    from blender_mcp.trajectory import semantic_action_for_tool

    assert semantic_action_for_tool("run_comfyui_workflow") == "GENERATE_3D"
    assert semantic_action_for_tool("import_comfyui_output") == "IMPORT_ASSET"
