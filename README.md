# fingerprint-jetson-nano

Fingerprint worker for Jetson Nano on the Python 3.6 / JetPack TensorRT stack.

## Install with `uv`

This branch keeps TensorRT, NumPy, OpenCV, and PyQt5 from the JetPack system
packages. Do not create a clean isolated env for this branch.

```bash
cd fingerprint-jetson-nano
uv venv --python /usr/bin/python3 --system-site-packages venv
source venv/bin/activate
uv sync --active --extra jetson
```

If you need the ONNX fallback environment instead of TensorRT:

```bash
source venv/bin/activate
uv sync --active --extra onnx
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
