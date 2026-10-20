"""Locate checkout-owned experiment configuration and external resources."""

import os
from pathlib import Path


def workspace_root() -> Path:
    """Use an explicit experiment checkout when running an installed wheel."""
    configured = os.environ.get("CAP_HARNESS_SO101_WORKSPACE")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("CAP_HARNESS_SO101_WORKSPACE must name an existing checkout directory")
        return root
    return Path(__file__).resolve().parents[3]
