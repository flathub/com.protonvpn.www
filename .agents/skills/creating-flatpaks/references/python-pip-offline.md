# Python / Pip Offline Dependency Management for Flatpak

This reference guide provides a complete technical blueprint for packaging Python applications and Python libraries for Flatpak and Flathub. It explains the mechanics of Flatpak's offline build isolation, how to download and vendor Python dependencies ahead-of-time using `flatpak-pip-generator`, how to configure build backends and flags, and how to resolve complex native compilation and runtime dependency challenges.

---

## 1. Overview & Sandboxing Principles

### Flatpak Build Isolation Model
Flathub and `flatpak-builder` enforce a strict separation between source resolution and compilation:

1. **Download Phase (Online)**: `flatpak-builder` parses the manifest and all included resource files, downloads every declared source archive, wheel, or git repository via the host network, and cryptographically verifies its `sha256` checksum.
2. **Build Phase (Offline / Unshared Network)**: The build executes inside an isolated sandbox with the network namespace completely unshared (`--unshare=network`). Any attempt by `pip`, `setuptools`, `poetry`, or `cargo` to open a socket or query PyPI fails immediately with a network unreachable error.

```
+-------------------------------------------------------------------------+
| DOWNLOAD PHASE (Host Network Enabled)                                   |
|   1. flatpak-builder reads com.example.App.yml and pip-resources.*.yaml |
|   2. Downloads wheels (.whl) & source tarballs (.tar.gz) from PyPI      |
|   3. Verifies SHA256 integrity against manifest declarations            |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| BUILD PHASE (Network Namespace Unshared: NO NETWORK ACCESS)             |
|   1. Downloaded archives unpacked into /run/build/<module-name>/        |
|   2. pip3 install --no-index --find-links="file://${PWD}"               |
|   3. pip3 searches only the local directory for matching packages       |
|   4. Compiles C/Rust extensions & installs to /app (FLATPAK_DEST)       |
+-------------------------------------------------------------------------+
```

### The Offline Pip Paradigm
Standard Python deployment workflows (`pip install <package>`) dynamically query the PyPI JSON/Simple API, download the latest matching wheel or source distribution, resolve transitive dependencies on the fly, and download build dependencies into temporary virtual environments.

In Flatpak packaging:
- **No Dynamic Index**: `pip` is invoked with `--no-index` to prevent querying remote package indexes.
- **Local Link Directory**: `pip` is pointed to the build directory containing the downloaded artifacts using `--find-links="file://${PWD}"`.
- **No Build Isolation**: `pip` is invoked with `--no-build-isolation` to prevent it from attempting to fetch PEP 517/518 build-time dependencies over the disabled network.
- **Explicit Target Prefix**: Packages are installed into the Flatpak application tree via `--prefix=${FLATPAK_DEST}` (which expands to `/app`).

---

## 2. `flatpak-pip-generator` Tooling

