# fingerprint-jetson-nano

Fingerprint worker for Jetson Nano on the Python 3.6 / JetPack TensorRT stack.

## Install with `uv`

This branch keeps TensorRT, NumPy, OpenCV, and PyQt5 from the JetPack system
packages. Do not create a clean isolated env for this branch.

```bash
cd fingerprint-jetson-nano
uv venv --python /usr/bin/python3 --system-site-packages venv
source venv/bin/activate
uv sync --active --no-editable --extra jetson
```

For day-to-day Jetson updates, prefer the repo setup script instead of a raw
`uv sync`. It keeps the existing `venv`, refreshes the project package, and
re-installs Jetson-specific runtime pieces like PyCUDA / FAISS when needed:

```bash
cd fingerprint-jetson-nano
SKIP_APT=1 RECREATE_VENV=0 ./scripts/setup_jetson_env.sh
```

If you still want to use `uv sync` directly, use `--inexact` so `uv` does not
remove manually installed Jetson runtime packages from the environment.

Because the package is installed with `--no-editable`, a plain `git pull` can
leave `uv` reusing a cached wheel for `fingerprint-jetson-worker` if the
package version has not changed. After pulling code changes, force-refresh the
local package before starting the worker:

```bash
source venv/bin/activate
uv sync --active --inexact --no-editable --extra jetson \
  --refresh-package fingerprint-jetson-worker \
  --reinstall-package fingerprint-jetson-worker
```

If you need the ONNX fallback environment instead of TensorRT:

```bash
source venv/bin/activate
uv sync --active --inexact --no-editable --extra onnx \
  --refresh-package fingerprint-jetson-worker \
  --reinstall-package fingerprint-jetson-worker
```

## Run

Start the API:

```bash
fingerprint-worker-api
```

Start the desktop GUI:

```bash
fingerprint-worker-gui
```

Start the interactive CLI:

```bash
fingerprint-worker-cli
```

## Verify Demo Compatibility

The worker exposes both the legacy worker WebSocket route and the demo route:

- `WS /api/v1/ws/verify`
- `WS /api/v1/ws/verification`
- `WS /ws/verify`
- `WS /ws/verification`

Demo-style messages now work directly on the worker:

- `{"action":"start","mode":"verify","user_id":"123"}`
- `{"action":"start","mode":"identify","top_k":5}`
- `{"action":"stop"}`

While streaming, the worker sends:

- `capture_preview`
- `verification_result`
- `identification_result`

## Configuration

Copy `.env.example` to `.env` and adjust the values you need.

Important path variables are resolved relative to `WORKER_HOME` when they are
not absolute:

- `WORKER_HOME`
- `WORKER_MODEL_DIR`
- `WORKER_DATA_DIR`
- `WORKER_BACKUP_DIR`
- `WORKER_MODEL_PATH`

`WORKER_MODEL_PATH` can point to either a specific model file or a directory.
For Jetson deployments with versioned models, prefer setting it to the embedding
folder such as `models/embedding`. The worker will then auto-discover the best
candidate for the active backend, while MQTT-managed downloads still take
priority via `loaded_models.json`.
