"""SAM3 service boundary and real shared RGB-D composition, independent of harvest success."""

import base64
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from so101_rgbd_fixture import sphere_views

from cap_harness.api import CapApi
from cap_harness.contracts import PointCloud, Segmentation, SegmentationSet
from cap_harness.errors import ErrorCode
from cap_harness.geometry import estimate_oriented_bounding_box
from cap_harness.registry import ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101 import perception


def test_actual_vision_probe_program_runs_inside_restricted_aspire_executor():
    """Use the shipped probe, including pixel statistics, under the real import guard."""
    program = (
        Path(__file__).resolve().parents[1] / "examples/robosuite/so101_perception.py"
    ).read_text()
    registry = ToolRegistry()
    calls = []

    def segment_text(camera, query):
        calls.append((camera, query))
        return SegmentationSet(
            ok=True,
            segmentations=[
                Segmentation(
                    mask=np.array([[True, False], [True, True]]),
                    label=query,
                    score=0.9,
                    camera_name=camera,
                    frame=camera,
                )
            ],
        )

    def project(mask, camera_name, target_frame, *, erosion_pixels=0, depth_range_m=None):
        assert erosion_pixels == 1 and depth_range_m == [0.1, 2.0]
        return PointCloud(
            points=np.array([[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0], [0, 0, 0.01]]),
            frame=target_frame,
        )

    for name, function in [
        ("segment_text", segment_text),
        ("mask_to_point_cloud", project),
        ("estimate_geometry", estimate_oriented_bounding_box),
    ]:
        registry.register(function, name=name, public=True, layer="shared", capability="perception")
    outcome = ProgramExecutor(registry).execute_program(program)
    assert outcome.ok, outcome.error
    assert len(calls) == 6 and len(outcome.result["views"]) == 6
    assert all(
        row["instances"][0]["pixel_count"] == 3 and row["instances"][0]["frame"] == "so101_base"
        for row in outcome.result["views"]
    )


