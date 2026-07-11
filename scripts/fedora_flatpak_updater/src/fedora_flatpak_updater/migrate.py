# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/migrate.py
"""One-off helper for building the initial .fedora-tracked-modules.yaml.

Walks the manifest forest, collects every distinct third-party PyPI
`x-checker-data.name` value plus the known native archive/git modules,
guesses a Fedora package name for each, and verifies the guess against
MDAPI (including a HEAD check for archive url_templates, since the design
doc's `polkit` case shows a stale template resolving to a 404). Prints a
YAML draft to stdout; a human reviews it, hand-fixes anything flagged
`_needs_manual_fix`, and saves the result to .fedora-tracked-modules.yaml.

Not part of the ongoing scheduled job — run manually only when rebuilding
the mapping from scratch (e.g. after adding a new dependency).
"""
from __future__ import annotations

import sys
from pathlib import Path
from string import Template
from typing import Any

import click
import requests
from packaging.utils import canonicalize_name
from ruamel.yaml import YAML

from .fedora_release import get_current_stable_branch
from .mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError

PROTON_PREFIX = "proton"

NATIVE_MODULE_HINTS: dict[str, dict] = {
    "libndp": {
        "recipe": "archive",
        "url_template": "https://github.com/jpirko/libndp/archive/v$version.tar.gz",
    },
    "polkit": {
        "recipe": "archive",
        "url_template": "https://github.com/polkit-org/polkit/archive/refs/tags/$version.tar.gz",
    },
    "libnma": {
        "recipe": "archive",
        "url_template": "https://gitlab.gnome.org/GNOME/libnma/-/archive/$version/libnma-$version.tar.gz",
    },
    "iproute2": {
        "recipe": "archive",
        "url_template": "https://www.kernel.org/pub/linux/utils/net/iproute2/iproute2-$version.tar.xz",
    },
    "python-dbus": {
        "recipe": "archive",
        "fedora_package": "dbus-python",
        "url_template": "https://dbus.freedesktop.org/releases/dbus-python/dbus-python-$version.tar.gz",
    },
    "NetworkManager": {
        "recipe": "git",
        "repo_url": "https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
        "tag_template": "$version",
    },
    "NetworkManager-openvpn": {
        "recipe": "git",
        "repo_url": "https://github.com/NetworkManager/NetworkManager-openvpn.git",
        "tag_template": "$version",
    },
    "systemd": {
        "recipe": "git",
        "repo_url": "https://github.com/systemd/systemd.git",
        "tag_pattern": r"^v([\d.]+)$",
    },
}

MANUAL_FOLLOWUP = {
    "python3-bcrypt": (
        "bcrypt vendors Rust crate sources in bcrypt-cargo-sources.json. "
        "Re-run flatpak-cargo-generator against the new version's Cargo.lock "
        "before merging."
    ),
}

# Known guess-convention exceptions (design doc item 6).
FEDORA_NAME_OVERRIDES = {
    "pycairo": "python3-cairo",
    "pygobject": "python3-gobject",
}


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def _load_forest(root_path: Path) -> list[Any]:
    yaml = YAML(typ="safe")
    documents = []
    seen: set[Path] = set()

    def load(path: Path) -> None:
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.load(fh)
        documents.append(data)
        for d in _iter_dicts(data):
            modules = d.get("modules")
            if isinstance(modules, list):
                for item in modules:
                    if isinstance(item, str):
                        load(path.parent / item)

    load(root_path)
    return documents


def discover_pypi_names(root_path: Path) -> set[str]:
    names = set()
    for document in _load_forest(root_path):
        for d in _iter_dicts(document):
            checker = d.get("x-checker-data")
            if isinstance(checker, dict) and checker.get("type") in ("pypi", "json"):
                name = checker.get("name")
                if name and not name.lower().startswith(PROTON_PREFIX):
                    names.add(name)
    return names


def guess_fedora_package(pypi_name: str) -> str:
    if pypi_name in FEDORA_NAME_OVERRIDES:
        return FEDORA_NAME_OVERRIDES[pypi_name]
    return f"python3-{canonicalize_name(pypi_name)}"


def build_draft(root_path: Path, branch: str, session: requests.Session) -> dict:
    mdapi = MdapiClient(branch, session=session)
    modules: dict[str, dict] = {}

    for pypi_name in sorted(discover_pypi_names(root_path)):
        guess = guess_fedora_package(pypi_name)
        entry = {"recipe": "pypi", "pypi_name": pypi_name, "fedora_package": guess}
        try:
            mdapi.get_version(guess)
        except (PackageNotFoundError, MdapiTransientError, requests.RequestException) as exc:
            entry["_needs_manual_fix"] = f"{guess} lookup failed in Fedora {branch}: {exc}"
        modules[guess] = entry

    for name, hint in NATIVE_MODULE_HINTS.items():
        fedora_package = hint.get("fedora_package", name)
        entry = {"recipe": hint["recipe"], "fedora_package": fedora_package}
        entry.update({k: v for k, v in hint.items() if k not in ("recipe", "fedora_package")})
        try:
            version = mdapi.get_version(fedora_package)
        except (PackageNotFoundError, MdapiTransientError, requests.RequestException) as exc:
            entry["_needs_manual_fix"] = f"{fedora_package} lookup failed in Fedora {branch}: {exc}"
            modules[name] = entry
            continue

        if hint["recipe"] == "archive":
            rendered = Template(hint["url_template"]).substitute(version=version)
            try:
                response = session.head(rendered, allow_redirects=True, timeout=30)
                if response.status_code >= 400:
                    entry["_needs_manual_fix"] = (
                        f"url_template renders to {rendered} which returned "
                        f"{response.status_code} for version {version}"
                    )
            except requests.RequestException as exc:
                entry["_needs_manual_fix"] = f"url_template check failed for {rendered}: {exc}"
        modules[name] = entry

    for module_name, note in MANUAL_FOLLOWUP.items():
        modules.setdefault(module_name, {})["manual_followup"] = note

    return {"modules": modules}


@click.command()
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("com.protonvpn.www.yml"),
    show_default=True,
    help="Path to the root Flatpak manifest to walk.",
)
def main(manifest: Path) -> None:
    """Print a draft .fedora-tracked-modules.yaml to stdout for review."""
    session = requests.Session()
    branch = get_current_stable_branch(session=session)
    draft = build_draft(manifest, branch, session)

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.dump(draft, sys.stdout)


if __name__ == "__main__":
    main()
