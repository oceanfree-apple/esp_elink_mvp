"""IPA inspection shared by public packaging and private local preparation."""
from __future__ import annotations

import hashlib
import json
import plistlib
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

EMPTY_CONFIG = {"version": 1, "base_url": "", "app_token": ""}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def inspect_ipa(path: Path, *, public=True):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("IPA contains duplicate entries")
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name:
                raise ValueError("IPA contains unsafe entry paths")
        apps = [name for name in names if name.startswith("Payload/") and
                len(PurePosixPath(name).parts) == 3 and
                PurePosixPath(name).parts[1].endswith(".app") and name.endswith("/Info.plist")]
        if len(apps) != 1:
            raise ValueError("Expected exactly one Payload application")
        info = plistlib.loads(archive.read(apps[0]))
        prefix = apps[0].removesuffix("Info.plist")
        candidates = [prefix + "Frameworks/App.framework/flutter_assets/assets/connection.json",
                      prefix + "flutter_assets/assets/connection.json"]
        assets = [name for name in candidates if name in names]
        if len(assets) != 1:
            raise ValueError("Registered Flutter connection asset missing or ambiguous")
        config = json.loads(archive.read(assets[0]))
        if public and config != EMPTY_CONFIG:
            raise ValueError("Public IPA must have empty connection configuration")
        if not isinstance(info.get("CFBundleIdentifier"), str):
            raise ValueError("IPA bundle identifier missing")
        return {"config_path": assets[0], "bundle_id": info["CFBundleIdentifier"],
                "version": str(info.get("CFBundleShortVersionString", "")),
                "build_number": str(info.get("CFBundleVersion", ""))}
