# Fix NetworkManager Build Error Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Flatpak build failure of the `NetworkManager` module by disabling `nm-cloud-setup` which requires the missing `jansson` library.

**Architecture:** Add `- -Dnm_cloud_setup=false` to the `config-opts` block of the `NetworkManager` module in the Flatpak manifest `com.protonvpn.www.yml`.

**Tech Stack:** Flatpak, Meson, NetworkManager

## Global Constraints
- Keep NetworkManager tag at `1.56.1` and commit at `b829f838fc5d8c93437faa5db44a5396b67893de`.
- Follow YAML styling of `com.protonvpn.www.yml`.

---

### Task 1: Disable nm-cloud-setup in NetworkManager configuration

**Files:**
- Modify: `com.protonvpn.www.yml:193-222`

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: Write the YAML modification**

Edit `com.protonvpn.www.yml` and add the `- -Dnm_cloud_setup=false` flag to `config-opts` under the `NetworkManager` module.

```diff
  - -Dlibpsl=false
  - -Dqt=false
+ - -Dnm_cloud_setup=false
```

- [ ] **Step 2: Verify manifest YAML syntax**

Verify that the YAML file is still syntactically valid.

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('com.protonvpn.www.yml'))"
```
Expected: Command exits successfully with no output (exit code 0).

- [ ] **Step 3: Commit the changes**

```bash
git add com.protonvpn.www.yml
git commit -m "build: disable nm-cloud-setup in NetworkManager config"
```
