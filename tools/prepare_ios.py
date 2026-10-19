#!/usr/bin/env python3
"""Inject private connection data into a verified public IPA BEFORE signing."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from ios_package import inspect_ipa, sha256

ROOT = Path(__file__).resolve().parents[1]


def prepare(source: Path, manifest_path: Path, settings_path: Path, output: Path):
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("signing") != "unsigned" or manifest.get("profile") != "release":
        raise ValueError("Expected an unsigned release build manifest")
    if sha256(source) != manifest.get("sha256"):
        raise ValueError("IPA digest differs from build-info.json")
    info = inspect_ipa(source)
    for key in ("config_path", "bundle_id", "version", "build_number"):
        if info[key] != manifest.get(key):
            raise ValueError("IPA metadata differs from build-info.json")
    settings = json.loads(settings_path.read_text())
    url = settings.get("base_url") or ("https://" + settings.get("ip", ""))
    token = settings.get("app_token", "")
    uri = urlsplit(url)
    if (uri.scheme != "https" or not uri.hostname or uri.username or uri.password or
            uri.query or uri.fragment or uri.path not in ("", "/") or
            not isinstance(token, str) or not token or re.search(r"\s", token)):
        raise ValueError("Private connection settings are invalid")
    # Restrict all configured outputs to the ignored private directory.
    private_root = (ROOT / ".private").resolve()
    output = output.resolve()
    if private_root not in output.parents:
        raise ValueError("Configured IPA output must be inside .private/")
    if source.resolve() == output:
        raise ValueError("Original public IPA must be preserved")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    config = json.dumps({"version": 1, "base_url": url, "app_token": token}, separators=(",", ":")).encode()
    handle, temporary = tempfile.mkstemp(prefix=".prepare-", suffix=".ipa", dir=output.parent)
    os.close(handle)
    try:
        with ZipFile(source) as original, ZipFile(temporary, "w") as target:
            for member in original.infolist():
                entry = copy.copy(member)
                if member.filename == info["config_path"]:
                    target.writestr(entry, config)
                else:
                    with original.open(member) as incoming, target.open(entry, "w") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        result = inspect_ipa(Path(temporary), public=False)
        if result != info:
            raise ValueError("Prepared IPA application metadata changed")
        os.replace(temporary, output)
        output.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)
    metadata = {"schema_version": 1, "source_sha256": manifest["sha256"], "sha256": sha256(output),
                "commit": manifest["commit"], "bundle_id": info["bundle_id"],
                "signing": "not-yet-signed", "private_configuration": True}
    sidecar = output.with_suffix(".json")
    fd = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps(metadata, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "artifacts/ios/mojian-unsigned.ipa")
    parser.add_argument("--build-info", type=Path, default=ROOT / "artifacts/ios/build-info.json")
    parser.add_argument("--settings", type=Path, default=ROOT / ".private/settings.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".private/ios/mojian-configured.ipa")
    args = parser.parse_args()
    try:
        prepare(args.input, args.build_info, args.settings, args.output)
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit("IPA preparation failed: " + str(error))
    print("Configured personal IPA ready for local signing:", args.output)
    print("No Apple credentials were needed. Open this file in iloader after connecting the iPhone.")
