#!/usr/bin/env python3
"""Create private local config and project CA. Never prints tokens or private keys."""
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".private"
PRIVATE.mkdir(mode=0o700, exist_ok=True)


def private_write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


path = PRIVATE / "settings.json"
if path.exists():
    s = json.loads(path.read_text())
else:
    host = subprocess.check_output(["ssh", "-G", "tencent"], stderr=subprocess.DEVNULL, text=True)
    ip = next(line.split()[1] for line in host.splitlines() if line.startswith("hostname "))
    s = {"ip": ip, "device_id": "frame-001", "app_token": secrets.token_urlsafe(32),
         "device_token": secrets.token_urlsafe(32), "mqtt_api_password": secrets.token_urlsafe(32),
         "mqtt_device_password": secrets.token_urlsafe(32)}
    private_write(path, json.dumps(s, indent=2) + "\n")

ca_key, ca_cert = PRIVATE / "ca.key", ROOT / "mobile/assets/cloud_ca.pem"
tls_key, tls_cert = PRIVATE / "server.key", PRIVATE / "server.crt"
if not ca_key.exists():
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(ca_key),
        "-out", str(ca_cert), "-days", "3650", "-subj", "/CN=Elink Personal CA",
        "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    ca_key.chmod(0o600)
if not tls_cert.exists():
    ext = PRIVATE / "server.ext"
    private_write(ext, f"subjectAltName=IP:{s['ip']}\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
    run("openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(tls_key),
        "-out", str(PRIVATE / "server.csr"), "-subj", f"/CN={s['ip']}")
    run("openssl", "x509", "-req", "-in", str(PRIVATE / "server.csr"), "-CA", str(ca_cert),
        "-CAkey", str(ca_key), "-CAcreateserial", "-CAserial", str(PRIVATE / "ca.srl"),
        "-out", str(tls_cert), "-days", "825", "-extfile", str(ext))
    tls_key.chmod(0o600)
(ROOT / "firmware/main/cloud_ca.pem").write_bytes(ca_cert.read_bytes())
header = "#pragma once\n" + "".join(f"#define {key} {json.dumps(value)}\n" for key, value in {
    "CLOUD_BASE_URL": f"https://{s['ip']}", "CLOUD_MQTT_URI": f"mqtts://{s['ip']}:8883",
    "CLOUD_TLS_NAME": s["ip"],
    "CLOUD_DEVICE_ID": s["device_id"], "CLOUD_DEVICE_TOKEN": s["device_token"],
    "CLOUD_MQTT_PASSWORD": s["mqtt_device_password"]}.items())
private_write(ROOT / "firmware/main/cloud_config.h", header)
private_write(PRIVATE / "mobile.json", json.dumps({"ELINK_URL": f"https://{s['ip']}", "ELINK_TOKEN": s["app_token"]}))
env = {"ELINK_PUBLIC_URL": f"https://{s['ip']}", "ELINK_DEVICE_ID": s["device_id"],
       "ELINK_DATA": "/var/lib/elink", "ELINK_APP_TOKEN": s["app_token"],
       "ELINK_DEVICE_TOKEN": s["device_token"], "ELINK_MQTT_USER": "elink-api",
       "ELINK_MQTT_PASSWORD": s["mqtt_api_password"]}
private_write(PRIVATE / "server.env", "".join(f"{k}={v}\n" for k, v in env.items()))
private_write(PRIVATE / "mqtt-users.json", json.dumps({"elink-api": s["mqtt_api_password"], s["device_id"]: s["mqtt_device_password"]}))
print("Private config and TLS files ready; no secrets printed.")
