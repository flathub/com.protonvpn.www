# CI Static Analysis, Linting, and Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate static analysis, linting, type-checking, pre-commit hooks, and a modular CI workflow for the Fedora Flatpak Updater script.

**Architecture:** Configure Ruff and Mypy in `pyproject.toml`, implement type safety annotations across Python files, add pre-commit hooks, and partition GHA workflow into parallel jobs.

**Tech Stack:** Python 3.13, Ruff, Mypy, pre-commit, pytest, GitHub Actions.

## Global Constraints

- Target Python: `requires-python = ">=3.13"`
- Dev dependencies: `ruff>=0.15.20`, `mypy>=2.2.0`, `pytest-github-actions-annotate-failures>=0.4.2`
- Ruff rules: `["E", "F", "I", "UP", "RUF"]` with target version `py313`
- Mypy rules: target version `3.13`, `strict = true`, ignore missing imports for `ruamel.yaml`, `tenacity`, `tabulate`
- Pre-commit: system hooks running via `uv`
- CI Workflow jobs: parallel jobs `lint`, `typecheck`, and `test`

---

### Task 1: Project Configuration & Setup

**Files:**
- Modify: `scripts/fedora_flatpak_updater/pyproject.toml`
- Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/py.typed`

**Interfaces:**
- Consumes: None
- Produces: Ruff and Mypy tools in Python 3.13 environment

- [ ] **Step 1: Create `py.typed` marker file**
  Create an empty file (with a marker comment) to indicate that the package supports type annotations.
  
  Create file `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/py.typed` with:
  ```python
  # PEP 561 marker
  ```

- [ ] **Step 2: Update `pyproject.toml`**
  Modify `scripts/fedora_flatpak_updater/pyproject.toml` to target Python 3.13, add the new dev group dependencies, and configure Ruff and Mypy options.

  Replace the contents of `scripts/fedora_flatpak_updater/pyproject.toml` with:
  ```toml
  [project]
  name = "fedora-flatpak-updater"
  version = "0.1.0"
  description = "Pins third-party Flatpak manifest dependencies to Fedora-stable versions"
  readme = "README.md"
  requires-python = ">=3.13"
  dependencies = [
      "requests>=2.34.2",
      "ruamel.yaml>=0.19.1",
      "tenacity>=9.1.4",
      "click>=8.4.2",
      "tabulate>=0.10.0",
      "packaging>=26.2",
  ]

  [project.scripts]
  fedora-flatpak-updater = "fedora_flatpak_updater.cli:main"
  fedora-flatpak-updater-migrate = "fedora_flatpak_updater.migrate:main"

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [dependency-groups]
  dev = [
      "pytest>=9.1.1",
      "responses>=0.26.2",
      "ruff>=0.15.20",
      "mypy>=2.2.0",
      "pytest-github-actions-annotate-failures>=0.4.2",
  ]

  [tool.ruff]
  target-version = "py313"
  line-length = 88
  lint.select = ["E", "F", "I", "UP", "RUF"]

  [tool.mypy]
  python_version = "3.13"
  strict = true

  [[tool.mypy.overrides]]
  module = [
      "ruamel.*",
      "tenacity",
      "tenacity.*",
      "tabulate",
      "tabulate.*",
  ]
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "tests.*"
  ignore_errors = true
  ```

- [ ] **Step 3: Run `uv sync` to install dependencies**
  Run: `uv sync --project scripts/fedora_flatpak_updater`
  Expected: Command finishes successfully and downloads the new tools into the virtual environment.

- [ ] **Step 4: Commit**
  ```bash
  git add scripts/fedora_flatpak_updater/pyproject.toml scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/py.typed
  git commit -m "chore: configure Python 3.13, Ruff, and Mypy tools in pyproject.toml"
  ```

---

### Task 2: Configure Local Pre-commit Hooks

**Files:**
- Create: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: None
- Produces: Local git hooks for automatic linting and checking

- [ ] **Step 1: Create `.pre-commit-config.yaml`**
  Create the `.pre-commit-config.yaml` file in the root of the repository to define the hooks running via `uv`.

  Create `/.pre-commit-config.yaml` with:
  ```yaml
  repos:
    - repo: local
      hooks:
        - id: ruff-format
          name: ruff format
          entry: uv run --project scripts/fedora_flatpak_updater ruff format --check
          language: system
          types: [python]
        - id: ruff-check
          name: ruff check
          entry: uv run --project scripts/fedora_flatpak_updater ruff check
          language: system
          types: [python]
        - id: mypy
          name: mypy
          entry: env MYPYPATH=scripts/fedora_flatpak_updater/src uv run --project scripts/fedora_flatpak_updater mypy --config-file scripts/fedora_flatpak_updater/pyproject.toml --explicit-package-bases scripts/fedora_flatpak_updater/src/fedora_flatpak_updater tests/fedora_flatpak_updater
          language: system
          types: [python]
          require_serial: true
  ```

- [ ] **Step 2: Install pre-commit hooks**
  Run: `pre-commit install`
  Expected: "pre-commit installed at .git/hooks/pre-commit"

- [ ] **Step 3: Test pre-commit config manually**
  Run: `pre-commit run --all-files`
  Expected: Pre-commit starts running the hooks (it is expected that formatting/linting/mypy checks might fail at this stage due to outstanding style and type violations).

- [ ] **Step 4: Commit**
  ```bash
  git add .pre-commit-config.yaml
  git commit -m "chore: add .pre-commit-config.yaml configured with uv system hooks"
  ```

---

### Task 3: Refactor GitHub Actions Workflow

**Files:**
- Modify: `.github/workflows/test-fedora-flatpak-updater.yml`

**Interfaces:**
- Consumes: None
- Produces: Parallel GHA workflow checks for format/lint, typecheck, and unit test suite

- [ ] **Step 1: Modify `.github/workflows/test-fedora-flatpak-updater.yml`**
  Split the single job into three parallel jobs: `lint`, `typecheck`, and `test`.

  Replace the contents of `.github/workflows/test-fedora-flatpak-updater.yml` with:
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
    lint:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v7
        - name: Run Ruff check and format
          uses: astral-sh/ruff-action@v3
          with:
            src: "./scripts/fedora_flatpak_updater/src ./tests/fedora_flatpak_updater"
            config: "./scripts/fedora_flatpak_updater/pyproject.toml"

    typecheck:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v7
        - name: Install uv
          uses: astral-sh/setup-uv@v8.3.2
          with:
            python-version: "3.13"
        - name: Sync environment
          run: uv sync --project scripts/fedora_flatpak_updater
        - name: Run mypy
          run: MYPYPATH=scripts/fedora_flatpak_updater/src uv run --project scripts/fedora_flatpak_updater mypy --config-file scripts/fedora_flatpak_updater/pyproject.toml --explicit-package-bases scripts/fedora_flatpak_updater/src/fedora_flatpak_updater tests/fedora_flatpak_updater

    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v7
        - name: Install uv
          uses: astral-sh/setup-uv@v8.3.2
          with:
            python-version: "3.13"
        - name: Sync environment
          run: uv sync --project scripts/fedora_flatpak_updater
        - name: Run test suite with GHA annotations
          run: uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
  ```

