# Upgrade GitHub Actions Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade GitHub Actions workflow files to use the latest versions of actions/checkout, setup-uv, and create-pull-request.

**Architecture:** Modify the YAML configurations for the repository's GitHub Actions workflows under `.github/workflows/` directly. Validate that the files are syntactically valid YAML and contain the upgraded version references using command-line checks before committing.

**Tech Stack:** GitHub Actions, Bash, Python

## Global Constraints

- Upgrade GitHub Actions dependencies to their latest stable releases as of July 2026.
- Maintain existing workflow logic and parameters.
- Ensure all workflow files remain syntactically valid YAML.

---

### Task 1: Upgrade `test-fedora-flatpak-updater.yml`

**Files:**
- Modify: `.github/workflows/test-fedora-flatpak-updater.yml`

**Interfaces:**
- Consumes: None
- Produces: Updated workflow `test-fedora-flatpak-updater.yml` with `actions/checkout@v7` and `astral-sh/setup-uv@v8.3.2`.

- [ ] **Step 1: Verify presence of old versions**

Verify that the file currently contains the old action versions.

Run:
```bash
grep -q 'checkout@v6' .github/workflows/test-fedora-flatpak-updater.yml && \
grep -q 'setup-uv@v8.3.0' .github/workflows/test-fedora-flatpak-updater.yml
```
Expected: Exit code 0 (success)

- [ ] **Step 2: Modify `test-fedora-flatpak-updater.yml`**

Update `actions/checkout` and `astral-sh/setup-uv` versions in `.github/workflows/test-fedora-flatpak-updater.yml`:

```yaml
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.2
        with:
          python-version: "3.13"
```

- [ ] **Step 3: Validate YAML syntax and new versions**

Verify that the file contains the new versions and is syntactically valid YAML.

Run:
```bash
grep -q 'checkout@v7' .github/workflows/test-fedora-flatpak-updater.yml && \
grep -q 'setup-uv@v8.3.2' .github/workflows/test-fedora-flatpak-updater.yml && \
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test-fedora-flatpak-updater.yml'))"
```
Expected: Exit code 0 (success)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test-fedora-flatpak-updater.yml
git commit -m "chore(ci): upgrade test-fedora-flatpak-updater.yml to checkout@v7 and setup-uv@v8.3.2"
```

---

### Task 2: Upgrade `update-fedora-flatpak-deps.yml`

**Files:**
- Modify: `.github/workflows/update-fedora-flatpak-deps.yml`

**Interfaces:**
- Consumes: None
- Produces: Updated workflow `update-fedora-flatpak-deps.yml` with `actions/checkout@v7`, `astral-sh/setup-uv@v8.3.2`, and `peter-evans/create-pull-request@v8.1.1`.

- [ ] **Step 1: Verify presence of old versions**

Verify that the file currently contains the old action versions.

Run:
```bash
grep -q 'checkout@v6' .github/workflows/update-fedora-flatpak-deps.yml && \
grep -q 'setup-uv@v8.3.0' .github/workflows/update-fedora-flatpak-deps.yml && \
grep -q 'create-pull-request@v8' .github/workflows/update-fedora-flatpak-deps.yml
```
Expected: Exit code 0 (success)

- [ ] **Step 2: Modify `update-fedora-flatpak-deps.yml`**

Update the versions in `.github/workflows/update-fedora-flatpak-deps.yml`:

```yaml
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.2
        with:
          python-version: "3.13"
```

and:

```yaml
      - name: Open pull request
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v8.1.1
        with:
          commit-message: "chore: update Flatpak dependencies to Fedora-stable versions"
```

- [ ] **Step 3: Validate YAML syntax and new versions**

Verify that the file contains the new versions and is syntactically valid YAML.

Run:
```bash
grep -q 'checkout@v7' .github/workflows/update-fedora-flatpak-deps.yml && \
grep -q 'setup-uv@v8.3.2' .github/workflows/update-fedora-flatpak-deps.yml && \
grep -q 'create-pull-request@v8.1.1' .github/workflows/update-fedora-flatpak-deps.yml && \
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-fedora-flatpak-deps.yml'))"
```
Expected: Exit code 0 (success)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/update-fedora-flatpak-deps.yml
git commit -m "chore(ci): upgrade update-fedora-flatpak-deps.yml to checkout@v7, setup-uv@v8.3.2, and create-pull-request@v8.1.1"
```
