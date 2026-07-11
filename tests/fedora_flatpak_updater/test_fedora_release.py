from __future__ import annotations

import pytest
import requests
import responses

from fedora_flatpak_updater.fedora_release import BodhiLookupError, get_current_stable_branch

BODHI_URL = "https://bodhi.fedoraproject.org/releases/"

SAMPLE_PAYLOAD = {
    "releases": [
        {"id_prefix": "FEDORA", "version": "43", "released_on": "2025-04-15", "state": "current"},
        {"id_prefix": "FEDORA", "version": "44", "released_on": "2025-11-11", "state": "current"},
        {"id_prefix": "FEDORA", "version": "45", "released_on": None, "state": "current"},
        {"id_prefix": "FEDORA-CONTAINER", "version": "44", "released_on": "2025-11-11", "state": "current"},
        {"id_prefix": "FEDORA-FLATPAK", "version": "44", "released_on": "2025-11-11", "state": "current"},
        {"id_prefix": "FEDORA-EPEL", "version": "9", "released_on": "2022-01-01", "state": "current"},
    ]
}


@responses.activate
def test_picks_highest_released_fedora_version():
    responses.add(responses.GET, BODHI_URL, json=SAMPLE_PAYLOAD, status=200)
    assert get_current_stable_branch() == "f44"


@responses.activate
def test_retries_once_on_transient_failure_then_succeeds():
    responses.add(responses.GET, BODHI_URL, body=requests.exceptions.ConnectionError("network blip"))
    responses.add(responses.GET, BODHI_URL, json=SAMPLE_PAYLOAD, status=200)
    assert get_current_stable_branch() == "f44"


@responses.activate
def test_raises_bodhi_lookup_error_after_exhausting_retries():
    responses.add(responses.GET, BODHI_URL, body=requests.exceptions.ConnectionError("still broken"))
    responses.add(responses.GET, BODHI_URL, body=requests.exceptions.ConnectionError("still broken"))
    with pytest.raises(BodhiLookupError):
        get_current_stable_branch()


@responses.activate
def test_raises_bodhi_lookup_error_when_no_current_release_found():
    responses.add(responses.GET, BODHI_URL, json={"releases": []}, status=200)
    with pytest.raises(BodhiLookupError):
        get_current_stable_branch()
