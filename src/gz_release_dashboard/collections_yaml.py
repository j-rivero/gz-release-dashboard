"""Turn ``gz-collections.yaml`` into the collections the dashboard shows.

Four upstream conventions are decoded here, none of them by hardcoding names:
a collection under development has no ``ci.configs``; a collection that is not
released at all (rotary) has libs without ``major_version``; a collection's
metapackage is the lib listed in ``packaging.linux.ignore_major_version``; and
the Linux releases still worth querying are the ones the live collections name
in ``packaging.configs``.
"""

from __future__ import annotations

from typing import Any

import yaml

from . import config
from .http import HttpClient
from .models import Collection, Library


def _metapackage_names(entry: dict[str, Any]) -> set[str]:
    packaging = entry.get("packaging") or {}
    linux = packaging.get("linux") or {}
    return set(linux.get("ignore_major_version") or [])


def _linux_platforms(data: dict[str, Any]) -> dict[str, str]:
    """Packaging config name -> Linux release, e.g. ``{"noble": "noble"}``.

    macOS and Windows configs are left out: they carry no distro axis.
    """
    platforms = {}
    for entry in data.get("packaging_configs") or []:
        system = entry.get("system") or {}
        if entry.get("name") and system.get("so") == "linux" and system.get("version"):
            platforms[entry["name"]] = system["version"]
    return platforms


def _collection_distros(entry: dict[str, Any], platforms: dict[str, str]) -> list[str]:
    packaging = entry.get("packaging") or {}
    seen: list[str] = []
    for name in packaging.get("configs") or []:
        distro = platforms.get(name)
        if distro and distro not in seen:
            seen.append(distro)
    return seen


def linux_distros(collections: list[Collection]) -> tuple[str, ...]:
    """Every Linux release still targeted by a live collection, oldest first.

    This is what keeps end-of-life distributions off the dashboard without a
    hardcoded list or an external EOL feed: focal is absent because no live
    collection packages for it any more, and jammy will drop out by itself the
    day fortress is retired from gz-collections.yaml. Collections are read in
    file order and each one's configs in declaration order, so the result stays
    chronological.
    """
    ordered: list[str] = []
    for collection in collections:
        for distro in collection.distros:
            if distro not in ordered:
                ordered.append(distro)
    return tuple(ordered)


def _is_in_development(entry: dict[str, Any]) -> bool:
    ci = entry.get("ci") or {}
    if not (ci.get("configs") or []):
        return True
    return entry.get("name") in config.IN_DEVELOPMENT_FALLBACK


def parse_collections(
    text: str, ignored: tuple[str, ...] = config.IGNORED_COLLECTIONS
) -> list[Collection]:
    """Parse the YAML text, dropping ignored collections and metapackages."""
    data = yaml.safe_load(text) or {}
    platforms = _linux_platforms(data)
    collections: list[Collection] = []
    for entry in data.get("collections") or []:
        name = entry.get("name")
        if not name or name in ignored:
            continue
        metapackages = _metapackage_names(entry)
        libraries = [
            Library(lib["name"], int(lib["major_version"]))
            for lib in entry.get("libs") or []
            # A lib without a major version belongs to an unreleased collection.
            if lib.get("name") and lib.get("major_version") is not None
            and lib["name"] not in metapackages
        ]
        if not libraries:
            continue
        collections.append(
            Collection(
                name,
                _is_in_development(entry),
                libraries,
                _collection_distros(entry, platforms),
            )
        )
    return collections


def load_collections(
    http: HttpClient, url: str = config.COLLECTIONS_YAML_URL
) -> list[Collection]:
    text = http.get_text(url)
    assert text is not None  # not probed with ok_404: a failure here is fatal
    return parse_collections(text)
