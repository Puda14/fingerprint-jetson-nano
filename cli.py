#!/usr/bin/env python3
"""
Interactive CLI for Fingerprint Jetson Nano Worker.
Works entirely over SSH — no GUI or PyQt5 required.

Features:
  - Local API operations (register, verify, identify)
  - MQTT monitoring (heartbeats, tasks, model updates from orchestrator)
"""

import base64
import glob
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False


# ── ANSI Colors ──────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"


# ── Configuration ────────────────────────────────────────────
BASE_URL = "http://localhost:8000/api/v1"

# Read from .env file if available
def _load_env():
    env = {}
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip().strip('"').strip("'")
    return env

_env = _load_env()
DEVICE_ID = os.environ.get("WORKER_DEVICE_ID", _env.get("WORKER_DEVICE_ID", "JETSON-001"))
MQTT_HOST = os.environ.get("WORKER_MQTT_BROKER_HOST", _env.get("WORKER_MQTT_BROKER_HOST", "localhost"))
MQTT_PORT = int(os.environ.get("WORKER_MQTT_BROKER_PORT", _env.get("WORKER_MQTT_BROKER_PORT", "1883")))
MQTT_USER = os.environ.get("WORKER_MQTT_USERNAME", _env.get("WORKER_MQTT_USERNAME", ""))
MQTT_PASS = os.environ.get("WORKER_MQTT_PASSWORD", _env.get("WORKER_MQTT_PASSWORD", ""))


# ── MQTT State ───────────────────────────────────────────────
_lock = threading.Lock()
_mqtt_connected = False
_mqtt_client_inst = None
_message_log = []       # (timestamp, event_type, topic, data_preview)
_max_log = 100
_mqtt_stats = {
    "messages_in": 0,
    "heartbeats_seen": 0,
    "tasks_received": 0,
    "model_updates": 0,
}


# ── Helpers ──────────────────────────────────────────────────
def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")


def fmt_ago(ts):
    if ts is None:
        return "—"
    diff = int(time.time() - ts)
    if diff < 60:
        return "{}s ago".format(diff)
    elif diff < 3600:
        return "{}m {}s ago".format(diff // 60, diff % 60)
    return "{}h ago".format(diff // 3600)


def api_request(method, endpoint, data=None, timeout=15):
    url = "{}{}".format(BASE_URL, endpoint)
    headers = {"Content-Type": "application/json"}
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {"success": False, "error": "HTTP {}: {}".format(e.code, body[:200])}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _add_log(event_type, topic, data_preview=""):
    with _lock:
        _message_log.append((time.time(), event_type, topic, data_preview))
        if len(_message_log) > _max_log:
            _message_log.pop(0)


# ── MQTT Client ─────────────────────────────────────────────
def _on_connect(client, userdata, flags, *args):
    global _mqtt_connected
    rc = args[0] if args else 0
    if rc == 0:
        _mqtt_connected = True
        # Subscribe to all topics for this worker
        client.subscribe("task/{}/+".format(DEVICE_ID), qos=1)
        client.subscribe("task/{}/model/update".format(DEVICE_ID), qos=1)
        # Also monitor orchestrator broadcasts
        client.subscribe("worker/{}/heartbeat".format(DEVICE_ID), qos=1)
        client.subscribe("result/+", qos=1)
        _add_log("system", "mqtt", "Connected to broker")
    else:
        _mqtt_connected = False


def _on_disconnect(client, userdata, *args):
    global _mqtt_connected
    _mqtt_connected = False
    _add_log("system", "mqtt", "Disconnected from broker")


def _on_message(client, userdata, message):
    _mqtt_stats["messages_in"] += 1
    topic = message.topic

    try:
        data = json.loads(message.payload.decode())
    except Exception:
        data = {"raw": message.payload.decode()[:100] if message.payload else ""}

    # Classify message
    if "heartbeat" in topic:
        _mqtt_stats["heartbeats_seen"] += 1
        _add_log("heartbeat", topic, "status={}".format(data.get("status", "?")))
    elif "model/update" in topic:
        _mqtt_stats["model_updates"] += 1
        _add_log("model", topic, "{}  v{}".format(data.get("model_name", "?"), data.get("version", "?")))
    elif topic.startswith("task/"):
        _mqtt_stats["tasks_received"] += 1
        task_type = topic.split("/")[-1]
        _add_log("task", topic, "type={} id={}".format(task_type, data.get("task_id", "?")[:12]))
    elif topic.startswith("result/"):
        _add_log("result", topic, "status={}".format(data.get("status", "?")))
    else:
        _add_log("other", topic, str(data)[:60])


def mqtt_connect():
    global _mqtt_client_inst, _mqtt_connected
    if not HAS_MQTT:
        return False

    client_id = "worker-cli-{}".format(os.getpid())
    try:
        _mqtt_client_inst = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id, protocol=mqtt.MQTTv311,
        )
    except (AttributeError, TypeError):
        _mqtt_client_inst = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    if MQTT_USER:
        _mqtt_client_inst.username_pw_set(MQTT_USER, MQTT_PASS)

    _mqtt_client_inst.on_connect = _on_connect
    _mqtt_client_inst.on_disconnect = _on_disconnect
    _mqtt_client_inst.on_message = _on_message

    try:
        _mqtt_client_inst.connect(MQTT_HOST, MQTT_PORT, 60)
        _mqtt_client_inst.loop_start()
        time.sleep(2)
        return _mqtt_connected
    except Exception as e:
        _add_log("error", "mqtt", str(e))
        return False


def mqtt_disconnect():
    if _mqtt_client_inst:
        _mqtt_client_inst.loop_stop()
        _mqtt_client_inst.disconnect()


# ── Banner ───────────────────────────────────────────────────
def print_banner():
    print("""
{cyan}{bold}╔══════════════════════════════════════════════════╗
║      🔐  FINGERPRINT WORKER — CLI                ║
╚══════════════════════════════════════════════════╝{reset}
""".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))


