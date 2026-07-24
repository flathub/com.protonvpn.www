# Fix GitHub Actions Startup Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the `startup_failure` in the GitHub Actions workflows caused by the restricted use of `astral-sh/setup-uv` in the Flathub organization by replacing it with allowed `actions/setup-python` and installing `uv` via pip.

**Architecture:** Use the allowed `actions/setup-python` action to bootstrap Python, followed by a standard `pip install uv` command to install `uv` into the environment. This ensures compatibility with Flathub's allowed action policies.

**Tech Stack:** GitHub Actions, Python 3.13, uv, pip

## Global Constraints

- GitHub Actions policy in `flathub` organization restricts allowed actions.
- Only actions owned by `flathub`, created by GitHub (`actions/`), or matching specific patterns (e.g., `peter-evans/create-pull-request`) are allowed.
- Modify the workflow files on the branch `automate-cargo-lock-updates` inside its git worktree.

---

### Task 1: Update Workflow Files to Use setup-python and pip install uv

**Files:**
- Modify: `.github/workflows/test-fedora-flatpak-updater.yml`
- Modify: `.github/workflows/update-fedora-flatpak-deps.yml`

**Interfaces:**
- Consumes: None
- Produces: Correctly configured YAML workflows that pass Flathub organization validation.

- [ ] **Step 1: Update test workflow file**

Modify `test-fedora-flatpak-updater.yml` to replace the `astral-sh/setup-uv` action step with `actions/setup-python` and `pip install uv`.

Replace:
```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.2
        with:
          python-version: "3.13"
```
With:
```yaml
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv
        run: pip install uv
```

- [ ] **Step 2: Update scheduled update workflow file**

Modify `update-fedora-flatpak-deps.yml` to replace the `astral-sh/setup-uv` action step with `actions/setup-python` and `pip install uv`.

Replace:
```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.2
        with:
          python-version: "3.13"
```
With:
```yaml
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv
        run: pip install uv
```

- [ ] **Step 3: Verify workflow YAML syntax locally**

Verify that both files are syntactically valid YAML files.

Run:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/test-fedora-flatpak-updater.yml'))"
python -c "import yaml; yaml.safe_load(open('.github/workflows/update-fedora-flatpak-deps.yml'))"
```
Expected: The commands complete successfully with no output (meaning the YAML is valid).

- [ ] **Step 4: Commit changes to the worktree branch**

Stage and commit the changes on the `automate-cargo-lock-updates` branch.

Run:
```bash
git add .github/workflows/test-fedora-flatpak-updater.yml .github/workflows/update-fedora-flatpak-deps.yml docs/superpowers/plans/2026-07-18-fix-github-actions-startup-failure.md
git commit -m "ci: replace blocked setup-uv action with setup-python and pip install uv"
```
Expected: The commit is created successfully.
