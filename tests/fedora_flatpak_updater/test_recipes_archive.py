from __future__ import annotations

import hashlib

import pytest
import responses

from fedora_flatpak_updater.recipes.archive import ArchiveResolutionError, render_url, resolve


def test_render_url_substitutes_version():
    rendered = render_url("https://github.com/jpirko/libndp/archive/v$version.tar.gz", "1.10")
    assert rendered == "https://github.com/jpirko/libndp/archive/v1.10.tar.gz"


@responses.activate
def test_resolve_computes_sha256_of_downloaded_content():
    content = b"fake tarball bytes"
    url = "https://github.com/jpirko/libndp/archive/v1.10.tar.gz"
    responses.add(responses.GET, url, body=content, status=200)

    source = resolve("https://github.com/jpirko/libndp/archive/v$version.tar.gz", "1.10")

    assert source.url == url
    assert source.sha256 == hashlib.sha256(content).hexdigest()


@responses.activate
def test_resolve_raises_on_404():
    url = "https://gitlab.freedesktop.org/polkit/polkit/-/archive/127/polkit-127.tar.gz"
    responses.add(responses.GET, url, status=404)

    with pytest.raises(ArchiveResolutionError):
        resolve(
            "https://gitlab.freedesktop.org/polkit/polkit/-/archive/$version/polkit-$version.tar.gz",
            "127",
        )
