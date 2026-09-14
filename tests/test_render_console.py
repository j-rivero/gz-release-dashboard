import re

from rich.console import Console

from gz_release_dashboard import engine, snapshot as snap
from gz_release_dashboard.models import (
    Collection,
    DependencyRecord,
    FetchError,
    GroundTruthEntry,
    Library,
    PackageRecord,
    Status,
    StatusEntry,
)
from gz_release_dashboard.render import aggregate_cell, column_order, dependency_columns
from gz_release_dashboard.render import console as console_render


def entry(status, found=None, expected=None, platform="noble", arch="amd64"):
    return StatusEntry(
        collection="jetty", library="gz-sim", major=10, source="osrf_debian",
        channel="stable", platform=platform, arch=arch, status=status,
        found_version=found, expected_version=expected,
    )


def test_aggregate_cell_is_empty_without_entries():
    assert aggregate_cell([]) is None


def test_the_worst_status_wins():
    cell = aggregate_cell([
        entry(Status.UP_TO_DATE, "10.5.0"),
        entry(Status.MISSING, expected="10.5.0", arch="arm64"),
    ])
    assert cell.status is Status.MISSING
    # ...but the version the source does ship is still reported.
    assert cell.version == "10.5.0"
    assert (cell.worst_count, cell.total) == (1, 2)
    assert cell.mixed


def test_a_behind_cell_names_the_version_that_is_behind():
    cell = aggregate_cell([
        entry(Status.BEHIND, "10.4.0", "10.5.0"),
        entry(Status.BEHIND, "10.3.0", "10.5.0", arch="arm64"),
        entry(Status.UP_TO_DATE, "10.5.0", "10.5.0", arch="armhf"),
    ])
    assert (cell.status, cell.version, cell.expected) == (Status.BEHIND, "10.3.0", "10.5.0")


def test_not_expected_cells_are_left_out_of_the_ratio():
    cell = aggregate_cell([
        entry(Status.UP_TO_DATE, "10.5.0"),
        entry(Status.NOT_EXPECTED, arch="i386"),
    ])
    assert (cell.status, cell.total) == (Status.UP_TO_DATE, 1)
    assert not cell.mixed


def test_a_wholly_unexpected_cell_still_renders():
    cell = aggregate_cell([entry(Status.NOT_EXPECTED), entry(Status.NOT_EXPECTED, arch="i386")])
    assert cell.status is Status.NOT_EXPECTED


def test_column_order_expands_channels_and_ignores_unfetched_sources():
    assert column_order(["osrf_debian"]) == [
        ("osrf_debian", "stable"),
        ("osrf_debian", "prerelease"),
    ]
    assert column_order([]) == []


def test_column_order_keeps_only_the_sources_that_publish_the_collection():
    """Asked about a collection, it answers for that collection.

    fortress predates conda-forge and the ROS vendor packages, and is the only
    collection the ROS repositories carry the gz packages themselves for.
    """
    fetched = ["osrf_debian", "conda_forge", "ros_vendor", "ros_gz_debian"]
    assert column_order(fetched, "fortress") == [
        ("osrf_debian", "stable"),
        ("osrf_debian", "prerelease"),
        ("ros_gz_debian", "bootstrap"),
        ("ros_gz_debian", "stable"),
    ]
    assert column_order(fetched, "jetty") == [
        ("osrf_debian", "stable"),
        ("osrf_debian", "prerelease"),
        ("conda_forge", ""),
        ("ros_vendor", "ros2"),
        ("ros_vendor", "ros2-testing"),
    ]
    # Asked about no collection in particular, it still answers for all of them.
    assert len(column_order(fetched)) == 7


