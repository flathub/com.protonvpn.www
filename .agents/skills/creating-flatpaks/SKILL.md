---
name: creating-flatpaks
description: >-
  Authoring, maintaining, and debugging Flatpak packages (YAML/JSON) for Flathub,
  including offline Rust/Cargo and Python/pip vendoring, Git submodules, SDK extensions,
  and build validation.
---

# Creating and Maintaining Flatpak Packages for Flathub

This skill provides an end-to-end engineering runbook and technical reference for packaging, building, vendoring, debugging, and maintaining sandboxed desktop applications and CLI utilities for Flatpak and Flathub.

---

## 1. Overview & Core Philosophy

Flatpak provides an isolated, sandboxed application runtime across Linux distributions. Building applications for Flathub requires strict adherence to container isolation, deterministic offline compilation, and the principle of least privilege.

```
+-------------------------------------------------------------------------------+
| 1. DOWNLOAD PHASE (Online / Host Network)                                     |
|    - Parse manifest and sub-manifests (pip-resources.*.yaml, cargo-sources.json)|
|    - Fetch all source archives, git repositories, PyPI wheels, and crates     |
|    - Cryptographically verify sha256 checksums                                |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| 2. BUILD PHASE (Offline / Network Namespace Unshared: NO NETWORK)             |
|    - Mount base SDK (e.g., org.gnome.Sdk//50) and active SDK extensions        |
|    - Build modules sequentially (/run/build/<module-name>)                    |
|    - Install compiled binaries and assets to /app (${FLATPAK_DEST})           |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| 3. SANDBOXED RUNTIME (Host Isolation & Least Privilege)                       |
|    - Runtime mount (e.g., org.gnome.Platform//50) + /app filesystem           |
|    - Bubblewrap container with scoped finish-args (Wayland, D-Bus, Portals)   |
+-------------------------------------------------------------------------------+
```

### Core Packaging Pillars

1. **Deterministic Offline Builds**: Flathub build workers unshare the network namespace during compilation (`--unshare=network`). All source code, libraries, PyPI packages, and Cargo crates must be declared ahead of time with SHA256 checksums and vendored locally.
2. **Strict Sandboxing & Least Privilege**: Manifest `finish-args` must grant only the minimal permissions required for operation. Prefer modern XDG Desktop Portals over raw filesystem or unrestricted D-Bus access.
3. **Modular Manifest Design**: Decompose complex manifests into modular sub-manifests (`pip-resources.*.yaml`, `*-cargo-sources.json`) to keep specifications maintainable and compatible with automated updaters.
4. **SDK Extension Management**: Toolchains not bundled in the base SDK (e.g., specific Rust compiler versions, LLVM/Clang toolchains) must be mounted via `sdk-extensions` and activated per module.

---

## 2. Progressive Deep-Dive References

For detailed technical specifications, architecture diagrams, and specialized recipes, consult the dedicated reference documents:

- **[Manifest Architecture, SDK Extensions & Permissions Guide](references/manifest-structure-and-permissions.md)**:
  Full specification of manifest schemas (YAML vs JSON), `sdk-extensions` mounting, deep dive into container isolation flags (`finish-args`), D-Bus filtering, XDG Portals, and Flathub review standards.
- **[Cargo / Rust Offline Dependency Generation](references/cargo-offline-generation.md)**:
  Comprehensive guide for packaging standalone Rust apps and native extensions, running `flatpak-cargo-generator.py`, lockfile preparation, cargo config overrides, and offline crate vendoring.
- **[Python / Pip Offline Dependency Management](references/python-pip-offline.md)**:
  End-to-end blueprint for Python packaging with `flatpak-pip-generator`, modular `pip-resources.*.yaml` splitting, PyPI metadata tracking (`x-checker-data`), C/Rust native extensions (PyO3/Maturin), and wheel compilation.

---

## 3. End-to-End Packaging Runbook

Follow these structured steps when creating a new Flatpak package or maintaining an existing Flathub repository.

