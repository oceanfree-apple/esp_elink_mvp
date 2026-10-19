#!/usr/bin/env python3
"""Package a macOS-built, unsigned Release .app; contains no personal config."""
import argparse
import json
import os
import stat
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from ios_package import inspect_ipa, sha256


def package(app: Path, output: Path, commit: str):
    if not app.is_dir() or app.suffix != ".app":
        raise ValueError("Provide the built iphoneos .app directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        # Do not follow directory symlinks. Preserve framework links and modes.
        for directory, directories, files in os.walk(app, followlinks=False):
            paths = [Path(directory) / name for name in files]
            for name in list(directories):
                path = Path(directory) / name
                if path.is_symlink():
                    paths.append(path)
                    directories.remove(name)
            for path in sorted(paths):
                name = "Payload/" + app.name + "/" + path.relative_to(app).as_posix()
                if path.is_symlink():
                    item = ZipInfo(name)
                    item.create_system = 3
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(item, os.readlink(path).encode())
                else:
                    archive.write(path, name)
    try:
        info = inspect_ipa(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    manifest = {"schema_version": 1, "archive": output.name, "sha256": sha256(output),
                "commit": commit, "profile": "release", "signing": "unsigned", **info}
    (output.parent / "build-info.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output.parent / "SHA256SUMS").write_text(manifest["sha256"] + "  " + output.name + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "local"))
    args = parser.parse_args()
    result = package(args.app, args.output, args.commit)
    print("Public unsigned IPA ready:", args.output, "commit:", result["commit"])