- [ ] **Step 2: Commit**
  ```bash
  git add .github/workflows/test-fedora-flatpak-updater.yml
  git commit -m "ci: modularize CI pipeline into parallel lint, typecheck, and test jobs"
  ```

---

### Task 4: Ruff Formatting & StrEnum Refactoring

**Files:**
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/models.py`
- Modify: All files in `scripts/fedora_flatpak_updater` and `tests/fedora_flatpak_updater` via automatic formatter

**Interfaces:**
- Consumes: None
- Produces: PEP8 compliant codebase and `RecipeKind` using `enum.StrEnum`

- [ ] **Step 1: Refactor `RecipeKind` in `models.py`**
  Modify `RecipeKind` to inherit from `StrEnum` instead of both `str` and `Enum` to satisfy Ruff UP042 rules.

  In `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/models.py`, replace lines 1-13 with:
  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from enum import StrEnum


  class RecipeKind(StrEnum):
      PYPI = "pypi"
      PYPI_MULTI_WHEEL = "pypi-multi-wheel"
      ARCHIVE = "archive"
      GIT = "git"
  ```

- [ ] **Step 2: Run Ruff Formatter**
  Format all files in the python target paths.
  Run: `uv run --project scripts/fedora_flatpak_updater ruff format`
  Expected: Re-formats all python source and test files to the standard Ruff format.

