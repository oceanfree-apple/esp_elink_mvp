"""Exercise the same IPA bytes that move from public CI to private signing."""
import json
import plistlib
import stat
from zipfile import ZipFile

import pytest

import prepare_ios
from ios_package import EMPTY_CONFIG, inspect_ipa, sha256
from pack_ios import package


@pytest.fixture
def build(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_ios, "ROOT", tmp_path)
    app = tmp_path / "build/Runner.app"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "com.mojian.frame", "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "17",
    }))
    (app / "Runner").write_bytes(b"example-arm64-executable")
    (app / "Runner").chmod(0o755)
    assets = app / "Frameworks/App.framework/flutter_assets/assets"
    assets.mkdir(parents=True)
    (assets / "connection.json").write_text(json.dumps(EMPTY_CONFIG))
    (assets / "cloud_ca.pem").write_bytes(b"public-test-certificate")
    (app / "Frameworks/Current").symlink_to("App.framework", target_is_directory=True)
    source = tmp_path / "artifacts/ios/mojian-unsigned.ipa"
    manifest = package(app, source, "a" * 40)
    private = tmp_path / ".private"
    private.mkdir()
    settings = private / "settings.json"
    settings.write_text(json.dumps({"ip": "192.0.2.1", "app_token": "test-only-private-token"}))
    return source, source.parent / "build-info.json", settings, manifest


def test_private_preparation_changes_only_config_and_keeps_public_input(build, tmp_path):
    source, manifest_path, settings, manifest = build
    before = source.read_bytes()
    output = tmp_path / ".private/ios/mojian-configured.ipa"
    result = prepare_ios.prepare(source, manifest_path, settings, output)

    assert source.read_bytes() == before
    assert inspect_ipa(source)["bundle_id"] == "com.mojian.frame"
    assert result["source_sha256"] == sha256(source) == manifest["sha256"]
    assert result["sha256"] == sha256(output)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert "test-only-private-token" not in output.with_suffix(".json").read_text()
    assert "test-only-private-token" not in manifest_path.read_text()
    with ZipFile(source) as public, ZipFile(output) as personal:
        assert public.namelist() == personal.namelist()
        for entry in public.infolist():
            configured = personal.getinfo(entry.filename)
            assert entry.external_attr == configured.external_attr
            if entry.filename == manifest["config_path"]:
                assert json.loads(personal.read(entry.filename)) == {
                    "version": 1, "base_url": "https://192.0.2.1", "app_token": "test-only-private-token",
                }
            else:
                assert public.read(entry) == personal.read(entry.filename)
        executable = public.getinfo("Payload/Runner.app/Runner")
        assert executable.external_attr >> 16 & 0o111
        link = public.getinfo("Payload/Runner.app/Frameworks/Current")
        assert stat.S_ISLNK(link.external_attr >> 16)
        assert personal.read(link.filename) == b"App.framework"
    with pytest.raises(ValueError, match="empty connection"):
        inspect_ipa(output)


def test_corrupted_download_cannot_be_prepared(build, tmp_path):
    source, manifest_path, settings, _ = build
    with source.open("ab") as stream:
        stream.write(b"tampered")
    output = tmp_path / ".private/ios/configured.ipa"
    with pytest.raises(ValueError, match="digest"):
        prepare_ios.prepare(source, manifest_path, settings, output)
    assert not output.exists()


@pytest.mark.parametrize("field,value", [("bundle_id", "other.app"), ("signing", "signed"),
                                         ("profile", "debug")])
def test_wrong_build_metadata_cannot_be_prepared(build, tmp_path, field, value):
    source, manifest_path, settings, manifest = build
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        prepare_ios.prepare(source, manifest_path, settings, tmp_path / ".private/ios/app.ipa")


def test_private_output_cannot_be_written_to_public_artifacts(build, tmp_path):
    source, manifest_path, settings, _ = build
    output = tmp_path / "artifacts/ios/configured.ipa"
    with pytest.raises(ValueError, match=r"inside .private/"):
        prepare_ios.prepare(source, manifest_path, settings, output)
    assert not output.exists()


def test_invalid_connection_does_not_create_personal_ipa(build, tmp_path):
    source, manifest_path, settings, _ = build
    settings.write_text(json.dumps({"base_url": "http://192.0.2.1", "app_token": "private-example"}))
    output = tmp_path / ".private/ios/configured.ipa"
    with pytest.raises(ValueError, match="settings are invalid") as error:
        prepare_ios.prepare(source, manifest_path, settings, output)
    assert "private-example" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize("extra", ["../escaped", "/absolute", "Payload\\bad"])
def test_unsafe_archive_paths_are_rejected(build, extra):
    source, _, _, _ = build
    with ZipFile(source, "a") as archive:
        archive.writestr(extra, b"invalid")
    with pytest.raises(ValueError, match="unsafe entry paths"):
        inspect_ipa(source)


def test_public_packager_rejects_accidental_credentials(build, tmp_path):
    _, _, _, _ = build
    app = tmp_path / "build/Runner.app"
    asset = app / "Frameworks/App.framework/flutter_assets/assets/connection.json"
    asset.write_text(json.dumps({"version": 1, "base_url": "https://192.0.2.1", "app_token": "secret"}))
    output = tmp_path / "bad.ipa"
    with pytest.raises(ValueError, match="empty connection"):
        package(app, output, "local")
    assert not output.exists()


def test_missing_registered_asset_fails_packaging(build, tmp_path):
    _, _, _, _ = build
    app = tmp_path / "build/Runner.app"
    (app / "Frameworks/App.framework/flutter_assets/assets/connection.json").unlink()
    output = tmp_path / "missing.ipa"
    with pytest.raises(ValueError, match="asset missing"):
        package(app, output, "local")
    assert not output.exists()
