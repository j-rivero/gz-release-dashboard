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
        packages_url(config.OSRF_DEB_CHANNELS["stable"], "noble", "amd64"):
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


def test_a_narrowed_view_scores_the_same_as_the_whole_dashboard(runner, tmp_path):
    """`--collection` must not change any verdict, only which ones are shown.

    Rolling belongs to the newest collection, so scoring a snapshot narrowed to
    jetty would make jetty the newest one there is and hand it Rolling -- a
    view that quietly disagreed with the dashboard it was cut from.
    """
    from gz_release_dashboard import engine
    from gz_release_dashboard.models import Collection, GroundTruthEntry, Library, PackageRecord

    def vendor(library, major, version, rosdistro):
        return PackageRecord(
            source="ros_vendor", channel="ros2", platform=f"{rosdistro}@noble",
            arch="amd64", library=library, major=major, pkg_name=f"{library}{major}",
            raw_version=version, upstream_version=version,
        )

    s = snap.new_snapshot(["ros_vendor"])
    s.collections = [
        Collection("jetty", False, [Library("gz-sim", 10), Library("gz-math", 9)]),
        Collection("m", True, [Library("gz-sim", 11), Library("gz-math", 10)]),
    ]
    s.ground_truth = [
        GroundTruthEntry("gz-sim", 10, "10.5.0", None),
        GroundTruthEntry("gz-math", 9, "9.3.0", None),
        GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1"),
        GroundTruthEntry("gz-math", 10, None, "10.0.0-pre1"),
    ]
    s.records = [
        vendor("gz-sim", 10, "10.1.1", "rolling"),   # jetty's, left behind
        vendor("gz-math", 9, "9.1.0", "rolling"),
        vendor("gz-sim", 11, "11.0.0-pre1", "rolling"),
        vendor("gz-math", 10, "10.0.0-pre1", "rolling"),
    ]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snap.to_dict(s)))

    whole = [e for e in engine.compute_statuses(snap.load(path)) if e.collection == "jetty"]
    _, narrowed, _ = cli._filtered(snap.load(path), ("jetty",), (), ())
    assert narrowed == whole
    assert not any(e.platform.startswith("rolling") for e in narrowed)


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


def test_a_collection_restricted_source_is_only_handed_its_collections():
    """What a Debian source is asked for follows from the collections it gets.

    The distributions to query are derived from the collections, so handing the
    ROS gz import every collection would have it download noble and resolute
    indexes that cannot hold anything for it.
    """
    from gz_release_dashboard.models import Collection, Library

    collections = [
        Collection("fortress", False, [Library("gz-sim", 6)], ["jammy"]),
        Collection("jetty", False, [Library("gz-sim", 10)], ["noble"]),
    ]
    narrowed = cli._collections_for("ros_gz_debian", collections)
    assert [c.name for c in narrowed] == ["fortress"]
    # Every other source keeps the whole list, untouched.
    assert cli._collections_for("osrf_debian", collections) is collections


@pytest.fixture
def fake_readers(monkeypatch):
    """A deb reader with one record and one alias warning, and a conda reader."""
    from gz_release_dashboard import deps
    from gz_release_dashboard.deps.base import DependencyReader
    from gz_release_dashboard.models import DependencyRecord, FetchError

    class Deb(DependencyReader):
        system = "deb"

        def read(self, collections):
            self.errors.append(FetchError("deps:aliases", "libfoo-dev has no alias"))
            return [
                DependencyRecord(
                    collection=c.name, library="gz-physics", major=9, dependency="dart",
                    system="deb", platform="noble/amd64", declared="libdart6.16-dev",
                    version="6.16.6", origin="osrf",
                )
                for c in collections
            ]

    class Conda(DependencyReader):
        system = "conda"

        def read(self, collections):
            raise AssertionError("conda_forge was not selected")

    monkeypatch.setattr(deps, "_REGISTRY", {"deb": Deb, "conda": Conda})
    return {"deb": Deb, "conda": Conda}


def test_fetch_reads_the_dependencies_of_the_selected_sources(
    runner, offline, fake_readers, tmp_path
):
    target = tmp_path / "snapshot.json"
    result = runner.invoke(
        cli.main,
        ["fetch", "-o", str(target), "--source", "osrf_debian", "--collection", "jetty"],
    )
    assert result.exit_code == 0, result.output
    snapshot = snap.load(target)
    assert [(d.collection, d.dependency, d.system) for d in snapshot.dependencies] == [
        ("jetty", "dart", "deb")
    ]
    sources = {e.source for e in snapshot.errors}
    assert "deps:aliases" in sources
    assert "deps:conda" not in sources


def test_a_failing_reader_is_recorded_but_fails_nothing_else(
    runner, offline, fake_readers, tmp_path, monkeypatch
):
    def boom(self, collections):
        raise RuntimeError("raw.githubusercontent down")

    monkeypatch.setattr(fake_readers["deb"], "read", boom)
    target = tmp_path / "snapshot.json"
    result = runner.invoke(
        cli.main, ["fetch", "-o", str(target), "--source", "osrf_debian"]
    )
    assert result.exit_code == 0, result.output
    snapshot = snap.load(target)
    assert snapshot.records
    assert any(
        e.source == "deps:deb" and "raw.githubusercontent down" in e.message
        for e in snapshot.errors
    )


@pytest.fixture
def dependency_snapshot_file(tmp_path):
    from test_render_console import build_dependency_snapshot

    return snap.save(build_dependency_snapshot(), tmp_path / "deps.json")


def test_narrowing_to_one_source_keeps_the_divergence_mark(runner, dependency_snapshot_file):
    _, _, rows = cli._filtered(snap.load(dependency_snapshot_file), (), ("osrf_debian",), ())
    [dart] = [r for r in rows if r.dependency == "dart"]
    assert set(dart.cells) == {"deb"}
    assert dart.diverges
    result = runner.invoke(
        cli.main, ["console", str(dependency_snapshot_file), "--source", "osrf_debian"]
    )
    assert result.exit_code == 0, result.output
    assert "dart ◇" in result.output
    assert "6.19.4" not in result.output


def test_lib_keeps_the_dependencies_that_library_declares(dependency_snapshot_file):
    snapshot, _, rows = cli._filtered(
        snap.load(dependency_snapshot_file), (), (), ("gz-rendering",)
    )
    assert [r.dependency for r in rows] == ["ogre-next"]
    assert {d.library for d in snapshot.dependencies} == {"gz-rendering"}


def test_collection_keeps_only_that_collections_dependencies(dependency_snapshot_file):
    snapshot, _, rows = cli._filtered(snap.load(dependency_snapshot_file), ("m",), (), ())
    assert rows == []
    assert snapshot.dependencies == []


def test_a_dependency_warning_never_fails_the_gate(runner, tmp_path):
    from test_render_console import build_dependency_snapshot

    snapshot = build_dependency_snapshot()
    snapshot.sources_fetched = ["osrf_debian"]
    snapshot.records[1].upstream_version = "9.3.0"
    target = snap.save(snapshot, tmp_path / "deps.json")
    result = runner.invoke(cli.main, ["console", str(target), "--fail-on-problems"])
    assert result.exit_code == 0, result.output
    assert "2.3.1–2.3.3 ⚠" in result.output
