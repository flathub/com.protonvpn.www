import tempfile
from pathlib import Path

from scripts.generate_proton_platform_sources import (
    get_manifest_tag,
    get_protun_version,
    parse_proton_crates,
    rewrite_cargo_sources,
)

SAMPLE_CARGO_LOCK = """
version = 3

[[package]]
name = "serde"
version = "1.0.228"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "deadbeef"

[[package]]
name = "proton-boringtun"
version = "3.0.0"
source = "sparse+https://rust-registry.proton.me/index/"
checksum = "d6cbef9a3ddc5f97501607f1a689c459a1894069745b4cede7c519b71bb64434"

[[package]]
name = "protun"
version = "2.2.1"
dependencies = [
 "derive_more",
]

[[package]]
name = "pvpnclient"
version = "3.0.3"
source = "sparse+https://rust-registry.proton.me/index/"
checksum = "3c14ef052727e0204ec5e80cf8df50786db38a83b6a6557a188b78a4c264f380"
"""

SAMPLE_MANIFEST = """
modules:
  - name: python-proton-vpn-api-core
    sources:
      - type: git
        url: https://github.com/ProtonVPN/python-proton-vpn-api-core
        tag: v5.6.10
        commit: f1d13b71c506bbd5f47351a9e4392572e21d0169
"""


def test_parse_proton_crates() -> None:
    crates = parse_proton_crates(SAMPLE_CARGO_LOCK)
    assert crates == {("proton-boringtun", "3.0.0"), ("pvpnclient", "3.0.3")}


def test_get_protun_version() -> None:
    version = get_protun_version(SAMPLE_CARGO_LOCK)
    assert version == "2.2.1"


def test_get_manifest_tag() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(SAMPLE_MANIFEST)
        temp_path = Path(f.name)

    try:
        tag = get_manifest_tag(temp_path)
        assert tag == "v5.6.10"
    finally:
        temp_path.unlink()


def test_rewrite_cargo_sources() -> None:
    raw_sources = [
        {
            "type": "archive",
            "url": "https://static.crates.io/crates/serde/serde-1.0.228.crate",
            "sha256": "deadbeef",
            "dest": "cargo/vendor/serde-1.0.228",
        },
        {
            "type": "archive",
            "url": "https://static.crates.io/crates/proton-boringtun/proton-boringtun-3.0.0.crate",
            "sha256": "d6cbef9a3ddc5f97501607f1a689c459a1894069745b4cede7c519b71bb64434",
            "dest": "cargo/vendor/proton-boringtun-3.0.0",
        },
        {
            "type": "inline",
            "contents": "[source.crates-io]\nreplace-with = 'vendored-sources'",
            "dest": "cargo",
            "dest-filename": "config",
        },
    ]

    proton_crates = {("proton-boringtun", "3.0.0")}
    rewritten = rewrite_cargo_sources(raw_sources, proton_crates)

    assert len(rewritten) == 3
    # Standard crate is untouched
    assert rewritten[0]["url"] == "https://static.crates.io/crates/serde/serde-1.0.228.crate"
    # Proton crate URL is rewritten
    assert rewritten[1]["url"] == "https://rust-registry.proton.me/downloads/proton-boringtun@3.0.0.crate"
    # Config entry uses config.toml and contains sparse registry setup
    assert rewritten[2]["dest-filename"] == "config.toml"
    assert "https://rust-registry.proton.me/index/" in rewritten[2]["contents"]
