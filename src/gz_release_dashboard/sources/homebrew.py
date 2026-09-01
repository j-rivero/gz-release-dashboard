"""The osrf/simulation homebrew tap, read straight from the formula sources.

formulae.brew.sh has no JSON for third-party taps, so each ``Formula/*.rb`` is
fetched raw and scraped.
"""

from __future__ import annotations

import re

from .. import config
from ..ground_truth import candidate_tag_prefixes
from ..models import Collection, Library, PackageRecord
from ..versions import GzVersion
from . import register_source
from .base import PackageSource

#: The tarball is not always named after the formula (`gz-fuel_tools-11.0.0`),
#: so only the version and the archive suffix are anchored.
URL_VERSION_RE = re.compile(r'url\s+"[^"]*?-(\d+\.\d+\.\d+(?:-pre\d+)?)\.tar\.(?:bz2|gz|xz)"')
REVISION_RE = re.compile(r"^\s*revision\s+(\d+)\s*$", re.MULTILINE)
BOTTLE_BLOCK_RE = re.compile(r"^\s*bottle do\s*$(.*?)^\s*end\s*$", re.MULTILINE | re.DOTALL)
#: `sha256 arm64_sonoma: "..."`, optionally preceded by `cellar: :any,`.
BOTTLE_LABEL_RE = re.compile(r"sha256\s+(?:cellar:\s*:[a-z_]+,\s*)?([a-z0-9_]+):")

#: A formula with no bottle block ships from source only.
SOURCE_ONLY = "source-only"


def formula_names(library: str, major: int) -> tuple[str, ...]:
    """Candidate formula basenames, newest naming convention first.

    The tap follows the same naming eras as the release tags, so the tag
    prefixes minus their trailing underscore are exactly the formula names
    (`gz-sim10`, `ignition-gazebo6`, `ignition-tools`).
    """
    return tuple(prefix.rstrip("_") for prefix in candidate_tag_prefixes(library, major))


def bottle_labels(text: str) -> list[str]:
    match = BOTTLE_BLOCK_RE.search(text)
    if not match:
        return []
    # Codenames are never hardcoded: whatever the tap bottles for is reported.
    return BOTTLE_LABEL_RE.findall(match.group(1))


def label_arch(label: str) -> str:
    return "arm64" if label.startswith("arm64_") else "x86_64"


@register_source
class HomebrewSource(PackageSource):
    """One record per (library, major, bottle label)."""

    name = "homebrew"
    channels = ()

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        libraries = sorted({lib for c in collections for lib in c.libraries})
        records: list[PackageRecord] = []
        for library in libraries:
            found = self._formula(library)
            if found is None:
                continue
            records.extend(self._records(library, *found))
        return records

    def _formula(self, library: Library) -> tuple[str, str] | None:
        """First candidate formula that exists, as ``(name, source)``."""
        for name in formula_names(library.name, library.major):
            url = config.HOMEBREW_FORMULA_URL.format(formula=name)
            text = self.http.get_text(url, ok_404=True)
            if text is not None:
                return name, text
        return None

    def _records(self, library: Library, name: str, text: str) -> list[PackageRecord]:
        match = URL_VERSION_RE.search(text)
        if not match:
            # gz-rotary-* formulas are head-only: no url, hence no version.
            return []
        version = GzVersion.parse(match.group(1))
        if version is None or version.major != library.major:
            return []
        revision = REVISION_RE.search(text)
        raw = f"{version}_{revision.group(1)}" if revision else str(version)
        labels = bottle_labels(text) or [SOURCE_ONLY]
        return [
            PackageRecord(
                source=self.name,
                channel="",
                platform=label,
                arch=label_arch(label) if label != SOURCE_ONLY else "all",
                library=library.name,
                major=library.major,
                pkg_name=name,
                raw_version=raw,
                upstream_version=str(version),
            )
            for label in labels
        ]
