"""Bazel Central Registry: the pins in the MODULE.bazel a gz module was published with.

A registry version's MODULE.bazel names every dependency at one exact version,
so for Bazel the declaration and its resolution are the same line. The module
read is the release ``bazel_registry`` reports for the collection, the newest
non-yanked version of the major, so the library table and the dependency table
speak about the same file.
"""

from __future__ import annotations

import re

from .. import config
from ..models import Collection, DependencyRecord
from ..sources.bazel_registry import newest_version
from ..versions import dependency_version
from . import register_reader
from .aliases import match_dependency
from .base import DependencyReader

#: One ``bazel_dep(...)`` call, however many lines it spans. Its arguments are
#: strings and booleans, never a parenthesis, so the first ``)`` closes it.
BAZEL_DEP_RE = re.compile(r"(?<![\w.])bazel_dep\s*\(([^)]*)\)")
#: A keyword argument, either a string or a bare ``True``/``False``.
ARG_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|(\w+))')
#: No ``bazel_dep`` string holds a ``#``, so cutting from it to the end of the
#: line only ever drops a comment, a switched-off ``bazel_dep`` included.
COMMENT_RE = re.compile(r"#[^\n]*")


def bazel_deps(text: str) -> list[tuple[str, str | None]]:
    """``(name, version)`` of every ``bazel_dep`` a MODULE.bazel makes its users build with.

    A ``dev_dependency`` is the module's own test tooling: Bazel ignores it
    whenever the module is someone else's dependency, so it is not part of what
    a collection gets.
    """
    deps = []
    for call in BAZEL_DEP_RE.finditer(COMMENT_RE.sub("", text)):
        args = {key: string or bare for key, string, bare in ARG_RE.findall(call.group(1))}
        if "name" not in args or args.get("dev_dependency") == "True":
            continue
        deps.append((args["name"], args.get("version") or None))
    return deps


@register_reader
class BcrModuleReader(DependencyReader):
    """A flat reader: the registry has no platform axis, so every record is ``all``."""

    system = "bazel"

    def read(self, collections: list[Collection]) -> list[DependencyRecord]:
        # Asking for a library bazel_registry knows has no module only collects 404s.
        absent = config.EXPECTED_ABSENT.get(self.source, frozenset())
        records = []
        for collection in self.applicable(collections):
            for library in collection.libraries:
                if library.name in absent:
                    continue
                for name, pin in self._pins(library.name, library.major):
                    dependency = match_dependency(self.system, name)
                    if dependency is None:
                        continue
                    records.append(
                        DependencyRecord(
                            collection=collection.name,
                            library=library.name,
                            major=library.major,
                            dependency=dependency,
                            system=self.system,
                            platform="all",
                            declared=f"{name} {pin}" if pin else name,
                            version=dependency_version(pin),
                            origin="bcr",
                        )
                    )
        return records

    def _pins(self, module: str, major: int) -> list[tuple[str, str | None]]:
        # A module, a major or a MODULE.bazel the registry lacks is absence the
        # library table already reports; the inventory has nothing to add to it.
        # The metadata URL is the one bazel_registry fetches, so the run's memo
        # serves it, and a major shared by collections is only fetched once.
        data = self.http.get_json(config.BCR_METADATA_URL.format(module=module), ok_404=True)
        newest = newest_version(data, major) if data else None
        if newest is None:
            return []
        raw, _ = newest
        # The directory is the registry's spelling (`4.0.0.bcr.1`), not upstream's.
        text = self.http.get_text(
            config.BCR_MODULE_URL.format(module=module, version=raw), ok_404=True
        )
        return bazel_deps(text) if text is not None else []
