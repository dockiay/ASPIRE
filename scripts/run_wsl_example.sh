#!/usr/bin/env bash
set -euo pipefail

# Run from PowerShell:
# wsl -d Ubuntu-24.04 -- bash /mnt/d/AI/Aspire/scripts/run_wsl_example.sh
cd "$HOME/src/ASPIRE"
source .venv-libero/bin/activate
export LIBERO_CONFIG_PATH="$PWD/.libero"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export MUJOCO_GL=glfw
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
export CUDA_VISIBLE_DEVICES=0
unset PYOPENGL_PLATFORM EGL_PLATFORM MUJOCO_EGL_DEVICE_ID

cap-harness run --benchmark libero-pro --suite libero_object_swap \
  --task-id 0 --seed 1 --init-mode saved \
  --program "${1:-examples/libero/gripper_demo.py}" \
  --output-root outputs/local/wsl-example --max-steps 200 \
  --camera-width 512 --camera-height 512