- [ ] **Step 3: Run Ruff Check Autofix**
  Autofix simple lint errors.
  Run: `uv run --project scripts/fedora_flatpak_updater ruff check --fix --unsafe-fixes`
  Expected: Cleans up import order and code upgrades. Ruff check should now return 0 errors.

- [ ] **Step 4: Verify Formatting and Linting**
  Run: `uv run --project scripts/fedora_flatpak_updater ruff check` and `uv run --project scripts/fedora_flatpak_updater ruff format --check`
  Expected: Both commands exit with code 0.

- [ ] **Step 5: Commit**
  ```bash
  git add scripts/fedora_flatpak_updater/
  git commit -m "style: apply ruff format and check fixes, refactor RecipeKind to StrEnum"
  ```

---

### Task 5: Fix Mypy Type Safety Errors in Source Code

**Files:**
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/git.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/manifest_patcher.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/pypi.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/archive.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cli.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/fedora_release.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mdapi_client.py`
- Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/migrate.py`
- Modify: `tests/fedora_flatpak_updater/test_mapping_loader.py`

**Interfaces:**
- Consumes: None
- Produces: Strict-mode typecheck passing codebase

- [ ] **Step 1: Fix `recipes/git.py`**
  Modify lines 70-96 in `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/git.py` to assert non-None types and verify commit is resolved:
  ```python
      if tag_template:
          target_tag = Template(tag_template).substitute(version=version)
      else:
          assert tag_pattern is not None
          pattern = re.compile(tag_pattern)
          target_tag = None
          for tag_name in by_tag:
              match = pattern.match(tag_name)
              if match:
                  try:
                      captured = match.group(1)
                  except IndexError:
                      captured = match.group(0)
                  if captured == version:
                      target_tag = tag_name
                      break
          if target_tag is None:
              raise GitTagNotFoundError(
                  f"no tag matching {tag_pattern!r} for version {version} on {repo_url}"
              )

      assert target_tag is not None
      hashes = by_tag.get(target_tag)
      if not hashes:
          raise GitTagNotFoundError(f"tried tag {target_tag!r} on {repo_url}, not found")

      commit = hashes.get("peeled") or hashes.get("plain")
      if not commit:
          raise GitTagNotFoundError(f"tag {target_tag!r} has no commit hash")
      return GitSource(tag=target_tag, commit=commit)
  ```

