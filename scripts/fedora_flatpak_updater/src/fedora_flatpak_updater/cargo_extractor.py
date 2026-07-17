from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

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
    except Exception as exc:
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
    except Exception as exc:
        raise CargoLockExtractionError(f"Failed to download sdist from {sdist_url}: {exc}") from exc

    filename = sdist_url.split("/")[-1]
    
    # Handle tar.gz / tar.bz2 / tar.xz / zip
    if filename.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tar:
                # Prepend top-level directory dynamically
                members = tar.getmembers()
                if not members:
                    raise CargoLockExtractionError("Empty sdist archive")
                top_level = members[0].name.split("/")[0]
                target_name = f"{top_level}/{cargo_lock_path}"

                for member in members:
                    if member.name == target_name:
                        f = tar.extractfile(member)
                        if f is not None:
                            return f.read()
        except Exception as exc:
            if isinstance(exc, CargoLockExtractionError):
                raise
            raise CargoLockExtractionError(f"Error extracting tarball: {exc}") from exc
    elif filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_ref:
                names = zip_ref.namelist()
                if not names:
                    raise CargoLockExtractionError("Empty zip archive")
                top_level = names[0].split("/")[0]
                target_name = f"{top_level}/{cargo_lock_path}"

                if target_name in names:
                    return zip_ref.read(target_name)
        except Exception as exc:
            if isinstance(exc, CargoLockExtractionError):
                raise
            raise CargoLockExtractionError(f"Error extracting zip: {exc}") from exc

    raise CargoLockExtractionError(f"Could not find lockfile at {cargo_lock_path} inside sdist archive {filename}")


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
    except Exception as exc:
        raise CargoLockExtractionError(f"Failed to download flatpak-cargo-generator.py: {exc}") from exc

    with tempfile.TemporaryDirectory() as tempdir:
        script_path = Path(tempdir) / "flatpak-cargo-generator.py"
        script_path.write_bytes(generator_script)
        
        lock_path = Path(tempdir) / "Cargo.lock"
        lock_path.write_bytes(cargo_lock_content)

        cmd = [
            sys.executable,
            str(script_path),
            "-o",
            str(output_sources_file),
            str(lock_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            raise CargoLockExtractionError(
                f"flatpak-cargo-generator.py failed with exit code {exc.returncode}\n"
                f"stdout: {exc.stdout}\n"
                f"stderr: {exc.stderr}"
            ) from exc
