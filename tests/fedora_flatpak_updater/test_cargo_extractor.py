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
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as _tar:
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
    with zipfile.ZipFile(zip_buffer, mode="w") as _zip_file:
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
def test_run_cargo_generator(tmp_path):
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

    with requests.Session() as session:
        with patch("subprocess.run") as mock_run:
            def side_effect(cmd, *args, **kwargs):
                Path(cmd[3]).write_bytes(b"[mock generator output]")
                return MagicMock(returncode=0)
            mock_run.side_effect = side_effect
            
            output_file = tmp_path / "mock-sources.json"
            run_cargo_generator(session, b"[mock cargo lock]", output_file)
            
            # Assert subprocess was called
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "flatpak-cargo-generator.py" in args[1]
            assert "-o" in args
            
            assert output_file.exists()
            assert output_file.read_bytes() == b"[mock generator output]"


@responses.activate
def test_run_cargo_generator_timeout(tmp_path):
    from unittest.mock import patch
    import subprocess
    from fedora_flatpak_updater.cargo_extractor import run_cargo_generator

    # Mock the flatpak-cargo-generator.py script download
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/cargo/flatpak-cargo-generator.py",
        body=b"print('mock generator script')",
        status=200
    )

    with requests.Session() as session:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["mock"], timeout=60)
            
            output_file = tmp_path / "mock-sources.json"
            with pytest.raises(CargoLockExtractionError, match="flatpak-cargo-generator.py timed out after 60 seconds"):
                run_cargo_generator(session, b"[mock cargo lock]", output_file)


@responses.activate
def test_download_and_extract_cargo_lock_query_params_and_dynamic_top_level():
    # Mock the PyPI JSON response with query params in the URL and non-standard casing
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/bcrypt/4.3.0/json",
        json={
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.TAR.GZ?some_param=value&other=1"
                }
            ]
        },
        status=200
    )

    # Create an in-memory tarball containing some-custom-top-level/src/_bcrypt/Cargo.lock
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        content = b"[package]\nname = \"bcrypt-custom\"\n"
        tarinfo = tarfile.TarInfo(name="some-custom-top-level/src/_bcrypt/Cargo.lock")
        tarinfo.size = len(content)
        tar.addfile(tarinfo, io.BytesIO(content))
    tar_buffer.seek(0)

    responses.add(
        responses.GET,
        "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-4.3.0.TAR.GZ",
        body=tar_buffer.read(),
        status=200
    )

    with requests.Session() as session:
        lockfile_bytes = download_and_extract_cargo_lock(
            session, "bcrypt", "4.3.0", "src/_bcrypt/Cargo.lock"
        )
        assert lockfile_bytes == b"[package]\nname = \"bcrypt-custom\"\n"


def test_matches_cargo_lock_path():
    from fedora_flatpak_updater.cargo_extractor import _matches_cargo_lock_path

    # Standard sdist: root folder + top-level Cargo.lock
    assert _matches_cargo_lock_path("bcrypt-4.3.0/Cargo.lock", "Cargo.lock") is True

    # Standard sdist: root folder + nested Cargo.lock
    assert _matches_cargo_lock_path("bcrypt-4.3.0/src/_bcrypt/Cargo.lock", "src/_bcrypt/Cargo.lock") is True

    # Direct match without top-level wrapper directory
    assert _matches_cargo_lock_path("Cargo.lock", "Cargo.lock") is True

    # Mismatch cases
    assert _matches_cargo_lock_path("bcrypt-4.3.0/other/Cargo.lock", "src/Cargo.lock") is False
    assert _matches_cargo_lock_path("", "Cargo.lock") is False




