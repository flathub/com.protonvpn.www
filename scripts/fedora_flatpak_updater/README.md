# fedora_flatpak_updater

Pins every third-party dependency in `com.protonvpn.www.yml` and its
`pip-resources.*.yaml` files to the version shipped in Fedora's latest
stable release. See `docs/superpowers/specs/2026-07-01-fedora-stable-flatpak-deps-design.md`
for the full design.

## Setup

From the repository root:

    uv sync --project scripts/fedora_flatpak_updater

This creates `scripts/fedora_flatpak_updater/.venv` and installs runtime +
dev dependencies from `uv.lock`.

## Usage

    uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --dry-run
    uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --only python3-idna --only libndp

## Rebuilding the mapping file from scratch

    uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.migrate > /tmp/draft.yaml

Review the draft, hand-fix anything flagged `_needs_manual_fix`, and merge
it into `.fedora-tracked-modules.yaml`.

## Running tests

    uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
