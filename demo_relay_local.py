"""
Demo Relay — runs on Neo's laptop during live demo.

Receives POST from demo.html (localhost:8889), queues a @trinity task
directly on the VM via SSH + trinity_queue.py, AND sends the message
to Neo's WhatsApp so it appears on his phone screen.

Start before the meeting:
    python demo_relay_local.py
"""

import http.server
import json
import subprocess
import os

PORT = 8889
VM = "opc@80.225.205.232"
KEY = os.path.expanduser("~") + "\\.ssh\\oracle_cloud_nopass"
CHAT_JID = "919867782241@s.whatsapp.net"
SENDER = "919867782241"


def ssh_cmd(command):
    return subprocess.run(
        ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", VM, command],
        capture_output=True, text=True, timeout=20
    )


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

        # 1. Queue @trinity task on VM (so Trinity picks it up)
        safe_msg = message.replace("'", "'\\''")
        queue_cmd = (
            f"python3 /home/opc/PROJECT/ZION/trinity_queue.py add "
            f"'{CHAT_JID}' '{safe_msg}' '{SENDER}'"
        )
        result = ssh_cmd(queue_cmd)

        if result.returncode != 0:
            self._reply(False, "Queue failed: " + result.stderr)
            print("[RELAY] Queue failed:", result.stderr)
            return

        task_info = result.stdout.strip()
        print(f"[RELAY] Task queued: {task_info}")

        # 2. Also send the message to Neo's WhatsApp so it shows on phone
        send_cmd = (
            f"python3 -c \""
            f"import urllib.request, json; "
            f"data = json.dumps({{'recipient': '{CHAT_JID}', 'message': '{safe_msg}'}}).encode(); "
            f"req = urllib.request.Request('http://localhost:8080/api/send', data=data, "
            f"headers={{'Content-Type': 'application/json; charset=utf-8'}}); "
            f"urllib.request.urlopen(req)"
            f"\""
        )
        ssh_cmd(send_cmd)

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
    print("[RELAY] Hit SEND on demo.html - queues task + shows on WhatsApp")
    server.serve_forever()
