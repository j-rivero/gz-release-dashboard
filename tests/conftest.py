from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeHttpClient:
    """Dict-backed stand-in for :class:`HttpClient`; the factory injects it."""

    def __init__(self, bodies: dict[str, bytes | str] | None = None):
        self.bodies: dict[str, bytes] = {}
        for url, body in (bodies or {}).items():
            self.bodies[url] = body.encode() if isinstance(body, str) else body
        self.requested: list[str] = []

    def add(self, url: str, body: bytes | str) -> "FakeHttpClient":
        self.bodies[url] = body.encode() if isinstance(body, str) else body
        return self

    def add_gzip(self, url: str, text: str) -> "FakeHttpClient":
        import gzip

        self.bodies[url] = gzip.compress(text.encode())
        return self

    def get_bytes(self, url: str, *, ok_404: bool = False):
        self.requested.append(url)
        if url in self.bodies:
            return self.bodies[url]
        if ok_404:
            return None
        raise AssertionError(f"unexpected request to {url}")

    def get_text(self, url: str, *, ok_404: bool = False):
        body = self.get_bytes(url, ok_404=ok_404)
        return None if body is None else body.decode()

    def get_json(self, url: str, *, ok_404: bool = False):
        import json

        text = self.get_text(url, ok_404=ok_404)
        return None if text is None else json.loads(text)

    def get_gzip_text(self, url: str, *, ok_404: bool = False):
        import gzip

        body = self.get_bytes(url, ok_404=ok_404)
        return None if body is None else gzip.decompress(body).decode()


@pytest.fixture
def http():
    return FakeHttpClient()


@pytest.fixture
def collections():
    from gz_release_dashboard.collections_yaml import parse_collections

    return parse_collections(fixture_text("gz-collections.yaml"))
