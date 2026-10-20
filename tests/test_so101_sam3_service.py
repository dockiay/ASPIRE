"""Service startup/provenance tests with mocked SAM3 and Torch, not model accuracy."""

import asyncio
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def service_module(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("PIL")
    pytest.importorskip("uvicorn")
    source = tmp_path / "sam3-source"
    package = source / "sam3"
    package.mkdir(parents=True)
    calls = {}
    sam3 = ModuleType("sam3")
    sam3.__file__ = str(package / "__init__.py")
    processor = ModuleType("sam3.model.sam3_image_processor")
    builder = ModuleType("sam3.model_builder")

    def build(**kwargs):
        calls["builder"] = kwargs
        return object()

    def process(model, **kwargs):
        calls["processor"] = kwargs
        return object()

    processor.Sam3Processor = process
    builder.build_sam3_image_model = build
    torch = ModuleType("torch")
    torch.__version__ = "fixture"
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.inference_mode = lambda: lambda function: function
    for name, module in {
        "sam3": sam3,
        "sam3.model": ModuleType("sam3.model"),
        "sam3.model.sam3_image_processor": processor,
        "sam3.model_builder": builder,
        "torch": torch,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "src/cap_harness/providers/sam3/service.py"
    spec = importlib.util.spec_from_file_location(
        "cap_harness.providers.sam3._fixture_service", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda args, **kw: str(source) if args[-1] == "--show-toplevel" else "a" * 40,
    )
    monkeypatch.setattr(module.uvicorn, "run", lambda *args, **kw: calls.update(server=kw))
    return module, calls, source


def test_local_checkpoint_startup_reports_actual_hash_and_preserves_default_threshold(
    service_module, monkeypatch, tmp_path
):
    module, calls, _ = service_module
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"mock checkpoint, not SAM3 weights")
    monkeypatch.setattr(sys, "argv", ["sam3", "--device", "cpu", "--checkpoint", str(checkpoint)])
    module.main()
    metadata = asyncio.run(module.metadata())
    assert metadata["ready"] is True
    assert metadata["checkpoint_sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert metadata["sam3_commit"] == "a" * 40
    assert metadata["confidence_threshold"] == 0.0
    assert (
        metadata["service_sha256"] == hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    )
    assert calls["builder"]["checkpoint_path"] == str(checkpoint.resolve())
    assert calls["builder"]["load_from_HF"] is False
    assert calls["processor"]["confidence_threshold"] == 0.0


def test_missing_source_provenance_does_not_falsely_report_parent_repository(
    service_module, monkeypatch, tmp_path
):
    module, _, source = service_module
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"mock checkpoint")
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kw: str(source.parent))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sam3",
            "--device",
            "cpu",
            "--checkpoint",
            str(checkpoint),
            "--confidence-threshold",
            "0.5",
        ],
    )
    module.main()
    assert asyncio.run(module.metadata())["sam3_commit"] is None
    assert asyncio.run(module.metadata())["confidence_threshold"] == 0.5


@pytest.mark.parametrize("threshold", ["nan", "-1", "1.1"])
def test_invalid_threshold_never_loads_model(service_module, monkeypatch, threshold):
    module, calls, _ = service_module
    monkeypatch.setattr(sys, "argv", ["sam3", "--confidence-threshold", threshold])
    with pytest.raises(SystemExit):
        module.main()
    assert "builder" not in calls