```
+---------------------------------------------------------------------------------+
| STEP 1: Manifest Initialization & SDK Selection                                 |
|         Choose Runtime/SDK (GNOME/Freedesktop/KDE) and configure base permissions|
+---------------------------------------------------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| STEP 2: Generate Offline Dependencies                                           |
|         Run flatpak-cargo-generator.py and/or flatpak-pip-generator             |
+---------------------------------------------------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| STEP 3: Configure Git Submodules, Nested Sources & Patches                      |
|         Structure source trees using 'dest' and manage local patches            |
+---------------------------------------------------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| STEP 4: Build Hybrid & Native Stacks                                            |
|         Wire PyO3/Maturin, C/Meson, and CMake native module dependencies        |
+---------------------------------------------------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| STEP 5: Local Build, Test & Interactive Debugging                               |
|         Execute flatpak-builder, inspect container, verify CLI & GUI            |
+---------------------------------------------------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
| STEP 6: Flathub Quality Linting & Upstream Maintenance                          |
|         Validate AppStream metainfo, run flatpak-builder-lint, configure checks |
+---------------------------------------------------------------------------------+
```

---

### Step 1: Manifest Initialization & SDK Selection

1. **Choose Base Runtime & SDK**:
   - **GNOME Platform** (`org.gnome.Platform` / `org.gnome.Sdk`): GTK3, GTK4, Libadwaita, Python PyGObject, GStreamer applications.
   - **Freedesktop Platform** (`org.freedesktop.Platform` / `org.freedesktop.Sdk`): Generic Linux apps, Electron, Qt/raw X11, CLI tools.
   - **KDE Platform** (`org.kde.Platform` / `org.kde.Sdk`): Qt5, Qt6, KDE Frameworks applications.

2. **Define Base Skeleton**:
   Create `<app-id>.yml` (e.g., `com.example.App.yml`) with schema header:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
app-id: com.example.App
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
command: app-binary

# Toolchain extensions (Rust, LLVM, etc.)
sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable

finish-args:
  # Display & IPC
  - --socket=wayland
  - --socket=fallback-x11
  - --share=ipc
  # Networking (if required)
  - --share=network
  # Audio (if required)
  - --socket=pulseaudio

cleanup:
  - /include
  - /lib/pkgconfig
  - /share/pkgconfig
  - /share/aclocal
  - /man
  - /share/man
  - '*.la'
  - '*.a'

modules: []
```

> [!TIP]
> For complete permission flag references and security review rules, see [references/manifest-structure-and-permissions.md](references/manifest-structure-and-permissions.md).

---

### Step 2: Generating Offline Dependencies

#### 2.1 Rust / Cargo Dependencies
When an application or Python C-extension relies on Rust crates:

1. **Obtain or Generate `Cargo.lock`**:
   If upstream does not ship `Cargo.lock` in the tarball, generate it locally from `Cargo.toml`:
   ```bash
   cargo generate-lockfile --manifest-path Cargo.toml
   ```

2. **Generate `cargo-sources.json`**:
   Use `flatpak-cargo-generator.py` from `flatpak-builder-tools`:
   ```bash
   python3 /path/to/flatpak-cargo-generator.py Cargo.lock -o cargo-sources.json
   ```

3. **Wire Cargo Sources into Module**:
   ```yaml
   modules:
     - name: rust-component
       buildsystem: simple
       build-options:
         append-path: /usr/lib/sdk/rust-stable/bin
         env:
           CARGO_HOME: /run/build/rust-component/cargo
           CARGO_NET_OFFLINE: 'true'
       build-commands:
         - cargo --offline fetch --manifest-path Cargo.toml --verbose
         - cargo --offline build --release --verbose
         - install -Dm755 target/release/app-binary /app/bin/app-binary
       sources:
         - type: git
           url: https://github.com/example/app.git
           tag: v1.0.0
           commit: 0123456789abcdef0123456789abcdef01234567
         - cargo-sources.json
   ```

> [!NOTE]
> For detailed instructions on Git dependencies, cargo configs, and workspace configurations, consult [references/cargo-offline-generation.md](references/cargo-offline-generation.md).

#### 2.2 Python / Pip Dependencies
When packaging Python applications or native Python extensions:

1. **Generate Resource Files**:
   Use `flatpak-pip-generator` to create YAML source blocks with `x-checker-data` automation:
   ```bash
   flatpak-pip-generator --checker-data --yaml --runtime='org.gnome.Sdk//50' \
     click dbus-fast tabulate -o pip-resources.my-module
   ```

2. **Split Monolithic Dependency Trees**:
   Divide large dependency graphs into domain-specific sub-manifests (e.g., `pip-resources.api-core.yaml`, `pip-resources.gui.yaml`).

3. **Install Offline with Pip**:
   ```yaml
   modules:
     - name: python-dependencies
       buildsystem: simple
       build-commands:
         - pip3 install --verbose --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} --no-build-isolation .
       sources:
         - pip-resources.my-module.yaml
   ```

> [!IMPORTANT]
> Always pass `--no-build-isolation` to `pip3 install`. In an offline sandbox, pip build isolation will attempt to create a temporary virtual environment and fetch build dependencies from PyPI, which fails immediately. See [references/python-pip-offline.md](references/python-pip-offline.md).

---

### Step 3: Handling Git Submodules & Nested Sources

When upstream repositories use submodules, vendored components, or custom patches:

```yaml
sources:
  # Primary repository
  - type: git
    url: https://github.com/example/main-repo.git
    tag: v2.4.0
    commit: abc1234def567890abcdef1234567890abcdef12

  # Submodule checked out into specific destination directory
  - type: git
    url: https://github.com/example/submodule-dep.git
    tag: v1.2.0
    commit: fedcba0987654321fedcba0987654321fedcba09
    dest: subprojects/submodule-dep

  # Custom patch to fix build paths or runtime behaviors
  - type: patch
    path: patches/fix-hardcoded-paths.patch

  # Desktop launcher or wrapper script
  - type: file
    path: com.example.App.desktop

  # AppStream metainfo
  - type: file
    path: com.example.App.metainfo.xml
