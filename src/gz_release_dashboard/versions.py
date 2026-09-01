"""Gazebo upstream version parsing plus the per-source normalizers.

Every source spells the same upstream release differently (``9.6.0-1~noble``,
``9.6.0.bcr.1``, ``9.6.0_2``); the normalizers bring them all back to the
canonical ``M.m.p[-preN]`` form that :class:`GzVersion` understands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Iterable

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-pre(\d+))?$")


@total_ordering
@dataclass(frozen=True)
class GzVersion:
    """An upstream Gazebo version; ``9.0.0`` outranks ``9.0.0-pre2``."""

    major: int
    minor: int
    patch: int
    pre: int | None = None

    @classmethod
    def parse(cls, text: str | None) -> "GzVersion | None":
        if not text:
            return None
        match = VERSION_RE.match(text.strip())
        if not match:
            return None
        major, minor, patch, pre = match.groups()
        return cls(int(major), int(minor), int(patch), int(pre) if pre else None)

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None

    def sort_key(self) -> tuple[int, int, int, int, int]:
        return (
            self.major,
            self.minor,
            self.patch,
            0 if self.pre is not None else 1,
            self.pre or 0,
        )

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, GzVersion):
            return NotImplemented
        return self.sort_key() < other.sort_key()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-pre{self.pre}" if self.pre is not None else base


def max_version(candidates: Iterable[str | None]) -> str | None:
    """Highest parseable version among ``candidates``, or ``None``."""
    parsed = [v for v in (GzVersion.parse(c) for c in candidates) if v is not None]
    return str(max(parsed)) if parsed else None


def normalize_plain(raw: str | None) -> str | None:
    """Accept a version that is already in canonical form."""
    parsed = GzVersion.parse(raw)
    return str(parsed) if parsed else None


def normalize_deb(raw: str | None) -> str | None:
    """``9.6.0-1~noble`` -> ``9.6.0``; ``9.0.0~pre1-1~noble`` -> ``9.0.0-pre1``."""
    if not raw:
        return None
    text = raw.strip()
    if ":" in text:  # drop the epoch
        text = text.split(":", 1)[1]
    text = text.replace("~pre", "-pre")
    parsed = GzVersion.parse(text)
    if parsed:
        return str(parsed)
    if "-" in text:  # drop the Debian revision (`-1~noble`, `-1.995~noble`)
        parsed = GzVersion.parse(text.rsplit("-", 1)[0])
        if parsed:
            return str(parsed)
    return None


def normalize_bcr(raw: str | None) -> str | None:
    """``9.6.0.bcr.1`` -> ``9.6.0``: ``.bcr.N`` is a registry repack revision."""
    if not raw:
        return None
    return normalize_plain(re.sub(r"\.bcr\.\d+$", "", raw.strip()))
