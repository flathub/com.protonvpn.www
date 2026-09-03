# Cargo / Rust Offline Dependency Generation for Flatpak

This reference guide details how to package Rust applications and Rust-backed native extensions for Flatpak and Flathub. It explains the mechanics of Flatpak's offline build isolation, how to generate and integrate offline Cargo dependency manifests, how to configure SDK extensions, and how to troubleshoot common build and vendoring issues.

---

## 1. Overview & Principles

### Flatpak Build Isolation
Flathub and `flatpak-builder` enforce strict network isolation during the **build phase**:
1. **Download Phase (Online)**: `flatpak-builder` parses the manifest, downloads all declared files, git repositories, archives, and dependencies, and verifies their cryptographic checksums (`sha256`).
2. **Build Phase (Offline)**: The build environment is unshared from the host network namespace. All network access is blocked (`--unshare=network`).

```
+-------------------------------------------------------------------------+
| DOWNLOAD PHASE (Host Network Enabled)                                   |
|   1. Manifest declared sources downloaded                               |
|   2. Crates fetched from static.crates.io & Git repos cloned            |
|   3. SHA256 integrity verified                                          |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| BUILD PHASE (Network Namespace Unshared: NO NETWORK)                    |
|   1. Sources unpacked to /run/build/<module-name>/                      |
|   2. Cargo reads vendored crates from local directory                   |
|   3. cargo build --release --offline compiles application               |
+-------------------------------------------------------------------------+
```

### Why Cargo Needs Manifest Generation
By default, the Cargo package manager downloads crate dependencies dynamically at build time over HTTPS from `crates.io`. In an offline Flatpak build container, any un-vendored dependency request fails immediately with a network resolution error.

To package Rust code for Flatpak:
- Every crate dependency in the dependency graph must be enumerated ahead of time.
- All crates must be downloaded during the Flatpak download phase as distinct source entries.
- Cargo must be configured to replace the default `crates.io` registry with a local vendored filesystem source.

