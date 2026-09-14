"""A small requests wrapper: retries, a real UA and an optional disk cache."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config


class HttpClient:
    """Fetch URLs, memoising bodies for the life of the client and optionally on disk.

    ``ok_404`` turns "not found" into ``None`` instead of an exception: most
    sources are probed by guessing package names, so 404 is a normal answer.

    The in-memory memo is what lets the dependency readers walk the same
    Packages.gz indexes, formulas and anaconda documents the library sources
    already downloaded, without downloading them again.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        timeout: int = config.HTTP_TIMEOUT,
        retries: int = config.HTTP_RETRIES,
        user_agent: str = config.USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        retry = Retry(
            total=retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        #: url -> body, or None for a 404. Failures are never remembered.
        self._memo: dict[str, bytes | None] = {}

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / hashlib.sha256(url.encode()).hexdigest()

    def get_bytes(self, url: str, *, ok_404: bool = False) -> bytes | None:
        if url not in self._memo:
            self._memo[url] = self._fetch(url, ok_404=ok_404)
        body = self._memo[url]
        if body is None and not ok_404:
            # Remembered from a caller that allowed it; this one does not.
            raise requests.HTTPError(f"404 Client Error: Not Found for url: {url}")
        return body

    def _fetch(self, url: str, *, ok_404: bool) -> bytes | None:
        cached = self._cache_path(url)
        if cached and cached.exists():
            body = cached.read_bytes()
            return None if body == b"\x00404" else body
        response = self.session.get(url, timeout=self.timeout)
        if ok_404 and response.status_code == 404:
            if cached:
                cached.write_bytes(b"\x00404")
            return None
        response.raise_for_status()
        if cached:
            cached.write_bytes(response.content)
        return response.content

    def get_text(self, url: str, *, ok_404: bool = False) -> str | None:
        body = self.get_bytes(url, ok_404=ok_404)
        return None if body is None else body.decode("utf-8", errors="replace")

    def get_json(self, url: str, *, ok_404: bool = False) -> Any | None:
        body = self.get_text(url, ok_404=ok_404)
        return None if body is None else json.loads(body)

    def get_gzip_text(self, url: str, *, ok_404: bool = False) -> str | None:
        """Fetch and inflate a ``.gz`` body (the Debian ``Packages.gz`` files)."""
        body = self.get_bytes(url, ok_404=ok_404)
        if body is None:
            return None
        return gzip.decompress(body).decode("utf-8", errors="replace")
