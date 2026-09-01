"""A single self-contained HTML page, ready to publish on GitHub Pages."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader

from ..engine import SEVERITY
from ..models import Snapshot, Status, StatusEntry
from ..snapshot import to_dict
from . import (
    STATUS_CSS,
    STATUS_GLYPHS,
    STATUS_LABELS,
    aggregate_cell,
    column_order,
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


def build_view(snapshot: Snapshot, entries: list[StatusEntry]) -> dict:
    """Everything the template needs, with no logic left in the template."""
    columns = column_order(snapshot.sources_fetched)
    grouped = group_cells(entries)
    collections = []
    for collection in snapshot.collections:
        libraries = sorted({(k[1], k[2]) for k in grouped if k[0] == collection.name})
        if not libraries:
            continue
        collections.append(
            {
                "name": collection.name,
                "in_development": collection.in_development,
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
            }
        )
    found = group_problems(entries)
    return {
        "generated_at": snapshot.generated_at,
        "tool_version": snapshot.tool_version,
        "columns": [
            {"source": source_label(source), "channel": channel or "(all)"}
            for source, channel in columns
        ],
        "collections": collections,
        "legend": [
            {"glyph": glyph, "css": STATUS_CSS[status], "label": STATUS_LABELS[status]}
            for status, glyph in STATUS_GLYPHS.items()
        ],
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
        "errors": [{"source": e.source, "message": e.message} for e in snapshot.errors],
    }


def render(snapshot: Snapshot, entries: list[StatusEntry]) -> str:
    template = _environment().get_template("dashboard.html.j2")
    return template.render(**build_view(snapshot, entries))


def write(snapshot: Snapshot, entries: list[StatusEntry], out_dir: str | Path) -> Path:
    """Write ``index.html`` plus the snapshot it was rendered from."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "index.html"
    index.write_text(render(snapshot, entries))
    (directory / "snapshot.json").write_text(
        json.dumps(to_dict(snapshot), indent=2) + "\n"
    )
    return index
