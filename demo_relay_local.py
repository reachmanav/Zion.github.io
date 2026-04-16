"""
Demo Relay — runs on Neo's laptop during live demo.
Receives POST from demo.html (localhost:8889) and sends to WhatsApp via SSH to VM.

Start before the meeting:
    python demo_relay_local.py

Then open https://reachmanav.github.io/Zion.github.io/demo.html
Hit SEND — message goes to WhatsApp.
"""

import http.server
import json
import subprocess
import os
import tempfile

PORT = 8889
VM = "opc@80.225.205.232"
KEY = os.path.expanduser("~") + "\\.ssh\\oracle_cloud_nopass"


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
        recipient = body.get("recipient", "")
        message = body.get("message", "")

        script = (
            "import urllib.request, json\n"
            "data = json.dumps({'recipient': %s, 'message': %s}).encode()\n"
            "req = urllib.request.Request('http://localhost:8080/api/send', data=data,\n"
            "    headers={'Content-Type': 'application/json; charset=utf-8'})\n"
            "resp = urllib.request.urlopen(req)\n"
            "print(resp.read().decode())\n"
        ) % (repr(recipient), repr(message))

        tmp = os.path.join(tempfile.gettempdir(), "demo_send.py")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(script)

        scp = subprocess.run(
            ["scp", "-i", KEY, "-o", "StrictHostKeyChecking=no", tmp, f"{VM}:/tmp/demo_send.py"],
            capture_output=True, text=True, timeout=15
        )
        if scp.returncode != 0:
            self._reply(False, "SCP failed: " + scp.stderr)
            return

        ssh = subprocess.run(
            ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", VM, "python3 /tmp/demo_send.py"],
            capture_output=True, text=True, timeout=15
        )
        if ssh.returncode == 0:
            self._reply(True, "Sent")
            print("[RELAY] Message delivered to WhatsApp")
        else:
            self._reply(False, ssh.stderr or "SSH failed")
            print("[RELAY] Error:", ssh.stderr)

    def _reply(self, success, msg):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"success": success, "error": "" if success else msg}).encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), RelayHandler)
    print(f"[RELAY] Demo relay running on http://localhost:{PORT}")
    print("[RELAY] Open demo.html and hit SEND")
    server.serve_forever()
