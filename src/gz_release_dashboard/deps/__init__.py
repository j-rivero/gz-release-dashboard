"""The dependency inventory: what each collection's builds declare, and get.

Readers are a factory registry, one per build system, the way sources are.
Each follows one library source (``config.DEPENDENCY_SYSTEMS``), so selecting
sources selects readers and the ``--source`` choices need nothing new.
"""

from __future__ import annotations

from .. import config
from ..sources.base import Http
from .base import DependencyReader

_REGISTRY: dict[str, type[DependencyReader]] = {}


def register_reader(cls: type[DependencyReader]) -> type[DependencyReader]:
    if cls.system not in config.DEPENDENCY_SYSTEMS:
        raise ValueError(f"{cls.__name__} reads unknown system {cls.system!r}")
    if cls.system in _REGISTRY:
        raise ValueError(f"duplicate dependency reader for {cls.system!r}")
    _REGISTRY[cls.system] = cls
    return cls


def available_readers() -> tuple[str, ...]:
    """Registered systems, in registration order."""
    return tuple(_REGISTRY)


def create_readers(sources: list[str] | None, http: Http) -> list[DependencyReader]:
    """The readers whose library source is among ``sources``; all when ``None``."""
    selected = set(sources) if sources else None
    return [
        cls(http)
        for cls in _REGISTRY.values()
        if selected is None or config.DEPENDENCY_SYSTEMS[cls.system] in selected
    ]


# Imported for their @register_reader side effect, in the order of the library
# sources they follow, so the fetch log reads the same way the columns do.
from . import deb_control  # noqa: E402,F401
from . import bcr_module  # noqa: E402,F401
from . import conda_artifacts  # noqa: E402,F401
from . import brew_formula  # noqa: E402,F401
from . import ros_vendor_deps  # noqa: E402,F401
