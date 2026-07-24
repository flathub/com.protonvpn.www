# AGENTS.md

Technical context and operational instructions for AI coding agents working on the Proton VPN Flatpak repository (`com.protonvpn.www`).

---

## Project Overview

This repository maintains the **Flathub package build specifications** for Proton VPN (`com.protonvpn.www`). It builds a sandboxed Flatpak package of the Proton VPN GTK Desktop app and CLI tools using GNOME Platform 50.

### Core Stack & Key Components

- **Flatpak Manifest**: [`com.protonvpn.www.yml`](file:///home/slash/Development/com.protonvpn.www/com.protonvpn.www.yml) (YAML specification using GNOME Platform 50 / SDK 50).
- **Sub-manifests / Resources**: `pip-resources.*.yaml` files defining Python dependencies for core components:
  - [`pip-resources.proton-vpn-cli.yaml`](file:///home/slash/Development/com.protonvpn.www/pip-resources.proton-vpn-cli.yaml)
  - [`pip-resources.proton-vpn-gtk-app.yaml`](file:///home/slash/Development/com.protonvpn.www/pip-resources.proton-vpn-gtk-app.yaml)
  - [`pip-resources.python-proton-core.yaml`](file:///home/slash/Development/com.protonvpn.www/pip-resources.python-proton-core.yaml)
  - [`pip-resources.python-proton-keyring-linux.yaml`](file:///home/slash/Development/com.protonvpn.www/pip-resources.python-proton-keyring-linux.yaml)
  - [`pip-resources.python-proton-vpn-api-core.yaml`](file:///home/slash/Development/com.protonvpn.www/pip-resources.python-proton-vpn-api-core.yaml)
  - [`pip-resources.python-skbuild.yaml`](file:///home/slash/Development/com.protonvpn.www/pip-resources.python-skbuild.yaml)
- **Rust / Cargo Sources**: [`bcrypt-cargo-sources.json`](file:///home/slash/Development/com.protonvpn.www/bcrypt-cargo-sources.json) for native Python modules requiring Rust compilation (`python3-bcrypt`, `python3-cryptography`).
- **AppStream Metainfo**: [`com.protonvpn.www.metainfo.xml`](file:///home/slash/Development/com.protonvpn.www/com.protonvpn.www.metainfo.xml)
- **Dependency Automation Tool**: [`scripts/fedora_flatpak_updater`](file:///home/slash/Development/com.protonvpn.www/scripts/fedora_flatpak_updater) — a Python package managed via `uv` that synchronizes Flatpak dependency versions with Fedora stable releases.

---

## Setup & Prerequisites

To develop, build, test, and manage this repository, the following system tools are needed:

- **Flatpak Builder**: `flatpak`, `flatpak-builder`
- **Python / Package Management**: `python3` (3.12+), `uv` (for script environment management), `flatpak-pip-generator` (from flatpak-builder-tools)
- **Updater Tooling**: Initialize the updater subproject virtual environment:

```bash
uv sync --project scripts/fedora_flatpak_updater
```
*(Alternatively, if `uv` is unavailable on PATH, use `python3 -m venv` or execute directly via `scripts/fedora_flatpak_updater/.venv/bin/python`)*

---

## Development Workflow

### 1. Building the Flatpak Package

Build the app locally using `flatpak-builder`:

```bash
# Clean build
flatpak-builder --force-clean build-dir com.protonvpn.www.yml

# Install build locally for test user
flatpak-builder --force-clean --user --install build-dir com.protonvpn.www.yml
```

### 2. Testing App & CLI Execution

To launch the GUI or run CLI commands from the built Flatpak:

```bash
# Run GUI App
flatpak run com.protonvpn.www

# CLI: Check status & help
flatpak run com.protonvpn.www protonvpn --help
flatpak run com.protonvpn.www protonvpn status
```

### 3. Updating Dependency Resource Files

When upstream Python packages release updates, use `flatpak-pip-generator` to update `pip-resources.*.yaml`:

```bash
flatpak-pip-generator --checker-data --yaml --runtime='org.gnome.Sdk//49' \
  click dbus-fast tabulate -o pip-resources.proton-vpn-cli
```

### 4. Fedora Dependency Updater Tool (`fedora_flatpak_updater`)

The updater syncs tracked dependencies in [`com.protonvpn.www.yml`](file:///home/slash/Development/com.protonvpn.www/com.protonvpn.www.yml) and `pip-resources.*.yaml` with Fedora's latest stable release.

```bash
# Preview changes (dry run)
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --dry-run

# Update specific package(s)
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --only python3-idna --only libndp

# Rebuild the package mapping draft
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.migrate > /tmp/draft.yaml
```

---

## Testing Instructions

Unit tests cover the `fedora_flatpak_updater` tool and live in [`tests/fedora_flatpak_updater`](file:///home/slash/Development/com.protonvpn.www/tests/fedora_flatpak_updater).

### Running Test Suite

```bash
# Standard test run via uv
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v

# Direct virtual environment execution fallback
scripts/fedora_flatpak_updater/.venv/bin/pytest tests/fedora_flatpak_updater -v
```

### CI Workflows

GitHub Actions workflows are defined in [`.github/workflows/`](file:///home/slash/Development/com.protonvpn.www/.github/workflows):
- `test-fedora-flatpak-updater.yml`: Runs `pytest` on PRs touching updater scripts or tests.
- `update-fedora-flatpak-deps.yml`: Scheduled/manual workflow that runs the updater tool and submits automated dependency updates.

---

## Code Style & Formatting Guidelines

- **YAML Files**:
  - Keep 2-space indentation.
  - Preserve standard Flatpak manifest structural conventions (`id`, `runtime`, `runtime-version`, `sdk`, `finish-args`, `modules`).
  - Retain `x-checker-data` annotations on PyPI and source blocks to enable automated update checks.
- **Python Code**:
  - Target Python 3.12+.
  - Formatting & Linting: Use `ruff`.
  
  ```bash
  # Check python code linting
  uv run --project scripts/fedora_flatpak_updater ruff check scripts/fedora_flatpak_updater tests/
  ```
  - Type Hints: Maintain explicit typing in `scripts/fedora_flatpak_updater/src/`.

---

## Security & System Permissions

The Flatpak manifest requests specific system bus permissions required for VPN operations:
- D-Bus Talk Permissions:
  - `org.freedesktop.secrets` (to store and retrieve credentials via Secret Service API)
  - `org.freedesktop.NetworkManager` (system bus, to monitor and manage host network status)
  - `org.freedesktop.login1` (system bus, DBus daemon reconnector)
  - `org.kde.StatusNotifierWatcher` (tray icon support)
- Filesystem Access:
  - `~/.cert/nm-openvpn/` and `~/.cert:create` (OpenVPN profile certificates)
  - `/var/log/journal:ro` (read-only system logs for debugging/support reporting)
- Devices:
  - `--device=all` (for FIDO2 USB hardware security keys during authentication)

When modifying `finish-args` in [`com.protonvpn.www.yml`](file:///home/slash/Development/com.protonvpn.www/com.protonvpn.www.yml), ensure permissions remain minimal and justified according to Flathub policies.

---

## Pull Request Guidelines

1. Ensure all changes to `com.protonvpn.www.yml` maintain valid manifest schema syntax (`https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json`).
2. Run pytest suite (`uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v`) and ensure all 49+ tests pass before committing Python script changes.
3. Verify that `ruff` checks pass cleanly on all modified Python files.
