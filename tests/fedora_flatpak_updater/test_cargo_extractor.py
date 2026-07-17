import io
import tarfile
import zipfile
import pytest
import responses
import requests
from fedora_flatpak_updater.cargo_extractor import (
    download_and_extract_cargo_lock,
    CargoLockExtractionError,
)

@responses.activate
def test_download_and_extract_cargo_lock_tar_gz():
    # Mock the PyPI JSON response
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz"
                }
            ]
        },
        status=200
    )

    # Create an in-memory tarball containing src/_bcrypt/Cargo.lock
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        content = b"[package]\nname = \"bcrypt\"\n"
        tarinfo = tarfile.TarInfo(name="bcrypt-4.3.0/src/_bcrypt/Cargo.lock")
        tarinfo.size = len(content)
        tar.addfile(tarinfo, io.BytesIO(content))
    tar_buffer.seek(0)

    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz",
        body=tar_buffer.read(),
        status=200
    )

    with requests.Session() as session:
        lockfile_bytes = download_and_extract_cargo_lock(
            session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
        )
        assert lockfile_bytes == b"[package]\nname = \"bcrypt\"\n"

@responses.activate
def test_download_and_extract_cargo_lock_zip():
    # Mock the PyPI JSON response
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.zip"
                }
            ]
        },
        status=200
    )

    # Create an in-memory zip containing src/_bcrypt/Cargo.lock
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w") as zip_file:
        content = b"[package]\nname = \"bcrypt\"\n"
        zip_file.writestr("bcrypt-4.3.0/src/_bcrypt/Cargo.lock", content)
    zip_buffer.seek(0)

    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.zip",
        body=zip_buffer.read(),
        status=200
    )

    with requests.Session() as session:
        lockfile_bytes = download_and_extract_cargo_lock(
            session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
        )
        assert lockfile_bytes == b"[package]\nname = \"bcrypt\"\n"

@responses.activate
def test_pypi_metadata_failure():
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        status=500
    )

    with requests.Session() as session:
        with pytest.raises(CargoLockExtractionError, match="Failed to fetch PyPI metadata"):
            download_and_extract_cargo_lock(
                session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
            )

@responses.activate
def test_no_sdist_found():
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "bdist_wheel",
                    "url": "https://files.pythonhosted.org/packages/bcrypt-4.3.0-cp39-cp39-manylinux.whl"
                }
            ]
        },
        status=200
    )

    with requests.Session() as session:
        with pytest.raises(CargoLockExtractionError, match="No source distribution"):
            download_and_extract_cargo_lock(
                session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
            )

@responses.activate
def test_sdist_download_failure():
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz"
                }
            ]
        },
        status=200
    )
    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz",
        status=404
    )

    with requests.Session() as session:
        with pytest.raises(CargoLockExtractionError, match="Failed to download sdist"):
            download_and_extract_cargo_lock(
                session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
            )

@responses.activate
def test_empty_tarball():
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz"
                }
            ]
        },
        status=200
    )

    # Empty tarball
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        pass
    tar_buffer.seek(0)

    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz",
        body=tar_buffer.read(),
        status=200
    )

    with requests.Session() as session:
        with pytest.raises(CargoLockExtractionError, match="Empty sdist archive|Error extracting tarball"):
            download_and_extract_cargo_lock(
                session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
            )

@responses.activate
def test_empty_zip():
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.zip"
                }
            ]
        },
        status=200
    )

    # Empty zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w") as zip_file:
        pass
    zip_buffer.seek(0)

    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.zip",
        body=zip_buffer.read(),
        status=200
    )

    with requests.Session() as session:
        with pytest.raises(CargoLockExtractionError, match="Empty zip archive|Error extracting zip"):
            download_and_extract_cargo_lock(
                session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
            )

@responses.activate
def test_lockfile_missing_in_archive():
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz"
                }
            ]
        },
        status=200
    )

    # Create tarball without the lockfile
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        content = b"some other file content"
        tarinfo = tarfile.TarInfo(name="bcrypt-4.3.0/README.md")
        tarinfo.size = len(content)
        tar.addfile(tarinfo, io.BytesIO(content))
    tar_buffer.seek(0)

    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.tar.gz",
        body=tar_buffer.read(),
        status=200
    )

    with requests.Session() as session:
        with pytest.raises(CargoLockExtractionError, match="Could not find lockfile"):
            download_and_extract_cargo_lock(
                session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
            )


@responses.activate
def test_run_cargo_generator():
    from unittest.mock import patch, MagicMock
    from pathlib import Path
    from fedora_flatpak_updater.cargo_extractor import run_cargo_generator

    # Mock the flatpak-cargo-generator.py script download
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/cargo/flatpak-cargo-generator.py",
        body=b"print('mock generator script')",
        status=200
    )

    import requests
    with requests.Session() as session:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            run_cargo_generator(session, b"[mock cargo lock]", Path("mock-sources.json"))
            
            # Assert subprocess was called
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "flatpak-cargo-generator.py" in args[1]
            assert "-o" in args
            assert "mock-sources.json" in args

