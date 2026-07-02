from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
import requests
from tabulate import tabulate

from .fedora_release import BodhiLookupError, get_current_stable_branch
from .manifest_patcher import ManifestForest, apply_archive, apply_git, apply_pypi
from .mapping_loader import load_mapping
from .mdapi_client import MdapiClient, MdapiTransientError, PackageNotFoundError
from .models import ModuleSpec, RecipeKind
from .recipes import archive as archive_recipe
from .recipes import git as git_recipe
from .recipes import pypi as pypi_recipe
from .recipes.archive import ArchiveResolutionError
from .recipes.git import GitTagNotFoundError
from .recipes.pypi import PypiVersionNotFoundError


@dataclass
class Row:
    module_name: str
    status: str  # "updated" | "unchanged" | "skipped"
    detail: str


def _infer_prefer(url: str, fallback: str) -> str:
    if url.endswith(".whl"):
        return "wheel"
    if url.endswith((".tar.gz", ".tar.bz2", ".zip")):
        return "sdist"
    return fallback


def _resolve_pypi_block(
    block: dict,
    spec: ModuleSpec,
    fedora_version: str,
    session: requests.Session,
    multi_wheel_cache: dict,
):
    if spec.recipe == RecipeKind.PYPI_MULTI_WHEEL and block.get("only-arches"):
        arch = block["only-arches"][0]
        cache_key = (spec.pypi_name, fedora_version)
        if cache_key not in multi_wheel_cache:
            multi_wheel_cache[cache_key] = pypi_recipe.resolve_multi_wheel(
                spec.pypi_name, fedora_version, spec.wheel_arches, session=session
            )
        return multi_wheel_cache[cache_key].get(arch)

    prefer = _infer_prefer(block.get("url", ""), spec.prefer)
    return pypi_recipe.resolve(spec.pypi_name, fedora_version, prefer=prefer, session=session)


def run(
    mapping_path: Path,
    manifest_root: Path,
    *,
    dry_run: bool = False,
    only: list[str] | None = None,
) -> list[Row]:
    with requests.Session() as session:
        branch = get_current_stable_branch(session=session)
        specs = load_mapping(mapping_path)
        if only:
            specs = [spec for spec in specs if spec.name in only]

        forest = ManifestForest(manifest_root)
        mdapi = MdapiClient(branch, session=session)
        multi_wheel_cache: dict = {}
        rows: list[Row] = []

        for spec in specs:
            try:
                fedora_version = mdapi.get_version(spec.fedora_package)
            except (PackageNotFoundError, MdapiTransientError) as exc:
                rows.append(Row(spec.name, "skipped", str(exc)))
                continue

            try:
                if spec.recipe in (RecipeKind.PYPI, RecipeKind.PYPI_MULTI_WHEEL):
                    report = apply_pypi(
                        forest,
                        spec,
                        lambda block: _resolve_pypi_block(block, spec, fedora_version, session, multi_wheel_cache),
                    )
                elif spec.recipe == RecipeKind.ARCHIVE:
                    source = archive_recipe.resolve(spec.url_template, fedora_version, session=session)
                    report = apply_archive(forest, spec, source)
                elif spec.recipe == RecipeKind.GIT:
                    source = git_recipe.resolve(
                        repo_url=spec.repo_url,
                        version=fedora_version,
                        tag_template=spec.tag_template,
                        tag_pattern=spec.tag_pattern,
                    )
                    report = apply_git(forest, spec, source)
                else:  # pragma: no cover - RecipeKind is exhaustive
                    rows.append(Row(spec.name, "skipped", f"unknown recipe {spec.recipe}"))
                    continue
            except (PypiVersionNotFoundError, ArchiveResolutionError, GitTagNotFoundError) as exc:
                rows.append(Row(spec.name, "skipped", str(exc)))
                continue

            if report.blocks_touched == 0:
                rows.append(Row(spec.name, "unchanged", f"no matching source blocks found for {fedora_version}"))
            else:
                detail = f"-> {fedora_version} ({report.blocks_touched} block(s))"
                if spec.manual_followup:
                    detail += f" [manual follow-up: {spec.manual_followup}]"
                rows.append(Row(spec.name, "updated", detail))

        if not dry_run and any(row.status == "updated" for row in rows):
            forest.save()

        return rows


def format_summary(rows: list[Row]) -> str:
    table = [[row.module_name, row.status, row.detail] for row in rows]
    return tabulate(table, headers=["Module", "Status", "Detail"], tablefmt="github")


@click.command()
@click.option(
    "--mapping",
    type=click.Path(path_type=Path),
    default=Path(".fedora-tracked-modules.yaml"),
    show_default=True,
    help="Path to the tracked-modules mapping file.",
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("com.protonvpn.www.yml"),
    show_default=True,
    help="Path to the root Flatpak manifest.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Resolve and report without writing files.")
@click.option("--only", multiple=True, help="Limit to specific tracked module name(s). Repeatable.")
def main(mapping: Path, manifest: Path, dry_run: bool, only: tuple[str, ...]) -> None:
    """Pin Flatpak manifest dependencies to Fedora-stable versions."""
    try:
        rows = run(mapping, manifest, dry_run=dry_run, only=list(only) or None)
    except BodhiLookupError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1)

    click.echo(format_summary(rows))
    if not any(row.status == "updated" for row in rows):
        click.echo("\nNothing to update.")


if __name__ == "__main__":
    main()
