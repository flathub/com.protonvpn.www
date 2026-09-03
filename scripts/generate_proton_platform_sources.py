#!/usr/bin/env python3
"""Generate proton-vpn-platform-cargo-sources.json for Flatpak offline vendoring.

This script parses Cargo.lock from python-proton-vpn-api-core, runs flatpak-cargo-generator.py,
rewrites Proton-hosted sparse registry crate URLs to https://rust-registry.proton.me/downloads/,
and injects the offline sparse registry cargo configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "com.protonvpn.www.yml"
DEFAULT_OUTPUT = REPO_ROOT / "proton-vpn-platform-cargo-sources.json"
GENERATOR_URL = "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/cargo/flatpak-cargo-generator.py"
PROTON_SPARSE_REGISTRY = "sparse+https://rust-registry.proton.me/index/"
PROTON_DOWNLOAD_BASE = "https://rust-registry.proton.me/downloads"

OFFLINE_CARGO_CONFIG = """[source.vendored-sources]
directory = "cargo/vendor"

[source.crates-io]
replace-with = "vendored-sources"

[source."sparse+https://rust-registry.proton.me/index/"]
registry = "sparse+https://rust-registry.proton.me/index/"
replace-with = "vendored-sources"

[registries.proton]
index = "sparse+https://rust-registry.proton.me/index/"

[registries.proton_public]
index = "sparse+https://rust-registry.proton.me/index/"
"""


def parse_proton_crates(cargo_lock_text: str) -> set[tuple[str, str]]:
    """Extract (crate_name, version) pairs originating from Proton's sparse registry."""
    pattern = (
        r'\[\[package\]\]\n'
        r'name\s*=\s*"([^"]+)"\n'
        r'version\s*=\s*"([^"]+)"\n'
        r'source\s*=\s*"sparse\+https://rust-registry\.proton\.me/index/"'
    )
    return set(re.findall(pattern, cargo_lock_text))


def get_protun_version(cargo_lock_text: str) -> str | None:
    """Extract the required version of protun from Cargo.lock."""
    match = re.search(
        r'\[\[package\]\]\nname\s*=\s*"protun"\nversion\s*=\s*"([^"]+)"',
        cargo_lock_text,
    )
    return match.group(1) if match else None


