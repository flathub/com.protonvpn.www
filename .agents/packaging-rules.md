# Critical Packaging & Build Rules

Key build constraints and architectural rules for packaging Proton VPN on Flatpak.

## 1. Deterministic Offline Builds
- Flathub build workers disable network access during compilation (`--unshare=network`).
- Every remote archive, git repository, PyPI wheel, and Cargo crate must be declared in the manifest or sub-manifests with valid SHA256 checksums.

## 2. Rust & Sparse Registry Vendoring (`proton-vpn-platform`)
- `python-proton-vpn-api-core` relies on Proton's sparse registry (`sparse+https://rust-registry.proton.me/index/`).
- Standard `flatpak-cargo-generator.py` points non-git crates to `static.crates.io`. Proton crates must explicitly use `https://rust-registry.proton.me/downloads/{crate}@{version}.crate` in [`proton-vpn-platform-cargo-sources.json`](../proton-vpn-platform-cargo-sources.json).
- The embedded `cargo/config.toml` must replace `sparse+https://rust-registry.proton.me/index/` with `vendored-sources` and define both `[registries.proton]` and `[registries.proton_public]`.
- Use `uv run --project scripts/fedora_flatpak_updater python3 scripts/generate_proton_platform_sources.py` to regenerate [`proton-vpn-platform-cargo-sources.json`](../proton-vpn-platform-cargo-sources.json).
- Always pass `--no-default-features` during cargo build to avoid compiling host-level nftables killswitch features (`mnl-sys` / `nftnl-sys`).

## 3. Python Pip Offline Builds
- Always pass `--no-build-isolation` to `pip3 install` to prevent pip from querying PyPI for build environments.
- Build-time dependencies (`setuptools_rust`, `flit_core`, `skbuild`, `meson`) must be installed as preceding or nested modules.
- Strip removed or obsolete dependencies via patches in [`patches/`](../patches/).

## 4. Security & System Permissions
- Manifest `finish-args` must remain minimal and compliant with Flathub standards.
- Required D-Bus interfaces:
  - `org.freedesktop.secrets` (keyring)
  - `org.freedesktop.NetworkManager` (system bus for VPN connections & killswitch)
  - `org.freedesktop.login1` (daemon reconnect upon sleep/wake)
  - `org.kde.StatusNotifierWatcher` (tray icon integration)
