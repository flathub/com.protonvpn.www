# Update GitHub Actions Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update all GitHub Actions workflows to use the latest versions of checkout, setup-uv, and create-pull-request.

**Architecture:** Modify the YAML configurations for the repository's GitHub Actions workflows under `.github/workflows/` to reference the latest action versions.

**Tech Stack:** GitHub Actions

## Global Constraints
- Upgrade GitHub Actions dependencies to their latest stable releases as of July 2026.
- Maintain existing workflow logic and parameters.

---

### Task 1: Update action references in `test-fedora-flatpak-updater.yml`

**Files:**
- Modify: `.github/workflows/test-fedora-flatpak-updater.yml:25-30`

**Interfaces:**
- Consumes: None
- Produces: Updated workflow references in `test-fedora-flatpak-updater.yml`

- [ ] **Step 1: Modify `test-fedora-flatpak-updater.yml`**

Modify [test-fedora-flatpak-updater.yml](file:///home/slash/Development/com.protonvpn.www/.github/workflows/test-fedora-flatpak-updater.yml#L25-L30) to update actions/checkout and setup-uv references:

```yaml
      - uses: actions/checkout@v6

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.0
        with:
          python-version: "3.13"
```

- [ ] **Step 2: Commit changes**

```bash
git add .github/workflows/test-fedora-flatpak-updater.yml
git commit -m "chore(ci): update actions in test-fedora-flatpak-updater.yml"
```

---

### Task 2: Update action references in `update-fedora-flatpak-deps.yml`

**Files:**
- Modify: `.github/workflows/update-fedora-flatpak-deps.yml:18-24` and `.github/workflows/update-fedora-flatpak-deps.yml:43-46`

**Interfaces:**
- Consumes: None
- Produces: Updated workflow references in `update-fedora-flatpak-deps.yml`

- [ ] **Step 1: Modify `update-fedora-flatpak-deps.yml`**

Modify [update-fedora-flatpak-deps.yml](file:///home/slash/Development/com.protonvpn.www/.github/workflows/update-fedora-flatpak-deps.yml#L18-L24) and [update-fedora-flatpak-deps.yml](file:///home/slash/Development/com.protonvpn.www/.github/workflows/update-fedora-flatpak-deps.yml#L43-L46) to update checkout, setup-uv, and create-pull-request:

```yaml
      - uses: actions/checkout@v6

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.0
        with:
          python-version: "3.13"
```

and:

```yaml
      - name: Open pull request
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v8
```

- [ ] **Step 2: Commit changes**

```bash
git add .github/workflows/update-fedora-flatpak-deps.yml
git commit -m "chore(ci): update actions in update-fedora-flatpak-deps.yml"
```
