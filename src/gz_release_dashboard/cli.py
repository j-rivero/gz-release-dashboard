"""Command line entry point: ``fetch`` writes a snapshot, the rest render it."""

from __future__ import annotations

import click

from rich.console import Console

from . import __version__, config, deps, engine, ground_truth, snapshot as snap
from .collections_yaml import load_collections
from .deps.inventory import DependencyRow, dependency_rows, narrow_rows
from .http import HttpClient
from .models import FetchError, Snapshot, StatusEntry
from .render import console as console_render, html as html_render
from .sources import available_sources, create_sources


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="gz-dashboard")
def main() -> None:
    """Track Gazebo library versions across every packaging system."""


def _collections_for(source: str, collections: list) -> list:
    """The collections to hand ``source``, for one restricted to a few of them.

    Only narrows a source that config declares does not apply beyond certain
    collections; every other source is handed the whole list unchanged. It is
    the query matrix this saves: the distributions to ask a Debian repository
    for are derived from the collections it is given, so telling the ROS gz
    import that it is fortress business keeps it from downloading noble and
    resolute indexes that cannot hold anything for it.
    """
    if source not in config.COLLECTION_SOURCES_ONLY:
        return collections
    return [c for c in collections if config.source_applies(source, c.name)]


def _collect(
    sources: tuple[str, ...],
    collection_filter: tuple[str, ...],
    cache_dir: str | None,
):
    """Fetch the ground truth and every selected source into a snapshot."""
    http = HttpClient(cache_dir=cache_dir)
    collections = load_collections(http)
    if collection_filter:
        wanted = set(collection_filter)
        collections = [c for c in collections if c.name in wanted]
        if not collections:
            raise click.ClickException(
                f"no collection matched {', '.join(sorted(wanted))}"
            )

    instances = create_sources(list(sources) or None, http)
    snapshot = snap.new_snapshot([s.name for s in instances])
    snapshot.collections = collections

    click.echo(f"ground truth: {len(collections)} collections", err=True)
    entries, errors = ground_truth.build_ground_truth(collections)
    snapshot.ground_truth = entries
    snapshot.errors.extend(errors)

    failures = 0
    for source in instances:
        click.echo(f"fetching {source.name}...", err=True)
        try:
            wanted = _collections_for(source.name, collections)
            snapshot.records.extend(source.fetch(wanted))
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the run
            failures += 1
            snapshot.errors.append(FetchError(source.name, f"{type(exc).__name__}: {exc}"))
            click.echo(f"  {source.name} failed: {exc}", err=True)
    if instances and failures == len(instances):
        raise click.ClickException("every source failed; refusing to write a snapshot")

    # After the sources, so the HTTP memo serves the readers the indexes,
    # formulas and anaconda documents already downloaded. A reader follows its
    # library source, so --source selects both. A failing reader is not a
    # failing source: a snapshot without dependencies is still worth writing.
    for reader in deps.create_readers(list(sources) or None, http):
        click.echo(f"reading {reader.system} dependencies...", err=True)
        try:
            snapshot.dependencies.extend(reader.read(collections))
        except Exception as exc:  # noqa: BLE001 - one bad reader must not stop the run
            snapshot.errors.append(
                FetchError(f"deps:{reader.system}", f"{type(exc).__name__}: {exc}")
            )
            click.echo(f"  {reader.system} dependencies failed: {exc}", err=True)
        snapshot.errors.extend(reader.errors)
    return snapshot


