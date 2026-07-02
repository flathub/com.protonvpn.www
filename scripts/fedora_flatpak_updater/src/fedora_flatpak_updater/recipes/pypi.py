from __future__ import annotations

from dataclasses import dataclass

import requests

PYPI_BASE = "https://pypi.org/pypi"


class PypiVersionNotFoundError(RuntimeError):
    """Raised when a specific pypi_name==version has no usable distribution."""


@dataclass(frozen=True)
class PypiSource:
    url: str
    sha256: str
    only_arches: tuple[str, ...] = ()


def fetch_release_files(pypi_name: str, version: str, session: requests.Session | None = None) -> list[dict]:
    own_session = session is None
    if session is None:
        session = requests.Session()
    try:
        url = f"{PYPI_BASE}/{pypi_name}/{version}/json"
        response = session.get(url, timeout=30)
        if response.status_code == 404:
            raise PypiVersionNotFoundError(f"{pypi_name}=={version} not found on PyPI")
        response.raise_for_status()
        return response.json()["urls"]
    finally:
        if own_session:
            session.close()


def resolve_wheel(pypi_name: str, version: str, session: requests.Session | None = None) -> PypiSource:
    for file_info in fetch_release_files(pypi_name, version, session):
        if file_info["packagetype"] == "bdist_wheel":
            return PypiSource(url=file_info["url"], sha256=file_info["digests"]["sha256"])
    raise PypiVersionNotFoundError(f"No wheel for {pypi_name}=={version}")


def resolve_sdist(pypi_name: str, version: str, session: requests.Session | None = None) -> PypiSource:
    for file_info in fetch_release_files(pypi_name, version, session):
        if file_info["packagetype"] == "sdist":
            return PypiSource(url=file_info["url"], sha256=file_info["digests"]["sha256"])
    raise PypiVersionNotFoundError(f"No sdist for {pypi_name}=={version}")


def resolve(
    pypi_name: str,
    version: str,
    *,
    prefer: str = "wheel",
    session: requests.Session | None = None,
) -> PypiSource:
    primary, fallback = (resolve_wheel, resolve_sdist) if prefer == "wheel" else (resolve_sdist, resolve_wheel)
    try:
        return primary(pypi_name, version, session)
    except PypiVersionNotFoundError:
        return fallback(pypi_name, version, session)


def resolve_multi_wheel(
    pypi_name: str,
    version: str,
    wheel_arches: tuple[str, ...],
    session: requests.Session | None = None,
) -> dict[str, PypiSource]:
    """The `cryptography` case: one manylinux wheel per architecture."""
    files = fetch_release_files(pypi_name, version, session)
    result: dict[str, PypiSource] = {}
    for arch in wheel_arches:
        for file_info in files:
            if file_info["packagetype"] != "bdist_wheel":
                continue
            filename = file_info["filename"]
            if arch in filename and "manylinux" in filename:
                result[arch] = PypiSource(
                    url=file_info["url"],
                    sha256=file_info["digests"]["sha256"],
                    only_arches=(arch,),
                )
                break
        else:
            raise PypiVersionNotFoundError(f"No wheel for {pypi_name}=={version} arch={arch}")
    return result