- [ ] **Step 2: Fix `manifest_patcher.py`**
  Add explicit type annotations for `seen`, `dict[Any, Any]`, and imported symbols.
  
  Replace the contents of `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/manifest_patcher.py` with:
  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from pathlib import Path
  from typing import Any, Callable, Generator

  from packaging.utils import canonicalize_name
  from ruamel.yaml import YAML

  from .models import ModuleSpec
  from .recipes.archive import ArchiveSource
  from .recipes.git import GitSource


  def _matches_pypi_name(url: str, pypi_name: str) -> bool:
      filename = url.rsplit("/", 1)[-1].lower()
      canonical = str(canonicalize_name(pypi_name))  # PEP 503, e.g. "jaraco-classes"
      prefixes = {
          pypi_name.lower() + "-",
          canonical + "-",
          canonical.replace("-", "_") + "-",  # wheel filenames use underscores
      }
      for prefix in prefixes:
          if filename.startswith(prefix):
              remainder = filename[len(prefix) :]
              if remainder and remainder[0].isdigit():
                  return True
      return False


  def _iter_dicts(node: Any, seen: set[int] | None = None) -> Generator[dict[Any, Any], None, None]:
      if seen is None:
          seen = set()
      if isinstance(node, dict):
          if id(node) in seen:
              return
          seen.add(id(node))
          yield node
          for value in node.values():
              yield from _iter_dicts(value, seen)
      elif isinstance(node, list):
          if id(node) in seen:
              return
          seen.add(id(node))
          for item in node:
              yield from _iter_dicts(item, seen)


  def _remove_checker_data(block: dict[Any, Any]) -> None:
      if "x-checker-data" not in block:
          return
      ca = getattr(block, "ca", None)
      x_ca_items = ca.items.pop("x-checker-data", None) if ca and hasattr(ca, "items") else None
      x_data = block.pop("x-checker-data")
      if not block:
          return

      trailing_tokens = []
      if x_ca_items:
          for idx in (2, 3):
              if len(x_ca_items) > idx and x_ca_items[idx] is not None:
                  trailing_tokens.append(x_ca_items[idx])
      x_ca = getattr(x_data, "ca", None)
      if isinstance(x_data, dict) and x_ca:
          if getattr(x_ca, "comment", None) is not None:
              trailing_tokens.append(x_ca.comment)
          if x_data:
              last_k = list(x_data.keys())[-1]
              x_ca_items_dict = getattr(x_ca, "items", None)
              if x_ca_items_dict and last_k in x_ca_items_dict:
                  last_items = x_ca_items_dict[last_k]
                  for idx in (2, 3):
                      if len(last_items) > idx and last_items[idx] is not None:
                          trailing_tokens.append(last_items[idx])

      flat_tokens = []

      def _flatten(obj: Any) -> None:
          if obj is None:
              return
          if isinstance(obj, (list, tuple)):
              for item in obj:
                  _flatten(item)
          elif hasattr(obj, "value"):
              flat_tokens.append(obj)

      for t in trailing_tokens:
          _flatten(t)

      if flat_tokens:
          first = flat_tokens[0]
          combined = "".join(t.value for t in flat_tokens)
          first.value = combined
          for t in flat_tokens[1:]:
              t.value = ""


  @dataclass(frozen=True)
  class PatchReport:
      module_name: str
      blocks_touched: int


  class ManifestForest:
      def __init__(self, root_path: Path):
          self._yaml = YAML()
          self._yaml.indent(mapping=2, sequence=4, offset=2)
          self._yaml.preserve_quotes = True

          self.documents: dict[Path, Any] = {}
          self._discover_refs(root_path, root_path.parent)

      def _discover_refs(self, path: Path, base_dir: Path) -> None:
          path = path.resolve()
          if path in self.documents:
              return

          with path.open("r", encoding="utf-8") as fh:
              data = self._yaml.load(fh)
          self.documents[path] = data

          for d in _iter_dicts(data):
              modules = d.get("modules")
              if isinstance(modules, list):
                  for item in modules:
                      if isinstance(item, str):
                          ref_path = base_dir / item
                          self._discover_refs(ref_path, ref_path.parent)

          if isinstance(data, dict):
              for key, value in data.items():
                  if key == "modules":
                      continue
                  self._discover_refs(value, base_dir)
          elif isinstance(data, list):
              for item in data:
                  self._discover_refs(item, base_dir)

      def iter_dicts(self) -> Generator[dict[Any, Any], None, None]:
          seen: set[int] = set()
          for data in self.documents.values():
              yield from _iter_dicts(data, seen)

      def save(self) -> list[Path]:
          written = []
          for path, data in self.documents.items():
              if "shared-modules" in path.parts:
                  continue
              with path.open("w", encoding="utf-8") as fh:
                  self._yaml.dump(data, fh)
              written.append(path)
          return written


  def find_module_blocks(forest: ManifestForest, module_name: str) -> list[dict[Any, Any]]:
      """archive/git recipes: match standalone flatpak modules by `name:`."""
      return [d for d in forest.iter_dicts() if d.get("name") == module_name and "sources" in d]


  def find_pypi_source_blocks(forest: ManifestForest, pypi_name: str) -> list[dict[Any, Any]]:
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


  def apply_pypi(forest: ManifestForest, spec: ModuleSpec, resolve_block: Callable[[dict[Any, Any]], Any]) -> PatchReport:
      """`resolve_block(current_block)` is called once per matched block so
      each occurrence can be resolved according to its own existing shape
      (wheel vs sdist, arch-specific vs generic)."""
      if spec.pypi_name is None:
          raise ValueError(f"pypi_name is required for spec {spec.name}")
      blocks = find_pypi_source_blocks(forest, spec.pypi_name)
      touched = 0
      for block in blocks:
          source = resolve_block(block)
          if source is None:
              continue
          block["url"] = source.url
          block["sha256"] = source.sha256
          _remove_checker_data(block)
          touched += 1
      return PatchReport(module_name=spec.name, blocks_touched=touched)


  def apply_archive(forest: ManifestForest, spec: ModuleSpec, source: ArchiveSource) -> PatchReport:
      touched = 0
      for module_block in find_module_blocks(forest, spec.name):
          for src in module_block.get("sources", []):
              if isinstance(src, dict) and src.get("type") == "archive":
                  src["url"] = source.url
                  src["sha256"] = source.sha256
                  _remove_checker_data(src)
                  touched += 1
      return PatchReport(module_name=spec.name, blocks_touched=touched)


  def apply_git(forest: ManifestForest, spec: ModuleSpec, source: GitSource) -> PatchReport:
      touched = 0
      for module_block in find_module_blocks(forest, spec.name):
          for src in module_block.get("sources", []):
              if isinstance(src, dict) and src.get("type") == "git":
                  src["tag"] = source.tag
                  src["commit"] = source.commit
                  _remove_checker_data(src)
                  touched += 1
      return PatchReport(module_name=spec.name, blocks_touched=touched)
  ```

- [ ] **Step 3: Fix `recipes/pypi.py`**
  Modify `fetch_release_files` to return a strongly-typed `list[dict[str, Any]]` and raise unreachable error to prevent implicit None return:
  
  In `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/pypi.py`, replace lines 22-42 with:
  ```python
  def fetch_release_files(pypi_name: str, version: str, session: requests.Session | None = None) -> list[dict[str, Any]]:
      own_session = session is None
      if session is None:
          session = requests.Session()
      try:
          url = f"{PYPI_BASE}/{pypi_name}/{version}/json"
          for attempt in range(3):
              try:
                  response = session.get(url, timeout=60)
                  if response.status_code == 404:
                      raise PypiVersionNotFoundError(f"{pypi_name}=={version} not found on PyPI")
                  response.raise_for_status()
                  res = response.json()["urls"]
                  assert isinstance(res, list)
                  return res
              except (requests.RequestException, PypiVersionNotFoundError) as exc:
                  if isinstance(exc, PypiVersionNotFoundError) or attempt == 2:
                      raise
                  time.sleep(2 * (attempt + 1))
          raise RuntimeError("Unreachable")
      finally:
          if own_session:
              session.close()
  ```

- [ ] **Step 4: Fix `recipes/archive.py`**
  Modify `resolve` to raise unreachable error to prevent implicit None return:

  In `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/recipes/archive.py`, replace lines 25-49 with:
  ```python
  def resolve(url_template: str, version: str, session: requests.Session | None = None) -> ArchiveSource:
      own_session = session is None
      if session is None:
          session = requests.Session()
      try:
          url = render_url(url_template, version)
          for attempt in range(3):
              try:
                  with session.get(url, timeout=60, stream=True) as response:
                      if response.status_code == 404:
                          raise ArchiveResolutionError(f"{url} returned 404")
                      response.raise_for_status()

                      digest = hashlib.sha256()
                      for chunk in response.iter_content(chunk_size=65536):
                          digest.update(chunk)
                      return ArchiveSource(url=url, sha256=digest.hexdigest())
              except (requests.RequestException, ArchiveResolutionError) as exc:
                  if isinstance(exc, ArchiveResolutionError) or attempt == 2:
                      raise
                  time.sleep(2 * (attempt + 1))
          raise RuntimeError("Unreachable")
      finally:
          if own_session:
              session.close()
  ```

- [ ] **Step 5: Fix `cli.py`**
  Add explicit type annotations for parameters and return types. Replace the `cli.py` file content:
  
  Replace the contents of `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cli.py` with:
  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from pathlib import Path
  from typing import Any

  import click
  import requests
  import subprocess
  from tabulate import tabulate

  from .fedora_release import BodhiLookupError, get_current_stable_branch
  from .manifest_patcher import ManifestForest, apply_archive, apply_git, apply_pypi
  from .mapping_loader import MappingError, load_mapping
  from .mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError
  from .models import ModuleSpec, RecipeKind
  from .recipes import archive as archive_recipe
  from .recipes import git as git_recipe
  from .recipes import pypi as pypi_recipe
  from .recipes.archive import ArchiveResolutionError
  from .recipes.git import GitTagNotFoundError
  from .recipes.pypi import PypiSource, PypiVersionNotFoundError


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
      block: dict[str, Any],
      spec: ModuleSpec,
      fedora_version: str,
      session: requests.Session,
      multi_wheel_cache: dict[tuple[str, str], dict[str, PypiSource]],
  ) -> PypiSource | None:
      if spec.pypi_name is None:
          raise ValueError(f"pypi_name is required for spec {spec.name}")
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
      with requests.Session() as session:
          branch = get_current_stable_branch(session=session)
          specs = load_mapping(mapping_path)
          if only:
              specs = [spec for spec in specs if spec.name in only]

          forest = ManifestForest(manifest_root)
          mdapi = MdapiClient(branch, session=session)
          multi_wheel_cache: dict[tuple[str, str], dict[str, PypiSource]] = {}
          rows: list[Row] = []

          for spec in specs:
              try:
                  fedora_version = mdapi.get_version(spec.fedora_package)
              except (PackageNotFoundError, MdapiTransientError) as exc:
                  rows.append(Row(spec.name, "skipped", str(exc)))
                  continue
              except requests.RequestException as exc:
                  rows.append(Row(spec.name, "skipped", f"network error querying mdapi: {exc}"))
                  continue

              try:
                  if spec.recipe in (RecipeKind.PYPI, RecipeKind.PYPI_MULTI_WHEEL):
                      report = apply_pypi(
                          forest,
                          spec,
                          lambda block: _resolve_pypi_block(block, spec, fedora_version, session, multi_wheel_cache),
                      )
                  elif spec.recipe == RecipeKind.ARCHIVE:
                      if spec.url_template is None:
                          raise ValueError(f"url_template is required for archive spec {spec.name}")
                      archive_source = archive_recipe.resolve(spec.url_template, fedora_version, session=session)
                      report = apply_archive(forest, spec, archive_source)
                  elif spec.recipe == RecipeKind.GIT:
                      if spec.repo_url is None:
                          raise ValueError(f"repo_url is required for git spec {spec.name}")
                      git_source = git_recipe.resolve(
                          repo_url=spec.repo_url,
                          version=fedora_version,
                          tag_template=spec.tag_template,
                          tag_pattern=spec.tag_pattern,
                      )
                      report = apply_git(forest, spec, git_source)
                  else:  # pragma: no cover - RecipeKind is exhaustive
                      rows.append(Row(spec.name, "skipped", f"unknown recipe {spec.recipe}"))
                      continue
              except (PypiVersionNotFoundError, ArchiveResolutionError, GitTagNotFoundError) as exc:
                  rows.append(Row(spec.name, "skipped", str(exc)))
                  continue
              except requests.RequestException as exc:
                  rows.append(Row(spec.name, "skipped", f"network error resolving source: {exc}"))
                  continue
              except subprocess.SubprocessError as exc:
                  rows.append(Row(spec.name, "skipped", f"subprocess error: {exc}"))
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
      res = tabulate(table, headers=["Module", "Status", "Detail"], tablefmt="github")
      return str(res)


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
      default=Path("org.protonvpn.protonvpn.yml"),
      show_default=True,
      help="Path to the root Flatpak manifest.",
  )
  @click.option(
      "--dry-run",
      is_flag=True,
      help="Do not modify Flatpak manifests on disk.",
  )
  @click.option(
      "--only",
      multiple=True,
      help="Only update the specified module names (can be repeated).",
  )
  def main(mapping: Path, manifest: Path, dry_run: bool, only: tuple[str, ...]) -> None:
      """Pins flatpak manifest dependencies to latest Fedora-stable versions."""
      try:
          rows = run(
              mapping,
              manifest,
              dry_run=dry_run,
              only=list(only) if only else None,
          )
      except BodhiLookupError as exc:
          click.echo(f"Error: {exc}", err=True)
          sys.exit(1)
      except MappingError as exc:
          click.echo(f"Mapping error: {exc}", err=True)
          sys.exit(2)

      click.echo(format_summary(rows))
      if any(row.status == "updated" for row in rows):
          sys.exit(0)
  ```

