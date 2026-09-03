# Flatpak Manifest Structure, SDK Extensions, and Permissions Reference

This reference guide provides an exhaustive technical specification for designing, structuring, and securing Flatpak manifests for Flathub packages. It details the manifest schema, build lifecycle, SDK extension activation, sandboxing permission architecture (`finish-args`), Flathub security review standards, and production-grade manifest blueprints.

---

## Table of Contents
1. [Manifest Architecture & Schema Overview](#1-manifest-architecture--schema-overview)
   - [YAML vs. JSON Format Standards](#11-yaml-vs-json-format-standards)
   - [Schema Definition & Language Server Integration](#12-schema-definition--language-server-integration)
   - [Top-Level Properties Reference](#13-top-level-properties-reference)
   - [Module Specification & Build Systems](#14-module-specification--build-systems)
   - [Source Types & Properties](#15-source-types--properties)
2. [SDK Extensions Management](#2-sdk-extensions-management)
   - [Extension Architecture & Mount Mechanics](#21-extension-architecture--mount-mechanics)
   - [Declaration in `sdk-extensions`](#22-declaration-in-sdk-extensions)
   - [Activating Extensions Inside Modules](#23-activating-extensions-inside-modules)
   - [Multi-Extension Configurations & Runtime Matching](#24-multi-extension-configurations--runtime-matching)
   - [SDK Extension Cleanup](#25-sdk-extension-cleanup)
3. [Sandboxing & `finish-args` Deep Dive](#3-sandboxing--finish-args-deep-dive)
   - [Display & GUI Sockets](#31-display--gui-sockets)
   - [Audio & Media Sockets](#32-audio--media-sockets)
   - [Peripheral & IPC Sockets](#33-peripheral--ipc-sockets)
   - [Filesystem Permissions & Modifiers](#34-filesystem-permissions--modifiers)
   - [D-Bus Mediation (Session & System Bus)](#35-d-bus-mediation-session--system-bus)
   - [Device & Subsystem Access](#36-device--subsystem-access)
4. [Flathub Quality Standards & Least Privilege](#4-flathub-quality-standards--least-privilege)
   - [The Principle of Least Privilege & XDG Portals](#41-the-principle-of-least-privilege--xdg-portals)
   - [Flathub Sensitive Permission Policy & Justifications](#42-flathub-sensitive-permission-policy--justifications)
   - [AppStream Metainfo Integration & Validation](#43-appstream-metainfo-integration--validation)
5. [Real-World Manifest Blueprints & Auditing](#5-real-world-manifest-blueprints--auditing)
   - [Blueprint 1: GNOME 50 / GTK4 / Libadwaita Desktop App](#51-blueprint-1-gnome-50--gtk4--libadwaita-desktop-app)
   - [Blueprint 2: System / Network Utility (Proton VPN Architecture)](#52-blueprint-2-system--network-utility-proton-vpn-architecture)
   - [Permission Auditing & Verification Tooling](#53-permission-auditing--verification-tooling)

---

## 1. Manifest Architecture & Schema Overview

A Flatpak manifest is a declarative build recipe parsed by `flatpak-builder`. It defines the application identifier, base runtime, development SDK, required system permissions, compilation flags, and the ordered tree of modules that comprise the final application payload.

### 1.1 YAML vs. JSON Format Standards

`flatpak-builder` natively supports manifests written in either **YAML** (`.yaml`, `.yml`) or **JSON** (`.json`).

| Feature | YAML Format | JSON Format |
| :--- | :--- | :--- |
| **Standard File Extension** | `<app-id>.yml` or `<app-id>.yaml` | `<app-id>.json` |
| **Comments** | Supported (`# comment`) | Unsupported (requires non-standard hacks) |
| **Multiline Strings** | Supported (`|`, `>`) | Unsupported (requires `\n` escaping) |
| **Readability** | High; compact 2-space indentation | Verbose; requires braces and trailing commas |
| **External File Includes** | Full support (`shared-modules/...`, `pip-resources.*.yaml`) | Full support (`shared-modules/...`) |
| **Flathub Preference** | **Standard & Recommended** for primary manifests | Recommended for shared sub-modules / cargo lists |

#### Formatting Rules for YAML Manifests:
- Use consistent **2-space indentation** (do not use tabs).
- Enforce strings containing version numbers or special characters (e.g. `'50'`, `'24.08'`) as quoted strings to avoid YAML type coercion to numbers or dates.
- Keep module names kebab-case or lower-snake-case matching upstream conventions.
- Retain upstream metadata annotations such as `x-checker-data`.

### 1.2 Schema Definition & Language Server Integration

To enable real-time validation, autocomplete, and error diagnostics in modern editors (VS Code, Neovim, Zed, Emacs), include the Flatpak manifest JSON Schema header on line 1 of the manifest:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json

id: org.example.App
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
command: app-binary
finish-args:
  - --socket=wayland
  - --socket=fallback-x11
modules: []
```

### 1.3 Top-Level Properties Reference

The root object of the manifest configures the global build environment, runtime linkages, and execution sandbox.

```
+-----------------------------------------------------------------------------------+
| Flatpak Manifest (Top-Level)                                                      |
|                                                                                   |
|  [Identity]          id: com.protonvpn.www                                        |
|  [Runtime Stack]     runtime: org.gnome.Platform, runtime-version: '50'           |
|                      sdk: org.gnome.Sdk                                           |
|  [SDK Extensions]    sdk-extensions: [ org.freedesktop.Sdk.Extension.rust-stable ]|
|  [Entrypoint]        command: protonvpn-app                                       |
|  [Sandbox]           finish-args: [ --socket=wayland, --share=network, ... ]      |
|  [Global Build Opts] build-options: { cflags: "...", env: { ... } }               |
|  [Global Cleanup]    cleanup: [ "/include", "*.la", "/lib/pkgconfig" ]            |
|  [Modules Tree]      modules: [ module-1, module-2, ..., main-app-module ]        |
+-----------------------------------------------------------------------------------+
```

#### Complete Top-Level Property Reference Table:

| Property | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `id` / `app-id` | `string` | **Yes** | Unique reverse-DNS application ID (e.g., `com.protonvpn.www`, `org.gnome.Calculator`). Must match the desktop file and AppStream metainfo name. |
| `runtime` | `string` | **Yes** | Application runtime ID (e.g., `org.gnome.Platform`, `org.freedesktop.Platform`, `org.kde.Platform`). |
| `runtime-version` | `string` | **Yes** | Version branch of the runtime and SDK (e.g., `'50'`, `'24.08'`, `'6.8'`). Must be enclosed in quotes. |
| `sdk` | `string` | **Yes** | Development SDK matching the runtime (e.g., `org.gnome.Sdk`, `org.freedesktop.Sdk`, `org.kde.Sdk`). |
| `command` | `string` | **Yes** | Primary executable binary or wrapper script located in `/app/bin/` executed when `flatpak run <id>` is called. |
| `finish-args` | `array[string]` | **Yes** | Command-line arguments passed to `flatpak build-finish` to define the runtime sandbox boundary and host permissions. |
| `modules` | `array[object\|string]`| **Yes** | Sequential list of module objects or paths to included module files (`.json` or `.yaml`) built in order. |
| `sdk-extensions` | `array[string]` | No | List of SDK extension IDs required during build time (e.g., `org.freedesktop.Sdk.Extension.rust-stable`). |
| `build-options` | `object` | No | Global compiler flags, environment variables, and search path overrides applied to all modules. |
| `cleanup` | `array[string]` | No | Global filename and path glob patterns removed from `/app` after all modules are built (e.g., header files, static libraries). |
| `cleanup-commands` | `array[string]` | No | Arbitrary shell commands executed inside the container during final cleanup phase. |
| `branch` | `string` | No | The Flatpak branch name for the built package (defaults to `stable` on Flathub). |
| `tags` | `array[string]` | No | Tags describing build metadata (e.g., `["nightly"]`). |
| `separate-locales` | `boolean` | No | When `true` (default), translations are extracted into a separate `.Locale` extension to reduce base download size. |
| `copy-icon` | `boolean` | No | When `true`, automatically extracts application icons from the source directories into the exported export root. |

#### Global `build-options` Configuration:
```yaml
build-options:
  cflags: "-O2 -g -fstack-protector-strong"
  cxxflags: "-O2 -g -fstack-protector-strong"
  env:
    V: "1"
    PYTHONNOUSERSITE: "1"
  append-path: "/usr/lib/sdk/rust-stable/bin"
  prepend-path: "/app/bin"
  append-ld-library-path: "/app/lib"
  strip: true
  no-debuginfo: false
```

---

### 1.4 Module Specification & Build Systems

Modules represent isolated compilation units. They are executed sequentially in the order declared in the manifest. All module artifacts are installed directly into `/app` (`${FLATPAK_DEST}`).

```yaml
modules:
  - name: libsodium
    buildsystem: autotools
    config-opts:
      - --disable-static
      - --enable-shared
    sources:
      - type: archive
        url: https://download.libsodium.org/libsodium/releases/libsodium-1.0.20-RELEASE.tar.gz
        sha256: ebb60a8be0160204a37b38eb15e523f20f04c644efb4d24174d8ac85474e2d45
    cleanup:
      - /include
      - /lib/pkgconfig
      - "*.la"
```

#### Module Property Reference:

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | `string` | *Required* | Name of the module. Used for build directories (`/run/build/<name>`) and logs. |
| `buildsystem` | `string` | `autotools` | Build system driver: `simple`, `meson`, `cmake`, `cmake-ninja`, `autotools`, `qmake`. |
| `sources` | `array[object]` | `[]` | List of source archives, git repositories, files, or scripts fetched and placed in the build directory. |
| `config-opts` | `array[string]` | `[]` | Flags passed to the configuration command (e.g., `./configure`, `meson setup`, `cmake`). |
| `build-commands` | `array[string]` | `[]` | Shell commands executed when `buildsystem: simple` is used, or custom compilation phases. |
| `post-install` | `array[string]` | `[]` | Shell commands executed immediately after module installation finishes. |
| `build-options` | `object` | `{}` | Module-scoped overrides for environment variables, compiler flags, and search paths. |
| `cleanup` | `array[string]` | `[]` | Glob patterns of files to remove from `/app` after this specific module completes. |
| `ensure-writable`| `array[string]` | `[]` | Files or directories in `/app` made writable during module build steps. |
| `modules` | `array[object]` | `[]` | Nested sub-modules compiled recursively before the parent module build starts. |

#### Supported `buildsystem` Types:

1. **`simple`**: No automated configure/make/install harness. `flatpak-builder` executes the exact list of shell commands declared in `build-commands`. Essential for Python `pip` installs, binary repackaging, and custom shell scripts.
2. **`meson`**: Runs `meson setup _flatpak_build --prefix=/app ${config-opts}`, `ninja -C _flatpak_build`, and `ninja -C _flatpak_build install`.
3. **`cmake` / `cmake-ninja`**: Runs `cmake -B _flatpak_build -DCMAKE_INSTALL_PREFIX:PATH=/app ${config-opts}`, followed by `make` or `ninja` compilation and installation.
4. **`autotools`**: Runs `./configure --prefix=/app ${config-opts}`, `make -j${FLATPAK_BUILDER_N_JOBS}`, and `make install`.
5. **`qmake`**: Invokes `qmake PREFIX=/app ${config-opts}`, `make`, and `make install`.

---

### 1.5 Source Types & Properties

Flatpak downloads all sources ahead-of-time during the online download phase, verifying cryptographic hashes.

```yaml
sources:
  # 1. Archive Source (tar.gz, tar.xz, tar.bz2, zip)
  - type: archive
    url: https://github.com/example/app/releases/download/v1.0.0/app-1.0.0.tar.gz
    sha256: 3a2c5e...
    strip-components: 1
    dest: subfolder-name

  # 2. Git Repository
  - type: git
    url: https://github.com/example/libfoo.git
    tag: v2.1.0
    commit: e4d909c290d0fb1ca068ffaddf22cbd038f61406

  # 3. Static File / Wheel
  - type: file
    url: https://files.pythonhosted.org/packages/.../package-1.0-py3-none-any.whl
    sha256: d8e20...
    dest-filename: package-1.0-py3-none-any.whl

  # 4. Inline Script / Shell
  - type: script
    commands:
      - exec python3 /app/lib/python3.12/site-packages/my_app/main.py "$@"
    dest-filename: my-app-wrapper

  # 5. Patch
  - type: patch
    path: fix-hardcoded-paths.patch
    strip-components: 1

  # 6. Local Directory / File
  - type: dir
    path: ../local-source-tree

  # 7. Inline Content
  - type: inline
    contents: |
      [Desktop Entry]
      Type=Application
      Name=Custom Tool
      Exec=custom-tool
      Icon=com.example.App
    dest-filename: com.example.App.desktop
```

#### Source Types Comparison:

| Source Type | Key Properties | Purpose & Usage Notes |
| :--- | :--- | :--- |
| `archive` | `url`, `sha256`, `strip-components`, `dest` | Source tarballs and zip archives. Standard for upstream C/C++/Rust libraries. |
| `git` | `url`, `tag`, `commit`, `branch` | Git repositories. Always pin to an immutable `commit` hash for reproducibility. |
| `file` | `url`, `sha256`, `dest-filename`, `dest` | Standalone files, Python `.whl` wheels, prebuilt assets. |
| `script` | `commands`, `dest-filename` | Generates an executable shell script in the build directory. |
| `inline` | `contents`, `dest-filename` | Generates a static text configuration or desktop entry file. |
| `patch` | `path` (local) or `url` (remote), `strip-components` | Applies unified diff patches using `patch -p<strip-components>`. |
| `dir` | `path`, `dest` | Copies local repository directories into the build sandbox. |
| `extra-data` | `url`, `sha256`, `size`, `filename` | Proprietary/unredistributable binaries downloaded at client install time. |

---

## 2. SDK Extensions Management

Flatpak SDK extensions provide isolated toolchains (Rust, LLVM/Clang, OpenJDK, Go, Vala, Mono) without bloating the base runtime image.

```
Host Filesystem -> /usr/lib/sdk/<extension-name>/ (Mounted during build)
                     ├── bin/ (Compilers: rustc, cargo, clang, javac)
                     ├── lib/ (Libraries, LLVM runtime, Rust stdlib)
                     └── include/ (Header files)
```

### 2.1 Extension Architecture & Mount Mechanics

When `flatpak-builder` encounters an entry in `sdk-extensions`, it mounts the extension filesystem from the host into `/usr/lib/sdk/<extension-name>/` inside the build container. SDK extensions are build-time only: they are never included in the exported `/app` runtime unless explicitly copied or referenced.

### 2.2 Declaration in `sdk-extensions`

Declare required extensions at the manifest root under `sdk-extensions`:

```yaml
id: com.protonvpn.www
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk

sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable
  - org.freedesktop.Sdk.Extension.llvm18
  - org.freedesktop.Sdk.Extension.openjdk21
```

#### Common SDK Extension Identifiers:

| Extension Identifier | Contained Toolchains | Primary Use Cases |
| :--- | :--- | :--- |
| `org.freedesktop.Sdk.Extension.rust-stable` | `rustc`, `cargo`, `rust-std` | Rust applications, PyO3/maturin/setuptools-rust native modules. |
| `org.freedesktop.Sdk.Extension.llvm18` | `clang`, `clang++`, `llvm-config`, `lld` | Modern C++20 builds, Clang plugins, Rust bindgen. |
| `org.freedesktop.Sdk.Extension.openjdk21` | `javac`, `java`, `jar`, Maven/Gradle | Java desktop applications and build tools. |
| `org.freedesktop.Sdk.Extension.golang` | `go`, Go toolchain | Go applications and utilities. |
| `org.freedesktop.Sdk.Extension.vala-extra` | `valac`, Vala bindings | Advanced Vala / GObject development. |
| `org.freedesktop.Sdk.Extension.node20` | `node`, `npm`, `yarn` | Electron / Node.js web asset builds. |

---

### 2.3 Activating Extensions Inside Modules

Declaring an extension in `sdk-extensions` only mounts it into `/usr/lib/sdk/<extension>/`. To make compilers and libraries visible during compilation, configure module-level `build-options`:

```yaml
modules:
  - name: python3-bcrypt
    buildsystem: simple
    build-options:
      # Prepend or append the extension binaries to PATH
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/python3-bcrypt/cargo-home
        RUSTUP_HOME: /run/build/python3-bcrypt/rustup-home
        # Set LLVM / Clang environment if needed
        CC: /usr/lib/sdk/llvm18/bin/clang
        CXX: /usr/lib/sdk/llvm18/bin/clang++
        PKG_CONFIG_PATH: /app/lib/pkgconfig:/usr/lib/pkgconfig:/usr/lib/sdk/llvm18/lib/pkgconfig
    build-commands:
      - pip3 install --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} . --no-build-isolation
    sources:
      - type: archive
        url: https://files.pythonhosted.org/packages/.../bcrypt-4.3.0.tar.gz
        sha256: 4b297...
```

#### Key `build-options` for SDK Extension Control:
- `append-path` / `prepend-path`: Injects `/usr/lib/sdk/<extension>/bin` into the shell `$PATH`.
- `append-ld-library-path` / `prepend-ld-library-path`: Injects `/usr/lib/sdk/<extension>/lib` into dynamic linker search paths.
- `append-pkg-config-path`: Adds extension `.pc` files to `$PKG_CONFIG_PATH`.
- `env`: Exports necessary environment variables such as `JAVA_HOME: /usr/lib/sdk/openjdk21/jvm/openjdk-21` or `CARGO_HOME`.

---

### 2.4 Multi-Extension Configurations & Runtime Matching

When combining multiple SDK extensions (e.g., Rust + LLVM + OpenJDK):

```yaml
sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable
  - org.freedesktop.Sdk.Extension.llvm18

modules:
  - name: native-hybrid-module
    buildsystem: meson
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin:/usr/lib/sdk/llvm18/bin
      append-ld-library-path: /usr/lib/sdk/llvm18/lib
      env:
        CC: /usr/lib/sdk/llvm18/bin/clang
        CXX: /usr/lib/sdk/llvm18/bin/clang++
        LIBCLANG_PATH: /usr/lib/sdk/llvm18/lib
```

> [!IMPORTANT]
> **Runtime Branch Matching**: SDK extensions must match the base runtime version branch. If `runtime-version: '50'` (GNOME 50 based on Freedesktop 24.08), `flatpak-builder` automatically requests the `50` or `24.08` branch of `org.freedesktop.Sdk.Extension.*`.

### 2.5 SDK Extension Cleanup

Because SDK extensions are mounted into `/usr/lib/sdk/` during the build container lifecycle, they are automatically detached when `flatpak-builder` packages the application. They leave zero footprint in the final `/app` directory unless files were explicitly copied into `/app`.

---

## 3. Sandboxing & `finish-args` Deep Dive

The `finish-args` section defines the security boundary and hardware access rules for the application. Each argument configures the Flatpak bubblewrap container and `xdg-dbus-proxy`.

```yaml
finish-args:
  # Display & Graphics
  - --socket=wayland
  - --socket=fallback-x11
  - --device=dri
  - --share=ipc
  # Networking
  - --share=network
  # Audio
  - --socket=pulseaudio
  # D-Bus IPC
  - --talk-name=org.freedesktop.secrets
  - --system-talk-name=org.freedesktop.NetworkManager
  - --own-name=org.example.App
  # Filesystem
  - --filesystem=xdg-download
  - --filesystem=~/.cert/nm-openvpn:create
  - --filesystem=/var/log/journal:ro
```

---

### 3.1 Display & GUI Sockets

GUI applications require display server sockets to communicate with Wayland compositors and X11 display servers.

```
                      +-----------------------------+
                      | Application in Flatpak      |
                      +-----------------------------+
                                     |
                    +----------------+----------------+
                    |                                 |
                    v                                 v
          [--socket=wayland]               [--socket=fallback-x11]
                    |                                 |
           (Active Wayland Session)          (Active X11 Session)
                    v                                 v
         /run/user/$UID/wayland-0              /tmp/.X11-unix/X0
          (Fully Isolated Surface)        (Legacy X11 Window System)
```

#### Display Socket Directives:

| Argument | Description | Security Impact & Guidance |
| :--- | :--- | :--- |
| `--socket=wayland` | Grants access to the Wayland display socket (`/run/user/$UID/wayland-0`). | **Secure**. Wayland enforces client isolation, preventing screen scraping or keylogging between apps. |
| `--socket=fallback-x11` | Grants access to X11 (`/tmp/.X11-unix/X0`) **only if** Wayland is not available. | **Recommended standard**. Enables Wayland on modern compositors while preserving backwards compatibility without granting unconditional X11 access. |
| `--socket=x11` | Unconditionally opens the X11 display socket on both Wayland and X11 sessions. | **Discouraged on Flathub**. On Wayland, this forces Xwayland and allows the app to sniff keystrokes and windows of other Xwayland clients. |
| `--share=ipc` | Shares the Inter-Process Communication (IPC) namespace with the host. | **Required for X11 MIT-SHM** shared memory extension to avoid GUI rendering performance degradation. |

---

### 3.2 Audio & Media Sockets

| Argument | Target System | Description & Usage |
| :--- | :--- | :--- |
| `--socket=pulseaudio` | PulseAudio / PipeWire Pulse | Connects to `/run/user/$UID/pulse/native`. Enables audio playback and microphone capture. On modern systems, this communicates with PipeWire's PulseAudio emulation layer. |
| `--socket=pipewire` | Native PipeWire (Direct) | Direct socket connection to PipeWire. Note: Most portal-aware applications should use the XDG Desktop Camera/ScreenCast portal rather than raw socket access. |

---

### 3.3 Peripheral & IPC Sockets

| Argument | Socket Subsystem | Description & Usage Notes |
| :--- | :--- | :--- |
| `--socket=cups` | CUPS Printing Subsystem | Grants access to `/run/cups/cups.sock` for legacy direct print queue spooling. Modern apps should prefer the XDG Print Portal. |
| `--socket=pcsc` | PC/SC Smart Card Subsystem | Grants access to `/run/pcscd/pcscd.comm` for hardware smart cards, PKCS#11 tokens, and cryptographic card readers. |
| `--socket=ssh-auth` | SSH Agent Forwarding | Forwards `SSH_AUTH_SOCK` into the container for Git/SSH operations using host identities. |
| `--socket=gpg-agent` | GnuPG Agent Socket | Forwards GPG keyring sockets for cryptographic signing and decryption. |

---

### 3.4 Filesystem Permissions & Modifiers

Flatpak isolates the host filesystem. Applications always have exclusive read-write access to their private persistent sandbox directories:
- `XDG_CONFIG_HOME` -> `~/.var/app/<app-id>/config/`
- `XDG_DATA_HOME` -> `~/.var/app/<app-id>/data/`
- `XDG_CACHE_HOME` -> `~/.var/app/<app-id>/cache/`

Additional host filesystem access is explicitly granted using `--filesystem=...`.

#### Permission Modifiers:
- `:ro` -> **Read-Only**: The app can inspect files but cannot write, create, or delete.
- `:rw` -> **Read-Write**: Default access mode if no modifier is specified.
- `:create` -> **Create Directory**: Creates the directory on the host filesystem if it does not already exist before launching the sandbox.

```yaml
finish-args:
  # Standard XDG well-known directories
  - --filesystem=xdg-download
  - --filesystem=xdg-pictures:ro
  - --filesystem=xdg-documents
  - --filesystem=xdg-music:ro
  - --filesystem=xdg-desktop

  # Scoped host paths with creation modifier
  - --filesystem=~/.cert/nm-openvpn/
  - --filesystem=~/.cert:create
  - --filesystem=~/.config/mpv:ro

  # System paths
  - --filesystem=/var/log/journal:ro
  - --filesystem=/tmp
```

#### Filesystem Targets Reference Table:

| Filesystem Target | Scope & Resolved Host Path | Appropriate Use Case |
| :--- | :--- | :--- |
| `xdg-download` | `~/Downloads` (`XDG_DOWNLOAD_DIR`) | Download managers, browsers, torrent clients. |
| `xdg-pictures` | `~/Pictures` (`XDG_PICTURES_DIR`) | Photo editors, image viewers, graphic tools. |
| `xdg-documents` | `~/Documents` (`XDG_DOCUMENTS_DIR`) | Document processors, PDF viewers, office suites. |
| `xdg-music` | `~/Music` (`XDG_MUSIC_DIR`) | Music players, DAWs, taggers. |
| `xdg-desktop` | `~/Desktop` (`XDG_DESKTOP_DIR`) | Desktop file utilities, icon managers. |
| `xdg-run/<name>` | `/run/user/$UID/<name>` | Access to custom user-level daemon sockets. |
| `~/<path>` | Scoped path relative to user `$HOME` | Preserving specific existing configuration/state dirs (e.g. `~/.cert/nm-openvpn`). |
| `/var/log/journal:ro` | `/var/log/journal` (Systemd journal) | Diagnostic tools, VPN bug reporting, system logs. |
| `home` | Entire user `$HOME` directory | **Strictly scrutinised on Flathub**. File managers, IDEs only. |
| `host` | Entire host filesystem (`/`) | **Heavily restricted on Flathub**. Virtualization / system diagnostics only. |

---

### 3.5 D-Bus Mediation (Session & System Bus)

Flatpak intercepts and filters all D-Bus traffic via `xdg-dbus-proxy`. Applications cannot communicate with D-Bus services unless explicitly permitted.

```
+-------------------------------------------------------------+
| Flatpak Application                                         |
+-------------------------------------------------------------+
                              |
                              v
                +----------------------------+
                |     xdg-dbus-proxy         |
                |  (Security Policy Filter)  |
                +----------------------------+
                 /                          \
                v                            v
   [Session Bus: dbus-daemon]    [System Bus: dbus-daemon]
   - org.freedesktop.secrets     - org.freedesktop.NetworkManager
   - org.kde.StatusNotifier      - org.freedesktop.login1
```

#### D-Bus Directives:
- `--talk-name=<bus-name>`: Allows sending calls and receiving replies from a specific service on the **Session Bus**.
- `--own-name=<bus-name>`: Allows the application to register and own a service name on the **Session Bus**.
- `--system-talk-name=<bus-name>`: Allows sending calls and receiving replies on the **System Bus**.
- `--system-own-name=<bus-name>`: Allows owning a service name on the **System Bus** (rarely granted).

#### Common Session Bus Services:

| D-Bus Name | Service Purpose | Common Use Cases |
| :--- | :--- | :--- |
| `org.freedesktop.secrets` | Secret Service API (Keyrings) | Storing and retrieving encrypted credentials, API keys, tokens (GNOME Keyring, KeePassXC). |
| `org.kde.StatusNotifierWatcher` | Tray Icon / AppIndicator API | Creating system tray icons and indicators across GNOME (via extension), KDE Plasma, and XFCE. |
| `org.freedesktop.Notifications` | Desktop Notifications | Displaying notifications (used if XDG desktop notification portal is not utilized). |
| `org.mpris.MediaPlayer2.*` | Media Player Remote Interfacing | Media playback controls for desktop shell / lock screen integration. |
| `org.freedesktop.portal.*` | XDG Desktop Portals | Standard portal communication (enabled by default in runtime). |

#### Common System Bus Services:

| D-Bus Name | Service Purpose | Common Use Cases |
| :--- | :--- | :--- |
| `org.freedesktop.NetworkManager` | Host Network Management | Checking connection status, monitoring Wi-Fi/Ethernet links, managing VPN connections. |
| `org.freedesktop.login1` | systemd-logind Management | Inhibiting sleep/suspend, monitoring system power/reboot states, reconnecting network daemons. |
| `org.freedesktop.ModemManager1` | Cellular / Mobile Broadband | Controlling cellular modems, SMS, and mobile data connections. |
| `org.freedesktop.UPower` | Power & Battery Management | Checking battery levels, power profiles, and charging status. |
| `org.bluez` | Bluetooth Stack | Managing Bluetooth adapters, scanning, and pairing peripheral devices. |

---

### 3.6 Device & Subsystem Access

| Argument | Subsystem / Device Node | Technical Scope & Security Implications |
| :--- | :--- | :--- |
| `--device=dri` | Direct Rendering Infrastructure (`/dev/dri/*`) | Enables hardware GPU acceleration for OpenGL, Vulkan, VA-API, and video decoding. **Standard for GUI apps**. |
| `--device=kvm` | Kernel Virtual Machine (`/dev/kvm`) | Enables hardware virtualization acceleration. Required for QEMU, Android emulators, virtual machines. |
| `--device=all` | All Devices (`/dev/*`, `/dev/bus/usb/*`, HID) | Raw device access. Required for USB security keys (FIDO2 / U2F), raw USB hardware, serial/CAN controllers. **Triggers Flathub review scrutiny**. |
| `--device=shm` | Shared Memory (`/dev/shm`) | Grants access to host `/dev/shm` shared memory segment. |
| `--share=network` | Network Namespace | Connects container to the host network stack. Enables TCP, UDP, DNS, and HTTP operations. |
| `--share=ipc` | IPC Namespace | Shares SysV IPC and POSIX shared memory with the host. Required for high-performance X11 graphics rendering. |
| `--unshare=network` | Network Isolation | Explicitly disables network access (default during build phase). |

---

## 4. Flathub Quality Standards & Least Privilege

Flathub maintains strict review guidelines to protect end-user security and system integrity.

### 4.1 The Principle of Least Privilege & XDG Portals

Modern Flatpak applications should never request broad filesystem or device permissions when an **XDG Desktop Portal** (`org.freedesktop.portal.*`) can satisfy the requirement dynamically with user consent.

```
+-------------------------------------------------------------------------------+
|                      LEGACY PERMISSIONS VS MODERN PORTALS                     |
+-------------------------------------------------------------------------------+
| Legacy (Discouraged)                     | Modern Portal (Recommended)        |
+------------------------------------------+------------------------------------+
| --filesystem=home                        | org.freedesktop.portal.FileChooser |
| --filesystem=/tmp                        | org.freedesktop.portal.OpenURI     |
| --talk-name=org.freedesktop.secrets      | org.freedesktop.portal.Secret      |
| --device=all (for webcams)               | org.freedesktop.portal.Camera      |
| --talk-name=org.freedesktop.Notifications| org.freedesktop.portal.Notification|
+------------------------------------------+------------------------------------+
```

#### Why Portals Are Superior:
1. **Dynamic User Consent**: When the user opens a file via `FileChooserPortal`, only the selected file is temporarily exposed to the container via FUSE document portal (`/run/user/$UID/doc/`).
2. **Zero Ambient Authority**: The application cannot browse or exfiltrate private files in `$HOME`.
3. **Desktop Native UX**: Dialogs render in the host theme and native environment.

---

### 4.2 Flathub Sensitive Permission Policy & Justifications

During Flathub PR review, requests for broad permissions require explicit technical justification in the pull request description:

| Sensitive Permission | Flathub Policy & Acceptable Justifications | Rejection Triggers |
| :--- | :--- | :--- |
| `--filesystem=host` / `--filesystem=host:ro` | **Strictly Restricted**. Only permitted for system administration tools, IDEs with terminal access, or container managers. | Requesting `host` for simple file browsing or media playing. |
| `--filesystem=home` / `--filesystem=home:ro` | **Restricted**. Acceptable only for legacy software incapable of supporting the XDG FileChooser portal, or complex developer tools. | Requesting `home` when only `xdg-download` or `xdg-documents` is needed. |
| `--device=all` | **Restricted**. Acceptable for hardware token authentication (FIDO2/Yubikey), flashing microcontrollers, or raw hardware debuggers. | Requesting `device=all` for webcams or audio input (use Portals/PulseAudio). |
| `--socket=session-bus` / `--socket=system-bus` | **Strictly Forbidden**. Completely exposes the host D-Bus, bypassing all sandbox boundaries. | Automatically rejected by Flathub CI. Must use specific `--talk-name` / `--system-talk-name`. |
| `--talk-name=org.freedesktop.Flatpak` | **Strictly Restricted**. Allows controlling Flatpak installations on the host. | Only allowed for Flatpak management GUI utilities. |

---

### 4.3 AppStream Metainfo Integration & Validation

Every Flathub application must include a valid AppStream metainfo XML file located at `/app/share/metainfo/<app-id>.metainfo.xml` or `/app/share/appdata/<app-id>.appdata.xml`.

#### Required AppStream Elements:
- `<id>`: Must match the manifest `id` / `app-id` exactly.
- `<metadata_license>`: Must be a permissive license (e.g. `FSFAP` or `CC0-1.0`).
- `<project_license>`: SPDX license expression of the upstream application (e.g. `GPL-3.0-or-later`).
- `<name>` & `<summary>`: Human-readable title and short single-sentence summary.
- `<description>`: Formatted description paragraphs and bullet lists.
- `<launchable type="desktop-id">`: References the desktop file (`<app-id>.desktop`).
- `<screenshots>`: Publicly accessible screenshot URLs with aspect ratios.
- `<releases>`: Release history with version tags, dates, and changelog descriptions.
- `<content_rating type="oars-1.1" />`: OARS rating specification.

#### Metainfo Validation Commands:
```bash
# Validate using appstream-util (checks syntax and Flathub constraints)
appstream-util validate --nonet com.protonvpn.www.metainfo.xml

# Validate using appstreamcli (checks specification compliance)
appstreamcli validate --no-net com.protonvpn.www.metainfo.xml
```

---

## 5. Real-World Manifest Blueprints & Auditing

### 5.1 Blueprint 1: GNOME 50 / GTK4 / Libadwaita Desktop App

A modern, portal-aware GTK4 desktop application written in Rust and compiled with Meson:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json

id: org.gnome.ExampleApp
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
command: example-app

sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable

finish-args:
  # Display & GPU
  - --socket=wayland
  - --socket=fallback-x11
  - --share=ipc
  - --device=dri
  # Networking
  - --share=network
  # Audio
  - --socket=pulseaudio
  # D-Bus Application Ownership
  - --own-name=org.gnome.ExampleApp

cleanup:
  - /include
  - /lib/pkgconfig
  - /share/doc
  - /share/man
  - "*.la"
  - "*.a"

modules:
  # C dependency built with Meson
  - name: libexample-helper
    buildsystem: meson
    config-opts:
      - -Dbuildtype=release
      - -Dtests=false
    sources:
      - type: archive
        url: https://github.com/example/libhelper/releases/download/v1.2.0/libhelper-1.2.0.tar.xz
        sha256: 7f83b1657ff1...

  # Main Application (Rust + Meson)
  - name: example-app
    buildsystem: meson
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/example-app/cargo-home
    sources:
      - type: git
        url: https://gitlab.gnome.org/GNOME/example-app.git
        tag: 1.0.0
        commit: a1b2c3d4e5f6...
      - cargo-sources.json
```

---

### 5.2 Blueprint 2: System / Network Utility (Proton VPN Architecture)

A hybrid Python/GTK system network utility requiring Secret Service integration, NetworkManager system bus communication, FIDO2 hardware security keys, and scoped filesystem access:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json

id: com.protonvpn.www
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
command: protonvpn-app

sdk-extensions:
  - org.freedesktop.Sdk.Extension.rust-stable

finish-args:
  # IPC and Host Network Stack
  - --share=ipc
  - --share=network

  # GUI Wayland with X11 fallback
  - --socket=wayland
  - --socket=fallback-x11

  # Secret Service API (Keyring credential storage)
  - --talk-name=org.freedesktop.secrets

  # System Bus: NetworkManager API for monitoring and VPN state
  - --system-talk-name=org.freedesktop.NetworkManager

  # System Bus: systemd-logind for sleep/wake hooks and DBus daemon reconnection
  - --system-talk-name=org.freedesktop.login1

  # Status Notifier tray icon integration
  - --talk-name=org.kde.StatusNotifierWatcher

  # D-Bus session name registration
  - --own-name=proton.vpn.app.gtk

  # Scoped Filesystem: OpenVPN configuration & certificate persistence
  - --filesystem=~/.cert/nm-openvpn/
  - --filesystem=~/.cert:create

  # Scoped Filesystem: Read-only system journal access for diagnostics
  - --filesystem=/var/log/journal:ro

  # Hardware Devices: FIDO2 / U2F USB hardware security key authentication
  - --device=all

modules:
  # Intltool translation utilities
  - shared-modules/intltool/intltool-0.51.json

  # Shared Python packaging tooling
  - name: python3-packaging
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "packaging" --no-build-isolation
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/20/12/38679034af332785aac8774540895e234f4d07f7545804097de4b666afd8/packaging-25.0-py3-none-any.whl
        sha256: 29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484

  # Native Rust-backed Python cryptography module using SDK extension
  - name: python3-bcrypt
    buildsystem: simple
    build-options:
      append-path: /usr/lib/sdk/rust-stable/bin
      env:
        CARGO_HOME: /run/build/python3-bcrypt/cargo-home
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "bcrypt" --no-build-isolation
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz
        sha256: 4b29796e6a3ef73ef808b2dc1e16f316279f22c66860e6e76fc6d5b0373ab1b1
      - bcrypt-cargo-sources.json

  # Main Application Package
  - name: proton-vpn-gtk-app
    buildsystem: simple
    build-commands:
      - pip3 install --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} . --no-build-isolation
      - install -Dm644 rpm/com.protonvpn.www.desktop /app/share/applications/com.protonvpn.www.desktop
      - install -Dm644 rpm/com.protonvpn.www.metainfo.xml /app/share/metainfo/com.protonvpn.www.metainfo.xml
      - install -Dm644 rpm/com.protonvpn.www.svg /app/share/icons/hicolor/scalable/apps/com.protonvpn.www.svg
    sources:
      - type: git
        url: https://github.com/ProtonVPN/proton-vpn-gtk-app.git
        tag: v4.12.0
        commit: 81bca6a94fb21a37c35...
```

---

### 5.3 Permission Auditing & Verification Tooling

To ensure permissions adhere to the principle of least privilege and Flathub automated checks, use the following verification workflows:

#### 1. Manifest Dependency and Permission Verification:
```bash
# Check dependencies and source modules declared in the manifest
flatpak-builder --show-deps com.protonvpn.www.yml

# Inspect configured sandbox permissions after building
flatpak-builder --show-manifest com.protonvpn.www.yml
```

#### 2. Inspecting Installed Application Permissions:
```bash
# Display formatted permissions for an installed Flatpak
flatpak info --show-permissions com.protonvpn.www

# Output example:
# [Context]
# shared=ipc;network;
# sockets=wayland;fallback-x11;
# devices=all;
# filesystems=/var/log/journal:ro;~/.cert:create;~/.cert/nm-openvpn;
#
# [Session Bus Policy]
# org.freedesktop.secrets=talk
# org.kde.StatusNotifierWatcher=talk
# proton.vpn.app.gtk=own
#
# [System Bus Policy]
# org.freedesktop.NetworkManager=talk
# org.freedesktop.login1=talk
```

#### 3. Automated Linter Inspection (`flatpak-builder-lint`):
```bash
# Install and execute flatpak-builder-lint (Flathub CI standard tool)
flatpak-builder-lint manifest com.protonvpn.www.yml
flatpak-builder-lint appstream com.protonvpn.www.metainfo.xml
flatpak-builder-lint repo build-dir/
```

#### 4. Permission Auditing Checklist:
- [ ] **Wayland + X11**: `--socket=wayland` and `--socket=fallback-x11` used instead of unrestricted `--socket=x11`.
- [ ] **IPC Sharing**: `--share=ipc` included for X11 rendering performance.
- [ ] **Filesystem Scoping**: Avoided `--filesystem=home` or `--filesystem=host` unless strictly required.
- [ ] **D-Bus Boundaries**: No wildcard `--socket=session-bus` or `--socket=system-bus`; all bus targets explicitly named.
- [ ] **Device Access**: `--device=dri` for graphics; `--device=all` justified with hardware token (FIDO2) or peripheral usage.
- [ ] **AppStream**: Metainfo XML validated cleanly with `appstream-util validate --nonet`.
- [ ] **Language Server Schema**: Header `# yaml-language-server: $schema=...` present on line 1.
