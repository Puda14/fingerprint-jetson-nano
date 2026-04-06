"""
MQTT Worker Client — connects to orchestrator broker.

Ported from fingerprint_worker/app/mqtt/client.py with extensions for
register/verify task topics.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from app.core.config import get_settings
from app.mqtt.payloads import HeartbeatPayload, WorkerStatus

logger = logging.getLogger(__name__)

MessageHandler = Callable[[mqtt.Client, mqtt.MQTTMessage], None]


class MQTTWorkerClient:
    """MQTT client that maintains connection to orchestrator broker.

    Features:
    - Auto-reconnect with LWT (Last Will and Testament)
    - Periodic heartbeat with worker status
    - Subscribe to task, model, and message topics
    - Singleton via get_mqtt_client()
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._worker_id = self._settings.device_id
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._message_handler: Optional[MessageHandler] = None
        self._current_task_id: Optional[str] = None
        self._start_time = time.time()
        self.stats: Dict[str, Any] = {
            "messages_received": 0,
            "messages_sent": 0,
            "heartbeats_sent": 0,
            "connect_count": 0,
            "last_connected_at": None,
            "last_disconnected_at": None,
        }

    # -- Properties ----------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def current_task_id(self) -> Optional[str]:
        return self._current_task_id

    @current_task_id.setter
    def current_task_id(self, value: Optional[str]) -> None:
        self._current_task_id = value

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    # -- Connection ----------------------------------------------------------

    def connect(self) -> None:
        """Connect to the MQTT broker."""
        client_id = self._settings.mqtt_client_id or "worker-{}".format(self._worker_id)

        try:
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
            )
        except (AttributeError, TypeError):
            # Older paho-mqtt versions
            self._client = mqtt.Client(
                client_id=client_id,
                protocol=mqtt.MQTTv311,
            )

        if self._settings.mqtt_username:
            self._client.username_pw_set(
                self._settings.mqtt_username,
                self._settings.mqtt_password,
            )

        # Last Will and Testament — auto-publish offline status if connection drops
        lwt_topic = "worker/{}/status".format(self._worker_id)
        lwt_payload = json.dumps({"status": "offline", "worker_id": self._worker_id})
        self._client.will_set(lwt_topic, payload=lwt_payload, qos=1, retain=True)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        logger.info(
            "Connecting to MQTT %s:%d ...",
            self._settings.mqtt_broker_host,
            self._settings.mqtt_broker_port,
        )
        self._client.connect(
            host=self._settings.mqtt_broker_host,
            port=self._settings.mqtt_broker_port,
            keepalive=self._settings.mqtt_keepalive,
        )
        self._client.loop_start()

    def disconnect(self) -> None:
        """Gracefully disconnect from MQTT broker."""
        self._send_heartbeat(status=WorkerStatus.OFFLINE)
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        if self._client:
            self._client.disconnect()
            self._client.loop_stop()
        self._connected = False
        self.stats["last_disconnected_at"] = time.time()

    # -- Callbacks -----------------------------------------------------------

    def _on_connect(self, client: Any, userdata: Any, flags: Any, *args: Any) -> None:
        rc = args[0] if args else 0
        if rc == 0:
            self._connected = True
            self.stats["connect_count"] += 1
            self.stats["last_connected_at"] = time.time()
            logger.info("MQTT connected to broker")

            # Subscribe to all task topics for this worker
            topics = [
                ("task/{}/embed".format(self._worker_id), 1),
                ("task/{}/match".format(self._worker_id), 1),
                ("task/{}/register".format(self._worker_id), 1),
                ("task/{}/verify".format(self._worker_id), 1),
                ("task/{}/sync".format(self._worker_id), 1),
                ("task/{}/message".format(self._worker_id), 1),
                ("task/{}/model/update".format(self._worker_id), 1),
            ]
            for topic, qos in topics:
                client.subscribe(topic, qos=qos)
                logger.debug("Subscribed: %s", topic)

            self._send_heartbeat(status=WorkerStatus.ONLINE)
            self._sync_offline_data_on_connect()
            self._start_heartbeat()
        else:
            logger.error("MQTT connection failed, rc=%s", rc)

    def _on_disconnect(self, client: Any, userdata: Any, *args: Any) -> None:
        self._connected = False
        self.stats["last_disconnected_at"] = time.time()
        rc = args[-2] if len(args) >= 2 else (args[0] if args else 0)
        if rc != 0:
            logger.warning("MQTT connection lost (rc=%s), will auto-reconnect", rc)

    def _on_message(self, client: Any, userdata: Any, message: mqtt.MQTTMessage) -> None:
        self.stats["messages_received"] += 1
        if self._message_handler:
            try:
                self._message_handler(client, message)
            except Exception as exc:
                logger.error("Error processing message '%s': %s", message.topic, exc)

    # -- Public API ----------------------------------------------------------

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the callback for incoming MQTT messages."""
        self._message_handler = handler

    def publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        """Publish a message to the MQTT broker."""
        if self._client and self._connected:
            result = self._client.publish(topic, payload=payload, qos=qos)
            self.stats["messages_sent"] += 1
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        return False

    def publish_result(self, task_id: str, payload: str) -> bool:
        """Publish a task result to result/{task_id}."""
        return self.publish("result/{}".format(task_id), payload, qos=1)

    # -- Heartbeat -----------------------------------------------------------

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="mqtt-heartbeat",
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                status = WorkerStatus.BUSY if self._current_task_id else WorkerStatus.IDLE
                self._send_heartbeat(status=status)
            except Exception as exc:
                logger.error("Heartbeat error: %s", exc)
            self._stop_event.wait(timeout=self._settings.heartbeat_interval)

    def _send_heartbeat(self, status: WorkerStatus = WorkerStatus.IDLE) -> None:
        # Gather loaded models info
        try:
            from app.services.model_service import get_model_service
            loaded_models = get_model_service().loaded_models
        except Exception:
            loaded_models = {}

        # Check sensor status
        sensor_connected = False
        try:
            from app.services.sensor_service import SensorService
            inst = SensorService.get_instance()
            if inst:
                sensor_connected = inst.is_connected
        except Exception:
            pass

        heartbeat = HeartbeatPayload(
            worker_id=self._worker_id,
            status=status.value if hasattr(status, "value") else status,
            current_task_id=self._current_task_id,
            uptime_seconds=round(self.uptime, 1),
            loaded_models=loaded_models,
            sensor_connected=sensor_connected,
        )
        topic = "worker/{}/heartbeat".format(self._worker_id)
        if self.publish(topic, json.dumps(heartbeat.__dict__), qos=1):
            self.stats["heartbeats_sent"] += 1

    def send_manual_heartbeat(self, status: WorkerStatus = WorkerStatus.IDLE) -> bool:
        """Send a heartbeat immediately (for CLI/GUI use)."""
        self._send_heartbeat(status)
        return self._connected

    def _sync_offline_data_on_connect(self) -> None:
        """Flush locally queued enrollment events after MQTT reconnects."""

        def _worker() -> None:
            try:
                from app.services.pipeline_service import get_pipeline_service

                svc = get_pipeline_service()
                sent = svc.sync_offline_enrollments()
                if sent:
                    logger.info("Offline sync on reconnect sent %d event(s).", sent)
            except Exception as exc:
                logger.warning("Offline sync on reconnect failed: %s", exc)

        threading.Thread(
            target=_worker,
            daemon=True,
            name="mqtt-offline-sync",
        ).start()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mqtt_client: Optional[MQTTWorkerClient] = None


def get_mqtt_client() -> MQTTWorkerClient:
    """Get the singleton MQTT client instance."""
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = MQTTWorkerClient()
    return _mqtt_client
