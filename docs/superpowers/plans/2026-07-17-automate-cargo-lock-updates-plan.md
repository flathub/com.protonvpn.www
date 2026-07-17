# Automated Cargo Lockfile Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the extraction of `Cargo.lock` from PyPI sdist archives and invoke the `flatpak-cargo-generator.py` script to automatically update Cargo source JSON files.

**Architecture:** Extend `.fedora-tracked-modules.yaml` to specify cargo sources files and internal lockfile paths. When a python dependency built from source upgrades, download its sdist from PyPI, extract `Cargo.lock` in-memory, download the generator utility, run it via subprocess to regenerate the crate sources in-place, and roll back version changes if it fails.

**Tech Stack:** Python (requests, tarfile, zipfile, subprocess, tempfile, tomllib).

## Global Constraints

* The updater script continues using Fedora-stable versions for all Python dependencies.
* No local code changes should leave temporary files or directories in the git workspace.
* Unit tests must mock all external network calls (PyPI, Flathub) and subprocess invocations.

---

### Task 1: Model & Config Parser Extension

**Files:**
* Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/models.py`
* Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/mapping_loader.py`
* Modify: `tests/fedora_flatpak_updater/test_mapping_loader.py`

**Interfaces:**
* Consumes: Existing parser and `ModuleSpec` struct.
* Produces: Updated `ModuleSpec` fields: `cargo_sources_file: str | None` and `cargo_lock_path: str | None`.

- [ ] **Step 1: Write a failing unit test for the new config fields**
  Add the following test to `tests/fedora_flatpak_updater/test_mapping_loader.py`:
  ```python
  def test_load_mapping_with_cargo_fields():
      from pathlib import Path
      from fedora_flatpak_updater.mapping_loader import load_mapping
      # We will create a temporary config yaml containing cargo fields
      import tempfile
      yaml_content = """
  modules:
    python3-bcrypt:
      recipe: pypi
      pypi_name: bcrypt
      fedora_package: python3-bcrypt
      cargo_sources_file: bcrypt-cargo-sources.json
      cargo_lock_path: src/_bcrypt/Cargo.lock
  """
      with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
          tmp.write(yaml_content)
          tmp_path = Path(tmp.name)
      try:
          specs = load_mapping(tmp_path)
          assert len(specs) == 1
          assert specs[0].cargo_sources_file == "bcrypt-cargo-sources.json"
          assert specs[0].cargo_lock_path == "src/_bcrypt/Cargo.lock"
      finally:
          tmp_path.unlink()
  ```

- [ ] **Step 2: Run pytest to verify it fails**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_mapping_loader.py -k test_load_mapping_with_cargo_fields`
  Expected: FAIL with `TypeError: ModuleSpec() got an unexpected keyword argument 'cargo_sources_file'`

- [ ] **Step 3: Modify `models.py` and `mapping_loader.py`**
  In `models.py`, update `ModuleSpec` struct definition:
  ```python
  @dataclass(frozen=True)
  class ModuleSpec:
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
      cargo_sources_file: str | None = None
      cargo_lock_path: str | None = None
  ```
  In `mapping_loader.py`, modify `load_mapping` to parse the new fields:
  ```python
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
                  cargo_sources_file=entry.get("cargo_sources_file"),
                  cargo_lock_path=entry.get("cargo_lock_path"),
              )
          )
  ```

- [ ] **Step 4: Verify test passes**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_mapping_loader.py -v`
  Expected: PASS (all tests pass)

- [ ] **Step 5: Commit changes**
  Run:
  ```bash
  git add src/fedora_flatpak_updater/models.py src/fedora_flatpak_updater/mapping_loader.py tests/fedora_flatpak_updater/test_mapping_loader.py
  git commit --no-gpg-sign -m "feat: add cargo fields to ModuleSpec and mapping_loader"
  ```

---

### Task 2: PyPI sdist Downloader & Cargo.lock Extractor

