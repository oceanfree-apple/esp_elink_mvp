#!/usr/bin/env python3
"""Download a successful iOS workflow artifact using the user's gh login."""
import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ios_package import inspect_ipa, sha256

ROOT = Path(__file__).resolve().parents[1]


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="oceanfree-apple/esp_elink_mvp")
    parser.add_argument("--run", type=int)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    subprocess.run(["gh", "auth", "status"], check=True, stdout=subprocess.DEVNULL)
    deadline, last = time.monotonic() + 3000, None
    while True:
        if args.run:
            run = api(f"repos/{args.repo}/actions/runs/{args.run}")
        else:
            runs = api(f"repos/{args.repo}/actions/workflows/ios.yml/runs?branch=main&per_page=1")["workflow_runs"]
            if not runs:
                raise SystemExit("No iOS run exists yet; push main or dispatch ios.yml first.")
            run = runs[0]
        state = (run["id"], run["status"], run.get("conclusion"))
        if state != last:
            print("iOS build:", run["html_url"], state[1:], flush=True)
            last = state
        if run["status"] == "completed":
            if run["conclusion"] != "success":
                raise SystemExit("iOS build did not succeed. Inspect that run's logs.")
            break
        if not args.wait or time.monotonic() > deadline:
            raise SystemExit("Build still running. Retry with --wait or the specific --run ID.")
        time.sleep(15)
    output = ROOT / "artifacts/ios"
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ios-download-", dir=output.parent) as temporary:
        subprocess.run(["gh", "run", "download", str(run["id"]), "--repo", args.repo,
                        "--name", "ios-unsigned", "--dir", temporary], check=True)
        directory = Path(temporary)
        manifest = json.loads((directory / "build-info.json").read_text())
        archive = directory / "mojian-unsigned.ipa"
        if manifest["commit"] != run["head_sha"] or manifest["sha256"] != sha256(archive):
            raise SystemExit("Artifact commit or checksum verification failed")
        inspect_ipa(archive)
        output.mkdir(exist_ok=True)
        for name in ("mojian-unsigned.ipa", "build-info.json", "SHA256SUMS"):
            shutil.copyfile(directory / name, output / name)
    print("Verified public IPA downloaded:", output / "mojian-unsigned.ipa")
    print("Next: python3 tools/prepare_ios.py")


if __name__ == "__main__":
    main()
