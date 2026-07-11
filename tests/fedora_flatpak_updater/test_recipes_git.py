from __future__ import annotations

import pytest

from fedora_flatpak_updater.recipes.git import GitTagNotFoundError, resolve

NETWORKMANAGER_LS_REMOTE = (
    "2db3748ec8162ce948ba52f71b42a258ff8d64ba\trefs/tags/1.40.18\n"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/1.54.3\n"
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/1.54.3^{}\n"
)

SYSTEMD_LS_REMOTE = (
    "cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v259.0\n"
    "dddddddddddddddddddddddddddddddddddddddd\trefs/tags/v260.2\n"
    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\trefs/tags/v260.2^{}\n"
)


class _FakeCompleted:
    def __init__(self, stdout: str):
        self.stdout = stdout


def _runner_returning(stdout: str):
    def runner(*args, **kwargs):
        return _FakeCompleted(stdout)

    return runner


def test_resolve_by_tag_template_prefers_peeled_hash():
    source = resolve(
        repo_url="https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
        version="1.54.3",
        tag_template="$version",
        runner=_runner_returning(NETWORKMANAGER_LS_REMOTE),
    )
    assert source.tag == "1.54.3"
    assert source.commit == "b" * 40


def test_resolve_by_tag_pattern_matches_captured_version():
    source = resolve(
        repo_url="https://github.com/systemd/systemd.git",
        version="260.2",
        tag_pattern=r"^v([\d.]+)$",
        runner=_runner_returning(SYSTEMD_LS_REMOTE),
    )
    assert source.tag == "v260.2"
    assert source.commit == "e" * 40


def test_resolve_raises_when_tag_not_found():
    with pytest.raises(GitTagNotFoundError):
        resolve(
            repo_url="https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
            version="99.0.0",
            tag_template="$version",
            runner=_runner_returning(NETWORKMANAGER_LS_REMOTE),
        )


def test_resolve_ignores_lines_without_tabs():
    output_with_noise = (
        "warning: some git warning here\n"
        "2db3748ec8162ce948ba52f71b42a258ff8d64ba\trefs/tags/1.40.18\n"
    )
    source = resolve(
        repo_url="https://gitlab.freedesktop.org/NetworkManager/NetworkManager.git",
        version="1.40.18",
        tag_template="$version",
        runner=_runner_returning(output_with_noise),
    )
    assert source.tag == "1.40.18"
    assert source.commit == "2db3748ec8162ce948ba52f71b42a258ff8d64ba"

