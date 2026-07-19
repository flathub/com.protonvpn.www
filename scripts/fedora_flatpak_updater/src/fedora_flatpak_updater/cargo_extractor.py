from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

class CargoLockExtractionError(RuntimeError):
    """Raised when sdist download or lockfile extraction fails."""

def download_and_extract_cargo_lock(
    session: requests.Session,
    pypi_name: str,
    version: str,
    cargo_lock_path: str,
) -> bytes:
    pypi_url = f"https://pypi.org/pypi/{pypi_name}/{version}/json"
    try:
        resp = session.get(pypi_url, timeout=30)
        resp.raise_for_status()
        metadata = resp.json()
    except requests.RequestException as exc:
        raise CargoLockExtractionError(f"Failed to fetch PyPI metadata for {pypi_name}=={version}: {exc}") from exc

    sdist_url = None
    for url_info in metadata.get("urls", []):
        if url_info.get("packagetype") == "sdist":
            sdist_url = url_info.get("url")
            break

    if not sdist_url:
        raise CargoLockExtractionError(f"No source distribution (sdist) found for {pypi_name}=={version}")

    try:
        sdist_resp = session.get(sdist_url, timeout=30)
        sdist_resp.raise_for_status()
        archive_bytes = sdist_resp.content
    except requests.RequestException as exc:
        raise CargoLockExtractionError(f"Failed to download sdist from {sdist_url}: {exc}") from exc

    parsed_url = urlparse(sdist_url)
    url_path_lower = parsed_url.path.lower()
    filename = Path(parsed_url.path).name
    
    # Handle tar.gz / tar.bz2 / tar.xz / zip
    if url_path_lower.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tar:
                members = tar.getmembers()
                if not members:
                    raise CargoLockExtractionError("Empty sdist archive")

                for member in members:
                    if _matches_cargo_lock_path(member.name, cargo_lock_path):
                        f = tar.extractfile(member)
                        if f is not None:
                            return f.read()
        except Exception as exc:
            if isinstance(exc, CargoLockExtractionError):
                raise
            raise CargoLockExtractionError(f"Error extracting tarball: {exc}") from exc
    elif url_path_lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_ref:
                names = zip_ref.namelist()
                if not names:
                    raise CargoLockExtractionError("Empty zip archive")

                for name in names:
                    if _matches_cargo_lock_path(name, cargo_lock_path):
                        return zip_ref.read(name)
        except Exception as exc:
            if isinstance(exc, CargoLockExtractionError):
                raise
            raise CargoLockExtractionError(f"Error extracting zip: {exc}") from exc


    raise CargoLockExtractionError(f"Could not find lockfile at {cargo_lock_path} inside sdist archive {filename}")


def _matches_cargo_lock_path(member_name: str, target_rel_path: str) -> bool:
    """Matches an archive member path against the target relative lockfile path.

    Strips the top-level sdist directory prefix if present (e.g.
    'bcrypt-4.3.0/src/_bcrypt/Cargo.lock' -> 'src/_bcrypt/Cargo.lock'),
    supporting arbitrary subdirectory depths. Also matches direct paths if no
    top-level wrapper directory is present.
    """
    parts = [p for p in member_name.split("/") if p]
    if not parts:
        return False
    if "/".join(parts) == target_rel_path:
        return True
    if len(parts) > 1 and "/".join(parts[1:]) == target_rel_path:
        return True
    return False


GENERATOR_URL = "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/cargo/flatpak-cargo-generator.py"


def run_cargo_generator(
    session: requests.Session,
    cargo_lock_content: bytes,
    output_sources_file: Path,
) -> None:
    # Download flatpak-cargo-generator.py
    try:
        resp = session.get(GENERATOR_URL, timeout=30)
        resp.raise_for_status()
        generator_script = resp.content
    except requests.RequestException as exc:
        raise CargoLockExtractionError(f"Failed to download flatpak-cargo-generator.py: {exc}") from exc

    with tempfile.TemporaryDirectory() as tempdir:
        script_path = Path(tempdir) / "flatpak-cargo-generator.py"
        script_path.write_bytes(generator_script)
        
        lock_path = Path(tempdir) / "Cargo.lock"
        lock_path.write_bytes(cargo_lock_content)

        temp_output_path = Path(tempdir) / "sources.json"

        cmd = [
            sys.executable,
            str(script_path),
            "-o",
            str(temp_output_path),
            str(lock_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            stdout = getattr(exc, "stdout", "")
            stderr = getattr(exc, "stderr", "")
            if isinstance(exc, subprocess.TimeoutExpired):
                raise CargoLockExtractionError(
                    f"flatpak-cargo-generator.py timed out after {exc.timeout} seconds\n"
                    f"stdout: {stdout}\n"
                    f"stderr: {stderr}"
                ) from exc
            raise CargoLockExtractionError(
                f"flatpak-cargo-generator.py failed with exit code {exc.returncode}\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            ) from exc

        # Copy the temporary output file to the final destination atomically
        local_temp_file = output_sources_file.parent / f".tmp_{output_sources_file.name}"
        try:
            shutil.copy2(temp_output_path, local_temp_file)
            os.replace(local_temp_file, output_sources_file)
        except Exception as exc:
            if local_temp_file.exists():
                local_temp_file.unlink()
            raise exc
