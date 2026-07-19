from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecipeKind(str, Enum):
    PYPI = "pypi"
    PYPI_MULTI_WHEEL = "pypi-multi-wheel"
    ARCHIVE = "archive"
    GIT = "git"


@dataclass(frozen=True)
class ModuleSpec:
    """One entry from .fedora-tracked-modules.yaml."""

    name: str
    fedora_package: str
    recipe: RecipeKind
    pypi_name: str | None = None
    prefer: str = "wheel"
    wheel_arches: tuple[str, ...] = ()
    url_template: str | None = None
    repo_url: str | None = None
    tag_template: str | None = None
    tag_pattern: str | None = None
    manual_followup: str | None = None
    cargo_sources_file: str | None = None
    cargo_lock_path: str | None = None

