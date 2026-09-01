import json

import pytest
from click.testing import CliRunner
from conftest import fixture_text

from gz_release_dashboard import cli, config, ground_truth, snapshot as snap
from gz_release_dashboard.sources.debian_repo import packages_url


@pytest.fixture
def offline(monkeypatch):
    """Point every network call at the fixtures."""
    bodies = {
        config.COLLECTIONS_YAML_URL: fixture_text("gz-collections.yaml").encode(),
    }
    gzipped = {
        packages_url(config.OSRF_DEB_BASE, "ubuntu-stable", "noble", "amd64"):
            fixture_text("osrf-packages-stable.txt"),
    }
    import gzip

    for url, text in gzipped.items():
        bodies[url] = gzip.compress(text.encode())

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def get_bytes(self, url, *, ok_404=False):
            if url in bodies:
                return bodies[url]
            if ok_404:
                return None
            raise AssertionError(f"unexpected request to {url}")

        def get_text(self, url, *, ok_404=False):
            body = self.get_bytes(url, ok_404=ok_404)
            return None if body is None else body.decode()

        def get_json(self, url, *, ok_404=False):
            text = self.get_text(url, ok_404=ok_404)
            return None if text is None else json.loads(text)

        def get_gzip_text(self, url, *, ok_404=False):
            body = self.get_bytes(url, ok_404=ok_404)
            return None if body is None else gzip.decompress(body).decode()

    monkeypatch.setattr(cli, "HttpClient", Client)
    monkeypatch.setattr(
        ground_truth, "run_ls_remote", lambda url: fixture_text("ls-remote-gz-sim.txt")
    )


@pytest.fixture
def runner():
    return CliRunner()


def test_help_lists_every_command(runner):
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    for command in ("fetch", "console", "html", "all"):
        assert command in result.output


def test_source_choices_come_from_the_registry(runner):
    result = runner.invoke(cli.main, ["fetch", "--help"])
    for source in ("osrf_debian", "conda_forge", "homebrew", "bazel_registry", "ros_vendor"):
        assert source in result.output


def test_fetch_writes_a_snapshot(runner, offline, tmp_path):
    target = tmp_path / "snapshot.json"
    result = runner.invoke(
        cli.main, ["fetch", "-o", str(target), "--source", "osrf_debian"]
    )
    assert result.exit_code == 0, result.output
    snapshot = snap.load(target)
    assert snapshot.sources_fetched == ["osrf_debian"]
    assert {c.name for c in snapshot.collections} == {"fortress", "jetty", "m"}
    assert snapshot.records


def test_fetch_can_be_narrowed_to_one_collection(runner, offline, tmp_path):
    target = tmp_path / "snapshot.json"
    result = runner.invoke(
        cli.main,
        ["fetch", "-o", str(target), "--source", "osrf_debian", "--collection", "jetty"],
    )
    assert result.exit_code == 0, result.output
    assert [c.name for c in snap.load(target).collections] == ["jetty"]


def test_fetch_rejects_an_unknown_collection(runner, offline, tmp_path):
    result = runner.invoke(
        cli.main, ["fetch", "-o", str(tmp_path / "s.json"), "--collection", "nope"]
    )
    assert result.exit_code != 0
    assert "no collection matched" in result.output


def test_a_failing_source_is_recorded_but_not_fatal(runner, offline, tmp_path, monkeypatch):
    from gz_release_dashboard.sources.osrf_debian import OsrfDebianSource

    def boom(self, collections):
        raise RuntimeError("repo down")

    monkeypatch.setattr(OsrfDebianSource, "fetch", boom)
    target = tmp_path / "snapshot.json"
    result = runner.invoke(
        cli.main, ["fetch", "-o", str(target), "--source", "bazel_registry"]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        cli.main, ["fetch", "-o", str(target), "--source", "osrf_debian"]
    )
    assert result.exit_code != 0
    assert "every source failed" in result.output


@pytest.fixture
def snapshot_file(runner, offline, tmp_path):
    target = tmp_path / "snapshot.json"
    runner.invoke(cli.main, ["fetch", "-o", str(target), "--source", "osrf_debian"])
    return target


def test_console_renders_a_snapshot(runner, snapshot_file):
    result = runner.invoke(cli.main, ["console", str(snapshot_file)])
    assert result.exit_code == 0, result.output
    assert "jetty" in result.output
    assert "gz-sim" in result.output


def test_console_filters(runner, snapshot_file):
    result = runner.invoke(
        cli.main, ["console", str(snapshot_file), "--collection", "jetty", "--lib", "gz-sim"]
    )
    assert result.exit_code == 0, result.output
    assert "gz-math" not in result.output
    assert "fortress" not in result.output


def test_console_problems_only(runner, snapshot_file):
    result = runner.invoke(cli.main, ["console", str(snapshot_file), "--problems-only"])
    assert result.exit_code == 0, result.output
    assert "problems" in result.output
    assert "library" not in result.output


def test_a_healthy_snapshot_passes_the_gate(runner, snapshot_file):
    result = runner.invoke(cli.main, ["console", str(snapshot_file), "--fail-on-problems"])
    assert result.exit_code == 0, result.output


def test_fail_on_problems_sets_the_exit_code(runner, tmp_path):
    from test_render_console import build_snapshot

    target = snap.save(build_snapshot(), tmp_path / "problems.json")
    plain = runner.invoke(cli.main, ["console", str(target)])
    strict = runner.invoke(cli.main, ["console", str(target), "--fail-on-problems"])
    assert plain.exit_code == 0
    assert strict.exit_code == 1
    assert "gz-math9 9.1.0 < 9.3.0" in strict.output


def test_html_writes_the_page_and_the_snapshot(runner, snapshot_file, tmp_path):
    out = tmp_path / "public"
    result = runner.invoke(cli.main, ["html", str(snapshot_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "index.html").exists()
    assert (out / "snapshot.json").exists()


def test_all_fetches_and_publishes_in_one_go(runner, offline, tmp_path):
    out = tmp_path / "public"
    result = runner.invoke(
        cli.main, ["all", "-o", str(out), "--source", "osrf_debian"]
    )
    assert result.exit_code == 0, result.output
    page = (out / "index.html").read_text()
    assert "Gazebo release dashboard" in page
    assert "problems" in result.output
