# Fedora-Stable Flatpak Dependency Pinning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/fedora_flatpak_updater/`, a scheduled tool that resolves every third-party dependency in `com.protonvpn.www.yml` (and its five `pip-resources.*.yaml` files) to the version Fedora's latest stable release ships, patches the manifests in place, and opens a PR — replacing the incomplete `fedora_pip_updater` scratch work.

**Architecture:** A small Python package with one client per external service (Bodhi, MDAPI, PyPI JSON, `git ls-remote`), one "recipe" module per source kind (`pypi`, `pypi-multi-wheel`, `archive`, `git`), a `ruamel.yaml`-based patcher that mutates the manifest forest in place, and a CLI that orchestrates a full run. A `.fedora-tracked-modules.yaml` mapping file at the repo root is the single source of truth for which modules are tracked and how to resolve their sources.

**Tech Stack:** Python 3.10+, managed with `uv`. `requests`, `ruamel.yaml` (round-trip mode), `tenacity`, `click`, `tabulate`, `packaging`. Dev-only: `pytest`, `responses`. CI: GitHub Actions, `astral-sh/setup-uv`, `peter-evans/create-pull-request`.

## Global Constraints

- Proton-owned modules (`python-proton-core`, `python-proton-keyring-linux`, `python-proton-vpn-api-core`, `python-proton-vpn-local-agent`, `proton-vpn-cli`, `proton-vpn-gtk-app`, and the `proton-vpn-local-agent` PyPI wheel) are never touched. General rule: any package whose PyPI/Fedora name starts with `proton` (case-insensitive) is excluded.
- `NetworkManager` and `NetworkManager-openvpn` version ceilings (`versions: < 1.42.0` / `< 1.10.4`) are dropped — always take whatever version Fedora ships.
- All HTTP and `git` calls are mocked in unit tests. No real network access in the test suite.
- `x-checker-data` is removed from every source block the tool successfully patches (so Flathub's `flatpak-external-data-checker` stops fighting the pinned version). Untouched (skipped/Proton) blocks keep whatever `x-checker-data` they already had.
- Fedora branch resolution (`f44`, `f45`, ...) is always automatic via Bodhi. No manual "bump the target Fedora version" step ever exists.
- The package is installed and run exclusively through `uv` (`uv sync`, `uv run`) — no bare `pip`/`venv` commands.

## Third-Party Libraries Adopted

Beyond the two load-bearing libraries the design doc already calls for (`requests` for HTTP, `ruamel.yaml` for comment/anchor-preserving round-trip YAML, for which there is no simpler popular alternative), this plan adopts:

- **`tenacity`** — replaces hand-rolled retry loops. `fedora_release.py` retries once on any `requests.RequestException`; `mdapi_client.py` retries once on a 5xx status. Both become a `@retry(...)` decorator instead of a manual `for attempt in range(...)` loop.
- **`click`** — replaces `argparse` in `cli.py` and `migrate.py`. Less boilerplate, auto-generated `--help`, and it's already a real dependency this tool tracks (`pip-resources.proton-vpn-cli.yaml`).
- **`tabulate`** — replaces a hand-built markdown table string in `cli.format_summary()`. `tabulate(rows, headers=[...], tablefmt="github")` produces the exact GitHub-flavored markdown table the PR body needs. Also already tracked by this tool.
- **`packaging`** — replaces hand-rolled PEP 503 normalization regexes in `manifest_patcher.py` and `migrate.py` with `packaging.utils.canonicalize_name()`, the reference implementation pip itself uses.
- **`responses`** (dev-only) — replaces hand-rolled `FakeResponse`/`FakeSession` test doubles entirely. `@responses.activate` + `responses.add(responses.GET, url, json=..., status=...)` mocks `requests` at the transport layer, so tests are declarative and don't need session-injection plumbing to be testable.

**Considered and not adopted:**
- **`pydantic`** — would replace `mapping_loader.py`'s ~15 lines of manual key-checking with schema validation. Skipped: the mapping file's shape is small and stable enough that the manual version is easy to read; revisit if the schema grows.
- **`GitPython`** — would wrap `git ls-remote --tags`. Skipped: a single subprocess call is simpler and lighter than a full git-porcelain dependency, and the injectable `runner` callable already makes it trivially mockable.
- **`httpx`** — no benefit over `requests` here (no async need), and `responses` mocks `requests` more seamlessly than `httpx`'s mocking story for this project's needs.

## Design Clarification (read before starting)

The design doc's `.fedora-tracked-modules.yaml` example keys entries by "the exact Flatpak module `name`" and says the patcher "finds every source block belonging to a given module name." Inspecting the real manifest tree shows this needs one refinement for `pypi`/`pypi-multi-wheel` recipes:

Flatpak modules generated by `flatpak-pip-generator` routinely **bundle several unrelated PyPI packages as sibling `sources` entries under one module name** (e.g. the module `python3-requests` in `pip-resources.python-proton-core.yaml` bundles `certifi`, `charset_normalizer`, `idna`, `requests`, and `urllib3` as five separate source blocks; the module `python3-setuptools_scm` in `com.protonvpn.www.yml` bundles `vcs-versioning`, `pyparsing`, `tomli`, and `setuptools_scm`). The same PyPI package (e.g. `idna`, `cffi`, `cryptography`) also appears as a source block nested inside several *different* carrier modules across different files, never as a standalone module with a matching `name:` field.

Because of this, **Task 9 matches `pypi`/`pypi-multi-wheel` sources by the resolved PyPI distribution name found in the source's `url` filename prefix (normalized via `packaging.utils.canonicalize_name`), not by any module's `name:` field.** This is also what makes it safe to strip `x-checker-data` on every patched run: relocation on the *next* run no longer depends on `x-checker-data.name` surviving. Native `archive`/`git` recipes (`libndp`, `polkit`, `libnma`, `NetworkManager`, `NetworkManager-openvpn`, `systemd`, `iproute2`, `python-dbus`) *are* real standalone modules, so those are matched by the module's `name:` field, exactly as the design doc describes.

If this refinement is wrong for your intent, stop and raise it before Task 9 — it is the load-bearing decision for the whole patcher.

## File Structure

```
scripts/fedora_flatpak_updater/
  pyproject.toml
  uv.lock                 # generated by `uv sync`, committed
  README.md
  src/fedora_flatpak_updater/
    __init__.py
    fedora_release.py      # Bodhi client -> current stable branch string (tenacity retry)
    mdapi_client.py        # MdapiClient -> per-package Fedora version, cache + 404/5xx handling (tenacity retry)
    models.py              # RecipeKind enum, ModuleSpec dataclass
    mapping_loader.py      # .fedora-tracked-modules.yaml -> list[ModuleSpec]
    manifest_patcher.py    # ruamel.yaml forest loader + matchers + patch functions (packaging.canonicalize_name)
    migrate.py             # one-off helper that drafts the initial mapping file (click CLI)
    cli.py                 # orchestration + click entry point (tabulate summary table)
    recipes/
      __init__.py
      pypi.py               # resolve/resolve_wheel/resolve_sdist/resolve_multi_wheel
      archive.py            # render_url + sha256 download
      git.py                # ls-remote + peeled-tag resolution

tests/fedora_flatpak_updater/
  __init__.py
  test_fedora_release.py     # responses
  test_mdapi_client.py       # responses
  test_mapping_loader.py
  test_recipes_pypi.py       # responses
  test_recipes_archive.py    # responses
  test_recipes_git.py        # injectable runner callable, no HTTP
  test_manifest_patcher.py
  test_cli.py                # click.testing.CliRunner + direct run()/format_summary() calls
  fixtures/
    root.yml
    pip-resources.example.yaml

.fedora-tracked-modules.yaml            # repo root, the mapping data
.github/workflows/update-fedora-flatpak-deps.yml       # scheduled run + PR
.github/workflows/test-fedora-flatpak-updater.yml      # conditional test run on changes to the updater itself
```

Deleted as part of Task 1: `scripts/fedora_pip_updater/`, `.fedora-pip-mapping.yaml`, `tests/fedora_pip_updater/`, `docs/superpowers/plans/2026-05-29-fedora-pip-versions-workflow.md`.

All commands in this plan are run **from the repository root**, using `uv run --project scripts/fedora_flatpak_updater <command>` (which uses that project's environment without changing the working directory, so relative paths like `tests/fedora_flatpak_updater/...` and `com.protonvpn.www.yml` resolve against the repo root as expected).

---

### Task 1: Delete the obsolete scratch work

**Files:**
- Delete: `scripts/fedora_pip_updater/` (whole directory)
- Delete: `.fedora-pip-mapping.yaml`
- Delete: `tests/fedora_pip_updater/` (whole directory)
- Delete: `docs/superpowers/plans/2026-05-29-fedora-pip-versions-workflow.md`

**Interfaces:** None — this task has no code dependencies on later tasks.

- [ ] **Step 1: Delete the four paths**

```bash
git rm -r --cached scripts/fedora_pip_updater tests/fedora_pip_updater .fedora-pip-mapping.yaml docs/superpowers/plans/2026-05-29-fedora-pip-versions-workflow.md 2>/dev/null
rm -rf scripts/fedora_pip_updater tests/fedora_pip_updater
rm -f .fedora-pip-mapping.yaml docs/superpowers/plans/2026-05-29-fedora-pip-versions-workflow.md
```

- [ ] **Step 2: Verify nothing references the deleted package**

```bash
grep -rn "fedora_pip_updater\|fedora-pip-mapping" --include="*.py" --include="*.yml" --include="*.yaml" --include="*.md" .
```

Expected: no output (empty).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove incomplete fedora_pip_updater scratch work"
```

---

### Task 2: Scaffold the new package with `uv`

**Files:**
- Create: `scripts/fedora_flatpak_updater/pyproject.toml`
- Create: `scripts/fedora_flatpak_updater/README.md`
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/__init__.py`
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/__init__.py`
- Create: `tests/fedora_flatpak_updater/__init__.py`
- Modify: `.gitignore`

**Interfaces:** None — pure scaffolding, consumed implicitly by every later task's `uv run` commands.

- [ ] **Step 1: Create the package's `pyproject.toml`**

```toml
[project]
name = "fedora-flatpak-updater"
version = "0.1.0"
description = "Pins third-party Flatpak manifest dependencies to Fedora-stable versions"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "requests>=2.32",
    "ruamel.yaml>=0.18",
    "tenacity>=9.0",
    "click>=8.1",
    "tabulate>=0.9",
    "packaging>=24.0",
]

[project.scripts]
fedora-flatpak-updater = "fedora_flatpak_updater.cli:main"
fedora-flatpak-updater-migrate = "fedora_flatpak_updater.migrate:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "responses>=0.25",
]
```

- [ ] **Step 2: Create `scripts/fedora_flatpak_updater/README.md`**

```markdown
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
```

- [ ] **Step 3: Create empty package `__init__.py` files**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/__init__.py
```

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/__init__.py
```

```python
# tests/fedora_flatpak_updater/__init__.py
```

- [ ] **Step 4: Add the venv directory to `.gitignore` (keep `uv.lock` tracked)**

```
### Python (fedora_flatpak_updater) ###
scripts/fedora_flatpak_updater/.venv
**/__pycache__/
.pytest_cache
```

Append this block to the end of the existing `.gitignore`.

- [ ] **Step 5: Sync the environment with `uv`**

```bash
uv sync --project scripts/fedora_flatpak_updater
```

Expected: `uv` creates `scripts/fedora_flatpak_updater/.venv` and `scripts/fedora_flatpak_updater/uv.lock`, installing `requests`, `ruamel.yaml`, `tenacity`, `click`, `tabulate`, `packaging`, `pytest`, `responses`.

- [ ] **Step 6: Run pytest to confirm the empty suite collects cleanly**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
```

