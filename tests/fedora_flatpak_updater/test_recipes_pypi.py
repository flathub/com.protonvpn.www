from __future__ import annotations

import pytest
import responses

from fedora_flatpak_updater.recipes.pypi import (
    PypiVersionNotFoundError,
    resolve,
    resolve_multi_wheel,
    resolve_sdist,
    resolve_wheel,
)

IDNA_URL = "https://pypi.org/pypi/idna/3.11/json"
IDNA_JSON = {
    "urls": [
        {
            "packagetype": "sdist",
            "url": "https://files.pythonhosted.org/packages/.../idna-3.11.tar.gz",
            "digests": {"sha256": "sdist" + "0" * 59},
        },
        {
            "packagetype": "bdist_wheel",
            "filename": "idna-3.11-py3-none-any.whl",
            "url": "https://files.pythonhosted.org/packages/.../idna-3.11-py3-none-any.whl",
            "digests": {"sha256": "wheel" + "0" * 59},
        },
    ]
}

CRYPTOGRAPHY_URL = "https://pypi.org/pypi/cryptography/46.0.7/json"
CRYPTOGRAPHY_JSON = {
    "urls": [
        {
            "packagetype": "bdist_wheel",
            "filename": "cryptography-46.0.7-cp311-abi3-manylinux_2_28_aarch64.whl",
            "url": "https://files.pythonhosted.org/.../cryptography-46.0.7-cp311-abi3-manylinux_2_28_aarch64.whl",
            "digests": {"sha256": "aarch64" + "0" * 57},
        },
        {
            "packagetype": "bdist_wheel",
            "filename": "cryptography-46.0.7-cp311-abi3-manylinux_2_28_x86_64.whl",
            "url": "https://files.pythonhosted.org/.../cryptography-46.0.7-cp311-abi3-manylinux_2_28_x86_64.whl",
            "digests": {"sha256": "x86_64" + "0" * 58},
        },
    ]
}


@responses.activate
def test_resolve_wheel_picks_bdist_wheel_entry():
    responses.add(responses.GET, IDNA_URL, json=IDNA_JSON, status=200)
    source = resolve_wheel("idna", "3.11")
    assert source.url.endswith(".whl")
    assert source.sha256.startswith("wheel")


@responses.activate
def test_resolve_sdist_picks_sdist_entry():
    responses.add(responses.GET, IDNA_URL, json=IDNA_JSON, status=200)
    source = resolve_sdist("idna", "3.11")
    assert source.url.endswith(".tar.gz")
    assert source.sha256.startswith("sdist")


@responses.activate
def test_resolve_prefers_wheel_by_default():
    responses.add(responses.GET, IDNA_URL, json=IDNA_JSON, status=200)
    source = resolve("idna", "3.11")
    assert source.url.endswith(".whl")


@responses.activate
def test_resolve_falls_back_to_sdist_when_no_wheel_available():
    payload = {"urls": [IDNA_JSON["urls"][0]]}  # sdist only
    responses.add(responses.GET, IDNA_URL, json=payload, status=200)
    source = resolve("idna", "3.11", prefer="wheel")
    assert source.url.endswith(".tar.gz")


@responses.activate
def test_resolve_raises_when_version_missing_on_pypi():
    responses.add(responses.GET, "https://pypi.org/pypi/idna/999.0/json", status=404)
    with pytest.raises(PypiVersionNotFoundError):
        resolve("idna", "999.0")


@responses.activate
def test_resolve_multi_wheel_selects_one_wheel_per_arch():
    responses.add(responses.GET, CRYPTOGRAPHY_URL, json=CRYPTOGRAPHY_JSON, status=200)
    result = resolve_multi_wheel("cryptography", "46.0.7", ("aarch64", "x86_64"))
    assert result["aarch64"].sha256.startswith("aarch64")
    assert result["x86_64"].sha256.startswith("x86_64")
    assert result["aarch64"].only_arches == ("aarch64",)
