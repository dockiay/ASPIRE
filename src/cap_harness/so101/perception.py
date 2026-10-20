"""Select ASPIRE's real SAM3 service or an explicitly labelled color baseline."""

import math
import os

from cap_harness.providers.http import HttpProviderClient, ProviderHttpError
from cap_harness.providers.sam3.client import DEFAULT_SAM3_URL, Sam3Provider


def configuration(suite=None, env=None):
    env = os.environ if env is None else env
    backend = env.get("CAP_HARNESS_SO101_SEGMENTATION") or "color-rgbd"
    if backend not in ("sam3", "color-rgbd"):
        raise ValueError("CAP_HARNESS_SO101_SEGMENTATION must be sam3 or color-rgbd")
    return {
        "backend": backend,
        "url": env.get("CAP_HARNESS_SAM3_URL", DEFAULT_SAM3_URL) if backend == "sam3" else None,
        "fallback": None,
        "input": "public camera RGB; metric geometry uses calibrated public depth only",
        "geometry_scope": "visible surfaces only; no hidden simulator object poses or complete shape",
    }


def provider(config):
    if config["backend"] == "sam3":
        return Sam3Provider(base_url=config["url"])
    if config["backend"] != "color-rgbd":
        raise ValueError("Unknown SO-101 segmentation backend")
    from cap_harness.so101.segmentation import ColorSegmentationProvider

    return ColorSegmentationProvider()


def runtime_identity(suite=None, env=None):
    """Preflight readiness and record checkpoint/code/threshold before model calls."""
    config = configuration(suite, env)
    if config["backend"] == "sam3":
        try:
            metadata = HttpProviderClient(config["url"], timeout_s=5, max_retries=0).request_json(
                "GET", "/metadata"
            )
        except ProviderHttpError as exc:
            raise ValueError(
                "SAM3 is unavailable. Start the SAM3 service before launching or resuming ASPIRE; "
                "controller dispatch is blocked at this check. " + exc.error.message
            ) from exc
        required = ("checkpoint_sha256", "sam3_commit", "service_sha256", "confidence_threshold")
        if (
            not isinstance(metadata, dict)
            or metadata.get("provider") != "sam3"
            or metadata.get("ready") is not True
            or any(metadata.get(key) is None for key in required)
        ):
            raise ValueError("SAM3 service must expose ready model provenance at /metadata")
        for key, length in (("checkpoint_sha256", 64), ("sam3_commit", 40), ("service_sha256", 64)):
            value = metadata[key]
            if (
                not isinstance(value, str)
                or len(value) != length
                or any(c not in "0123456789abcdefABCDEF" for c in value)
            ):
                raise ValueError("SAM3 service must expose valid model provenance at /metadata")
        threshold = metadata["confidence_threshold"]
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("SAM3 service must expose a valid confidence threshold")
        config["model"] = {key: metadata[key] for key in ("provider", "ready", *required)}
    return config
