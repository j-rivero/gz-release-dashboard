"""conda-forge dependencies, read from the pins its gz builds carry.

A conda-forge build records what it was linked against in ``attrs.depends``:
``dartsim-cpp >=6.19.4,<6.20.0a0`` is the run-export pin of a build made
against dart 6.19.4. That floor is the version reported (decision 6). The top
of the pin is whatever the solver picks on the day of an install; the floor is
a fact about the gz build itself.

The pins sit on the ``libgz-<x>`` outputs, not on the ``gz-<x>`` metapackage,
and older majors are still published under the legacy ``libgz-<x><major>``
names, so both are read, as ``conda_forge`` reads both feedstock names.
"""

from __future__ import annotations

import re

from .. import config
from ..models import Collection, DependencyRecord
from ..sources.conda_forge import CondaForgeSource
from ..versions import GzVersion, dependency_version
from . import register_reader
from .aliases import match_dependency
from .base import DependencyReader

#: A clause of a pin that states its floor outright: ``>=X``, ``==X``, a bare
#: ``X`` or ``X.*``. ``>X``, or an ``|`` between alternatives, has no one floor.
FLOOR_RE = re.compile(r"(?:>=|==)?(\d[\w.]*?)(?:\.\*)?")


def pin_floor(spec: str) -> str | None:
    """The version a conda depends spec is bounded below by, or ``None``."""
    parts = spec.split()
    if len(parts) < 2:
        return None
    for clause in parts[1].split(","):
        match = FLOOR_RE.fullmatch(clause)
        if match:
            return dependency_version(match.group(1))
    return None


@register_reader
class CondaArtifactsReader(DependencyReader):
    """One record per subdir and tracked pin of the newest build that pins any."""

    system = "conda"

    def read(self, collections: list[Collection]) -> list[DependencyRecord]:
        pins: dict[tuple[str, int], dict[str, list[tuple[str, str]]]] = {}
        records: list[DependencyRecord] = []
        for collection in self.applicable(collections):
            for library in collection.libraries:
                key = (library.name, library.major)
                if key not in pins:
                    pins[key] = self._pins(library.name, library.major)
                for subdir, declared in sorted(pins[key].items()):
                    for dependency, spec in declared:
                        records.append(
                            DependencyRecord(
                                collection=collection.name,
                                library=library.name,
                                major=library.major,
                                dependency=dependency,
                                system=self.system,
                                platform=subdir,
                                declared=spec,
                                version=pin_floor(spec),
                                origin="conda-forge",
                            )
                        )
        return records

    def _pins(self, library: str, major: int) -> dict[str, list[tuple[str, str]]]:
        """``{subdir: [(dependency, spec)]}`` from the newest build of ``major`` that pins any.

        A build pinning nothing tracked is passed over rather than chosen: the
        unversioned ``libgz-physics`` has 7.5.0 builds whose depends name no
        dart at all, while ``libgz-physics7`` 7.5.0 pins it.
        """
        best: dict[str, tuple[tuple[GzVersion, int, int], list[tuple[str, str]]]] = {}
        for name in CondaForgeSource.candidate_names(library, major):
            url = config.ANACONDA_PACKAGE_URL.format(name=f"lib{name}")
            data = self.http.get_json(url, ok_404=True) or {}
            for entry in data.get("files") or []:
                attrs = entry.get("attrs") or {}
                subdir = attrs.get("subdir")
                version = GzVersion.parse(entry.get("version"))
                if not subdir or version is None or version.major != major:
                    continue
                # A build can list one pin twice; libgz-rendering 10.0.0 does.
                declared = list(
                    dict.fromkeys(
                        (dependency, spec)
                        for spec in attrs.get("depends") or []
                        if (dependency := match_dependency(self.system, spec.partition(" ")[0]))
                    )
                )
                if not declared:
                    continue
                # A version is rebuilt as its dependencies migrate, re-pinning
                # each time, so the build number decides between its builds.
                rank = (version, attrs.get("build_number") or 0, attrs.get("timestamp") or 0)
                if subdir not in best or rank > best[subdir][0]:
                    best[subdir] = (rank, declared)
        return {subdir: declared for subdir, (_, declared) in best.items()}
