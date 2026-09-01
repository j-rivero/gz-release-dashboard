"""The contract every package source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from ..models import Collection, PackageRecord


class Http(Protocol):
    """The slice of :class:`~gz_release_dashboard.http.HttpClient` sources use."""

    def get_text(self, url: str, *, ok_404: bool = False) -> str | None: ...
    def get_json(self, url: str, *, ok_404: bool = False): ...
    def get_gzip_text(self, url: str, *, ok_404: bool = False) -> str | None: ...


class PackageSource(ABC):
    """One packaging system, fetched into a flat list of records."""

    #: Registry key, CLI ``--source`` value and column group in the output.
    name: str = ""
    #: Independent feeds within the source, e.g. stable vs prerelease.
    channels: tuple[str, ...] = ()

    def __init__(self, http: Http) -> None:
        self.http = http

    @abstractmethod
    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        """Return every record this source knows about for ``collections``."""
