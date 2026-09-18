# Proton VPN Flatpak (`com.protonvpn.www`)

Flathub package build specifications for Proton VPN, packaging the GTK Desktop application and CLI tools using GNOME Platform 50 (`org.gnome.Platform//50` / `org.gnome.Sdk//50`).

## Universal Rules

- **Always use `uv` for Python**: Run all Python scripts, tests, and linters using `uv` (e.g. `uv run --project scripts/fedora_flatpak_updater ...`). Never execute bare `python3` or direct `.venv/bin/` binaries.
- **Deterministic Offline Builds**: Flathub build workers disable network during compilation (`--unshare=network`). All crates and wheels must be pre-vendored and declared.

## Quick Reference Commands

- **Build Package**: `flatpak run --filesystem="$PWD" org.flatpak.Builder --force-clean build-dir com.protonvpn.www.yml`
- **Download Check**: `flatpak-builder --download-only build-dir com.protonvpn.www.yml`
- **Run Test Suite**: `uv run --project scripts/fedora_flatpak_updater pytest tests/ -v`
- **Lint Python Code**: `uv run --project scripts/fedora_flatpak_updater ruff check scripts/fedora_flatpak_updater tests/`
- **Regenerate Cargo Sources**: `uv run --project scripts/fedora_flatpak_updater python3 scripts/generate_proton_platform_sources.py`

## Detailed Instructions & References

- [Bot PR Triage Guide](.agents/bot-triage.md): Checklist for triaging `flatpak-external-data-checker` updates.
- [Critical Packaging Rules](.agents/packaging-rules.md): Offline crate vendoring, `--no-default-features`, pip wheels, and D-Bus sandboxing.
- [Creating Flatpaks Runbook](.agents/skills/creating-flatpaks/SKILL.md): Complete packaging manual.
- [Cargo / Rust Vendoring Reference](.agents/skills/creating-flatpaks/references/cargo-offline-generation.md)
- [Python / Pip Offline Reference](.agents/skills/creating-flatpaks/references/python-pip-offline.md)
