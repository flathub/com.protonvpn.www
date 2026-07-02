from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from string import Template

import requests


class ArchiveResolutionError(RuntimeError):
    """Raised when a rendered archive URL cannot be fetched."""


@dataclass(frozen=True)
class ArchiveSource:
    url: str
    sha256: str


def render_url(url_template: str, version: str) -> str:
    return Template(url_template).substitute(version=version)


def resolve(url_template: str, version: str, session: requests.Session | None = None) -> ArchiveSource:
    own_session = session is None
    if session is None:
        session = requests.Session()
    try:
        url = render_url(url_template, version)
        for attempt in range(3):
            response = None
            try:
                response = session.get(url, timeout=60, stream=True)
                if response.status_code == 404:
                    raise ArchiveResolutionError(f"{url} returned 404")
                response.raise_for_status()

                digest = hashlib.sha256()
                for chunk in response.iter_content(chunk_size=65536):
                    digest.update(chunk)
                return ArchiveSource(url=url, sha256=digest.hexdigest())
            except (requests.RequestException, ArchiveResolutionError) as exc:
                if response is not None:
                    response.close()
                if isinstance(exc, ArchiveResolutionError) or attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
    finally:
        if own_session:
            session.close()
