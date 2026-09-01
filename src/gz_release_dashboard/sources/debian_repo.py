"""Shared plumbing for the two APT repositories we read.

Both packages.osrfoundation.org and packages.ros.org publish plain RFC822
``Packages.gz`` indexes, so the stanza parser and the gz naming rules live here
rather than being written twice.
"""

from __future__ import annotations

import re
from typing import Iterator

#: `gz-fuel-tools10` -> (gz-fuel-tools, 10). The major group is optional
#: because the first ignition release of a lib carried no suffix at all
#: (`ignition-tools`, `ignition-plugin`), which means major 1.
SOURCE_NAME_RE = re.compile(r"^(?P<base>[a-z][a-z-]*?)(?P<major>\d+)?$")


def parse_stanzas(text: str) -> Iterator[dict[str, str]]:
    """Yield each blank-line-separated RFC822 stanza as a dict."""
    stanza: dict[str, str] = {}
    key: str | None = None
    for line in text.splitlines():
        if not line.strip():
            if stanza:
                yield stanza
            stanza, key = {}, None
            continue
        if line[0] in " \t":  # a folded continuation of the previous field
            if key:
                stanza[key] += "\n" + line.strip()
            continue
        name, separator, value = line.partition(":")
        if not separator:
            continue
        key = name.strip()
        stanza[key] = value.strip()
    if stanza:
        yield stanza


def source_name(stanza: dict[str, str]) -> str:
    """The source package a binary came from; ``Source`` defaults to ``Package``."""
    source = stanza.get("Source") or stanza.get("Package", "")
    return source.split(" ", 1)[0]  # `Source: gz-sim10 (10.5.0-1)`


def canonical_library(base: str) -> str:
    """Rename the ignition era onto today's library names."""
    if base == "ignition-gazebo":
        return "gz-sim"
    if base.startswith("ignition-"):
        return "gz-" + base.removeprefix("ignition-")
    return base


def split_source_name(source: str) -> tuple[str, int] | None:
    """``ignition-gazebo6`` -> ``("gz-sim", 6)``; ``dart6.13`` -> ``None``."""
    match = SOURCE_NAME_RE.match(source)
    if not match:
        return None
    major = match.group("major")
    return canonical_library(match.group("base")), int(major) if major else 1


def packages_url(base: str, repository: str, distro: str, arch: str) -> str:
    return f"{base}/{repository}/dists/{distro}/main/binary-{arch}/Packages.gz"
