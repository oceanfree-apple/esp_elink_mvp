#!/usr/bin/env python3
"""Deploy this explicitly authorized personal MVP to the configured SSH alias."""
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
s = json.loads((ROOT / ".private/settings.json").read_text())
archive = ROOT / ".private/deploy.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    for path in (ROOT / "server").rglob("*"):
        if path.is_file() and not any(part in ("__pycache__", "data", ".pytest_cache") for part in path.parts):
            tar.add(path, arcname=str(path.relative_to(ROOT)))
    for name in ("server.key", "server.crt", "server.env", "mqtt-users.json"):
        tar.add(ROOT / ".private" / name, arcname="config/" + name)
    tar.add(ROOT / "mobile/assets/cloud_ca.pem", arcname="config/ca.crt")
subprocess.run(["scp", "-q", str(archive), "tencent:/tmp/elink-deploy.tar.gz"], check=True)
script = r'''
set -eu
sudo install -d -m 700 /opt/elink-release
sudo tar xzf /tmp/elink-deploy.tar.gz -C /opt/elink-release
rm /tmp/elink-deploy.tar.gz
id elink >/dev/null 2>&1 || sudo useradd --system --home /var/lib/elink --shell /usr/sbin/nologin elink
sudo install -d -o elink -g elink /var/lib/elink
sudo install -d /opt/elink/server /etc/elink
sudo cp /opt/elink-release/server/app.py /opt/elink/server/
sudo cp /opt/elink-release/server/requirements.txt /opt/elink/server/
sudo python3 -m venv /opt/elink/venv
sudo /opt/elink/venv/bin/pip install -q -r /opt/elink/server/requirements.txt
sudo install -m 600 /opt/elink-release/config/server.env /etc/elink/server.env
sudo install -m 640 -o root -g mosquitto /opt/elink-release/config/server.key /etc/elink/server.key
sudo install -m 644 /opt/elink-release/config/server.crt /etc/elink/server.crt
sudo install -m 644 /opt/elink-release/config/ca.crt /etc/elink/ca.crt
sudo python3 - <<'PY'
import json, subprocess
users=json.load(open('/opt/elink-release/config/mqtt-users.json'))
for i,(user,password) in enumerate(users.items()):
    subprocess.run(['mosquitto_passwd','-b']+(['-c'] if i==0 else [])+['/etc/mosquitto/elink.passwd',user,password],check=True)
PY
sudo chown root:mosquitto /etc/mosquitto/elink.passwd
sudo chmod 640 /etc/mosquitto/elink.passwd
sudo tee /etc/mosquitto/elink.acl >/dev/null <<'EOF'
user elink-api
topic write elink/v1/frame-001/command
topic read elink/v1/frame-001/events
topic read elink/v1/frame-001/presence
user frame-001
topic read elink/v1/frame-001/command
topic write elink/v1/frame-001/events
topic write elink/v1/frame-001/presence
EOF
sudo tee /etc/mosquitto/conf.d/elink.conf >/dev/null <<'EOF'
allow_anonymous false
password_file /etc/mosquitto/elink.passwd
acl_file /etc/mosquitto/elink.acl
listener 1883 127.0.0.1
listener 8883
certfile /etc/elink/server.crt
keyfile /etc/elink/server.key
tls_version tlsv1.2
EOF
sudo tee /etc/systemd/system/elink-api.service >/dev/null <<'EOF'
[Unit]
Description=Elink image relay
After=network-online.target mosquitto.service
Wants=network-online.target
[Service]
User=elink
Group=elink
WorkingDirectory=/opt/elink
EnvironmentFile=/etc/elink/server.env
ExecStart=/opt/elink/venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/elink
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/nginx/sites-available/elink >/dev/null <<'EOF'
server {
    listen 443 ssl;
    server_name _;
    ssl_certificate /etc/elink/server.crt;
    ssl_certificate_key /etc/elink/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 256k;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF
sudo ln -sfn /etc/nginx/sites-available/elink /etc/nginx/sites-enabled/elink
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable elink-api mosquitto nginx >/dev/null
sudo systemctl restart mosquitto elink-api nginx
sudo rm -rf /opt/elink-release
sudo systemctl is-active elink-api mosquitto nginx
'''
subprocess.run(["ssh", "-o", "BatchMode=yes", "tencent", "bash", "-s"], input=script, text=True, check=True)
print("Deployment complete.")
