"""Turn ``gz-collections.yaml`` into the collections the dashboard shows.

Three upstream conventions are decoded here, none of them by hardcoding names:
a collection under development has no ``ci.configs``; a collection that is not
released at all (rotary) has libs without ``major_version``; and a collection's
metapackage is the lib listed in ``packaging.linux.ignore_major_version``.
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
        collections.append(Collection(name, _is_in_development(entry), libraries))
    return collections


def load_collections(
    http: HttpClient, url: str = config.COLLECTIONS_YAML_URL
) -> list[Collection]:
    text = http.get_text(url)
    assert text is not None  # not probed with ok_404: a failure here is fatal
    return parse_collections(text)
