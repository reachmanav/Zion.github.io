"""
Demo Relay — runs on Neo's laptop during live demo.

SEND on demo.html -> relay does:
  1. Deletes live.html from GitHub (fresh start)
  2. Queues @trinity task (trinity_queue.py add) — same as zion.py does
  3. Sends [Trinity] Received on WhatsApp — same as zion.py does

To Zion and Trinity, this is indistinguishable from typing @trinity in WhatsApp.

Start before the meeting:
    python demo_relay_local.py
"""

import http.server
import json
import subprocess
import os
import re
import tempfile

PORT = 8889
VM = "opc@80.225.205.232"
KEY = os.path.expanduser("~") + "\\.ssh\\oracle_cloud_nopass"
CHAT_JID = "919867782241@s.whatsapp.net"
SENDER = "919867782241"
SITE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_SCRIPT = os.path.join(tempfile.gettempdir(), "demo_action.py")


def run_on_vm(script_content):
    with open(TMP_SCRIPT, "w", encoding="utf-8") as f:
        f.write(script_content)
    scp = subprocess.run(
        ["scp", "-i", KEY, "-o", "StrictHostKeyChecking=no",
         TMP_SCRIPT, f"{VM}:/tmp/demo_action.py"],
        capture_output=True, text=True, timeout=15
    )
    if scp.returncode != 0:
        print(f"[RELAY] SCP failed: {scp.stderr}", flush=True)
        return None
    ssh = subprocess.run(
        ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no",
         VM, "python3 /tmp/demo_action.py"],
        capture_output=True, text=True, timeout=30
    )
    print(f"[RELAY] VM: {ssh.stdout.strip()}", flush=True)
    if ssh.returncode != 0:
        print(f"[RELAY] VM err: {ssh.stderr.strip()}", flush=True)
    return ssh


def delete_live_html():
    live_path = os.path.join(SITE_DIR, "live.html")
    if os.path.exists(live_path):
        os.remove(live_path)
        subprocess.run(["git", "add", "-A"], capture_output=True, text=True, cwd=SITE_DIR)
        subprocess.run(
            ["git", "commit", "-m", "Demo: remove live.html for fresh build"],
            capture_output=True, text=True, cwd=SITE_DIR
        )
        r = subprocess.run(
            ["git", "push"], capture_output=True, text=True, cwd=SITE_DIR, timeout=30
        )
        print("[RELAY] live.html deleted from GitHub" if r.returncode == 0
              else f"[RELAY] git push issue: {r.stderr}", flush=True)
    else:
        print("[RELAY] live.html already absent", flush=True)


class RelayHandler(http.server.BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        message = body.get("message", "")

        # Strip @trinity prefix (same as zion.py line 1506)
        task_text = re.sub(r'^@?trinity\s*', '', message, flags=re.IGNORECASE).strip()
        if not task_text:
            task_text = message.strip()

        print(f"\n[RELAY] === NEW REQUEST ===", flush=True)
        print(f"[RELAY] Message: {message}", flush=True)
        print(f"[RELAY] Task: {task_text}", flush=True)

        # Step 0: Kill standby worker so it doesn't steal the task
        print("[RELAY] Step 0: Stopping standby worker...", flush=True)
        try:
            for proc in subprocess.run(
                ["powershell", "-Command",
                 "Get-WmiObject Win32_Process -Filter \"name='python.exe'\" | "
                 "Where-Object { $_.CommandLine -like '*standby_trigger*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                capture_output=True, text=True, timeout=10
            ).stdout.strip().split('\n'):
                if proc.strip():
                    print(f"[RELAY] Killed standby PID {proc.strip()}", flush=True)
        except Exception as e:
            print(f"[RELAY] Standby kill skipped: {e}", flush=True)

        # Step 1: Delete live.html
        print("[RELAY] Step 1: Delete live.html...", flush=True)
        delete_live_html()

        # Step 2+3: Queue task + send [Trinity] Received (lightweight, no zion import)
        print("[RELAY] Step 2: Queue + ack...", flush=True)

        vm_script = f"""
import sys, json, urllib.request
sys.path.insert(0, '/home/opc/PROJECT/ZION')
from trinity_queue import add_task

# 1. Queue the task (same as zion.py handle_trinity_command)
tid = add_task({repr(task_text)}, {repr(CHAT_JID)}, {repr(SENDER)})
print(f"QUEUED: {{tid}}")

# 2. Send [Trinity] Received on WhatsApp (same as zion.py send_reply)
data = json.dumps({{"recipient": {repr(CHAT_JID)}, "message": "[Trinity] Received \\u2713"}}).encode()
req = urllib.request.Request("http://localhost:8080/api/send", data=data,
    headers={{"Content-Type": "application/json; charset=utf-8"}})
urllib.request.urlopen(req)
print("ACK: sent")
"""
        result = run_on_vm(vm_script)

        if result and result.returncode == 0 and "QUEUED:" in result.stdout:
            tid = result.stdout.split("QUEUED:")[1].split()[0].strip()
            print(f"[RELAY] Done! Task {tid} queued + ack sent", flush=True)
            self._reply(True, f"Task {tid} queued")
        else:
            err = (result.stderr if result else "VM unreachable")[:200]
            print(f"[RELAY] FAILED: {err}", flush=True)
            self._reply(False, err)

    def _reply(self, success, msg):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"success": success, "info": msg}).encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"[RELAY] Demo relay on http://localhost:{PORT}", flush=True)
    print("[RELAY] Queue + ack (lightweight, no zion.py import)", flush=True)
    server = http.server.HTTPServer(("127.0.0.1", PORT), RelayHandler)
    server.serve_forever()
