#!/usr/bin/env python3
"""Bundle the verified factory images. Firmware contains private device config."""
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
build = root / "firmware/build"
out = root / "artifacts/firmware"
out.mkdir(mode=0o700, parents=True, exist_ok=True)
args = json.loads((build / "flasher_args.json").read_text())
manifest = {}
lines = ["--flash_mode dio", "--flash_freq 80m", "--flash_size 32MB"]
for offset, source in args["flash_files"].items():
    target = out / Path(source).name
    shutil.copyfile(build / source, target)
    target.chmod(0o600)
    lines.append(offset + " " + target.name)
    manifest[target.name] = {"offset": offset, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
(out / "flash_args").write_text("\n".join(lines) + "\n")
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
archive = root / "artifacts/esp-elink-firmware.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    tar.add(out, arcname="firmware")
archive.chmod(0o600)
apk = root / "artifacts/mojian-android.apk"
if apk.exists():
    (root / "artifacts/SHA256SUMS").write_text(hashlib.sha256(apk.read_bytes()).hexdigest() + "  mojian-android.apk\n" + hashlib.sha256(archive.read_bytes()).hexdigest() + "  esp-elink-firmware.tar.gz\n")
print("Private firmware bundle ready.")
