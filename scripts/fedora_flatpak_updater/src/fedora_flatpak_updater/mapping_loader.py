from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from .models import ModuleSpec, RecipeKind

_yaml = YAML(typ="safe")


class MappingError(ValueError):
    """Raised when .fedora-tracked-modules.yaml is malformed."""


def load_mapping(path: Path) -> list[ModuleSpec]:
    with Path(path).open("r", encoding="utf-8") as fh:
        raw = _yaml.load(fh) or {}

    modules = raw.get("modules") or {}
    specs: list[ModuleSpec] = []
    for name, entry in modules.items():
        if not isinstance(entry, dict):
            raise MappingError(f"{name}: entry must be a mapping")
        try:
            recipe = RecipeKind(entry["recipe"])
        except (KeyError, ValueError) as exc:
            raise MappingError(f"{name}: invalid or missing 'recipe'") from exc
        if "fedora_package" not in entry:
            raise MappingError(f"{name}: missing 'fedora_package'")

        specs.append(
            ModuleSpec(
                name=name,
                fedora_package=entry["fedora_package"],
                recipe=recipe,
                pypi_name=entry.get("pypi_name"),
                prefer=entry.get("prefer", "wheel"),
                wheel_arches=tuple(entry.get("wheel_arches", ())),
                url_template=entry.get("url_template"),
                repo_url=entry.get("repo_url"),
                tag_template=entry.get("tag_template"),
                tag_pattern=entry.get("tag_pattern"),
                manual_followup=entry.get("manual_followup"),
                cargo_sources_file=entry.get("cargo_sources_file"),
                cargo_lock_path=entry.get("cargo_lock_path"),
            )
        )
    return specs

