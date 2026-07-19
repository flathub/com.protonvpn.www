# Rollback NetworkManager & Fix CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roll back NetworkManager to version 1.40.18 and NetworkManager-openvpn to version 1.10.2 to fix the Flatpak CI compilation errors.

**Architecture:** We will adjust the manifest (`com.protonvpn.www.yml`) to use the compatible versions of both `NetworkManager` and `NetworkManager-openvpn`. This ensures that `NetworkManager-openvpn` does not fail with unmet requirements for a newer `libnm` version. We will also add checker limits to prevent the automated updater from breaking these versions.

**Tech Stack:** YAML, Flatpak manifest parser.

## Global Constraints

- NetworkManager must be rolled back to version 1.40.18.
- NetworkManager-openvpn must be rolled back to version 1.10.2 to remain compatible with NetworkManager 1.40.18.
- YAML manifest `com.protonvpn.www.yml` must parse correctly and have both modules configured at their rolled-back versions.

---

### Task 1: Rollback NetworkManager-openvpn and Verify Manifest

**Files:**
- Modify: `com.protonvpn.www.yml:265-271`
- Create: `tests/test_manifest_structure.py`

**Interfaces:**
- Consumes: None
- Produces: Correctly configured Flatpak manifest where NetworkManager is at 1.40.18 and NetworkManager-openvpn is at 1.10.2.

- [ ] **Step 1: Write the failing test**

Create a Python script `tests/test_manifest_structure.py` that parses the manifest and asserts that both `NetworkManager` and `NetworkManager-openvpn` are present as top-level items in the `modules` list and pinned to the correct versions.

Write to `tests/test_manifest_structure.py`:
```python
import yaml

def test_manifest_structure():
    with open("com.protonvpn.www.yml", "r") as f:
        data = yaml.safe_load(f)
    
    modules = data.get("modules", [])
    
    # 1. Verify NetworkManager
    nm_module = next((m for m in modules if isinstance(m, dict) and m.get("name") == "NetworkManager"), None)
    assert nm_module is not None, "NetworkManager module not found as a top-level item under 'modules'!"
    assert nm_module.get("sources") is not None, "NetworkManager sources list not found!"
    nm_source = next((s for s in nm_module["sources"] if s.get("type") == "git"), None)
    assert nm_source is not None, "NetworkManager git source not found!"
    assert nm_source.get("tag") == "1.40.18", f"Expected NetworkManager tag 1.40.18, got {nm_source.get('tag')}"
    assert nm_source.get("commit") == "2db3748ec8162ce948ba52f71b42a258ff8d64ba", f"Expected NetworkManager commit 2db3748ec8162ce948ba52f71b42a258ff8d64ba, got {nm_source.get('commit')}"
    
    # 2. Verify NetworkManager-openvpn
    nmo_module = next((m for m in modules if isinstance(m, dict) and m.get("name") == "NetworkManager-openvpn"), None)
    assert nmo_module is not None, "NetworkManager-openvpn module not found as a top-level item under 'modules'!"
    assert nmo_module.get("sources") is not None, "NetworkManager-openvpn sources list not found!"
    nmo_source = next((s for s in nmo_module["sources"] if s.get("type") == "git"), None)
    assert nmo_source is not None, "NetworkManager-openvpn git source not found!"
    assert nmo_source.get("tag") == "1.10.2", f"Expected NetworkManager-openvpn tag 1.10.2, got {nmo_source.get('tag')}"
    assert nmo_source.get("commit") == "ae9575dd07cc2d2d51ec8d0297823e07017cb6e6", f"Expected NetworkManager-openvpn commit ae9575dd07cc2d2d51ec8d0297823e07017cb6e6, got {nmo_source.get('commit')}"

    print("Test passed: NetworkManager and NetworkManager-openvpn are rolled back correctly.")

if __name__ == "__main__":
    test_manifest_structure()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_manifest_structure.py`
Expected: FAIL with `AssertionError: Expected NetworkManager-openvpn tag 1.10.2, got 1.12.5` (or similar assertion error)

- [ ] **Step 3: Write minimal implementation**

Modify `com.protonvpn.www.yml` to rollback `NetworkManager-openvpn` to 1.10.2.

Target lines 265-271:
```yaml
- name: NetworkManager-openvpn
  buildsystem: autotools
  sources:
  - type: git
    url: https://github.com/NetworkManager/NetworkManager-openvpn.git
    tag: 1.12.5
    commit: d03d6a636866e9be9fbec7977ef377c191fb2988 # 1.10.4 causes connection failure
```

Change to:
```yaml
- name: NetworkManager-openvpn
  buildsystem: autotools
  sources:
  - type: git
    url: https://github.com/NetworkManager/NetworkManager-openvpn.git
    tag: 1.10.2
    commit: ae9575dd07cc2d2d51ec8d0297823e07017cb6e6
    x-checker-data:
      type: anitya
      project-id: 69977
      stable-only: true
      tag-template: $version
      versions:
        # 1.10.4 causes connection failure
        <: 1.10.4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_manifest_structure.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_manifest_structure.py com.protonvpn.www.yml
git commit -m "fix(manifest): rollback NetworkManager-openvpn to 1.10.2 for NetworkManager compatibility"
```
