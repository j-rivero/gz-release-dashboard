"""Persist a fetch run as JSON so the renderers never touch the network."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .models import (
    Collection,
    FetchError,
    GroundTruthEntry,
    Library,
    PackageRecord,
    Snapshot,
)

SCHEMA_VERSION = 1


def new_snapshot(sources_fetched: list[str]) -> Snapshot:
    return Snapshot(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        tool_version=__version__,
        sources_fetched=list(sources_fetched),
    )


def to_dict(snapshot: Snapshot) -> dict[str, Any]:
    return asdict(snapshot)


def from_dict(data: dict[str, Any]) -> Snapshot:
    schema = data.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported snapshot schema_version {schema!r}; "
            f"this tool writes and reads version {SCHEMA_VERSION}"
        )
    return Snapshot(
        schema_version=schema,
        generated_at=data["generated_at"],
        tool_version=data.get("tool_version", "unknown"),
        sources_fetched=list(data.get("sources_fetched", [])),
        collections=[
            Collection(
                name=c["name"],
                in_development=c["in_development"],
                libraries=[Library(**lib) for lib in c["libraries"]],
                distros=list(c.get("distros", [])),
            )
            for c in data.get("collections", [])
        ],
        ground_truth=[GroundTruthEntry(**g) for g in data.get("ground_truth", [])],
        records=[PackageRecord(**r) for r in data.get("records", [])],
        errors=[FetchError(**e) for e in data.get("errors", [])],
    )


def save(snapshot: Snapshot, path: str | Path) -> Path:
    target = Path(path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_dict(snapshot), indent=2, sort_keys=False) + "\n")
    return target


def load(path: str | Path) -> Snapshot:
    return from_dict(json.loads(Path(path).read_text()))
