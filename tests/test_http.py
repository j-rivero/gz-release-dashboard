import pytest
import requests

from gz_release_dashboard.http import HttpClient


class Response:
    """The slice of ``requests.Response`` that HttpClient reads."""

    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def client_serving(responses: dict[str, Response]) -> tuple[HttpClient, list[str]]:
    """A real client whose network stops at ``session.get``."""
    client = HttpClient()
    calls: list[str] = []

    def get(url, timeout):
        calls.append(url)
        return responses[url]

    client.session.get = get
    return client, calls


def test_a_url_is_downloaded_once_per_client():
    client, calls = client_serving({"http://x/Packages": Response(200, b"body")})
    assert client.get_text("http://x/Packages") == "body"
    assert client.get_text("http://x/Packages") == "body"
    assert calls == ["http://x/Packages"]


def test_a_404_is_remembered_as_well():
    client, calls = client_serving({"http://x/missing": Response(404)})
    assert client.get_text("http://x/missing", ok_404=True) is None
    assert client.get_text("http://x/missing", ok_404=True) is None
    assert calls == ["http://x/missing"]


def test_a_remembered_404_still_raises_where_404_is_not_ok():
    client, _ = client_serving({"http://x/missing": Response(404)})
    assert client.get_text("http://x/missing", ok_404=True) is None
    with pytest.raises(requests.HTTPError):
        client.get_text("http://x/missing")


def test_separate_clients_do_not_share_what_they_remember():
    responses = {"http://x/a": Response(200, b"body")}
    first, first_calls = client_serving(responses)
    second, second_calls = client_serving(responses)
    first.get_text("http://x/a")
    second.get_text("http://x/a")
    assert first_calls == ["http://x/a"] and second_calls == ["http://x/a"]
