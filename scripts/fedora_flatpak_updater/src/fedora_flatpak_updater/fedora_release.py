from __future__ import annotations

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt

BODHI_RELEASES_URL = "https://bodhi.fedoraproject.org/releases/"


class BodhiLookupError(RuntimeError):
    """Raised when the current Fedora stable branch cannot be determined."""


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(2),  # 1 try + 1 retry
    reraise=True,
)
def _fetch_releases(session: requests.Session) -> dict:
    response = session.get(BODHI_RELEASES_URL, params={"state": "current"}, timeout=30)
    response.raise_for_status()
    return response.json()


def get_current_stable_branch(session: requests.Session | None = None) -> str:
    """Returns the current Fedora stable branch, e.g. "f44".

    Queries Bodhi for releases with state=current, keeps only entries whose
    id_prefix is exactly "FEDORA" (excluding *-CONTAINER/*-FLATPAK/*-EPEL*
    variants) and that have already been released (`released_on` is set),
    then returns the highest `version` among those.
    """
    session = session or requests.Session()
    try:
        payload = _fetch_releases(session)
    except requests.RequestException as exc:
        raise BodhiLookupError(f"Bodhi releases lookup failed: {exc}") from exc

    candidates = [
        release
        for release in payload.get("releases", [])
        if release.get("id_prefix") == "FEDORA"
        and release.get("released_on")
        and release.get("version") is not None
    ]
    if not candidates:
        raise BodhiLookupError("No current, released Fedora releases found in Bodhi response")

    newest = max(candidates, key=lambda release: int(release["version"]))
    return f"f{newest['version']}"