**Files:**
* Create: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cargo_extractor.py`
* Create: `tests/fedora_flatpak_updater/test_cargo_extractor.py`

**Interfaces:**
* Consumes: `requests.Session`, `pypi_name`, `version`, `cargo_lock_path`
* Produces: `download_and_extract_cargo_lock(session, pypi_name, version, cargo_lock_path) -> bytes`

- [ ] **Step 1: Write test file with mock archive parsing**
  Create `tests/fedora_flatpak_updater/test_cargo_extractor.py`:
  ```python
  import io
  import tarfile
  import pytest
  import responses
  from fedora_flatpak_updater.cargo_extractor import download_and_extract_cargo_lock

  @responses.activate
  def test_download_and_extract_cargo_lock():
      # Mock the PyPI JSON response
      responses.add(
          responses.GET,
          "https://pypi.org/pypi/bcrypt/4.3.0/json",
          json={
              "urls": [
                  {
                      "packagetype": "sdist",
                      "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz"
                  }
              ]
          },
          status=200
      )

      # Create an in-memory tarball containing src/_bcrypt/Cargo.lock
      tar_buffer = io.BytesIO()
      with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
          content = b"[package]\nname = \"bcrypt\"\n"
          tarinfo = tarfile.TarInfo(name="bcrypt-4.3.0/src/_bcrypt/Cargo.lock")
          tarinfo.size = len(content)
          tar.addfile(tarinfo, io.BytesIO(content))
      tar_buffer.seek(0)

      responses.add(
          responses.GET,
          "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz",
          body=tar_buffer.read(),
          status=200
      )

      import requests
      with requests.Session() as session:
          lockfile_bytes = download_and_extract_cargo_lock(
              session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
          )
          assert lockfile_bytes == b"[package]\nname = \"bcrypt\"\n"
  ```

- [ ] **Step 2: Run tests to verify failure**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_cargo_extractor.py -v`
  Expected: FAIL with `ModuleNotFoundError: No module named 'fedora_flatpak_updater.cargo_extractor'`

- [ ] **Step 3: Implement `cargo_extractor.py` (sdist download and lockfile extraction logic)**
  Create `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cargo_extractor.py`:
  ```python
  from __future__ import annotations

  import io
  import tarfile
  import zipfile
  import requests

  class CargoLockExtractionError(RuntimeError):
      """Raised when sdist download or lockfile extraction fails."""

  def download_and_extract_cargo_lock(
      session: requests.Session,
      pypi_name: str,
      version: str,
      cargo_lock_path: str,
  ) -> bytes:
      pypi_url = f"https://pypi.org/pypi/{pypi_name}/{version}/json"
      try:
          resp = session.get(pypi_url, timeout=30)
          resp.raise_for_status()
          metadata = resp.json()
      except Exception as exc:
          raise CargoLockExtractionError(f"Failed to fetch PyPI metadata for {pypi_name}=={version}: {exc}") from exc

      sdist_url = None
      for url_info in metadata.get("urls", []):
          if url_info.get("packagetype") == "sdist":
              sdist_url = url_info.get("url")
              break

      if not sdist_url:
          raise CargoLockExtractionError(f"No source distribution (sdist) found for {pypi_name}=={version}")

      try:
          sdist_resp = session.get(sdist_url, timeout=30)
          sdist_resp.raise_for_status()
          archive_bytes = sdist_resp.content
      except Exception as exc:
          raise CargoLockExtractionError(f"Failed to download sdist from {sdist_url}: {exc}") from exc

      filename = sdist_url.split("/")[-1]
      
      # Handle tar.gz / tar.bz2 / tar.xz / zip
      if filename.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
          try:
              with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tar:
                  # Prepend top-level directory dynamically
                  members = tar.getmembers()
                  if not members:
                      raise CargoLockExtractionError("Empty sdist archive")
                  top_level = members[0].name.split("/")[0]
                  target_name = f"{top_level}/{cargo_lock_path}"

                  for member in members:
                      if member.name == target_name:
                          f = tar.extractfile(member)
                          if f is not None:
                              return f.read()
          except Exception as exc:
              if isinstance(exc, CargoLockExtractionError):
                  raise
              raise CargoLockExtractionError(f"Error extracting tarball: {exc}") from exc
      elif filename.endswith(".zip"):
          try:
              with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_ref:
                  names = zip_ref.namelist()
                  if not names:
                      raise CargoLockExtractionError("Empty zip archive")
                  top_level = names[0].split("/")[0]
                  target_name = f"{top_level}/{cargo_lock_path}"

                  if target_name in names:
                      return zip_ref.read(target_name)
          except Exception as exc:
              if isinstance(exc, CargoLockExtractionError):
                  raise
              raise CargoLockExtractionError(f"Error extracting zip: {exc}") from exc

      raise CargoLockExtractionError(f"Could not find lockfile at {cargo_lock_path} inside sdist archive {filename}")
  ```