def get_manifest_tag(manifest_path: Path) -> str:
    """Read the current tag for python-proton-vpn-api-core from the Flatpak manifest."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    content = manifest_path.read_text(encoding="utf-8")
    # Locate module: python-proton-vpn-api-core and extract tag
    match = re.search(
        r'name:\s*python-proton-vpn-api-core.*?'
        r'url:\s*https://github\.com/ProtonVPN/python-proton-vpn-api-core.*?'
        r'tag:\s*([^\s\n]+)',
        content,
        re.DOTALL,
    )
    if not match:
        raise ValueError(
            f"Could not locate python-proton-vpn-api-core tag in {manifest_path}"
        )
    return match.group(1)


def fetch_cargo_lock_from_tag(tag: str) -> str:
    """Fetch Cargo.lock from ProtonVPN/python-proton-vpn-api-core GitHub repository."""
    url = f"https://raw.githubusercontent.com/ProtonVPN/python-proton-vpn-api-core/{tag}/Cargo.lock"
    req = urllib.request.Request(url, headers={"User-Agent": "ProtonVPN-Flatpak-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def rewrite_cargo_sources(
    raw_sources: list[dict],
    proton_crates: set[tuple[str, str]],
) -> list[dict]:
    """Rewrite crates.io URLs to Proton registry URLs and inject offline cargo config."""
    updated_sources = []

    for item in raw_sources:
        if item.get("type") == "archive":
            url = item.get("url", "")
            for name, ver in proton_crates:
                crates_io_url = f"https://static.crates.io/crates/{name}/{name}-{ver}.crate"
                if url == crates_io_url:
                    item = dict(item)
                    item["url"] = f"{PROTON_DOWNLOAD_BASE}/{name}@{ver}.crate"
                    break
        updated_sources.append(item)

    # Ensure trailing inline config sets up sparse registry vendoring
    if updated_sources and updated_sources[-1].get("dest") == "cargo":
        updated_sources[-1] = {
            "type": "inline",
            "contents": OFFLINE_CARGO_CONFIG,
            "dest": "cargo",
            "dest-filename": "config.toml",
        }
    else:
        updated_sources.append(
            {
                "type": "inline",
                "contents": OFFLINE_CARGO_CONFIG,
                "dest": "cargo",
                "dest-filename": "config.toml",
            }
        )

    return updated_sources


def find_python_with_aiohttp() -> str:
    """Find a Python interpreter that has aiohttp installed for flatpak-cargo-generator."""
    try:
        subprocess.run(
            [sys.executable, "-c", "import aiohttp"],
            check=True,
            capture_output=True,
        )
        return sys.executable
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    venv_python = REPO_ROOT / "scripts" / "fedora_flatpak_updater" / ".venv" / "bin" / "python"
    if venv_python.is_file() and os.access(venv_python, os.X_OK):
        return str(venv_python)

    return sys.executable


def generate_sources(
    cargo_lock_text: str,
    output_path: Path,
) -> None:
    """Run flatpak-cargo-generator on cargo_lock_text and write adjusted sources to output_path."""
    proton_crates = parse_proton_crates(cargo_lock_text)
    print(f"Found {len(proton_crates)} Proton registry crates in Cargo.lock.")

    protun_version = get_protun_version(cargo_lock_text)
    if protun_version:
        print(f"Proton protun requirement: v{protun_version}")

    python_bin = find_python_with_aiohttp()

    # Download flatpak-cargo-generator.py
    req = urllib.request.Request(GENERATOR_URL, headers={"User-Agent": "ProtonVPN-Flatpak-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        generator_code = resp.read()

    with tempfile.TemporaryDirectory() as tempdir:
        temp_dir_path = Path(tempdir)
        script_file = temp_dir_path / "flatpak-cargo-generator.py"
        script_file.write_bytes(generator_code)

        lock_file = temp_dir_path / "Cargo.lock"
        lock_file.write_text(cargo_lock_text, encoding="utf-8")

        temp_sources = temp_dir_path / "sources.json"

        cmd = [python_bin, str(script_file), str(lock_file), "-o", str(temp_sources)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"flatpak-cargo-generator.py failed with code {proc.returncode}:\n"
                f"stdout: {proc.stdout}\n"
                f"stderr: {proc.stderr}"
            )

        with open(temp_sources, encoding="utf-8") as f:
            raw_sources = json.load(f)

        final_sources = rewrite_cargo_sources(raw_sources, proton_crates)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output = output_path.parent / f".tmp_{output_path.name}"
        with open(temp_output, "w", encoding="utf-8") as f:
            json.dump(final_sources, f, indent=4)
            f.write("\n")

        shutil.move(temp_output, output_path)
        print(f"Successfully wrote {len(final_sources)} sources to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate proton-vpn-platform-cargo-sources.json from Cargo.lock"
    )
    parser.add_argument(
        "--cargo-lock",
        "-l",
        type=Path,
        help="Path to local Cargo.lock file (if omitted, fetched from git tag)",
    )
    parser.add_argument(
        "--tag",
        "-t",
        help="Git tag for python-proton-vpn-api-core (e.g. v5.6.10, defaults to tag in manifest)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to output cargo-sources.json file (default: proton-vpn-platform-cargo-sources.json)",
    )
    parser.add_argument(
        "--manifest",
        "-m",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to com.protonvpn.www.yml manifest",
    )
    args = parser.parse_args()

    if args.cargo_lock:
        print(f"Reading Cargo.lock from {args.cargo_lock}...")
        cargo_lock_text = args.cargo_lock.read_text(encoding="utf-8")
    else:
        tag = args.tag or get_manifest_tag(args.manifest)
        print(f"Fetching Cargo.lock for tag '{tag}'...")
        cargo_lock_text = fetch_cargo_lock_from_tag(tag)

    generate_sources(cargo_lock_text, args.output)


if __name__ == "__main__":
    main()
