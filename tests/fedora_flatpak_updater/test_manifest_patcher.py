from __future__ import annotations

from pathlib import Path

from fedora_flatpak_updater.manifest_patcher import (
    ManifestForest,
    apply_archive,
    apply_git,
    apply_pypi,
    find_module_blocks,
    find_pypi_source_blocks,
)
from fedora_flatpak_updater.models import ModuleSpec, RecipeKind
from fedora_flatpak_updater.recipes.archive import ArchiveSource
from fedora_flatpak_updater.recipes.git import GitSource
from fedora_flatpak_updater.recipes.pypi import PypiSource

FIXTURES = Path(__file__).parent / "fixtures"


def _fresh_forest(tmp_path: Path) -> ManifestForest:
    for name in ("root.yml", "pip-resources.example.yaml"):
        (tmp_path / name).write_text((FIXTURES / name).read_text())
    return ManifestForest(tmp_path / "root.yml")


def test_find_pypi_source_blocks_finds_every_occurrence_across_files(tmp_path):
    forest = _fresh_forest(tmp_path)
    blocks = find_pypi_source_blocks(forest, "idna")
    assert len(blocks) == 2  # root.yml's own block + the shared anchor/alias block


def test_apply_pypi_updates_every_occurrence_and_strips_checker_data(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-idna", fedora_package="python3-idna", recipe=RecipeKind.PYPI, pypi_name="idna")
    new_source = PypiSource(url="https://files.pythonhosted.org/idna-3.11-py3-none-any.whl", sha256="deadbeef")

    report = apply_pypi(forest, spec, lambda block: new_source)

    assert report.blocks_touched == 2
    for block in find_pypi_source_blocks(forest, "idna"):
        assert block["url"] == new_source.url
        assert block["sha256"] == new_source.sha256
        assert "x-checker-data" not in block


def test_apply_pypi_leaves_unrelated_packages_untouched(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-idna", fedora_package="python3-idna", recipe=RecipeKind.PYPI, pypi_name="idna")
    apply_pypi(forest, spec, lambda block: PypiSource(url="https://x/idna-3.11-py3-none-any.whl", sha256="deadbeef"))

    [requests_block] = find_pypi_source_blocks(forest, "requests")
    assert requests_block["sha256"] == "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0"
    assert requests_block["x-checker-data"]["name"] == "requests"


def test_apply_pypi_updates_duplicate_module_occurrences_independently(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-flit_core", fedora_package="python3-flit_core", recipe=RecipeKind.PYPI, pypi_name="flit_core")
    new_source = PypiSource(url="https://x/flit_core-4.0.0.tar.gz", sha256="cafef00d")

    report = apply_pypi(forest, spec, lambda block: new_source)

    assert report.blocks_touched == 2
    assert all(b["url"] == new_source.url for b in find_pypi_source_blocks(forest, "flit_core"))


def test_apply_archive_updates_module_matched_by_name(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(
        name="libndp",
        fedora_package="libndp",
        recipe=RecipeKind.ARCHIVE,
        url_template="https://github.com/jpirko/libndp/archive/v$version.tar.gz",
    )
    source = ArchiveSource(url="https://github.com/jpirko/libndp/archive/v1.10.tar.gz", sha256="abc123")

    report = apply_archive(forest, spec, source)

    assert report.blocks_touched == 1
    [module] = find_module_blocks(forest, "libndp")
    [src] = module["sources"]
    assert src["url"] == source.url
    assert src["sha256"] == source.sha256
    assert "x-checker-data" not in src


def test_apply_git_updates_tag_and_commit(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(
        name="python-proton-core",
        fedora_package="python-proton-core",
        recipe=RecipeKind.GIT,
        repo_url="https://github.com/ProtonVPN/python-proton-core",
        tag_template="v$version",
    )
    source = GitSource(tag="v0.8.0", commit="a" * 40)

    report = apply_git(forest, spec, source)

    assert report.blocks_touched == 1
    [module] = find_module_blocks(forest, "python-proton-core")
    [src] = module["sources"]
    assert src["tag"] == "v0.8.0"
    assert src["commit"] == "a" * 40


def test_save_preserves_comments_and_unrelated_structure(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-idna", fedora_package="python3-idna", recipe=RecipeKind.PYPI, pypi_name="idna")
    apply_pypi(forest, spec, lambda block: PypiSource(url="https://x/idna-3.11-py3-none-any.whl", sha256="deadbeef"))
    forest.save()

    root_text = (tmp_path / "root.yml").read_text()
    assert "keep me: comment that must survive patching" in root_text
    assert "buildsystem: autotools" in root_text
    assert "cleanup:" in root_text


def test_remove_checker_data_concatenates_comments(tmp_path):
    yaml_content = """modules:
  - name: test-mod
    sources:
      - type: file
        url: https://example.com/foo-1.0.whl
        sha256: 1234  # existing comment on sha256
        x-checker-data:
          type: pypi
          name: foo
        # trailing comment from checker block
"""
    test_file = tmp_path / "test.yml"
    test_file.write_text(yaml_content)
    forest = ManifestForest(test_file)
    spec = ModuleSpec(name="test-mod", fedora_package="test-mod", recipe=RecipeKind.PYPI, pypi_name="foo")
    apply_pypi(forest, spec, lambda block: PypiSource(url="https://example.com/foo-2.0.whl", sha256="5678"))
    forest.save()

    saved = test_file.read_text()
    assert "# existing comment on sha256" in saved
    assert "# trailing comment from checker block" in saved
    assert "x-checker-data:" not in saved
    assert "type: pypi" not in saved

