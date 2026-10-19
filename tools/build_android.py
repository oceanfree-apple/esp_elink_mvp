#!/usr/bin/env python3
"""Build a privately configured APK signed with a persistent personal key."""
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
private = ROOT / ".private"
props = private / "android-signing.properties"
if not props.exists():
    password = secrets.token_urlsafe(32)
    keystore = private / "android-release.jks"
    env = {**os.environ, "ELINK_SIGN_PASS": password}
    subprocess.run(["keytool", "-genkeypair", "-keystore", str(keystore), "-alias", "elink", "-keyalg", "RSA",
                    "-keysize", "2048", "-validity", "10000", "-dname", "CN=Elink Personal",
                    "-storepass:env", "ELINK_SIGN_PASS", "-keypass:env", "ELINK_SIGN_PASS", "-noprompt"],
                   env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    keystore.chmod(0o600)
    fd = os.open(props, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"storeFile={keystore}\nstorePassword={password}\nkeyPassword={password}\n")
flutter = shutil.which("flutter") or str(Path.home() / "software/flutter/bin/flutter")
subprocess.run([flutter, "build", "apk", "--release", "--target-platform", "android-arm,android-arm64",
                "--dart-define-from-file=../.private/mobile.json"], cwd=ROOT / "mobile", check=True)
target = ROOT / "artifacts/mojian-android.apk"
shutil.copyfile(ROOT / "mobile/build/app/outputs/flutter-apk/app-release.apk", target)
target.chmod(0o600)
print("Private signed APK:", target)
