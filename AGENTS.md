# AGENTS.md

Technical context and operational instructions for AI coding agents working on the Proton VPN Flatpak repository (`com.protonvpn.www`).

---

## Project Overview

Flathub package build specifications for Proton VPN (`com.protonvpn.www`), packaging the Proton VPN GTK Desktop application and CLI tools using GNOME Platform 50 (`org.gnome.Platform//50` / `org.gnome.Sdk//50`).

### Core Architecture & Key Files

- **Flatpak Manifest**: [`com.protonvpn.www.yml`](file:///home/slash/Development/com.protonvpn.www/com.protonvpn.www.yml) (Root YAML manifest using GNOME 50 and `org.freedesktop.Sdk.Extension.rust-stable`).
- **Python Dependency Sub-manifests**: `pip-resources.*.yaml` files defining Python dependencies.
- **Rust / Cargo Sources**:
  - [`proton-vpn-platform-cargo-sources.json`](file:///home/slash/Development/com.protonvpn.www/proton-vpn-platform-cargo-sources.json): Offline crate vendoring for `proton-vpn-platform` (`libproton_vpn_platform.so`, `nm-protun-service`, `nm-protun-auth-dialog`).
  - [`bcrypt-cargo-sources.json`](file:///home/slash/Development/com.protonvpn.www/bcrypt-cargo-sources.json): Offline crate vendoring for `python3-bcrypt`.
- **Local Patches**: Located in [`patches/`](file:///home/slash/Development/com.protonvpn.www/patches/) for path corrections, lockfile synchronization, and stripping deprecated requirements.
- **Dependency Automation Tool**: [`scripts/fedora_flatpak_updater`](file:///home/slash/Development/com.protonvpn.www/scripts/fedora_flatpak_updater) — synchronizes Fedora-tracked dependencies with stable releases.

---

## Quick Reference Commands

```bash
# Build package locally (Clean)
flatpak-builder --force-clean build-dir com.protonvpn.www.yml

# Build via Flatpak Builder container (fallback if flatpak-builder binary is not on host)
flatpak run --filesystem="$PWD" org.flatpak.Builder --force-clean build-dir com.protonvpn.www.yml

# Test download phase only (Network verification)
flatpak-builder --download-only build-dir com.protonvpn.www.yml

# Run CLI / GUI from built Flatpak
flatpak run com.protonvpn.www protonvpn --help
flatpak run com.protonvpn.www

# Run updater test suite
scripts/fedora_flatpak_updater/.venv/bin/pytest tests/fedora_flatpak_updater -v
```

---

## Critical Packaging & Build Rules

1. **Deterministic Offline Builds**:
   - Flathub build workers disable network access during compilation (`--unshare=network`).
   - Every remote archive, git repository, PyPI wheel, and Cargo crate must be declared in the manifest or sub-manifests with valid SHA256 checksums.

2. **Rust & Sparse Registry Vendoring (`proton-vpn-platform`)**:
   - `python-proton-vpn-api-core` relies on Proton's sparse registry (`sparse+https://rust-registry.proton.me/index/`).
   - Standard `flatpak-cargo-generator.py` points non-git crates to `static.crates.io`. Proton crates must explicitly use `https://rust-registry.proton.me/downloads/{crate}@{version}.crate` in [`proton-vpn-platform-cargo-sources.json`](file:///home/slash/Development/com.protonvpn.www/proton-vpn-platform-cargo-sources.json).
   - The embedded `cargo/config.toml` must replace `sparse+https://rust-registry.proton.me/index/` with `vendored-sources` and define both `[registries.proton]` and `[registries.proton_public]`.
   - If upstream tagged releases contain stale internal lockfiles, maintain [`patches/python-proton-vpn-api-core/update-cargo-lock.patch`](file:///home/slash/Development/com.protonvpn.www/patches/python-proton-vpn-api-core/update-cargo-lock.patch) to satisfy `cargo build --locked`.

3. **Python Pip Offline Builds**:
   - Always pass `--no-build-isolation` to `pip3 install` to prevent pip from querying PyPI for build environments.
   - Build-time dependencies (`setuptools_rust`, `flit_core`, `skbuild`, `meson`) must be installed as preceding or nested modules.
   - Strip removed/redundant requirements (e.g. `proton-vpn-local-agent`) via patches in [`patches/`](file:///home/slash/Development/com.protonvpn.www/patches/).

4. **Security & System Permissions**:
   - Manifest `finish-args` must remain minimal and compliant with Flathub standards.
   - Required D-Bus interfaces: `org.freedesktop.secrets` (keyring), `org.freedesktop.NetworkManager` (system bus), `org.freedesktop.login1` (daemon reconnect), `org.kde.StatusNotifierWatcher` (tray icon).

---

## Deep-Dive Reference Guides

For comprehensive runbooks and technical guides, consult:
- [Cargo / Rust Offline Dependency Generation](.agents/skills/creating-flatpaks/references/cargo-offline-generation.md)
- [Python / Pip Offline Dependency Management](.agents/skills/creating-flatpaks/references/python-pip-offline.md)
- [Manifest Architecture & Permissions Guide](.agents/skills/creating-flatpaks/references/manifest-structure-and-permissions.md)
- [Creating & Maintaining Flatpaks Runbook](.agents/skills/creating-flatpaks/SKILL.md)

---

## Pull Request Guidelines

1. Validate manifest schema before committing (`https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json`).
2. Run pytest suite (`scripts/fedora_flatpak_updater/.venv/bin/pytest tests/fedora_flatpak_updater -v`) and ensure all tests pass when modifying updater code.
3. Validate Python formatting/linting via `ruff check scripts/fedora_flatpak_updater tests/`.
