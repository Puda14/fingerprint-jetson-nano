#!/usr/bin/env python3
"""
Interactive Command Line Interface (CLI) for Fingerprint Jetson Nano.
Works entirely over SSH without requiring any GUI or PyQt5.
Ensure the Backend (uvicorn) is running before using this tool.
"""

import argparse
import base64
import json
import socket
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000/api/v1"

def api_request(method, endpoint, data=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    req_data = None
    if data:
        req_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except urllib.error.HTTPError as e:
        res_body = e.read().decode("utf-8")
        try:
            return json.loads(res_body)
        except:
            return {"success": False, "error": f"HTTP {e.code}: {res_body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def print_header(title):
    print(f"\n{'='*50}")
    print(f" {title.upper()} ".center(50, '='))
    print(f"{'='*50}\n")

# --- Commands ---

def cmd_status():
    print_header("System Status")
    res = api_request("GET", "/system/health")
    if not res.get("success"):
        print(f"[!] Cannot connect to backend: {res.get('error')}")
        return

    data = res["data"]
    print(f"API Version : {data.get('version')}")
    print(f"Device ID   : {data.get('device_id')}")
    print(f"MQTT Status : {data.get('mqtt_connected')}")
    print(f"Sensor      : {data.get('sensor_connected')}")
    print(f"Total Users : {data.get('total_users')}")
    print(f"Total Prints: {data.get('total_fingerprints')}")
    print(f"Sys Uptime  : {data.get('uptime_seconds', 0):.1f}s")

    cfg = api_request("GET", "/system/config")
    if cfg.get("success"):
        print(f"\nConfig Backend : {cfg['data'].get('backend')}")
        print(f"Active Model   : {cfg['data'].get('model_path')}")

def cmd_list_users():
    print_header("User List")
    res = api_request("GET", "/users?limit=50")
    if not res.get("success"):
        print(f"[!] Error: {res.get('error')}")
        return

    users = res["data"]["users"]
    if not users:
        print("No users found in the database.")
        return

    print(f"{'ID':<38} | {'Emp_ID':<10} | {'Name':<20} | Fingers")
    print("-" * 85)
    for u in users:
        fingers = len(u.get("enrolled_fingers", []))
        print(f"{u['id']:<38} | {u.get('employee_id',''):<10} | {u.get('full_name',''):<20} | {fingers}")

def cmd_register():
    print_header("Register New User")
    emp_id = input("Enter Employee ID (e.g. EMP001): ").strip()
    name = input("Enter Full Name: ").strip()

    if not emp_id or not name:
        print("[!] Employee ID and Name are required.")
        return

    # 1. Create User
    print(f"\n[*] Creating user {name}...")
    res = api_request("POST", "/users", {"employee_id": emp_id, "full_name": name})
    if not res.get("success"):
        print(f"[!] Error creating user: {res.get('error', res)}")
        return

    user_id = res['data']['id']
    print(f"[+] User created successfully. ID: {user_id}")

    # 2. Enroll Finger
    ans = input("\nDo you want to enroll a fingerprint now? (y/n): ").strip().lower()
    if ans == 'y':
        print("\n[!] Please place your finger on the sensor...")
        # Since this involves multiple captures, we just call the enroll endpoint and let the backend do it.
        # The backend assumes 3 samples by default.
        print("[*] Waiting for 3 fingerprint samples... (Keep scanning)")

        # We need to increase timeout for enrollment which takes time
        try:
            enroll_res = api_request("POST", f"/users/{user_id}/enroll-finger", {
                "finger": "right_index",
                "num_samples": 3
            })
            if enroll_res.get("success"):
                print(f"[+] Enrollment successful! Quality: {enroll_res['data']['quality_score']:.1f}")
            else:
                print(f"[-] Enrollment failed: {enroll_res.get('error') or enroll_res.get('detail')}")
        except Exception as e:
            print(f"[!] Request timed out or failed: {e}")

def cmd_verify():
    print_header("1:1 Verification")
    user_id = input("Enter User ID to verify against: ").strip()
    if not user_id:
        return

    print("\n[*] Please place your finger on the sensor...")
    res = api_request("POST", "/verify", {"user_id": user_id})

    if not res.get("success"):
        print(f"[-] Verification error: {res.get('error') or res.get('detail')}")
        return

    data = res["data"]
    if data["matched"]:
        print(f"[+] MATCHED! Score: {data['score']:.4f} (Threshold: {data['threshold']:.2f})")
    else:
        print(f"[-] REJECTED. Score: {data['score']:.4f} (Threshold: {data['threshold']:.2f})")

def cmd_identify():
    print_header("1:N Identification")
    print("[*] Please place your finger on the sensor...")

    res = api_request("POST", "/identify", {"top_k": 5})
    if not res.get("success"):
        print(f"[-] Identification error: {res.get('error') or res.get('detail')}")
        return

    data = res["data"]
    if data["matched"] and data["candidates"]:
        best = data["candidates"][0]
        print(f"\n[+] IDENTIFIED!")
        print(f"    User ID: {best['user_id']}")
        print(f"    Score  : {best['score']:.4f}")
    else:
        print("\n[-] NO MATCH FOUND in the database.")

def main_menu():
    while True:
        print("\n" + "="*40)
        print(" FINGERPRINT CLI ".center(40, "="))
        print("="*40)
        print(" 1. View System Status")
        print(" 2. List Users")
        print(" 3. Register New User & Fingerprint")
        print(" 4. Verify 1:1 (Check specific user)")
        print(" 5. Identify 1:N (Search all users)")
        print(" 0. Exit")
        print("="*40)

        choice = input("Select an option: ").strip()

        if choice == '1':
            cmd_status()
        elif choice == '2':
            cmd_list_users()
        elif choice == '3':
            cmd_register()
        elif choice == '4':
            cmd_verify()
        elif choice == '5':
            cmd_identify()
        elif choice == '0':
            print("Exiting CLI...")
            sys.exit(0)
        else:
            print("[!] Invalid option. Try again.")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nExiting CLI...")
        sys.exit(0)
