# Fedora Flatpak Updater: Design Limitations & Caveats

This document outlines the architectural limitations, edge cases, and design caveats of `fedora_flatpak_updater`.

---

## 1. Scope Exclusions & Proton-Owned Packages

- **Proton Components Ignored**: Packages owned by Proton (e.g., `proton-vpn-cli`, `proton-vpn-gtk-app`, `python-proton-core`, `python-proton-keyring-linux`, `python-proton-vpn-api-core`, `python-proton-vpn-local-agent`) are intentionally excluded. Any module starting with `proton` or flagged as Proton-owned is ignored because Fedora does not package internal Proton dependencies.
- **Explicitly Ignored Modules (`ignored: true`)**: Certain native dependencies mapped in `.fedora-tracked-modules.yaml` (such as `NetworkManager`, `NetworkManager-openvpn`, and `libnma`) are explicitly flagged with `ignored: true`. Automated updates to these core system network packages could break host integration, Flatpak D-Bus capabilities, or existing custom patches.

---

## 2. Unvalidated Dependency Pinning

- **No Pre-flight Build or Compatibility Tests**: The updater queries Bodhi and MDAPI for the target Fedora release version and updates manifest fields (`url`, `sha256`, `tag`, `commit`) directly. It does **not** test if custom patches (e.g., in `patches/`) apply cleanly or if API/ABI breaks occur.
- **CI Error Surface**: Compatibility breakages or patch failures are intended to be caught during the standard Flatpak build workflow in CI or PR code review, rather than preemptively blocked by the script.

---

## 3. PyPI Version Alignment

- **Fedora vs. PyPI Version Mismatch**: For `pypi` and `pypi-multi-wheel` recipes, the updater queries the PyPI JSON API (`https://pypi.org/pypi/<name>/<version>/json`) using the version reported by Fedora.
- **Downstream Distro Patches**: If Fedora packages a downstream patch version (e.g., `1.2.3.post1` or a version not published on PyPI), the PyPI lookup fails with a 404, causing the updater to skip updating that module for the cycle.

---

## 4. Native & Rust Cargo Dependencies

- **Rust Crate Source Generation**: Native Python modules requiring Rust compilation (e.g., `python3-bcrypt`) store offline Cargo dependency sources in files like `bcrypt-cargo-sources.json`.
- **Lockfile Extraction Dependency**: The updater attempts to download the module's PyPI `sdist`, extract `Cargo.lock`, and run `flatpak-cargo-generator.py`. If the PyPI source archive omits `Cargo.lock`, changes internal directory paths, or `flatpak-cargo-generator.py` fails, cargo extraction fails and manual intervention is required.

---

## 5. Repository Template Fragility

- **URL & Tag Template Assumptions**: `archive` and `git` recipes rely on static templates (`url_template`, `tag_template`, or `tag_pattern`) defined in `.fedora-tracked-modules.yaml`.
- **Upstream Structure Changes**: If an upstream project changes its tagging format (e.g., switching from `v1.2` to `1.2`) or migrates repository platforms (e.g., GitLab to GitHub), version resolution will fail until `.fedora-tracked-modules.yaml` is updated manually.

---

## 6. Disabling External Data Checker

- **Removal of `x-checker-data`**: For modules managed in `.fedora-tracked-modules.yaml`, the `x-checker-data` manifest annotations are removed. This prevents Flathub's `flatpak-external-data-checker` bot from attempting to update packages to upstream latest versions, which would conflict with Fedora-pinned versions.