```

---

### Step 4: Building Hybrid & Native Stacks

#### 4.1 Hybrid Python + Rust Extensions (PyO3 / Maturin / `setuptools-rust`)
Modules like `python3-bcrypt` or `python3-cryptography` require both Python build headers and the Rust toolchain:

```yaml
- name: python3-bcrypt
  buildsystem: simple
  build-options:
    append-path: /usr/lib/sdk/rust-stable/bin
    env:
      CARGO_HOME: /run/build/python3-bcrypt/cargo
      CARGO_NET_OFFLINE: 'true'
      PYO3_OFFLINE: '1'
  build-commands:
    - pip3 install --verbose --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} --no-build-isolation .
  sources:
    - type: archive
      url: https://files.pythonhosted.org/packages/.../bcrypt-4.3.0.tar.gz
      sha256: 0123456789abcdef...
      x-checker-data:
        type: pypi
        name: bcrypt
    - bcrypt-cargo-sources.json
```

#### 4.2 Native C / Meson / CMake Modules
Build supporting native C/C++ libraries prior to the main application:

```yaml
- name: libndp
  buildsystem: autotools
  config-opts:
    - --disable-static
    - --enable-shared
  sources:
    - type: archive
      url: http://libndp.org/files/libndp-1.9.tar.gz
      sha256: 1234567890abcdef...
      x-checker-data:
        type: anitya
        project-id: 13083
        url-template: http://libndp.org/files/libndp-$version.tar.gz
```

---

### Step 5: Local Build, Test, & Debugging

#### 5.1 Clean Build & Incremental Iteration
```bash
# Full clean build into local directory
flatpak-builder --force-clean build-dir com.example.App.yml

# Build up to a specific module for rapid debugging
flatpak-builder --keep-build-dirs --stop-at=target-module build-dir com.example.App.yml
```

#### 5.2 Local Installation & Execution
```bash
# Build and install directly to local user scope
flatpak-builder --force-clean --user --install build-dir com.example.App.yml

# Launch application
flatpak run com.example.App

# Pass CLI parameters or subcommands
flatpak run com.example.App status --verbose
```

#### 5.3 Interactive Debugging Inside the Container
When build steps fail or runtime permission errors occur:

```bash
# 1. Shell into the build container at the exact failure state
flatpak-builder --run build-dir com.example.App.yml sh

