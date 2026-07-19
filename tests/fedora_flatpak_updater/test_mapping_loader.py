from __future__ import annotations

from pathlib import Path

import pytest

from fedora_flatpak_updater.mapping_loader import MappingError, load_mapping
from fedora_flatpak_updater.models import RecipeKind


def test_load_mapping_parses_all_recipe_kinds(tmp_path: Path):
    mapping_file = tmp_path / ".fedora-tracked-modules.yaml"
    mapping_file.write_text(
        """
modules:
  python3-idna:
    fedora_package: python3-idna
    recipe: pypi
    pypi_name: idna
    prefer: wheel
  python3-cryptography:
    fedora_package: python3-cryptography
    recipe: pypi-multi-wheel
    pypi_name: cryptography
    wheel_arches: [aarch64, x86_64]
  libndp:
    fedora_package: libndp
    recipe: archive
    url_template: "https://github.com/jpirko/libndp/archive/v$version.tar.gz"
  NetworkManager:
    fedora_package: NetworkManager
    recipe: git
    repo_url: "https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git"
    tag_template: "$version"
  python3-bcrypt:
    fedora_package: python3-bcrypt
    recipe: pypi
    pypi_name: bcrypt
    manual_followup: "regenerate bcrypt-cargo-sources.json"
"""
    )

    specs = load_mapping(mapping_file)
    by_name = {spec.name: spec for spec in specs}

    assert by_name["python3-idna"].recipe == RecipeKind.PYPI
    assert by_name["python3-idna"].pypi_name == "idna"

    assert by_name["python3-cryptography"].recipe == RecipeKind.PYPI_MULTI_WHEEL
    assert by_name["python3-cryptography"].wheel_arches == ("aarch64", "x86_64")

    assert by_name["libndp"].recipe == RecipeKind.ARCHIVE
    assert by_name["libndp"].url_template.endswith("v$version.tar.gz")

    assert by_name["NetworkManager"].recipe == RecipeKind.GIT
    assert by_name["NetworkManager"].tag_template == "$version"

    assert by_name["python3-bcrypt"].manual_followup == "regenerate bcrypt-cargo-sources.json"


def test_load_mapping_rejects_missing_recipe(tmp_path: Path):
    mapping_file = tmp_path / ".fedora-tracked-modules.yaml"
    mapping_file.write_text(
        """
modules:
  broken:
    fedora_package: broken
"""
    )
    with pytest.raises(MappingError):
        load_mapping(mapping_file)


def test_load_mapping_rejects_missing_fedora_package(tmp_path: Path):
    mapping_file = tmp_path / ".fedora-tracked-modules.yaml"
    mapping_file.write_text(
        """
modules:
  broken:
    recipe: pypi
    pypi_name: broken
"""
    )
    with pytest.raises(MappingError):
        load_mapping(mapping_file)


def test_load_mapping_with_cargo_fields(tmp_path: Path):
    # We will create a temporary config yaml containing cargo fields
    yaml_content = """
modules:
  python3-bcrypt:
    recipe: pypi
    pypi_name: bcrypt
    fedora_package: python3-bcrypt
    cargo_sources_file: bcrypt-cargo-sources.json
    cargo_lock_path: src/_bcrypt/Cargo.lock
"""
    mapping_file = tmp_path / "mapping.yaml"
    mapping_file.write_text(yaml_content)
    specs = load_mapping(mapping_file)
    assert len(specs) == 1
    assert specs[0].cargo_sources_file == "bcrypt-cargo-sources.json"
    assert specs[0].cargo_lock_path == "src/_bcrypt/Cargo.lock"


