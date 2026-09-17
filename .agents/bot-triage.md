# Automated Bot PR Triage (`flatpak-external-data-checker`)

When Flathub's automated checker creates a PR bumping `python-proton-vpn-api-core`, follow this checklist to bring CI to green:

## Checklist

1. **Synchronize `dependencies/protun`**:
   - Check the `protun` version pinned in `Cargo.lock` (reported by `scripts/generate_proton_platform_sources.py`).
   - Update `tag` and `commit` for `dependencies/protun` in [`com.protonvpn.www.yml`](../com.protonvpn.www.yml) to match.

2. **Regenerate Cargo Sources**:
   - Run `uv run --project scripts/fedora_flatpak_updater python3 scripts/generate_proton_platform_sources.py` to regenerate [`proton-vpn-platform-cargo-sources.json`](../proton-vpn-platform-cargo-sources.json).

3. **Re-anchor Patches**:
   - Verify that patches in [`patches/python-proton-vpn-api-core/`](../patches/python-proton-vpn-api-core/) (e.g. `fix-ip-path.patch`) apply cleanly against upstream. Upstream releases starting at `v5.6.20+` dropped `proton-vpn-local-agent` from `setup.py`, making `remove-local-agent-dep.patch` obsolete.

4. **Verify Cargo Build Features**:
   - Ensure `cargo build` in module `python-proton-vpn-api-core` includes `--no-default-features`.
   - Upstream includes `kill_switch` in default features (starting in `v5.6.20`), which requires `libmnl` and `libnftnl` (not present in Flatpak SDK). Only compile required features: `protun,nm_protun_auth_dialog,python,core,local_agent`.

5. **Preserve Dependency Build Order**:
   - If upstream added new requirements to `setup.py` (e.g. `dbus-fast`), ensure they are declared in [`pip-resources.python-proton-vpn-api-core.yaml`](../pip-resources.python-proton-vpn-api-core.yaml) so they are installed before `python-proton-vpn-api-core` compiles.