@main.command()
@click.option(
    "-o", "--output", default="snapshot.json", show_default=True,
    type=click.Path(dir_okay=False), help="Where to write the snapshot.",
)
@click.option(
    "--source", "sources", multiple=True, type=click.Choice(available_sources()),
    help="Fetch only these sources (repeatable).",
)
@click.option(
    "--collection", "collections_", multiple=True,
    help="Fetch only these collections (repeatable).",
)
@click.option(
    "--cache-dir", type=click.Path(file_okay=False),
    help="Memoise HTTP bodies here; handy while iterating.",
)
def fetch(output, sources, collections_, cache_dir):
    """Query every source and write a JSON snapshot."""
    snapshot = _collect(sources, collections_, cache_dir)
    path = snap.save(snapshot, output)
    click.echo(
        f"wrote {path}: {len(snapshot.records)} records, "
        f"{len(snapshot.dependencies)} dependency records, "
        f"{len(snapshot.errors)} errors",
        err=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()


def _filtered(
    snapshot: Snapshot,
    collections_: tuple[str, ...],
    sources: tuple[str, ...],
    libs: tuple[str, ...],
) -> tuple[Snapshot, list[StatusEntry], list[DependencyRow]]:
    """Compute the statuses of the whole snapshot, then narrow what is shown.

    The narrowing has to come after the scoring, never before it. Several rules
    weigh a collection against the others -- which collection owns ROS Rolling,
    what share of a collection a platform has to carry -- so scoring a narrowed
    snapshot answers a different question: ``--collection jetty`` would make
    jetty the newest collection in existence and hand it Rolling, and the same
    view would disagree with the full dashboard about it.

    The dependency marks are settled the same way. ◇ compares build systems,
    so marking a view cut down to one of them would find nothing to compare:
    ``--source`` would take the mark away along with the columns.

    The snapshot is still narrowed afterwards, because the renderers take the
    collection order and the column list from it.
    """
    entries = engine.compute_statuses(snapshot)
    rows = dependency_rows(snapshot.dependencies)
    checks = []
    if collections_:
        wanted = set(collections_)
        snapshot.collections = [c for c in snapshot.collections if c.name in wanted]
        entries = [e for e in entries if e.collection in wanted]
        checks.append(lambda d: d.collection in wanted)
    if sources:
        keep = set(sources)
        snapshot.sources_fetched = [s for s in snapshot.sources_fetched if s in keep]
        snapshot.records = [r for r in snapshot.records if r.source in keep]
        entries = [e for e in entries if e.source in keep]
        checks.append(lambda d: config.DEPENDENCY_SYSTEMS.get(d.system) in keep)
    if libs:
        names = set(libs)
        for collection in snapshot.collections:
            collection.libraries = [l for l in collection.libraries if l.name in names]
        entries = [e for e in entries if e.library in names]
        checks.append(lambda d: d.library in names)
    if checks:
        def kept(record) -> bool:
            return all(check(record) for check in checks)

        snapshot.dependencies = [d for d in snapshot.dependencies if kept(d)]
        rows = narrow_rows(rows, kept)
    return snapshot, entries, rows


_filter_options = [
    click.option("--collection", "collections_", multiple=True,
                 help="Show only these collections (repeatable)."),
    click.option("--source", "sources", multiple=True,
                 type=click.Choice(available_sources()),
                 help="Show only these sources (repeatable)."),
    click.option("--lib", "libs", multiple=True,
                 help="Show only these libraries (repeatable)."),
]


def add_filter_options(command):
    for option in reversed(_filter_options):
        command = option(command)
    return command


@main.command(name="console")
@click.argument("snapshot_path", metavar="[SNAPSHOT]", default="snapshot.json",
                type=click.Path(exists=True, dir_okay=False))
@add_filter_options
@click.option("--problems-only", is_flag=True, help="Print only the problems panel.")
@click.option("--verbose", is_flag=True, help="Add a per-platform detail table.")
@click.option("--fail-on-problems", is_flag=True,
              help="Exit non-zero when anything is behind or missing.")
def console_cmd(snapshot_path, collections_, sources, libs, problems_only, verbose,
                fail_on_problems):
    """Render a snapshot as a colourful terminal dashboard."""
    snapshot, entries, rows = _filtered(
        snap.load(snapshot_path), collections_, sources, libs
    )
    count = console_render.render(
        snapshot, entries, Console(), verbose=verbose, problems_only=problems_only,
        rows=rows,
    )
    if fail_on_problems and count:
        raise SystemExit(1)


@main.command(name="html")
@click.argument("snapshot_path", metavar="[SNAPSHOT]", default="snapshot.json",
                type=click.Path(exists=True, dir_okay=False))
@add_filter_options
@click.option("-o", "--output", "out_dir", default="public", show_default=True,
              type=click.Path(file_okay=False),
              help="Directory to write index.html and snapshot.json into.")
def html_cmd(snapshot_path, collections_, sources, libs, out_dir):
    """Render a snapshot as a static page for GitHub Pages."""
    snapshot, entries, rows = _filtered(
        snap.load(snapshot_path), collections_, sources, libs
    )
    path = html_render.write(snapshot, entries, out_dir, rows)
    click.echo(f"wrote {path}", err=True)


@main.command(name="all")
@click.option("-o", "--output", "out_dir", default="public", show_default=True,
              type=click.Path(file_okay=False), help="Directory to publish into.")
@click.option("--source", "sources", multiple=True, type=click.Choice(available_sources()),
              help="Fetch only these sources (repeatable).")
@click.option("--collection", "collections_", multiple=True,
              help="Fetch only these collections (repeatable).")
@click.option("--cache-dir", type=click.Path(file_okay=False),
              help="Memoise HTTP bodies here; handy while iterating.")
@click.option("--fail-on-problems", is_flag=True,
              help="Exit non-zero when anything is behind or missing.")
def all_cmd(out_dir, sources, collections_, cache_dir, fail_on_problems):
    """Fetch, report the problems on stderr, and publish the page."""
    snapshot = _collect(sources, collections_, cache_dir)
    entries = engine.compute_statuses(snapshot)
    count = console_render.render(
        snapshot, entries, Console(stderr=True), problems_only=True
    )
    path = html_render.write(snapshot, entries, out_dir)
    click.echo(f"wrote {path}", err=True)
    if fail_on_problems and count:
        raise SystemExit(1)
