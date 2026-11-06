#!/usr/bin/env bash
# Install KorvaTTS and its model files locally for offline Orange Pi inference.
set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$REPO_ROOT/.venv"
ASSETS_DIR="$REPO_ROOT/assets"
HF_REPO="${KORVATTS_HF_REPO:-dogenthq/KorvaTTS}"

require_python() {
  "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")
PY
}

create_env() {
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    "$VENV_DIR/bin/python" -m ensurepip --upgrade
  fi
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install "$REPO_ROOT"
}

download_assets() {
  mkdir -p "$ASSETS_DIR"
  ASSETS_DIR="$ASSETS_DIR" HF_REPO="$HF_REPO" "$VENV_DIR/bin/python" - <<'PY'
import os
from huggingface_hub import snapshot_download

assets_dir = os.environ["ASSETS_DIR"]
repo_id = os.environ["HF_REPO"]
snapshot_download(
    repo_id=repo_id,
    allow_patterns=["onnx/*", "voice_styles/*"],
    local_dir=assets_dir,
)
PY
}

configure_env() {
  if [ ! -f "$REPO_ROOT/.env" ]; then
    token="$($VENV_DIR/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
    sed "s|^KORVATTS_API_TOKEN=.*|KORVATTS_API_TOKEN=$token|" \
      "$REPO_ROOT/.env.example" > "$REPO_ROOT/.env"
    chmod 600 "$REPO_ROOT/.env"
  fi
}

verify_assets() {
  ASSETS_DIR="$ASSETS_DIR" "$VENV_DIR/bin/python" - <<'PY'
import os
from pathlib import Path
from korvatts.assets import ONNX_FILES, is_valid_assets_dir

assets_dir = Path(os.environ["ASSETS_DIR"])
if not is_valid_assets_dir(assets_dir):
    missing = [name for name in ONNX_FILES if not (assets_dir / "onnx" / name).is_file()]
    raise SystemExit(f"Model download incomplete; missing: {', '.join(missing)}")
print(f"Local model ready: {assets_dir}")
PY
}

require_python
create_env
download_assets
configure_env
verify_assets

cat <<EOF

Installation complete. The downloaded model is stored in:
  $ASSETS_DIR

Run fully offline from the project directory:
  cd "$REPO_ROOT"
  HF_MODEL_ONLINE=false "$VENV_DIR/bin/python" web_service.py

The local web service listens on http://127.0.0.1:8080 by default.
EOF
