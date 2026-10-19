#!/usr/bin/env python3
"""Check the exact tracked publication set; never prints matching secret values."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {'.private', '.venv', '.dart_tool', '.gradle', 'build', '__pycache__', 'Pods', 'data'}
FORBIDDEN_SUFFIXES = {'.ipa', '.apk', '.jks', '.p12', '.pfx', '.mobileprovision', '.key', '.csr'}


def check():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    secrets = []
    private = ROOT / '.private/settings.json'
    if private.exists():
        settings = json.loads(private.read_text())
        secrets = [settings.get(key, '').encode() for key in
                   ('app_token', 'device_token', 'mqtt_api_password', 'mqtt_device_password')]
        secrets = [value for value in secrets if value]
    failures = []
    for name in filter(None, tracked):
        relative = Path(name)
        if (any(part in FORBIDDEN_PARTS for part in relative.parts) or
                relative.suffix in FORBIDDEN_SUFFIXES or
                name.startswith('artifacts/') and name != 'artifacts/.gitkeep' or
                relative.name in ('cloud_config.h', 'wifi_credentials.h', 'hosts.yml', '.env')):
            failures.append(name + ': private/generated path')
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----', data):
            failures.append(name + ': private key material')
        if any(value in data for value in secrets):
            failures.append(name + ': known local credential')
    config = json.loads((ROOT / 'mobile/assets/connection.json').read_text())
    if config != {'version': 1, 'base_url': '', 'app_token': ''}:
        failures.append('mobile/assets/connection.json: public bootstrap must be empty')
    if failures:
        raise SystemExit('Publication checks failed:\n' + '\n'.join(failures))
    print('Tracked publication set and empty connection asset verified.')


if __name__ == '__main__':
    check()
