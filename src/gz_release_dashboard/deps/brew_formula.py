"""What the osrf/simulation formulas depend on, and which version that gets.

A gz formula names its dependencies by formula (``depends_on "ogre2.3"``). The
tap carries its own builds of some of them, often forks pinned to a commit
(``ogre2.2``, ``dartsim@6.10.0``), so a name is looked up in the tap before
homebrew-core, which is where the rest (``dartsim``, ``bullet``) come from.
"""

from __future__ import annotations

import re

from .. import config
from ..models import Collection, DependencyRecord, Library
from ..sources.homebrew import SOURCE_ONLY, URL_VERSION_RE, bottle_labels, formula_names
from ..versions import dependency_version
from . import register_reader
from .aliases import match_dependency, unmapped_error
from .base import DependencyReader

#: `depends_on "name"` and whatever follows it, such as `=> [:build, :test]`.
DEPENDS_ON_RE = re.compile(r'^\s*depends_on\s+"([^"]+)"(.*)$', re.MULTILINE)
#: What is only needed to build or test the formula is not what a user gets.
BUILD_OR_TEST_RE = re.compile(r":(?:build|test)\b")
VERSION_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)
#: GitHub tag archives are named after the tag alone (`v2.3.1.tar.gz`,
#: `2.87.tar.gz`), with no `-` for URL_VERSION_RE to anchor on.
TAG_ARCHIVE_RE = re.compile(r'url\s+"[^"]*/v?(\d+(?:\.\d+)+)\.tar\.(?:bz2|gz|xz)"')
#: The tap's own libraries and collections, which depend on each other and are
#: never a dependency to track.
GZ_FORMULA_PREFIXES = ("gz-", "ignition-", "sdformat")

TAP_ORIGIN = "tap"
CORE_ORIGIN = "homebrew-core"
TAP_WHERE = "osrf/simulation tap"


def declared_dependencies(text: str) -> list[str]:
    """The formulas ``text`` needs at run time, in the order it lists them."""
    return [
        name for name, rest in DEPENDS_ON_RE.findall(text) if not BUILD_OR_TEST_RE.search(rest)
    ]


def tap_version(text: str) -> str | None:
    """The version a tap formula states, spelled as the formula spells it.

    A ``version`` line overrides whatever brew would read from the url, and the
    tap writes one exactly where the url is a commit tarball with no version in
    it (``2.2.6+20211021~312bf40``).
    """
    for regex in (VERSION_RE, URL_VERSION_RE, TAG_ARCHIVE_RE):
        match = regex.search(text)
        if match:
            return match.group(1)
    return None


@register_reader
class BrewFormulaReader(DependencyReader):
    """One record per tracked dependency of a gz formula, per bottle label."""

    system = "brew"

    def read(self, collections: list[Collection]) -> list[DependencyRecord]:
        self.errors = []
        records: list[DependencyRecord] = []
        for collection in self.applicable(collections):
            for library in collection.libraries:
                found = self._formula(library)
                if found is not None:
                    records.extend(self._records(collection.name, library, found))
        return records

    def _formula(self, library: Library) -> str | None:
        """The source of the first candidate formula that exists."""
        for name in formula_names(library.name, library.major):
            text = self._tap(name)
            if text is not None:
                return text
        return None

    def _tap(self, name: str) -> str | None:
        # The URL the homebrew source fetches, so a run's memo serves both.
        return self.http.get_text(config.HOMEBREW_FORMULA_URL.format(formula=name), ok_404=True)

    def _records(self, collection: str, library: Library, text: str) -> list[DependencyRecord]:
        labels = bottle_labels(text) or [SOURCE_ONLY]
        records: list[DependencyRecord] = []
        for name in declared_dependencies(text):
            dependency = match_dependency(self.system, name)
            if dependency is None:
                self._check_alias(collection, library, name)
                continue
            raw, origin = self._resolve(name)
            records.extend(
                DependencyRecord(
                    collection=collection,
                    library=library.name,
                    major=library.major,
                    dependency=dependency,
                    system=self.system,
                    platform=label,
                    declared=name,
                    version=dependency_version(raw),
                    origin=origin,
                )
                for label in labels
            )
        return records

    def _resolve(self, name: str) -> tuple[str | None, str]:
        """``(raw version, origin)`` of the formula ``name``.

        A tap formula that states no version still settles it: that formula is
        what gets installed, so core's version of the name would be wrong.
        """
        text = self._tap(name)
        if text is not None:
            return tap_version(text), TAP_ORIGIN
        url = config.HOMEBREW_CORE_FORMULA_URL.format(formula=name)
        data = self.http.get_json(url, ok_404=True)
        if data is not None:
            return (data.get("versions") or {}).get("stable"), CORE_ORIGIN
        return None, ""

    def _check_alias(self, collection: str, library: Library, name: str) -> None:
        """Report a name the tap hosts for Gazebo that the alias table lacks.

        Everything else a formula declares (qtbase, python@3.14) is
        homebrew-core's, 404s in the tap and is nobody's to track here.
        """
        if name.startswith(GZ_FORMULA_PREFIXES) or self._tap(name) is None:
            return
        self.errors.append(
            unmapped_error(collection, library.name, library.major, name, where=TAP_WHERE)
        )