`flatpak-pip-generator` is the standard tool maintained within [flatpak-builder-tools](https://github.com/flatpak/flatpak-builder-tools) to automate the resolution, downloading, and YAML/JSON source block generation for Python dependencies.

### 2.1 Installation & Setup

You can obtain `flatpak-pip-generator` directly from the `flatpak-builder-tools` repository:

```bash
# Clone flatpak-builder-tools
git clone https://github.com/flatpak/flatpak-builder-tools.git /tmp/flatpak-builder-tools

# Add to PATH or invoke directly
python3 /tmp/flatpak-builder-tools/pip/flatpak-pip-generator --help
```

### 2.2 CLI Invocations & Common Flags

```bash
# Generate YAML resources for a list of packages matching a specific runtime SDK
flatpak-pip-generator \
  --yaml \
  --checker-data \
  --runtime='org.gnome.Sdk//50' \
  -o pip-resources.proton-vpn-cli \
  click dbus-fast tabulate

# Generate resources from a requirements.txt file
flatpak-pip-generator \
  --yaml \
  --checker-data \
  --runtime='org.gnome.Sdk//50' \
  --requirements-file=requirements.txt \
  -o pip-resources.my-app
```

#### Key Options Reference:
- `--yaml`: Emits output in YAML format (the default is JSON).
- `--checker-data`: Appends `x-checker-data` blocks to each package source entry, enabling automated update tracking with `flatpak-external-data-checker`.
- `--runtime='<runtime-id>//<version>'`: Specifies the target Flatpak runtime (e.g. `org.gnome.Sdk//50` or `org.freedesktop.Sdk//24.08`). `flatpak-pip-generator` uses this to resolve matching Python version ABI tags (e.g. CPython 3.12).
- `-o <filename>` / `--output <filename>`: Base output filename (writes `<filename>.yaml` or `<filename>.json`).
- `-r <file>` / `--requirements-file <file>`: Reads package specifications from a standard `requirements.txt` file.

### 2.3 Anatomy of Generated Source Blocks

When `flatpak-pip-generator` runs, it queries PyPI for each package and its transitive dependency tree, resolves matching wheel or source distributions, and generates Flatpak module declarations:

```yaml
# Generated with flatpak-pip-generator --checker-data --yaml --runtime=org.gnome.Sdk//50 click dbus-fast tabulate -o pip-resources.proton-vpn-cli
build-commands: []
buildsystem: simple
modules:
- name: python3-click
  buildsystem: simple
  build-commands:
  - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} "click" --no-build-isolation
  sources:
  - type: file
    url: https://files.pythonhosted.org/packages/98/78/01c019cdb5d6498122777c1a43056ebb3ebfeef2076d9d026bfe15583b2b/click-8.3.1-py3-none-any.whl
    sha256: 981153a64e25f12d547d3426c367a4857371575ee7ad18df2a6183ab0545b2a6
    x-checker-data:
      name: click
      packagetype: bdist_wheel
      type: pypi
- name: python3-dbus-fast
  buildsystem: simple
  build-commands:
  - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} "dbus-fast" --no-build-isolation
  sources:
  - type: file
    url: https://files.pythonhosted.org/packages/4d/45/43e2826069e8ed2cb3a3b83da72d39a0fe52ece2eca3cac8ff5e070bbfa4/dbus_fast-2.45.1.tar.gz
    sha256: 486195c42c5f8fac77e9c55b575e2c85636cff7db45ebc7a19f680b3b4084314
    x-checker-data:
      name: dbus-fast
      packagetype: sdist
      type: pypi
name: pip-resources.proton-vpn-cli
```

### 2.4 YAML Anchors and Shared Dependencies
When multiple modules share common dependencies (e.g. `pycairo` required by both `python3-pygobject` and `python3-pycairo`), `flatpak-pip-generator` uses standard YAML anchors (`&id001`) and references (`*id001`) to avoid duplicate downloads:

```yaml
modules:
- name: python3-pygobject
  buildsystem: simple
  build-commands:
  - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} "pygobject" --no-build-isolation
  sources:
  - &id001
    type: file
    url: https://files.pythonhosted.org/packages/40/d9/412da520de9052b7e80bfc810ec10f5cb3dbfa4aa3e23c2820dc61cdb3d0/pycairo-1.28.0.tar.gz
    sha256: 26ec5c6126781eb167089a123919f87baa2740da2cca9098be8b3a6b91cc5fbc
  - type: file
    url: https://files.pythonhosted.org/packages/a2/80/09247a2be28af2c2240132a0af6c1005a2b1d089242b13a2cd782d2de8d7/pygobject-3.56.2.tar.gz
    sha256: b816098969544081de9eecedb94ad6ac59c77e4d571fe7051f18bebcec074313
- name: python3-pycairo
  buildsystem: simple
  build-commands:
  - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} "pycairo" --no-build-isolation
  sources:
  - *id001
```

---

## 3. Artifact Types & Resolution Strategy

Selecting the right distribution format on PyPI is critical for reliable offline Flatpak compilation.

### 3.1 Distribution Types

| Artifact Type | Filename Pattern | Characteristics | Flatpak Suitability |
|---|---|---|---|
| **Pure Python Wheel** | `*-py3-none-any.whl` | Pre-built bytecode, no native C/Rust compilation needed. Zero build-backend overhead. | **Ideal**: Fastest to install, lowest build overhead. |
| **Source Distribution (sdist)** | `*.tar.gz` / `*.zip` | Raw source tree. Built on-demand inside the Flatpak build container against runtime libraries. | **Required** for packages with C/C++/Rust extensions linking against SDK headers. |
| **Pre-built Binary Wheel** | `*-cp312-cp312-manylinux_*.whl` | Pre-compiled binary against generic `manylinux` glibc standard. | **Use with caution**: May conflict with runtime system libraries or fail arch cross-compilation. |

### 3.2 Why Source Distributions (sdist) are Favored for Native Extensions

When a Python package contains native C/C++ extensions or Rust bindings (e.g. `pygobject`, `pycairo`, `bcrypt`, `cryptography`, `dbus-fast`, `psutil`):
1. **ABI and Library Consistency**: Compiling from sdist ensures the extension links against the exact shared libraries (`glib2`, `cairo`, `gtk4`, `openssl`, `libsecret`) provided by the Flatpak runtime (e.g. `org.gnome.Platform//50`).
2. **Multi-Architecture Support**: Flathub builds for multiple CPU architectures (`x86_64`, `aarch64`). An sdist is architecture-neutral in the manifest; `flatpak-builder` compiles it natively on each builder architecture.
3. **Debugging and Symbol Stripping**: Source compilation respects Flatpak build options, producing valid `.debug` symbols for crash reporting and debugging extensions.

### 3.3 Runtime SDK & Python Version Alignment

Flatpak runtimes provide specific Python versions. Ensure your package resolutions and wheel compatibility tags match the target SDK:

- **GNOME 50 / Freedesktop 24.08**: Python 3.12+ (CPython ABI: `cp312`)
- **GNOME 49 / Freedesktop 23.08**: Python 3.11+ (CPython ABI: `cp311`)

When running `flatpak-pip-generator`, always supply the exact target runtime (`--runtime='org.gnome.Sdk//50'`) so that it selects matching wheel ABI tags for packages where binary wheels are accepted.

---

## 4. Offline Installation Mechanics & Build Flags

### 4.1 The Standard Build Command

Every offline Python module in Flatpak uses the following standardized invocation:

```bash
pip3 install \
  --verbose \
  --exists-action=i \
  --no-index \
  --find-links="file://${PWD}" \
  --prefix=${FLATPAK_DEST} \
  --no-build-isolation \
  "<package-name>"
```

For installing the application itself from the current source root:

```bash
pip3 install \
  --verbose \
  --exists-action=i \
  --no-index \
  --find-links="file://${PWD}" \
  --prefix=${FLATPAK_DEST} \
  --no-build-isolation \
  "."
```

#### Detailed Flag Breakdown:
- `--verbose`: Prints detailed wheel building and installation logs, which are essential for debugging CI build failures on Flathub.
- `--exists-action=i`: Ignore existing installed packages if encountered.
- `--no-index`: Completely ignores PyPI and all package indexes.
- `--find-links="file://${PWD}"`: Tells pip to search for `.whl` and `.tar.gz` files in the current build directory where Flatpak placed the downloaded `sources`.
- `--prefix=${FLATPAK_DEST}`: Directs installation into `/app` (`/app/lib/python3.12/site-packages` and `/app/bin`).
- `--no-build-isolation`: **Critical flag**. Disables PEP 517/518 isolated build environments.

### 4.2 Why `--no-build-isolation` is Essential

Under PEP 517 and PEP 518, `pip` defaults to build isolation:
1. When building a package with a `pyproject.toml`, pip creates a temporary virtualenv in `/tmp`.
2. Pip reads `[build-system] requires = [...]` (e.g. `["setuptools>=61.0", "wheel", "flit_core>=3.2"]`).
3. Pip attempts to connect to PyPI to install those build tools into the temporary virtualenv.
4. In Flatpak's unshared network sandbox, this network request **fails instantly**.

By passing `--no-build-isolation`, you force pip to use the build backends already installed in the Flatpak build environment (`/usr` from the SDK, or `/app` from preceding manifest modules).

### 4.3 Pre-Installing Build Backends & Build-Time Tools

Because build isolation is disabled, all build backends specified in `build-system.requires` must be present before the module is built.

Common build backends and build tools include:
- `setuptools` & `wheel` (Standard setuptools builds)
- `flit_core` (Lightweight pure Python packages, e.g. `typing_extensions`, `tomli`)
- `poetry-core` (Poetry-based packages)
- `hatchling` (Hatch-based packages)
- `setuptools_scm` (Version extraction from SCM/git tags)
- `maturin` / `setuptools-rust` (Rust-backed Python extensions)
- `scikit-build` / `ninja` (CMake-backed C/C++ extensions)
- `cython` (C-extension transpiler)
- `editables`, `pathspec`, `calver`, `pluggy`, `packaging`

### 4.4 The Build Backend Module Pattern (`cleanup: ['*']`)

When build tools are only needed during compilation and should not bloat the final Flatpak runtime image, declare them as nested submodules with `cleanup: ['*']`:

```yaml
  - name: python3-my-package
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "my-package" --no-build-isolation
    modules:
      # Build dependency required only during build
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
            x-checker-data:
              name: flit_core
              type: pypi
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/ab/cd/.../my_package-1.0.0.tar.gz
        sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

`cleanup: ['*']` ensures that all files installed by `python3-flit_core` into `${FLATPAK_DEST}` are purged before the final Flatpak runtime bundle is created, leaving only the compiled target package.

---

## 5. Modularization Patterns & Manifest Integration

In complex applications (such as Proton VPN), having dozens of Python dependencies directly in the main manifest file (`com.example.App.yml`) makes maintenance unmanageable. Splitting dependencies into modular resource files is the recommended Flathub pattern.

### 5.1 Modular File Organization

A clean repository structure separates concerns by component:

```
com.protonvpn.www/
├── com.protonvpn.www.yml                  # Main application manifest
├── pip-resources.python-skbuild.yaml       # Build tools (scikit-build, ninja)
├── pip-resources.python-proton-core.yaml   # Core networking dependencies
├── pip-resources.python-proton-keyring-linux.yaml # Secret service / keyring deps
├── pip-resources.python-proton-vpn-api-core.yaml  # API / FIDO2 / Crypto deps
├── pip-resources.proton-vpn-cli.yaml       # CLI specific dependencies
├── pip-resources.proton-vpn-gtk-app.yaml   # GTK UI specific dependencies (PyGObject, PyCairo)
└── bcrypt-cargo-sources.json               # Cargo vendored sources for Rust extensions
```

### 5.2 Manifest Integration Patterns

#### Pattern A: Including as Submodule in `modules:`
This pattern is ideal when a group of dependencies belongs to a specific sub-component of your build:

```yaml
  - name: proton-vpn-cli
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "." --no-build-isolation
    modules:
      - pip-resources.proton-vpn-cli.yaml
    sources:
      - type: git
        url: https://github.com/ProtonVPN/proton-vpn-cli.git
        tag: v1.0.3
        commit: a7c7abc8d3777f33b8d4c82279bd621258bd810d
```

#### Pattern B: Top-Level Module Inclusions
Modular files can also be referenced directly in the root `modules` list of the manifest:

```yaml
modules:
  - pip-resources.python-proton-core.yaml
  - pip-resources.python-proton-keyring-linux.yaml
  - pip-resources.python-proton-vpn-api-core.yaml
  - name: my-main-application
    buildsystem: simple
    build-commands:
      - pip3 install --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} "." --no-build-isolation
