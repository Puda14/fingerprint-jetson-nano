"""HTTP and WebSocket client for communicating with the FastAPI backend."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class ApiClient:
    """Synchronous HTTP client wrapping the FastAPI worker endpoints.

    Designed to be called from QThread workers to avoid blocking the UI.
    """

    def __init__(self, base_url: str = "http://localhost:8000/api/v1") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = 10

    # -- helpers -------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            resp = requests.get(
                "{}/{}".format(self.base_url, path.lstrip("/")),
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("GET %s failed: %s", path, exc)
            return {"success": False, "error": str(exc)}

    def _post(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            resp = requests.post(
                "{}/{}".format(self.base_url, path.lstrip("/")),
                json=json_data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("POST %s failed: %s", path, exc)
            return {"success": False, "error": str(exc)}

    def _delete(self, path: str) -> Dict[str, Any]:
        try:
            resp = requests.delete(
                "{}/{}".format(self.base_url, path.lstrip("/")),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("DELETE %s failed: %s", path, exc)
            return {"success": False, "error": str(exc)}

    # -- system --------------------------------------------------------------

    def get_health(self) -> Dict[str, Any]:
        return self._get("/system/health")

    def get_config(self) -> Dict[str, Any]:
        return self._get("/system/config")

    def get_stats(self) -> Dict[str, Any]:
        return self._get("/system/stats")

    # -- sensor --------------------------------------------------------------

    def get_sensor_status(self) -> Dict[str, Any]:
        return self._get("/sensor/status")

    def capture_image(self) -> Dict[str, Any]:
        return self._post("/sensor/capture")

    def set_led(self, color: str = "green", duration_ms: int = 1000) -> Dict[str, Any]:
        return self._post("/sensor/led", {"color": color, "duration_ms": duration_ms})

    # -- users ---------------------------------------------------------------

    def list_users(
        self, page: int = 1, limit: int = 50, search: Optional[str] = None
    ) -> Dict[str, Any]:
        params = {"page": page, "limit": limit}
        if search:
            params["search"] = search
        return self._get("/users", params=params)

    def create_user(
        self,
        employee_id: str,
        full_name: str,
        department: str = "",
        role: str = "employee",
    ) -> Dict[str, Any]:
        return self._post(
            "/users",
            {
                "employee_id": employee_id,
                "full_name": full_name,
                "department": department,
                "role": role,
            },
        )

    def enroll_finger(
        self, user_id: str, finger: str = "right_index", num_samples: int = 3
    ) -> Dict[str, Any]:
        return self._post(
            "/users/{}/enroll".format(user_id),
            {"finger": finger, "num_samples": num_samples},
        )

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        return self._delete("/users/{}".format(user_id))

    # -- verification --------------------------------------------------------

    def verify(self, user_id: str) -> Dict[str, Any]:
        return self._post("/verify", {"user_id": user_id})

    def identify(self, top_k: int = 5) -> Dict[str, Any]:
        return self._post("/identify", {"top_k": top_k})

    # -- models --------------------------------------------------------------

    def list_models(self) -> Dict[str, Any]:
        return self._get("/models")


# ---------------------------------------------------------------------------
# Background worker threads
# ---------------------------------------------------------------------------


class HealthPollerThread(QThread):
    """Periodically polls backend health and emits the result."""

    health_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(self, client: ApiClient, interval_sec: float = 5.0) -> None:
        super().__init__()
        self.client = client
        self.interval_sec = interval_sec
        self._running = True
        self._was_connected = False

    def run(self) -> None:
        while self._running:
            result = self.client.get_health()
            is_connected = result.get("success", False)

            if is_connected != self._was_connected:
                self.connection_changed.emit(is_connected)
                self._was_connected = is_connected

            self.health_received.emit(result)
            time.sleep(self.interval_sec)

    def stop(self) -> None:
        self._running = False


class ApiWorkerThread(QThread):
    """Runs a single API call in a background thread."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs) -> None:
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class StreamThread(QThread):
    """Connects to WebSocket sensor stream and emits frames."""

    frame_received = pyqtSignal(dict)
    stream_error = pyqtSignal(str)
    stream_status = pyqtSignal(str)

    def __init__(self, ws_url: str, fps: int = 10) -> None:
        super().__init__()
        self.ws_url = ws_url
        self.fps = fps
        self._running = True

    def run(self) -> None:
        try:
            import websocket
        except ImportError:
            # Fallback: use polling via HTTP instead
            self._poll_fallback()
            return

        try:
            ws = websocket.WebSocket()
            ws.connect(self.ws_url, timeout=5)
            self.stream_status.emit("connected")

            # Send start command
            ws.send(json.dumps({"action": "start", "fps": self.fps}))

            while self._running:
                try:
                    ws.settimeout(2.0)
                    msg = ws.recv()
                    if msg:
                        data = json.loads(msg)
                        if data.get("type") == "frame":
                            self.frame_received.emit(data)
                except Exception:
                    if not self._running:
                        break
                    continue

            ws.send(json.dumps({"action": "stop"}))
            ws.close()
        except Exception as exc:
            self.stream_error.emit(str(exc))
            # Fallback to HTTP polling
            self._poll_fallback()

    def _poll_fallback(self) -> None:
        """Fallback: poll /sensor/capture via HTTP."""
        self.stream_status.emit("polling")
        # Extract base URL from ws URL
        base = self.ws_url.replace("ws://", "http://").replace("/sensor/stream", "")
        client = ApiClient(base)
        interval = 1.0 / max(self.fps, 1)

        while self._running:
            try:
                result = client.capture_image()
                data = result.get("data", {})
                if data and data.get("success"):
                    self.frame_received.emit({
                        "type": "frame",
                        "image_base64": data.get("image_base64", ""),
                        "width": data.get("width", 192),
                        "height": data.get("height", 192),
                        "quality_score": data.get("quality_score", 0),
                        "has_finger": data.get("has_finger", False),
                        "timestamp": time.time(),
                    })
            except Exception:
                pass
            time.sleep(interval)

    def stop(self) -> None:
        self._running = False
