"""Group dependency records into the rows and cells the renderers draw. Pure.

There is no status here, only agreement. Two marks, at two levels:

- a cell warns (⚠) when one system disagrees with itself -- platforms,
  declaring libraries or declared names carrying different versions, which is
  usually something someone can fix (osrf noble still on ogre-next 2.3.1 while
  resolute has 2.3.3);
- a row diverges (◇) when systems disagree on the series, which is often
  deliberate (conda-forge pins dart 6.19 while the Debian side ships 6.16) and
  is shown so it is known, not so it is fixed. A patch-level difference between
  systems is not marked at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..models import DependencyRecord
from ..versions import series, version_key


@dataclass
class DependencyCell:
    """One system's records for one dependency of one collection.

    ``warn`` is worked out from the records unless it is given: a narrowed view
    hands over the mark of the whole one, so hiding a declaring library cannot
    make a system look as if it agreed with itself.
    """

    collection: str
    dependency: str
    system: str
    records: list[DependencyRecord]
    warn: bool | None = None

    def __post_init__(self) -> None:
        if self.warn is None:
            self.warn = len(self.versions) > 1

    @property
    def versions(self) -> list[str]:
        """The distinct versions, lowest first; ``1.9`` and ``1.9.0`` are one."""
        distinct: dict[tuple[int, ...], str] = {}
        for record in self.records:
            if record.version is not None:
                distinct.setdefault(version_key(record.version), record.version)
        return [distinct[key] for key in sorted(distinct)]

    @property
    def low(self) -> str | None:
        versions = self.versions
        return versions[0] if versions else None

    @property
    def high(self) -> str | None:
        versions = self.versions
        return versions[-1] if versions else None

    @property
    def series(self) -> frozenset[tuple[int, int]]:
        return frozenset(series(version) for version in self.versions)

    @property
    def text(self) -> str:
        """One version, a ``low–high`` range, the provider's label, or ``?``."""
        versions = self.versions
        if len(versions) == 1:
            return versions[0]
        if versions:
            return f"{versions[0]}–{versions[-1]}"
        labels = {record.label for record in self.records if record.label}
        return labels.pop() if len(labels) == 1 else "?"

    @property
    def lowest_platforms(self) -> list[str]:
        """Where the lowest version is: the places a warning points at."""
        low = self.low
        if low is None:
            return []
        key = version_key(low)
        return sorted(
            {
                record.platform
                for record in self.records
                if record.version is not None and version_key(record.version) == key
            }
        )


@dataclass
class DependencyRow:
    """One dependency of one collection, across every system that declares it.

    ``diverges`` -- two systems hold different series, unversioned systems
    sitting it out -- is worked out from the cells unless it is given, for the
    same reason as a cell's ``warn``: ◇ compares systems, so a view showing only
    some of them must keep the verdict reached with all of them.
    """

    collection: str
    dependency: str
    cells: dict[str, DependencyCell]
    diverges: bool | None = None

    def __post_init__(self) -> None:
        if self.diverges is None:
            held = {cell.series for cell in self.cells.values() if cell.series}
            self.diverges = len(held) > 1


def dependency_rows(records: list[DependencyRecord]) -> list[DependencyRow]:
    """One row per ``(collection, dependency)``, sorted by both."""
    grouped: dict[tuple[str, str], dict[str, list[DependencyRecord]]] = {}
    for record in records:
        by_system = grouped.setdefault((record.collection, record.dependency), {})
        by_system.setdefault(record.system, []).append(record)
    return [
        DependencyRow(
            collection=collection,
            dependency=dependency,
            cells={
                system: DependencyCell(collection, dependency, system, system_records)
                for system, system_records in by_system.items()
            },
        )
        for (collection, dependency), by_system in sorted(grouped.items())
    ]


def narrow_rows(
    rows: list[DependencyRow], keep: Callable[[DependencyRecord], bool]
) -> list[DependencyRow]:
    """Keep the records ``keep`` accepts, and every mark exactly as it was.

    A cell left without records goes, and so does a row left without cells.
    """
    narrowed = []
    for row in rows:
        cells = {}
        for system, cell in row.cells.items():
            kept = [record for record in cell.records if keep(record)]
            if kept:
                cells[system] = DependencyCell(
                    cell.collection, cell.dependency, system, kept, warn=cell.warn
                )
        if cells:
            narrowed.append(
                DependencyRow(row.collection, row.dependency, cells, diverges=row.diverges)
            )
    return narrowed
