from __future__ import annotations

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt

MDAPI_BASE = "https://mdapi.fedoraproject.org"


class PackageNotFoundError(Exception):
    def __init__(self, package_name: str, branch: str):
        super().__init__(f"{package_name} not found in Fedora {branch}")
        self.package_name = package_name
        self.branch = branch


class MdapiTransientError(RuntimeError):
    """Raised when MDAPI returns a server error even after one retry."""


class MdapiClient:
    """Thin client for mdapi.fedoraproject.org/<branch>/pkg/<name>, with a
    per-instance in-memory cache."""

    def __init__(self, branch: str, session: requests.Session | None = None):
        self.branch = branch
        self.session = session or requests.Session()
        self._cache: dict[str, str] = {}

    def get_version(self, package_name: str) -> str:
        if package_name in self._cache:
            return self._cache[package_name]

        url = f"{MDAPI_BASE}/{self.branch}/pkg/{package_name}"
        response = self._get_with_retry(url)

        if response.status_code in (400, 404):
            raise PackageNotFoundError(package_name, self.branch)
        response.raise_for_status()

        try:
            version = response.json()["version"]
        except (ValueError, KeyError) as exc:
            raise MdapiTransientError(f"Invalid JSON response from MDAPI: {exc}") from exc
        self._cache[package_name] = version
        return version

    @retry(
        retry=retry_if_exception_type(MdapiTransientError),
        stop=stop_after_attempt(2),  # 1 try + 1 retry
        reraise=True,
    )
    def _get_with_retry(self, url: str) -> requests.Response:
        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException as exc:
            raise MdapiTransientError(f"{url} request failed: {exc}") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise MdapiTransientError(f"{url} returned {response.status_code}")
        return response