```

---

## 6. Handling Native Extensions (Rust, CMake, CFFI, GObject)

### 6.1 PyO3 / `setuptools-rust` Extensions (e.g. `bcrypt`, `cryptography`)

Packages combining Python with Rust native code require both the Python build backend (`setuptools-rust`, `semantic_version`, `flit_core`) and the Rust toolchain with offline Cargo sources:

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

### 6.2 CMake / `scikit-build` Extensions

For packages using `scikit-build` to drive CMake compilation (e.g. `ninja`, C++ wrappers):
1. Install `ninja` and `scikit-build` in a prior module or nested module.
2. Ensure CMake finds host compilers and libraries in `${FLATPAK_DEST}` and `/usr`.

```yaml
  - name: python-skbuild
    buildsystem: simple
    build-commands:
      - pip3 install --no-index --no-build-isolation --prefix="${FLATPAK_DEST}" .
    cleanup: ['*']
    sources:
      - type: archive
        url: https://files.pythonhosted.org/packages/9e/e2/2e440c30e93fc5b505ee56169a4396b05e797a1daadb721aba429adbfd51/scikit-build-0.15.0.tar.gz
        sha256: e723cd0f3489a042370b9ea988bbb9cfd7725e8b25b20ca1c7981821fcf65fb9
```

### 6.3 PyGObject & PyCairo Extensions

Packages interacting with GTK4 / Libadwaita require `pygobject` and `pycairo`. These compile against C headers (`gobject-introspection-1.0`, `cairo`, `gtk4`) provided by `org.gnome.Sdk`.

```yaml
  - name: proton-vpn-gtk-app
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "." --no-build-isolation
    modules:
      - pip-resources.proton-vpn-gtk-app.yaml