Expected: `no tests ran` (0 collected, exit code 0), no import errors.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold fedora_flatpak_updater package (uv-managed)"
```

---

### Task 3: `fedora_release.py` (Bodhi client, via `tenacity`)

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/fedora_release.py`
- Test: `tests/fedora_flatpak_updater/test_fedora_release.py`

**Interfaces:**
- Consumes: `tenacity.retry`, `tenacity.retry_if_exception_type`, `tenacity.stop_after_attempt`
- Produces: `get_current_stable_branch(session=None) -> str`, `BodhiLookupError`. Consumed later by `mdapi_client.py` usage in `cli.py` (`cli.py` imports `get_current_stable_branch` and `BodhiLookupError` directly from `fedora_flatpak_updater.fedora_release`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/fedora_flatpak_updater/test_fedora_release.py
from __future__ import annotations

import pytest
import requests
import responses

from fedora_flatpak_updater.fedora_release import BodhiLookupError, get_current_stable_branch

BODHI_URL = "https://bodhi.fedoraproject.org/releases/"

SAMPLE_PAYLOAD = {
    "releases": [
        {"id_prefix": "FEDORA", "version": "43", "released_on": "2025-04-15", "state": "current"},
        {"id_prefix": "FEDORA", "version": "44", "released_on": "2025-11-11", "state": "current"},
        {"id_prefix": "FEDORA", "version": "45", "released_on": None, "state": "current"},
        {"id_prefix": "FEDORA-CONTAINER", "version": "44", "released_on": "2025-11-11", "state": "current"},
        {"id_prefix": "FEDORA-FLATPAK", "version": "44", "released_on": "2025-11-11", "state": "current"},
        {"id_prefix": "FEDORA-EPEL", "version": "9", "released_on": "2022-01-01", "state": "current"},
    ]
}


@responses.activate
def test_picks_highest_released_fedora_version():
    responses.add(responses.GET, BODHI_URL, json=SAMPLE_PAYLOAD, status=200)
    assert get_current_stable_branch() == "f44"


@responses.activate
def test_retries_once_on_transient_failure_then_succeeds():
    responses.add(responses.GET, BODHI_URL, body=requests.exceptions.ConnectionError("network blip"))
    responses.add(responses.GET, BODHI_URL, json=SAMPLE_PAYLOAD, status=200)
    assert get_current_stable_branch() == "f44"


@responses.activate
def test_raises_bodhi_lookup_error_after_exhausting_retries():
    responses.add(responses.GET, BODHI_URL, body=requests.exceptions.ConnectionError("still broken"))
    responses.add(responses.GET, BODHI_URL, body=requests.exceptions.ConnectionError("still broken"))
    with pytest.raises(BodhiLookupError):
        get_current_stable_branch()


@responses.activate
def test_raises_bodhi_lookup_error_when_no_current_release_found():
    responses.add(responses.GET, BODHI_URL, json={"releases": []}, status=200)
    with pytest.raises(BodhiLookupError):
        get_current_stable_branch()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_fedora_release.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.fedora_release'`.

- [ ] **Step 3: Implement `fedora_release.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/fedora_release.py
from __future__ import annotations

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt

BODHI_RELEASES_URL = "https://bodhi.fedoraproject.org/releases/"


class BodhiLookupError(RuntimeError):
    """Raised when the current Fedora stable branch cannot be determined."""


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(2),  # 1 try + 1 retry
    reraise=True,
)
def _fetch_releases(session: requests.Session) -> dict:
    response = session.get(BODHI_RELEASES_URL, params={"state": "current"}, timeout=30)
    response.raise_for_status()
    return response.json()


def get_current_stable_branch(session: requests.Session | None = None) -> str:
    """Returns the current Fedora stable branch, e.g. "f44".

    Queries Bodhi for releases with state=current, keeps only entries whose
    id_prefix is exactly "FEDORA" (excluding *-CONTAINER/*-FLATPAK/*-EPEL*
    variants) and that have already been released (`released_on` is set),
    then returns the highest `version` among those.
    """
    session = session or requests.Session()
    try:
        payload = _fetch_releases(session)
    except requests.RequestException as exc:
        raise BodhiLookupError(f"Bodhi releases lookup failed: {exc}") from exc

    candidates = [
        release
        for release in payload.get("releases", [])
        if release.get("id_prefix") == "FEDORA"
        and release.get("released_on")
        and release.get("version") is not None
    ]
    if not candidates:
        raise BodhiLookupError("No current, released Fedora releases found in Bodhi response")

    newest = max(candidates, key=lambda release: int(release["version"]))
    return f"f{newest['version']}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_fedora_release.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add Bodhi current-stable-branch lookup with tenacity retry"
```

---

### Task 4: `mdapi_client.py` (via `tenacity`)

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mdapi_client.py`
- Test: `tests/fedora_flatpak_updater/test_mdapi_client.py`

**Interfaces:**
- Produces: `MdapiClient(branch, session=None)` with `.get_version(package_name) -> str`; `PackageNotFoundError(package_name, branch)`; `MdapiTransientError`. Consumed later by `cli.py` and `migrate.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fedora_flatpak_updater/test_mdapi_client.py
from __future__ import annotations

import pytest
import responses

from fedora_flatpak_updater.mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError


@responses.activate
def test_get_version_returns_version_field():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-cryptography"
    responses.add(responses.GET, url, json={"version": "46.0.7"}, status=200)

    client = MdapiClient("f44")
    assert client.get_version("python3-cryptography") == "46.0.7"


@responses.activate
def test_get_version_caches_repeat_calls():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-cryptography"
    responses.add(responses.GET, url, json={"version": "46.0.7"}, status=200)

    client = MdapiClient("f44")
    client.get_version("python3-cryptography")
    client.get_version("python3-cryptography")
    assert len(responses.calls) == 1


@responses.activate
def test_get_version_raises_package_not_found_on_404():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-does-not-exist"
    responses.add(responses.GET, url, status=404)

    client = MdapiClient("f44")
    with pytest.raises(PackageNotFoundError):
        client.get_version("python3-does-not-exist")


@responses.activate
def test_get_version_retries_once_on_5xx_then_succeeds():
    url = "https://mdapi.fedoraproject.org/f44/pkg/libndp"
    responses.add(responses.GET, url, status=502)
    responses.add(responses.GET, url, json={"version": "1.10"}, status=200)

    client = MdapiClient("f44")
    assert client.get_version("libndp") == "1.10"


@responses.activate
def test_get_version_raises_transient_error_after_two_5xx():
    url = "https://mdapi.fedoraproject.org/f44/pkg/libndp"
    responses.add(responses.GET, url, status=502)
    responses.add(responses.GET, url, status=502)

    client = MdapiClient("f44")
    with pytest.raises(MdapiTransientError):
        client.get_version("libndp")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_mdapi_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.mdapi_client'`.

- [ ] **Step 3: Implement `mdapi_client.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mdapi_client.py
from __future__ import annotations

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt

MDAPI_BASE = "https://mdapi.fedoraproject.org"


class PackageNotFoundError(Exception):
    def __init__(self, package_name: str, branch: str):
        super().__init__(f"{package_name} not found in Fedora {branch}")
        self.package_name = package_name
        self.branch = branch


class MdapiTransientError(RuntimeError):
    """Raised when MDAPI returns a server error even after one retry."""


class MdapiClient:
    """Thin client for mdapi.fedoraproject.org/<branch>/pkg/<name>, with a
    per-instance in-memory cache."""

    def __init__(self, branch: str, session: requests.Session | None = None):
        self.branch = branch
        self.session = session or requests.Session()
        self._cache: dict[str, str] = {}

    def get_version(self, package_name: str) -> str:
        if package_name in self._cache:
            return self._cache[package_name]

        url = f"{MDAPI_BASE}/{self.branch}/pkg/{package_name}"
        response = self._get_with_retry(url)

        if response.status_code == 404:
            raise PackageNotFoundError(package_name, self.branch)
        response.raise_for_status()

        version = response.json()["version"]
        self._cache[package_name] = version
        return version

    @retry(
        retry=retry_if_exception_type(MdapiTransientError),
        stop=stop_after_attempt(2),  # 1 try + 1 retry
        reraise=True,
    )
    def _get_with_retry(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=30)
        if response.status_code >= 500:
            raise MdapiTransientError(f"{url} returned {response.status_code}")
        return response
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_mdapi_client.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add MDAPI client with caching and tenacity-based 5xx retry"
```

---

### Task 5: `models.py` + `mapping_loader.py`

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/models.py`
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mapping_loader.py`
- Test: `tests/fedora_flatpak_updater/test_mapping_loader.py`

**Interfaces:**
- Produces: `RecipeKind` enum (`PYPI="pypi"`, `PYPI_MULTI_WHEEL="pypi-multi-wheel"`, `ARCHIVE="archive"`, `GIT="git"`); `ModuleSpec` frozen dataclass with fields `name, fedora_package, recipe, pypi_name=None, prefer="wheel", wheel_arches=(), url_template=None, repo_url=None, tag_template=None, tag_pattern=None, manual_followup=None`; `load_mapping(path) -> list[ModuleSpec]`; `MappingError`. Consumed by `manifest_patcher.py` and `cli.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fedora_flatpak_updater/test_mapping_loader.py
from __future__ import annotations

from pathlib import Path

import pytest

from fedora_flatpak_updater.mapping_loader import MappingError, load_mapping
from fedora_flatpak_updater.models import RecipeKind


def test_load_mapping_parses_all_recipe_kinds(tmp_path: Path):
    mapping_file = tmp_path / ".fedora-tracked-modules.yaml"
    mapping_file.write_text(
        """
modules:
  python3-idna:
    fedora_package: python3-idna
    recipe: pypi
    pypi_name: idna
    prefer: wheel
  python3-cryptography:
    fedora_package: python3-cryptography
    recipe: pypi-multi-wheel
    pypi_name: cryptography
    wheel_arches: [aarch64, x86_64]
  libndp:
    fedora_package: libndp
    recipe: archive
    url_template: "https://github.com/jpirko/libndp/archive/v$version.tar.gz"
  NetworkManager:
    fedora_package: NetworkManager
    recipe: git
    repo_url: "https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git"
    tag_template: "$version"
  python3-bcrypt:
    fedora_package: python3-bcrypt
    recipe: pypi
    pypi_name: bcrypt
    manual_followup: "regenerate bcrypt-cargo-sources.json"
"""
    )

    specs = load_mapping(mapping_file)
    by_name = {spec.name: spec for spec in specs}

    assert by_name["python3-idna"].recipe == RecipeKind.PYPI
    assert by_name["python3-idna"].pypi_name == "idna"

    assert by_name["python3-cryptography"].recipe == RecipeKind.PYPI_MULTI_WHEEL
    assert by_name["python3-cryptography"].wheel_arches == ("aarch64", "x86_64")

    assert by_name["libndp"].recipe == RecipeKind.ARCHIVE
    assert by_name["libndp"].url_template.endswith("v$version.tar.gz")

    assert by_name["NetworkManager"].recipe == RecipeKind.GIT
    assert by_name["NetworkManager"].tag_template == "$version"

    assert by_name["python3-bcrypt"].manual_followup == "regenerate bcrypt-cargo-sources.json"


def test_load_mapping_rejects_missing_recipe(tmp_path: Path):
    mapping_file = tmp_path / ".fedora-tracked-modules.yaml"
    mapping_file.write_text(
        """
modules:
  broken:
    fedora_package: broken
"""
    )
    with pytest.raises(MappingError):
        load_mapping(mapping_file)


def test_load_mapping_rejects_missing_fedora_package(tmp_path: Path):
    mapping_file = tmp_path / ".fedora-tracked-modules.yaml"
    mapping_file.write_text(
        """
modules:
  broken:
    recipe: pypi
    pypi_name: broken
"""
    )
    with pytest.raises(MappingError):
        load_mapping(mapping_file)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_mapping_loader.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.mapping_loader'`.

- [ ] **Step 3: Implement `models.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/models.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecipeKind(str, Enum):
    PYPI = "pypi"
    PYPI_MULTI_WHEEL = "pypi-multi-wheel"
    ARCHIVE = "archive"
    GIT = "git"


@dataclass(frozen=True)
class ModuleSpec:
    """One entry from .fedora-tracked-modules.yaml."""

    name: str
    fedora_package: str
    recipe: RecipeKind
    pypi_name: str | None = None
    prefer: str = "wheel"
    wheel_arches: tuple[str, ...] = ()
    url_template: str | None = None
    repo_url: str | None = None
    tag_template: str | None = None
    tag_pattern: str | None = None
    manual_followup: str | None = None
```

- [ ] **Step 4: Implement `mapping_loader.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mapping_loader.py
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from .models import ModuleSpec, RecipeKind

_yaml = YAML(typ="safe")


class MappingError(ValueError):
    """Raised when .fedora-tracked-modules.yaml is malformed."""


def load_mapping(path: Path) -> list[ModuleSpec]:
    with Path(path).open("r", encoding="utf-8") as fh:
        raw = _yaml.load(fh) or {}

    modules = raw.get("modules") or {}
    specs: list[ModuleSpec] = []
    for name, entry in modules.items():
        if not isinstance(entry, dict):
            raise MappingError(f"{name}: entry must be a mapping")
        try:
            recipe = RecipeKind(entry["recipe"])
        except (KeyError, ValueError) as exc:
            raise MappingError(f"{name}: invalid or missing 'recipe'") from exc
        if "fedora_package" not in entry:
            raise MappingError(f"{name}: missing 'fedora_package'")

        specs.append(
            ModuleSpec(
                name=name,
                fedora_package=entry["fedora_package"],
                recipe=recipe,
                pypi_name=entry.get("pypi_name"),
                prefer=entry.get("prefer", "wheel"),
                wheel_arches=tuple(entry.get("wheel_arches", ())),
                url_template=entry.get("url_template"),
                repo_url=entry.get("repo_url"),
                tag_template=entry.get("tag_template"),
                tag_pattern=entry.get("tag_pattern"),
                manual_followup=entry.get("manual_followup"),
            )
        )
    return specs
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_mapping_loader.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add ModuleSpec/RecipeKind models and mapping file loader"
```

---

### Task 6: `recipes/pypi.py`

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/pypi.py`
- Test: `tests/fedora_flatpak_updater/test_recipes_pypi.py`

**Interfaces:**
- Produces: `PypiSource(url, sha256, only_arches=())` dataclass; `resolve_wheel`, `resolve_sdist`, `resolve(pypi_name, version, *, prefer="wheel", session=None)`, `resolve_multi_wheel(pypi_name, version, wheel_arches, session=None) -> dict[str, PypiSource]`; `PypiVersionNotFoundError`. Consumed by `cli.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fedora_flatpak_updater/test_recipes_pypi.py
from __future__ import annotations

import pytest
import responses

from fedora_flatpak_updater.recipes.pypi import (
    PypiVersionNotFoundError,
    resolve,
    resolve_multi_wheel,
    resolve_sdist,
    resolve_wheel,
)

IDNA_URL = "https://pypi.org/pypi/idna/3.11/json"
IDNA_JSON = {
    "urls": [
        {
            "packagetype": "sdist",
            "url": "https://files.pythonhosted.org/packages/.../idna-3.11.tar.gz",
            "digests": {"sha256": "sdist" + "0" * 59},
        },
        {
            "packagetype": "bdist_wheel",
            "filename": "idna-3.11-py3-none-any.whl",
            "url": "https://files.pythonhosted.org/packages/.../idna-3.11-py3-none-any.whl",
            "digests": {"sha256": "wheel" + "0" * 59},
        },
    ]
}

CRYPTOGRAPHY_URL = "https://pypi.org/pypi/cryptography/46.0.7/json"
CRYPTOGRAPHY_JSON = {
    "urls": [
        {
            "packagetype": "bdist_wheel",
            "filename": "cryptography-46.0.7-cp311-abi3-manylinux_2_28_aarch64.whl",
            "url": "https://files.pythonhosted.org/.../cryptography-46.0.7-cp311-abi3-manylinux_2_28_aarch64.whl",
            "digests": {"sha256": "aarch64" + "0" * 57},
        },
        {
            "packagetype": "bdist_wheel",
            "filename": "cryptography-46.0.7-cp311-abi3-manylinux_2_28_x86_64.whl",
            "url": "https://files.pythonhosted.org/.../cryptography-46.0.7-cp311-abi3-manylinux_2_28_x86_64.whl",
            "digests": {"sha256": "x86_64" + "0" * 58},
        },
    ]
}


@responses.activate
def test_resolve_wheel_picks_bdist_wheel_entry():
    responses.add(responses.GET, IDNA_URL, json=IDNA_JSON, status=200)
    source = resolve_wheel("idna", "3.11")
    assert source.url.endswith(".whl")
    assert source.sha256.startswith("wheel")


@responses.activate
def test_resolve_sdist_picks_sdist_entry():
    responses.add(responses.GET, IDNA_URL, json=IDNA_JSON, status=200)
    source = resolve_sdist("idna", "3.11")
    assert source.url.endswith(".tar.gz")
    assert source.sha256.startswith("sdist")


@responses.activate
def test_resolve_prefers_wheel_by_default():
    responses.add(responses.GET, IDNA_URL, json=IDNA_JSON, status=200)
    source = resolve("idna", "3.11")
    assert source.url.endswith(".whl")


@responses.activate
def test_resolve_falls_back_to_sdist_when_no_wheel_available():
    payload = {"urls": [IDNA_JSON["urls"][0]]}  # sdist only
    responses.add(responses.GET, IDNA_URL, json=payload, status=200)
    source = resolve("idna", "3.11", prefer="wheel")
    assert source.url.endswith(".tar.gz")


@responses.activate
def test_resolve_raises_when_version_missing_on_pypi():
    responses.add(responses.GET, "https://pypi.org/pypi/idna/999.0/json", status=404)
    with pytest.raises(PypiVersionNotFoundError):
        resolve("idna", "999.0")


@responses.activate
def test_resolve_multi_wheel_selects_one_wheel_per_arch():
    responses.add(responses.GET, CRYPTOGRAPHY_URL, json=CRYPTOGRAPHY_JSON, status=200)
    result = resolve_multi_wheel("cryptography", "46.0.7", ("aarch64", "x86_64"))
    assert result["aarch64"].sha256.startswith("aarch64")
    assert result["x86_64"].sha256.startswith("x86_64")
    assert result["aarch64"].only_arches == ("aarch64",)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_recipes_pypi.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.recipes.pypi'`.

- [ ] **Step 3: Implement `recipes/pypi.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/pypi.py
from __future__ import annotations

from dataclasses import dataclass

import requests

PYPI_BASE = "https://pypi.org/pypi"


class PypiVersionNotFoundError(RuntimeError):
    """Raised when a specific pypi_name==version has no usable distribution."""


@dataclass(frozen=True)
class PypiSource:
    url: str
    sha256: str
    only_arches: tuple[str, ...] = ()


def fetch_release_files(pypi_name: str, version: str, session: requests.Session | None = None) -> list[dict]:
    session = session or requests.Session()
    url = f"{PYPI_BASE}/{pypi_name}/{version}/json"
    response = session.get(url, timeout=30)
    if response.status_code == 404:
        raise PypiVersionNotFoundError(f"{pypi_name}=={version} not found on PyPI")
    response.raise_for_status()
    return response.json()["urls"]


def resolve_wheel(pypi_name: str, version: str, session: requests.Session | None = None) -> PypiSource:
    for file_info in fetch_release_files(pypi_name, version, session):
        if file_info["packagetype"] == "bdist_wheel":
            return PypiSource(url=file_info["url"], sha256=file_info["digests"]["sha256"])
    raise PypiVersionNotFoundError(f"No wheel for {pypi_name}=={version}")


def resolve_sdist(pypi_name: str, version: str, session: requests.Session | None = None) -> PypiSource:
    for file_info in fetch_release_files(pypi_name, version, session):
        if file_info["packagetype"] == "sdist":
            return PypiSource(url=file_info["url"], sha256=file_info["digests"]["sha256"])
    raise PypiVersionNotFoundError(f"No sdist for {pypi_name}=={version}")


def resolve(
    pypi_name: str,
    version: str,
    *,
    prefer: str = "wheel",
    session: requests.Session | None = None,
) -> PypiSource:
    primary, fallback = (resolve_wheel, resolve_sdist) if prefer == "wheel" else (resolve_sdist, resolve_wheel)
    try:
        return primary(pypi_name, version, session)
    except PypiVersionNotFoundError:
        return fallback(pypi_name, version, session)


def resolve_multi_wheel(
    pypi_name: str,
    version: str,
    wheel_arches: tuple[str, ...],
    session: requests.Session | None = None,
) -> dict[str, PypiSource]:
    """The `cryptography` case: one manylinux wheel per architecture."""
    files = fetch_release_files(pypi_name, version, session)
    result: dict[str, PypiSource] = {}
    for arch in wheel_arches:
        for file_info in files:
            if file_info["packagetype"] != "bdist_wheel":
                continue
            filename = file_info["filename"]
            if arch in filename and "manylinux" in filename:
                result[arch] = PypiSource(
                    url=file_info["url"],
                    sha256=file_info["digests"]["sha256"],
                    only_arches=(arch,),
                )
                break
        else:
            raise PypiVersionNotFoundError(f"No wheel for {pypi_name}=={version} arch={arch}")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_recipes_pypi.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add pypi recipe (wheel/sdist/multi-wheel resolution)"
```

---

### Task 7: `recipes/archive.py`

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/archive.py`
- Test: `tests/fedora_flatpak_updater/test_recipes_archive.py`

**Interfaces:**
- Produces: `ArchiveSource(url, sha256)` dataclass; `render_url(url_template, version) -> str`; `resolve(url_template, version, session=None) -> ArchiveSource`; `ArchiveResolutionError`. Consumed by `cli.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fedora_flatpak_updater/test_recipes_archive.py
from __future__ import annotations

import hashlib

import pytest
import responses

from fedora_flatpak_updater.recipes.archive import ArchiveResolutionError, render_url, resolve


def test_render_url_substitutes_version():
    rendered = render_url("https://github.com/jpirko/libndp/archive/v$version.tar.gz", "1.10")
    assert rendered == "https://github.com/jpirko/libndp/archive/v1.10.tar.gz"


@responses.activate
def test_resolve_computes_sha256_of_downloaded_content():
    content = b"fake tarball bytes"
    url = "https://github.com/jpirko/libndp/archive/v1.10.tar.gz"
    responses.add(responses.GET, url, body=content, status=200)

    source = resolve("https://github.com/jpirko/libndp/archive/v$version.tar.gz", "1.10")

    assert source.url == url
    assert source.sha256 == hashlib.sha256(content).hexdigest()


@responses.activate
def test_resolve_raises_on_404():
    url = "https://gitlab.freedesktop.org/polkit/polkit/-/archive/127/polkit-127.tar.gz"
    responses.add(responses.GET, url, status=404)

    with pytest.raises(ArchiveResolutionError):
        resolve(
            "https://gitlab.freedesktop.org/polkit/polkit/-/archive/$version/polkit-$version.tar.gz",
            "127",
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_recipes_archive.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.recipes.archive'`.

- [ ] **Step 3: Implement `recipes/archive.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/archive.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from string import Template

import requests


class ArchiveResolutionError(RuntimeError):
    """Raised when a rendered archive URL cannot be fetched."""


@dataclass(frozen=True)
class ArchiveSource:
    url: str
    sha256: str


def render_url(url_template: str, version: str) -> str:
    return Template(url_template).substitute(version=version)


def resolve(url_template: str, version: str, session: requests.Session | None = None) -> ArchiveSource:
    session = session or requests.Session()
    url = render_url(url_template, version)
    response = session.get(url, timeout=60, stream=True)
    if response.status_code == 404:
        raise ArchiveResolutionError(f"{url} returned 404")
    response.raise_for_status()

    digest = hashlib.sha256()
    for chunk in response.iter_content(chunk_size=65536):
        digest.update(chunk)
    return ArchiveSource(url=url, sha256=digest.hexdigest())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_recipes_archive.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add archive recipe (url templating + sha256 download)"
```

---

### Task 8: `recipes/git.py`

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/git.py`
- Test: `tests/fedora_flatpak_updater/test_recipes_git.py`

**Interfaces:**
- Produces: `GitSource(tag, commit)` dataclass; `resolve(*, repo_url, version, tag_template=None, tag_pattern=None, runner=subprocess.run) -> GitSource`; `GitTagNotFoundError`. Consumed by `cli.py`.

No HTTP is involved here (`git ls-remote` is a subprocess call), so `responses` doesn't apply — the injectable `runner` callable is already the simplest way to make this testable without a real network/git dependency.

- [ ] **Step 1: Write the failing test**

```python
# tests/fedora_flatpak_updater/test_recipes_git.py
from __future__ import annotations

import pytest

from fedora_flatpak_updater.recipes.git import GitTagNotFoundError, resolve

NETWORKMANAGER_LS_REMOTE = (
    "2db3748ec8162ce948ba52f71b42a258ff8d64ba\trefs/tags/1.40.18\n"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/1.54.3\n"
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/1.54.3^{}\n"
)

SYSTEMD_LS_REMOTE = (
    "cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v259.0\n"
    "dddddddddddddddddddddddddddddddddddddddd\trefs/tags/v260.2\n"
    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\trefs/tags/v260.2^{}\n"
)


class _FakeCompleted:
    def __init__(self, stdout: str):
        self.stdout = stdout


def _runner_returning(stdout: str):
    def runner(*args, **kwargs):
        return _FakeCompleted(stdout)

    return runner


def test_resolve_by_tag_template_prefers_peeled_hash():
    source = resolve(
        repo_url="https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
        version="1.54.3",
        tag_template="$version",
        runner=_runner_returning(NETWORKMANAGER_LS_REMOTE),
    )
    assert source.tag == "1.54.3"
    assert source.commit == "b" * 40


def test_resolve_by_tag_pattern_matches_captured_version():
    source = resolve(
        repo_url="https://github.com/systemd/systemd.git",
        version="260.2",
        tag_pattern=r"^v([\d.]+)$",
        runner=_runner_returning(SYSTEMD_LS_REMOTE),
    )
    assert source.tag == "v260.2"
    assert source.commit == "e" * 40


def test_resolve_raises_when_tag_not_found():
    with pytest.raises(GitTagNotFoundError):
        resolve(
            repo_url="https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
            version="99.0.0",
            tag_template="$version",
            runner=_runner_returning(NETWORKMANAGER_LS_REMOTE),
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_recipes_git.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.recipes.git'`.

- [ ] **Step 3: Implement `recipes/git.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/git.py
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from string import Template


class GitTagNotFoundError(RuntimeError):
    """Raised when the target tag cannot be found on the remote."""


@dataclass(frozen=True)
class GitSource:
    tag: str
    commit: str


def _ls_remote_tags(repo_url: str, runner) -> list[tuple[str, str]]:
    result = runner(
        ["git", "ls-remote", "--tags", repo_url],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    entries = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, ref = line.split("\t", 1)
        entries.append((sha, ref.strip()))
    return entries


def resolve(
    *,
    repo_url: str,
    version: str,
    tag_template: str | None = None,
    tag_pattern: str | None = None,
    runner=subprocess.run,
) -> GitSource:
    if not tag_template and not tag_pattern:
        raise ValueError("Either tag_template or tag_pattern must be provided")

    entries = _ls_remote_tags(repo_url, runner)

    by_tag: dict[str, dict[str, str]] = {}
    for sha, ref in entries:
        if not ref.startswith("refs/tags/"):
            continue
        peeled = ref.endswith("^{}")
        tag_name = ref[len("refs/tags/"):]
        if peeled:
            tag_name = tag_name[: -len("^{}")]
        by_tag.setdefault(tag_name, {})["peeled" if peeled else "plain"] = sha

    if tag_template:
        target_tag = Template(tag_template).substitute(version=version)
    else:
        pattern = re.compile(tag_pattern)
        target_tag = None
        for tag_name in by_tag:
            match = pattern.match(tag_name)
            if match and match.group(1) == version:
                target_tag = tag_name
                break
        if target_tag is None:
            raise GitTagNotFoundError(
                f"no tag matching {tag_pattern!r} for version {version} on {repo_url}"
            )

    hashes = by_tag.get(target_tag)
    if not hashes:
        raise GitTagNotFoundError(f"tried tag {target_tag!r} on {repo_url}, not found")

    commit = hashes.get("peeled") or hashes.get("plain")
    return GitSource(tag=target_tag, commit=commit)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_recipes_git.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add git recipe (tag-template/tag-pattern + peeled hash resolution)"
```

---

### Task 9: `manifest_patcher.py` (via `packaging.utils.canonicalize_name`)

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/manifest_patcher.py`
- Test: `tests/fedora_flatpak_updater/test_manifest_patcher.py`
- Fixture: `tests/fedora_flatpak_updater/fixtures/root.yml`
- Fixture: `tests/fedora_flatpak_updater/fixtures/pip-resources.example.yaml`

**Interfaces:**
- Consumes: `fedora_flatpak_updater.models.ModuleSpec`, `fedora_flatpak_updater.recipes.pypi.PypiSource`, `fedora_flatpak_updater.recipes.archive.ArchiveSource`, `fedora_flatpak_updater.recipes.git.GitSource`, `packaging.utils.canonicalize_name`
- Produces: `ManifestForest(root_path)` with `.iter_dicts()` and `.save() -> list[Path]`; `find_module_blocks(forest, module_name) -> list[dict]`; `find_pypi_source_blocks(forest, pypi_name) -> list[dict]`; `apply_pypi(forest, spec, resolve_block) -> PatchReport`; `apply_archive(forest, spec, source) -> PatchReport`; `apply_git(forest, spec, source) -> PatchReport`; `PatchReport(module_name, blocks_touched, files_touched)`. Consumed by `cli.py`.

- [ ] **Step 1: Create the fixture files**

```yaml
# tests/fedora_flatpak_updater/fixtures/root.yml
modules:
  - name: python3-idna
    buildsystem: simple
    build-commands:
      - pip3 install idna
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/94/16/idna-3.16-py3-none-any.whl
        sha256: cc246e3a3f89580c3a951b5ad298ca4638078b2cdd4f115654332b5c26daded5
        x-checker-data:
          name: idna
          packagetype: bdist_wheel
          type: pypi

  # keep me: comment that must survive patching
  - name: libndp
    buildsystem: autotools
    cleanup:
      - /bin
      - /include
    sources:
      - type: archive
        url: https://github.com/jpirko/libndp/archive/v1.9.tar.gz
        sha256: e564f5914a6b1b799c3afa64c258824a801c1b79a29e2fe6525b682249c65261
        x-checker-data:
          type: anitya
          project-id: 14944
          url-template: https://github.com/jpirko/libndp/archive/v$version.tar.gz

  - name: python-proton-core
    buildsystem: simple
    build-commands:
      - pip3 install .
    modules:
      - pip-resources.example.yaml
    sources:
      - type: git
        url: https://github.com/ProtonVPN/python-proton-core
        tag: v0.7.0
        commit: f7a178a99c3adc0e88c7f91d4db5371a052c4985
```

```yaml
# tests/fedora_flatpak_updater/fixtures/pip-resources.example.yaml
name: pip-resources.example
build-commands: []
buildsystem: simple
modules:
  - name: python3-requests
    buildsystem: simple
    build-commands:
      - pip3 install requests
    sources:
      - &idna_anchor
        type: file
        url: https://files.pythonhosted.org/packages/94/16/idna-3.16-py3-none-any.whl
        sha256: cc246e3a3f89580c3a951b5ad298ca4638078b2cdd4f115654332b5c26daded5
        x-checker-data:
          name: idna
          packagetype: bdist_wheel
          type: pypi
      - type: file
        url: https://files.pythonhosted.org/packages/a0/f4/requests-2.34.2-py3-none-any.whl
        sha256: 2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0
        x-checker-data:
          name: requests
          packagetype: bdist_wheel
          type: pypi
  - name: python3-flit_core
    buildsystem: simple
    build-commands:
      - pip3 install flit_core
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/69/59/flit_core-3.12.0.tar.gz
        sha256: 18f63100d6f94385c6ed57a72073443e1a71a4acb4339491615d0f16d6ff01b2
        x-checker-data:
          type: pypi
          name: flit_core
  - name: python3-flit_core_dup
    buildsystem: simple
    build-commands:
      - pip3 install flit_core
    sources:
      - type: file
        url: https://files.pythonhosted.org/packages/69/59/flit_core-3.12.0.tar.gz
        sha256: 18f63100d6f94385c6ed57a72073443e1a71a4acb4339491615d0f16d6ff01b2
        x-checker-data:
          type: pypi
          name: flit_core
      - *idna_anchor
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/fedora_flatpak_updater/test_manifest_patcher.py
from __future__ import annotations

from pathlib import Path

from fedora_flatpak_updater.manifest_patcher import (
    ManifestForest,
    apply_archive,
    apply_git,
    apply_pypi,
    find_module_blocks,
    find_pypi_source_blocks,
)
from fedora_flatpak_updater.models import ModuleSpec, RecipeKind
from fedora_flatpak_updater.recipes.archive import ArchiveSource
from fedora_flatpak_updater.recipes.git import GitSource
from fedora_flatpak_updater.recipes.pypi import PypiSource

FIXTURES = Path(__file__).parent / "fixtures"


def _fresh_forest(tmp_path: Path) -> ManifestForest:
    for name in ("root.yml", "pip-resources.example.yaml"):
        (tmp_path / name).write_text((FIXTURES / name).read_text())
    return ManifestForest(tmp_path / "root.yml")


def test_find_pypi_source_blocks_finds_every_occurrence_across_files(tmp_path):
    forest = _fresh_forest(tmp_path)
    blocks = find_pypi_source_blocks(forest, "idna")
    assert len(blocks) == 2  # root.yml's own block + the shared anchor/alias block


def test_apply_pypi_updates_every_occurrence_and_strips_checker_data(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-idna", fedora_package="python3-idna", recipe=RecipeKind.PYPI, pypi_name="idna")
    new_source = PypiSource(url="https://files.pythonhosted.org/idna-3.11-py3-none-any.whl", sha256="deadbeef")

    report = apply_pypi(forest, spec, lambda block: new_source)

    assert report.blocks_touched == 2
    for block in find_pypi_source_blocks(forest, "idna"):
        assert block["url"] == new_source.url
        assert block["sha256"] == new_source.sha256
        assert "x-checker-data" not in block


def test_apply_pypi_leaves_unrelated_packages_untouched(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-idna", fedora_package="python3-idna", recipe=RecipeKind.PYPI, pypi_name="idna")
    apply_pypi(forest, spec, lambda block: PypiSource(url="https://x/idna-3.11-py3-none-any.whl", sha256="deadbeef"))

    [requests_block] = find_pypi_source_blocks(forest, "requests")
    assert requests_block["sha256"] == "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0"
    assert requests_block["x-checker-data"]["name"] == "requests"


def test_apply_pypi_updates_duplicate_module_occurrences_independently(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-flit_core", fedora_package="python3-flit_core", recipe=RecipeKind.PYPI, pypi_name="flit_core")
    new_source = PypiSource(url="https://x/flit_core-4.0.0.tar.gz", sha256="cafef00d")

    report = apply_pypi(forest, spec, lambda block: new_source)

    assert report.blocks_touched == 2
    assert all(b["url"] == new_source.url for b in find_pypi_source_blocks(forest, "flit_core"))


def test_apply_archive_updates_module_matched_by_name(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(
        name="libndp",
        fedora_package="libndp",
        recipe=RecipeKind.ARCHIVE,
        url_template="https://github.com/jpirko/libndp/archive/v$version.tar.gz",
    )
    source = ArchiveSource(url="https://github.com/jpirko/libndp/archive/v1.10.tar.gz", sha256="abc123")

    report = apply_archive(forest, spec, source)

    assert report.blocks_touched == 1
    [module] = find_module_blocks(forest, "libndp")
    [src] = module["sources"]
    assert src["url"] == source.url
    assert src["sha256"] == source.sha256
    assert "x-checker-data" not in src


def test_apply_git_updates_tag_and_commit(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(
        name="python-proton-core",
        fedora_package="python-proton-core",
        recipe=RecipeKind.GIT,
        repo_url="https://github.com/ProtonVPN/python-proton-core",
        tag_template="v$version",
    )
    source = GitSource(tag="v0.8.0", commit="a" * 40)

    report = apply_git(forest, spec, source)

    assert report.blocks_touched == 1
    [module] = find_module_blocks(forest, "python-proton-core")
    [src] = module["sources"]
    assert src["tag"] == "v0.8.0"
    assert src["commit"] == "a" * 40


def test_save_preserves_comments_and_unrelated_structure(tmp_path):
    forest = _fresh_forest(tmp_path)
    spec = ModuleSpec(name="python3-idna", fedora_package="python3-idna", recipe=RecipeKind.PYPI, pypi_name="idna")
    apply_pypi(forest, spec, lambda block: PypiSource(url="https://x/idna-3.11-py3-none-any.whl", sha256="deadbeef"))
    forest.save()

    root_text = (tmp_path / "root.yml").read_text()
    assert "keep me: comment that must survive patching" in root_text
    assert "buildsystem: autotools" in root_text
    assert "cleanup:" in root_text
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_manifest_patcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.manifest_patcher'`.

- [ ] **Step 4: Implement `manifest_patcher.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/manifest_patcher.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from packaging.utils import canonicalize_name
from ruamel.yaml import YAML


def _matches_pypi_name(url: str, pypi_name: str) -> bool:
    filename = url.rsplit("/", 1)[-1].lower()
    canonical = str(canonicalize_name(pypi_name))  # PEP 503, e.g. "jaraco-classes"
    prefixes = {
        pypi_name.lower() + "-",
        canonical + "-",
        canonical.replace("-", "_") + "-",  # wheel filenames use underscores
    }
    return any(filename.startswith(prefix) for prefix in prefixes)


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


@dataclass
class PatchReport:
    module_name: str
    blocks_touched: int
    files_touched: tuple[str, ...] = ()


class ManifestForest:
    """Loads the root manifest and every pip-resources.*.yaml it
    (transitively) references as separate ruamel round-trip documents, keyed
    by resolved Path, so each file can be re-serialized independently."""

    def __init__(self, root_path: Path):
        self._yaml = YAML(typ="rt")
        self._yaml.preserve_quotes = True
        self._yaml.width = 1_000_000  # never re-wrap lines we didn't touch
        self.root_path = Path(root_path).resolve()
        self.documents: dict[Path, Any] = {}
        self._load(self.root_path)

    def _load(self, path: Path) -> None:
        if path in self.documents:
            return
        with path.open("r", encoding="utf-8") as fh:
            data = self._yaml.load(fh)
        self.documents[path] = data
        self._discover_refs(data, path.parent)

    def _discover_refs(self, node: Any, base_dir: Path) -> None:
        if isinstance(node, dict):
            modules = node.get("modules")
            if isinstance(modules, list):
                for item in modules:
                    if isinstance(item, str):
                        self._load((base_dir / item).resolve())
                    elif isinstance(item, dict):
                        self._discover_refs(item, base_dir)
            for key, value in node.items():
                if key == "modules":
                    continue
                self._discover_refs(value, base_dir)
        elif isinstance(node, list):
            for item in node:
                self._discover_refs(item, base_dir)

    def iter_dicts(self):
        for data in self.documents.values():
            yield from _iter_dicts(data)

    def save(self) -> list[Path]:
        written = []
        for path, data in self.documents.items():
            with path.open("w", encoding="utf-8") as fh:
                self._yaml.dump(data, fh)
            written.append(path)
        return written


def find_module_blocks(forest: ManifestForest, module_name: str) -> list[dict]:
    """archive/git recipes: match standalone flatpak modules by `name:`."""
    return [d for d in forest.iter_dicts() if d.get("name") == module_name and "sources" in d]


def find_pypi_source_blocks(forest: ManifestForest, pypi_name: str) -> list[dict]:
    """pypi/pypi-multi-wheel recipes: match source dicts by URL filename
    prefix, since the same PyPI package routinely appears bundled inside
    many differently-named carrier modules across the manifest forest."""
    return [
        d
        for d in forest.iter_dicts()
        if d.get("type") in ("file", "archive")
        and isinstance(d.get("url"), str)
        and _matches_pypi_name(d["url"], pypi_name)
    ]


def apply_pypi(forest: ManifestForest, spec, resolve_block: Callable[[dict], Any]) -> PatchReport:
    """`resolve_block(current_block)` is called once per matched block so
    each occurrence can be resolved according to its own existing shape
    (wheel vs sdist, arch-specific vs generic)."""
    blocks = find_pypi_source_blocks(forest, spec.pypi_name)
    touched = 0
    for block in blocks:
        source = resolve_block(block)
        if source is None:
            continue
        block["url"] = source.url
        block["sha256"] = source.sha256
        block.pop("x-checker-data", None)
        touched += 1
    return PatchReport(module_name=spec.name, blocks_touched=touched)


def apply_archive(forest: ManifestForest, spec, source) -> PatchReport:
    touched = 0
    for module_block in find_module_blocks(forest, spec.name):
        for src in module_block.get("sources", []):
            if isinstance(src, dict) and src.get("type") == "archive":
                src["url"] = source.url
                src["sha256"] = source.sha256
                src.pop("x-checker-data", None)
                touched += 1
    return PatchReport(module_name=spec.name, blocks_touched=touched)


def apply_git(forest: ManifestForest, spec, source) -> PatchReport:
    touched = 0
    for module_block in find_module_blocks(forest, spec.name):
        for src in module_block.get("sources", []):
            if isinstance(src, dict) and src.get("type") == "git":
                src["tag"] = source.tag
                src["commit"] = source.commit
                src.pop("x-checker-data", None)
                touched += 1
    return PatchReport(module_name=spec.name, blocks_touched=touched)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_manifest_patcher.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add ruamel-based manifest forest loader and patch functions"
```

---

### Task 10: `cli.py` (via `click` + `tabulate`)

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cli.py`
- Test: `tests/fedora_flatpak_updater/test_cli.py`

**Interfaces:**
- Consumes: `fedora_release.get_current_stable_branch`, `fedora_release.BodhiLookupError`, `mdapi_client.MdapiClient`, `mdapi_client.PackageNotFoundError`, `mdapi_client.MdapiTransientError`, `mapping_loader.load_mapping`, `manifest_patcher.ManifestForest/apply_pypi/apply_archive/apply_git`, `models.RecipeKind`, `recipes.pypi`, `recipes.archive`, `recipes.git`, `click`, `tabulate.tabulate`
- Produces: `Row(module_name, status, detail)`; `run(mapping_path, manifest_root, *, dry_run=False, only=None) -> list[Row]`; `format_summary(rows) -> str`; `main` (a `click.Command`, the package's console-script entry point). Consumed by the GitHub Actions workflow in Task 13.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fedora_flatpak_updater/test_cli.py
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from fedora_flatpak_updater import cli
from fedora_flatpak_updater.mdapi_client import PackageNotFoundError
from fedora_flatpak_updater.recipes.archive import ArchiveSource
from fedora_flatpak_updater.recipes.pypi import PypiSource

FIXTURES = Path(__file__).parent / "fixtures"


class FakeMdapi:
    _VERSIONS = {"python3-idna": "3.99", "libndp": "9.9"}

    def __init__(self, branch, session=None):
        self.branch = branch

    def get_version(self, package_name):
        if package_name not in self._VERSIONS:
            raise PackageNotFoundError(package_name, self.branch)
        return self._VERSIONS[package_name]


@pytest.fixture
def manifest_root(tmp_path):
    for name in ("root.yml", "pip-resources.example.yaml"):
        (tmp_path / name).write_text((FIXTURES / name).read_text())
    return tmp_path / "root.yml"


@pytest.fixture
def mapping_file(tmp_path):
    path = tmp_path / ".fedora-tracked-modules.yaml"
    path.write_text(
        """
modules:
  python3-idna:
    fedora_package: python3-idna
    recipe: pypi
    pypi_name: idna
  libndp:
    fedora_package: libndp
    recipe: archive
    url_template: "https://github.com/jpirko/libndp/archive/v$version.tar.gz"
  python3-nonexistent:
    fedora_package: python3-nonexistent
    recipe: pypi
    pypi_name: nonexistent
"""
    )
    return path


def _patch_common(monkeypatch):
    monkeypatch.setattr(cli, "get_current_stable_branch", lambda session=None: "f44")
    monkeypatch.setattr(cli, "MdapiClient", FakeMdapi)
    monkeypatch.setattr(
        cli.pypi_recipe,
        "resolve",
        lambda pypi_name, version, prefer="wheel", session=None: PypiSource(
            url=f"https://x/{pypi_name}-{version}-py3-none-any.whl", sha256="deadbeef"
        ),
    )
    monkeypatch.setattr(
        cli.archive_recipe,
        "resolve",
        lambda url_template, version, session=None: ArchiveSource(
            url=f"https://x/libndp-{version}.tar.gz", sha256="cafef00d"
        ),
    )


def test_run_reports_updated_and_skipped_modules(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)

    rows = cli.run(mapping_file, manifest_root, dry_run=True)

    statuses = {row.module_name: row.status for row in rows}
    assert statuses["python3-idna"] == "updated"
    assert statuses["libndp"] == "updated"
    assert statuses["python3-nonexistent"] == "skipped"


def test_dry_run_does_not_write_files(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)
    original_text = manifest_root.read_text()

    cli.run(mapping_file, manifest_root, dry_run=True, only=["python3-idna"])

    assert manifest_root.read_text() == original_text


def test_non_dry_run_writes_updated_files(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)

    cli.run(mapping_file, manifest_root, dry_run=False, only=["python3-idna"])

    assert "idna-3.99-py3-none-any.whl" in manifest_root.read_text()


def test_format_summary_produces_a_github_markdown_table(monkeypatch, manifest_root, mapping_file):
    _patch_common(monkeypatch)
    rows = cli.run(mapping_file, manifest_root, dry_run=True)

    summary = cli.format_summary(rows)

    assert "| Module" in summary
    assert "python3-idna" in summary
    assert "python3-nonexistent" in summary


def test_main_command_wires_flags_into_run(monkeypatch, manifest_root, mapping_file):
    captured = {}

    def fake_run(mapping, manifest, *, dry_run=False, only=None):
        captured["dry_run"] = dry_run
        captured["only"] = only
        return [cli.Row("python3-idna", "updated", "-> 3.99 (1 block(s))")]

    monkeypatch.setattr(cli, "run", fake_run)

    result = CliRunner().invoke(
        cli.main,
        [
            "--mapping", str(mapping_file),
            "--manifest", str(manifest_root),
            "--dry-run",
            "--only", "python3-idna",
        ],
    )

    assert result.exit_code == 0
    assert "python3-idna" in result.output
    assert captured["dry_run"] is True
    assert captured["only"] == ["python3-idna"]


def test_main_command_exits_nonzero_on_bodhi_failure(monkeypatch, manifest_root, mapping_file):
    def raise_bodhi_error(mapping, manifest, *, dry_run=False, only=None):
        raise cli.BodhiLookupError("Bodhi is down")

    monkeypatch.setattr(cli, "run", raise_bodhi_error)

    result = CliRunner().invoke(cli.main, ["--mapping", str(mapping_file), "--manifest", str(manifest_root)])

    assert result.exit_code == 1
    assert "Bodhi is down" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_cli.py -v
```

Expected: `ModuleNotFoundError: No module named 'fedora_flatpak_updater.cli'`.

- [ ] **Step 3: Implement `cli.py`**

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cli.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
import requests
from tabulate import tabulate

from .fedora_release import BodhiLookupError, get_current_stable_branch
from .manifest_patcher import ManifestForest, apply_archive, apply_git, apply_pypi
from .mapping_loader import load_mapping
from .mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError
from .models import ModuleSpec, RecipeKind
from .recipes import archive as archive_recipe
from .recipes import git as git_recipe
from .recipes import pypi as pypi_recipe
from .recipes.archive import ArchiveResolutionError
from .recipes.git import GitTagNotFoundError
from .recipes.pypi import PypiVersionNotFoundError


@dataclass
class Row:
    module_name: str
    status: str  # "updated" | "unchanged" | "skipped"
    detail: str


def _infer_prefer(url: str, fallback: str) -> str:
    if url.endswith(".whl"):
        return "wheel"
    if url.endswith((".tar.gz", ".tar.bz2", ".zip")):
        return "sdist"
    return fallback


def _resolve_pypi_block(
    block: dict,
    spec: ModuleSpec,
    fedora_version: str,
    session: requests.Session,
    multi_wheel_cache: dict,
):
    if spec.recipe == RecipeKind.PYPI_MULTI_WHEEL and block.get("only-arches"):
        arch = block["only-arches"][0]
        cache_key = (spec.pypi_name, fedora_version)
        if cache_key not in multi_wheel_cache:
            multi_wheel_cache[cache_key] = pypi_recipe.resolve_multi_wheel(
                spec.pypi_name, fedora_version, spec.wheel_arches, session=session
            )
        return multi_wheel_cache[cache_key].get(arch)

    prefer = _infer_prefer(block.get("url", ""), spec.prefer)
    return pypi_recipe.resolve(spec.pypi_name, fedora_version, prefer=prefer, session=session)


def run(
    mapping_path: Path,
    manifest_root: Path,
    *,
    dry_run: bool = False,
    only: list[str] | None = None,
) -> list[Row]:
    session = requests.Session()
    branch = get_current_stable_branch(session=session)
    specs = load_mapping(mapping_path)
    if only:
        specs = [spec for spec in specs if spec.name in only]

    forest = ManifestForest(manifest_root)
    mdapi = MdapiClient(branch, session=session)
    multi_wheel_cache: dict = {}
    rows: list[Row] = []

    for spec in specs:
        try:
            fedora_version = mdapi.get_version(spec.fedora_package)
        except (PackageNotFoundError, MdapiTransientError) as exc:
            rows.append(Row(spec.name, "skipped", str(exc)))
            continue

        try:
            if spec.recipe in (RecipeKind.PYPI, RecipeKind.PYPI_MULTI_WHEEL):
                report = apply_pypi(
                    forest,
                    spec,
                    lambda block: _resolve_pypi_block(block, spec, fedora_version, session, multi_wheel_cache),
                )
            elif spec.recipe == RecipeKind.ARCHIVE:
                source = archive_recipe.resolve(spec.url_template, fedora_version, session=session)
                report = apply_archive(forest, spec, source)
            elif spec.recipe == RecipeKind.GIT:
                source = git_recipe.resolve(
                    repo_url=spec.repo_url,
                    version=fedora_version,
                    tag_template=spec.tag_template,
                    tag_pattern=spec.tag_pattern,
                )
                report = apply_git(forest, spec, source)
            else:  # pragma: no cover - RecipeKind is exhaustive
                rows.append(Row(spec.name, "skipped", f"unknown recipe {spec.recipe}"))
                continue
        except (PypiVersionNotFoundError, ArchiveResolutionError, GitTagNotFoundError) as exc:
            rows.append(Row(spec.name, "skipped", str(exc)))
            continue

        if report.blocks_touched == 0:
            rows.append(Row(spec.name, "unchanged", f"no matching source blocks found for {fedora_version}"))
        else:
            detail = f"-> {fedora_version} ({report.blocks_touched} block(s))"
            if spec.manual_followup:
                detail += f" [manual follow-up: {spec.manual_followup}]"
            rows.append(Row(spec.name, "updated", detail))

    if not dry_run and any(row.status == "updated" for row in rows):
        forest.save()

    return rows


def format_summary(rows: list[Row]) -> str:
    table = [[row.module_name, row.status, row.detail] for row in rows]
    return tabulate(table, headers=["Module", "Status", "Detail"], tablefmt="github")


@click.command()
@click.option(
    "--mapping",
    type=click.Path(path_type=Path),
    default=Path(".fedora-tracked-modules.yaml"),
    show_default=True,
    help="Path to the tracked-modules mapping file.",
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("com.protonvpn.www.yml"),
    show_default=True,
    help="Path to the root Flatpak manifest.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Resolve and report without writing files.")
@click.option("--only", multiple=True, help="Limit to specific tracked module name(s). Repeatable.")
def main(mapping: Path, manifest: Path, dry_run: bool, only: tuple[str, ...]) -> None:
    """Pin Flatpak manifest dependencies to Fedora-stable versions."""
    try:
        rows = run(mapping, manifest, dry_run=dry_run, only=list(only) or None)
    except BodhiLookupError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1)

    click.echo(format_summary(rows))
    if not any(row.status == "updated" for row in rows):
        click.echo("\nNothing to update.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater/test_cli.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the full test suite**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
```

Expected: all tests across every task pass (roughly 35-40 total).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add CLI orchestration (click command, tabulate summary)"
```

---

### Task 11: Build the initial `.fedora-tracked-modules.yaml`

**Files:**
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/migrate.py`
- Create: `.fedora-tracked-modules.yaml` (repo root)

**Interfaces:**
- Consumes: `fedora_release.get_current_stable_branch`, `mdapi_client.MdapiClient`, `mdapi_client.PackageNotFoundError`, `packaging.utils.canonicalize_name`, `click`
- Produces: `.fedora-tracked-modules.yaml`, consumed by `mapping_loader.load_mapping` in every subsequent CLI run (Task 12, Task 13).

- [ ] **Step 1: Implement `migrate.py`**

This is a one-off helper, not part of the scheduled job — it prints a draft mapping to stdout for a human to review.

```python
# scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/migrate.py
"""One-off helper for building the initial .fedora-tracked-modules.yaml.

Walks the manifest forest, collects every distinct third-party PyPI
`x-checker-data.name` value plus the known native archive/git modules,
guesses a Fedora package name for each, and verifies the guess against
MDAPI (including a HEAD check for archive url_templates, since the design
doc's `polkit` case shows a stale template resolving to a 404). Prints a
YAML draft to stdout; a human reviews it, hand-fixes anything flagged
`_needs_manual_fix`, and saves the result to .fedora-tracked-modules.yaml.

Not part of the ongoing scheduled job — run manually only when rebuilding
the mapping from scratch (e.g. after adding a new dependency).
"""
from __future__ import annotations

import sys
from pathlib import Path
from string import Template
from typing import Any

import click
import requests
from packaging.utils import canonicalize_name
from ruamel.yaml import YAML

from .fedora_release import get_current_stable_branch
from .mdapi_client import MdapiClient, PackageNotFoundError

PROTON_PREFIX = "proton"

NATIVE_MODULE_HINTS: dict[str, dict] = {
    "libndp": {
        "recipe": "archive",
        "url_template": "https://github.com/jpirko/libndp/archive/v$version.tar.gz",
    },
    "polkit": {
        "recipe": "archive",
        "url_template": "https://github.com/polkit-org/polkit/archive/refs/tags/$version.tar.gz",
    },
    "libnma": {
        "recipe": "archive",
        "url_template": "https://gitlab.gnome.org/GNOME/libnma/-/archive/$version/libnma-$version.tar.gz",
    },
    "iproute2": {
        "recipe": "archive",
        "url_template": "https://www.kernel.org/pub/linux/utils/net/iproute2/iproute2-$version.tar.xz",
    },
    "python-dbus": {
        "recipe": "archive",
        "fedora_package": "dbus-python",
        "url_template": "https://dbus.freedesktop.org/releases/dbus-python/dbus-python-$version.tar.gz",
    },
    "NetworkManager": {
        "recipe": "git",
        "repo_url": "https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
        "tag_template": "$version",
    },
    "NetworkManager-openvpn": {
        "recipe": "git",
        "repo_url": "https://github.com/NetworkManager/NetworkManager-openvpn.git",
        "tag_template": "$version",
    },
    "systemd": {
        "recipe": "git",
        "repo_url": "https://github.com/systemd/systemd.git",
        "tag_pattern": r"^v([\d.]+)$",
    },
}

MANUAL_FOLLOWUP = {
    "python3-bcrypt": (
        "bcrypt vendors Rust crate sources in bcrypt-cargo-sources.json. "
        "Re-run flatpak-cargo-generator against the new version's Cargo.lock "
        "before merging."
    ),
}

# Known guess-convention exceptions (design doc item 6).
FEDORA_NAME_OVERRIDES = {
    "pycairo": "python3-cairo",
    "pygobject": "python3-gobject",
}


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def _load_forest(root_path: Path) -> list[Any]:
    yaml = YAML(typ="safe")
    documents = []
    seen: set[Path] = set()

    def load(path: Path) -> None:
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.load(fh)
        documents.append(data)
        for d in _iter_dicts(data):
            modules = d.get("modules")
            if isinstance(modules, list):
                for item in modules:
                    if isinstance(item, str):
                        load(path.parent / item)

    load(root_path)
    return documents


def discover_pypi_names(root_path: Path) -> set[str]:
    names = set()
    for document in _load_forest(root_path):
        for d in _iter_dicts(document):
            checker = d.get("x-checker-data")
            if isinstance(checker, dict) and checker.get("type") in ("pypi", "json"):
                name = checker.get("name")
                if name and not name.lower().startswith(PROTON_PREFIX):
                    names.add(name)
    return names


def guess_fedora_package(pypi_name: str) -> str:
    if pypi_name in FEDORA_NAME_OVERRIDES:
        return FEDORA_NAME_OVERRIDES[pypi_name]
    return f"python3-{canonicalize_name(pypi_name)}"


def build_draft(root_path: Path, branch: str, session: requests.Session) -> dict:
    mdapi = MdapiClient(branch, session=session)
    modules: dict[str, dict] = {}

    for pypi_name in sorted(discover_pypi_names(root_path)):
        guess = guess_fedora_package(pypi_name)
        entry = {"recipe": "pypi", "pypi_name": pypi_name, "fedora_package": guess}
        try:
            mdapi.get_version(guess)
        except PackageNotFoundError:
            entry["_needs_manual_fix"] = f"{guess} not found in Fedora {branch}"
        modules[guess] = entry

    for name, hint in NATIVE_MODULE_HINTS.items():
        fedora_package = hint.get("fedora_package", name)
        entry = {"recipe": hint["recipe"], "fedora_package": fedora_package}
        entry.update({k: v for k, v in hint.items() if k not in ("recipe", "fedora_package")})
        try:
            version = mdapi.get_version(fedora_package)
        except PackageNotFoundError:
            entry["_needs_manual_fix"] = f"{fedora_package} not found in Fedora {branch}"
            modules[name] = entry
            continue

        if hint["recipe"] == "archive":
            rendered = Template(hint["url_template"]).substitute(version=version)
            response = session.head(rendered, allow_redirects=True, timeout=30)
            if response.status_code >= 400:
                entry["_needs_manual_fix"] = (
                    f"url_template renders to {rendered} which returned "
                    f"{response.status_code} for version {version}"
                )
        modules[name] = entry

    for module_name, note in MANUAL_FOLLOWUP.items():
        modules.setdefault(module_name, {})["manual_followup"] = note

    return {"modules": modules}


@click.command()
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("com.protonvpn.www.yml"),
    show_default=True,
    help="Path to the root Flatpak manifest to walk.",
)
def main(manifest: Path) -> None:
    """Print a draft .fedora-tracked-modules.yaml to stdout for review."""
    session = requests.Session()
    branch = get_current_stable_branch(session=session)
    draft = build_draft(manifest, branch, session)

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.dump(draft, sys.stdout)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the migration script from the repo root**

```bash
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.migrate --manifest com.protonvpn.www.yml > /tmp/fedora-tracked-modules.draft.yaml
cat /tmp/fedora-tracked-modules.draft.yaml
```

Expected: a YAML document with a `modules:` map covering every discovered PyPI name (as `python3-<name>` keys) plus the 8 `NATIVE_MODULE_HINTS` entries. Entries MDAPI couldn't verify carry `_needs_manual_fix: "..."`.

- [ ] **Step 3: Apply the known hand-fixes**

Open `/tmp/fedora-tracked-modules.draft.yaml` and apply these changes (all confirmed live against real services per the design doc):

1. Change the `python3-cryptography` entry's `recipe` from `pypi` to `pypi-multi-wheel` and add `wheel_arches: [aarch64, x86_64]`.
2. Confirm `pycairo` → `python3-cairo` and `pygobject` → `python3-gobject` have no `_needs_manual_fix` (already handled by `FEDORA_NAME_OVERRIDES`).
3. For every remaining entry still carrying `_needs_manual_fix`, resolve it by hand: query `https://mdapi.fedoraproject.org/<branch>/pkg/<candidate-name>` for plausible alternate spellings, or remove the module from the mapping entirely if it turns out to have no Fedora equivalent (it then simply stays untracked, keeping its current upstream-pinned behavior).
4. Delete every remaining `_needs_manual_fix` key once resolved (they are debugging aids only, not part of the final schema `mapping_loader.py` expects).
5. Double check no entry's `fedora_package` or `pypi_name` starts with `proton` (case-insensitive) — if one slipped through, delete that module entry.

- [ ] **Step 4: Save the reviewed file as `.fedora-tracked-modules.yaml`**

```bash
cp /tmp/fedora-tracked-modules.draft.yaml .fedora-tracked-modules.yaml
```

- [ ] **Step 5: Validate the file loads cleanly**

```bash
uv run --project scripts/fedora_flatpak_updater python -c "
from pathlib import Path
from fedora_flatpak_updater.mapping_loader import load_mapping
specs = load_mapping(Path('.fedora-tracked-modules.yaml'))
print(f'{len(specs)} modules loaded')
assert not any(s.name.lower().startswith('proton') or (s.pypi_name or '').lower().startswith('proton') for s in specs)
"
```

Expected: prints a module count (roughly 50-60) with no `AssertionError`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add migration helper and initial .fedora-tracked-modules.yaml"
```

---

### Task 12: Run the updater for real and pin the manifests

**Files:**
- Modify: `com.protonvpn.www.yml`
- Modify: `pip-resources.proton-vpn-cli.yaml`
- Modify: `pip-resources.proton-vpn-gtk-app.yaml`
- Modify: `pip-resources.python-proton-core.yaml`
- Modify: `pip-resources.python-proton-keyring-linux.yaml`
- Modify: `pip-resources.python-proton-vpn-api-core.yaml`

**Interfaces:**
- Consumes: `cli.main` (Task 10), `.fedora-tracked-modules.yaml` (Task 11)

- [ ] **Step 1: Dry-run first and read the summary**

```bash
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --dry-run
```

Expected: a GitHub-flavored markdown table with one row per tracked module, status `updated`/`unchanged`/`skipped`. Read every `skipped` reason before proceeding.

- [ ] **Step 2: Run for real**

```bash
uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli
```

Expected: same table, and this time `com.protonvpn.www.yml` plus the `pip-resources.*.yaml` files are modified on disk.

- [ ] **Step 3: Review the diff**

```bash
git --no-pager diff --stat
git --no-pager diff com.protonvpn.www.yml
```

Confirm: (a) only `url`/`sha256`/`tag`/`commit`/`x-checker-data` fields changed on tracked modules, (b) Proton-owned modules are untouched, (c) the `NetworkManager`/`NetworkManager-openvpn` `versions: <...>` ceilings and ALL other `x-checker-data` blocks on tracked sources are gone.

- [ ] **Step 4: Sanity-check the manifest is still valid YAML**

```bash
uv run --project scripts/fedora_flatpak_updater python -c "
from ruamel.yaml import YAML
yaml = YAML(typ='safe')
for path in ['com.protonvpn.www.yml', 'pip-resources.proton-vpn-cli.yaml', 'pip-resources.proton-vpn-gtk-app.yaml', 'pip-resources.python-proton-core.yaml', 'pip-resources.python-proton-keyring-linux.yaml', 'pip-resources.python-proton-vpn-api-core.yaml']:
    with open(path) as fh:
        yaml.load(fh)
    print(path, 'OK')
"
```

Expected: `OK` for all six files.

- [ ] **Step 5: If `python3-bcrypt` was updated, regenerate its Cargo sources**

Check the CLI summary table for the `[manual follow-up: ...]` annotation on `python3-bcrypt`. If present, use `flatpak-builder-tools`' `cargo/flatpak-cargo-generator.py` against the new version's `Cargo.lock` to regenerate `bcrypt-cargo-sources.json` before merging. This is a manual follow-up outside the tool's scope (see design doc's Known Limitations) — flag it in the PR description rather than trying to automate it here.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: pin Flatpak dependencies to Fedora-stable versions"
```

---

### Task 13: GitHub Actions workflows (scheduled update + conditional tests) + final validation

**Files:**
- Create: `.github/workflows/update-fedora-flatpak-deps.yml`
- Create: `.github/workflows/test-fedora-flatpak-updater.yml`

**Interfaces:**
- Consumes: `fedora_flatpak_updater.cli` (Task 10), `.fedora-tracked-modules.yaml` (Task 11), the test suite from Tasks 3-10

- [ ] **Step 1: Create the scheduled update workflow file**

```yaml
# .github/workflows/update-fedora-flatpak-deps.yml
name: Update Fedora-stable Flatpak dependencies

on:
  schedule:
    - cron: "0 6 * * 1"  # every Monday at 06:00 UTC
  workflow_dispatch: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"

      - name: Sync fedora_flatpak_updater environment
        run: uv sync --project scripts/fedora_flatpak_updater

      - name: Run updater
        run: |
          uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli \
            --mapping .fedora-tracked-modules.yaml \
            --manifest com.protonvpn.www.yml | tee summary.md

      - name: Check for changes
        id: diff
        run: |
          if git diff --quiet; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Open pull request
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v7
        with:
          commit-message: "chore: update Flatpak dependencies to Fedora-stable versions"
          title: "chore: update Flatpak dependencies to Fedora-stable versions"
          body-path: summary.md
          branch: fedora-stable-flatpak-deps-update
          delete-branch: true
```

- [ ] **Step 2: Create the conditional test workflow file**

This workflow runs the unit test suite on every push/PR that touches the updater's own code or tests — separate from the scheduled workflow above, which actually calls out to Fedora/PyPI/git and opens a PR. It never makes real network calls; it only exercises the mocked test suite from Tasks 3-10.

```yaml
# .github/workflows/test-fedora-flatpak-updater.yml
name: Test fedora_flatpak_updater

on:
  push:
    branches: [main]
    paths:
      - "scripts/fedora_flatpak_updater/**"
      - "tests/fedora_flatpak_updater/**"
      - ".github/workflows/test-fedora-flatpak-updater.yml"
  pull_request:
    paths:
      - "scripts/fedora_flatpak_updater/**"
      - "tests/fedora_flatpak_updater/**"
      - ".github/workflows/test-fedora-flatpak-updater.yml"

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"

      - name: Sync fedora_flatpak_updater environment
        run: uv sync --project scripts/fedora_flatpak_updater

      - name: Run test suite
        run: uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
```

The `paths:` filters mean this job is skipped entirely on commits/PRs that don't touch `scripts/fedora_flatpak_updater/`, `tests/fedora_flatpak_updater/`, or the workflow file itself (e.g. changes to `com.protonvpn.www.yml` alone, or to unrelated parts of the repo, won't trigger it). If your repository requires this check to be "required" in branch protection, add it as a required status check named `test` under the `Test fedora_flatpak_updater` workflow — GitHub still reports skipped-due-to-path-filter runs as passing for that purpose.

- [ ] **Step 3: Commit both workflow files**

```bash
git add -A
git commit -m "ci: add scheduled Fedora-stable Flatpak dependency update workflow and conditional test run (uv)"
```

- [ ] **Step 4: Run the full test suite one final time locally**

```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
```

Expected: every test from Tasks 3-10 passes (no network calls made — all HTTP interactions are mocked via `responses`, all `git` interactions via the injectable `runner` callable).

- [ ] **Step 5: Confirm the old scratch work is fully gone and nothing references it**

```bash
git --no-pager log --oneline -1
find . -iname "*fedora_pip_updater*" -o -iname "*.fedora-pip-mapping*" 2>/dev/null
```

Expected: no matches (aside from `.git` internals, if any).

- [ ] **Step 6: Final review**

```bash
git --no-pager log --oneline -13
git --no-pager diff --stat main...HEAD
```

Confirm the commit history matches the 13 tasks above and the diff touches exactly: the new `scripts/fedora_flatpak_updater/` package (including committed `uv.lock`), the new `tests/fedora_flatpak_updater/` suite, `.fedora-tracked-modules.yaml`, `.github/workflows/update-fedora-flatpak-deps.yml`, `.github/workflows/test-fedora-flatpak-updater.yml`, `.gitignore`, the six patched manifest files, and the deletions from Task 1.
