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


def _iter_dicts(node: Any, seen: set[int] | None = None):
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


def _remove_checker_data(block: dict) -> None:
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
    if isinstance(x_data, dict) and getattr(x_data, "ca", None):
        if x_data.ca.comment is not None:
            trailing_tokens.append(x_data.ca.comment)
        if x_data:
            last_k = list(x_data.keys())[-1]
            if hasattr(x_data.ca, "items") and last_k in x_data.ca.items:
                last_items = x_data.ca.items[last_k]
                for idx in (2, 3):
                    if len(last_items) > idx and last_items[idx] is not None:
                        trailing_tokens.append(last_items[idx])

    flat_tokens = []
    def _flatten(obj):
        if obj is None:
            return
        if isinstance(obj, (list, tuple)):
            for item in obj:
                _flatten(item)
        elif hasattr(obj, "value"):
            flat_tokens.append(obj)

    for t in trailing_tokens:
        _flatten(t)

    if flat_tokens and ca and hasattr(ca, "items"):
        new_last_k = list(block.keys())[-1]
        if new_last_k not in ca.items:
            ca.items[new_last_k] = [None, None, None, None]
        items_list = ca.items[new_last_k]
        while len(items_list) < 4:
            items_list.append(None)
        for token in flat_tokens:
            if items_list[2] is None:
                items_list[2] = token
            elif hasattr(items_list[2], "value") and hasattr(token, "value"):
                items_list[2].value += token.value


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
        self._yaml.indent(mapping=2, sequence=4, offset=2)
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
        seen = set()
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
        _remove_checker_data(block)
        touched += 1
    return PatchReport(module_name=spec.name, blocks_touched=touched)


def apply_archive(forest: ManifestForest, spec, source) -> PatchReport:
    touched = 0
    for module_block in find_module_blocks(forest, spec.name):
        for src in module_block.get("sources", []):
            if isinstance(src, dict) and src.get("type") == "archive":
                src["url"] = source.url
                src["sha256"] = source.sha256
                _remove_checker_data(src)
                touched += 1
    return PatchReport(module_name=spec.name, blocks_touched=touched)


def apply_git(forest: ManifestForest, spec, source) -> PatchReport:
    touched = 0
    for module_block in find_module_blocks(forest, spec.name):
        for src in module_block.get("sources", []):
            if isinstance(src, dict) and src.get("type") == "git":
                src["tag"] = source.tag
                src["commit"] = source.commit
                _remove_checker_data(src)
                touched += 1
    return PatchReport(module_name=spec.name, blocks_touched=touched)
