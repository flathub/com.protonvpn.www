# Update Fedora Flatpak Updater Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update all runtime and dev dependencies in `scripts/fedora_flatpak_updater/pyproject.toml` to their latest stable versions and regenerate `uv.lock`.

**Architecture:** Modify version constraints in `pyproject.toml`, regenerate the project's lockfile using `uv sync`, and verify correctness by running the existing unit test suite.

**Tech Stack:** Python, uv, pytest

## Global Constraints
- Upgrade python dependencies to their latest stable releases as of July 2026.
- Maintain python >= 3.10 compatibility.
- Ensure all 47 tests pass post-update.

---

### Task 1: Update dependency constraints in `pyproject.toml` and synchronize environment

**Files:**
- Modify: `scripts/fedora_flatpak_updater/pyproject.toml:7-14`, `scripts/fedora_flatpak_updater/pyproject.toml:25-28`

**Interfaces:**
- Consumes: None
- Produces: Updated version constraints in `pyproject.toml` and a synchronized `uv.lock` file.

- [ ] **Step 1: Modify `pyproject.toml`**

Modify [pyproject.toml](file:///home/slash/Development/com.protonvpn.www/scripts/fedora_flatpak_updater/pyproject.toml#L7-L14) and [pyproject.toml](file:///home/slash/Development/com.protonvpn.www/scripts/fedora_flatpak_updater/pyproject.toml#L25-L28) to update the versions of click, packaging, requests, ruamel.yaml, tabulate, tenacity, pytest, and responses:

```toml
dependencies = [
    "requests>=2.34.2",
    "ruamel.yaml>=0.19.1",
    "tenacity>=9.1.4",
    "click>=8.4.2",
    "tabulate>=0.10.0",
    "packaging>=26.2",
]
```

and:

```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "responses>=0.26.2",
]
```

- [ ] **Step 2: Sync python virtual environment and update lockfile**

Run `uv sync` to update `uv.lock` and regenerate the local virtual environment.

Run:
```bash
uv sync --project scripts/fedora_flatpak_updater
```

Expected Output:
```
Resolved 21 packages in ...
Audited ...
```

- [ ] **Step 3: Run existing unit tests to verify no regressions**

Verify that all existing tests pass under the upgraded dependencies.

Run:
```bash
uv run --project scripts/fedora_flatpak_updater pytest tests/fedora_flatpak_updater -v
```

Expected Output:
```
============================== 47 passed in ...s ==============================
```

- [ ] **Step 4: Commit changes**

Commit the updated dependencies and lockfile.

Run:
```bash
git add scripts/fedora_flatpak_updater/pyproject.toml scripts/fedora_flatpak_updater/uv.lock
git commit -m "chore(deps): update python dependencies to latest versions"
```