@contextmanager
def service(camera, *, ready=True, malformed=False):
    calls = []
    mask = (camera.rgb[:, :, 0] > 100).astype(np.uint8)
    ys, xs = np.nonzero(mask)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.reply(
                {
                    "provider": "sam3",
                    "ready": ready,
                    "checkpoint_sha256": "1" * 64,
                    "sam3_commit": "2" * 40,
                    "service_sha256": "3" * 64,
                    "confidence_threshold": 0.5,
                }
            )

        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.reply(
                {
                    "results": [
                        {
                            "shape": list(mask.shape),
                            "mask_base64": "invalid"
                            if malformed
                            else base64.b64encode(mask.tobytes()).decode(),
                            "score": 0.88,
                            "label": calls[-1]["text_prompt"],
                            "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                        }
                    ]
                }
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_backend_selection_is_explicit_and_has_no_fallback():
    assert (
        perception.configuration("so101_control", {"CAP_HARNESS_SO101_SEGMENTATION": "sam3"})[
            "backend"
        ]
        == "sam3"
    )
    assert perception.configuration("so101_control", {})["backend"] == "color-rgbd"
    assert (
        perception.configuration("so101_control", {"CAP_HARNESS_SO101_SEGMENTATION": "color-rgbd"})[
            "fallback"
        ]
        is None
    )
    with pytest.raises(ValueError):
        perception.configuration("so101_control", {"CAP_HARNESS_SO101_SEGMENTATION": "invented"})
    with pytest.raises(ValueError):
        perception.provider({"backend": "invented"})


def test_sam3_uses_only_rgb_and_shared_depth_handles_missing_observations():
    # Synthetic HTTP model fixture: this tests protocol, not real SAM3 accuracy.
    observation = sphere_views([0, 0, 0.45])
    camera = observation.cameras["agentview"]
    with service(camera) as (url, calls):
        config = perception.runtime_identity(
            "so101_control", {"CAP_HARNESS_SAM3_URL": url, "CAP_HARNESS_SO101_SEGMENTATION": "sam3"}
        )
        adapter = SimpleNamespace(get_observation=lambda: observation)
        api = CapApi(
            adapter,
            home_joint_positions={},
            segmentation_provider=perception.provider(config),
            default_camera="agentview",
        )
        found = api.localize_object("strawberry", target_frame=camera.frame)
        assert found.ok and found.point_cloud.frame == camera.frame
        assert len(found.point_cloud.points) > 30
        assert found.segmentation.score == 0.88
        assert set(calls[0]) == {"image_base64", "text_prompt"}
        assert base64.b64decode(calls[0]["image_base64"]).startswith(b"\x89PNG")
        missing = replace(camera, depth_m=np.zeros_like(camera.depth_m))
        adapter.get_observation = lambda: SimpleNamespace(cameras={"agentview": missing})
        failed = api.localize_object("strawberry", target_frame=camera.frame)
        assert not failed.ok and failed.error.code == ErrorCode.POINT_CLOUD_FAILED


def test_provider_errors_and_preflight_never_substitute_color_masks():
    camera = sphere_views([0, 0, 0.45]).cameras["agentview"]
    with service(camera, malformed=True) as (url, calls):
        provider = perception.provider(
            perception.configuration(
                "so101_control",
                {"CAP_HARNESS_SAM3_URL": url, "CAP_HARNESS_SO101_SEGMENTATION": "sam3"},
            )
        )
        result = provider.segment_text(camera, "strawberry")
        assert not result.ok and result.error.code == ErrorCode.PERCEPTION_FAILED
        assert len(calls) == 1
    with service(camera, ready=False) as (url, _), pytest.raises(ValueError, match="provenance"):
        perception.runtime_identity(
            "so101_control", {"CAP_HARNESS_SAM3_URL": url, "CAP_HARNESS_SO101_SEGMENTATION": "sam3"}
        )
    with pytest.raises(ValueError, match="dispatch is blocked"):
        perception.runtime_identity(
            "so101_control",
            {
                "CAP_HARNESS_SAM3_URL": "http://127.0.0.1:1",
                "CAP_HARNESS_SO101_SEGMENTATION": "sam3",
            },
        )


def test_native_episode_uses_sam3_http_and_saves_overlay_without_robot_motion(
    tmp_path, monkeypatch
):
    pytest.importorskip("robosuite")
    from cap_harness.run import run_program

    reference = sphere_views([0, 0, 0.45]).cameras["agentview"]
    # This is a protocol fixture mask, deliberately not a real model prediction.
    camera = replace(
        reference, rgb=np.full((64, 64, 3), 128, dtype=np.uint8), depth_m=np.ones((64, 64))
    )
    with service(camera) as (url, calls):
        monkeypatch.setenv("CAP_HARNESS_SAM3_URL", url)
        monkeypatch.setenv("CAP_HARNESS_SO101_SEGMENTATION", "sam3")
        program = tmp_path / "observe.py"
        program.write_text(
            "found = localize_object('strawberry', camera_name='agentview', target_frame='so101_base')\n"
            "assert found.ok, str(found.error)\n"
            "result = {'frame': found.point_cloud.frame}\n"
        )
        outcome = run_program(
            benchmark="so101",
            suite="so101_control",
            task_id=0,
            seed=0,
            program_path=program,
            output_root=tmp_path / "episodes",
            max_steps=2,
            camera_width=64,
            camera_height=64,
            capture_videos=False,
        )
        assert outcome.program_ok, outcome
        assert outcome.task_success is False
        assert len(calls) == 1 and calls[0]["text_prompt"] == "strawberry"
        recorded = json.loads((outcome.run_dir / "outcome.json").read_text())
        assert recorded["steps_executed"] == 0
        result = json.loads((outcome.run_dir / "source/program-result.json").read_text())["result"]
        assert result == {"frame": "so101_base"}
        assert len(list((outcome.run_dir / "media/overlays").glob("*.png"))) == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"ready": "yes"},
        {"sam3_commit": "unknown"},
        {"checkpoint_sha256": None},
        {"service_sha256": "z" * 64},
        {"confidence_threshold": float("nan")},
        {"confidence_threshold": True},
    ],
)
def test_preflight_rejects_incomplete_or_invalid_provenance(monkeypatch, changed):
    metadata = {
        "provider": "sam3",
        "ready": True,
        "checkpoint_sha256": "1" * 64,
        "sam3_commit": "2" * 40,
        "service_sha256": "3" * 64,
        "confidence_threshold": 0.5,
        **changed,
    }
    monkeypatch.setattr(
        perception.HttpProviderClient, "request_json", lambda *args, **kwargs: metadata
    )
    with pytest.raises(ValueError):
        perception.runtime_identity(env={"CAP_HARNESS_SO101_SEGMENTATION": "sam3"})


def test_failed_preflight_prevents_simulator_construction(monkeypatch, tmp_path):
    from cap_harness.run import run_program
    from cap_harness.so101 import adapter as adapter_module

    monkeypatch.setenv("CAP_HARNESS_SO101_SEGMENTATION", "sam3")
    monkeypatch.setenv("CAP_HARNESS_SAM3_URL", "http://127.0.0.1:1")

    def forbidden(*args, **kwargs):
        pytest.fail("Simulator constructed before SAM3 preflight")

    monkeypatch.setattr(adapter_module, "SO101Adapter", forbidden)
    program = tmp_path / "probe.py"
    program.write_text("result = {}\n")
    with pytest.raises(ValueError, match="dispatch is blocked"):
        run_program(
            benchmark="so101",
            suite="so101_control",
            task_id=0,
            seed=0,
            program_path=program,
            output_root=tmp_path / "runs",
            capture_videos=False,
        )