```

---

## 7. Automated Upstream Updating

### 7.1 Flatpak External Data Checker (`x-checker-data`)

Flathub's automated bot (`flatpak-external-data-checker`) scans manifest source entries for `x-checker-data` annotations and automatically opens PRs when newer versions are released.

#### PyPI Checker Schema:
```yaml
sources:
  - type: file
    url: https://files.pythonhosted.org/packages/98/78/01c019cdb5d6498122777c1a43056ebb3ebfeef2076d9d026bfe15583b2b/click-8.3.1-py3-none-any.whl
    sha256: 981153a64e25f12d547d3426c367a4857371575ee7ad18df2a6183ab0545b2a6
    x-checker-data:
      type: pypi
      name: click
      packagetype: bdist_wheel # or sdist
```

- `type: pypi`: Directs the checker to query `https://pypi.org/pypi/<name>/json`.
- `name`: PyPI package name.
- `packagetype`: `bdist_wheel` (for wheels) or `sdist` (for source tarballs).

### 7.2 Custom Downstream Automation (`fedora_flatpak_updater`)

Repositories maintaining complex packages (like `com.protonvpn.www`) often use custom automated updater tools (e.g. `scripts/fedora_flatpak_updater`) to synchronize dependencies with downstream Linux distributions (Fedora stable) and PyPI:

