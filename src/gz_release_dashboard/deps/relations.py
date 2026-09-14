"""Debian relationship fields -- Build-Depends, Depends -- as far as we read them.

gazebo-release control files and the ROS vendor packages both declare their
dependencies this way, so the grammar is read once, here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ARCH_QUALIFIER_RE = re.compile(r"\[([^\]]*)\]")
#: Everything that decorates a name without being part of it: version
#: constraints, architecture qualifiers and build profiles.
DECORATION_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]|<[^>]*>")


@dataclass(frozen=True)
class Alternative:
    """One name in a relation, with the architectures it is restricted to."""

    name: str
    arches: tuple[str, ...] = ()
    negated: bool = False

    def applies_to(self, arch: str) -> bool:
        """``[!armhf]`` excludes armhf; ``[amd64 arm64]`` includes only those."""
        if not self.arches:
            return True
        return (arch in self.arches) != self.negated


def parse_relations(field: str) -> list[list[Alternative]]:
    """Every relation in ``field``, each a list of its ``|`` alternatives."""
    relations: list[list[Alternative]] = []
    for entry in field.replace("\n", " ").split(","):
        alternatives = [
            alternative
            for alternative in (_alternative(text) for text in entry.split("|"))
            if alternative is not None
        ]
        if alternatives:
            relations.append(alternatives)
    return relations


def _alternative(text: str) -> Alternative | None:
    qualifier = ARCH_QUALIFIER_RE.search(text)
    arches: tuple[str, ...] = ()
    negated = False
    if qualifier:
        tokens = qualifier.group(1).split()
        negated = bool(tokens) and all(token.startswith("!") for token in tokens)
        arches = tuple(token.lstrip("!") for token in tokens)
    bare = DECORATION_RE.sub(" ", text).strip()
    # `${shlibs:Depends}` is filled in at build time and names nothing yet.
    if not bare or bare.startswith("${"):
        return None
    name = bare.split()[0].split(":", 1)[0]  # `python3:any`
    return Alternative(name, arches, negated)
