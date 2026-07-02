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
        tag_name = ref[len("refs/tags/") :]
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