```bash
# Check and preview dependency updates against Fedora / PyPI
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --dry-run

# Regenerate pip resource manifests when dependencies change
flatpak-pip-generator --checker-data --yaml --runtime='org.gnome.Sdk//50' \
  click dbus-fast tabulate -o pip-resources.proton-vpn-cli
```

---

## 8. Real-World End-to-End Manifest Examples

### Example 1: Standalone Pure Python CLI Application

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
id: org.example.PythonCli
runtime: org.freedesktop.Platform
runtime-version: '24.08'
sdk: org.freedesktop.Sdk
command: example-cli

finish-args:
  - --share=network
  - --filesystem=home

modules:
  - name: python3-dependencies
    buildsystem: simple
    build-commands: []
    modules:
      - pip-resources.example-cli.yaml

  - name: example-cli
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "." --no-build-isolation
    sources:
      - type: git
        url: https://github.com/example/example-cli.git
        tag: v1.0.0
        commit: 1234567890abcdef1234567890abcdef12345678
```

---

### Example 2: Desktop GTK4 / Libadwaita Python Application with Assets

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
id: com.example.GtkApp
runtime: org.gnome.Platform
runtime-version: '50'
sdk: org.gnome.Sdk
command: example-gtk-app

finish-args:
  - --share=ipc
  - --socket=fallback-x11
  - --socket=wayland
  - --talk-name=org.freedesktop.secrets

modules:
  # Included modular Python dependencies
  - pip-resources.example-app.yaml

  - name: example-gtk-app
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}"
        --prefix=${FLATPAK_DEST} "." --no-build-isolation

      # Install Desktop file and icon metadata
      - install -Dm644 data/com.example.GtkApp.desktop ${FLATPAK_DEST}/share/applications/${FLATPAK_ID}.desktop
      - install -Dm644 data/icons/com.example.GtkApp.svg ${FLATPAK_DEST}/share/icons/hicolor/scalable/apps/${FLATPAK_ID}.svg
      - install -Dm644 data/com.example.GtkApp.metainfo.xml ${FLATPAK_DEST}/share/metainfo/${FLATPAK_ID}.metainfo.xml

    sources:
      - type: git
        url: https://github.com/example/example-gtk-app.git
        tag: v2.0.0
        commit: abcdef0123456789abcdef0123456789abcdef01
```

