"""
Demo Relay — runs on Neo's laptop during live demo.

Hit SEND on demo.html -> relay queues a @trinity task on VM
AND sends the message to Neo's WhatsApp (shows on phone screen).

Zion sees the queued task -> routes to Trinity -> Lobo -> build -> deploy.

Start before the meeting:
    python demo_relay_local.py
"""

import http.server
import json
import subprocess
import os
import tempfile

PORT = 8889
VM = "opc@80.225.205.232"
KEY = os.path.expanduser("~") + "\\.ssh\\oracle_cloud_nopass"
CHAT_JID = "919867782241@s.whatsapp.net"
SENDER = "919867782241"


def ssh_run(command):
    return subprocess.run(
        ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", VM, command],
        capture_output=True, text=True, timeout=20
    )


def scp_and_run(script_content):
    tmp = os.path.join(tempfile.gettempdir(), "demo_send.py")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(script_content)
    subprocess.run(
        ["scp", "-i", KEY, "-o", "StrictHostKeyChecking=no", tmp, f"{VM}:/tmp/demo_send.py"],
        capture_output=True, text=True, timeout=15
    )
    return ssh_run("python3 /tmp/demo_send.py")


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

        # 1. Queue @trinity task directly in VM SQLite
        safe_msg = message.replace("'", "'\\''")
        queue_result = ssh_run(
            f"python3 /home/opc/PROJECT/ZION/trinity_queue.py add "
            f"'{CHAT_JID}' '{safe_msg}' '{SENDER}'"
        )
        if queue_result.returncode != 0:
            self._reply(False, "Queue failed: " + queue_result.stderr)
            print("[RELAY] Queue FAILED:", queue_result.stderr)
            return

        task_info = queue_result.stdout.strip()
        print(f"[RELAY] Task queued: {task_info}")

        # 2. Send message to Neo's WhatsApp (shows on phone for audience)
        send_script = (
            "import urllib.request, json\n"
            f"data = json.dumps({{'recipient': {repr(CHAT_JID)}, 'message': {repr(message)}}}).encode()\n"
            "req = urllib.request.Request('http://localhost:8080/api/send', data=data,\n"
            "    headers={'Content-Type': 'application/json; charset=utf-8'})\n"
            "resp = urllib.request.urlopen(req)\n"
            "print(resp.read().decode())\n"
        )
        wa_result = scp_and_run(send_script)
        if wa_result.returncode == 0:
            print("[RELAY] WhatsApp message sent")
        else:
            print("[RELAY] WhatsApp send failed (task still queued):", wa_result.stderr)

        self._reply(True, task_info)

    def _reply(self, success, msg):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"success": success, "info": msg}).encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), RelayHandler)
    print(f"[RELAY] Demo relay on http://localhost:{PORT}")
    print(f"[RELAY] Queues @trinity task + sends to WhatsApp")
    print(f"[RELAY] Open demo.html -> SEND -> watch phone + laptop")
    server.serve_forever()
