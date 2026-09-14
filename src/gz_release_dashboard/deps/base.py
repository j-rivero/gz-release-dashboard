"""The contract every dependency reader implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .. import config
from ..models import Collection, DependencyRecord, FetchError
from ..sources.base import Http


class DependencyReader(ABC):
    """One build system: what each collection's builds declare, and resolve to."""

    #: The column in the dependency tables, and a key of DEPENDENCY_SYSTEMS.
    system: str = ""

    def __init__(self, http: Http) -> None:
        self.http = http
        #: Non-fatal findings of the last read, next to the records it returned:
        #: an alias the table lacks, a base archive that could not be asked.
        self.errors: list[FetchError] = []

    @property
    def source(self) -> str:
        """The library source this system follows."""
        return config.DEPENDENCY_SYSTEMS[self.system]

    def applicable(self, collections: list[Collection]) -> list[Collection]:
        """The collections this system's library source publishes."""
        return [c for c in collections if config.source_applies(self.source, c.name)]

    @abstractmethod
    def read(self, collections: list[Collection]) -> list[DependencyRecord]:
        """Every dependency record this system has for ``collections``."""