---

## 9. Troubleshooting & Common Pitfalls

### 9.1 Error: Network Connection Attempt During Build
```
pip._vendor.urllib3.exceptions.NewConnectionError: <urllib3.connection.HTTPSConnection object>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution
```
**Cause**: Missing `--no-build-isolation` or missing `--no-index`. Pip attempted to query PyPI to create an isolated build environment or fetch a missing dependency.
**Solution**:
1. Verify that `--no-build-isolation` and `--no-index --find-links="file://${PWD}"` are present in `build-commands`.
2. Ensure every transitive dependency is declared in `sources` or included `pip-resources.*.yaml`.

---

### 9.2 Error: Missing Build Backend (`ModuleNotFoundError: No module named 'flit_core'`)
```
ModuleNotFoundError: No module named 'flit_core'
error: subprocess-exited-with-error
```
**Cause**: The package uses `flit_core` (or `setuptools_scm`, `poetry-core`, `hatchling`) as its build backend in `pyproject.toml`, but it is not installed in the SDK or earlier manifest modules.
**Solution**:
Add a preceding module or nested submodule with `cleanup: ['*']` that installs `flit_core` before building the target package.

---

### 9.3 Error: Wheel ABI / Architecture Incompatibility
```
ERROR: package-1.0.0-cp311-cp311-manylinux_2_17_x86_64.whl is not a supported wheel on this platform.
```
**Cause**:
1. The wheel was compiled for Python 3.11 (`cp311`), but the Flatpak runtime provides Python 3.12 (`cp312`).
2. Or a wheel built for `x86_64` was attempted on an `aarch64` builder.
**Solution**:
- Regenerate dependencies using `flatpak-pip-generator --runtime='org.gnome.Sdk//50'` to fetch Python 3.12 compatible wheels.
- For packages with native code, switch to source distributions (`sdist`, `.tar.gz`) instead of platform-specific binary wheels.

---

### 9.4 Executable Entry Point Shebang & `$PATH` Issues
```
bash: /app/bin/my-tool: /usr/bin/python3: bad interpreter: No such file or directory
```
**Cause**: Pip installed an entry point script with a shebang pointing to `/usr/bin/python3`, but runtime packages reside in `/app`.
**Solution**:
In the Flatpak environment, `/usr/bin/python3` is provided by the runtime. If the script cannot find `/app/lib/python3.12/site-packages`, ensure `PYTHONPATH` or environment setup includes `/app`:

```yaml
build-options:
  env:
    PYTHONPATH: /app/lib/python3.12/site-packages
```

Alternatively, fix shebangs in post-install commands:
```yaml
build-commands:
  - pip3 install --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} "." --no-build-isolation
  - sed -i '1s|.*|#!/usr/bin/env python3|' ${FLATPAK_DEST}/bin/my-tool
```

---

### 9.5 Python `site-packages` Directory Path Discrepancies (`lib` vs `lib64`)
On 64-bit Linux distributions, some distutils/setuptools configurations may place packages into `/app/lib64/python3.12/site-packages` instead of `/app/lib/python3.12/site-packages`.

**Solution**:
Create a symbolic link if necessary in post-install or module build commands:
```yaml
build-commands:
  - |
    if [ -d "${FLATPAK_DEST}/lib64" ] && [ ! -e "${FLATPAK_DEST}/lib" ]; then
      ln -s lib64 "${FLATPAK_DEST}/lib"
    fi
```

---

### 9.6 Dependency Version Pin Conflicts Across Modular Sub-Manifests
When multiple `pip-resources.*.yaml` sub-manifests require different versions of a shared transitive dependency (e.g. `requests==2.31.0` vs `requests==2.32.3`):
1. The latter module will overwrite the former in `/app/lib/python3.12/site-packages`.
2. If versions are incompatible, runtime breakage can occur.

**Solution**:
- Align shared dependency versions across all `pip-resources.*.yaml` files.
- Run `flatpak-pip-generator` with all packages in a single invocation when possible, or synchronize versions across modular files using an automated updater tool like `fedora_flatpak_updater`.