- [ ] **Step 6: Fix `fedora_release.py`**
  Add explicit type annotations and cast Bodhi release output:

  In `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/fedora_release.py`, replace lines 18-21 with:
  ```python
  def _fetch_releases(session: requests.Session) -> dict[str, Any]:
      response = session.get(BODHI_RELEASES_URL, params={"state": "current"}, timeout=30)
      response.raise_for_status()
      res = response.json()
      if not isinstance(res, dict):
          raise BodhiLookupError("Invalid response from Bodhi")
      ret: dict[str, Any] = res
      return ret
  ```

- [ ] **Step 7: Fix `mdapi_client.py`**
  Modify JSON parsing to return a `str` explicitly:

  In `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mdapi_client.py`, replace lines 40-45 with:
  ```python
          try:
              val = response.json()
              if not isinstance(val, dict) or "version" not in val:
                  raise MdapiTransientError("Invalid JSON response from MDAPI")
              version = str(val["version"])
          except (ValueError, KeyError) as exc:
              raise MdapiTransientError(f"Invalid JSON response from MDAPI: {exc}") from exc
          self._cache[package_name] = version
          return version
  ```

- [ ] **Step 8: Fix `migrate.py`**
  Update signatures, `NATIVE_MODULE_HINTS` type, and variable annotations:

  Replace the contents of `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/migrate.py` with:
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
  from typing import Any, Generator

  import click
  import requests
  from packaging.utils import canonicalize_name
  from ruamel.yaml import YAML

  from .fedora_release import get_current_stable_branch
  from .mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError

  PROTON_PREFIX = "proton"

  NATIVE_MODULE_HINTS: dict[str, dict[str, Any]] = {
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


  def _iter_dicts(node: Any) -> Generator[dict[Any, Any], None, None]:
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


  def build_draft(root_path: Path, branch: str, session: requests.Session) -> dict[str, Any]:
      mdapi = MdapiClient(branch, session=session)
      modules: dict[str, dict[str, Any]] = {}

      for pypi_name in sorted(discover_pypi_names(root_path)):
          guess = guess_fedora_package(pypi_name)
          entry: dict[str, Any] = {"recipe": "pypi", "pypi_name": pypi_name, "fedora_package": guess}
          try:
              mdapi.get_version(guess)
          except (PackageNotFoundError, MdapiTransientError, requests.RequestException) as exc:
              entry["_needs_manual_fix"] = f"{guess} lookup failed in Fedora {branch}: {exc}"
          modules[guess] = entry

      for name, hint in NATIVE_MODULE_HINTS.items():
          fedora_package = hint.get("fedora_package", name)
          entry = {"recipe": hint["recipe"], "fedora_package": fedora_package}
          entry.update({k: v for k, v in hint.items() if k not in ("recipe", "fedora_package")})
          try:
              version = mdapi.get_version(fedora_package)
          except (PackageNotFoundError, MdapiTransientError, requests.RequestException) as exc:
              entry["_needs_manual_fix"] = f"{fedora_package} lookup failed in Fedora {branch}: {exc}"
              modules[name] = entry
              continue

          if hint["recipe"] == "archive":
              rendered = Template(hint["url_template"]).substitute(version=version)
              try:
                  response = session.head(rendered, allow_redirects=True, timeout=30)
                  if response.status_code >= 400:
                      entry["_needs_manual_fix"] = (
                          f"url_template renders to {rendered} which returned "
                          f"{response.status_code} for version {version}"
                      )
              except requests.RequestException as exc:
                  entry["_needs_manual_fix"] = f"url_template check failed for {rendered}: {exc}"
          modules[name] = entry

      for module_name, note in MANUAL_FOLLOWUP.items():
          modules.setdefault(module_name, {})["manual_followup"] = note

      return {"modules": modules}


  @click.command()
  @click.option(
      "--manifest",
      type=click.Path(path_type=Path),
      default=Path("org.protonvpn.protonvpn.yml"),
      show_default=True,
      help="Path to the root Flatpak manifest.",
  )
  def main(manifest: Path) -> None:
      yaml = YAML()
      yaml.indent(mapping=2, sequence=4, offset=2)
      with requests.Session() as session:
          try:
              branch = get_current_stable_branch(session=session)
              draft = build_draft(manifest, branch, session)
              yaml.dump(draft, sys.stdout)
          except Exception as exc:
              click.echo(f"Error building draft mapping: {exc}", err=True)
              sys.exit(1)
  ```

- [ ] **Step 9: Fix assertion in `tests/fedora_flatpak_updater/test_mapping_loader.py`**
  Modify line 53 in `tests/fedora_flatpak_updater/test_mapping_loader.py` to assert that `url_template` is not None:
  ```python
      assert by_name["libndp"].recipe == RecipeKind.ARCHIVE
      assert by_name["libndp"].url_template is not None
      assert by_name["libndp"].url_template.endswith("v$version.tar.gz")
  ```

- [ ] **Step 10: Verify Mypy type checks pass**
  Run: `MYPYPATH=scripts/fedora_flatpak_updater/src uv run --project scripts/fedora_flatpak_updater mypy --config-file scripts/fedora_flatpak_updater/pyproject.toml --explicit-package-bases scripts/fedora_flatpak_updater/src/fedora_flatpak_updater tests/fedora_flatpak_updater`
  Expected: Success: no issues found in 22 source files.

- [ ] **Step 11: Run tests to verify correctness**
  Run: `uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v`
  Expected: All 49 unit tests pass successfully.

- [ ] **Step 12: Commit**
  ```bash
  git add scripts/fedora_flatpak_updater/ tests/fedora_flatpak_updater/
  git commit -m "feat: fix mypy strict-mode type errors across source and tests"
  ```