def build_snapshot():
    s = snap.new_snapshot(["osrf_debian"])
    s.collections = [
        Collection("jetty", False, [Library("gz-sim", 10), Library("gz-math", 9)]),
        Collection("m", True, [Library("gz-sim", 11)]),
    ]
    s.ground_truth = [
        GroundTruthEntry("gz-sim", 10, "10.5.0", None),
        GroundTruthEntry("gz-math", 9, "9.3.0", None),
        GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1"),
    ]
    s.records = [
        PackageRecord("osrf_debian", "stable", "noble", "amd64", "gz-sim", 10,
                      "gz-sim10", "10.5.0-1~noble", "10.5.0"),
        PackageRecord("osrf_debian", "stable", "noble", "amd64", "gz-math", 9,
                      "gz-math9", "9.1.0-1~noble", "9.1.0"),
        # The in-development collection only ever reaches the staging channel.
        PackageRecord("osrf_debian", "prerelease", "noble", "amd64", "gz-sim", 11,
                      "gz-sim11", "11.0.0~pre1-1~noble", "11.0.0-pre1"),
    ]
    s.errors = [FetchError("conda_forge", "connection reset")]
    return s


def render(**kwargs):
    snapshot = build_snapshot()
    entries = engine.compute_statuses(snapshot)
    console = Console(record=True, width=200, force_terminal=False)
    count = console_render.render(snapshot, entries, console, **kwargs)
    return count, console.export_text()


def test_render_shows_a_table_per_collection_with_glyphs():
    count, text = render()
    assert "jetty" in text and "m  [in development]" in text
    assert "gz-sim (10)" in text and "✅ 10.5.0" in text
    assert "🔶 9.1.0" in text and "→ 9.3.0" in text
    assert "✅ 11.0.0-pre1" in text


def test_render_lists_the_problems_and_counts_them():
    count, text = render()
    assert count == 1
    assert "problems (1)" in text
    assert "jetty/gz-math9 9.1.0 < 9.3.0 in osrf deb stable — noble/amd64" in text


def test_render_surfaces_fetch_errors():
    _, text = render()
    assert "fetch errors (1)" in text
    assert "conda_forge: connection reset" in text


def test_problems_only_hides_the_tables():
    _, text = render(problems_only=True)
    assert "problems (1)" in text
    assert "gz-sim (10)" not in text


def test_verbose_adds_the_per_platform_details():
    _, text = render(verbose=True)
    assert "details" in text
    assert "not expected" in text


def test_a_clean_snapshot_reports_no_problems():
    snapshot = build_snapshot()
    snapshot.records[1].upstream_version = "9.3.0"
    snapshot.errors = []
    console = Console(record=True, width=200)
    count = console_render.render(snapshot, engine.compute_statuses(snapshot), console)
    assert count == 0
    assert "every source matches the latest release" in console.export_text()


def test_problems_that_differ_only_by_platform_collapse_into_one_line():
    snapshot = build_snapshot()
    snapshot.records = [
        r for r in snapshot.records if (r.library, r.channel) != ("gz-math", "stable")
    ]
    for arch in ("amd64", "arm64", "armhf"):
        snapshot.records.append(
            PackageRecord("osrf_debian", "stable", "noble", arch, "gz-sim", 10,
                          "gz-sim10", "10.5.0-1~noble", "10.5.0"))
        snapshot.records.append(
            PackageRecord("osrf_debian", "stable", "noble", arch, "gz-math", 9,
                          "gz-math9", "9.1.0-1~noble", "9.1.0"))
    entries = engine.compute_statuses(snapshot)
    console = Console(record=True, width=200)
    count = console_render.render(snapshot, entries, console)
    text = console.export_text()
    # One finding, three platform cells.
    assert count == 3
    assert "problems (1, 3 platform cells)" in text
    assert "noble/amd64, noble/arm64, noble/armhf" in text


def test_a_collection_older_than_a_source_does_not_get_its_column():
    """The Bazel registry's oldest modules are ionic's majors.

    harmonic predates them, so the column was dots all the way down; ionic and
    everything after it keeps it.
    """
    fetched = ["osrf_debian", "bazel_registry"]
    assert ("bazel_registry", "") not in column_order(fetched, "harmonic")
    assert ("bazel_registry", "") in column_order(fetched, "ionic")


def dependency(name, system, version, platform, *, library="gz-physics", major=9,
               declared="", origin="osrf", channel=""):
    return DependencyRecord(
        collection="jetty", library=library, major=major, dependency=name,
        system=system, platform=platform, declared=declared, version=version,
        origin=origin, channel=channel,
    )


