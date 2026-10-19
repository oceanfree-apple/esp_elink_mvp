#!/usr/bin/env python3
"""Read device state or explicitly send a packed frame; optional SSH transport."""
import argparse
import http.client
import json
import socket
import ssl
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--ssh", action="store_true", help="Use an SSH tunnel, still verifying the real TLS certificate")
parser.add_argument("--send", type=Path, help="Upload this 192000-byte frame and refresh the actual screen")
args = parser.parse_args()
s = json.loads((ROOT / ".private/settings.json").read_text())
tls = ssl.create_default_context(cafile=str(ROOT / "mobile/assets/cloud_ca.pem"))
tunnel = None
local_port = None
if args.ssh:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        local_port = probe.getsockname()[1]
    tunnel = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-N", "-L",
                               f"127.0.0.1:{local_port}:127.0.0.1:443", "tencent"], stdout=subprocess.DEVNULL)
    for _ in range(50):
        if tunnel.poll() is not None:
            raise RuntimeError("SSH tunnel failed")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=.2):
                break
        except OSError:
            time.sleep(.1)


class Connection(http.client.HTTPSConnection):
    def connect(self):
        if local_port is None:
            super().connect()
        else:
            raw = socket.create_connection(("127.0.0.1", local_port), timeout=10)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def request(method, path, body=None):
    c = Connection(s["ip"], context=tls, timeout=15)
    try:
        headers = {"Authorization": "Bearer " + s["app_token"]}
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        elif body is not None:
            headers["Content-Type"] = "application/octet-stream"
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        result = json.loads(r.read())
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}: {result}")
        return result
    finally:
        c.close()


try:
    print(json.dumps({"transport": "ssh-tunnel" if args.ssh else "public", "health": request("GET", "/health"),
                      "device": request("GET", "/v1/device")}, ensure_ascii=False), flush=True)
    if args.send:
        data = args.send.read_bytes()
        if len(data) != 192000:
            raise ValueError("Expected exactly 192000 bytes")
        import hashlib
        import secrets
        uploaded = request("POST", "/v1/images", data)
        assert uploaded["sha256"] == hashlib.sha256(data).hexdigest()
        job = request("POST", "/v1/refresh-jobs", {"image_id": uploaded["image_id"], "idempotency_key": secrets.token_hex(16)})
        last = None
        for _ in range(245):
            result = request("GET", "/v1/refresh-jobs/" + job["id"])
            if result["state"] != last:
                print(json.dumps(result), flush=True)
                last = result["state"]
            if last in ("succeeded", "failed", "uncertain"):
                if last != "succeeded":
                    raise RuntimeError("Screen did not confirm success")
                break
            time.sleep(1)
        else:
            raise TimeoutError("No final screen result")
finally:
    if tunnel:
        tunnel.terminate()
        tunnel.wait(timeout=5)
