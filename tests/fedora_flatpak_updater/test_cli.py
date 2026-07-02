from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
import runpy
import sys

import pytest
from click.testing import CliRunner

from fedora_flatpak_updater import cli
from fedora_flatpak_updater.mdapi_client import PackageNotFoundError
from fedora_flatpak_updater.recipes.archive import ArchiveSource
from fedora_flatpak_updater.recipes.pypi import PypiSource

FIXTURES = Path(__file__).parent / "fixtures"


class FakeMdapi:
    _VERSIONS = {"python3-idna": "3.99", "libndp": "9.9"}

    def __init__(self, branch, session=None):
        self.branch = branch

    def get_version(self, package_name):
        if package_name not in self._VERSIONS:
            raise PackageNotFoundError(package_name, self.branch)
        return self._VERSIONS[package_name]


@pytest.fixture
def manifest_root(tmp_path):
    for name in ("root.yml", "pip-resources.example.yaml"):
        (tmp_path / name).write_text((FIXTURES / name).read_text())
    return tmp_path / "root.yml"


@pytest.fixture
def mapping_file(tmp_path):
    path = tmp_path / ".fedora-tracked-modules.yaml"
    path.write_text(
        """
modules:
  python3-idna:
    fedora_package: python3-idna
    recipe: pypi
    pypi_name: idna
  libndp:
    fedora_package: libndp
    recipe: archive
    url_template: "https://github.com/jpirko/libndp/archive/v$version.tar.gz"
  python3-nonexistent:
    fedora_package: python3-nonexistent
    recipe: pypi
    pypi_name: nonexistent
"""
    )
    return path


def _patch_common(monkeypatch):
    monkeypatch.setattr(cli, "get_current_stable_branch", lambda session=None: "f44")
    monkeypatch.setattr(cli, "MdapiClient", FakeMdapi)
    monkeypatch.setattr(
        cli.pypi_recipe,
        "resolve",
        lambda pypi_name, version, prefer="wheel", session=None: PypiSource(
            url=f"https://x/{pypi_name}-{version}-py3-none-any.whl", sha256="deadbeef"
        ),
    )
    monkeypatch.setattr(
        cli.archive_recipe,
        "resolve",
        lambda url_template, version, session=None: ArchiveSource(
            url=f"https://x/libndp-{version}.tar.gz", sha256="cafef00d"
        ),
    )


def test_run_reports_updated_and_skipped_modules(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)

    rows = cli.run(mapping_file, manifest_root, dry_run=True)

    statuses = {row.module_name: row.status for row in rows}
    assert statuses["python3-idna"] == "updated"
    assert statuses["libndp"] == "updated"
    assert statuses["python3-nonexistent"] == "skipped"


def test_dry_run_does_not_write_files(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)
    original_text = manifest_root.read_text()

    cli.run(mapping_file, manifest_root, dry_run=True, only=["python3-idna"])

    assert manifest_root.read_text() == original_text


def test_non_dry_run_writes_updated_files(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)

    cli.run(mapping_file, manifest_root, dry_run=False, only=["python3-idna"])

    assert "idna-3.99-py3-none-any.whl" in manifest_root.read_text()


def test_format_summary_produces_a_github_markdown_table(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)
    rows = cli.run(mapping_file, manifest_root, dry_run=True)

    summary = cli.format_summary(rows)

    assert "| Module" in summary
    assert "python3-idna" in summary
    assert "python3-nonexistent" in summary


def test_main_command_wires_flags_into_run(monkeypatch, manifest_root, mapping_file):
    captured = {}

    def fake_run(mapping, manifest, *, dry_run=False, only=None):
        captured["dry_run"] = dry_run
        captured["only"] = only
        return [cli.Row("python3-idna", "updated", "-> 3.99 (1 block(s))")]

    monkeypatch.setattr(cli, "run", fake_run)

    result = CliRunner().invoke(
        cli.main,
        [
            "--mapping", str(mapping_file),
            "--manifest", str(manifest_root),
            "--dry-run",
            "--only", "python3-idna",
        ],
    )

    assert result.exit_code == 0
    assert "python3-idna" in result.output
    assert captured["dry_run"] is True
    assert captured["only"] == ["python3-idna"]


def test_main_command_exits_nonzero_on_bodhi_failure(monkeypatch, manifest_root, mapping_file):
    def raise_bodhi_error(mapping, manifest, *, dry_run=False, only=None):
        raise cli.BodhiLookupError("Bodhi is down")

    monkeypatch.setattr(cli, "run", raise_bodhi_error)

    result = CliRunner().invoke(cli.main, ["--mapping", str(mapping_file), "--manifest", str(manifest_root)])

    assert result.exit_code == 1
    assert "Bodhi is down" in result.output


def test_entry_point_wired():
    eps = entry_points(group="console_scripts")
    matching = [ep for ep in eps if ep.name == "fedora-flatpak-updater"]
    assert len(matching) == 1
    assert matching[0].value == "fedora_flatpak_updater.cli:main"


def test_main_module_execution(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fedora-flatpak-updater",
            "--mapping",
            str(mapping_file),
            "--manifest",
            str(manifest_root),
            "--dry-run",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("fedora_flatpak_updater.__main__", run_name="__main__")
    assert exc_info.value.code == 0
