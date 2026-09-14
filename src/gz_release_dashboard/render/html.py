"""A single self-contained HTML page, ready to publish on GitHub Pages."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader

from ..deps.inventory import DependencyCell, DependencyRow, dependency_rows
from ..engine import SEVERITY
from ..models import DependencyRecord, Snapshot, Status, StatusEntry
from ..snapshot import to_dict
from . import (
    DIVERGE_GLYPH,
    DIVERGE_LABEL,
    STATUS_CSS,
    STATUS_GLYPHS,
    STATUS_LABELS,
    WARN_GLYPH,
    WARN_LABEL,
    aggregate_cell,
    column_order,
    dependency_columns,
    dependency_label,
    group_problems,
    group_cells,
    source_label,
)


def _environment() -> Environment:
    return Environment(
        loader=PackageLoader("gz_release_dashboard.render", "templates"),
        # Unconditional, not select_autoescape: the template is named
        # dashboard.html.j2, whose extension is .j2, so extension sniffing
        # would quietly leave escaping off.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _detail(entry: StatusEntry) -> dict:
    return {
        "platform": entry.platform,
        "arch": entry.arch,
        "glyph": STATUS_GLYPHS[entry.status],
        "css": STATUS_CSS[entry.status],
        "label": STATUS_LABELS[entry.status],
        "found": entry.found_version,
        "expected": entry.expected_version,
    }


def _column_views(columns: list[tuple[str, str]]) -> list[dict]:
    return [
        {"source": source_label(source), "channel": channel or "(all)"}
        for source, channel in columns
    ]


def _cell_view(entries: list[StatusEntry]) -> dict | None:
    cell = aggregate_cell(entries)
    if cell is None:
        return None
    ordered = sorted(
        entries, key=lambda e: (-SEVERITY[e.status], e.platform, e.arch)
    )
    return {
        "css": STATUS_CSS[cell.status],
        "glyph": cell.glyph,
        "label": STATUS_LABELS[cell.status],
        "version": cell.version,
        "expected": cell.expected if cell.status is Status.BEHIND else None,
        "mixed": cell.mixed,
        "worst_count": cell.worst_count,
        "total": cell.total,
        # A cell covering a single platform says everything already.
        "details": [_detail(e) for e in ordered] if len(entries) > 1 else [],
    }


def _dependency_detail(record: DependencyRecord) -> dict:
    version = record.version or record.label or "?"
    if record.system == "conda" and record.version:
        # A conda-forge pin is a range; its floor is what the gz package was
        # built against, not a package anyone installed.
        version = f"built against {record.version}"
    return {
        "platform": record.platform,
        "version": version,
        "declared": record.declared,
        "library": f"{record.library}{record.major}",
        "origin": record.origin,
    }


def _dependency_cell_view(cell: DependencyCell | None) -> dict | None:
    if cell is None:
        return None
    ordered = sorted(cell.records, key=lambda r: (r.platform, r.library, r.declared))
    return {
        "text": cell.text,
        "warn": cell.warn,
        # Always expandable, even for one record: the summary shows a version,
        # never the name that was declared or where it came from.
        "details": [_dependency_detail(record) for record in ordered],
    }


def _dependency_rows_view(rows: list[DependencyRow], systems: list[str]) -> list[dict]:
    return [
        {
            "dependency": row.dependency,
            "diverges": row.diverges,
            "cells": [_dependency_cell_view(row.cells.get(system)) for system in systems],
        }
        for row in rows
        if any(system in row.cells for system in systems)
    ]


def _divergence(rows: list[DependencyRow]) -> list[dict]:
    """The ⚠ cells. A ◇ row is not listed: the tables already show it."""
    return [
        {
            "collection": row.collection,
            "dependency": row.dependency,
            "system": dependency_label(system),
            "range": cell.text,
            "lowest": cell.lowest_platforms,
        }
        for row in rows
        for system, cell in sorted(row.cells.items())
        if cell.warn
    ]


def build_view(
    snapshot: Snapshot,
    entries: list[StatusEntry],
    rows: list[DependencyRow] | None = None,
) -> dict:
    """Everything the template needs, with no logic left in the template.

    ``rows`` are the dependency rows, marks already settled on the whole
    snapshot; without them they are worked out from this one.
    """
    if rows is None:
        rows = dependency_rows(snapshot.dependencies)
    grouped = group_cells(entries)
    collections = []
    for collection in snapshot.collections:
        libraries = sorted({(k[1], k[2]) for k in grouped if k[0] == collection.name})
        if not libraries:
            continue
        # Per collection, not once for the run: the sources that publish
        # fortress are not the ones that publish jetty.
        columns = column_order(snapshot.sources_fetched, collection.name)
        systems = dependency_columns(snapshot.sources_fetched, collection.name)
        collections.append(
            {
                "name": collection.name,
                "in_development": collection.in_development,
                "columns": _column_views(columns),
                "rows": [
                    {
                        "library": library,
                        "major": major,
                        "cells": [
                            _cell_view(
                                grouped.get(
                                    (collection.name, library, major, source, channel), []
                                )
                            )
                            for source, channel in columns
                        ],
                    }
                    for library, major in libraries
                ],
                "dependency_columns": [dependency_label(system) for system in systems],
                "dependency_rows": _dependency_rows_view(
                    [row for row in rows if row.collection == collection.name], systems
                ),
            }
        )
    found = group_problems(entries)
    legend = [
        {"glyph": glyph, "css": STATUS_CSS[status], "label": STATUS_LABELS[status]}
        for status, glyph in STATUS_GLYPHS.items()
    ]
    if rows:
        legend += [
            {"glyph": WARN_GLYPH, "css": "warn", "label": WARN_LABEL},
            {"glyph": DIVERGE_GLYPH, "css": "diverge", "label": DIVERGE_LABEL},
        ]
    return {
        "generated_at": snapshot.generated_at,
        "tool_version": snapshot.tool_version,
        "collections": collections,
        "legend": legend,
        "problems": [
            {
                "title": problem.title,
                "source": source_label(problem.source),
                "channel": problem.channel,
                "glyph": problem.glyph,
                "css": STATUS_CSS[problem.status],
                "found": problem.found,
                "expected": problem.expected,
                "places": problem.places,
            }
            for problem in found
        ],
        "problem_cells": sum(len(problem.places) for problem in found),
        "has_dependencies": bool(rows),
        "divergence": _divergence(rows),
        "warn_glyph": WARN_GLYPH,
        "warn_label": WARN_LABEL,
        "diverge_glyph": DIVERGE_GLYPH,
        "diverge_label": DIVERGE_LABEL,
        "errors": [{"source": e.source, "message": e.message} for e in snapshot.errors],
    }


def render(
    snapshot: Snapshot,
    entries: list[StatusEntry],
    rows: list[DependencyRow] | None = None,
) -> str:
    template = _environment().get_template("dashboard.html.j2")
    return template.render(**build_view(snapshot, entries, rows))


def write(
    snapshot: Snapshot,
    entries: list[StatusEntry],
    out_dir: str | Path,
    rows: list[DependencyRow] | None = None,
) -> Path:
    """Write ``index.html`` plus the snapshot it was rendered from."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "index.html"
    index.write_text(render(snapshot, entries, rows))
    (directory / "snapshot.json").write_text(
        json.dumps(to_dict(snapshot), indent=2) + "\n"
    )
    return index
