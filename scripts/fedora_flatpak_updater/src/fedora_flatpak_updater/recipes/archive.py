from __future__ import annotations

import hashlib
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
        response = session.get(url, timeout=60, stream=True)
        if response.status_code == 404:
            raise ArchiveResolutionError(f"{url} returned 404")
        response.raise_for_status()

        digest = hashlib.sha256()
        for chunk in response.iter_content(chunk_size=65536):
            digest.update(chunk)
        return ArchiveSource(url=url, sha256=digest.hexdigest())
    finally:
        if own_session:
            session.close()
