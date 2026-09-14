"""Which tracked dependency a name stands for, in one system's own spelling."""

from __future__ import annotations

import re

from .. import config
from ..models import FetchError


def match_dependency(system: str, name: str) -> str | None:
    """The canonical dependency ``name`` is, in ``system``, or ``None``."""
    for dependency, systems in config.DEPENDENCY_ALIASES.items():
        if any(re.fullmatch(pattern, name) for pattern in systems.get(system, ())):
            return dependency
    return None


def unmapped_error(collection: str, library: str, major: int, name: str, where: str) -> FetchError:
    """A Gazebo-hosted name a build declares that the alias table does not know.

    Reported rather than skipped: the alias table is the one list kept by hand,
    and this is how it finds out it has fallen behind.
    """
    return FetchError(
        "deps:aliases",
        f"{collection}/{library}{major} declares {name} ({where}) with no alias",
    )