# Inside the build container:
$ cd /run/build/target-module
$ echo $PATH
$ pkg-config --cflags --libs libndp
$ cargo build --verbose

# 2. Shell into the installed runtime sandbox (with SDK debug tools)
flatpak run --command=sh --devel com.example.App

# Inside the runtime sandbox:
$ ls -la /app/bin /app/lib/python3.12/site-packages
$ busctl --user list | grep -E 'secrets|portal'
```

#### 5.4 Diagnostic Environment Flags
```bash
# Trace GIO and GTK debug messages
G_MESSAGES_DEBUG=all flatpak run com.example.App

# Trace Wayland display events
WAYLAND_DEBUG=1 flatpak run com.example.App

# Trace Secret Service / Keyring interactions
G_MESSAGES_DEBUG=all SECRET_DEBUG=1 flatpak run com.example.App
```

---

### Step 6: Flathub Quality, Linting & Upstream Maintenance

#### 6.1 AppStream Metadata Validation
Flathub requires valid AppStream metainfo placed in `/app/share/metainfo/<app-id>.metainfo.xml`:

```bash
# Validate metainfo file without internet access
appstream-util validate --nonet com.example.App.metainfo.xml
appstreamcli validate --no-net com.example.App.metainfo.xml
```

Ensure the metainfo includes:
- `<id>com.example.App</id>` matching manifest `app-id`.
- Valid `<name>`, `<summary>`, `<description>` with clean paragraphs.
- `<metadata_license>CC0-1.0</metadata_license>` or `FSFAP`.
- `<project_license>` specifying the application license.
- `<launchable type="desktop-id">com.example.App.desktop</launchable>`.
- `<releases>` containing at least the latest release tag and date.
- `<screenshots>` with 16:9 images hosted on public HTTPS URLs.

#### 6.2 Manifest & Repo Linting
Run `flatpak-builder-lint` to catch Flathub submission policy violations:

```bash
# Lint manifest
flatpak-builder-lint manifest com.example.App.yml

# Lint AppStream file
flatpak-builder-lint appstream com.example.App.metainfo.xml

# Lint built repository build directory
flatpak-builder-lint repo build-dir
```

#### 6.3 Automated Dependency Tracking
Flathub's build system runs [Flatpak-External-Data-Checker](https://github.com/flathub/flatpak-external-data-checker) to monitor and open pull requests for new upstream releases:

```yaml
sources:
  - type: archive
    url: https://github.com/example/app/archive/v1.5.0.tar.gz
    sha256: 0123456789abcdef...
    x-checker-data:
      type: json
      url: https://api.github.com/repos/example/app/releases/latest
      version-query: .tag_name | sub("^v"; "")
      url-query: '"https://github.com/example/app/archive/v" + $version + ".tar.gz"'