# ── Menu ─────────────────────────────────────────────────────
def print_menu():
    # Backend status
    health = api_request("GET", "/system/health")
    if health.get("success"):
        be_status = "{green}● ONLINE{reset}".format(green=C.GREEN, reset=C.RESET)
        d = health.get("data", {})
        users = d.get("total_users", "?")
        sensor = d.get("sensor_connected", False)
        sensor_str = "{green}● Yes{reset}".format(green=C.GREEN, reset=C.RESET) if sensor else "{red}● No{reset}".format(red=C.RED, reset=C.RESET)
    else:
        be_status = "{red}● OFFLINE{reset}".format(red=C.RED, reset=C.RESET)
        users = "?"
        sensor_str = "{dim}?{reset}".format(dim=C.DIM, reset=C.RESET)

    # MQTT status
    if _mqtt_connected:
        mq_status = "{green}● CONNECTED{reset}".format(green=C.GREEN, reset=C.RESET)
    elif not HAS_MQTT:
        mq_status = "{dim}● NO PAHO{reset}".format(dim=C.DIM, reset=C.RESET)
    else:
        mq_status = "{red}● DISCONNECTED{reset}".format(red=C.RED, reset=C.RESET)

    print("  {dim}Worker{reset} {bold}{did}{reset}  │  Backend: {be}  │  MQTT: {mq}".format(
        dim=C.DIM, reset=C.RESET, bold=C.BOLD, did=DEVICE_ID, be=be_status, mq=mq_status))
    print("  {dim}Users:{reset} {bold}{u}{reset}  │  Sensor: {s}  │  {dim}Broker:{reset} {h}:{p}".format(
        dim=C.DIM, reset=C.RESET, bold=C.BOLD, u=users, s=sensor_str, h=MQTT_HOST, p=MQTT_PORT))
    print()
    print("  {yellow}{line}{reset}".format(yellow=C.YELLOW, line="─" * 48, reset=C.RESET))
    print("  {bold}[1]{reset}  🖥️   System Status".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[2]{reset}  👥  List Users".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[3]{reset}  📝  Register New User".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[4]{reset}  ✋  Enroll Fingerprint".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[5]{reset}  🔍  Verify 1:1".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[6]{reset}  🔎  Identify 1:N".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[7]{reset}  🧠  Model Info".format(bold=C.BOLD, reset=C.RESET))
    print("  {yellow}{line}{reset}".format(yellow=C.YELLOW, line="─" * 48, reset=C.RESET))
    print("  {bold}[8]{reset}  📡  MQTT Event Log".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[9]{reset}  📈  MQTT Statistics".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[t]{reset}  🧪  Test (image-based)".format(bold=C.BOLD, reset=C.RESET))
    print("  {yellow}{line}{reset}".format(yellow=C.YELLOW, line="─" * 48, reset=C.RESET))
    print("  {bold}[r]{reset}  🔄  Reconnect MQTT".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[s]{reset}  🔄  Sync from Server".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[c]{reset}  🧹  Clear Screen".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[0]{reset}  🚪  Exit".format(bold=C.BOLD, reset=C.RESET))
    print("  {yellow}{line}{reset}".format(yellow=C.YELLOW, line="─" * 48, reset=C.RESET))


# ── [1] System Status ───────────────────────────────────────
def cmd_status():
    print("\n  {cyan}{bold}═══ SYSTEM STATUS ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    health = api_request("GET", "/system/health")
    if not health.get("success"):
        print("  {red}✗ Backend unreachable: {err}{reset}".format(red=C.RED, err=health.get("error", ""), reset=C.RESET))
        return

    d = health["data"]
    items = [
        ("Device ID",    d.get("device_id", "—")),
        ("Version",      d.get("version", "—")),
        ("MQTT",         d.get("mqtt_connected")),
        ("Sensor",       d.get("sensor_connected")),
        ("Total Users",  d.get("total_users", "—")),
        ("Total Prints", d.get("total_fingerprints", "—")),
        ("Active Model", d.get("active_model")),
    ]
    for label, val in items:
        if isinstance(val, bool):
            vs = "{green}● Yes{reset}".format(green=C.GREEN, reset=C.RESET) if val else "{red}● No{reset}".format(red=C.RED, reset=C.RESET)
        elif val is None:
            vs = "{dim}(none){reset}".format(dim=C.DIM, reset=C.RESET)
        else:
            vs = str(val)
        print("  {:<17} {}".format(label, vs))

    # Config
    cfg = api_request("GET", "/system/config")
    if cfg.get("success"):
        cd = cfg["data"]
        print()
        print("  {bold}▸ Configuration{reset}".format(bold=C.BOLD, reset=C.RESET))
        print("  {dim}{line}{reset}".format(dim=C.DIM, line="─" * 40, reset=C.RESET))
        for label, key in [("Backend", "backend"), ("Model Path", "model_path"), ("Threshold", "verify_threshold")]:
            print("  {:<17} {}".format(label, cd.get(key, "—")))
    print()


# ── [2] List Users ──────────────────────────────────────────
def cmd_list_users():
    print("\n  {cyan}{bold}═══ USER LIST ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))
    res = api_request("GET", "/users?limit=50")
    if not res.get("success"):
        print("  {red}✗ Error: {err}{reset}".format(red=C.RED, err=res.get("error", ""), reset=C.RESET))
        return

    users = res.get("data", {}).get("users", [])
    if not users:
        print("  {dim}No users found.{reset}".format(dim=C.DIM, reset=C.RESET))
        return

    print("  {dim}{hdr}{reset}".format(dim=C.DIM, reset=C.RESET,
        hdr="{:<6} {:<20} {:<12} {:<10} {}".format("#", "Name", "Emp ID", "Status", "Fingers")))
    print("  {dim}{line}{reset}".format(dim=C.DIM, line="─" * 65, reset=C.RESET))

    for i, u in enumerate(users, 1):
        fingers = len(u.get("enrolled_fingers", []))
        active = u.get("is_active", True)
        st = "{green}active{reset}".format(green=C.GREEN, reset=C.RESET) if active else "{red}off{reset}".format(red=C.RED, reset=C.RESET)
        fs = "{mag}{n}{reset}".format(mag=C.MAGENTA, n=fingers, reset=C.RESET) if fingers else "{dim}0{reset}".format(dim=C.DIM, reset=C.RESET)
        print("  {bold}[{i}]{reset}  {name:<20} {eid:<12} {st:<22} {fs}".format(
            bold=C.BOLD, reset=C.RESET, i=i,
            name=u.get("full_name", "")[:18], eid=u.get("employee_id", "")[:10],
            st=st, fs=fs))
    print()


# ── [3] Register User ──────────────────────────────────────
def cmd_register():
    print("\n  {cyan}{bold}═══ REGISTER NEW USER ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))
    emp_id = input("  {yellow}▸ Employee ID:{reset} ".format(yellow=C.YELLOW, reset=C.RESET)).strip()
    name = input("  {yellow}▸ Full Name:{reset} ".format(yellow=C.YELLOW, reset=C.RESET)).strip()
    dept = input("  {yellow}▸ Department (optional):{reset} ".format(yellow=C.YELLOW, reset=C.RESET)).strip()

    if not emp_id or not name:
        print("  {red}✗ Employee ID and Name are required.{reset}".format(red=C.RED, reset=C.RESET))
        return

    payload = {"employee_id": emp_id, "full_name": name}
    if dept:
        payload["department"] = dept

    res = api_request("POST", "/users", payload)
    if not res.get("success"):
        print("  {red}✗ Failed: {d}{reset}".format(red=C.RED, d=res.get("detail", res.get("error", str(res))), reset=C.RESET))
        return

    user = res["data"]
    print("\n  {green}✓ User created!{reset}".format(green=C.GREEN, reset=C.RESET))
    print("    ID   : {bold}{uid}{reset}".format(bold=C.BOLD, uid=user["id"], reset=C.RESET))
    print("    Name : {}".format(user.get("full_name")))
    print()


# ── [4] Enroll Fingerprint ──────────────────────────────────
def cmd_enroll():
    print("\n  {cyan}{bold}═══ ENROLL FINGERPRINT ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    res = api_request("GET", "/users?limit=50")
    users = res.get("data", {}).get("users", []) if res.get("success") else []

    if users:
        print("  {bold}▸ Select User:{reset}".format(bold=C.BOLD, reset=C.RESET))
        for i, u in enumerate(users, 1):
            n = len(u.get("enrolled_fingers", []))
            print("    {bold}[{i}]{reset} {name} ({eid}) — {n} finger(s)".format(
                bold=C.BOLD, reset=C.RESET, i=i,
                name=u.get("full_name", ""), eid=u.get("employee_id", ""), n=n))
        try:
            idx = int(input("\n  {yellow}▸ User [1-{n}]: {reset}".format(
                yellow=C.YELLOW, n=len(users), reset=C.RESET)).strip()) - 1
            if idx < 0 or idx >= len(users):
                print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET)); return
            user_id = users[idx]["id"]
        except (ValueError, EOFError):
            print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET)); return
    else:
        user_id = input("  {yellow}▸ User ID: {reset}".format(yellow=C.YELLOW, reset=C.RESET)).strip()

    if not user_id:
        return

    fingers = ["right_index", "right_middle", "right_thumb", "left_index", "left_middle", "left_thumb"]
    print("\n  {bold}▸ Select Finger:{reset}".format(bold=C.BOLD, reset=C.RESET))
    for i, f in enumerate(fingers, 1):
        print("    {bold}[{i}]{reset} {f}".format(bold=C.BOLD, reset=C.RESET, i=i, f=f))
    try:
        fi = int(input("  {yellow}▸ Finger [1-6]: {reset}".format(yellow=C.YELLOW, reset=C.RESET)).strip()) - 1
        if fi < 0 or fi >= len(fingers): fi = 0
    except (ValueError, EOFError):
        fi = 0

    print("\n  {yellow}⏳ Place your finger on the sensor... (3 samples){reset}".format(yellow=C.YELLOW, reset=C.RESET))

    res = api_request("POST", "/users/{}/enroll-finger".format(user_id),
                      {"finger": fingers[fi], "num_samples": 3}, timeout=30)
    if res.get("success"):
        d = res["data"]
        print("  {green}✓ Enrolled!{reset}  Quality: {:.1f}  Templates: {}".format(
            d.get("quality_score", 0), d.get("template_count", "?"),
            green=C.GREEN, reset=C.RESET))
    else:
        print("  {red}✗ Failed: {d}{reset}".format(red=C.RED,
            d=res.get("detail", res.get("error", str(res))), reset=C.RESET))
    print()


# ── [5] Verify 1:1 ──────────────────────────────────────────
def cmd_verify():
    print("\n  {cyan}{bold}═══ 1:1 VERIFICATION ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    res = api_request("GET", "/users?limit=50")
    users = res.get("data", {}).get("users", []) if res.get("success") else []
    enrolled = [u for u in users if len(u.get("enrolled_fingers", [])) > 0]

    if enrolled:
        print("  {bold}▸ Users with fingerprints:{reset}".format(bold=C.BOLD, reset=C.RESET))
        for i, u in enumerate(enrolled, 1):
            flist = ", ".join([f.get("finger", "?") for f in u.get("enrolled_fingers", [])])
            print("    {bold}[{i}]{reset} {name} ({eid}) — {f}".format(
                bold=C.BOLD, reset=C.RESET, i=i,
                name=u.get("full_name", ""), eid=u.get("employee_id", ""), f=flist))
        try:
            idx = int(input("\n  {yellow}▸ User [1-{n}]: {reset}".format(
                yellow=C.YELLOW, n=len(enrolled), reset=C.RESET)).strip()) - 1
            if idx < 0 or idx >= len(enrolled):
                print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET)); return
            user_id = enrolled[idx]["id"]
        except (ValueError, EOFError):
            print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET)); return
    else:
        user_id = input("  {yellow}▸ User ID: {reset}".format(yellow=C.YELLOW, reset=C.RESET)).strip()

    if not user_id:
        return

    print("\n  {yellow}⏳ Place your finger on the sensor...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
    res = api_request("POST", "/verify", {"user_id": user_id}, timeout=20)

    if not res.get("success"):
        print("  {red}✗ Error: {d}{reset}".format(red=C.RED,
            d=res.get("detail", res.get("error", "")), reset=C.RESET)); return

    d = res["data"]
    print()
    if d.get("matched"):
        print("  {green}{bold}┌─────────────────────────────────┐{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}│     ✅  MATCH — VERIFIED        │{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}└─────────────────────────────────┘{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
    else:
        print("  {red}{bold}┌─────────────────────────────────┐{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}│     ❌  REJECTED — NO MATCH     │{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}└─────────────────────────────────┘{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
    print("    Score: {bold}{:.4f}{reset}  Threshold: {:.2f}  Latency: {:.0f}ms".format(
        d.get("score", 0), d.get("threshold", 0), d.get("latency_ms", 0),
        bold=C.BOLD, reset=C.RESET))
    print()


# ── [6] Identify 1:N ────────────────────────────────────────
def cmd_identify():
    print("\n  {cyan}{bold}═══ 1:N IDENTIFICATION ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))
    print("  {yellow}⏳ Place your finger on the sensor...{reset}".format(yellow=C.YELLOW, reset=C.RESET))

    res = api_request("POST", "/identify", {"top_k": 5}, timeout=20)
    if not res.get("success"):
        print("  {red}✗ Error: {d}{reset}".format(red=C.RED,
            d=res.get("detail", res.get("error", "")), reset=C.RESET)); return

    d = res["data"]
    candidates = d.get("candidates", [])
    print()
    if d.get("matched") and candidates:
        best = candidates[0]
        print("  {green}{bold}┌─────────────────────────────────┐{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}│     ✅  IDENTIFIED              │{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}└─────────────────────────────────┘{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("    User  : {bold}{uid}{reset}".format(bold=C.BOLD, uid=best.get("user_id", "?"), reset=C.RESET))
        print("    Score : {bold}{:.4f}{reset}".format(best.get("score", 0), bold=C.BOLD, reset=C.RESET))
        if len(candidates) > 1:
            print("\n  {dim}Other candidates:{reset}".format(dim=C.DIM, reset=C.RESET))
            for c in candidates[1:]:
                print("    {dim}• {uid} ({s:.4f}){reset}".format(
                    dim=C.DIM, uid=c.get("user_id", "?"), s=c.get("score", 0), reset=C.RESET))
    else:
        print("  {red}{bold}┌─────────────────────────────────┐{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}│     ❌  NO MATCH FOUND          │{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}└─────────────────────────────────┘{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
    print()


# ── [7] Model Info ──────────────────────────────────────────
def cmd_models():
    print("\n  {cyan}{bold}═══ MODEL INFO ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))
    res = api_request("GET", "/models")
    if not res.get("success"):
        print("  {red}✗ Error: {err}{reset}".format(red=C.RED, err=res.get("error", ""), reset=C.RESET))
        return

    data = res.get("data", {})
    models = data.get("models", [])
    active = data.get("active_model")

    if not models:
        print("  {dim}No models found. They will be downloaded via MQTT.{reset}".format(dim=C.DIM, reset=C.RESET))
        return

    print("  {dim}{hdr}{reset}".format(dim=C.DIM, reset=C.RESET,
        hdr="{:<30} {:<10} {}".format("Name", "Size", "Status")))
    print("  {dim}{line}{reset}".format(dim=C.DIM, line="─" * 55, reset=C.RESET))
    for m in models:
        n = m.get("name", "?")
        s = "{:.1f} MB".format(m.get("size_mb", 0))
        is_active = (n == active)
        st = "{green}● ACTIVE{reset}".format(green=C.GREEN, reset=C.RESET) if is_active else "{dim}idle{reset}".format(dim=C.DIM, reset=C.RESET)
        print("  {:<30} {:<10} {}".format(n, s, st))
    print()


# ── [8] MQTT Event Log ──────────────────────────────────────
def cmd_mqtt_log():
    print("\n  {cyan}{bold}═══ MQTT EVENT LOG ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    if not HAS_MQTT:
        print("  {red}✗ paho-mqtt not installed. Run: pip install paho-mqtt{reset}".format(red=C.RED, reset=C.RESET))
        return

    if not _mqtt_connected:
        print("  {red}✗ Not connected to MQTT broker.{reset}".format(red=C.RED, reset=C.RESET))
        print("  {dim}Use [r] to reconnect.{reset}".format(dim=C.DIM, reset=C.RESET))

    with _lock:
        logs = list(_message_log)

    if not logs:
        print("  {dim}No events captured yet. Events will appear as MQTT messages arrive.{reset}".format(dim=C.DIM, reset=C.RESET))
        print("  {dim}Subscribed topics:{reset}".format(dim=C.DIM, reset=C.RESET))
        print("    {dim}→ task/{did}/+{reset}".format(dim=C.DIM, did=DEVICE_ID, reset=C.RESET))
        print("    {dim}→ task/{did}/model/update{reset}".format(dim=C.DIM, did=DEVICE_ID, reset=C.RESET))
        print("    {dim}→ worker/{did}/heartbeat{reset}".format(dim=C.DIM, did=DEVICE_ID, reset=C.RESET))
        print("    {dim}→ result/+{reset}".format(dim=C.DIM, did=DEVICE_ID, reset=C.RESET))
        return

    type_colors = {
        "heartbeat": C.DIM,
        "task": C.CYAN,
        "model": C.MAGENTA,
        "result": C.GREEN,
        "system": C.BLUE,
        "error": C.RED,
    }

    print("  {dim}{hdr}{reset}".format(dim=C.DIM, reset=C.RESET,
        hdr="{:<10} {:<12} {:<35} {}".format("Time", "Type", "Topic", "Detail")))
    print("  {dim}{line}{reset}".format(dim=C.DIM, line="─" * 80, reset=C.RESET))

    for ts, event_type, topic, detail in logs[-20:]:
        t = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        color = type_colors.get(event_type, C.WHITE)
        # Truncate topic for display
        topic_short = topic[-33:] if len(topic) > 35 else topic
        print("  {t:<10} {color}{et:<12}{reset} {topic:<35} {detail}".format(
            t=t, color=color, et=event_type, reset=C.RESET,
            topic=topic_short, detail=detail[:30]))

    print("\n  {dim}({n}/{total} events shown){reset}".format(dim=C.DIM, n=min(20, len(logs)), total=len(logs), reset=C.RESET))
    print()


# ── [9] MQTT Statistics ─────────────────────────────────────
def cmd_mqtt_stats():
    print("\n  {cyan}{bold}═══ MQTT STATISTICS ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    if _mqtt_connected:
        conn_str = "{green}● CONNECTED{reset}".format(green=C.GREEN, reset=C.RESET)
    else:
        conn_str = "{red}● DISCONNECTED{reset}".format(red=C.RED, reset=C.RESET)

    print("  Connection     : {}".format(conn_str))
    print("  Broker         : {}:{}".format(MQTT_HOST, MQTT_PORT))
    print("  Worker ID      : {bold}{did}{reset}".format(bold=C.BOLD, did=DEVICE_ID, reset=C.RESET))
    print()
    print("  {dim}{line}{reset}".format(dim=C.DIM, line="─" * 40, reset=C.RESET))
    print("  Messages In    : {bold}{n}{reset}".format(bold=C.BOLD, n=_mqtt_stats["messages_in"], reset=C.RESET))
    print("  Heartbeats     : {}".format(_mqtt_stats["heartbeats_seen"]))
    print("  Tasks Received : {cyan}{n}{reset}".format(cyan=C.CYAN, n=_mqtt_stats["tasks_received"], reset=C.RESET))
    print("  Model Updates  : {mag}{n}{reset}".format(mag=C.MAGENTA, n=_mqtt_stats["model_updates"], reset=C.RESET))
    print("  Event Log Size : {}/{}".format(len(_message_log), _max_log))

    print()
    print("  {bold}▸ Subscribed Topics:{reset}".format(bold=C.BOLD, reset=C.RESET))
    print("    → task/{did}/embed".format(did=DEVICE_ID))
    print("    → task/{did}/match".format(did=DEVICE_ID))
    print("    → task/{did}/register".format(did=DEVICE_ID))
    print("    → task/{did}/verify".format(did=DEVICE_ID))
    print("    → task/{did}/model/update".format(did=DEVICE_ID))
    print("    → worker/{did}/heartbeat".format(did=DEVICE_ID))
    print("    → result/+")
    print()


# ── [t] Test (image-based) ──────────────────────────────────

def _get_sample_dir():
    """Return the path to the data/sample directory."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "data", "sample")


def _pick_sample_image():
    """List sample images and let the user pick one. Returns (path, base64_str) or (None, None)."""
    sample_dir = _get_sample_dir()
    if not os.path.isdir(sample_dir):
        print("  {red}✗ Sample directory not found: {d}{reset}".format(red=C.RED, d=sample_dir, reset=C.RESET))
        return None, None

    images = sorted(glob.glob(os.path.join(sample_dir, "*.tif")))
    images += sorted(glob.glob(os.path.join(sample_dir, "*.png")))
    images += sorted(glob.glob(os.path.join(sample_dir, "*.bmp")))

    if not images:
        print("  {red}✗ No sample images found in {d}{reset}".format(red=C.RED, d=sample_dir, reset=C.RESET))
        return None, None

    print("\n  {bold}▸ Select a fingerprint image:{reset}".format(bold=C.BOLD, reset=C.RESET))
    for i, path in enumerate(images, 1):
        name = os.path.basename(path)
        size_kb = os.path.getsize(path) / 1024
        print("    {bold}[{i}]{reset} {name}  {dim}({s:.0f} KB){reset}".format(
            bold=C.BOLD, reset=C.RESET, i=i, name=name, dim=C.DIM, s=size_kb))

    try:
        idx = int(input("\n  {yellow}▸ Image [1-{n}]: {reset}".format(
            yellow=C.YELLOW, n=len(images), reset=C.RESET)).strip()) - 1
        if idx < 0 or idx >= len(images):
            print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET))
            return None, None
    except (ValueError, EOFError):
        print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET))
        return None, None

    path = images[idx]
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    print("  {green}✓ Loaded: {name}{reset}".format(
        green=C.GREEN, name=os.path.basename(path), reset=C.RESET))
    return path, b64


def _test_register():
    """Register a new user and enroll with a sample image."""
    print("\n  {cyan}{bold}─── TEST REGISTER ───{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    emp_id = input("  {yellow}▸ Employee ID:{reset} ".format(yellow=C.YELLOW, reset=C.RESET)).strip()
    name = input("  {yellow}▸ Full Name:{reset} ".format(yellow=C.YELLOW, reset=C.RESET)).strip()
    dept = input("  {yellow}▸ Department (optional):{reset} ".format(yellow=C.YELLOW, reset=C.RESET)).strip()

    if not emp_id or not name:
        print("  {red}✗ Employee ID and Name are required.{reset}".format(red=C.RED, reset=C.RESET))
        return

    # Step 1: Pick a sample fingerprint image
    path, b64 = _pick_sample_image()
    if b64 is None:
        return

    # Step 2: Create user
    payload = {"employee_id": emp_id, "full_name": name}
    if dept:
        payload["department"] = dept

    print("\n  {yellow}⏳ Creating user...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
    res = api_request("POST", "/users", payload)
    if not res.get("success"):
        print("  {red}✗ Failed: {d}{reset}".format(red=C.RED, d=res.get("detail", res.get("error", str(res))), reset=C.RESET))
        return

    user = res["data"]
    user_id = user["id"]
    print("  {green}✓ User created (ID: {uid}){reset}".format(green=C.GREEN, uid=user_id, reset=C.RESET))

    # Step 3: Enroll fingerprint (auto: right_index)
    print("  {yellow}⏳ Enrolling fingerprint...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
    enroll_res = api_request("POST", "/users/{}/enroll-finger".format(user_id),
                             {"finger": "right_index", "num_samples": 1, "image_base64": b64}, timeout=30)
    if enroll_res.get("success"):
        d = enroll_res["data"]
        print("  {green}✓ Enrolled!{reset}  Quality: {q:.1f}  Templates: {t}".format(
            green=C.GREEN, reset=C.RESET,
            q=d.get("quality_score", 0), t=d.get("template_count", "?")))
    else:
        print("  {red}✗ Enroll failed: {d}{reset}".format(red=C.RED,
            d=enroll_res.get("detail", enroll_res.get("error", str(enroll_res))), reset=C.RESET))
    print()


def _test_verify():
    """Verify 1:1 with a sample image."""
    print("\n  {cyan}{bold}─── TEST VERIFY 1:1 ───{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    # Pick user
    res = api_request("GET", "/users?limit=50")
    users = res.get("data", {}).get("users", []) if res.get("success") else []
    enrolled = [u for u in users if u.get("fingerprint_count", 0) > 0]

    if not enrolled:
        print("  {red}✗ No users with fingerprints found. Register first.{reset}".format(red=C.RED, reset=C.RESET))
        return

    print("  {bold}▸ Users with fingerprints:{reset}".format(bold=C.BOLD, reset=C.RESET))
    for i, u in enumerate(enrolled, 1):
        print("    {bold}[{i}]{reset} {name} ({eid})".format(
            bold=C.BOLD, reset=C.RESET, i=i,
            name=u.get("full_name", ""), eid=u.get("employee_id", "")))
    try:
        idx = int(input("\n  {yellow}▸ User [1-{n}]: {reset}".format(
            yellow=C.YELLOW, n=len(enrolled), reset=C.RESET)).strip()) - 1
        if idx < 0 or idx >= len(enrolled):
            print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET)); return
        user_id = enrolled[idx]["id"]
    except (ValueError, EOFError):
        print("  {red}✗ Invalid{reset}".format(red=C.RED, reset=C.RESET)); return

    # Pick image
    path, b64 = _pick_sample_image()
    if b64 is None:
        return

    # Verify
    print("\n  {yellow}⏳ Verifying...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
    res = api_request("POST", "/verify", {"user_id": user_id, "image_base64": b64}, timeout=20)

    if not res.get("success"):
        print("  {red}✗ Error: {d}{reset}".format(red=C.RED,
            d=res.get("detail", res.get("error", "")), reset=C.RESET)); return

    d = res["data"]
    print()
    if d.get("matched"):
        print("  {green}{bold}┌─────────────────────────────────┐{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}│     ✅  MATCH — VERIFIED        │{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}└─────────────────────────────────┘{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
    else:
        print("  {red}{bold}┌─────────────────────────────────┐{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}│     ❌  REJECTED — NO MATCH     │{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}└─────────────────────────────────┘{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
    print("    Score: {bold}{s:.4f}{reset}  Threshold: {t:.2f}  Latency: {l:.0f}ms".format(
        s=d.get("score", 0), t=d.get("threshold", 0), l=d.get("latency_ms", 0),
        bold=C.BOLD, reset=C.RESET))
    print()


def _test_identify():
    """Identify 1:N with a sample image."""
    print("\n  {cyan}{bold}─── TEST IDENTIFY 1:N ───{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    # Pick image
    path, b64 = _pick_sample_image()
    if b64 is None:
        return

    # Identify
    print("\n  {yellow}⏳ Identifying...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
    res = api_request("POST", "/identify", {"top_k": 5, "image_base64": b64}, timeout=20)
    if not res.get("success"):
        print("  {red}✗ Error: {d}{reset}".format(red=C.RED,
            d=res.get("detail", res.get("error", "")), reset=C.RESET)); return

    d = res["data"]
    candidates = d.get("candidates", [])
    print()
    if d.get("identified") and candidates:
        best = candidates[0]
        print("  {green}{bold}┌─────────────────────────────────┐{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}│     ✅  IDENTIFIED              │{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("  {green}{bold}└─────────────────────────────────┘{reset}".format(green=C.GREEN, bold=C.BOLD, reset=C.RESET))
        print("    Name  : {bold}{name}{reset}".format(bold=C.BOLD, name=best.get("full_name", "?"), reset=C.RESET))
        print("    EmpID : {bold}{eid}{reset}".format(bold=C.BOLD, eid=best.get("employee_id", "?"), reset=C.RESET))
        print("    Score : {bold}{s:.4f}{reset}  Threshold: {t:.2f}".format(
            s=best.get("score", 0), t=d.get("threshold", 0), bold=C.BOLD, reset=C.RESET))
        if len(candidates) > 1:
            print("\n  {dim}Other candidates:{reset}".format(dim=C.DIM, reset=C.RESET))
            for c in candidates[1:]:
                print("    {dim}• {name} ({eid}) — score {s:.4f}{reset}".format(
                    dim=C.DIM, name=c.get("full_name", "?"),
                    eid=c.get("employee_id", "?"), s=c.get("score", 0), reset=C.RESET))
    else:
        print("  {red}{bold}┌─────────────────────────────────┐{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}│     ❌  NO MATCH FOUND          │{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))
        print("  {red}{bold}└─────────────────────────────────┘{reset}".format(red=C.RED, bold=C.BOLD, reset=C.RESET))

    print("    Latency: {l:.0f}ms".format(l=d.get("latency_ms", 0)))
    print()


def cmd_test():
    """Test menu: register, verify, identify using sample images."""
    print("\n  {cyan}{bold}═══ TEST MODE (image-based) ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))
    print("  {dim}Use sample images from data/sample/ instead of sensor.{reset}\n".format(dim=C.DIM, reset=C.RESET))
    print("  {bold}[1]{reset}  📝  Register (create user + enroll with image)".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[2]{reset}  🔍  Verify 1:1 (compare image against a user)".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[3]{reset}  🔎  Identify 1:N (find who the image belongs to)".format(bold=C.BOLD, reset=C.RESET))
    print("  {bold}[0]{reset}  ↩️   Back".format(bold=C.BOLD, reset=C.RESET))

    try:
        choice = input("\n  {yellow}{bold}▸ Select: {reset}".format(
            yellow=C.YELLOW, bold=C.BOLD, reset=C.RESET)).strip()
    except (KeyboardInterrupt, EOFError):
        return

    if choice == "1":
        _test_register()
    elif choice == "2":
        _test_verify()
    elif choice == "3":
        _test_identify()
    elif choice == "0":
        return
    else:
        print("  {red}Invalid choice{reset}".format(red=C.RED, reset=C.RESET))


# ── [r] Reconnect MQTT ──────────────────────────────────────
def cmd_reconnect():
    print("\n  {cyan}{bold}═══ RECONNECT MQTT ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))

    if not HAS_MQTT:
        print("  {red}✗ paho-mqtt not installed.{reset}".format(red=C.RED, reset=C.RESET))
        return

    if _mqtt_connected:
        print("  {yellow}Disconnecting...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
        mqtt_disconnect()
        time.sleep(1)

    print("  {yellow}Connecting to {h}:{p}...{reset}".format(yellow=C.YELLOW, h=MQTT_HOST, p=MQTT_PORT, reset=C.RESET))
    if mqtt_connect():
        print("  {green}✓ Connected!{reset}".format(green=C.GREEN, reset=C.RESET))
    else:
        print("  {red}✗ Connection failed.{reset}".format(red=C.RED, reset=C.RESET))
    print()


# ── [s] Sync from Server ──────────────────────────────────
def cmd_sync():
    print("\n  {cyan}{bold}═══ SYNC DATA FROM SERVER ═══{reset}\n".format(cyan=C.CYAN, bold=C.BOLD, reset=C.RESET))
    # Fetch from orchestrator
    url = "http://{}:8000/api/sync/full".format(MQTT_HOST)
    print("  {yellow}⏳ Fetching data from Orchestrator: {}{reset}".format(url, yellow=C.YELLOW, reset=C.RESET))

    try:
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print("  {red}✗ Failed to fetch sync data: {}{reset}".format(e, red=C.RED, reset=C.RESET))
        return

    users = payload.get("users", [])
    fingerprints = payload.get("fingerprints", [])
    print("  {green}✓ Received {} users, {} fingerprints.{reset}".format(
        len(users), len(fingerprints), green=C.GREEN, reset=C.RESET))

    print("  {yellow}⏳ Overwriting local database and rebuilding FAISS...{reset}".format(yellow=C.YELLOW, reset=C.RESET))
    res = api_request("POST", "/system/sync", data=payload)
    if res.get("success"):
        data = res.get("data", {})
        print("  {green}✓ Sync completed! Synced {} users, {} templates.{reset}".format(
            data.get("users_synced"), data.get("fingerprints_synced"), green=C.GREEN, reset=C.RESET))
    else:
        print("  {red}✗ Sync failed! {err}{reset}".format(red=C.RED, err=res.get("error"), reset=C.RESET))

# ── Main CLI Loop ───────────────────────────────────────────
def run_cli():
    clear_screen()
    print_banner()

    # Quick backend check
    if api_request("GET", "/system/health").get("success"):
        print("  {green}✓ Backend is running!{reset}".format(green=C.GREEN, reset=C.RESET))
    else:
        print("  {red}✗ Backend not reachable at {url}{reset}".format(red=C.RED, url=BASE_URL, reset=C.RESET))
        print("  {dim}  Start with: uvicorn app.main:app --host 0.0.0.0 --port 8000{reset}".format(dim=C.DIM, reset=C.RESET))

    # Auto-connect MQTT
    if HAS_MQTT:
        print("  {yellow}Connecting to MQTT {h}:{p}...{reset}".format(yellow=C.YELLOW, h=MQTT_HOST, p=MQTT_PORT, reset=C.RESET))
        if mqtt_connect():
            print("  {green}✓ MQTT connected!{reset}".format(green=C.GREEN, reset=C.RESET))
        else:
            print("  {red}✗ MQTT connection failed (use [r] to retry){reset}".format(red=C.RED, reset=C.RESET))
    else:
        print("  {dim}ℹ paho-mqtt not installed — MQTT monitoring disabled{reset}".format(dim=C.DIM, reset=C.RESET))

    print()
    input("  {dim}Press Enter to open main menu...{reset}".format(dim=C.DIM, reset=C.RESET))

    clear_screen()
    print_banner()

    actions = {
        "1": cmd_status,
        "2": cmd_list_users,
        "3": cmd_register,
        "4": cmd_enroll,
        "5": cmd_verify,
        "6": cmd_identify,
        "7": cmd_models,
        "8": cmd_mqtt_log,
        "9": cmd_mqtt_stats,
        "t": cmd_test,
        "r": cmd_reconnect,
        "s": cmd_sync,
        "c": lambda: (clear_screen(), print_banner()),
    }

    while True:
        print_menu()
        try:
            choice = input("\n  {yellow}{bold}▸ Select: {reset}".format(
                yellow=C.YELLOW, bold=C.BOLD, reset=C.RESET)).strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = "0"

        if choice == "0":
            print("\n  {dim}Exiting...{reset}".format(dim=C.DIM, reset=C.RESET))
            break

        action = actions.get(choice)
        if action:
            action()
            input("\n  {dim}Press Enter to continue...{reset}".format(dim=C.DIM, reset=C.RESET))
            clear_screen()
            print_banner()
        else:
            print("  {red}Invalid choice!{reset}".format(red=C.RED, reset=C.RESET))

    mqtt_disconnect()
    print("  {green}👋 CLI stopped.{reset}\n".format(green=C.GREEN, reset=C.RESET))


if __name__ == "__main__":
    try:
        run_cli()
    except KeyboardInterrupt:
        mqtt_disconnect()
        print("\n  Exiting...")
        sys.exit(0)