The standard tool for generating these source declarations is `flatpak-cargo-generator.py` from [flatpak-builder-tools](https://github.com/flatpak/flatpak-builder-tools).

---

## 2. Lockfile Extraction & Preparation

Cargo uses `Cargo.lock` as the single source of truth for the exact versions, checksums, and git commits of all transitive dependencies.

### 2.1 Obtaining `Cargo.lock`

Depending on the upstream repository structure:
- **Upstream includes `Cargo.lock` in git or release tarballs**: Use the lockfile directly.
- **Upstream does not ship `Cargo.lock` (common in Rust library crates or Python sdists)**:
  Generate the lockfile locally before generating the Flatpak manifest:

```bash
# Clone the upstream repository at the exact target tag
git clone --depth 1 --branch v4.3.0 https://github.com/pyca/bcrypt.git /tmp/bcrypt
cd /tmp/bcrypt/src/_bcrypt

# Generate an exact lockfile matching upstream Cargo.toml dependencies
cargo generate-lockfile

# The resulting Cargo.lock is now ready for flatpak-cargo-generator.py
```

### 2.2 Workspaces and Multi-Crate Repositories
In a Rust workspace (defined by `[workspace]` in the root `Cargo.toml`), dependencies across all workspace members are resolved in a single top-level `Cargo.lock` located at the root of the workspace.

Always run `flatpak-cargo-generator.py` on the **root** `Cargo.lock` of the workspace to ensure all member dependencies are captured.

### 2.3 Lockfile Formats and Version Compatibility
Cargo lockfiles have evolved across Rust editions (V1, V2, V3, and V4):
- **V1 / V2**: Standard `[[package]]` entries with explicit `checksum` fields.
- **V3 / V4**: Introduces workspace tree resolver formats and direct dependency specifications.

`flatpak-cargo-generator.py` supports standard lockfile formats. If `flatpak-cargo-generator.py` fails to parse a modern lockfile, ensure you are using the latest version of `flatpak-builder-tools` and Python 3.10+.

---

## 3. Using `flatpak-cargo-generator.py`

`flatpak-cargo-generator.py` parses `Cargo.lock`, downloads crate metadata when necessary, and produces a JSON file containing Flatpak source entries for every dependency.

### 3.1 Command Syntax & Execution

```bash
# Basic usage
python3 flatpak-cargo-generator.py /path/to/Cargo.lock -o cargo-sources.json

# Real-world example (from Proton VPN bcrypt packaging)
wget https://raw.githubusercontent.com/pyca/bcrypt/refs/tags/4.3.0/src/_bcrypt/Cargo.lock -O /tmp/Cargo.lock
python3 /path/to/flatpak-builder-tools/cargo/flatpak-cargo-generator.py -o bcrypt-cargo-sources.json /tmp/Cargo.lock
```

### 3.2 Output Structure Deep Dive

The generated `cargo-sources.json` is a JSON array containing Flatpak source definitions:

```json
[
  {
    "type": "archive",
    "archive-type": "tar-gzip",
    "url": "https://static.crates.io/crates/autocfg/autocfg-1.4.0.crate",
    "sha256": "ace50bade8e6234aa140d9a2f552bbee1db4d353f69b8217bc503490fc1a9f26",
    "dest": "cargo/vendor/autocfg-1.4.0"
  },
  {
    "type": "inline",
    "contents": "{\"package\": \"ace50bade8e6234aa140d9a2f552bbee1db4d353f69b8217bc503490fc1a9f26\", \"files\": {}}",
    "dest": "cargo/vendor/autocfg-1.4.0",
    "dest-filename": ".cargo-checksum.json"
  },
  {
    "type": "inline",
    "contents": "[source.crates-io]\nreplace-with = \"vendored-sources\"\n\n[source.vendored-sources]\ndirectory = \"cargo/vendor\"\n",
    "dest": "cargo",
    "dest-filename": "config"
  }
]
```

### Key Source Components:
1. **Crate Archives (`type: archive`)**:
   - Downloads each `.crate` file (which is a gzip-compressed tar archive) directly from `https://static.crates.io/crates/<name>/<name>-<version>.crate`.
   - Extracts the crate directly into the target vendor directory: `cargo/vendor/<name>-<version>`.
   - Specifies exact `sha256` checksums for build integrity.

2. **Cargo Checksum Files (`type: inline`, `.cargo-checksum.json`)**:
   - Cargo verifies vendored crate integrity using `.cargo-checksum.json` in each crate directory.
   - The inline source creates this file with the expected crate hash: `{"package": "<sha256>", "files": {}}`.

3. **Cargo Configuration File (`type: inline`, `cargo/config` or `.cargo/config.toml`)**:
   - Injects the source-replacement configuration into `cargo/config` (or `.cargo/config`), pointing Cargo to the `cargo/vendor` directory.

4. **Git Repositories (for git dependencies)**:
   - When `Cargo.lock` contains a dependency sourced from git (e.g. `source = "git+https://github.com/..."`), `flatpak-cargo-generator.py` generates `type: git` source entries pinned to the exact commit hash:
   ```json
   {
     "type": "git",
     "url": "https://github.com/example/crate-repo.git",
     "commit": "a1b2c3d4e5f678901234567890abcdef12345678",
     "dest": "cargo/vendor/crate-repo"
   }
   ```

---

## 4. Manifest Integration

Integrating generated Cargo sources into a Flatpak manifest (`.yml` or `.json`) requires configuring the Rust SDK extension, build environment variables, and source inclusions.

### 4.1 Manifest Top-Level SDK Extension

Rust is provided in the Freedesktop and GNOME SDKs via SDK extensions. Declare the extension at the root of the manifest:

```yaml
id: com.example.App
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable
```

*(For nightly features or newer compiler requirements, `org.freedesktop.Sdk.Extension.rust-nightly` can be used instead).*

### 4.2 Module Build Options & Environment Variables

Inside the module that compiles Rust code:

```yaml
modules:
  - name: my-rust-module
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/my-rust-module/cargo
        CARGO_NET_OFFLINE: 'true'
        RUST_BACKTRACE: '1'
    buildsystem: simple
    build-commands:
      - cargo --offline fetch --manifest-path Cargo.toml || true
      - cargo build --release --offline --locked
      - install -Dm755 target/release/my-binary -t /app/bin/
    sources:
      - type: archive
        url: https://github.com/example/my-rust-app/archive/refs/tags/v1.0.0.tar.gz
        sha256: 8f8f...
      - cargo-sources.json
```

### Explanation of Environment Variables:
- `append-path: /usr/lib/sdk/rust-stable/bin`: Mounts the Rust toolchain (`cargo`, `rustc`, `rustfmt`) into the module's `$PATH`.
- `CARGO_HOME: /run/build/<module-name>/cargo`: Directs Cargo to use the directory populated with `cargo/config` and `cargo/vendor`. By placing `CARGO_HOME` in `/run/build/<module-name>/cargo`, Cargo automatically picks up `/run/build/<module-name>/cargo/config`.
- `CARGO_NET_OFFLINE: 'true'`: Forces Cargo to immediately fail if any internal command tries to initiate a network connection, preventing silent hanging or unexpected network calls.
- `RUST_BACKTRACE: '1'`: Provides complete stack traces if compilation or a build script (`build.rs`) panics.

### 4.3 Cargo Vendoring Directory Mapping

The generated `cargo/config` instructs Cargo how to redirect queries for `crates.io`:

```toml
[source.crates-io]
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "cargo/vendor"
```

If the project uses `.cargo/config.toml` in its own repository root, ensure it does not override or disable this source replacement.

---

## 5. Build Systems, Flags & Native Dependencies

### 5.1 Standard Build Invocations

#### Using `buildsystem: simple` with standard `cargo`
```yaml
buildsystem: simple
build-commands:
  # Install binary to /app/bin
  - cargo install --offline --locked --no-track --path . --root "${FLATPAK_DEST}"
```
- `--offline`: Prevents network requests.
- `--locked`: Requires that `Cargo.lock` matches `Cargo.toml` dependencies exactly without attempting resolution updates.
- `--no-track`: Prevents writing `.crates2.json` metadata tracking in `/app`.
- `--root "${FLATPAK_DEST}"`: Installs the compiled binaries directly to `${FLATPAK_DEST}/bin` (which is `/app/bin`).

#### Using `buildsystem: meson` (e.g., GNOME Rust Apps)
When using Meson with Rust (common for GTK4/Libadwaita apps):
```yaml
buildsystem: meson
build-options:
  append-path: /usr/lib/sdk/rust-stable/bin
  env:
    CARGO_HOME: /run/build/my-gnome-app/cargo
    CARGO_NET_OFFLINE: 'true'
config-opts:
  - -Dprofile=release
```
Ensure the upstream `meson.build` invokes `cargo` with `--offline` and `--locked`, or passes `CARGO_HOME` correctly.

### 5.2 Common Cargo Flags
- **Features**: `--no-default-features`, `--features "feature1,feature2"`
- **Binary Selection**: `--bin <binary-name>` (for repositories with multiple binaries)
- **Target Selection**: `--lib` or `--package <member-crate>`

### 5.3 Handling Native C/C++ System Libraries (`*-sys` Crates)

Many Rust crates link against system C libraries (e.g., `openssl-sys`, `libsqlite3-sys`, `dbus-sys`, `libndp-sys`, `zstandard-sys`).

#### 1. OpenSSL (`openssl-sys`)
By default, `openssl-sys` may try to download and build a vendored copy of OpenSSL. In Flatpak, use the SDK's system OpenSSL:
```yaml
build-options:
  env:
    OPENSSL_NO_VENDOR: '1'
```

#### 2. `pkg-config` Configuration
Rust `-sys` crates use `pkg-config` to locate C header and library files in `/app` and `/usr`.
```yaml
build-options:
  env:
    PKG_CONFIG_PATH: /app/lib/pkgconfig:/app/share/pkgconfig:/usr/lib/pkgconfig:/usr/share/pkgconfig
```

#### 3. `bindgen` and `libclang`
Crates that generate bindings dynamically using `bindgen` (e.g. interfacing with C headers) require Clang and LLVM from the SDK:
```yaml
build-options:
  env:
    LIBCLANG_PATH: /usr/lib
    BINDGEN_EXTRA_CLANG_ARGS: "-I/app/include -I/usr/include"
```

#### 4. GTK4 and Libadwaita Bindings (`gtk4-rs`, `libadwaita-rs`)
These crates bind to `libgtk-4.so` and `libadwaita-1.so` provided by `org.gnome.Sdk`. Ensure `runtime: org.gnome.Platform` and `sdk: org.gnome.Sdk` are used so all GObject-introspection and C headers are available.

---

## 6. Real-World Examples

### 6.1 Example 1: Standalone Rust CLI Application

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
id: org.example.RipgrepCli
runtime: org.freedesktop.Platform
runtime-version: '24.08'
sdk: org.freedesktop.Sdk
sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable
command: rg

finish-args:
  - --share=ipc
  - --filesystem=host:ro

modules:
  - name: ripgrep
    buildsystem: simple
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/ripgrep/cargo
        CARGO_NET_OFFLINE: 'true'
        RUST_BACKTRACE: '1'
    build-commands:
      - cargo install --offline --locked --no-track --path . --root "${FLATPAK_DEST}"
      # Install shell completions and manpages
      - install -Dm644 complete/_rg -t /app/share/zsh/site-functions/
      - install -Dm644 doc/rg.1 -t /app/share/man/man1/
    sources:
      - type: archive
        url: https://github.com/BurntSushi/ripgrep/archive/refs/tags/14.1.1.tar.gz
        sha256: 497537b049f5bed65306e9ec2ff68798bf1b38f8cf0fb5d7c92b23ad759b8be9
      - ripgrep-cargo-sources.json
```

---

### 6.2 Example 2: Python Native C/Rust Extension (PyO3 / `setuptools-rust` / `bcrypt`)

This is the exact production pattern used in the Proton VPN Flatpak manifest for packages with native Rust extensions (such as `bcrypt` and `cryptography`):

```yaml
  # Python bcrypt library with native Rust extension
  - name: python3-bcrypt
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/python3-bcrypt/cargo
        CARGO_NET_OFFLINE: 'true'
        RUST_BACKTRACE: '1'
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "bcrypt" --no-build-isolation
    modules:
      # Build dependencies required by setuptools-rust
      - name: python3-flit_core
        buildsystem: simple
        cleanup: ['*']
        build-commands:
          - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
            --prefix=${FLATPAK_DEST} "flit_core" --no-build-isolation
        sources:
          - type: file
            url: https://files.pythonhosted.org/packages/69/59/b6fc2188dfc7ea4f936cd12b49d707f66a1cb7a1d2c16172963534db741b/flit_core-3.12.0.tar.gz
            sha256: 18f63100d6f94385c6ed57a72073443e1a71a4acb4339491615d0f16d6ff01b2

      - name: python3-setuptools_rust
        buildsystem: simple
        cleanup: ['*']
        build-commands:
          - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
            --prefix=${FLATPAK_DEST} "setuptools_rust" --no-build-isolation
        sources:
          - type: file
            url: https://files.pythonhosted.org/packages/7d/31/f2289ce78b9b473d582568c234e104d2a342fd658cc288a7553d83bb8595/semantic_version-2.10.0.tar.gz
            sha256: bdabb6d336998cbb378d4b9db3a4b56a1e3235701dc05ea2690d9a997ed5041c
          - type: file
            url: https://files.pythonhosted.org/packages/68/ba/b31781d61bf9ee3c232a1d1160db11c11cdeae1d44e06c90723b25a8279f/setuptools_rust-1.13.0.tar.gz
            sha256: f2afcf4baeee689910ce49cfa8aad4e08cce72f417449bcc32891b8664fdc726
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/bb/5d/6d7433e0f3cd46ce0b43cd65e1db465ea024dbb8216fb2404e919c2ad77b/bcrypt-4.3.0.tar.gz
        sha256: 3a3fd2204178b6d2adcf09cb4f6426ffef54762577a7c9b54c159008cb288c18
      # Cargo sources generated via flatpak-cargo-generator.py
      - bcrypt-cargo-sources.json
```

**Why this works**:
- When `pip3 install --no-build-isolation "bcrypt"` executes, `setuptools-rust` triggers `cargo build` internally.
- `cargo` finds `CARGO_HOME: /run/build/python3-bcrypt/cargo` and reads `cargo/config` from `bcrypt-cargo-sources.json`.
- All native Rust dependencies compile offline against the vendored crate tarballs extracted into `cargo/vendor/`.

---

### 6.3 Example 3: GTK4 / Libadwaita Rust Desktop App with Meson

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
id: org.gnome.ExampleApp
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable
command: example-app

finish-args:
  - --share=ipc
  - --socket=fallback-x11
  - --socket=wayland
  - --device=dri

modules:
  - name: example-app
    buildsystem: meson
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/example-app/cargo
        CARGO_NET_OFFLINE: 'true'
    sources:
      - type: git
        url: https://gitlab.gnome.org/World/example-app.git
        tag: '1.2.0'
        commit: 'd2e8b0123456789abcdef0123456789abcdef012'
      - cargo-sources.json
```

---

## 7. Maintenance & Update Workflow

When upgrading a Rust application or Rust-backed dependency (e.g., upgrading `bcrypt` from `4.2.0` to `4.3.0`):

1. **Obtain the new lockfile**:
   ```bash
   NEW_VERSION="4.3.0"
   wget "https://raw.githubusercontent.com/pyca/bcrypt/refs/tags/${NEW_VERSION}/src/_bcrypt/Cargo.lock" -O /tmp/Cargo.lock
   ```

2. **Regenerate the cargo sources JSON**:
   ```bash
   python3 flatpak-cargo-generator.py /tmp/Cargo.lock -o bcrypt-cargo-sources.json
   ```

3. **Update the module tarball URL and SHA256 in the manifest**:
   Update `bcrypt-4.3.0.tar.gz` and its new sha256 checksum in `com.protonvpn.www.yml`.

4. **Verify the build locally**:
   ```bash
   flatpak-builder --force-clean --stop-at=python3-bcrypt build-dir com.protonvpn.www.yml
   ```

---

## 8. Troubleshooting & Common Failure Modes

### 8.1 Error: `error: no matching package named ... found` or `offline mode enabled`
**Cause**: A dependency in `Cargo.lock` was missing from `cargo-sources.json`, or the `Cargo.lock` used to generate the JSON did not match the source tarball's `Cargo.lock`.
**Solution**:
1. Check if the upstream source tarball contains a modified `Cargo.lock` or `Cargo.toml`.
2. Extract the source tarball, run `cargo generate-lockfile` inside the extracted source, and run `flatpak-cargo-generator.py` on that exact lockfile.

### 8.2 Error: `blocking waiting for file lock on package cache`
**Cause**: Multiple parallel build steps or modules sharing the same `CARGO_HOME` simultaneously.
**Solution**:
- Ensure `CARGO_HOME` is scoped to the module's unique build directory:
  ```yaml
  CARGO_HOME: /run/build/<module-name>/cargo
  ```

### 8.3 Error: `the package requires rustc 1.82 or newer`
**Cause**: The default SDK rust extension version is older than required by upstream crates.
**Solution**:
- Update `runtime-version` (e.g. GNOME 50 / Freedesktop 24.08).
- Or use `org.freedesktop.Sdk.Extension.rust-nightly` if bleeding-edge compiler features are required.

### 8.4 Checksum Failure in `.cargo-checksum.json`
**Cause**: A vendored crate archive was modified or corrupted, causing Cargo's internal verification to fail against `.cargo-checksum.json`.
**Solution**:
- Regenerate `cargo-sources.json` cleanly using `flatpak-cargo-generator.py`. Ensure the `sha256` in the `type: archive` entry matches the hash in `contents: "{\"package\": \"...\", \"files\": {}}"`.

### 8.5 PyO3 / Maturin Wheels Failing with `pip` Build Isolation
**Cause**: `pip` tries to create an isolated virtual environment and fetch build tools (`maturin`, `setuptools-rust`, `wheel`) from PyPI over the network.
**Solution**:
- Always supply `--no-build-isolation` to `pip3 install`.
- Declare `setuptools_rust`, `flit_core`, `maturin`, etc., as explicit nested or preceding modules in the Flatpak manifest.

### 8.6 Custom / Sparse Registries (e.g., Proton Sparse Registry)
**Cause**: Upstream crates rely on proprietary or custom sparse Cargo registries (e.g., `sparse+https://rust-registry.proton.me/index/`). Standard `flatpak-cargo-generator.py` hardcodes `https://static.crates.io/crates` for all non-git dependencies and fails to add source replacement for custom registries.
**Solution**:
1. **Correct Crate URLs & Checksums**: In `*-cargo-sources.json`, replace `static.crates.io` URLs for registry crates with their official endpoint (e.g. `https://rust-registry.proton.me/downloads/{crate}@{version}.crate`) and matching SHA256 checksums.
2. **Configure Cargo Source Replacement**: Ensure the embedded `cargo/config.toml` defines both the registries and source replacements:
   ```toml
   [source.vendored-sources]
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
   ```
   *(Note: Do not define separate `[source.proton]` tables if multiple registry names share the exact same sparse URL, as Cargo will reject duplicate source definitions).*
3. **Lockfile Alignment**: If upstream `Cargo.lock` contains stale internal URLs or old checksums, apply a patch to synchronize `Cargo.lock` with the public registry to satisfy `cargo build --locked`.

