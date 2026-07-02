from __future__ import annotations

import pytest
import requests
import responses

from fedora_flatpak_updater.mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError


@responses.activate
def test_get_version_returns_version_field():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-cryptography"
    responses.add(responses.GET, url, json={"version": "46.0.7"}, status=200)

    client = MdapiClient("f44")
    assert client.get_version("python3-cryptography") == "46.0.7"


@responses.activate
def test_get_version_caches_repeat_calls():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-cryptography"
    responses.add(responses.GET, url, json={"version": "46.0.7"}, status=200)

    client = MdapiClient("f44")
    client.get_version("python3-cryptography")
    client.get_version("python3-cryptography")
    assert len(responses.calls) == 1


@responses.activate
def test_get_version_raises_package_not_found_on_404():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-does-not-exist"
    responses.add(responses.GET, url, status=404)

    client = MdapiClient("f44")
    with pytest.raises(PackageNotFoundError):
        client.get_version("python3-does-not-exist")


@responses.activate
def test_get_version_raises_package_not_found_on_400():
    url = "https://mdapi.fedoraproject.org/f44/pkg/python3-meson"
    responses.add(responses.GET, url, status=400)

    client = MdapiClient("f44")
    with pytest.raises(PackageNotFoundError):
        client.get_version("python3-meson")


@responses.activate
def test_get_version_retries_once_on_5xx_then_succeeds():
    url = "https://mdapi.fedoraproject.org/f44/pkg/libndp"
    responses.add(responses.GET, url, status=502)
    responses.add(responses.GET, url, json={"version": "1.10"}, status=200)

    client = MdapiClient("f44")
    assert client.get_version("libndp") == "1.10"


@responses.activate
def test_get_version_raises_transient_error_after_two_5xx():
    url = "https://mdapi.fedoraproject.org/f44/pkg/libndp"
    responses.add(responses.GET, url, status=502)
    responses.add(responses.GET, url, status=502)

    client = MdapiClient("f44")
    with pytest.raises(MdapiTransientError):
        client.get_version("libndp")


@responses.activate
def test_get_version_retries_and_raises_transient_error_on_connection_error():
    url = "https://mdapi.fedoraproject.org/f44/pkg/libndp"
    responses.add(responses.GET, url, body=requests.ConnectionError("Connection aborted"))
    responses.add(responses.GET, url, body=requests.ConnectionError("Connection aborted"))

    client = MdapiClient("f44")
    with pytest.raises(MdapiTransientError):
        client.get_version("libndp")