def build_dependency_snapshot():
    """``build_snapshot`` plus two of jetty's dependencies as they stand.

    dart diverges (◇): the Debian side ships 6.16 while conda-forge pins 6.19.
    ogre-next warns (⚠): osrf noble never got the 2.3.3 resolute has.
    """
    s = build_snapshot()
    s.sources_fetched = ["osrf_debian", "conda_forge"]
    s.dependencies = [
        dependency("dart", "deb", "6.16.6", "noble/amd64", declared="libdart6.16-dev"),
        dependency("dart", "conda", "6.19.4", "linux-64",
                   declared="dartsim-cpp >=6.19.4,<6.20.0a0", origin="conda-forge"),
        dependency("ogre-next", "deb", "2.3.1", "noble/amd64", library="gz-rendering",
                   major=10, declared="libogre-next-2.3-dev"),
        dependency("ogre-next", "deb", "2.3.3", "resolute/amd64", library="gz-rendering",
                   major=10, declared="libogre-next-2.3-dev"),
    ]
    return s


def render_dependencies(**kwargs):
    snapshot = build_dependency_snapshot()
    console = Console(record=True, width=200, force_terminal=False)
    count = console_render.render(
        snapshot, engine.compute_statuses(snapshot), console, **kwargs
    )
    return count, console.export_text()


def test_a_collection_gets_a_dependency_table_with_both_marks():
    _, text = render_dependencies()
    assert "dart ◇" in text
    assert "2.3.1–2.3.3 ⚠" in text
    assert "6.19.4" in text
    assert "ogre-next ◇" not in text


def test_dependency_columns_follow_the_order_and_reach_of_the_library_sources():
    fetched = ["osrf_debian", "conda_forge", "homebrew", "bazel_registry", "ros_vendor"]
    assert dependency_columns(fetched, "jetty") == [
        ("deb", "stable"), ("deb", "prerelease"), ("bazel", ""), ("conda", ""), ("brew", ""),
        ("ros", ""),
    ]
    # harmonic predates the Bazel modules, for its dependencies as for its libraries.
    assert ("bazel", "") not in dependency_columns(fetched, "harmonic")
    assert dependency_columns(["osrf_debian"], "jetty") == [
        ("deb", "stable"), ("deb", "prerelease"),
    ]


def test_problems_only_prints_no_dependency_table():
    _, text = render_dependencies(problems_only=True)
    assert "dart" not in text


def test_verbose_details_what_each_build_declares():
    _, text = render_dependencies(verbose=True)
    assert "libogre-next-2.3-dev" in text
    assert "dartsim-cpp >=6.19.4,<6.20.0a0" in text
    assert "gz-rendering10" in text


def test_the_legend_explains_the_dependency_marks_once_there_are_dependencies():
    _, text = render_dependencies()
    assert "⚠ a system disagrees with itself" in text
    assert "◇ systems on different series" in text
    _, plain = render()
    assert "◇" not in plain


def test_dependencies_never_count_as_problems():
    snapshot = build_dependency_snapshot()
    entries = engine.compute_statuses(snapshot)
    with_them = console_render.render(snapshot, entries, Console(record=True, width=200))
    snapshot.dependencies = []
    without = console_render.render(snapshot, entries, Console(record=True, width=200))
    assert with_them == without


def test_a_dependency_queued_in_prerelease_gets_a_deb_column_of_its_own():
    """osrf prerelease holds zenoh 1.8.0 while stable has 1.5.0, as of 2026-09-14."""
    snapshot = build_dependency_snapshot()
    for channel, version in (("stable", "1.5.0"), ("prerelease", "1.8.0")):
        snapshot.dependencies.append(
            dependency("zenoh", "deb", version, "noble/amd64", library="gz-transport",
                       major=15, declared="libzenohc-dev", channel=channel)
        )
    console = Console(record=True, width=200, force_terminal=False)
    console_render.render(snapshot, engine.compute_statuses(snapshot), console)
    text = console.export_text()
    assert re.search(r"│ zenoh\s+│ 1\.5\.0\s+│ 1\.8\.0\s+│ ·", text)
    # The warning stays in the stable column, the one that is compared.
    assert re.search(r"│ ogre-next\s+│ 2\.3\.1–2\.3\.3 ⚠\s+│ ·\s+│ ·", text)