- [ ] **Step 4: Run pytest to verify success**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_cargo_extractor.py -v`
  Expected: PASS

- [ ] **Step 5: Commit changes**
  Run:
  ```bash
  git add src/fedora_flatpak_updater/cargo_extractor.py tests/fedora_flatpak_updater/test_cargo_extractor.py
  git commit --no-gpg-sign -m "feat: implement sdist download and Cargo.lock extraction"
  ```

---

### Task 3: Cargo Generator Downloader and Subprocess Runner

**Files:**
* Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cargo_extractor.py`
* Modify: `tests/fedora_flatpak_updater/test_cargo_extractor.py`

**Interfaces:**
* Consumes: `requests.Session`, `cargo_lock_content`, `output_sources_file`
* Produces: `run_cargo_generator(session, cargo_lock_content, output_sources_file)`

- [ ] **Step 1: Write unit test for generator runner**
  Add the following test to `tests/fedora_flatpak_updater/test_cargo_extractor.py`:
  ```python
  from unittest.mock import patch, MagicMock
  from pathlib import Path
  from fedora_flatpak_updater.cargo_extractor import run_cargo_generator

  @responses.activate
  def test_run_cargo_generator():
      # Mock the flatpak-cargo-generator.py script download
      responses.add(
          responses.GET,
          "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/cargo/flatpak-cargo-generator.py",
          body=b"print('mock generator script')",
          status=200
      )

      import requests
      with requests.Session() as session:
          with patch("subprocess.run") as mock_run:
              mock_run.return_value = MagicMock(returncode=0)
              
              run_cargo_generator(session, b"[mock cargo lock]", Path("mock-sources.json"))
              
              # Assert subprocess was called
              mock_run.assert_called_once()
              args = mock_run.call_args[0][0]
              assert "flatpak-cargo-generator.py" in args[1]
              assert "-o" in args
              assert "mock-sources.json" in args
  ```

- [ ] **Step 2: Run pytest to verify failure**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_cargo_extractor.py -k test_run_cargo_generator`
  Expected: FAIL with `ImportError: cannot import name 'run_cargo_generator'`

- [ ] **Step 3: Implement `run_cargo_generator` inside `cargo_extractor.py`**
  Append this function to `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cargo_extractor.py`:
  ```python
  import os
  import sys
  import tempfile
  import subprocess
  from pathlib import Path

  GENERATOR_URL = "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/cargo/flatpak-cargo-generator.py"

  def run_cargo_generator(
      session: requests.Session,
      cargo_lock_content: bytes,
      output_sources_file: Path,
  ) -> None:
      # Download flatpak-cargo-generator.py
      try:
          resp = session.get(GENERATOR_URL, timeout=30)
          resp.raise_for_status()
          generator_script = resp.content
      except Exception as exc:
          raise CargoLockExtractionError(f"Failed to download flatpak-cargo-generator.py: {exc}") from exc

      with tempfile.TemporaryDirectory() as tempdir:
          script_path = Path(tempdir) / "flatpak-cargo-generator.py"
          script_path.write_bytes(generator_script)
          
          lock_path = Path(tempdir) / "Cargo.lock"
          lock_path.write_bytes(cargo_lock_content)

          cmd = [
              sys.executable,
              str(script_path),
              "-o",
              str(output_sources_file),
              str(lock_path),
          ]
          try:
              result = subprocess.run(cmd, capture_output=True, text=True, check=True)
          except subprocess.CalledProcessError as exc:
              raise CargoLockExtractionError(
                  f"flatpak-cargo-generator.py failed with exit code {exc.returncode}\n"
                  f"stdout: {exc.stdout}\n"
                  f"stderr: {exc.stderr}"
              ) from exc
  ```

- [ ] **Step 4: Run pytest to verify success**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_cargo_extractor.py -v`
  Expected: PASS