```

---

## 4. Quick Reference Cheatsheets

### Common CLI Commands

| Action | Command |
| :--- | :--- |
| **Clean Build** | `flatpak-builder --force-clean build-dir <manifest.yml>` |
| **User Install** | `flatpak-builder --force-clean --user --install build-dir <manifest.yml>` |
| **Incremental Stop** | `flatpak-builder --keep-build-dirs --stop-at=<module> build-dir <manifest.yml>` |
| **Build Shell** | `flatpak-builder --run build-dir <manifest.yml> sh` |
| **Runtime Shell** | `flatpak run --command=sh --devel <app-id>` |
| **Override Permission**| `flatpak run --socket=session-bus <app-id>` |
| **Show Permissions** | `flatpak info --show-permissions <app-id>` |
| **Show Dependencies** | `flatpak-builder --show-deps <manifest.yml>` |
| **Generate Cargo** | `python3 flatpak-cargo-generator.py Cargo.lock -o cargo-sources.json` |
| **Generate Pip** | `flatpak-pip-generator --checker-data --yaml --runtime='org.gnome.Sdk//50' <pkgs>` |
| **Lint Manifest** | `flatpak-builder-lint manifest <manifest.yml>` |
| **Validate Metainfo**| `appstreamcli validate --no-net <metainfo.xml>` |

---

### Essential `finish-args` Matrix

| Permission Category | Argument | Purpose / Flathub Review Guidance |
| :--- | :--- | :--- |
| **Display** | `--socket=wayland` | Native Wayland display socket (preferred). |
| | `--socket=fallback-x11` | X11 display socket fallback for legacy sessions. |
| | `--share=ipc` | Shared memory IPC (required for X11 shared memory buffers). |
| **Networking** | `--share=network` | Outbound and inbound internet connectivity. |
| **Audio** | `--socket=pulseaudio` | Audio playback and capture via PulseAudio/PipeWire. |
| **Filesystems** | `xdg-download` | Access to `~/Downloads` (read/write). |
| | `xdg-config/app:create` | Access to `~/.config/app`, creating directory if missing. |
| | `~/.cert:create` | Access to custom certificate directories. |
| | `/var/log/journal:ro` | Read-only access to host systemd journal for diagnostic logs. |
| **Session D-Bus** | `--talk-name=org.freedesktop.secrets` | Secret Service credential storage (GNOME Keyring/KWallet). |
| | `--talk-name=org.kde.StatusNotifierWatcher` | System tray icon notification area integration. |
| **System D-Bus** | `--system-talk-name=org.freedesktop.NetworkManager` | Monitor & control host network connections via NetworkManager. |
| | `--system-talk-name=org.freedesktop.login1` | Monitor system sleep/resume/shutdown states via logind. |
| **Devices** | `--device=dri` | GPU hardware acceleration (OpenGL / Vulkan). |
| | `--device=all` | Full `/dev` access (requires Flathub justification; e.g. FIDO2 keys). |

---

### Build Environment & Toolchain Variables

| Variable | Recommended Value | Context & Purpose |
| :--- | :--- | :--- |
| `CARGO_HOME` | `/run/build/<module>/cargo` | Isolates cargo state directory to current build container. |
| `CARGO_NET_OFFLINE` | `'true'` | Strictly enforces offline crate compilation. |
| `PYO3_OFFLINE` | `'1'` | Forces PyO3 native build scripts to avoid querying remote metadata. |
| `PIP_NO_INDEX` | `'true'` | Ensures pip refuses remote network queries. |
| `PIP_FIND_LINKS` | `'file://${PWD}'` | Instructs pip to resolve all wheels/sdists from working directory. |
| `PKG_CONFIG_PATH` | `/app/lib/pkgconfig:/app/share/pkgconfig:...` | Ensures compiler discovers installed `/app` native libraries. |
| `PYTHONPATH` | `/app/lib/python3.12/site-packages` | Ensures Python scripts can discover modules installed into `/app`. |

---

### Common Build Failures & Resolution Matrix

| Symptom / Error Message | Root Cause | Actionable Fix |
| :--- | :--- | :--- |
| `error: net: network unreachable` during `cargo build` | Cargo attempted to download an un-vendored crate. | Run `flatpak-cargo-generator.py` on the complete `Cargo.lock` and include `cargo-sources.json` in `sources`. |
| `ERROR: Could not find a version that satisfies the requirement` | Pip tried to fetch a missing dependency or build tool. | Run `flatpak-pip-generator` to include all transitive dependencies; pass `--no-build-isolation` to `pip3 install`. |
| `rustc: command not found` | Rust toolchain extension not mounted or not in `PATH`. | Add `org.freedesktop.Sdk.Extension.rust-stable` to `sdk-extensions` and set `append-path: /usr/lib/sdk/rust-stable/bin`. |
| `Package <name> was not found in pkg-config search path` | C dependency not built or pkg-config path missing. | Add required C library module before target module; verify `/app/lib/pkgconfig` is in `PKG_CONFIG_PATH`. |
| App crashes on startup with `KeyringLocked` or Secret Service error | Missing Secret Service D-Bus permission in `finish-args`. | Add `--talk-name=org.freedesktop.secrets` to `finish-args`. |
| App crashes under Wayland compositor | Missing Wayland socket or fallback display permission. | Ensure manifest includes both `--socket=wayland` and `--socket=fallback-x11`. |
