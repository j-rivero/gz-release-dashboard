"""Factory registry for package sources.

Adding a source is one module plus one ``@register_source`` decorator; the CLI
choices, the fetch loop and the renderer columns all follow automatically.
"""

from __future__ import annotations

from .base import Http, PackageSource

_REGISTRY: dict[str, type[PackageSource]] = {}


def register_source(cls: type[PackageSource]) -> type[PackageSource]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a name")
    if cls.name in _REGISTRY:
        raise ValueError(f"duplicate source name {cls.name!r}")
    _REGISTRY[cls.name] = cls
    return cls


def available_sources() -> tuple[str, ...]:
    """Registered source names, in the order the dashboard displays them."""
    return tuple(_REGISTRY)


def source_class(name: str) -> type[PackageSource]:
    return _REGISTRY[name]


def create_sources(names: list[str] | None, http: Http) -> list[PackageSource]:
    selected = list(names) if names else list(_REGISTRY)
    unknown = [n for n in selected if n not in _REGISTRY]
    if unknown:
        raise KeyError(f"unknown source(s): {', '.join(unknown)}")
    return [_REGISTRY[name](http) for name in selected]


# Imported for their side effect: each module registers itself.
from . import osrf_debian  # noqa: E402,F401
from . import bazel_registry  # noqa: E402,F401
