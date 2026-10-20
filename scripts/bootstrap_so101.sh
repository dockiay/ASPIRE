#!/usr/bin/env bash
# Download the official SO-101 description without changing Robosuite's checkout.
set -euo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$REPO_ROOT/src/cap_harness/configs/robots/so101.json"
read_config() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$CONFIG" "$1"; }
MODEL_REPO="$(read_config repository)"
MODEL_COMMIT="$(read_config commit)"
MODEL_ROOT="$REPO_ROOT/$(read_config checkout)"

printf 'Official SO-101 model\nRepository: %s\nCommit: %s\n' "$MODEL_REPO" "$MODEL_COMMIT"
NEW_CHECKOUT=0
if [[ ! -e "$MODEL_ROOT" ]]; then
  git clone --filter=blob:none --no-checkout --depth 1 "$MODEL_REPO" "$MODEL_ROOT"
  NEW_CHECKOUT=1
fi
[[ "$(git -C "$MODEL_ROOT" remote get-url origin)" == "$MODEL_REPO" ]] || {
  printf 'error: unexpected origin in %s\n' "$MODEL_ROOT" >&2; exit 1;
}
if [[ "$NEW_CHECKOUT" == 0 && -n "$(git -C "$MODEL_ROOT" status --porcelain)" ]]; then
  printf 'error: model checkout has local changes; preserve them before updating\n' >&2; exit 1
fi
if ! git -C "$MODEL_ROOT" cat-file -e "$MODEL_COMMIT^{commit}" 2>/dev/null; then
  git -C "$MODEL_ROOT" fetch --depth 1 origin "$MODEL_COMMIT"
fi
git -C "$MODEL_ROOT" sparse-checkout set "$(read_config sparse_path)"
git -C "$MODEL_ROOT" checkout --detach "$MODEL_COMMIT"
[[ "$(git -C "$MODEL_ROOT" rev-parse HEAD)" == "$MODEL_COMMIT" ]]
for relative in LICENSE "$(read_config model)" "$(read_config urdf)"; do
  [[ -f "$MODEL_ROOT/$relative" ]] || { printf 'error: missing %s\n' "$relative" >&2; exit 1; }
done
printf '\nSO-101 description ready: %s\nOriginal files and upstream license retained.\n' "$MODEL_ROOT"