- [ ] **Step 5: Commit changes**
  Run:
  ```bash
  git add src/fedora_flatpak_updater/cargo_extractor.py tests/fedora_flatpak_updater/test_cargo_extractor.py
  git commit --no-gpg-sign -m "feat: implement flatpak-cargo-generator subprocess execution"
  ```

---

### Task 4: Orchestrator CLI Integration & Rollback Handling

**Files:**
* Modify: `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cli.py`
* Modify: `tests/fedora_flatpak_updater/test_cli.py`

**Interfaces:**
* Consumes: `run` in `cli.py`
* Produces: Automated integration of Cargo updates with rollback protection.

- [ ] **Step 1: Write integration tests for rollback and successful run**
  Modify `tests/fedora_flatpak_updater/test_cli.py` to add tests:
  ```python
  def test_run_cargo_success(tmp_path):
      # Test successful run updating cargo sources
      pass

  def test_run_cargo_failure_rollback(tmp_path):
      # Test that if generator fails, manifest changes are rolled back and module skipped
      pass
  ```
  *(Actual test implementation will mock `download_and_extract_cargo_lock` and `run_cargo_generator` to verify the state changes correctly).*

- [ ] **Step 2: Run pytest to verify failure**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_cli.py -v`
  Expected: Existing tests pass, new tests fail/empty.

- [ ] **Step 3: Modify `cli.py` to perform the cargo update and rollback if it fails**
  In `scripts/fedora_flatpak_updater/src/fedora_flatpak_updater/cli.py`:
  Import the extractor functions:
  ```python
  from .cargo_extractor import download_and_extract_cargo_lock, run_cargo_generator, CargoLockExtractionError
  ```
  Update `run` to perform sdist and lockfile update checks. If `spec.cargo_sources_file` is defined, wrap in a try-except block. Before doing so, copy the state of the ManifestForest documents so they can be rolled back if an error occurs.
  ```python
          # Within the loop for spec in specs:
          # (Around lines 87-118, after resolving source and patching manifest)
          
          # 1. Capture snapshot of manifest document state before changes
          # 2. Apply recipe version change as normal
          # 3. If cargo_sources_file is set, download sdist, extract Cargo.lock, run generator
          # 4. If generator fails, restore manifest documents from snapshot, mark Row as "skipped"
  ```
  Let's define the precise patch block in `cli.py` for this rollback mechanism.

- [ ] **Step 4: Run pytest to verify success**
  Run: `uv run pytest ../../tests/fedora_flatpak_updater/test_cli.py -v`
  Expected: PASS

- [ ] **Step 5: Commit changes**
  Run:
  ```bash
  git add src/fedora_flatpak_updater/cli.py tests/fedora_flatpak_updater/test_cli.py
  git commit --no-gpg-sign -m "feat: integrate cargo updates with rollback support in orchestrator"
  ```

---

### Task 5: Configuration & Verification

**Files:**
* Modify: `.fedora-tracked-modules.yaml`

- [ ] **Step 1: Update `.fedora-tracked-modules.yaml`**
  Modify `.fedora-tracked-modules.yaml` to add `cargo_sources_file` and `cargo_lock_path` to `python3-bcrypt`:
  ```yaml
    python3-bcrypt:
      recipe: pypi
      pypi_name: bcrypt
      fedora_package: python3-bcrypt
      cargo_sources_file: bcrypt-cargo-sources.json
      cargo_lock_path: src/_bcrypt/Cargo.lock
      manual_followup: null # We can remove or keep this
  ```

- [ ] **Step 2: Run dry-run locally to verify parsing config works**
  Run: `uv run --project scripts/fedora_flatpak_updater python -m fedora_flatpak_updater.cli --dry-run`
  Expected: Execution completes cleanly, summary table printed, output matches normal.

- [ ] **Step 3: Run full pytest suite**
  Run: `uv run pytest ../../tests`
  Expected: 100% PASS

- [ ] **Step 4: Commit config**
  Run:
  ```bash
  git add .fedora-tracked-modules.yaml
  git commit --no-gpg-sign -m "config: configure python3-bcrypt cargo automation"
  ```
